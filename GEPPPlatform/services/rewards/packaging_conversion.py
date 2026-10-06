"""
Packaging → materials conversion for GEPP Rewards (migration 098).

A campaign item of type 'packaging' is claimed in pieces. Each piece converts to the
materials of its packaging by weight (packaging_materials), so a claim of
"Singha bottle × 10" becomes PET 0.700 kg + HDPE 0.010 kg on the waste side.

Rules (kept here so the staff claim, the admin claim and the member self-claim agree):
  * pieces must be a whole number ≥ 1;
  * the composition is read once and SNAPSHOTTED on the claim — catalogue edits only
    affect later claims;
  * the reward ledger keeps `value` in kg (sum of the components) and the pieces in
    `quantity` — see RewardPointTransaction.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from ...exceptions import BadRequestException
from ...models.cores.packagings import Packaging, PackagingBrand, PackagingMaterial
from ...models.cores.references import Material

KG_PLACES = Decimal("0.000001")


def compositions(db: Session, packaging_ids: Iterable[int]) -> dict[int, list[dict]]:
    """packaging_id → [{material_id, weight_kg (Decimal, per piece), main_material_id,
    category_id, unit_weight, name_th, name_en}] in display order."""
    ids = {int(p) for p in packaging_ids if p}
    if not ids:
        return {}
    rows = (
        db.query(PackagingMaterial, Material)
        .join(Material, Material.id == PackagingMaterial.material_id)
        .filter(
            PackagingMaterial.packaging_id.in_(ids),
            PackagingMaterial.deleted_date.is_(None),
            PackagingMaterial.is_active.is_(True),
        )
        .order_by(PackagingMaterial.packaging_id, PackagingMaterial.sort_order, PackagingMaterial.id)
        .all()
    )
    out: dict[int, list[dict]] = {pid: [] for pid in ids}
    for pm, mat in rows:
        out[int(pm.packaging_id)].append({
            "material_id": int(mat.id),
            "weight_kg": Decimal(str(pm.weight_kg)),
            "main_material_id": mat.main_material_id,
            "category_id": mat.category_id,
            "unit_weight": Decimal(str(mat.unit_weight)) if mat.unit_weight else Decimal("1"),
            "name_th": mat.name_th,
            "name_en": mat.name_en,
        })
    return out


def pieces_of(value) -> int:
    """Validate a packaging quantity: a whole number of pieces, at least 1."""
    try:
        d = Decimal(str(value))
    except Exception:
        raise BadRequestException("Packaging quantity must be a whole number of pieces")
    if d <= 0 or d != d.to_integral_value():
        raise BadRequestException("Packaging quantity must be a whole number of pieces (1 or more)")
    return int(d)


def convert(composition: list[dict], pieces: int) -> list[dict]:
    """Per-material kilograms for `pieces` of a packaging (snapshot dicts, JSON-friendly
    except weight_kg which stays Decimal for the arithmetic)."""
    if not composition:
        raise BadRequestException("This packaging has no material composition yet")
    return [{
        "material_id": c["material_id"],
        "weight_kg": (c["weight_kg"] * pieces).quantize(KG_PLACES, rounding=ROUND_HALF_UP),
        "main_material_id": c["main_material_id"],
        "category_id": c["category_id"],
        "unit_weight": c["unit_weight"],
        "name_th": c["name_th"],
        "name_en": c["name_en"],
    } for c in composition]


def packaging_label(db: Session, packaging_id: Optional[int]) -> Optional[str]:
    """"Brand · Name · size" for notes; None when the packaging is unknown."""
    if not packaging_id:
        return None
    p = db.query(Packaging).filter(Packaging.id == packaging_id).first()
    if not p:
        return None
    brand = db.query(PackagingBrand).filter(PackagingBrand.id == p.brand_id).first() if p.brand_id else None
    parts = [p.name_th or p.name_en or f"#{p.id}"]
    if p.size_label:
        parts.append(p.size_label)
    name = " ".join(parts)
    if brand and (brand.name_th or brand.name_en) and (brand.name_th or brand.name_en) not in name:
        name = f"{brand.name_th or brand.name_en} {name}"
    return name


def fmt_kg(v) -> str:
    return f"{Decimal(str(v)).quantize(Decimal('0.001'), rounding=ROUND_HALF_UP)} กก."


def packaging_ghg_kg(db: Session, *rpt_filters) -> float:
    """kg CO2e of PACKAGING claims: Σ component kg × materials.calc_ghg.

    The material path (RewardActivityMaterial.material_id → Material.calc_ghg) only sees
    type='material' items; packaging claims carry their materials in
    reward_point_transaction_components instead. `rpt_filters` are extra conditions on
    RewardPointTransaction (organization, campaign, date range...)."""
    from sqlalchemy import func
    from ...models.rewards.points import RewardPointTransaction, RewardPointTransactionComponent as C
    q = (
        db.query(func.coalesce(func.sum(C.weight_kg * Material.calc_ghg), 0))
        .select_from(C)
        .join(RewardPointTransaction, RewardPointTransaction.id == C.reward_point_transaction_id)
        .join(Material, Material.id == C.material_id)
        .filter(
            C.deleted_date.is_(None),
            RewardPointTransaction.deleted_date.is_(None),
            RewardPointTransaction.reference_type == "claim",
            Material.calc_ghg.isnot(None),
            Material.calc_ghg > 0,
            *rpt_filters,
        )
    )
    return float(q.scalar() or 0)
