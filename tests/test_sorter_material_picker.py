"""ตัวเลือกวัสดุบนหน้าชั่งต้องถามถึงปลายทางที่เลือก ไม่ใช่ห้องขยะของตัวเอง.

Setting four materials on a destination still showed all 270 on the tablet, and
the earlier fix did not touch what the operator sees: it narrowed the material
list in the /my-memberships login payload, which the installed build parses into
`MembershipModel.materials` and never reads back. The picker is filled by a
SECOND call — `app_state.selectLocation` -> `getAllowedMaterials(originId)` ->
`POST /api/iot-devices/locations/{id}/allowed-materials` — and that route
substituted the sorter's own waste room for the id the tablet posted.

On prod org 31 the substitution is the whole bug: station 21076
'ห้องคัดแยกขยะ One Bangkok' is a root with `materials = []`, so the tree walk
found nothing to inherit and fell through to "every material", while the
destination 4419 'Trash Room' accepts exactly four.

The invariant these tests exist to hold is not "the list is short" but that the
PICKER and the WRITE ask about the same location. /records checks the chosen
destination's materials (test_iot_records_handler.py), so a picker built from the
station offers material that save() then refuses — the operator is shown 270
options of which 266 fail on submit. Either both read the destination or the
feature is a trap.
"""

import pytest

from GEPPPlatform.services.cores.iot_devices import iot_devices_handlers as handlers
from tests.test_iot_records_handler import _AutoApproveDb


WASTE_ROOM = 21076      # the sorter's station — nothing configured
TRASH_ROOM = 4419       # the destination — four materials
OTHER_HUB = 4417


def _event(location_id):
    return {"rawPath": f"/api/iot-devices/locations/{location_id}/allowed-materials"}


def _ask(monkeypatch, db, location_id, user_id=21138):
    """Run the route and report which location it actually asked about."""
    asked = []

    def fake_lookup(db_session, loc_id, organization_id):
        asked.append(int(loc_id))
        return {"success": True, "data": {"materials": []}}

    monkeypatch.setattr(handlers, "handle_get_location_allowed_materials", fake_lookup)
    handlers.handle_iot_devices_routes(
        _event(location_id),
        data={},
        db_session=db,
        method="POST",
        current_device={"device_id": 3},
        # org 10 is what the shared fake reports for the DEVICE; the route
        # refuses a user/device organisation mismatch before any of this.
        current_user={"user_id": user_id, "organization_id": 10},
    )
    return asked


# ── The reported bug ────────────────────────────────────────────────────────

def test_the_picker_asks_about_the_destination_the_operator_picked(monkeypatch):
    """The fix. Previously this asked about WASTE_ROOM every time."""
    db = _AutoApproveDb(
        sorter_location_id=WASTE_ROOM,
        destinations=[TRASH_ROOM],
        dest_materials={TRASH_ROOM: [290, 366, 356, 367]},
    )
    assert _ask(monkeypatch, db, TRASH_ROOM) == [TRASH_ROOM]


def test_the_station_is_not_consulted_even_though_it_is_configured(monkeypatch):
    """A station with its own list must not override the destination's: the
    station governs what tenants may drop OFF here, the destination governs what
    may be shipped TO it, and a weigh-out is the second question."""
    db = _AutoApproveDb(
        sorter_location_id=WASTE_ROOM,
        destinations=[TRASH_ROOM],
        dest_materials={TRASH_ROOM: [290], WASTE_ROOM: [1, 2, 3, 4, 5, 6, 7, 8]},
    )
    assert _ask(monkeypatch, db, TRASH_ROOM) == [TRASH_ROOM]


def test_each_destination_is_asked_about_separately(monkeypatch):
    """The tablet caches per location id (`_locationMaterialsCache`), so switching
    destination has to be able to produce a different list. Answering for the
    station made every destination identical."""
    db = _AutoApproveDb(
        sorter_location_id=WASTE_ROOM,
        destinations=[TRASH_ROOM, OTHER_HUB],
        dest_materials={TRASH_ROOM: [290], OTHER_HUB: [94, 6]},
    )
    assert _ask(monkeypatch, db, TRASH_ROOM) == [TRASH_ROOM]
    assert _ask(monkeypatch, db, OTHER_HUB) == [OTHER_HUB]


# ── Agreement with the write guard ─────────────────────────────────────────

def test_the_picker_and_the_write_guard_read_the_same_location(monkeypatch):
    """Stated as an equality rather than two separate assertions, because the
    failure mode is drift: whichever id the write guard checks materials against
    is the one the picker must offer."""
    from GEPPPlatform.services.cores.iot_devices.sorter import allowed_material_ids

    db = _AutoApproveDb(
        sorter_location_id=WASTE_ROOM,
        destinations=[TRASH_ROOM],
        dest_materials={TRASH_ROOM: [290, 366, 356, 367]},
    )
    (picker_asked,) = _ask(monkeypatch, db, TRASH_ROOM)
    write_checks = allowed_material_ids(db, 10, [TRASH_ROOM])

    assert picker_asked == TRASH_ROOM
    assert write_checks == {290, 366, 356, 367}


# ── Degradation: keep the screen alive, let the write guard refuse ─────────

def test_a_destination_this_sorter_does_not_belong_to_falls_back_to_the_station(monkeypatch):
    """A tablet holding a picker from before a membership change. 401-ing here
    would strand the station mid-shift for a screen that is only a hint; the
    write guard refuses the post either way."""
    db = _AutoApproveDb(
        sorter_location_id=WASTE_ROOM,
        destinations=[TRASH_ROOM, OTHER_HUB],
        member_of=[TRASH_ROOM],
    )
    assert _ask(monkeypatch, db, OTHER_HUB) == [WASTE_ROOM]


def test_a_sorter_who_belongs_to_no_destination_still_gets_a_screen(monkeypatch):
    db = _AutoApproveDb(
        sorter_location_id=WASTE_ROOM,
        destinations=[TRASH_ROOM],
        member_of=[],
    )
    assert _ask(monkeypatch, db, TRASH_ROOM) == [WASTE_ROOM]


@pytest.mark.parametrize("junk", ["abc", "0", "-1"])
def test_a_nonsense_location_id_does_not_reach_the_lookup_as_a_destination(monkeypatch, junk):
    """`is_allowed_destination` coerces and returns False on junk, so these land
    on the station rather than being passed through."""
    db = _AutoApproveDb(
        sorter_location_id=WASTE_ROOM,
        destinations=[TRASH_ROOM],
    )
    assert _ask(monkeypatch, db, junk) == [WASTE_ROOM]


# ── The weigher path is untouched ──────────────────────────────────────────

def test_a_weigher_with_no_binding_is_asked_about_the_posted_location(monkeypatch):
    """No sorter binding means none of this applies: the posted origin is theirs
    and the membership gate is what authorises it."""
    monkeypatch.setattr(handlers, "can_input_at_location", lambda *a, **k: True)
    db = _AutoApproveDb(sorter_location_id=None)
    assert _ask(monkeypatch, db, 21091) == [21091]


def test_a_weigher_who_is_not_a_member_is_still_refused(monkeypatch):
    """The gate the sorter branch skips must still stand for everyone else."""
    monkeypatch.setattr(handlers, "can_input_at_location", lambda *a, **k: False)
    db = _AutoApproveDb(sorter_location_id=None)

    with pytest.raises(Exception):
        _ask(monkeypatch, db, 21091)
