"""Everything the routes need, built once. Tests pass fakes for the model clients and the HTTP transports."""

from __future__ import annotations

import dataclasses
import secrets
from dataclasses import dataclass
from typing import Callable

import httpx

from mimamori_common.config import Settings
from mimamori_common.llm import ModelClient, get_copilot_client
from mimamori_common.store import IntelRepo, RefRepo, open_case_repo, open_intel_repo, open_ref_repo

from .casestore import CaseStore
from .clients import ConversationClient, CoreBankClient, ScoringClient
from .config import SvcConfig

SERVICE_NAME = "case-svc"


@dataclass
class Deps:
    settings: Settings
    svc: SvcConfig
    store: CaseStore
    intel: IntelRepo
    ref: RefRepo
    copilot: ModelClient  # counter copilot turns
    investigator: ModelClient  # investigation agent steps (separate so replay queues don't mix)
    core: CoreBankClient
    scoring: ScoringClient
    conversation: ConversationClient
    case_code: Callable[[], str]


def build_deps(settings: Settings | None = None, svc: SvcConfig | None = None, *, copilot: ModelClient | None = None,
               investigator: ModelClient | None = None, core_transport: httpx.AsyncBaseTransport | None = None,
               scoring_transport: httpx.AsyncBaseTransport | None = None,
               conversation_transport: httpx.AsyncBaseTransport | None = None) -> Deps:
    settings = dataclasses.replace(settings or Settings.from_env(), service_name=SERVICE_NAME)
    svc = svc or SvcConfig.from_env()
    model = copilot or get_copilot_client(settings)
    fixed = svc.case_code
    return Deps(
        settings=settings, svc=svc,
        store=CaseStore(open_case_repo(settings), settings),
        intel=open_intel_repo(settings), ref=open_ref_repo(settings),
        copilot=model, investigator=investigator or model,
        core=CoreBankClient(settings.core_bank_url, core_transport),
        scoring=ScoringClient(settings.scoring_url, scoring_transport),
        conversation=ConversationClient(settings.conversation_svc_url, conversation_transport),
        case_code=(lambda: fixed) if fixed else (lambda: f"{secrets.randbelow(10000):04d}"),
    )
