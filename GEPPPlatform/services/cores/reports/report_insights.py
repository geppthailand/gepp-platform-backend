"""
Comparison metrics + rule-based recommendations for the waste report.

Feeds the Compare tab (web) and the comparison pages of the PDF export. The selected
period is compared with the SAME period one year earlier (compare_mode "yearly") or one
month earlier (compare_mode "monthly"); both periods are clamped to today by the caller,
so "this year so far" is never set against a whole previous year.

Recommendations come from GEPPCriteria/recommendations/report_rules.json. Each rule names
the report modes it belongs to:
  location — the building owner/operator's view (they control bins, contracts, spaces)
  tenant   — an occupant's view (what a tenant can do themselves, or ask the building for)
  tag      — an event / tagged-area view (situation-level advice)

Everything here is pure: callers hand in plain record dicts, nothing touches the DB.

Record shape:
    {
      'date': datetime.date,       # local calendar date of the weighing
      'kg': float,
      'category_en': str,          # material category name (English)
      'main_material_en': str,     # main material name (English)
      'material_en': str,
      'material_th': str,
      'tx_id': int | None,
      'group_id': int | None,      # tag / tenant id in those modes (None = unassigned)
      'group_name': str | None,
    }
"""
from __future__ import annotations

import ast
import calendar
import hashlib
import json
import logging
import math
import os
import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

MONTHS_EN = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
MONTHS_TH = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.']
LANGS = ('th', 'en')
MODES = ('location', 'tenant', 'tag')

# Section key in the rules file -> key in the API payload.
SECTION_KEYS = {'risk': 'risks', 'opportunity': 'opportunities', 'quickwin': 'quickwins'}

CATEGORY_KEYS = (
    'general', 'recyclable', 'organic', 'hazardous', 'bio_hazardous',
    'electronic', 'construction', 'wte', 'rubber', 'other',
)

# Waste streams people recognise ("which 2-3 kinds of waste do we produce most"). Mixes
# category-level streams (general, food) with material-level ones (paper, plastic) on
# purpose: that is how people describe their own bins.
RANKED_STREAMS = (
    'general', 'organic', 'paper', 'plastic', 'glass', 'metal',
    'hazardous', 'electronic', 'construction', 'wte',
)
STREAM_NAMES = {
    'general': {'th': 'ขยะทั่วไป', 'en': 'general waste'},
    'organic': {'th': 'ขยะอินทรีย์/เศษอาหาร', 'en': 'organic/food waste'},
    'paper': {'th': 'กระดาษ', 'en': 'paper'},
    'plastic': {'th': 'พลาสติก', 'en': 'plastic'},
    'glass': {'th': 'แก้ว', 'en': 'glass'},
    'metal': {'th': 'โลหะ', 'en': 'metal'},
    'hazardous': {'th': 'ขยะอันตราย', 'en': 'hazardous waste'},
    'electronic': {'th': 'ขยะอิเล็กทรอนิกส์', 'en': 'e-waste'},
    'construction': {'th': 'ขยะก่อสร้าง', 'en': 'construction waste'},
    'wte': {'th': 'ขยะเผาทำเชื้อเพลิง', 'en': 'waste-to-energy'},
}
COMPARE_WORDS = {
    'yearly': {'th': 'ช่วงเดียวกันของปีก่อน', 'en': 'the same period last year'},
    'monthly': {'th': 'ช่วงเดียวกันของเดือนก่อน', 'en': 'the same days last month'},
}

# A month counts as "up" in the consecutive-growth streak only past this kg/day step, so
# ordinary noise doesn't build a streak.
STREAK_STEP = 1.05

_DEFAULT_RULES_CANDIDATES = (
    # .../GEPPPlatform/services/cores/reports -> <backend>/GEPPCriteria
    os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'GEPPCriteria', 'recommendations', 'report_rules.json'),
    os.path.join(os.path.dirname(__file__), '..', '..', '..', 'GEPPCriteria', 'recommendations', 'report_rules.json'),
    os.path.join('GEPPCriteria', 'recommendations', 'report_rules.json'),
)


# ---------------------------------------------------------------------------
# Dates and labels
# ---------------------------------------------------------------------------

def month_label(year: int, month: int, lang: str) -> str:
    if lang == 'th':
        return f"{MONTHS_TH[month - 1]} {year + 543}"
    return f"{MONTHS_EN[month - 1]} {year}"


def date_label(d: date, lang: str) -> str:
    if lang == 'th':
        return f"{d.day} {MONTHS_TH[d.month - 1]} {d.year + 543}"
    return f"{d.day} {MONTHS_EN[d.month - 1]} {d.year}"


def range_label(start: date, end: date, lang: str) -> str:
    """'13–30 ส.ค. 2569' / '13 ก.ค. – 30 ส.ค. 2569' / '13 Jul – 30 Aug 2026'."""
    months = MONTHS_TH if lang == 'th' else MONTHS_EN
    yr = (lambda y: y + 543) if lang == 'th' else (lambda y: y)
    if start == end:
        return date_label(start, lang)
    if start.year == end.year and start.month == end.month:
        return f"{start.day}–{end.day} {months[end.month - 1]} {yr(end.year)}"
    if start.year == end.year:
        return f"{start.day} {months[start.month - 1]} – {end.day} {months[end.month - 1]} {yr(end.year)}"
    return f"{date_label(start, lang)} – {date_label(end, lang)}"


def _days_in_month(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def shift_years(d: date, years: int) -> date:
    """Same calendar date N years away; 29 Feb falls back to 28 Feb."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def shift_months(d: date, months: int) -> date:
    """Same day number N months away, clamped to the target month's length (31 → 30/28)."""
    idx = d.year * 12 + (d.month - 1) + months
    y, m = divmod(idx, 12)
    m += 1
    return date(y, m, min(d.day, _days_in_month(y, m)))


def comparison_periods(start: date, end: date, today: date, compare_mode: str) -> Tuple[date, date, date, date]:
    """(cur_start, cur_end, prev_start, prev_end). The current period is clamped to today and
    the previous one mirrors the clamped range, so both cover the same days."""
    cur_end = min(end, today) if start <= today else end
    shift = (lambda d: shift_years(d, -1)) if compare_mode == 'yearly' else (lambda d: shift_months(d, -1))
    return start, cur_end, shift(start), shift(cur_end)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def category_key(name_en: Optional[str]) -> str:
    n = (name_en or '').lower()
    if 'bio' in n and 'hazard' in n:
        return 'bio_hazardous'
    if 'hazard' in n:
        return 'hazardous'
    if 'recycl' in n:
        return 'recyclable'
    if 'organic' in n:
        return 'organic'
    if 'general' in n:
        return 'general'
    if 'electronic' in n:
        return 'electronic'
    if 'construction' in n:
        return 'construction'
    if 'energy' in n:
        return 'wte'
    if 'rubber' in n:
        return 'rubber'
    return 'other'


def material_streams(main_material_en: Optional[str], material_en: Optional[str], material_th: Optional[str]) -> set:
    """Material-level streams a record belongs to (can be several, e.g. paper + cardboard)."""
    mm = (main_material_en or '').lower()
    en = (material_en or '').lower()
    th = material_th or ''
    out = set()
    # "Non-Specific Organic/General" are still their own stream (food, landfill) — only
    # unspecified recyclables/e-waste/hazardous say the bins weren't sorted finely.
    unspecified = (mm.startswith('non-specific') or mm.startswith('non specific')) \
        and 'organic' not in mm and 'general' not in mm
    if unspecified:
        out.add('unspecified')
        if 'recycl' in mm:
            out.add('unspecified_recyclable')
    if 'paper' in mm:
        out.add('paper')
        if 'mixed' in en or 'จับจั๊ว' in th:
            out.add('mixed_paper')
        if 'cardboard' in en or 'carton' in en or 'ลัง' in th:
            out.add('cardboard')
    if 'plastic' in mm:
        out.add('contaminated_plastic' if 'contaminated' in mm else 'plastic')
    if 'glass' in mm:
        out.add('glass')
    if 'metal' in mm:
        out.add('metal')
    return out


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _pct(part: float, whole: float) -> float:
    return round(part / whole * 100.0, 2) if whole > 0 else 0.0


def _in_range(records: List[Dict[str, Any]], start: date, end: date) -> List[Dict[str, Any]]:
    return [
        r for r in records
        if isinstance(r.get('date'), date) and start <= r['date'] <= end and float(r.get('kg') or 0) > 0
    ]


def _category_totals(records: List[Dict[str, Any]]) -> Dict[str, float]:
    cats = {k: 0.0 for k in CATEGORY_KEYS}
    for r in records:
        cats[category_key(r.get('category_en'))] += float(r['kg'])
    return cats


def _monthly_series(records: List[Dict[str, Any]], start: date, end: date) -> List[Dict[str, Any]]:
    """Months of the current period with kg and days covered (for streak / gap rules)."""
    out = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        first = max(start, date(y, m, 1))
        last = min(end, date(y, m, _days_in_month(y, m)))
        out.append({'year': y, 'month': m, 'kg': 0.0, 'days': (last - first).days + 1})
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    idx = {(mo['year'], mo['month']): mo for mo in out}
    for r in records:
        mo = idx.get((r['date'].year, r['date'].month))
        if mo is not None:
            mo['kg'] += float(r['kg'])
    return out


def compute_metrics(cur: List[Dict[str, Any]], prev: List[Dict[str, Any]],
                    cur_start: date, cur_end: date, prev_start: date, prev_end: date,
                    today: date, compare_mode: str) -> Tuple[Dict[str, Any], Dict[str, Dict[str, str]]]:
    """Numbers (language-neutral) + text labels per language, for conditions and templates."""
    num: Dict[str, Any] = {}
    txt: Dict[str, Dict[str, str]] = {lang: {} for lang in LANGS}

    total = sum(float(r['kg']) for r in cur)
    num['total_kg'] = num['cur_kg'] = round(total, 2)
    num['record_count'] = len(cur)
    num['tx_count'] = len({r.get('tx_id') for r in cur if r.get('tx_id') is not None})
    num['has_data'] = total > 0
    num['active_days'] = len({r['date'] for r in cur})

    cats = _category_totals(cur)
    streams: Dict[str, float] = {}
    for r in cur:
        for s in material_streams(r.get('main_material_en'), r.get('material_en'), r.get('material_th')):
            streams[s] = streams.get(s, 0.0) + float(r['kg'])

    for k in CATEGORY_KEYS:
        num[f'{k}_kg'] = round(cats[k], 2)
        num[f'{k}_pct'] = _pct(cats[k], total)
    diversion = cats['recyclable'] + cats['organic']
    num['diversion_kg'] = round(diversion, 2)
    num['diversion_pct'] = _pct(diversion, total)

    for s in ('paper', 'plastic', 'contaminated_plastic', 'glass', 'metal', 'unspecified',
              'unspecified_recyclable', 'mixed_paper', 'cardboard'):
        num[f'{s}_kg'] = round(streams.get(s, 0.0), 2)
        num[f'{s}_pct'] = _pct(streams.get(s, 0.0), total)
    num['glass_metal_kg'] = round(streams.get('glass', 0.0) + streams.get('metal', 0.0), 2)
    num['glass_metal_pct'] = _pct(streams.get('glass', 0.0) + streams.get('metal', 0.0), total)
    num['unspecified_recyclable_share'] = _pct(streams.get('unspecified_recyclable', 0.0), cats['recyclable'])
    num['contaminated_plastic_share'] = _pct(
        streams.get('contaminated_plastic', 0.0),
        streams.get('plastic', 0.0) + streams.get('contaminated_plastic', 0.0),
    )
    num['mixed_paper_share'] = _pct(streams.get('mixed_paper', 0.0), streams.get('paper', 0.0))

    # Stream ranking (1 = largest). Absent streams rank 99 so "rank <= 3" never matches them.
    rank_values = {
        'general': cats['general'], 'organic': cats['organic'],
        'paper': streams.get('paper', 0.0),
        'plastic': streams.get('plastic', 0.0) + streams.get('contaminated_plastic', 0.0),
        'glass': streams.get('glass', 0.0), 'metal': streams.get('metal', 0.0),
        'hazardous': cats['hazardous'], 'electronic': cats['electronic'],
        'construction': cats['construction'], 'wte': cats['wte'],
    }
    ranked = sorted([(k, v) for k, v in rank_values.items() if v > 0], key=lambda kv: kv[1], reverse=True)
    for k in RANKED_STREAMS:
        num[f'{k}_rank'] = 99
    for i, (k, _v) in enumerate(ranked):
        num[f'{k}_rank'] = i + 1
    for lang in LANGS:
        txt[lang]['top_stream_label'] = STREAM_NAMES[ranked[0][0]][lang] if ranked else ''
        txt[lang]['top3_labels'] = ', '.join(STREAM_NAMES[k][lang] for k, _ in ranked[:3])

    # --- Current vs previous period --------------------------------------------------
    prev_total = sum(float(r['kg']) for r in prev)
    num['prev_kg'] = round(prev_total, 2)
    num['has_prev'] = prev_total > 0
    num['change_kg'] = round(total - prev_total, 2)
    num['change_pct'] = round((total - prev_total) / prev_total * 100.0, 2) if prev_total > 0 else 0.0
    num['change_pct_abs'] = abs(num['change_pct'])
    prev_cats = _category_totals(prev)
    for k in ('general', 'recyclable', 'organic', 'hazardous'):
        num[f'{k}_cur_kg'] = round(cats[k], 2)
        num[f'{k}_prev_kg'] = round(prev_cats[k], 2)
        num[f'{k}_has_prev'] = prev_cats[k] > 0
        num[f'{k}_change_pct'] = round((cats[k] - prev_cats[k]) / prev_cats[k] * 100.0, 2) if prev_cats[k] > 0 else 0.0
    num['diversion_pct_prev'] = _pct(prev_cats['recyclable'] + prev_cats['organic'], prev_total)
    num['diversion_change_pts'] = round(num['diversion_pct'] - num['diversion_pct_prev'], 2) if prev_total > 0 and total > 0 else 0.0

    # --- Monthly shape of the current period ------------------------------------------
    months = _monthly_series(cur, cur_start, cur_end)
    with_data = [mo for mo in months if mo['kg'] > 0]
    num['months_with_data'] = len(with_data)
    streak = 0
    if with_data:
        i = months.index(with_data[-1])
        while i - 1 >= 0 and months[i - 1]['kg'] > 0 and \
                months[i]['kg'] / max(1, months[i]['days']) > months[i - 1]['kg'] / max(1, months[i - 1]['days']) * STREAK_STEP:
            streak += 1
            i -= 1
    num['consecutive_increase_months'] = streak
    gaps: List[Dict[str, Any]] = []
    if with_data:
        first_i, last_i = months.index(with_data[0]), months.index(with_data[-1])
        gaps = [mo for mo in months[first_i + 1:last_i] if mo['kg'] <= 0]
    num['gap_months'] = len(gaps)
    last_date = max((r['date'] for r in cur), default=None)
    num['days_since_last_record'] = (min(today, cur_end) - last_date).days if last_date else 0

    # --- Groups (tag / tenant modes) ---------------------------------------------------
    group_kg: Dict[Any, float] = {}
    group_names: Dict[Any, str] = {}
    for r in cur:
        gid = r.get('group_id')
        group_kg[gid] = group_kg.get(gid, 0.0) + float(r['kg'])
        if gid is not None and r.get('group_name'):
            group_names[gid] = r['group_name']
    named = [(g, kg) for g, kg in group_kg.items() if g is not None]
    named.sort(key=lambda kv: kv[1], reverse=True)
    num['group_count'] = len(named)
    num['top_group_kg'] = round(named[0][1], 2) if named else 0.0
    num['top_group_share'] = _pct(named[0][1], total) if named else 0.0
    num['unassigned_kg'] = round(group_kg.get(None, 0.0), 2)
    num['unassigned_share'] = _pct(group_kg.get(None, 0.0), total)

    for lang in LANGS:
        t = txt[lang]
        t['cur_label'] = range_label(cur_start, cur_end, lang)
        t['prev_label'] = range_label(prev_start, prev_end, lang)
        t['compare_word'] = COMPARE_WORDS.get(compare_mode, COMPARE_WORDS['yearly'])[lang]
        t['gap_month_labels'] = ', '.join(month_label(mo['year'], mo['month'], lang) for mo in gaps)
        t['last_record_date'] = date_label(last_date, lang) if last_date else '-'
        t['top_group_label'] = (group_names.get(named[0][0]) or str(named[0][0])) if named else '-'
        t['trend_note'] = ''
        if num['has_data'] and not num['has_prev']:
            t['trend_note'] = (f" · ยังเปรียบเทียบไม่ได้ เพราะช่วง {t['prev_label']} ไม่มีข้อมูล" if lang == 'th'
                               else f" No comparison yet: {t['prev_label']} has no data.")
    return num, txt


# ---------------------------------------------------------------------------
# Safe expressions
# ---------------------------------------------------------------------------

_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.Name, ast.Load,
    ast.Constant, ast.And, ast.Or, ast.Not, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.USub, ast.UAdd, ast.Gt, ast.Lt, ast.GtE, ast.LtE, ast.Eq, ast.NotEq, ast.Call,
)
_ALLOWED_FUNCS = {'min': min, 'max': max, 'abs': abs, 'round': round}


def _compile_expr(expr: str):
    tree = ast.parse(expr, mode='eval')
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError(f"disallowed syntax in {expr!r}: {type(node).__name__}")
        if isinstance(node, ast.Call):
            if not (isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS) or node.keywords:
                raise ValueError(f"only min/max/abs/round calls are allowed: {expr!r}")
    return compile(tree, '<rule>', 'eval'), {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} - set(_ALLOWED_FUNCS)


def eval_expr(expr: str, values: Dict[str, Any]) -> Any:
    """Evaluate a rule expression. Unknown names raise KeyError — a typo in the rules
    file must fail loudly in tests, not silently evaluate as zero."""
    code, names = _compile_expr(expr)
    missing = names - set(values)
    if missing:
        raise KeyError(f"unknown metric(s) {sorted(missing)} in {expr!r}")
    scope = {k: values[k] for k in names}
    return eval(code, {'__builtins__': {}, **_ALLOWED_FUNCS}, scope)  # noqa: S307 - AST-whitelisted above


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_PLACEHOLDER = re.compile(r'\{([a-z_0-9]+)(?::([a-z_]+))?\}')


def _fmt_number(v: float, decimals: int = 2) -> str:
    return f"{v:,.{decimals}f}"


def format_value(value: Any, fmt: Optional[str], lang: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return str(value)
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if not math.isfinite(v):
        return '-'
    if fmt == 'kg':
        return f"{_fmt_number(v)} {'กก.' if lang == 'th' else 'kg'}"
    if fmt == 'pct':
        # A small but real share (e.g. 45 kg hazardous in 280 t) must not read as "0.0%".
        return "<0.1%" if 0 < v < 0.05 else f"{v:,.1f}%"
    if fmt == 'pct_signed':
        return f"{v:+,.1f}%"
    if fmt == 'pts':
        return f"{v:+,.1f} {'จุด' if lang == 'th' else 'pts'}"
    if fmt == 'int':
        return f"{int(round(v)):,}"
    if fmt == 'num' or fmt is None:
        return _fmt_number(v) if (fmt == 'num' or not float(v).is_integer()) else f"{int(v):,}"
    return _fmt_number(v)


def render_template(template: str, num: Dict[str, Any], txt: Dict[str, str], lang: str) -> str:
    def repl(m):
        name, fmt = m.group(1), m.group(2)
        if name in txt:
            return txt[name]
        if name in num:
            return format_value(num[name], fmt, lang)
        raise KeyError(f"unknown placeholder {{{name}}} in {template!r}")
    return _PLACEHOLDER.sub(repl, template or '')


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def load_rules(path: Optional[str] = None) -> Dict[str, Any]:
    candidates = [path] if path else list(_DEFAULT_RULES_CANDIDATES)
    for p in candidates:
        if p and os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                return json.load(f)
    raise FileNotFoundError('report_rules.json not found in ' + ', '.join(str(c) for c in candidates))


def _render_item(rule: Dict[str, Any], section: str, num: Dict[str, Any], txt: Dict[str, Dict[str, str]],
                 priority: float, fallback: bool) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        'id': rule.get('id') or f"fallback_{section}",
        'section': section,
        'group': rule.get('group'),
        'priority': round(float(priority), 2),
        'fallback': fallback,
    }
    for lang in LANGS:
        item[f'title_{lang}'] = render_template((rule.get('title') or {}).get(lang, ''), num, txt[lang], lang)
        item[f'bullets_{lang}'] = [
            render_template(b, num, txt[lang], lang) for b in ((rule.get('bullets') or {}).get(lang) or [])
        ]
        item[f'reason_{lang}'] = render_template((rule.get('reason') or {}).get(lang, ''), num, txt[lang], lang)
    return item


def evaluate_rules(rules_doc: Dict[str, Any], num: Dict[str, Any], txt: Dict[str, Dict[str, str]],
                   mode: str = 'location') -> Dict[str, List[Dict[str, Any]]]:
    mode = mode if mode in MODES else 'location'
    max_items = int(rules_doc.get('max_items_per_section') or 2)
    fallbacks = rules_doc.get('fallback') or {}
    mode_fallbacks = fallbacks.get(mode) or {}
    out: Dict[str, List[Dict[str, Any]]] = {v: [] for v in SECTION_KEYS.values()}

    if not num.get('has_data'):
        nd = fallbacks.get('no_data')
        if nd:
            for section, key in SECTION_KEYS.items():
                out[key] = [_render_item(nd, section, num, txt, 0, True)]
        return out

    matched: Dict[str, List[Tuple[float, Dict[str, Any]]]] = {s: [] for s in SECTION_KEYS}
    # Every rule whose condition held, with its priority and whether it made the cut (group
    # dedupe / max items). Kept with the advice snapshot so feedback samples can learn the
    # ranking too, not only the condition (B5).
    evaluated: List[Dict[str, Any]] = []
    for rule in rules_doc.get('rules') or []:
        section = rule.get('section')
        if section not in SECTION_KEYS or mode not in (rule.get('modes') or MODES):
            continue
        try:
            if not eval_expr(rule['when'], num):
                continue
            priority = float(eval_expr(str(rule.get('priority', '0')), num))
            item = _render_item(rule, section, num, txt, priority, False)
        except Exception as exc:  # a broken rule must not take the whole report down
            logger.warning("[report_insights] rule %s skipped: %s", rule.get('id'), exc)
            continue
        matched[section].append((priority, item))

    for section, key in SECTION_KEYS.items():
        seen_groups = set()
        picked: List[Dict[str, Any]] = []
        for _prio, item in sorted(matched[section], key=lambda p: p[0], reverse=True):
            g = item.get('group')
            dropped = None
            if g and g in seen_groups:
                dropped = 'group'
            elif len(picked) >= max_items:
                dropped = 'max_items'
            evaluated.append({'id': item['id'], 'section': section, 'group': g,
                              'priority': item['priority'], 'shown': dropped is None, 'dropped': dropped})
            if dropped:
                continue
            if g:
                seen_groups.add(g)
            picked.append(item)
        if not picked and mode_fallbacks.get(section):
            picked = [_render_item(mode_fallbacks[section], section, num, txt, 0, True)]
        out[key] = picked
    out['evaluated'] = evaluated
    return out


def rules_fingerprint(rules_doc: Dict[str, Any]) -> str:
    """'v<version>-<sha12>' of the rules file: identifies exactly which rule set produced an
    advice, so feedback collected under an older rule set is not mixed up with the new one."""
    raw = json.dumps(rules_doc, sort_keys=True, ensure_ascii=False).encode('utf-8')
    return f"v{rules_doc.get('version', 0)}-{hashlib.sha256(raw).hexdigest()[:12]}"


def rule_input_names(rule: Dict[str, Any]) -> List[str]:
    """Metric names a rule reads: its condition, its priority and its text placeholders."""
    names = set()
    for expr in (rule.get('when'), str(rule.get('priority', '0'))):
        if expr:
            try:
                names |= _compile_expr(expr)[1]
            except (SyntaxError, ValueError):
                pass
    for part in ('title', 'reason'):
        for text_ in (rule.get(part) or {}).values():
            names |= {m.group(1) for m in _PLACEHOLDER.finditer(text_ or '')}
    for lst in (rule.get('bullets') or {}).values():
        for text_ in lst or []:
            names |= {m.group(1) for m in _PLACEHOLDER.finditer(text_ or '')}
    return sorted(names)


def rule_sample(rule: Dict[str, Any], num: Dict[str, Any], txt: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """The rule as it fired on these metrics: definition, the inputs it read (values), whether
    the condition holds, its priority and the rendered text — one self-contained training
    sample once a like / dislike is attached (B5)."""
    inputs = {n: num[n] for n in rule_input_names(rule) if n in num}
    labels = {n: {lang: txt[lang].get(n) for lang in LANGS} for n in rule_input_names(rule)
              if n not in num and any(txt[lang].get(n) is not None for lang in LANGS)}
    try:
        holds = bool(eval_expr(rule['when'], num))
    except Exception:  # noqa: BLE001 — a sample is still useful when the rule no longer evaluates
        holds = None
    try:
        priority = float(eval_expr(str(rule.get('priority', '0')), num))
    except Exception:  # noqa: BLE001
        priority = None
    return {
        'rule': {k: rule.get(k) for k in ('id', 'section', 'modes', 'group', 'when', 'priority', 'title', 'bullets', 'reason')},
        'inputs': inputs,
        'labels': labels,
        'condition_holds': holds,
        'priority': priority,
        'rendered': {lang: {
            'title': render_template((rule.get('title') or {}).get(lang, ''), num, txt[lang], lang),
            'bullets': [render_template(b, num, txt[lang], lang) for b in ((rule.get('bullets') or {}).get(lang) or [])],
            'reason': render_template((rule.get('reason') or {}).get(lang, ''), num, txt[lang], lang),
        } for lang in LANGS},
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_report_insights(cur_records: List[Dict[str, Any]], prev_records: List[Dict[str, Any]],
                          cur_start: date, cur_end: date, prev_start: date, prev_end: date,
                          today: date, mode: str = 'location', compare_mode: str = 'yearly',
                          rules_doc: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cur = _in_range(cur_records, cur_start, cur_end)
    prev = _in_range(prev_records, prev_start, prev_end)
    num, txt = compute_metrics(cur, prev, cur_start, cur_end, prev_start, prev_end, today, compare_mode)
    if rules_doc is None:
        rules_doc = load_rules()
    scores = evaluate_rules(rules_doc, num, txt, mode)
    scores['metrics'] = num
    scores['rules_version'] = rules_fingerprint(rules_doc)
    return {'scores': scores, 'txt': txt,
            'labels': {lang: {k: txt[lang][k] for k in ('cur_label', 'prev_label')} for lang in LANGS}}
