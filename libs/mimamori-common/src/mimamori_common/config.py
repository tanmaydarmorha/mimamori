"""Settings from environment variables. The only place defaults live: no region, URL, model name
or port is hard-coded anywhere else. `Settings.from_env()` re-reads the environment each call."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9), "Asia/Tokyo")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    # Deployment
    region: str = "asia-south1"  # prototype; production for a Japanese bank is asia-northeast1
    env: str = "local"  # local | cloud
    project_id: str | None = None
    port: int = 8080
    service_name: str = "mimamori"
    cors_origins: tuple[str, ...] = ("*",)

    # Stores: memory (tests, single process) | firestore (emulator locally, real in cloud)
    store_backend: str = "memory"
    case_db_id: str = "case-db"
    intel_db_id: str = "intel-db"
    ref_db_id: str = "ref-db"

    # Service URLs (docker-compose names locally, Cloud Run URLs in cloud)
    core_bank_url: str = "http://localhost:8081"
    scoring_url: str = "http://localhost:8082"
    case_svc_url: str = "http://localhost:8083"
    conversation_svc_url: str = "http://localhost:8084"

    # Models. copilot_backend: ollama | vertex_gemma | gemini | fake  (case service, Gemma)
    #         general_backend: ollama | gemini | fake  (conversation service, intelligence and simulation jobs)
    copilot_backend: str = "ollama"
    general_backend: str = "ollama"
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:12b"
    vertex_gemma_endpoint_id: str | None = None
    vertex_gemma_model: str = "gemma"
    gemini_model: str = "gemini-2.5-flash"
    gemini_location: str | None = None  # defaults to `region`; set if Gemini isn't served there (open item)
    gemini_thinking_budget: int = 0  # 0 = thinking off (our calls are schema-constrained); -1 = leave it to the model
    model_timeout_s: float = 120.0
    model_max_retries: int = 4  # Vertex 429/500/503 retries, within model_timeout_s

    # Speech. backend: typed | cloud
    speech_backend: str = "typed"
    tts_backend: str = "typed"  # typed | cloud; defaults to speech_backend (cloud voice with typed input)
    stt_model: str = "chirp_2"
    stt_language: str = "ja-JP"
    tts_voice: str = "ja-JP-Chirp3-HD-Aoede"
    stt_language_en: str = "en-US"
    tts_voice_en: str = "en-US-Chirp3-HD-Aoede"

    # Bank behaviour
    scoring_timeout_s: float = 0.5  # core-bank-mock's pre-transaction call (fail open)
    large_transfer_threshold_jpy: int = 1_000_000
    business_day_close: str = "15:00"  # local time, JST
    branch_name_ja: str = "サンプル銀行 駅前支店"
    branch_name_en: str = "Sample Bank, Ekimae Branch"
    branch_published_phone_e164: str = "+81312345678"

    # Demo clock: fixed "now" so seeded relative dates (account opened 4 days ago) hold. Empty = real time.
    demo_now: str | None = None
    schemas_dir: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        env = _env("MIMAMORI_ENV", "local")
        return cls(
            region=_env("MIMAMORI_REGION", cls.region),
            env=env,
            project_id=os.environ.get("MIMAMORI_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT"),
            port=_int("PORT", cls.port),
            service_name=_env("MIMAMORI_SERVICE", cls.service_name),
            cors_origins=tuple(_env("MIMAMORI_CORS_ORIGINS", "*").split(",")),
            store_backend=_env("MIMAMORI_STORE", "firestore" if env == "cloud" else "memory"),
            case_db_id=_env("MIMAMORI_CASE_DB", cls.case_db_id),
            intel_db_id=_env("MIMAMORI_INTEL_DB", cls.intel_db_id),
            ref_db_id=_env("MIMAMORI_REF_DB", cls.ref_db_id),
            core_bank_url=_env("CORE_BANK_URL", cls.core_bank_url),
            scoring_url=_env("SCORING_URL", cls.scoring_url),
            case_svc_url=_env("CASE_SVC_URL", cls.case_svc_url),
            conversation_svc_url=_env("CONVERSATION_SVC_URL", cls.conversation_svc_url),
            copilot_backend=_env("MIMAMORI_COPILOT_BACKEND", "vertex_gemma" if env == "cloud" else "ollama"),
            ollama_url=_env("OLLAMA_URL", cls.ollama_url),
            ollama_model=_env("OLLAMA_MODEL", cls.ollama_model),
            vertex_gemma_endpoint_id=os.environ.get("VERTEX_GEMMA_ENDPOINT_ID"),
            vertex_gemma_model=_env("VERTEX_GEMMA_MODEL", cls.vertex_gemma_model),
            general_backend=_env("MIMAMORI_GENERAL_BACKEND", "gemini" if env == "cloud" else "ollama"),
            gemini_model=_env("GEMINI_MODEL", cls.gemini_model),
            gemini_location=os.environ.get("MIMAMORI_GEMINI_LOCATION") or None,
            gemini_thinking_budget=int(_env("MIMAMORI_GEMINI_THINKING_BUDGET", str(cls.gemini_thinking_budget))),
            model_timeout_s=float(_env("MIMAMORI_MODEL_TIMEOUT_S", str(cls.model_timeout_s))),
            model_max_retries=int(_env("MIMAMORI_MODEL_MAX_RETRIES", str(cls.model_max_retries))),
            speech_backend=(speech := _env("MIMAMORI_SPEECH", "cloud" if env == "cloud" else "typed")),
            tts_backend=_env("MIMAMORI_TTS", speech),
            stt_model=_env("MIMAMORI_STT_MODEL", cls.stt_model),
            stt_language=_env("MIMAMORI_STT_LANGUAGE", cls.stt_language),
            tts_voice=_env("MIMAMORI_TTS_VOICE", cls.tts_voice),
            stt_language_en=_env("MIMAMORI_STT_LANGUAGE_EN", cls.stt_language_en),
            tts_voice_en=_env("MIMAMORI_TTS_VOICE_EN", cls.tts_voice_en),
            scoring_timeout_s=float(_env("SCORING_TIMEOUT_S", str(cls.scoring_timeout_s))),
            large_transfer_threshold_jpy=_int("LARGE_TRANSFER_THRESHOLD_JPY", cls.large_transfer_threshold_jpy),
            business_day_close=_env("BUSINESS_DAY_CLOSE", cls.business_day_close),
            branch_name_ja=_env("BRANCH_NAME_JA", cls.branch_name_ja),
            branch_name_en=_env("BRANCH_NAME_EN", cls.branch_name_en),
            branch_published_phone_e164=_env("BRANCH_PUBLISHED_PHONE", cls.branch_published_phone_e164),
            demo_now=os.environ.get("MIMAMORI_DEMO_NOW") or None,
            schemas_dir=os.environ.get("MIMAMORI_SCHEMAS_DIR") or None,
        )

    def now(self) -> datetime:
        """Current time in JST, or the fixed demo time (MIMAMORI_DEMO_NOW=2026-10-13T11:42:00+09:00)."""
        if self.demo_now:
            return datetime.fromisoformat(self.demo_now).astimezone(JST)
        return datetime.now(JST)


def get_settings() -> Settings:
    return Settings.from_env()
