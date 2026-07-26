"""Route-level guards for POST /api/iot-devices/daily-summary.

The station's daily intake by material is commercial information, so the
interesting assertions here are the refusals: no user token, wrong location,
bad input. Follows the fake-session style of test_iot_records_handler.py so no
database is required.
"""

import pytest

from GEPPPlatform.libs.exceptions import APIException
from GEPPPlatform.services.cores.iot_devices import iot_devices_handlers as handlers


@pytest.fixture(autouse=True)
def _pin_real_exceptions(real_api_exceptions):
    """Immunise this module from the shim mutation done by
    tests/crm_features/test_deliveries_csv.py — see the fixture's docstring."""


def _event():
    return {"rawPath": "/api/iot-devices/daily-summary"}


class _FakeQuery:
    """Stands in for the device organisation lookup at the top of the handler."""

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return (10,)


class _FakeDb:
    def query(self, *args, **kwargs):
        return _FakeQuery()


def _call(monkeypatch=None, *, data=None, current_user=None, method="POST",
          members=None, summary=None):
    """Invoke the route with the collaborators stubbed out."""
    if monkeypatch is not None:
        if members is not None:
            monkeypatch.setattr(handlers, "member_origin_ids",
                                lambda *a, **k: set(members))
        if summary is not None:
            monkeypatch.setattr(handlers, "get_daily_summary",
                                lambda *a, **k: dict(summary))
            monkeypatch.setattr(handlers, "make_report_token",
                                lambda *a, **k: ("tok", __import__("datetime").datetime(2026, 7, 28, 9, 0)))
            monkeypatch.setattr(handlers, "build_report_url",
                                lambda t: "https://geppdata.com/scale-report/" + t)

    return handlers.handle_iot_devices_routes(
        _event(),
        data=data if data is not None else {"origin_id": 1},
        db_session=_FakeDb(),
        method=method,
        current_device={"device_id": 1},
        current_user=current_user if current_user is not None
        else {"user_id": 5, "organization_id": 10},
    )


# ── authentication ───────────────────────────────────────────────────────────

def test_requires_a_user_token():
    """The whole point of the second review pass: an idle tablet with only a
    device token must not surrender the day's figures."""
    with pytest.raises(APIException) as exc:
        _call(current_user={})
    assert exc.value.status_code == 401
    assert exc.value.error_code == "UNAUTHORIZED"


def test_requires_the_user_to_have_an_organization():
    with pytest.raises(APIException) as exc:
        _call(current_user={"user_id": 5})
    assert exc.value.status_code == 400


def test_rejects_a_location_the_user_is_not_a_member_of(monkeypatch):
    """A borrowed tablet must not be able to read another site's intake,
    even inside the same organisation."""
    with pytest.raises(APIException) as exc:
        _call(monkeypatch, data={"origin_id": 999}, members={1, 2, 3})
    assert exc.value.status_code == 401


# ── input validation ─────────────────────────────────────────────────────────

def test_rejects_non_post():
    with pytest.raises(APIException) as exc:
        _call(method="GET")
    assert exc.value.status_code == 405


@pytest.mark.parametrize("body", [{}, {"origin_id": None}, {"origin_id": "abc"}])
def test_rejects_missing_or_unparseable_origin_id(body):
    with pytest.raises(APIException) as exc:
        _call(data=body)
    assert exc.value.status_code == 400


@pytest.mark.parametrize("bad_date", ["26/07/2026", "today", "2026-13-01"])
def test_rejects_malformed_date(monkeypatch, bad_date):
    """Must refuse rather than quietly fall back to today — a wrong date is
    worse than an error because the number still looks plausible."""
    with pytest.raises(APIException) as exc:
        _call(monkeypatch, data={"origin_id": 1, "date": bad_date}, members={1})
    assert exc.value.status_code == 400


# ── success path ─────────────────────────────────────────────────────────────

_SUMMARY = {
    "date": "2026-07-26",
    "location": {"origin_id": 1, "display_name": "สาขาบางนา"},
    "totals": {"weight_kg": 12.5, "entries": 2},
    "materials": [],
}


def test_returns_summary_with_a_report_url(monkeypatch):
    result = _call(monkeypatch, data={"origin_id": 1}, members={1}, summary=_SUMMARY)
    assert result["success"] is True
    assert result["data"]["totals"]["weight_kg"] == 12.5
    assert result["data"]["report_url"].endswith("/scale-report/tok")
    assert result["data"]["report_expires_at"] == "2026-07-28T09:00:00"


def test_report_url_points_at_the_web_host_not_the_api(monkeypatch):
    result = _call(monkeypatch, data={"origin_id": 1}, members={1}, summary=_SUMMARY)
    assert "/scale-report/" in result["data"]["report_url"]
    assert "api." not in result["data"]["report_url"]


def test_omitted_date_is_accepted_and_means_today(monkeypatch):
    result = _call(monkeypatch, data={"origin_id": 1}, members={1}, summary=_SUMMARY)
    assert result["success"] is True


def test_tablet_response_keeps_the_material_breakdown(monkeypatch):
    """Counterpart to test_scale_report_public_payload: staff *do* get the
    detail. Only the public QR route is trimmed."""
    result = _call(monkeypatch, data={"origin_id": 1}, members={1}, summary=_SUMMARY)
    assert "materials" in result["data"]


def test_preserves_status_code_from_the_service(monkeypatch):
    """Mirrors test_iot_records_handler's equivalent: a service-raised
    APIException must not be flattened into a 500."""
    def boom(*args, **kwargs):
        raise APIException("location gone", status_code=404, error_code="NOT_FOUND")

    monkeypatch.setattr(handlers, "member_origin_ids", lambda *a, **k: {1})
    monkeypatch.setattr(handlers, "get_daily_summary", boom)

    with pytest.raises(APIException) as exc:
        _call(data={"origin_id": 1})
    assert exc.value.status_code == 404
