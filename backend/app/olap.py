from datetime import date, datetime

from clickhouse_driver import Client

from .config import Settings

REPORT_METRICS = (
    "total_sessions",
    "total_movements",
    "active_hours",
    "avg_response_time_ms",
    "slow_responses",
    "avg_signal_quality",
    "avg_battery_level",
    "last_activity",
)


class OlapError(Exception):
    pass


class OlapClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _connect(self) -> Client:
        try:
            return Client(
                host=self._settings.clickhouse_host,
                port=self._settings.clickhouse_port,
                database=self._settings.clickhouse_database,
            )
        except Exception as exc:
            raise OlapError(
                f"Cannot connect to ClickHouse {self._settings.clickhouse_host}:{self._settings.clickhouse_port}"
            ) from exc

    @staticmethod
    def _execute(client: Client, sql: str, params: dict) -> list:
        try:
            return client.execute(sql, params)
        except Exception as exc:
            raise OlapError(f"OLAP query failed: {exc}") from exc

    @staticmethod
    def _round(value) -> float | int:
        if isinstance(value, float):
            return round(value, 2)
        return value

    def get_latest_telemetry_day(self) -> date | None:
        client = self._connect()
        try:
            rows = self._execute(
                client,
                "SELECT max(toDate(recorded_at)) FROM bionicpro.telemetry",
                {},
            )
        finally:
            client.disconnect()
        return rows[0][0] if rows and rows[0][0] is not None else None

    def get_report(self, email: str, report_date: date | None = None) -> dict | None:
        client = self._connect()
        try:
            if report_date is None:
                rows = self._execute(
                    client,
                    "SELECT max(report_date) FROM bionicpro.report_mart FINAL WHERE email = %(email)s",
                    {"email": email},
                )
                latest = rows[0][0] if rows and rows[0][0] is not None else None
                if latest is None:
                    return None
                report_date = latest

            columns = ", ".join(REPORT_METRICS)
            rows = self._execute(
                client,
                f"""
                SELECT
                    first_name, last_name,
                    {columns}
                FROM bionicpro.report_mart FINAL
                WHERE email = %(email)s AND report_date = toDate(%(date)s)
                """,
                {"email": email, "date": report_date.isoformat()},
            )
        finally:
            client.disconnect()

        if not rows:
            return None

        row = rows[0]
        metrics = {key: self._round(value) for key, value in zip(REPORT_METRICS, row[2:])}
        metrics["last_activity"] = (
            row[-1].isoformat(sep=" ") if isinstance(row[-1], datetime) else str(row[-1])
        )
        return {
            "email": email,
            "first_name": row[0],
            "last_name": row[1],
            "report_date": report_date.isoformat() if isinstance(report_date, date) else str(report_date),
            "metrics": metrics,
        }