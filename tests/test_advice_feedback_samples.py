"""B5: advice feedback carries the inputs that produced the advice (training samples)."""
from GEPPPlatform.services.cores.reports.report_insights import (
    evaluate_rules, load_rules, rule_input_names, rule_sample, rules_fingerprint,
)


def _rule(rid):
    return next(r for r in load_rules()['rules'] if r['id'] == rid)


TXT = {'th': {'prev_label': 'ปีก่อน', 'cur_label': 'ปีนี้'}, 'en': {'prev_label': 'last year', 'cur_label': 'this year'}}


def test_input_names_cover_condition_priority_and_text():
    names = rule_input_names(_rule('T-O02'))
    assert {'organic_rank', 'organic_pct', 'organic_kg'} <= set(names)


def test_sample_is_self_contained():
    num = {'organic_rank': 1, 'organic_pct': 59.22, 'organic_kg': 9304.6, 'unrelated': 1}
    s = rule_sample(_rule('T-O02'), num, TXT)
    assert s['inputs'] == {'organic_kg': 9304.6, 'organic_pct': 59.22, 'organic_rank': 1}
    assert s['condition_holds'] is True
    assert s['priority'] == 45 + 59.22
    assert s['rule']['when'] and s['rendered']['th']['title']
    assert '59.22' in s['rendered']['th']['reason'] or '59.2' in s['rendered']['th']['reason']


def test_evaluate_records_every_match_with_shown_flag():
    from tests.test_report_insights import _insights, _office_tenant
    out = _insights(_office_tenant(), mode='tenant')
    scores = out['scores']
    ev = scores['evaluated']
    shown = {e['id'] for e in ev if e['shown']}
    picked = {i['id'] for k in ('risks', 'opportunities', 'quickwins') for i in scores[k] if not i.get('fallback')}
    assert shown == picked
    assert all(e['dropped'] in (None, 'group', 'max_items') for e in ev)
    assert scores['rules_version'].startswith('v')
    # the text values used by templates travel with the snapshot
    assert 'cur_label' in out['txt']['th']


def test_fingerprint_changes_with_rules():
    doc = load_rules()
    a = rules_fingerprint(doc)
    doc2 = {**doc, 'rules': doc['rules'][:-1]}
    assert a != rules_fingerprint(doc2) and a.startswith(f"v{doc.get('version')}-")
