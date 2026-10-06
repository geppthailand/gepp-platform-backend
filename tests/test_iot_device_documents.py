"""Per-device document library (backoffice IoT device → Documents tab).

The interesting cases are not "can it store a file". They are:

  * an upload whose bytes never reached S3 must NOT become a document — the
    only honest source for "did that land?" is S3, never the browser;
  * a document belongs to ONE device, and must not be reachable through
    another device's URL;
  * these uploads are deliberately exempt from the organization's
    per-transaction attachment limit, so a customer on a 0.1 MB plan can still
    have its 3 MB calibration certificate filed;
  * a file type the browser would render (html/svg) must be refused, even on
    an admin-only surface.
"""

import json
from types import SimpleNamespace

import pytest

from GEPPPlatform.services.admin import iot_documents as D

DEVICE_ID = 42
ORG_ID = 7
ADMIN = {'user_id': 99}


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class FakeDB:
    """Answers the handful of statements this module issues, by shape."""

    def __init__(self, org=ORG_ID, device_exists=True, doc_row=None):
        self.org = org
        self.device_exists = device_exists
        self.doc_row = doc_row
        self.executed = []
        self.committed = 0

    def execute(self, statement, params=None):
        sql = ' '.join(str(statement).split())
        self.executed.append((sql, params or {}))

        if 'FROM iot_devices' in sql:
            if not self.device_exists:
                return FakeResult([])
            return FakeResult([(self.org,)])
        if sql.startswith('UPDATE files'):
            return FakeResult([])
        if 'FROM user_locations' in sql:
            return FakeResult([(99, 'GEPP Admin', 'admin@gepp.me')])
        if 'FROM files' in sql:
            return FakeResult([self.doc_row] if self.doc_row else [])
        return FakeResult([])

    def commit(self):
        self.committed += 1


class TestDeviceMustBeAssigned:
    def test_missing_device_is_not_found(self):
        with pytest.raises(Exception) as e:
            D._device_org(FakeDB(device_exists=False), DEVICE_ID)
        assert 'not found' in str(e.value)

    def test_unassigned_device_explains_the_fix(self):
        # files.organization_id is NOT NULL with an FK, so this genuinely
        # cannot work — but an IntegrityError tells the admin nothing.
        with pytest.raises(Exception) as e:
            D._device_org(FakeDB(org=None), DEVICE_ID)
        msg = str(e.value)
        assert 'organization' in msg
        assert 'Assign it to an organization' in msg


class TestFileTypeAllowlist:
    @pytest.mark.parametrize('name', [
        'sticker.jpg', 'photo.webp', 'cert.PDF', 'sheet.xlsx',
        'manual.docx', 'deck.pptx', 'log.csv',
    ])
    def test_accepted(self, name):
        assert D._extension(name) in D.ALLOWED_EXTENSIONS

    @pytest.mark.parametrize('name', [
        'page.html', 'icon.svg', 'run.sh', 'app.exe', 'noext',
    ])
    def test_refused(self, name):
        # svg and html are refused even though this is an admin-only surface:
        # both are rendered by the browser, and "only admins upload here" is
        # not a reason to serve active content from our own origin later.
        db = FakeDB()
        with pytest.raises(Exception) as e:
            D.start_upload(db, DEVICE_ID, {'files': [{'fileName': name}]}, ADMIN)
        assert 'not accepted' in str(e.value)

    def test_nothing_is_written_for_a_refused_type(self):
        # A rejected file must not leave a pending row behind for someone to
        # wonder about later.
        db = FakeDB()
        with pytest.raises(Exception):
            D.start_upload(db, DEVICE_ID, {'files': [{'fileName': 'x.svg'}]}, ADMIN)
        assert not any(s.startswith('UPDATE files') for s, _ in db.executed)
        assert db.committed == 0


class TestUploadGuards:
    def test_empty_payload(self):
        with pytest.raises(Exception, match='files'):
            D.start_upload(FakeDB(), DEVICE_ID, {'files': []}, ADMIN)

    def test_oversized_is_refused_before_a_url_is_issued(self):
        with pytest.raises(Exception) as e:
            D.start_upload(FakeDB(), DEVICE_ID, {'files': [
                {'fileName': 'huge.pdf', 'fileSize': D.MAX_DOCUMENT_BYTES + 1},
            ]}, ADMIN)
        assert '25 MB limit' in str(e.value)

    def test_batch_is_bounded(self):
        with pytest.raises(Exception, match='20 documents'):
            D.start_upload(FakeDB(), DEVICE_ID, {
                'files': [{'fileName': f'f{i}.pdf'} for i in range(21)],
            }, ADMIN)

    def test_an_anonymous_caller_cannot_upload(self):
        # files.uploader_id is NOT NULL; refusing here beats an IntegrityError.
        with pytest.raises(Exception, match='admin user'):
            D.start_upload(FakeDB(), DEVICE_ID,
                           {'files': [{'fileName': 'a.pdf'}]}, {})


class TestNotBoundByTheTransactionLimit:
    """The org's attachment limit is a per-transaction total for customer data
    entry. A calibration certificate is GEPP's service record, billed to
    nobody — an org on a 0.1 MB plan must still be able to have one filed."""

    def test_presign_is_called_with_an_explicit_override(self, monkeypatch):
        captured = {}

        class FakeSvc:
            def get_transaction_file_upload_presigned_urls(self, **kw):
                captured.update(kw)
                return {'success': True, 'presigned_urls': [{
                    'file_id': 1, 'original_filename': 'cert.pdf',
                    'upload_url': 'https://s3', 'upload_fields': {},
                    'content_type': 'application/pdf', 'expires_at': 'x',
                }]}

        import GEPPPlatform.services.cores.transactions.presigned_url_service as mod
        monkeypatch.setattr(mod, 'TransactionPresignedUrlService', FakeSvc)

        D.start_upload(FakeDB(), DEVICE_ID,
                       {'files': [{'fileName': 'cert.pdf', 'fileSize': 3_000_000}],
                        'category': 'calibration'}, ADMIN)

        # The override is what keeps resolve_org_limits out of this path.
        assert captured['max_upload_bytes_override'] == D.MAX_DOCUMENT_BYTES
        assert captured['file_type'] == 'document'
        assert captured['related_entity_type'] == 'iot_device'
        assert captured['related_entity_id'] == DEVICE_ID

    def test_documents_do_not_land_in_the_transactions_folder(self, monkeypatch):
        captured = {}

        class FakeSvc:
            def get_transaction_file_upload_presigned_urls(self, **kw):
                captured.update(kw)
                return {'success': True, 'presigned_urls': []}

        import GEPPPlatform.services.cores.transactions.presigned_url_service as mod
        monkeypatch.setattr(mod, 'TransactionPresignedUrlService', FakeSvc)

        D.start_upload(FakeDB(), DEVICE_ID,
                       {'files': [{'fileName': 'a.pdf'}]}, ADMIN)
        assert captured['key_prefix'] == f'iot-devices/{DEVICE_ID}/documents'
        assert 'transactions' not in captured['key_prefix']


class TestConfirmTrustsS3NotTheBrowser:
    def _db(self):
        return FakeDB(doc_row=(5, 'pending', 'org/7/k.pdf', 'bucket'))

    def test_a_missing_object_marks_the_row_failed(self, monkeypatch):
        import GEPPPlatform.services.subscriptions.upload_guard as guard
        monkeypatch.setattr(guard, '_head_object_size', lambda *a, **k: 0)

        db = self._db()
        with pytest.raises(Exception, match='did not reach storage'):
            D.confirm_upload(db, DEVICE_ID, 5, {}, ADMIN)

        # Visible as failed rather than silently absent — an upload that
        # vanished without trace is retried forever.
        assert any("status = 'failed'" in s for s, _ in db.executed)

    def test_size_comes_from_s3_not_the_request(self, monkeypatch):
        import GEPPPlatform.services.subscriptions.upload_guard as guard
        monkeypatch.setattr(guard, '_head_object_size', lambda *a, **k: 4242)

        db = self._db()
        # The client claims something absurd; it must be ignored entirely.
        res = D.confirm_upload(db, DEVICE_ID, 5, {'fileSize': 999_999_999}, ADMIN)
        assert res['fileSize'] == 4242
        assert res['status'] == 'uploaded'

    def test_confirming_an_unknown_document_is_not_found(self, monkeypatch):
        import GEPPPlatform.services.subscriptions.upload_guard as guard
        monkeypatch.setattr(guard, '_head_object_size', lambda *a, **k: 10)
        with pytest.raises(Exception, match='not found'):
            D.confirm_upload(FakeDB(doc_row=None), DEVICE_ID, 5, {}, ADMIN)


class TestCategories:
    @pytest.mark.parametrize('raw,expect', [
        ('settings_photo', 'settings_photo'),
        ('NAMEPLATE', 'nameplate'),
        ('  calibration  ', 'calibration'),
        ('made_up', 'other'),
        (None, 'other'),
        (123, 'other'),
        ('', 'other'),
    ])
    def test_normalization_never_rejects(self, raw, expect):
        # An unknown category from an older client is filed under 'other'
        # rather than failing the upload — the file matters more than its tag.
        assert D._normalize_category(raw) == expect

    def test_other_is_a_real_category(self):
        assert D.DEFAULT_CATEGORY in D.DOCUMENT_CATEGORIES


class TestPreviewFlags:
    @pytest.mark.parametrize('mime,image,preview', [
        ('image/jpeg', True, True),
        ('image/png', True, True),
        # The business platform compresses every photo to webp, so this is the
        # single most important row here.
        ('image/webp', True, True),
        # An image by MIME type that NO desktop browser paints: an <img> gives
        # a broken-image icon, which reads as "the file is corrupt".
        ('image/heic', False, False),
        ('application/pdf', False, True),
        ('text/csv', False, True),
        ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', False, False),
        (None, False, False),
    ])
    def test_flags(self, mime, image, preview):
        assert D._is_image(mime) is image
        assert D._is_previewable(mime) is preview


class TestDeleteIsIdempotent:
    def test_deleting_a_gone_document_is_not_an_error(self):
        # This is what a double-click produces; it is not worth an error toast.
        res = D.delete_document(FakeDB(doc_row=None), DEVICE_ID, 5, ADMIN)
        assert res['deleted'] is True and res['alreadyGone'] is True

    def test_row_is_soft_deleted_before_s3(self, monkeypatch):
        db = FakeDB(doc_row=('org/7/k.pdf', 'bucket', 'ext'))  # ext = no S3 call
        res = D.delete_document(db, DEVICE_ID, 5, ADMIN)
        assert res['deleted'] is True
        updates = [s for s, _ in db.executed if s.startswith('UPDATE files')]
        assert updates and 'is_active = FALSE' in updates[0]


class TestUpdate:
    def test_nothing_to_update_is_refused(self):
        db = FakeDB(doc_row=({},))
        with pytest.raises(Exception, match='Nothing to update'):
            D.update_document(db, DEVICE_ID, 5, {}, ADMIN)

    def test_blank_note_clears_rather_than_storing_whitespace(self):
        db = FakeDB(doc_row=({},))
        res = D.update_document(db, DEVICE_ID, 5, {'note': '   '}, ADMIN)
        assert res['note'] is None

    def test_note_is_bounded(self):
        db = FakeDB(doc_row=({},))
        res = D.update_document(db, DEVICE_ID, 5, {'note': 'x' * 900}, ADMIN)
        assert len(res['note']) == 500
