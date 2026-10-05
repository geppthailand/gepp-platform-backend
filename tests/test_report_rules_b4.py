"""B4 (2 Oct review): recommendations that contradicted the data they were shown next to."""
from GEPPPlatform.services.cores.reports.report_insights import load_rules, eval_expr


def _rule(rid):
    return next(r for r in load_rules()['rules'] if r['id'] == rid)


BASE = {
    'has_data': True, 'total_kg': 200, 'paper_rank': 1, 'paper_pct': 30, 'general_pct': 45,
    'general_kg': 90, 'diversion_kg': 70, 'diversion_pct': 35,
}


def test_reduce_paper_skipped_when_sorting_is_already_strong():
    assert eval_expr(_rule('T-O01')['when'], BASE)
    assert not eval_expr(_rule('T-O01')['when'], {**BASE, 'diversion_pct': 70})
    assert not eval_expr(_rule('E-O03')['when'], {**BASE, 'diversion_pct': 70})


def test_bin_pairing_only_when_sorting_is_poor():
    assert eval_expr(_rule('T-Q03')['when'], BASE)
    assert not eval_expr(_rule('T-Q03')['when'], {**BASE, 'diversion_pct': 45})


def test_general_waste_target_has_no_fixed_percentage():
    bullets = _rule('T-O05')['bullets']
    assert not any('5–10%' in b for b in bullets['th'] + bullets['en'])
    assert any('{general_pct:pct}' in b for b in bullets['th'])
