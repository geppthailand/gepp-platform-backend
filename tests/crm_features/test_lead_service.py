"""
Unit tests for lead_service.py (Sprint 9 Phase 2 — Lead Management).

Coverage:
  - create_lead idempotency (same email twice returns same row)
  - change_status writes activity row + emits crm_event
  - convert_lead sets both sides of the FK pair, is idempotent
  - bulk_import_csv handles missing email rows, duplicate emails, malformed CSV
  - score_lead produces expected score for known fixtures

Run:
    python -m pytest tests/crm_features/test_lead_service.py -v
"""

import sys
import os
import importlib.util as _ilu
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

_OWNS_EXCEPTION_BINDING = True  # opt out of conftest exception rebinding (see tests/conftest.py)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ─── Stub helpers (same pattern as test_campaign_actions.py) ─────────────────

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


# ─── Exception stubs ──────────────────────────────────────────────────────────

class _APIExc(Exception):
    def __init__(self, msg="error", status_code=500, error_code="ERROR"):
        self.message = msg; self.status_code = status_code
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

# ─── Package stubs needed before loading lead_service ────────────────────────

for _pkg in [
    "GEPPPlatform",
    "GEPPPlatform.models",
    "GEPPPlatform.models.crm",
    "GEPPPlatform.models.crm.events",
    "GEPPPlatform.models.crm.leads",
    "GEPPPlatform.services",
    "GEPPPlatform.services.admin",
    "GEPPPlatform.services.admin.crm",
]:
    if _pkg not in sys.modules:
        _stub(_pkg)

# sqlalchemy.text pass-through
_sa = _stub("sqlalchemy")
_sa.text = lambda s: s

_orm = _stub("sqlalchemy.orm")

# crm_service stub — we want to verify emit_event is called.
_crm_svc_stub = _stub("GEPPPlatform.services.admin.crm.crm_service")

# ─── Load the real module ─────────────────────────────────────────────────────

_ls = _load(
    "GEPPPlatform/services/admin/crm/lead_service.py",
    "GEPPPlatform.services.admin.crm.lead_service",
)
# Wire real exception classes into the loaded module so raises work correctly.
_ls.BadRequestException = _BadReqExc
_ls.NotFoundException   = _NotFoundExc
_ls.crm_service         = _crm_svc_stub
# Tell conftest.py NOT to rebind these exception names — we own them.
_ls._OWNS_EXCEPTION_BINDING = True

lead_service = _ls

NotFoundException   = _NotFoundExc
BadRequestException = _BadReqExc


# ─── DB helpers ───────────────────────────────────────────────────────────────

def _row(**kwargs):
    """Fake DB row with _mapping and index support."""
    r = MagicMock()
    r._mapping = kwargs
    vals = list(kwargs.values())
    r.__getitem__ = lambda self, i: vals[i]
    for k, v in kwargs.items():
        setattr(r, k, v)
    return r


def _lead_row(
    lead_id=10, org_id=1, email='alice@example.com', status='new',
    converted_user_id=None, lead_score=0, tags=None,
    first_name='Alice', last_name='Smith', company='ACME',
    job_title=None, phone=None, country=None,
    last_activity_at=None, deleted_date=None,
):
    return _row(
        id=lead_id, organization_id=org_id, email=email,
        first_name=first_name, last_name=last_name, company=company,
        job_title=job_title, phone=phone, country=country, language=None,
        source='manual', source_metadata=None, status=status,
        status_changed_at=None, lead_score=lead_score, owner_user_id=None,
        tags=tags, notes=None, converted_user_id=converted_user_id, converted_at=None,
        last_activity_at=last_activity_at,
        created_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        deleted_date=deleted_date,
    )


# ─── Base class: re-pins stubs before every test ─────────────────────────────

class _LeadServiceBase(unittest.TestCase):
    """Re-pins exception stubs and the crm_service stub before every test.

    Needed because test_public_lead_capture.py (when collected in the same
    pytest session) overwrites sys.modules['GEPPPlatform.exceptions'] in its
    own setUp.  We counter that by re-pinning our stubs here.
    """
    def setUp(self):
        # Re-pin our exception stubs into GEPPPlatform.exceptions.
        _exc_mod.NotFoundException   = _NotFoundExc
        _exc_mod.BadRequestException = _BadReqExc
        _exc_mod.APIException        = _APIExc
        sys.modules['GEPPPlatform.exceptions'] = _exc_mod
        # Re-pin onto the loaded lead_service module.
        lead_service.BadRequestException = _BadReqExc
        lead_service.NotFoundException   = _NotFoundExc
        # Reset crm_service stub call history.
        _crm_svc_stub.reset_mock()


# ─── Tests: create_lead idempotency ──────────────────────────────────────────

class TestCreateLeadIdempotency(_LeadServiceBase):

    def test_new_email_inserts_and_returns(self):
        """First call creates row; returns lead dict with id."""
        row = _lead_row(lead_id=42)
        call_n = [0]

        def _exec(sql, params=None):
            call_n[0] += 1
            res = MagicMock()
            if call_n[0] == 1:      # idempotency SELECT → no existing
                res.fetchone.return_value = None
            elif call_n[0] == 2:    # INSERT lead RETURNING id
                res.fetchone.return_value = (42,)
            elif call_n[0] == 3:    # add_activity INSERT RETURNING id
                res.fetchone.return_value = (99,)
            elif call_n[0] == 4:    # add_activity UPDATE last_activity_at
                res.fetchone.return_value = None
            else:                   # get_lead SELECT (call 5+)
                res.fetchone.return_value = row
            return res

        db = MagicMock()
        db.execute.side_effect = _exec
        db.commit = MagicMock()

        result = lead_service.create_lead(db, org_id=1,
                                          data={'email': 'alice@example.com'})
        self.assertEqual(result.get('id'), 42)

    def test_same_email_twice_returns_existing(self):
        """Second call with same (org_id, email) returns existing row, no INSERT."""
        existing = _row(id=42)
        row      = _lead_row(lead_id=42)
        call_n   = [0]

        def _exec(sql, params=None):
            call_n[0] += 1
            res = MagicMock()
            if call_n[0] == 1:      # idempotency SELECT → found
                res.fetchone.return_value = existing
            elif call_n[0] == 2:    # deleted_date check → not deleted
                res.fetchone.return_value = _row(deleted_date=None)
            else:                   # get_lead SELECT
                res.fetchone.return_value = row
            return res

        db = MagicMock()
        db.execute.side_effect = _exec
        db.commit = MagicMock()

        result = lead_service.create_lead(db, org_id=1,
                                          data={'email': 'ALICE@EXAMPLE.COM'})
        self.assertEqual(result.get('id'), 42)
        # No INSERT attempted — call count must be ≤ 3.
        self.assertLessEqual(call_n[0], 3)

    def test_missing_email_raises(self):
        import sys as _sys
        print(f"\nDEBUG: BadRequestException id={id(BadRequestException)}")
        print(f"DEBUG: _BadReqExc id={id(_BadReqExc)}")
        print(f"DEBUG: lead_service.BadRequestException id={id(lead_service.BadRequestException)}")
        print(f"DEBUG: same? {BadRequestException is _BadReqExc}")
        print(f"DEBUG: ls.BadReq same as _BadReqExc? {lead_service.BadRequestException is _BadReqExc}")
        db = MagicMock()
        with self.assertRaises(BadRequestException):
            lead_service.create_lead(db, org_id=1, data={'email': ''})


# ─── Tests: change_status ────────────────────────────────────────────────────

class TestChangeStatus(_LeadServiceBase):

    def test_writes_activity_and_emits_event(self):
        row_new       = _lead_row(status='new')
        row_contacted = _lead_row(status='contacted')
        call_n = [0]

        def _exec(sql, params=None):
            call_n[0] += 1
            res = MagicMock()
            if call_n[0] == 1:      # get_lead SELECT
                res.fetchone.return_value = row_new
            elif call_n[0] == 2:    # UPDATE status
                res.fetchone.return_value = None
            elif call_n[0] == 3:    # add_activity INSERT
                res.fetchone.return_value = (55,)
            elif call_n[0] == 4:    # last_activity touch
                res.fetchone.return_value = None
            else:                   # final get_lead
                res.fetchone.return_value = row_contacted
            return res

        db = MagicMock()
        db.execute.side_effect = _exec
        db.commit = MagicMock()

        emit_mock = MagicMock()
        _crm_svc_stub.emit_event = emit_mock

        result = lead_service.change_status(db, lead_id=10, org_id=1,
                                            new_status='contacted', by_user_id=7)
        self.assertEqual(result.get('status'), 'contacted')
        # Activity INSERT must have happened (call_n >= 3).
        self.assertGreaterEqual(call_n[0], 3)
        # emit_event called once with lead_status_changed.
        emit_mock.assert_called_once()
        _, kw = emit_mock.call_args
        self.assertEqual(kw.get('event_type'), 'lead_status_changed')
        self.assertEqual(kw['properties']['from'], 'new')
        self.assertEqual(kw['properties']['to'], 'contacted')

    def test_invalid_status_raises(self):
        db = MagicMock()
        with self.assertRaises(BadRequestException):
            lead_service.change_status(db, lead_id=10, org_id=1,
                                       new_status='flying_saucer')

    def test_same_status_is_noop(self):
        row = _lead_row(status='qualified')
        db  = MagicMock()
        db.execute.return_value = MagicMock(fetchone=lambda: row)

        result = lead_service.change_status(db, lead_id=10, org_id=1,
                                            new_status='qualified')
        self.assertEqual(result.get('status'), 'qualified')


# ─── Tests: convert_lead ─────────────────────────────────────────────────────

class TestConvertLead(_LeadServiceBase):

    def test_sets_converted_user_id_and_back_fills_user_locations(self):
        row     = _lead_row(converted_user_id=None)
        row_cvt = _lead_row(converted_user_id=300)
        call_n  = [0]

        def _exec(sql, params=None):
            call_n[0] += 1
            res = MagicMock()
            if call_n[0] == 1:      # get_lead
                res.fetchone.return_value = row
            elif call_n[0] == 2:    # UPDATE crm_leads
                res.fetchone.return_value = None
            elif call_n[0] == 3:    # UPDATE user_locations
                res.fetchone.return_value = None
            elif call_n[0] == 4:    # add_activity INSERT
                res.fetchone.return_value = (66,)
            elif call_n[0] == 5:    # last_activity touch
                res.fetchone.return_value = None
            else:                   # final get_lead
                res.fetchone.return_value = row_cvt
            return res

        db = MagicMock()
        db.execute.side_effect = _exec
        db.commit = MagicMock()

        result = lead_service.convert_lead(db, lead_id=10, org_id=1,
                                           user_location_id=300)
        self.assertEqual(result.get('converted_user_id'), 300)
        # user_locations UPDATE must have been called.
        calls_str = ' '.join(str(c) for c in db.execute.call_args_list)
        self.assertIn('user_locations', calls_str)

    def test_idempotent_same_user_loc(self):
        """Calling convert_lead with same user_location_id twice is a no-op."""
        row = _lead_row(converted_user_id=300)
        db  = MagicMock()
        db.execute.return_value = MagicMock(fetchone=lambda: row)
        db.commit = MagicMock()

        result = lead_service.convert_lead(db, lead_id=10, org_id=1,
                                           user_location_id=300)
        self.assertEqual(result.get('converted_user_id'), 300)
        # Only one execute call (the get_lead SELECT).
        self.assertEqual(db.execute.call_count, 1)


# ─── Tests: bulk_import_csv ───────────────────────────────────────────────────

class TestBulkImportCsv(_LeadServiceBase):

    def _db_no_existing(self):
        """DB that returns 'no existing lead' for every dedup SELECT."""
        db = MagicMock()
        call_n = [0]

        def _exec(sql, params=None):
            call_n[0] += 1
            res = MagicMock()
            sql_s = str(sql)
            if 'SELECT id FROM crm_leads' in sql_s:
                res.fetchone.return_value = None
            elif 'INSERT INTO crm_leads' in sql_s:
                res.fetchone.return_value = (call_n[0] * 10,)
            else:
                res.fetchone.return_value = (call_n[0] * 100,)
            return res

        db.execute.side_effect = _exec
        db.commit = MagicMock()
        db.rollback = MagicMock()
        return db

    def test_basic_import_valid_rows(self):
        csv_text = ("email,first_name,last_name\n"
                    "alice@example.com,Alice,Smith\n"
                    "bob@example.com,Bob,Jones")
        result = lead_service.bulk_import_csv(self._db_no_existing(), org_id=1,
                                              csv_text=csv_text)
        self.assertEqual(result['imported'], 2)
        self.assertEqual(result['skipped'], 0)
        self.assertEqual(result['errors'], [])

    def test_no_email_column_raises(self):
        with self.assertRaises(BadRequestException) as ctx:
            lead_service.bulk_import_csv(MagicMock(), org_id=1,
                                         csv_text="name,company\nAlice,ACME")
        self.assertIn("email", str(ctx.exception).lower())

    def test_empty_email_rows_skipped_with_error(self):
        csv_text = "email,first_name\n,NoEmail\nbob@example.com,Bob"
        result = lead_service.bulk_import_csv(self._db_no_existing(), org_id=1,
                                              csv_text=csv_text)
        self.assertEqual(result['imported'], 1)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(len(result['errors']), 1)
        self.assertIn("missing email", result['errors'][0].lower())

    def test_duplicate_email_skipped_silently(self):
        csv_text = "email\nexisting@example.com\nnew@example.com"

        db = MagicMock()
        call_n = [0]

        def _exec(sql, params=None):
            call_n[0] += 1
            res = MagicMock()
            sql_s = str(sql)
            if 'SELECT id FROM crm_leads' in sql_s:
                email = (params or {}).get('email', '')
                res.fetchone.return_value = _row(id=99) if email == 'existing@example.com' \
                    else None
            elif 'INSERT INTO crm_leads' in sql_s:
                res.fetchone.return_value = (200,)
            else:
                res.fetchone.return_value = (300,)
            return res

        db.execute.side_effect = _exec
        db.commit = MagicMock()

        result = lead_service.bulk_import_csv(db, org_id=1, csv_text=csv_text)
        self.assertEqual(result['imported'], 1)
        self.assertEqual(result['skipped'], 1)
        self.assertEqual(result['errors'], [])

    def test_empty_csv_raises(self):
        with self.assertRaises(BadRequestException):
            lead_service.bulk_import_csv(MagicMock(), org_id=1, csv_text="")

    def test_header_only_csv_imports_zero(self):
        result = lead_service.bulk_import_csv(
            self._db_no_existing(), org_id=1, csv_text="email,first_name"
        )
        self.assertEqual(result['imported'], 0)
        self.assertEqual(result['errors'], [])


# ─── Tests: score_lead ───────────────────────────────────────────────────────

class TestScoreLead(_LeadServiceBase):

    def _db_for_score(self, status='new', tags=None, email_opens=0,
                      first_name=None, last_name=None, company=None):
        # score_lead unpacks: (id, org_id, status, lead_score, tags,
        #   first_name, last_name, company, job_title, phone, country,
        #   last_activity_at, created_date, deleted_date)  — 14 fields
        lead_tuple = (
            5, 1, status, 0, tags,
            first_name, last_name, company, None, None, None,
            None, datetime(2026, 1, 1, tzinfo=timezone.utc), None,
        )

        final_lead = _lead_row(lead_id=5, status=status, lead_score=0)

        db = MagicMock()
        call_n = [0]

        def _exec(sql, params=None):
            call_n[0] += 1
            res = MagicMock()
            if call_n[0] == 1:   # SELECT for score_lead → plain tuple for unpacking
                res.fetchone.return_value = lead_tuple
            elif call_n[0] == 2: # COUNT email_opened
                res.scalar.return_value = email_opens
            elif call_n[0] == 3: # UPDATE lead_score
                res.fetchone.return_value = None
            elif call_n[0] == 4: # add_activity INSERT
                res.fetchone.return_value = (77,)
            elif call_n[0] == 5: # add_activity UPDATE last_activity_at
                res.fetchone.return_value = None
            else:                # get_lead SELECT
                res.fetchone.return_value = final_lead
            return res

        db.execute.side_effect = _exec
        db.commit = MagicMock()
        return db, call_n

    def _get_score_param(self, db):
        for c in db.execute.call_args_list:
            args, _ = c
            if len(args) > 1 and isinstance(args[1], dict) and 'score' in args[1]:
                return args[1]['score']
        return None

    def test_new_no_data_score_zero(self):
        db, _ = self._db_for_score(status='new')
        lead_service.score_lead(db, lead_id=5)
        score = self._get_score_param(db)
        self.assertEqual(score, 0)

    def test_qualified_status_score_25(self):
        db, _ = self._db_for_score(status='qualified')
        lead_service.score_lead(db, lead_id=5)
        score = self._get_score_param(db)
        self.assertEqual(score, 25)

    def test_email_opens_add_3_each(self):
        db, _ = self._db_for_score(status='new', email_opens=3)
        lead_service.score_lead(db, lead_id=5)
        score = self._get_score_param(db)
        # 0 (status) + 9 (3*3 opens) = 9
        self.assertEqual(score, 9)

    def test_email_opens_capped_at_15(self):
        db, _ = self._db_for_score(status='new', email_opens=10)
        lead_service.score_lead(db, lead_id=5)
        score = self._get_score_param(db)
        # 0 + min(30, 15) = 15
        self.assertEqual(score, 15)

    def test_tags_capped_at_5(self):
        tags = ['a', 'b', 'c', 'd', 'e', 'f', 'g']
        db, _ = self._db_for_score(status='new', tags=tags)
        lead_service.score_lead(db, lead_id=5)
        score = self._get_score_param(db)
        # 0 (status) + min(7, 5) tags = 5
        self.assertEqual(score, 5)

    def test_lost_status_floored_at_zero(self):
        # STATUS_SCORE['lost'] = -10 → floored to 0
        db, _ = self._db_for_score(status='lost')
        lead_service.score_lead(db, lead_id=5)
        score = self._get_score_param(db)
        self.assertGreaterEqual(score, 0)

    def test_data_completeness_adds_to_score(self):
        # 3 filled fields × 2 = 6, new status = 0, total = 6
        db, _ = self._db_for_score(
            status='new', first_name='Alice', last_name='Smith', company='ACME'
        )
        lead_service.score_lead(db, lead_id=5)
        score = self._get_score_param(db)
        self.assertEqual(score, 6)


if __name__ == '__main__':
    unittest.main()
