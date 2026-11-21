import httpx

from .config import Settings


class AirflowError(Exception):
    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.status_code = status_code


class AirflowClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.airflow_url.rstrip("/")
        self._auth = (
            (settings.airflow_username, settings.airflow_password or "")
            if settings.airflow_username
            else None
        )

    def _dag_url(self, *parts: str) -> str:
        base = f"{self._base_url}/api/v1/dags/{self._settings.airflow_dag_id}"
        return "/".join([base, *parts]) if parts else base

    def get_runs_for_date(self, logical_date: str) -> list[dict]:
        try:
            resp = httpx.get(
                self._dag_url("dagRuns"),
                params={
                    "execution_date_gte": f"{logical_date}T00:00:00Z",
                    "execution_date_lte": f"{logical_date}T23:59:59Z",
                    "order_by": "-execution_date",
                },
                auth=self._auth,
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise AirflowError(f"Airflow unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise AirflowError(
                f"Airflow API error {resp.status_code}: {resp.text[:300]}",
                status_code=503 if resp.status_code >= 500 else 502,
            )
        return resp.json().get("dag_runs", [])

    def trigger_dag_run(self, dag_run_id: str, logical_date: str) -> dict:
        try:
            resp = httpx.post(
                self._dag_url("dagRuns"),
                json={
                    "dag_run_id": dag_run_id,
                    "logical_date": f"{logical_date}T00:00:00Z",
                },
                auth=self._auth,
                timeout=10.0,
            )
        except httpx.HTTPError as exc:
            raise AirflowError(f"Airflow unreachable: {exc}") from exc
        if resp.status_code >= 400:
            raise AirflowError(
                f"Airflow API error {resp.status_code}: {resp.text[:300]}",
                status_code=503 if resp.status_code >= 500 else 409 if resp.status_code == 409 else 502,
            )
        return resp.json()