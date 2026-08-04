"""
File helpers for the EPR dedup pipeline.

Fetches an image OR a PDF from `image_url` and returns a base64 data URL
ready to feed into the vision LLM (chat-completions) for structured
data extraction.

- Images: decoded, downscaled to MAX_SIDE_PX, re-encoded as JPEG (quality 85)
  to keep request bodies small. JPEG is the right format for LLM input.
- PDFs:   left untouched — the LLM ingests multi-page PDFs natively and
  selectable text is preserved (rasterizing would degrade quality and
  force us to choose a page).

Failures (network, decode, encode) are caught by `safe_process_image` and
surfaced as None — callers log it and store NULL extracted_data, the row
still inserts so the file is tracked.
"""

import base64
import io
import logging
from typing import List, Optional

import requests
from PIL import Image

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECS = 15
MAX_SIDE_PX = 1024  # downscale image long edge before base64-encoding

# Rasterized-PDF path (models without OpenRouter's "file" modality).
# Documents need more pixels than scene photos: MAX_SIDE_PX=1024 is tuned for
# waste-pile snapshots, but a rasterized A4 scale ticket at that size smears
# 8pt Thai digits. 200 DPI ≈ 1654x2339 for A4, capped to 2000px long edge.
PDF_RENDER_DPI = 200
MAX_SIDE_DOC_PX = 2000
MAX_PDF_PAGES = 8  # ceiling on pages per file; see pdf_to_jpeg_data_urls

PDF_MAGIC = b"%PDF"


def fetch_image_bytes(url: str) -> bytes:
    resp = requests.get(url, timeout=FETCH_TIMEOUT_SECS)
    resp.raise_for_status()
    return resp.content


def _is_pdf(raw: bytes) -> bool:
    return raw[:4] == PDF_MAGIC


def to_pdf_data_url(pdf_bytes: bytes) -> str:
    """Wrap raw PDF bytes in a base64 data URL. No rasterization — Gemini
    reads PDFs natively in the chat-completions endpoint (verified empirically)."""
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    return f"data:application/pdf;base64,{b64}"


def _jpeg_data_url(img, max_side: int) -> str:
    """Downscale if needed → JPEG → base64 data URL. Caller owns `img`."""
    img = img.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def to_resized_jpeg_data_url(image_bytes: bytes, max_side: int = MAX_SIDE_PX) -> str:
    """Decode → optionally downscale → re-encode as JPEG → base64 data URL."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        return _jpeg_data_url(img, max_side)


def pdf_to_jpeg_data_urls(
    pdf_bytes: bytes,
    dpi: int = PDF_RENDER_DPI,
    max_pages: int = MAX_PDF_PAGES,
    max_side: int = MAX_SIDE_DOC_PX,
) -> List[str]:
    """Rasterize a PDF to one JPEG data URL per page.

    Only needed for models that lack OpenRouter's "file" input modality
    (kimi-k3, gpt-4.1-mini, haiku-4.5) — those 400 on to_pdf_data_url output.
    Prefer the native path when the model supports it: rasterizing discards the
    PDF text layer, which costs accuracy on the fine Thai print in scale
    tickets and QC certs.

    ponytail: hard page cap rather than splitting into several requests. A
    capped PDF logs a warning and silently loses its tail pages — raise
    MAX_PDF_PAGES or chunk the call if real documents run longer.
    """
    import pypdfium2 as pdfium  # native ext; only import on the raster path

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        n_pages = len(pdf)
        if n_pages > max_pages:
            logger.warning(
                "PDF has %d pages, rendering first %d only (MAX_PDF_PAGES)",
                n_pages, max_pages,
            )
        out = []
        for i in range(min(n_pages, max_pages)):
            bitmap = pdf[i].render(scale=dpi / 72.0)
            pil = bitmap.to_pil()
            try:
                out.append(_jpeg_data_url(pil, max_side))
            finally:
                pil.close()
        return out
    finally:
        pdf.close()


def safe_process_image(url: str) -> Optional[str]:
    """Fetch a file from `url`, detect PDF vs image by magic bytes, and return
    the appropriate base64 data URL ready for the vision LLM. None on any
    failure (errors are logged).

    A PDF comes back as ONE native-PDF data URL, which only Gemini accepts.
    For models without the "file" modality use safe_process_pages().
    """
    try:
        raw = fetch_image_bytes(url)
        if _is_pdf(raw):
            return to_pdf_data_url(raw)
        return to_resized_jpeg_data_url(raw)
    except Exception as exc:
        logger.warning("file processing failed for %s: %s", url, exc)
        return None


def safe_process_pages(url: str, raster_pdf: bool = True) -> Optional[List[str]]:
    """Like safe_process_image but always returns a LIST of data URLs.

    An image yields one entry. A PDF yields one entry PER PAGE when raster_pdf
    is True, otherwise a single native-PDF entry. None on any failure.

    Callers that map results back by index MUST handle one input file expanding
    into several entries — see epr_ai_audit/api/ocr.py for the pattern.
    """
    try:
        raw = fetch_image_bytes(url)
        if not _is_pdf(raw):
            return [to_resized_jpeg_data_url(raw)]
        if not raster_pdf:
            return [to_pdf_data_url(raw)]
        pages = pdf_to_jpeg_data_urls(raw)
        if not pages:
            logger.warning("PDF rendered zero pages: %s", url)
            return None
        return pages
    except Exception as exc:
        logger.warning("file processing failed for %s: %s", url, exc)
        return None
