"""
Test session bootstrap.

Two responsibilities:

1. **Pre-import real CRM submodules** so they are cached in ``sys.modules`` *before*
   ``test_mailchimp_webhook.py`` / ``test_delivery_sender.py`` (which both stub the
   ``GEPPPlatform.services.admin.crm`` package object via ``sys.modules`` mutation
   at import time).  Without this, after pytest collects those modules the stubbed
   ``crm`` package replaces the real one, and any later test that does
   ``from GEPPPlatform.services.admin.crm.X import …`` raises
   ``ModuleNotFoundError: 'GEPPPlatform.services.admin.crm' is not a package``.

   By pre-importing, the children are already keyed in ``sys.modules`` under their
   full dotted path — Python returns them directly without walking the parent's
   ``__path__``.

2. **Snapshot sys.modules per test** and restore afterwards, so tests that stub
   parent packages (``GEPPPlatform``, ``GEPPPlatform.models``, …) with
   ``MagicMock`` objects don't permanently shadow the real packages for tests that
   run after them.
"""

import importlib
import sys

import pytest


# ──────────────────────────────────────────────────────────────────────────────
# 1. Pre-import real GEPPPlatform.services.admin.crm.* and models so stubs added
#    later don't break imports.
# ──────────────────────────────────────────────────────────────────────────────

_PRE_IMPORTS = (
    # Real CRM service modules
    "GEPPPlatform.services.admin.crm.segment_evaluator",
    "GEPPPlatform.services.admin.crm.profile_refresher",
    "GEPPPlatform.services.admin.crm.email_renderer",
    "GEPPPlatform.services.admin.crm.crm_service",
    "GEPPPlatform.services.admin.crm.crm_handlers",
    "GEPPPlatform.services.admin.crm.delivery_sender",
    "GEPPPlatform.services.admin.crm.cooldown",
    "GEPPPlatform.services.admin.crm.property_filter",
    "GEPPPlatform.services.admin.crm.ai_rate_limit",
    "GEPPPlatform.services.admin.crm.unsubscribe_token",
    "GEPPPlatform.services.admin.crm.campaign_impact",
    "GEPPPlatform.services.admin.crm.crm_health",
    "GEPPPlatform.services.admin.crm.logger",
    "GEPPPlatform.services.admin.crm.inbox_service",
    "GEPPPlatform.services.admin.crm.inbox_handlers",
    # Canonical exception module. The GEPPPlatform.exceptions shim re-exports
    # from here, so if this copy is swapped mid-run the shim's snapshot ends up
    # holding classes from a stale copy and `pytest.raises(APIException)` stops
    # matching what production code actually raises.
    "GEPPPlatform.libs.exceptions",
    # Scale daily-report modules: they raise APIException / UnauthorizedException
    # from module-level imports and are asserted on by test_scale_report_*.py
    # and test_daily_summary_route.py.
    "GEPPPlatform.services.cores.scale_reports.bkk_time",
    "GEPPPlatform.services.cores.scale_reports.scale_report_token",
    "GEPPPlatform.services.cores.scale_reports.scale_report_service",
    # Models referenced by stubbing tests
    "GEPPPlatform.models.crm.events",
    "GEPPPlatform.models.crm.campaigns",
    "GEPPPlatform.models.crm.profiles",
    "GEPPPlatform.models.crm.segments",
    "GEPPPlatform.models.crm.templates",
    "GEPPPlatform.models.crm.lists",
    "GEPPPlatform.models.crm.conversations",
)

for _name in _PRE_IMPORTS:
    try:
        importlib.import_module(_name)
    except Exception:  # pragma: no cover — best-effort cache priming
        pass


# Snapshot the *real* references for these critical packages.  Tests are free to
# mutate sys.modules; the autouse fixture below restores these after every test.
_SNAPSHOT = {}
for _name in (
    "GEPPPlatform",
    "GEPPPlatform.services",
    "GEPPPlatform.services.admin",
    "GEPPPlatform.services.admin.crm",
    "GEPPPlatform.models",
    "GEPPPlatform.models.crm",
    "GEPPPlatform.exceptions",
    # Some suites (e.g. crm_features/test_public_lead_capture) stub sqlalchemy with
    # MagicMocks in sys.modules at import time and never restore it. Snapshot the real
    # modules so the per-test/per-module restore hooks below put them back — otherwise
    # later suites that need a real DB session (e.g. the reward walk-in/merge tests)
    # bind to the mock.
    "sqlalchemy",
    "sqlalchemy.orm",
) + _PRE_IMPORTS:
    if _name in sys.modules:
        _SNAPSHOT[_name] = sys.modules[_name]


# ──────────────────────────────────────────────────────────────────────────────
# 2. Per-test sys.modules restoration.
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _restore_sys_modules_after_test():
    """
    After every test, restore the snapshotted real packages back into sys.modules.

    Tests that intentionally swap in MagicMock stubs (test_delivery_sender,
    test_mailchimp_webhook) still see their stubs *during* the test — this only
    runs after the test function returns.
    """
    yield
    for _name, _mod in _SNAPSHOT.items():
        sys.modules[_name] = _mod


_REAL_EXC_NAMES = (
    "BadRequestException",
    "NotFoundException",
    "UnauthorizedException",
    "APIException",
)


@pytest.fixture
def real_api_exceptions(request, monkeypatch):
    """Pin the genuine API exception classes for the duration of one test.

    Opt-in, not autouse: it repairs a specific pollution rather than changing
    behaviour for suites that deliberately run against stubs.

    Why it is needed
    ────────────────
    ``tests/crm_features/test_deliveries_csv.py`` (and
    ``test_list_deliveries_user_filter.py``) do this at *import* time::

        _exc = sys.modules["GEPPPlatform.exceptions"]
        _exc.APIException = _StubAPIException      # plain Exception subclass

    That mutates the real shim module **in place**, so ``_SNAPSHOT`` — which
    holds a reference to that same object — cannot undo it, and
    ``_rebind_exception_names_in_test_modules`` then reads the stub back out of
    it and propagates it further. Any module left bound to the stub blows up
    with ``TypeError: _StubAPIException() takes no keyword arguments`` as soon
    as production code does ``APIException(msg, status_code=…, error_code=…)``.

    ``GEPPPlatform.libs.exceptions`` is never touched by those tests, so it is
    used here as the source of truth. monkeypatch reverts everything afterwards.
    """
    from GEPPPlatform.libs import exceptions as real

    names = (
        'APIException', 'UnauthorizedException', 'ValidationException',
        'NotFoundException', 'BadRequestException', 'ForbiddenException',
        'ConflictException', 'InternalServerException',
    )
    targets = [request.module]
    for _name in (
        'GEPPPlatform.exceptions',
        'GEPPPlatform.services.cores.iot_devices.iot_devices_handlers',
        'GEPPPlatform.services.cores.scale_reports.scale_report_token',
        'GEPPPlatform.services.cores.scale_reports.scale_report_service',
    ):
        _mod = sys.modules.get(_name)
        if _mod is not None:
            targets.append(_mod)

    for _mod in targets:
        for _attr in names:
            if hasattr(real, _attr) and hasattr(_mod, _attr):
                monkeypatch.setattr(_mod, _attr, getattr(real, _attr), raising=False)

    return real


def _restore_snapshot():
    """Put the real GEPPPlatform.* package modules back in sys.modules."""
    for _name, _mod in _SNAPSHOT.items():
        sys.modules[_name] = _mod


def _rebind_exception_names_in_test_modules():
    """
    Walk sys.modules; for every test module *and* every CRM/exceptions-importing
    GEPPPlatform module, force re-bind ``BadRequestException`` (and friends) to
    the canonical real exception class.

    Why this is necessary
    ─────────────────────
    Polluting test files use ``importlib.util`` to load isolated copies of
    GEPPPlatform packages and stub ``GEPPPlatform.exceptions`` with a
    ``MagicMock``.  When those isolated copies execute their module-level
    ``from ....exceptions import BadRequestException``, they bind the wrong
    object.  Even after we restore ``sys.modules['GEPPPlatform.exceptions']``,
    the bound name inside the production module's namespace is stale — and
    when production code raises ``BadRequestException``, it raises the *stale*
    class.  ``self.assertRaises(BadRequestException)`` in the *test* module then
    sees a different class and fails with TypeError or simply misses the raise.

    We solve both ends: rebind in test modules AND in ``GEPPPlatform.*`` modules.
    """
    real_exc = _SNAPSHOT.get("GEPPPlatform.exceptions")
    if real_exc is None:
        return
    # Build the canonical real exception classes we want to coerce everything to.
    real_classes = {n: getattr(real_exc, n, None) for n in _REAL_EXC_NAMES}
    for _mod_name, _mod in list(sys.modules.items()):
        if _mod is None:
            continue
        # Only touch test modules AND production modules under
        # GEPPPlatform.services.admin.crm.* (handlers + service code that raise
        # the exceptions tests assert on).
        if (
            "test_" not in _mod_name
            and not _mod_name.startswith("GEPPPlatform.services.admin.crm")
            and _mod_name != "GEPPPlatform.exceptions"
        ):
            continue
        # Opt-out marker: if a test (or test-loaded production copy) has set
        # `_OWNS_EXCEPTION_BINDING = True`, we must not rebind — it has its own
        # exception-class scheme deliberately set up (see crm_features/test_lead_service.py).
        # We also skip rebinding into the test's loaded copy of lead_service since the
        # test rebinds it manually at module load.
        if getattr(_mod, "_OWNS_EXCEPTION_BINDING", False):
            continue
        for _attr, real_attr in real_classes.items():
            if real_attr is None:
                continue
            current = getattr(_mod, _attr, None)
            if current is None or current is real_attr:
                continue
            try:
                setattr(_mod, _attr, real_attr)
            except (AttributeError, TypeError):
                pass


def pytest_collectstart(collector):
    _restore_snapshot()


def pytest_pycollect_makemodule(module_path, parent):
    _restore_snapshot()
    return None


def pytest_runtest_setup(item):
    """Right before each test, restore sys.modules AND rebind exception classes."""
    _restore_snapshot()
    _rebind_exception_names_in_test_modules()


def pytest_collection_finish(session):
    """
    After all test modules have been imported (and test_delivery_sender / test_mailchimp_webhook
    have polluted sys.modules with their stubs), restore the real packages and force-reload
    any test modules whose ``BadRequestException`` / ``NotFoundException`` etc. now point to
    a stale MagicMock attribute.

    This is what actually fixes the test_segment_evaluator failures: the binding inside that
    module's namespace is patched in-place to point back to the real exception classes.
    """
    _restore_snapshot()
    _rebind_exception_names_in_test_modules()
