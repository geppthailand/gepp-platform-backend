"""PDF rasterization + the index-parallel invariant in the OCR reader.

The invariant is the load-bearing part. The prompt numbers entries by position
and _resolve_indices maps the model's returned index back through kept_urls, so
when one PDF expands into N page images the two lists must grow together --
otherwise a file-slot silently resolves to the WRONG document.
"""

import base64
import io

import pytest
from PIL import Image, ImageDraw

from GEPPPlatform.libs import image_processing as ip
from GEPPPlatform.libs.openrouter import pdf_needs_raster
from GEPPPlatform.services.cores.epr_ai_audit.api import ocr


def make_pdf(n_pages: int) -> bytes:
    """An n-page A4-ish PDF, each page labelled, built with Pillow."""
    pages = []
    for i in range(n_pages):
        im = Image.new("RGB", (1240, 1754), "white")
        ImageDraw.Draw(im).text((80, 80), f"PAGE {i + 1} of {n_pages}", fill="black")
        pages.append(im)
    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", save_all=True, append_images=pages[1:])
    return buf.getvalue()


def make_jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (3000, 200), "blue").save(buf, "JPEG")
    return buf.getvalue()


def dims_of(data_url: str):
    b64 = data_url.split(",", 1)[1]
    return Image.open(io.BytesIO(base64.b64decode(b64))).size


# ── rasterization ──────────────────────────────────────────────────────────

def test_pdf_yields_one_jpeg_per_page():
    urls = ip.pdf_to_jpeg_data_urls(make_pdf(3))
    assert len(urls) == 3
    assert all(u.startswith("data:image/jpeg;base64,") for u in urls)


def test_pages_render_above_the_photo_cap():
    """Documents need more pixels than waste-pile photos, or fine Thai print
    smears. Must beat MAX_SIDE_PX but respect MAX_SIDE_DOC_PX."""
    w, h = dims_of(ip.pdf_to_jpeg_data_urls(make_pdf(1))[0])
    assert max(w, h) > ip.MAX_SIDE_PX
    assert max(w, h) <= ip.MAX_SIDE_DOC_PX


def test_page_cap_drops_the_tail():
    assert len(ip.pdf_to_jpeg_data_urls(make_pdf(12), max_pages=8)) == 8


@pytest.mark.parametrize("model,expected", [
    ("google/gemini-3.5-flash", False),
    ("google/gemini-2.5-flash", False),
    ("moonshotai/kimi-k3", True),
    ("openai/gpt-4.1-mini", True),
    ("anthropic/haiku-4.5", True),
])
def test_pdf_needs_raster(model, expected):
    assert pdf_needs_raster(model) is expected


def test_safe_process_pages_raster_vs_native(monkeypatch):
    pdf = make_pdf(3)
    monkeypatch.setattr(ip, "fetch_image_bytes", lambda u: pdf)
    assert len(ip.safe_process_pages("b.pdf", raster_pdf=True)) == 3
    native = ip.safe_process_pages("b.pdf", raster_pdf=False)
    assert len(native) == 1
    assert native[0].startswith("data:application/pdf")


# ── the index-parallel invariant ───────────────────────────────────────────

@pytest.fixture
def three_files(monkeypatch):
    """a.jpg, b.pdf (3 pages), c.jpg — b expands to 3 entries under raster."""
    fake = {"a.jpg": make_jpeg(), "b.pdf": make_pdf(3), "c.jpg": make_jpeg()}
    monkeypatch.setattr(ip, "fetch_image_bytes", lambda u: fake[u])
    monkeypatch.setattr(ocr, "safe_process_pages", ip.safe_process_pages)
    return ["a.jpg", "b.pdf", "c.jpg"]


def test_raster_expands_and_repeats_source_url(monkeypatch, three_files):
    monkeypatch.setattr(ocr, "pdf_needs_raster", lambda m: True)
    data_urls, kept = ocr._load_data_urls(three_files)
    assert len(data_urls) == len(kept) == 5
    assert kept == ["a.jpg", "b.pdf", "b.pdf", "b.pdf", "c.jpg"]


def test_page_index_resolves_to_its_own_document(monkeypatch, three_files):
    """Index 3 is page 3 of b.pdf. It must NOT resolve to c.jpg."""
    monkeypatch.setattr(ocr, "pdf_needs_raster", lambda m: True)
    _, kept = ocr._load_data_urls(three_files)
    file_fields = [{"name": "doc", "type": "file"}]

    slot = {"doc": 3}
    ocr._resolve_indices(slot, file_fields, kept)
    assert slot["doc"] == "b.pdf"

    slot = {"doc": 4}
    ocr._resolve_indices(slot, file_fields, kept)
    assert slot["doc"] == "c.jpg"


def test_native_path_stays_one_to_one(monkeypatch, three_files):
    monkeypatch.setattr(ocr, "pdf_needs_raster", lambda m: False)
    data_urls, kept = ocr._load_data_urls(three_files)
    assert len(data_urls) == len(kept) == 3
    assert kept == three_files


def test_unprocessable_file_shifts_both_lists(monkeypatch):
    monkeypatch.setattr(ocr, "pdf_needs_raster", lambda m: True)
    monkeypatch.setattr(
        ocr, "safe_process_pages",
        lambda u, raster_pdf=True: None if u == "bad.jpg" else ["data:image/jpeg;base64,x"],
    )
    data_urls, kept = ocr._load_data_urls(["a.jpg", "bad.jpg", "c.jpg"])
    assert len(data_urls) == len(kept) == 2
    assert kept == ["a.jpg", "c.jpg"]


def test_out_of_range_index_resolves_to_none():
    slot = {"doc": 99}
    ocr._resolve_indices(slot, [{"name": "doc", "type": "file"}], ["a.jpg"])
    assert slot["doc"] is None
