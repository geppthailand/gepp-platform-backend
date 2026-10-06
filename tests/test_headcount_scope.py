"""Per-capita headcount: a node's stored headcount covers its whole subtree."""
from GEPPPlatform.services.cores.users.user_service import resolve_headcount_scope, rollup_headcount


def _tree():
    # Bangkok Branch (no headcount)
    #   UOB Plaza (building) 1000
    #     Floor 1 100
    #       Room 101 (no headcount)
    #     Floor 2 (no headcount)
    #   UOB Sathorn (building, no headcount)
    #     Floor 9 40
    #     Floor 10 60
    return [{
        'nodeId': 1, 'children': [
            {'nodeId': 10, 'children': [
                {'nodeId': 11, 'children': [{'nodeId': 111, 'children': []}]},
                {'nodeId': 12, 'children': []},
            ]},
            {'nodeId': 20, 'children': [
                {'nodeId': 21, 'children': []},
                {'nodeId': 22, 'children': []},
            ]},
        ],
    }]


HEADCOUNTS = {10: 1000, 11: 100, 21: 40, 22: 60}


def test_building_headcount_is_not_added_to_its_floors():
    res = resolve_headcount_scope(_tree(), {10}, HEADCOUNTS)
    assert res['total'] == 1000
    assert res['covered_ids'] == {10, 11, 111, 12}


def test_branch_and_building_selected_counts_building_once():
    # The One Bangkok case: Branch + UOB Plaza selected → 1,000 (was 1,100).
    assert resolve_headcount_scope(_tree(), {1, 10}, HEADCOUNTS)['total'] == 1000 + 40 + 60


def test_floor_selected_alone_uses_the_floor():
    assert resolve_headcount_scope(_tree(), {11}, HEADCOUNTS)['total'] == 100


def test_node_without_headcount_falls_back_to_children():
    res = resolve_headcount_scope(_tree(), {20}, HEADCOUNTS)
    assert res['total'] == 100
    assert 20 not in res['covered_ids']          # its own waste has no people to pair with
    assert {21, 22} <= res['covered_ids']


def test_nothing_filled_in_is_none_not_zero():
    assert resolve_headcount_scope(_tree(), {12}, HEADCOUNTS)['total'] is None


def test_rollup_matches_report_rule():
    assert rollup_headcount(_tree(), {10}, HEADCOUNTS) == 1000
    assert rollup_headcount(_tree(), {1}, HEADCOUNTS) == 1100
    assert rollup_headcount(_tree(), {12}, HEADCOUNTS) is None
