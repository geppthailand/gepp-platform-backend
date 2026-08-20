"""
ESG LIFF Insights Service — the /api/esg/liff/* analytics endpoints behind the
Dashboard and Report chart sections.

Why this file exists: the frontend has shipped these eight sections for a while
(src/liff/pages/LiffEsgDashboard/sections/*, src/liff/pages/LiffReport/sections/*,
reused by the desktop src/pages/Dashboard) and each calls an `esgApi.liffGet*`
wrapper. None of the routes existed server-side, so every one of those cards
rendered its empty state ("No data yet", "No carbon budget set",
"No abatement options yet") no matter how much data the org had.

Every response here is derived from real rows — esg_records, esg_macc_initiatives
and esg_organization_settings. Nothing is hardcoded.

Response shapes are dictated by the chart components' prop interfaces; each
method documents the one it feeds. Changing a key here breaks a chart silently,
because the components fall back to `data?.data || []`.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy import func, extract
from sqlalchemy.orm import Session

from ...models.esg.records import EsgRecord
from ...models.esg.data_hierarchy import EsgDataCategory
from ...models.esg.settings import EsgOrganizationSettings
from ...models.esg.macc import EsgMaccInitiative
from .esg_dashboard_service import SCOPE3_CATEGORY_LABELS

MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']


class EsgLiffInsightsService:

    def __init__(self, db: Session):
        self.db = db

    # ─── shared helpers ─────────────────────────────────────────────────

    def _base(self, organization_id: int):
        return self.db.query(EsgRecord).filter(
            EsgRecord.organization_id == organization_id,
            EsgRecord.is_active == True,
        )

    def _settings(self, organization_id: int) -> Optional[EsgOrganizationSettings]:
        return (
            self.db.query(EsgOrganizationSettings)
            .filter(EsgOrganizationSettings.organization_id == organization_id)
            .first()
        )

    @staticmethod
    def _scope_of(cat_id: Optional[int], is_scope3: Optional[bool]) -> Optional[str]:
        """
        Resolve a record's GHG scope from its category.

        Deliberately not from EsgRecord.pillar — that column is CHAR(1) holding
        'E'/'S'/'G', which is why several callers comparing it to 'Scope 1'
        silently produced zeros.
        """
        if cat_id == 1:
            return 'Scope 1'
        if cat_id == 2:
            return 'Scope 2'
        if is_scope3 or cat_id == 3:
            return 'Scope 3'
        return None

    # NOTE on column labels: never label an aggregate 't'. SQLAlchemy 2.0's
    # Row exposes `.t` as the typed-tuple accessor, so `row.t` silently returns
    # the whole Row instead of the labelled column — it does not raise, it just
    # yields the wrong object. Same applies to `.count`, `.index` and `._*`.
    def _year_totals(self, organization_id: int) -> Dict[int, float]:
        rows = (
            self._base(organization_id)
            .filter(EsgRecord.entry_date.isnot(None))
            .with_entities(
                extract('year', EsgRecord.entry_date).label('y'),
                func.coalesce(func.sum(EsgRecord.kgco2e / 1000.0), 0).label('tco2e_sum'),
            )
            .group_by(extract('year', EsgRecord.entry_date))
            .all()
        )
        return {int(r.y): float(r.tco2e_sum or 0) for r in rows}

    def _latest_year(self, organization_id: int) -> Optional[int]:
        y = (
            self._base(organization_id)
            .filter(EsgRecord.entry_date.isnot(None))
            .with_entities(func.max(extract('year', EsgRecord.entry_date)))
            .scalar()
        )
        return int(y) if y else None

    # ─── 1. enhanced-scope → StackedAreaChart ───────────────────────────

    def get_enhanced_scope(self, organization_id: int,
                           year: int = None) -> List[Dict[str, Any]]:
        """StackedAreaDatum[] = {month: str, scope: str, value: number}"""
        year = year or self._latest_year(organization_id) or datetime.utcnow().year
        # Fall back to the most recent year with data so a demo viewed in a
        # quiet January doesn't render an empty chart.
        if not self._base(organization_id).filter(
                extract('year', EsgRecord.entry_date) == year).first():
            year = self._latest_year(organization_id) or year

        rows = (
            self._base(organization_id)
            .join(EsgDataCategory, EsgDataCategory.id == EsgRecord.category_id)
            .filter(extract('year', EsgRecord.entry_date) == year)
            .with_entities(
                extract('month', EsgRecord.entry_date).label('m'),
                EsgDataCategory.id.label('cat_id'),
                EsgDataCategory.is_scope3.label('is_s3'),
                func.coalesce(func.sum(EsgRecord.kgco2e / 1000.0), 0).label('tco2e_sum'),
            )
            .group_by(extract('month', EsgRecord.entry_date),
                      EsgDataCategory.id, EsgDataCategory.is_scope3)
            .all()
        )

        grid: Dict[tuple, float] = {}
        for r in rows:
            scope = self._scope_of(r.cat_id, r.is_s3)
            if not scope or r.m is None:
                continue
            grid[(int(r.m), scope)] = grid.get((int(r.m), scope), 0.0) + float(r.tco2e_sum or 0)

        scopes_present = sorted({k[1] for k in grid}) or ['Scope 3']
        out = []
        for m in range(1, 13):
            for scope in scopes_present:
                out.append({
                    'month': MONTH_LABELS[m - 1],
                    'scope': scope,
                    'value': round(grid.get((m, scope), 0.0), 3),
                })
        return out

    # ─── 2. carbon-budget → CarbonBudgetGauge ───────────────────────────

    def get_carbon_budget(self, organization_id: int) -> Dict[str, Any]:
        """
        {percent, used_tco2e, total_budget_tco2e, target_year}

        Budget = the cumulative emissions the org may still emit between the
        base year and the target year while landing on its reduction target,
        assuming a straight-line pathway. `used` is what it has emitted since
        the base year.
        """
        s = self._settings(organization_id)
        if not s or not s.base_year or not s.reduction_target_percent \
                or not s.reduction_target_year:
            return {'percent': 0, 'used_tco2e': 0, 'total_budget_tco2e': 0,
                    'target_year': None, 'has_budget': False}

        base_year = int(s.base_year)
        target_year = int(s.reduction_target_year)
        target_pct = float(s.reduction_target_percent)

        totals = self._year_totals(organization_id)
        base_tco2e = totals.get(base_year, 0.0)
        if base_tco2e <= 0 or target_year <= base_year:
            return {'percent': 0, 'used_tco2e': 0, 'total_budget_tco2e': 0,
                    'target_year': target_year, 'has_budget': False}

        # Straight line from base_tco2e down to base*(1 - target). Area under
        # that line over the period is the allowed cumulative budget.
        end_tco2e = base_tco2e * (1 - target_pct / 100.0)
        n_years = target_year - base_year
        total_budget = (base_tco2e + end_tco2e) / 2.0 * n_years

        used = sum(v for y, v in totals.items() if base_year <= y <= target_year)
        percent = round(used / total_budget * 100, 1) if total_budget > 0 else 0

        return {
            'percent': percent,
            'used_tco2e': round(used, 2),
            'total_budget_tco2e': round(total_budget, 2),
            'target_year': target_year,
            'base_year': base_year,
            'has_budget': True,
        }

    # ─── 3. macc → MaccChart ────────────────────────────────────────────

    def get_macc(self, organization_id: int,
                 year: int = None) -> List[Dict[str, Any]]:
        """MaccDatum[] = {name, potential_tco2e, cost_per_tco2e, category}"""
        rows = (
            self.db.query(EsgMaccInitiative)
            .filter(
                EsgMaccInitiative.organization_id == organization_id,
                EsgMaccInitiative.is_active == True,
            )
            .all()
        )
        # Fall back to the global template library so the curve is never empty
        # for an org that hasn't cloned any initiatives yet.
        if not rows:
            rows = (
                self.db.query(EsgMaccInitiative)
                .filter(
                    EsgMaccInitiative.is_template == True,
                    EsgMaccInitiative.is_active == True,
                )
                .all()
            )

        out = []
        for r in rows:
            out.append({
                'id': r.id,
                'name': r.name,
                'name_th': r.name_th,
                'potential_tco2e': float(r.abatement_potential_tco2e or 0),
                'cost_per_tco2e': float(r.cost_per_tco2e or 0),
                'category': r.category or 'other',
                'status': r.status,
                'payback_years': float(r.payback_years) if r.payback_years else None,
            })
        # MACC convention: cheapest abatement first (negative cost = saves money)
        out.sort(key=lambda d: d['cost_per_tco2e'])
        return out

    # ─── 4. alerts → SmartAlertBanner ───────────────────────────────────

    def get_alerts(self, organization_id: int,
                   lang: str = 'en') -> List[Dict[str, Any]]:
        """
        Alert[] = {id, severity, title, message, section?, action_url?}

        Reuses the report's insight engine so alerts stay consistent with the
        narrative shown elsewhere, keeping only the warning-ish types.
        """
        from .esg_report_service import EsgReportService
        report = EsgReportService(self.db).get_report(
            organization_id, view='executive', lang=lang)
        insights = (report.get('report') or {}).get('insights') or []

        sev_name = {4: 'critical', 3: 'high', 2: 'medium', 1: 'low', 0: 'low'}
        out = []
        for i, ins in enumerate(insights, start=1):
            if ins.get('type') not in ('alert', 'critical'):
                continue
            out.append({
                'id': i,
                'severity': sev_name.get(int(ins.get('severity') or 0), 'low'),
                'title': ins.get('title') or '',
                'message': ins.get('message') or '',
                'section': ins.get('section'),
                'action_url': ins.get('action_url'),
            })
        out.sort(key=lambda a: ['low', 'medium', 'high', 'critical'].index(a['severity']),
                 reverse=True)
        return out

    # ─── 5. quick-wins → QuickWinSpotlight ──────────────────────────────

    def get_quick_wins(self, organization_id: int) -> List[Dict[str, Any]]:
        """
        QuickWin[] = {id, title, description, estimated_savings_tco2e,
                      estimated_cost, payback_months, category}

        A "quick win" = an available initiative that pays back inside 3 years.
        """
        rows = (
            self.db.query(EsgMaccInitiative)
            .filter(
                EsgMaccInitiative.is_active == True,
                EsgMaccInitiative.organization_id == organization_id,
            )
            .all()
        )
        if not rows:
            rows = (
                self.db.query(EsgMaccInitiative)
                .filter(EsgMaccInitiative.is_template == True,
                        EsgMaccInitiative.is_active == True)
                .all()
            )

        out = []
        for r in rows:
            payback = float(r.payback_years) if r.payback_years else None
            if payback is None or payback > 3:
                continue
            if r.status in ('completed', 'cancelled'):
                continue
            out.append({
                'id': r.id,
                'title': r.name,
                'description': r.description or (r.name_th or ''),
                'estimated_savings_tco2e': float(r.abatement_potential_tco2e or 0),
                'estimated_cost': float(r.implementation_cost or 0),
                'payback_months': int(round(payback * 12)),
                'category': r.category or 'other',
            })
        out.sort(key=lambda d: d['payback_months'])
        return out

    # ─── 6. sbti-pathway → SBTiPathwayChart ─────────────────────────────

    def get_sbti_pathway(self, organization_id: int) -> Dict[str, Any]:
        """
        {annual_data: [{year, actual?, target_15?, target_2?}], ...}

        1.5 °C ≈ 4.2%/yr linear reduction, well-below-2 °C ≈ 2.5%/yr — the SBTi
        near-term absolute-contraction rates.
        """
        s = self._settings(organization_id)
        totals = self._year_totals(organization_id)
        if not totals:
            return {'annual_data': [], 'has_pathway': False}

        base_year = int(s.base_year) if (s and s.base_year) else min(totals)
        base_tco2e = totals.get(base_year) or totals[min(totals)]
        target_year = int(s.reduction_target_year) if (s and s.reduction_target_year) \
            else base_year + 7

        annual = []
        for y in range(base_year, target_year + 1):
            n = y - base_year
            row = {
                'year': y,
                'target_15': round(base_tco2e * max(0.0, 1 - 0.042 * n), 2),
                'target_2': round(base_tco2e * max(0.0, 1 - 0.025 * n), 2),
            }
            if y in totals:
                row['actual'] = round(totals[y], 2)
            annual.append(row)

        return {
            'annual_data': annual,
            'base_year': base_year,
            'base_tco2e': round(base_tco2e, 2),
            'target_year': target_year,
            'has_pathway': True,
        }

    # ─── 7. scope3-pareto → ParetoChart ─────────────────────────────────

    def get_scope3_pareto(self, organization_id: int,
                          year: int = None) -> List[Dict[str, Any]]:
        """ParetoDatum[] = {category, tco2e, cumulative_pct}"""
        q = (
            self._base(organization_id)
            .join(EsgDataCategory, EsgDataCategory.id == EsgRecord.category_id)
            .filter(
                EsgDataCategory.is_scope3 == True,
                EsgDataCategory.scope3_category_id.isnot(None),
            )
        )
        if year:
            q = q.filter(extract('year', EsgRecord.entry_date) == year)

        rows = (
            q.with_entities(
                EsgDataCategory.scope3_category_id.label('cat'),
                func.coalesce(func.sum(EsgRecord.kgco2e / 1000.0), 0).label('tco2e_sum'),
            )
            .group_by(EsgDataCategory.scope3_category_id)
            .all()
        )
        items = [
            {'cat': int(r.cat), 'tco2e': float(r.tco2e_sum or 0)}
            for r in rows if r.cat is not None and float(r.tco2e_sum or 0) > 0
        ]
        items.sort(key=lambda d: d['tco2e'], reverse=True)

        grand = sum(d['tco2e'] for d in items)
        out, running = [], 0.0
        for d in items:
            running += d['tco2e']
            label = SCOPE3_CATEGORY_LABELS.get(d['cat'], {})
            out.append({
                'scope3_category_id': d['cat'],
                'category': label.get('en') or f"Category {d['cat']}",
                'category_th': label.get('th'),
                'tco2e': round(d['tco2e'], 2),
                'cumulative_pct': round(running / grand * 100, 1) if grand > 0 else 0,
            })
        return out

    # ─── 8. risk-opportunity → BubbleMatrix ─────────────────────────────

    def get_risk_opportunity(self, organization_id: int) -> List[Dict[str, Any]]:
        """
        BubbleDatum[] = {name, likelihood, impact, value, type}

        Built from the org's own Scope 3 concentration plus its initiative
        pipeline: big categories are transition risks, cheap abatement with
        fast payback is an opportunity / quick win. Likelihood and impact are
        scored 1-10 so the matrix axes stay stable.
        """
        pareto = self.get_scope3_pareto(organization_id)
        grand = sum(p['tco2e'] for p in pareto) or 1.0

        out: List[Dict[str, Any]] = []
        for p in pareto[:6]:
            share = p['tco2e'] / grand
            out.append({
                'name': p['category'],
                # Concentration drives both axes: a category carrying half the
                # footprint is both more likely to be regulated and more costly.
                'likelihood': round(min(10.0, 3 + share * 14), 1),
                'impact': round(min(10.0, 2 + share * 16), 1),
                'value': round(p['tco2e'], 2),
                'type': 'risk',
            })

        for w in self.get_quick_wins(organization_id)[:5]:
            payback_yr = max(0.1, w['payback_months'] / 12.0)
            out.append({
                'name': w['title'],
                'likelihood': round(min(10.0, 10 - payback_yr * 2), 1),
                'impact': round(min(10.0, 1 + (w['estimated_savings_tco2e'] / 60.0)), 1),
                'value': round(w['estimated_savings_tco2e'], 2),
                'type': 'quickwin' if w['payback_months'] <= 24 else 'opportunity',
            })

        return out
