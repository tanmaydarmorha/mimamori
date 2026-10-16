"""The mock core-banking ledger: its own in-memory store (never `case-db`).

All state lives in `Bank`. Methods raise `BankError`, which the app turns into an `ApiError` body.
Balances are static (the seed does not reconcile them with its history) and are never mutated;
executed transfers append transactions only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Callable

from mimamori_common.models import (
    Account,
    BankTransaction,
    Customer,
    Freeze,
    FreezeBody,
    Hold,
    HoldPatch,
    HoldRequest,
    PayerRow,
    PayersResponse,
    Transfer,
    TransferPatch,
    TransferRequest,
)
from mimamori_common.seed import BankData

from .window import BusinessCalendar, compute_window

log = logging.getLogger("core-bank-mock")


class BankError(Exception):
    def __init__(self, status: int, error: str, detail: str | None = None):
        super().__init__(f"{error}: {detail}")
        self.status, self.error, self.detail = status, error, detail


class Bank:
    def __init__(self, data: BankData, calendar: BusinessCalendar, now: Callable[[], datetime]):
        self._now = now
        self.calendar = calendar
        self.customers: dict[str, Customer] = {c.customer_ref: c for c in data.customers}
        self.accounts: dict[str, Account] = {a.account_id: a.model_copy() for a in data.accounts}
        self.transactions: dict[str, list[BankTransaction]] = {}
        for t in sorted(data.transactions, key=lambda t: t.booked_at):
            self.transactions.setdefault(t.account_id, []).append(t)
        self._txn_seq = len(data.transactions)
        self.transfers: dict[str, Transfer] = {}
        self.holds: dict[str, Hold] = {}
        self.freezes: dict[str, Freeze] = {}
        self._seq = {"tr": 0, "hold": 0, "frz": 0}

    # ------------------------------------------------------------------ reads

    def customer(self, ref: str) -> Customer:
        if ref not in self.customers:
            raise BankError(404, "not_found", f"customer {ref}")
        return self.customers[ref]

    def account(self, account_id: str) -> Account:
        if account_id not in self.accounts:
            raise BankError(404, "not_found", f"account {account_id}")
        return self.accounts[account_id]

    def list_accounts(self, customer_ref: str | None) -> list[Account]:
        return [a for a in self.accounts.values() if customer_ref is None or a.customer_ref == customer_ref]

    def list_transactions(
        self, account_id: str, since: datetime | None, until: datetime | None, limit: int | None, order: str
    ) -> list[BankTransaction]:
        self.account(account_id)
        rows = [
            t for t in self.transactions.get(account_id, [])
            if (since is None or t.booked_at >= since) and (until is None or t.booked_at <= until)
        ]
        if limit is not None:
            rows = rows[-limit:] if limit else []  # the most recent `limit`
        return list(reversed(rows)) if order == "desc" else rows

    def payers(self, account_id: str, days: int) -> PayersResponse:
        """Distinct payers of completed transfers into the account in the last `days` days."""
        self.account(account_id)
        now = self._now()
        since = now - timedelta(days=days)
        grouped: dict[str, list[BankTransaction]] = {}
        for t in self.transactions.get(account_id, []):
            if t.kind == "transfer_in" and t.counterparty_account_id and since <= t.booked_at <= now:
                grouped.setdefault(t.counterparty_account_id, []).append(t)
        rows: list[PayerRow] = []
        for payer_account_id, txns in grouped.items():
            payer_account = self.accounts.get(payer_account_id)
            if payer_account is None:
                continue
            customer = self.customers.get(payer_account.customer_ref)
            rows.append(PayerRow(
                customer_ref=payer_account.customer_ref,
                account_id=payer_account_id,
                display_name_ja=customer.display_name_ja if customer else payer_account.holder_name_kana,
                payments=len(txns),
                total_jpy=sum(t.amount_jpy for t in txns),
                last_paid_at=max(t.booked_at for t in txns),
            ))
        rows.sort(key=lambda r: r.last_paid_at)
        return PayersResponse(account_id=account_id, days=days, distinct_payers=len(rows), payers=rows)

    # ------------------------------------------------------------------ transfers

    def _next(self, prefix: str) -> int:
        self._seq[prefix] += 1
        return self._seq[prefix]

    def validate_transfer(self, req: TransferRequest) -> None:
        account = self.account(req.account_id)
        if account.customer_ref != req.customer_ref:
            raise BankError(422, "account_customer_mismatch", f"{req.account_id} does not belong to {req.customer_ref}")
        if req.kind == "transfer" and req.payee is None:
            raise BankError(422, "payee_required", "a transfer needs a payee")
        self._require_not_frozen(account)
        if req.payee and req.payee.relation == "same_bank":
            if not req.payee.account_id:
                raise BankError(422, "payee_account_required", "a same_bank payee needs account_id")
            self._require_not_frozen(self.account(req.payee.account_id))

    def _require_not_frozen(self, account: Account) -> None:
        if account.status == "frozen":
            raise BankError(409, "account_frozen", account.account_id)

    def create_transfer(self, req: TransferRequest, scoring: str, status: str, case_id: str | None = None) -> Transfer:
        transfer = Transfer(
            transfer_id=f"tr-{self._next('tr'):04d}",
            status=status,  # type: ignore[arg-type]
            scoring=scoring,  # type: ignore[arg-type]
            case_id=case_id,
            request=req,
            created_at=self._now(),
        )
        self.transfers[transfer.transfer_id] = transfer
        if status == "executed":
            self._book(transfer)
        return transfer

    def transfer(self, transfer_id: str) -> Transfer:
        if transfer_id not in self.transfers:
            raise BankError(404, "not_found", f"transfer {transfer_id}")
        t = self.transfers[transfer_id]
        if t.hold_id:
            t.hold = self._refresh_hold(self.holds[t.hold_id])
        return t

    def patch_transfer(self, transfer_id: str, patch: TransferPatch) -> Transfer:
        t = self.transfer(transfer_id)
        if patch.action == "execute":
            if t.status != "pending_alert":
                raise BankError(409, "wrong_state", f"cannot execute a transfer that is {t.status}; release its hold instead")
            self._execute(t)
        else:
            if t.status not in ("pending_alert", "held"):
                raise BankError(409, "wrong_state", f"cannot cancel a transfer that is {t.status}")
            if t.hold_id:
                hold = self.holds[t.hold_id]
                if hold.status != "released":
                    hold.status, hold.released_at, hold.release_reason = "released", self._now(), f"transfer cancelled: {patch.reason}"
                t.hold = hold
            t.status = "cancelled"
        log.info("transfer %s %s by %s: %s", t.transfer_id, patch.action, patch.actor, patch.reason)
        return t

    def _execute(self, t: Transfer, status: str = "executed") -> None:
        # Re-check at execution time: a freeze may have landed while the transfer was pending.
        self._require_not_frozen(self.account(t.request.account_id))
        if t.request.payee and t.request.payee.relation == "same_bank" and t.request.payee.account_id:
            self._require_not_frozen(self.account(t.request.payee.account_id))
        t.status = status  # type: ignore[assignment]
        self._book(t)

    def _book(self, t: Transfer) -> None:
        """Append the transactions an executed transfer creates (the payee side only for same-bank payees)."""
        req, now = t.request, self._now()
        payee = req.payee
        if req.kind == "cash_withdrawal":
            self._add_txn(req.account_id, now, "withdrawal", req.amount_jpy, req.channel, None, None, None, req.memo)
            return
        assert payee is not None
        category = "company" if ("）" in payee.name_kana or "(" in payee.name_kana) else "individual"
        self._add_txn(req.account_id, now, "transfer_out", req.amount_jpy, req.channel,
                      payee.account_id, payee.name_kana, category, req.memo)
        if payee.relation == "same_bank" and payee.account_id:
            payer = self.account(req.account_id)
            self._add_txn(payee.account_id, now, "transfer_in", req.amount_jpy, req.channel,
                          req.account_id, payer.holder_name_kana, "individual", req.memo)

    def _add_txn(self, account_id, at, kind, amount, channel, cp_account, cp_name, category, memo) -> None:
        self._txn_seq += 1
        self.transactions.setdefault(account_id, []).append(BankTransaction(
            txn_id=f"txn-{self._txn_seq:06d}", account_id=account_id, booked_at=at, kind=kind,
            amount_jpy=amount, channel=channel, counterparty_account_id=cp_account,
            counterparty_name_kana=cp_name, counterparty_category=category, memo=memo,
        ))

    def execute_now(self, t: Transfer) -> None:
        self._execute(t)

    # ------------------------------------------------------------------ holds

    def _refresh_hold(self, hold: Hold) -> Hold:
        if hold.status == "active" and self._now() >= hold.ends_at:
            hold.status = "expired"
        return hold

    def place_hold(self, req: HoldRequest) -> Hold:
        t = self.transfer(req.transfer_id)
        if req.account_id != t.request.account_id:
            raise BankError(422, "account_mismatch", f"{req.account_id} is not the account of {t.transfer_id}")
        if t.status != "pending_alert":
            raise BankError(409, "wrong_state", f"transfer {t.transfer_id} is {t.status}; only a pending_alert transfer can be held")
        placed = self._now()
        w = compute_window(placed, req.window, self.calendar)
        hold = Hold(
            hold_id=f"hold-{self._next('hold'):04d}", account_id=req.account_id, transfer_id=req.transfer_id,
            case_id=req.case_id, placed_by=req.placed_by, placed_at=placed, minimum_ends_at=w.minimum_ends_at,
            ends_at=w.ends_at, cap_ends_at=w.cap_ends_at, status="active", overrides=list(req.overrides),
        )
        self.holds[hold.hold_id] = hold
        t.status, t.hold_id, t.hold = "held", hold.hold_id, hold
        log.info("hold %s placed on %s by %s until %s", hold.hold_id, t.transfer_id, req.placed_by, hold.ends_at)
        return hold

    def hold(self, hold_id: str) -> Hold:
        if hold_id not in self.holds:
            raise BankError(404, "not_found", f"hold {hold_id}")
        return self._refresh_hold(self.holds[hold_id])

    def patch_hold(self, hold_id: str, patch: HoldPatch) -> Hold:
        hold = self.hold(hold_id)
        if hold.status == "released":
            raise BankError(409, "wrong_state", f"hold {hold_id} is already released")
        if patch.action == "keep":
            return hold
        now = self._now()
        if patch.action == "release":
            # A plain release is only for a window that has run out; ending it early needs an override.
            # A hold with no overrides is a bank-policy voluntary wait: it may be released at any time.
            if now < hold.ends_at and hold.overrides:
                raise BankError(409, "hold_active", f"hold runs until {hold.ends_at.isoformat()}; use an override to release it earlier")
        elif patch.action == "override_after_contact_reached":
            if "after_contact_reached" not in hold.overrides:
                raise BankError(409, "override_not_allowed", "this hold does not allow override after contact reached")
            if not patch.contact_reached:
                raise BankError(409, "override_conditions_not_met", "contact_reached must be true")
        else:  # override_after_manager_review
            if "after_manager_review_and_second_confirmation" not in hold.overrides:
                raise BankError(409, "override_not_allowed", "this hold does not allow override after manager review")
            if not (patch.manager_id and patch.second_confirmed_by):
                raise BankError(409, "override_conditions_not_met", "manager_id and second_confirmed_by are required")
            if patch.second_confirmed_by in (patch.manager_id, hold.placed_by):
                raise BankError(409, "override_conditions_not_met", "second_confirmed_by must be a different person")
        t = self.transfers[hold.transfer_id]
        self._execute(t, "released")  # may raise account_frozen; the hold then stays in force
        hold.status, hold.released_at = "released", now
        hold.release_reason = f"{patch.action}: {patch.reason} (by {patch.actor})"
        t.hold = hold
        log.info("hold %s released: %s", hold_id, hold.release_reason)
        return hold

    # ------------------------------------------------------------------ freezes

    def freeze(self, body: FreezeBody) -> Freeze:
        account = self.account(body.account_id)
        existing = next((f for f in self.freezes.values() if f.account_id == body.account_id), None)
        if existing:  # idempotent: a retry returns the first freeze
            return existing
        freeze = Freeze(
            freeze_id=f"frz-{self._next('frz'):04d}", account_id=body.account_id, case_id=body.case_id,
            approved_by=body.approved_by, frozen_at=self._now(), status="frozen",
        )
        self.freezes[freeze.freeze_id] = freeze
        account.status = "frozen"
        log.info("account %s frozen for %s, approved by %s: %s", body.account_id, body.case_id, body.approved_by, body.rationale)
        return freeze
