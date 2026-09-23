"""Async OCR jobs.

The failure modes that matter are the silent ones: a job nobody is running, a
job run twice, and an exception that never reaches the poller.
"""

import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from GEPPPlatform.services.cores.epr_ai_audit.api import ocr_jobs


class FakeResult:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class FakeDB:
    """Records statements; returns whatever row was queued."""

    def __init__(self, row=None):
        self.row = row
        self.statements = []
        self.commits = 0

    def execute(self, stmt, params=None):
        self.statements.append((str(stmt), params or {}))
        return FakeResult(self.row)

    def commit(self):
        self.commits += 1


def _sql(db):
    return " | ".join(s for s, _ in db.statements)


# ── create ─────────────────────────────────────────────────────────────────

def test_create_job_returns_an_unguessable_id(monkeypatch):
    monkeypatch.setattr(ocr_jobs, "_dispatch", lambda job_id: None)
    db = FakeDB()
    out = ocr_jobs.create_job(db, ["u0"], [{"name": "invoiceNo"}])
    assert out["status"] == ocr_jobs.PENDING
    assert out["job_id"].startswith("ocr_")
    # 32 hex chars — this id is the only thing guarding a public endpoint
    assert len(out["job_id"]) == len("ocr_") + 32


def test_create_job_commits_before_dispatching(monkeypatch):
    """The other invocation opens its own session and cannot see an
    uncommitted row — this ordering is the whole reason it works."""
    seen = {}
    db = FakeDB()
    monkeypatch.setattr(ocr_jobs, "_dispatch",
                        lambda job_id: seen.update(commits_at_dispatch=db.commits))
    ocr_jobs.create_job(db, ["u0"], [])
    assert seen["commits_at_dispatch"] == 1


def test_create_job_stores_the_request_verbatim(monkeypatch):
    monkeypatch.setattr(ocr_jobs, "_dispatch", lambda job_id: None)
    db = FakeDB()
    fields = [{"name": "invoiceNo", "type": "text"}]
    ocr_jobs.create_job(db, ["u0", "u1"], fields)
    _, params = db.statements[0]
    assert json.loads(params["request"]) == {"files": ["u0", "u1"], "fields": fields}


def test_a_job_that_cannot_be_dispatched_fails_immediately(monkeypatch):
    """Otherwise it sits at 'pending' until the caller's timeout with no reason.
    This is exactly what happens if the Lambda role cannot invoke itself."""
    def boom(job_id):
        raise PermissionError("AccessDeniedException")

    monkeypatch.setattr(ocr_jobs, "_dispatch", boom)
    db = FakeDB()
    out = ocr_jobs.create_job(db, ["u0"], [])
    assert out["status"] == ocr_jobs.FAILED
    assert "UPDATE epr_ocr_jobs" in _sql(db)


def test_dispatch_outside_lambda_is_a_clear_error(monkeypatch):
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    with pytest.raises(RuntimeError, match="AWS_LAMBDA_FUNCTION_NAME"):
        ocr_jobs._dispatch("ocr_x")


def test_dispatch_is_fire_and_forget(monkeypatch):
    calls = {}

    class FakeLambda:
        def invoke(self, **kw):
            calls.update(kw)

    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "DEV-GEPPPlatform")
    monkeypatch.setattr(ocr_jobs.boto3, "client", lambda svc: FakeLambda())
    ocr_jobs._dispatch("ocr_abc")
    assert calls["InvocationType"] == "Event"          # never RequestResponse
    assert calls["FunctionName"] == "DEV-GEPPPlatform"  # itself
    assert json.loads(calls["Payload"]) == {
        "async_task": ocr_jobs.ASYNC_TASK, "job_id": "ocr_abc"}


# ── read ───────────────────────────────────────────────────────────────────

def test_get_job_returns_none_when_missing():
    assert ocr_jobs.get_job(FakeDB(None), "ocr_nope") is None


def test_get_job_shape_is_what_the_poller_expects():
    db = FakeDB(("ocr_1", "transaction", "done", {"transaction": {}}, None))
    assert ocr_jobs.get_job(db, "ocr_1") == {
        "job_id": "ocr_1", "kind": "transaction", "status": "done",
        "result": {"transaction": {}}, "error": None,
    }


# ── run ────────────────────────────────────────────────────────────────────

@contextmanager
def _session(db):
    yield db


def _patch_session(monkeypatch, db):
    import GEPPPlatform.libs.database as database
    monkeypatch.setattr(database, "get_session", lambda: _session(db))


def test_run_job_does_the_ocr_and_stores_the_result(monkeypatch):
    db = FakeDB(("transaction", ocr_jobs.PENDING, {"files": ["u0"], "fields": []}))
    _patch_session(monkeypatch, db)
    import GEPPPlatform.services.cores.epr_ai_audit.api.ocr as ocr
    monkeypatch.setattr(ocr, "read_transaction", lambda f, fl: {"transaction": {"invoiceNo": "X"}})

    out = ocr_jobs.run_job("ocr_1")
    assert out["status"] == ocr_jobs.DONE
    stored = [p for s, p in db.statements if "result" in s][-1]
    assert json.loads(stored["result"]) == {"transaction": {"invoiceNo": "X"}}


def test_run_job_is_idempotent_because_lambda_retries(monkeypatch):
    """An async invocation is retried on failure, so the same event can arrive
    twice. Redoing it would pay for the model call again."""
    db = FakeDB(("transaction", ocr_jobs.DONE, {"files": [], "fields": []}))
    _patch_session(monkeypatch, db)
    out = ocr_jobs.run_job("ocr_1")
    assert out["status"] == ocr_jobs.DONE
    assert "UPDATE" not in _sql(db)          # nothing was rewritten


def test_run_job_writes_failures_to_the_row_not_just_the_log(monkeypatch):
    """An exception that only reaches CloudWatch leaves the caller polling a
    job stuck at 'processing' forever."""
    db = FakeDB(("transaction", ocr_jobs.PENDING, {"files": ["u0"], "fields": []}))
    _patch_session(monkeypatch, db)
    import GEPPPlatform.services.cores.epr_ai_audit.api.ocr as ocr

    def boom(files, fields):
        raise ValueError("OCR response was truncated")

    monkeypatch.setattr(ocr, "read_transaction", boom)
    out = ocr_jobs.run_job("ocr_1")
    assert out["status"] == ocr_jobs.FAILED
    err = [p for s, p in db.statements if "error" in s][-1]
    assert "truncated" in err["error"]


def test_run_job_on_a_missing_job_does_not_explode(monkeypatch):
    db = FakeDB(None)
    _patch_session(monkeypatch, db)
    assert ocr_jobs.run_job("ocr_gone")["status"] == "missing"


def test_audit_kind_uses_the_audit_reader(monkeypatch):
    db = FakeDB((ocr_jobs.KIND_AUDIT, ocr_jobs.PENDING, {"files": ["u0"], "fields": []}))
    _patch_session(monkeypatch, db)
    import GEPPPlatform.services.cores.epr_ai_audit.api.ocr as ocr
    monkeypatch.setattr(ocr, "read_audit", lambda f, fl: {"section": {}})
    monkeypatch.setattr(ocr, "read_transaction",
                        lambda f, fl: pytest.fail("wrong reader for kind=audit"))
    assert ocr_jobs.run_job("ocr_1")["status"] == ocr_jobs.DONE


def test_error_message_is_truncated():
    db = FakeDB()
    ocr_jobs.fail_job(db, "ocr_1", "x" * 5000)
    _, params = db.statements[-1]
    assert len(params["error"]) == ocr_jobs.ERROR_MAX_LEN


# ── routing: two job paths, mirroring the two sync OCR endpoints ───────────

import GEPPPlatform.services.cores.epr_ai_audit.api.handlers as handlers


@pytest.fixture
def no_dispatch(monkeypatch):
    """Run the real handler and the real create_job, just don't invoke Lambda."""
    monkeypatch.setattr(ocr_jobs, "_dispatch", lambda job_id: None)
    monkeypatch.setattr(handlers, "EprAiAuditService", lambda db: None)


def _kind_written(db):
    """The kind create_job actually persisted."""
    return db.statements[0][1]["kind"]


def _post(path, db, body=None):
    return handlers.handle_epr_ai_audit_routes(
        {"rawPath": path},
        data=body or {"files": ["u0"], "fields": []},
        method="POST", db_session=db)


def test_transaction_path_uses_the_transaction_reader(no_dispatch):
    db = FakeDB()
    _post("/api/epr/ai_audit/ocr/jobs", db)
    assert _kind_written(db) == ocr_jobs.KIND_TRANSACTION


def test_recycler_audit_path_uses_the_audit_reader(no_dispatch):
    """This path must exist or the recycler audit page 404s — it works today,
    so missing it would be a regression, unlike transactions which are new."""
    db = FakeDB()
    _post("/api/epr/ai_audit/recycler-audit-ocr/jobs", db)
    assert _kind_written(db) == ocr_jobs.KIND_AUDIT


def test_the_two_post_paths_do_not_collide(no_dispatch):
    # "/recycler-audit-ocr/jobs" must not be swallowed by the "/ocr/jobs" rule
    a, b = FakeDB(), FakeDB()
    _post("/api/epr/ai_audit/ocr/jobs", a)
    _post("/api/epr/ai_audit/recycler-audit-ocr/jobs", b)
    assert (_kind_written(a), _kind_written(b)) == (
        ocr_jobs.KIND_TRANSACTION, ocr_jobs.KIND_AUDIT)


@pytest.mark.parametrize("path", [
    "/api/epr/ai_audit/ocr/jobs/ocr_abc",
    "/api/epr/ai_audit/recycler-audit-ocr/jobs/ocr_abc",
])
def test_either_poll_path_resolves_a_job(no_dispatch, path):
    db = FakeDB(("ocr_abc", "transaction", "done", {}, None))
    out = handlers.handle_epr_ai_audit_routes(
        {"rawPath": path}, data={}, method="GET", db_session=db)
    assert out["data"]["job_id"] == "ocr_abc"


def test_an_explicit_kind_in_the_body_still_wins(no_dispatch):
    db = FakeDB()
    _post("/api/epr/ai_audit/ocr/jobs", db,
          {"files": ["u0"], "fields": [], "kind": "audit"})
    assert _kind_written(db) == ocr_jobs.KIND_AUDIT


def test_a_job_post_with_no_files_is_rejected(no_dispatch):
    from GEPPPlatform.libs.exceptions import APIException
    with pytest.raises(APIException):
        _post("/api/epr/ai_audit/recycler-audit-ocr/jobs", FakeDB(),
              {"files": [], "fields": []})
