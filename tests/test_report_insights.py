"""Period comparison + recommendation rules for the waste report (report_insights).

The report compares the selected range with the same range a year earlier (yearly) or a
month earlier (monthly), and picks advice for the report mode: building owner (location),
tenant, or event/activity (tag). These pin the parts that are easy to break silently:
the period arithmetic, the rules file compiling in every mode, mode isolation, and that
every shown item carries a filled-in reason.
"""
from datetime import date

import pytest

from GEPPPlatform.services.cores.reports.report_insights import (
    MODES,
    build_report_insights,
    comparison_periods,
    compute_metrics,
    eval_expr,
    format_value,
    load_rules,
    range_label,
    render_template,
    shift_months,
    shift_years,
)

TODAY = date(2026, 9, 29)
SECTIONS = ('risks', 'opportunities', 'quickwins')


def _rec(d, kg, cat='General Waste', mm='General Waste', mat_en='General Waste', mat_th='ขยะทั่วไป',
         tx=1, group=None, group_name=None):
    return {'date': d, 'kg': kg, 'category_en': cat, 'main_material_en': mm,
            'material_en': mat_en, 'material_th': mat_th, 'tx_id': tx,
            'group_id': group, 'group_name': group_name}


def _office_tenant():
    """The One Bangkok feedback export: an office tenant, Aug 2569, no hazardous waste."""
    return [
        _rec(date(2026, 8, 5), 40.0),
        _rec(date(2026, 8, 6), 18.14, cat='Organic Waste', mm='Non-Specific Organic Waste',
             mat_en='Organic and Food Waste', mat_th='ขยะอินทรีย์และเศษอาหาร', tx=2),
        _rec(date(2026, 8, 7), 5.58, cat='Recyclable Waste', mm='Paper', mat_en='Mixed Paper',
             mat_th='กระดาษรวม (จับจั๊ว)', tx=3),
        _rec(date(2026, 8, 8), 4.96, cat='Recyclable Waste', mm='Paper',
             mat_en='Brown Paper Box / Carton / Cardboard', mat_th='กระดาษลังสีน้ำตาล', tx=4),
        _rec(date(2026, 8, 9), 2.04, cat='Recyclable Waste', mm='Non-Specific Recyclables',
             mat_en='Recyclable Material', mat_th='วัสดุรีไซเคิลรวม', tx=5),
    ]


AUG = (date(2026, 8, 1), date(2026, 8, 31))
AUG_PREV_YEAR = (date(2025, 8, 1), date(2025, 8, 31))


def _insights(cur, prev=(), period=AUG, prev_period=AUG_PREV_YEAR, mode='location', compare_mode='yearly'):
    return build_report_insights(list(cur), list(prev), *period, *prev_period, TODAY,
                                 mode=mode, compare_mode=compare_mode)


def _ids(out):
    return {i['id'] for key in SECTIONS for i in out['scores'][key]}


# --- Periods ---------------------------------------------------------------------------

def test_yearly_compares_the_same_days_last_year():
    assert comparison_periods(date(2026, 7, 13), date(2026, 8, 30), TODAY, 'yearly') == \
        (date(2026, 7, 13), date(2026, 8, 30), date(2025, 7, 13), date(2025, 8, 30))


def test_monthly_compares_the_same_days_last_month():
    assert comparison_periods(date(2026, 8, 13), date(2026, 8, 30), TODAY, 'monthly') == \
        (date(2026, 8, 13), date(2026, 8, 30), date(2026, 7, 13), date(2026, 7, 30))


def test_future_end_is_clamped_to_today_on_both_sides():
    # Sep 1–30 viewed on Sep 29: compare 1–29 with 1–29, not a full month with a partial one.
    assert comparison_periods(date(2026, 9, 1), date(2026, 9, 30), TODAY, 'monthly') == \
        (date(2026, 9, 1), date(2026, 9, 29), date(2026, 8, 1), date(2026, 8, 29))


def test_date_shifts_clamp_to_real_days():
    assert shift_years(date(2028, 2, 29), -1) == date(2027, 2, 28)
    assert shift_months(date(2026, 3, 31), -1) == date(2026, 2, 28)
    assert shift_months(date(2026, 1, 15), -1) == date(2025, 12, 15)


def test_range_labels():
    assert range_label(date(2026, 8, 13), date(2026, 8, 30), 'th') == '13–30 ส.ค. 2569'
    assert range_label(date(2026, 7, 13), date(2026, 8, 30), 'th') == '13 ก.ค. – 30 ส.ค. 2569'
    assert range_label(date(2026, 7, 13), date(2026, 8, 30), 'en') == '13 Jul – 30 Aug 2026'


# --- Rules file ------------------------------------------------------------------------

@pytest.mark.parametrize('mode', MODES)
def test_every_rule_compiles_and_every_placeholder_resolves(mode):
    """A typo in the rules file must fail here, not silently hide a rule in production."""
    rules = load_rules()
    cur = _office_tenant() + [_rec(date(2026, 8, 10), 3.0, group=7, group_name='Andaz', tx=9)]
    prev = [_rec(date(2025, 8, 5), 30.0)]
    num, txt = compute_metrics(cur, prev, *AUG, *AUG_PREV_YEAR, TODAY, 'yearly')
    to_render = [r for r in rules['rules'] if mode in r['modes']]
    to_render += list(rules['fallback'][mode].values()) + [rules['fallback']['no_data']]
    for rule in to_render:
        if 'when' in rule:
            eval_expr(rule['when'], num)
            eval_expr(str(rule['priority']), num)
        for lang in ('th', 'en'):
            parts = [rule['title'][lang], rule['reason'][lang], *rule['bullets'][lang]]
            for part in parts:
                assert '{' not in render_template(part, num, txt[lang], lang), (rule.get('id'), part)


def test_rule_ids_unique_sections_and_modes_valid():
    rules = load_rules()
    ids = [r['id'] for r in rules['rules']]
    assert len(ids) == len(set(ids))
    for r in rules['rules']:
        assert r['section'] in ('risk', 'opportunity', 'quickwin')
        assert r['modes'] and set(r['modes']) <= set(MODES)
    for mode in MODES:
        assert set(rules['fallback'][mode]) == {'risk', 'opportunity', 'quickwin'}
        for section in ('risk', 'opportunity', 'quickwin'):
            assert any(r['section'] == section and mode in r['modes'] for r in rules['rules'])


# --- Selection -------------------------------------------------------------------------

def test_mostly_general_waste_picks_the_rule_for_the_mode():
    recs = [_rec(date(2026, 8, d), 8.0) for d in range(1, 6)] + \
           [_rec(date(2026, 8, 6), 5.0, cat='Recyclable Waste', mm='Paper', tx=2)]
    assert 'L-R05' in _ids(_insights(recs, mode='location'))
    assert 'T-R05' in _ids(_insights(recs, mode='tenant'))
    assert 'E-R05' in _ids(_insights(recs, mode='tag'))


@pytest.mark.parametrize('mode,prefixes', [('location', ('L-',)), ('tenant', ('T-', 'L-')), ('tag', ('E-', 'L-'))])
def test_modes_never_leak_rules(mode, prefixes):
    rules = {r['id']: r for r in load_rules()['rules']}
    out = _insights(_office_tenant(), mode=mode)
    for rid in _ids(out):
        if rid.startswith('fallback_'):
            continue
        assert rid.startswith(prefixes) and mode in rules[rid]['modes']


def test_office_tenant_gets_tenant_actionable_advice_only():
    out = _insights(_office_tenant(), mode='tenant')
    ids = _ids(out)
    assert not ids & {'T-R07', 'L-R08', 'L-R09', 'L-Q08', 'L-O06'}   # nothing hazardous / construction
    assert 'T-O01' in ids or 'T-O02' in ids                          # paper / food are its top streams
    for key in SECTIONS:
        items = out['scores'][key]
        assert 1 <= len(items) <= 2
        for it in items:
            assert it['reason_th'] and it['reason_en']
            assert '{' not in it['reason_th'] + it['reason_en'] + it['title_th'] + it['title_en']


def test_trend_rule_fires_against_last_year():
    cur = [_rec(date(2026, 8, d), 13.0) for d in range(1, 11)] + \
          [_rec(date(2026, 8, d), 13.0, cat='Recyclable Waste', mm='Paper', tx=2) for d in range(1, 11)]
    prev = [_rec(date(2025, 8, d), 10.0) for d in range(1, 11)] + \
           [_rec(date(2025, 8, d), 10.0, cat='Recyclable Waste', mm='Paper', tx=2) for d in range(1, 11)]
    out = _insights(cur, prev)
    risk = out['scores']['risks'][0]
    assert risk['id'] == 'L-R01'
    assert '30.0%' in risk['reason_th']
    assert out['scores']['metrics']['change_pct'] == pytest.approx(30.0)


def test_monthly_mode_labels_the_previous_month():
    cur = [_rec(date(2026, 8, 20), 10.0)]
    prev = [_rec(date(2026, 7, 20), 8.0)]
    out = _insights(cur, prev, period=(date(2026, 8, 13), date(2026, 8, 30)),
                    prev_period=(date(2026, 7, 13), date(2026, 7, 30)), compare_mode='monthly')
    assert out['labels']['th'] == {'cur_label': '13–30 ส.ค. 2569', 'prev_label': '13–30 ก.ค. 2569'}
    assert out['scores']['metrics']['prev_kg'] == 8.0


@pytest.mark.parametrize('mode,rid', [('location', 'L-R07'), ('tenant', 'T-R07'), ('tag', 'E-R07')])
def test_hazardous_is_always_flagged(mode, rid):
    recs = [_rec(date(2026, 8, 3), 20.0),
            _rec(date(2026, 8, 3), 25.0, cat='Recyclable Waste', mm='Paper', tx=2),
            _rec(date(2026, 8, 4), 0.3, cat='Hazardous Waste', mm='Batteries', mat_en='Battery',
                 mat_th='ถ่านไฟฉาย', tx=3)]
    assert rid in {i['id'] for i in _insights(recs, mode=mode)['scores']['risks']}


def test_tag_mode_reads_groups():
    paper = dict(cat='Recyclable Waste', mm='Paper', mat_en='Mixed Paper', mat_th='กระดาษรวม')
    recs = [_rec(date(2026, 8, 3), 30.0, group=1, group_name='Run 2026', **paper),
            _rec(date(2026, 8, 4), 5.0, group=2, group_name='Fair', **paper),
            _rec(date(2026, 8, 5), 15.0, **paper)]                          # no tag
    m = _insights(recs, mode='tag')['scores']['metrics']
    assert m['group_count'] == 2
    assert m['top_group_share'] == pytest.approx(60.0)
    assert m['unassigned_share'] == pytest.approx(30.0)
    assert 'E-Q07' in {i['id'] for i in _insights(recs, mode='tag')['scores']['quickwins']}


def test_no_data_uses_the_no_data_note_everywhere():
    out = _insights([], mode='tenant')
    for key in SECTIONS:
        assert len(out['scores'][key]) == 1 and out['scores'][key][0]['fallback']


def test_one_rule_per_group_and_at_most_two():
    recs = [_rec(date(2026, 8, 3), 80.0), _rec(date(2026, 8, 4), 5.0, cat='Recyclable Waste', mm='Paper')]
    for mode in MODES:
        out = _insights(recs, mode=mode)
        for key in SECTIONS:
            groups = [i['group'] for i in out['scores'][key] if i['group']]
            assert len(groups) == len(set(groups))
            assert len(out['scores'][key]) <= 2


def test_tiny_shares_do_not_read_as_zero():
    assert format_value(0.016, 'pct', 'th') == '<0.1%'
    assert format_value(0.0, 'pct', 'th') == '0.0%'
    assert format_value(12.345, 'pct', 'en') == '12.3%'
