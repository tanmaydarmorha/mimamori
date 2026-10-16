"""Arm (a): today's counter check, built from published practice (docs/research.md R1), not invented.

Sources (R1 table numbers):
  [1] NPA request: speak to customers making high-value transfers / taking high-value cash, contact the
      nearest police station.
  [2] Akita prefectural police five-step routine: show the police request, questionnaire, suggest
      transfer instead of cash, suggest a bank cheque, report to police.
  [3][4] Hiroshima / Hyogo: do not ask "are you being scammed?"; ask in detail what the money is for.
  [6] NPA: at a staffed counter the withdrawal goes ahead once a basic "not scam-related" confirmation
      is given, but scammers coach victims on what to say. This is the arm's known weakness, in the NPA's
      own words, and the sim keeps it (coached personas pass).
  [8] Okayama practice: ask for purchase documents; phone the named relative; report if unexplained.

Parameters that are NOT sourced and are stated instead (never hidden):
  * amount threshold (`SimParams.amount_threshold_jpy`; no national figure is published; the report
    sweeps it);
  * the age trigger of R1's draft is not modelled: every sim customer is treated as in scope;
  * the teller's questions are the four approved general-bank questions that match R1's step 2 wording
    (purpose, who asked, in a call now, documents), asked in that order;
  * red flags are recognised by the lexicon below, derived from R1 [2][6][7][8] and from the NPA's
    published script phrases. A person reads more flexibly than a lexicon; that is a limit of this arm
    and is listed in the report.

Escalation = pause and call the police (R1 draft step 6). The teller assumption (teller.py) decides
whether the teller acts on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .params import SimParams
from .personas import QuestionIndex, RolePlayer
from .scenarios import Scenario
from .teller import ArmOutcome, decide

ARM = "a_counter_check"

# The routine's questions, in order (ids from the approved general bank; wording is team wording that
# follows R1's draft baseline step 2-3).
ROUTINE = ["q.general.purpose", "q.general.who_asked", "q.general.on_phone", "q.general.documents"]

# flag code -> (regex over the customer's reply, question purpose it applies to or None for any, source)
_NOT_TOLD = r"(誰にも|だれにも|人には|家族にも|家族には|嫁には|娘には|息子には|妻には|夫には)[^。]{0,8}(言うな|言わないで|言ってはいけ|言っちゃいけ|話すな|話してはいけ)"
LEXICON: dict[str, tuple[str, str | None, str]] = {
    # someone official told the customer to do this
    "official_instruction": (r"警察|警視庁|検察|検事|裁判所|金融庁|捜査|逮捕|刑事|出入国", None, "R1 [2][7]: customer says police/officials involved"),
    # told not to tell anyone (not merely "it was a secret")
    "secrecy_instruction": (_NOT_TOLD + r"|言うなと|内緒にしてと言われ", None, "R1 [2][7]; NPA script phrase 捜査の秘密"),
    # NPA-published script phrases of the fake-police method
    "script_phrase": (r"安全な口座|犯罪に使われ|資産を保全|後で戻|終わったら戻|口座が凍結|無実", None, "R1 [6]: NPA 手口 PDF script phrases"),
    # a caller is on the line or about to call back
    "live_instruction": (r"つながった|連絡を待|待っているんです|電話中|通話中|またかかって", "check_contact", "R1 draft step 2: on the phone now"),
    # cannot say what it is for
    "cannot_explain_purpose": (r"言えません|言えない|わかりません|分かりません|詳しくは言え", None, "R1 [8a] Tomato Bank: could only say 'son asked'"),
    # no documents for the stated purpose (R1 [8d])
    "no_documents": (r"書類(は|が)?(特に)?(ありません|ない)|後で送|あとで送|持っていません|持ってない|書類なんて", "verify_purpose", "R1 [8d]: asked for purchase papers, could not produce"),
    # R1 [8c]: purpose is a request from a relative the teller should phone (not decided here): no flag
}
_COMPILED = {code: (re.compile(rx), purpose, src) for code, (rx, purpose, src) in LEXICON.items()}


def red_flags(reply: str, purpose: str | None) -> list[str]:
    """Which published red flags a trained teller would hear in this reply."""
    out = []
    for code, (rx, only_purpose, _src) in _COMPILED.items():
        if only_purpose and only_purpose != purpose:
            continue
        if rx.search(reply):
            out.append(code)
    return out


def triggered(scenario: Scenario, params: SimParams) -> bool:
    """R1 [1]: high-value transfer or cash. Amount at or above the stated threshold."""
    return scenario.amount_jpy >= params.amount_threshold_jpy


@dataclass
class ArmA:
    index: QuestionIndex
    params: SimParams

    async def run(self, scenario: Scenario, role: RolePlayer) -> ArmOutcome:
        acts = self.params.teller_acts(scenario.id)
        out = ArmOutcome(ARM, scenario.id, paused=False, paused_at_turn=None, flag_ever=False, flag_first_turn=None)
        if not triggered(scenario, self.params):
            out.engaged = False
            out.notes.append(f"below the amount threshold (¥{self.params.amount_threshold_jpy:,}): no check")
            return out
        history: list[dict] = []
        asked: dict[str, int] = {}
        for turn, qid in enumerate(ROUTINE[: self.params.max_turns], start=1):
            q = self.index.get(qid)
            if q is None:
                raise KeyError(f"routine question {qid} missing from the approved bank")
            out.questions.append({"id": q.id, "ja": q.ja, "purpose": q.purpose})
            history.append({"turn_id": f"t{turn}", "speaker": "teller", "text": q.ja})
            reply = await role.reply(scenario.persona, q.purpose, q.ja, history, asked.get(q.purpose, 0))
            asked[q.purpose] = asked.get(q.purpose, 0) + 1
            history.append({"turn_id": f"c{turn}", "speaker": "customer", "text": reply})
            flags = red_flags(reply, q.purpose)
            if flags:
                out.reasons += [f"{f} (turn c{turn})" for f in flags]
                if not out.flag_ever:
                    out.flag_ever, out.flag_first_turn = True, turn
                if decide(True, acts):
                    out.paused, out.paused_at_turn = True, turn
                    break
        out.transcript = history
        if out.flag_ever and not out.paused:
            out.notes.append("flag raised; the teller did not act on it (shared teller assumption)")
        return out
