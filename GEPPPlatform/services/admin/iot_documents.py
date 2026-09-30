"""Per-device document library for the backoffice IoT device page.

A weighing scale arrives with paperwork — a calibration certificate, a manual,
a warranty slip — and carries a nameplate sticker and a settings screen that a
technician photographs. Today that all lives in someone's phone or a shared
drive, so the person looking at the device record in the backoffice cannot see
any of it. This puts it on the device.

**No new table.** A document is a row in `files`:

    related_entity_type = 'iot_device'
    related_entity_id   = <iot_devices.id>
    file_type           = 'document'

`files` already carries that entity pair (indexed), already owns the S3 key,
bucket, size, MIME type and soft-delete, and the IoT *screenshots* feature
already writes rows shaped exactly this way. `file_type` is what keeps the two
apart: screenshots are `iot_screenshot`, and neither tab can ever show the
other's rows. See migration 092 for the full reasoning.

**Three-step upload, because the browser talks to S3 directly.** `start_upload`
creates a `pending` row and hands back a presigned POST; the browser posts the
bytes to S3; `confirm_upload` flips the row to `uploaded`. The size written in
that last step is read from S3 with HEAD, never taken from the browser — a
client that never uploaded anything, or uploaded something else, cannot talk
its way into a plausible-looking row.

**These uploads are NOT bound by the organization's attachment limit.** That
limit is a per-transaction total for customer data entry; a 3 MB calibration
certificate belongs to GEPP's service records and is billed to nobody. An org
on a 0.1 MB plan would otherwise be unable to have its own paperwork filed.
`MAX_DOCUMENT_BYTES` is the ceiling instead — a real one, just a different one.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text as _t

from GEPPPlatform.exceptions import BadRequestException, NotFoundException

logger = logging.getLogger(__name__)

#: Ceiling for one uploaded document. Generous enough for a scanned multi-page
#: certificate or a phone photo at full resolution, small enough that nobody
#: parks a video of a site visit in the device record.
MAX_DOCUMENT_BYTES = 25 * 1024 * 1024

#: What the document IS, for filtering and for the thumbnail caption. Kept as
#: free-form-with-a-known-set rather than an enum column: ops will rename and
#: extend these, and each change would otherwise be a migration. An unknown
#: value from an older client is stored as 'other' rather than rejected.
DOCUMENT_CATEGORIES = (
    'settings_photo',   # photo of the scale's settings/config screen
    'nameplate',        # the serial/model sticker on the machine
    'calibration',      # calibration or verification certificate
    'manual',           # manual, datasheet, wiring diagram
    'warranty',         # warranty, invoice, purchase paperwork
    'other',
)
DEFAULT_CATEGORY = 'other'

#: Extensions the tab accepts. Anything else is refused at the presign step, so
#: a rejected file never reaches S3 and never leaves a pending row behind.
#: Deliberately a allowlist: this is an admin-only surface, but "admin-only" is
#: not a reason to accept an .html or .svg that a later viewer would render.
ALLOWED_EXTENSIONS = {
    # images — the sticker/settings photos this feature exists for
    'jpg', 'jpeg', 'png', 'gif', 'webp', 'heic',
    # documents
    'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'txt',
    'ppt', 'pptx',
}

#: Images every current browser can actually paint. Listed explicitly rather
#: than testing `mime.startswith('image/')`, because HEIC is an image by MIME
#: type and renders in no desktop browser — an <img> pointed at one yields a
#: broken-image icon, which reads as "the upload is corrupt" when it is fine.
#: A HEIC is shown as a file card with a download action instead, which is
#: honest about what the browser can do with it.
BROWSER_RENDERABLE_IMAGE_MIMES = {
    'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp',
}

#: Rendered inline (in an iframe or <img>). Everything else gets a download
#: link — an .xlsx has no in-page preview anywhere, and pretending otherwise
#: produces a blank frame the user reads as "broken".
INLINE_PREVIEWABLE_MIMES = (
    BROWSER_RENDERABLE_IMAGE_MIMES
    | {'application/pdf', 'text/plain', 'text/csv'}
)


def _extension(name: str) -> str:
    return name.rsplit('.', 1)[1].lower() if '.' in name else ''


def _normalize_category(raw: Any) -> str:
    value = (raw or '').strip().lower() if isinstance(raw, str) else ''
    return value if value in DOCUMENT_CATEGORIES else DEFAULT_CATEGORY


def _device_org(db, device_id: int) -> int:
    """The device's organization, or a refusal explaining what to do.

    `files.organization_id` is NOT NULL with an FK, so an unassigned device
    genuinely cannot own a document. Saying so — and naming the fix — beats an
    IntegrityError, which is what the caller would otherwise see.
    """
    row = db.execute(_t(
        "SELECT organization_id FROM iot_devices "
        " WHERE id = :id AND deleted_date IS NULL"
    ), {'id': device_id}).fetchone()

    if row is None:
        raise NotFoundException(f'IoT device {device_id} not found')
    if row[0] is None:
        raise BadRequestException(
            'This device is not assigned to an organization yet, so documents '
            'cannot be filed against it. Assign it to an organization first '
            '(Settings tab → Edit).'
        )
    return int(row[0])


def _is_previewable(mime: Optional[str]) -> bool:
    return bool(mime) and mime in INLINE_PREVIEWABLE_MIMES


def _is_image(mime: Optional[str]) -> bool:
    """Can the browser paint this as a thumbnail? Not "is it an image"."""
    return bool(mime) and mime in BROWSER_RENDERABLE_IMAGE_MIMES


# ── List ───────────────────────────────────────────────────────────────

def list_documents(db, device_id: int, query_params: dict = None) -> Dict[str, Any]:
    """Every document on one device, newest first, with view URLs.

    `pending` rows are included and flagged: an upload that was started and
    never confirmed is the thing an admin most needs to see — otherwise a
    failed upload is simply invisible and they try again forever.
    """
    from GEPPPlatform.services.cores.transactions.presigned_url_service import (
        TransactionPresignedUrlService,
    )

    query_params = query_params or {}
    organization_id = _device_org(db, device_id)

    category = _normalize_category(query_params.get('category')) \
        if query_params.get('category') else None

    params: Dict[str, Any] = {'device_id': device_id}
    category_clause = ''
    if category:
        # Stored inside the JSONB blob, so it is matched there rather than
        # with a column comparison.
        category_clause = " AND COALESCE(metadata->>'category', 'other') = :category "
        params['category'] = category

    rows = db.execute(_t(
        "SELECT id, status, original_filename, file_size, mime_type, "
        "       uploader_id, created_date, upload_completed_at, metadata, "
        "       source, s3_key, processing_error "
        "  FROM files "
        " WHERE related_entity_type = 'iot_device' "
        "   AND related_entity_id = :device_id "
        "   AND file_type = 'document' "
        "   AND is_active = TRUE "
        f"  {category_clause} "
        # id DESC is a tiebreaker, not decoration: a batch upload writes every
        # row in one transaction, so their created_date values are identical
        # and the grid would reshuffle on each refresh without it.
        " ORDER BY created_date DESC, id DESC "
        " LIMIT 500"
    ), params).fetchall()

    # Resolve view URLs in ONE batch. Per-row signing would be 50 round trips
    # on a well-documented device.
    #
    # Both sources are included, not just 's3': the resolver already returns an
    # 'ext' row's URL verbatim instead of signing it, and filtering those out
    # here meant a document backfilled from elsewhere rendered as a grey
    # file-type tile with no way to open it — indistinguishable from a broken
    # upload. (The Screenshots tab filters to 's3'; screenshots are only ever
    # written by us, so it never sees an 'ext' row.)
    uploaded_ids = [int(r[0]) for r in rows if r[1] == 'uploaded']
    view_url_by_id: Dict[int, str] = {}
    if uploaded_ids:
        try:
            res = TransactionPresignedUrlService(
            ).get_transaction_file_view_presigned_urls_by_ids(
                file_ids=uploaded_ids,
                db=db,
                organization_id=organization_id,
                user_id=0,
                expiration_seconds=3600,
            )
            for fid, info in (res.get('presigned_urls') or {}).items():
                if isinstance(info, dict) and info.get('view_url'):
                    try:
                        view_url_by_id[int(fid)] = info['view_url']
                    except (TypeError, ValueError):
                        continue
        except Exception:
            # A signing failure must not blank the whole tab: the rows still
            # carry name, size, category and date, which is most of what the
            # page is for.
            logger.warning('Could not presign document view URLs for device %s',
                           device_id, exc_info=True)

    # Uploader names in one query, so the card can say who filed it.
    uploader_ids = {int(r[5]) for r in rows if r[5]}
    uploader_by_id: Dict[int, str] = {}
    if uploader_ids:
        try:
            for uid, name, email in db.execute(_t(
                "SELECT id, display_name, email FROM user_locations "
                " WHERE id = ANY(:ids)"
            ), {'ids': list(uploader_ids)}).fetchall():
                uploader_by_id[int(uid)] = name or email or f'#{uid}'
        except Exception:
            logger.warning('Could not resolve document uploaders', exc_info=True)

    items: List[Dict[str, Any]] = []
    for r in rows:
        meta = r[8] or {}
        mime = r[4]
        items.append({
            'id': int(r[0]),
            'status': r[1],
            'originalFilename': r[2],
            'fileSize': int(r[3]) if r[3] is not None else None,
            'mimeType': mime,
            'uploaderId': int(r[5]) if r[5] else None,
            'uploaderName': uploader_by_id.get(int(r[5])) if r[5] else None,
            'createdDate': r[6].isoformat() if r[6] else None,
            'uploadCompletedAt': r[7],
            'category': _normalize_category(meta.get('category')),
            'note': meta.get('note'),
            'viewUrl': view_url_by_id.get(int(r[0])),
            'processingError': r[11],
            # Told by the server, not guessed from the filename in the UI, so
            # the two can never disagree about what opens inline.
            'isImage': _is_image(mime),
            'isPreviewable': _is_previewable(mime),
        })

    return {
        'items': items,
        'total': len(items),
        'categories': list(DOCUMENT_CATEGORIES),
        'maxFileSizeBytes': MAX_DOCUMENT_BYTES,
        'allowedExtensions': sorted(ALLOWED_EXTENSIONS),
    }


# ── Upload (start → browser posts to S3 → confirm) ──────────────────────

def start_upload(db, device_id: int, data: dict, current_user: dict) -> Dict[str, Any]:
    """Create the pending row(s) + presigned POST the browser uploads with."""
    from GEPPPlatform.services.cores.transactions.presigned_url_service import (
        TransactionPresignedUrlService,
    )

    organization_id = _device_org(db, device_id)

    uploader_id = (current_user or {}).get('user_id')
    if not uploader_id:
        raise BadRequestException('Cannot determine the uploading admin user')

    raw_files = data.get('files')
    if not isinstance(raw_files, list) or not raw_files:
        raise BadRequestException('files[] is required: [{fileName, fileSize}]')
    if len(raw_files) > 20:
        raise BadRequestException('At most 20 documents can be uploaded at once')

    file_names: List[str] = []
    file_sizes: List[Optional[int]] = []
    for entry in raw_files:
        if not isinstance(entry, dict):
            raise BadRequestException('Each files[] entry must be an object')
        name = (entry.get('fileName') or '').strip()
        if not name:
            raise BadRequestException('files[].fileName is required')

        ext = _extension(name)
        if ext not in ALLOWED_EXTENSIONS:
            raise BadRequestException(
                f'"{name}": .{ext or "?"} files are not accepted here. '
                f'Allowed: {", ".join(sorted(ALLOWED_EXTENSIONS))}.'
            )

        size = entry.get('fileSize')
        try:
            size = int(size) if size is not None else None
        except (TypeError, ValueError):
            size = None
        if size is not None and size > MAX_DOCUMENT_BYTES:
            raise BadRequestException(
                f'"{name}" is {size / (1024 * 1024):.1f} MB, over the '
                f'{MAX_DOCUMENT_BYTES // (1024 * 1024)} MB limit for device '
                f'documents.'
            )

        file_names.append(name)
        file_sizes.append(size)

    category = _normalize_category(data.get('category'))
    note = data.get('note')
    note = note.strip()[:500] if isinstance(note, str) else None

    res = TransactionPresignedUrlService().get_transaction_file_upload_presigned_urls(
        file_names=file_names,
        organization_id=organization_id,
        user_id=int(uploader_id),
        db=db,
        file_type='document',
        related_entity_type='iot_device',
        related_entity_id=device_id,
        expiration_seconds=900,          # 15 min — a slow phone on site 3G
        file_sizes=file_sizes,
        # Not a transaction attachment: see the module docstring.
        max_upload_bytes_override=MAX_DOCUMENT_BYTES,
        key_prefix=f'iot-devices/{device_id}/documents',
    )

    if not res.get('success'):
        raise BadRequestException(
            res.get('message') or 'Could not allocate an upload URL')

    items = res.get('presigned_urls') or []

    # The category and note are known now, not at confirm time — write them
    # immediately so a row that is never confirmed is still identifiable
    # rather than an anonymous pending blob.
    for item in items:
        file_id = item.get('file_id')
        if not file_id:
            continue
        db.execute(_t(
            "UPDATE files "
            "   SET metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:patch AS jsonb) "
            " WHERE id = :id"
        ), {
            'id': int(file_id),
            'patch': _json_dumps({
                'category': category,
                'note': note,
                'device_id': device_id,
                'uploaded_via': 'backoffice',
            }),
        })
    db.commit()

    return {
        'uploads': [{
            'fileId': i.get('file_id'),
            'fileName': i.get('original_filename'),
            'uploadUrl': i.get('upload_url'),
            'uploadFields': i.get('upload_fields'),
            'contentType': i.get('content_type'),
            'expiresAt': i.get('expires_at'),
        } for i in items],
        'category': category,
        'maxFileSizeBytes': MAX_DOCUMENT_BYTES,
    }


def _json_dumps(obj) -> str:
    import json
    return json.dumps(obj)


def confirm_upload(db, device_id: int, file_id: int, data: dict,
                   current_user: dict = None) -> Dict[str, Any]:
    """Flip a pending row to `uploaded`, sizing it from S3 rather than trust.

    The browser posted the bytes straight to S3, so the only honest source for
    "did that actually land, and how big is it?" is S3 itself. A HEAD that
    finds nothing means the upload failed; the row is marked failed so the tab
    shows a reason instead of a document that is not there.
    """
    from GEPPPlatform.services.subscriptions.upload_guard import _head_object_size

    _device_org(db, device_id)  # existence + ownership

    row = db.execute(_t(
        "SELECT id, status, s3_key, s3_bucket FROM files "
        " WHERE id = :id "
        "   AND related_entity_type = 'iot_device' "
        "   AND related_entity_id = :device_id "
        "   AND file_type = 'document' "
        "   AND is_active = TRUE"
    ), {'id': file_id, 'device_id': device_id}).fetchone()

    if row is None:
        raise NotFoundException(
            f'Document {file_id} not found on device {device_id}')

    size = _head_object_size(None, row[3], row[2])

    if size <= 0:
        db.execute(_t(
            "UPDATE files SET status = 'failed', "
            "       processing_error = :err, updated_date = NOW() "
            " WHERE id = :id"
        ), {
            'id': file_id,
            'err': 'Upload did not reach S3 (object missing or empty).',
        })
        db.commit()
        raise BadRequestException(
            'The upload did not reach storage. Please try again.')

    db.execute(_t(
        "UPDATE files "
        "   SET status = 'uploaded', "
        "       file_size = :size, "
        "       upload_completed_at = :ts, "
        "       processing_error = NULL, "
        "       updated_date = NOW() "
        " WHERE id = :id"
    ), {
        'id': file_id,
        'size': size,
        'ts': int(datetime.now(timezone.utc).timestamp()),
    })
    db.commit()

    return {'id': file_id, 'status': 'uploaded', 'fileSize': size}


# ── Update / delete ────────────────────────────────────────────────────

def update_document(db, device_id: int, file_id: int, data: dict,
                    current_user: dict = None) -> Dict[str, Any]:
    """Re-file a document under a different category, or fix its note.

    Nothing about the stored object changes — a mis-categorised certificate
    should not have to be deleted and re-uploaded to be corrected.
    """
    _device_org(db, device_id)

    row = db.execute(_t(
        "SELECT metadata FROM files "
        " WHERE id = :id AND related_entity_type = 'iot_device' "
        "   AND related_entity_id = :device_id AND file_type = 'document' "
        "   AND is_active = TRUE"
    ), {'id': file_id, 'device_id': device_id}).fetchone()
    if row is None:
        raise NotFoundException(
            f'Document {file_id} not found on device {device_id}')

    patch: Dict[str, Any] = {}
    if 'category' in data:
        patch['category'] = _normalize_category(data.get('category'))
    if 'note' in data:
        note = data.get('note')
        patch['note'] = note.strip()[:500] if isinstance(note, str) and note.strip() else None
    if not patch:
        raise BadRequestException('Nothing to update: send category and/or note')

    db.execute(_t(
        "UPDATE files "
        "   SET metadata = COALESCE(metadata, '{}'::jsonb) || CAST(:patch AS jsonb), "
        "       updated_date = NOW() "
        " WHERE id = :id"
    ), {'id': file_id, 'patch': _json_dumps(patch)})
    db.commit()

    return {'id': file_id, **patch}


def delete_document(db, device_id: int, file_id: int,
                    current_user: dict = None) -> Dict[str, Any]:
    """Remove a document from the device and from S3.

    The row is soft-deleted first and the S3 object second: if the object
    delete fails, the document is already gone from the tab, which is what the
    admin asked for. The reverse order can leave a row pointing at an object
    that no longer exists — a broken thumbnail nobody can clear.
    """
    _device_org(db, device_id)

    row = db.execute(_t(
        "SELECT s3_key, s3_bucket, source FROM files "
        " WHERE id = :id AND related_entity_type = 'iot_device' "
        "   AND related_entity_id = :device_id AND file_type = 'document' "
        "   AND is_active = TRUE"
    ), {'id': file_id, 'device_id': device_id}).fetchone()

    if row is None:
        # Already gone. Deleting twice is what happens when someone
        # double-clicks, and it is not an error worth showing them.
        return {'id': file_id, 'deleted': True, 'alreadyGone': True}

    s3_key, s3_bucket, source = row[0], row[1], row[2]

    db.execute(_t(
        "UPDATE files "
        "   SET is_active = FALSE, status = 'deleted', "
        "       deleted_date = NOW(), updated_date = NOW() "
        " WHERE id = :id"
    ), {'id': file_id})
    db.commit()

    s3_deleted = False
    if source == 's3' and s3_key:
        try:
            import os
            import boto3
            from botocore.config import Config as BotoConfig
            bucket = s3_bucket or os.getenv('S3_BUCKET_NAME',
                                            'prod-gepp-platform-assets')
            boto3.client('s3', config=BotoConfig(signature_version='s3v4')
                         ).delete_object(Bucket=bucket, Key=s3_key)
            s3_deleted = True
        except Exception:
            # Storage keeps paying for the object, but the record is correct
            # and the admin is not blocked. Logged loudly for cleanup.
            logger.warning('Could not delete s3://%s/%s for document %s',
                           s3_bucket, s3_key, file_id, exc_info=True)

    return {'id': file_id, 'deleted': True, 's3Deleted': s3_deleted}
