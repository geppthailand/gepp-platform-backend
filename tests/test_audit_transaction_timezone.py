"""transaction_date must be formatted in the transaction's own timezone.

It is stored as midnight LOCAL written as UTC — 17:00:00 for a UTC+7 country,
16:00:00 for UTC+8 — so formatting it in the wrong zone moves the date a day.
The audit prompt used to hardcode Bangkok, which put every Malaysian and
Philippine record one day early against the date printed on the document.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from GEPPPlatform.prompts.ai_audit_v1.default.scripts.audit_scripts import (
    _COUNTRY_UTC_OFFSET,
    _build_record_data,
    _resolve_timezone,
)


class _FakeQuery:
    def __init__(self, value):
        self._value = value

    def filter(self, *_a, **_k):
        return self

    def scalar(self):
        return self._value


class _FakeDB:
    """Returns one country code, whatever is asked for."""

    def __init__(self, code):
        self.code = code

    def query(self, *_a, **_k):
        return _FakeQuery(self.code)


NAMES = {"mat_map": {}, "dest_map": {}, "origin_name": ""}


def _date_for(code, stored):
    tz = _resolve_timezone(1, _FakeDB(code))
    rec = SimpleNamespace(
        id=1, material_id=None, destination_id=None,
        origin_weight_kg=None, origin_quantity=None,
        origin_price_per_unit=None, total_amount=None,
        transaction_date=datetime.fromisoformat(stored),
    )
    return _build_record_data(rec, {**NAMES, "tz": tz})["transaction_date"]


@pytest.mark.parametrize("code,stored,expected", [
    # UTC+7 stores 17:00; UTC+8 stores 16:00. Both mean the NEXT local day.
    ("TH", "2025-08-24 17:00:00", "2025-08-25"),
    ("TH_DEFAULT", "2025-08-24 17:00:00", "2025-08-25"),
    ("MY", "2025-07-06 16:00:00", "2025-07-07"),
    ("PH", "2025-01-29 16:00:00", "2025-01-30"),
])
def test_local_business_date(code, stored, expected):
    assert _date_for(code, stored) == expected


def test_the_bug_this_fixes():
    """A +8 country's 16:00 timestamp read as Bangkok lands a day early."""
    stored = "2025-01-29 16:00:00"
    bangkok = (datetime.fromisoformat(stored)
               .replace(tzinfo=timezone.utc)
               .astimezone(timezone(timedelta(hours=7))).strftime("%Y-%m-%d"))
    assert bangkok == "2025-01-29"            # what the old code produced
    assert _date_for("PH", stored) == "2025-01-30"   # what the document says


def test_unknown_country_falls_back_to_thailand():
    # never crash on a country nobody has mapped yet
    assert _date_for("ZZ", "2025-08-24 17:00:00") == "2025-08-25"
    assert _date_for(None, "2025-08-24 17:00:00") == "2025-08-25"


def test_no_country_id_skips_the_lookup_entirely():
    assert _resolve_timezone(None, None) == timezone(timedelta(hours=7))


def test_aware_timestamps_are_converted_not_relabelled():
    tz = _resolve_timezone(1, _FakeDB("PH"))
    rec = SimpleNamespace(
        id=1, material_id=None, destination_id=None, origin_weight_kg=None,
        origin_quantity=None, origin_price_per_unit=None, total_amount=None,
        transaction_date=datetime.fromisoformat("2025-01-29 16:00:00+00:00"),
    )
    assert _build_record_data(rec, {**NAMES, "tz": tz})["transaction_date"] == "2025-01-30"


def test_every_country_we_ship_to_is_mapped():
    # the three countries with live projects; add here when a fourth appears
    assert {"TH", "MY", "PH"} <= set(_COUNTRY_UTC_OFFSET)
