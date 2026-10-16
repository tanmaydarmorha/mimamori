"""Case-service settings that are not shared with other services (shared ones live in
`mimamori_common.config.Settings`). Everything comes from env vars."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

# Stopgap: the customer's own chosen way of being referred to on the call should live in the advance
# wishes (reported as a schema change). Until then: per-customer override, else a neutral phrase.
DEFAULT_REFERENCE_JA = {"cust-tanaka-0001": "お母様"}
NEUTRAL_REFERENCE_JA = "ご家族の方"
DEFAULT_REFERENCE_EN = {"cust-tanaka-0001": "your mother"}
NEUTRAL_REFERENCE_EN = "your family member"


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SvcConfig:
    investigation_enabled: bool = True
    investigation_inline: bool = False  # tests: run the investigation before POST /cases returns
    investigation_max_steps: int = 10
    seed_on_start: bool = True  # load seed/ into the in-memory stores at startup (local only)
    case_code: str | None = None  # fixed 4-digit code for the demo; random per call when unset
    contact_phone_change_days: int = 30
    policy_minimum_hours: int = 4  # bank-policy (voluntary wait) hold window
    policy_extend_to_close: bool = True
    policy_cap_hours: int = 24
    payee_total_days: int = 7  # same names and defaults as Scoring (running totals, WI-012)
    outflow_window_hours: int = 24
    reference_ja: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_REFERENCE_JA))
    reference_en: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_REFERENCE_EN))

    @classmethod
    def from_env(cls) -> "SvcConfig":
        ref = dict(DEFAULT_REFERENCE_JA)
        ref.update(json.loads(os.environ.get("MIMAMORI_REFERENCE_JA", "{}")))
        ref_en = dict(DEFAULT_REFERENCE_EN)
        ref_en.update(json.loads(os.environ.get("MIMAMORI_REFERENCE_EN", "{}")))
        code = os.environ.get("MIMAMORI_CASE_CODE") or None
        if code and not (code.isdigit() and len(code) == 4):
            raise ValueError("MIMAMORI_CASE_CODE must be 4 digits")
        return cls(
            investigation_enabled=_bool("CASE_SVC_INVESTIGATION", True),
            investigation_inline=_bool("CASE_SVC_INVESTIGATION_INLINE", False),
            investigation_max_steps=int(os.environ.get("CASE_SVC_INVESTIGATION_MAX_STEPS", "10")),
            seed_on_start=_bool("CASE_SVC_SEED_ON_START", True),
            case_code=code,
            contact_phone_change_days=int(os.environ.get("CASE_SVC_CONTACT_PHONE_CHANGE_DAYS", "30")),
            policy_minimum_hours=int(os.environ.get("CASE_SVC_POLICY_MINIMUM_HOURS", "4")),
            policy_extend_to_close=_bool("CASE_SVC_POLICY_EXTEND_TO_CLOSE", True),
            policy_cap_hours=int(os.environ.get("CASE_SVC_POLICY_CAP_HOURS", "24")),
            payee_total_days=int(os.environ.get("SCORING_PAYEE_TOTAL_DAYS", "7")),
            outflow_window_hours=int(os.environ.get("SCORING_OUTFLOW_WINDOW_HOURS", "24")),
            reference_ja=ref,
            reference_en=ref_en,
        )
