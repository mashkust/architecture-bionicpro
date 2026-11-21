import os
from dataclasses import dataclass


def _env_flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, "true" if default else "false").lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 9000
    clickhouse_database: str = "bionicpro"
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "reports-realm"
    keycloak_issuer: str | None = None
    jwt_audience: str | None = None
    required_roles: frozenset = frozenset({"prothetic_user", "administrator"})
    auth_disabled: bool = False
    cors_origins: tuple = ("http://localhost:3000",)
    airflow_url: str = "http://localhost:8080"
    airflow_username: str | None = None
    airflow_password: str | None = None
    airflow_dag_id: str = "bionicpro_etl_reports"

    @classmethod
    def from_env(cls) -> "Settings":
        audience = os.getenv("JWT_AUDIENCE", "").strip() or None
        roles = frozenset(
            r.strip() for r in os.getenv("REQUIRED_ROLES", "prothetic_user,administrator").split(",") if r.strip()
        )
        origins = tuple(
            o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
        )
        return cls(
            clickhouse_host=os.getenv("CLICKHOUSE_HOST", "localhost"),
            clickhouse_port=int(os.getenv("CLICKHOUSE_PORT", "9000")),
            clickhouse_database=os.getenv("CLICKHOUSE_DATABASE", "bionicpro"),
            keycloak_url=os.getenv("KEYCLOAK_URL", "http://localhost:8080").rstrip("/"),
            keycloak_realm=os.getenv("KEYCLOAK_REALM", "reports-realm"),
            keycloak_issuer=os.getenv("KEYCLOAK_ISSUER") or None,
            jwt_audience=audience,
            required_roles=roles,
            auth_disabled=_env_flag("DISABLE_AUTH"),
            cors_origins=origins,
            airflow_url=os.getenv("AIRFLOW_URL", "http://localhost:8080").rstrip("/"),
            airflow_username=os.getenv("AIRFLOW_USERNAME") or None,
            airflow_password=os.getenv("AIRFLOW_PASSWORD") or None,
            airflow_dag_id=os.getenv("AIRFLOW_DAG_ID", "bionicpro_etl_reports"),
        )