"""
ESG Smart Insight Engine — Condition-based insight generation.
Evaluates report data against rules and produces contextual messages
(quickwins, opportunities, alerts, critical, praise, benchmarks)
targeted at specific dashboard/report sections.

Inspired by GEPPCriteria's AST-based condition evaluation pattern,
but simplified to use direct Python comparisons against report data.
"""

from typing import Dict, Any, List
import logging

logger = logging.getLogger(__name__)


# Insight types with display metadata
INSIGHT_TYPES = {
    'quickwin':  {'color': '#4ade80', 'icon': 'thunderbolt', 'label': 'Quick Win'},
    'opportunity': {'color': '#38bdf8', 'icon': 'bulb',        'label': 'Opportunity'},
    'alert':     {'color': '#fb923c', 'icon': 'warning',     'label': 'Attention'},
    'critical':  {'color': '#f87171', 'icon': 'alert',       'label': 'Critical'},
    'praise':    {'color': '#76b900', 'icon': 'trophy',      'label': 'Achievement'},
    'benchmark': {'color': '#a78bfa', 'icon': 'bar-chart',   'label': 'Benchmark'},
}


def generate_insights(report: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Evaluate all condition rules against the report data.
    Returns a list of triggered insights sorted by severity.

    Each insight: {type, severity, section, title, message, data}
    severity: 0=info, 1=low, 2=medium, 3=high, 4=critical
    """
    insights = []

    # Extract report fields with safe defaults
    summary = report.get('summary', {})
    total = summary.get('total_tco2e', 0) or 0
    total_entries = summary.get('total_entries', 0) or 0
    verified = summary.get('verified_count', 0) or 0
    pending = summary.get('pending_count', 0) or 0
    scope_breakdown = summary.get('scope_breakdown', [])

    yoy = report.get('yoy', {})
    yoy_pct = yoy.get('change_percent')
    prev_tco2e = yoy.get('previous_tco2e', 0) or 0

    intensities = report.get('intensities', {})
    target = report.get('target_progress', {})
    completeness = report.get('completeness', {})
    overall_score = completeness.get('overall_score', 0) or 0
    pillars = {p['pillar']: p for p in completeness.get('pillars', [])}

    data_quality = report.get('data_quality', {})
    verified_pct = data_quality.get('verified_percent', 0) or 0
    sources = data_quality.get('sources', {})
    line_pct = 0
    if total_entries > 0:
        line_pct = round((sources.get('line_chat', 0) / total_entries) * 100, 0)

    top_emitters = report.get('top_emitters', [])
    pl = report.get('pl_impact', {})
    fw = report.get('framework_alignment', {})
    monthly = report.get('monthly_trend', [])
    scope3 = report.get('scope3_detail', [])

    # Scope percentages
    s1 = next((s for s in scope_breakdown if s.get('scope') == 'Scope 1'), {})
    s2 = next((s for s in scope_breakdown if s.get('scope') == 'Scope 2'), {})
    s3 = next((s for s in scope_breakdown if s.get('scope') == 'Scope 3'), {})
    s1_pct = s1.get('percentage', 0) or 0
    s2_pct = s2.get('percentage', 0) or 0
    s3_pct = s3.get('percentage', 0) or 0
    s2_tco2e = s2.get('tco2e', 0) or 0

    # ═══════════════════════════════════════
    # EMISSION PROFILE RULES
    # ═══════════════════════════════════════

    # E01: No data at all
    if total == 0 and total_entries == 0:
        insights.append(_insight(
            'critical', 4, 'hero', 'No Emission Data',
            'No emission data recorded yet. Start by photographing utility bills, fuel receipts, or invoices via LINE to capture your carbon footprint.',
        ))

    # E02: Scope 3 dominant
    if s3_pct > 70 and total > 0:
        insights.append(_insight(
            'opportunity', 2, 'scope', 'Scope 3 Dominates Your Footprint',
            f'Scope 3 accounts for {s3_pct:.0f}% of total emissions. Engage key suppliers for primary emission data — this improves accuracy by 20-30% and reveals reduction opportunities in your value chain.',
        ))
    elif s3_pct > 50 and total > 0:
        insights.append(_insight(
            'opportunity', 1, 'scope', 'Value Chain Emissions Are Significant',
            f'Scope 3 is {s3_pct:.0f}% of total. Consider supplier screening and spend-based analysis to identify high-impact procurement categories.',
        ))

    # E03: Scope 2 reduction opportunity
    if s2_tco2e > 0 and s2_pct > 25:
        insights.append(_insight(
            'quickwin', 2, 'scope', 'Renewable Energy Opportunity',
            f'Scope 2 is {s2_pct:.0f}% ({s2_tco2e:.1f} tCO2e) from purchased electricity. Switching to green tariff, solar PPA, or RECs can reduce market-based Scope 2 to near zero.',
        ))

    # E04: Scope 1 high — efficiency opportunity
    if s1_pct > 40 and total > 0:
        insights.append(_insight(
            'quickwin', 1, 'scope', 'Direct Emission Reduction',
            f'Scope 1 is {s1_pct:.0f}% of total. Review fuel efficiency, fleet electrification, refrigerant leak management, and process optimization.',
        ))

    # E05: Top emitter concentration
    if top_emitters and total > 0:
        top = top_emitters[0]
        top_pct = top.get('percentage', 0) or 0
        if top_pct > 50:
            savings_10pct = top.get('tco2e', 0) * 0.1
            insights.append(_insight(
                'opportunity', 3, 'emitters', f'Concentrated Emission Source',
                f'"{top["name"]}" accounts for {top_pct:.0f}% of total emissions. A 10% reduction here saves {savings_10pct:.1f} tCO2e — the highest-leverage improvement.',
                {'category': top['name'], 'tco2e': top.get('tco2e'), 'savings_10pct': savings_10pct},
            ))
        elif top_pct > 30:
            insights.append(_insight(
                'opportunity', 1, 'emitters', f'Focus Area: {top["name"]}',
                f'Largest source at {top_pct:.0f}% — prioritize reduction initiatives here for maximum impact.',
            ))

    # ═══════════════════════════════════════
    # YEAR-OVER-YEAR RULES
    # ═══════════════════════════════════════

    if yoy_pct is not None:
        if yoy_pct < -20:
            insights.append(_insight(
                'praise', 3, 'hero', 'Outstanding Emission Reduction!',
                f'Emissions decreased {abs(yoy_pct):.1f}% year-over-year — exceeding most industry peers. This demonstrates strong climate leadership.',
            ))
        elif yoy_pct < -5:
            insights.append(_insight(
                'praise', 2, 'hero', 'Good Progress on Emissions',
                f'Emissions down {abs(yoy_pct):.1f}% YoY. Keep the momentum — sustained reductions compound into significant long-term impact.',
            ))
        elif yoy_pct > 20:
            insights.append(_insight(
                'critical', 4, 'hero', 'Significant Emission Increase',
                f'Emissions increased {yoy_pct:.1f}% year-over-year. Urgent review needed — check if this is from business growth, new operations, or operational inefficiency.',
            ))
        elif yoy_pct > 10:
            insights.append(_insight(
                'alert', 3, 'trend', 'Emissions Rising',
                f'Emissions up {yoy_pct:.1f}% YoY. Review energy consumption and new emission sources to identify and address the increase.',
            ))
        elif yoy_pct > 0:
            insights.append(_insight(
                'alert', 1, 'trend', 'Slight Emission Increase',
                f'Emissions increased {yoy_pct:.1f}%. Determine if this correlates with revenue growth (intensity may still be improving).',
            ))
    elif prev_tco2e == 0 and total > 0:
        insights.append(_insight(
            'opportunity', 1, 'hero', 'First Year of Reporting',
            'This is your baseline year. Future reports will show year-over-year progress from this starting point.',
        ))

    # ═══════════════════════════════════════
    # DATA QUALITY RULES
    # ═══════════════════════════════════════

    if overall_score < 20 and total_entries > 0:
        insights.append(_insight(
            'critical', 4, 'completeness', 'Critical Data Gaps',
            f'Data completeness at only {overall_score:.0f}%. SEC ONE Report and CDP require comprehensive disclosure. Priority: fill Environment pillar data first.',
        ))
    elif overall_score < 50:
        insights.append(_insight(
            'alert', 2, 'completeness', 'Improve Data Coverage',
            f'Completeness at {overall_score:.0f}%. Target 80%+ for credible sustainability reporting and better ESG ratings.',
        ))
    elif overall_score >= 80:
        insights.append(_insight(
            'praise', 2, 'completeness', 'Excellent Data Coverage',
            f'Data completeness at {overall_score:.0f}%! Your ESG data is comprehensive and audit-ready.',
        ))

    # Pillar-specific gaps
    for p_code, p_label in [('E', 'Environment'), ('S', 'Social'), ('G', 'Governance')]:
        p_data = pillars.get(p_code, {})
        p_score = p_data.get('score', 0) or 0
        p_total = p_data.get('total', 0) or 0
        if p_score == 0 and p_total > 0:
            tips = {
                'E': 'Start with electricity bills, fuel receipts, and water meter readings.',
                'S': 'Start with employee headcount, safety incident records, and training hours.',
                'G': 'Start with board composition, meeting frequency, and anti-corruption policies.',
            }
            insights.append(_insight(
                'alert', 3, 'completeness', f'No {p_label} Data',
                f'{p_label} pillar at 0% ({p_total} datapoints available). ESG ratings require all three pillars. {tips.get(p_code, "")}',
            ))

    # Verification rate
    if verified_pct < 30 and total_entries > 10:
        insights.append(_insight(
            'alert', 2, 'quality', 'Low Verification Rate',
            f'Only {verified_pct:.0f}% of entries verified ({pending} pending). Unverified data weakens report credibility and assurance readiness.',
        ))
    elif verified_pct >= 90 and total_entries > 5:
        insights.append(_insight(
            'praise', 1, 'quality', 'High Data Verification',
            f'{verified_pct:.0f}% of entries verified — strong data governance for audit and reporting.',
        ))

    # AI extraction usage
    if line_pct > 70 and total_entries > 5:
        insights.append(_insight(
            'praise', 1, 'quality', 'Efficient AI Data Collection',
            f'{line_pct:.0f}% of data captured via AI extraction — scalable and consistent data collection workflow.',
        ))

    # ═══════════════════════════════════════
    # TARGET & PROGRESS RULES
    # ═══════════════════════════════════════

    if not target.get('has_target'):
        insights.append(_insight(
            'critical', 3, 'target', 'Set Reduction Targets',
            'No emission reduction target configured. Set a base year and target aligned with SBTi 1.5°C pathway to demonstrate climate commitment and track progress.',
        ))
    elif target.get('on_track'):
        insights.append(_insight(
            'praise', 3, 'target', 'On Track for Target!',
            f'Current reduction: {target.get("current_reduction_percent", 0):.1f}% vs target: {target.get("target_percent", 0)}% by {target.get("target_year")}. Excellent progress!',
        ))
    elif target.get('has_target') and not target.get('on_track'):
        gap = (target.get('target_percent', 0) or 0) - (target.get('current_reduction_percent', 0) or 0)
        insights.append(_insight(
            'alert', 3, 'target', 'Behind Reduction Target',
            f'Current reduction {target.get("current_reduction_percent", 0):.1f}% vs target {target.get("target_percent", 0)}% — {gap:.1f}% gap to close. Accelerate initiatives.',
        ))

    # ═══════════════════════════════════════
    # FINANCIAL IMPACT RULES
    # ═══════════════════════════════════════

    carbon_tax_mid = (pl.get('carbon_tax', {}).get('mid', 0) or 0)
    if carbon_tax_mid > 100000:
        insights.append(_insight(
            'alert', 2, 'pl_impact', 'Significant Carbon Tax Exposure',
            f'Estimated carbon tax at $75/tCO2e: ${carbon_tax_mid:,.0f}/yr. Every 10% reduction saves ${carbon_tax_mid * 0.1:,.0f}.',
            {'carbon_tax_mid': carbon_tax_mid},
        ))

    savings = (pl.get('savings_from_reduction', {}).get('value', 0) or 0)
    if savings > 0:
        insights.append(_insight(
            'praise', 1, 'pl_impact', 'Carbon Cost Savings',
            f'YoY emission reduction saves an estimated ${savings:,.0f}/yr in potential carbon costs at $75/tCO2e.',
        ))

    # ═══════════════════════════════════════
    # FRAMEWORK ALIGNMENT RULES
    # ═══════════════════════════════════════

    ghg = fw.get('ghg_protocol', 0) or 0
    gri = fw.get('gri', 0) or 0
    cdp = fw.get('cdp', 0) or 0
    tcfd = fw.get('tcfd', 0) or 0

    if ghg < 25:
        insights.append(_insight(
            'critical', 3, 'framework', 'GHG Protocol Foundation Missing',
            f'GHG Protocol coverage at {ghg:.0f}%. This is the foundation for all carbon reporting. Focus on Scope 1 & 2 data first.',
        ))
    elif ghg >= 70:
        insights.append(_insight(
            'praise', 1, 'framework', 'Strong GHG Protocol Alignment',
            f'GHG Protocol at {ghg:.0f}% — well-positioned for carbon reporting and TGO CFO certification.',
        ))

    if gri >= 60:
        insights.append(_insight(
            'praise', 1, 'framework', 'GRI Reporting Ready',
            f'GRI Standards alignment at {gri:.0f}% — strong position for publishing a sustainability report.',
        ))

    if cdp < 40 and cdp > 0:
        insights.append(_insight(
            'quickwin', 2, 'framework', 'Boost CDP Score Quickly',
            'Add Scope 2 electricity data, governance disclosures, and reduction targets to improve CDP from D/C to B level.',
        ))

    # ═══════════════════════════════════════
    # MONTHLY TREND RULES
    # ═══════════════════════════════════════

    if monthly:
        values = [m.get('tco2e', 0) or 0 for m in monthly]
        non_zero = [v for v in values if v > 0]
        if non_zero:
            avg = sum(non_zero) / len(non_zero)
            peak = max(values)
            peak_idx = values.index(peak)
            peak_month = monthly[peak_idx].get('label', f'Month {peak_idx + 1}')

            if peak > 2 * avg and avg > 0:
                insights.append(_insight(
                    'alert', 2, 'trend', f'Emission Spike in {peak_month}',
                    f'{peak_month} had {peak:.1f} tCO2e — more than 2x the monthly average ({avg:.1f}). Investigate if this is seasonal, one-time, or systemic.',
                ))

            # Declining trend (last 3 months)
            last_3 = values[-3:]
            if len(last_3) == 3 and last_3[0] > 0 and last_3[1] > 0 and last_3[2] > 0:
                if last_3[0] > last_3[1] > last_3[2]:
                    insights.append(_insight(
                        'praise', 2, 'trend', 'Declining Emission Trend',
                        'Emissions have decreased for 3 consecutive months — your reduction efforts are producing results.',
                    ))

        # Zero-data months
        zero_months = sum(1 for v in values if v == 0)
        if zero_months > 6 and total_entries > 0:
            insights.append(_insight(
                'alert', 2, 'trend', 'Months with Missing Data',
                f'{zero_months} months have zero emissions data. Are emissions truly zero, or is data not being collected for these months?',
            ))

    # ═══════════════════════════════════════
    # SCOPE 3 DETAIL RULES
    # ═══════════════════════════════════════

    if scope3:
        # Find dominant Scope 3 category
        if scope3[0].get('percentage', 0) > 50:
            top_s3 = scope3[0]
            insights.append(_insight(
                'opportunity', 2, 'scope3', f'Scope 3 Dominated by {top_s3["name"]}',
                f'{top_s3["name"]} is {top_s3["percentage"]:.0f}% of Scope 3. Focus supplier engagement and data collection here for the biggest impact.',
            ))

        # Categories with zero data
        if len(scope3) < 5 and s3_pct > 0:
            insights.append(_insight(
                'alert', 1, 'scope3', 'Incomplete Scope 3 Coverage',
                f'Only {len(scope3)} of 15 Scope 3 categories have data. Screen remaining categories to ensure no material emissions are missing.',
            ))

    # Sort by severity (highest first), then by type
    type_order = {'critical': 0, 'alert': 1, 'opportunity': 2, 'quickwin': 3, 'praise': 4, 'benchmark': 5}
    insights.sort(key=lambda i: (-i['severity'], type_order.get(i['type'], 9)))

    return insights


def _insight(insight_type: str, severity: int, section: str,
             title: str, message: str, data: Dict = None) -> Dict[str, Any]:
    """Build a single insight dict."""
    meta = INSIGHT_TYPES.get(insight_type, {})
    return {
        'type': insight_type,
        'severity': severity,
        'section': section,
        'title': title,
        'message': message,
        'color': meta.get('color', '#888'),
        'icon': meta.get('icon', 'info'),
        'label': meta.get('label', insight_type.title()),
        'data': data or {},
    }
