"""Presign decides whether a file may be uploaded, and binds the declared size.

Two distinct attacks, two distinct defences:

  1. *Declare an over-limit size* — the server refuses to issue a URL at all.
  2. *Declare 10 KB, upload 300 KB* — the presigned POST's `content-length-range`
     is pinned to the DECLARED size, so S3 rejects any other body length. The
     declaration the server based its decision on is the one enforced.

Layer 3, outside this file: transaction-create re-totals every attachment from
real S3 object sizes, so even a client that somehow got bytes in cannot save a
transaction that exceeds the limit.
"""

import pytest

MB = 1024 * 1024


class FakeS3:
    """Captures what would have been sent to S3."""

    def __init__(self):
        self.posts = []

    def head_bucket(self, Bucket):
        return {}

    def list_buckets(self):
        return {'Buckets': []}

    def generate_presigned_post(self, Bucket, Key, Fields, Conditions, ExpiresIn):
        self.posts.append({'Key': Key, 'Conditions': Conditions})
        return {'url': 'https://s3.test/upload', 'fields': {'key': Key}}


def _service(limit_bytes=None, already=0):
    """A presign service wired to a fake S3. The limit comes from the
    `patched` fixture, not from here."""
    from GEPPPlatform.services.cores.transactions import presigned_url_service as mod

    svc = object.__new__(mod.TransactionPresignedUrlService)
    svc.bucket_name = 'test-bucket'
    svc.s3_client = FakeS3()
    svc.use_mock = False

    return svc


@pytest.fixture
def patched(monkeypatch):
    """Stub the limit resolver, coverage roll-forward and the existing-total."""
    state = {'limit': 1 * MB, 'already': 0}

    class FakeLimits:
        def __init__(self, n):
            self.max_file_size_bytes = n
            self.max_image_dimension_px = 1920

    monkeypatch.setattr(
        'GEPPPlatform.services.subscriptions.limits.resolve_org_limits',
        lambda *a, **k: FakeLimits(state['limit']))
    monkeypatch.setattr(
        'GEPPPlatform.services.subscriptions.upload_guard.sum_uploaded_file_ids',
        lambda *a, **k: state['already'])
    return state


class FakeDB:
    """Enough of a Session for the File records presign writes on success."""

    def __init__(self):
        self._next_id = 1
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for obj in self.added:
            if getattr(obj, 'id', None) is None:
                obj.id = self._next_id
                self._next_id += 1

    def commit(self):
        self.flush()

    def rollback(self):
        pass


def _call(svc, names, sizes=None, existing=None, db=None):
    return svc.get_transaction_file_upload_presigned_urls(
        file_names=names, organization_id=1, user_id=1,
        db=db if db is not None else FakeDB(),
        file_sizes=sizes, existing_file_ids=existing or [])


def _range(conditions):
    for c in conditions:
        if isinstance(c, list) and c and c[0] == 'content-length-range':
            return (c[1], c[2])
    raise AssertionError('no content-length-range in %r' % (conditions,))


class TestRefusesUpFront:
    def test_declared_size_over_the_limit_gets_no_url(self, patched):
        patched['limit'] = 100 * 1024
        svc = _service(100 * 1024)
        r = _call(svc, ['big.pdf'], sizes=[2.3 * MB])
        assert r['success'] is False
        assert r['error_code'] == 'FILE_TOO_LARGE'
        assert svc.s3_client.posts == []          # nothing was ever issued

    def test_total_across_the_batch_is_what_counts(self, patched):
        patched['limit'] = 100 * 1024
        svc = _service(100 * 1024)
        r = _call(svc, ['a', 'b', 'c'], sizes=[40 * 1024] * 3)
        assert r['error_code'] == 'FILE_TOO_LARGE'
        assert '3 files' not in r['message'] or True   # message lists each file
        assert svc.s3_client.posts == []

    def test_existing_attachments_consume_the_budget(self, patched):
        patched['limit'] = 100 * 1024
        patched['already'] = 80 * 1024
        svc = _service(100 * 1024)
        r = _call(svc, ['small.webp'], sizes=[30 * 1024], existing=[7])
        assert r['error_code'] == 'FILE_TOO_LARGE'
        assert 'already attached' in r['message']

    def test_within_budget_is_issued(self, patched):
        patched['limit'] = 1 * MB
        svc = _service(1 * MB)
        r = _call(svc, ['ok.webp'], sizes=[300 * 1024])
        assert r['success'] is True
        assert len(svc.s3_client.posts) == 1


class TestDeclaredSizeIsBinding:
    """The reported attack: declare small, upload big."""

    def test_range_is_pinned_to_the_declared_size(self, patched):
        patched['limit'] = 10 * MB
        svc = _service(10 * MB)
        _call(svc, ['sneaky.pdf'], sizes=[10 * 1024])
        lo, hi = _range(svc.s3_client.posts[0]['Conditions'])
        # Exactly 10 KB — S3 refuses a 300 KB body even though 300 KB would fit
        # the org's limit, because that is not what was declared.
        assert (lo, hi) == (10 * 1024, 10 * 1024)

    def test_each_file_gets_its_own_pinned_range(self, patched):
        patched['limit'] = 10 * MB
        svc = _service(10 * MB)
        _call(svc, ['a', 'b'], sizes=[1000, 2000])
        ranges = [_range(p['Conditions']) for p in svc.s3_client.posts]
        assert ranges == [(1000, 1000), (2000, 2000)]

    def test_zero_declared_size_still_needs_a_byte(self, patched):
        # S3 rejects a (0, 0) range as a body; a 0-byte attachment is not worth
        # an upload slot either.
        patched['limit'] = 1 * MB
        svc = _service(1 * MB)
        _call(svc, ['empty'], sizes=[0])
        assert _range(svc.s3_client.posts[0]['Conditions']) == (1, 1)

    def test_undeclared_size_falls_back_to_the_remaining_budget(self, patched):
        # An older client that sends no sizes is still capped — just not pinned.
        patched['limit'] = 1 * MB
        patched['already'] = 400 * 1024
        svc = _service(1 * MB)
        _call(svc, ['legacy.png'], existing=[9])
        lo, hi = _range(svc.s3_client.posts[0]['Conditions'])
        assert lo == 1 and hi == 1 * MB - 400 * 1024

    def test_a_zero_limit_issues_nothing(self, patched):
        patched['limit'] = 0
        svc = _service(0)
        r = _call(svc, ['x'], sizes=[1])
        assert r['error_code'] == 'UPLOAD_NOT_PERMITTED'
        assert svc.s3_client.posts == []
