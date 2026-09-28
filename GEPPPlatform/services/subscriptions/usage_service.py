"""Usage actually consumed in a subscription period — the billing input.

Everything here is DERIVED from `transactions`, never read from a counter.

That is a deliberate and load-bearing choice. `subscription_monthly_quotas`
already carries a `create_transaction_usage` column, but it is incremented on
exactly one write path (the BMA integration) out of several — web create, QR
channel, IoT scale intake and imports all miss it. It is therefore already wrong
for most organizations. A billing number that drifts silently is worse than a
slower query, and recomputation is idempotent and back-dateable in a way an
incrementing counter can never be.

The monthly allowance is ADVISORY: nothing blocks on it. This report is the
whole point of recording it — it turns "they went over" into a number someone
can invoice.
"""

from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from .limits import (
    _as_date,
    months_in_period,
    resolve_org_limits,
)


def _month_key(d: date) -> str:
    return f'{d.year:04d}-{d.month:02d}'


def _month_span(start: date, end: date) -> List[str]:
    """Every 'YYYY-MM' from start to end inclusive, so months with ZERO
    transactions still appear as rows. A gap the report omits reads as "we have
    no data"; a 0 reads as "they used none", which is the fact being billed."""
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append(f'{y:04d}-{m:02d}')
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


class SubscriptionUsageService:
    """Reads only. Safe against a read-only session."""

    def __init__(self, db):
        self.db = db

    # ── the report ────────────────────────────────────────────────────

    def period_usage(self, subscription_id: int,
                     as_of: Optional[date] = None) -> Dict[str, Any]:
        """Quota set vs quota used for one subscription period.

        Returns a dict shaped for both the backoffice detail modal and the Excel
        export, so the two can never disagree about the numbers.
        """
        from ...models.subscriptions.subscription_models import Subscription

        as_of = as_of or datetime.now(timezone.utc).date()

        period = (
            self.db.query(Subscription)
            .filter(Subscription.id == subscription_id,
                    Subscription.deleted_date.is_(None))
            .first()
        )
        if period is None:
            return {'success': False, 'message': f'Subscription {subscription_id} not found'}

        org_id = period.organization_id
        start = _as_date(period.current_period_starts_at)
        # An open-ended period reports up to today rather than reporting nothing.
        end = _as_date(period.current_period_ends_at) or as_of

        # Resolve through the shared resolver rather than reading the row, so the
        # report shows the SAME effective numbers the enforcement path uses —
        # including values inherited from the org default.
        limits = resolve_org_limits(self.db, org_id, at=start, period=period)

        monthly_allowance = limits.transactions_per_month
        months = months_in_period(start, end, cap_at=as_of)
        # Bill only months that have actually begun. A 12-month contract three
        # months in has consumed three months of allowance, not twelve.
        elapsed = months_in_period(start, min(end, as_of), cap_at=as_of) if start else 0

        by_month = self._transactions_by_month(org_id, start, end)
        by_location = self._transactions_by_location(org_id, start, end)

        month_keys = _month_span(start, end) if start else []
        months_detail = []
        for key in month_keys:
            used = by_month.get(key, 0)
            months_detail.append({
                'month': key,
                'allowance': monthly_allowance,
                'used': used,
                'over': max(0, used - monthly_allowance),
                # A month that has not started yet is not an underspend.
                'in_past': key <= _month_key(as_of),
            })

        total_used = sum(by_month.values())
        total_allowance = monthly_allowance * months
        elapsed_allowance = monthly_allowance * elapsed

        return {
            'success': True,
            'subscription_id': period.id,
            'organization_id': org_id,
            'plan_id': period.plan_id,
            'plan_name': period.plan.display_name if period.plan else None,
            'period_label': period.period_label,
            'status': period.status,
            'period_start': start.isoformat() if start else None,
            'period_end': (_as_date(period.current_period_ends_at).isoformat()
                           if period.current_period_ends_at else None),
            'is_open_ended': period.current_period_ends_at is None,
            'as_of': as_of.isoformat(),

            # ── what was agreed ──
            'transactions_per_month': monthly_allowance,
            'transactions_limit_is_advisory': True,
            'max_file_size_mb': limits.max_file_size_mb,
            'limit_sources': {
                'transactions': limits.transactions_source,
                'file_size': limits.file_size_source,
            },

            # ── what it adds up to ──
            'months_in_period': months,
            'months_elapsed': elapsed,
            'total_allowance': total_allowance,
            'elapsed_allowance': elapsed_allowance,

            # ── what was used ──
            'total_used': total_used,
            # Measured against the allowance for months that have STARTED, which
            # is the only comparison that means anything mid-contract.
            'over_allowance': max(0, total_used - elapsed_allowance),
            'utilisation_pct': (round(total_used / elapsed_allowance * 100, 1)
                                if elapsed_allowance else None),
            'months_over': sum(1 for m in months_detail
                               if m['in_past'] and m['over'] > 0),

            'months': months_detail,
            # The org-level limit is contractual, but ops still needs to see
            # WHICH site drove the overage.
            'locations': by_location,
        }

    # ── queries ───────────────────────────────────────────────────────

    def _transactions_by_month(self, org_id: int, start: Optional[date],
                               end: Optional[date]) -> Dict[str, int]:
        """Counted on `transaction_date`, not `created_date`.

        A transaction back-dated into last month belongs to last month's
        allowance — that is the month the waste was actually collected, and it is
        what a customer disputing an invoice will point at.
        """
        if start is None:
            return {}
        rows = self._exec(
            """
            SELECT to_char(date_trunc('month', t.transaction_date), 'YYYY-MM') AS ym,
                   COUNT(*) AS n
              FROM transactions t
             WHERE t.organization_id = %(org)s
               AND t.deleted_date IS NULL
               AND t.transaction_date >= %(start)s
               AND t.transaction_date < %(end_exclusive)s
             GROUP BY 1
            """,
            {'org': org_id, 'start': start, 'end_exclusive': _next_month_start(end)},
        )
        return {r[0]: int(r[1]) for r in rows}

    def _transactions_by_location(self, org_id: int, start: Optional[date],
                                  end: Optional[date]) -> List[Dict[str, Any]]:
        """Per-origin breakdown, biggest first.

        The contractual limit is org-wide, so this carries no allowance of its
        own — it answers "which site is responsible for the volume?", which is
        the question that follows every overage.
        """
        if start is None:
            return []
        rows = self._exec(
            """
            SELECT t.origin_id,
                   COALESCE(ul.name_th, ul.name_en, ul.display_name,
                            ul.company_name, '(unassigned)') AS name,
                   COUNT(*) AS n
              FROM transactions t
              LEFT JOIN user_locations ul ON ul.id = t.origin_id
             WHERE t.organization_id = %(org)s
               AND t.deleted_date IS NULL
               AND t.transaction_date >= %(start)s
               AND t.transaction_date < %(end_exclusive)s
             GROUP BY 1, 2
             ORDER BY n DESC
            """,
            {'org': org_id, 'start': start, 'end_exclusive': _next_month_start(end)},
        )
        return [
            {'location_id': r[0], 'location_name': (r[1] or '').strip(), 'used': int(r[2])}
            for r in rows
        ]

    def _exec(self, sql: str, params: Dict[str, Any]):
        """Run raw SQL against either a Session or a bare DBAPI connection.

        `exec_driver_sql` passes psycopg2's `%(name)s` paramstyle straight
        through, so one SQL string serves both.
        """
        conn = getattr(self.db, 'connection', None)
        if callable(conn):
            return self.db.connection().exec_driver_sql(sql, params).fetchall()
        with self.db.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def _next_month_start(d: date) -> date:
    """First day of the month AFTER `d`.

    The range predicate is half-open (`>= start AND < end_exclusive`) rather
    than `<= end`, because `transaction_date` is a timestamptz: `<= '2026-03-31'`
    silently drops everything logged during that last day.
    """
    return date(d.year + 1, 1, 1) if d.month == 12 else date(d.year, d.month + 1, 1)
