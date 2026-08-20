"""ใบชั่งออกของผู้คัดแยกไม่โผล่ที่ไหนที่มนุษย์รีวิวงานชั่งเข้า.

The weigh-out (is_internal_transfer, migration 083) is a TRACEABILITY record —
where already-reviewed material went — not a new waste intake. Three surfaces
must therefore leave it out:

  * the web transaction list — the same kilograms already appear there as the
    weigh-in that brought them into the building; showing both reads as the
    material twice;
  * the AI audit sweep — an AI rejection would withdraw the tank's outbound
    legs on a row no list shows, so nobody could ever see or overturn it;
  * (the manual-audit inbox needs no filter: the IoT route stores weigh-outs
    approved at both levels, and that inbox selects by pending records only —
    which also makes it the escape hatch if a weigh-out ever lands pending.)

These tests capture the criteria the real functions apply to a recording
session and assert the exclusion is present and NULL-safe (`IS NOT true`, so
pre-083 rows with NULL keep appearing). The full query cannot run outside
Postgres — the models use JSONB/ARRAY — which is exactly why the *presence* of
the predicate is what gets pinned.
"""

from GEPPPlatform.services.cores.transactions.transaction_service import TransactionService
from GEPPPlatform.services.cores.transaction_audit.transaction_audit_service import (
    TransactionAuditService,
)


class _RecordingQuery:
    """Chains like a Query, records every filter criterion, returns nothing."""

    def __init__(self, log):
        self._log = log

    def options(self, *a, **k):
        return self

    def filter(self, *criteria):
        self._log.extend(criteria)
        return self

    def order_by(self, *a, **k):
        return self

    def offset(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def join(self, *a, **k):
        return self

    def outerjoin(self, *a, **k):
        return self

    def distinct(self, *a, **k):
        return self

    def count(self):
        return 0

    def all(self):
        return []

    def first(self):
        return None


class _RecordingDb:
    def __init__(self):
        self.criteria = []

    def query(self, *entities, **k):
        return _RecordingQuery(self.criteria)


def _compiled(criteria):
    return [str(c) for c in criteria]


def test_the_transaction_list_excludes_weigh_outs():
    db = _RecordingDb()
    TransactionService(db).list_transactions(organization_id=None)

    assert any(
        "is_internal_transfer IS NOT true" in s for s in _compiled(db.criteria)
    ), "list_transactions no longer filters out ผู้คัดแยก weigh-outs"


def test_the_list_exclusion_keeps_pre_083_null_rows():
    """isnot(True), not != True: a NULL (pre-083) row must keep appearing, or
    an old organization's entire history vanishes from the list."""
    db = _RecordingDb()
    TransactionService(db).list_transactions(organization_id=None)

    matching = [s for s in _compiled(db.criteria) if "is_internal_transfer" in s]
    assert matching, "exclusion predicate missing entirely"
    assert all("IS NOT true" in s for s in matching), (
        "predicate must be NULL-safe (IS NOT true), got: %s" % matching
    )


def test_the_ai_audit_sweep_excludes_weigh_outs():
    db = _RecordingDb()
    TransactionAuditService()._get_pending_transactions(db, organization_id=None)

    assert any(
        "is_internal_transfer IS NOT true" in s for s in _compiled(db.criteria)
    ), "_get_pending_transactions no longer filters out ผู้คัดแยก weigh-outs"


def test_the_ai_audit_sweep_excludes_deleted_transactions():
    """Observed on dev: soft-deleted weighings sat in the AI queue because the
    status filters never excluded them. Auditing a deleted row burns AI quota
    and can flip statuses nobody can see."""
    db = _RecordingDb()
    TransactionAuditService()._get_pending_transactions(db, organization_id=None)

    assert any(
        "deleted_date IS NULL" in s for s in _compiled(db.criteria)
    ), "_get_pending_transactions no longer excludes deleted transactions"
