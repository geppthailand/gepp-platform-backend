"""GEPP Team SSO — verify the 60-second assertion issued by the GEPP Team identity (ISO platform).

The back-office signs every staff member in at ISO (password + MFA), asks ISO for an
assertion with `aud` = "v3", and posts it to /api/admin/sso, which exchanges it for the
usual v3 admin token. The shared secret is GEPP_TEAM_SSO_SECRET (same value as ISO's
SSM /gepp-team/sso-secret). It is not the v3 JWT secret and not the ISO session secret.
"""
import os
import time
from collections import OrderedDict

import jwt

from .exceptions import UnauthorizedException

ISSUER = "gepp-team"
_SEEN = OrderedDict()   # jti → exp; per container, enough against a replay inside the 60-second window


def _secret() -> str:
    secret = (os.environ.get("GEPP_TEAM_SSO_SECRET") or "").strip()
    if not secret:
        raise UnauthorizedException("GEPP Team sign-in is not configured on this server (GEPP_TEAM_SSO_SECRET)")
    return secret


def allowed_domains() -> list:
    raw = os.environ.get("GEPP_TEAM_ALLOWED_DOMAINS", "gepp.me")
    return [d.strip().lower().lstrip("@") for d in raw.split(",") if d.strip()]


def verify(assertion: str, audience: str) -> dict:
    if not assertion or assertion.count(".") != 2:
        raise UnauthorizedException("Missing GEPP Team assertion")
    try:
        claims = jwt.decode(assertion, _secret(), algorithms=["HS256"], audience=audience, issuer=ISSUER,
                            leeway=30, options={"require": ["exp", "iat", "aud", "iss", "jti"]})
    except jwt.ExpiredSignatureError:
        raise UnauthorizedException("GEPP Team sign-in expired — sign in again")
    except jwt.InvalidTokenError:
        raise UnauthorizedException("Invalid GEPP Team assertion")
    if claims.get("typ") != "sso" or not (claims.get("email") or "").strip():
        raise UnauthorizedException("Invalid GEPP Team assertion")
    now = int(time.time())
    for jti, exp in list(_SEEN.items()):
        if exp < now - 60:
            _SEEN.pop(jti, None)
    if claims["jti"] in _SEEN:
        raise UnauthorizedException("This GEPP Team sign-in was already used — sign in again")
    _SEEN[claims["jti"]] = int(claims["exp"])
    claims["email"] = claims["email"].strip().lower()
    return claims
