"""
ESG Report Service — Consolidated report data for Dashboard, Report, and Share pages.
Single endpoint returns ALL computed metrics, replacing mock data.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy import func, extract, and_, case
from sqlalchemy.orm import Session
import logging

from ...models.esg.records import EsgRecord
from ...models.esg.data_hierarchy import EsgDataCategory, EsgDataSubcategory, EsgDatapoint
from ...models.esg.settings import EsgOrganizationSettings
from .esg_insight_engine import generate_insights
from ...models.esg.organization_setup import EsgOrganizationSetup


class EntryStatus:
    PENDING_VERIFY = 'PENDING_VERIFY'
    VERIFIED = 'VERIFIED'


class EntrySource:
    LINE_CHAT = 'LINE_CHAT'
    LIFF_MANUAL = 'LIFF_MANUAL'

logger = logging.getLogger(__name__)

# Carbon price estimates (USD/tCO2e) for P&L impact calculation
CARBON_PRICE_LOW = 25
CARBON_PRICE_MID = 75
CARBON_PRICE_HIGH = 150


class EsgReportService:

    def __init__(self, db: Session):
        self.db = db

    def _resolve_line_user_id(self, esg_user_id: int, organization_id: int = None):
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

    def get_report(self, organization_id: int, year: int = None,
                   view: str = 'executive', user_id: int = None) -> Dict[str, Any]:
        """
        Consolidated report endpoint. Returns all data needed for
        Dashboard, Report, and Share pages in a single call.

        Args:
            user_id: optional EsgUser.id. When set (LIFF /report endpoint),
                every aggregate is scoped to that user's entries only.
                Desktop callers leave this None for the org-wide view.

        view: 'executive' | 'manager' | 'operations'
        """
        if not year:
            year = datetime.now(timezone.utc).year

        prev_year = year - 1

        # Base query — per-user filter ORs on user_id and line_user_id so
        # legacy LINE-webhook entries with user_id=0 still surface.
        base = self.db.query(EsgRecord).filter(
            EsgRecord.organization_id == organization_id,
            EsgRecord.is_active == True,
        )
        if user_id is not None:
            line_uid = self._resolve_line_user_id(user_id, organization_id)
            if line_uid:
                from sqlalchemy import or_
                base = base.filter(or_(
                    EsgRecord.user_id == user_id,
                    EsgRecord.line_user_id == line_uid,
                ))
            else:
                base = base.filter(EsgRecord.user_id == user_id)
        base_year_q = base.filter(extract('year', EsgRecord.entry_date) == year)
        base_prev_q = base.filter(extract('year', EsgRecord.entry_date) == prev_year)

        # ── 1. Organization info ──
        org_info = self._get_org_info(organization_id)

        # ── 2. Summary (current year) ──
        summary = self._get_summary(base, base_year_q)

        # ── 3. YoY comparison ──
        yoy = self._get_yoy(base_year_q, base_prev_q, year, prev_year)

        # ── 4. Carbon intensities ──
        intensities = self._get_intensities(summary['total_tco2e'], org_info)

        # ── 5. Target progress ──
        target_progress = self._get_target_progress(organization_id, summary['total_tco2e'], base)

        # ── 6. Monthly trend ──
        monthly_trend = self._get_monthly_trend(base, year)

        # ── 7. Donut (scope proportions) ──
        donut = summary['scope_breakdown']

        # ── 8. Top emitters with YoY ──
        top_n = 5 if view == 'executive' else 10
        top_emitters = self._get_top_emitters(base_year_q, base_prev_q, summary['total_tco2e'], top_n)

        # ── 9. Completeness ──
        completeness = self._get_completeness(organization_id)

        # ── 10. Data quality ──
        data_quality = self._get_data_quality(base)

        # ── 11. P&L impact estimates ──
        pl_impact = self._get_pl_impact(summary['total_tco2e'], yoy)

        # Build base response
        report = {
            'organization': org_info,
            'period': {
                'year': year,
                'start_date': f'{year}-01-01',
                'end_date': f'{year}-12-31',
            },
            'summary': summary,
            'scope_breakdown': donut,
            'yoy': yoy,
            'intensities': intensities,
            'target_progress': target_progress,
            'monthly_trend': monthly_trend,
            'donut': [{'label': s['scope'], 'value': s['tco2e']} for s in donut],
            'top_emitters': top_emitters,
            'completeness': completeness,
            'data_quality': data_quality,
            'pl_impact': pl_impact,
        }

        # Manager/Operations views get more detail
        if view in ('manager', 'operations'):
            report['scope3_detail'] = self._get_scope3_detail(base_year_q)
            report['framework_alignment'] = self._get_framework_alignment(organization_id)
            report['recommendations'] = self._get_recommendations(
                summary, completeness, target_progress, yoy, top_emitters
            )
        else:
            # Executive gets top 3 recommendations and simplified framework
            all_recs = self._get_recommendations(
                summary, completeness, target_progress, yoy, top_emitters
            )
            report['recommendations'] = all_recs[:3]
            report['framework_alignment'] = self._get_framework_alignment(organization_id)

        # ── Generate smart insights from all computed data ──
        report['insights'] = generate_insights(report)

        return {'success': True, 'report': report}

    # ─────────────────────────────────────────────
    # Private computation methods
    # ─────────────────────────────────────────────

    def _get_org_info(self, organization_id: int) -> Dict:
        setup = self.db.query(EsgOrganizationSetup).filter(
            EsgOrganizationSetup.organization_id == organization_id,
        ).first()

        # Try to get org name from organizations table
        org_name = f'Organization #{organization_id}'
        try:
            from ...models.organizations.organizations import Organization
            org = self.db.query(Organization).filter(Organization.id == organization_id).first()
            if org and hasattr(org, 'name') and org.name:
                org_name = org.name
            elif org and hasattr(org, 'company_name') and org.company_name:
                org_name = org.company_name
        except Exception:
            pass

        return {
            'name': org_name,
            'industry_sector': setup.industry_sector if setup else None,
            'employee_count': setup.employee_count if setup else None,
            'annual_revenue': float(setup.annual_revenue) if setup and setup.annual_revenue else None,
            'revenue_currency': setup.revenue_currency if setup else 'THB',
        }

    def _get_summary(self, base, base_year_q) -> Dict:
        total_tco2e = float(base.with_entities(
            func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0)
        ).scalar() or 0)

        total_entries = base.count()
        verified = base.filter(EsgRecord.status == EntryStatus.VERIFIED).count()
        pending = base.filter(EsgRecord.status == EntryStatus.PENDING_VERIFY).count()

        scope_breakdown = []
        total_scope = 0
        for scope in ['Scope 1', 'Scope 2', 'Scope 3']:
            val = float(base.filter(EsgRecord.pillar == scope).with_entities(
                func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0)
            ).scalar() or 0)
            scope_breakdown.append({'scope': scope, 'tco2e': val})
            total_scope += val

        # Add percentage
        for s in scope_breakdown:
            s['percentage'] = round(s['tco2e'] / total_scope * 100, 1) if total_scope > 0 else 0

        # Scope 3 categories (1..15) — used by every consumer when
        # focus_mode='scope3_only'. Always returns 15 rows in stable order.
        scope3_categories = self._get_scope3_categories(base, total_tco2e)

        # Top categories — when scope3_only callers will use scope3_categories
        # instead, but we keep this for legacy free-form text grouping.
        top_cats = (
            base
            .filter((EsgRecord.kgco2e / 1000.0).isnot(None))
            .join(EsgDataCategory, EsgDataCategory.id == EsgRecord.category_id, isouter=True).with_entities(EsgDataCategory.name, func.sum((EsgRecord.kgco2e / 1000.0)))
            .group_by(EsgDataCategory.name)
            .order_by(func.sum(EsgRecord.kgco2e).desc())
            .limit(5).all()
        )

        return {
            'total_tco2e': total_tco2e,
            'total_entries': total_entries,
            'verified_count': verified,
            'pending_count': pending,
            'scope_breakdown': scope_breakdown,
            'scope3_categories': scope3_categories,
            'top_categories': [
                {'category': r[0] or 'Unknown', 'tco2e': float(r[1] or 0)}
                for r in top_cats
            ],
        }

    def _get_scope3_categories(self, base, total_tco2e: float) -> List[Dict]:
        """
        Return SUM(tCO2e) per Scope 3 category 1..15 by JOIN'ing
        esg_data_entries → esg_data_category. Always emits 15 rows
        (zero where missing) so the dashboard / report can render a
        stable bar/donut.
        """
        # Mirror the canonical labels from EsgDashboardService so we don't
        # duplicate. Local import avoids a circular import at module load.
        from .esg_dashboard_service import SCOPE3_CATEGORY_LABELS

        rows = (
            base
            .with_entities(
                EsgDataCategory.scope3_category_id.label('cat_id'),
                EsgDataCategory.name.label('cat_name'),
                func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0).label('total'),
                func.count(EsgRecord.id).label('cnt'),
            )
            .join(EsgDataCategory, EsgDataCategory.id == EsgRecord.category_id)
            .filter(
                EsgDataCategory.is_scope3 == True,
                EsgDataCategory.scope3_category_id.isnot(None),
            )
            .group_by(EsgDataCategory.scope3_category_id, EsgDataCategory.name)
            .all()
        )
        by_cat = {int(r.cat_id): r for r in rows if r.cat_id is not None}
        out: List[Dict] = []
        for cat_id in range(1, 16):
            r = by_cat.get(cat_id)
            label = SCOPE3_CATEGORY_LABELS.get(cat_id, {})
            tco2e = float(r.total or 0) if r else 0.0
            pct = round(tco2e / total_tco2e * 100, 1) if total_tco2e > 0 else 0
            out.append({
                'scope3_category_id': cat_id,
                'name_en': label.get('en'),
                'name_th': label.get('th'),
                'tco2e': tco2e,
                'entry_count': int(r.cnt or 0) if r else 0,
                'percentage': pct,
            })
        return out

    def _get_yoy(self, curr_q, prev_q, year, prev_year) -> Dict:
        curr = float(curr_q.with_entities(
            func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0)
        ).scalar() or 0)

        prev = float(prev_q.with_entities(
            func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0)
        ).scalar() or 0)

        change_pct = round((curr - prev) / prev * 100, 1) if prev > 0 else None

        return {
            'current_year': year,
            'previous_year': prev_year,
            'current_tco2e': curr,
            'previous_tco2e': prev,
            'change_percent': change_pct,
            'change_absolute': round(curr - prev, 4) if prev > 0 else None,
        }

    def _get_intensities(self, total_tco2e: float, org_info: Dict) -> Dict:
        revenue = org_info.get('annual_revenue')
        employees = org_info.get('employee_count')

        return {
            'per_revenue': round(total_tco2e / (revenue / 1_000_000), 2) if revenue and revenue > 0 else None,
            'per_employee': round(total_tco2e / employees, 2) if employees and employees > 0 else None,
            'revenue_unit': f"tCO2e/M {org_info.get('revenue_currency', 'THB')}",
        }

    def _get_target_progress(self, org_id: int, current_tco2e: float, base) -> Dict:
        settings = self.db.query(EsgOrganizationSettings).filter(
            EsgOrganizationSettings.organization_id == org_id,
        ).first()

        if not settings or not settings.base_year or not settings.reduction_target_percent:
            return {
                'base_year': None, 'base_tco2e': None,
                'target_percent': None, 'target_year': None,
                'current_reduction_percent': 0, 'on_track': False,
                'has_target': False,
            }

        # Get base year emissions
        base_tco2e = float(
            base.filter(extract('year', EsgRecord.entry_date) == settings.base_year)
            .with_entities(func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0))
            .scalar() or 0
        )

        reduction = round((base_tco2e - current_tco2e) / base_tco2e * 100, 1) if base_tco2e > 0 else 0
        target_pct = float(settings.reduction_target_percent) if settings.reduction_target_percent else 0

        return {
            'base_year': settings.base_year,
            'base_tco2e': base_tco2e,
            'target_percent': target_pct,
            'target_year': settings.reduction_target_year,
            'current_reduction_percent': reduction,
            'on_track': reduction >= target_pct * 0.8 if target_pct > 0 else False,
            'has_target': True,
        }

    def _get_monthly_trend(self, base, year: int) -> List[Dict]:
        months = []
        for m in range(1, 13):
            val = float(
                base.filter(
                    extract('year', EsgRecord.entry_date) == year,
                    extract('month', EsgRecord.entry_date) == m,
                ).with_entities(
                    func.coalesce(func.sum((EsgRecord.kgco2e / 1000.0)), 0)
                ).scalar() or 0
            )
            months.append({
                'month': m,
                'label': datetime(year, m, 1).strftime('%b'),
                'tco2e': val,
            })
        return months

    def _get_top_emitters(self, curr_q, prev_q, total_tco2e: float, limit: int) -> List[Dict]:
        # Current year by category
        curr_cats = dict(
            curr_q
            .filter((EsgRecord.kgco2e / 1000.0).isnot(None))
            .join(EsgDataCategory, EsgDataCategory.id == EsgRecord.category_id, isouter=True).with_entities(EsgDataCategory.name, func.sum((EsgRecord.kgco2e / 1000.0)))
            .group_by(EsgDataCategory.name)
            .order_by(func.sum(EsgRecord.kgco2e).desc())
            .limit(limit).all()
        )

        # Previous year by category
        prev_cats = dict(
            prev_q
            .filter((EsgRecord.kgco2e / 1000.0).isnot(None))
            .join(EsgDataCategory, EsgDataCategory.id == EsgRecord.category_id, isouter=True).with_entities(EsgDataCategory.name, func.sum((EsgRecord.kgco2e / 1000.0)))
            .group_by(EsgDataCategory.name).all()
        )

        # Get scope tags
        scope_map = dict(
            curr_q
            .filter(EsgRecord.pillar.isnot(None))
            .join(EsgDataCategory, EsgDataCategory.id == EsgRecord.category_id, isouter=True).with_entities(EsgDataCategory.name, EsgRecord.pillar)
            .distinct().all()
        )

        emitters = []
        for cat, tco2e in curr_cats.items():
            tco2e_f = float(tco2e or 0)
            prev_val = float(prev_cats.get(cat, 0) or 0)
            yoy = round((tco2e_f - prev_val) / prev_val * 100, 1) if prev_val > 0 else None

            emitters.append({
                'name': cat or 'Unknown',
                'tco2e': tco2e_f,
                'scope': scope_map.get(cat, 'Unknown'),
                'yoy_delta': yoy,
                'percentage': round(tco2e_f / total_tco2e * 100, 1) if total_tco2e > 0 else 0,
            })

        return emitters

    def _get_completeness(self, organization_id: int) -> Dict:
        categories = self.db.query(EsgDataCategory).filter(EsgDataCategory.is_active == True).all()
        subcategories = self.db.query(EsgDataSubcategory).filter(EsgDataSubcategory.is_active == True).all()
        datapoints = self.db.query(EsgDatapoint).filter(EsgDatapoint.is_active == True).all()

        # Get datapoint IDs that have entries
        filled_ids = set(
            r[0] for r in
            self.db.query(EsgRecord.id)
            .filter(
                EsgRecord.organization_id == organization_id,
                EsgRecord.is_active == True,
                EsgRecord.id.isnot(None),
            )
            .distinct().all()
        )

        # Build pillar scores
        dp_by_pillar = {}
        for dp in datapoints:
            dp_by_pillar.setdefault(dp.pillar, []).append(dp.id)

        pillars = []
        total_dp = len(datapoints)
        total_filled = len(filled_ids)

        for pillar, label in [('E', 'Environment'), ('S', 'Social'), ('G', 'Governance')]:
            ids = dp_by_pillar.get(pillar, [])
            filled = len([i for i in ids if i in filled_ids])
            pillars.append({
                'pillar': pillar,
                'name': label,
                'total': len(ids),
                'filled': filled,
                'score': round(filled / len(ids) * 100, 1) if ids else 0,
            })

        return {
            'overall_score': round(total_filled / total_dp * 100, 1) if total_dp > 0 else 0,
            'total_datapoints': total_dp,
            'filled_datapoints': total_filled,
            'pillars': pillars,
        }

    def _get_data_quality(self, base) -> Dict:
        total = base.count()
        verified = base.filter(EsgRecord.status == EntryStatus.VERIFIED).count()
        line_chat = base.filter(EsgRecord.entry_source == EntrySource.LINE_CHAT).count()
        liff_manual = base.filter(EsgRecord.entry_source == EntrySource.LIFF_MANUAL).count()

        return {
            'verified_percent': round(verified / total * 100, 1) if total > 0 else 0,
            'total_entries': total,
            'verified_count': verified,
            'sources': {
                'line_chat': line_chat,
                'liff_manual': liff_manual,
            },
        }

    def _get_pl_impact(self, total_tco2e: float, yoy: Dict) -> Dict:
        """Estimate P&L impact from carbon pricing scenarios."""
        reduction = abs(yoy.get('change_absolute', 0) or 0)

        return {
            'carbon_tax': {
                'low': round(total_tco2e * CARBON_PRICE_LOW, 0),
                'mid': round(total_tco2e * CARBON_PRICE_MID, 0),
                'high': round(total_tco2e * CARBON_PRICE_HIGH, 0),
                'unit': 'USD',
            },
            'offset_cost': {
                'value': round(total_tco2e * 15, 0),  # ~$15/tCO2e average offset price
                'unit': 'USD',
            },
            'savings_from_reduction': {
                'value': round(reduction * CARBON_PRICE_MID, 0),
                'unit': 'USD',
            },
        }

    def _get_scope3_detail(self, curr_q) -> List[Dict]:
        """Detailed Scope 3 breakdown by subcategory (maps to GHG Protocol 15 categories)."""
        rows = (
            curr_q
            .filter(EsgRecord.pillar == 'Scope 3')
            .join(EsgDataSubcategory, EsgRecord.subcategory_id == EsgDataSubcategory.id, isouter=True)
            .with_entities(
                EsgDataSubcategory.name,
                func.sum((EsgRecord.kgco2e / 1000.0)),
                func.count(EsgRecord.id),
            )
            .group_by(EsgDataSubcategory.name)
            .order_by(func.sum(EsgRecord.kgco2e).desc())
            .all()
        )

        total_s3 = sum(float(r[1] or 0) for r in rows)

        result = []
        for i, (name, tco2e, count) in enumerate(rows):
            val = float(tco2e or 0)
            # Extract category number from name (e.g., "Category 10: Processing...")
            cat_num = 0
            if name and 'Category' in name:
                try:
                    cat_num = int(name.split('Category')[1].split(':')[0].strip())
                except (ValueError, IndexError):
                    pass

            result.append({
                'category_number': cat_num,
                'name': name or 'Unknown',
                'tco2e': val,
                'percentage': round(val / total_s3 * 100, 1) if total_s3 > 0 else 0,
                'entry_count': count,
            })

        return result

    def _get_framework_alignment(self, organization_id: int) -> Dict:
        """Estimate framework coverage based on filled datapoints."""
        completeness = self._get_completeness(organization_id)
        e_score = next((p['score'] for p in completeness['pillars'] if p['pillar'] == 'E'), 0)
        s_score = next((p['score'] for p in completeness['pillars'] if p['pillar'] == 'S'), 0)
        g_score = next((p['score'] for p in completeness['pillars'] if p['pillar'] == 'G'), 0)

        # GHG Protocol primarily needs E pillar emission data
        # GRI needs all three pillars
        # CDP focuses on E (climate) + G (governance)
        # TCFD focuses on E (climate risk) + G (governance)
        return {
            'ghg_protocol': round(e_score * 0.9, 1),  # Mostly E pillar
            'gri': round((e_score * 0.4 + s_score * 0.35 + g_score * 0.25), 1),  # All pillars
            'cdp': round((e_score * 0.7 + g_score * 0.3), 1),  # E + G heavy
            'tcfd': round((e_score * 0.6 + g_score * 0.4), 1),  # E + G
        }

    def _get_recommendations(self, summary: Dict, completeness: Dict,
                             target: Dict, yoy: Dict, top_emitters: List) -> List[Dict]:
        """Generate data-driven recommendations from analysis of current state."""
        recs = []
        rec_id = 1

        # 1. Data completeness
        if completeness['overall_score'] < 50:
            recs.append({
                'id': rec_id, 'priority': 'high',
                'title': 'Improve data collection coverage',
                'description': f"Current data completeness is {completeness['overall_score']}%. "
                               f"Only {completeness['filled_datapoints']}/{completeness['total_datapoints']} datapoints have data. "
                               f"Focus on filling gaps in the lowest-scoring pillars.",
                'estimated_savings': 'Better data = better decisions',
                'impact': 'Enables accurate reporting and target setting',
                'scope_affected': 'All',
            })
            rec_id += 1

        # 2. Target setting
        if not target.get('has_target'):
            recs.append({
                'id': rec_id, 'priority': 'high',
                'title': 'Set science-based reduction targets',
                'description': 'No emission reduction target is configured. '
                               'Set a base year and reduction target aligned with SBTi (1.5C pathway) '
                               'to demonstrate climate commitment.',
                'estimated_savings': 'Required for SBTi validation and CDP A-list',
                'impact': 'Enables progress tracking and stakeholder confidence',
                'scope_affected': 'All',
            })
            rec_id += 1

        # 3. Scope 3 dominance
        s3 = next((s for s in summary['scope_breakdown'] if s['scope'] == 'Scope 3'), None)
        if s3 and s3.get('percentage', 0) > 50:
            recs.append({
                'id': rec_id, 'priority': 'high',
                'title': 'Engage suppliers for primary emission data',
                'description': f"Scope 3 accounts for {s3['percentage']}% of total emissions. "
                               f"Transition from spend-based to supplier-specific emission factors "
                               f"for more accurate reporting and reduction opportunities.",
                'estimated_savings': '10-30% more accurate Scope 3 data',
                'impact': 'Better supplier relationships and data quality',
                'scope_affected': 'Scope 3',
            })
            rec_id += 1

        # 4. Scope 2 reduction
        s2 = next((s for s in summary['scope_breakdown'] if s['scope'] == 'Scope 2'), None)
        if s2 and s2['tco2e'] > 0:
            recs.append({
                'id': rec_id, 'priority': 'medium',
                'title': 'Switch to renewable energy sources',
                'description': f"Scope 2 emissions are {s2['tco2e']:.1f} tCO2e from purchased electricity. "
                               f"Consider solar PPA, RECs, or green tariff to reduce market-based Scope 2 to near zero.",
                'estimated_savings': f"Up to {s2['tco2e']:.1f} tCO2e reduction",
                'impact': 'Direct emission reduction, RE100 eligibility',
                'scope_affected': 'Scope 2',
            })
            rec_id += 1

        # 5. Top emitter focus
        if top_emitters:
            top = top_emitters[0]
            recs.append({
                'id': rec_id, 'priority': 'medium',
                'title': f"Prioritize reduction in {top['name']}",
                'description': f"'{top['name']}' is the largest emission source at {top['tco2e']:.1f} tCO2e "
                               f"({top['percentage']}% of total). "
                               f"Focus reduction efforts here for maximum impact.",
                'estimated_savings': f"Target 10% = {top['tco2e'] * 0.1:.1f} tCO2e",
                'impact': 'Highest leverage reduction opportunity',
                'scope_affected': top.get('scope', 'Unknown'),
            })
            rec_id += 1

        # 6. Verification rate
        if summary['pending_count'] > summary['verified_count']:
            recs.append({
                'id': rec_id, 'priority': 'low',
                'title': 'Verify pending data entries',
                'description': f"{summary['pending_count']} entries are pending verification vs "
                               f"{summary['verified_count']} verified. Verify data to improve quality "
                               f"and meet assurance requirements.",
                'estimated_savings': 'Audit readiness',
                'impact': 'Higher data quality score for ratings',
                'scope_affected': 'All',
            })
            rec_id += 1

        # 7. Pillar gaps
        for p in completeness['pillars']:
            if p['score'] == 0 and p['total'] > 0:
                recs.append({
                    'id': rec_id, 'priority': 'medium',
                    'title': f"Start tracking {p['name']} data",
                    'description': f"No data for {p['name']} pillar ({p['total']} datapoints available). "
                                   f"ESG ratings require all three pillars (E, S, G) for comprehensive assessment.",
                    'estimated_savings': f"Unlock {p['name']} reporting",
                    'impact': f"Complete ESG profile for ratings and ONE Report",
                    'scope_affected': p['pillar'],
                })
                rec_id += 1

        # Sort by priority
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        recs.sort(key=lambda r: priority_order.get(r['priority'], 3))

        return recs
