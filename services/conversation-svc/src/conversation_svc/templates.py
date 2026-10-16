"""Approved reply templates (schemas/examples/call-templates.json), filled by code from the brief.

Facts can only come from here (CR 5). A template whose required fields are not all disclosable
(present in the brief, allowed by the call policy, and true for booleans) gives its fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from mimamori_common.models import CallRequest, CallTemplate
from mimamori_common.schemas import load_example

from .fixed_text import NEUTRAL_REFERENCE_EN, REASON_CATEGORY_EN, REASON_CATEGORY_JA, REFERENCE_EN_FOR_JA

SLOTS = {"customer_reference", "reason_category_ja", "reason_category_en"}
_SLOT_RE = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True)
class Filled:
    intent: str
    text: str
    disclosed: tuple[str, ...]  # brief fields actually spoken
    used_fallback: bool
    gloss_en: str | None = None  # English twin, only for a Japanese call


def disclosable_fields(call: CallRequest) -> dict[str, object]:
    """Brief fields that may be spoken now: in the brief AND in the policy's `may_disclose`."""
    brief = call.brief.disclosable.model_dump(mode="json", exclude_none=True)
    return {k: v for k, v in brief.items() if k in call.policy.may_disclose}


def _available(field: str, value: object) -> bool:
    if isinstance(value, bool):
        return value  # "customer_at_branch: false" is not something a template can say
    return True


def _fill(text: str, slots: dict[str, str]) -> str:
    return _SLOT_RE.sub(lambda m: slots[m.group(1)], text)


class TemplateBook:
    def __init__(self, templates: list[CallTemplate]) -> None:
        self.by_intent = {t.intent.value: t for t in templates}
        for t in templates:
            for text in (t.ja, t.en, t.fallback_ja, t.fallback_en):
                unknown = set(_SLOT_RE.findall(text)) - SLOTS
                if unknown:
                    raise ValueError(f"template {t.intent.value} has unknown slots {sorted(unknown)}")
            ja_slots = {x.replace("_ja", "") for x in _SLOT_RE.findall(t.ja)}
            en_slots = {x.replace("_en", "") for x in _SLOT_RE.findall(t.en)}
            fb_ja = {x.replace("_ja", "") for x in _SLOT_RE.findall(t.fallback_ja)}
            fb_en = {x.replace("_en", "") for x in _SLOT_RE.findall(t.fallback_en)}
            if ja_slots != en_slots or fb_ja != fb_en:
                raise ValueError(f"template {t.intent.value}: ja and en use different slots")
        if "other" not in self.by_intent:
            raise ValueError("call-templates.json must contain an 'other' template")

    @classmethod
    def load(cls) -> "TemplateBook":
        return cls([CallTemplate.model_validate(t) for t in load_example("call-templates.json")])

    def fill(self, intent: str, call: CallRequest) -> Filled:
        template = self.by_intent.get(intent) or self.by_intent["other"]
        fields = disclosable_fields(call)
        requires = [r.value for r in template.requires]
        ok = all(r in fields and _available(r, fields[r]) for r in requires)
        # "大きな金額のお手続きです" would be untrue for the lowest band: use the fallback.
        if "amount_band" in requires and fields.get("amount_band") == "under_1m":
            ok = False
        slots_ja = {
            "customer_reference": call.brief.customer_reference,
            "reason_category_ja": REASON_CATEGORY_JA.get(str(fields.get("reason_category")), ""),
        }
        category = str(fields.get("reason_category"))
        gloss = None
        if call.brief.language.value == "en":
            text = _fill(template.en if ok else template.fallback_en,
                         {"customer_reference": call.brief.customer_reference, "reason_category_en": REASON_CATEGORY_EN.get(category, "")})
        else:
            text = _fill(template.ja if ok else template.fallback_ja, slots_ja)
            ref_en = REFERENCE_EN_FOR_JA.get(call.brief.customer_reference, NEUTRAL_REFERENCE_EN)
            gloss = _fill(template.en if ok else template.fallback_en,
                          {"customer_reference": ref_en, "reason_category_en": REASON_CATEGORY_EN.get(category, "")})
        return Filled(template.intent.value, text, tuple(requires) if ok else (), not ok, gloss)

    def all_bodies(self, call: CallRequest) -> set[str]:
        """Every body this call may legitimately speak (used by the rule check)."""
        return {self.fill(intent, call).text for intent in self.by_intent}
