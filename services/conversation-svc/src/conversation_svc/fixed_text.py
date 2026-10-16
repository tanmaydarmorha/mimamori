"""Wording that is fixed in code (not model output, not in schemas/examples/call-templates.json yet).

The opening line and the notice are constants here because `call-templates.json` has no slot for
them (its `intent` enum is the per-turn classification only). The orchestrator is asked to add an
`opening` / `notice` template kind to `schemas/`; until then these are the source of truth.

CR 4: the notice reveals nothing but the branch, "about your mother", the published number and the
case code. CR 24: the callback lets the family verify the bank; it is not proof of identity.
CR 26: the first callback line says the assistant is automated and the call is recorded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# CR 26. Said first on every verified callback, before anything else.
OPENING_JA = "自動音声のアシスタントです。この通話は録音されます。ご用件をお話しください。"

# Notice (CR 4, CR 24). Slots: branch, customer_reference, published_phone, case_code.
# It asks the family to check the bank by calling the published number; it claims no identity proof.
NOTICE_TEMPLATE_JA = (
    "{branch}です。{customer_reference}の件でご連絡しました。"
    "この連絡が当店からのものかどうか、当店の公開番号 {published_phone} へお電話のうえ、"
    "音声案内で「ご連絡への折り返し」を選び、確認番号 {case_code} をお伝えください。"
)

# Used only if a template, once filled, fails the rule check (should never happen; tests assert it).
SAFE_FALLBACK_JA = "申し訳ございません、その点については担当者から改めてご説明いたします。"

# Words for brief.disclosable.reason_category. Fixed here; no amounts, no names, no numbers.
REASON_CATEGORY_JA = {
    "call_from_someone_claiming_authority": "公的機関を名乗る方からの電話があったとのことで、念のため確認をしております。",
    "unfamiliar_payee": "お振込先に初めてのお相手が含まれているため、念のため確認をしております。",
    "unusual_amount": "普段とは異なるお手続きのため、念のため確認をしております。",
}


# ---- English pack (same slots, same facts) -------------------------------------------------------
OPENING_EN = "This is an automated voice assistant. This call is recorded. Please tell me what you are calling about."

NOTICE_TEMPLATE_EN = (
    "This is {branch}. We are contacting you about {customer_reference}. "
    "To check that this message is from us, please call our published number {published_phone}, "
    "choose \"Return a call about a message\" from the voice menu, and give the confirmation number {case_code}."
)

SAFE_FALLBACK_EN = "I'm sorry, our staff will follow up with you on that point."

REASON_CATEGORY_EN = {
    "call_from_someone_claiming_authority": "We are checking as a precaution, because we were told of a call from someone claiming to be an official.",
    "unfamiliar_payee": "We are checking as a precaution, because the payee is new to the account.",
    "unusual_amount": "We are checking as a precaution, because the transaction is unlike the usual ones.",
}

# English twin of brief.customer_reference for the gloss shown beside a Japanese call. Display only;
# an English call receives its reference from the brief.
REFERENCE_EN_FOR_JA = {"お母様": "your mother", "お父様": "your father", "ご家族の方": "your family member"}
NEUTRAL_REFERENCE_EN = "your family member"

_SLOT_RE = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True)
class FixedText:
    """The fixed wording for one language."""

    language: str
    opening: str
    notice_template: str
    safe_fallback: str
    reason_category: dict[str, str]


_PACKS = {
    "ja": FixedText("ja", OPENING_JA, NOTICE_TEMPLATE_JA, SAFE_FALLBACK_JA, REASON_CATEGORY_JA),
    "en": FixedText("en", OPENING_EN, NOTICE_TEMPLATE_EN, SAFE_FALLBACK_EN, REASON_CATEGORY_EN),
}


def text_for(language: str) -> FixedText:
    return _PACKS[language]


# The two notice templates must use the same slots (checked at import, and again in tests).
assert set(_SLOT_RE.findall(NOTICE_TEMPLATE_JA)) == set(_SLOT_RE.findall(NOTICE_TEMPLATE_EN))
assert set(REASON_CATEGORY_JA) == set(REASON_CATEGORY_EN)


def format_phone_national(e164: str) -> str:
    """+81312345678 -> 03-1234-5678, +819012345678 -> 090-1234-5678 (Japanese numbers), else digits."""
    digits = e164.lstrip("+")
    if digits.startswith("81"):
        n = "0" + digits[2:]
        if n[1] in "789" and len(n) == 11:
            return f"{n[:3]}-{n[3:7]}-{n[7:]}"
        if n[1] in "36" and len(n) == 10:
            return f"{n[:2]}-{n[2:6]}-{n[6:]}"
        return n
    return digits
