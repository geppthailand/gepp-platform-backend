"""Unit tests for Thai phone normalization used by walk-in member registration."""

import pytest

from GEPPPlatform.libs.exceptions import APIException
from GEPPPlatform.services.rewards._phone import (
    normalize_thai_phone,
    is_valid_thai_mobile,
    normalize_and_validate_thai_mobile,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0812345678", "0812345678"),
        ("081-234-5678", "0812345678"),
        ("081 234 5678", "0812345678"),
        ("(081) 234-5678", "0812345678"),
        ("+66812345678", "0812345678"),
        ("66812345678", "0812345678"),
        ("0066812345678", "0812345678"),
        ("  0912345678  ", "0912345678"),
    ],
)
def test_normalize_variants_collapse_to_canonical(raw, expected):
    assert normalize_thai_phone(raw) == expected


def test_normalize_empty_inputs_return_none():
    assert normalize_thai_phone(None) is None
    assert normalize_thai_phone("") is None
    assert normalize_thai_phone("---") is None


@pytest.mark.parametrize("value", ["0612345678", "0812345678", "0912345678"])
def test_valid_thai_mobiles(value):
    assert is_valid_thai_mobile(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "0712345678",   # 07 not a mobile prefix
        "081234567",    # too short (9)
        "08123456789",  # too long (11)
        "1234567890",   # no leading 0
        "",
        None,
    ],
)
def test_invalid_thai_mobiles(value):
    assert is_valid_thai_mobile(value) is False


def test_normalize_and_validate_returns_canonical():
    assert normalize_and_validate_thai_mobile("081-234-5678") == "0812345678"
    assert normalize_and_validate_thai_mobile("+66912345678") == "0912345678"


def test_normalize_and_validate_raises_on_garbage():
    with pytest.raises(APIException):
        normalize_and_validate_thai_mobile("not-a-phone")
    with pytest.raises(APIException):
        normalize_and_validate_thai_mobile("0712345678")
