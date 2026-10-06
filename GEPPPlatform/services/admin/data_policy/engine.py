"""
v3 Data Policy engine — rules CRUD, unit listing, and the resumable Diagnose run.

Diagnose = probe → evaluate → persist:

  probe     one aggregate SQL per category, GROUP BY organization. Per-rule
            cutoff counts are computed inline (SUM(CASE…)), so a full run is
            N_categories queries — not N_orgs × N_rules.
  evaluate  pure functions in evaluator.py (mirrored in the v2 TS engine).
  persist   data_policy_unit_results keeps the LATEST snapshot per unit; the
            list page only ever reads that table, never re-probes.

A run is resumable and time-budgeted because v3 sits behind API Gateway
(~29 s hard cap): each POST /diagnose works through pending categories until
STEP_BUDGET_S is used, then returns `done: false`; the client re-POSTs with
the runId. Each step is one DB transaction holding a NOWAIT row lock on the
run, so a double-click can't run the same probe twice.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from ....exceptions import BadRequestException, NotFoundException
from . import catalog as C
from .evaluator import (
    CUTOFF_ACTIONS,
    DURATION_UNITS,
    SEVERITIES,
    UNVERIFIABLE_ACTIONS,
    evaluate,
    rule_warnings,
    severity_counts,
    snapshot_rule,
)

logger = logging.getLogger(__name__)

ENGINE_VERSION = 'v3-2026.10.1'
STEP_BUDGET_S = 14.0          # stop starting new probes after this
FINALIZE_DEFER_S = 9.0        # if probes ate this much, finalize on the next call
PROBE_TIMEOUT_MS = 12000      # per-statement cap inside a step
STALE_RUN_MINUTES = 15
MAX_SCOPED_UNITS = 500
UPSERT_CHUNK = 400

# Status of an organization, as the retention clock sees it. "inactive" from a
# lapsed subscription only counts when nothing happened after it lapsed — the
# subscription gate ships off, so a lapsed-but-working org is still a customer.
UNITS_CTE = """
WITH sub AS (
    SELECT organization_id,
           bool_or(now() BETWEEN COALESCE(current_period_starts_at, '-infinity'::timestamptz)
                             AND COALESCE(current_period_ends_at, 'infinity'::timestamptz)) AS covered,
           MAX(current_period_ends_at) AS ended_at
    FROM subscriptions WHERE deleted_date IS NULL GROUP BY organization_id
), act AS (
    SELECT organization_id, MAX(created_date) AS last_tx
    FROM transactions WHERE organization_id IS NOT NULL GROUP BY organization_id
), u AS (
    SELECT o.id, o.name, o.created_date, o.owner_id,
           act.last_tx, sub.ended_at AS subscription_ended_at,
           (sub.organization_id IS NOT NULL AND NOT sub.covered) AS subscription_lapsed,
           CASE WHEN o.deleted_date IS NOT NULL THEN 'deleted'
                WHEN o.is_active = false THEN 'inactive'
                WHEN sub.organization_id IS NOT NULL AND NOT sub.covered AND sub.ended_at IS NOT NULL
                     AND (act.last_tx IS NULL OR act.last_tx < sub.ended_at) THEN 'inactive'
                ELSE 'active' END AS status,
           CASE WHEN o.deleted_date IS NOT NULL THEN o.deleted_date
                WHEN o.is_active = false THEN o.updated_date
                WHEN sub.organization_id IS NOT NULL AND NOT sub.covered AND sub.ended_at IS NOT NULL
                     AND (act.last_tx IS NULL OR act.last_tx < sub.ended_at) THEN sub.ended_at
           END AS inactive_since
    FROM organizations o
    LEFT JOIN sub ON sub.organization_id = o.id
    LEFT JOIN act ON act.organization_id = o.id
)
"""

_SORTS = {
    'issues': ('COALESCE(r.critical_count, -1) {d}, COALESCE(r.high_count, -1) {d}, '
               'COALESCE(r.issue_count, -1) {d}'),
    'name': 'u.name {d}',
    'records': 'COALESCE(r.total_records, -1) {d}',
    'oldest': 'r.oldest_record_at {d} NULLS LAST',
    'diagnosed': 'r.diagnosed_at {d} NULLS LAST',
}


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        # Always UTC, so ISO strings from different columns compare correctly.
        v = v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)
        return v.isoformat()
    return str(v)


def _int(v: Any) -> Optional[int]:
    return None if v is None else int(v)


def _json(v: Any) -> Any:
    if v is None or isinstance(v, (list, dict)):
        return v
    return json.loads(v)


class DataPolicyService:
    def __init__(self, db, current_user: Optional[Dict[str, Any]] = None):
        self.db = db
        self.user_id = (current_user or {}).get('user_id') or (current_user or {}).get('id')

    # ─── catalog ──────────────────────────────────────────────────────────
    def catalog(self) -> Dict[str, Any]:
        return C.catalog_doc(ENGINE_VERSION)

    # ─── rules ────────────────────────────────────────────────────────────
    @staticmethod
    def _rule_out(row) -> Dict[str, Any]:
        m = row._mapping
        return {
            'id': int(m['id']),
            'categoryKey': m['category_key'],
            'action': m['action'],
            'retentionValue': _int(m['retention_value']),
            'retentionUnit': m['retention_unit'],
            'scheduleValue': _int(m['schedule_value']),
            'scheduleUnit': m['schedule_unit'],
            'severity': m['severity'],
            'isActive': bool(m['is_active']),
            'exemptUnitIds': [int(x) for x in (_json(m['exempt_unit_ids']) or [])],
            'note': m['note'],
            'updatedAt': _iso(m['updated_date']),
            'updatedBy': _int(m['updated_by']),
        }

    def _rules(self, only_active: bool = False) -> List[Dict[str, Any]]:
        rows = self.db.execute(text(
            "SELECT * FROM data_policy_rules WHERE deleted_date IS NULL"
            + (" AND is_active = true" if only_active else "")
            + " ORDER BY category_key, id"
        )).fetchall()
        return [self._rule_out(r) for r in rows]

    def list_rules(self) -> Dict[str, Any]:
        rules = self._rules()
        return {'rules': rules, 'warnings': rule_warnings(rules, C.CATEGORY_BY_KEY)}

    def _validate_rule(self, data: Dict[str, Any], existing: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        merged = dict(existing or {})
        merged.update({k: v for k, v in (data or {}).items() if k in (
            'categoryKey', 'action', 'retentionValue', 'retentionUnit', 'scheduleValue', 'scheduleUnit',
            'severity', 'isActive', 'exemptUnitIds', 'note')})
        cat = C.CATEGORY_BY_KEY.get(merged.get('categoryKey') or '')
        if not cat:
            raise BadRequestException('Unknown categoryKey')
        action = next((a for a in C.ACTIONS if a['key'] == merged.get('action')), None)
        if not action:
            raise BadRequestException('Unknown action')
        if action['key'] not in cat['supportedActions']:
            raise BadRequestException(f"Action '{action['key']}' is not supported for category '{cat['key']}'")

        def duration(prefix: str, required: bool):
            v, u = merged.get(f'{prefix}Value'), merged.get(f'{prefix}Unit')
            if v in (None, '', 0):
                if required:
                    raise BadRequestException(f'{prefix}Value is required for {action["key"]}')
                return None, None
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise BadRequestException(f'{prefix}Value must be an integer')
            if not 1 <= v <= 3650:
                raise BadRequestException(f'{prefix}Value must be between 1 and 3650')
            if u not in DURATION_UNITS:
                raise BadRequestException(f'{prefix}Unit must be one of {", ".join(DURATION_UNITS)}')
            return v, u

        rv, ru = duration('retention', action['needsRetention'])
        if not action['needsRetention']:
            rv, ru = None, None
        sv, su = duration('schedule', action['needsSchedule'])
        severity = merged.get('severity') or None
        if severity is not None and severity not in SEVERITIES:
            raise BadRequestException('Invalid severity')
        exempt = merged.get('exemptUnitIds') or []
        if not isinstance(exempt, list) or len(exempt) > 1000:
            raise BadRequestException('exemptUnitIds must be a list (max 1000)')
        try:
            exempt = sorted({int(x) for x in exempt if int(x) > 0})
        except (TypeError, ValueError):
            raise BadRequestException('exemptUnitIds must contain integers')
        note = merged.get('note')
        if note is not None:
            note = str(note).strip()[:1000] or None
        return {
            'category_key': cat['key'], 'action': action['key'],
            'retention_value': rv, 'retention_unit': ru, 'schedule_value': sv, 'schedule_unit': su,
            'severity': severity, 'is_active': bool(merged.get('isActive', True)),
            'exempt_unit_ids': json.dumps(exempt), 'note': note,
        }

    def _get_rule(self, rule_id: int) -> Dict[str, Any]:
        row = self.db.execute(text(
            "SELECT * FROM data_policy_rules WHERE id = :id AND deleted_date IS NULL"), {'id': rule_id}).fetchone()
        if not row:
            raise NotFoundException('Rule not found')
        return self._rule_out(row)

    def create_rule(self, data: Dict[str, Any]) -> Dict[str, Any]:
        v = self._validate_rule(data)
        row = self.db.execute(text(
            "INSERT INTO data_policy_rules (category_key, action, retention_value, retention_unit, schedule_value, "
            " schedule_unit, severity, is_active, exempt_unit_ids, note, created_by, updated_by) "
            "VALUES (:category_key, :action, :retention_value, :retention_unit, :schedule_value, :schedule_unit, "
            " :severity, :is_active, CAST(:exempt_unit_ids AS jsonb), :note, :uid, :uid) RETURNING *"
        ), {**v, 'uid': self.user_id}).fetchone()
        return self._rule_out(row)

    def update_rule(self, rule_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        v = self._validate_rule(data, self._get_rule(rule_id))
        row = self.db.execute(text(
            "UPDATE data_policy_rules SET category_key = :category_key, action = :action, "
            " retention_value = :retention_value, retention_unit = :retention_unit, schedule_value = :schedule_value, "
            " schedule_unit = :schedule_unit, severity = :severity, is_active = :is_active, "
            " exempt_unit_ids = CAST(:exempt_unit_ids AS jsonb), note = :note, updated_by = :uid, updated_date = now() "
            "WHERE id = :id AND deleted_date IS NULL RETURNING *"
        ), {**v, 'uid': self.user_id, 'id': rule_id}).fetchone()
        return self._rule_out(row)

    def delete_rule(self, rule_id: int) -> Dict[str, Any]:
        self._get_rule(rule_id)
        self.db.execute(text(
            "UPDATE data_policy_rules SET deleted_date = now(), is_active = false, updated_by = :uid, "
            " updated_date = now() WHERE id = :id"), {'id': rule_id, 'uid': self.user_id})
        return {'id': rule_id}

    # ─── units ────────────────────────────────────────────────────────────
    @staticmethod
    def _unit_out(m) -> Dict[str, Any]:
        counts = {s: int(m.get(f'{s}_count') or 0) for s in SEVERITIES}
        return {
            'id': int(m['id']),
            'name': m['name'],
            'status': m['status'],
            'createdDate': _iso(m['created_date']),
            'inactiveSince': _iso(m['inactive_since']),
            'meta': {
                'ownerEmail': m.get('owner_email'),
                'userCount': _int(m.get('user_count')),
                'lastActivityAt': _iso(m.get('last_tx')),
                'subscriptionEndedAt': _iso(m.get('subscription_ended_at')),
                'subscriptionLapsed': bool(m.get('subscription_lapsed')),
            },
            'diagnosedAt': _iso(m.get('diagnosed_at')),
            'issueCount': int(m.get('issue_count') or 0),
            'severityCounts': counts,
            'totalRecords': _int(m.get('total_records')),
            'oldestRecordAt': _iso(m.get('oldest_record_at')),
        }

    def list_units(self, q: Dict[str, Any]) -> Dict[str, Any]:
        try:
            page = max(1, int(q.get('page') or 1))
            page_size = min(200, max(1, int(q.get('pageSize') or 20)))
        except (TypeError, ValueError):
            raise BadRequestException('page/pageSize must be integers')
        search = str(q.get('search') or '').strip()
        status = str(q.get('status') or '').strip()
        if status and status not in ('active', 'inactive', 'deleted'):
            raise BadRequestException('Invalid status')
        only_issues = str(q.get('onlyWithIssues') or '') in ('1', 'true', 'True')
        sort_key, _, sort_dir = str(q.get('sort') or 'issues:desc').partition(':')
        order = _SORTS.get(sort_key, _SORTS['issues']).format(d='ASC' if sort_dir == 'asc' else 'DESC')

        where = ("(:search = '' OR u.name ILIKE :like OR CAST(u.id AS text) = :search) "
                 "AND (:status = '' OR u.status = :status) "
                 "AND (:only_issues = false OR r.issue_count > 0)")
        params = {'search': search, 'like': f'%{search}%', 'status': status, 'only_issues': only_issues}
        total = self.db.execute(text(
            f"{UNITS_CTE} SELECT COUNT(*) FROM u LEFT JOIN data_policy_unit_results r ON r.unit_id = u.id WHERE {where}"
        ), params).scalar() or 0
        rows = self.db.execute(text(
            f"{UNITS_CTE} SELECT p.*, ow.email AS owner_email, "
            "  (SELECT COUNT(*) FROM user_locations ul WHERE ul.organization_id = p.id AND ul.is_user = true "
            "     AND ul.deleted_date IS NULL) AS user_count "
            "FROM (SELECT u.*, r.diagnosed_at, r.issue_count, r.critical_count, r.high_count, r.medium_count, "
            "        r.low_count, r.info_count, r.total_records, r.oldest_record_at, "
            f"       ROW_NUMBER() OVER (ORDER BY {order}, u.id) AS rn "
            "      FROM u LEFT JOIN data_policy_unit_results r ON r.unit_id = u.id "
            f"     WHERE {where} ORDER BY {order}, u.id LIMIT :limit OFFSET :offset) p "
            "LEFT JOIN user_locations ow ON ow.id = p.owner_id ORDER BY p.rn"
        ), {**params, 'limit': page_size, 'offset': (page - 1) * page_size}).fetchall()
        items = [self._unit_out(dict(r._mapping)) for r in rows]
        return {'items': items, 'total': int(total), 'lastRun': self._last_full_run()}

    def get_unit(self, unit_id: int) -> Dict[str, Any]:
        row = self.db.execute(text(
            f"{UNITS_CTE} SELECT u.*, ow.email AS owner_email, r.diagnosed_at, r.issue_count, r.critical_count, "
            " r.high_count, r.medium_count, r.low_count, r.info_count, r.total_records, r.oldest_record_at, "
            " r.inventory, r.issues, r.run_id, "
            " (SELECT COUNT(*) FROM user_locations ul WHERE ul.organization_id = u.id AND ul.is_user = true "
            "    AND ul.deleted_date IS NULL) AS user_count "
            "FROM u LEFT JOIN data_policy_unit_results r ON r.unit_id = u.id "
            "LEFT JOIN user_locations ow ON ow.id = u.owner_id WHERE u.id = :id"
        ), {'id': unit_id}).fetchone()
        if not row:
            raise NotFoundException('Organization not found')
        m = dict(row._mapping)
        inventory = _json(m.get('inventory')) or []
        run_id = _int(m.get('run_id'))
        if run_id:
            run = self.db.execute(text(
                "SELECT plan_keys, probe_errors FROM data_policy_runs WHERE id = :id"), {'id': run_id}).fetchone()
            if run:
                have = {i['categoryKey'] for i in inventory}
                errors = {e['categoryKey']: e['error'] for e in (_json(run.probe_errors) or [])}
                for key in _json(run.plan_keys) or []:
                    if key not in have:
                        inventory.append(_empty_inventory(key, errors.get(key)))
        return {
            'unit': self._unit_out(m),
            'inventory': inventory,
            'issues': _json(m.get('issues')) or [],
            'runId': run_id,
        }

    def _unit_states(self, unit_ids: Optional[List[int]]) -> List[Dict[str, Any]]:
        sql = f"{UNITS_CTE} SELECT u.id, u.status, u.inactive_since FROM u"
        params: Dict[str, Any] = {}
        if unit_ids:
            sql += " WHERE u.id = ANY(:ids)"
            params['ids'] = unit_ids
        return [{'id': int(r.id), 'status': r.status, 'inactiveSince': _iso(r.inactive_since)}
                for r in self.db.execute(text(sql), params).fetchall()]

    # ─── diagnose ─────────────────────────────────────────────────────────
    def _last_full_run(self) -> Optional[Dict[str, Any]]:
        row = self.db.execute(text(
            "SELECT * FROM data_policy_runs WHERE status = 'completed' AND scope_unit_ids IS NULL "
            "ORDER BY finished_at DESC LIMIT 1")).fetchone()
        return self._run_out(row) if row else None

    @staticmethod
    def _run_out(row, busy: bool = False) -> Dict[str, Any]:
        m = row._mapping
        plan = _json(m['plan_keys']) or []
        pending = _json(m['pending_keys']) or []
        return {
            'runId': int(m['id']),
            'status': m['status'],
            'done': m['status'] != 'running',
            'busy': busy,
            'scope': {'unitIds': _json(m['scope_unit_ids'])},
            'progress': {'total': len(plan), 'completed': len(plan) - len(pending), 'current': pending[:3]},
            'startedAt': _iso(m['started_at']),
            'finishedAt': _iso(m['finished_at']),
            'durationMs': _int(m['duration_ms']),
            'unitsScanned': _int(m['units_scanned']),
            'issuesFound': _int(m['issues_found']),
            'severityCounts': _json(m['severity_counts']),
            'probeErrors': _json(m['probe_errors']) or [],
            'unverifiableRules': int(m['unverifiable_rules'] or 0),
        }

    def get_run(self, run_id: int) -> Dict[str, Any]:
        row = self.db.execute(text("SELECT * FROM data_policy_runs WHERE id = :id"), {'id': run_id}).fetchone()
        if not row:
            raise NotFoundException('Run not found')
        return self._run_out(row)

    def _existing_tables(self) -> set:
        return {r[0] for r in self.db.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")).fetchall()}

    def _start_run(self, unit_ids: Optional[List[int]]) -> int:
        self.db.execute(text(
            "UPDATE data_policy_runs SET status = 'abandoned', updated_date = now() "
            "WHERE status = 'running' AND updated_date < now() - make_interval(mins => :m)"),
            {'m': STALE_RUN_MINUTES})
        now = datetime.now(timezone.utc)
        rules = [snapshot_rule(r, now) for r in self._rules(only_active=True)]
        tables = self._existing_tables()
        plan, skipped = [], []
        for c in C.CATEGORIES:
            (plan if all(t in tables for t in c['_tables']) else skipped).append(c['key'])
        unverifiable = sum(1 for r in rules if r['action'] in UNVERIFIABLE_ACTIONS)
        row = self.db.execute(text(
            "INSERT INTO data_policy_runs (status, scope_unit_ids, plan_keys, pending_keys, skipped_keys, "
            " rules_snapshot, probe_errors, started_at, unverifiable_rules, engine_version, created_by) "
            "VALUES ('running', CAST(:scope AS jsonb), CAST(:plan AS jsonb), CAST(:plan AS jsonb), "
            " CAST(:skipped AS jsonb), CAST(:rules AS jsonb), '[]'::jsonb, :now, :unv, :ver, :uid) RETURNING id"
        ), {
            'scope': json.dumps(unit_ids) if unit_ids else None, 'plan': json.dumps(plan),
            'skipped': json.dumps(skipped), 'rules': json.dumps(rules), 'now': now,
            'unv': unverifiable, 'ver': ENGINE_VERSION, 'uid': self.user_id,
        }).fetchone()
        return int(row.id)

    def diagnose_step(self, data: Dict[str, Any]) -> Dict[str, Any]:
        t0 = time.monotonic()
        data = data or {}
        run_id = data.get('runId')
        if run_id is None:
            unit_ids = data.get('unitIds')
            if unit_ids is not None:
                if not isinstance(unit_ids, list) or not unit_ids:
                    raise BadRequestException('unitIds must be a non-empty list or null')
                try:
                    unit_ids = sorted({int(x) for x in unit_ids})
                except (TypeError, ValueError):
                    raise BadRequestException('unitIds must contain integers')
                if len(unit_ids) > MAX_SCOPED_UNITS:
                    raise BadRequestException(f'At most {MAX_SCOPED_UNITS} units per scoped run')
            run_id = self._start_run(unit_ids)
        else:
            try:
                run_id = int(run_id)
            except (TypeError, ValueError):
                raise BadRequestException('runId must be an integer')

        try:
            # Savepoint: a lock failure must not roll back the request's transaction.
            # The row lock itself outlives the savepoint and holds until commit.
            with self.db.begin_nested():
                row = self.db.execute(text(
                    "SELECT * FROM data_policy_runs WHERE id = :id FOR UPDATE NOWAIT"), {'id': run_id}).fetchone()
        except Exception:
            # Another step holds the run. Report state without waiting on the lock.
            return {**self.get_run(run_id), 'busy': True}
        if not row:
            raise NotFoundException('Run not found')
        if row.status != 'running':
            return self._run_out(row)

        self.db.execute(text(f"SET LOCAL statement_timeout = {int(PROBE_TIMEOUT_MS)}"))
        pending: List[str] = list(_json(row.pending_keys) or [])
        errors: List[Dict[str, str]] = list(_json(row.probe_errors) or [])
        rules = _json(row.rules_snapshot) or []
        scope = _json(row.scope_unit_ids)

        while pending and time.monotonic() - t0 < STEP_BUDGET_S:
            key = pending[0]
            cat = C.CATEGORY_BY_KEY.get(key)
            p0 = time.monotonic()
            result, err = {}, None
            if cat is not None:
                try:
                    with self.db.begin_nested():
                        result = self._probe(cat, [r for r in rules if r['categoryKey'] == key], scope)
                except Exception as e:  # one bad category must not sink the run
                    err = str(getattr(e, 'orig', e)).strip().splitlines()[0][:300]
                    logger.warning('data-policy probe %s failed: %s', key, err)
            if err:
                errors.append({'categoryKey': key, 'error': err})
            self.db.execute(text(
                "INSERT INTO data_policy_run_probes (run_id, category_key, result, duration_ms, error) "
                "VALUES (:run, :key, CAST(:result AS jsonb), :ms, :err) "
                "ON CONFLICT (run_id, category_key) DO UPDATE SET result = EXCLUDED.result, "
                " duration_ms = EXCLUDED.duration_ms, error = EXCLUDED.error"
            ), {'run': run_id, 'key': key, 'result': json.dumps(result), 'ms': int((time.monotonic() - p0) * 1000),
                'err': err})
            pending.pop(0)

        self.db.execute(text(
            "UPDATE data_policy_runs SET pending_keys = CAST(:p AS jsonb), probe_errors = CAST(:e AS jsonb), "
            " updated_date = now() WHERE id = :id"), {'p': json.dumps(pending), 'e': json.dumps(errors), 'id': run_id})

        if not pending and time.monotonic() - t0 < FINALIZE_DEFER_S:
            self._finalize(run_id)
        row = self.db.execute(text("SELECT * FROM data_policy_runs WHERE id = :id"), {'id': run_id}).fetchone()
        return self._run_out(row)

    def _probe(self, cat: Dict[str, Any], rules: List[Dict[str, Any]], scope: Optional[List[int]]) -> Dict[str, Any]:
        base = C.category_sql(cat, self.db)
        if not base:
            return {}
        params: Dict[str, Any] = {}
        if scope:
            params['unit_ids'] = scope
        base = _apply_unit_filter(base, bool(scope))
        cols = [
            "b.unit_id",
            "SUM(CASE WHEN b.deleted_at IS NULL THEN 1 ELSE 0 END) AS live_count",
            "MIN(CASE WHEN b.deleted_at IS NULL THEN b.age_at END) AS oldest_at",
            "MAX(CASE WHEN b.deleted_at IS NULL THEN b.age_at END) AS newest_at",
            "SUM(CASE WHEN b.deleted_at IS NULL THEN COALESCE(b.items, 0) ELSE 0 END) AS item_count",
            "SUM(CASE WHEN b.deleted_at IS NOT NULL THEN 1 ELSE 0 END) AS soft_deleted_count",
            "MIN(b.deleted_at) AS oldest_deleted_at",
            "SUM(CASE WHEN b.deleted_at IS NULL AND b.pii = 1 THEN 1 ELSE 0 END) AS pii_live_count",
            "MIN(CASE WHEN b.deleted_at IS NULL AND b.pii = 1 THEN b.age_at END) AS pii_oldest_at",
        ]
        rule_cols: List[int] = []
        for r in rules:
            if r['action'] not in CUTOFF_ACTIONS or r['action'] not in cat['supportedActions']:
                continue
            rid = int(r['id'])
            p = f'r{rid}'
            if r['action'] == 'retain_min':
                cond = (f"b.deleted_at IS NOT NULL AND b.age_at IS NOT NULL "
                        f"AND EXTRACT(EPOCH FROM (b.deleted_at - b.age_at)) < :{p}_secs")
                params[f'{p}_secs'] = r['minSeconds']
                cols += [f"SUM(CASE WHEN {cond} THEN 1 ELSE 0 END) AS {p}_n",
                         f"MIN(CASE WHEN {cond} THEN b.age_at END) AS {p}_min"]
            else:
                if r['action'] == 'purge_soft_deleted':
                    col, live = 'b.deleted_at', 'b.deleted_at IS NOT NULL'
                else:
                    col, live = 'b.age_at', 'b.deleted_at IS NULL'
                if r['action'] == 'anonymize':
                    live += ' AND b.pii = 1'
                params[f'{p}_due'] = r['dueCutoff']
                params[f'{p}_over'] = r['overCutoff']
                cols += [f"SUM(CASE WHEN {live} AND {col} < CAST(:{p}_due AS timestamptz) THEN 1 ELSE 0 END) AS {p}_n",
                         f"SUM(CASE WHEN {live} AND {col} < CAST(:{p}_over AS timestamptz) THEN 1 ELSE 0 END) AS {p}_o"]
            rule_cols.append(rid)
        sql = f"SELECT {', '.join(cols)} FROM ({base}) b WHERE b.unit_id IS NOT NULL GROUP BY b.unit_id"
        out: Dict[str, Any] = {}
        for row in self.db.execute(text(sql), params).fetchall():
            m = row._mapping
            metrics: Dict[str, Any] = {
                'liveCount': int(m['live_count'] or 0),
                'oldestAt': _iso(m['oldest_at']),
                'newestAt': _iso(m['newest_at']),
                'itemCount': int(m['item_count'] or 0) if cat.get('itemLabel') else None,
                'softDeletedCount': int(m['soft_deleted_count'] or 0) if cat['softDelete'] else None,
                'oldestDeletedAt': _iso(m['oldest_deleted_at']) if cat['softDelete'] else None,
                'piiLiveCount': int(m['pii_live_count'] or 0) if cat['piiFields'] else None,
                'piiOldestAt': _iso(m['pii_oldest_at']) if cat['piiFields'] else None,
                'rules': {},
            }
            for rid in rule_cols:
                p = f'r{rid}'
                metrics['rules'][str(rid)] = {
                    'n': int(m.get(f'{p}_n') or 0),
                    'o': int(m.get(f'{p}_o') or 0) if f'{p}_o' in m else None,
                    'min': _iso(m.get(f'{p}_min')) if f'{p}_min' in m else None,
                }
            out[str(int(m['unit_id']))] = metrics
        return out

    def _finalize(self, run_id: int) -> None:
        run = self.db.execute(text("SELECT * FROM data_policy_runs WHERE id = :id"), {'id': run_id}).fetchone()
        started = run.started_at if run.started_at.tzinfo else run.started_at.replace(tzinfo=timezone.utc)
        rules = _json(run.rules_snapshot) or []
        scope = _json(run.scope_unit_ids)
        probes = {
            r.category_key: (_json(r.result) or {})
            for r in self.db.execute(text(
                "SELECT category_key, result FROM data_policy_run_probes WHERE run_id = :id"), {'id': run_id})
        }
        rules_by_cat: Dict[str, List[Dict[str, Any]]] = {}
        for r in rules:
            rules_by_cat.setdefault(r['categoryKey'], []).append(r)

        units = self._unit_states(scope)
        payload: List[Dict[str, Any]] = []
        all_issues = 0
        totals = {s: 0 for s in SEVERITIES}
        for unit in units:
            uid = str(unit['id'])
            inventory, issues = [], []
            total, oldest = 0, None
            for key, result in probes.items():
                cat = C.CATEGORY_BY_KEY.get(key)
                if not cat:
                    continue
                m = result.get(uid)
                if m:
                    inventory.append(_inventory_row(key, m))
                    if cat['_primary']:
                        total += m['liveCount']
                    if m.get('oldestAt') and (oldest is None or m['oldestAt'] < oldest):
                        oldest = m['oldestAt']
                for rule in rules_by_cat.get(key, []):
                    issue = evaluate(rule, cat, unit, m, started)
                    if issue:
                        issues.append(issue)
            counts = severity_counts(issues)
            for s in SEVERITIES:
                totals[s] += counts[s]
            all_issues += len(issues)
            payload.append({
                'unit_id': unit['id'], 'issue_count': len(issues),
                **{f'{s}_count': counts[s] for s in SEVERITIES},
                'total_records': total, 'oldest_record_at': oldest,
                'inventory': inventory, 'issues': issues,
            })

        for i in range(0, len(payload), UPSERT_CHUNK):
            self.db.execute(text(
                "INSERT INTO data_policy_unit_results (unit_id, run_id, diagnosed_at, issue_count, critical_count, "
                " high_count, medium_count, low_count, info_count, total_records, oldest_record_at, inventory, issues, "
                " updated_date) "
                "SELECT x.unit_id, :run, :at, x.issue_count, x.critical_count, x.high_count, x.medium_count, "
                " x.low_count, x.info_count, x.total_records, x.oldest_record_at, x.inventory, x.issues, now() "
                "FROM jsonb_to_recordset(CAST(:payload AS jsonb)) AS x(unit_id bigint, issue_count int, "
                " critical_count int, high_count int, medium_count int, low_count int, info_count int, "
                " total_records bigint, oldest_record_at timestamptz, inventory jsonb, issues jsonb) "
                "ON CONFLICT (unit_id) DO UPDATE SET run_id = EXCLUDED.run_id, diagnosed_at = EXCLUDED.diagnosed_at, "
                " issue_count = EXCLUDED.issue_count, critical_count = EXCLUDED.critical_count, "
                " high_count = EXCLUDED.high_count, medium_count = EXCLUDED.medium_count, "
                " low_count = EXCLUDED.low_count, info_count = EXCLUDED.info_count, "
                " total_records = EXCLUDED.total_records, oldest_record_at = EXCLUDED.oldest_record_at, "
                " inventory = EXCLUDED.inventory, issues = EXCLUDED.issues, updated_date = now()"
            ), {'run': run_id, 'at': datetime.now(timezone.utc), 'payload': json.dumps(payload[i:i + UPSERT_CHUNK])})

        self.db.execute(text("DELETE FROM data_policy_run_probes WHERE run_id = :id"), {'id': run_id})
        self.db.execute(text(
            # clock_timestamp(), not now(): now() is the TRANSACTION start, which for a
            # one-step run is earlier than started_at and yields a negative duration.
            "UPDATE data_policy_runs SET status = 'completed', finished_at = clock_timestamp(), "
            " duration_ms = CAST(EXTRACT(EPOCH FROM (clock_timestamp() - started_at)) * 1000 AS bigint), "
            " units_scanned = :units, issues_found = :issues, severity_counts = CAST(:counts AS jsonb), "
            " updated_date = now() WHERE id = :id"
        ), {'units': len(units), 'issues': all_issues, 'counts': json.dumps(totals), 'id': run_id})


def _apply_unit_filter(sql: str, scoped: bool) -> str:
    """Replace every /*UF:<expr>*/ marker with the unit filter (or nothing)."""
    out, start = [], 0
    while True:
        i = sql.find('/*UF:', start)
        if i < 0:
            out.append(sql[start:])
            return ''.join(out)
        j = sql.find('*/', i)
        expr = sql[i + 5:j]
        out.append(sql[start:i])
        out.append(f"AND ({expr}) = ANY(:unit_ids)" if scoped else '')
        start = j + 2


def _inventory_row(key: str, m: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'categoryKey': key,
        'liveCount': m['liveCount'],
        'itemCount': m.get('itemCount'),
        'oldestAt': m.get('oldestAt'),
        'newestAt': m.get('newestAt'),
        'softDeletedCount': m.get('softDeletedCount'),
        'oldestDeletedAt': m.get('oldestDeletedAt'),
        'piiLiveCount': m.get('piiLiveCount'),
        'piiOldestAt': m.get('piiOldestAt'),
    }


def _empty_inventory(key: str, error: Optional[str]) -> Dict[str, Any]:
    cat = C.CATEGORY_BY_KEY.get(key) or {}
    return {
        'categoryKey': key, 'liveCount': 0,
        'itemCount': 0 if cat.get('itemLabel') else None,
        'oldestAt': None, 'newestAt': None,
        'softDeletedCount': 0 if cat.get('softDelete') else None, 'oldestDeletedAt': None,
        'piiLiveCount': 0 if cat.get('piiFields') else None, 'piiOldestAt': None,
        'error': error,
    }
