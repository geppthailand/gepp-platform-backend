"""
Data Policy evaluator — pure-function tests.

The CASES table is duplicated verbatim (as data) in
v2/gepp-new-api/src/data-policy/evaluator.spec.ts. Both engines must produce
the same outcome for every row; if you add or change a case here, mirror it
there. That is the guard against the two evaluators drifting apart.
"""

from datetime import datetime, timezone

import pytest

from GEPPPlatform.services.admin.data_policy.evaluator import (
    derive_severity,
    evaluate,
    rule_warnings,
    snapshot_rule,
    subtract_duration,
)

NOW = datetime(2026, 10, 1, 12, 0, 0, tzinfo=timezone.utc)

CAT_HIGH_SD_PII = {
    'key': 'cat', 'sensitivity': 'high',
    'supportedActions': ['purge', 'anonymize', 'purge_soft_deleted', 'retain_min', 'inactive_unit_purge',
                         'review', 'backup', 'archive'],
}
ACTIVE = {'id': 7, 'status': 'active', 'inactiveSince': None}
INACTIVE_2Y = {'id': 7, 'status': 'inactive', 'inactiveSince': '2024-09-01T00:00:00+00:00'}

# (name, rule, unit, metrics, expected: None or {field: value})
CASES = [
    ('purge overdue', {'id': 1, 'action': 'purge', 'retentionValue': 3, 'retentionUnit': 'year',
                       'scheduleValue': 1, 'scheduleUnit': 'month'},
     ACTIVE, {'liveCount': 10, 'oldestAt': '2020-01-01T00:00:00+00:00', 'rules': {'1': {'n': 4, 'o': 3}}},
     {'status': 'overdue', 'severity': 'high', 'affectedCount': 4, 'overdueCount': 3, 'oldestAt': '2020-01-01T00:00:00+00:00'}),
    ('purge due only (inside grace) is one level lower', {'id': 1, 'action': 'purge', 'retentionValue': 3, 'retentionUnit': 'year',
                                                          'scheduleValue': 1, 'scheduleUnit': 'month'},
     ACTIVE, {'liveCount': 10, 'oldestAt': '2023-09-15T00:00:00+00:00', 'rules': {'1': {'n': 2, 'o': 0}}},
     {'status': 'due', 'severity': 'medium', 'affectedCount': 2, 'overdueCount': 0}),
    ('purge compliant', {'id': 1, 'action': 'purge', 'retentionValue': 3, 'retentionUnit': 'year'},
     ACTIVE, {'liveCount': 10, 'rules': {'1': {'n': 0, 'o': 0}}}, None),
    ('exempt unit is skipped', {'id': 1, 'action': 'purge', 'retentionValue': 3, 'retentionUnit': 'year', 'exemptUnitIds': [7]},
     ACTIVE, {'liveCount': 10, 'rules': {'1': {'n': 5, 'o': 5}}}, None),
    ('review is info', {'id': 2, 'action': 'review', 'retentionValue': 1, 'retentionUnit': 'year'},
     ACTIVE, {'liveCount': 3, 'oldestAt': '2024-01-01T00:00:00+00:00', 'rules': {'2': {'n': 3, 'o': 3}}},
     {'status': 'review', 'severity': 'info', 'affectedCount': 3}),
    ('anonymize uses piiOldestAt', {'id': 3, 'action': 'anonymize', 'retentionValue': 90, 'retentionUnit': 'day'},
     ACTIVE, {'liveCount': 5, 'oldestAt': '2020-01-01T00:00:00+00:00', 'piiOldestAt': '2025-01-01T00:00:00+00:00',
              'rules': {'3': {'n': 1, 'o': 1}}},
     {'status': 'overdue', 'oldestAt': '2025-01-01T00:00:00+00:00'}),
    ('purge_soft_deleted uses oldestDeletedAt', {'id': 4, 'action': 'purge_soft_deleted', 'retentionValue': 30, 'retentionUnit': 'day'},
     ACTIVE, {'liveCount': 0, 'oldestDeletedAt': '2026-01-01T00:00:00+00:00', 'rules': {'4': {'n': 2, 'o': 2}}},
     {'status': 'overdue', 'affectedCount': 2, 'oldestAt': '2026-01-01T00:00:00+00:00'}),
    ('retain_min violation is at least high', {'id': 5, 'action': 'retain_min', 'retentionValue': 5, 'retentionUnit': 'year'},
     ACTIVE, {'liveCount': 1, 'rules': {'5': {'n': 2, 'min': '2024-02-02T00:00:00+00:00'}}},
     {'status': 'violation', 'severity': 'high', 'affectedCount': 2, 'oldestAt': '2024-02-02T00:00:00+00:00'}),
    ('inactive unit beyond retention', {'id': 6, 'action': 'inactive_unit_purge', 'retentionValue': 1, 'retentionUnit': 'year'},
     INACTIVE_2Y, {'liveCount': 12, 'oldestAt': '2021-01-01T00:00:00+00:00'},
     {'status': 'overdue', 'affectedCount': 12, 'params': {'inactiveSince': '2024-09-01T00:00:00+00:00'}}),
    ('inactive unit inside retention', {'id': 6, 'action': 'inactive_unit_purge', 'retentionValue': 3, 'retentionUnit': 'year'},
     INACTIVE_2Y, {'liveCount': 12}, None),
    ('active unit never triggers inactive purge', {'id': 6, 'action': 'inactive_unit_purge', 'retentionValue': 1, 'retentionUnit': 'day'},
     ACTIVE, {'liveCount': 12}, None),
    ('backup is never an issue', {'id': 8, 'action': 'backup', 'scheduleValue': 1, 'scheduleUnit': 'day'},
     ACTIVE, {'liveCount': 12}, None),
    ('severity override wins', {'id': 1, 'action': 'purge', 'retentionValue': 3, 'retentionUnit': 'year', 'severity': 'low'},
     ACTIVE, {'liveCount': 10, 'rules': {'1': {'n': 4, 'o': 4}}}, {'severity': 'low'}),
    ('no metrics (unit holds nothing)', {'id': 1, 'action': 'purge', 'retentionValue': 3, 'retentionUnit': 'year'},
     ACTIVE, None, None),
]


@pytest.mark.parametrize('name,rule,unit,metrics,expected', CASES, ids=[c[0] for c in CASES])
def test_evaluate(name, rule, unit, metrics, expected):
    snap = snapshot_rule({'categoryKey': 'cat', 'exemptUnitIds': [], 'severity': None, **rule}, NOW)
    issue = evaluate(snap, CAT_HIGH_SD_PII, unit, metrics, NOW)
    if expected is None:
        assert issue is None
    else:
        assert issue is not None
        for k, v in expected.items():
            assert issue[k] == v, f'{k}: {issue[k]!r} != {v!r}'


@pytest.mark.parametrize('dt,value,unit,expected', [
    (datetime(2026, 3, 31, tzinfo=timezone.utc), 1, 'month', datetime(2026, 2, 28, tzinfo=timezone.utc)),
    (datetime(2028, 2, 29, tzinfo=timezone.utc), 1, 'year', datetime(2027, 2, 28, tzinfo=timezone.utc)),
    (datetime(2026, 10, 1, tzinfo=timezone.utc), 3, 'year', datetime(2023, 10, 1, tzinfo=timezone.utc)),
    (datetime(2026, 1, 15, tzinfo=timezone.utc), 2, 'week', datetime(2026, 1, 1, tzinfo=timezone.utc)),
    (datetime(2026, 1, 31, tzinfo=timezone.utc), 13, 'month', datetime(2024, 12, 31, tzinfo=timezone.utc)),
])
def test_subtract_duration_is_calendar_aware(dt, value, unit, expected):
    assert subtract_duration(dt, value, unit) == expected


def test_snapshot_grace_window():
    snap = snapshot_rule({'id': 1, 'action': 'purge', 'retentionValue': 3, 'retentionUnit': 'year',
                          'scheduleValue': 1, 'scheduleUnit': 'month'}, NOW)
    assert snap['dueCutoff'] == '2023-10-01T12:00:00+00:00'
    assert snap['overCutoff'] == '2023-09-01T12:00:00+00:00'


def test_derive_severity():
    assert derive_severity('critical', 'purge', 'overdue') == 'critical'
    assert derive_severity('critical', 'purge', 'due') == 'high'
    assert derive_severity('low', 'purge', 'due') == 'low'
    assert derive_severity('low', 'retain_min', 'violation') == 'high'
    assert derive_severity('critical', 'review', 'review') == 'info'


def test_rule_warnings_conflict_and_unsupported():
    cats = {'docs': {'key': 'docs', 'supportedActions': ['purge', 'retain_min', 'backup']}}
    rules = [
        {'id': 1, 'categoryKey': 'docs', 'action': 'purge', 'retentionValue': 3, 'retentionUnit': 'year', 'isActive': True},
        {'id': 2, 'categoryKey': 'docs', 'action': 'retain_min', 'retentionValue': 5, 'retentionUnit': 'year', 'isActive': True},
        {'id': 3, 'categoryKey': 'docs', 'action': 'anonymize', 'retentionValue': 1, 'retentionUnit': 'year', 'isActive': True},
        {'id': 4, 'categoryKey': 'docs', 'action': 'backup', 'scheduleValue': 1, 'scheduleUnit': 'day', 'isActive': True},
        {'id': 5, 'categoryKey': 'docs', 'action': 'purge', 'retentionValue': 1, 'retentionUnit': 'day', 'isActive': False},
    ]
    kinds = sorted(w['kind'] for w in rule_warnings(rules, cats))
    assert kinds == ['conflict', 'unsupported', 'unverifiable']
