"""Deleting an uploaded-but-unsaved attachment.

Attachments reach S3 the moment the user picks them, before the transaction is
saved. Un-picking one therefore has to undo that — otherwise the object stays in
the bucket forever, paid for and referenced by nothing, AND keeps counting
toward the transaction's total-size limit on the next attempt.

The one case that must NOT delete: a file a saved transaction still points at.
Removing an attachment in the UI is not the same act as saving that removal, so
deleting the bytes at click time would leave a live transaction pointing at a
missing object if the user then cancels.
"""

import pytest

from GEPPPlatform.services.cores.transactions.transaction_handlers import (
    handle_delete_transaction_file,
)

# Taken from the handler's OWN namespace, not imported from
# `GEPPPlatform.libs.exceptions` directly. Under the full suite that module ends
# up in sys.modules twice — same `__module__` string, different class objects —
# so `pytest.raises(BadRequestException)` failed to catch an exception the
# traceback showed being raised. This is the same import pollution behind the
# 26 pre-existing suite failures; referencing the class the handler will
# actually raise sidesteps it without weakening the assertion.
# (exceptions are asserted by class name — see TestGuards for why)


class FakeFile:
    def __init__(self, fid=1, org=7, key='k/a.webp', bucket='b'):
        self.id = fid
        self.organization_id = org
        self.s3_key = key
        self.s3_bucket = bucket
        self.original_filename = 'a.webp'
        self.deleted_date = None
        self.is_active = True


class FakeSession:
    """Query chain for the File lookup + a scalar for the reference check."""

    def __init__(self, record, referenced=False):
        self._record = record
        self._referenced = referenced
        self.committed = False

    # File lookup
    def query(self, _model):
        return self

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return self._record

    # reference check goes through execute(...).scalar()
    def execute(self, *_a, **_k):
        outer = self

        class R:
            def scalar(self_inner):
                return outer._referenced

        return R()

    def commit(self):
        self.committed = True


@pytest.fixture(autouse=True)
def _no_real_s3(monkeypatch):
    """Never touch S3 from a unit test; record whether a delete was attempted."""
    calls = []

    class FakeS3Service:
        def __init__(self):
            self.bucket_name = 'default-bucket'

        def delete_file(self, key):
            calls.append((self.bucket_name, key))
            return True

    monkeypatch.setattr(
        'GEPPPlatform.services.file_upload_service.S3FileUploadService',
        FakeS3Service)
    return calls


class TestDeleteUnreferencedFile:
    def test_deletes_object_and_row(self, _no_real_s3):
        f = FakeFile()
        db = FakeSession(f, referenced=False)
        r = handle_delete_transaction_file(f.id, 7, db)

        assert (r['success'], r['deleted'], r['s3Deleted']) == (True, True, True)
        assert f.deleted_date is not None and f.is_active is False
        assert db.committed

    def test_deletes_from_the_bucket_the_object_was_written_to(self, _no_real_s3):
        # Not today's default bucket: a bucket rename would otherwise orphan
        # every older object instead of deleting it.
        f = FakeFile(bucket='old-bucket-2024')
        handle_delete_transaction_file(f.id, 7, FakeSession(f))
        assert _no_real_s3 == [('old-bucket-2024', 'k/a.webp')]

    def test_row_is_removed_even_if_s3_fails(self, monkeypatch):
        # A stale row pointing at an object that may not exist is worse than no
        # row: it keeps counting toward the size limit and the user can never
        # clear it.
        class BrokenS3:
            def __init__(self):
                self.bucket_name = 'b'

            def delete_file(self, key):
                raise RuntimeError('S3 down')

        monkeypatch.setattr(
            'GEPPPlatform.services.file_upload_service.S3FileUploadService',
            BrokenS3)
        f = FakeFile()
        r = handle_delete_transaction_file(f.id, 7, FakeSession(f))
        assert r['deleted'] is True and r['s3Deleted'] is False
        assert f.deleted_date is not None

    def test_no_s3_key_still_removes_the_row(self, _no_real_s3):
        f = FakeFile(key=None)
        r = handle_delete_transaction_file(f.id, 7, FakeSession(f))
        assert r['deleted'] is True
        assert _no_real_s3 == []


class TestReferencedFileIsProtected:
    def test_not_deleted_and_reported_as_detached(self, _no_real_s3):
        f = FakeFile()
        db = FakeSession(f, referenced=True)
        r = handle_delete_transaction_file(f.id, 7, db)

        assert (r['success'], r['deleted'], r['detached']) == (True, False, True)
        # The bytes and the row both survive — the user may cancel the edit.
        assert f.deleted_date is None
        assert _no_real_s3 == []
        assert not db.committed


class TestGuards:
    def test_other_organization_is_refused(self):
        f = FakeFile(org=7)
        with pytest.raises(Exception) as ei:      # see the note below on identity
            handle_delete_transaction_file(f.id, 999, FakeSession(f))
        assert type(ei.value).__name__ == 'UnauthorizedException'
        assert 'different organization' in str(ei.value)

    def test_missing_file_is_idempotent_not_an_error(self):
        # A double-click, or a retry after success, must not surface an error.
        r = handle_delete_transaction_file(123, 7, FakeSession(None))
        assert (r['success'], r['deleted']) == (True, False)

    @pytest.mark.parametrize('bad', ['abc', '', 'files/12', None])
    def test_non_numeric_id_is_a_bad_request(self, bad):
        # Matched on the class NAME rather than with `pytest.raises(Class)`.
        #
        # `GEPPPlatform.exceptions` is a `from ... import *` shim over
        # `GEPPPlatform.libs.exceptions`, and under full-suite collection the two
        # end up holding DIFFERENT class objects for the same name (verified:
        # differing id() for BadRequestException). An isinstance-based assertion
        # then fails on an exception the traceback plainly shows being raised.
        # That shim duplication is the pre-existing pollution behind the other
        # long-standing suite failures and is not this feature's to fix.
        with pytest.raises(Exception) as ei:
            handle_delete_transaction_file(bad, 7, FakeSession(FakeFile()))
        assert type(ei.value).__name__ == 'BadRequestException'
        assert 'Invalid file id' in str(ei.value)

    def test_numeric_string_id_is_accepted(self, _no_real_s3):
        # The route parses the id out of the path, so it arrives as a string.
        f = FakeFile(fid=42)
        r = handle_delete_transaction_file('42', 7, FakeSession(f))
        assert r['fileId'] == 42 and r['deleted'] is True
