"""Thai phone number normalization + validation for walk-in members.

Used everywhere a phone is accepted (staff walk-in register, phone lookup,
LIFF profile completion, merge matching) so that "081-234-5678", "0812345678",
and "+66812345678" all resolve to the SAME canonical value — otherwise the same
person could end up with duplicate member accounts.
"""

import re

from ...exceptions import BadRequestException

# Thai mobile: 10 digits, starts 06 / 08 / 09 (e.g. 0812345678).
_THAI_MOBILE_RE = re.compile(r"^0[689]\d{8}$")


def normalize_thai_phone(raw: str | None) -> str | None:
    """Reduce a phone string to canonical local form (digits only, leading 0).

    Strips spaces/dashes/parens, converts +66 / 0066 country-code forms to the
    local 0-prefixed form. Returns None for empty input. Does NOT validate — pair
    with is_valid_thai_mobile() or use normalize_and_validate_thai_mobile().
    """
    if raw is None:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    # +66XXXXXXXXX / 66XXXXXXXXX  -> 0XXXXXXXXX   (country code drops the leading 0)
    if digits.startswith("0066"):
        digits = "0" + digits[4:]
    elif digits.startswith("66") and len(digits) >= 11:
        digits = "0" + digits[2:]
    return digits


def is_valid_thai_mobile(normalized: str | None) -> bool:
    """True if the normalized value is a valid Thai mobile number."""
    return bool(normalized and _THAI_MOBILE_RE.match(normalized))


def normalize_and_validate_thai_mobile(raw: str | None) -> str:
    """Normalize + validate; raise BadRequestException on invalid input.

    Returns the canonical 10-digit local form (e.g. "0812345678").
    """
    normalized = normalize_thai_phone(raw)
    if not is_valid_thai_mobile(normalized):
        raise BadRequestException("Invalid Thai mobile number (expected 10 digits starting 06/08/09)")
    return normalized
