"""ผู้คัดแยกเห็นได้เฉพาะปลายทางที่ตัวเองเป็นสมาชิก.

The first cut handed a sorter every destination in the organisation, reasoning
that holding the binding was authorisation enough and that a sorter — a member
of their waste room only — would otherwise face an empty picker. That trade
stops being acceptable the moment an organisation has more than one destination:
a ผู้คัดแยก at one tower could file a weigh-out against a recycler belonging to
another, and nothing downstream would ever question it (the record path stores
destination_id verbatim).

Membership on the destination is the permission now. Two properties matter more
than the filter itself:

  • the PICKER and the WRITE CHECK must narrow together — narrowing only the
    picker leaves the API accepting anything while the tablet shows one option,
    which is a hole, not a restriction;
  • no silent widening — a sorter with no destination membership gets nothing,
    because a rule that falls back to "everything" when it cannot decide is not
    a rule.
"""

import pytest

from GEPPPlatform.services.cores.iot_devices.sorter import (
    is_allowed_destination,
    list_destinations,
)


HUBS = {4417: 'BMA', 4418: 'Recycle Store', 4419: 'Trash Room'}


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Db:
    """Answers the three reads list_destinations makes, by SQL content."""

    def __init__(self, member_of=(), hubs=HUBS, explode_membership=False):
        self.member_of = list(member_of)
        self.hubs = dict(hubs)
        self.explode_membership = explode_membership
        self.membership_asked = False

    def execute(self, statement, params=None):
        sql = str(statement)
        if "jsonb_array_elements(members)" in sql:
            self.membership_asked = True
            if self.explode_membership:
                raise RuntimeError("jsonb function unavailable")
            return _Rows([(i,) for i in self.member_of])
        if "type = 'hub'" in sql:
            return _Rows([(i, n) for i, n in self.hubs.items()])
        if "organization_setup" in sql:
            return _Rows([([],)])
        return _Rows([])


def _ids(destinations):
    return sorted(d['origin_id'] for d in destinations)


# ── The picker ──────────────────────────────────────────────────────────────

def test_a_sorter_sees_only_the_destination_they_belong_to():
    """Mirrors prod org 31: three hubs exist, the ผู้คัดแยก is a member of one."""
    db = _Db(member_of=[4419])
    assert _ids(list_destinations(db, 31, user_id=21138)) == [4419]


def test_membership_on_several_destinations_shows_all_of_them():
    db = _Db(member_of=[4417, 4419])
    assert _ids(list_destinations(db, 31, user_id=21138)) == [4417, 4419]


def test_a_sorter_who_belongs_nowhere_gets_nothing():
    """No silent widening: an empty list is the answer, and the caller reports it
    rather than falling back to every destination in the organisation."""
    db = _Db(member_of=[])
    assert list_destinations(db, 31, user_id=21138) == []


def test_membership_on_a_non_destination_does_not_invent_one():
    """Being a member of a floor does not make the floor a place to ship TO."""
    db = _Db(member_of=[4391])          # a floor, not one of the hubs
    assert list_destinations(db, 31, user_id=21138) == []


def test_omitting_the_user_keeps_the_organisation_wide_list():
    """The old signature still works for callers that are not scale weighings —
    and the membership read is not even attempted."""
    db = _Db(member_of=[4419])
    assert _ids(list_destinations(db, 31)) == [4417, 4418, 4419]
    assert db.membership_asked is False


# ── The write check must narrow with the picker ─────────────────────────────

def test_the_write_check_accepts_what_the_picker_offered():
    db = _Db(member_of=[4419])
    assert is_allowed_destination(db, 31, 4419, user_id=21138) is True


def test_the_write_check_refuses_a_destination_the_picker_never_offered():
    """The hole this guards: narrowing the picker alone would leave the API
    happily accepting every hub in the organisation."""
    db = _Db(member_of=[4419])
    assert is_allowed_destination(db, 31, 4417, user_id=21138) is False
    assert is_allowed_destination(db, 31, 4418, user_id=21138) is False


def test_the_write_check_refuses_everything_when_the_sorter_belongs_nowhere():
    db = _Db(member_of=[])
    for hub in HUBS:
        assert is_allowed_destination(db, 31, hub, user_id=21138) is False


@pytest.mark.parametrize("bad", [None, "", "abc", -1, 999999])
def test_junk_or_unknown_destinations_are_refused(bad):
    db = _Db(member_of=[4419])
    assert is_allowed_destination(db, 31, bad, user_id=21138) is False


# ── Degradation: closed, not open ──────────────────────────────────────────

def test_a_failed_membership_read_denies_rather_than_opens():
    """Everywhere else in this module a failed read costs visibility; here it
    would cost authorisation, so it fails CLOSED."""
    db = _Db(member_of=[4419], explode_membership=True)
    assert list_destinations(db, 31, user_id=21138) == []
    assert is_allowed_destination(db, 31, 4419, user_id=21138) is False
