"""Approved counter wording. Only `approved` playbooks and banks are ever read here, so nothing
pending or rejected can reach the copilot (decisions.md, containers rule 3)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from mimamori_common.store import IntelRepo

log = logging.getLogger("case_svc.bank")

FALLBACK_QUESTION_ID = "q.general.purpose"
FALLBACK_HOLD_LINE_ID = "h.general.protect"
PLAYBOOK_KEYS = ["id", "hypothesis", "name", "impersonates", "script_phrases", "victim_instructions",
                 "cover_stories", "payment_methods"]


@dataclass
class BankView:
    playbooks: list[dict] = field(default_factory=list)  # approved only
    questions: dict[str, dict] = field(default_factory=dict)
    hold_lines: dict[str, dict] = field(default_factory=dict)

    def playbook(self, playbook_id: str | None) -> dict | None:
        return next((p for p in self.playbooks if p["id"] == playbook_id), None)

    def playbook_for(self, hypothesis: str) -> dict | None:
        return next((p for p in self.playbooks if p.get("hypothesis") == hypothesis), None)

    def playbooks_for_model(self) -> list[dict]:
        return [{k: pb[k] for k in PLAYBOOK_KEYS if k in pb} for pb in self.playbooks]

    def shown(self, suggested: list[str], has_payee: bool) -> dict[str, dict]:
        """The bank the model sees: leaves out questions already suggested in this case (spike run 3: the
        model repeated one four times) and questions whose slots can't be filled."""
        used = set(suggested)
        return {qid: q for qid, q in self.questions.items()
                if qid not in used and (has_payee or "payee_name" not in q.get("slots", []))}

    @staticmethod
    def for_model(shown: dict[str, dict]) -> list[dict]:
        return [{"id": q["id"], "ja": q["ja"], "purpose": q["purpose"], "separates": q["separates"]} for q in shown.values()]

    def choose_hold_line(self, hypothesis: str, playbook_id: str | None) -> dict | None:
        """Chosen by code: the matched playbook's line for the hypothesis, else any line for it, else the general line."""
        pb = self.playbook(playbook_id) or self.playbook_for(hypothesis)
        for line in (pb or {}).get("question_bank", {}).get("hold_lines", []):
            if hypothesis in line["for_hypotheses"]:
                return line
        for line in self.hold_lines.values():
            if hypothesis in line["for_hypotheses"]:
                return line
        return self.hold_lines.get(FALLBACK_HOLD_LINE_ID)


def load_bank(intel: IntelRepo) -> BankView:
    view = BankView(playbooks=intel.list_playbooks("approved"))
    for bank in intel.list_question_banks("approved"):
        for q in bank["questions"]:
            view.questions[q["id"]] = q
        for h in bank["hold_lines"]:
            view.hold_lines[h["id"]] = h
    for pb in view.playbooks:
        for q in pb["question_bank"]["questions"]:
            view.questions[q["id"]] = q
        for h in pb["question_bank"]["hold_lines"]:
            view.hold_lines[h["id"]] = h
    return view


def fill(question: dict, *, payee_name: str | None, branch_name: str) -> str:
    """Slots are filled by code from verified case data, never by the model."""
    return question["ja"].replace("{payee_name}", payee_name or "").replace("{branch_name}", branch_name)


def fill_en(question: dict, *, payee_name: str | None, branch_name: str) -> str:
    return question["en"].replace("{payee_name}", payee_name or "").replace("{branch_name}", branch_name)


def question_view(question: dict, payee: dict | None, settings) -> dict:
    """`card.next_question`: the approved wording in both languages, slots filled by code. The console shows
    the case language first."""
    name = payee["name_kana"] if payee else None
    return {"question_id": question["id"],
            "ja_filled": fill(question, payee_name=name, branch_name=settings.branch_name_ja),
            "en_filled": fill_en(question, payee_name=name, branch_name=settings.branch_name_en)}


def resolve_question(view: BankView, shown: dict[str, dict], model_id: str, hypothesis: str) -> tuple[dict | None, str | None]:
    """Returns (question, problem). An ID not in the bank shown (unknown, or already suggested) falls back to
    q.general.purpose and the miss is logged (`problem` = "unknown_question_id"). If even the fallback is used up,
    the first remaining question that helps with the leading hypothesis; with none left, no question."""
    if model_id in shown:
        return shown[model_id], None
    log.warning("unknown_question_id: model chose %r, not in the bank shown; falling back to %s", model_id, FALLBACK_QUESTION_ID)
    if FALLBACK_QUESTION_ID in shown:
        return shown[FALLBACK_QUESTION_ID], "unknown_question_id"
    for q in shown.values():
        if hypothesis in q["separates"]:
            return q, "unknown_question_id"
    return next(iter(shown.values()), None), "unknown_question_id"
