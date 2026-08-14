"""Response post-processing for the Lambda proxy handler.

Kept out of the entry point so it can be imported — and tested — without pulling in
boto3, numpy and the rest of the application.
"""

import base64
import gzip
from typing import Any, Dict

# Below this, gzip's header plus base64's 33% expansion make the response BIGGER.
_GZIP_MIN_BYTES = 1400


def maybe_gzip(response: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    """Compress a JSON response body, when the client asked for it and it pays off.

    Lambda caps a synchronous response at 6 MB and returns nothing at all past it —
    not a partial result, an error. The traceability board is the payload that gets
    there first: one pile per weigh-in puts a busy building at ~900 cards a month,
    and a handful of buildings crosses the limit. Board payloads repeat the same
    origin and material objects on every card, which compresses extremely well, so
    this buys back far more headroom than the field-level savings would.

    Deliberately conservative — anything unexpected returns the response untouched:
      • a client that did not offer gzip gets plain JSON;
      • a body already flagged isBase64Encoded (the PDF download path) is left alone,
        since double-encoding it would corrupt the file;
      • a small body is left alone, because gzip + base64 would inflate it;
      • a body that did not actually shrink is left alone;
      • any failure falls through to the original, because a slightly large response
        is recoverable and a broken one is not.
    """
    try:
        body = response.get("body")
        if not isinstance(body, str) or response.get("isBase64Encoded"):
            return response
        raw = body.encode("utf-8")
        if len(raw) < _GZIP_MIN_BYTES:
            return response
        headers = event.get("headers") or {}
        accept = str(
            headers.get("accept-encoding") or headers.get("Accept-Encoding") or ""
        ).lower()
        if "gzip" not in accept:
            return response
        packed = base64.b64encode(gzip.compress(raw, 6)).decode("ascii")
        if len(packed) >= len(raw):
            return response
        out = dict(response)
        out["headers"] = {**(response.get("headers") or {}), "Content-Encoding": "gzip"}
        out["body"] = packed
        out["isBase64Encoded"] = True
        return out
    except Exception:  # noqa: BLE001 — see docstring
        return response
