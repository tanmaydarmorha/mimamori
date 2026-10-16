"""Arms (b) statistics only and (c) full Mimamori, from ONE `POST /transfers` per scenario.

The teller keys the transfer into core-bank-mock, which asks Scoring. That single call gives:

  arm (b): Scoring alone. The flag is `scoring == "alert"`. No case-svc involvement. Raised before any
           question (turn 0).
  arm (c): on an alert Scoring has opened a case. The teller runs the copilot conversation through
           case-svc (`/turns`, approved questions only, `/decision`) and the flag is the card's
           `risk.pause_recommended` (computed in code, risk-v1). With no alert there is no case: Mimamori
           is as silent as statistics alone.

Same teller assumption as arm (a) (teller.py). Statistics-only has no questions to ask, so its teller
acts on the alert at once or not at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from mimamori_common.models import DecisionRequest

from .clients import CaseSvcClient, CoreBankClient, ServiceError
from .params import MANAGER_ID, TELLER_ID, SimParams
from .personas import QuestionIndex, RolePlayer
from .scenarios import Scenario
from .teller import ArmOutcome, decide

ARM_B = "b_statistics"
ARM_C = "c_mimamori"
OPENING_QUESTION = "q.general.purpose"  # the shared opening question of every arm


def _fired(card) -> list[str]:
    try:
        return [f.condition for f in card.risk.fired]
    except AttributeError:
        return []


@dataclass
class ServiceArms:
    core: CoreBankClient
    case: CaseSvcClient
    index: QuestionIndex
    params: SimParams

    async def run(self, scenario: Scenario, role: RolePlayer) -> tuple[ArmOutcome, ArmOutcome]:
        acts = self.params.teller_acts(scenario.id)
        b = ArmOutcome(ARM_B, scenario.id, paused=False, paused_at_turn=None, flag_ever=False, flag_first_turn=None)
        c = ArmOutcome(ARM_C, scenario.id, paused=False, paused_at_turn=None, flag_ever=False, flag_first_turn=None)
        try:
            resp = await self.core.post_transfer(scenario.transfer_body(TELLER_ID))
        except ServiceError as err:
            b.error = c.error = str(err)
            b.engaged = c.engaged = False
            return b, c
        b.scoring = c.scoring = resp.scoring
        c.case_id = b.case_id = resp.case_id

        # ---- arm (b)
        if resp.scoring == "alert":
            b.flag_ever, b.flag_first_turn = True, 0
            b.reasons.append("scoring alert")
            if decide(True, acts):
                b.paused, b.paused_at_turn = True, 0
            else:
                b.notes.append("alert raised; the teller did not act on it (shared teller assumption)")
        else:
            b.engaged = False
            b.notes.append(f"scoring: {resp.scoring}")

        # ---- arm (c)
        if not resp.case_id:
            c.engaged = False
            c.notes.append(f"no case opened (scoring: {resp.scoring})")
            return b, c
        try:
            await self._conversation(scenario, resp.case_id, c, b, role, acts)
        except ServiceError as err:
            c.error = str(err)
        return b, c

    async def _conversation(self, scenario: Scenario, case_id: str, c: ArmOutcome, b: ArmOutcome,
                            role: RolePlayer, acts: bool) -> None:
        case = await self.case.get_case(case_id)
        c.signals = [f"{s.code}={s.value}" for s in case.signals]
        b.signals = list(c.signals)
        next_id: str | None = OPENING_QUESTION
        next_ja: str | None = None
        asked: dict[str, int] = {}
        history: list[dict] = []
        turn = 0
        while next_id and turn < self.params.max_turns:
            q = self.index.get(next_id)
            if q is None:
                c.notes.append(f"copilot suggested {next_id}, not in the approved bank index; teller stops asking")
                break
            turn += 1
            text = next_ja or q.ja  # the filled wording case-svc gave us (slots done in code)
            c.questions.append({"id": q.id, "ja": text, "purpose": q.purpose})
            await self.case.post_turn(case_id, "teller", text)
            history.append({"turn_id": f"t{turn}", "speaker": "teller", "text": text})
            reply = await role.reply(scenario.persona, q.purpose, text, history, asked.get(q.purpose, 0))
            asked[q.purpose] = asked.get(q.purpose, 0) + 1
            tr = await self.case.post_turn(case_id, "customer", reply)
            history.append({"turn_id": tr.turn_id, "speaker": "customer", "text": reply})
            card = tr.card
            if card is None:
                c.notes.append("case-svc returned no card for a customer turn")
                break
            c.risk_level = getattr(card.risk.level, "value", str(card.risk.level))
            flag = bool(card.risk.pause_recommended)
            if flag:
                c.reasons = _fired(card)
                if not c.flag_ever:
                    c.flag_ever, c.flag_first_turn = True, turn
                if decide(True, acts):
                    c.paused, c.paused_at_turn = True, turn
                    break
            nq = card.next_question
            # The teller reads the approved next question; the copilot never repeats one (case-svc rule).
            next_id, next_ja = (nq.question_id, nq.ja_filled) if nq else (None, None)
        c.transcript = history
        await self._decide(scenario, case_id, c)

    async def _decide(self, scenario: Scenario, case_id: str, c: ArmOutcome) -> None:
        if c.paused:
            rationale = f"sim teller pauses on the copilot's recommendation (fired: {', '.join(c.reasons) or 'n/a'})"
            req = DecisionRequest(action="pause", basis=scenario.basis, rationale=rationale, teller_id=TELLER_ID)
            res = await self.case.post_decision(case_id, req)
            c.warnings = list(res.warnings)
            case = await self.case.get_case(case_id)
            if case.hold_line:
                c.hold_line_ja = case.hold_line.ja
        else:
            why = ("copilot flag not acted on by the teller" if c.flag_ever
                   else "no pause recommended after the questions")
            req = DecisionRequest(action="release", release_reason="cleared_by_teller",
                                  rationale=f"sim teller clears: {why}", teller_id=TELLER_ID)
            res = await self.case.post_decision(case_id, req)
            c.warnings = list(res.warnings)
            if c.flag_ever:
                c.notes.append("flag raised; the teller did not act on it (shared teller assumption)")


__all__ = ["ServiceArms", "ARM_B", "ARM_C", "MANAGER_ID"]
