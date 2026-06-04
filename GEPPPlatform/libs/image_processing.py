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
from typing import Optional

import requests
from PIL import Image

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECS = 15
MAX_SIDE_PX = 1024  # downscale image long edge before base64-encoding

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


def to_resized_jpeg_data_url(image_bytes: bytes, max_side: int = MAX_SIDE_PX) -> str:
    """Decode → optionally downscale → re-encode as JPEG → base64 data URL."""
    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        if max(img.size) > max_side:
            img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def safe_process_image(url: str) -> Optional[str]:
    """Fetch a file from `url`, detect PDF vs image by magic bytes, and return
    the appropriate base64 data URL ready for the vision LLM. None on any
    failure (errors are logged)."""
    try:
        raw = fetch_image_bytes(url)
        if _is_pdf(raw):
            return to_pdf_data_url(raw)
        return to_resized_jpeg_data_url(raw)
    except Exception as exc:
        logger.warning("file processing failed for %s: %s", url, exc)
        return None
