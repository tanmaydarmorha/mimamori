"""The rule check on everything the contact hears (CR 5, DA 13). Code, not a second model.

Rejects amounts in any form (digits in any width, kanji numerals, 万/億/円, kana amounts such as
さんびゃくまんえん), account numbers (any digit), and anything that is not an approved template
filled from the brief (optionally led by a checked connecting phrase). The checks are deliberately
over-inclusive: a false positive costs a fallback sentence, a false negative is a leak.

Language-aware (WI-005): a `ja` call is checked as above. An `en` call rejects any digit, number
word, currency word or symbol and "account number", and a connecting phrase must be plain ASCII
letters and `,.!?'` (at most 60 characters) free of the words in `_PHRASE_DENY_EN`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MAX_PHRASE_CHARS = 30
MAX_PHRASE_CHARS_EN = 60

# Characters that make a money amount or a count when they appear in text.
_UNIT_CHARS = "十百千万萬億兆円圓拾壱弐参"
_KANJI_DIGIT_RUN = re.compile(r"[〇零一二三四五六七八九]{2,}")
_KANA_DIGIT = r"(?:いち|に|さん|よん|よ|し|ご|ろく|しち|なな|はち|きゅう|く)"
_KANA_UNIT = r"(?:ひゃく|びゃく|ぴゃく|せん|ぜん|まん|おく|ちょう|じゅう|じっ)"
_KANA_AMOUNT = re.compile(rf"(?:{_KANA_DIGIT}{_KANA_UNIT}|{_KANA_UNIT}{_KANA_UNIT}|(?:{_KANA_DIGIT}|{_KANA_UNIT})えん)")
_LATIN = re.compile(r"[A-Za-z]")

# Connecting phrase: Japanese letters, long vowel mark, and 、。！？ only.
_PHRASE_CHARS = re.compile(r"^[ぁ-ゖァ-ヺー一-鿿、。！？]+$")
# Words a lead-in must not carry: facts, claims, assurances, instructions. Drop the phrase if present.
_PHRASE_DENY = (
    "口座", "残高", "番号", "金額", "いくら", "お金", "支払", "振込", "振り込", "送金", "暗証", "パスワード",
    "警察", "詐欺", "犯罪", "逮捕", "凍結", "停止", "保留", "支店", "店舗",
    "安全", "安心", "無事", "大丈夫", "保証", "ご案内", "お願い", "ください", "教えて", "伝えて",
)


# ---- English ------------------------------------------------------------------------------------
_NUMBER_WORDS = (
    "zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|thirty|forty|fifty|sixty|seventy|"
    "eighty|ninety|hundred|thousand|million|billion|lakh|crore"
)
_EN_AMOUNT = re.compile(rf"\b(?:{_NUMBER_WORDS})\b|\b(?:yen|rupees?|dollars?|euros?)\b|[¥$₹€]|\baccount\s+number", re.I)
_PHRASE_CHARS_EN = re.compile(r"^[A-Za-z ,.!?']+$")
# Stems, matched at a word start (so "payment" and "holding" are caught); PIN only as a whole word.
_PHRASE_DENY_EN = re.compile(
    r"\b(?:account|balance|number|amount|how much|money|pay|transfer|password|police|fraud|scam|crime|arrest|freeze|hold|"
    r"branch|safe|fine|guarantee|please|tell|must)|\bpin\b", re.I)


def amount_problems_en(text: str, allowed_literals: tuple[str, ...] = ()) -> list[str]:
    cleaned = text
    for literal in sorted(allowed_literals, key=len, reverse=True):
        cleaned = cleaned.replace(literal, "")
    norm = unicodedata.normalize("NFKC", cleaned)
    reasons: list[str] = []
    if any(unicodedata.category(c) in ("Nd", "No", "Nl") for c in norm):
        reasons.append("digit")
    if _EN_AMOUNT.search(norm):
        reasons.append("amount_word")
    return reasons


def phrase_problems_en(phrase: str) -> list[str]:
    reasons = amount_problems_en(phrase)
    if not phrase.strip():
        reasons.append("empty")
    if len(phrase) > MAX_PHRASE_CHARS_EN:
        reasons.append("too_long")
    if not _PHRASE_CHARS_EN.match(phrase):
        reasons.append("characters")
    if _PHRASE_DENY_EN.search(phrase):
        reasons.append("denied_word")
    return sorted(set(reasons))


def _kata_to_hira(text: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def amount_problems(text: str, allowed_literals: tuple[str, ...] = ()) -> list[str]:
    """Reasons `text` contains a number, amount or account-number-like token. `allowed_literals` are
    exact strings (e.g. the published phone number and the case code in the notice) removed first."""
    cleaned = text
    for literal in sorted(allowed_literals, key=len, reverse=True):
        cleaned = cleaned.replace(literal, "")
    norm = unicodedata.normalize("NFKC", cleaned)
    reasons: list[str] = []
    if any(unicodedata.category(c) in ("Nd", "No", "Nl") for c in norm):
        reasons.append("digit")
    if any(c in _UNIT_CHARS for c in norm):
        reasons.append("amount_unit")
    if _KANJI_DIGIT_RUN.search(norm):
        reasons.append("kanji_numeral")
    if _KANA_AMOUNT.search(_kata_to_hira(norm)):
        reasons.append("kana_amount")
    return reasons


def phrase_problems(phrase: str) -> list[str]:
    """Reasons a model-written connecting phrase must be dropped (empty list = usable)."""
    reasons = amount_problems(phrase)
    if not phrase.strip():
        reasons.append("empty")
    if len(phrase) > MAX_PHRASE_CHARS:
        reasons.append("too_long")
    if not _PHRASE_CHARS.match(phrase):
        reasons.append("characters")
    if _LATIN.search(unicodedata.normalize("NFKC", phrase)):
        reasons.append("latin")
    if any(word in phrase for word in _PHRASE_DENY):
        reasons.append("denied_word")
    return sorted(set(reasons))


@dataclass
class CheckResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)


def check_outgoing(text: str, allowed_bodies: set[str], phrase: str | None = None,
                   allowed_literals: tuple[str, ...] = (), language: str = "ja") -> CheckResult:
    """The full check on the text sent to TTS. `text` must be exactly `phrase + body` (or `body`)
    where `body` is one of the approved, brief-filled `allowed_bodies` and `phrase` passed
    `phrase_problems`. Anything else is 'not_in_brief'."""
    en = language == "en"
    sep = " " if en else ""
    reasons = (amount_problems_en if en else amount_problems)(text, allowed_literals)
    if not any(text == b or (phrase and text == phrase + sep + b) for b in allowed_bodies):
        reasons.append("not_in_brief")
    if phrase and (phrase_problems_en if en else phrase_problems)(phrase):
        reasons.append("bad_phrase")
    return CheckResult(not reasons, sorted(set(reasons)))
