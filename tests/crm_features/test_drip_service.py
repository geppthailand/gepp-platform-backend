"""
Unit tests for drip_service.py (Sprint 10 — Drip Sequences).

Coverage:
  - tick_advances_active_enrollment_when_due
  - tick_skips_when_skip_filter_matches
  - tick_marks_completed_on_last_step
  - tick_marks_errored_on_exception
  - enroll_is_idempotent_per_lead
  - auto_enroll_lead_status_changed_matches_target_status

Run:
    python -m pytest tests/crm_features/test_drip_service.py -v
"""

import sys
import os
import importlib.util as _ilu
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

_OWNS_EXCEPTION_BINDING = True  # opt out of conftest exception rebinding

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ─── Stub helpers ────────────────────────────────────────────────────────────

def _load(rel_path, name):
    spec = _ilu.spec_from_file_location(name, os.path.join(_ROOT, rel_path))
    mod = _ilu.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _stub(name):
    m = MagicMock()
    m.__spec__ = None
    sys.modules[name] = m
    return m


# ─── Exception stubs ─────────────────────────────────────────────────────────

class _APIExc(Exception):
    def __init__(self, msg="error", status_code=500, error_code="ERROR"):
        self.message = msg
        self.status_code = status_code
        super().__init__(msg)


class _NotFoundExc(_APIExc):
    def __init__(self, msg="not found", status_code=404, error_code="NOT_FOUND"):
        super().__init__(msg, status_code, error_code)


class _BadReqExc(_APIExc):
    def __init__(self, msg="bad request", status_code=400, error_code="BAD_REQUEST"):
        super().__init__(msg, status_code, error_code)


_exc_mod = _stub("GEPPPlatform.exceptions")
_exc_mod.NotFoundException   = _NotFoundExc
_exc_mod.BadRequestException = _BadReqExc
_exc_mod.APIException        = _APIExc

# ─── Package stubs ───────────────────────────────────────────────────────────

for _pkg in [
    "GEPPPlatform",
    "GEPPPlatform.models",
    "GEPPPlatform.models.crm",
    "GEPPPlatform.models.crm.drip",
    "GEPPPlatform.services",
    "GEPPPlatform.services.admin",
    "GEPPPlatform.services.admin.crm",
]:
    if _pkg not in sys.modules:
        _stub(_pkg)

# Stub sub-dependencies of drip_service
_delivery_sender_stub = _stub("GEPPPlatform.services.admin.crm.delivery_sender")
_delivery_sender_stub.enqueue_delivery = MagicMock(return_value={"status": "sent"})

_logger_stub = _stub("GEPPPlatform.services.admin.crm.logger")
_logger_stub.crm_log = MagicMock()
_logger_stub.new_correlation_id = MagicMock(return_value="test-cid")

_prop_filter_stub = _stub("GEPPPlatform.services.admin.crm.property_filter")
_prop_filter_stub.matches = MagicMock(return_value=False)

# Load the module under test
drip_service = _load(
    "GEPPPlatform/services/admin/crm/drip_service.py",
    "GEPPPlatform.services.admin.crm.drip_service",
)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_row(mapping: dict):
    """Build a mock row with ._mapping that _serialize can read."""
    row = MagicMock()
    row._mapping = mapping
    for k, v in mapping.items():
        setattr(row, k, v)
    row.__getitem__ = lambda self, idx: list(mapping.values())[idx]
    return row


def _now():
    return datetime.now(timezone.utc)


# ─── Tests ───────────────────────────────────────────────────────────────────

class TestTickAdvancesEnrollment(unittest.TestCase):
    """tick_enrollments advances current_step when a due enrollment exists."""

    def _build_db(self, skip_filter_matches=False):
        """Return a mock db that simulates one active enrollment due now."""
        db = MagicMock()
        _prop_filter_stub.matches.return_value = skip_filter_matches

        call_n = [0]

        def _exec(sql_or_text, params=None):
            res = MagicMock()
            call_n[0] += 1
            n = call_n[0]

            sql_str = str(getattr(sql_or_text, 'text', sql_or_text) or '').lower()

            # SELECT due enrollments
            if 'for update skip locked' in sql_str:
                res.fetchall.return_value = [
                    (101, 1, 42, None, 0)  # id, seq_id, lead_id, user_loc_id, current_step
                ]
            # SELECT step at current_step=0
            elif 'step_index = :idx' in sql_str and n <= 6:
                res.fetchone.return_value = _make_row({
                    "id": 1, "step_index": 0, "template_id": 7,
                    "delay_days": 0, "delay_hours": 0, "skip_filter": None
                })
            # SELECT lead props (for skip_filter)
            elif 'crm_leads' in sql_str and 'status' in sql_str:
                res.fetchone.return_value = _make_row({
                    "status": "new", "company": None, "country": None,
                    "language": None, "lead_score": 0, "tags": []
                })
            # SELECT lead email
            elif 'crm_leads' in sql_str and 'email' in sql_str:
                res.fetchone.return_value = (b'lead@example.com',)[0:1]
                res.fetchone.return_value = type('R', (), {'__getitem__': lambda s, i: 'lead@example.com'})()
            # SELECT sequence info (for campaign_like)
            elif 'crm_drip_sequences' in sql_str and 'organization_id' in sql_str:
                res.fetchone.return_value = (1, 10, "Test Sequence")
            # SELECT next step (step_index = next_step_index)
            elif 'step_index = :idx' in sql_str:
                res.fetchone.return_value = _make_row({
                    "delay_days": 1, "delay_hours": 0
                })
            # UPDATE enrollment
            elif 'update crm_drip_enrollments' in sql_str:
                res.fetchone.return_value = None
            else:
                res.fetchone.return_value = None
                res.fetchall.return_value = []
                res.scalar.return_value = 0
            return res

        db.execute.side_effect = _exec
        db.commit = MagicMock()
        return db

    def test_tick_advances_active_enrollment_when_due(self):
        db = self._build_db()
        # Patch delivery_sender on the drip_service module directly (handles real-import case)
        mock_enqueue = MagicMock(return_value={"status": "sent"})
        import GEPPPlatform.services.admin.crm.drip_service as _ds
        orig = getattr(_ds.delivery_sender, 'enqueue_delivery', None)
        _ds.delivery_sender.enqueue_delivery = mock_enqueue
        try:
            summary = drip_service.tick_enrollments(db, batch_size=10)
            self.assertGreaterEqual(summary["processed"], 1)
            mock_enqueue.assert_called()
        finally:
            if orig is not None:
                _ds.delivery_sender.enqueue_delivery = orig

    def test_tick_skips_when_skip_filter_matches(self):
        """When skip_filter matches the lead, step is skipped (no delivery) but enrollment advances."""
        _delivery_sender_stub.enqueue_delivery.reset_mock()
        _prop_filter_stub.matches.return_value = True

        db = self._build_db(skip_filter_matches=True)

        # We need the step to have a skip_filter set
        call_n = [0]
        orig_side = db.execute.side_effect

        def _patched(sql_or_text, params=None):
            res = orig_side(sql_or_text, params)
            sql_str = str(getattr(sql_or_text, 'text', sql_or_text) or '').lower()
            if 'step_index = :idx' in sql_str and call_n[0] < 3:
                res.fetchone.return_value = _make_row({
                    "id": 1, "step_index": 0, "template_id": 7,
                    "delay_days": 0, "delay_hours": 0,
                    "skip_filter": {"field": "status", "op": "eq", "value": "new"}
                })
            call_n[0] += 1
            return res

        db.execute.side_effect = _patched
        summary = drip_service.tick_enrollments(db, batch_size=10)
        self.assertGreaterEqual(summary["processed"], 1)
        # enqueue_delivery should NOT have been called
        _delivery_sender_stub.enqueue_delivery.assert_not_called()

        # Reset for other tests
        _prop_filter_stub.matches.return_value = False


class TestTickCompleted(unittest.TestCase):
    """tick_enrollments marks completed when there is no next step."""

    def test_tick_marks_completed_on_last_step(self):
        """When current_step is the last step, enrollment status → 'completed'."""
        db = MagicMock()
        _prop_filter_stub.matches.return_value = False
        _delivery_sender_stub.enqueue_delivery.reset_mock()
        _delivery_sender_stub.enqueue_delivery.return_value = {"status": "sent"}

        call_n = [0]

        def _exec(sql_or_text, params=None):
            res = MagicMock()
            call_n[0] += 1
            sql_str = str(getattr(sql_or_text, 'text', sql_or_text) or '').lower()

            if 'for update skip locked' in sql_str:
                res.fetchall.return_value = [(200, 2, 55, None, 0)]
            elif 'step_index = :idx' in sql_str:
                idx_val = (params or {}).get('idx', -1)
                if idx_val == 0:
                    # step 0 exists
                    res.fetchone.return_value = _make_row({
                        "id": 1, "step_index": 0, "template_id": 5,
                        "delay_days": 0, "delay_hours": 0, "skip_filter": None
                    })
                else:
                    # no next step — None triggers completion
                    res.fetchone.return_value = None
            elif 'crm_leads' in sql_str and 'email' in sql_str:
                res.fetchone.return_value = type('R', (), {'__getitem__': lambda s, i: 'last@example.com'})()
            elif 'crm_drip_sequences' in sql_str and 'organization_id' in sql_str:
                res.fetchone.return_value = (2, 10, "Last-Step Seq")
            elif 'update crm_drip_enrollments' in sql_str:
                res.fetchone.return_value = None
            else:
                res.fetchone.return_value = None
                res.fetchall.return_value = []
                res.scalar.return_value = 0
            return res

        db.execute.side_effect = _exec
        db.commit = MagicMock()

        summary = drip_service.tick_enrollments(db, batch_size=10)
        self.assertEqual(summary["completed"], 1)

        # The UPDATE should set status='completed'
        update_calls = [
            str(c.args[0].text if hasattr(c.args[0], 'text') else c.args[0]).lower()
            for c in db.execute.call_args_list
        ]
        completed_updates = [s for s in update_calls if 'completed' in s]
        self.assertGreater(len(completed_updates), 0)


class TestTickErrored(unittest.TestCase):
    """tick_enrollments marks errored when an unexpected exception occurs."""

    def test_tick_marks_errored_on_exception(self):
        db = MagicMock()
        _prop_filter_stub.matches.return_value = False

        call_n = [0]

        def _exec(sql_or_text, params=None):
            res = MagicMock()
            call_n[0] += 1
            sql_str = str(getattr(sql_or_text, 'text', sql_or_text) or '').lower()

            if 'for update skip locked' in sql_str:
                res.fetchall.return_value = [(300, 3, 66, None, 0)]
            elif 'step_index = :idx' in sql_str and (params or {}).get('idx', -1) == 0:
                # Raise an exception mid-processing to trigger errored path
                raise RuntimeError("simulated DB failure")
            elif 'update crm_drip_enrollments' in sql_str:
                res.fetchone.return_value = None
            else:
                res.fetchone.return_value = None
                res.fetchall.return_value = []
            return res

        db.execute.side_effect = _exec
        db.commit = MagicMock()
        db.rollback = MagicMock()

        summary = drip_service.tick_enrollments(db, batch_size=10)
        self.assertGreaterEqual(summary["errored"], 1)


class TestEnrollIdempotency(unittest.TestCase):
    """enroll() returns existing active enrollment without creating a duplicate."""

    def test_enroll_is_idempotent_per_lead(self):
        db = MagicMock()

        call_n = [0]

        def _exec(sql_or_text, params=None):
            res = MagicMock()
            call_n[0] += 1
            sql_str = str(getattr(sql_or_text, 'text', sql_or_text) or '').lower()

            # Sequence exists and is active
            if 'select id, status from crm_drip_sequences' in sql_str:
                res.fetchone.return_value = (10, 'active')
            # Idempotency check — existing active enrollment found
            elif 'lead_id = :lead_id and status' in sql_str:
                res.fetchone.return_value = (999,)  # existing enrollment id
            # _get_enrollment
            elif 'from crm_drip_enrollments where id' in sql_str:
                res.fetchone.return_value = _make_row({
                    "id": 999, "sequence_id": 10, "lead_id": 42,
                    "user_location_id": None, "current_step": 0,
                    "next_step_at": datetime.now(timezone.utc),
                    "status": "active",
                    "enrolled_at": datetime.now(timezone.utc),
                    "completed_at": None,
                })
            else:
                res.fetchone.return_value = None
                res.fetchall.return_value = []
            return res

        db.execute.side_effect = _exec
        db.commit = MagicMock()

        result = drip_service.enroll(db, sequence_id=10, lead_id=42)
        self.assertEqual(result["id"], 999)
        self.assertEqual(result["status"], "active")

        # No INSERT should have been made (idempotent)
        insert_calls = [
            c for c in db.execute.call_args_list
            if 'insert into crm_drip_enrollments' in
               str(getattr(c.args[0], 'text', c.args[0]) or '').lower()
        ]
        self.assertEqual(len(insert_calls), 0)


class TestAutoEnrollStatusChanged(unittest.TestCase):
    """_auto_enroll_on_event for lead_status_changed only enrolls when targetStatus matches."""

    def test_auto_enroll_lead_status_changed_matches_target_status(self):
        db = MagicMock()

        # Two sequences: one matching targetStatus='qualified', one not
        seq_rows = [
            (10, {"targetStatus": "qualified"}),   # should enroll
            (11, {"targetStatus": "negotiating"}),  # should NOT enroll
        ]

        enrolled_seqs = []

        call_n = [0]

        def _exec(sql_or_text, params=None):
            res = MagicMock()
            call_n[0] += 1
            sql_str = str(getattr(sql_or_text, 'text', sql_or_text) or '').lower()

            if 'select id, trigger_config from crm_drip_sequences' in sql_str:
                res.fetchall.return_value = [(sid, cfg) for sid, cfg in seq_rows]
            elif 'select id, status from crm_drip_sequences' in sql_str:
                # For the enroll() call's sequence validation
                sid = (params or {}).get('id', 10)
                enrolled_seqs.append(sid)
                res.fetchone.return_value = (sid, 'active')
            elif 'lead_id = :lead_id and status' in sql_str:
                # No existing enrollment
                res.fetchone.return_value = None
            elif 'select delay_days, delay_hours from crm_drip_steps' in sql_str:
                res.fetchone.return_value = None  # no steps, next_step_at = now
            elif 'insert into crm_drip_enrollments' in sql_str:
                res.fetchone.return_value = (500,)
            elif 'from crm_drip_enrollments where id' in sql_str:
                res.fetchone.return_value = _make_row({
                    "id": 500, "sequence_id": 10, "lead_id": 77,
                    "user_location_id": None, "current_step": 0,
                    "next_step_at": datetime.now(timezone.utc),
                    "status": "active",
                    "enrolled_at": datetime.now(timezone.utc),
                    "completed_at": None,
                })
            else:
                res.fetchone.return_value = None
                res.fetchall.return_value = []
            return res

        db.execute.side_effect = _exec
        db.commit = MagicMock()

        lead = {
            "id": 77,
            "organization_id": 5,
            "status": "qualified",  # matches sequence 10 but not 11
        }

        drip_service._auto_enroll_on_event(
            db, event='lead_status_changed', lead=lead, org_id=5
        )

        # Only sequence 10 should have been enrolled (targetStatus='qualified' matches)
        insert_calls = [
            c for c in db.execute.call_args_list
            if 'insert into crm_drip_enrollments' in
               str(getattr(c.args[0], 'text', c.args[0]) or '').lower()
        ]
        self.assertEqual(len(insert_calls), 1, "Should enroll exactly once (matching seq only)")

    def test_auto_enroll_does_not_enroll_when_status_mismatches(self):
        """No enrollment when lead status does not match any sequence's targetStatus."""
        db = MagicMock()

        def _exec(sql_or_text, params=None):
            res = MagicMock()
            sql_str = str(getattr(sql_or_text, 'text', sql_or_text) or '').lower()
            if 'select id, trigger_config from crm_drip_sequences' in sql_str:
                # Only one sequence expecting 'customer'
                res.fetchall.return_value = [(20, {"targetStatus": "customer"})]
            else:
                res.fetchone.return_value = None
                res.fetchall.return_value = []
            return res

        db.execute.side_effect = _exec
        db.commit = MagicMock()

        lead = {"id": 88, "organization_id": 5, "status": "new"}  # doesn't match 'customer'

        drip_service._auto_enroll_on_event(
            db, event='lead_status_changed', lead=lead, org_id=5
        )

        insert_calls = [
            c for c in db.execute.call_args_list
            if 'insert into crm_drip_enrollments' in
               str(getattr(c.args[0], 'text', c.args[0]) or '').lower()
        ]
        self.assertEqual(len(insert_calls), 0)


if __name__ == '__main__':
    unittest.main()
