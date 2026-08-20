"""ตาชั่งต้องเสนอเฉพาะวัสดุที่ปลายทางรับ.

Setting materials on a destination did nothing to the scale: the login payload
handed over `_get_cached_materials` — every material in the system — and the
tablet copies that single list onto every location itself (see
production_api_service.dart: "ใส่ materials ทั้งหมดในทุก location"). So a
Trash Room configured for four materials still offered all of them.

Two properties are pinned here:

  • the PICKER narrows to what the sorter's destinations accept, and
  • the WRITE refuses a material the chosen destination does not accept,

because a picker without the second is decoration — a tablet holding a list
cached from before a config change would still post the old material, and
nothing downstream compares material against destination.

The platform convention that an EMPTY `materials` array means "not configured,
accept anything" is load-bearing (it is what handle_get_location_allowed_materials
already does). One unconfigured destination therefore widens the union back to
"no restriction": restricting it would refuse material the organisation never
said no to.
"""

import pytest

from GEPPPlatform.services.cores.iot_devices.sorter import (
    allowed_material_ids,
    filter_materials,
)


TRASH_ROOM = 4419
BMA = 4417
RECYCLE_STORE = 4418


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _Db:
    """Answers the materials-column read. `config` maps location id -> array."""

    def __init__(self, config, explode=False):
        self.config = dict(config)
        self.explode = explode

    def execute(self, statement, params=None):
        if self.explode:
            raise RuntimeError("connection lost")
        wanted = (params or {}).get('ids') or []
        return _Rows([(i, self.config.get(i)) for i in wanted if i in self.config])


# ── The union ───────────────────────────────────────────────────────────────

def test_one_configured_destination_gives_exactly_its_list():
    """The reported case: Trash Room set to four materials on prod."""
    db = _Db({TRASH_ROOM: [290, 94, 256, 357]})
    assert allowed_material_ids(db, 31, [TRASH_ROOM]) == {290, 94, 256, 357}


def test_several_configured_destinations_union_their_lists():
    db = _Db({TRASH_ROOM: [290, 94], RECYCLE_STORE: [94, 6]})
    assert allowed_material_ids(db, 31, [TRASH_ROOM, RECYCLE_STORE]) == {290, 94, 6}


def test_one_unconfigured_destination_removes_the_restriction():
    """An empty array means "accepts anything". Restricting the union anyway would
    refuse material at a destination the organisation never limited."""
    db = _Db({TRASH_ROOM: [290, 94], BMA: []})
    assert allowed_material_ids(db, 31, [TRASH_ROOM, BMA]) is None


@pytest.mark.parametrize("empty", [[], None])
def test_a_destination_with_nothing_configured_is_unrestricted(empty):
    db = _Db({BMA: empty})
    assert allowed_material_ids(db, 31, [BMA]) is None


def test_no_destinations_means_no_restriction_to_express():
    db = _Db({TRASH_ROOM: [290]})
    assert allowed_material_ids(db, 31, []) is None


def test_a_destination_that_no_longer_exists_contributes_nothing():
    """Deleted or cross-org id: it cannot narrow anything, and on its own leaves
    nothing honest to say."""
    db = _Db({})
    assert allowed_material_ids(db, 31, [999999]) is None


def test_junk_ids_do_not_produce_a_bogus_restriction():
    db = _Db({TRASH_ROOM: [290]})
    assert allowed_material_ids(db, 31, ["not-an-id"]) is None


def test_a_failed_read_leaves_the_picker_as_wide_as_today():
    """Opposite of the membership read, on purpose: precision is what a failure
    costs here, not authorisation — the write check does its own lookup."""
    db = _Db({TRASH_ROOM: [290]}, explode=True)
    assert allowed_material_ids(db, 31, [TRASH_ROOM]) is None


# ── Filtering the payload ───────────────────────────────────────────────────

MATERIALS = [
    {'material_id': 290, 'name_th': 'ก'},
    {'material_id': 94, 'name_th': 'ข'},
    {'material_id': 6, 'name_th': 'ค'},
]


def test_the_payload_is_narrowed_to_the_allowed_ids():
    out = filter_materials(MATERIALS, {290, 6})
    assert [m['material_id'] for m in out] == [290, 6]


def test_no_restriction_returns_everything():
    assert len(filter_materials(MATERIALS, None)) == 3


def test_filtering_never_mutates_the_shared_cache():
    """`_get_cached_materials` hands back a process-level list. Filtering it in
    place would leak one sorter's restriction into every other tablet served by
    the same warm container."""
    before = [dict(m) for m in MATERIALS]
    filter_materials(MATERIALS, {290})
    assert MATERIALS == before
    assert filter_materials(MATERIALS, None) is not MATERIALS


def test_an_allowed_id_that_is_no_longer_live_is_simply_absent():
    """Configured-but-deleted material: the list shrinks, it does not error."""
    out = filter_materials(MATERIALS, {290, 999999})
    assert [m['material_id'] for m in out] == [290]
