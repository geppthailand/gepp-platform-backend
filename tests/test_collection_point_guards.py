"""Material may only leave a collection point by being weighed out (085).

The tank balance is the join between two chains that are otherwise unrelated:
what tenants delivered, and what the ผู้คัดแยก shipped onward. That join holds
only while every exit is measured. Any other way out — extending a delivered
leg, consolidating a pile that is sitting in the room, editing a leg's
destination or weight after the fact — takes kilograms out of the room without
an OUT entry, and the balance is wrong forever after with no way to notice.

Hiding the buttons is not enough: a stale browser tab open across the deploy,
or any direct API call, reaches the same service methods. So the refusals live
in the service layer, and they run BEFORE anything is written — the request
dispatcher commits the session even when a handler turns a refusal into an
error response, so a late refusal would persist the very damage it refused.
"""

import pytest

from GEPPPlatform.services.cores.traceability.traceability_service import (
    TraceabilityService,
)


class _Group:
    def __init__(self, gid=1, origin_id=500, source_transaction_id=None):
        self.id = gid
        self.origin_id = origin_id
        self.source_transaction_id = source_transaction_id
        self.organization_id = 1
        self.is_active = True
        self.deleted_date = None
        self.transaction_record_id = []
        self.transaction_carried_over = []
        self.location_tag_id = None
        self.tenant_id = None


class _Row:
    def __init__(self, tid, delivered=False, group_id=1, destination_id=None):
        self.id = tid
        self.delivered_to_collection = delivered
        self.transaction_group_id = group_id
        self.destination_id = destination_id
        self.organization_id = 1
        self.is_active = True
        self.deleted_date = None
        self.disposal_method = None
        self.weight = 10
        self.parent_id = None
        self.meta_data = None
        self.status = "arrived"
        self.arrival_date = None
        self.origin_id = 1
        self.material_id = None


class _Q:
    def __init__(self, rows, single=None):
        self._rows, self._single = rows, single

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return self._single

    def all(self):
        return self._rows


class _Db:
    """Serves transports and the group.

    Transport lookups are answered in CALL ORDER rather than by parsing the
    filter: the code under test looks each item up once, in the order they were
    submitted, which is exactly what a batch-refusal test needs to exercise.
    """

    def __init__(self, transports=(), group=None, stamp=None):
        self.transports = list(transports)
        self._queue = list(transports)
        self.group = group or _Group()
        self.stamp = stamp          # transactions.collection_location_id
        self.added = []
        self.flushed = 0

    def query(self, *args, **_k):
        first_arg = args[0] if args else None
        name = getattr(first_arg, '__name__', str(first_arg))
        if 'TraceabilityTransactionGroup' in name:
            return _Q([self.group], single=self.group)
        nxt = self._queue.pop(0) if self._queue else (
            self.transports[-1] if self.transports else None
        )
        return _Q(list(self.transports), single=nxt)

    def execute(self, statement, params=None):
        class _R:
            def __init__(self, row):
                self._row = row

            def fetchone(self):
                return self._row
        return _R((self.stamp,) if self.stamp is not None else None)

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        self.flushed += 1


def _svc(db):
    svc = TraceabilityService.__new__(TraceabilityService)
    svc.db = db
    return svc


# ── A delivered leg is the end of its chain ─────────────────────────────────

def test_a_delivered_leg_cannot_be_extended():
    """Continuing it on the web board would move material out of the room while
    the room still counts it as inflow."""
    parent = _Row(7, delivered=True)
    svc = _svc(_Db(transports=[parent]))
    svc._check_group_write_access = lambda *_a, **_k: None

    res = svc.create_transport_transactions(
        data=[{"weight": 5, "origin_id": 1, "destination_id": 2}],
        organization_id=1,
        transport_transaction_id=7,
    )
    assert res["success"] is False
    assert "LOCKED_IN_COLLECTION" in res["message"]


def test_nothing_is_written_when_the_extension_is_refused():
    """The refusal must land before any row is created — the dispatcher commits
    the session even on a refusal."""
    db = _Db(transports=[_Row(7, delivered=True)])
    svc = _svc(db)
    svc._check_group_write_access = lambda *_a, **_k: None

    svc.create_transport_transactions(
        data=[{"weight": 5, "origin_id": 1, "destination_id": 2}],
        organization_id=1,
        transport_transaction_id=7,
    )
    assert db.added == [], "a refused request must leave no rows behind"


def test_an_ordinary_arrived_leg_can_still_be_extended():
    """Legacy multi-hop flows are untouched: only delivered legs are terminal."""
    parent = _Row(7, delivered=False)
    db = _Db(transports=[parent])
    svc = _svc(db)
    svc._check_group_write_access = lambda *_a, **_k: None
    svc._reject_partial_dispatch = lambda *_a, **_k: None
    svc._recalculate_absolute_percentage = lambda *_a, **_k: None

    res = svc.create_transport_transactions(
        data=[{"weight": 5, "origin_id": 1, "destination_id": 2}],
        organization_id=1,
        transport_transaction_id=7,
    )
    assert res["success"] is True


# ── Material sitting in the room ────────────────────────────────────────────

def test_a_pile_inside_a_collection_point_cannot_be_dispatched_from_the_web():
    """It leaves when the ผู้คัดแยก weighs it out, and not before — otherwise the
    kilograms vanish from the balance with nothing recording where they went."""
    group = _Group(gid=1, origin_id=500, source_transaction_id=900)
    db = _Db(group=group, stamp=500)          # stamped tank == origin
    svc = _svc(db)
    svc._check_group_write_access = lambda *_a, **_k: None

    res = svc.create_transport_transactions(
        data=[{"weight": 5, "origin_id": 500, "destination_id": 2}],
        organization_id=1,
        transaction_group_id=1,
    )
    assert res["success"] is False
    assert "LOCKED_IN_COLLECTION" in res["message"]


def test_the_approve_time_auto_hop_is_still_allowed_through():
    """The one sanctioned root-creator on a stamped pile: records that named
    their own destination still ship at approval."""
    group = _Group(gid=1, origin_id=500, source_transaction_id=900)
    db = _Db(group=group, stamp=500)
    svc = _svc(db)
    svc._check_group_write_access = lambda *_a, **_k: None
    svc._reject_partial_dispatch = lambda *_a, **_k: None
    svc._recalculate_absolute_percentage = lambda *_a, **_k: None

    res = svc.create_transport_transactions(
        data=[{"weight": 5, "origin_id": 500, "destination_id": 2}],
        organization_id=1,
        transaction_group_id=1,
        _internal_scale_hop=True,
    )
    assert res["success"] is True


def test_a_pile_that_merely_passed_through_a_tank_is_not_locked():
    """Stamped, but the tank is NOT the origin — the material moved on, so the
    pile behaves normally."""
    group = _Group(gid=1, origin_id=500, source_transaction_id=900)
    db = _Db(group=group, stamp=777)          # tank != origin
    svc = _svc(db)
    svc._check_group_write_access = lambda *_a, **_k: None
    svc._reject_partial_dispatch = lambda *_a, **_k: None
    svc._recalculate_absolute_percentage = lambda *_a, **_k: None

    res = svc.create_transport_transactions(
        data=[{"weight": 5, "origin_id": 500, "destination_id": 2}],
        organization_id=1,
        transaction_group_id=1,
    )
    assert res["success"] is True


def test_a_legacy_pile_is_never_locked():
    """No source transaction ⇒ pre-085 monthly grain ⇒ today's behaviour."""
    group = _Group(gid=1, origin_id=500, source_transaction_id=None)
    db = _Db(group=group, stamp=500)
    svc = _svc(db)
    assert svc._group_is_in_tank(group) is False


def test_an_unreadable_stamp_never_locks_a_pile():
    """A session running ahead of migration 085 must not start refusing work."""
    group = _Group(gid=1, origin_id=500, source_transaction_id=900)

    class _Boom(_Db):
        def execute(self, *_a, **_k):
            raise RuntimeError("column does not exist")

    assert _svc(_Boom(group=group))._group_is_in_tank(group) is False


# ── Editing a delivered leg ─────────────────────────────────────────────────

def test_a_delivered_leg_cannot_be_edited():
    """Repointing it, reweighing it or stamping a method on it all corrupt the
    balance silently. Reverting the source weighing is the supported undo."""
    db = _Db(transports=[_Row(7, delivered=True)])
    svc = _svc(db)

    res = svc.update_transport_transactions(
        data=[{"transport_transaction_id": 7, "weight": 99}],
        organization_id=1,
    )
    assert res["success"] is False
    assert "LOCKED_IN_COLLECTION" in res["message"]


def test_a_refused_edit_does_not_soft_delete_the_descendants_first():
    """The update path wipes descendants before it validates fields. A refusal
    placed after that point would persist the wipe of a rejected edit."""
    wiped = []
    db = _Db(transports=[_Row(7, delivered=True)])
    svc = _svc(db)
    svc._soft_delete_descendants = lambda tid, now: wiped.append(tid)

    svc.update_transport_transactions(
        data=[{"transport_transaction_id": 7, "weight": 99}],
        organization_id=1,
    )
    assert wiped == [], "nothing may be destroyed by a refused edit"


def test_a_batch_is_refused_whole_when_any_item_is_locked():
    """Item 1 is fine, item 2 is delivered: neither may be applied, or the
    partial write survives the refusal."""
    wiped = []
    db = _Db(transports=[_Row(7, delivered=False), _Row(8, delivered=True)])
    svc = _svc(db)
    svc._soft_delete_descendants = lambda tid, now: wiped.append(tid)

    res = svc.update_transport_transactions(
        data=[
            {"transport_transaction_id": 7, "weight": 1},
            {"transport_transaction_id": 8, "weight": 2},
        ],
        organization_id=1,
    )
    assert res["success"] is False
    assert wiped == []
