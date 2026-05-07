"""
ESG Carbon Service — tCO2e calculation using emission factors.

Lookup order on calculate_tco2e:
  1. Exact match on EmissionFactor (category + unit, optionally + sub + fuel)
  2. Fuzzy match on EmissionFactor (category contains + unit)
  3. **NEW** Scope 3 category-id fallback — if the entry's category resolves
     to a known Scope 3 category id (1..15), apply a conservative default
     EF from `SCOPE3_FALLBACK_EFS`. This prevents the dashboard showing
     0 tCO2e for every uploaded receipt while emission_factors is being
     seeded. The fallback is flagged in `data_quality` so users know it's
     a default estimate, not a verified factor.
"""

from decimal import Decimal
from typing import Optional, Tuple
import logging
from sqlalchemy.orm import Session

from ...models.esg.emission_factors import EmissionFactor
from ...models.esg.data_hierarchy import EsgDataCategory

logger = logging.getLogger(__name__)


# Conservative default EFs per Scope 3 category, by unit.
# Sources: GHG Protocol guidance + DEFRA + TGO Thailand averages, simplified
# to a single round number per unit so we always have *something* to show.
# These are intentionally conservative ("good enough for a screen") and
# should be replaced by org-specific factors via the `emission_factors`
# table once the team seeds them.
#
# Format: { scope3_category_id: { normalized_unit: kgCO2e_per_unit } }
# All factors are in kgCO2e per unit; we divide by 1000 at the end.
SCOPE3_FALLBACK_EFS = {
    1:  {  # Purchased goods and services — spend-based
        'thb': 0.5, 'usd': 18.0,
        'kg': 2.5, 'tonne': 2500.0, 'unit': 5.0, 'piece': 5.0,
    },
    2:  {  # Capital goods — spend-based capex
        'thb': 0.4, 'usd': 14.0,
        'kg': 3.0, 'tonne': 3000.0,
    },
    3:  {  # Fuel- and energy-related (well-to-tank)
        'kwh': 0.06, 'mwh': 60.0,
        'litre': 0.6, 'l': 0.6, 'gallon': 2.3,
        'kg': 0.4,
    },
    4:  {  # Upstream transportation
        'tonne-km': 0.062, 'kg-km': 0.000062, 'tkm': 0.062,
        'km': 0.062, 'thb': 0.3,
    },
    5:  {  # Waste in operations
        'kg': 0.45, 'tonne': 450.0,
        'litre': 0.6, 'l': 0.6,
        'thb': 0.3,
    },
    6:  {  # Business travel
        'km': 0.18, 'mile': 0.29,
        'thb': 0.4, 'usd': 14.0,
        'flight': 250.0, 'night': 25.0,
    },
    7:  {  # Employee commuting
        'km': 0.18, 'passenger-km': 0.18, 'pkm': 0.18,
        'thb': 0.35,
    },
    8:  {  # Upstream leased assets
        'kwh': 0.5, 'sqm': 90.0, 'm2': 90.0,
        'thb': 0.3,
    },
    9:  {  # Downstream transport
        'tonne-km': 0.07, 'kg-km': 0.00007, 'tkm': 0.07, 'km': 0.07,
    },
    10: {  # Processing of sold
        'kg': 1.5, 'tonne': 1500.0, 'thb': 0.4,
    },
    11: {  # Use of sold products
        'kwh': 0.5, 'mwh': 500.0,
        'litre': 2.3, 'l': 2.3,
        'unit-year': 200.0, 'unit': 200.0,
    },
    12: {  # End-of-life
        'kg': 0.4, 'tonne': 400.0,
        'unit': 0.5, 'piece': 0.5,
    },
    13: {  # Downstream leased
        'kwh': 0.5, 'sqm': 90.0, 'm2': 90.0,
    },
    14: {  # Franchises
        'kwh': 0.5, 'thb': 0.3, 'store-year': 12000.0,
    },
    15: {  # Investments
        'thb': 0.2, 'usd': 7.0,
    },
}


# Currency units. When a record's only quantitative datapoint uses a
# currency, the spend-based EF is a *very rough* proxy and we record
# that explicitly via `ghg_method='spend_based'` so the user can see
# how the number was derived (and choose to upgrade with activity data).
CURRENCY_UNITS = {
    'thb', 'baht', '฿',
    'usd', '$', 'usd$', 'us$',
    'eur', '€', 'gbp', '£', 'jpy', '¥',
    'cny', 'rmb', 'sgd', 'sg$', 'hkd', 'hk$',
    'aud', 'krw', 'inr', 'rs', 'idr', 'rp',
    'vnd', '₫', 'php', '₱', 'myr', 'rm',
}

# What activity-data is required to compute a real (non-spend-based)
# kgCO2e for each Scope 3 category. The first list of any tuple that
# is fully satisfied = sufficient. Values are normalized field names
# (lower, snake-style) checked against the LLM-emitted `datapoint_name`.
SCOPE3_REQUIRED_FIELDS = {
    1:  [],                                 # spend-based legitimate
    2:  [],                                 # spend-based legitimate
    3:  [['kwh'], ['mwh'], ['litre']],
    4:  [['weight', 'distance'], ['tonne_km'], ['tkm']],
    5:  [['weight'], ['mass'], ['kg']],
    6:  [['distance'], ['nights'], ['flight_legs', 'class'], ['flight']],
    7:  [['distance'], ['passenger_km']],
    8:  [['kwh'], ['floor_area']],
    9:  [['weight', 'distance'], ['tonne_km']],
    10: [['weight']],
    11: [['kwh'], ['litre'], ['unit_year']],
    12: [['weight']],
    13: [['kwh'], ['floor_area']],
    14: [['kwh'], ['stores']],              # franchises spend-based fallback
    15: [],                                 # spend-based legitimate (financed)
}


def _normalize_unit(unit: str) -> str:
    if not unit:
        return ''
    u = unit.strip().lower()
    # collapse common variants
    aliases = {
        'liter': 'litre', 'liters': 'litre', 'litres': 'litre',
        'kgs': 'kg', 'kilograms': 'kg', 'kilogram': 'kg',
        'tonnes': 'tonne', 'tons': 'tonne', 'ton': 'tonne', 't': 'tonne',
        'units': 'unit', 'pcs': 'piece', 'pieces': 'piece',
        'baht': 'thb', '฿': 'thb',
        'usd$': 'usd', '$': 'usd',
        'mile': 'mile', 'miles': 'mile',
        'kilometer': 'km', 'kilometers': 'km', 'kms': 'km',
        'sqm': 'sqm', 'sq m': 'sqm', 'm²': 'sqm', 'square metre': 'sqm',
        'tkm': 'tonne-km', 't-km': 'tonne-km', 't.km': 'tonne-km',
        'pkm': 'passenger-km', 'p-km': 'passenger-km',
        'kilowatt-hour': 'kwh', 'kilowatt hour': 'kwh', 'kw-h': 'kwh',
    }
    return aliases.get(u, u)


def _is_currency_unit(unit: str) -> bool:
    return _normalize_unit(unit) in CURRENCY_UNITS


# When the LLM forgets to set `unit` (or sets it to a label like
# "distance"), we infer the canonical unit from the datapoint_name /
# tags. This fills in the gap that was making evaluate_record_ghg
# declare records insufficient even when distance/weight/kWh was
# clearly extracted (just the unit field was empty).
_NAME_TO_UNIT = {
    # distance
    'distance': 'km', 'travel distance': 'km', 'travel_distance': 'km',
    'distance km': 'km', 'distance_km': 'km',
    'kilometer': 'km', 'kilometers': 'km', 'kilometre': 'km', 'kilometres': 'km',
    'ระยะทาง': 'km',
    'mileage': 'km', 'mile': 'mile',
    # weight
    'weight': 'kg', 'mass': 'kg', 'cargo weight': 'kg', 'cargo_weight': 'kg',
    'waste weight': 'kg', 'waste_weight': 'kg', 'น้ำหนัก': 'kg',
    'tonnage': 'tonne',
    # energy
    'kwh': 'kwh', 'kilowatt hour': 'kwh', 'kilowatt-hour': 'kwh',
    'energy': 'kwh', 'electricity': 'kwh', 'kwh consumed': 'kwh',
    'พลังงาน': 'kwh', 'หน่วย': 'kwh',
    # nights / hotel
    'nights': 'nights', 'night': 'nights', 'จำนวนคืน': 'nights',
    'room nights': 'nights', 'room_nights': 'nights',
    # passenger
    'passenger km': 'passenger-km', 'passenger-km': 'passenger-km',
    # composite
    'tonne km': 'tonne-km', 'tonne-km': 'tonne-km', 'tkm': 'tonne-km',
    # litre
    'litre': 'litre', 'liter': 'litre', 'volume': 'litre', 'fuel': 'litre',
    'น้ำมัน': 'litre',
}


def _infer_unit_from_field(datapoint_name: str, tags) -> str:
    """
    Best-effort: pick a canonical unit from the datapoint_name, then
    from each tag (most-specific first). Empty string if nothing
    matches — caller decides whether to skip the field.
    """
    candidates = []
    if datapoint_name:
        candidates.append(datapoint_name)
    if isinstance(tags, list):
        # tags are emitted general → specific; reverse so the most
        # descriptive one wins ("travel distance" beats "fare").
        candidates.extend([t for t in reversed(tags) if isinstance(t, str)])
    for c in candidates:
        key = (c or '').strip().lower()
        if not key:
            continue
        if key in _NAME_TO_UNIT:
            return _NAME_TO_UNIT[key]
        # Also try collapsing "_" / "-" to spaces, in case the LLM
        # emitted "travel_distance" vs "travel distance".
        flat = key.replace('_', ' ').replace('-', ' ').strip()
        if flat in _NAME_TO_UNIT:
            return _NAME_TO_UNIT[flat]
    return ''


# Per Scope 3 category default EF citation. Used when the LLM didn't
# emit `ghg_source_url` (e.g. records created before the prompt was
# updated, or low-confidence extractions). The URL must be a real,
# verifiable root from an authoritative publisher.
SCOPE3_DEFAULT_CITATIONS: dict = {
    1:  {  # Purchased goods and services — spend-based
        'name': 'GHG Protocol — Scope 3 Calculation Guidance (Cat 1: Purchased goods and services, spend-based method)',
        'url':  'https://ghgprotocol.org/scope-3-calculation-guidance-2',
    },
    2:  {  # Capital goods
        'name': 'GHG Protocol — Scope 3 Calculation Guidance (Cat 2: Capital goods)',
        'url':  'https://ghgprotocol.org/scope-3-calculation-guidance-2',
    },
    3:  {  # Fuel & energy related
        'name': 'DEFRA 2024 GHG Conversion Factors — Well-to-tank fuels & T&D losses',
        'url':  'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting',
    },
    4:  {  # Upstream transportation
        'name': 'DEFRA 2024 GHG Conversion Factors — Freight (tonne-km)',
        'url':  'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting',
    },
    5:  {  # Waste in operations
        'name': 'DEFRA 2024 GHG Conversion Factors — Waste disposal',
        'url':  'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting',
    },
    6:  {  # Business travel
        'name': 'DEFRA 2024 GHG Conversion Factors — Business travel (passenger.km)',
        'url':  'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting',
    },
    7:  {  # Employee commuting
        'name': 'DEFRA 2024 GHG Conversion Factors — Passenger transport (passenger.km)',
        'url':  'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting',
    },
    8:  {  # Upstream leased assets
        'name': 'TGO Thailand Grid Emission Factor (purchased electricity)',
        'url':  'https://ghgreduction.tgo.or.th/',
    },
    9:  {  # Downstream transportation
        'name': 'DEFRA 2024 GHG Conversion Factors — Freight (tonne-km)',
        'url':  'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting',
    },
    10: {  # Processing of sold
        'name': 'GHG Protocol — Scope 3 Calculation Guidance (Cat 10: Processing of sold products)',
        'url':  'https://ghgprotocol.org/scope-3-calculation-guidance-2',
    },
    11: {  # Use of sold
        'name': 'GHG Protocol — Scope 3 Calculation Guidance (Cat 11: Use of sold products)',
        'url':  'https://ghgprotocol.org/scope-3-calculation-guidance-2',
    },
    12: {  # End-of-life
        'name': 'DEFRA 2024 GHG Conversion Factors — Waste disposal (end-of-life)',
        'url':  'https://www.gov.uk/government/collections/government-conversion-factors-for-company-reporting',
    },
    13: {  # Downstream leased
        'name': 'TGO Thailand Grid Emission Factor (purchased electricity)',
        'url':  'https://ghgreduction.tgo.or.th/',
    },
    14: {  # Franchises
        'name': 'GHG Protocol — Scope 3 Calculation Guidance (Cat 14: Franchises)',
        'url':  'https://ghgprotocol.org/scope-3-calculation-guidance-2',
    },
    15: {  # Investments
        'name': 'GHG Protocol — Scope 3 Calculation Guidance (Cat 15: Investments)',
        'url':  'https://ghgprotocol.org/scope-3-calculation-guidance-2',
    },
}


def get_default_citation(scope3_category_id):
    if scope3_category_id is None:
        return None
    return SCOPE3_DEFAULT_CITATIONS.get(int(scope3_category_id))


class EsgCarbonService:

    def __init__(self, db: Session):
        self.db = db

    def calculate_tco2e(
        self,
        category: str,
        amount: float,
        unit: str,
        subcategory: str = None,
        fuel_type: str = None,
        category_id: Optional[int] = None,
    ) -> Optional[float]:
        """
        Compute tCO2e for an activity. Returns None ONLY if no factor at
        all is available (DB miss + fallback miss).
        """
        if amount is None or unit is None:
            return None

        # 1 + 2 — DB lookup
        factor = self._find_factor(category, unit, subcategory, fuel_type)
        if factor:
            tco2e = Decimal(str(amount)) * factor.factor_value
            return float(tco2e)

        # 3 — Scope 3 category-id fallback
        scope3_id = self._resolve_scope3_id(category, category_id)
        if scope3_id is not None:
            ef_kg = self._fallback_ef(scope3_id, unit)
            if ef_kg is not None:
                kg = Decimal(str(amount)) * Decimal(str(ef_kg))
                tco2e = kg / Decimal('1000')
                logger.info(
                    'tCO2e fallback applied: cat=%s unit=%s amount=%s ef_kg=%s tco2e=%s',
                    scope3_id, unit, amount, ef_kg, float(tco2e),
                )
                return float(tco2e)

        logger.warning(
            'No emission factor found (DB or fallback) for category=%r unit=%r — entry will have NULL tco2e',
            category, unit,
        )
        return None

    def calculate_tco2e_for_entry(self, entry) -> Tuple[Optional[float], str]:
        """
        Convenience for the entry pipeline. Returns (tco2e, source) where
        `source` is one of: 'db_factor' | 'scope3_fallback' | 'none'.
        """
        if not entry:
            return None, 'none'

        # Try DB first
        factor = self._find_factor(
            entry.category or '',
            entry.unit or '',
            getattr(entry, 'subcategory_name', None),
            getattr(entry, 'fuel_type', None),
        )
        if factor:
            return float(Decimal(str(entry.value)) * factor.factor_value), 'db_factor'

        scope3_id = self._resolve_scope3_id(entry.category, entry.category_id)
        if scope3_id is not None:
            ef_kg = self._fallback_ef(scope3_id, entry.unit)
            if ef_kg is not None:
                kg = Decimal(str(entry.value)) * Decimal(str(ef_kg))
                return float(kg / Decimal('1000')), 'scope3_fallback'

        return None, 'none'

    def get_scope_for_category(self, category: str, subcategory: str = None) -> Optional[str]:
        """Get the GHG scope tag for a given category."""
        factor = self.db.query(EmissionFactor).filter(
            EmissionFactor.category == category,
            EmissionFactor.is_active == True,
        ).first()
        return factor.scope if factor else None

    def list_factors(self, category: str = None) -> list:
        query = self.db.query(EmissionFactor).filter(EmissionFactor.is_active == True)
        if category:
            query = query.filter(EmissionFactor.category == category)
        return [f.to_dict() for f in query.order_by(EmissionFactor.category).all()]

    def reevaluate_records(self, organization_id: int = None) -> dict:
        """
        Walk existing EsgRecord rows and re-run `evaluate_record_ghg`
        on each. Used after the unit-inference fix landed — records
        that were previously declared insufficient because the LLM
        left `unit` empty can now compute. Idempotent.
        """
        from ...models.esg.records import EsgRecord
        q = self.db.query(EsgRecord).filter(EsgRecord.is_active == True)
        if organization_id:
            q = q.filter(EsgRecord.organization_id == organization_id)
        updated = 0
        skipped = 0
        for rec in q.all():
            ghg = self.evaluate_record_ghg(
                scope3_category_id=rec.scope3_category_id,
                category_id=rec.category_id,
                category_name=None,
                datapoints=rec.datapoints or [],
            )
            new_kg = ghg.get('kgco2e')
            new_status = ghg.get('status')
            old_kg = float(rec.kgco2e) if rec.kgco2e is not None else None
            if new_status == rec.ghg_status and new_kg == old_kg:
                skipped += 1
                continue
            rec.kgco2e = new_kg
            rec.ghg_status = new_status
            rec.ghg_method = ghg.get('method')
            rec.ghg_missing_fields = ghg.get('missing_fields') or []
            rec.ghg_reason = ghg.get('reason')
            if ghg.get('source_name') and not rec.ghg_source_name:
                rec.ghg_source_name = ghg.get('source_name')
            if ghg.get('source_url') and not rec.ghg_source_url:
                rec.ghg_source_url = ghg.get('source_url')
            if ghg.get('ef_value') is not None:
                rec.ghg_ef_value = ghg.get('ef_value')
            if ghg.get('ef_unit'):
                rec.ghg_ef_unit = ghg.get('ef_unit')
            updated += 1
        self.db.commit()
        return {'updated': updated, 'skipped': skipped}

    # ─── record-level GHG evaluator ─────────────────────────────────────

    def evaluate_record_ghg(
        self,
        scope3_category_id: Optional[int],
        category_id: Optional[int],
        category_name: Optional[str],
        datapoints: list,
    ) -> dict:
        """
        Evaluate whether a record has enough activity data to compute
        a *real* (non-spend-based) kgCO2e, then compute it.

        Returns dict:
          {
            'kgco2e':           float | None,
            'status':           'computed' | 'insufficient' | 'method_unknown',
            'method':           'activity_ef' | 'spend_based' | None,
            'missing_fields':   ['distance_km', 'transport_mode', ...],
            'reason':           short Thai/English explanation,
            'used_field':       which datapoint produced the number,
          }

        Rules:
          • If a datapoint with a *physical* unit (km / kg / kwh / nights …)
            has both a value and an EF → status='computed', method='activity_ef'.
          • Else, if the only available unit is currency AND the category
            permits spend-based (Cat 1, 2, 14, 15) → status='computed',
            method='spend_based'.
          • Else → status='insufficient' with an explicit list of what's
            missing, surfaced to the user via the LINE analysis card.
        """
        if not datapoints:
            return {
                'kgco2e': None, 'status': 'insufficient',
                'method': None, 'missing_fields': ['ANY_QUANTITATIVE_DATA'],
                'reason': 'ไม่มีข้อมูลเชิงปริมาณใด ๆ ในเอกสาร',
                'used_field': None,
            }

        # Helper — populate the citation fields from the per-category
        # fallback table whenever the LLM didn't supply its own.
        cite = get_default_citation(scope3_category_id) or {}

        # 1. Try every physical-unit datapoint first.
        for d in datapoints:
            unit = (d.get('unit') or '').strip()
            value = d.get('value')
            # When the LLM left `unit` empty but the datapoint name
            # implies one (e.g. "distance" → km), infer it. This fixes
            # a class of false-insufficient cases where the value was
            # clearly extracted (28.60 in a Distance column) but the
            # evaluator skipped it because unit was blank.
            if not unit:
                unit = _infer_unit_from_field(
                    d.get('datapoint_name') or d.get('canonical_name') or '',
                    d.get('tags') or [],
                )
            if value is None or unit == '' or _is_currency_unit(unit):
                continue
            try:
                num = float(value)
            except (TypeError, ValueError):
                continue
            if num <= 0:
                continue
            kg = self._compute_kg(category_name, unit, num,
                                   category_id=category_id)
            if kg is not None:
                # Reverse-derive the EF we actually applied so the
                # popover can display "EF = 0.45 kgCO2e/kg" (kg / num).
                ef_value = round(kg / num, 6) if num else None
                ef_unit = f'kgCO2e/{_normalize_unit(unit)}' if unit else None
                return {
                    'kgco2e': kg,
                    'status': 'computed',
                    'method': 'activity_ef',
                    'missing_fields': [],
                    'reason': f'คำนวณจาก {num:g} {unit} × ค่าการปล่อยมาตรฐาน',
                    'used_field': d.get('datapoint_name') or d.get('canonical_name'),
                    'source_name': cite.get('name'),
                    'source_url':  cite.get('url'),
                    'ef_value': ef_value,
                    'ef_unit': ef_unit,
                }

        # 2. Currency-only fallback. Only allowed for spend-based-friendly cats.
        SPEND_OK = {1, 2, 14, 15}
        currency_dp = None
        for d in datapoints:
            unit = (d.get('unit') or '').strip()
            if _is_currency_unit(unit) and d.get('value') is not None:
                currency_dp = d
                break

        if currency_dp and scope3_category_id in SPEND_OK:
            try:
                num = float(currency_dp.get('value'))
            except (TypeError, ValueError):
                num = None
            if num and num > 0:
                kg = self._compute_kg(category_name,
                                      currency_dp.get('unit') or '',
                                      num, category_id=category_id)
                if kg is not None:
                    spend_unit = currency_dp.get('unit') or ''
                    ef_value = round(kg / num, 6) if num else None
                    ef_unit = f'kgCO2e/{_normalize_unit(spend_unit)}' if spend_unit else None
                    return {
                        'kgco2e': kg,
                        'status': 'computed',
                        'method': 'spend_based',
                        'missing_fields': [],
                        'reason': (
                            'คำนวณแบบ spend-based (เป็นค่าประมาณจากจำนวนเงิน). '
                            'หากมีข้อมูลกิจกรรม เช่น น้ำหนัก / ระยะทาง / kWh '
                            'จะได้ค่าที่แม่นยำขึ้น.'
                        ),
                        'used_field': currency_dp.get('datapoint_name')
                                       or currency_dp.get('canonical_name'),
                        'source_name': cite.get('name'),
                        'source_url':  cite.get('url'),
                        'ef_value': ef_value,
                        'ef_unit': ef_unit,
                    }

        # 3. Insufficient — list what's needed.
        missing = []
        if scope3_category_id and scope3_category_id in SCOPE3_REQUIRED_FIELDS:
            specs = SCOPE3_REQUIRED_FIELDS[scope3_category_id]
            if specs:
                # Show the first option set (most common) as the missing list.
                missing = list(specs[0])

        if not missing:
            missing = ['ACTIVITY_DATA']

        # Friendly Thai explanation per category
        cat_label = {
            6:  'ต้องการระยะทาง (km) หรือจำนวนคืนพัก (nights) ไม่ใช่แค่จำนวนเงิน',
            7:  'ต้องการระยะทาง (km) หรือ passenger-km',
            4:  'ต้องการน้ำหนัก × ระยะทาง (tonne-km) หรืออย่างน้อย kg + km',
            9:  'ต้องการน้ำหนัก × ระยะทาง (tonne-km) สำหรับขนส่งปลายน้ำ',
            3:  'ต้องการ kWh / MWh / litre ของพลังงาน',
            5:  'ต้องการน้ำหนักของของเสีย (kg / tonne)',
            10: 'ต้องการน้ำหนักของสินค้าที่ขายเข้าสู่กระบวนการ',
            11: 'ต้องการ kWh / litre ที่สินค้าใช้พลังงาน',
            12: 'ต้องการน้ำหนักของสินค้าที่หมดอายุ',
            8:  'ต้องการ kWh หรือพื้นที่ (m²) ของสินทรัพย์เช่า',
            13: 'ต้องการ kWh หรือพื้นที่ (m²) ของสินทรัพย์เช่าปลายน้ำ',
        }.get(scope3_category_id, 'ข้อมูลกิจกรรมไม่เพียงพอที่จะคำนวณ kgCO₂e')

        return {
            'kgco2e': None,
            'status': 'insufficient',
            'method': None,
            'missing_fields': missing,
            'reason': cat_label,
            'used_field': None,
            'source_name': cite.get('name'),
            'source_url':  cite.get('url'),
            'ef_value': None,
            'ef_unit': None,
        }

    def _compute_kg(self, category_name: Optional[str], unit: str,
                    amount: float, category_id: Optional[int] = None) -> Optional[float]:
        """Internal — returns kgCO2e (not tCO2e). Reuses calculate_tco2e and converts."""
        tco2e = self.calculate_tco2e(
            category=category_name or '',
            amount=amount,
            unit=unit,
            category_id=category_id,
        )
        if tco2e is None:
            return None
        return float(tco2e) * 1000.0

    # ─── helpers ────────────────────────────────────────────────────────

    def _find_factor(self, category: str, unit: str,
                     subcategory: str = None, fuel_type: str = None) -> Optional[EmissionFactor]:
        """Find the best matching emission factor."""
        if not category or not unit:
            return None
        query = self.db.query(EmissionFactor).filter(
            EmissionFactor.is_active == True,
        )
        cat_lower = category.lower().strip()

        exact = query.filter(
            EmissionFactor.category.ilike(cat_lower),
            EmissionFactor.unit.ilike(unit.strip()),
        )
        if subcategory:
            exact = exact.filter(EmissionFactor.subcategory.ilike(subcategory.strip()))
        if fuel_type:
            exact = exact.filter(EmissionFactor.fuel_type.ilike(fuel_type.strip()))

        result = exact.first()
        if result:
            return result

        # Fallback: contains-match on category + unit
        return query.filter(
            EmissionFactor.category.ilike(f'%{cat_lower}%'),
            EmissionFactor.unit.ilike(unit.strip()),
        ).first()

    def _resolve_scope3_id(self, category_name: Optional[str], category_id: Optional[int]) -> Optional[int]:
        """
        Resolve the Scope 3 category id (1..15) from either:
          - an EsgDataCategory.id (looked up via FK), or
          - a free-text category name matched on EsgDataCategory.name.
        Returns None if the category is non-Scope-3 or unknown.
        """
        try:
            if category_id:
                row = (
                    self.db.query(EsgDataCategory)
                    .filter(EsgDataCategory.id == category_id)
                    .first()
                )
                if row and row.is_scope3 and row.scope3_category_id:
                    return int(row.scope3_category_id)

            if category_name:
                row = (
                    self.db.query(EsgDataCategory)
                    .filter(
                        EsgDataCategory.name.ilike(category_name.strip()),
                        EsgDataCategory.is_scope3 == True,
                    )
                    .first()
                )
                if row and row.scope3_category_id:
                    return int(row.scope3_category_id)
        except Exception:
            logger.exception('Scope 3 id resolution failed')
        return None

    def _fallback_ef(self, scope3_id: int, unit: str) -> Optional[float]:
        """Look up the conservative default EF (kgCO2e per unit)."""
        table = SCOPE3_FALLBACK_EFS.get(int(scope3_id))
        if not table:
            return None
        u = _normalize_unit(unit)
        if u in table:
            return table[u]
        # try a partial match (e.g. "kwh/year" → "kwh")
        for key, val in table.items():
            if key in u:
                return val
        return None
