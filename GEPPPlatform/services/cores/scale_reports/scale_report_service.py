"""Daily weighing summary for one scale station (one `user_locations` row).

Powers two endpoints that must never disagree on the numbers:

  * `POST /api/iot-devices/daily-summary` — the tablet, full detail
  * `GET  /api/scale-report/<token>`      — the customer's phone, trimmed

Both call :func:`get_daily_summary`; the public one passes the result through
:func:`to_public_payload` first.
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

from sqlalchemy import func, or_

from GEPPPlatform.libs.exceptions import NotFoundException, UnauthorizedException
from GEPPPlatform.models.cores.references import MainMaterial, Material
from GEPPPlatform.models.transactions.transaction_records import TransactionRecord
from GEPPPlatform.models.transactions.transactions import Transaction
from GEPPPlatform.models.users.user_location import UserLocation

from ..reports.ghg_equivalents import kg_co2_to_forest_rai, kg_co2_to_trees
from .bkk_time import bkk_day_to_utc_window

logger = logging.getLogger(__name__)


def _f(value) -> float:
    """Decimal/None → float. `json.dumps` cannot serialize Decimal."""
    return float(value) if value is not None else 0.0


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
        )
        .join(Transaction, TransactionRecord.created_transaction_id == Transaction.id)
        # outer joins: material_id is nullable, and an inner join would make
        # records without a material vanish from the totals silently.
        .outerjoin(Material, TransactionRecord.material_id == Material.id)
        .outerjoin(MainMaterial, TransactionRecord.main_material_id == MainMaterial.id)
        .filter(
            Transaction.origin_id == origin_id,
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
        )
        .all()
    )

    materials: List[Dict[str, Any]] = []
    total_weight = 0.0
    total_entries = 0
    total_co2e = 0.0
    first_at = None
    last_at = None

    for r in rows:
        weight = _f(r.weight_kg)
        # kgCO2e = weight × materials.calc_ghg — same formula the overview
        # report uses (reports_handlers: `record_ghg = weight * calc_ghg`).
        co2e = weight * _f(r.calc_ghg)

        total_weight += weight
        total_entries += int(r.entries or 0)
        total_co2e += co2e
        if r.first_at and (first_at is None or r.first_at < first_at):
            first_at = r.first_at
        if r.last_at and (last_at is None or r.last_at > last_at):
            last_at = r.last_at

        materials.append({
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
            'weight_kg': round(weight, 2),
            'quantity': round(_f(r.quantity), 2),
            'entries': int(r.entries or 0),
            'co2e_kg': round(co2e, 2),
            # share_pct filled in below, once the total is known
        })

    materials.sort(key=lambda m: m['weight_kg'], reverse=True)
    for m in materials:
        m['share_pct'] = round(m['weight_kg'] / total_weight * 100, 1) if total_weight else 0.0

    return {
        'date': day.strftime('%Y-%m-%d'),
        'timezone': 'Asia/Bangkok',
        'window_utc': {
            'start': start_utc.isoformat(),
            'end': end_utc.isoformat(),
        },
        'location': location,
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
        'generated_at': datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
    }


def to_public_payload(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Trim a summary down to what a customer scanning the QR may see.

    Built as an **allowlist** — every exposed field is named here explicitly.
    A denylist (`del summary['materials']`) would leak any field added to
    `get_daily_summary` later, silently and with no test failing.

    Withheld on purpose:
      * `materials[]` / `material_count` — per-material volumes are the
        station's commercial position, not something a walk-in should read.
      * `origin_id`, `window_utc` — internal identifiers, no reader value.
      * prices and operator identity are never in the summary at all.
    """
    totals = summary.get('totals', {})
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
            'co2e_kg': totals.get('co2e_kg'),
            'trees_equivalent': totals.get('trees_equivalent'),
            'forest_rai_equivalent': totals.get('forest_rai_equivalent'),
        },
        'generated_at': summary.get('generated_at'),
    }
