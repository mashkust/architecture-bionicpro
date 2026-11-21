from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth import TokenVerifier
from .config import Settings
from .olap import OlapClient
from .reports import build_reports_router


def create_app(settings: Settings | None = None, olap: OlapClient | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    olap = olap or OlapClient(settings)
    verifier = TokenVerifier(settings)

    app = FastAPI(title="BionicPRO Reports API", version="1.0.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(build_reports_router(settings, olap, verifier))
    return app


app = create_app()