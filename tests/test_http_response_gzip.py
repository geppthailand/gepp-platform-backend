"""Compressing the Lambda proxy response.

AWS returns nothing at all past a 6 MB synchronous response — not a truncated page,
an error — so the board hitting that ceiling means a blank screen. Every guard here
exists because getting one wrong breaks a working endpoint to save bytes on a big
one, which is a bad trade.
"""

import base64
import gzip
import json

import pytest

from GEPPPlatform.libs.http_response import maybe_gzip

GZIP_EVENT = {"headers": {"accept-encoding": "gzip, deflate, br"}}


def _big_json(cards=200):
    """Shaped like the board: the same origin and material repeated on every card."""
    origin = {"id": 1, "name_th": "ร้านกาแฟ ชั้น 1", "path": "อาคาร A, ชั้น 1"}
    material = {"id": 42, "name_th": "กระดาษ", "unit_name_th": "กิโลกรัม"}
    return json.dumps({"data": [{"id": i, "weight": 100.0, "origin": origin,
                                 "material": material} for i in range(cards)]})


def _response(body, **extra):
    return {"statusCode": 200, "headers": {"Content-Type": "application/json"},
            "body": body, **extra}


def test_a_large_body_is_compressed_and_survives_the_round_trip():
    original = _big_json()
    out = maybe_gzip(_response(original), GZIP_EVENT)

    assert out["isBase64Encoded"] is True
    assert out["headers"]["Content-Encoding"] == "gzip"
    restored = gzip.decompress(base64.b64decode(out["body"])).decode("utf-8")
    assert restored == original, 'the client would receive different bytes'


def test_thai_text_survives_exactly():
    """Encoding is where this would corrupt data silently rather than fail loudly."""
    original = json.dumps({"name": "ห้องขยะ อาคาร A", "note": "คัดแยกแล้ว" * 200},
                          ensure_ascii=False)
    out = maybe_gzip(_response(original), GZIP_EVENT)
    assert gzip.decompress(base64.b64decode(out["body"])).decode("utf-8") == original


def test_it_actually_shrinks_a_board_sized_payload():
    original = _big_json(900)
    out = maybe_gzip(_response(original), GZIP_EVENT)
    assert len(out["body"]) < len(original) / 5


def test_existing_headers_and_status_are_preserved():
    out = maybe_gzip(
        {"statusCode": 201, "headers": {"Content-Type": "application/json",
                                        "X-App-Version": "1.2.3"},
         "body": _big_json()},
        GZIP_EVENT,
    )
    assert out["statusCode"] == 201
    assert out["headers"]["X-App-Version"] == "1.2.3"
    assert out["headers"]["Content-Type"] == "application/json"


def test_the_original_response_is_not_mutated():
    """The caller may still hold it; a shared dict edited in place is a nasty bug."""
    response = _response(_big_json())
    before = dict(response)
    maybe_gzip(response, GZIP_EVENT)
    assert response == before


# ── the guards ────────────────────────────────────────────────────────────

def test_a_client_that_did_not_offer_gzip_gets_plain_json():
    response = _response(_big_json())
    assert maybe_gzip(response, {"headers": {}}) == response


def test_a_small_body_is_left_alone():
    """gzip's header plus base64 would make it bigger."""
    response = _response(json.dumps({"success": True}))
    assert maybe_gzip(response, GZIP_EVENT) == response


def test_a_pdf_download_is_left_alone():
    """It is already base64; compressing it again would corrupt the file."""
    response = _response("JVBERi0xLjQK" * 500, isBase64Encoded=True)
    assert maybe_gzip(response, GZIP_EVENT) == response


@pytest.mark.parametrize('body', [None, 123, {"already": "a dict"}, b"bytes"])
def test_a_non_string_body_is_left_alone(body):
    response = _response(body)
    assert maybe_gzip(response, GZIP_EVENT) == response


@pytest.mark.parametrize('event', [{}, {"headers": None}, {"headers": {}}])
def test_a_request_without_usable_headers_is_left_alone(event):
    response = _response(_big_json())
    assert maybe_gzip(response, event) == response


def test_header_casing_from_the_gateway_is_handled():
    out = maybe_gzip(_response(_big_json()), {"headers": {"Accept-Encoding": "gzip"}})
    assert out["isBase64Encoded"] is True


def test_incompressible_content_is_left_alone():
    """Random bytes grow under gzip+base64; shipping the bigger one would be absurd."""
    import os
    response = _response(base64.b64encode(os.urandom(4000)).decode())
    assert maybe_gzip(response, GZIP_EVENT) == response


def test_an_unexpected_response_shape_never_raises():
    """This runs on the way out of every request — it must not be able to 500."""
    assert maybe_gzip({}, GZIP_EVENT) == {}
