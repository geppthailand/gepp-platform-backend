"""The attachment-size guard. The limit is a TOTAL, per transaction.

Not per file: three 40 KB photos against a 100 KB limit is a refusal even
though no single file is over. A per-file rule would let an unbounded number of
just-under-the-limit files through, which is the opposite of a storage limit.

Two failure modes drive these tests:

  * measuring the WRONG size — base64 inflates ~33%, so a check on the encoded
    string refuses files that fit, while a decoded measurement of something that
    was never encoded under-counts;
  * checking the wrong QUANTITY — the bug that shipped: a 2.3 MB PDF against a
    0.1 MB limit was let through and the transaction was created anyway.
"""

import base64

import pytest

from GEPPPlatform.services.subscriptions.upload_guard import (
    FileTooLargeError,
    check_b64_images,
    check_files,
    payload_size_bytes,
    transaction_total_bytes,
)

MB = 1024 * 1024


def b64_of(n_bytes: int) -> str:
    return base64.b64encode(b'x' * n_bytes).decode()


def data_url(n_bytes: int, mime: str = 'image/webp') -> str:
    return f'data:{mime};base64,{b64_of(n_bytes)}'


class TestPayloadSize:
    def test_raw_bytes(self):
        assert payload_size_bytes(b'x' * 1234) == 1234

    def test_bytearray_and_memoryview(self):
        assert payload_size_bytes(bytearray(b'x' * 10)) == 10
        assert payload_size_bytes(memoryview(b'x' * 10)) == 10

    def test_data_url_measures_the_DECODED_size(self):
        # The whole point: a 3 MB image arrives as ~4 MB of base64 text. Judging
        # it on the string would refuse a file that fits.
        url = data_url(3 * MB)
        assert len(url) > 4 * MB              # the encoded form really is bigger
        assert payload_size_bytes(url) == 3 * MB

    def test_data_url_with_odd_mime_and_casing(self):
        assert payload_size_bytes(f'DATA:image/PNG;BASE64,{b64_of(500)}') == 500

    def test_bare_base64_also_measures_decoded(self):
        # JSON cannot carry raw bytes, so a string payload on these endpoints is
        # essentially always encoded. Measuring the text would report a 2 MB
        # photo as 2.7 MB — and would disagree with the QR path, which decodes.
        raw = b'x' * (2 * MB)
        assert payload_size_bytes(base64.b64encode(raw).decode()) == 2 * MB

    def test_plain_text_measures_stored_bytes(self):
        # Not valid base64 (wrong length / charset) -> stored verbatim, so its
        # own UTF-8 length is the object size.
        assert payload_size_bytes('hello') == 5
        assert payload_size_bytes('hello world, this is a note.') == 28

    def test_plain_string_counts_utf8_not_characters(self):
        # Thai text is ~3 bytes/char; counting characters would under-measure.
        assert payload_size_bytes('สวัสดี') == len('สวัสดี'.encode('utf-8'))

    def test_the_two_string_forms_agree(self):
        # Same file, with and without the data-URL wrapper, must measure equal —
        # otherwise the web path and the QR path disagree about one photo.
        raw = b'y' * 4096
        bare = base64.b64encode(raw).decode()
        assert payload_size_bytes(bare) == payload_size_bytes(
            f'data:image/webp;base64,{bare}') == 4096

    def test_undecodable_base64_falls_back_to_encoded_length(self):
        # Over-estimating is the safe direction for a guard: it can reject
        # something borderline, but never lets an oversized file through.
        bad = 'data:image/png;base64,!!!not-base64!!!'
        assert payload_size_bytes(bad) > 0

    def test_none_and_wrong_types_are_zero(self):
        assert payload_size_bytes(None) == 0
        assert payload_size_bytes(12345) == 0
        assert payload_size_bytes({'a': 1}) == 0


class TestCheckFiles:
    def test_passes_when_within_limit(self):
        files = [{'data': data_url(1 * MB), 'filename': 'a.webp'}]
        measured = check_files(files, 5 * MB)
        assert measured[0]['size_bytes'] == 1 * MB

    def test_raises_when_a_single_file_is_over(self):
        files = [{'data': data_url(6 * MB), 'filename': 'big.webp'}]
        with pytest.raises(FileTooLargeError) as ei:
            check_files(files, 5 * MB)
        assert 'big.webp' in str(ei.value)
        assert '6.00 MB' in str(ei.value)
        assert '5.00 MB' in str(ei.value)

    def test_the_TOTAL_is_what_counts(self):
        # The case the shipped bug got wrong. Every file is comfortably under
        # the limit; together they are not.
        files = [{'data': data_url(40 * 1024), 'filename': f'p{i}.webp'}
                 for i in range(3)]
        with pytest.raises(FileTooLargeError) as ei:
            check_files(files, 100 * 1024)
        assert ei.value.total_bytes == 120 * 1024
        # The message has to show the breakdown, or "too large" is unactionable
        # when no individual file looks too large.
        assert 'p0.webp' in str(ei.value) and 'p2.webp' in str(ei.value)
        assert '3 files total' in str(ei.value)

    def test_reports_every_file_not_just_the_big_ones(self):
        # With a total limit, a small file is still part of the reason it failed.
        files = [
            {'data': data_url(1 * MB), 'filename': 'small.webp'},
            {'data': data_url(6 * MB), 'filename': 'big.webp'},
        ]
        with pytest.raises(FileTooLargeError) as ei:
            check_files(files, 5 * MB)
        assert {f['filename'] for f in ei.value.files} == {'small.webp', 'big.webp'}

    def test_a_0_1_mb_limit_is_not_rounded_to_zero_in_the_message(self):
        # The reported case used 0.1 MB. Formatting at one decimal would print
        # the limit and a 0.05 MB file as the same number.
        with pytest.raises(FileTooLargeError) as ei:
            check_files([{'data': b'x' * (300 * 1024), 'filename': 'doc.pdf'}],
                        int(0.1 * MB))
        assert '0.10 MB' in str(ei.value)
        assert '0.29 MB' in str(ei.value)

    def test_exactly_at_the_limit_is_allowed(self):
        check_files([{'data': b'x' * (5 * MB), 'filename': 'edge'}], 5 * MB)

    def test_one_byte_over_the_total_is_refused(self):
        with pytest.raises(FileTooLargeError):
            check_files([{'data': b'x' * (3 * MB), 'filename': 'a'},
                         {'data': b'x' * (2 * MB + 1), 'filename': 'b'}], 5 * MB)

    def test_none_limit_skips_the_check(self):
        # None = "could not resolve the limit". A lookup failure must not block
        # uploads.
        measured = check_files([{'data': b'x' * (999 * MB), 'filename': 'huge'}], None)
        assert measured[0]['size_bytes'] == 999 * MB

    def test_zero_limit_rejects_everything(self):
        # 0 is a real, deliberate value — "no uploads allowed" — and must NOT be
        # treated like None. This is the case a falsy check would get wrong.
        with pytest.raises(FileTooLargeError):
            check_files([{'data': b'x', 'filename': 'tiny'}], 0)

    def test_zero_limit_with_no_files_is_fine(self):
        assert check_files([], 0) == []

    def test_missing_filename_gets_a_positional_label(self):
        with pytest.raises(FileTooLargeError) as ei:
            check_files([{'data': b'x' * (2 * MB)}], MB)
        assert 'file 1' in str(ei.value)

    def test_non_dict_entries_are_skipped_not_crashed(self):
        assert check_files(['garbage', None, 42], MB) == []

    def test_empty_and_none_input(self):
        assert check_files([], MB) == []
        assert check_files(None, MB) == []

    def test_subclasses_ValueError(self):
        # The QR channel's existing `except ValueError` turns this into a clean
        # FILE_TOO_LARGE response; that must keep working.
        assert issubclass(FileTooLargeError, ValueError)


class TestCheckB64Images:
    def test_qr_shape_is_a_bare_list_of_strings(self):
        with pytest.raises(FileTooLargeError) as ei:
            check_b64_images([data_url(1 * MB), data_url(9 * MB)], 5 * MB)
        assert 'Photo 2' in str(ei.value)

    def test_qr_photos_are_totalled_too(self):
        with pytest.raises(FileTooLargeError) as ei:
            check_b64_images([data_url(40 * 1024)] * 3, 100 * 1024)
        assert ei.value.total_bytes == 120 * 1024

    def test_within_limit(self):
        measured = check_b64_images([data_url(MB)], 5 * MB)
        assert measured[0]['size_bytes'] == MB

    def test_bare_base64_without_data_url_prefix(self):
        # MobileInput sends `data:` URLs, but a raw base64 body should still be
        # measured, not silently zero.
        assert check_b64_images([b64_of(100)], None)[0]['size_bytes'] > 0


class TestTransactionTotal:
    def test_sums_the_measured_files(self):
        measured = check_files(
            [{'data': b'x' * MB, 'filename': 'a'},
             {'data': b'x' * (2 * MB), 'filename': 'b'}],
            10 * MB)
        assert transaction_total_bytes(measured) == 3 * MB

    def test_the_total_is_enforced(self):
        # Three 4 MB files against a 5 MB limit: each fits, the transaction does
        # not. This assertion used to say the opposite — it encoded the per-file
        # reading of the rule, which was wrong.
        files = [{'data': b'x' * (4 * MB), 'filename': f'f{i}'} for i in range(3)]
        with pytest.raises(FileTooLargeError) as ei:
            check_files(files, 5 * MB)
        assert ei.value.total_bytes == 12 * MB
        assert transaction_total_bytes(ei.value.files) == 12 * MB


class TestCollectFileIds:
    """Attachments live in two places on a transaction and the limit covers the
    transaction, so both have to be gathered before anything is measured."""

    def test_gathers_transaction_and_record_ids(self):
        from GEPPPlatform.services.subscriptions.upload_guard import collect_file_ids
        assert collect_file_ids([1, 2], [3], [4, 5]) == [1, 2, 3, 4, 5]

    def test_deduplicates(self):
        # The same file referenced by the transaction AND one of its records is
        # one object in S3 and must be counted once.
        from GEPPPlatform.services.subscriptions.upload_guard import collect_file_ids
        assert collect_file_ids([1, 2], [2, 3]) == [1, 2, 3]

    def test_skips_legacy_urls(self):
        # Old rows keep S3 URLs in the same field; there is no id to size those
        # by, so they are ignored rather than crashing the check.
        from GEPPPlatform.services.subscriptions.upload_guard import collect_file_ids
        assert collect_file_ids(
            [1, 'https://bucket.s3.amazonaws.com/a.jpg', 2]) == [1, 2]

    def test_accepts_numeric_strings(self):
        from GEPPPlatform.services.subscriptions.upload_guard import collect_file_ids
        assert collect_file_ids(['7', 8]) == [7, 8]

    def test_ignores_booleans(self):
        # bool is an int subclass in Python; True would otherwise become id 1.
        from GEPPPlatform.services.subscriptions.upload_guard import collect_file_ids
        assert collect_file_ids([True, False, 5]) == [5]

    def test_tolerates_none_and_non_lists(self):
        from GEPPPlatform.services.subscriptions.upload_guard import collect_file_ids
        assert collect_file_ids(None, 'nope', 42, [9]) == [9]

    def test_no_sources(self):
        from GEPPPlatform.services.subscriptions.upload_guard import collect_file_ids
        assert collect_file_ids() == []


class TestCheckUploadedFileIds:
    """The web path's real enforcement: files are already in S3 when the
    transaction is created, so their sizes come from S3, not from the client."""

    class _File:
        def __init__(self, fid, size=None, key=None, name=None):
            self.id = fid
            self.file_size = size
            self.s3_key = key
            self.s3_bucket = 'b'
            self.original_filename = name or f'f{fid}'

    class _DB:
        def __init__(self, rows):
            self._rows = rows

        def query(self, _m):
            return self

        def filter(self, *_a, **_k):
            return self

        def all(self):
            return self._rows

    def _check(self, rows, max_bytes, head=None):
        from GEPPPlatform.services.subscriptions.upload_guard import (
            check_uploaded_file_ids,
        )

        class FakeS3:
            def head_object(self, Bucket, Key):
                if head is None:
                    raise RuntimeError('no S3')
                return {'ContentLength': head[Key]}

        return check_uploaded_file_ids(
            self._DB(rows), [r.id for r in rows], max_bytes, s3_client=FakeS3())

    def test_uses_stored_size_when_present(self):
        rows = [self._File(1, size=30 * 1024), self._File(2, size=40 * 1024)]
        assert self._check(rows, 100 * 1024) == 70 * 1024

    def test_totals_across_files_and_refuses(self):
        rows = [self._File(i, size=40 * 1024) for i in (1, 2, 3)]
        with pytest.raises(FileTooLargeError) as ei:
            self._check(rows, 100 * 1024)
        assert ei.value.total_bytes == 120 * 1024

    def test_falls_back_to_s3_head_when_size_is_null(self):
        # The real situation: `mark_uploaded` has no callers, so file_size is
        # always NULL for presigned uploads and S3 is the only source of truth.
        rows = [self._File(1, size=None, key='k1'),
                self._File(2, size=None, key='k2')]
        total = self._check(rows, 10 * MB, head={'k1': 2 * MB, 'k2': 1 * MB})
        assert total == 3 * MB

    def test_unreadable_size_counts_as_zero_not_a_block(self):
        # Under-counting is the safe direction: an S3 hiccup must not refuse
        # legitimate work.
        rows = [self._File(1, size=None, key='k1')]
        assert self._check(rows, 1024, head=None) == 0

    def test_none_limit_skips_entirely(self):
        from GEPPPlatform.services.subscriptions.upload_guard import (
            check_uploaded_file_ids,
        )
        rows = [self._File(1, size=999 * MB)]
        assert check_uploaded_file_ids(self._DB(rows), [1], None) == 0

    def test_no_ids_is_zero(self):
        from GEPPPlatform.services.subscriptions.upload_guard import (
            check_uploaded_file_ids,
        )
        assert check_uploaded_file_ids(self._DB([]), [], 1024) == 0

    def test_ids_with_no_matching_rows(self):
        # Stale ids must not fail the transaction.
        assert self._check([], 1024) == 0
