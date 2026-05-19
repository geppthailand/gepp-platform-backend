"""
ESG Dashboard Service — Summary KPIs + chart data for Executive Dashboard.

Per-user mode: when a `user_id` is supplied (LIFF context), every aggregate
is filtered to entries that user submitted. The full org-wide view stays
on the desktop platform.

Scope 3 focus mode: when `focus_mode='scope3_only'` (the default), the
"scope_breakdown" returns the **15 Scope 3 categories** instead of the
old Scope 1 / 2 / 3 split, and "top_categories" groups by
`scope3_category_id` rather than the raw `category` text.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from ...models.esg.records import EsgRecord
from ...models.esg.data_hierarchy import EsgDataCategory
from ...models.esg.settings import EsgOrganizationSettings


# Status enum (legacy) — kept for compatibility with pre-existing callers.
class EntryStatus:
    PENDING_VERIFY = 'PENDING_VERIFY'
    VERIFIED = 'VERIFIED'


# Bilingual canonical labels for the 15 Scope 3 categories. Used when the
# DB join fails to return a name (e.g. row missing) so the dashboard can
# still render a stable label.
SCOPE3_CATEGORY_LABELS: Dict[int, Dict[str, str]] = {
    1:  {'en': 'Purchased goods and services',                          'th': 'สินค้าและบริการที่ซื้อ'},
    2:  {'en': 'Capital goods',                                          'th': 'สินค้าทุน'},
    3:  {'en': 'Fuel- and energy-related activities',                    'th': 'กิจกรรมที่เกี่ยวข้องกับเชื้อเพลิงและพลังงาน'},
    4:  {'en': 'Upstream transportation and distribution',               'th': 'การขนส่งและกระจายสินค้าต้นน้ำ'},
    5:  {'en': 'Waste generated in operations',                          'th': 'ของเสียที่เกิดจากการดำเนินงาน'},
    6:  {'en': 'Business travel',                                        'th': 'การเดินทางเพื่อธุรกิจ'},
    7:  {'en': 'Employee commuting',                                     'th': 'การเดินทางมาทำงานของพนักงาน'},
    8:  {'en': 'Upstream leased assets',                                 'th': 'สินทรัพย์เช่าต้นน้ำ'},
    9:  {'en': 'Downstream transportation and distribution',             'th': 'การขนส่งและกระจายสินค้าปลายน้ำ'},
    10: {'en': 'Processing of sold products',                            'th': 'การแปรรูปสินค้าที่ขาย'},
    11: {'en': 'Use of sold products',                                   'th': 'การใช้งานสินค้าที่ขาย'},
    12: {'en': 'End-of-life treatment of sold products',                 'th': 'การจัดการสินค้าที่ขายเมื่อหมดอายุ'},
    13: {'en': 'Downstream leased assets',                               'th': 'สินทรัพย์เช่าปลายน้ำ'},
    14: {'en': 'Franchises',                                             'th': 'แฟรนไชส์'},
    15: {'en': 'Investments',                                            'th': 'การลงทุน'},
}


class EsgDashboardService:

    def __init__(self, db: Session):
        self.db = db

    # ─── helpers ────────────────────────────────────────────────────────

    def _is_scope3_only(self, organization_id: int) -> bool:
        settings = (
            self.db.query(EsgOrganizationSettings)
            .filter(EsgOrganizationSettings.organization_id == organization_id)
            .first()
        )
        if not settings:
            return True  # default to scope3_only when no settings row yet
        return (settings.focus_mode or 'scope3_only') == 'scope3_only'

    def _resolve_user_org_ids(self, jwt_user_id: Optional[int],
                               jwt_org_id: int) -> list:
        """
        Return every organization id the JWT user belongs to. Used so a
        desktop user with memberships in multiple orgs sees the union
        of their records — not just the org currently pinned in the
        JWT (which can drift behind, e.g. when LINE-uploaded receipts
        land in a different org_id than the desktop login resolved).
        Falls back to [jwt_org_id] when we can't enumerate.
        """
        ids = {int(jwt_org_id)} if jwt_org_id else set()
        if not jwt_user_id:
            return list(ids) or [jwt_org_id]
        try:
            from ...models.users.user_location import UserLocation
            email_row = (
                self.db.query(UserLocation.email)
                .filter(UserLocation.id == jwt_user_id)
                .first()
            )
            email = email_row[0] if email_row else None
            if email:
                rows = (
                    self.db.query(UserLocation.organization_id)
                    .filter(UserLocation.email == email)
                    .filter(UserLocation.organization_id.isnot(None))
                    .distinct()
                    .all()
                )
                for (oid,) in rows:
                    if oid:
                        ids.add(int(oid))
        except Exception:
            pass
        return list(ids) or [jwt_org_id]

    def _base_query(self, organization_id: int, user_id: Optional[int] = None,
                    jwt_user_id: Optional[int] = None):
        # ── Desktop fall-through ──────────────────────────────────────
        # Desktop pages currently hit the LIFF endpoint (which always
        # passes user_id). When the JWT user has *no* LINE binding,
        # they're a desktop user, not a LINE user — so return the org
        # aggregate instead of a zero-row user-scoped result. This is
        # what makes the desktop Carbon Dashboard populate with the
        # same numbers admins expect.
        if user_id is not None:
            line_uid = self._resolve_line_user_id(user_id, organization_id)
            if not line_uid:
                # No LINE binding → treat as desktop. Span all orgs the
                # user belongs to so multi-org admins see the union.
                org_ids = self._resolve_user_org_ids(user_id, organization_id)
                return self.db.query(EsgRecord).filter(
                    EsgRecord.organization_id.in_(org_ids),
                    EsgRecord.is_active == True,
                )

        # Multi-org membership: when no per-LIFF-user filter is in
        # play (true /api/dashboard/* path), include records from
        # every org this email belongs to.
        if user_id is None and jwt_user_id:
            org_ids = self._resolve_user_org_ids(jwt_user_id, organization_id)
            q = self.db.query(EsgRecord).filter(
                EsgRecord.organization_id.in_(org_ids),
                EsgRecord.is_active == True,
            )
            return q

        q = self.db.query(EsgRecord).filter(
            EsgRecord.organization_id == organization_id,
            EsgRecord.is_active == True,
        )
        if user_id is not None:
            # user_id is set AND has a LINE binding (line_uid resolved above)
            line_uid = self._resolve_line_user_id(user_id, organization_id)
            from sqlalchemy import or_
            q = q.filter(or_(
                EsgRecord.user_id == user_id,
                EsgRecord.line_user_id == line_uid,
            ))
        return q

    def _resolve_line_user_id(self, esg_user_id: int, organization_id: int = None) -> Optional[str]:
        """
        OR-filter helper — returns LINE platform user id for an EsgUser.
        Filters by organization_id when supplied to defend against the
        (unlikely) case that a user_id from JWT belongs to a different org.
        """
        if not esg_user_id:
            return None
        try:
            from ...models.esg.esg_users import EsgUser
            q = (
                self.db.query(EsgUser)
                .filter(EsgUser.id == esg_user_id, EsgUser.platform == 'line')
            )
            if organization_id is not None:
                q = q.filter(EsgUser.organization_id == organization_id)
            row = q.first()
            return row.platform_user_id if row else None
        except Exception:
            return None

    def _scope3_breakdown(
        self, organization_id: int, user_id: Optional[int] = None,
        jwt_user_id: Optional[int] = None,
    ) -> list:
        """
        SUM(tCO2e) per Scope 3 category 1..15 — for the user (LIFF) or org
        (desktop), depending on whether user_id is set.
        Always returns 15 rows in category-id order, even if some are zero,
        so the dashboard can render a stable bar/donut.
        """
        # Org scoping mirrors _base_query:
        #   • user_id with no LINE binding (desktop user mistakenly
        #     hitting the LIFF path) → expand to every org the user
        #     belongs to.
        #   • no user_id but JWT user_id present → multi-org expand.
        #   • LIFF user with LINE binding → stay org-pinned + apply
        #     the LINE-user filter below.
        desktop_fallthrough = False
        if user_id is not None:
            line_uid = self._resolve_line_user_id(user_id, organization_id)
            if not line_uid:
                org_ids = self._resolve_user_org_ids(user_id, organization_id)
                desktop_fallthrough = True
            else:
                org_ids = [organization_id]
        elif jwt_user_id:
            org_ids = self._resolve_user_org_ids(jwt_user_id, organization_id)
        else:
            org_ids = [organization_id]
        q = (
            self.db.query(
                EsgDataCategory.scope3_category_id.label('cat_id'),
                EsgDataCategory.name.label('cat_name'),
                func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0).label('total_tco2e'),
                func.count(EsgRecord.id).label('entry_count'),
            )
            .join(EsgRecord, EsgRecord.category_id == EsgDataCategory.id)
            .filter(
                EsgRecord.organization_id.in_(org_ids),
                EsgRecord.is_active == True,
                EsgDataCategory.is_scope3 == True,
                EsgDataCategory.scope3_category_id.isnot(None),
            )
        )
        # Apply the LINE-user filter only when the caller is a real
        # LIFF user (has a LINE binding). Desktop users hitting the
        # LIFF path with a UserLocation id end up here via
        # desktop_fallthrough and stay unscoped (org-wide).
        if user_id is not None and not desktop_fallthrough:
            line_uid = self._resolve_line_user_id(user_id, organization_id)
            from sqlalchemy import or_
            q = q.filter(or_(
                EsgRecord.user_id == user_id,
                EsgRecord.line_user_id == line_uid,
            ))
        q = q.group_by(EsgDataCategory.scope3_category_id, EsgDataCategory.name)
        rows = q.all()

        # Map results onto a stable 15-row scaffold
        by_cat = {int(r.cat_id): r for r in rows if r.cat_id is not None}
        out = []
        for cat_id in range(1, 16):
            r = by_cat.get(cat_id)
            label = SCOPE3_CATEGORY_LABELS.get(cat_id, {})
            out.append({
                'scope3_category_id': cat_id,
                'name_en': label.get('en'),
                'name_th': label.get('th'),
                'tco2e': float(r.total_tco2e or 0) if r else 0.0,
                'entry_count': int(r.entry_count or 0) if r else 0,
            })
        return out

    # ─── public ─────────────────────────────────────────────────────────

    def get_summary(
        self,
        organization_id: int,
        user_id: Optional[int] = None,
        jwt_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Summary KPIs.

        Args:
            organization_id: required.
            user_id: optional EsgUser.id. When set, the summary is scoped
                to that LIFF user's own entries only — used by the LIFF
                /summary endpoint so each LINE user sees their own numbers.
                Desktop callers leave this None.
        """
        base = self._base_query(organization_id, user_id, jwt_user_id=jwt_user_id)
        scope3_only = self._is_scope3_only(organization_id)

        # Total tCO2e
        total_tco2e_row = base.with_entities(
            func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0)
        ).scalar()
        total_tco2e = float(total_tco2e_row or 0)

        # Entry counts by status
        total_entries = base.count()
        verified_count = base.filter(EsgRecord.status == EntryStatus.VERIFIED).count()
        pending_count = base.filter(EsgRecord.status == EntryStatus.PENDING_VERIFY).count()

        # Breakdown — scope3 categories when scope3_only, else legacy scopes
        if scope3_only:
            scope_breakdown = []
            scope3_breakdown = self._scope3_breakdown(organization_id, user_id, jwt_user_id=jwt_user_id)
        else:
            scope_breakdown = []
            for scope_tag in ['Scope 1', 'Scope 2', 'Scope 3']:
                val = base.filter(EsgRecord.pillar == scope_tag).with_entities(
                    func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0)
                ).scalar()
                scope_breakdown.append({'scope': scope_tag, 'tco2e': float(val or 0)})
            scope3_breakdown = []

        # Top 3 emission contributors. Scope3 mode → top by category 1..15;
        # legacy mode → top by raw category text.
        if scope3_only:
            top_categories = [
                {
                    'scope3_category_id': r['scope3_category_id'],
                    'category': r['name_en'] or f"Category {r['scope3_category_id']}",
                    'tco2e': r['tco2e'],
                }
                for r in sorted(scope3_breakdown, key=lambda x: x['tco2e'], reverse=True)
                if r['tco2e'] > 0
            ][:3]
        else:
            top_q = (
                base
                .filter(EsgRecord.kgco2e.isnot(None))
                .join(EsgDataCategory, EsgDataCategory.id == EsgRecord.category_id)
                .with_entities(
                    EsgDataCategory.name.label('cat_name'),
                    func.sum(EsgRecord.kgco2e / 1000.0).label('total'),
                )
                .group_by(EsgDataCategory.name)
                .order_by(func.sum(EsgRecord.kgco2e).desc())
                .limit(3)
                .all()
            )
            top_categories = [
                {'category': row[0] or 'Unknown', 'tco2e': float(row[1] or 0)}
                for row in top_q
            ]

        return {
            'total_tco2e': total_tco2e,
            'total_entries': total_entries,
            'verified_count': verified_count,
            'pending_count': pending_count,
            'scope_breakdown': scope_breakdown,        # legacy (E/S/G or 1/2/3)
            'scope3_breakdown': scope3_breakdown,      # new — 15 rows
            'top_categories': top_categories,
            'focus_mode': 'scope3_only' if scope3_only else 'full_esg',
            'is_user_scoped': user_id is not None,
        }

    def get_charts(
        self,
        organization_id: int,
        year: int = None,
        user_id: Optional[int] = None,
        jwt_user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Chart data: donut (scope3 categories) + monthly trend.

        Same per-user / focus-mode behaviour as get_summary.
        """
        explicit_year = bool(year)
        if not year:
            year = datetime.utcnow().year

        base = self._base_query(organization_id, user_id, jwt_user_id=jwt_user_id)
        scope3_only = self._is_scope3_only(organization_id)

        # If caller didn't pin a year and the default (current calendar)
        # year has no records, fall back to the most recent year that
        # does. Without this, an org viewing 2023 receipts from 2026
        # sees an entirely-empty Monthly Trend chart.
        if not explicit_year:
            recent_year = (
                base
                .filter(EsgRecord.entry_date.isnot(None))
                .with_entities(func.max(extract('year', EsgRecord.entry_date)))
                .scalar()
            )
            if recent_year:
                year = int(recent_year)

        # Donut — scope3 category proportions when scope3_only
        if scope3_only:
            scope3 = self._scope3_breakdown(organization_id, user_id, jwt_user_id=jwt_user_id)
            donut_data = [
                {
                    'category_id': r['scope3_category_id'],
                    'label': r['name_en'] or f"Cat {r['scope3_category_id']}",
                    'label_th': r['name_th'],
                    'value': r['tco2e'],
                }
                for r in scope3 if r['tco2e'] > 0
            ]
        else:
            donut_data = []
            for scope_tag in ['Scope 1', 'Scope 2', 'Scope 3']:
                val = base.filter(EsgRecord.pillar == scope_tag).with_entities(
                    func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0)
                ).scalar()
                donut_data.append({'label': scope_tag, 'value': float(val or 0)})

        # Line chart: monthly tCO2e trend
        monthly_data = []
        for month in range(1, 13):
            val = (
                base
                .filter(
                    extract('year', EsgRecord.entry_date) == year,
                    extract('month', EsgRecord.entry_date) == month,
                )
                .with_entities(func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0))
                .scalar()
            )
            monthly_data.append({
                'month': month,
                'label': datetime(year, month, 1).strftime('%b'),
                'tco2e': float(val or 0),
            })

        return {
            'year': year,
            'donut': donut_data,
            'monthly_trend': monthly_data,
            'focus_mode': 'scope3_only' if scope3_only else 'full_esg',
            'is_user_scoped': user_id is not None,
        }
