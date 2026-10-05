"""
Back-office CRUD for the packaging catalogue (migration 098) — /admin/packagings and
/admin/packaging-brands, used by the "Packaging" / "Brands" tabs of /v3-materials.

A packaging converts to materials by weight per piece. The composition is edited as a
whole (the request carries the full list); rows that disappear are soft-deleted so a
claim's snapshot never points at a hard-deleted row. Claims snapshot the composition when
they are made, so edits here only affect later claims.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ...exceptions import BadRequestException, NotFoundException
from ...models.cores.packagings import Packaging, PackagingBrand, PackagingMaterial, PACKAGING_TYPES
from ...models.cores.references import Material
from ...models.rewards.management import RewardActivityMaterial


def _now():
    return datetime.now(timezone.utc)


def _dec(v, field: str) -> Decimal:
    try:
        d = Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        raise BadRequestException(f'{field} must be a number')
    return d


class PackagingAdminService:
    def __init__(self, db: Session):
        self.db = db

    # ── helpers ──────────────────────────────────────────────────────────────
    def _brand_names(self, ids) -> Dict[int, PackagingBrand]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        return {b.id: b for b in self.db.query(PackagingBrand).filter(PackagingBrand.id.in_(ids)).all()}

    def _components(self, packaging_ids) -> Dict[int, List[dict]]:
        ids = {int(i) for i in packaging_ids if i}
        out: Dict[int, List[dict]] = {i: [] for i in ids}
        if not ids:
            return out
        rows = (
            self.db.query(PackagingMaterial, Material)
            .join(Material, Material.id == PackagingMaterial.material_id)
            .filter(PackagingMaterial.packaging_id.in_(ids), PackagingMaterial.deleted_date.is_(None))
            .order_by(PackagingMaterial.packaging_id, PackagingMaterial.sort_order, PackagingMaterial.id)
            .all()
        )
        for pm, m in rows:
            w = float(pm.weight_kg)
            out[int(pm.packaging_id)].append({
                'id': pm.id,
                'materialId': m.id,
                'materialNameTh': m.name_th,
                'materialNameEn': m.name_en,
                'mainMaterialId': m.main_material_id,
                'categoryId': m.category_id,
                'calcGhg': float(m.calc_ghg) if m.calc_ghg is not None else None,
                'weightKg': w,
                'weightGrams': round(w * 1000, 3),
                'sortOrder': pm.sort_order,
            })
        return out

    def _usage(self, packaging_ids) -> Dict[int, int]:
        ids = {int(i) for i in packaging_ids if i}
        if not ids:
            return {}
        rows = (
            self.db.query(RewardActivityMaterial.packaging_id, func.count(RewardActivityMaterial.id))
            .filter(RewardActivityMaterial.packaging_id.in_(ids), RewardActivityMaterial.deleted_date.is_(None))
            .group_by(RewardActivityMaterial.packaging_id)
            .all()
        )
        return {int(pid): int(n) for pid, n in rows}

    def _serialize(self, p: Packaging, brands: Dict[int, PackagingBrand], comps: Dict[int, List[dict]],
                   usage: Dict[int, int]) -> Dict[str, Any]:
        parts = comps.get(int(p.id), [])
        brand = brands.get(p.brand_id) if p.brand_id else None
        return {
            'id': p.id,
            'brandId': p.brand_id,
            'brandNameTh': brand.name_th if brand else None,
            'brandNameEn': brand.name_en if brand else None,
            'nameTh': p.name_th,
            'nameEn': p.name_en,
            'sizeLabel': p.size_label,
            'volumeMl': float(p.volume_ml) if p.volume_ml is not None else None,
            'barcode': p.barcode,
            'packagingType': p.packaging_type,
            'imageFileId': p.image_file_id,
            'organizationId': p.organization_id,
            'isActive': bool(p.is_active),
            'components': parts,
            'totalWeightKg': round(sum(c['weightKg'] for c in parts), 6),
            'ghgPerPiece': round(sum(c['weightKg'] * (c['calcGhg'] or 0) for c in parts), 6),
            'usedByRewardItems': usage.get(int(p.id), 0),
            'createdDate': p.created_date.isoformat() if p.created_date else None,
            'updatedDate': p.updated_date.isoformat() if p.updated_date else None,
        }

    def _get(self, packaging_id: int) -> Packaging:
        p = self.db.query(Packaging).filter(Packaging.id == packaging_id, Packaging.deleted_date.is_(None)).first()
        if not p:
            raise NotFoundException('Packaging not found')
        return p

    def _validate_components(self, raw) -> List[dict]:
        if not isinstance(raw, list) or not raw:
            raise BadRequestException('A packaging needs at least one material')
        seen, out = set(), []
        for i, c in enumerate(raw):
            if not isinstance(c, dict):
                raise BadRequestException('Invalid component')
            try:
                mid = int(c.get('materialId'))
            except (TypeError, ValueError):
                raise BadRequestException(f'Component {i + 1}: material is required')
            if mid in seen:
                raise BadRequestException('The same material appears twice')
            seen.add(mid)
            if c.get('weightKg') not in (None, ''):
                w = _dec(c['weightKg'], 'weightKg')
            elif c.get('weightGrams') not in (None, ''):
                w = _dec(c['weightGrams'], 'weightGrams') / Decimal(1000)
            else:
                raise BadRequestException(f'Component {i + 1}: weight is required')
            if w <= 0:
                raise BadRequestException(f'Component {i + 1}: weight must be greater than 0')
            out.append({'material_id': mid, 'weight_kg': w, 'sort_order': i})
        mats = {m.id: m for m in self.db.query(Material).filter(Material.id.in_(seen)).all()}
        for c in out:
            m = mats.get(c['material_id'])
            if not m or not m.is_active or m.deleted_date is not None:
                raise BadRequestException(f"Material {c['material_id']} not found")
            if not m.is_global:
                raise BadRequestException(f'"{m.name_th or m.name_en}" is an organisation-only material; use a global one')
        return out

    def _apply_fields(self, p: Packaging, data: dict, creating: bool) -> None:
        if creating or 'nameTh' in data:
            name = (data.get('nameTh') or '').strip()
            if not name:
                raise BadRequestException('nameTh is required')
            p.name_th = name
        if 'nameEn' in data:
            p.name_en = (data.get('nameEn') or '').strip() or None
        if 'brandId' in data:
            bid = data.get('brandId')
            if bid in (None, ''):
                p.brand_id = None
            else:
                b = self.db.query(PackagingBrand).filter(PackagingBrand.id == int(bid),
                                                         PackagingBrand.deleted_date.is_(None)).first()
                if not b:
                    raise BadRequestException('Brand not found')
                p.brand_id = b.id
        if 'sizeLabel' in data:
            p.size_label = (data.get('sizeLabel') or '').strip() or None
        if 'volumeMl' in data:
            p.volume_ml = _dec(data['volumeMl'], 'volumeMl') if data.get('volumeMl') not in (None, '') else None
        if 'barcode' in data:
            p.barcode = (data.get('barcode') or '').strip() or None
        if creating or 'packagingType' in data:
            t = data.get('packagingType') or 'other'
            if t not in PACKAGING_TYPES:
                raise BadRequestException(f"packagingType must be one of {', '.join(PACKAGING_TYPES)}")
            p.packaging_type = t
        if 'isActive' in data:
            p.is_active = bool(data['isActive'])

    def _check_unique(self, p: Packaging) -> None:
        q = self.db.query(Packaging.id).filter(
            Packaging.deleted_date.is_(None),
            func.coalesce(Packaging.brand_id, 0) == (p.brand_id or 0),
            func.lower(Packaging.name_th) == (p.name_th or '').lower(),
            func.coalesce(func.lower(Packaging.size_label), '') == (p.size_label or '').lower(),
        )
        if p.id:
            q = q.filter(Packaging.id != p.id)
        if q.first():
            raise BadRequestException('This brand already has a packaging with that name and size')

    def _replace_components(self, p: Packaging, comps: List[dict]) -> None:
        existing = {pm.material_id: pm for pm in self.db.query(PackagingMaterial).filter(
            PackagingMaterial.packaging_id == p.id, PackagingMaterial.deleted_date.is_(None)).all()}
        keep = set()
        for c in comps:
            pm = existing.get(c['material_id'])
            if pm:
                pm.weight_kg = c['weight_kg']
                pm.sort_order = c['sort_order']
            else:
                self.db.add(PackagingMaterial(packaging_id=p.id, material_id=c['material_id'],
                                              weight_kg=c['weight_kg'], sort_order=c['sort_order']))
            keep.add(c['material_id'])
        for mid, pm in existing.items():
            if mid not in keep:
                pm.deleted_date = _now()
                pm.is_active = False

    def _one(self, p: Packaging) -> Dict[str, Any]:
        return self._serialize(p, self._brand_names([p.brand_id]), self._components([p.id]), self._usage([p.id]))

    # ── packagings ───────────────────────────────────────────────────────────
    def list_packagings(self, query_params: dict) -> Dict[str, Any]:
        page = max(1, int(query_params.get('page', 1) or 1))
        page_size = min(500, max(1, int(query_params.get('pageSize', 20) or 20)))
        q = self.db.query(Packaging).filter(Packaging.deleted_date.is_(None))
        search = (query_params.get('q') or query_params.get('search') or '').strip()
        if search:
            like = f'%{search}%'
            brand_ids = [b.id for b in self.db.query(PackagingBrand.id).filter(
                or_(PackagingBrand.name_th.ilike(like), PackagingBrand.name_en.ilike(like))).all()]
            q = q.filter(or_(Packaging.name_th.ilike(like), Packaging.name_en.ilike(like),
                             Packaging.barcode.ilike(like), Packaging.brand_id.in_(brand_ids or [-1])))
        if query_params.get('brandId'):
            q = q.filter(Packaging.brand_id == int(query_params['brandId']))
        if query_params.get('packagingType'):
            q = q.filter(Packaging.packaging_type == query_params['packagingType'])
        active = query_params.get('isActive')
        if active is not None and str(active).strip() != '':
            q = q.filter(Packaging.is_active == (str(active).lower() in ('true', '1', 'yes')))
        total = q.count()
        rows = q.order_by(Packaging.brand_id.asc().nullslast(), Packaging.name_th, Packaging.id).offset(
            (page - 1) * page_size).limit(page_size).all()
        ids = [p.id for p in rows]
        brands, comps, usage = self._brand_names([p.brand_id for p in rows]), self._components(ids), self._usage(ids)
        return {'items': [self._serialize(p, brands, comps, usage) for p in rows],
                'total': total, 'page': page, 'pageSize': page_size}

    def get_packaging(self, packaging_id: int) -> Dict[str, Any]:
        return self._one(self._get(packaging_id))

    def create_packaging(self, data: dict) -> Dict[str, Any]:
        comps = self._validate_components(data.get('components'))
        p = Packaging()
        self._apply_fields(p, data, creating=True)
        self._check_unique(p)
        self.db.add(p)
        self.db.flush()
        self._replace_components(p, comps)
        self.db.commit()
        return self._one(p)

    def update_packaging(self, packaging_id: int, data: dict) -> Dict[str, Any]:
        p = self._get(packaging_id)
        self._apply_fields(p, data, creating=False)
        self._check_unique(p)
        if 'components' in data:
            self._replace_components(p, self._validate_components(data.get('components')))
        self.db.commit()
        return self._one(p)

    def delete_packaging(self, packaging_id: int) -> Dict[str, Any]:
        p = self._get(packaging_id)
        used = self._usage([p.id]).get(int(p.id), 0)
        if used:
            raise BadRequestException(
                f'Used by {used} reward item(s). Deactivate it instead, or remove it from those campaigns first.')
        p.deleted_date = _now()
        p.is_active = False
        self.db.commit()
        return {'id': packaging_id, 'deleted': True}

    # ── brands ───────────────────────────────────────────────────────────────
    def _serialize_brand(self, b: PackagingBrand, counts: Dict[int, int]) -> Dict[str, Any]:
        return {'id': b.id, 'nameTh': b.name_th, 'nameEn': b.name_en, 'logoFileId': b.logo_file_id,
                'isActive': bool(b.is_active), 'packagingCount': counts.get(b.id, 0),
                'createdDate': b.created_date.isoformat() if b.created_date else None}

    def _brand_counts(self, ids) -> Dict[int, int]:
        ids = {i for i in ids if i}
        if not ids:
            return {}
        rows = (self.db.query(Packaging.brand_id, func.count(Packaging.id))
                .filter(Packaging.brand_id.in_(ids), Packaging.deleted_date.is_(None))
                .group_by(Packaging.brand_id).all())
        return {int(bid): int(n) for bid, n in rows}

    def list_brands(self, query_params: dict) -> Dict[str, Any]:
        page = max(1, int(query_params.get('page', 1) or 1))
        page_size = min(500, max(1, int(query_params.get('pageSize', 50) or 50)))
        q = self.db.query(PackagingBrand).filter(PackagingBrand.deleted_date.is_(None))
        search = (query_params.get('q') or '').strip()
        if search:
            like = f'%{search}%'
            q = q.filter(or_(PackagingBrand.name_th.ilike(like), PackagingBrand.name_en.ilike(like)))
        total = q.count()
        rows = q.order_by(PackagingBrand.name_th).offset((page - 1) * page_size).limit(page_size).all()
        counts = self._brand_counts([b.id for b in rows])
        return {'items': [self._serialize_brand(b, counts) for b in rows], 'total': total,
                'page': page, 'pageSize': page_size}

    def _get_brand(self, brand_id: int) -> PackagingBrand:
        b = self.db.query(PackagingBrand).filter(PackagingBrand.id == brand_id,
                                                 PackagingBrand.deleted_date.is_(None)).first()
        if not b:
            raise NotFoundException('Brand not found')
        return b

    def _brand_unique(self, name_th: str, exclude_id: Optional[int] = None) -> None:
        q = self.db.query(PackagingBrand.id).filter(PackagingBrand.deleted_date.is_(None),
                                                    func.lower(PackagingBrand.name_th) == name_th.lower())
        if exclude_id:
            q = q.filter(PackagingBrand.id != exclude_id)
        if q.first():
            raise BadRequestException('A brand with this name already exists')

    def get_brand(self, brand_id: int) -> Dict[str, Any]:
        b = self._get_brand(brand_id)
        return self._serialize_brand(b, self._brand_counts([b.id]))

    def create_brand(self, data: dict) -> Dict[str, Any]:
        name = (data.get('nameTh') or '').strip()
        if not name:
            raise BadRequestException('nameTh is required')
        self._brand_unique(name)
        b = PackagingBrand(name_th=name, name_en=(data.get('nameEn') or '').strip() or None)
        self.db.add(b)
        self.db.commit()
        return self._serialize_brand(b, {})

    def update_brand(self, brand_id: int, data: dict) -> Dict[str, Any]:
        b = self._get_brand(brand_id)
        if 'nameTh' in data:
            name = (data.get('nameTh') or '').strip()
            if not name:
                raise BadRequestException('nameTh is required')
            self._brand_unique(name, exclude_id=b.id)
            b.name_th = name
        if 'nameEn' in data:
            b.name_en = (data.get('nameEn') or '').strip() or None
        if 'isActive' in data:
            b.is_active = bool(data['isActive'])
        self.db.commit()
        return self._serialize_brand(b, self._brand_counts([b.id]))

    def delete_brand(self, brand_id: int) -> Dict[str, Any]:
        b = self._get_brand(brand_id)
        n = self._brand_counts([b.id]).get(b.id, 0)
        if n:
            raise BadRequestException(f'The brand still has {n} packaging item(s)')
        b.deleted_date = _now()
        b.is_active = False
        self.db.commit()
        return {'id': brand_id, 'deleted': True}
