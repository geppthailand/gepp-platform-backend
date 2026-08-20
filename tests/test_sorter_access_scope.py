"""A ผู้คัดแยก's waste-room binding has to grant access, or they cannot save at all.

The binding lives in a column, `user_locations.sorter_location_id` (migration 079),
because the org-chart save rewrites `user_locations.members` wholesale and would
destroy a membership row. But every write is authorised from membership: the tablet
substitutes the bound room as the ORIGIN of a weigh-out, `_validate_origin_access`
asks `grant_for_write` whether the author may write there, and the answer used to be
no for the one location the sorter is supposed to be working in. Result on the
tablet: "บันทึกไม่สำเร็จ" on every save, with the picker itself working fine.

These tests pin the binding as a source of access, and pin the validation that stops
a stale binding from becoming a way in.
"""

import pytest

from GEPPPlatform.libs.locationAccess import grant_for_write
from GEPPPlatform.services.cores.users.user_service import UserService


SORTER_ID = 501
WASTE_ROOM_ID = 77
ORG_ID = 9


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeDb:
    """Answers the one raw-SQL lookup `_sorter_bound_location_ids` makes.

    `rows` is what the JOIN returns, so priming it with [] models every rejection
    the SQL itself performs — no binding, cross-org, deleted or inactive room.
    """

    def __init__(self, rows=None, raises=None):
        self.rows = rows if rows is not None else []
        self.raises = raises
        self.calls = []

    def execute(self, statement, params=None):
        self.calls.append(params)
        if self.raises is not None:
            raise self.raises
        return _FakeResult(self.rows)


def _service(db):
    """UserService without touching UserCRUD/UserPermissionService constructors."""
    svc = UserService.__new__(UserService)
    svc.db = db
    return svc


# ── the binding as a source of access ────────────────────────────────────────

def test_a_bound_waste_room_is_returned_as_membership():
    db = _FakeDb(rows=[(WASTE_ROOM_ID,)])
    assert _service(db)._sorter_bound_location_ids({SORTER_ID}, ORG_ID) == {WASTE_ROOM_ID}


def test_the_lookup_is_scoped_to_the_users_and_the_organization():
    """Both halves matter: a binding is only honoured for the org being resolved."""
    db = _FakeDb(rows=[(WASTE_ROOM_ID,)])
    _service(db)._sorter_bound_location_ids({SORTER_ID, 502}, ORG_ID)
    assert db.calls == [{'user_ids': [SORTER_ID, 502], 'org_id': ORG_ID}]


def test_ids_are_coerced_so_a_string_user_id_still_binds():
    """current_user_id arrives as a string from the token on some paths."""
    db = _FakeDb(rows=[('77',)])
    result = _service(db)._sorter_bound_location_ids({'501'}, ORG_ID)
    assert result == {WASTE_ROOM_ID}
    assert db.calls == [{'user_ids': [SORTER_ID], 'org_id': ORG_ID}]


def test_a_weigher_with_no_binding_gains_nothing():
    """The common case must stay untouched: no binding, no extra access."""
    db = _FakeDb(rows=[])
    assert _service(db)._sorter_bound_location_ids({SORTER_ID}, ORG_ID) == set()


def test_no_users_means_no_query_at_all():
    db = _FakeDb(rows=[(WASTE_ROOM_ID,)])
    assert _service(db)._sorter_bound_location_ids(set(), ORG_ID) == set()
    assert db.calls == []


def test_a_read_failure_degrades_to_no_access_instead_of_raising():
    """Deployed ahead of migration 079 the column does not exist. That must cost a
    sorter their binding, not take down every access check in the platform."""
    db = _FakeDb(raises=RuntimeError('column "sorter_location_id" does not exist'))
    assert _service(db)._sorter_bound_location_ids({SORTER_ID}, ORG_ID) == set()


# ── what the binding has to buy, at the guard that was rejecting saves ───────

def test_without_the_binding_the_write_guard_rejects_the_weigh_out():
    """The bug, stated at the guard that produced it: a sorter is a member of
    nothing, so the substituted origin is refused and the save fails."""
    scope = {'is_owner': False, 'assigned_ids': set(), 'scoped_by_location': {}}
    assert grant_for_write(scope, WASTE_ROOM_ID) == 'You do not have access to this location'


def test_with_the_binding_counted_as_membership_the_write_is_allowed():
    """Tier 1 is what the binding has to reach — a tag/tenant grant would not do,
    because `grant_for_write` then demands a tag or tenant on the payload and the
    tablet has neither to send."""
    scope = {'is_owner': False, 'assigned_ids': {WASTE_ROOM_ID}, 'scoped_by_location': {}}
    assert grant_for_write(scope, WASTE_ROOM_ID) is None


def test_the_binding_does_not_open_up_other_locations():
    """Scope must widen by exactly the bound room."""
    scope = {'is_owner': False, 'assigned_ids': {WASTE_ROOM_ID}, 'scoped_by_location': {}}
    assert grant_for_write(scope, WASTE_ROOM_ID + 1) == 'You do not have access to this location'


# ── the tier resolver folds the binding in ──────────────────────────────────

@pytest.mark.parametrize('bound_rows,expected', [
    ([(WASTE_ROOM_ID,)], {WASTE_ROOM_ID}),
    ([], set()),
])
def test_resolve_location_tiers_assigns_the_bound_room(monkeypatch, bound_rows, expected):
    """End of the chain: a sorter who is a member of nothing still comes out of the
    resolver with tier-1 access to their room, which is what the write guard reads."""

    class _Setup:
        root_nodes = [{'nodeId': WASTE_ROOM_ID, 'children': []}]
        hub_node = None

    db = _FakeDb(rows=bound_rows)

    class _Q:
        def __init__(self, result):
            self.result = result

        def filter(self, *_a):
            return self

        def order_by(self, *_a):
            return self

        def first(self):
            return self.result

    # Organization is queried first (owner check), OrganizationSetup second.
    answers = [None, _Setup()]
    db.query = lambda *_a: _Q(answers.pop(0) if answers else None)

    svc = _service(db)
    monkeypatch.setattr(svc, '_get_created_by_descendants', lambda *_a, **_k: set())

    tiers = svc._resolve_location_tiers(
        locations=[], organization_id=ORG_ID, current_user_id=SORTER_ID
    )
    assert tiers['assigned_ids'] == expected
    assert tiers['is_owner'] is False
