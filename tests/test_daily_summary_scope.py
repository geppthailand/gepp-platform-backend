"""Tag/tenant-scoped daily summary: who qualifies, and that the QR token keeps it.

The point of the narrowing is that a tenant sees its own weights and nothing
else at a shared station, so the cases that matter are the exclusions: grants
attached outside the station's subtree, grants whose window misses the day,
and owners (who are handled by the route's existing rule, not here).
"""

from datetime import date, datetime, timezone

from GEPPPlatform.services.cores.scale_reports import summary_scope as S
from GEPPPlatform.services.cores.scale_reports.scale_report_token import (
    make_report_token,
    verify_report_token,
)

DAY = date(2026, 11, 2)


def _utc(y, m, d):
    return datetime(y, m, d, tzinfo=timezone.utc)


# ── grant_covers_day ────────────────────────────────────────────────────────

def test_open_ended_grant_covers_any_day():
    assert S.grant_covers_day({}, DAY)


def test_window_including_the_day():
    assert S.grant_covers_day({"start_date": _utc(2026, 11, 1), "end_date": _utc(2026, 11, 30)}, DAY)


def test_window_that_starts_or_ends_on_the_day_still_counts():
    assert S.grant_covers_day({"start_date": _utc(2026, 11, 2)}, DAY)
    assert S.grant_covers_day({"end_date": _utc(2026, 11, 2)}, DAY)


def test_window_outside_the_day():
    assert not S.grant_covers_day({"end_date": _utc(2026, 11, 1)}, DAY)
    assert not S.grant_covers_day({"start_date": _utc(2026, 11, 3)}, DAY)


# ── resolve_scoped_summary ──────────────────────────────────────────────────

def _patch(monkeypatch, scope, subtree=(100, 101)):
    class FakeUserService:
        def __init__(self, db):
            pass

        def resolve_access_scope(self, org_id, user_id):
            return scope

    monkeypatch.setattr(S, "UserService", FakeUserService)
    monkeypatch.setattr(S, "descendant_origin_ids", lambda db, org, origin: list(subtree))


def test_grant_attached_in_the_subtree_gives_a_narrowed_scope(monkeypatch):
    _patch(monkeypatch, {
        "is_owner": False, "assigned_ids": set(),
        "scoped_grants": [{"kind": "tenant", "id": 7, "name": "Andaz", "location_ids": {101}}],
    })
    out = S.resolve_scoped_summary(None, 5, 10, 100, DAY)
    assert out["grants"] == [{"kind": "tenant", "id": 7, "name": "Andaz"}]
    sql = str(out["clause"])
    assert "tenant_id" in sql and "origin_id" in sql


def test_grant_elsewhere_in_the_org_does_not_open_this_station(monkeypatch):
    _patch(monkeypatch, {
        "is_owner": False, "assigned_ids": set(),
        "scoped_grants": [{"kind": "tag", "id": 3, "name": "Zone 1", "location_ids": {555}}],
    })
    assert S.resolve_scoped_summary(None, 5, 10, 100, DAY) is None


def test_grant_whose_window_misses_the_day_does_not_count(monkeypatch):
    _patch(monkeypatch, {
        "is_owner": False, "assigned_ids": set(),
        "scoped_grants": [{"kind": "tenant", "id": 7, "name": "Old tenant",
                           "location_ids": {100}, "end_date": _utc(2026, 10, 1)}],
    })
    assert S.resolve_scoped_summary(None, 5, 10, 100, DAY) is None


def test_owner_is_left_to_the_route(monkeypatch):
    _patch(monkeypatch, {"is_owner": True})
    assert S.resolve_scoped_summary(None, 5, 10, 100, DAY) is None


# ── report token ────────────────────────────────────────────────────────────

def test_scoped_token_round_trips_the_user():
    token, _ = make_report_token(100, 10, DAY, scope_user_id=5)
    claims = verify_report_token(token)
    assert claims["scope_user_id"] == 5
    assert (claims["origin_id"], claims["org_id"], claims["day"]) == (100, 10, DAY)


def test_unscoped_token_is_unchanged_and_carries_no_user():
    token, _ = make_report_token(100, 10, DAY)
    assert verify_report_token(token)["scope_user_id"] is None
