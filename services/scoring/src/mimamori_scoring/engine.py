"""The scoring engine: baseline lookup, counterpart graph, watchlist, rules, persistence, case opening.

Rule `score-v1` (deterministic, no model):

    seasonal   amount within tolerance of a seasonal baseline item in that calendar month
               -> `matched_baseline = seasonal:<key>`, and the amount is not counted as unusual
    unusual    amount >= floor, >= `ratio_threshold` x the customer's median monthly outflow (or, for a
               customer with no history, >= the large-transfer threshold), and above their p95 item
    new payee  a transfer to a payee not in the customer's known payees (account id, else kana name)
    young      same-bank payee account younger than `young_account_days`
    fan-in     >= `fan_in_payers` distinct payers into the payee account in 7 days, the requester included
    watchlist  payee name or account matches the latest ref-db snapshot

    alert = watchlist hit
         or (unusual and (new payee or young or fan-in or it is a cash withdrawal))
         or (young and fan-in and max(amount, payee total) >= `mule_alert_min_amount_jpy`)

    Running totals (structuring): the rules judge the total as well as the payment itself.
      payee total   the customer's `transfer_out` rows to the same payee (account id, else kana name) in
                    the last `payee_total_days` days, plus this payment; the mule term uses
                    max(amount, payee total).
      outflow 24h   all the customer's outflows (`transfer_out`, `withdrawal`) in the last
                    `outflow_window_hours` hours, plus this payment; `unusual` runs its ratio, floor and
                    p95 checks on max(amount, outflow 24h).
      Earlier rows that match a seasonal baseline item are left out of both sums, and a payment that
      itself matches a seasonal item is never `unusual`. The watchlist rule ignores totals.
      A `payee_running_total` / `outflow_running_total` signal is added only when the total, not the
      single payment, is what crossed the threshold.

    Below the mule floor the decision is `allow`, but the signals are still returned and stored, so the
    payment still counts toward the payee account's payers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta

import anyio
from mimamori_common.config import Settings
from mimamori_common.models import (
    EventResponse,
    OpenCaseRequest,
    ScoreRequest,
    ScoreResponse,
    ScoreSignal,
)
from mimamori_common.models.baseline import Baseline
from mimamori_common.store import CaseRepo

from .baseline import compute_baseline
from .clients import BankClient, CaseClient
from .config import RULE_VERSION, ScoringConfig
from .watchlist import Watchlist

log = logging.getLogger("scoring.engine")


@dataclass
class Totals:
    payee_total_jpy: int  # including this payment
    payee_count: int  # including this payment
    outflow_24h_jpy: int  # including this payment


@dataclass
class Counterpart:
    account_age_days: int
    distinct_payers_7d: int


def _num(x: float) -> int | float:
    return int(x) if float(x).is_integer() else round(x, 1)


def _yen(n: int) -> str:
    return f"¥{n:,}"


def _seasonal_match(base: Baseline, month: int, amount_jpy: int) -> str | None:
    for item in base.seasonal_items:
        lo = item.typical_amount_jpy * (100 - item.tolerance_pct) / 100
        hi = item.typical_amount_jpy * (100 + item.tolerance_pct) / 100
        if item.month == month and lo <= amount_jpy <= hi:
            return f"seasonal:{item.key}"
    return None


class Scorer:
    def __init__(
        self, settings: Settings, cfg: ScoringConfig, bank: BankClient, cases: CaseClient,
        case_repo: CaseRepo, watchlist: Watchlist,
    ) -> None:
        self.settings, self.cfg, self.bank, self.cases = settings, cfg, bank, cases
        self.repo, self.watchlist = case_repo, watchlist

    # ------------------------------------------------------------------ baselines

    async def _compute_baseline(self, customer_ref: str, as_of: datetime) -> Baseline:
        customer, accounts = await asyncio.gather(self.bank.customer(customer_ref), self.bank.accounts_of(customer_ref))
        per_account = await asyncio.gather(*(self.bank.transactions(a.account_id, until=as_of) for a in accounts))
        txns = [t for rows in per_account for t in rows]
        return compute_baseline(customer_ref, customer.tenure_years, txns, as_of, self.cfg)

    async def refresh_baseline(self, customer_ref: str) -> Baseline:
        """Recompute as of now and store it (the baseline job, DA 14)."""
        baseline = await self._compute_baseline(customer_ref, self.settings.now())
        await anyio.to_thread.run_sync(self.repo.put_baseline, customer_ref, baseline.model_dump(mode="json"))
        return baseline

    async def refresh_all(self) -> list[Baseline]:
        customers = await self.bank.customers()
        sem = asyncio.Semaphore(8)

        async def one(ref: str) -> Baseline:
            async with sem:
                return await self.refresh_baseline(ref)

        return list(await asyncio.gather(*(one(c.customer_ref) for c in customers)))

    async def baseline_for(self, customer_ref: str, as_of: datetime, live: bool) -> Baseline:
        """The cached baseline when it is fresh and predates `as_of`; otherwise computed as of `as_of`
        (historic replays are never cached)."""
        doc = await anyio.to_thread.run_sync(self.repo.get_baseline, customer_ref)
        if doc:
            cached = Baseline.model_validate(doc)
            if cached.computed_at <= as_of and (as_of - cached.computed_at).total_seconds() < self.cfg.baseline_ttl_s:
                return cached
        baseline = await self._compute_baseline(customer_ref, as_of)
        if live:
            await anyio.to_thread.run_sync(self.repo.put_baseline, customer_ref, baseline.model_dump(mode="json"))
        return baseline

    # ------------------------------------------------------------------ counterpart graph

    async def counterpart(self, req: ScoreRequest, live: bool) -> Counterpart | None:
        if not req.payee or req.payee.relation != "same_bank" or not req.payee.account_id:
            return None
        payee_id = req.payee.account_id
        if live:
            account, payers = await asyncio.gather(self.bank.account(payee_id), self.bank.payers(payee_id, self.cfg.fan_in_days))
            payer_ids = {p.account_id for p in payers.payers}
        else:
            window_start = req.occurred_at - timedelta(days=self.cfg.fan_in_days)
            account, rows = await asyncio.gather(
                self.bank.account(payee_id), self.bank.transactions(payee_id, since=window_start, until=req.occurred_at)
            )
            payer_ids = {
                t.counterparty_account_id for t in rows
                if t.kind == "transfer_in" and t.counterparty_account_id and window_start <= t.booked_at <= req.occurred_at
            }
        payer_ids.add(req.account_id)  # the payer asking now counts (api-contracts.md)
        age = (req.occurred_at.date() - datetime.fromisoformat(account.opened_on).date()).days
        return Counterpart(account_age_days=max(age, 0), distinct_payers_7d=len(payer_ids))

    # ------------------------------------------------------------------ running totals

    async def recent_outflows(self, req: ScoreRequest) -> list:
        """The customer's own account rows for the longer of the two windows, read once."""
        span = max(timedelta(days=self.cfg.payee_total_days), timedelta(hours=self.cfg.outflow_window_hours))
        rows = await self.bank.transactions(req.account_id, since=req.occurred_at - span, until=req.occurred_at)
        # A post-transaction event is already booked: don't count the payment twice.
        return [t for t in rows if t.txn_id != req.transfer_id]

    def running_totals(self, req: ScoreRequest, rows: list, base: Baseline) -> Totals:
        cfg = self.cfg
        payee_since = req.occurred_at - timedelta(days=cfg.payee_total_days)
        out_since = req.occurred_at - timedelta(hours=cfg.outflow_window_hours)
        payee = req.payee
        payee_total, payee_count, outflow = req.amount_jpy, 1, req.amount_jpy
        for t in rows:
            if t.kind not in ("transfer_out", "withdrawal") or t.booked_at > req.occurred_at:
                continue
            if _seasonal_match(base, t.booked_at.month, t.amount_jpy):
                continue
            if t.booked_at >= out_since:
                outflow += t.amount_jpy
            if (req.kind == "transfer" and payee and t.kind == "transfer_out" and t.booked_at >= payee_since and (
                    (payee.account_id and t.counterparty_account_id == payee.account_id)
                    or (not payee.account_id and t.counterparty_name_kana == payee.name_kana))):
                payee_total += t.amount_jpy
                payee_count += 1
        return Totals(payee_total_jpy=payee_total, payee_count=payee_count, outflow_24h_jpy=outflow)

    # ------------------------------------------------------------------ the rule

    def _evaluate(self, req: ScoreRequest, base: Baseline, graph: Counterpart | None, hits: list, totals: Totals | None = None) -> tuple[bool, list[ScoreSignal], str | None]:
        cfg = self.cfg
        signals: list[ScoreSignal] = []

        # seasonal match
        matched = _seasonal_match(base, req.occurred_at.month, req.amount_jpy)
        totals = totals or Totals(req.amount_jpy, 1, req.amount_jpy)

        def over_threshold(amount: int) -> bool:
            ratio_ = amount / base.median_monthly_withdrawal_jpy if base.median_monthly_withdrawal_jpy else None
            if ratio_ is not None:
                hit = ratio_ >= cfg.ratio_threshold
            else:
                hit = amount >= self.settings.large_transfer_threshold_jpy
            return hit and amount >= cfg.min_unusual_amount_jpy and amount > base.p95_withdrawal_jpy

        ratio = req.amount_jpy / base.median_monthly_withdrawal_jpy if base.median_monthly_withdrawal_jpy else None
        single_unusual = over_threshold(req.amount_jpy) and not matched
        total_unusual = over_threshold(totals.outflow_24h_jpy) and not matched and not single_unusual
        unusual = single_unusual or total_unusual

        if total_unusual:
            signals.append(ScoreSignal(
                code="outflow_running_total", tool="recent_transactions", field="outflow_24h_jpy", value=totals.outflow_24h_jpy,
                statement_en=f"{_yen(totals.outflow_24h_jpy)} paid out in the last {cfg.outflow_window_hours} hours, including this payment",
            ))
        if single_unusual:
            if ratio is not None:
                signals.append(ScoreSignal(
                    code="amount_vs_baseline", tool="get_baseline", field="amount_vs_median_ratio", value=_num(ratio),
                    statement_en=f"{_yen(req.amount_jpy)} is {_num(ratio)}x the customer's median monthly outflow "
                                 f"({_yen(base.median_monthly_withdrawal_jpy)})",
                ))
            else:
                signals.append(ScoreSignal(
                    code="amount_vs_baseline", tool="get_baseline", field="median_monthly_withdrawal_jpy", value=0,
                    statement_en=f"{_yen(req.amount_jpy)} with no outflow history to compare against",
                ))

        new_payee = False
        if req.kind == "transfer" and req.payee:
            known_accounts = {p.account_id for p in base.known_payees if p.account_id}
            known_names = {p.name_kana for p in base.known_payees}
            new_payee = req.payee.account_id not in known_accounts and req.payee.name_kana not in known_names
            if new_payee:
                signals.append(ScoreSignal(
                    code="new_payee", tool="get_baseline", field="new_payee", value=True,
                    statement_en="The customer has never paid this payee before",
                ))

        young = fan_in = False
        if graph:
            young = graph.account_age_days < cfg.young_account_days
            fan_in = graph.distinct_payers_7d >= cfg.fan_in_payers
            if young:
                signals.append(ScoreSignal(
                    code="payee_account_age", tool="counterpart_graph", field="account_age_days", value=graph.account_age_days,
                    statement_en=f"The payee account was opened {graph.account_age_days} days ago",
                ))
            if fan_in:
                signals.append(ScoreSignal(
                    code="payer_fan_in", tool="counterpart_graph", field="distinct_payers_7d", value=graph.distinct_payers_7d,
                    statement_en=f"{graph.distinct_payers_7d} distinct payers sent money to this account in the last "
                                 f"{cfg.fan_in_days} days, including this customer",
                ))

        for hit in hits:
            signals.append(ScoreSignal(
                code="watchlist_match", tool="check_lists", field="watchlist_match", value=hit.list_name,
                statement_en=f"The payee matches {hit.list_name} entry {hit.source_ref} (notice {hit.notice_date})",
            ))

        mule_single = young and fan_in and req.amount_jpy >= cfg.mule_alert_min_amount_jpy
        mule_total = young and fan_in and not mule_single and totals.payee_total_jpy >= cfg.mule_alert_min_amount_jpy
        if mule_total:
            signals.append(ScoreSignal(
                code="payee_running_total", tool="recent_transactions", field="payee_total_7d_jpy", value=totals.payee_total_jpy,
                statement_en=f"{totals.payee_count} payments to this payee in {cfg.payee_total_days} days, "
                             f"{_yen(totals.payee_total_jpy)} in total, including this one",
            ))
        alert = bool(hits) or (unusual and (new_payee or young or fan_in or req.kind == "cash_withdrawal")) or mule_single or mule_total
        return alert, signals, matched

    # ------------------------------------------------------------------ entry points

    def is_live(self, occurred_at: datetime) -> bool:
        return (self.settings.now() - occurred_at).total_seconds() <= self.cfg.live_window_s

    async def _score(self, req: ScoreRequest, *, open_case: bool) -> ScoreResponse:
        started = time.perf_counter()
        live = self.is_live(req.occurred_at)
        payee = req.payee
        base, graph, hits, rows = await asyncio.gather(
            self.baseline_for(req.customer_ref, req.occurred_at, live),
            self.counterpart(req, live),
            self.watchlist.match(payee.name_kana, payee.account_id) if payee else _none(),
            self.recent_outflows(req),
        )
        alert, signals, matched = self._evaluate(req, base, graph, hits or [], self.running_totals(req, rows, base))

        case_id = None
        if alert and open_case:
            opened = await self.cases.open_case(OpenCaseRequest(
                transfer_id=req.transfer_id, customer_ref=req.customer_ref, account_id=req.account_id,
                request={
                    "channel": req.channel, "kind": req.kind, "amount_jpy": req.amount_jpy,
                    "payee": {"name_kana": payee.name_kana, "relation": payee.relation} if payee else None,
                },
                signals=signals, opened_at=req.occurred_at,
            ))
            case_id = opened.case_id if opened else None

        response = ScoreResponse(
            decision="alert" if alert else "allow", signals=signals, case_id=case_id, matched_baseline=matched,
            scored_at=self.settings.now(), latency_ms=round((time.perf_counter() - started) * 1000),
        )
        record = {
            "transfer_id": req.transfer_id, "customer_ref": req.customer_ref, "account_id": req.account_id,
            "mode": "pre_transaction" if open_case else "post_transaction", "rule_version": RULE_VERSION,
            "amount_jpy": req.amount_jpy, "occurred_at": req.occurred_at.isoformat(),
            "watchlist_snapshot": self.watchlist.snapshot_id, **response.model_dump(mode="json"),
        }
        await anyio.to_thread.run_sync(self.repo.put_score, req.transfer_id, record)
        return response

    async def score(self, req: ScoreRequest) -> ScoreResponse:
        return await self._score(req, open_case=True)

    async def event(self, req: ScoreRequest) -> EventResponse:
        """Post-transaction monitoring: never opens a case in the prototype."""
        return EventResponse.model_validate((await self._score(req, open_case=False)).model_dump())


async def _none():
    return None
