"""GEPP Team SSO exchange: POST /api/admin/sso turns a 60-second ISO assertion into the v3 admin token."""
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import jwt
import pytest

SECRET = "test-gepp-team-sso-secret-" + "z" * 30


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("GEPP_TEAM_SSO_SECRET", SECRET)
    monkeypatch.setenv("JWT_SECRET_KEY", "v3-test-secret")
    monkeypatch.delenv("GEPP_TEAM_SSO_AUTO_PROVISION", raising=False)
    from GEPPPlatform.libs import gepp_team_sso
    gepp_team_sso._SEEN.clear()


def _assertion(aud="v3", email="nida@gepp.me", exp_in=60, secret=SECRET, **extra):
    now = int(time.time())
    claims = {"iss": "gepp-team", "typ": "sso", "aud": aud, "sub": "01ISOUID", "email": email, "name": "Nida Sukjai",
              "isAdmin": False, "iat": now, "exp": now + exp_in, "jti": f"jti-{now}-{email}-{aud}-{exp_in}", **extra}
    return jwt.encode(claims, secret, algorithm="HS256")


def _handlers(rows):
    from GEPPPlatform.services.admin.admin_handlers import AdminHandlers
    session = MagicMock()
    session.query.return_value.filter.return_value.order_by.return_value.all.return_value = rows
    h = AdminHandlers.__new__(AdminHandlers)
    h.db_session, h.current_user, h.jwt_secret = session, {}, "v3-test-secret"
    return h, session


def _row(**kw):
    base = dict(id=7, organization_id=None, email="nida@gepp.me", platform_role="gepp-admin", display_name="Nida")
    return SimpleNamespace(**{**base, **kw})


def test_existing_admin_gets_the_normal_admin_token():
    h, session = _handlers([_row(platform_role="super-admin")])
    out = h.admin_sso({"assertion": _assertion()})
    claims = jwt.decode(out["token"], "v3-test-secret", algorithms=["HS256"])
    assert claims["admin_role"] == "super-admin" and claims["user_id"] == 7 and claims["type"] == "auth"
    assert out["sso"]["provider"] == "gepp-team" and out["role"] == {"id": 1}
    session.add.assert_not_called()


def test_customer_account_with_same_email_is_never_elevated():
    from GEPPPlatform.libs.exceptions import UnauthorizedException
    h, session = _handlers([_row(platform_role=None)])
    with pytest.raises(UnauthorizedException):
        h.admin_sso({"assertion": _assertion()})
    session.add.assert_not_called()


def test_new_staff_is_provisioned_as_gepp_admin_without_password(monkeypatch):
    h, session = _handlers([])

    def _flush():
        session.add.call_args[0][0].id = 99
    session.flush.side_effect = _flush
    out = h.admin_sso({"assertion": _assertion(email="Kanya@GEPP.me")})
    created = session.add.call_args[0][0]
    assert created.email == "kanya@gepp.me" and created.password is None and created.platform_role == "gepp-admin"
    assert created.is_user and not created.is_location and created.display_name == "Nida Sukjai"
    assert jwt.decode(out["token"], "v3-test-secret", algorithms=["HS256"])["user_id"] == 99


def test_iso_admin_is_provisioned_as_super_admin():
    h, session = _handlers([])
    session.flush.side_effect = lambda: setattr(session.add.call_args[0][0], "id", 5)
    h.admin_sso({"assertion": _assertion(isAdmin=True)})
    assert session.add.call_args[0][0].platform_role == "super-admin"


def test_provisioning_can_be_switched_off_and_is_domain_limited(monkeypatch):
    from GEPPPlatform.libs.exceptions import UnauthorizedException
    monkeypatch.setenv("GEPP_TEAM_SSO_AUTO_PROVISION", "0")
    h, session = _handlers([])
    with pytest.raises(UnauthorizedException):
        h.admin_sso({"assertion": _assertion()})
    monkeypatch.delenv("GEPP_TEAM_SSO_AUTO_PROVISION")
    with pytest.raises(UnauthorizedException):
        h.admin_sso({"assertion": _assertion(email="x@auditfirm.co.th")})
    session.add.assert_not_called()


@pytest.mark.parametrize("bad", [
    lambda: _assertion(aud="v2"),                       # meant for another backend
    lambda: _assertion(exp_in=-120),                    # expired (beyond the 30 s leeway)
    lambda: _assertion(secret="someone-elses-secret-" + "q" * 20),
    lambda: _assertion(typ="access"),                   # an ISO session token is not an assertion
    lambda: "not-a-jwt",
])
def test_bad_assertions_are_rejected(bad):
    from GEPPPlatform.libs.exceptions import UnauthorizedException
    h, _ = _handlers([_row()])
    with pytest.raises(UnauthorizedException):
        h.admin_sso({"assertion": bad()})


def test_replay_is_rejected():
    from GEPPPlatform.libs.exceptions import UnauthorizedException
    h, _ = _handlers([_row()])
    a = _assertion()
    h.admin_sso({"assertion": a})
    with pytest.raises(UnauthorizedException):
        h.admin_sso({"assertion": a})


def test_missing_secret_is_a_clear_error(monkeypatch):
    from GEPPPlatform.libs.exceptions import UnauthorizedException
    monkeypatch.delenv("GEPP_TEAM_SSO_SECRET")
    h, _ = _handlers([_row()])
    with pytest.raises(UnauthorizedException, match="not configured"):
        h.admin_sso({"assertion": _assertion()})


def test_password_login_still_issues_identical_token_shape():
    import bcrypt
    pw = bcrypt.hashpw(b"Old-Pass-2026!", bcrypt.gensalt(4)).decode()
    h, session = _handlers([])
    session.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        id=3, organization_id=1, email="ops@gepp.me", platform_role="gepp-admin", display_name="Ops", password=pw)
    out = h.admin_login({"email": "ops@gepp.me", "password": "Old-Pass-2026!"})
    assert set(out) >= {"token", "tokenExpiry", "auth_token", "refresh_token", "role", "adminRole", "id"}
