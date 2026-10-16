"""Investigation (build step 2): read-only tools driven by an ADK agent, every fact checked in code against
its tool field, ungrounded inferences dropped. The result replaces the seeded card."""

from __future__ import annotations

import json
import logging
import time

from mimamori_common.llm import data_block

from .. import card as cardlib
from ..bank import load_bank, question_view, resolve_question
from ..copilot import describe_request
from ..deps import Deps
from ..errors import ApiProblem
from .adk_runner import run_agent
from .tools import TOOLS, ToolEnv
from .verify import verify_findings

log = logging.getLogger("case_svc.investigation")


async def build_env(deps: Deps, case: dict, state: dict) -> ToolEnv:
    req = case["request"]
    payee = req.get("payee")
    payee_account = state.get("payee_account_id")
    if payee and payee["relation"] == "same_bank" and not payee_account:
        try:
            transfer = await deps.core.get_transfer(case["transfer_id"])
            payee_account = transfer.request.payee.account_id if transfer.request.payee else None
        except ApiProblem as err:
            log.warning("could not read transfer %s: %s", case["transfer_id"], err.detail)
    return ToolEnv(deps=deps, case_id=case["case_id"], customer_ref=case["customer_ref"], account_id=case["account_id"],
                   kind=req["kind"], amount_jpy=req["amount_jpy"], payee_name=payee["name_kana"] if payee else None,
                   payee_relation=payee["relation"] if payee else None, payee_account_id=payee_account)


def case_context(case: dict, bank_questions: list[dict]) -> str:
    sig = [{"tool": s["tool"], "field": s["field"], "value": s["value"]} for s in case["signals"]]
    return "\n\n".join([
        data_block("case", describe_request(case)),
        data_block("alert_signals", json.dumps(sig, ensure_ascii=False)),
        data_block("question_bank", json.dumps(bank_questions, ensure_ascii=False, indent=1)),
        "Investigate with the tools, then finish.",
    ])


async def run_investigation(deps: Deps, case_id: str) -> None:
    """Never raises: a failed investigation leaves the seeded card, marked as such, and the teller carries on."""
    store = deps.store
    began = time.monotonic()
    try:
        async with store.lock(case_id):
            case, state = store.case(case_id), store.state(case_id)
        env = await build_env(deps, case, state)
        view = load_bank(deps.intel)
        shown = view.shown([], has_payee=bool(case["request"].get("payee")))
        notes: list[str] = []
        status = "done"
        try:
            run = await run_agent(deps.investigator, env, case_context(case, view.for_model(shown)), deps.svc.investigation_max_steps)
        except Exception as err:  # model down, ADK error: fall back to code-run checks of the alert signals
            log.warning("investigation agent failed for %s: %r", case_id, err)
            from .adk_runner import AgentRun
            run, status = AgentRun(), "failed"
            notes.append(f"agent failed: {err!r}"[:300])
        notes += run.notes

        # Code runs any tool that backs an alert signal but the model skipped, so every signal is checked, not trusted.
        for sig in case["signals"]:
            if sig["tool"] not in run.results:
                try:
                    run.results[sig["tool"]] = await TOOLS[sig["tool"]](env)
                except ApiProblem as err:
                    notes.append(f"{sig['tool']} unavailable: {err.detail}")
        final = run.final or {}
        candidates = [{"tool": s["tool"], "field": s["field"], "value": s["value"], "statement_en": s["statement_en"]} for s in case["signals"]]
        candidates += final.get("facts", [])
        verified = verify_findings(candidates, final.get("inferences", []), run.results)

        log.info("investigation done case=%s status=%s model_calls=%d tools=%d (%s) seconds=%.1f", case_id, status,
                 run.llm_calls, len(run.tools_called), ",".join(run.tools_called), time.monotonic() - began)

        async with store.lock(case_id):
            case, state = store.case(case_id), store.state(case_id)
            if payee_id := env.payee_account_id:
                state["payee_account_id"] = payee_id
            cardlib.set_facts(state, verified.facts)
            cardlib.set_inferences(state, "investigation", verified.inferences)
            for d in verified.dropped:
                cardlib.add_dropped(state, d["claim"], d["reason"])
            no_turns_yet = not any(t["speaker"] == "customer" for t in case["transcript"])
            if no_turns_yet:  # a copilot turn that already landed knows more than the pre-conversation investigation
                if final.get("leading_hypothesis"):
                    state["leading_hypothesis"] = final["leading_hypothesis"]
                if final.get("first_question_id"):
                    shown_now = view.shown([], has_payee=bool(case["request"].get("payee")))
                    q, problem = resolve_question(view, shown_now, final["first_question_id"], state["leading_hypothesis"])
                    if problem:
                        cardlib.add_dropped(state, {"first_question_id": final["first_question_id"]}, "unknown_question_id")
                    if q:  # only the seeded first question had been shown so far; replace it
                        payee = case["request"].get("payee")
                        state["next_question"] = question_view(q, payee, deps.settings)
                        state["suggested_question_ids"] = [q["id"]]
            state["investigation"] = {"status": status, "tools_called": run.tools_called, "llm_calls": run.llm_calls,
                                      "model": getattr(deps.investigator, "name", "?"), "notes": notes}
            card = cardlib.build_card(case, state, view, store.now())
            case["risk_level"] = card["risk"]["level"]
            store.save_case(case)
            store.save_state(case_id, state)
            store.save_card(card)
            store.audit(case_id, "investigation.completed", "investigation-agent", f"status={status}",
                        tools_called=run.tools_called, facts_verified=len(verified.facts),
                        dropped=[d["reason"] for d in verified.dropped])
            store.emit(case_id, "card_updated", {"card": card, "source": "investigation", "status": status})
    except Exception:  # pragma: no cover - last resort: investigation must never take the case down
        log.exception("investigation crashed for %s", case_id)
