"""
Canonical datapoint-name registry + normaliser.

Single source of truth for every datapoint key the LLM extraction
pipeline is allowed to emit. The contract is:

  • Calculation-critical numerics (distance_km, weight_kg, …) have
    a CANONICAL key whose value is ALWAYS a number (no units in the
    `value` field) and whose unit is the registry-defined string.
  • The verbatim original literal that the LLM saw on the receipt
    is preserved in a `raw_<canonical>` sibling row, so audits can
    always trace back to the source phrasing.
  • Categorical companions (currency, transport_mode, …) have a
    closed-vocabulary normalised string value.
  • Anything that doesn't match the registry passes through
    unchanged — those are descriptive datapoints (vendor names,
    document numbers, etc.) that don't drive the GHG calculation.

The same module is used in two places:

  1. `EsgImageExtractionService` / `EsgExtractionService` —
     pre-persist normalisation of every LLM JSON before writing
     `esg_records.datapoints`.
  2. Migration 065 — one-shot heal of every existing row in the
     `esg_records` table; idempotent, safe to re-run.

DO NOT add database calls or ORM imports here. This module must
stay pure-Python so unit tests run without a DB and the migration
can import it without circular dependencies.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


# ============================================================
# CANONICAL NUMERIC KEYS
# value is ALWAYS a number; unit is the canonical unit string;
# raw_<key> sibling carries the verbatim original literal.
# ============================================================
CANONICAL_NUMERIC_KEYS: dict[str, Optional[str]] = {
    # ── Activity quantities ──────────────────────────────────
    'distance_km':              'km',           # Cat 4, 6, 7, 9
    'passenger_km':             'passenger-km', # Cat 7 (alt to distance×headcount)
    'tonne_km':                 'tonne-km',     # Cat 4, 9 (alt to weight×distance)
    'weight_kg':                'kg',           # Cat 4, 5, 9, 10, 12
    'volume_litres':            'litre',        # Cat 3, 4, 7, 8, 10, 11, 13
    'energy_kwh':               'kwh',          # Cat 3, 8, 10, 11, 13, 14
    'energy_mwh':               'mwh',          # Cat 3 (large org)
    'energy_per_use_kwh':       'kwh',          # Cat 11 — per-unit lifetime use
    'floor_area_sqm':           'sqm',          # Cat 8, 13, 14
    'refrigerant_kg':           'kg',           # Cat 11
    # ── Counts ───────────────────────────────────────────────
    'nights':                   'nights',       # Cat 6
    'headcount':                'persons',      # Cat 6, 7
    'working_days':             'days',         # Cat 7
    'flight_legs':              'count',        # Cat 6
    'units_sold':               'count',        # Cat 11, 12
    'lifetime_years':           'years',        # Cat 11
    'franchise_count':          'count',        # Cat 14
    # ── Money / financial ────────────────────────────────────
    'amount':                   None,           # money — needs `currency`
    'unit_cost':                None,           # money/unit — needs `currency`
    'investee_emissions_tco2e': 'tco2e',        # Cat 15
    'ownership_pct':            'percent',      # Cat 15 (0-100)
}


# ============================================================
# CANONICAL CATEGORICAL KEYS — closed-vocabulary string values.
# value is normalised to lowercase ASCII; the registry's allowed
# set drives EF lookup downstream.
# ============================================================
CANONICAL_CATEGORICAL_KEYS: dict[str, set[str]] = {
    'currency':         {'THB','USD','EUR','JPY','GBP','SGD','CNY','MYR','VND','IDR','AUD','NZD','HKD','INR'},
    'transport_mode':   {'taxi','car','motorbike','flight','train','bus','ship','truck','van','bicycle','walk','other'},
    'flight_class':     {'economy','premium_economy','business','first'},
    'fuel_type':        {'diesel','petrol','lpg','cng','biogas','jet_fuel','marine_diesel','heavy_oil','coal','natural_gas','biomass','electric','hybrid'},
    'disposal_method':  {'landfill','recycle','incinerate','compost','anaerobic_digestion','reuse','open_burning','energy_recovery','open_dump'},
    'material_type':    {'paper','plastic','metal','aluminum','steel','glass','wood','organic','textile','electronics','mixed','hazardous','concrete','rubber'},
    'waste_type':       {'msw','industrial','hazardous','organic','recyclable','construction','medical','electronic','sludge'},
    'processing_method':{'machining','assembly','heat_treatment','coating','packaging','cutting','welding','molding','printing'},
    'asset_type':       {'building','vehicle','machinery','it_equipment','furniture','land','aircraft','ship'},
    'refrigerant_type': {'r22','r32','r134a','r404a','r410a','r407c','r600a','co2','ammonia','hfc_blend'},
    'country':          set(),       # ISO-3166 alpha-2 — open set, validated downstream
    'investment_type':  {'equity','debt','project_finance','managed_fund'},
}


# Aliases for categorical *values* (the right-hand side). Keys are
# the case-folded incoming string; values are the normalised entry
# from the controlled vocab. Currency is uppercased separately.
CATEGORICAL_VALUE_ALIASES: dict[str, dict[str, str]] = {
    'transport_mode': {
        'แท็กซี่': 'taxi', 'taxi cab': 'taxi', 'cab': 'taxi',
        'private car': 'car', 'sedan': 'car', 'รถยนต์': 'car',
        'รถจักรยานยนต์': 'motorbike', 'มอเตอร์ไซค์': 'motorbike', 'motorcycle': 'motorbike',
        'plane': 'flight', 'airplane': 'flight', 'เครื่องบิน': 'flight',
        'รถไฟ': 'train', 'mrt': 'train', 'bts': 'train', 'subway': 'train',
        'รถบัส': 'bus', 'รถเมล์': 'bus', 'coach': 'bus',
        'lorry': 'truck', 'รถบรรทุก': 'truck', 'pickup': 'truck',
        'minibus': 'van', 'รถตู้': 'van',
        'bike': 'bicycle', 'จักรยาน': 'bicycle', 'cycling': 'bicycle',
        'foot': 'walk', 'walking': 'walk', 'เดิน': 'walk',
        'vessel': 'ship', 'boat': 'ship', 'เรือ': 'ship',
    },
    'flight_class': {
        'eco': 'economy', 'y': 'economy', 'coach': 'economy',
        'premium': 'premium_economy', 'pe': 'premium_economy',
        'biz': 'business', 'j': 'business',
        'f': 'first',
    },
    'fuel_type': {
        'gasoline': 'petrol', 'gas': 'petrol', 'unleaded': 'petrol',
        'jet a': 'jet_fuel', 'jet-a': 'jet_fuel', 'aviation fuel': 'jet_fuel',
        'natural-gas': 'natural_gas', 'ng': 'natural_gas',
    },
    'disposal_method': {
        'dump': 'landfill', 'open dump': 'open_dump',
        'recycling': 'recycle', 'recycled': 'recycle',
        'incineration': 'incinerate', 'incineration with energy': 'energy_recovery',
        'composting': 'compost',
        'reuse': 'reuse', 'reused': 'reuse',
        'ฝังกลบ': 'landfill', 'รีไซเคิล': 'recycle', 'เผา': 'incinerate', 'หมัก': 'compost',
    },
    'material_type': {
        'pet': 'plastic', 'pp': 'plastic', 'pe': 'plastic', 'hdpe': 'plastic', 'ldpe': 'plastic',
        'cardboard': 'paper', 'corrugated': 'paper', 'newspaper': 'paper',
        'al': 'aluminum', 'alu': 'aluminum',
        'fe': 'steel', 'iron': 'steel',
        'food': 'organic', 'food waste': 'organic',
        'fabric': 'textile', 'cloth': 'textile',
        'e-waste': 'electronics', 'ewaste': 'electronics',
    },
    'waste_type': {
        'general': 'msw', 'general waste': 'msw', 'household': 'msw',
        'food waste': 'organic', 'biowaste': 'organic',
        'mixed recyclable': 'recyclable', 'recyclables': 'recyclable',
    },
}


# ============================================================
# ALIAS MAP (datapoint_name → canonical key)
# Bilingual, case-insensitive, whitespace-collapsed lookups.
# ============================================================
ALIAS_MAP: dict[str, str] = {
    # ── distance_km ──
    'distance': 'distance_km', 'distance_in_km': 'distance_km',
    'distance (km)': 'distance_km', 'distance_km': 'distance_km',
    'travel_distance': 'distance_km', 'travel distance': 'distance_km',
    'one_way_distance': 'distance_km', 'one way distance': 'distance_km',
    'mileage': 'distance_km', 'kilometers': 'distance_km',
    'kilometres': 'distance_km',
    'ระยะทาง': 'distance_km', 'ระยะทางการเดินทาง': 'distance_km',
    'ระยะทางเดินทาง': 'distance_km',

    # ── passenger_km ──
    'passenger_km': 'passenger_km', 'pkm': 'passenger_km',
    'pax_km': 'passenger_km', 'passenger-km': 'passenger_km',

    # ── tonne_km ──
    'tonne_km': 'tonne_km', 'tkm': 'tonne_km', 'ton_km': 'tonne_km',
    't_km': 'tonne_km', 'tonne-km': 'tonne_km',
    'tonne_kilometre': 'tonne_km',

    # ── weight_kg ──
    'weight': 'weight_kg', 'weight_kg': 'weight_kg',
    'weight (kg)': 'weight_kg', 'mass': 'weight_kg',
    'cargo_weight': 'weight_kg', 'cargo weight': 'weight_kg',
    'waste_weight': 'weight_kg', 'waste weight': 'weight_kg',
    'product_weight': 'weight_kg', 'asset_weight': 'weight_kg',
    'น้ำหนัก': 'weight_kg', 'น้ำหนักสินค้า': 'weight_kg',
    'น้ำหนักของเสีย': 'weight_kg',

    # ── volume_litres ──
    'volume': 'volume_litres', 'volume_litres': 'volume_litres',
    'litre': 'volume_litres', 'litres': 'volume_litres',
    'liters': 'volume_litres', 'liter': 'volume_litres',
    'fuel_volume': 'volume_litres', 'fuel_quantity': 'volume_litres',
    'ปริมาตร': 'volume_litres', 'น้ำมัน': 'volume_litres',
    'ปริมาณน้ำมัน': 'volume_litres',

    # ── energy_kwh / energy_mwh ──
    'energy': 'energy_kwh', 'energy_kwh': 'energy_kwh',
    'kwh': 'energy_kwh', 'kwh_consumed': 'energy_kwh',
    'electricity': 'energy_kwh', 'electricity_consumed': 'energy_kwh',
    'energy_consumption': 'energy_kwh', 'energy_consumed': 'energy_kwh',
    'หน่วยไฟฟ้า': 'energy_kwh', 'ไฟฟ้าที่ใช้': 'energy_kwh',
    'ค่าไฟ': 'energy_kwh', 'พลังงาน': 'energy_kwh',
    'พลังงานที่ใช้': 'energy_kwh',
    'mwh': 'energy_mwh', 'energy_mwh': 'energy_mwh',
    'megawatt_hours': 'energy_mwh',

    # ── energy_per_use_kwh ──
    'energy_per_use': 'energy_per_use_kwh',
    'energy_per_unit': 'energy_per_use_kwh',
    'kwh_per_use': 'energy_per_use_kwh',

    # ── floor_area_sqm ──
    'floor_area': 'floor_area_sqm', 'floor_area_sqm': 'floor_area_sqm',
    'area': 'floor_area_sqm', 'building_area': 'floor_area_sqm',
    'sqm': 'floor_area_sqm', 'square_metres': 'floor_area_sqm',
    'พื้นที่': 'floor_area_sqm', 'พื้นที่อาคาร': 'floor_area_sqm',

    # ── refrigerant_kg ──
    'refrigerant_kg': 'refrigerant_kg',
    'refrigerant_charge': 'refrigerant_kg',
    'refrigerant_amount': 'refrigerant_kg',

    # ── nights ──
    'nights': 'nights', 'hotel_nights': 'nights',
    'room_nights': 'nights', 'night': 'nights',
    'จำนวนคืน': 'nights', 'คืนพัก': 'nights',
    'จำนวนคืนที่พัก': 'nights',

    # ── headcount ──
    'headcount': 'headcount', 'persons': 'headcount',
    'people': 'headcount', 'employees': 'headcount',
    'passengers': 'headcount', 'num_passengers': 'headcount',
    'จำนวนคน': 'headcount', 'จำนวนพนักงาน': 'headcount',
    'จำนวนผู้โดยสาร': 'headcount',

    # ── working_days ──
    'working_days': 'working_days', 'work_days': 'working_days',
    'business_days': 'working_days', 'commute_days': 'working_days',
    'จำนวนวันทำงาน': 'working_days',

    # ── flight_legs ──
    'flight_legs': 'flight_legs', 'flights': 'flight_legs',
    'segments': 'flight_legs', 'flight_segments': 'flight_legs',
    'num_flights': 'flight_legs', 'num_segments': 'flight_legs',

    # ── units_sold / lifetime_years ──
    'units_sold': 'units_sold', 'units': 'units_sold',
    'quantity_sold': 'units_sold', 'sales_quantity': 'units_sold',
    'lifetime_years': 'lifetime_years', 'lifetime': 'lifetime_years',
    'product_lifetime': 'lifetime_years',
    'expected_life_years': 'lifetime_years',

    # ── franchise_count ──
    'franchise_count': 'franchise_count',
    'stores': 'franchise_count', 'num_stores': 'franchise_count',
    'franchisees': 'franchise_count', 'outlets': 'franchise_count',

    # ── ownership_pct ──
    'ownership_pct': 'ownership_pct', 'ownership': 'ownership_pct',
    'equity_share': 'ownership_pct', 'stake': 'ownership_pct',
    'shareholding': 'ownership_pct',

    # ── investee_emissions_tco2e ──
    'investee_emissions_tco2e': 'investee_emissions_tco2e',
    'investee_emissions': 'investee_emissions_tco2e',
    'project_emissions': 'investee_emissions_tco2e',

    # ── amount (money) ──
    'amount': 'amount', 'fare': 'amount', 'base_fare': 'amount',
    'total_fare': 'amount', 'total_cost': 'amount',
    'total_amount': 'amount', 'total_price': 'amount',
    'price': 'amount', 'cost': 'amount', 'spend': 'amount',
    'invoice_total': 'amount', 'grand_total': 'amount',
    'ราคา': 'amount', 'ราคารวม': 'amount', 'มูลค่ารวม': 'amount',
    'ยอดรวม': 'amount', 'ค่าบริการ': 'amount', 'ราคาทั้งหมด': 'amount',

    # ── unit_cost ──
    'unit_cost': 'unit_cost', 'unit_price': 'unit_cost',
    'rate': 'unit_cost', 'rate_per_unit': 'unit_cost',
    'price_per_unit': 'unit_cost',

    # ── categorical aliases (datapoint_name → categorical key) ──
    'mode': 'transport_mode', 'travel_mode': 'transport_mode',
    'transport_mode': 'transport_mode',
    'รูปแบบ': 'transport_mode', 'รูปแบบการเดินทาง': 'transport_mode',
    'class': 'flight_class', 'cabin': 'flight_class',
    'flight_class': 'flight_class',
    'ชั้นโดยสาร': 'flight_class',
    'fuel': 'fuel_type', 'fuel_kind': 'fuel_type',
    'fuel_type': 'fuel_type',
    'ประเภทเชื้อเพลิง': 'fuel_type',
    'disposal': 'disposal_method', 'waste_treatment': 'disposal_method',
    'disposal_method': 'disposal_method',
    'วิธีกำจัด': 'disposal_method',
    'material': 'material_type', 'commodity': 'material_type',
    'material_type': 'material_type',
    'ประเภทวัสดุ': 'material_type',
    'waste_stream': 'waste_type', 'waste_type': 'waste_type',
    'ประเภทขยะ': 'waste_type',
    'processing_method': 'processing_method',
    'asset_type': 'asset_type',
    'refrigerant_type': 'refrigerant_type', 'refrigerant': 'refrigerant_type',
    'country': 'country', 'country_code': 'country',
    'investment_type': 'investment_type',
    'curr': 'currency', 'currency': 'currency',
    'currency_code': 'currency',
    'สกุลเงิน': 'currency',
}


# ============================================================
# UNIT CONVERTERS — multiplier from (raw_unit → canonical_unit)
# ============================================================
UNIT_CONVERTERS: dict[tuple[str, str], float] = {
    # distance → km
    ('mile','km'): 1.609344, ('miles','km'): 1.609344,
    ('mi','km'): 1.609344,
    ('m','km'): 0.001, ('meter','km'): 0.001, ('metre','km'): 0.001,
    ('meters','km'): 0.001, ('metres','km'): 0.001,
    ('yard','km'): 0.0009144, ('yd','km'): 0.0009144,
    ('foot','km'): 0.0003048, ('ft','km'): 0.0003048,
    # weight → kg
    ('lb','kg'): 0.45359237, ('lbs','kg'): 0.45359237,
    ('pound','kg'): 0.45359237, ('pounds','kg'): 0.45359237,
    ('tonne','kg'): 1000.0, ('tonnes','kg'): 1000.0,
    ('ton','kg'): 1000.0, ('tons','kg'): 1000.0, ('t','kg'): 1000.0,
    ('mt','kg'): 1000.0, ('metric_ton','kg'): 1000.0,
    ('g','kg'): 0.001, ('gram','kg'): 0.001, ('grams','kg'): 0.001,
    # volume → litre
    ('gallon','litre'): 3.78541, ('gallons','litre'): 3.78541,
    ('gal','litre'): 3.78541,
    ('uk_gallon','litre'): 4.54609,
    ('ml','litre'): 0.001, ('millilitre','litre'): 0.001,
    ('cubic_metre','litre'): 1000.0, ('m3','litre'): 1000.0,
    ('cubic meters','litre'): 1000.0,
    # energy → kwh
    ('mwh','kwh'): 1000.0, ('gwh','kwh'): 1_000_000.0,
    ('gj','kwh'): 277.778, ('mj','kwh'): 0.277778,
    ('btu','kwh'): 0.000293071, ('mmbtu','kwh'): 293.071,
    ('therm','kwh'): 29.3001,
    # area → sqm
    ('sqft','sqm'): 0.092903, ('ft2','sqm'): 0.092903,
    ('square_feet','sqm'): 0.092903, ('square_foot','sqm'): 0.092903,
    ('rai','sqm'): 1600.0,                  # Thai unit of area
    ('ngan','sqm'): 400.0,
    ('square_wa','sqm'): 4.0,
}


# ============================================================
# Helpers
# ============================================================

# Match a leading number (int or float, possibly with thousands sep
# or sign) followed by an optional unit token. Used to peel
# "28.6 km" or "1,200 baht" or "28,6 กม." apart.
_NUM_UNIT_RE = re.compile(
    r'^\s*([+-]?\d{1,3}(?:[,\s]\d{3})*(?:[.,]\d+)?|\d+(?:[.,]\d+)?)'
    r'\s*([^\d\s].*)?$'
)


def _normalize_lookup_key(s: str) -> str:
    """Lowercase + collapse whitespace + strip — used to look up an
    incoming `datapoint_name` against ALIAS_MAP."""
    if not s:
        return ''
    return re.sub(r'\s+', ' ', str(s).strip().lower())


def _normalize_unit(unit: str) -> str:
    """Canonicalise a unit string (lowercase, strip, common aliases)."""
    if not unit:
        return ''
    u = re.sub(r'\s+', ' ', str(unit).strip().lower())
    aliases = {
        'liter': 'litre', 'liters': 'litre', 'litres': 'litre',
        'kgs': 'kg', 'kilograms': 'kg', 'kilogram': 'kg',
        'kilometer': 'km', 'kilometers': 'km', 'kms': 'km',
        'kilometre': 'km', 'kilometres': 'km',
        'กม.': 'km', 'กม': 'km', 'กิโลเมตร': 'km',
        'กก.': 'kg', 'กก': 'kg', 'กิโล': 'kg', 'กิโลกรัม': 'kg',
        'ลิตร': 'litre',
        'mile': 'mile', 'miles': 'mile',
        'sq m': 'sqm', 'm²': 'sqm', 'm2': 'sqm', 'square metre': 'sqm',
        'tkm': 'tonne-km', 't-km': 'tonne-km', 't.km': 'tonne-km',
        'pkm': 'passenger-km', 'p-km': 'passenger-km',
        'kilowatt-hour': 'kwh', 'kilowatt hour': 'kwh', 'kw-h': 'kwh',
        'baht': 'thb', '฿': 'thb', 'usd$': 'usd', '$': 'usd',
    }
    return aliases.get(u, u)


def parse_numeric_with_unit(
    raw_value: Any,
    raw_unit: Any = None,
) -> tuple[Optional[float], Optional[str], str]:
    """
    Tease a numeric magnitude + unit out of an LLM-emitted value.

    Handles three shapes:
      • value=28.6, unit='km'         → (28.6, 'km', '28.6 km')
      • value='28.6 km', unit=None    → (28.6, 'km', '28.6 km')
      • value='28.6', unit='กม.'      → (28.6, 'km', '28.6 km')

    Returns `(numeric_or_None, unit_or_None, raw_string)`. The
    `raw_string` always reflects what was in the input
    (`f'{value} {unit}'` if both, else whichever was given) so the
    caller can preserve it as `raw_<key>`.
    """
    raw_str = ''
    num: Optional[float] = None
    unit: Optional[str] = None

    if isinstance(raw_value, (int, float)):
        num = float(raw_value)
        raw_str = str(raw_value)
        if raw_unit:
            raw_str = f'{raw_value} {raw_unit}'
        unit = _normalize_unit(str(raw_unit or '')) or None
    elif isinstance(raw_value, str):
        raw_str = raw_value
        s = raw_value.strip()
        if not s:
            return None, _normalize_unit(str(raw_unit or '')) or None, raw_str
        m = _NUM_UNIT_RE.match(s)
        if m:
            num_str = m.group(1).replace(',', '').replace(' ', '')
            try:
                num = float(num_str)
            except ValueError:
                num = None
            tail = (m.group(2) or '').strip()
            if tail:
                unit = _normalize_unit(tail)
        # If the parser failed, fall through with unit from raw_unit.
        if unit is None and raw_unit:
            unit = _normalize_unit(str(raw_unit))
    else:
        # Booleans / None / lists etc. — un-parseable as a number.
        raw_str = str(raw_value) if raw_value is not None else ''
        unit = _normalize_unit(str(raw_unit or '')) or None
    return num, unit, raw_str


def _convert_to_canonical_unit(
    value: float, raw_unit: Optional[str], canonical_unit: Optional[str],
) -> Optional[float]:
    """
    Convert a numeric value from `raw_unit` to `canonical_unit`. If
    units already match (or `canonical_unit` is None), return as-is.
    Returns None when conversion isn't possible — caller decides
    whether to skip the canonical row or use the raw value at face
    value.
    """
    if canonical_unit is None:
        return value
    if not raw_unit or raw_unit == canonical_unit:
        return value
    factor = UNIT_CONVERTERS.get((raw_unit, canonical_unit))
    if factor is None:
        # Some units share a canonical (e.g. 'kwh' for both 'kwh' and
        # 'kilowatt-hour'). _normalize_unit collapses these. If we
        # still don't know, refuse to silently mis-convert.
        return None
    return round(value * factor, 6)


def _normalise_categorical(
    canonical_key: str, value: Any,
) -> Optional[str]:
    """
    Map an arbitrary string into the canonical vocabulary for
    `canonical_key`. Currency values uppercase; everything else
    lowercases and matches against `CATEGORICAL_VALUE_ALIASES` then
    the canonical set.
    Returns None when we can't normalise (caller keeps the raw
    string but doesn't claim it's canonical).
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    if canonical_key == 'currency':
        return raw.upper()
    s = raw.lower()
    aliases = CATEGORICAL_VALUE_ALIASES.get(canonical_key, {})
    if s in aliases:
        return aliases[s]
    allowed = CANONICAL_CATEGORICAL_KEYS.get(canonical_key)
    if allowed is None:
        return s   # open-set categorical (e.g. country) — accept as-is
    if not allowed:
        return s
    if s in allowed:
        return s
    return None


# ============================================================
# Public API
# ============================================================

def normalize_datapoint(
    dp: dict,
) -> list[dict]:
    """
    Normalise a single LLM-emitted datapoint into 1-2 rows:
      [canonical_row, raw_<key>_row?]

    Always returns a list. For descriptive datapoints (no canonical
    match), returns the original row unchanged in a single-element
    list. For canonical numerics, also emits a `raw_<key>` sibling
    that preserves the original literal.

    Idempotent: a row that's already canonical (correct name,
    numeric value, sane unit) round-trips unchanged.
    """
    if not isinstance(dp, dict):
        return [dp] if dp else []

    name = dp.get('datapoint_name', '')
    lookup = _normalize_lookup_key(name)

    # Pass-through for already-`raw_*` rows — never touch them.
    if lookup.startswith('raw_'):
        return [dp]

    canonical = ALIAS_MAP.get(lookup)
    if canonical is None:
        # Descriptive datapoint — pass through unchanged.
        return [dp]

    # ── CASE A: canonical NUMERIC key ────────────────────────
    if canonical in CANONICAL_NUMERIC_KEYS:
        canonical_unit = CANONICAL_NUMERIC_KEYS[canonical]
        num, parsed_unit, raw_str = parse_numeric_with_unit(
            dp.get('value'), dp.get('unit'),
        )
        # No numeric value found → emit only the raw_<key> sibling
        # so the platform records the LLM saw the field but couldn't
        # parse it. Calculation will treat the record as missing.
        if num is None:
            raw_row = {
                **{k: v for k, v in dp.items() if k not in (
                    'datapoint_name', 'canonical_name', 'is_canonical',
                )},
                'datapoint_name': f'raw_{canonical}',
                'canonical_name': None,
                'is_canonical': False,
                'value': raw_str if raw_str else dp.get('value'),
            }
            return [raw_row]

        # Convert raw_unit → canonical_unit when we know the
        # conversion (miles→km, lbs→kg, etc.). If the unit is
        # already canonical (or there's no canonical unit, e.g.
        # `amount`), keep the value as-is.
        final_unit: Optional[str] = canonical_unit or parsed_unit
        final_value: float = num
        if canonical_unit and parsed_unit and parsed_unit != canonical_unit:
            converted = _convert_to_canonical_unit(num, parsed_unit, canonical_unit)
            if converted is None:
                # Unknown conversion — keep numeric but flag it
                # came in a non-canonical unit by leaving raw_str
                # in raw_<key>. The carbon service will reject this
                # row (unit mismatch) and the record stays
                # insufficient until the user clarifies.
                logger.warning(
                    "[registry] no conversion for %r → %r; keeping raw value",
                    parsed_unit, canonical_unit,
                )
                final_unit = canonical_unit  # claim canonical so EF lookup at least tries
            else:
                final_value = converted

        canonical_row: dict[str, Any] = {
            **{k: v for k, v in dp.items() if k not in (
                'datapoint_name', 'canonical_name', 'is_canonical',
                'value', 'unit',
            )},
            'datapoint_name': canonical,
            'canonical_name': canonical,
            'is_canonical': True,
            'value': final_value,
            'unit': final_unit,
        }

        # Emit the raw_<key> sibling only when the original looked
        # different from the canonical (otherwise it's noise).
        result: list[dict] = [canonical_row]
        original_looked_different = (
            lookup != canonical
            or isinstance(dp.get('value'), str)
            or (parsed_unit and parsed_unit != canonical_unit)
        )
        if original_looked_different and raw_str:
            raw_row = {
                'datapoint_name': f'raw_{canonical}',
                'canonical_name': None,
                'is_canonical': False,
                'value': raw_str,
                'confidence': dp.get('confidence'),
                'tags': list(dp.get('tags') or []),
            }
            # Drop None values so we keep the JSON tidy.
            raw_row = {k: v for k, v in raw_row.items() if v is not None}
            result.append(raw_row)
        return result

    # ── CASE B: canonical CATEGORICAL key ────────────────────
    if canonical in CANONICAL_CATEGORICAL_KEYS:
        normalised = _normalise_categorical(canonical, dp.get('value'))
        if normalised is None:
            # Couldn't fit the controlled vocab — keep as descriptive
            # row so we don't drop information. Calculation will
            # ignore it.
            return [{
                **dp,
                'datapoint_name': canonical,
                'canonical_name': canonical,
                'is_canonical': False,
            }]
        return [{
            **{k: v for k, v in dp.items() if k not in (
                'datapoint_name', 'canonical_name', 'is_canonical', 'value',
            )},
            'datapoint_name': canonical,
            'canonical_name': canonical,
            'is_canonical': True,
            'value': normalised,
        }]

    # Unknown canonical bucket — defensive fallback.
    return [dp]


def normalize_datapoints(dp_list: Iterable[dict]) -> list[dict]:
    """
    Walk a datapoints array and run `normalize_datapoint` on each
    entry. Dedupes canonical numeric rows (highest-confidence wins,
    `raw_<key>` siblings are preserved verbatim).

    Idempotent: `normalize_datapoints(normalize_datapoints(x))` ==
    `normalize_datapoints(x)` for any input `x`.
    """
    if not dp_list:
        return []

    expanded: list[dict] = []
    for dp in dp_list:
        expanded.extend(normalize_datapoint(dp))

    # Dedup canonical numeric rows. Keep the highest-confidence one;
    # merge tags. raw_<key> siblings are NOT deduped (different
    # sources may carry different literals).
    by_canonical: dict[str, dict] = {}
    other_rows: list[dict] = []
    for row in expanded:
        name = row.get('datapoint_name')
        is_canonical = bool(row.get('is_canonical'))
        if (
            is_canonical
            and name in CANONICAL_NUMERIC_KEYS
            and isinstance(row.get('value'), (int, float))
        ):
            existing = by_canonical.get(name)
            if existing is None:
                by_canonical[name] = row
            else:
                ec = existing.get('confidence') or 0
                rc = row.get('confidence') or 0
                winner = row if rc > ec else existing
                merged_tags = list({
                    *(existing.get('tags') or []),
                    *(row.get('tags') or []),
                })
                winner = {**winner}
                if merged_tags:
                    winner['tags'] = merged_tags
                by_canonical[name] = winner
        else:
            other_rows.append(row)
    return list(by_canonical.values()) + other_rows
