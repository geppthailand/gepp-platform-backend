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

**Scope of the rule.** `subscriptions.max_file_size_mb` is the maximum COMBINED
size of every file on ONE transaction — not a per-file cap. Three 40 KB photos
against a 100 KB limit is a refusal. A per-file rule would let an unbounded
number of just-under-the-limit files through, which is the opposite of a storage
limit.

A violation fails the WHOLE transaction rather than dropping the offending
attachment, because a transaction saved with some of its evidence missing is
worse than one the user retries. The error therefore lists every file with its
size, since with a total limit no individual file need look too large.
"""

import base64
import binascii
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: `data:image/webp;base64,....` — an explicit, unambiguous marker that the
#: string is an encoded file rather than the file's own text.
_DATA_URL_RE = re.compile(r'^data:([^;,]*);base64,', re.IGNORECASE)


def _mb(n: float) -> str:
    """MB to 2dp — the limit can legitimately be 0.1 MB, and '0.1' rendered at
    one decimal from a 0.05 value would read as the same number as the limit."""
    return f'{n / (1024 * 1024):.2f}'


class FileTooLargeError(ValueError):
    """A transaction's attachments exceed the org's total-size limit.

    Subclasses ValueError so the QR channel's existing `except ValueError` —
    which already turns a size refusal into a clean `FILE_TOO_LARGE` response —
    keeps working unchanged.
    """

    def __init__(self, files: Sequence[Dict[str, Any]], max_bytes: int,
                 total: Optional[int] = None):
        self.files = list(files)
        #: Kept as `offenders` for callers that report a per-file breakdown.
        self.offenders = self.files
        self.max_bytes = max_bytes
        self.total_bytes = (total if total is not None
                            else sum(f['size_bytes'] for f in self.files))

        if len(self.files) == 1:
            f = self.files[0]
            detail = f"{f['filename']} is {_mb(f['size_bytes'])} MB"
        else:
            breakdown = ', '.join(
                f"{f['filename']} {_mb(f['size_bytes'])} MB" for f in self.files)
            detail = (f"{len(self.files)} files total "
                      f"{_mb(self.total_bytes)} MB ({breakdown})")
        super().__init__(
            f"Attachments exceed this organization's {_mb(max_bytes)} MB limit "
            f"per transaction: {detail}."
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
    """Raise `FileTooLargeError` if the files' COMBINED size exceeds `max_bytes`.

    The limit is per TRANSACTION, not per file: three 40 KB photos against a
    100 KB limit is a refusal, even though no single file is over. A per-file
    rule would let an unbounded number of just-under-the-limit files through,
    which is the opposite of a storage limit.

    Returns the per-file sizes it measured, so callers can report the breakdown
    without measuring twice.

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

    if max_bytes is None or not measured:
        return measured

    total = sum(m['size_bytes'] for m in measured)
    if total > max_bytes:
        raise FileTooLargeError(measured, max_bytes, total=total)
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
        # No auto-renewal here on purpose. A lapsed period used to be rolled
        # forward automatically so the limit stayed the agreed one; that is now
        # handled by refusing access outright (see `access.py`), so an org that
        # reaches this code has a live period by definition.
        return resolve_org_limits(db, organization_id).max_file_size_bytes
    except Exception:      # pragma: no cover - defensive
        import logging
        logging.getLogger(__name__).warning(
            'Could not resolve upload size limit for org %s; per-file size '
            'will not be enforced on this request', organization_id,
            exc_info=True)
        return None


def collect_file_ids(*sources) -> List[int]:
    """Every integer file id found across `images`-style lists.

    A transaction carries attachments in two places — the transaction's own
    `images` and each record's `images` — and the limit is on the transaction as
    a whole, so both have to be gathered before anything is measured.

    Legacy rows put S3 URLs in the same field; those are strings and are skipped
    (there is no id to look a size up by). Duplicates are collapsed: the same
    file referenced by the transaction and by one of its records is one object in
    S3 and must be counted once.
    """
    seen, out = set(), []
    for source in sources:
        if not isinstance(source, (list, tuple)):
            continue
        for item in source:
            if isinstance(item, bool):
                continue
            if isinstance(item, int):
                fid = item
            elif isinstance(item, str) and item.strip().isdigit():
                fid = int(item.strip())
            else:
                continue          # a URL (legacy) — nothing to measure
            if fid not in seen:
                seen.add(fid)
                out.append(fid)
    return out


def check_uploaded_file_ids(db, file_ids: Sequence[int],
                            max_bytes: Optional[int],
                            s3_client=None) -> int:
    """Total the real sizes of already-uploaded files; raise if over the limit.

    This is the check that makes the limit true for the WEB path. There the
    browser POSTs each file straight to S3 before the transaction exists, so:

      * the presigned `content-length-range` can only bound ONE object — S3 has
        no notion of "these five uploads together";
      * `File.file_size` is never populated (`mark_uploaded` has no callers), so
        the database cannot answer it either.

    So the sizes come from S3 itself via HEAD, which is authoritative and cannot
    be spoofed by a patched client. A handful of HEADs per transaction is a few
    milliseconds and only happens when attachments are present.

    Returns the measured total. Raises `FileTooLargeError` when it exceeds
    `max_bytes`. A file whose size cannot be determined contributes 0 rather
    than blocking the transaction — under-counting is the safe direction for a
    check that can otherwise refuse legitimate work over an S3 hiccup.
    """
    if max_bytes is None or not file_ids:
        return 0

    measured = measure_uploaded_file_ids(db, file_ids, s3_client=s3_client)
    if not measured:
        return 0

    total = sum(m['size_bytes'] for m in measured)
    if total > max_bytes:
        raise FileTooLargeError(measured, max_bytes, total=total)
    return total


def measure_uploaded_file_ids(db, file_ids: Sequence[int],
                              s3_client=None) -> List[Dict[str, Any]]:
    """Sizes of already-uploaded files, measured but NOT judged.

    Split out from `check_uploaded_file_ids` because presign needs the running
    total to work out the REMAINING budget, and raising there would be wrong —
    it has to answer "may I issue a URL for this new file", which needs the
    existing total as a number, not an exception.
    """
    from ...models.cores.files import File

    if not file_ids:
        return []

    rows = (
        db.query(File)
        .filter(File.id.in_(list(file_ids)),
                File.deleted_date.is_(None))
        .all()
    )

    measured = []
    for row in rows:
        size = row.file_size or 0
        if not size and row.s3_key:
            size = _head_object_size(s3_client, row.s3_bucket, row.s3_key)
        measured.append({
            'index': row.id,
            'filename': row.original_filename or f'file #{row.id}',
            'size_bytes': int(size or 0),
        })
    return measured


def sum_uploaded_file_ids(db, file_ids: Sequence[int], s3_client=None) -> int:
    """Total bytes already attached, for computing the remaining budget."""
    return sum(m['size_bytes']
               for m in measure_uploaded_file_ids(db, file_ids, s3_client))


def _head_object_size(s3_client, bucket: Optional[str], key: str) -> int:
    """ContentLength of one S3 object, or 0 if it cannot be read."""
    try:
        if s3_client is None:
            import boto3
            from botocore.config import Config as BotoConfig
            s3_client = boto3.client(
                's3', config=BotoConfig(signature_version='s3v4'))
        import os
        bucket = bucket or os.getenv('S3_BUCKET_NAME', 'prod-gepp-platform-assets')
        return int(s3_client.head_object(Bucket=bucket, Key=key)['ContentLength'])
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            'Could not HEAD s3://%s/%s for size; counting it as 0', bucket, key)
        return 0


def transaction_total_bytes(measured: Sequence[Dict[str, Any]]) -> int:
    """Sum of the measured files — the size of the whole transaction's evidence,
    and the quantity the limit is enforced against."""
    return sum(m['size_bytes'] for m in measured)
