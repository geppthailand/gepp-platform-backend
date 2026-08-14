"""Reading node ids out of the org-chart JSON.

A node the web app created but never finished saving keeps its temporary
client-side id — "2186_1768891622748_hub-child-1". Every walker that called
int() on that raised ValueError and returned a 500, which on the locations list
is a blank screen rather than one missing node.
"""

import pytest

from GEPPPlatform.libs.node_ids import to_node_id


@pytest.mark.parametrize('value', [
    '2186_1768891622748_hub-child-1',   # the id that actually took the page down
    '3641_1700000000000_hub-child-12',
    'hub-main',
    'abc',
    '',
    '   ',
    None,
])
def test_ids_that_match_no_row_return_none(value):
    assert to_node_id(value) is None


@pytest.mark.parametrize('value,expected', [
    (2186, 2186),
    ('2186', 2186),
    (' 2186 ', 2186),          # setup JSON has been seen with padding
    ('007', 7),
])
def test_real_ids_are_read_in_either_form(value, expected):
    """nodeId is written as an int by some paths and a string by others."""
    assert to_node_id(value) == expected


def test_shared_location_sentinels_survive():
    """Shared locations are overlaid with large NEGATIVE ids on purpose. Rejecting
    them would make shared subtrees invisible instead of merely unsaved ones."""
    assert to_node_id(-2_000_000_042) == -2_000_000_042
    assert to_node_id('-2000000042') == -2_000_000_042


@pytest.mark.parametrize('value', [True, False])
def test_booleans_are_not_ids(value):
    """bool is a subclass of int, so a bare isinstance check would let True
    through as node 1 and silently attach a real location's data to it."""
    assert to_node_id(value) is None


@pytest.mark.parametrize('value', [1.9, [], {}, object()])
def test_other_junk_returns_none_rather_than_raising(value):
    assert to_node_id(value) is None


def test_a_broken_node_does_not_hide_its_children():
    """The fix must not throw the subtree away with the node: an unsaved parent can
    still have saved children, and dropping them silently loses real locations."""
    from GEPPPlatform.libs.node_ids import to_node_id as f
    tree = [{'nodeId': '2186_1768891622748_hub-child-1',
             'children': [{'nodeId': 55, 'children': []}]}]
    seen = []

    def walk(nodes):
        for n in nodes:
            nid = f(n.get('nodeId'))
            if nid is not None:
                seen.append(nid)
            walk(n.get('children') or [])

    walk(tree)
    assert seen == [55]
