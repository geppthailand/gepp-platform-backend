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
import os
import random
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URI_DEFAULT = 'https://oauth2.googleapis.com/token'
SHEETS_BASE = 'https://sheets.googleapis.com/v4/spreadsheets'

#: ASN.1 DigestInfo prefix for SHA-256, per RFC 8017 §9.2 notes. Fixed bytes:
#: SEQUENCE { SEQUENCE { OID 2.16.840.1.101.3.4.2.1, NULL }, OCTET STRING }
_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex('3031300d060960864801650304020105000420')

#: Measured on the BMA workbook, whose `Master-*` tabs hold ~450,000 formula
#: cells that Sheets recalculates before serving any cell value:
#:
#:     values.get of 1 cell   530 s
#:     values.get of 1 row    601 s
#:     spreadsheets.get       0.6 s   (metadata; serves no values)
#:
#: So a timeout is not a safety net here, it is a policy decision about how long
#: a legitimate call may take. Set it BELOW the real distribution and every call
#: fails, is retried, and fails again — burning the budget without ever
#: succeeding. 120 s looked generous and was well inside the normal range.
_HTTP_TIMEOUT = int(os.environ.get('GOOGLE_HTTP_TIMEOUT', '540'))

#: Deliberately low, for the same reason. When the p50 is minutes, a retry is
#: not a cheap second chance — it is another several minutes against a hard
#: Lambda ceiling, and a call that timed out has usually not failed so much as
#: not finished yet. One retry covers a genuine blip; four turns a slow run into
#: a failed one. Retried on timeout, on 5xx and on 429.
_HTTP_RETRIES = int(os.environ.get('GOOGLE_HTTP_RETRIES', '1'))
_HTTP_BACKOFF = 2.0
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


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


def _request(url, method='GET', body=None, headers=None, retries=None):
    """One call, retried through the failures Google actually produces.

    A PUT is retried too. `values.update` and `values.clear` address an exact
    A1 range and set it to an exact content, so repeating one converges on the
    same cells — unlike an append, which would duplicate. If that ever stops
    being true for a caller, that caller must pass ``retries=0``.
    """
    data = None
    headers = dict(headers or {})
    if body is not None:
        if isinstance(body, (dict, list)):
            data = json.dumps(body).encode()
            headers.setdefault('Content-Type', 'application/json; charset=UTF-8')
        else:
            data = body
    attempts = (_HTTP_RETRIES if retries is None else retries) + 1
    last = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, headers=headers,
                                     method=method)
        try:
            with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
                raw = resp.read().decode()
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode()
            except Exception:
                detail = ''
            # Google's error bodies say exactly what is wrong and often carry
            # the console URL that fixes it — truncating them turns a 5-second
            # fix into an afternoon, so the whole body is kept on the exception.
            err = GoogleApiError(method, url, e.code, detail)
            if e.code not in _RETRY_STATUS or attempt == attempts - 1:
                raise err from None
            last = err
        except (socket.timeout, TimeoutError, urllib.error.URLError,
                ConnectionError) as e:
            if attempt == attempts - 1:
                raise
            last = e
        # Full jitter: several tabs are synced in a loop, and a fixed backoff
        # would line their retries up on the same second.
        delay = _HTTP_BACKOFF * (2 ** attempt)
        time.sleep(random.uniform(delay / 2, delay))
    raise last


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

    def batch_update_values(self, sheet_id, writes, value_input_option='RAW'):
        """PUT several disjoint ranges in one request.

        `writes` is ``[(a1_range, values), …]``. One call rather than one per
        range matters when a caller deliberately writes around a column it must
        not touch: the ranges land together, so the sheet is never briefly half
        updated.
        """
        if not writes:
            return {}
        body = {
            'valueInputOption': value_input_option,
            'data': [{'range': rng, 'values': values} for rng, values in writes],
        }
        return _request(f'{SHEETS_BASE}/{sheet_id}/values:batchUpdate',
                        'POST', body, self._headers)

    def batch_get(self, sheet_id, ranges):
        """Several ranges in one GET; returns one value-grid per range, in order."""
        if not ranges:
            return []
        qs = '&'.join(['majorDimension=ROWS']
                      + [f'ranges={self._range(r)}' for r in ranges])
        data = _request(f'{SHEETS_BASE}/{sheet_id}/values:batchGet?{qs}',
                        'GET', None, self._headers)
        return [vr.get('values', []) or []
                for vr in (data.get('valueRanges') or [])]

    def column_values(self, sheet_id, tab, column, start_row=1):
        """One column, top to bottom, as a flat list of strings.

        Short rows come back from the API as missing rather than empty, so the
        result is padded to the last non-empty cell and no further — the length
        is the number of rows that actually carry something.
        """
        rng = f"'{tab}'!{column}{start_row}:{column}"
        values = self.get(sheet_id, rng).get('values', []) or []
        return [(row[0] if row else '') for row in values]

    def tab_properties(self, sheet_id):
        """``{title: {'sheet_id': int, 'rows': int, 'cols': int}}``.

        A Sheets grid is finite — the `All data-GEPP` tab is 28 columns wide, so
        a range like `ZZ9999` is rejected with "exceeds grid limits" rather than
        being treated as empty space. Anything that writes past the current
        edge has to ask for the real dimensions first, and `sheet_id` is what
        `resize_tab` and every other structural call address a tab by.
        """
        qs = urllib.parse.urlencode(
            {'fields': 'sheets.properties(sheetId,title,gridProperties)'})
        data = _request(f'{SHEETS_BASE}/{sheet_id}?{qs}', 'GET', None, self._headers)
        out = {}
        for sheet in data.get('sheets') or []:
            props = sheet.get('properties') or {}
            grid = props.get('gridProperties') or {}
            out[props.get('title')] = {
                'sheet_id': props.get('sheetId'),
                'rows': grid.get('rowCount', 0),
                'cols': grid.get('columnCount', 0),
            }
        return out

    def tab_grid(self, sheet_id):
        """{tab title: (row_count, column_count)} for every tab."""
        return {title: (p['rows'], p['cols'])
                for title, p in self.tab_properties(sheet_id).items()}

    def batch_update(self, sheet_id, requests):
        """The structural API (`spreadsheets.batchUpdate`) — tabs, not cells."""
        return _request(f'{SHEETS_BASE}/{sheet_id}:batchUpdate',
                        'POST', {'requests': requests}, self._headers)

    def add_tab(self, sheet_id, title, rows=1000, cols=26):
        """Create a tab and return its properties dict.

        Sized up front rather than grown later: a new sheet defaults to 26
        columns, which a few years of monthly columns walks straight past.
        """
        resp = self.batch_update(sheet_id, [{'addSheet': {'properties': {
            'title': title,
            'gridProperties': {'rowCount': rows, 'columnCount': cols},
        }}}])
        props = (resp.get('replies') or [{}])[0].get('addSheet', {}).get('properties', {})
        grid = props.get('gridProperties') or {}
        return {'sheet_id': props.get('sheetId'),
                'rows': grid.get('rowCount', rows),
                'cols': grid.get('columnCount', cols)}

    def resize_tab(self, sheet_id, tab_sheet_id, rows, cols):
        """Grow a tab's grid. Only ever called to enlarge."""
        return self.batch_update(sheet_id, [{'updateSheetProperties': {
            'properties': {'sheetId': tab_sheet_id,
                           'gridProperties': {'rowCount': rows,
                                              'columnCount': cols}},
            'fields': 'gridProperties.rowCount,gridProperties.columnCount',
        }}])
