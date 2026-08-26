"""Google service-account auth + Sheets writes using only the standard library.

WHY
    `google-api-python-client` + `google-auth` drag in httplib2, uritemplate,
    google-auth-httplib2, rsa, pyasn1, pyasn1-modules and cachetools — a large
    slice of a Lambda layer for what is, underneath, two HTTPS calls. The parts
    we actually need are:

      1. sign a JWT with the service account's RSA key   (RS256)
      2. POST it to Google's token endpoint for an access token
      3. call the Sheets REST API with that token

    Steps 2 and 3 are `urllib.request`. Step 1 is the only real work, and RSA
    signing is `pow(m, d, n)` — the private exponent is right there in the key
    file. So this module implements PKCS#1 v1.5 over SHA-256 directly and drops
    both packages.

    Correctness is not left to inspection: `tests/test_google_sa_auth.py`
    round-trips the signature against `cryptography` and against PyJWT, and
    checks the DER parser on a freshly generated key.

SCOPE
    Deliberately minimal — service-account (two-legged) flow only. No user
    OAuth, no refresh tokens, no resumable uploads. If a caller needs more than
    `values.update` / `values.clear`, reach for the real client instead of
    growing this file.
"""

import base64
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URI_DEFAULT = 'https://oauth2.googleapis.com/token'
SHEETS_BASE = 'https://sheets.googleapis.com/v4/spreadsheets'

#: ASN.1 DigestInfo prefix for SHA-256, per RFC 8017 §9.2 notes. Fixed bytes:
#: SEQUENCE { SEQUENCE { OID 2.16.840.1.101.3.4.2.1, NULL }, OCTET STRING }
_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex('3031300d060960864801650304020105000420')

_HTTP_TIMEOUT = 30


# ── minimal DER reader ────────────────────────────────────────────────────

def _der_read_tlv(buf, pos):
    """Return (tag, value_bytes, next_pos) for one DER element."""
    tag = buf[pos]
    pos += 1
    length = buf[pos]
    pos += 1
    if length & 0x80:
        n = length & 0x7F
        if n == 0 or n > 4:
            raise ValueError(f'unsupported DER length form ({n} bytes)')
        length = int.from_bytes(buf[pos:pos + n], 'big')
        pos += n
    return tag, buf[pos:pos + length], pos + length


def _der_int(value):
    return int.from_bytes(value, 'big')


def _pem_to_der(pem):
    """Strip the PEM armour and base64-decode the body."""
    lines = [ln.strip() for ln in pem.strip().splitlines()]
    body = ''.join(ln for ln in lines if ln and not ln.startswith('-----'))
    if not body:
        raise ValueError('no PEM body found in private key')
    return base64.b64decode(body)


def parse_rsa_private_key(pem):
    """PEM (PKCS#8 or PKCS#1) -> (n, e, d).

    Google issues PKCS#8 ("BEGIN PRIVATE KEY"), which wraps a PKCS#1
    RSAPrivateKey inside an OCTET STRING. PKCS#1 ("BEGIN RSA PRIVATE KEY") is
    accepted too so a manually converted key still works.
    """
    der = _pem_to_der(pem)

    tag, outer, _ = _der_read_tlv(der, 0)
    if tag != 0x30:
        raise ValueError('private key: expected an outer SEQUENCE')

    # Peek: PKCS#1 starts version(0) then a very long INTEGER (the modulus).
    # PKCS#8 starts version(0) then a SEQUENCE (the algorithm identifier).
    pos = 0
    tag, _version, pos = _der_read_tlv(outer, pos)
    if tag != 0x02:
        raise ValueError('private key: expected a version INTEGER')

    tag, value, pos = _der_read_tlv(outer, pos)
    if tag == 0x30:
        # PKCS#8 — the next element is the wrapped PKCS#1 key.
        tag, inner_der, _ = _der_read_tlv(outer, pos)
        if tag != 0x04:
            raise ValueError('PKCS#8: expected privateKey OCTET STRING')
        tag, inner, _ = _der_read_tlv(inner_der, 0)
        if tag != 0x30:
            raise ValueError('PKCS#8: wrapped key is not a SEQUENCE')
        p = 0
        tag, _v, p = _der_read_tlv(inner, p)          # version
        _, n_b, p = _der_read_tlv(inner, p)
        _, e_b, p = _der_read_tlv(inner, p)
        _, d_b, p = _der_read_tlv(inner, p)
        return _der_int(n_b), _der_int(e_b), _der_int(d_b)

    if tag == 0x02:
        # PKCS#1 — `value` was already the modulus.
        n_b = value
        _, e_b, pos = _der_read_tlv(outer, pos)
        _, d_b, pos = _der_read_tlv(outer, pos)
        return _der_int(n_b), _der_int(e_b), _der_int(d_b)

    raise ValueError('private key: unrecognised structure')


# ── RS256 ─────────────────────────────────────────────────────────────────

def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b'=')


def rsa_sign_sha256(message, n, d):
    """RSASSA-PKCS1-v1_5 signature over SHA-256(message)."""
    k = (n.bit_length() + 7) // 8
    digest_info = _SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(message).digest()
    # EM = 0x00 || 0x01 || PS(0xFF…) || 0x00 || DigestInfo, PS >= 8 bytes.
    pad_len = k - len(digest_info) - 3
    if pad_len < 8:
        raise ValueError('RSA key too small for a SHA-256 PKCS#1 signature')
    em = b'\x00\x01' + b'\xff' * pad_len + b'\x00' + digest_info
    sig = pow(int.from_bytes(em, 'big'), d, n)
    return sig.to_bytes(k, 'big')


def make_jwt_assertion(client_email, scope, token_uri, n, d, lifetime=3600):
    """Signed JWT bearer assertion for the two-legged service-account flow."""
    now = int(time.time())
    header = {'alg': 'RS256', 'typ': 'JWT'}
    claims = {
        'iss': client_email,
        'scope': scope,
        'aud': token_uri,
        'iat': now,
        # A little back-dating absorbs clock skew between Lambda and Google;
        # without it a fast-firing function can be rejected as "issued in the
        # future".
        'exp': now + lifetime,
    }
    signing_input = b'.'.join((
        _b64url(json.dumps(header, separators=(',', ':')).encode()),
        _b64url(json.dumps(claims, separators=(',', ':')).encode()),
    ))
    return b'.'.join((signing_input, _b64url(rsa_sign_sha256(signing_input, n, d))))


# ── HTTP ──────────────────────────────────────────────────────────────────

class GoogleApiError(RuntimeError):
    """An HTTP error from Google, with the bits needed to act on it.

    A bare status code is not enough to diagnose these: **403 alone is
    ambiguous** — it is returned both for "the API is not enabled on this
    project" and for "this account cannot see that file", which need completely
    different fixes. Google distinguishes them in the body
    (`error.details[].reason`), so that gets parsed out here rather than being
    guessed at from the status by every caller.
    """

    def __init__(self, method, url, status_code, raw_body):
        self.method = method
        self.url = url
        self.status_code = status_code
        self.raw_body = raw_body
        self.body = {}
        try:
            self.body = json.loads(raw_body) or {}
        except Exception:
            pass

        err = self.body.get('error') or {}
        # `error` is a dict for the JSON APIs and a plain string for the OAuth
        # token endpoint — normalise both.
        if isinstance(err, str):
            self.message = self.body.get('error_description') or err
            self.reason = err
            self.activation_url = None
        else:
            self.message = err.get('message') or raw_body[:500]
            self.reason = None
            self.activation_url = None
            for detail in err.get('details') or []:
                if not isinstance(detail, dict):
                    continue
                self.reason = self.reason or detail.get('reason')
                meta = detail.get('metadata') or {}
                self.activation_url = (self.activation_url
                                       or meta.get('activationUrl'))
                for link in detail.get('links') or []:
                    if isinstance(link, dict) and link.get('url'):
                        self.activation_url = self.activation_url or link['url']

        super().__init__(f'{method} {url} -> HTTP {status_code}: {self.message}')

    @property
    def service_disabled(self):
        """True when the fix is 'enable the API', not 'share the file'."""
        if self.reason in ('SERVICE_DISABLED', 'accessNotConfigured'):
            return True
        m = (self.message or '').lower()
        return 'has not been used in project' in m or 'is disabled' in m


def _request(url, method='GET', body=None, headers=None):
    data = None
    headers = dict(headers or {})
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode()
            headers.setdefault('Content-Type', 'application/json; charset=UTF-8')
        else:
            data = body
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            raw = resp.read().decode()
    except urllib.error.HTTPError as e:
        try:
            detail = e.read().decode()
        except Exception:
            detail = ''
        # Google's error bodies say exactly what is wrong and often carry the
        # console URL that fixes it — truncating them turns a 5-second fix into
        # an afternoon, so the whole body is kept on the exception.
        raise GoogleApiError(method, url, e.code, detail) from None
    return json.loads(raw) if raw else {}


def get_access_token(sa_info, scope='https://www.googleapis.com/auth/spreadsheets'):
    """Service-account dict (the key JSON) -> access token string."""
    for field in ('client_email', 'private_key'):
        if not sa_info.get(field):
            raise ValueError(f'service account JSON is missing `{field}`')
    token_uri = sa_info.get('token_uri') or TOKEN_URI_DEFAULT
    n, _e, d = parse_rsa_private_key(sa_info['private_key'])
    assertion = make_jwt_assertion(sa_info['client_email'], scope, token_uri, n, d)
    payload = urllib.parse.urlencode({
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': assertion.decode(),
    }).encode()
    resp = _request(token_uri, 'POST', payload,
                    {'Content-Type': 'application/x-www-form-urlencoded'})
    token = resp.get('access_token')
    if not token:
        raise RuntimeError(f'token endpoint returned no access_token: {resp}')
    return token


def column_letter(index_1_based):
    """1 -> 'A', 26 -> 'Z', 27 -> 'AA', 28 -> 'AB'."""
    if index_1_based < 1:
        raise ValueError('column index is 1-based')
    out = ''
    n = index_1_based
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(ord('A') + rem) + out
    return out


class SheetsClient:
    """The handful of calls this project needs, over plain HTTPS."""

    def __init__(self, sa_info, scope='https://www.googleapis.com/auth/spreadsheets'):
        self._token = get_access_token(sa_info, scope)

    @property
    def _headers(self):
        return {'Authorization': f'Bearer {self._token}'}

    @staticmethod
    def _range(rng):
        # Sheets ranges carry ' and ! which must survive as path segments.
        return urllib.parse.quote(rng, safe='')

    def get(self, sheet_id, rng):
        return _request(
            f'{SHEETS_BASE}/{sheet_id}/values/{self._range(rng)}',
            'GET', None, self._headers)

    def clear(self, sheet_id, rng):
        return _request(
            f'{SHEETS_BASE}/{sheet_id}/values/{self._range(rng)}:clear',
            'POST', {}, self._headers)

    def update(self, sheet_id, rng, values, value_input_option='RAW'):
        qs = urllib.parse.urlencode({'valueInputOption': value_input_option})
        return _request(
            f'{SHEETS_BASE}/{sheet_id}/values/{self._range(rng)}?{qs}',
            'PUT', {'values': values}, self._headers)

    def tab_grid(self, sheet_id):
        """{tab title: (row_count, column_count)} for every tab.

        A Sheets grid is finite — the `All data-GEPP` tab is 28 columns wide, so
        a range like `ZZ9999` is rejected with "exceeds grid limits" rather than
        being treated as empty space. Anything that needs a scratch cell has to
        ask for the real dimensions first.
        """
        qs = urllib.parse.urlencode(
            {'fields': 'sheets.properties(title,gridProperties)'})
        data = _request(f'{SHEETS_BASE}/{sheet_id}?{qs}', 'GET', None, self._headers)
        out = {}
        for sheet in data.get('sheets') or []:
            props = sheet.get('properties') or {}
            grid = props.get('gridProperties') or {}
            out[props.get('title')] = (grid.get('rowCount', 0),
                                       grid.get('columnCount', 0))
        return out
