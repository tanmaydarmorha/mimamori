"""FastAPI app for the scoring service: `/v1/score`, `/v1/events`, `/v1/baselines/...`, `/healthz`."""

from __future__ import annotations

import asyncio
import contextlib
import logging

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse
from mimamori_common.config import Settings
from mimamori_common.models import ApiError, EventResponse, ScoreRequest, ScoreResponse
from mimamori_common.models.baseline import Baseline
from mimamori_common.store import CaseRepo, RefRepo, open_case_repo, open_ref_repo
from mimamori_common.web import create_app

from .clients import BankClient, BankUnavailable, CaseClient, UnknownReference
from .config import ScoringConfig
from .engine import Scorer
from .watchlist import Watchlist

log = logging.getLogger("scoring")


def create_scoring_app(
    settings: Settings | None = None,
    cfg: ScoringConfig | None = None,
    *,
    bank_http: httpx.AsyncClient | None = None,
    case_http: httpx.AsyncClient | None = None,
    case_repo: CaseRepo | None = None,
    ref_repo: RefRepo | None = None,
    warm_on_start: bool | None = None,
):
    settings = settings or Settings.from_env()
    cfg = cfg or ScoringConfig.from_env()
    bank_http = bank_http or httpx.AsyncClient(base_url=settings.core_bank_url, timeout=cfg.bank_timeout_s)
    case_http = case_http or httpx.AsyncClient(base_url=settings.case_svc_url, timeout=cfg.case_timeout_s)
    scorer = Scorer(
        settings, cfg, BankClient(bank_http), CaseClient(case_http),
        case_repo or open_case_repo(settings),
        Watchlist(ref_repo or open_ref_repo(settings), cfg.watchlist_ttl_s),
    )
    warm = cfg.warm_on_start if warm_on_start is None else warm_on_start

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        task = None
        if warm:
            async def _warm():
                try:
                    done = await scorer.refresh_all()
                    log.info("warmed %d baselines", len(done))
                except Exception as exc:  # the bank may not be up yet; baselines are computed lazily anyway
                    log.warning("baseline warm-up skipped: %r", exc)

            task = asyncio.create_task(_warm())
        yield
        if task:
            task.cancel()
        await bank_http.aclose()
        await case_http.aclose()

    app = create_app("scoring", settings, lifespan=lifespan)
    app.state.scorer = scorer

    @app.exception_handler(BankUnavailable)
    async def _bank_down(_request: Request, exc: BankUnavailable):
        log.error("core bank unavailable: %s", exc)
        return JSONResponse(ApiError(error="bank_unavailable", detail=str(exc)).model_dump(), status_code=503)

    @app.exception_handler(UnknownReference)
    async def _unknown(_request: Request, exc: UnknownReference):
        return JSONResponse(ApiError(error="not_found", detail=str(exc)).model_dump(), status_code=404)

    @app.post("/v1/score", response_model=ScoreResponse, tags=["scoring"])
    async def score(req: ScoreRequest) -> ScoreResponse:
        return await scorer.score(req)

    @app.post("/v1/events", response_model=EventResponse, tags=["scoring"])
    async def events(req: ScoreRequest) -> EventResponse:
        return await scorer.event(req)

    @app.post("/v1/baselines/refresh", response_model=list[Baseline], tags=["baselines"])
    async def refresh_all() -> list[Baseline]:
        return await scorer.refresh_all()

    @app.post("/v1/baselines/{customer_ref}/refresh", response_model=Baseline, tags=["baselines"])
    async def refresh_one(customer_ref: str) -> Baseline:
        return await scorer.refresh_baseline(customer_ref)

    return app


app = create_scoring_app()
