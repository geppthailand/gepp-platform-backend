"""Guards the boundary between internal and customer-visible report data.

The public report page is reachable by anyone holding the QR link. Anything
that reaches `to_public_payload` output leaves the organisation. These tests
exist so that stays a deliberate decision rather than an accident.
"""

from GEPPPlatform.services.cores.scale_reports.scale_report_service import to_public_payload


def _full_summary(**extra):
    """A realistic full summary, shaped like get_daily_summary's return."""
    summary = {
        'date': '2026-07-26',
        'timezone': 'Asia/Bangkok',
        'window_utc': {'start': '2026-07-25T17:00:00', 'end': '2026-07-26T17:00:00'},
        'location': {
            'origin_id': 123,
            'display_name': 'ศูนย์รับซื้อ สาขาบางนา',
            'name_th': 'สาขาบางนา',
            'name_en': 'Bangna branch',
        },
        'totals': {
            'weight_kg': 1234.56,
            'entries': 42,
            'material_count': 7,
            'co2e_kg': 987.65,
            'trees_equivalent': 103.9,
            'forest_rai_equivalent': 1.04,
            'first_entry_at': '2026-07-26T01:15:00',
            'last_entry_at': '2026-07-26T09:40:00',
        },
        'materials': [
            {'material_id': 1, 'name_th': 'ขวด PET ใส', 'weight_kg': 500.0,
             'entries': 12, 'co2e_kg': 400.0, 'share_pct': 40.5},
        ],
        'generated_at': '2026-07-26T09:41:02',
    }
    summary.update(extra)
    return summary


def _summary_with_subtree(**extra):
    """A building-level summary: readings arrive at the floors underneath it.

    Shaped like what `_split_by_location` builds, including the row for the
    building itself (`is_self`) which is what a scale plugged in at the lobby
    produces.
    """
    return _full_summary(subtree={
        'location_count': 3,
        'has_descendants': True,
        'totals': {
            'weight_kg': 900.0, 'entries': 30, 'material_count': 2,
            'co2e_kg': 700.0, 'trees_equivalent': 73.7,
            'forest_rai_equivalent': 0.74,
            'first_entry_at': '2026-07-26T01:15:00',
            'last_entry_at': '2026-07-26T09:40:00',
        },
        'materials': [
            {'material_id': 1, 'name_th': 'ขวด PET ใส', 'weight_kg': 600.0,
             'entries': 20, 'co2e_kg': 500.0, 'share_pct': 66.7},
            {'material_id': 2, 'name_th': 'กระดาษ', 'weight_kg': 300.0,
             'entries': 10, 'co2e_kg': 200.0, 'share_pct': 33.3},
        ],
        'locations': [
            {
                'origin_id': 991,
                'display_name': 'ชั้น 1',
                'is_self': False,
                'share_pct': 66.7,
                'totals': {
                    'weight_kg': 600.0, 'entries': 20, 'material_count': 2,
                    'co2e_kg': 500.0, 'trees_equivalent': 52.6,
                    'forest_rai_equivalent': 0.53,
                    'first_entry_at': '2026-07-26T01:15:00',
                    'last_entry_at': '2026-07-26T09:40:00',
                },
                'materials': [
                    {'material_id': 1, 'name_th': 'ขวด PET ใส',
                     'weight_kg': 400.0, 'entries': 14, 'quantity': 14.0,
                     'co2e_kg': 330.0, 'share_pct': 66.7},
                    {'material_id': 2, 'name_th': 'กระดาษ',
                     'weight_kg': 200.0, 'entries': 6, 'quantity': 6.0,
                     'co2e_kg': 170.0, 'share_pct': 33.3},
                ],
            },
            {
                'origin_id': 123,
                'display_name': 'ศูนย์รับซื้อ สาขาบางนา',
                'is_self': True,
                'share_pct': 33.3,
                'totals': {
                    'weight_kg': 300.0, 'entries': 10, 'material_count': 1,
                    'co2e_kg': 200.0, 'trees_equivalent': 21.1,
                    'forest_rai_equivalent': 0.21,
                    'first_entry_at': '2026-07-26T02:00:00',
                    'last_entry_at': '2026-07-26T08:00:00',
                },
                'materials': [
                    {'material_id': 1, 'name_th': 'ขวด PET ใส',
                     'weight_kg': 300.0, 'entries': 10, 'quantity': 10.0,
                     'co2e_kg': 200.0, 'share_pct': 100.0},
                ],
            },
        ],
    }, **extra)


# ── what must never leave the organisation ───────────────────────────────────

def test_per_material_breakdown_is_exposed():
    """Deliberate reversal of the original decision.

    It was withheld at first because volumes by material are the station's
    commercial position. The business chose to show it anyway: "the community
    brought in 300 kg of PET" is the reason a customer scans at all. The
    trade-off was accepted knowingly, so the test states the new intent
    rather than being quietly deleted.
    """
    public = to_public_payload(_full_summary())
    assert len(public['materials']) == 1
    assert public['materials'][0]['name_th'] == 'ขวด PET ใส'
    assert public['totals']['material_count'] == 7


def test_internal_identifiers_are_withheld():
    public = to_public_payload(_full_summary())
    assert 'window_utc' not in public
    assert 'origin_id' not in public['location']


def test_internal_ids_never_reach_a_material_entry():
    """The breakdown is public now, but the ids behind it are not — they have
    no reader value and invite scraping the material catalogue."""
    entry = to_public_payload(_full_summary())['materials'][0]
    for forbidden in ('material_id', 'main_material_id', 'category_id',
                      'entries', 'quantity'):
        assert forbidden not in entry, forbidden


def test_a_field_added_later_does_not_leak_automatically():
    """The allowlist guarantee.

    If this were implemented by deleting unwanted keys, a future field on
    get_daily_summary — say a per-operator or per-price breakdown — would flow
    straight out to the public page and no test would notice.
    """
    public = to_public_payload(_full_summary(
        operator_names=['สมชาย'],
        total_amount_thb=45000,
    ))
    assert 'operator_names' not in public
    assert 'total_amount_thb' not in public
    assert 'สมชาย' not in repr(public)
    assert '45000' not in repr(public)


def test_totals_sub_dict_is_rebuilt_not_passed_through():
    """A shared reference would let a later mutation of the full summary
    change what was already handed to a customer."""
    full = _full_summary()
    public = to_public_payload(full)
    assert public['totals'] is not full['totals']
    assert public['location'] is not full['location']


# ── what customers are meant to see ──────────────────────────────────────────

def test_headline_numbers_are_present_and_unchanged():
    public = to_public_payload(_full_summary())
    assert public['date'] == '2026-07-26'
    assert public['location']['display_name'] == 'ศูนย์รับซื้อ สาขาบางนา'
    assert public['totals']['weight_kg'] == 1234.56
    assert public['totals']['entries'] == 42


def test_carbon_equivalents_are_present():
    """These are the reason a customer bothers to scan at all."""
    totals = to_public_payload(_full_summary())['totals']
    assert totals['co2e_kg'] == 987.65
    assert totals['trees_equivalent'] == 103.9
    assert totals['forest_rai_equivalent'] == 1.04


def test_exposed_key_set_is_exactly_what_we_intend():
    """Locks the contract so widening it has to be an explicit edit here."""
    public = to_public_payload(_full_summary())
    assert set(public) == {
        'date', 'timezone', 'location', 'totals', 'materials', 'locations',
        'generated_at',
    }
    assert set(public['location']) == {'display_name', 'name_th', 'name_en'}
    assert set(public['totals']) == {
        'weight_kg', 'entries', 'material_count', 'co2e_kg',
        'trees_equivalent', 'forest_rai_equivalent',
    }
    assert set(public['materials'][0]) == {
        'name_th', 'name_en', 'main_material_name_th', 'main_material_name_en',
        'unit_name_th', 'unit_name_en', 'color', 'weight_kg', 'share_pct',
        'co2e_kg',
    }


# ── the per-location split ───────────────────────────────────────────────────

def test_per_location_split_is_exposed():
    """Answers "which floor", which the material list alone cannot."""
    locations = to_public_payload(_summary_with_subtree())['locations']
    assert [loc['display_name'] for loc in locations] == [
        'ชั้น 1', 'ศูนย์รับซื้อ สาขาบางนา',
    ]
    assert locations[0]['weight_kg'] == 600.0
    assert locations[0]['share_pct'] == 66.7


def test_a_location_carries_its_own_material_breakdown():
    """The whole point of the accordion — expanding a floor shows its mix."""
    first = to_public_payload(_summary_with_subtree())['locations'][0]
    assert [m['name_th'] for m in first['materials']] == ['ขวด PET ใส', 'กระดาษ']
    # share_pct under a location is relative to that location, not the branch
    assert sum(m['share_pct'] for m in first['materials']) == 100.0


def test_is_self_survives_so_the_page_can_label_the_own_node_row():
    """A scale plugged in at the building itself produces a row that reads
    wrong as just another floor name — the page needs to mark it."""
    locations = to_public_payload(_summary_with_subtree())['locations']
    assert [loc['is_self'] for loc in locations] == [False, True]


def test_origin_ids_never_reach_a_location_entry():
    """Same rule as materials: internal ids stay in. The page keys its rows on
    array position, so it never needs one."""
    public = to_public_payload(_summary_with_subtree())
    for loc in public['locations']:
        assert 'origin_id' not in loc
        assert set(loc) == {
            'display_name', 'is_self', 'weight_kg', 'entries',
            'material_count', 'co2e_kg', 'share_pct', 'materials',
        }
    assert '991' not in repr(public)


def test_the_material_allowlist_applies_inside_a_location_too():
    """The nested list is the easy one to forget — it must go through the same
    allowlist as the top-level one, not be passed through."""
    nested = to_public_payload(_summary_with_subtree())['locations'][0]['materials'][0]
    for forbidden in ('material_id', 'main_material_id', 'category_id',
                      'entries', 'quantity'):
        assert forbidden not in nested, forbidden
    assert set(nested) == {
        'name_th', 'name_en', 'main_material_name_th', 'main_material_name_en',
        'unit_name_th', 'unit_name_en', 'color', 'weight_kg', 'share_pct',
        'co2e_kg',
    }


def test_a_field_added_later_to_a_location_does_not_leak():
    """Same allowlist guarantee as the top level, checked at the nested level
    where a `del`-based implementation would most plausibly slip through."""
    summary = _summary_with_subtree()
    summary['subtree']['locations'][0]['operator_names'] = ['สมชาย']
    summary['subtree']['locations'][0]['materials'][0]['unit_price_thb'] = 12.5
    public = to_public_payload(summary)
    assert 'สมชาย' not in repr(public)
    assert 'unit_price_thb' not in repr(public)


def test_a_leaf_station_reports_no_location_split():
    """Most stations are leaves. `locations` stays present but empty so the
    page can branch on length instead of on a missing key."""
    public = to_public_payload(_full_summary())
    assert public['locations'] == []


def test_survives_an_empty_day():
    """A station with no readings yet must still render, not 500."""
    public = to_public_payload({
        'date': '2026-07-26',
        'timezone': 'Asia/Bangkok',
        'location': {'display_name': 'สาขาบางนา'},
        'totals': {'weight_kg': 0.0, 'entries': 0, 'co2e_kg': 0.0,
                   'trees_equivalent': 0.0, 'forest_rai_equivalent': 0.0},
        'materials': [],
        'generated_at': '2026-07-26T01:00:00',
    })
    assert public['totals']['weight_kg'] == 0.0
    assert public['materials'] == []


def test_missing_sections_do_not_raise():
    """Defensive: a partial dict should degrade to nulls, not KeyError."""
    public = to_public_payload({})
    assert public['date'] is None
    assert public['totals']['weight_kg'] is None
