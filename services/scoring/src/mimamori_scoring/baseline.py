"""Baseline computation: a pure function from a customer's transactions to `mimamori_common.models.Baseline`.

Field names double as the `get_baseline.<field>` facts the investigation agent cites, so absence is a
field too (`contractor_payments_count_12y = 0`).

Definitions (all "as of" a cutoff: only transactions booked strictly before it are used, so a
transaction never forms part of its own baseline):

- Outflow = cash withdrawals and transfers out. Direct debits (utilities, insurance) are recurring and
  are only used for the known-payee list.
- `median_monthly_withdrawal_jpy`: median, over the calendar months in the window that had any outflow,
  of that month's outflow total. Window = `baseline_window_months` (default 36).
- `p95_withdrawal_jpy`: 95th percentile (nearest rank) of single outflow items in the window.
- `largest_payment_12m_jpy`: largest single outflow in the 365 days before the cutoff.
- `contractor_payments_count_12y`: payments to a payee the bank classifies as `contractor` in the 12
  years before the cutoff.
- `seasonal_items`: outflow items at least `seasonal_min_multiple` x the monthly median that recur in the
  same calendar month, with similar amounts (within `seasonal_tolerance_pct`), in at least
  `seasonal_min_years` distinct years.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from mimamori_common.models import BankTransaction
from mimamori_common.models.baseline import Baseline, KnownPayee, SeasonalItem

from .config import ScoringConfig

OUTFLOW_KINDS = {"withdrawal", "transfer_out"}
PAYEE_KINDS = {"transfer_out", "direct_debit"}
MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september",
               "october", "november", "december"]


def payee_key(account_id: str | None, name_kana: str | None) -> str | None:
    return account_id or name_kana


def _percentile(sorted_values: list[int], p: float) -> int:
    if not sorted_values:
        return 0
    rank = max(1, math.ceil(round(len(sorted_values) * p, 9)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def _months_back(as_of: datetime, months: int) -> datetime:
    return as_of - timedelta(days=round(months * 30.4375))


def _seasonal_items(outflows: list[BankTransaction], monthly_median: int, cfg: ScoringConfig) -> list[SeasonalItem]:
    floor = max(monthly_median * cfg.seasonal_min_multiple, cfg.min_unusual_amount_jpy)
    by_month: dict[int, list[BankTransaction]] = defaultdict(list)
    for t in outflows:
        if t.amount_jpy >= floor:
            by_month[t.booked_at.month].append(t)
    items: list[SeasonalItem] = []
    for month, txs in sorted(by_month.items()):
        txs.sort(key=lambda t: t.amount_jpy)
        clusters: list[list[BankTransaction]] = []
        for t in txs:
            if clusters:
                centre = statistics.median(c.amount_jpy for c in clusters[-1])
                if abs(t.amount_jpy - centre) <= centre * cfg.seasonal_tolerance_pct / 100:
                    clusters[-1].append(t)
                    continue
            clusters.append([t])
        for n, cluster in enumerate(clusters):
            years = {t.booked_at.year for t in cluster}
            if len(years) < cfg.seasonal_min_years:
                continue
            # April is the start of the Japanese school year: a recurring large April outflow is labelled
            # as the school fee (a heuristic; the bank data carries no purpose for cash withdrawals).
            label = "school_fee" if month == 4 else "annual_payment"
            key = f"{MONTH_NAMES[month - 1]}_{label}" + (f"_{n + 1}" if n else "")
            items.append(SeasonalItem(
                key=key, month=month, typical_amount_jpy=int(statistics.median(t.amount_jpy for t in cluster)),
                tolerance_pct=cfg.seasonal_tolerance_pct, years_seen=len(years),
            ))
    return items


def compute_baseline(
    customer_ref: str, tenure_years: int, txns: list[BankTransaction], as_of: datetime, cfg: ScoringConfig,
) -> Baseline:
    history = sorted((t for t in txns if t.booked_at < as_of), key=lambda t: t.booked_at)
    outflows = [t for t in history if t.kind in OUTFLOW_KINDS]

    window_start = _months_back(as_of, cfg.baseline_window_months)
    windowed = [t for t in outflows if t.booked_at >= window_start]
    monthly: dict[tuple[int, int], int] = defaultdict(int)
    for t in windowed:
        monthly[(t.booked_at.year, t.booked_at.month)] += t.amount_jpy
    median_monthly = int(statistics.median(monthly.values())) if monthly else 0
    p95 = _percentile(sorted(t.amount_jpy for t in windowed), 0.95)

    year_ago = as_of - timedelta(days=365)
    largest_12m = max((t.amount_jpy for t in outflows if t.booked_at >= year_ago), default=0)

    twelve_years_ago = as_of - timedelta(days=365 * 12 + 3)
    contractor = sum(
        1 for t in history
        if t.kind in PAYEE_KINDS and t.counterparty_category == "contractor" and t.booked_at >= twelve_years_ago
    )

    payees: dict[str, list[BankTransaction]] = defaultdict(list)
    for t in history:
        key = payee_key(t.counterparty_account_id, t.counterparty_name_kana) if t.kind in PAYEE_KINDS else None
        if key:
            payees[key].append(t)
    known = [
        KnownPayee(
            name_kana=txs[0].counterparty_name_kana or "", account_id=txs[0].counterparty_account_id,
            category=txs[-1].counterparty_category, payments=len(txs),
            last_paid_on=max(t.booked_at for t in txs).date(),
        )
        for txs in payees.values()
    ]
    known.sort(key=lambda p: (-p.payments, p.name_kana))
    new_payees_12m = sum(
        1 for txs in payees.values()
        if txs[0].kind == "transfer_out" and txs[0].booked_at >= year_ago
    )

    return Baseline(
        customer_ref=customer_ref,
        computed_at=as_of,
        customer_tenure_years=tenure_years,
        median_monthly_withdrawal_jpy=median_monthly,
        p95_withdrawal_jpy=p95,
        largest_payment_12m_jpy=largest_12m,
        contractor_payments_count_12y=contractor,
        renovation_loan_enquiries_count=0,  # no loan-enquiry data in the bank feed
        transfers_to_new_payees_12m=new_payees_12m,
        known_payees=known,
        seasonal_items=_seasonal_items(outflows, median_monthly, cfg),
    )
