"""Callback verification: caller number AND case code (DA 5, CR 15). It lets the family verify the
bank and blocks strangers; it is not proof of identity (CR 24)."""

from __future__ import annotations

import hmac
import re
import unicodedata


def normalise_e164(raw: str | None, default_country_code: str = "81") -> str:
    """Best-effort E.164: '090-1234-5678', '+81 90 1234 5678', full-width digits and '+81 (0)90...'
    all become '+819012345678'. Returns '' when it can't make sense of the input (never matches)."""
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", raw).strip()
    plus = text.startswith("+")
    digits = re.sub(r"\D", "", text)
    if not digits:
        return ""
    if not plus:
        if digits.startswith("00"):
            digits = digits[2:]
        elif digits.startswith("0"):
            digits = default_country_code + digits[1:]
        elif not digits.startswith(default_country_code):
            return ""
    if digits.startswith(default_country_code + "0"):  # '+81 (0)90...'
        digits = default_country_code + digits[len(default_country_code) + 1:]
    if not 8 <= len(digits) <= 15:
        return ""
    return "+" + digits


def normalise_code(raw: str | None) -> str:
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", raw or ""))


def _eq(a: str, b: str) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


def numbers_match(caller_number: str | None, locked_e164: str) -> bool:
    return _eq(normalise_e164(caller_number), normalise_e164(locked_e164))


def codes_match(given: str | None, expected: str) -> bool:
    return _eq(normalise_code(given), normalise_code(expected))
