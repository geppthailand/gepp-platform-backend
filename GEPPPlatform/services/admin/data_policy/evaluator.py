"""
Pure rule evaluation for the Data Policy engine — no DB, no I/O.

MIRRORED in TypeScript at v2/gepp-new-api/src/data-policy/evaluator.ts.
The two must stay behaviour-identical: same cutoff math, same severity
derivation, same issue shape. If you change one, change the other and the
shared vectors in docs/Services/GEPP-Backoffice/features/data_policy.md.

Vocabulary
  rule      a row of data_policy_rules, snapshotted at run start with absolute
            cutoffs so every chunk of a run agrees on "older than 3 years".
  metrics   what one category's probe measured for one unit (see engine.py).
  unit      {id, status, inactiveSince} — the legal data unit (org / project).
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

SEVERITIES = ['critical', 'high', 'medium', 'low', 'info']
_RANK = {'info': 0, 'low': 1, 'medium': 2, 'high': 3, 'critical': 4}
_BY_RANK = {v: k for k, v in _RANK.items()}

DURATION_UNITS = ('day', 'week', 'month', 'year')
# Approximate days, used only to COMPARE durations (conflict warnings) and for
# retain_min's "lived for at least N" check. Cutoffs use calendar math below.
UNIT_DAYS = {'day': 1, 'week': 7, 'month': 30, 'year': 365}

VERIFIABLE_ACTIONS = ('purge', 'anonymize', 'purge_soft_deleted', 'retain_min', 'inactive_unit_purge', 'review')
UNVERIFIABLE_ACTIONS = ('backup', 'archive')
# Actions whose probe needs per-rule cutoff columns.
CUTOFF_ACTIONS = ('purge', 'anonymize', 'purge_soft_deleted', 'review', 'retain_min')


def subtract_duration(dt: datetime, value: int, unit: str) -> datetime:
    """Calendar-aware `dt - value unit`. Month/year clamp the day (31 Mar - 1 month = 28/29 Feb)."""
    value = int(value)
    if unit == 'day':
        return dt - timedelta(days=value)
    if unit == 'week':
        return dt - timedelta(weeks=value)
    if unit in ('month', 'year'):
        months = value * (12 if unit == 'year' else 1)
        total = dt.year * 12 + (dt.month - 1) - months
        year, month = divmod(total, 12)
        month += 1
        day = min(dt.day, calendar.monthrange(year, month)[1])
        return dt.replace(year=year, month=month, day=day)
    raise ValueError(f'unknown duration unit: {unit}')


def duration_days(value: Optional[int], unit: Optional[str]) -> Optional[int]:
    if not value or not unit:
        return None
    return int(value) * UNIT_DAYS[unit]


def snapshot_rule(rule: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """Freeze a rule with absolute cutoffs (ISO strings) for one run."""
    snap = dict(rule)
    rv, ru = rule.get('retentionValue'), rule.get('retentionUnit')
    sv, su = rule.get('scheduleValue'), rule.get('scheduleUnit')
    due = subtract_duration(now, rv, ru) if rv and ru else None
    over = subtract_duration(due, sv, su) if due and sv and su else due
    snap['dueCutoff'] = due.isoformat() if due else None
    snap['overCutoff'] = over.isoformat() if over else None
    days = duration_days(rv, ru)
    snap['minSeconds'] = days * 86400 if days else None
    return snap


def derive_severity(sensitivity: str, action: str, status: str) -> str:
    if action == 'review':
        return 'info'
    rank = _RANK.get(sensitivity, 2)
    if action == 'retain_min':
        rank = max(rank, _RANK['high'])
    if status == 'due':
        rank = max(_RANK['low'], rank - 1)
    return _BY_RANK[rank]


def _parse(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    d = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def evaluate(
    rule: Dict[str, Any],
    category: Dict[str, Any],
    unit: Dict[str, Any],
    metrics: Optional[Dict[str, Any]],
    now: datetime,
) -> Optional[Dict[str, Any]]:
    """One rule × one category × one unit → an issue dict, or None if compliant/not applicable."""
    action = rule['action']
    if action in UNVERIFIABLE_ACTIONS:
        return None
    if action not in category.get('supportedActions', []):
        return None
    if int(unit['id']) in set(int(x) for x in (rule.get('exemptUnitIds') or [])):
        return None
    m = metrics or {}
    rid = str(rule['id'])
    r = (m.get('rules') or {}).get(rid) or {}
    affected, overdue, oldest, status = 0, 0, None, None
    params: Dict[str, Any] = {}

    if action in ('purge', 'review', 'anonymize', 'purge_soft_deleted'):
        affected, overdue = int(r.get('n') or 0), int(r.get('o') or 0)
        if affected <= 0:
            return None
        status = 'review' if action == 'review' else ('overdue' if overdue > 0 else 'due')
        oldest = {
            'purge': m.get('oldestAt'),
            'review': m.get('oldestAt'),
            'anonymize': m.get('piiOldestAt'),
            'purge_soft_deleted': m.get('oldestDeletedAt'),
        }[action]
    elif action == 'retain_min':
        affected = int(r.get('n') or 0)
        if affected <= 0:
            return None
        overdue, status, oldest = affected, 'violation', r.get('min')
    elif action == 'inactive_unit_purge':
        inactive_since = _parse(unit.get('inactiveSince'))
        live = int(m.get('liveCount') or 0)
        if unit.get('status') == 'active' or not inactive_since or live <= 0:
            return None
        due = _parse(rule.get('dueCutoff'))
        over = _parse(rule.get('overCutoff')) or due
        if not due or inactive_since >= due:
            return None
        affected = live
        overdue = live if inactive_since < over else 0
        status = 'overdue' if overdue else 'due'
        oldest = m.get('oldestAt')
        params['inactiveSince'] = unit.get('inactiveSince')
    else:
        return None

    severity = rule.get('severity') or derive_severity(category.get('sensitivity', 'medium'), action, status)
    return {
        'ruleId': int(rule['id']),
        'categoryKey': category['key'],
        'action': action,
        'severity': severity,
        'status': status,
        'affectedCount': affected,
        'overdueCount': overdue,
        'oldestAt': oldest,
        'cutoffAt': rule.get('dueCutoff'),
        'params': params,
    }


def severity_counts(issues: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {s: 0 for s in SEVERITIES}
    for i in issues:
        counts[i['severity']] = counts.get(i['severity'], 0) + 1
    return counts


def rule_warnings(rules: List[Dict[str, Any]], categories: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Problems with the rule SET itself — shown on the policy tab, independent of any unit."""
    out: List[Dict[str, Any]] = []
    active = [r for r in rules if r.get('isActive')]
    for r in active:
        cat = categories.get(r['categoryKey'])
        if not cat or r['action'] not in cat.get('supportedActions', []):
            out.append({'kind': 'unsupported', 'categoryKey': r['categoryKey'], 'ruleIds': [r['id']],
                        'params': {'action': r['action']}})
        elif r['action'] in UNVERIFIABLE_ACTIONS:
            out.append({'kind': 'unverifiable', 'categoryKey': r['categoryKey'], 'ruleIds': [r['id']], 'params': {}})
    by_cat: Dict[str, List[Dict[str, Any]]] = {}
    for r in active:
        by_cat.setdefault(r['categoryKey'], []).append(r)
    for key, rs in by_cat.items():
        keeps = [r for r in rs if r['action'] == 'retain_min' and duration_days(r.get('retentionValue'), r.get('retentionUnit'))]
        purges = [r for r in rs if r['action'] == 'purge' and duration_days(r.get('retentionValue'), r.get('retentionUnit'))]
        for p in purges:
            for k in keeps:
                if duration_days(p['retentionValue'], p['retentionUnit']) < duration_days(k['retentionValue'], k['retentionUnit']):
                    out.append({
                        'kind': 'conflict', 'categoryKey': key, 'ruleIds': [p['id'], k['id']],
                        'params': {
                            'purgeValue': p['retentionValue'], 'purgeUnit': p['retentionUnit'],
                            'keepValue': k['retentionValue'], 'keepUnit': k['retentionUnit'],
                        },
                    })
    return out
