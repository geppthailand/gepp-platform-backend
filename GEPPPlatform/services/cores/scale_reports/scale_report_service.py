"""Daily weighing summary for one scale station (one `user_locations` row).

Powers two endpoints that must never disagree on the numbers:

  * `POST /api/iot-devices/daily-summary` — the tablet, full detail
  * `GET  /api/scale-report/<token>`      — the customer's phone, trimmed

Both call :func:`get_daily_summary`; the public one passes the result through
:func:`to_public_payload` first.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Set

from sqlalchemy import func, or_

from GEPPPlatform.libs.exceptions import NotFoundException, UnauthorizedException
from GEPPPlatform.models.cores.references import MainMaterial, Material
from GEPPPlatform.models.transactions.transaction_records import TransactionRecord
from GEPPPlatform.models.transactions.transactions import Transaction
from GEPPPlatform.models.subscriptions.organizations import OrganizationSetup
from GEPPPlatform.models.users.user_location import UserLocation

from ..reports.ghg_equivalents import kg_co2_to_forest_rai, kg_co2_to_trees
from .bkk_time import bkk_day_to_utc_window

logger = logging.getLogger(__name__)


def _f(value) -> float:
    """Decimal/None → float. `json.dumps` cannot serialize Decimal."""
    return float(value) if value is not None else 0.0


def descendant_origin_ids(db_session, organization_id: int, origin_id: int) -> List[int]:
    """`origin_id` บวกกับทุกจุดที่อยู่ใต้มันในผังองค์กร

    สถานที่เป็นต้นไม้ (สาขา → อาคาร → ชั้น) และตาชั่งมักตั้งอยู่ที่ใบล่างสุด
    หัวหน้าที่ดูแลระดับอาคารจึงต้องเห็นยอดรวมของชั้นข้างใต้ด้วย ไม่ใช่ 0
    เพราะไม่มีใครชั่งโดยระบุตัวอาคารตรง ๆ

    หมายเหตุ: `ReportsService._resolve_descendant_ids()` ทำเรื่องเดียวกัน แต่
    เป็น method ส่วนตัวของคลาสอื่น จึงไม่เรียกข้ามมา ถ้าวันหลังมีการรวมโค้ด
    เดินต้นไม้ทั้งหมดเข้าด้วยกัน ควรรวมตัวนี้ไปด้วย
    """
    setup = (
        db_session.query(OrganizationSetup)
        .filter(
            OrganizationSetup.organization_id == organization_id,
            OrganizationSetup.is_active == True,  # noqa: E712
            OrganizationSetup.deleted_date.is_(None),
        )
        .order_by(OrganizationSetup.created_date.desc())
        .first()
    )
    if not setup or not setup.root_nodes:
        return [origin_id]

    roots = setup.root_nodes
    if isinstance(roots, dict):
        roots = [roots]
    if not isinstance(roots, list):
        return [origin_id]

    def _to_int(v):
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
        return None

    def _collect(node, out):
        nid = _to_int(node.get('nodeId'))
        if nid is not None:
            out.add(nid)
        for child in (node.get('children') or []):
            if isinstance(child, dict):
                _collect(child, out)

    found: Set[int] = {origin_id}

    def _walk(nodes):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if _to_int(node.get('nodeId')) == origin_id:
                _collect(node, found)
            _walk([c for c in (node.get('children') or []) if isinstance(c, dict)])

    _walk([n for n in roots if isinstance(n, dict)])
    return sorted(found)


def _resolve_location(db_session, origin_id: int, organization_id: int) -> Dict[str, Any]:
    """Load the station row and confirm it belongs to *organization_id*.

    Deliberately does **not** filter on `is_location`: a real station with a
    stale flag would 404 and break the feature for that site. Whether the
    caller may see this location at all is decided upstream by the membership
    check in the route — this is the organisation-scoping backstop.
    """
    row = (
        db_session.query(
            UserLocation.id,
            UserLocation.display_name,
            UserLocation.name_th,
            UserLocation.name_en,
            UserLocation.organization_id,
        )
        .filter(
            UserLocation.id == origin_id,
            UserLocation.deleted_date.is_(None),
        )
        .first()
    )
    if not row:
        raise NotFoundException('Location not found')
    if row[4] != organization_id:
        raise UnauthorizedException('User is not a member of this location')

    return {
        'origin_id': int(row[0]),
        'display_name': row[1] or row[2] or row[3] or '',
        'name_th': row[2],
        'name_en': row[3],
    }


def get_daily_summary(
    db_session,
    origin_id: int,
    organization_id: int,
    day: date,
) -> Dict[str, Any]:
    """Aggregate one Thai calendar day of weighing at one station.

    Returns the full payload — see `to_public_payload` before exposing it to
    anyone outside the organisation.
    """
    location = _resolve_location(db_session, origin_id, organization_id)
    start_utc, end_utc = bkk_day_to_utc_window(day)

    # ดึงทีเดียวครอบทั้งกิ่ง แล้วค่อยแยกเป็นสองถังฝั่ง Python — ประหยัดกว่า
    # ยิง query สองรอบ และรับประกันว่าสองตัวเลขมาจากข้อมูลชุดเดียวกัน
    subtree_ids = descendant_origin_ids(db_session, organization_id, origin_id)

    rows = (
        db_session.query(
            TransactionRecord.material_id,
            TransactionRecord.main_material_id,
            TransactionRecord.category_id,
            func.sum(TransactionRecord.origin_weight_kg).label('weight_kg'),
            func.sum(TransactionRecord.origin_quantity).label('quantity'),
            func.count(TransactionRecord.id).label('entries'),
            func.min(TransactionRecord.transaction_date).label('first_at'),
            func.max(TransactionRecord.transaction_date).label('last_at'),
            Material.name_th,
            Material.name_en,
            Material.unit_name_th,
            Material.unit_name_en,
            Material.color,
            Material.calc_ghg,
            MainMaterial.name_th.label('mm_name_th'),
            MainMaterial.name_en.label('mm_name_en'),
            Transaction.origin_id.label('row_origin_id'),
        )
        .join(Transaction, TransactionRecord.created_transaction_id == Transaction.id)
        # outer joins: material_id is nullable, and an inner join would make
        # records without a material vanish from the totals silently.
        .outerjoin(Material, TransactionRecord.material_id == Material.id)
        .outerjoin(MainMaterial, TransactionRecord.main_material_id == MainMaterial.id)
        .filter(
            Transaction.origin_id.in_(subtree_ids),
            Transaction.organization_id == organization_id,
            Transaction.deleted_date.is_(None),
            TransactionRecord.deleted_date.is_(None),
            or_(
                TransactionRecord.status != 'rejected',
                TransactionRecord.status.is_(None),
            ),
            # Authoritative window: the *record* date. A record can be logged
            # later with a back-dated transaction_date, and the parent's date
            # would then put it in the wrong day (same reasoning as
            # transaction_service's records-by-date filter).
            TransactionRecord.transaction_date >= start_utc,
            TransactionRecord.transaction_date < end_utc,
            # Pruning only: there is no index on transaction_records.
            # transaction_date, but transactions.transaction_date has one.
            # Widened by a day on each side so nothing legitimately
            # back-dated inside the record window gets cut here.
            Transaction.transaction_date >= start_utc - timedelta(days=1),
            Transaction.transaction_date < end_utc + timedelta(days=1),
        )
        .group_by(
            TransactionRecord.material_id,
            TransactionRecord.main_material_id,
            TransactionRecord.category_id,
            Material.name_th,
            Material.name_en,
            Material.unit_name_th,
            Material.unit_name_en,
            Material.color,
            Material.calc_ghg,
            MainMaterial.name_th,
            MainMaterial.name_en,
            Transaction.origin_id,
        )
        .all()
    )

    own_rows = [r for r in rows if r.row_origin_id == origin_id]

    return {
        'date': day.strftime('%Y-%m-%d'),
        'timezone': 'Asia/Bangkok',
        'window_utc': {
            'start': start_utc.isoformat(),
            'end': end_utc.isoformat(),
        },
        'location': location,
        # ยอดของจุดที่เลือกเป๊ะ ๆ
        **_fold_rows(own_rows),
        # ยอดรวมทั้งกิ่ง (จุดนี้ + ทุกจุดข้างใต้) — ตาชั่งมักตั้งที่ใบล่างสุด
        # หัวหน้าที่ดูแลระดับอาคารจึงต้องเห็นตัวนี้ ไม่ใช่ 0
        'subtree': {
            'location_count': len(subtree_ids),
            'has_descendants': len(subtree_ids) > 1,
            **_fold_rows(rows),
        },
        'generated_at': datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }


def _fold_rows(rows) -> Dict[str, Any]:
    """รวมแถวจาก query เป็น {'totals': ..., 'materials': ...}

    แยกเป็นฟังก์ชันเพราะต้องเรียกสองครั้งด้วยชุดแถวคนละชุด (เฉพาะจุดนี้ กับ
    ทั้งกิ่ง) การคำนวณต้องเหมือนกันเป๊ะ ไม่งั้นสองตัวเลขบนจอจะเทียบกันไม่ได้
    """
    materials: List[Dict[str, Any]] = []
    total_weight = 0.0
    total_entries = 0
    total_co2e = 0.0
    first_at = None
    last_at = None

    # หนึ่งวัสดุอาจมาจากหลายจุดในกิ่ง — ยุบให้เหลือรายการเดียวต่อวัสดุ
    merged: Dict[Any, Dict[str, Any]] = {}

    for r in rows:
        weight = _f(r.weight_kg)
        # kgCO2e = weight × materials.calc_ghg — สูตรเดียวกับรายงาน overview
        co2e = weight * _f(r.calc_ghg)

        total_weight += weight
        total_entries += int(r.entries or 0)
        total_co2e += co2e
        if r.first_at and (first_at is None or r.first_at < first_at):
            first_at = r.first_at
        if r.last_at and (last_at is None or r.last_at > last_at):
            last_at = r.last_at

        key = (r.material_id, r.main_material_id, r.category_id)
        entry = merged.get(key)
        if entry is None:
            merged[key] = {
                'material_id': r.material_id,
                'main_material_id': r.main_material_id,
                'category_id': r.category_id,
                'name_th': r.name_th,
                'name_en': r.name_en,
                'main_material_name_th': r.mm_name_th,
                'main_material_name_en': r.mm_name_en,
                'unit_name_th': r.unit_name_th,
                'unit_name_en': r.unit_name_en,
                'color': r.color,
                'weight_kg': weight,
                'quantity': _f(r.quantity),
                'entries': int(r.entries or 0),
                'co2e_kg': co2e,
            }
        else:
            entry['weight_kg'] += weight
            entry['quantity'] += _f(r.quantity)
            entry['entries'] += int(r.entries or 0)
            entry['co2e_kg'] += co2e

    materials = list(merged.values())
    for m in materials:
        m['weight_kg'] = round(m['weight_kg'], 2)
        m['quantity'] = round(m['quantity'], 2)
        m['co2e_kg'] = round(m['co2e_kg'], 2)
    materials.sort(key=lambda m: m['weight_kg'], reverse=True)
    for m in materials:
        m['share_pct'] = (
            round(m['weight_kg'] / total_weight * 100, 1) if total_weight else 0.0
        )

    return {
        'totals': {
            'weight_kg': round(total_weight, 2),
            'entries': total_entries,
            'material_count': len(materials),
            'co2e_kg': round(total_co2e, 2),
            'trees_equivalent': round(kg_co2_to_trees(total_co2e), 1),
            'forest_rai_equivalent': round(kg_co2_to_forest_rai(total_co2e), 2),
            'first_entry_at': first_at.isoformat() if first_at else None,
            'last_entry_at': last_at.isoformat() if last_at else None,
        },
        'materials': materials,
    }


def to_public_payload(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a summary down to what a customer scanning the QR may see.

    Built as an **allowlist** — every exposed field is named here explicitly.
    A denylist (`del summary['x']`) would leak any field added to
    `get_daily_summary` later, silently and with no test failing.

    The per-material breakdown *is* exposed. That was a deliberate reversal:
    it was withheld at first because volumes by material are the station's
    commercial position, but showing "the community brought in 300 kg of PET"
    is the reason a customer bothers to scan at all, and the business accepted
    that trade-off knowingly.

    Still withheld:
      * `material_id` / `main_material_id` / `category_id` — internal ids, no
        reader value, and they invite scraping the catalogue.
      * `origin_id`, `window_utc` — internal identifiers.
      * `quantity` / `entries` per material — closer to transaction-level
        detail than the headline the page is for.
      * prices and operator identity are never in the summary at all.
    """
    # ใช้ยอด "รวมทั้งกิ่ง" ไม่ใช่ยอดเฉพาะจุด — พนักงานยื่น QR ให้ลูกค้าขณะที่
    # ตัวเองมองตัวเลขรวมอยู่บนจอ ถ้าสองจอโชว์คนละเลขจะอธิบายกันไม่ถูก
    # จุดที่เป็นใบล่างสุด (ส่วนใหญ่) สองค่านี้เท่ากันอยู่แล้ว
    subtree = summary.get('subtree') or {}
    totals = subtree.get('totals') or summary.get('totals', {})
    materials_src = subtree.get('materials')
    if materials_src is None:
        materials_src = summary.get('materials') or []
    location = summary.get('location', {})
    return {
        'date': summary.get('date'),
        'timezone': summary.get('timezone'),
        'location': {
            'display_name': location.get('display_name'),
            'name_th': location.get('name_th'),
            'name_en': location.get('name_en'),
        },
        'totals': {
            'weight_kg': totals.get('weight_kg'),
            'entries': totals.get('entries'),
            'material_count': totals.get('material_count'),
            'co2e_kg': totals.get('co2e_kg'),
            'trees_equivalent': totals.get('trees_equivalent'),
            'forest_rai_equivalent': totals.get('forest_rai_equivalent'),
        },
        'materials': [
            {
                'name_th': m.get('name_th'),
                'name_en': m.get('name_en'),
                'main_material_name_th': m.get('main_material_name_th'),
                'main_material_name_en': m.get('main_material_name_en'),
                'unit_name_th': m.get('unit_name_th'),
                'unit_name_en': m.get('unit_name_en'),
                'color': m.get('color'),
                'weight_kg': m.get('weight_kg'),
                'share_pct': m.get('share_pct'),
                'co2e_kg': m.get('co2e_kg'),
            }
            for m in materials_src
        ],
        'generated_at': summary.get('generated_at'),
    }
