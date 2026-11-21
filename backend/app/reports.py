import csv
import io
import re
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from .airflow import AirflowClient, AirflowError
from .auth import Identity, TokenVerifier, resolve_identity
from .config import Settings
from .olap import REPORT_METRICS, OlapClient, OlapError


def _safe_email_slug(email: str) -> str:
    return re.sub(r"[^\w.-]", "_", email)


def build_reports_router(
    settings: Settings, olap: OlapClient, verifier: TokenVerifier, airflow: AirflowClient
) -> APIRouter:
    router = APIRouter()

    def current_identity(request: Request) -> Identity:
        return resolve_identity(request, verifier, settings)

    @router.get("/reports")
    def get_report(
        identity: Identity = Depends(current_identity),
        user: str | None = Query(default=None, alias="user", description="Email of the report owner; allowed only if it matches the authenticated user"),
        date_param: str | None = Query(default=None, alias="date", description="Report date as YYYY-MM-DD; defaults to the latest available"),
        output_format: str = Query(default="json", alias="format", pattern="^(json|csv)$"),
    ):
        if user and user.strip().lower() != identity.email:
            raise HTTPException(status_code=403, detail="Access to another user's report is forbidden")

        report_date: date | None = None
        if date_param is not None:
            try:
                report_date = date.fromisoformat(date_param)
            except ValueError:
                raise HTTPException(status_code=400, detail="'date' must be in YYYY-MM-DD format")

        try:
            report = olap.get_report(identity.email, report_date)
        except OlapError as exc:
            raise HTTPException(status_code=503, detail=f"OLAP storage unavailable: {exc}") from exc

        if report is None:
            detail = f"No report found for user {identity.email}"
            if date_param:
                detail += f" on {date_param}"
            raise HTTPException(status_code=404, detail=detail)

        if output_format == "csv":
            return _build_csv(report)
        return report

    @router.post("/reports/generate")
    def generate_report(identity: Identity = Depends(current_identity)):
        try:
            target_day = olap.get_latest_telemetry_day()
        except OlapError as exc:
            raise HTTPException(status_code=503, detail=f"OLAP storage unavailable: {exc}") from exc

        if target_day is None:
            raise HTTPException(
                status_code=409,
                detail="Nothing to generate: no telemetry data in ClickHouse",
            )
        if target_day >= datetime.now(timezone.utc).date():
            raise HTTPException(
                status_code=409,
                detail="Latest telemetry is from today; the day interval is not complete yet",
            )

        report_date_iso = target_day.isoformat()
        safe_email = _safe_email_slug(identity.email)
        dag_run_id = (
            f"generate_{safe_email}_{target_day.strftime('%Y%m%d')}_{uuid.uuid4().hex[:6]}"
        )

        try:
            runs = airflow.get_runs_for_date(report_date_iso)
        except AirflowError as exc:
            raise HTTPException(status_code=exc.status_code, detail=f"Report generation failed: {exc}") from exc

        for run in runs:
            state = run.get("state")
            if state == "success":
                return JSONResponse(
                    status_code=200,
                    content={
                        "status": "already_generated",
                        "dag_run_id": run.get("dag_run_id"),
                        "report_date": report_date_iso,
                    },
                )
            if state in ("queued", "running"):
                return JSONResponse(
                    status_code=202,
                    content={
                        "status": "in_progress",
                        "dag_run_id": run.get("dag_run_id"),
                        "report_date": report_date_iso,
                    },
                )
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Previous generation run {run.get('dag_run_id')} is {state}; "
                    "resolve it in the Airflow UI before retrying"
                ),
            )

        try:
            run = airflow.trigger_dag_run(dag_run_id, report_date_iso)
        except AirflowError as exc:
            if exc.status_code == 409:
                return JSONResponse(
                    status_code=202,
                    content={
                        "status": "in_progress",
                        "dag_run_id": dag_run_id,
                        "report_date": report_date_iso,
                    },
                )
            raise HTTPException(
                status_code=exc.status_code,
                detail=f"Report generation failed: {exc}",
            ) from exc

        return JSONResponse(
            status_code=202,
            content={
                "status": "started",
                "dag_run_id": run.get("dag_run_id"),
                "report_date": report_date_iso,
            },
        )

    @router.get("/health")
    def health():
        return {"status": "ok"}

    return router


def _build_csv(report: dict) -> Response:
    header = ["email", "report_date", *REPORT_METRICS]
    row = [report["email"], report["report_date"], *[report["metrics"][key] for key in REPORT_METRICS]]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerow(row)

    safe_email = _safe_email_slug(report["email"])
    safe_date = re.sub(r"[^\w-]", "_", report["report_date"])
    filename = f"report_{safe_email}_{safe_date}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )