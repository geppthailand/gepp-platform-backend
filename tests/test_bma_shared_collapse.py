"""Two rules that decide whose id ends up in the BMA workbook.

1. **A shared location reports alone.** Another organization shares ONE node;
   the recursive visibility walk makes its children visible too, which is right
   for "may we read this" and wrong for "whose row is it". UOB shares three
   buildings carrying 115 floors, and those floors were being published
   individually — 525 of the 1,259 ids on `All data-GEPP`.

2. **Positions come from the sheet's header, never from a constant.** `Origin`
   is edited by hand and gained `Display (On/Off)` at K, which shifted
   `GEPP Location ID` from K to L. Index-based writing would have put location
   ids into the Display column and the date over the ids.
"""

from GEPPPlatform.services.integrations.bma.bma_gsheet_service import (
    ORIGIN_ADDED_ON,
    ORIGIN_COLUMNS,
    ORIGIN_LOCATION_ID,
    BMAGSheetService,
    origin_column_map,
)

#: The live header, as the tab actually reads today.
LIVE_HEADER = [
    'Name', 'County', 'Baseline Data',
    'Landfill Waste Reduction\n(Monthly Average)',
    'Recyclable Material\n(Monthly Average)',
    'Organic Material\n(Monthly Average)',
    'Greenhouse Gas Reduction\n(Monthly Average)',
    'Latitude', 'Longitude', 'Google Map Link',
    'Display (On/Off)', 'GEPP Location ID', 'Added On', 'Phasing',
]


class TestOriginColumnMap:
    def test_finds_the_id_column_after_a_column_was_inserted(self):
        m = origin_column_map(LIVE_HEADER)
        assert m[ORIGIN_LOCATION_ID] == 11      # column L, not K
        assert m[ORIGIN_ADDED_ON] == 12         # column M, not L

    def test_the_seed_layout_still_maps_to_itself(self):
        m = origin_column_map(ORIGIN_COLUMNS)
        assert m == {n: i for i, n in enumerate(ORIGIN_COLUMNS)}

    def test_header_whitespace_and_case_do_not_matter(self):
        # The real cells carry embedded newlines and the sheet re-wraps them.
        h = list(LIVE_HEADER)
        h[4] = '  recyclable material   (monthly average)  '
        assert origin_column_map(h)['Recyclable Material\n(Monthly Average)'] == 4

    def test_unknown_columns_are_simply_absent(self):
        m = origin_column_map(LIVE_HEADER)
        assert 'Display (On/Off)' not in m and 'Phasing' not in m

    def test_an_empty_header_maps_nothing(self):
        assert origin_column_map([]) == {}

    def test_first_occurrence_wins_on_a_duplicated_header(self):
        assert origin_column_map(['Name', 'County', 'Name'])['Name'] == 0


class FakeDB:
    """Answers `_rows` from canned results, picked by a fragment of the SQL."""

    def __init__(self, answers):
        self.answers = answers

    def cursor(self):
        raise AssertionError('should not be reached')


class StubService(BMAGSheetService):
    def __init__(self, shared_tree, locations, chart=None):
        super().__init__(None)
        self._shared_tree = shared_tree     # [(root, id, depth), ...]
        self._locations = locations         # [(id, parent_id, district_name)]
        self._chart = chart or {}

    def _rows(self, sql, params=None):
        if 'shared_tree' in sql:
            return self._shared_tree
        return self._locations

    def _chart_edges(self, org_id=None):
        return dict(self._chart)


# A share of 100 that happens to own 101 and 102; 102 owns 103.
SHARED_TREE = [(100, 100, 0), (100, 101, 1), (100, 102, 1), (100, 103, 2)]


class TestSharedRootMap:
    def test_descendants_map_to_the_shared_root(self):
        collapse, roots = StubService(SHARED_TREE, []).shared_root_map()
        assert collapse == {101: 100, 102: 100, 103: 100}
        assert roots == {100}

    def test_the_root_is_not_in_the_collapse_map(self):
        collapse, _ = StubService(SHARED_TREE, []).shared_root_map()
        assert 100 not in collapse

    def test_no_shares_is_empty_not_an_error(self):
        collapse, roots = StubService([], []).shared_root_map()
        assert collapse == {} and roots == set()


class TestResolveDistrictsHonoursTheShare:
    def test_the_root_county_wins_over_a_childs_own_district(self):
        # 101 is tagged ปทุมวัน; the share was granted on 100, which is สาทร.
        svc = StubService(SHARED_TREE, [
            (100, None, 'สาทร'), (101, 100, 'ปทุมวัน'),
            (102, 100, None), (103, 102, None),
        ])
        resolved, info = svc.resolve_districts()
        assert resolved[100] == 'County28'
        assert all(resolved[i] == 'County28' for i in (101, 102, 103))
        assert all(info['authority'][i] == 100 for i in (101, 102, 103))

    def test_a_root_with_no_county_takes_its_whole_subtree_out(self):
        # Never fall back to a floor's own tag: that publishes the other
        # organization's internal breakdown under a county we were not given.
        svc = StubService(SHARED_TREE, [
            (100, None, None), (101, 100, 'ปทุมวัน'),
            (102, 100, None), (103, 102, None),
        ])
        resolved, _ = svc.resolve_districts()
        assert not ({100, 101, 102, 103} & set(resolved))

    def test_own_org_locations_are_untouched_by_the_rule(self):
        svc = StubService(SHARED_TREE, [
            (100, None, 'สาทร'), (101, 100, 'ปทุมวัน'),
            (102, 100, None), (103, 102, None),
            (200, None, 'บางรัก'), (201, 200, 'ดินแดง'),
        ])
        resolved, info = svc.resolve_districts()
        # 201's own เขต still loses to its ancestor — that is the ordinary rule,
        # and it is the ancestor 200, not a shared root.
        assert resolved[201] == 'County04'
        assert info['authority'][201] == 200

    def test_the_collapse_map_is_published_on_the_info_dict(self):
        svc = StubService(SHARED_TREE, [(100, None, 'สาทร'), (101, 100, None),
                                        (102, 100, None), (103, 102, None)])
        _, info = svc.resolve_districts()
        assert info['shared_collapse'] == {101: 100, 102: 100, 103: 100}
        assert info['shared_roots'] == {100}
