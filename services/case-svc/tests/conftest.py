from __future__ import annotations

import json
import os
import re
from contextlib import ExitStack
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mimamori_common.config import Settings
from mimamori_common.llm import FakeClient
from mimamori_common.models import PayeeRef, TransferRequest
from mimamori_common.store import reset_memory_stores

from case_svc.app import create_case_app
from case_svc.config import SvcConfig
from case_svc.deps import Deps, build_deps

from fakes import FakeBank, FakeConversation, FakeScoring, compute_baseline

DEMO_NOW = "2026-10-13T11:42:00+09:00"
FIXTURES = Path(__file__).parent / "fixtures"
REPLAY = json.loads((FIXTURES / "replay.json").read_text())
REPLAY_EN = json.loads((FIXTURES / "replay_en.json").read_text())  # A, B, C in English
REPLAYS = {"ja": REPLAY, "en": REPLAY_EN}
STAFF = {"X-Mimamori-Role": "teller", "X-Mimamori-User": "teller-sato"}
ANALYST = {"X-Mimamori-Role": "analyst", "X-Mimamori-User": "analyst-ito"}

HERO_SIGNALS = [
    {"code": "amount_vs_baseline", "statement_en": "60x baseline", "tool": "get_baseline", "field": "amount_vs_median_ratio", "value": 60},
    {"code": "new_payee", "statement_en": "new payee", "tool": "get_baseline", "field": "new_payee", "value": True},
    {"code": "payee_account_age", "statement_en": "payee account 4 days old", "tool": "counterpart_graph", "field": "account_age_days", "value": 4},
    {"code": "payer_fan_in", "statement_en": "7 payers this week", "tool": "counterpart_graph", "field": "distinct_payers_7d", "value": 7},
]


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith(("MIMAMORI_", "OLLAMA_", "CORE_BANK", "SCORING_", "CASE_SVC", "CONVERSATION_SVC")):
            monkeypatch.delenv(key, raising=False)
    reset_memory_stores()
    yield
    reset_memory_stores()


def tool_results(user: str) -> dict[str, dict]:
    """Parse `<data label="tool_result:NAME">{json}</data>` blocks out of an investigation prompt."""
    return {m.group(1): json.loads(m.group(2)) for m in re.finditer(r'<data label="tool_result:([a-z_]+)">\n(.*?)\n</data>', user, re.S)}


PLAN = ["get_baseline", "recent_transactions", "explain_payee", "counterpart_graph", "check_lists", "search_playbooks",
        "get_advance_wishes", "teller_notes"]


def scripted_investigator(plan=PLAN, finish=None, per_step=None) -> FakeClient:
    """A model that asks for the tools in `plan` (all at once, or `per_step` at a time), then finishes. `finish(results)` builds the final payload; the default
    states each tool field truthfully (the happy path)."""

    def default_finish(results: dict[str, dict]) -> dict:
        facts = []
        for tool, res in results.items():
            for field, value in res.items():
                if isinstance(value, (int, bool, str)) and field != "watchlist_snapshot_id":
                    facts.append({"tool": tool, "field": field, "value": value, "statement_en": f"{tool} {field}"})
        grounds = [g for g in ("counterpart_graph.account_age_days", "counterpart_graph.distinct_payers_7d") if g.split(".")[1] in results.get("counterpart_graph", {})]
        return {"facts": facts, "inferences": [{"statement_en": "The payee account looks like a newly opened collection account.",
                                                "grounds": grounds}] if grounds else [],
                "leading_hypothesis": "fake_police" if grounds else "legitimate", "first_question_id": "q.general.purpose"}

    def handler(system: str, user: str, schema: dict):
        done = tool_results(user)
        base = {"action": "finish", "tools": [], "playbook_hypothesis": "none", "facts": [], "inferences": [],
                "leading_hypothesis": "other_scam", "first_question_id": "q.general.purpose"}
        todo = [t for t in plan if t not in done]
        if todo and "call_tool" in schema["properties"]["action"]["enum"]:
            return {**base, "action": "call_tool", "tools": todo[:per_step] if per_step else todo}
        return {**base, **(finish or default_finish)(done)}

    return FakeClient(json_handler=handler, name="fake-investigator")


@dataclass
class Env:
    client: TestClient
    deps: Deps
    bank: FakeBank
    conv: FakeConversation
    scoring: FakeScoring
    copilot: FakeClient
    investigator: FakeClient

    def open_case(self, customer_ref="cust-tanaka-0001", account_id="acct-tanaka-0001", payee_account="acct-mule-0001",
                  amount=3_000_000, signals=None, transfer_id="tr-0001", kind="transfer") -> str:
        payee = None
        if payee_account:
            acct = self.bank.accounts[payee_account]
            payee = PayeeRef(name_kana=acct.holder_name_kana, relation="same_bank", account_id=payee_account)
        req = TransferRequest(customer_ref=customer_ref, account_id=account_id, channel="counter", kind=kind, amount_jpy=amount, payee=payee)
        self.bank.add_transfer(transfer_id, req)
        body = {"transfer_id": transfer_id, "customer_ref": customer_ref, "account_id": account_id,
                "request": {"channel": "counter", "kind": kind, "amount_jpy": amount,
                            "payee": {"name_kana": payee.name_kana, "relation": "same_bank"} if payee else None},
                "signals": HERO_SIGNALS if signals is None else signals, "opened_at": DEMO_NOW}
        resp = self.client.post("/cases", json=body)
        assert resp.status_code == 200, resp.text
        return resp.json()["case_id"]

    def turn(self, case_id: str, text: str, speaker="customer"):
        resp = self.client.post(f"/cases/{case_id}/turns", json={"speaker": speaker, "text": text})
        assert resp.status_code == 200, resp.text
        return resp.json()

    def case(self, case_id: str) -> dict:
        resp = self.client.get(f"/cases/{case_id}")
        assert resp.status_code == 200, resp.text
        return resp.json()


@pytest.fixture
def make_env():
    stack = ExitStack()

    def make(copilot: FakeClient | None = None, investigator: FakeClient | None = None, svc: dict | None = None,
             conv_fail: bool = False, baselines: bool = True) -> Env:
        settings = replace(Settings.from_env(), demo_now=DEMO_NOW, service_name="case-svc", copilot_backend="fake")
        bank = FakeBank(settings.now())
        conv, scoring = FakeConversation(fail=conv_fail), FakeScoring(bank)
        cfg = SvcConfig(**{"investigation_inline": True, "case_code": "4821", **(svc or {})})
        model = copilot or FakeClient()
        inv = investigator or scripted_investigator()
        deps = build_deps(settings, cfg, copilot=model, investigator=inv, core_transport=bank.transport,
                          scoring_transport=scoring.transport, conversation_transport=conv.transport)
        client = stack.enter_context(TestClient(create_case_app(deps)))  # lifespan seeds the in-memory stores
        if baselines:
            for ref in ("cust-tanaka-0001", "cust-0005", "cust-0008", "cust-0010"):
                deps.store.repo.put_baseline(ref, compute_baseline(bank, ref).model_dump(mode="json"))
        return Env(client, deps, bank, conv, scoring, model, inv)

    yield make
    stack.close()


SCENARIOS = {
    "A": dict(customer_ref="cust-tanaka-0001", account_id="acct-tanaka-0001", payee_account="acct-mule-0001", amount=3_000_000),
    "B": dict(customer_ref="cust-0008", account_id="acct-0008", payee_account="acct-co-0002", amount=1_800_000),
    "C": dict(customer_ref="cust-0005", account_id="acct-0005", payee_account="acct-co-0001", amount=1_800_000),
    "D": dict(customer_ref="cust-0010", account_id="acct-0010", payee_account=None, amount=2_000_000, kind="cash_withdrawal"),
}


def replay(make_env, conv_id: str, upto: int | None = None, language: str = "ja", **env_kwargs):
    rec = REPLAYS[language][conv_id]
    env = make_env(copilot=FakeClient(json=list(rec["outputs"])), **env_kwargs)
    kwargs = dict(SCENARIOS[conv_id])
    if conv_id == "A":
        case_id = env.open_case(**kwargs)
    else:
        case_id = env.open_case(signals=[], **kwargs)
    if language != "ja":
        resp = env.client.patch(f"/cases/{case_id}/language", json={"language": language, "actor": "teller-sato"}, headers=STAFF)
        assert resp.status_code == 200, resp.text
    cards = [env.turn(case_id, text)["card"] for text in rec["customer_turns"][:upto]]
    return env, case_id, cards


