"""HTTP API request / response models between Mimamori containers.

The endpoint table and flows are in docs/architecture/api-contracts.md. Data-contract models
(evidence card, wishes, brief, ...) come from `schemas/` via `generated/`; the models here are the
envelopes around them. All times are timezone-aware ISO 8601 (Asia/Tokyo in the demo).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .generated import advance_wishes as _wishes
from .generated import contact_brief as _brief
from .generated import contact_view as _view
from .generated import evidence_card as _card

__all__ = [
    "ApiBase", "ApiError", "Health",
    # core banking
    "Customer", "Account", "BankTransaction", "PayerRow", "PayersResponse",
    "PayeeRef", "TransferRequest", "TransferResponse", "Transfer", "TransferPatch",
    "HoldWindow", "HoldRequest", "Hold", "HoldPatch", "FreezeBody", "Freeze",
    # scoring
    "ScoreSignal", "ScoreRequest", "ScoreResponse", "EventResponse",
    # case service
    "Language", "SetLanguageRequest", "OpenCaseRequest", "OpenCaseResponse", "HoldLineView", "Case", "CaseSummary", "CaseEvent", "Transcript",
    "TurnRequest", "TurnResponse", "DecisionRequest", "DecisionRecord", "DecisionResponse",
    "PoliceSummaryRequest", "PoliceSummaryResponse", "ContactOutcomeRequest",
    "FreezeRequestBody", "FreezeRequest", "FreezeDecisionBody", "OutreachItem", "FreezeDecisionResponse",
    "PlaybookPatch", "DismissIndicatorBody", "WishesChangeResponse",
    # conversation service
    "CallPolicy", "CallRequest", "CallResponse", "Notice",
    "PhoneCallback", "PhoneTurn", "PhoneHangup", "PhoneClientMessage",
    "PhoneSay", "PhoneVerification", "PhoneEnded", "PhoneServerMessage",
    # literals
    "Channel", "TransferKind", "DisclosureField", "PHONE_MENU_RETURN_CALL",
]

Channel = Literal["counter", "atm", "app"]
TransferKind = Literal["transfer", "cash_withdrawal"]
DisclosureField = Literal["transaction_paused", "amount_band", "reason_category", "customer_at_branch", "police_notified"]
PHONE_MENU_RETURN_CALL = "returning_a_call_about_a_case"

JPY = Annotated[int, Field(ge=1)]


class ApiBase(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiError(ApiBase):
    error: str
    detail: str | None = None


class Health(ApiBase):
    status: Literal["ok"] = "ok"
    service: str
    version: str = "0.1.0"


# --------------------------------------------------------------------------- core banking (mock)


class Customer(ApiBase):
    customer_ref: str
    display_name_ja: str
    display_name_kana: str
    tenure_years: int = Field(ge=0)
    branch_name_ja: str


class Account(ApiBase):
    account_id: str
    customer_ref: str
    holder_name_kana: str
    branch_name_ja: str
    opened_on: str = Field(description="ISO date")
    balance_jpy: int
    status: Literal["active", "frozen"] = "active"


class BankTransaction(ApiBase):
    txn_id: str
    account_id: str
    booked_at: datetime
    kind: Literal["deposit", "withdrawal", "transfer_out", "transfer_in", "direct_debit"]
    amount_jpy: JPY
    channel: Channel | Literal["system"]
    counterparty_account_id: str | None = None
    counterparty_name_kana: str | None = None
    counterparty_category: str | None = Field(
        default=None,
        description="e.g. pension, utilities, school, contractor, individual, retailer. Bank-side payee classification.",
    )
    memo: str | None = None


class PayerRow(ApiBase):
    customer_ref: str
    account_id: str
    display_name_ja: str
    payments: int
    total_jpy: int
    last_paid_at: datetime


class PayersResponse(ApiBase):
    """`GET /accounts/{id}/payers?days=7`: distinct payers to this account, completed transfers only."""

    account_id: str
    days: int
    distinct_payers: int
    payers: list[PayerRow]


class PayeeRef(ApiBase):
    name_kana: str
    relation: Literal["same_bank", "other_bank"]
    account_id: str | None = Field(default=None, description="Present for same_bank payees.")


class TransferRequest(ApiBase):
    """`POST /transfers`. The teller keys it in (counter) or the channel submits it (atm/app)."""

    customer_ref: str
    account_id: str
    channel: Channel
    kind: TransferKind
    amount_jpy: JPY
    payee: PayeeRef | None = None
    memo: str | None = None
    teller_id: str | None = None


class TransferResponse(ApiBase):
    transfer_id: str
    status: Literal["executed", "pending_alert", "held", "released", "cancelled"]
    scoring: Literal["allow", "alert", "unavailable", "not_checked"] = Field(
        description="`unavailable` = Scoring timed out or errored and the transfer proceeded (fail open, DA 7). `not_checked` = post-transaction channel."
    )
    case_id: str | None = None
    hold_id: str | None = None


class TransferPatch(ApiBase):
    """`PATCH /transfers/{id}`: the case service resolves a pending transfer the teller cleared
    without a hold (`execute`) or the customer withdrew (`cancel`). Releasing a hold executes the
    transfer by itself."""

    action: Literal["execute", "cancel"]
    actor: str
    reason: str


class HoldWindow(ApiBase):
    """Copied from the customer's wishes. Hold ends at max(placed + minimum_hours, next business-day
    close if extend_to_next_business_day_close), but never later than placed + cap_hours (CR 25)."""

    minimum_hours: int = Field(ge=1, le=24)
    extend_to_next_business_day_close: bool
    cap_hours: int = Field(ge=1, le=24)


HoldOverride = Literal["after_contact_reached", "after_manager_review_and_second_confirmation"]


class HoldRequest(ApiBase):
    """`POST /holds`."""

    account_id: str
    transfer_id: str
    case_id: str
    placed_by: str
    window: HoldWindow
    overrides: list[HoldOverride]


class Hold(ApiBase):
    hold_id: str
    account_id: str
    transfer_id: str
    case_id: str
    placed_by: str
    placed_at: datetime
    minimum_ends_at: datetime
    ends_at: datetime = Field(description="Computed end of the pause (after extension and cap).")
    cap_ends_at: datetime
    status: Literal["active", "released", "expired"]
    overrides: list[HoldOverride]
    released_at: datetime | None = None
    release_reason: str | None = None


class Transfer(TransferResponse):
    """`GET /transfers/{id}`."""

    request: TransferRequest
    created_at: datetime
    hold: Hold | None = None


class HoldPatch(ApiBase):
    """`PATCH /holds/{id}`. `override_after_contact_reached` needs `contact_reached=true`;
    `override_after_manager_review` needs `manager_id` and `second_confirmed_by`."""

    action: Literal["release", "override_after_contact_reached", "override_after_manager_review", "keep"]
    reason: str
    actor: str
    contact_reached: bool = False
    manager_id: str | None = None
    second_confirmed_by: str | None = None


class FreezeBody(ApiBase):
    """`POST /freezes`, only after an analyst approved (CR 21)."""

    account_id: str
    case_id: str
    approved_by: str
    rationale: str


class Freeze(ApiBase):
    freeze_id: str
    account_id: str
    case_id: str
    approved_by: str
    frozen_at: datetime
    status: Literal["frozen"]


# --------------------------------------------------------------------------- scoring


class ScoreSignal(ApiBase):
    """One computed fact behind an alert. Becomes a fact claim on the evidence card (same fields)."""

    code: str = Field(description="e.g. amount_vs_baseline, new_payee, payee_account_age, payer_fan_in")
    statement_en: str
    tool: _card.Tool
    field: str
    value: Any


class ScoreRequest(ApiBase):
    """`POST /v1/score` (pre-transaction) and `POST /v1/events` (post-transaction)."""

    transfer_id: str
    customer_ref: str
    account_id: str
    channel: Channel
    kind: TransferKind
    amount_jpy: JPY
    payee: PayeeRef | None = None
    memo: str | None = None
    occurred_at: datetime


class ScoreResponse(ApiBase):
    decision: Literal["allow", "alert"]
    signals: list[ScoreSignal] = []
    case_id: str | None = Field(default=None, description="Set on alert: Scoring has already opened the case.")
    matched_baseline: str | None = Field(
        default=None, description="Why an unusual amount was fine, e.g. seasonal:april_school_fee."
    )
    scored_at: datetime
    latency_ms: int | None = None


class EventResponse(ScoreResponse):
    """`POST /v1/events`. Post-transaction monitoring never opens a case in the prototype (step 2);
    `decision=alert` here is only logged."""


# --------------------------------------------------------------------------- case service

CaseStatus = Literal["open", "paused", "released", "closed"]


class OpenCaseRequest(ApiBase):
    """`POST /cases`, called by Scoring on alert."""

    transfer_id: str
    customer_ref: str
    account_id: str
    request: _card.Request
    signals: list[ScoreSignal]
    opened_at: datetime


class OpenCaseResponse(ApiBase):
    case_id: str
    status: CaseStatus


class Transcript(ApiBase):
    turn_id: str = Field(pattern=r"^[ct][0-9]+$", description="c<n> customer, t<n> teller")
    speaker: Literal["customer", "teller"]
    text: str
    at: datetime


class DecisionRecord(ApiBase):
    decision_id: str
    case_id: str
    action: Literal["pause", "release"]
    basis: Literal["advance_wishes", "bank_policy"] | None = None
    release_reason: str | None = None
    rationale: str
    decided_by: str
    manager_id: str | None = None
    decided_at: datetime
    warnings: list[str] = []


class FreezeRequest(ApiBase):
    freeze_id: str
    case_id: str
    account_id: str
    requested_by: str
    reason: str
    requested_at: datetime
    status: Literal["pending", "approved", "rejected"]
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_rationale: str | None = None


Language = Literal["ja", "en"]


class CaseSummary(ApiBase):
    case_id: str
    language: Language = "ja"
    status: CaseStatus
    customer_ref: str
    opened_at: datetime
    amount_jpy: int
    risk_level: Literal["low", "elevated", "high"] | None = None


class HoldLineView(ApiBase):
    """The approved hold line the teller reads when a pause is recommended, from the bank or playbook."""

    id: str
    ja: str
    en: str


class Case(CaseSummary):
    account_id: str
    transfer_id: str
    request: _card.Request
    signals: list[ScoreSignal]
    card: _card.EvidenceCardCaseDb | None = None
    hold_line: HoldLineView | None = Field(default=None, description="Filled text for card.risk.hold_line_id, set while a pause is recommended.")
    transcript: list[Transcript] = []
    decisions: list[DecisionRecord] = []
    hold: Hold | None = None
    call_id: str | None = None
    case_code: str | None = None
    contact_view: _view.ContactViewConversationServiceCaseService | None = None
    verification_failed: bool = False
    contact_suspected: str | None = Field(default=None, description="Why no call was made, if so.")
    freeze_request: FreezeRequest | None = None


class CaseEvent(ApiBase):
    """One SSE message on `GET /cases/{id}/events` (`event:` = type, `data:` = this JSON, `id:` = seq)."""

    seq: int
    case_id: str
    type: Literal[
        "case_opened", "card_updated", "transcript_turn", "decision_logged", "hold_placed", "hold_updated",
        "police_summary_issued", "contact_notice_sent", "contact_outcome", "verification_failed",
        "freeze_requested", "freeze_decided", "outreach_ready", "wishes_frozen",
    ]
    at: datetime
    data: dict[str, Any] = {}


class TurnRequest(ApiBase):
    """`POST /cases/{id}/turns`: a typed turn (fallback for STT) from either speaker. Only
    `customer` turns trigger a copilot model call; the teller's turns are kept for the transcript."""

    speaker: Literal["customer", "teller"] = "customer"
    text: str = Field(min_length=1)


class TurnResponse(ApiBase):
    turn_id: str
    card: _card.EvidenceCardCaseDb | None = Field(
        description="Updated card after a customer turn; null for a teller turn."
    )


class DecisionRequest(ApiBase):
    """`POST /cases/{id}/decision`. A human decides every pause and release (DA 11)."""

    action: Literal["pause", "release"]
    basis: Literal["advance_wishes", "bank_policy"] | None = None
    release_reason: Literal[
        "customer_override_after_contact_reached", "manager_review_second_confirmation", "cleared_by_teller"
    ] | None = None
    rationale: str = Field(min_length=1)
    teller_id: str
    manager_id: str | None = None
    second_confirmed_by: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.action == "pause" and not self.basis:
            raise ValueError("pause needs a basis (advance_wishes or bank_policy)")
        if self.action == "release" and not self.release_reason:
            raise ValueError("release needs a release_reason")
        if self.release_reason == "manager_review_second_confirmation" and not (self.manager_id and self.second_confirmed_by):
            raise ValueError("manager review needs manager_id and second_confirmed_by")
        return self


class DecisionResponse(ApiBase):
    decision: DecisionRecord
    status: CaseStatus
    hold: Hold | None = None
    warnings: list[str] = Field(default=[], description="e.g. single_source_pause (logged, never blocking)")


class PoliceSummaryRequest(ApiBase):
    """`POST /cases/{id}/police-summary`. On the officers' request, limited to `requested_items`."""

    officer_name: str = Field(min_length=1)
    officer_title: str = Field(min_length=1)
    requested_items: list[Literal["amount", "payee", "customer_statements", "indicators", "timeline"]] = Field(min_length=1)
    teller_id: str


class PoliceSummaryResponse(ApiBase):
    summary_id: str
    issued_at: datetime
    officer_name: str
    officer_title: str
    items: dict[str, Any] = Field(description="Only the requested sections.")
    text_ja: str = Field(description="Printable text, built from the same requested sections.")


class ContactOutcomeRequest(ApiBase):
    """`POST /cases/{id}/contact-outcome`, from the conversation service."""

    call_id: str
    outcome: Literal["contact_view", "verification_failed"]
    contact_view: _view.ContactViewConversationServiceCaseService | None = None

    @model_validator(mode="after")
    def _check(self):
        if (self.outcome == "contact_view") != (self.contact_view is not None):
            raise ValueError("contact_view must be present exactly when outcome == 'contact_view'")
        return self


class FreezeRequestBody(ApiBase):
    """`POST /cases/{id}/freeze-request`."""

    requested_by: str
    reason: str = Field(min_length=1)


class FreezeDecisionBody(ApiBase):
    """`POST /cases/{id}/freeze-decision`. The analyst decides (CR 21)."""

    decision: Literal["approve", "reject"]
    analyst_id: str
    rationale: str = Field(min_length=1)


class OutreachItem(ApiBase):
    customer_ref: str
    display_name_ja: str
    account_id: str
    last_paid_at: datetime
    total_jpy: int


class FreezeDecisionResponse(ApiBase):
    freeze_request: FreezeRequest
    freeze: Freeze | None = None
    outreach: list[OutreachItem] = Field(default=[], description="Other payers to the frozen account (excludes the case customer).")


class DismissIndicatorBody(ApiBase):
    """`POST /cases/{id}/claims/{claim_id}/dismiss`. Only a teller dismissal removes a verified
    indicator from the card (accumulation rule); it is audited."""

    teller_id: str
    reason: str = Field(min_length=1)


class WishesChangeResponse(ApiBase):
    """`PUT /customers/{ref}/wishes` result. During an open case the new version is stored as
    `frozen_pending_review` and the previous contact is notified (DA 12)."""

    customer_ref: str
    version: int
    status: Literal["active", "frozen_pending_review"]
    frozen_reason: str | None = None


class PlaybookPatch(ApiBase):
    """`PATCH /playbooks/{id}`. Only the case service may set `approved` (analyst role)."""

    status: Literal["approved", "rejected", "retired"]
    analyst_id: str
    note: str | None = None


# --------------------------------------------------------------------------- conversation service


class CallPolicy(ApiBase):
    may_disclose: list[DisclosureField]
    require_caller_number_match: Literal[True] = True
    require_case_code_match: Literal[True] = True


class CallRequest(ApiBase):
    """`POST /calls`. The brief is built in code by the case service; this is all the data the
    conversation service ever gets about a case."""

    brief: _brief.ContactBriefCaseServiceConversationService
    policy: CallPolicy


class CallResponse(ApiBase):
    call_id: str
    status: Literal["notice_sent"]
    notice_text_ja: str


class SetLanguageRequest(ApiBase):
    """`PATCH /cases/{id}/language`. Allowed until the first turn; then 409 `language_locked`. Audited."""

    language: Language
    actor: str


class Notice(ApiBase):
    """`GET /notices?to=<e164>`: what the simulated phone shows. Reveals nothing about the case."""

    call_id: str
    to_phone_e164: str
    sent_at: datetime
    text: str = Field(description="The notice, in `language`.")
    language: Language
    gloss_en: str | None = Field(default=None, description="English gloss for display; set only when language == ja.")
    published_phone_e164: str
    case_code: str
    audio_b64: str | None = None


class PhoneCallback(ApiBase):
    """First client message on `WS /phone`: the contact calls the published number."""

    type: Literal["callback"] = "callback"
    caller_number: str
    menu_choice: str = Field(description=f"'{PHONE_MENU_RETURN_CALL}' for the callback menu item")
    case_code: str


class PhoneTurn(ApiBase):
    type: Literal["turn"] = "turn"
    text: str | None = Field(default=None, description="Typed text (fallback). Audio goes as binary frames.")


class PhoneHangup(ApiBase):
    type: Literal["hangup"] = "hangup"


PhoneClientMessage = Annotated[PhoneCallback | PhoneTurn | PhoneHangup, Field(discriminator="type")]


class PhoneSay(ApiBase):
    type: Literal["say"] = "say"
    text: str = Field(description="What is spoken, in `language`.")
    language: Language
    gloss_en: str | None = Field(default=None, description="English gloss for display; set only when language == ja.")
    audio_b64: str | None = None
    template_intent: str | None = Field(default=None, description="Which template produced it, for audit.")


class PhoneVerification(ApiBase):
    type: Literal["verification"] = "verification"
    ok: bool


class PhoneEnded(ApiBase):
    type: Literal["ended"] = "ended"
    reason: Literal["hangup", "verification_failed", "completed"]


PhoneServerMessage = Annotated[PhoneSay | PhoneVerification | PhoneEnded, Field(discriminator="type")]
