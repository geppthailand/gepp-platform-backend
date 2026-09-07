"""The per-file size guard for byte-carrying upload paths.

Three server-side paths accept transaction file bytes and none of them had a
ceiling before: `POST /transactions/{id}/images`, `file_uploads` on create, and
the QR channel's `b64image`. They now share `upload_guard`.

The dangerous failure here is measuring the WRONG size — base64 inflates by
~33%, so a check on the encoded string rejects files that are within the limit,
and a check on a decoded blob that was never encoded under-counts. Those cases
come first.
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

    def test_raises_when_over(self):
        files = [{'data': data_url(6 * MB), 'filename': 'big.webp'}]
        with pytest.raises(FileTooLargeError) as ei:
            check_files(files, 5 * MB)
        assert 'big.webp' in str(ei.value)
        assert '6.0 MB' in str(ei.value)
        assert '5.0 MB' in str(ei.value)

    def test_reports_EVERY_offender_not_just_the_first(self):
        # So the user fixes one upload instead of rediscovering the limit file
        # by file.
        files = [
            {'data': data_url(1 * MB), 'filename': 'ok.webp'},
            {'data': data_url(6 * MB), 'filename': 'big1.webp'},
            {'data': data_url(7 * MB), 'filename': 'big2.webp'},
        ]
        with pytest.raises(FileTooLargeError) as ei:
            check_files(files, 5 * MB)
        assert {o['filename'] for o in ei.value.offenders} == {'big1.webp', 'big2.webp'}
        assert 'ok.webp' not in str(ei.value)

    def test_exactly_at_the_limit_is_allowed(self):
        check_files([{'data': b'x' * (5 * MB), 'filename': 'edge'}], 5 * MB)

    def test_one_byte_over_is_refused(self):
        with pytest.raises(FileTooLargeError):
            check_files([{'data': b'x' * (5 * MB + 1), 'filename': 'edge'}], 5 * MB)

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

    def test_total_is_reported_not_enforced(self):
        # Three 4 MB files pass a 5 MB PER-FILE limit even though they total
        # 12 MB. `max_file_size_mb` is documented as per-file; capping the total
        # here would enforce a limit nobody configured a value for.
        files = [{'data': b'x' * (4 * MB), 'filename': f'f{i}'} for i in range(3)]
        measured = check_files(files, 5 * MB)          # must not raise
        assert transaction_total_bytes(measured) == 12 * MB
