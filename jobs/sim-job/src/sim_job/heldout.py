"""The held-out set: public fake-police cases published on or after T, and the date-split guard (CR 16, CR 28).

Cases live in `data/heldout_cases.json` (from docs/research.md R2). Reported as a case-by-case failure
analysis, not rates: n is small, the cases are victim-side narratives that were not stopped at a counter,
and every replay needs assumptions, which the report prints next to each case.

Three role-played variants per runnable case:
  candid          the victim tells the teller what the caller told them (as far as the source records it);
  coached         the victim gives a generic cover story, denies being instructed, and says the papers are
                  "coming later";
  coached-papers  as coached, but the victim produces papers (scammers do send invoices).
Coached is the behaviour the NPA itself says defeats today's counter check (research R1 [6]). Its cover
story and its documents behaviour are assumptions (no source states them), which is why both document
behaviours are run rather than one picked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from importlib import resources
from typing import Any

from .params import T
from .personas import candid_persona, coached_persona
from .scenarios import CustomerSpec, PayeeSpec, Scenario

COACHED_COVER_DEFAULT = "家のことでお金が必要なんです。"  # ASSUMPTION: no source states the victim's cover story
_PAYEE_KANA = ["カ）ミズホシヨウジ", "カ）ホクセイシヨウカイ", "カ）アオバトレーディング", "カ）ミナトロジスティクス",
               "カ）ヤマボシコウサン", "カ）ワカバキカク", "カ）ナギサカンリ", "カ）ツバサトウシ"]


VARIANTS = ("candid", "coached", "coached-papers")


class CutoffViolation(AssertionError):
    """A playbook or held-out case breaks the date split."""


@dataclass(frozen=True)
class HeldOutSet:
    cutoff: date
    target_cases: int
    cases: list[dict]
    excluded: list[dict]

    @property
    def runnable(self) -> list[dict]:
        return [c for c in self.cases if c["runnable"]]


def load_heldout(path: str | None = None) -> HeldOutSet:
    if path:
        raw = json.loads(open(path, encoding="utf-8").read())
    else:
        raw = json.loads(resources.files("sim_job").joinpath("data/heldout_cases.json").read_text(encoding="utf-8"))
    hs = HeldOutSet(date.fromisoformat(raw["cutoff_T"]), raw["target_cases"], raw["cases"], raw.get("excluded", []))
    assert_cases_after_cutoff(hs.cases, hs.cutoff)
    return hs


def assert_cases_after_cutoff(cases: list[dict], cutoff: date) -> None:
    for c in cases:
        published = date.fromisoformat(c["published_at"])
        if published < cutoff:
            raise CutoffViolation(f"held-out case {c['id']} published {published} is before T = {cutoff}")


def _as_dict(playbook: Any) -> dict:
    return playbook.model_dump(mode="json") if hasattr(playbook, "model_dump") else playbook


def assert_playbooks_before_cutoff(playbooks: list[Any], cutoff: date = T, heldout: HeldOutSet | None = None) -> list[dict]:
    """Every playbook the copilot may use must have every source `published_at` before T (CR 16, CR 28),
    and must not cite a held-out case's source URL (no leakage the other way).

    Returns a table of what was checked, for the report. Raises CutoffViolation on the first problem.
    """
    held_urls = {c["source_url"] for c in (heldout.cases if heldout else [])}
    rows = []
    for raw in playbooks:
        pb = _as_dict(raw)
        sources = pb.get("sources") or []
        if not sources:
            raise CutoffViolation(f"playbook {pb['id']} has no sources with published_at (CR 28)")
        latest = None
        for src in sources:
            published = src.get("published_at")
            if not published:
                raise CutoffViolation(f"playbook {pb['id']} source {src.get('url')} has no published_at")
            d = date.fromisoformat(str(published)[:10])
            if d >= cutoff:
                raise CutoffViolation(f"playbook {pb['id']} source {src.get('url')} published {d} is not before T = {cutoff}")
            if src.get("url") in held_urls:
                raise CutoffViolation(f"playbook {pb['id']} cites held-out source {src.get('url')}")
            latest = max(latest, d) if latest else d
        first_seen = pb.get("first_seen")
        if first_seen and date.fromisoformat(str(first_seen)[:10]) >= cutoff:
            raise CutoffViolation(f"playbook {pb['id']} first_seen {first_seen} is not before T = {cutoff}")
        rows.append({"id": pb["id"], "status": pb.get("status"), "latest_source_published_at": latest.isoformat()})
    return rows


def to_scenarios(hs: HeldOutSet) -> list[Scenario]:
    """Three scenarios (see VARIANTS) per runnable case. All ground truth is `scam`: every held-out case
    is a reported fake-police victimisation."""
    out: list[Scenario] = []
    for n, c in enumerate(hs.runnable, start=1):
        m = c["modelled"]
        cash = m["kind"] == "cash_withdrawal"
        ins = c["instructions"]
        payee = None if cash else PayeeSpec("other_bank", _PAYEE_KANA[(n - 1) % len(_PAYEE_KANA)])
        personas = {
            "candid": candid_persona(
                f"{c['id']}-candid", claimed=c["claimed_ja"], cash=cash, secrecy=bool(ins["secrecy"]),
                threat=bool(ins["threat"]), live_contact=bool(ins["live_contact"]),
                description=f"candid replay of {c['id']} ({c['impersonation']})"),
            "coached": coached_persona(
                f"{c['id']}-coached", cover=ins.get("cover_story_stated") or COACHED_COVER_DEFAULT, cash=cash,
                secrecy_leak=bool(ins["secrecy"]), docs="later",
                description=f"coached replay of {c['id']}: generic cover story, documents 'later' (assumed)"),
            "coached-papers": coached_persona(
                f"{c['id']}-coached-papers", cover=ins.get("cover_story_stated") or COACHED_COVER_DEFAULT, cash=cash,
                secrecy_leak=bool(ins["secrecy"]), docs="provided",
                description=f"coached replay of {c['id']}: generic cover story, papers produced (assumed)"),
        }
        for tag, (variant, persona) in zip("ABC", personas.items()):
            ref = f"cust-ho-{n:02d}-{variant}"  # one synthetic customer per replay: no shared account state
            spec = CustomerSpec(ref=ref, name_ja=f"保留 {n:02d}{tag}", name_kana=f"ホリュウ {n:02d}{tag}",
                                tenure_years=15, income_jpy=200_000, median_withdrawal_jpy=60_000)
            out.append(Scenario(
                id=f"{c['id']}-{variant}", label=f"{c['id']} {variant}: {c['impersonation']}", ground_truth="scam",
                set="heldout", customer_ref=ref,
                account_id="acct-" + ref.removeprefix("cust-"), kind=m["kind"], amount_jpy=m["amount_jpy"],
                persona=persona, payee=payee,
                new_customer=spec,
                source={"case_id": c["id"], "variant": variant, "assumptions": c["assumptions"],
                        "source_url": c["source_url"], "published_at": c["published_at"]}))
    return out
