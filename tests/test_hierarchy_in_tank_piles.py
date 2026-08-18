"""กองที่นอนอยู่ในถังต้องอยู่ในแผนภาพ ไม่ใช่หายไปทั้งกอง (086).

The flow diagram is built from ``get_traceability_hierarchy``, which only ever
emitted piles that had at least one transport leg. That rule was right when the
only hopless pile was one still waiting to be dispatched — but a pile whose
resolved tank IS its origin never gets a leg at all: the material is already in
the room the moment it is weighed. Under the old rule a tenant's entire delivery
disappeared from the picture while the board and the tank ledger both counted
it, so the diagram showed a room shipping 0.40 kg out with nothing ever
arriving.

Two things are pinned here, and they pull in opposite directions:
  • an in-tank pile IS emitted (with no children — there is no journey yet);
  • an ordinary hopless pile is still NOT emitted, or every undispatched pile in
    the org would clutter the diagram with lines that go nowhere.

Plus the tenant name, which is what lets the diagram draw ผู้เช่า as the sender:
a tenant is a tag on the pile, not a node in the chart (two tenants in one
building weigh at the same location), so it cannot be read off the location.
"""

from GEPPPlatform.services.cores.traceability.traceability_service import TraceabilityService


class _Group:
    def __init__(self, gid, origin_id=21091, material_id=3, tenant_id=None):
        self.id = gid
        self.origin_id = origin_id
        self.material_id = material_id
        self.tenant_id = tenant_id
        self.location_tag_id = None
        self.transaction_year = 2026
        self.transaction_month = 8
        self.transaction_record_id = []
        self.transaction_carried_over = []
        self.source_transaction_id = None
        self.is_active = True
        self.deleted_date = None


class _Transport:
    """Just the columns transport_to_node projects."""

    def __init__(self, tid, group_id, destination_id=21105, weight=0.4,
                 disposal_method="Recycling (Own)", delivered=False):
        self.id = tid
        self.transaction_group_id = group_id
        self.parent_id = None
        self.origin_id = 21091
        self.destination_id = destination_id
        self.material_id = 3
        self.weight = weight
        self.status = "arrived"
        self.arrival_date = None
        self.disposal_method = disposal_method
        self.meta_data = None
        self.is_root = True
        self.absolute_percentage = 100.0
        self.delivered_to_collection = delivered


def _hierarchy_groups(monkeypatch, groups, group_dicts, transports_by_group):
    """Drive the origin→group→leg assembly with the DB reads stubbed out."""
    from GEPPPlatform.services.cores.users import user_service as _us
    monkeypatch.setattr(
        _us.UserService, "_build_location_paths", lambda self, org, locs: {}
    )
    svc = TraceabilityService(db=None)

    monkeypatch.setattr(svc, "_apply_idle_carry_over", lambda *a, **k: None)
    monkeypatch.setattr(svc, "_backfill_traceability_groups_for_month", lambda *a, **k: None)
    monkeypatch.setattr(svc, "_groups_to_dict_list", lambda *a, **k: group_dicts)
    monkeypatch.setattr(svc, "_parse_month_range", lambda *a, **k: (2026, 8))
    monkeypatch.setattr(
        TraceabilityService, "_location_to_dict", lambda self, loc, path="": None
    )

    class _Q:
        def __init__(self, rows):
            self._rows = rows

        def filter(self, *a, **k):
            return self

        def all(self):
            return self._rows

        def distinct(self):
            return self

        def join(self, *a, **k):
            # The batch enrichment passes (consolidation sources, attachments)
            # run once transports exist; they have nothing to add here.
            return _Q([])

    flat = [t for ts in transports_by_group.values() for t in ts]

    class _Db:
        def query(self, *entities, **k):
            name = getattr(entities[0], "__name__", "")
            if name == "TraceabilityTransactionGroup":
                return _Q(groups)
            if name == "TransportTransaction":
                return _Q(flat)
            return _Q([])

    svc.db = _Db()
    return svc.get_traceability_hierarchy(
        organization_id=1756, date_from="2026-08-01", date_to="2026-08-31"
    )["data"]


def _dict(gid, weight, tenant_name=None, in_collection=False, tenant_id=None, origin_id=21091):
    return {
        "id": gid, "group_id": gid, "origin_id": origin_id, "material_id": 3,
        "weight": weight, "total_weight_kg": weight,
        "tenant_id": tenant_id, "tenant_name": tenant_name,
        "location_tag_id": None, "in_collection": in_collection,
        "transaction_record_id": [], "transaction_carried_over": [],
        "transaction_year": 2026, "transaction_month": 8,
    }


def test_a_pile_sitting_in_the_tank_is_drawn(monkeypatch):
    """The tenant's delivery has no journey to draw, but it is real material and
    the room it is standing in ships it out later. Dropped, the diagram showed
    an outflow with no inflow."""
    g = _Group(8323, tenant_id=587)
    origins = _hierarchy_groups(
        monkeypatch, [g], [_dict(8323, 0.49, tenant_name="test1", in_collection=True, tenant_id=587)], {}
    )

    assert len(origins) == 1
    (group,) = origins[0]["children"]
    assert group["group_id"] == 8323
    assert group["in_collection"] is True
    assert group["weight"] == 0.49
    assert group["children"] == [], "material in a tank has not travelled anywhere yet"


def test_an_ordinary_undispatched_pile_is_still_left_out(monkeypatch):
    """The counterweight: piles merely waiting to ship would fill the diagram
    with senders that have no line leaving them."""
    g = _Group(9000)
    origins = _hierarchy_groups(monkeypatch, [g], [_dict(9000, 5.0, in_collection=False)], {})

    assert origins == []


def test_the_tenant_name_travels_with_the_pile(monkeypatch):
    """A tenant is a tag on the pile, not a node in the chart — without the name
    the diagram can only draw the building both tenants weighed at."""
    g = _Group(8323, tenant_id=587)
    origins = _hierarchy_groups(
        monkeypatch, [g], [_dict(8323, 0.49, tenant_name="test1", in_collection=True, tenant_id=587)], {}
    )

    (group,) = origins[0]["children"]
    assert group["tenant_name"] == "test1"
    assert group["tenant_id"] == 587


def test_a_pile_with_no_tenant_says_so_rather_than_guessing(monkeypatch):
    """The sorter's own weigh-out has no tenant; the diagram must fall back to
    the location instead of inventing one."""
    g = _Group(8324)
    origins = _hierarchy_groups(
        monkeypatch, [g], [_dict(8324, 0.4, in_collection=True)], {}
    )

    (group,) = origins[0]["children"]
    assert group["tenant_name"] is None


def test_both_halves_of_a_tank_appear_under_the_same_origin(monkeypatch):
    """What the fix is for: the delivery INTO the room and the shipment OUT of it
    are separate piles that share one location, and the diagram needs both to
    draw a tank with an inflow and an outflow."""
    incoming = _Group(8323, tenant_id=587)
    outgoing = _Group(8324)
    origins = _hierarchy_groups(
        monkeypatch,
        [incoming, outgoing],
        [
            _dict(8323, 0.49, tenant_name="test1", in_collection=True, tenant_id=587),
            _dict(8324, 0.40, in_collection=False),
        ],
        {8324: [_Transport(1244, 8324)]},
    )

    (origin,) = origins
    by_id = {g["group_id"]: g for g in origin["children"]}
    assert set(by_id) == {8323, 8324}
    # Inflow: a tenant's delivery standing in the room, no journey drawn.
    assert by_id[8323]["in_collection"] is True
    assert by_id[8323]["children"] == []
    # Outflow: the room's own weigh-out, with a real leg to a real destination.
    assert by_id[8324]["in_collection"] is False
    assert len(by_id[8324]["children"]) == 1
    assert by_id[8324]["children"][0]["disposal_method"] == "Recycling (Own)"


def test_an_in_tank_pile_still_gets_its_origin_s_real_name(monkeypatch):
    """Regression: the name lookup only collected origins of piles that had a
    transport. An in-tank pile has none BY DEFINITION — the material was
    weighed straight into the room — so its origin was never looked up and
    every card on the board and the diagram fell back to "Location 4384"
    (observed on dev org 31, where the location is really "Tower 4 (office)").
    A pile that is drawn always needs its origin's name."""
    seen_ids = {}

    class _Loc:
        def __init__(self, lid):
            self.id = lid
            self.display_name = f"Real name {lid}"
            self.name_en = None
            self.name_th = None

    class _Q:
        def __init__(self, rows, sink=None):
            self._rows = rows
            self._sink = sink

        def filter(self, *criteria):
            if self._sink is not None:
                self._sink['called'] = True
            return self

        def all(self):
            return self._rows

        def distinct(self):
            return self

        def join(self, *a, **k):
            return _Q([])

    g = _Group(8323, origin_id=4384, tenant_id=None)

    from GEPPPlatform.services.cores.users import user_service as _us
    monkeypatch.setattr(_us.UserService, "_build_location_paths", lambda self, org, locs: {})

    svc = TraceabilityService(db=None)
    monkeypatch.setattr(svc, "_apply_idle_carry_over", lambda *a, **k: None)
    monkeypatch.setattr(svc, "_backfill_traceability_groups_for_month", lambda *a, **k: None)
    monkeypatch.setattr(svc, "_parse_month_range", lambda *a, **k: (2026, 8))
    monkeypatch.setattr(
        svc, "_groups_to_dict_list",
        lambda *a, **k: [_dict(8323, 11.41, in_collection=True, origin_id=4384)],
    )
    monkeypatch.setattr(
        TraceabilityService, "_location_to_dict",
        lambda self, loc, path="": {"id": loc.id, "display_name": loc.display_name},
    )

    class _Db:
        def query(self, *entities, **k):
            name = getattr(entities[0], "__name__", "")
            if name == "TraceabilityTransactionGroup":
                return _Q([g])
            if name == "TransportTransaction":
                return _Q([])
            if name == "UserLocation":
                seen_ids['asked'] = True
                return _Q([_Loc(4384)])
            return _Q([])

    svc.db = _Db()
    origins = svc.get_traceability_hierarchy(
        organization_id=31, date_from="2026-08-01", date_to="2026-08-31"
    )["data"]

    assert seen_ids.get('asked'), "the origin of an in-tank pile was never looked up"
    (origin,) = origins
    assert origin["name"] == "Real name 4384"
    assert origin["name"] != "Location 4384"
    assert origin["origin"] is not None, "the card also needs the location object"
