# Shared Libraries

Shared runtime helpers live here. Lambda entry modules should import reusable
logic from `libs` or `services`; they should not carry business logic directly.

Compatibility shims still exist at `GEPPPlatform.config`, `GEPPPlatform.database`,
and `GEPPPlatform.exceptions` so existing imports continue to work during the
transition.

## `google_sa_auth.py`

Google service-account auth (RS256 JWT → access token) and the two Sheets
`values` calls, **standard library only** — so a Lambda that writes to a Google
Sheet needs no additions to its layer. Keep it that way: the hand-rolled RSA
signing is verified against `cryptography` and PyJWT in
`tests/test_google_sa_auth.py`, which also fails if a non-stdlib import appears
in the module.

It is deliberately service-account-only and limited to `values.update` /
`values.clear`. Anything richer (batchUpdate, formatting, user OAuth) should use
the official client rather than grow this file.

