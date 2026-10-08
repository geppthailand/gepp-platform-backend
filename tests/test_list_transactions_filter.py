"""GET /api/epr/ai_audit/transactions — the transaction_id filter.

Callers know a transaction by the id they posted it with (raw_data->>'id'),
not by epr_transactions_embeded.id, which is internal to this table. Same
convention the PUT and PATCH routes already use.
"""

import pytest

def _bad_request():
    """Resolved at call time, not import time.

    conftest snapshots and restores sys.modules per test, so a class imported
    at module load can be a DIFFERENT object from the one the service raises
    later — pytest.raises then catches nothing and the test fails while the
    code is correct. Importing inside the test sidesteps that entirely.
    """
    from GEPPPlatform.libs.exceptions import BadRequestException
    return BadRequestException



from GEPPPlatform.services.cores.epr_ai_audit.api.service import (
    _MAX_PAGE_SIZE, EprAiAuditService,
)


class CapturingDB:
    """Records the SQL and params so the WHERE clause can be asserted on."""

    def __init__(self):
        self.calls = []

    def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params or {}))
        db = self

        class R:
            def scalar(self):
                return 0

            def fetchall(self):
                return []
        return R()

    @property
    def where(self):
        return self.calls[0][0]

    @property
    def params(self):
        return self.calls[0][1]


def _list(**qp):
    db = CapturingDB()
    EprAiAuditService(db).list_transactions(qp)
    return db


def test_filtering_by_the_legacy_transaction_id():
    """Imported rows carry the legacy id at raw_data->>'_legacy_id'; rows
    posted live carry the caller's own at raw_data->>'id'. One filter has to
    find a transaction whichever way it arrived."""
    db = _list(transaction_id="151008")
    assert "raw_data->>'_legacy_id' = ANY(:transaction_ids)" in db.where
    assert "raw_data->>'id' = ANY(:transaction_ids)" in db.where
    assert db.params["transaction_ids"] == ["151008"]


def test_several_ids_in_one_call():
    """A list screen showing specific transactions should not need N requests."""
    db = _list(transaction_id="151008,151009 , 151010")
    assert db.params["transaction_ids"] == ["151008", "151009", "151010"]


def test_it_does_not_filter_on_the_embeded_id():
    db = _list(transaction_id="4482")
    assert "t.id = ANY" not in db.where
    assert db.params["transaction_ids"] == ["4482"]


def test_a_non_numeric_id_is_rejected_with_the_offending_value():
    """These ids are numeric. Silently matching nothing would look like "no
    results" rather than "you sent the wrong thing"."""
    with pytest.raises(_bad_request(), match="PRO2506-008"):
        _list(transaction_id="PRO2506-008")
    with pytest.raises(_bad_request()):
        _list(transaction_id="151008,oops")


def test_it_combines_with_the_other_filters():
    db = _list(transaction_id="151008", project_id="55", status="flagged")
    for clause in ("_legacy_id", "t.epr_project_id = :project_id",
                   "t.status = :status"):
        assert clause in db.where
    assert db.params["project_id"] == 55


def test_an_absent_or_empty_filter_is_ignored():
    for db in (_list(), _list(transaction_id=""), _list(transaction_id=None)):
        assert "_legacy_id" not in db.where


def test_a_blank_list_of_ids_is_rejected_not_silently_dropped():
    with pytest.raises(_bad_request()):
        _list(transaction_id=" , ")


def test_page_size_over_the_cap_is_a_clear_400():
    """page_size=500 is what a frontend reaches for first; the message has to
    say the limit, not just refuse."""
    with pytest.raises(_bad_request(), match=str(_MAX_PAGE_SIZE)):
        _list(page_size="500")


def test_the_cap_is_a_hundred():
    assert _MAX_PAGE_SIZE == 100


# ── the id a caller actually knows ─────────────────────────────────────────

def test_an_imported_row_reports_its_legacy_id():
    from GEPPPlatform.services.cores.epr_ai_audit.api.service import _source_id
    assert _source_id({"_legacy_id": 151008, "id": 727}) == 151008


def test_a_live_posted_row_reports_the_id_it_was_posted_with():
    from GEPPPlatform.services.cores.epr_ai_audit.api.service import _source_id
    assert _source_id({"id": 90210}) == 90210


def test_neither_present_is_none_not_a_crash():
    from GEPPPlatform.services.cores.epr_ai_audit.api.service import _source_id
    assert _source_id({}) is None and _source_id(None) is None
