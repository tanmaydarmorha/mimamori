"""Hand-written models for data that is not a `schemas/` contract: the customer baseline (written by
Scoring, read by the case service's `get_baseline` tool) and the watchlist snapshot (written by the
watchlist loader, read by Scoring)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class SeasonalItem(BaseModel):
    """A recurring unusual-but-normal amount, e.g. the annual April school fee."""

    model_config = ConfigDict(extra="forbid")
    key: str = Field(description="e.g. april_school_fee")
    month: int = Field(ge=1, le=12)
    typical_amount_jpy: int
    tolerance_pct: int = 15
    years_seen: int


class KnownPayee(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name_kana: str
    account_id: str | None = None
    category: str | None = None
    payments: int
    last_paid_on: date


class Baseline(BaseModel):
    """Field names double as the `get_baseline.<field>` facts the investigation agent cites
    (CR 27: absence is a field too, e.g. contractor_payments_count_12y = 0)."""

    model_config = ConfigDict(extra="forbid")
    customer_ref: str
    computed_at: datetime
    customer_tenure_years: int
    median_monthly_withdrawal_jpy: int
    p95_withdrawal_jpy: int
    largest_payment_12m_jpy: int
    contractor_payments_count_12y: int
    renovation_loan_enquiries_count: int = 0
    transfers_to_new_payees_12m: int = 0
    known_payees: list[KnownPayee] = []
    seasonal_items: list[SeasonalItem] = []


class WatchlistEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list_name: Literal["dicj_frozen_accounts", "fsa_unregistered_firms"]
    name_ja: str | None = None
    name_kana: str | None = None
    account_hint: str | None = Field(default=None, description="Bank / branch / account fragment as published")
    notice_date: date
    source_ref: str


class WatchlistSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    list_name: str
    url: str
    fetched_at: datetime
    entries: int


class WatchlistSnapshot(BaseModel):
    """`ref-db`: one dated snapshot per successful loader run; `latest` points at the newest."""

    model_config = ConfigDict(extra="forbid")
    snapshot_id: str = Field(description="YYYY-MM-DD, or YYYY-MM-DDTHHMM when run twice a day")
    created_at: datetime
    sources: list[WatchlistSource]
    entries: list[WatchlistEntry]
    content_hash: str = Field(description="sha256 of the entries; an unchanged re-run writes nothing new")
