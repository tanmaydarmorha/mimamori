"""Fake core-bank-mock and case-svc, as ASGI apps, built from docs/architecture/api-contracts.md only.

They exist so the sim's plumbing (clients, arms, runner, report) runs and is tested without the real
services, and so `sim-job run --fake-services` can show the report layout. THEY ARE NOT THE REAL
SERVICES: scoring is "alert at or above ¥1M", the "copilot" is a keyword extractor feeding the real
`mimamori_common.rules.assess_risk`, and numbers from a fake run say nothing about Mimamori. The report
says so on its first line when these are used.

Needs fastapi (`pip install "sim-job[fake]"`); imported lazily by the CLI.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from mimamori_common.config import JST
from mimamori_common.rules import assess_risk, merge_indicators, verify_quotes
from mimamori_common.schemas import load_example

_KEYWORDS = [  # (indicator type, regex over a customer turn)
    ("impersonated_official", r"警察|検察|検事|警視庁"),
    ("secrecy_instruction", r"誰にも言うな|言うなと|言っちゃいけ|言ってはいけ|言わないで"),
    ("safe_account_transfer", r"安全な口座|犯罪に使われ"),
    ("cash_or_card_handover", r"取りに来|駅で渡す|自宅に置"),
    ("urgency", r"今日中"),
    ("impersonated_relative", r"息子が|息子から"),
]
_QUEUE = ["q.general.purpose", "q.general.who_asked", "q.general.on_phone", "q.general.documents",
          "q.general.family_aware", "q.general.deadline", "q.general.recent_calls"]


class FakeWorld:
    """Shared state of the two fake services. `scoring_fn(body) -> bool` decides alerts."""

    def __init__(self, scoring_fn=None, unavailable: bool = False):
        self.scoring_fn = scoring_fn or (lambda body: body["amount_jpy"] >= 1_000_000)
        self.unavailable = unavailable
        self.cases: dict[str, dict] = {}
        self.transfers: dict[str, dict] = {}
        self.requests: list[tuple[str, str, str]] = []  # (service, method, path) for tests
        self._bank = {q["id"]: q for q in load_example("question-bank-general.json")["questions"]}
        self.core_app = self._core()
        self.case_app = self._case()

    # ------------------------------------------------------------------ transports
    def core_transport(self) -> httpx.ASGITransport:
        return httpx.ASGITransport(app=self.core_app)

    def case_transport(self) -> httpx.ASGITransport:
        return httpx.ASGITransport(app=self.case_app)

    # ------------------------------------------------------------------ core-bank-mock
    def _core(self) -> FastAPI:
        app = FastAPI()
        world = self

        @app.get("/healthz")
        def health():
            return {"status": "ok", "service": "core-bank-mock-fake", "version": "0.1.0"}

        @app.post("/transfers")
        def post_transfer(body: dict, request: Request):
            world.requests.append(("core", "POST", "/transfers"))
            tid = f"tr-fake-{len(world.transfers) + 1:04d}"
            if world.unavailable:
                world.transfers[tid] = {"status": "executed"}
                return {"transfer_id": tid, "status": "executed", "scoring": "unavailable", "case_id": None, "hold_id": None}
            if not world.scoring_fn(body):
                world.transfers[tid] = {"status": "executed"}
                return {"transfer_id": tid, "status": "executed", "scoring": "allow", "case_id": None, "hold_id": None}
            case_id = f"case-fake-{len(world.cases) + 1:04d}"
            payee = body.get("payee")
            world.cases[case_id] = {
                "case_id": case_id, "transfer_id": tid, "body": body, "turns": [], "indicators": [], "asked": [],
                "status": "open", "decisions": [], "risk": {"level": "low", "pause_recommended": False,
                                                          "rule_version": "risk-v1", "fired": [], "hold_line_id": None},
                "request": {"channel": body["channel"], "kind": body["kind"], "amount_jpy": body["amount_jpy"],
                            "payee": ({"name_kana": payee["name_kana"], "relation": payee["relation"]} if payee else None)},
            }
            world.transfers[tid] = {"status": "pending_alert", "case_id": case_id}
            return {"transfer_id": tid, "status": "pending_alert", "scoring": "alert", "case_id": case_id, "hold_id": None}

        return app

    # ------------------------------------------------------------------ case-svc
    def _card(self, c: dict) -> dict:
        card = load_example("evidence-card-tanaka.json")
        card["case_id"], card["customer_ref"] = c["case_id"], c["body"]["customer_ref"]
        card["request"] = c["request"]
        card["claims"] = [x for x in card["claims"] if x["kind"] == "fact"]
        card["risk"] = c["risk"]
        nxt = next((q for q in _QUEUE if q not in c["asked"]), None)
        card["next_question"] = {"question_id": nxt, "ja_filled": self._bank[nxt]["ja"]} if nxt else None
        card["dropped"] = []
        return card

    def _case_json(self, c: dict) -> dict:
        now = datetime.now(JST).isoformat()
        hold_line = None
        if c["risk"]["pause_recommended"]:
            hold_line = {"id": "h.general.protect", "ja": "お客様の大切なご資産をお守りするため、念のため、本日のお手続きを少しの間お待ちいただけますでしょうか。",
                         "en": "To protect your assets, could you wait a little while?"}
        return {
            "case_id": c["case_id"], "status": c["status"], "customer_ref": c["body"]["customer_ref"], "opened_at": now,
            "amount_jpy": c["body"]["amount_jpy"], "risk_level": c["risk"]["level"], "account_id": c["body"]["account_id"],
            "transfer_id": c["transfer_id"], "request": c["request"],
            "signals": [{"code": "amount_vs_baseline", "statement_en": "fake signal", "tool": "get_baseline",
                         "field": "amount_vs_median_ratio", "value": 20}],
            "card": self._card(c), "hold_line": hold_line, "transcript": [], "decisions": [], "hold": None,
        }

    def _case(self) -> FastAPI:
        app = FastAPI()
        world = self

        def get(case_id: str) -> dict:
            if case_id not in world.cases:
                raise HTTPException(404, "unknown case")
            return world.cases[case_id]

        @app.get("/healthz")
        def health():
            return {"status": "ok", "service": "case-svc-fake", "version": "0.1.0"}

        @app.get("/cases/{case_id}")
        def get_case(case_id: str):
            return world._case_json(get(case_id))

        @app.post("/cases/{case_id}/turns")
        def post_turn(case_id: str, body: dict):
            c = get(case_id)
            world.requests.append(("case", "POST", f"/cases/{case_id}/turns"))
            n = len(c["turns"]) + 1
            speaker = body.get("speaker", "customer")
            turn_id = f"{'c' if speaker == 'customer' else 't'}{sum(1 for t in c['turns'] if t['speaker'] == speaker) + 1}"
            c["turns"].append({"turn_id": turn_id, "speaker": speaker, "text": body["text"]})
            if speaker == "teller":
                for q in _QUEUE:
                    if world._bank[q]["ja"] == body["text"] and q not in c["asked"]:
                        c["asked"].append(q)
                return {"turn_id": turn_id, "card": None}
            customer_turns = {t["turn_id"]: t["text"] for t in c["turns"] if t["speaker"] == "customer"}
            found = [{"type": typ, "turn_id": turn_id, "quote": m.group(0)}
                     for typ, rx in _KEYWORDS if (m := re.search(rx, body["text"]))]
            kept, _ = verify_quotes(found, customer_turns)
            c["indicators"] = merge_indicators(c["indicators"], kept)
            c["risk"] = {**assess_risk(c["indicators"], {"consistent_with_history": "unknown"}, {}),
                         "hold_line_id": None}
            c["risk"]["fired"] = [{"condition": f, "claims": ["f1"]} for f in c["risk"]["fired"]]
            if c["risk"]["pause_recommended"]:
                c["risk"]["hold_line_id"] = "h.general.protect"
            return {"turn_id": turn_id, "card": world._card(c)}

        @app.post("/cases/{case_id}/decision")
        def decision(case_id: str, body: dict):
            c = get(case_id)
            world.requests.append(("case", "POST", f"/cases/{case_id}/decision"))
            c["status"] = "paused" if body["action"] == "pause" else "released"
            now = datetime.now(JST).isoformat()
            rec = {"decision_id": f"dec-fake-{len(c['decisions']) + 1}", "case_id": case_id, "action": body["action"],
                   "basis": body.get("basis"), "release_reason": body.get("release_reason"), "rationale": body["rationale"],
                   "decided_by": body["teller_id"], "manager_id": None, "decided_at": now, "warnings": []}
            c["decisions"].append(rec)
            return {"decision": rec, "status": c["status"], "hold": None, "warnings": []}

        @app.get("/playbooks")
        def playbooks(status: str | None = None):
            rows = load_example("playbooks.json")
            return [r for r in rows if not status or r["status"] == status]

        return app


def make_clients(world: FakeWorld) -> tuple[Any, Any]:
    from .clients import CaseSvcClient, CoreBankClient

    return (CoreBankClient("http://core.fake", transport=world.core_transport()),
            CaseSvcClient("http://case.fake", transport=world.case_transport()))
