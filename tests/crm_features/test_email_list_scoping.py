"""
Unit tests for per-org email-list scoping (Task 3 — Sprint 3 BE2).

Scenarios:
  1. Sponsor user from org A  → sees only org A's lists
  2. Super-admin              → sees all lists (both orgs)
  3. Sponsor with no org_id   → raises 403

Run:
    python -m pytest tests/crm/test_email_list_scoping.py -v
"""

import sys
import os
import importlib.util as _ilu
import unittest
from unittest.mock import MagicMock, patch, call

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# ---------------------------------------------------------------------------
# Minimal stubs so the module tree loads without a real DB or full package
# ---------------------------------------------------------------------------

def _stub(name):
    m = MagicMock()
    m.__spec__ = None
    return m


def _preload_stubs():
    """Pre-register stub modules to satisfy imports inside crm_handlers.py."""
    stub_names = [
        "GEPPPlatform",
        "GEPPPlatform.exceptions",
        "GEPPPlatform.models",
        "GEPPPlatform.models.crm",
    ]
    for name in stub_names:
        if name not in sys.modules:
            sys.modules[name] = _stub(name)

    # Wire real exception types so the scoping helper raises them correctly
    import importlib as _il
    exc_path = os.path.join(_ROOT, "GEPPPlatform", "exceptions.py")
    if os.path.exists(exc_path):
        spec = _ilu.spec_from_file_location("GEPPPlatform.exceptions", exc_path)
        exc_mod = _ilu.module_from_spec(spec)
        sys.modules["GEPPPlatform.exceptions"] = exc_mod
        spec.loader.exec_module(exc_mod)


_preload_stubs()


def _load_crm_handlers():
    """Load crm_handlers with its relative-import chain stubbed."""
    mod_name = "GEPPPlatform.services.admin.crm.crm_handlers"

    # Ensure parent packages exist
    for parent in [
        "GEPPPlatform.services",
        "GEPPPlatform.services.admin",
        "GEPPPlatform.services.admin.crm",
    ]:
        if parent not in sys.modules:
            sys.modules[parent] = _stub(parent)

    handlers_path = os.path.join(
        _ROOT,
        "GEPPPlatform", "services", "admin", "crm", "crm_handlers.py",
    )
    spec = _ilu.spec_from_file_location(mod_name, handlers_path)
    mod = _ilu.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(rows_count=None, rows=None):
    """Return a mock SQLAlchemy session whose execute() is pre-programmed."""
    db = MagicMock()
    # scalar() for COUNT, fetchall() for list rows
    count_result = MagicMock()
    count_result.scalar.return_value = rows_count if rows_count is not None else 0
    rows_result = MagicMock()
    rows_result.fetchall.return_value = rows or []
    db.execute.side_effect = [count_result, rows_result]
    return db


def _row(id_, org_id):
    """Fake SQLAlchemy Row for crm_email_lists."""
    from datetime import datetime, timezone
    return (
        id_,                    # id
        f"List {id_}",          # name
        "desc",                 # description
        org_id,                 # organization_id
        ["a@b.com"],            # emails
        datetime.now(timezone.utc),  # created_date
        datetime.now(timezone.utc),  # updated_date
    )


# ---------------------------------------------------------------------------
# Load handlers once at module level
# ---------------------------------------------------------------------------

_handlers = _load_crm_handlers()
list_crm_email_lists  = _handlers.list_crm_email_lists
get_crm_email_list    = _handlers.get_crm_email_list
create_crm_email_list = _handlers.create_crm_email_list
update_crm_email_list = _handlers.update_crm_email_list
delete_crm_email_list = _handlers.delete_crm_email_list

# Pull the real exception classes loaded from GEPPPlatform.exceptions
_exc_mod = sys.modules["GEPPPlatform.exceptions"]
APIException  = _exc_mod.APIException
NotFoundException = _exc_mod.NotFoundException


# ===========================================================================
# Test cases
# ===========================================================================

class TestEmailListScopingList(unittest.TestCase):
    """list_crm_email_lists — org scoping."""

    # ── scenario 1: org-scoped sponsor ──────────────────────────────────────

    def test_sponsor_sees_only_own_org(self):
        """Sponsor from org A: query must be restricted to org_id=10."""
        org_a_rows = [_row(1, 10), _row(2, 10)]
        db = _make_session(rows_count=2, rows=org_a_rows)

        current_user = {'organization_id': 10}
        result = list_crm_email_lists(db, {}, current_user=current_user)

        self.assertEqual(result['total'], 2)
        self.assertEqual(len(result['items']), 2)

        # Every returned item must belong to org 10
        for item in result['items']:
            self.assertEqual(item['organizationId'], 10)

        # The SQL must have been called with org_id=10 in params
        all_calls = db.execute.call_args_list
        # Second call carries the SELECT params (first is COUNT)
        select_params = all_calls[1].args[1] if len(all_calls) > 1 else {}
        self.assertIn('org_id', select_params)
        self.assertEqual(select_params['org_id'], 10)

    def test_sponsor_org_filter_overrides_query_param(self):
        """Even if sponsor passes ?organizationId=99, scope forces org_id=10."""
        org_a_rows = [_row(3, 10)]
        db = _make_session(rows_count=1, rows=org_a_rows)

        current_user = {'organization_id': 10}
        # Attacker tries to see org 99's lists via query param
        result = list_crm_email_lists(db, {'organizationId': '99'}, current_user=current_user)

        all_calls = db.execute.call_args_list
        select_params = all_calls[1].args[1] if len(all_calls) > 1 else {}
        # Scope must have won: org_id=10, not 99
        self.assertEqual(select_params.get('org_id'), 10)

    # ── scenario 2: super-admin ──────────────────────────────────────────────

    def test_super_admin_sees_all(self):
        """Super-admin: no org restriction; both orgs' rows returned."""
        all_rows = [_row(1, 10), _row(2, 20), _row(3, 30)]
        db = _make_session(rows_count=3, rows=all_rows)

        current_user = {'admin_role': 'super-admin'}
        result = list_crm_email_lists(db, {}, current_user=current_user)

        self.assertEqual(result['total'], 3)

        # No org_id param must appear in the SELECT call for a super-admin
        # with no organizationId filter passed via query params
        all_calls = db.execute.call_args_list
        select_params = all_calls[1].args[1] if len(all_calls) > 1 else {}
        self.assertNotIn('org_id', select_params)

    def test_gepp_admin_sees_all(self):
        """gepp-admin role: same full access as super-admin."""
        all_rows = [_row(5, 10), _row(6, 99)]
        db = _make_session(rows_count=2, rows=all_rows)

        current_user = {'admin_role': 'gepp-admin'}
        result = list_crm_email_lists(db, {}, current_user=current_user)

        self.assertEqual(result['total'], 2)

    def test_super_admin_can_filter_by_org_via_query_param(self):
        """Super-admin may still pass ?organizationId= to narrow results."""
        filtered_rows = [_row(7, 42)]
        db = _make_session(rows_count=1, rows=filtered_rows)

        current_user = {'admin_role': 'super-admin'}
        result = list_crm_email_lists(db, {'organizationId': '42'}, current_user=current_user)

        all_calls = db.execute.call_args_list
        select_params = all_calls[1].args[1] if len(all_calls) > 1 else {}
        self.assertEqual(select_params.get('org_id'), 42)

    # ── scenario 3: no org → 403 ────────────────────────────────────────────

    def test_no_org_raises_403(self):
        """User with no admin_role and no organization_id must get a 403."""
        db = MagicMock()
        current_user = {}  # no role, no org

        with self.assertRaises(APIException) as ctx:
            list_crm_email_lists(db, {}, current_user=current_user)

        self.assertEqual(ctx.exception.status_code, 403)
        db.execute.assert_not_called()

    def test_none_current_user_raises_403(self):
        """current_user=None (unauthenticated path) must also get a 403."""
        db = MagicMock()

        with self.assertRaises(APIException) as ctx:
            list_crm_email_lists(db, {}, current_user=None)

        self.assertEqual(ctx.exception.status_code, 403)


class TestEmailListScopingGet(unittest.TestCase):
    """get_crm_email_list — org scoping."""

    def test_sponsor_cannot_read_other_org(self):
        """get_crm_email_list for a list belonging to org 99 → NotFoundException for org 10 user."""
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = _row(1, 99)  # org 99

        current_user = {'organization_id': 10}
        with self.assertRaises(NotFoundException):
            get_crm_email_list(db, 1, current_user=current_user)

    def test_sponsor_can_read_own_org(self):
        """get_crm_email_list for own org list → succeeds."""
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = _row(1, 10)

        current_user = {'organization_id': 10}
        result = get_crm_email_list(db, 1, current_user=current_user)
        self.assertEqual(result['organizationId'], 10)

    def test_super_admin_can_read_any_org(self):
        """Super-admin reads any list regardless of org."""
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = _row(5, 99)

        current_user = {'admin_role': 'super-admin'}
        result = get_crm_email_list(db, 5, current_user=current_user)
        self.assertEqual(result['id'], 5)

    def test_no_org_raises_403_on_get(self):
        """No role, no org → 403 before any DB read."""
        db = MagicMock()
        with self.assertRaises(APIException) as ctx:
            get_crm_email_list(db, 1, current_user={})
        self.assertEqual(ctx.exception.status_code, 403)
        db.execute.assert_not_called()


class TestEmailListScopingCreate(unittest.TestCase):
    """create_crm_email_list — org scoping."""

    def test_sponsor_cannot_create_for_other_org(self):
        """Sponsor from org 10 cannot create a list with organizationId=99."""
        db = MagicMock()
        current_user = {'organization_id': 10}
        data = {'name': 'Attempt', 'organizationId': 99, 'emails': []}

        with self.assertRaises(APIException) as ctx:
            create_crm_email_list(db, data, current_user=current_user)

        self.assertEqual(ctx.exception.status_code, 403)
        db.add.assert_not_called()

    def test_sponsor_can_create_for_own_org(self):
        """Sponsor creates list for own org → DB row created."""
        from unittest.mock import patch as _patch

        # Patch CrmEmailList model
        fake_list = MagicMock()
        fake_list.id = 55

        db = MagicMock()
        # get_crm_email_list will be called internally at the end; stub it
        db.execute.return_value.fetchone.return_value = _row(55, 10)

        current_user = {'organization_id': 10}
        data = {'name': 'My List', 'organizationId': 10, 'emails': ['x@y.com']}

        with _patch.object(_handlers, 'get_crm_email_list') as mock_get, \
             _patch("GEPPPlatform.models.crm.CrmEmailList", return_value=fake_list):
            mock_get.return_value = {'id': 55, 'organizationId': 10, 'name': 'My List',
                                     'emails': ['x@y.com'], 'emailCount': 1,
                                     'description': None, 'createdDate': None, 'updatedDate': None}
            result = create_crm_email_list(db, data, current_user=current_user)

        db.add.assert_called_once()
        self.assertEqual(result['id'], 55)

    def test_no_org_raises_403_on_create(self):
        """No scope → 403 before touching DB."""
        db = MagicMock()
        with self.assertRaises(APIException) as ctx:
            create_crm_email_list(db, {'name': 'X', 'organizationId': 5}, current_user={})
        self.assertEqual(ctx.exception.status_code, 403)
        db.add.assert_not_called()


class TestEmailListScopingUpdateDelete(unittest.TestCase):
    """update_crm_email_list / delete_crm_email_list — org scoping."""

    def test_sponsor_cannot_update_other_org_list(self):
        """Sponsor from org 10 cannot update a list belonging to org 99."""
        db = MagicMock()
        # SELECT returns a row from org 99
        db.execute.return_value.fetchone.return_value = (1, 99)  # id, organization_id
        current_user = {'organization_id': 10}

        with self.assertRaises(NotFoundException):
            update_crm_email_list(db, 1, {'name': 'Hack'}, current_user=current_user)

    def test_sponsor_cannot_delete_other_org_list(self):
        """Sponsor from org 10 cannot delete a list belonging to org 99."""
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = (1, 99)
        current_user = {'organization_id': 10}

        with self.assertRaises(NotFoundException):
            delete_crm_email_list(db, 1, current_user=current_user)

    def test_super_admin_can_delete_any(self):
        """Super-admin deletes list from any org."""
        db = MagicMock()
        fetch_mock = MagicMock()
        fetch_mock.fetchone.return_value = (7, 99)
        db.execute.return_value = fetch_mock

        current_user = {'admin_role': 'super-admin'}
        result = delete_crm_email_list(db, 7, current_user=current_user)
        self.assertTrue(result['deleted'])


if __name__ == '__main__':
    unittest.main()
