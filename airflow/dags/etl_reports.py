import logging
import os
from datetime import datetime, timedelta, timezone

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from clickhouse_driver import Client as ClickHouseClient


logger = logging.getLogger(__name__)


CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "9000"))
CRM_POSTGRES_CONN_ID = os.getenv("CRM_POSTGRES_CONN_ID", "crm_postgres")
TELEMETRY_POSTGRES_CONN_ID = os.getenv("TELEMETRY_POSTGRES_CONN_ID", "telemetry_postgres")

default_args = {
    "owner": "bionicpro",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def get_clickhouse_client():
    return ClickHouseClient(host=CLICKHOUSE_HOST, port=CLICKHOUSE_PORT)


def extract_crm_customers(**context):
    hook = PostgresHook(postgres_conn_id=CRM_POSTGRES_CONN_ID)
    records = hook.get_records(
        """
        SELECT id, first_name, last_name, email, phone, created_at, updated_at
        FROM customers
        WHERE updated_at >= %(since)s AND updated_at < %(until)s
        """,
        parameters={
            "since": context["data_interval_start"],
            "until": context["data_interval_end"],
        },
    )
    context["ti"].xcom_push(key="customers", value=records)


def extract_telemetry(**context):
    hook = PostgresHook(postgres_conn_id=TELEMETRY_POSTGRES_CONN_ID)
    records = hook.get_records(
        """
        SELECT
            id, customer_id,
            signal_quality, battery_level, response_time_ms,
            session_duration_sec, movements_count,
            recorded_at
        FROM telemetry
        WHERE recorded_at >= %(since)s AND recorded_at < %(until)s
        """,
        parameters={
            "since": context["data_interval_start"],
            "until": context["data_interval_end"],
        },
    )
    context["ti"].xcom_push(key="telemetry", value=records)


def load_customers_to_clickhouse(**context):
    client = get_clickhouse_client()
    try:
        client.execute("CREATE DATABASE IF NOT EXISTS bionicpro")
        client.execute(
            """
            CREATE TABLE IF NOT EXISTS bionicpro.customers (
                id          UInt64,
                first_name  String,
                last_name   String,
                email       String,
                phone       String,
                created_at  DateTime,
                updated_at  DateTime
            ) ENGINE = ReplacingMergeTree(updated_at)
            ORDER BY id
            """
        )
    finally:
        client.disconnect()

    rows = context["ti"].xcom_pull(key="customers", task_ids="extract_crm_customers")
    if not rows:
        return

    client = get_clickhouse_client()
    try:
        client.execute("INSERT INTO bionicpro.customers VALUES", rows)
    finally:
        client.disconnect()


def load_telemetry_to_clickhouse(**context):
    client = get_clickhouse_client()
    try:
        client.execute("CREATE DATABASE IF NOT EXISTS bionicpro")
        client.execute(
            """
            CREATE TABLE IF NOT EXISTS bionicpro.telemetry (
                id                   UInt64,
                customer_id          UInt64,
                signal_quality       Float32,
                battery_level        Float32,
                response_time_ms     Float32,
                session_duration_sec UInt32,
                movements_count      UInt32,
                recorded_at          DateTime
            ) ENGINE = ReplacingMergeTree()
            ORDER BY (customer_id, recorded_at, id)
            """
        )
    finally:
        client.disconnect()

    rows = context["ti"].xcom_pull(key="telemetry", task_ids="extract_telemetry")
    if not rows:
        return

    client = get_clickhouse_client()
    try:
        client.execute("INSERT INTO bionicpro.telemetry VALUES", rows)
    finally:
        client.disconnect()


def build_report_mart(**context):
    interval_start = context["data_interval_start"]
    interval_end = context["data_interval_end"]
    if interval_end > datetime.now(timezone.utc):
        logger.warning(
            "Interval %s..%s has not elapsed yet, skipping mart build",
            interval_start,
            interval_end,
        )
        return
    report_date = interval_start.strftime("%Y-%m-%d")

    client = get_clickhouse_client()
    try:
        client.execute(
            """
            CREATE TABLE IF NOT EXISTS bionicpro.report_mart (
                customer_id        UInt64,
                email              String,
                first_name         String,
                last_name          String,
                report_date        Date,
                total_sessions     UInt64,
                total_movements    UInt64,
                active_hours       Float64,
                avg_response_time_ms Float64,
                slow_responses     UInt64,
                avg_signal_quality Float64,
                avg_battery_level  Float64,
                last_activity      DateTime
            ) ENGINE = ReplacingMergeTree(report_date)
            ORDER BY (email, report_date)
            """
        )
        client.execute(
            "ALTER TABLE bionicpro.report_mart DELETE WHERE report_date = toDate(%(report_date)s)",
            {"report_date": report_date},
        )
        client.execute(
            """
            INSERT INTO bionicpro.report_mart
            SELECT
                t.customer_id,
                c.email,
                c.first_name,
                c.last_name,
                toDate(%(report_date)s)         AS report_date,
                count()                         AS total_sessions,
                sum(t.movements_count)          AS total_movements,
                sum(t.session_duration_sec) / 3600.0 AS active_hours,
                avg(t.response_time_ms)         AS avg_response_time_ms,
                countIf(t.response_time_ms > 100) AS slow_responses,
                avg(t.signal_quality)           AS avg_signal_quality,
                avg(t.battery_level)            AS avg_battery_level,
                max(t.recorded_at)              AS last_activity
            FROM (
                SELECT *
                FROM bionicpro.telemetry
                FINAL
            ) AS t
            JOIN (
                SELECT *
                FROM bionicpro.customers
                FINAL
            ) AS c ON t.customer_id = c.id
            WHERE t.recorded_at >= %(start)s AND t.recorded_at < %(end)s
            GROUP BY
                t.customer_id, c.email, c.first_name, c.last_name
            """,
            {
                "report_date": report_date,
                "start": interval_start,
                "end": interval_end,
            },
        )
        built = client.execute(
            "SELECT count() FROM bionicpro.report_mart WHERE report_date = toDate(%(report_date)s)",
            {"report_date": report_date},
        )
        logger.info(
            "Mart for %s: %s rows built (interval %s..%s)",
            report_date,
            built[0][0],
            interval_start,
            interval_end,
        )
    finally:
        client.disconnect()


with DAG(
    dag_id="bionicpro_etl_reports",
    default_args=default_args,
    description="ETL: CRM + телеметрия -> ClickHouse -> витрина отчётности",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["bionicpro", "etl", "reports"],
) as dag:

    t_extract_crm = PythonOperator(
        task_id="extract_crm_customers",
        python_callable=extract_crm_customers,
    )

    t_extract_telemetry = PythonOperator(
        task_id="extract_telemetry",
        python_callable=extract_telemetry,
    )

    t_load_customers = PythonOperator(
        task_id="load_customers_to_clickhouse",
        python_callable=load_customers_to_clickhouse,
    )

    t_load_telemetry = PythonOperator(
        task_id="load_telemetry_to_clickhouse",
        python_callable=load_telemetry_to_clickhouse,
    )

    t_build_mart = PythonOperator(
        task_id="build_report_mart",
        python_callable=build_report_mart,
    )

    t_extract_crm >> t_load_customers >> t_build_mart
    t_extract_telemetry >> t_load_telemetry >> t_build_mart