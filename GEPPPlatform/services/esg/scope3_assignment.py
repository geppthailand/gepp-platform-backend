"""
Heuristic Scope 3 category assignment + "what's missing" hints for the
LINE reply card.

Why this exists:
  The LLM cascade sometimes returns a generic category name like
  'Carbon Emissions Scope 3' (matched against an old DB row), instead
  of one of the 15 specific GHG Protocol Scope 3 categories. The dashboard
  + emission-factor fallback both key off scope3_category_id (1..15), so
  we need a deterministic post-processing step to force the assignment
  into a specific category before we build the LINE reply.

  This module ALSO computes the "missing fields" list for the reply
  card — by comparing what the LLM extracted against what each Scope 3
  category typically expects, we can guide the user to fill in the gaps.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple, Dict, List

logger = logging.getLogger(__name__)


# ─── Canonical 15-category labels ──────────────────────────────────────────
SCOPE3_LABELS: Dict[int, Dict[str, str]] = {
    1:  {'en': 'Purchased goods and services',                 'th': 'สินค้าและบริการที่ซื้อ'},
    2:  {'en': 'Capital goods',                                 'th': 'สินค้าทุน'},
    3:  {'en': 'Fuel- and energy-related activities',           'th': 'กิจกรรมเชื้อเพลิงและพลังงาน'},
    4:  {'en': 'Upstream transportation and distribution',      'th': 'ขนส่งสินค้าต้นน้ำ'},
    5:  {'en': 'Waste generated in operations',                 'th': 'ของเสียจากการดำเนินงาน'},
    6:  {'en': 'Business travel',                               'th': 'การเดินทางเพื่อธุรกิจ'},
    7:  {'en': 'Employee commuting',                            'th': 'การเดินทางมาทำงานของพนักงาน'},
    8:  {'en': 'Upstream leased assets',                        'th': 'สินทรัพย์เช่าต้นน้ำ'},
    9:  {'en': 'Downstream transportation and distribution',    'th': 'ขนส่งสินค้าปลายน้ำ'},
    10: {'en': 'Processing of sold products',                   'th': 'การแปรรูปสินค้าที่ขาย'},
    11: {'en': 'Use of sold products',                          'th': 'การใช้งานสินค้าที่ขาย'},
    12: {'en': 'End-of-life treatment of sold products',        'th': 'การจัดการสินค้าที่ขายเมื่อหมดอายุ'},
    13: {'en': 'Downstream leased assets',                      'th': 'สินทรัพย์เช่าปลายน้ำ'},
    14: {'en': 'Franchises',                                    'th': 'แฟรนไชส์'},
    15: {'en': 'Investments',                                   'th': 'การลงทุน'},
}


# ─── Heuristic rules: keyword + unit → most likely Scope 3 cat ─────────────
# Order matters — the FIRST matching rule wins. Specific keywords come
# before generic ones.
KEYWORD_RULES: List[Dict] = [
    # Cat 6 — Business travel
    {'cat': 6,  'kw': ['flight', 'airline', 'airfare', 'tmc', 'hotel', 'business travel', 'conference', 'เที่ยวบิน', 'สายการบิน', 'โรงแรม', 'การเดินทางทำงาน']},
    # Cat 7 — Commuting
    {'cat': 7,  'kw': ['commute', 'commuting', 'transit pass', 'parking', 'bts', 'mrt', 'การเดินทางมาทำงาน']},
    # Cat 4/9 — Transportation
    {'cat': 4,  'kw': ['inbound', 'freight', 'shipping inbound', 'bill of lading', 'consignee', 'cif', 'ddp', 'การขนส่งขาเข้า']},
    {'cat': 9,  'kw': ['outbound', 'last-mile', 'lalamove', 'kerry', 'flash', 'shipping outbound', 'fob export', 'การขนส่งขาออก']},
    # Cat 5 — Waste
    {'cat': 5,  'kw': ['waste', 'landfill', 'recycling', 'hauler', 'manifest', 'ของเสีย', 'ขยะ', 'รีไซเคิล']},
    # Cat 11 — Use of sold products (energy ratings, fuel for sold products)
    {'cat': 11, 'kw': ['use phase', 'product use', 'rated power', 'energy star', 'use of sold', 'การใช้งานสินค้า']},
    # Cat 12 — EOL
    {'cat': 12, 'kw': ['end-of-life', 'eol', 'disposal', 'take-back', 'การกำจัด', 'หมดอายุ']},
    # Cat 3 — Fuel/energy upstream
    {'cat': 3,  'kw': ['well-to-tank', 'wtt', 't&d losses', 'transmission losses', 'upstream electricity', 'ต้นน้ำพลังงาน']},
    # Cat 14 — Franchises
    {'cat': 14, 'kw': ['franchise', 'royalty', 'แฟรนไชส์']},
    # Cat 15 — Investments
    {'cat': 15, 'kw': ['portfolio', 'investee', 'pcaf', 'equity holding', 'fund', 'การลงทุน']},
    # Cat 8/13 — Leased
    {'cat': 8,  'kw': ['lease', 'leased', 'serviced office', 'เช่า', 'การเช่า']},
    {'cat': 13, 'kw': ['lease out', 'tenant', 'lessor', 'mall', 'ผู้เช่าของเรา']},
    # Cat 2 — Capital goods
    {'cat': 2,  'kw': ['capex', 'capital purchase', 'fixed asset', 'machinery', 'equipment purchase', 'สินค้าทุน']},
    # Cat 10 — Processing
    {'cat': 10, 'kw': ['processing', 'further process', 'intermediate goods', 'การแปรรูปต่อ']},
    # Cat 1 — Purchased goods and services (catch-all default)
    {'cat': 1,  'kw': ['raw material', 'office supply', 'consulting', 'subscription', 'cloud', 'saas', 'professional service', 'invoice', 'purchase order', 'po', 'goods', 'product', 'material', 'service', 'สินค้า', 'บริการ', 'วัตถุดิบ', 'ใบเสร็จ', 'invoice']},
]

# When all else fails, pick by unit type
UNIT_TO_CAT_FALLBACK: Dict[str, int] = {
    'kwh': 11, 'mwh': 11,
    'litre': 6, 'l': 6, 'liter': 6, 'gallon': 6,
    'km': 6, 'mile': 6, 'tonne-km': 4, 'tkm': 4, 'passenger-km': 7, 'pkm': 7,
    'kg': 5, 'tonne': 5,
    'thb': 1, 'usd': 1, 'baht': 1,
    'unit': 1, 'piece': 1,
    'sqm': 8, 'm2': 8,
    'flight': 6, 'night': 6,
}


# ─── Expected fields per Scope 3 category ──────────────────────────────────
# What we'd like the user to provide for accurate calculation. Used to
# build the "ข้อมูลที่ยังขาด" hint in the LINE reply card.
EXPECTED_FIELDS: Dict[int, Dict[str, List[str]]] = {
    1:  {'en': ['vendor', 'amount (THB)', 'category of spend'],         'th': ['ผู้ขาย', 'ยอดเงิน (บาท)', 'ประเภทสินค้า/บริการ']},
    2:  {'en': ['asset type', 'capex amount', 'acquisition date'],      'th': ['ประเภทสินทรัพย์', 'มูลค่าลงทุน', 'วันที่ซื้อ']},
    3:  {'en': ['fuel type', 'volume', 'upstream EF source'],           'th': ['ประเภทเชื้อเพลิง', 'ปริมาณ', 'แหล่งค่า EF']},
    4:  {'en': ['mode (sea/air/road/rail)', 'weight', 'distance'],      'th': ['รูปแบบขนส่ง', 'น้ำหนัก', 'ระยะทาง']},
    5:  {'en': ['waste stream', 'weight', 'treatment (landfill/recycle)'], 'th': ['ประเภทของเสีย', 'น้ำหนัก', 'การจัดการ (ฝัง/รีไซเคิล)']},
    6:  {'en': ['mode (flight/hotel/ground)', 'route or distance', 'class'], 'th': ['รูปแบบ (บิน/โรงแรม/ภาคพื้น)', 'เส้นทาง/ระยะทาง', 'ชั้นที่นั่ง']},
    7:  {'en': ['mode', 'distance per day', 'days/week'],               'th': ['รูปแบบเดินทาง', 'ระยะทาง/วัน', 'จำนวนวัน/สัปดาห์']},
    8:  {'en': ['lease type', 'floor area or kWh', 'period'],           'th': ['ประเภทการเช่า', 'พื้นที่หรือ kWh', 'ระยะเวลา']},
    9:  {'en': ['mode', 'weight', 'distance', 'incoterm'],              'th': ['รูปแบบขนส่ง', 'น้ำหนัก', 'ระยะทาง', 'incoterm']},
    10: {'en': ['process type', 'volume', 'energy intensity'],          'th': ['ขั้นตอนการแปรรูป', 'ปริมาณ', 'ความเข้มข้นพลังงาน']},
    11: {'en': ['product type', 'lifetime energy use', 'units sold'],   'th': ['ประเภทสินค้า', 'พลังงานตลอดอายุ', 'จำนวนที่ขาย']},
    12: {'en': ['product material', 'weight per unit', 'units sold'],   'th': ['วัสดุของสินค้า', 'น้ำหนักต่อชิ้น', 'จำนวนที่ขาย']},
    13: {'en': ['asset type', 'tenant utility data'],                   'th': ['ประเภทสินทรัพย์', 'ข้อมูลสาธารณูปโภคของผู้เช่า']},
    14: {'en': ['franchisee count', 'avg energy per store'],            'th': ['จำนวนแฟรนไชส์', 'พลังงานเฉลี่ยต่อสาขา']},
    15: {'en': ['investee', 'investment value', 'ownership %'],         'th': ['บริษัทผู้รับการลงทุน', 'มูลค่าลงทุน', '% การถือหุ้น']},
}


def _normalize(s: str) -> str:
    return (s or '').lower().strip()


def assign_scope3_category(
    db_session,
    category_name: Optional[str],
    category_id: Optional[int],
    unit: Optional[str],
    raw_input: Optional[str] = None,
) -> Tuple[Optional[int], str, str, str]:
    """
    Determine the most-likely Scope 3 category id (1..15) for a piece of
    extracted evidence.

    Lookup order:
      1. If `category_id` resolves via DB to an EsgDataCategory with
         is_scope3=True AND scope3_category_id is not NULL → use that.
      2. If `category_name` matches a row in our canonical labels → use it.
      3. Apply keyword rules against (category_name + raw_input).
      4. Apply unit-based fallback.
      5. Default to cat 1 (Purchased goods and services) — the most
         common catch-all for receipts/invoices.

    Returns (scope3_id, label_en, label_th, source_tag).
    """
    # 1. DB resolution
    try:
        from ..esg import esg_carbon_service as _ccs  # avoid circular at top
    except Exception:
        _ccs = None

    if category_id and db_session is not None:
        try:
            from ...models.esg.data_hierarchy import EsgDataCategory
            row = (
                db_session.query(EsgDataCategory)
                .filter(EsgDataCategory.id == category_id)
                .first()
            )
            if row and row.is_scope3 and row.scope3_category_id:
                cid = int(row.scope3_category_id)
                lbl = SCOPE3_LABELS.get(cid, {})
                return cid, lbl.get('en', ''), lbl.get('th', ''), 'db_id'
        except Exception:
            logger.debug('DB resolution failed', exc_info=True)

    # 2. Canonical name match
    if category_name:
        for cid, lbl in SCOPE3_LABELS.items():
            if _normalize(category_name) == _normalize(lbl['en']):
                return cid, lbl['en'], lbl['th'], 'canonical_name'

    # 3. Keyword scan
    haystack = ' '.join(filter(None, [category_name, raw_input])).lower()
    if haystack:
        for rule in KEYWORD_RULES:
            for kw in rule['kw']:
                if kw in haystack:
                    cid = rule['cat']
                    lbl = SCOPE3_LABELS.get(cid, {})
                    return cid, lbl.get('en', ''), lbl.get('th', ''), 'keyword'

    # 4. Unit fallback
    u = _normalize(unit)
    if u in UNIT_TO_CAT_FALLBACK:
        cid = UNIT_TO_CAT_FALLBACK[u]
        lbl = SCOPE3_LABELS.get(cid, {})
        return cid, lbl.get('en', ''), lbl.get('th', ''), 'unit_fallback'

    # 5. Default — purchased goods catch-all
    cid = 1
    lbl = SCOPE3_LABELS.get(cid, {})
    return cid, lbl.get('en', ''), lbl.get('th', ''), 'default'


def missing_fields_for(scope3_id: int, present_fields: List[str], lang: str = 'th') -> List[str]:
    """
    Given a Scope 3 category and the field names the LLM extracted,
    return the list of expected fields that are NOT yet present. Used
    to render the "ข้อมูลที่ยังขาด" / "Still needed" section.
    """
    if not scope3_id:
        return []
    expected = EXPECTED_FIELDS.get(int(scope3_id), {}).get(lang, [])
    if not expected:
        return []
    present_norm = {_normalize(f) for f in present_fields if f}
    missing: List[str] = []
    for exp in expected:
        token = _normalize(exp.split(' (')[0].split('/')[0])
        if not any(token in p for p in present_norm):
            missing.append(exp)
    return missing
