import csv
import io
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from .auth import Identity, TokenVerifier, resolve_identity
from .config import Settings
from .olap import REPORT_METRICS, OlapClient, OlapError


def build_reports_router(settings: Settings, olap: OlapClient, verifier: TokenVerifier) -> APIRouter:
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

    safe_email = re.sub(r"[^\w.@+-]", "_", report["email"])
    safe_date = re.sub(r"[^\w-]", "_", report["report_date"])
    filename = f"report_{safe_email}_{safe_date}.csv"
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )