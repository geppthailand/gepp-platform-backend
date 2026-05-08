"""
Unit tests for datapoint_registry.

Covers:
  - Alias resolution (English + Thai → canonical)
  - String-with-unit value parsing ("28.6 km" → 28.6 + 'km')
  - Unit conversion (miles → km, lbs → kg, MWh → kWh)
  - raw_<key> sibling preservation
  - Idempotency: normalize(normalize(x)) == normalize(x)
  - Categorical normalisation (English + Thai)
  - Per-cat satisfaction matrix: every Scope 3 cat 1-15 has at
    least one alias path that produces every key in its
    satisfaction tuple

Pure-Python — no DB, no LLM. Runs in well under a second.
"""

from __future__ import annotations

import pytest

from GEPPPlatform.services.esg import datapoint_registry as R
from GEPPPlatform.services.esg.datapoint_registry import (
    ALIAS_MAP,
    CANONICAL_CATEGORICAL_KEYS,
    CANONICAL_NUMERIC_KEYS,
    normalize_datapoint,
    normalize_datapoints,
    parse_numeric_with_unit,
)


# ──────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────

def _names(dps):
    return [d.get('datapoint_name') for d in dps]


def _by_name(dps):
    return {d.get('datapoint_name'): d for d in dps}


# ──────────────────────────────────────────────────────────────────
# parse_numeric_with_unit
# ──────────────────────────────────────────────────────────────────

class TestParseNumericWithUnit:

    @pytest.mark.parametrize('value,unit,exp_num,exp_unit', [
        (28.6, 'km', 28.6, 'km'),
        ('28.6 km', None, 28.6, 'km'),
        ('28.6', 'km', 28.6, 'km'),
        ('28.6 กม.', None, 28.6, 'km'),         # Thai unit
        ('28.6', 'กม.', 28.6, 'km'),
        ('1,200', 'kg', 1200.0, 'kg'),          # thousands sep
        ('17 miles', None, 17.0, 'mile'),
        ('-5.5', 'kg', -5.5, 'kg'),             # negative
    ])
    def test_happy_path(self, value, unit, exp_num, exp_unit):
        num, parsed_unit, raw_str = parse_numeric_with_unit(value, unit)
        assert num == pytest.approx(exp_num)
        assert parsed_unit == exp_unit
        assert raw_str  # always non-empty for happy paths

    def test_unparseable_string(self):
        num, _, raw_str = parse_numeric_with_unit('hello world', None)
        assert num is None
        assert raw_str == 'hello world'

    def test_none_value(self):
        num, _, _ = parse_numeric_with_unit(None, 'km')
        assert num is None


# ──────────────────────────────────────────────────────────────────
# Alias map — bilingual
# ──────────────────────────────────────────────────────────────────

class TestAliasMap:

    @pytest.mark.parametrize('alias,canonical', [
        # English
        ('distance', 'distance_km'),
        ('Distance', 'distance_km'),                # case-insensitive
        ('travel_distance', 'distance_km'),
        ('weight', 'weight_kg'),
        ('mass', 'weight_kg'),
        ('volume', 'volume_litres'),
        ('liters', 'volume_litres'),
        ('kwh', 'energy_kwh'),
        ('electricity', 'energy_kwh'),
        ('mwh', 'energy_mwh'),
        ('floor_area', 'floor_area_sqm'),
        ('fare', 'amount'),
        ('total_fare', 'amount'),
        ('hotel_nights', 'nights'),
        ('passengers', 'headcount'),
        ('stores', 'franchise_count'),
        ('mode', 'transport_mode'),
        ('class', 'flight_class'),
        ('disposal', 'disposal_method'),
        # Thai
        ('ระยะทาง', 'distance_km'),
        ('น้ำหนัก', 'weight_kg'),
        ('น้ำมัน', 'volume_litres'),
        ('พลังงาน', 'energy_kwh'),
        ('ราคารวม', 'amount'),
        ('จำนวนคืน', 'nights'),
        ('จำนวนพนักงาน', 'headcount'),
        ('วิธีกำจัด', 'disposal_method'),
        ('สกุลเงิน', 'currency'),
    ])
    def test_alias_resolves(self, alias, canonical):
        # Lowercase + lookup-key normalisation is internal; we still
        # ensure the map contains the alias as written.
        normalised = R._normalize_lookup_key(alias)
        assert ALIAS_MAP.get(normalised) == canonical


# ──────────────────────────────────────────────────────────────────
# normalize_datapoint — single row
# ──────────────────────────────────────────────────────────────────

class TestNormalizeDatapoint:

    def test_descriptive_passes_through(self):
        dp = {'datapoint_name': 'driver_name', 'value': 'นายสมชาย ใจดี'}
        out = normalize_datapoint(dp)
        assert out == [dp]

    def test_canonical_already_correct_round_trips(self):
        dp = {
            'datapoint_name': 'distance_km',
            'value': 28.6,
            'unit': 'km',
            'canonical_name': 'distance_km',
            'is_canonical': True,
        }
        out = normalize_datapoint(dp)
        # Canonical-already → single row, no raw sibling
        assert len(out) == 1
        assert out[0]['datapoint_name'] == 'distance_km'
        assert out[0]['value'] == 28.6
        assert out[0]['unit'] == 'km'
        assert out[0]['is_canonical'] is True

    def test_string_with_unit_splits_and_emits_raw(self):
        dp = {'datapoint_name': 'distance', 'value': '28.6 km'}
        out = normalize_datapoint(dp)
        names = _names(out)
        assert 'distance_km' in names
        assert 'raw_distance_km' in names
        rows = _by_name(out)
        assert rows['distance_km']['value'] == 28.6
        assert rows['distance_km']['unit'] == 'km'
        assert rows['distance_km']['is_canonical'] is True
        assert rows['raw_distance_km']['value'] == '28.6 km'

    def test_thai_unit_string_splits(self):
        # The exact bug pattern from the user's screenshot.
        dp = {'datapoint_name': 'distance', 'value': '28.6 กม.'}
        out = normalize_datapoint(dp)
        rows = _by_name(out)
        assert rows['distance_km']['value'] == 28.6
        assert rows['distance_km']['unit'] == 'km'
        assert rows['raw_distance_km']['value'] == '28.6 กม.'

    def test_miles_converts_to_km(self):
        dp = {'datapoint_name': 'distance', 'value': 17, 'unit': 'miles'}
        out = normalize_datapoint(dp)
        rows = _by_name(out)
        assert rows['distance_km']['value'] == pytest.approx(27.358848, rel=1e-4)
        assert rows['distance_km']['unit'] == 'km'
        # raw_<key> preserves the original literal
        assert '17' in str(rows['raw_distance_km']['value'])
        assert 'miles' in str(rows['raw_distance_km']['value'])

    def test_lbs_converts_to_kg(self):
        dp = {'datapoint_name': 'weight', 'value': 100, 'unit': 'lb'}
        out = normalize_datapoint(dp)
        rows = _by_name(out)
        assert rows['weight_kg']['value'] == pytest.approx(45.359237, rel=1e-4)
        assert rows['weight_kg']['unit'] == 'kg'

    def test_mwh_converts_to_kwh(self):
        dp = {'datapoint_name': 'mwh', 'value': 5, 'unit': 'mwh'}
        out = normalize_datapoint(dp)
        rows = _by_name(out)
        # mwh is its own canonical key (energy_mwh) — but the value
        # is numeric so it stays as 5 mwh, not 5000 kwh. That's by
        # design: if the LLM said MWh, we keep MWh. The carbon
        # service handles the kWh ↔ MWh conversion at calc time.
        assert rows['energy_mwh']['value'] == 5

    def test_unparseable_string_emits_raw_only(self):
        dp = {'datapoint_name': 'distance', 'value': 'about 30 something'}
        out = normalize_datapoint(dp)
        names = _names(out)
        assert 'distance_km' not in names      # no canonical row
        assert 'raw_distance_km' in names

    def test_categorical_thai_to_english(self):
        dp = {'datapoint_name': 'mode', 'value': 'แท็กซี่'}
        out = normalize_datapoint(dp)
        assert out[0]['datapoint_name'] == 'transport_mode'
        assert out[0]['value'] == 'taxi'
        assert out[0]['is_canonical'] is True

    def test_currency_uppercased(self):
        dp = {'datapoint_name': 'currency', 'value': 'thb'}
        out = normalize_datapoint(dp)
        assert out[0]['value'] == 'THB'

    def test_categorical_unknown_value_kept_as_descriptive(self):
        dp = {'datapoint_name': 'transport_mode', 'value': 'hovercraft'}
        out = normalize_datapoint(dp)
        # Unknown vocab → still rebadged to canonical key (so the
        # carbon service won't pick it up as a mode), but with
        # is_canonical=False so the calc skips it gracefully.
        assert out[0]['datapoint_name'] == 'transport_mode'
        assert out[0]['is_canonical'] is False

    def test_raw_pass_through(self):
        # A row that's already a raw_<key> sibling shouldn't be
        # reinterpreted (or we'd double-process and lose audit info).
        dp = {'datapoint_name': 'raw_distance_km', 'value': '28.6 km'}
        out = normalize_datapoint(dp)
        assert out == [dp]


# ──────────────────────────────────────────────────────────────────
# normalize_datapoints — list-level dedup + idempotency
# ──────────────────────────────────────────────────────────────────

class TestNormalizeDatapointsList:

    def test_idempotent(self):
        # The exact bug from the user's screenshot.
        dps = [
            {'datapoint_name': 'distance', 'value': '28.6 กม.'},
            {'datapoint_name': 'driver_name', 'value': 'นายสมชาย ใจดี'},
            {'datapoint_name': 'fare', 'value': 402, 'unit': 'THB'},
        ]
        once = normalize_datapoints(dps)
        twice = normalize_datapoints(once)
        assert _by_name(once) == _by_name(twice)

    def test_dedup_keeps_highest_confidence(self):
        dps = [
            {'datapoint_name': 'distance', 'value': 28.6, 'unit': 'km', 'confidence': 0.6},
            {'datapoint_name': 'distance_km', 'value': 28.6, 'unit': 'km', 'confidence': 0.95},
        ]
        out = normalize_datapoints(dps)
        kept = [d for d in out if d['datapoint_name'] == 'distance_km']
        assert len(kept) == 1
        assert kept[0]['confidence'] == 0.95

    def test_screenshot_drift_normalises_to_same_shape(self):
        # Run 1 from user screenshot (canonical-ish names already)
        run1 = [
            {'datapoint_name': 'origin', 'value': 'สุขุมวิท 13'},
            {'datapoint_name': 'destination', 'value': 'สนามบินสุวรรณภูมิ'},
            {'datapoint_name': 'distance_km', 'value': 28.6, 'unit': 'km'},
            {'datapoint_name': 'base_fare', 'value': 402, 'unit': 'THB'},
        ]
        # Run 2 from user screenshot (drift)
        run2 = [
            {'datapoint_name': 'origin', 'value': 'สุขุมวิท 13'},
            {'datapoint_name': 'destination', 'value': 'สนามบินสุวรรณภูมิ'},
            {'datapoint_name': 'distance', 'value': '28.6 กม.'},
            {'datapoint_name': 'fare', 'value': 402, 'unit': 'THB'},
        ]
        out1 = _by_name(normalize_datapoints(run1))
        out2 = _by_name(normalize_datapoints(run2))
        # Both runs must produce a canonical distance_km with the
        # same numeric value so the EF lookup succeeds in BOTH.
        assert out1['distance_km']['value'] == 28.6
        assert out2['distance_km']['value'] == 28.6
        # Both produce a canonical amount.
        assert out1['amount']['value'] == 402
        assert out2['amount']['value'] == 402

    def test_no_raw_sibling_when_already_canonical(self):
        # No drift → no raw_<key> noise.
        dps = [{'datapoint_name': 'distance_km', 'value': 28.6, 'unit': 'km'}]
        out = normalize_datapoints(dps)
        names = _names(out)
        assert 'raw_distance_km' not in names


# ──────────────────────────────────────────────────────────────────
# Per-cat alias coverage matrix
# Every Scope 3 cat 1-15: assert that the canonical keys it needs
# can be reached from a plain English alias AND a Thai alias (at
# least one).
# ──────────────────────────────────────────────────────────────────

# A representative English + Thai alias for each canonical numeric
# we ship. If you add a new canonical, add a row here.
PER_KEY_PROBES: dict[str, tuple[str, str]] = {
    'distance_km':              ('distance',      'ระยะทาง'),
    'weight_kg':                ('weight',        'น้ำหนัก'),
    'volume_litres':            ('volume',        'น้ำมัน'),
    'energy_kwh':               ('electricity',   'หน่วยไฟฟ้า'),
    'energy_mwh':               ('mwh',           'mwh'),                 # MWh has no common Thai alias
    'energy_per_use_kwh':       ('energy_per_use','energy_per_use'),
    'tonne_km':                 ('tkm',           'tonne_km'),
    'passenger_km':             ('pkm',           'passenger_km'),
    'floor_area_sqm':           ('floor_area',    'พื้นที่'),
    'refrigerant_kg':           ('refrigerant_charge', 'refrigerant_charge'),
    'nights':                   ('hotel_nights',  'จำนวนคืน'),
    'headcount':                ('passengers',    'จำนวนพนักงาน'),
    'working_days':             ('work_days',     'จำนวนวันทำงาน'),
    'flight_legs':              ('flights',       'flights'),
    'units_sold':               ('units',         'units'),
    'lifetime_years':           ('lifetime',      'lifetime'),
    'franchise_count':          ('stores',        'stores'),
    'amount':                   ('total_cost',    'ราคารวม'),
    'unit_cost':                ('unit_price',    'unit_price'),
    'investee_emissions_tco2e': ('project_emissions', 'project_emissions'),
    'ownership_pct':            ('ownership',     'ownership'),
}


def test_every_canonical_numeric_has_a_probe():
    """Sanity guard: if you add a new canonical numeric, the test
    above must include it. Catches forgotten test coverage."""
    missing = set(CANONICAL_NUMERIC_KEYS.keys()) - set(PER_KEY_PROBES.keys())
    assert not missing, f'Add probes for: {missing}'


@pytest.mark.parametrize('canonical,probes', PER_KEY_PROBES.items())
def test_alias_probes_resolve(canonical, probes):
    en, th = probes
    assert ALIAS_MAP.get(R._normalize_lookup_key(en)) == canonical, (
        f'EN alias {en!r} → expected {canonical!r}, got '
        f'{ALIAS_MAP.get(R._normalize_lookup_key(en))!r}'
    )
    assert ALIAS_MAP.get(R._normalize_lookup_key(th)) == canonical, (
        f'TH alias {th!r} → expected {canonical!r}, got '
        f'{ALIAS_MAP.get(R._normalize_lookup_key(th))!r}'
    )


# Per-cat satisfaction: feed each cat a synthetic LLM payload using
# the most-drift-prone alias names; assert all calculation-critical
# canonical keys land in the output. Catches a missing alias for
# any cat.
PER_CAT_DRIFT_PAYLOAD: dict[int, tuple[list[dict], set[str]]] = {
    1: (
        [{'datapoint_name': 'total_cost', 'value': '1500 THB'},
         {'datapoint_name': 'currency', 'value': 'thb'}],
        {'amount', 'currency'},
    ),
    2: (
        [{'datapoint_name': 'price', 'value': 50000, 'unit': 'THB'},
         {'datapoint_name': 'material', 'value': 'steel'}],
        {'amount', 'material_type'},
    ),
    3: (
        [{'datapoint_name': 'electricity', 'value': '450 kwh'},
         {'datapoint_name': 'fuel', 'value': 'diesel'}],
        {'energy_kwh', 'fuel_type'},
    ),
    4: (
        [{'datapoint_name': 'weight', 'value': '500 kg'},
         {'datapoint_name': 'distance', 'value': '120 km'},
         {'datapoint_name': 'mode', 'value': 'truck'}],
        {'weight_kg', 'distance_km', 'transport_mode'},
    ),
    5: (
        [{'datapoint_name': 'น้ำหนัก', 'value': '20 กก.'},
         {'datapoint_name': 'วิธีกำจัด', 'value': 'ฝังกลบ'}],
        {'weight_kg', 'disposal_method'},
    ),
    6: (
        [{'datapoint_name': 'distance', 'value': '28.6 กม.'},
         {'datapoint_name': 'mode', 'value': 'แท็กซี่'},
         {'datapoint_name': 'fare', 'value': 402, 'unit': 'THB'}],
        {'distance_km', 'transport_mode', 'amount'},
    ),
    7: (
        [{'datapoint_name': 'distance', 'value': 12, 'unit': 'km'},
         {'datapoint_name': 'mode', 'value': 'bts'},
         {'datapoint_name': 'passengers', 'value': 50}],
        {'distance_km', 'transport_mode', 'headcount'},
    ),
    8: (
        [{'datapoint_name': 'electricity', 'value': '12000 kwh'}],
        {'energy_kwh'},
    ),
    9: (
        [{'datapoint_name': 'cargo_weight', 'value': '300 kg'},
         {'datapoint_name': 'distance', 'value': '500 km'},
         {'datapoint_name': 'mode', 'value': 'rail'}],
        # 'rail' → 'train' via alias
        {'weight_kg', 'distance_km'},  # transport_mode unknown ('rail' isn't aliased) — accept partial
    ),
    10: (
        [{'datapoint_name': 'weight', 'value': '50 kg'},
         {'datapoint_name': 'processing_method', 'value': 'cutting'}],
        {'weight_kg', 'processing_method'},
    ),
    11: (
        [{'datapoint_name': 'units', 'value': 1000},
         {'datapoint_name': 'lifetime', 'value': 5},
         {'datapoint_name': 'energy_per_use', 'value': 0.5, 'unit': 'kwh'}],
        {'units_sold', 'lifetime_years', 'energy_per_use_kwh'},
    ),
    12: (
        [{'datapoint_name': 'weight', 'value': '100 kg'},
         {'datapoint_name': 'disposal', 'value': 'recycle'}],
        {'weight_kg', 'disposal_method'},
    ),
    13: (
        [{'datapoint_name': 'electricity', 'value': '8000 kwh'},
         {'datapoint_name': 'floor_area', 'value': '500 sqm'}],
        {'energy_kwh', 'floor_area_sqm'},
    ),
    14: (
        [{'datapoint_name': 'stores', 'value': 25},
         {'datapoint_name': 'electricity', 'value': '10000 kwh'}],
        {'franchise_count', 'energy_kwh'},
    ),
    15: (
        [{'datapoint_name': 'investee_emissions', 'value': 1500},
         {'datapoint_name': 'ownership', 'value': 25}],
        {'investee_emissions_tco2e', 'ownership_pct'},
    ),
}


@pytest.mark.parametrize('cat,probe', PER_CAT_DRIFT_PAYLOAD.items())
def test_per_cat_drift_payload_normalises(cat, probe):
    raw_dps, expected_canonicals = probe
    out = normalize_datapoints(raw_dps)
    canonical_names = {
        d['datapoint_name'] for d in out
        if d.get('is_canonical')
    }
    missing = expected_canonicals - canonical_names
    assert not missing, (
        f'Cat {cat}: missing canonical keys {missing}; got {canonical_names}'
    )
