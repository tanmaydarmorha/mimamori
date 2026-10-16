"""FastAPI scaffolding shared by every service: `GET /healthz`, CORS from config, role headers.
Needs the `web` extra (fastapi)."""

from __future__ import annotations

import logging
from typing import Literal

from .config import Settings
from .models.api import Health

Role = Literal["teller", "analyst", "system"]


def configure_logging(*loggers: str, level: int = logging.INFO) -> None:
    """Make INFO lines from the named loggers (and the shared `mimamori_common`) show up in the service
    log. Only uvicorn's access log is configured by default. Safe to call twice."""
    for name in (*loggers, "mimamori_common"):
        lg = logging.getLogger(name)
        lg.setLevel(level)
        if not any(getattr(h, "_mimamori", False) for h in lg.handlers):
            h = logging.StreamHandler()
            h.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
            h._mimamori = True  # type: ignore[attr-defined]
            lg.addHandler(h)
            lg.propagate = False


def create_app(service: str, settings: Settings | None = None, **fastapi_kwargs):
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    settings = settings or Settings.from_env()
    app = FastAPI(title=service, **fastapi_kwargs)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_methods=["*"], allow_headers=["*"])

    @app.get("/healthz", response_model=Health, tags=["ops"])
    def healthz() -> Health:
        return Health(service=service)

    return app


def caller_role(headers) -> tuple[Role, str]:
    """Role and user from request headers. In the cloud IAP sets `X-Goog-Authenticated-User-Email`
    and the role comes from IAP group mapping into `X-Mimamori-Role`; locally the console's role
    switcher sets `X-Mimamori-Role` / `X-Mimamori-User` directly. Services use this for audit
    attribution and to gate analyst-only endpoints."""
    role = headers.get("x-mimamori-role", "teller")
    if role not in ("teller", "analyst", "system"):
        raise ValueError(f"unknown role {role!r}")
    user = headers.get("x-mimamori-user") or headers.get("x-goog-authenticated-user-email") or "unknown"
    return role, user  # type: ignore[return-value]
