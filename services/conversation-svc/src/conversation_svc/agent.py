"""One callback turn: classify (model) -> pick and fill template (code) -> connecting phrase (model,
checked) -> rule check (code) -> text for TTS. Nothing the model writes is spoken unless it passed."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from mimamori_common.models import CallRequest

from .classifier import Classified, Classifier
from .fixed_text import text_for
from .outgoing_check import check_outgoing
from .templates import TemplateBook

log = logging.getLogger("conversation_svc.agent")


@dataclass
class TurnReply:
    text: str
    intent: str
    disclosed: tuple[str, ...]
    signals: dict
    used_fallback: bool
    phrase_used: bool
    gloss_en: str | None = None
    classified: Classified = field(repr=False, default_factory=Classified)


class TurnAgent:
    def __init__(self, classifier: Classifier, templates: TemplateBook, max_utterance_chars: int = 500) -> None:
        self.classifier, self.templates, self.max_chars = classifier, templates, max_utterance_chars

    async def respond(self, call: CallRequest, utterance: str) -> TurnReply:
        language = call.brief.language.value
        sep = " " if language == "en" else ""
        classified = await self.classifier.classify(utterance[: self.max_chars], language)
        filled = self.templates.fill(classified.intent, call)
        bodies = self.templates.all_bodies(call)

        phrase = classified.connecting_phrase
        if phrase and language == "ja" and phrase[-1] not in "。！？、":
            phrase += "。"  # the lead-in and the template body are separate sentences
        text = (phrase + sep if phrase else "") + filled.text
        verdict = check_outgoing(text, bodies, phrase, language=language)
        if not verdict.ok and phrase:  # drop the connecting phrase silently, keep the template
            log.info("connecting phrase dropped by rule check: %s", verdict.reasons)
            phrase, text = None, filled.text
            verdict = check_outgoing(text, bodies, language=language)
        if not verdict.ok:  # should be unreachable: templates are tested clean
            log.error("template failed the rule check (%s): intent=%s", verdict.reasons, filled.intent)
            return TurnReply(text_for(language).safe_fallback, "other", (), classified.signals, True, False, None, classified)
        gloss = filled.gloss_en
        if gloss is not None and phrase:
            gloss += " (+ a short lead-in, not translated)"
        return TurnReply(text, filled.intent, filled.disclosed, classified.signals, filled.used_fallback,
                         phrase is not None, gloss, classified)
