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


def generate_insights(report: Dict[str, Any], lang: str = 'en') -> List[Dict[str, Any]]:
    """
    Evaluate all condition rules against the report data.
    Returns a list of triggered insights sorted by severity.

    Each insight: {type, severity, section, title, message, data}
    severity: 0=info, 1=low, 2=medium, 3=high, 4=critical

    `lang` ('en' | 'th') picks the localized title/message. Numbers and codes
    (tCO2e, scope %, $) stay as-is; the `_L(en, th)` helper chooses the string.
    """
    insights = []
    is_th = (lang == 'th')

    def _L(en: str, th: str) -> str:
        return th if is_th else en

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
            'critical', 4, 'hero', _L('No Emission Data', 'ยังไม่มีข้อมูลการปล่อย'),
            _L('No emission data recorded yet. Start by photographing utility bills, fuel receipts, or invoices via LINE to capture your carbon footprint.', 'ยังไม่มีข้อมูลการปล่อย เริ่มต้นด้วยการถ่ายรูปบิลค่าน้ำค่าไฟ ใบเสร็จน้ำมัน หรือใบแจ้งหนี้ผ่าน LINE เพื่อบันทึกคาร์บอนฟุตพรินต์ของคุณ'),
        ))

    # E02: Scope 3 dominant
    if s3_pct > 70 and total > 0:
        insights.append(_insight(
            'opportunity', 2, 'scope', _L('Scope 3 Dominates Your Footprint', 'Scope 3 เป็นสัดส่วนหลักของการปล่อย'),
            _L(f'Scope 3 accounts for {s3_pct:.0f}% of total emissions. Engage key suppliers for primary emission data — this improves accuracy by 20-30% and reveals reduction opportunities in your value chain.', f'Scope 3 คิดเป็น {s3_pct:.0f}% ของการปล่อยทั้งหมด ลองทำงานร่วมกับซัพพลายเออร์หลักเพื่อขอข้อมูลการปล่อยโดยตรง — ช่วยเพิ่มความแม่นยำ 20-30% และเผยโอกาสลดการปล่อยในห่วงโซ่คุณค่า'),
        ))
    elif s3_pct > 50 and total > 0:
        insights.append(_insight(
            'opportunity', 1, 'scope', _L('Value Chain Emissions Are Significant', 'การปล่อยในห่วงโซ่คุณค่ามีนัยสำคัญ'),
            _L(f'Scope 3 is {s3_pct:.0f}% of total. Consider supplier screening and spend-based analysis to identify high-impact procurement categories.', f'Scope 3 อยู่ที่ {s3_pct:.0f}% ของทั้งหมด ลองคัดกรองซัพพลายเออร์และวิเคราะห์แบบ spend-based เพื่อหาหมวดจัดซื้อที่มีผลกระทบสูง'),
        ))

    # E03: Scope 2 reduction opportunity
    if s2_tco2e > 0 and s2_pct > 25:
        insights.append(_insight(
            'quickwin', 2, 'scope', _L('Renewable Energy Opportunity', 'โอกาสด้านพลังงานหมุนเวียน'),
            _L(f'Scope 2 is {s2_pct:.0f}% ({s2_tco2e:.1f} tCO2e) from purchased electricity. Switching to green tariff, solar PPA, or RECs can reduce market-based Scope 2 to near zero.', f'Scope 2 อยู่ที่ {s2_pct:.0f}% ({s2_tco2e:.1f} tCO2e) จากไฟฟ้าที่ซื้อ การเปลี่ยนไปใช้ไฟเขียว, solar PPA หรือ RECs ช่วยลด Scope 2 แบบ market-based ให้เกือบเป็นศูนย์ได้'),
        ))

    # E04: Scope 1 high — efficiency opportunity
    if s1_pct > 40 and total > 0:
        insights.append(_insight(
            'quickwin', 1, 'scope', _L('Direct Emission Reduction', 'ลดการปล่อยทางตรง'),
            _L(f'Scope 1 is {s1_pct:.0f}% of total. Review fuel efficiency, fleet electrification, refrigerant leak management, and process optimization.', f'Scope 1 อยู่ที่ {s1_pct:.0f}% ของทั้งหมด ทบทวนประสิทธิภาพเชื้อเพลิง การเปลี่ยนยานพาหนะเป็นไฟฟ้า การจัดการการรั่วของสารทำความเย็น และการปรับปรุงกระบวนการ'),
        ))

    # E05: Top emitter concentration
    if top_emitters and total > 0:
        top = top_emitters[0]
        top_pct = top.get('percentage', 0) or 0
        if top_pct > 50:
            savings_10pct = top.get('tco2e', 0) * 0.1
            insights.append(_insight(
                'opportunity', 3, 'emitters', _L(f'Concentrated Emission Source', f'แหล่งปล่อยที่กระจุกตัว'),
                _L(f'"{top["name"]}" accounts for {top_pct:.0f}% of total emissions. A 10% reduction here saves {savings_10pct:.1f} tCO2e — the highest-leverage improvement.', f'"{top["name"]}" คิดเป็น {top_pct:.0f}% ของการปล่อยทั้งหมด การลดเพียง 10% ตรงนี้ช่วยลดได้ {savings_10pct:.1f} tCO2e — เป็นจุดที่คุ้มค่าที่สุด'),
                {'category': top['name'], 'tco2e': top.get('tco2e'), 'savings_10pct': savings_10pct},
            ))
        elif top_pct > 30:
            insights.append(_insight(
                'opportunity', 1, 'emitters', _L(f'Focus Area: {top["name"]}', f'จุดโฟกัส: {top["name"]}'),
                _L(f'Largest source at {top_pct:.0f}% — prioritize reduction initiatives here for maximum impact.', f'แหล่งปล่อยใหญ่สุดที่ {top_pct:.0f}% — ให้ความสำคัญกับการลดตรงนี้เพื่อผลกระทบสูงสุด'),
            ))

    # ═══════════════════════════════════════
    # YEAR-OVER-YEAR RULES
    # ═══════════════════════════════════════

    if yoy_pct is not None:
        if yoy_pct < -20:
            insights.append(_insight(
                'praise', 3, 'hero', _L('Outstanding Emission Reduction!', 'การลดการปล่อยที่ยอดเยี่ยม!'),
                _L(f'Emissions decreased {abs(yoy_pct):.1f}% year-over-year — exceeding most industry peers. This demonstrates strong climate leadership.', f'การปล่อยลดลง {abs(yoy_pct):.1f}% เทียบปีต่อปี — ดีกว่าคู่แข่งส่วนใหญ่ในอุตสาหกรรม แสดงถึงความเป็นผู้นำด้านสภาพภูมิอากาศ'),
            ))
        elif yoy_pct < -5:
            insights.append(_insight(
                'praise', 2, 'hero', _L('Good Progress on Emissions', 'ความคืบหน้าที่ดีในการลดการปล่อย'),
                _L(f'Emissions down {abs(yoy_pct):.1f}% YoY. Keep the momentum — sustained reductions compound into significant long-term impact.', f'การปล่อยลดลง {abs(yoy_pct):.1f}% เทียบปีก่อน รักษาโมเมนตัมไว้ — การลดอย่างต่อเนื่องสะสมเป็นผลกระทบระยะยาวที่สำคัญ'),
            ))
        elif yoy_pct > 20:
            insights.append(_insight(
                'critical', 4, 'hero', _L('Significant Emission Increase', 'การปล่อยเพิ่มขึ้นอย่างมีนัยสำคัญ'),
                _L(f'Emissions increased {yoy_pct:.1f}% year-over-year. Urgent review needed — check if this is from business growth, new operations, or operational inefficiency.', f'การปล่อยเพิ่มขึ้น {yoy_pct:.1f}% เทียบปีต่อปี ต้องทบทวนด่วน — ตรวจสอบว่ามาจากการเติบโตของธุรกิจ การดำเนินงานใหม่ หรือความไม่มีประสิทธิภาพ'),
            ))
        elif yoy_pct > 10:
            insights.append(_insight(
                'alert', 3, 'trend', _L('Emissions Rising', 'การปล่อยกำลังเพิ่มขึ้น'),
                _L(f'Emissions up {yoy_pct:.1f}% YoY. Review energy consumption and new emission sources to identify and address the increase.', f'การปล่อยเพิ่มขึ้น {yoy_pct:.1f}% เทียบปีก่อน ทบทวนการใช้พลังงานและแหล่งปล่อยใหม่ เพื่อหาสาเหตุและจัดการ'),
            ))
        elif yoy_pct > 0:
            insights.append(_insight(
                'alert', 1, 'trend', _L('Slight Emission Increase', 'การปล่อยเพิ่มขึ้นเล็กน้อย'),
                _L(f'Emissions increased {yoy_pct:.1f}%. Determine if this correlates with revenue growth (intensity may still be improving).', f'การปล่อยเพิ่มขึ้น {yoy_pct:.1f}% ตรวจสอบว่าสอดคล้องกับการเติบโตของรายได้หรือไม่ (ความเข้มข้นอาจยังดีขึ้นอยู่)'),
            ))
    elif prev_tco2e == 0 and total > 0:
        insights.append(_insight(
            'opportunity', 1, 'hero', _L('First Year of Reporting', 'ปีแรกของการรายงาน'),
            _L('This is your baseline year. Future reports will show year-over-year progress from this starting point.', 'นี่คือปีฐานของคุณ รายงานในอนาคตจะแสดงความคืบหน้าเทียบปีต่อปีจากจุดเริ่มต้นนี้'),
        ))

    # ═══════════════════════════════════════
    # DATA QUALITY RULES
    # ═══════════════════════════════════════

    if overall_score < 20 and total_entries > 0:
        insights.append(_insight(
            'critical', 4, 'completeness', _L('Critical Data Gaps', 'ข้อมูลขาดหายอย่างวิกฤต'),
            _L(f'Data completeness at only {overall_score:.0f}%. SEC ONE Report and CDP require comprehensive disclosure. Priority: fill Environment pillar data first.', f'ความครบถ้วนข้อมูลอยู่ที่เพียง {overall_score:.0f}% รายงาน SEC ONE และ CDP ต้องการการเปิดเผยที่ครบถ้วน ลำดับแรก: กรอกข้อมูลเสาหลักสิ่งแวดล้อมก่อน'),
        ))
    elif overall_score < 50:
        insights.append(_insight(
            'alert', 2, 'completeness', _L('Improve Data Coverage', 'เพิ่มความครอบคลุมของข้อมูล'),
            _L(f'Completeness at {overall_score:.0f}%. Target 80%+ for credible sustainability reporting and better ESG ratings.', f'ความครบถ้วนอยู่ที่ {overall_score:.0f}% ตั้งเป้า 80%+ เพื่อการรายงานความยั่งยืนที่น่าเชื่อถือและเรตติ้ง ESG ที่ดีขึ้น'),
        ))
    elif overall_score >= 80:
        insights.append(_insight(
            'praise', 2, 'completeness', _L('Excellent Data Coverage', 'ความครอบคลุมข้อมูลยอดเยี่ยม'),
            _L(f'Data completeness at {overall_score:.0f}%! Your ESG data is comprehensive and audit-ready.', f'ความครบถ้วนข้อมูลอยู่ที่ {overall_score:.0f}%! ข้อมูล ESG ของคุณครบถ้วนและพร้อมตรวจสอบ'),
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
                'alert', 3, 'completeness', _L(f'No {p_label} Data', f'ยังไม่มีข้อมูล {p_label}'),
                _L(f'{p_label} pillar at 0% ({p_total} datapoints available). ESG ratings require all three pillars. {tips.get(p_code, "")}', f'เสาหลัก {p_label} อยู่ที่ 0% (มี {p_total} จุดข้อมูล) เรตติ้ง ESG ต้องการครบทั้งสามเสาหลัก {tips.get(p_code, "")}'),
            ))

    # Verification rate
    if verified_pct < 30 and total_entries > 10:
        insights.append(_insight(
            'alert', 2, 'quality', _L('Low Verification Rate', 'อัตราการยืนยันต่ำ'),
            _L(f'Only {verified_pct:.0f}% of entries verified ({pending} pending). Unverified data weakens report credibility and assurance readiness.', f'มีเพียง {verified_pct:.0f}% ของรายการที่ยืนยันแล้ว ({pending} รอตรวจ) ข้อมูลที่ยังไม่ยืนยันลดความน่าเชื่อถือของรายงาน'),
        ))
    elif verified_pct >= 90 and total_entries > 5:
        insights.append(_insight(
            'praise', 1, 'quality', _L('High Data Verification', 'การยืนยันข้อมูลสูง'),
            _L(f'{verified_pct:.0f}% of entries verified — strong data governance for audit and reporting.', f'{verified_pct:.0f}% ของรายการได้รับการยืนยัน — การกำกับข้อมูลที่ดีสำหรับการตรวจสอบและรายงาน'),
        ))

    # AI extraction usage
    if line_pct > 70 and total_entries > 5:
        insights.append(_insight(
            'praise', 1, 'quality', _L('Efficient AI Data Collection', 'การเก็บข้อมูลด้วย AI ที่มีประสิทธิภาพ'),
            _L(f'{line_pct:.0f}% of data captured via AI extraction — scalable and consistent data collection workflow.', f'{line_pct:.0f}% ของข้อมูลถูกดึงด้วย AI — เวิร์กโฟลว์การเก็บข้อมูลที่ขยายได้และสม่ำเสมอ'),
        ))

    # ═══════════════════════════════════════
    # TARGET & PROGRESS RULES
    # ═══════════════════════════════════════

    if not target.get('has_target'):
        insights.append(_insight(
            'critical', 3, 'target', _L('Set Reduction Targets', 'ตั้งเป้าลดการปล่อย'),
            _L('No emission reduction target configured. Set a base year and target aligned with SBTi 1.5°C pathway to demonstrate climate commitment and track progress.', 'ยังไม่ได้ตั้งเป้าลดการปล่อย ตั้งปีฐานและเป้าหมายให้สอดคล้องกับเส้นทาง SBTi 1.5°C เพื่อแสดงความมุ่งมั่นด้านสภาพภูมิอากาศและติดตามความคืบหน้า'),
        ))
    elif target.get('on_track'):
        insights.append(_insight(
            'praise', 3, 'target', _L('On Track for Target!', 'เป็นไปตามเป้าหมาย!'),
            _L(f'Current reduction: {target.get("current_reduction_percent", 0):.1f}% vs target: {target.get("target_percent", 0)}% by {target.get("target_year")}. Excellent progress!', f'ลดได้ปัจจุบัน: {target.get("current_reduction_percent", 0):.1f}% เทียบเป้า: {target.get("target_percent", 0)}% ภายในปี {target.get("target_year")} ความคืบหน้ายอดเยี่ยม!'),
        ))
    elif target.get('has_target') and not target.get('on_track'):
        gap = (target.get('target_percent', 0) or 0) - (target.get('current_reduction_percent', 0) or 0)
        insights.append(_insight(
            'alert', 3, 'target', _L('Behind Reduction Target', 'ตามหลังเป้าลดการปล่อย'),
            _L(f'Current reduction {target.get("current_reduction_percent", 0):.1f}% vs target {target.get("target_percent", 0)}% — {gap:.1f}% gap to close. Accelerate initiatives.', f'ลดได้ปัจจุบัน {target.get("current_reduction_percent", 0):.1f}% เทียบเป้า {target.get("target_percent", 0)}% — ยังห่าง {gap:.1f}% เร่งดำเนินมาตรการ'),
        ))

    # ═══════════════════════════════════════
    # FINANCIAL IMPACT RULES
    # ═══════════════════════════════════════

    carbon_tax_mid = (pl.get('carbon_tax', {}).get('mid', 0) or 0)
    if carbon_tax_mid > 100000:
        insights.append(_insight(
            'alert', 2, 'pl_impact', _L('Significant Carbon Tax Exposure', 'ความเสี่ยงภาษีคาร์บอนสูง'),
            _L(f'Estimated carbon tax at $75/tCO2e: ${carbon_tax_mid:,.0f}/yr. Every 10% reduction saves ${carbon_tax_mid * 0.1:,.0f}.', f'ภาษีคาร์บอนประมาณการที่ $75/tCO2e: ${carbon_tax_mid:,.0f}/ปี ทุก ๆ การลด 10% ประหยัดได้ ${carbon_tax_mid * 0.1:,.0f}'),
            {'carbon_tax_mid': carbon_tax_mid},
        ))

    savings = (pl.get('savings_from_reduction', {}).get('value', 0) or 0)
    if savings > 0:
        insights.append(_insight(
            'praise', 1, 'pl_impact', _L('Carbon Cost Savings', 'ประหยัดต้นทุนคาร์บอน'),
            _L(f'YoY emission reduction saves an estimated ${savings:,.0f}/yr in potential carbon costs at $75/tCO2e.', f'การลดการปล่อยเทียบปีก่อนช่วยประหยัดประมาณ ${savings:,.0f}/ปี ในต้นทุนคาร์บอนที่อาจเกิดขึ้นที่ $75/tCO2e'),
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
            'critical', 3, 'framework', _L('GHG Protocol Foundation Missing', 'ยังขาดรากฐาน GHG Protocol'),
            _L(f'GHG Protocol coverage at {ghg:.0f}%. This is the foundation for all carbon reporting. Focus on Scope 1 & 2 data first.', f'ความครอบคลุม GHG Protocol อยู่ที่ {ghg:.0f}% นี่คือรากฐานของการรายงานคาร์บอนทั้งหมด เน้นข้อมูล Scope 1 และ 2 ก่อน'),
        ))
    elif ghg >= 70:
        insights.append(_insight(
            'praise', 1, 'framework', _L('Strong GHG Protocol Alignment', 'สอดคล้องกับ GHG Protocol อย่างแข็งแกร่ง'),
            _L(f'GHG Protocol at {ghg:.0f}% — well-positioned for carbon reporting and TGO CFO certification.', f'GHG Protocol อยู่ที่ {ghg:.0f}% — อยู่ในตำแหน่งที่ดีสำหรับการรายงานคาร์บอนและการรับรอง TGO CFO'),
        ))

    if gri >= 60:
        insights.append(_insight(
            'praise', 1, 'framework', _L('GRI Reporting Ready', 'พร้อมรายงานตาม GRI'),
            _L(f'GRI Standards alignment at {gri:.0f}% — strong position for publishing a sustainability report.', f'ความสอดคล้องกับ GRI Standards อยู่ที่ {gri:.0f}% — อยู่ในตำแหน่งที่ดีสำหรับการเผยแพร่รายงานความยั่งยืน'),
        ))

    if cdp < 40 and cdp > 0:
        insights.append(_insight(
            'quickwin', 2, 'framework', _L('Boost CDP Score Quickly', 'เพิ่มคะแนน CDP ได้เร็ว'),
            _L('Add Scope 2 electricity data, governance disclosures, and reduction targets to improve CDP from D/C to B level.', 'เพิ่มข้อมูลไฟฟ้า Scope 2, การเปิดเผยด้านธรรมาภิบาล และเป้าลดการปล่อย เพื่อยกระดับ CDP จาก D/C เป็น B'),
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
                    'alert', 2, 'trend', _L(f'Emission Spike in {peak_month}', f'การปล่อยพุ่งสูงในเดือน {peak_month}'),
                    _L(f'{peak_month} had {peak:.1f} tCO2e — more than 2x the monthly average ({avg:.1f}). Investigate if this is seasonal, one-time, or systemic.', f'{peak_month} มีการปล่อย {peak:.1f} tCO2e — มากกว่าค่าเฉลี่ยรายเดือน 2 เท่า ({avg:.1f}) ตรวจสอบว่าเป็นฤดูกาล ครั้งเดียว หรือเชิงระบบ'),
                ))

            # Declining trend (last 3 months)
            last_3 = values[-3:]
            if len(last_3) == 3 and last_3[0] > 0 and last_3[1] > 0 and last_3[2] > 0:
                if last_3[0] > last_3[1] > last_3[2]:
                    insights.append(_insight(
                        'praise', 2, 'trend', _L('Declining Emission Trend', 'แนวโน้มการปล่อยลดลง'),
                        _L('Emissions have decreased for 3 consecutive months — your reduction efforts are producing results.', 'การปล่อยลดลงต่อเนื่อง 3 เดือน — ความพยายามลดการปล่อยของคุณเห็นผลแล้ว'),
                    ))

        # Zero-data months
        zero_months = sum(1 for v in values if v == 0)
        if zero_months > 6 and total_entries > 0:
            insights.append(_insight(
                'alert', 2, 'trend', _L('Months with Missing Data', 'เดือนที่ข้อมูลขาดหาย'),
                _L(f'{zero_months} months have zero emissions data. Are emissions truly zero, or is data not being collected for these months?', f'มี {zero_months} เดือนที่ไม่มีข้อมูลการปล่อย การปล่อยเป็นศูนย์จริง หรือยังไม่ได้เก็บข้อมูลในเดือนเหล่านี้?'),
            ))

    # ═══════════════════════════════════════
    # SCOPE 3 DETAIL RULES
    # ═══════════════════════════════════════

    if scope3:
        # Find dominant Scope 3 category
        if scope3[0].get('percentage', 0) > 50:
            top_s3 = scope3[0]
            insights.append(_insight(
                'opportunity', 2, 'scope3', _L(f'Scope 3 Dominated by {top_s3["name"]}', f'Scope 3 ถูกครอบงำโดย {top_s3["name"]}'),
                _L(f'{top_s3["name"]} is {top_s3["percentage"]:.0f}% of Scope 3. Focus supplier engagement and data collection here for the biggest impact.', f'{top_s3["name"]} คิดเป็น {top_s3["percentage"]:.0f}% ของ Scope 3 เน้นการทำงานกับซัพพลายเออร์และเก็บข้อมูลตรงนี้เพื่อผลกระทบสูงสุด'),
            ))

        # Categories with zero data
        if len(scope3) < 5 and s3_pct > 0:
            insights.append(_insight(
                'alert', 1, 'scope3', _L('Incomplete Scope 3 Coverage', 'ความครอบคลุม Scope 3 ยังไม่ครบ'),
                _L(f'Only {len(scope3)} of 15 Scope 3 categories have data. Screen remaining categories to ensure no material emissions are missing.', f'มีเพียง {len(scope3)} จาก 15 หมวด Scope 3 ที่มีข้อมูล คัดกรองหมวดที่เหลือเพื่อให้แน่ใจว่าไม่มีการปล่อยที่มีนัยสำคัญตกหล่น'),
            ))

    # Localize the type labels (eyebrow tags) for Thai.
    if is_th:
        label_th = {
            'Quick Win': 'ลดได้เร็ว',
            'Opportunity': 'โอกาส',
            'Attention': 'ควรระวัง',
            'Critical': 'วิกฤต',
            'Achievement': 'ความสำเร็จ',
            'Benchmark': 'เทียบเคียง',
        }
        for ins in insights:
            ins['label'] = label_th.get(ins['label'], ins['label'])

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
