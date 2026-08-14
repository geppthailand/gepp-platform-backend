"""Guards on the ห้องขยะ binding (migration 081).

This column decides where the server will later move material without a human
confirming it, so a bad row silently ships waste to the wrong place. These tests
pin the rules that stop that: same organization, real live location, and never
the location itself.
"""

import pytest

from GEPPPlatform.services.cores.users.user_handlers import _validate_waste_room_location
from GEPPPlatform.exceptions import ValidationException


class _FakeQuery:
    """Records the filters it was given and returns whatever the db was primed with."""

    def __init__(self, db):
        self._db = db

    def filter(self, *criteria):
        self._db.filter_calls.append(criteria)
        return self

    def first(self):
        return self._db.waste_room_row


class _FakeDb:
    def __init__(self, waste_room_row=None):
        self.waste_room_row = waste_room_row
        self.filter_calls = []
        self.query_calls = 0

    def query(self, *_args):
        self.query_calls += 1
        return _FakeQuery(self)


@pytest.mark.parametrize('raw', [None, '', 0, '0'])
def test_clearing_values_return_none_without_touching_the_db(raw):
    """Clearing a binding must not be mistaken for setting one to id 0."""
    db = _FakeDb()
    assert _validate_waste_room_location(db, location_id=11, organization_id=1, raw_value=raw) is None
    assert db.query_calls == 0


def test_self_reference_is_rejected():
    """A location pointing at itself would make the auto-hop a self-loop."""
    db = _FakeDb(waste_room_row=object())
    with pytest.raises(ValidationException):
        _validate_waste_room_location(db, location_id=11, organization_id=1, raw_value=11)
    # Rejected before any lookup — the id alone is enough to know it is invalid.
    assert db.query_calls == 0


def test_self_reference_is_rejected_when_sent_as_a_string():
    """The web app sends Select values as numbers, but the API is public."""
    db = _FakeDb(waste_room_row=object())
    with pytest.raises(ValidationException):
        _validate_waste_room_location(db, location_id=11, organization_id=1, raw_value='11')


def test_non_numeric_value_is_rejected():
    db = _FakeDb()
    with pytest.raises(ValidationException):
        _validate_waste_room_location(db, location_id=11, organization_id=1, raw_value='not-an-id')
    assert db.query_calls == 0


def test_missing_or_out_of_org_location_is_rejected():
    """The query carries the org/live filters, so 'no row' means 'not allowed'."""
    db = _FakeDb(waste_room_row=None)
    with pytest.raises(ValidationException):
        _validate_waste_room_location(db, location_id=11, organization_id=1, raw_value=22)
    assert db.query_calls == 1


def test_valid_binding_returns_the_id():
    db = _FakeDb(waste_room_row=object())
    result = _validate_waste_room_location(db, location_id=11, organization_id=1, raw_value=22)
    assert result == 22


def test_valid_binding_accepts_a_string_id():
    db = _FakeDb(waste_room_row=object())
    assert _validate_waste_room_location(db, location_id=11, organization_id=1, raw_value='22') == 22
