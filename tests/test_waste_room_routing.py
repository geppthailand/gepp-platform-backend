"""Resolving the ห้องขยะ a location feeds (migration 081), used to auto-route the first hop.

An admin sets the waste room once on a building; material is weighed at a room or a
tenant several levels below. Reading only the location's own row therefore found
nothing and no hop was created — the symptom being every weigh-in sitting in the
origin column as if the feature were not deployed at all.

The org chart is JSON in organization_setup.root_nodes; user_locations' parent
columns are never written for locations, so the ancestor walk has to go through it.
"""

import pytest

from GEPPPlatform.services.cores.transactions.transaction_service import TransactionService


class _Setup:
    def __init__(self, root_nodes):
        self.root_nodes = root_nodes


class _Q:
    def __init__(self, rows, single=None):
        self._rows, self._single = rows, single

    def filter(self, *_a, **_k):
        return self

    def order_by(self, *_a, **_k):
        # The setup lookup picks the newest active row, matching how the tablet's
        # own picker chooses one — resolving against a different chart version
        # than the picker used would route material to a tank the operator was
        # never shown.
        return self

    def first(self):
        return self._single

    def all(self):
        return self._rows


class _Db:
    """Answers the setup lookup and the bindings lookup, in that order."""

    def __init__(self, setup=None, bindings=(), explode=False):
        self._setup, self._bindings, self._explode = setup, list(bindings), explode
        self.queries = 0

    def query(self, *args, **_k):
        self.queries += 1
        if self._explode:
            raise RuntimeError('column does not exist')
        # The setup lookup asks for the whole entity; the bindings lookup for 2 columns.
        if len(args) == 1:
            return _Q([], single=self._setup)
        return _Q(self._bindings)


def _svc(db):
    svc = TransactionService.__new__(TransactionService)
    svc.db = db
    return svc


# Branch 1 > Building 1 > Floor 1 > Room 1 — the shape the dev org actually has.
TREE = [{'nodeId': 21090, 'children': [
            {'nodeId': 21091, 'children': [
                {'nodeId': 21092, 'children': [
                    {'nodeId': 21093, 'children': []}]}]}]}]


def test_a_binding_on_the_location_itself_is_used():
    db = _Db(setup=_Setup(TREE), bindings=[(21092, 21111)])
    assert _svc(db)._waste_room_for_location(21092, 1) == 21111


def test_a_binding_on_the_building_reaches_a_room_below_it():
    """The reported bug: set on Building 1, material weighed at a room underneath,
    and nothing routed anywhere."""
    db = _Db(setup=_Setup(TREE), bindings=[(21091, 21111)])
    assert _svc(db)._waste_room_for_location(21093, 1) == 21111


def test_the_nearest_binding_wins():
    """A floor with its own waste room must not be overruled by the building's."""
    db = _Db(setup=_Setup(TREE), bindings=[(21091, 999), (21092, 21111)])
    assert _svc(db)._waste_room_for_location(21093, 1) == 21111


def test_no_binding_anywhere_up_the_chain_means_material_stays_put():
    db = _Db(setup=_Setup(TREE), bindings=[])
    assert _svc(db)._waste_room_for_location(21093, 1) is None


def test_a_location_outside_the_chart_falls_back_to_its_own_row():
    db = _Db(setup=_Setup(TREE), bindings=[(55555, 21111)])
    assert _svc(db)._waste_room_for_location(55555, 1) == 21111


# ── ancestor walk ─────────────────────────────────────────────────────────

def test_ancestors_are_returned_nearest_first():
    """Order is the whole point — it is what makes the nearest binding win."""
    db = _Db(setup=_Setup(TREE))
    assert _svc(db)._location_ancestors(21093, 1) == [21092, 21091, 21090]


def test_an_unsaved_node_does_not_sever_the_chain():
    """A node still carrying its temporary client-side id sits between a room and its
    building. Dropping the link there would silently stop routing for everything
    below it."""
    tree = [{'nodeId': 21091, 'children': [
                {'nodeId': '21091_1768891622748_hub-child-1', 'children': [
                    {'nodeId': 21093, 'children': []}]}]}]
    db = _Db(setup=_Setup(tree), bindings=[(21091, 21111)])
    assert _svc(db)._waste_room_for_location(21093, 1) == 21111


def test_a_cycle_in_the_chart_does_not_hang():
    """The chart is client-supplied JSON; a loop must not spin forever inside an
    approval."""
    tree = [{'nodeId': 1, 'children': [{'nodeId': 2, 'children': [{'nodeId': 1, 'children': []}]}]}]
    db = _Db(setup=_Setup(tree))
    assert _svc(db)._location_ancestors(2, 1) == [1]


def test_no_setup_means_no_ancestors_rather_than_an_error():
    assert _svc(_Db(setup=None))._location_ancestors(21093, 1) == []


# ── the paths that must never raise ───────────────────────────────────────

@pytest.mark.parametrize('location_id,organization_id', [
    (None, 1), (0, 1), (21093, None), (21093, 0), ('abc', 1),
])
def test_unusable_identifiers_return_none(location_id, organization_id):
    assert _svc(_Db(setup=_Setup(TREE)))._waste_room_for_location(location_id, organization_id) is None


def test_a_database_error_never_escapes():
    """This runs inside transaction approval. If the column is missing — code deployed
    ahead of migration 081 — approval must still succeed, just without routing."""
    assert _svc(_Db(explode=True))._waste_room_for_location(21093, 1) is None
