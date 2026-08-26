"""The stdlib-only Google service-account signer must match the real thing.

`libs/google_sa_auth.py` implements RS256 (RSASSA-PKCS1-v1_5 over SHA-256) and a
DER parser by hand so the BMA sheet cron needs no Google packages in its Lambda
layer. Hand-rolled crypto is only acceptable if it is checked against a
reference, so every test here verifies our output with `cryptography` and/or
PyJWT — both dev-only dependencies that are never shipped.
"""

import base64
import json

import pytest

from GEPPPlatform.libs.google_sa_auth import (
    make_jwt_assertion,
    parse_rsa_private_key,
    rsa_sign_sha256,
)

cryptography = pytest.importorskip('cryptography')
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402


@pytest.fixture(scope='module')
def keypair():
    """A throwaway 2048-bit key, exported the way Google exports one (PKCS#8)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pkcs8 = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    pkcs1 = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    return key, pkcs8, pkcs1


def test_der_parser_recovers_the_key_numbers(keypair):
    key, pkcs8, _ = keypair
    numbers = key.private_numbers()
    n, e, d = parse_rsa_private_key(pkcs8)
    assert n == numbers.public_numbers.n
    assert e == numbers.public_numbers.e
    assert d == numbers.d


def test_der_parser_also_accepts_pkcs1(keypair):
    """A key someone converted with `openssl rsa` must still load."""
    key, _, pkcs1 = keypair
    n, e, d = parse_rsa_private_key(pkcs1)
    numbers = key.private_numbers()
    assert (n, e, d) == (numbers.public_numbers.n, numbers.public_numbers.e, numbers.d)


@pytest.mark.parametrize('message', [
    b'',
    b'a',
    b'the quick brown fox',
    b'\x00\x01\x02\xff\xfe',
    b'x' * 10_000,
    'ไม่เทรวม'.encode(),
])
def test_signature_verifies_under_cryptography(keypair, message):
    """Our signature must be accepted by a real verifier, byte for byte."""
    key, pkcs8, _ = keypair
    n, _e, d = parse_rsa_private_key(pkcs8)
    sig = rsa_sign_sha256(message, n, d)

    # 1. it verifies
    key.public_key().verify(sig, message, padding.PKCS1v15(), hashes.SHA256())
    # 2. and it is bit-identical to what cryptography would have produced
    #    (PKCS#1 v1.5 is deterministic, unlike PSS)
    assert sig == key.sign(message, padding.PKCS1v15(), hashes.SHA256())
    assert len(sig) == 256          # 2048-bit key


def test_signature_rejects_a_tampered_message(keypair):
    key, pkcs8, _ = keypair
    n, _e, d = parse_rsa_private_key(pkcs8)
    sig = rsa_sign_sha256(b'original', n, d)
    with pytest.raises(Exception):
        key.public_key().verify(sig, b'tampered', padding.PKCS1v15(), hashes.SHA256())


def test_assertion_is_a_jwt_pyjwt_can_decode(keypair):
    """The assembled assertion must be a valid RS256 JWT with Google's claims."""
    jwt = pytest.importorskip('jwt')
    key, pkcs8, _ = keypair
    n, _e, d = parse_rsa_private_key(pkcs8)

    token = make_jwt_assertion(
        'svc@example.iam.gserviceaccount.com',
        'https://www.googleapis.com/auth/spreadsheets',
        'https://oauth2.googleapis.com/token',
        n, d,
    )

    decoded = jwt.decode(
        token.decode(), key.public_key(), algorithms=['RS256'],
        audience='https://oauth2.googleapis.com/token',
    )
    assert decoded['iss'] == 'svc@example.iam.gserviceaccount.com'
    assert decoded['scope'] == 'https://www.googleapis.com/auth/spreadsheets'
    assert decoded['exp'] > decoded['iat']

    header = json.loads(base64.urlsafe_b64decode(
        token.split(b'.')[0] + b'=' * (-len(token.split(b'.')[0]) % 4)))
    assert header == {'alg': 'RS256', 'typ': 'JWT'}


def test_assertion_has_no_base64_padding(keypair):
    """JWT is base64url *without* padding; '=' in a segment breaks strict parsers."""
    _key, pkcs8, _ = keypair
    n, _e, d = parse_rsa_private_key(pkcs8)
    token = make_jwt_assertion('a@b.com', 'scope', 'aud', n, d)
    assert token.count(b'.') == 2
    assert b'=' not in token


def test_bad_pem_fails_loudly():
    with pytest.raises(ValueError):
        parse_rsa_private_key('-----BEGIN PRIVATE KEY-----\n-----END PRIVATE KEY-----')
    with pytest.raises(Exception):
        parse_rsa_private_key('not a pem at all')


class TestGoogleApiErrorParsing:
    """403 is ambiguous — the body is the only thing that says which 403.

    Guarding a real bug: the credential checker used to key its advice off the
    status code, so "Sheets API not enabled" was reported as "the sheet is not
    shared" and sent the reader to fix the wrong thing.
    """

    def _err(self, body, code=403):
        from GEPPPlatform.libs.google_sa_auth import GoogleApiError
        return GoogleApiError('POST', 'https://example/x', code, json.dumps(body))

    def test_service_disabled_is_recognised_and_yields_the_console_url(self):
        err = self._err({'error': {
            'code': 403,
            'message': ('Google Sheets API has not been used in project '
                        '1078402786998 before or it is disabled.'),
            'status': 'PERMISSION_DENIED',
            'details': [{
                '@type': 'type.googleapis.com/google.rpc.ErrorInfo',
                'reason': 'SERVICE_DISABLED',
                'metadata': {
                    'activationUrl': 'https://console.developers.google.com/apis/api/sheets.googleapis.com/overview?project=1078402786998',
                    'consumer': 'projects/1078402786998',
                },
            }],
        }})
        assert err.service_disabled is True
        assert err.reason == 'SERVICE_DISABLED'
        assert 'sheets.googleapis.com/overview' in err.activation_url
        # the human-facing message must survive intact, not be truncated away
        assert 'has not been used in project' in err.message

    def test_permission_denied_without_service_disabled_is_a_sharing_problem(self):
        err = self._err({'error': {
            'code': 403,
            'message': 'The caller does not have permission',
            'status': 'PERMISSION_DENIED',
        }})
        assert err.service_disabled is False
        assert err.status_code == 403

    def test_legacy_access_not_configured_reason_also_counts(self):
        err = self._err({'error': {
            'message': 'Access Not Configured.',
            'errors': [{'reason': 'accessNotConfigured'}],
            'details': [{'reason': 'accessNotConfigured'}],
        }})
        assert err.service_disabled is True

    def test_oauth_token_endpoint_string_error_shape(self):
        """The token endpoint returns `error` as a string, not an object."""
        err = self._err({'error': 'invalid_grant',
                         'error_description': 'Invalid grant: account not found'},
                        code=400)
        assert err.reason == 'invalid_grant'
        assert err.message == 'Invalid grant: account not found'
        assert err.service_disabled is False

    def test_unparseable_body_still_produces_a_usable_error(self):
        err = self._err_raw('<html>502 Bad Gateway</html>', 502)
        assert err.status_code == 502
        assert '502' in str(err)
        assert err.service_disabled is False

    def _err_raw(self, raw, code):
        from GEPPPlatform.libs.google_sa_auth import GoogleApiError
        return GoogleApiError('GET', 'https://example/x', code, raw)


def test_module_imports_only_stdlib():
    """The whole point: no third-party import may creep into this module.

    If this fails, the Lambda layer silently needs a new package.
    """
    import ast
    import pathlib
    import sys

    src = pathlib.Path(
        __file__).parent.parent / 'GEPPPlatform' / 'libs' / 'google_sa_auth.py'
    tree = ast.parse(src.read_text(encoding='utf-8'))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split('.')[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split('.')[0])

    stdlib = set(getattr(sys, 'stdlib_module_names', ()))
    assert stdlib, 'need Python 3.10+ for sys.stdlib_module_names'
    assert roots <= stdlib, f'non-stdlib imports found: {sorted(roots - stdlib)}'
