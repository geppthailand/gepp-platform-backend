"""Enforce the per-transaction file-size limit on paths that receive BYTES.

There are two families of upload in v3 and they need opposite treatment:

  * **presigned** (browser POSTs straight to S3) — application code never sees
    the body, so the ceiling is baked into the presigned POST's
    `content-length-range` and S3 does the rejecting. See
    `presigned_url_service.py`.
  * **byte-carrying** (the payload arrives in our request body) — nothing
    rejects it unless we do. That is this module.

Byte-carrying paths, all now guarded:

    POST /api/transactions/{id}/images        transaction_handlers.py
    create transaction  `file_uploads`        transaction_service.py
    QR channel `b64image` / per-material      input_channel_service.py

The limit itself always comes from `limits.resolve_org_limits` — never a
hardcoded number — so a period's value, an org default and the system default
all reach every upload path identically.

**Scope of the rule.** The configured value is the maximum for a SINGLE file
(`subscriptions.max_file_size_mb`). It is enforced per file, but a violation
fails the WHOLE transaction rather than dropping the offending attachment,
because a transaction saved with some of its evidence missing is worse than one
the user retries. `check_files` therefore reports every offender at once, not
just the first, so the user fixes one upload instead of discovering the files
one at a time.
"""

import base64
import binascii
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: `data:image/webp;base64,....` — an explicit, unambiguous marker that the
#: string is an encoded file rather than the file's own text.
_DATA_URL_RE = re.compile(r'^data:([^;,]*);base64,', re.IGNORECASE)


class FileTooLargeError(ValueError):
    """One or more files exceed the org's per-file limit.

    Subclasses ValueError so the QR channel's existing `except ValueError` —
    which already turns a size refusal into a clean `FILE_TOO_LARGE` response —
    keeps working unchanged.
    """

    def __init__(self, offenders: Sequence[Dict[str, Any]], max_bytes: int):
        self.offenders = list(offenders)
        self.max_bytes = max_bytes
        limit_mb = max_bytes / (1024 * 1024)
        parts = [
            f"{o['filename']} ({o['size_bytes'] / (1024 * 1024):.1f} MB)"
            for o in self.offenders
        ]
        super().__init__(
            f"{'File' if len(parts) == 1 else 'Files'} too large for this "
            f"organization's {limit_mb:.1f} MB per-file limit: "
            f"{', '.join(parts)}."
        )


def _decoded_len(body: str) -> Optional[int]:
    """Decoded byte length if `body` is strictly-valid base64, else None.

    `validate=True` rejects any character outside the base64 alphabet, and the
    length-multiple-of-4 requirement rejects most natural text — so this is a
    usable discriminator between "an encoded file" and "a text file's own
    contents", not a guess.
    """
    if len(body) < 4 or len(body) % 4 != 0:
        return None
    try:
        return len(base64.b64decode(body, validate=True))
    except (binascii.Error, ValueError):
        return None


def payload_size_bytes(data: Any) -> int:
    """Size of an upload payload, measured as **the user's actual file**.

    Measuring the user's file rather than the stored object is deliberate: the
    limit is presented to people as "max file size", and a 2 MB photo that
    happens to travel as 2.7 MB of base64 must not be reported as 2.7 MB. It
    also keeps all three byte-carrying paths consistent — the QR channel decodes
    before measuring, so the other two must too, or the same photo passes on one
    and fails on another.

    Shapes that reach these handlers:

      * ``bytes`` — its own length.
      * a ``data:...;base64,`` URL — the DECODED length (MobileInput's shape).
      * a bare base64 ``str`` — the DECODED length. JSON cannot carry raw bytes,
        so a string payload on these endpoints is essentially always encoded;
        strict base64 validation is what distinguishes it from a genuine text
        attachment.
      * any other ``str`` — its UTF-8 byte length, which is what
        ``put_object(Body=...)`` stores verbatim.

    Never raises. An undecodable payload falls back to its encoded length, which
    over-estimates — the safe direction for a guard, since it can reject
    something borderline but cannot let an oversized file through.

    Caveat worth knowing: this path currently writes a ``str`` body to S3
    as-is, so a base64 payload is STORED ~33% larger than what is measured here.
    That is a pre-existing bug in the upload itself, not in the measurement; the
    guard deliberately reports the file the user chose.
    """
    if data is None:
        return 0
    if isinstance(data, (bytes, bytearray, memoryview)):
        return len(data)
    if not isinstance(data, str):
        return 0

    body = data
    match = _DATA_URL_RE.match(body)
    if match:
        body = body[match.end():]
    elif body[:5].lower() == 'data:' and ',' in body[:128]:
        # A data URL whose header we could not parse strictly; take everything
        # after the first comma rather than measuring the header as content.
        body = body.split(',', 1)[1]

    decoded = _decoded_len(body)
    if decoded is not None:
        return decoded
    return len(body.encode('utf-8', errors='ignore'))


def check_files(files: Sequence[Dict[str, Any]], max_bytes: Optional[int],
                data_key: str = 'data',
                name_key: str = 'filename') -> List[Dict[str, Any]]:
    """Raise `FileTooLargeError` if any file exceeds `max_bytes`.

    Returns the per-file sizes it measured, so callers can log or report the
    transaction total without measuring twice.

    `max_bytes=None` means "limit could not be resolved" and skips the check —
    a lookup failure must not block uploads. `max_bytes=0` is a real,
    deliberate value ("no uploads allowed") and rejects everything, which is
    why the None check is `is None` and not falsy.
    """
    measured = []
    for index, file_obj in enumerate(files or []):
        if not isinstance(file_obj, dict):
            continue
        size = payload_size_bytes(file_obj.get(data_key))
        measured.append({
            'index': index,
            'filename': file_obj.get(name_key) or f'file {index + 1}',
            'size_bytes': size,
        })

    if max_bytes is None:
        return measured

    offenders = [m for m in measured if m['size_bytes'] > max_bytes]
    if offenders:
        raise FileTooLargeError(offenders, max_bytes)
    return measured


def check_b64_images(images: Sequence[str], max_bytes: Optional[int],
                     label: str = 'Photo') -> List[Dict[str, Any]]:
    """`check_files` for a bare list of base64 strings (the QR channel shape)."""
    return check_files(
        [{'data': img, 'filename': f'{label} {i + 1}'}
         for i, img in enumerate(images or [])],
        max_bytes,
    )


def resolve_max_upload_bytes(db, organization_id: Optional[int]) -> Optional[int]:
    """The org's enforced per-file ceiling, or None if it cannot be resolved.

    None (rather than a fallback number) is deliberate: it makes "we do not know
    the limit" distinct from "the limit is X", so `check_files` can skip rather
    than guess. The presigned path makes the opposite choice — it must put SOME
    number in the S3 condition — and falls back to the system default there.
    """
    if not organization_id:
        return None
    try:
        from .limits import resolve_org_limits
        return resolve_org_limits(db, organization_id).max_file_size_bytes
    except Exception:      # pragma: no cover - defensive
        import logging
        logging.getLogger(__name__).warning(
            'Could not resolve upload size limit for org %s; per-file size '
            'will not be enforced on this request', organization_id,
            exc_info=True)
        return None


def transaction_total_bytes(measured: Sequence[Dict[str, Any]]) -> int:
    """Sum of the measured files — the size of the whole transaction's evidence.

    Reported rather than enforced: `max_file_size_mb` is documented and
    configured as a PER-FILE maximum, so capping the total here would apply a
    limit nobody set a value for. Surfacing it means the number exists for
    whoever decides whether a per-transaction total is also wanted.
    """
    return sum(m['size_bytes'] for m in measured)
