"""The counter copilot: one model call per customer turn, then code does the rest.

    model (schema-constrained to copilot-turn.json)   extracts indicators + quotes, judges the cover story,
                                                      names a hypothesis, picks a question ID
    code                                              quote rule -> accumulation -> risk-v1 -> bank wording

The model never produces a number, a pause flag or wording the teller reads out.
"""

from __future__ import annotations

import json
import logging
import re
from importlib import resources

from pydantic import ValidationError

from mimamori_common.llm import ModelOutputError, data_block
from mimamori_common.models import CopilotTurn
from mimamori_common.rules import merge_indicators, verify_quotes
from mimamori_common.schemas import load_schema

from . import card as cardlib
from .bank import BankView, load_bank, question_view, resolve_question
from .deps import Deps
from .errors import ApiProblem, conflict

log = logging.getLogger("case_svc.copilot")

PROMPT_NAME = "copilot_system_v3"
_PROMPTS = resources.files("case_svc").joinpath("prompts")
_BASE_PROMPT = _PROMPTS.joinpath(f"{PROMPT_NAME}.md").read_text(encoding="utf-8")
_LANGUAGE_NAME = {"ja": "Japanese", "en": "English"}
_EXAMPLES = {lang: _PROMPTS.joinpath(f"copilot_examples_{lang}.md").read_text(encoding="utf-8") for lang in _LANGUAGE_NAME}


def system_prompt(language: str = "ja") -> str:
    """One shared base (definitions, rules, output shape) plus the examples for the case language."""
    return _BASE_PROMPT.replace("{language}", _LANGUAGE_NAME[language]).rstrip() + "\n\n" + _EXAMPLES[language]


SYSTEM_PROMPT = system_prompt("ja")


def describe_request(case: dict) -> str:
    req = case["request"]
    payee = req.get("payee")
    kind = "cash withdrawal" if req["kind"] == "cash_withdrawal" else "transfer"
    to = f" to {payee['name_kana']} ({payee['relation'].replace('_', ' ')} account)" if payee else ""
    return f"{req['channel']} {kind} of ¥{req['amount_jpy']:,}{to}"


def transcript_text(case: dict) -> str:
    return "\n".join(f"{t['turn_id']} ({t['speaker']}): {t['text']}" for t in case["transcript"])


def build_user_message(case: dict, state: dict, view: BankView, shown: dict[str, dict]) -> str:
    """Untrusted text (payee name, transcript) and everything derived from public alerts sits in data blocks."""
    newest = [t for t in case["transcript"] if t["speaker"] == "customer"][-1]["turn_id"]
    return "\n\n".join([
        data_block("request", describe_request(case)),
        data_block("verified_facts", json.dumps(cardlib.fact_values(state), ensure_ascii=False, indent=1)),
        data_block("approved_playbooks", json.dumps(view.playbooks_for_model(), ensure_ascii=False, indent=1)),
        data_block("question_bank", json.dumps(view.for_model(shown), ensure_ascii=False, indent=1)),
        data_block("transcript", transcript_text(case)),
        f"The newest customer turn is {newest}. Reply with the JSON object.",
    ])


def _fit_rationale(data: dict, limit: int) -> dict:
    """Gemini doesn't enforce `maxLength` in constrained decoding. The rationale is an analyst note (not
    customer-facing, not bank wording), so cut it to fit: at a sentence end if there is one, else at a space."""
    text = data.get("rationale_en")
    if not isinstance(text, str) or len(text) <= limit:
        return data
    ends = [m.end() for m in re.finditer(r"(?:\.(?=\s|$)|。)", text) if m.end() <= limit]
    if ends:
        cut = text[:ends[-1]]
    else:
        space = text.rfind(" ", 0, limit - 1)
        cut = text[:space if space > 0 else limit - 1].rstrip() + "…"
    log.warning("copilot rationale_en trimmed from %d to %d chars", len(text), len(cut))
    return {**data, "rationale_en": cut}


async def call_model(deps: Deps, system: str, user: str) -> CopilotTurn:
    schema = load_schema("copilot-turn.json")
    last: Exception | None = None
    for attempt in (1, 2):  # constrained decoding makes a bad reply rare; retry once, then give up (teller falls back)
        try:
            result = await deps.copilot.generate_json(system, user, schema)
            limit = schema["properties"]["rationale_en"]["maxLength"]
            out = CopilotTurn.model_validate(_fit_rationale(result.data, limit))
            log.info("copilot turn ok prompt=%s model=%s seconds=%.1f", PROMPT_NAME, result.model, result.seconds)
            return out
        except (ModelOutputError, ValidationError) as err:
            last = err
            log.warning("copilot output invalid (attempt %d): %s", attempt, str(err)[:200])
        except Exception as err:  # model endpoint down, timeout
            raise ApiProblem(503, "model_unavailable", f"copilot model: {err!r}") from err
    raise ApiProblem(503, "model_output_invalid", str(last)[:200])


def append_turn(case: dict, speaker: str, text: str, now) -> dict:
    n = sum(1 for t in case["transcript"] if t["speaker"] == speaker) + 1
    turn = {"turn_id": f"{'c' if speaker == 'customer' else 't'}{n}", "speaker": speaker, "text": text, "at": now.isoformat()}
    case["transcript"].append(turn)
    return turn


def apply_output(deps: Deps, case: dict, state: dict, out: CopilotTurn, view: BankView, shown: dict[str, dict]) -> None:
    """Quote rule -> accumulation -> cover story -> inference -> question. Mutates `state`."""
    data = out.model_dump(mode="json")
    customer_turns = {t["turn_id"]: t["text"] for t in case["transcript"] if t["speaker"] == "customer"}
    kept, dropped = verify_quotes(data["indicators"], customer_turns)
    for d in dropped:
        cardlib.add_dropped(state, {"type": d["type"], "turn_id": d["turn_id"], "quote": d["quote"]}, "quote_not_found")
    cardlib.add_indicators(state, merge_indicators([], kept))

    cover = data["cover_story"]
    if cover["matches_playbook"] and not view.playbook(cover["matches_playbook"]):
        log.warning("copilot named playbook %r that is not approved/known; ignored", cover["matches_playbook"])
        cover["matches_playbook"] = None
    state["cover_story"] = cover
    state["leading_hypothesis"] = data["leading_hypothesis"]
    state["rationale_en"] = data["rationale_en"]

    # The model's rationale is shown as a hypothesis, grounded in the verified quotes and counterpart facts.
    refs = [f"quote:{k}" for k in state["quote_ids"]
            if any(i["id"] == v for i in state["indicators"] for v in [state["quote_ids"][k]])]
    refs += [f"fact:{k}" for k in cardlib.fact_values(state) if k.startswith(("counterpart_graph.", "get_baseline."))]
    cardlib.set_inferences(state, "copilot", [{"statement_en": data["rationale_en"], "refs": refs}]
                           if data["leading_hypothesis"] != "legitimate" and refs else [])

    payee = case["request"].get("payee")
    question, problem = resolve_question(view, shown, data["next_question_id"], data["leading_hypothesis"])
    if problem:
        cardlib.add_dropped(state, {"next_question_id": data["next_question_id"]}, "unknown_question_id")
        deps.store.audit(case["case_id"], "copilot.unknown_question_id", "copilot", f"model chose {data['next_question_id']!r}",
                         fell_back_to=question["id"] if question else None)
    if question:
        state["next_question"] = question_view(question, payee, deps.settings)
        state["suggested_question_ids"].append(question["id"])
    else:
        state["next_question"] = None  # every question has been used: the console shows no new question


async def customer_turn(deps: Deps, case_id: str, text: str) -> tuple[dict, dict | None]:
    """Process one customer turn. Returns (turn, card)."""
    store = deps.store
    async with store.turn_lock(case_id):
        async with store.lock(case_id):
            case, state = store.case(case_id), store.state(case_id)
            if case["status"] not in ("open", "paused"):
                raise conflict("case_not_open", f"case is {case['status']}")
            language = case.get("language", "ja")
            turn = append_turn(case, "customer", text, store.now())
            store.save_case(case)
            store.emit(case_id, "transcript_turn", turn)
            view = load_bank(deps.intel)  # approved playbooks and banks only
            shown = view.shown(state["suggested_question_ids"], has_payee=bool(case["request"].get("payee")))
            user = build_user_message(case, state, view, shown)
        out = await call_model(deps, system_prompt(language), user)  # no lock held: a decision can land meanwhile
        async with store.lock(case_id):
            case, state = store.case(case_id), store.state(case_id)
            apply_output(deps, case, state, out, view, shown)
            card = cardlib.build_card(case, state, view, store.now())
            case["risk_level"] = card["risk"]["level"]
            store.save_case(case)
            store.save_state(case_id, state)
            store.save_card(card)
            line = view.hold_lines.get(card["risk"].get("hold_line_id") or "")
            store.emit(case_id, "card_updated", {"card": card, "hold_line": line and {"id": line["id"], "ja": line["ja"], "en": line["en"]}})
            if card["risk"]["pause_recommended"]:
                log.info("case %s: pause recommended at %s (%s)", case_id, turn["turn_id"], [f["condition"] for f in card["risk"]["fired"]])
            return turn, card


async def teller_turn(deps: Deps, case_id: str, text: str) -> dict:
    store = deps.store
    async with store.lock(case_id):
        case = store.case(case_id)
        turn = append_turn(case, "teller", text, store.now())
        store.save_case(case)
        store.emit(case_id, "transcript_turn", turn)
        return turn
