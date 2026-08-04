"""_load_data_urls: PDF skip flag + the index-parallel invariant.

The invariant is the load-bearing one — the prompt numbers files by position
and _resolve_indices maps the model's returned index back through kept_urls,
so if the two lists ever drift a file-slot resolves to the WRONG document
with no error raised.
"""

from GEPPPlatform.services.cores.epr_ai_audit.api import ocr

PDF = "data:application/pdf;base64,JVBERi0="
JPG = "data:image/jpeg;base64,/9j/4AA="

FILES = ["a.pdf", "b.jpg", "c.pdf", "d.jpg"]
FAKE = {"a.pdf": PDF, "b.jpg": JPG, "c.pdf": PDF, "d.jpg": JPG}


def _patch(monkeypatch, mapping=FAKE):
    monkeypatch.setattr(ocr, "safe_process_image", lambda url: mapping.get(url))


def test_pdfs_kept_by_default(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.delenv("EPR_OCR_SKIP_PDF", raising=False)
    data_urls, kept_urls = ocr._load_data_urls(FILES)
    assert kept_urls == FILES
    assert len(data_urls) == len(kept_urls)


def test_skip_pdf_drops_only_pdfs(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setenv("EPR_OCR_SKIP_PDF", "1")
    data_urls, kept_urls = ocr._load_data_urls(FILES)
    assert kept_urls == ["b.jpg", "d.jpg"]
    assert data_urls == [JPG, JPG]


def test_lists_stay_parallel_when_files_drop(monkeypatch):
    """A dropped file must shift BOTH lists, so index -> URL stays correct."""
    _patch(monkeypatch, {**FAKE, "b.jpg": None})  # b fails to process
    monkeypatch.delenv("EPR_OCR_SKIP_PDF", raising=False)
    data_urls, kept_urls = ocr._load_data_urls(FILES)

    assert len(data_urls) == len(kept_urls), "index-parallel invariant broken"
    assert kept_urls == ["a.pdf", "c.pdf", "d.jpg"]

    # index 2 came back from the model -> must resolve to d.jpg, not c.pdf
    slot = {"photo": 2}
    ocr._resolve_indices(slot, [{"name": "photo", "type": "file"}], kept_urls)
    assert slot["photo"] == "d.jpg"


def test_out_of_range_index_resolves_to_none(monkeypatch):
    slot = {"photo": 99}
    ocr._resolve_indices(slot, [{"name": "photo", "type": "file"}], ["a.jpg"])
    assert slot["photo"] is None
