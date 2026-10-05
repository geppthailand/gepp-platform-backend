"""
Advice snapshots + like / dislike feedback on report advice cards (B5, migration 100).

Two steps, both server-side so the numbers in a training sample are the numbers the engine
really used:

1. When the comparison report runs, `save_snapshot` stores what the advice engine saw — all
   metrics, every rule that matched (priority, shown or dropped), the rule-set fingerprint,
   period, mode and filters — deduplicated by content hash. The response carries its id.
2. When a user votes, `upsert` attaches the vote to that snapshot and stores a
   self-contained `sample` for the rule: its definition, the inputs it read with their
   values, whether the condition holds, its priority and the rendered text.

`training_rows` joins both into one record per vote (see scripts/export_advice_feedback.py).
Raw SQL keeps these small tables out of the ORM model registry.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from ....exceptions import ValidationException, NotFoundException

logger = logging.getLogger(__name__)

VOTES = ('like', 'dislike')
SECTIONS = ('risk', 'opportunity', 'quickwin')
MAX_COMMENT = 2000
FILTER_KEYS = ('location_ids', 'origin_ids', 'origin_combos', 'filter_tag_ids', 'filter_tenant_ids',
               'location_tag_id', 'tenant_id', 'material_ids', 'destination_ids')


def _day(v) -> Optional[date]:
    if not v:
        return None
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise ValidationException('date_from / date_to must be dates (YYYY-MM-DD)')


def _json_safe(v: Any) -> Any:
    """Metrics may hold dates / Decimals / sets; store them as plain JSON."""
    return json.loads(json.dumps(v, default=lambda o: sorted(o) if isinstance(o, (set, frozenset)) else str(o)))


def snapshot_filters(filters: Dict[str, Any]) -> Dict[str, Any]:
    """The data-scope part of the report filters (ids only, sorted), for the snapshot."""
    out = {}
    for k in FILTER_KEYS:
        v = (filters or {}).get(k)
        if v in (None, '', [], ()):
            continue
        if isinstance(v, (list, tuple, set)):
            try:
                v = sorted(v)
            except TypeError:   # e.g. origin_combos (dicts / tuples): keep the order
                v = list(v)
        out[k] = v
    return out


def save_snapshot(db: Session, organization_id: int, user_id: Optional[int], *, rules_version: str,
                  report_mode: str, compare_mode: str, periods: Dict[str, date], filters: Dict[str, Any],
                  metrics: Dict[str, Any], labels: Dict[str, Any], evaluated: List[Dict[str, Any]]) -> Optional[int]:
    """Store (or find) the snapshot of one advice evaluation; returns its id, None on failure.
    Never raises: a report must not fail because its feedback context could not be logged."""
    try:
        payload = {
            'org': organization_id, 'rules': rules_version, 'mode': report_mode, 'compare': compare_mode,
            'periods': {k: str(v) for k, v in periods.items()}, 'filters': _json_safe(filters),
            'metrics': _json_safe(metrics),
        }
        content_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
        nested = db.begin_nested()
        try:
            sid = db.execute(text("""
                INSERT INTO report_advice_snapshots
                    (organization_id, content_hash, rules_version, report_mode, compare_mode,
                     period_from, period_to, prev_from, prev_to, filters, metrics, labels, evaluated, created_by_id)
                VALUES (:org, :hash, :rules, :mode, :compare, :pf, :pt, :ppf, :ppt,
                        CAST(:filters AS JSONB), CAST(:metrics AS JSONB), CAST(:labels AS JSONB), CAST(:evaluated AS JSONB), :uid)
                ON CONFLICT (organization_id, content_hash) DO UPDATE SET updated_date = NOW()
                RETURNING id
            """), {
                'org': organization_id, 'hash': content_hash, 'rules': rules_version, 'mode': report_mode,
                'compare': compare_mode, 'pf': periods.get('cur_start'), 'pt': periods.get('cur_end'),
                'ppf': periods.get('prev_start'), 'ppt': periods.get('prev_end'),
                'filters': json.dumps(payload['filters'], ensure_ascii=False),
                'metrics': json.dumps(payload['metrics'], ensure_ascii=False),
                'labels': json.dumps(_json_safe(labels), ensure_ascii=False),
                'evaluated': json.dumps(_json_safe(evaluated), ensure_ascii=False),
                'uid': user_id,
            }).scalar()
            nested.commit()
        except Exception:
            nested.rollback()
            raise
        db.commit()
        return int(sid) if sid else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("[advice] snapshot not saved: %s", exc)
        return None


class AdviceFeedbackService:
    def __init__(self, db: Session):
        self.db = db

    # ── reads ───────────────────────────────────────────────────────────────
    def list_mine(self, user_id: int, snapshot_id=None, date_from=None, date_to=None) -> List[Dict[str, Any]]:
        if snapshot_id:
            q, params = "snapshot_id = :sid", {'sid': int(snapshot_id)}
        else:
            q = ("snapshot_id IS NULL AND COALESCE(period_from, '1900-01-01') = COALESCE(CAST(:pf AS DATE), '1900-01-01') "
                 "AND COALESCE(period_to, '1900-01-01') = COALESCE(CAST(:pt AS DATE), '1900-01-01')")
            params = {'pf': _day(date_from), 'pt': _day(date_to)}
        rows = self.db.execute(text(f"""
            SELECT rule_id, vote, comment FROM report_advice_feedback
            WHERE user_location_id = :uid AND deleted_date IS NULL AND {q}
        """), {'uid': user_id, **params}).mappings().all()
        return [dict(r) for r in rows]

    def _snapshot(self, organization_id: int, snapshot_id) -> Optional[Dict[str, Any]]:
        if not snapshot_id:
            return None
        try:
            sid = int(snapshot_id)
        except (TypeError, ValueError):
            raise ValidationException('snapshot_id must be a number')
        row = self.db.execute(text("""
            SELECT id, rules_version, report_mode, period_from, period_to, filters, metrics, labels, evaluated
            FROM report_advice_snapshots WHERE id = :id AND organization_id = :org AND deleted_date IS NULL
        """), {'id': sid, 'org': organization_id}).mappings().first()
        if not row:
            raise NotFoundException('Advice snapshot not found')
        return dict(row)

    def _sample(self, snap: Dict[str, Any], rule_id: str) -> Optional[Dict[str, Any]]:
        """Re-render the rule on the snapshot's metrics (deterministic) into a training sample."""
        from .report_insights import load_rules, rule_sample, rules_fingerprint, LANGS
        rules_doc = load_rules()
        rule = next((r for r in rules_doc.get('rules') or [] if r.get('id') == rule_id), None)
        if rule is None:
            return None
        metrics = snap.get('metrics') or {}
        labels = snap.get('labels') or {}
        txt = {lang: (labels.get(lang) or {}) for lang in LANGS}
        sample = rule_sample(rule, metrics, txt)
        ev = next((e for e in (snap.get('evaluated') or []) if e.get('id') == rule_id), None)
        sample['shown'] = ev.get('shown') if ev else None
        sample['evaluated_priority'] = ev.get('priority') if ev else None
        sample['rules_version'] = snap.get('rules_version')
        sample['rules_version_matches'] = snap.get('rules_version') == rules_fingerprint(rules_doc)
        return sample

    # ── write ───────────────────────────────────────────────────────────────
    def upsert(self, organization_id: int, user_id: int, body: Dict[str, Any]) -> Dict[str, Any]:
        rule_id = str(body.get('rule_id') or '').strip()
        if not rule_id or len(rule_id) > 64:
            raise ValidationException('rule_id is required')
        vote = body.get('vote')
        if vote not in (None, '') and vote not in VOTES:
            raise ValidationException("vote must be 'like', 'dislike' or empty")
        vote = vote or None
        comment = (body.get('comment') or '').strip()[:MAX_COMMENT] or None
        section = body.get('section') if body.get('section') in SECTIONS else None

        snap = self._snapshot(organization_id, body.get('snapshot_id'))
        sample = self._sample(snap, rule_id) if snap else None
        params = {
            'org': organization_id, 'uid': user_id, 'rule': rule_id, 'section': section,
            'mode': (snap or {}).get('report_mode') or body.get('report_mode') or None,
            'pf': (snap or {}).get('period_from') or _day(body.get('date_from')),
            'pt': (snap or {}).get('period_to') or _day(body.get('date_to')),
            'vote': vote, 'comment': comment,
            'sid': (snap or {}).get('id'),
            'rules': (snap or {}).get('rules_version'),
            'sample': json.dumps(_json_safe(sample), ensure_ascii=False) if sample else None,
            'filters': json.dumps(_json_safe((snap or {}).get('filters'))) if snap else None,
            'advice': (str(body.get('advice_text') or '')[:500] or None),
        }
        if params['sid']:
            where = "snapshot_id = :sid"
        else:
            where = ("snapshot_id IS NULL AND COALESCE(period_from, '1900-01-01') = COALESCE(CAST(:pf AS DATE), '1900-01-01') "
                     "AND COALESCE(period_to, '1900-01-01') = COALESCE(CAST(:pt AS DATE), '1900-01-01')")
        existing = self.db.execute(text(f"""
            SELECT id FROM report_advice_feedback
            WHERE user_location_id = :uid AND rule_id = :rule AND deleted_date IS NULL AND {where}
        """), params).scalar()
        if existing:
            self.db.execute(text("""
                UPDATE report_advice_feedback
                SET vote = :vote, comment = :comment, section = COALESCE(:section, section),
                    sample = COALESCE(CAST(:sample AS JSONB), sample), advice_text = COALESCE(:advice, advice_text),
                    updated_date = NOW()
                WHERE id = :id
            """), {**params, 'id': existing})
        else:
            self.db.execute(text("""
                INSERT INTO report_advice_feedback
                    (organization_id, user_location_id, rule_id, section, report_mode, period_from, period_to,
                     vote, comment, snapshot_id, rules_version, sample, filters, advice_text)
                VALUES (:org, :uid, :rule, :section, :mode, :pf, :pt, :vote, :comment, :sid, :rules,
                        CAST(:sample AS JSONB), CAST(:filters AS JSONB), :advice)
            """), params)
        self.db.commit()
        return {'rule_id': rule_id, 'vote': vote, 'comment': comment, 'snapshot_id': params['sid'],
                'sample_saved': sample is not None}


def training_rows(db: Session, organization_ids: Optional[Iterable[int]] = None,
                  rules_version: Optional[str] = None, only_votes: bool = True) -> List[Dict[str, Any]]:
    """One record per feedback: label (vote/comment), the rule sample and the full snapshot
    (all metrics + every matched rule) — the shape used to compare and to train / fine-tune."""
    conds, params = ["f.deleted_date IS NULL"], {}
    if only_votes:
        conds.append("f.vote IS NOT NULL")
    if organization_ids:
        conds.append("f.organization_id = ANY(:orgs)")
        params['orgs'] = list(organization_ids)
    if rules_version:
        conds.append("f.rules_version = :rv")
        params['rv'] = rules_version
    rows = db.execute(text(f"""
        SELECT f.id, f.organization_id, f.rule_id, f.section, f.vote, f.comment, f.report_mode,
               f.period_from, f.period_to, f.rules_version, f.sample, f.created_date, f.updated_date,
               s.id AS snapshot_id, s.compare_mode, s.filters, s.metrics, s.labels, s.evaluated
        FROM report_advice_feedback f
        LEFT JOIN report_advice_snapshots s ON s.id = f.snapshot_id
        WHERE {' AND '.join(conds)}
        ORDER BY f.id
    """), params).mappings().all()
    out = []
    for r in rows:
        out.append({
            'feedback_id': r['id'],
            'label': {'vote': r['vote'], 'comment': r['comment']},
            'rule_id': r['rule_id'],
            'section': r['section'],
            'sample': r['sample'],
            'context': {
                'organization_id': r['organization_id'], 'report_mode': r['report_mode'],
                'compare_mode': r['compare_mode'], 'period_from': str(r['period_from']) if r['period_from'] else None,
                'period_to': str(r['period_to']) if r['period_to'] else None, 'filters': r['filters'],
                'rules_version': r['rules_version'], 'snapshot_id': r['snapshot_id'],
            },
            'metrics': r['metrics'],
            'labels': r['labels'],
            'evaluated': r['evaluated'],
            'created_date': r['created_date'].isoformat() if r['created_date'] else None,
            'updated_date': r['updated_date'].isoformat() if r['updated_date'] else None,
        })
    return out
