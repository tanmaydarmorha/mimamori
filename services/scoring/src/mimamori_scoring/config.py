"""Scoring thresholds. Defaults live here and nowhere else; each can be overridden by an env var.

Everything else (URLs, region, stores, the large-transfer threshold) comes from
`mimamori_common.config.Settings`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

RULE_VERSION = "score-v1"


def _f(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _i(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass(frozen=True)
class ScoringConfig:
    # "Unusual amount": at least this many times the customer's typical monthly outflow, above their
    # 95th-percentile single item, and above the absolute floor.
    ratio_threshold: float = 10.0
    min_unusual_amount_jpy: int = 100_000
    # Counterpart graph (same-bank payees only).
    young_account_days: int = 30
    fan_in_payers: int = 3
    fan_in_days: int = 7
    # The mule pattern (young account + fan-in) alone opens a case only at or above this amount.
    mule_alert_min_amount_jpy: int = 100_000
    # Running totals (structuring): payments to the same payee in this many days, and all outflows in
    # this many hours, are judged together with the payment being scored.
    payee_total_days: int = 7
    outflow_window_hours: int = 24
    # Baselines.
    baseline_window_months: int = 36
    baseline_ttl_s: int = 24 * 3600
    seasonal_tolerance_pct: int = 15
    seasonal_min_years: int = 2
    seasonal_min_multiple: float = 3.0
    # A request at most this old counts as "live" (use the bank's rolling payer window, cache baselines).
    live_window_s: int = 900
    # Watchlist snapshot cache.
    watchlist_ttl_s: float = 60.0
    # Timeouts for the services Scoring calls.
    bank_timeout_s: float = 2.0
    case_timeout_s: float = 3.0
    warm_on_start: bool = True

    @classmethod
    def from_env(cls) -> "ScoringConfig":
        d = cls()
        return cls(
            ratio_threshold=_f("SCORING_RATIO_THRESHOLD", d.ratio_threshold),
            min_unusual_amount_jpy=_i("SCORING_MIN_UNUSUAL_AMOUNT_JPY", d.min_unusual_amount_jpy),
            young_account_days=_i("SCORING_YOUNG_ACCOUNT_DAYS", d.young_account_days),
            fan_in_payers=_i("SCORING_FAN_IN_PAYERS", d.fan_in_payers),
            fan_in_days=_i("SCORING_FAN_IN_DAYS", d.fan_in_days),
            mule_alert_min_amount_jpy=_i("SCORING_MULE_ALERT_MIN_AMOUNT_JPY", d.mule_alert_min_amount_jpy),
            payee_total_days=_i("SCORING_PAYEE_TOTAL_DAYS", d.payee_total_days),
            outflow_window_hours=_i("SCORING_OUTFLOW_WINDOW_HOURS", d.outflow_window_hours),
            baseline_window_months=_i("SCORING_BASELINE_WINDOW_MONTHS", d.baseline_window_months),
            baseline_ttl_s=_i("SCORING_BASELINE_TTL_S", d.baseline_ttl_s),
            watchlist_ttl_s=_f("SCORING_WATCHLIST_TTL_S", d.watchlist_ttl_s),
            bank_timeout_s=_f("SCORING_BANK_TIMEOUT_S", d.bank_timeout_s),
            case_timeout_s=_f("SCORING_CASE_TIMEOUT_S", d.case_timeout_s),
            warm_on_start=os.environ.get("SCORING_WARM_ON_START", "true").lower() != "false",
        )
