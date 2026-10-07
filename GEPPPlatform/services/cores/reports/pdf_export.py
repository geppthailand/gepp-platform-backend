"""
Reusable PDF export for Reports.
This module adapts scripts/generate_pdf_report.py drawing functions for API usage.
"""
from __future__ import annotations

from io import BytesIO
from datetime import datetime
import json
import math
import base64
import os
try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics import renderPDF
from urllib.request import urlopen
from reportlab.lib.utils import ImageReader
from GEPPPlatform.services.cores.thai_canvas import ThaiCanvas

# --- Colors and constants (vendored from scripts/generate_pdf_report.py) ---
BuildingColors = [
    "#0f4a34",
    "#166b48",
    "#1d8a5e",
    "#28a074",
    "#43b58c",
    "#66c6a3",
    "#8fd6bd",
    "#b6e4d3",
    "#d5f0e6",
    "#e9f7f1",
]

# Keyed by ENGLISH category name — must match the dashboard palette (OverviewTab MATERIAL_COLORS)
# so the PDF pie matches what users see on screen.
MATERIAL_COLORS = {
    "General Waste": colors.HexColor("#2a78d6"),        # blue (was #cfe2f3)
    "Recyclable Waste": colors.HexColor("#eda100"),     # yellow/amber (was #fff8c8)
    "Organic Waste": colors.HexColor("#1baf7a"),        # teal-green (was #b0dad6)
    "Hazardous Waste": colors.HexColor("#e34948"),      # red (was #f4cccc)
    "Bio-Hazardous Waste": colors.HexColor("#c8553d"),  # terracotta (was #e6b8af)
    "Waste To Energy": colors.HexColor("#eb6834"),      # orange (was #fce5cd)
    "Electronic Waste": colors.HexColor("#64748b"),     # slate/grey (was #d9d9d9)
    "Construction Waste": colors.HexColor("#4a3aa7"),   # violet (was #e8e5ef)
}
main_material_colorPalette = [
  "#065F46", "#0F766E",
  "#059669", "#0D9488",
  "#10B981", "#14B8A6",
  "#34D399", "#2DD4BF",
  "#064E3B", "#134E4A",
  "#047857", "#115E59",
  "#022C22", "#042F2E",
]
# Materials pages: bars, pie and legend use the dashboard's palettes by rank (main materials =
# MaterialsTab, sub materials = SubMaterialsSection), so item N has the same colour as on
# screen. The PDF pie shows the top 5 and folds the rest into one grey "others" slice.
OTHERS_GREY = "#c8ced4"
sub_material_colorPalette = [
    "#166534", "#4D7C0F", "#854D0E",
    "#16A34A", "#65A30D", "#CA8A04",
    "#22C55E", "#84CC16", "#EAB308",
    "#15803D", "#3F6212", "#A16207",
    "#4ADE80", "#A3E635", "#FACC15",
]


def _rank_color(palette: list, i: int):
    return colors.HexColor(palette[i % len(palette)])


def _top5_pie(items_sorted: list, palette: list, value_key: str = "total_waste") -> tuple:
    """(values, colours, others_value): top 5 in the page's palette, the rest one grey slice."""
    vals = [float(it.get(value_key, 0) or 0) for it in items_sorted]
    top = vals[:5]
    rest = sum(vals[5:])
    values = top + ([rest] if rest > 0 else [])
    cols = [_rank_color(palette, i) for i in range(len(top))] + ([colors.HexColor(OTHERS_GREY)] if rest > 0 else [])
    return (values or [1.0]), (cols or [colors.HexColor(OTHERS_GREY)]), rest


def _paginate_table_rows(rows: list, per_page: int, is_data=lambda r: True, min_tail: int = 2,
                         continuation=None) -> list:
    """Split table rows into pages of at most `per_page`.

    - The last page keeps at least `min_tail` data rows with the closing row (e.g. the total),
      so a total never sits alone on a new page.
    - `continuation(prev_rows, next_row)` may return a row to repeat at the top of a page
      (e.g. a group header "(cont.)"); it counts towards the page size.
    - A row flagged `keep_with_next` (group header) is never the last row on a page.
    """
    def build(caps: dict) -> list:
        pages, cur, i = [], [], 0
        while i < len(rows):
            cap = per_page - caps.get(len(pages), 0)
            if not cur and pages and continuation:
                cont = continuation(pages[-1], rows[i])
                if cont is not None:
                    cur.append(cont)
            row = rows[i]
            room = cap - len(cur)
            needs = 2 if (isinstance(row, dict) and row.get("keep_with_next")) else 1
            if room >= needs or (not cur):
                cur.append(row)
                i += 1
                if len(cur) >= cap:
                    pages.append(cur)
                    cur = []
            else:
                pages.append(cur)
                cur = []
        if cur:
            pages.append(cur)
        return pages

    caps: dict = {}
    pages = build(caps)
    while len(pages) > 1 and sum(1 for r in pages[-1] if is_data(r)) < min_tail:
        k = len(pages) - 2
        caps[k] = caps.get(k, 0) + 1
        if caps[k] >= per_page - 1:
            break
        pages = build(caps)
    return pages


def _fit_text_to_width(text: str, font_name: str, font_size: float, max_w: float) -> str:
    """Truncate `text` with an ellipsis so it fits within `max_w` at the given font.
    Prevents long org/branch/building names from overlapping adjacent content in the PDF."""
    from reportlab.pdfbase.pdfmetrics import stringWidth as _sw
    t = str(text or "")
    if max_w <= 0:
        return ""
    if _sw(t, font_name, font_size) <= max_w:
        return t
    ell = "…"
    while t and _sw(t + ell, font_name, font_size) > max_w:
        t = t[:-1]
    return (t + ell) if t else ell

PAGE_WIDTH_IN = 11.69
PAGE_HEIGHT_IN = 8.27

# --- i18n labels ---
# SINGLE SOURCE lives in report_i18n.py (shared with reports_handlers.py). Import it
# normally when available; fall back to a by-path load because this module is often
# exec'd directly by the render lambda (spec_from_file_location), where package
# imports would drag in reports/__init__.py (SQLAlchemy) and fail.
try:
    from GEPPPlatform.services.cores.reports.report_i18n import LABELS as _TRANSLATIONS
except Exception:
    import importlib.util as _ilu
    _i18n_path = os.path.join(os.path.dirname(__file__), "report_i18n.py")
    _spec = _ilu.spec_from_file_location("report_i18n", _i18n_path)
    _mod = _ilu.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    _TRANSLATIONS = _mod.LABELS

def _t(key: str, data: dict) -> str:
    """Translate a key. Checks data['labels'] first (pre-computed by handler), then falls back to built-in translations."""
    labels = data.get('labels')
    if labels and key in labels:
        return labels[key]
    lang = data.get('language', 'en') or 'en'
    translations = _TRANSLATIONS.get(lang, _TRANSLATIONS['en'])
    return translations.get(key, _TRANSLATIONS['en'].get(key, key))

def _t_months_short(data: dict) -> list:
    labels = data.get('labels')
    if labels and 'months_short' in labels:
        return labels['months_short']
    lang = data.get('language', 'en') or 'en'
    return _TRANSLATIONS.get(lang, _TRANSLATIONS['en'])['months_short']

def _t_months_long(data: dict) -> list:
    labels = data.get('labels')
    if labels and 'months_long' in labels:
        return labels['months_long']
    lang = data.get('language', 'en') or 'en'
    return _TRANSLATIONS.get(lang, _TRANSLATIONS['en'])['months_long']

def _t_name(item: dict, prefix: str, data: dict) -> str:
    """Pick the localized name from an item dict based on language.
    e.g. prefix='main_material_name' looks for main_material_name_th/main_material_name_en."""
    lang = data.get('language', 'en') or 'en'
    localized = item.get(f'{prefix}_{lang}')
    if localized:
        return str(localized)
    # Fallback: try the other language, then the base name
    fallback_lang = 'en' if lang == 'th' else 'th'
    return str(item.get(f'{prefix}_{fallback_lang}') or item.get(prefix, '') or '')
PRIMARY = colors.HexColor("#54937a")
TEXT = colors.HexColor("#54937a")
CARD = colors.HexColor("#f6f8fb")
STROKE = colors.HexColor("#e6edf4")
BAR = colors.HexColor("#efefef")
WHITE = colors.white
BLACK = colors.black
BAR2 = colors.HexColor("#84b8a3")
BAR3 = colors.HexColor("#c8ced4")
BAR4 = colors.HexColor("#8fcfc6")
SERIES_COLORS = [colors.HexColor("#84b8a3"), colors.HexColor("#d1e4dc"), BAR4, BAR3, TEXT]

def wrap_label(text, font, size, max_w):
    words = text.split()
    lines = []
    current = ""
    for w in words:
        test = f"{current} {w}".strip()
        if stringWidth(test, font, size) <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines

def snake_to_title(text: str) -> str:
    """Convert snake_case text to Title Case (e.g., 'mother_fucker' -> 'Mother Fucker')."""
    if not text:
        return text
    return ' '.join(word.capitalize() for word in str(text).split('_'))

def _header(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    """Organisation logo, top right. The exporting user's name used to be printed here
    when there was no logo; a report handed to a tenant or an auditor should not carry
    whoever happened to press Download, so the fallback is now nothing."""
    padding = 0.78 * inch
    y = page_height_points - (0.7 * inch)
    try:
        profile_src = data.get("profile_img")
        if isinstance(profile_src, (list, tuple)):
            profile_src = profile_src[0] if profile_src else None
        profile_src = (str(profile_src or "")).strip()
        if not profile_src:
            return
        # Fixed logo box; the image is scaled to fit inside it (contain), so
        # wide and tall logos all occupy the same slot instead of sprawling.
        LOGO_BOX_W = 2.2 * inch
        LOGO_BOX_H = 40  # main knob: squarish logos are height-limited, so this sets size
        box_x = page_width_points - padding - LOGO_BOX_W
        box_y = y - 20  # lowered so the taller box stays clear of the page top edge
        img_obj = None
        if profile_src.startswith("http://") or profile_src.startswith("https://"):
            try:
                with urlopen(profile_src, timeout=4) as resp:
                    img_bytes = resp.read()
                img_obj = BytesIO(img_bytes)
                img_obj.seek(0)
            except Exception:
                img_obj = None
        elif os.path.exists(profile_src):
            img_obj = profile_src
        if img_obj is None:
            return
        try:
            reader = ImageReader(img_obj)
            # preserveAspectRatio fits (letterboxes) the image inside the
            # box; anchor='e' right-aligns it to the box's right edge.
            pdf.drawImage(reader, box_x, box_y, width=LOGO_BOX_W, height=LOGO_BOX_H,
                          preserveAspectRatio=True, anchor='e', mask='auto')
        except Exception:
            # Fallback without ImageReader (still confined to the box)
            try:
                pdf.drawImage(img_obj, box_x, box_y, width=LOGO_BOX_W, height=LOGO_BOX_H,
                              preserveAspectRatio=True, anchor='e', mask='auto')
            except Exception:
                pass
    except Exception:
        # Silently ignore image issues
        pass

def _sub_header(pdf, page_width_points: float, page_height_points: float, data: dict, header_text: str) -> None:
    padding = 0.78 * inch
    location_data = data.get("location", [])
    if isinstance(location_data, list):
        location_text = ", ".join(map(str, location_data))
    else:
        location_text = str(location_data)
    scope_text = f"{_t('location', data)}: {location_text}"
    tenants = data.get("tenants") or []
    if isinstance(tenants, str):
        tenants = [tenants]
    if tenants:
        scope_text += f"   ·   {_t('tenant', data)}: {', '.join(map(str, tenants))}"
    pdf.setFillColor(PRIMARY)
    pdf.setFont("IBMPlexSansThai-Bold", 48)
    pdf.drawString(padding, page_height_points - (1.38 * inch), header_text)
    pdf.setFont("IBMPlexSansThai-Regular", 12)
    pdf.drawString(padding, page_height_points - (1.75 * inch),
                   _fit_text_to_width(scope_text, "IBMPlexSansThai-Regular", 12, page_width_points - 2 * padding))
    pdf.drawString(padding, page_height_points - (1.96 * inch), f"{_t('date', data)}: {data['date_from']} - {data['date_to']}")

def _format_number(value) -> str:
    try:
        v = float(value)
        return f"{v:,.2f}"
    except Exception:
        return str(value)

def _rounded_card(pdf, x, y, w, h, radius=8, fill=CARD, stroke=STROKE):
    pdf.setFillColor(fill)
    pdf.setStrokeColor(stroke)
    pdf.roundRect(x, y, w, h, radius, stroke=1, fill=1)

def _wrap_text_lines(pdf, text: str, max_width: float, font_name: str, font_size: float) -> list[str]:
    pdf.setFont(font_name, font_size)
    words = (text or "").split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = current + " " + word
        if stringWidth(trial, font_name, font_size) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines

def _stat_chip(pdf, x, y, w, h, title, value, variant="gray", subtitle=None):
    fill_color = WHITE if variant == "white" else CARD
    _rounded_card(pdf, x, y, w, h, radius=8, fill=fill_color)
    pad_x = 12 if variant == "white" else 20
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Regular", 8)
    # Chips share the column width, so adding a 4th narrows every title. A white chip may
    # wrap its title onto a second line (the unit often lives there); anything longer is
    # truncated rather than run over the neighbouring chip.
    value_dy = 32
    title_lines = _wrap_thai(title, "IBMPlexSansThai-Regular", 7.5, w - pad_x * 2) if variant == "white" else [title]
    if variant == "white" and len(title_lines) > 1 and h >= 50:
        pdf.setFont("IBMPlexSansThai-Regular", 7.5)
        pdf.drawString(x + pad_x, y + h - 14, title_lines[0])
        pdf.drawString(x + pad_x, y + h - 23, _fit_text_to_width(" ".join(title_lines[1:]), "IBMPlexSansThai-Regular", 7.5, w - pad_x * 2))
        value_dy = 38
    else:
        pdf.drawString(
            x + pad_x, y + h - 18,
            _fit_text_to_width(title, "IBMPlexSansThai-Regular", 8, w - pad_x * 2),
        )
    pdf.setFont("IBMPlexSansThai-Regular", 12)
    # Allow callers to pass pre-formatted strings; otherwise format numerics
    try:
        if isinstance(value, str):
            value_text = value
        else:
            value_text = _format_number(value)
    except Exception:
        value_text = str(value)
    pdf.drawString(x + pad_x, y + h - value_dy, value_text)
    # Optional third line, e.g. the denominator behind a per-capita figure. Appending it to
    # the title instead would not fit an English label in a 4-across row.
    if subtitle:
        pdf.setFont("IBMPlexSansThai-Regular", 7)
        pdf.setFillColor(BAR3)  # muted grey — supporting detail, not a headline number
        pdf.drawString(
            x + pad_x, y + h - value_dy - 11,
            _fit_text_to_width(str(subtitle), "IBMPlexSansThai-Regular", 7, w - pad_x * 2),
        )
        pdf.setFillColor(TEXT)

def _progress_bar(pdf, x, y, w, h, ratio, bar_color=PRIMARY, back_color=STROKE):
    ratio = max(0.0, min(1.0, float(ratio or 0)))
    radius = h / 2
    pdf.setFillColor(back_color)
    pdf.roundRect(x, y, w, h, radius, stroke=0, fill=1)
    pdf.setFillColor(bar_color)
    bar_width = max(h, w * ratio)
    pdf.roundRect(x, y, bar_width, h, radius, stroke=0, fill=1)

def _label_progress(pdf, x, y, w, label, value_text, ratio, bar_color, back_color, bar_h=8):
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Regular", 10)
    pdf.drawString(x, y + 16, label)
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Regular", 10)
    txt_w = stringWidth(value_text, "IBMPlexSansThai-Regular", 10)
    pdf.drawString(x + w - txt_w, y + 16, value_text)
    _progress_bar(pdf, x, y, w, bar_h, ratio, bar_color, back_color)

def _draw_bar_top_round_rect(pdf, x, y, w, h, r, color):
    if w <= 0 or h <= 0:
        return
    rr = max(0.0, min(r, w / 2.0, h))
    pth = pdf.beginPath()
    pth.moveTo(x, y)
    pth.lineTo(x + w, y)
    pth.lineTo(x + w, y + h - rr)
    pth.arcTo(x + w - 2 * rr, y + h - 2 * rr, x + w, y + h, startAng=0, extent=90)
    pth.lineTo(x + rr, y + h)
    pth.arcTo(x, y + h - 2 * rr, x + 2 * rr, y + h, startAng=90, extent=90)
    pth.lineTo(x, y)
    pdf.setFillColor(color)
    pdf.drawPath(pth, stroke=0, fill=1)

def _simple_bar_chart(pdf, x, y, w, h, chart_series, allowed_months: set[int] | None = None, allowed_years: set[str] | None = None, data: dict = None):
    left_pad, bottom_pad, right_pad, top_pad = 32, 36, 24, 20
    gx = x + left_pad
    gy = y + bottom_pad
    gw = w - left_pad - right_pad
    gh = h - bottom_pad - top_pad
    pdf.setStrokeColor(STROKE)
    pdf.line(gx, gy, gx, gy + gh)
    pdf.line(gx, gy, gx + gw, gy)
    if not chart_series:
        return
    # English months for data key matching; translated months for display labels
    _months_en = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    months_display = _t_months_short(data or {})
    try:
        year_keys = [k for k in chart_series.keys() if (not allowed_years or k in allowed_years)]
        sorted_years = sorted([int(k) for k in year_keys])
        series_keys = [str(y) for y in sorted_years[-3:]]  # limit to last 3 years if many
    except Exception:
        try:
            year_keys = [k for k in chart_series.keys() if (not allowed_years or k in allowed_years)]
            series_keys = list(year_keys)[-3:]
        except Exception:
            series_keys = list(chart_series.keys())[-3:]
    values_by_series = {}
    months_with_data: set[int] = set()
    for key in series_keys:
        arr = [0.0] * 12
        for pt in chart_series.get(key, []):
            m = str(pt.get("month", ""))
            if m in _months_en:
                idx = _months_en.index(m)
                months_with_data.add(idx + 1)  # 1-based month number
                try:
                    arr[idx] = float(pt.get("value", 0) or 0.0)
                except Exception:
                    arr[idx] = 0.0
        values_by_series[key] = arr
    vmax = 0.0
    for arr in values_by_series.values():
        vmax = max(vmax, max(arr) if arr else 0.0)
    if vmax <= 0:
        vmax = 1.0
    # Draw Y-axis ticks and gridlines (5 ticks: 0%, 25%, 50%, 75%, 100%)
    # Choose a "nice" rounded top value >= vmax
    mag = 1.0
    while mag * 10 <= vmax:
        mag *= 10.0
    top_val = vmax
    for mul in (1.0, 2.0, 2.5, 5.0, 10.0):
        cand = mul * mag
        if cand >= vmax:
            top_val = cand
            break
    tick_vals = [0.0, top_val * 0.25, top_val * 0.5, top_val * 0.75, top_val]
    chart_h_scale = (gh - 10)  # match bar height scale below
    pdf.setStrokeColor(STROKE)
    pdf.setLineWidth(0.5)
    for tv in tick_vals:
        y_tick = gy + (tv / top_val) * chart_h_scale
        # gridline
        pdf.line(gx, y_tick, gx + gw, y_tick)
        # label at left of y-axis
        lbl = f"{int(round(tv))}"
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Regular", 10)
        lw_lbl = stringWidth(lbl, "IBMPlexSansThai-Regular", 10)
        pdf.drawString(gx - 6 - lw_lbl, y_tick - 3, lbl)
    # Only show months that have data (and optionally restrict to date range)
    month_numbers = []
    if months_with_data:
        if allowed_months:
            month_numbers = sorted([m for m in months_with_data if m in allowed_months and 1 <= int(m) <= 12])
        else:
            month_numbers = sorted([m for m in months_with_data if 1 <= int(m) <= 12])
    if not month_numbers:
        if allowed_months:
            month_numbers = sorted([m for m in allowed_months if 1 <= int(m) <= 12])
        if not month_numbers:
            month_numbers = list(range(1, 13))
    n_months = len(month_numbers)
    gap = 10
    slot_w = (gw - (n_months + 1) * gap) / max(1, n_months)
    group_scale = 0.86
    group_w = slot_w * group_scale
    s_count = max(1, len(series_keys))
    inner_gap_ratio = 0.06
    total_inner_gap = (s_count - 1) * group_w * inner_gap_ratio
    bar_w = (group_w - total_inner_gap) / s_count
    for i, m_num in enumerate(month_numbers):
        mi = int(m_num) - 1  # convert month number (1..12) to index (0..11)
        # Place bars sequentially by filtered index to center the group
        slot_x = gx + gap + i * (slot_w + gap)
        group_x = slot_x + (slot_w - group_w) / 2
        for si, key in enumerate(series_keys):
            color = SERIES_COLORS[si % len(SERIES_COLORS)]
            pdf.setFillColor(color)
            v = values_by_series[key][mi]
            bh = (v / top_val) * chart_h_scale
            bx = group_x + si * (bar_w + group_w * inner_gap_ratio)
            # Rounded top corners for bar
            radius = min(bar_w * 0.25, 5)
            _draw_bar_top_round_rect(pdf, bx, gy, bar_w, bh, radius, color)
        lbl = months_display[mi]
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Regular", 8)
        lw = stringWidth(lbl, "IBMPlexSansThai-Regular", 8)
        pdf.drawString(slot_x + (slot_w - lw) / 2, gy - 14, lbl)
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Regular", 9)
    pdf.drawString(gx - 18, gy + gh + 6, _t('kg', data or {}))
    if series_keys:
        sq = 8
        cur_x = x + w - 10
        pdf.setFont("IBMPlexSansThai-Regular", 9)
        for si in reversed(range(len(series_keys))):
            label = str(series_keys[si])
            lw = stringWidth(label, "IBMPlexSansThai-Regular", 9)
            entry_w = sq + 6 + lw + 12
            cur_x -= entry_w
            pdf.setFillColor(SERIES_COLORS[si % len(SERIES_COLORS)])
            pdf.roundRect(cur_x, y + h - 18, sq, sq, 2, stroke=0, fill=1)
            pdf.setFillColor(TEXT)
            pdf.drawString(cur_x + sq + 6, y + h - 18, label)

def _footer(pdf, page_width_points: float, data: dict = None):
    text = _t('copyright', data or {})
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Regular", 9)
    tw = stringWidth(text, "IBMPlexSansThai-Regular", 9)
    pdf.drawString((page_width_points - tw) / 2, 0.25 * inch, text)

def _parse_date_to_date(value) -> datetime.date | None:
    """
    Parse various incoming date strings to a date **in the user's locale (Asia/Bangkok)**.

    Why locale-aware: filter boundaries arrive as ISO strings already converted to UTC
    by the reports handler (e.g. "April 1 Bangkok" -> "2026-03-31T17:00:00+00:00").
    A naive 10-char truncation would yield "2026-03-31" -> month=3, leaking March
    into chart-month allow-lists when the actual filter is April-only. Convert to
    Bangkok TZ before extracting the date to match how data is bucketed elsewhere.

    Supports:
      - '01 Jan 2025' (d Mon YYYY)
      - '2025-01-01' (ISO date, locale-neutral)
      - '2025/01/01'
      - '01/01/2025'
      - ISO datetime variants, e.g. '2025-01-01T00:00:00Z' or with offsets

    Returns None if parsing fails.
    """
    from zoneinfo import ZoneInfo
    _BKK = ZoneInfo("Asia/Bangkok")

    try:
        if isinstance(value, datetime):
            if value.tzinfo is not None:
                return value.astimezone(_BKK).date()
            return value.date()
    except Exception:
        pass
    s = str(value or "").strip()
    if not s:
        return None
    # ISO datetime variants — convert TZ-aware values to Bangkok before taking date
    try:
        iso_norm = s.replace("Z", "+00:00")
        # If the string contains a time component, parse the full ISO
        if "T" in iso_norm or " " in iso_norm:
            dt = datetime.fromisoformat(iso_norm)
            if dt.tzinfo is not None:
                return dt.astimezone(_BKK).date()
            return dt.date()
    except Exception:
        pass
    # Date-only fast path (no time component, no TZ confusion)
    try:
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            return datetime.fromisoformat(s[:10]).date()
    except Exception:
        pass
    # Common explicit formats
    fmts = ["%d %b %Y", "%d %B %Y", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None

def _simple_pie_chart(pdf, x, y, size, values, colors_list, gap_width=2, gap_color=colors.white):
    try:
        vals = [max(0.0, float(v or 0)) for v in values]
    except Exception:
        vals = [1.0]
    if not vals or sum(vals) <= 0:
        vals = [1.0]
    # Sort slices descending so the largest starts first and proceeds clockwise
    order = list(range(len(vals)))
    order.sort(key=lambda i: vals[i], reverse=True)
    vals_sorted = [vals[i] for i in order]
    # Reorder colors to match sorted values when possible
    try:
        colors_sorted = [colors_list[i % len(colors_list)] for i in order]
    except Exception:
        colors_sorted = colors_list
    d = Drawing(size, size)
    pie = Pie()
    pie.x = 0
    pie.y = 0
    pie.width = size
    pie.height = size
    pie.data = vals_sorted
    pie.labels = None
    pie.strokeWidth = 0
    pie.slices.strokeWidth = max(0, int(gap_width))
    pie.slices.strokeColor = gap_color
    # Start at 90 degrees (top) and go clockwise
    try:
        pie.startAngle = 90
        pie.direction = 'clockwise'
    except Exception:
        pass
    for i in range(len(vals_sorted)):
        pie.slices[i].fillColor = colors_sorted[i % len(colors_sorted)]
    d.add(pie)
    renderPDF.draw(d, pdf, x, y)

def draw_table(pdf, x, y, w, h, r=6, type="Header"):
    # Use the current fill color for the stroke to match the background
    # For headers, explicitly use gray background and border
    if type == "Header":
        header_gray = colors.HexColor("#f3f3f3")
        pdf.setFillColor(header_gray)
        pdf.setStrokeColor(header_gray)
    else:
        try:
            # Get the current fill color from the canvas
            fill_color = pdf._fillColorObj if hasattr(pdf, '_fillColorObj') else colors.HexColor("#e2e8ef")
            pdf.setStrokeColor(fill_color)
        except Exception:
            # Fallback to default if we can't get the fill color
            pdf.setStrokeColor(colors.HexColor("#e2e8ef"))
    pdf.setLineWidth(0.5)
    if type == "Body":
        pdf.rect(x, y, w, h, stroke=1, fill=1)
        return
    p = pdf.beginPath()
    if type == "Header":
        p.moveTo(x, y)
        p.lineTo(x + w, y)
        p.lineTo(x + w, y + h - r)
        p.arcTo(x + w - 2*r, y + h - 2*r, x + w, y + h, startAng=0, extent=90)
        p.lineTo(x + r, y + h)
        p.arcTo(x, y + h - 2*r, x + 2*r, y + h, startAng=90, extent=90)
        p.lineTo(x, y)
    elif type == "Footer":
        p.moveTo(x, y + h)
        p.lineTo(x + w, y + h)
        p.lineTo(x + w, y + r)
        p.arcTo(x + w - 2*r, y, x + w, y + 2*r, startAng=0, extent=-90)
        p.lineTo(x + r, y)
        p.arcTo(x, y, x + 2*r, y + 2*r, startAng=-90, extent=-90)
        p.lineTo(x, y + h)
    pdf.drawPath(p, stroke=1, fill=1)

# --- Page drawing functions (vendored) ---
def draw_cover(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    _header(pdf, page_width_points, page_height_points, data)
    # Use report period year, or current year
    year_str = str(datetime.now().year)
    middle = page_height_points / 2
    # Slightly shift content down to better center on the page
    content_center = middle - 20
    pdf.setFillColor(PRIMARY)
    pdf.setFont("IBMPlexSansThai-Bold", 100)
    # Move text block down a bit to better center vertically
    pdf.drawString(0.63 * inch, content_center + 0, year_str)
    pdf.setFillColor(colors.HexColor("#9ac7b5"))
    pdf.setFont("IBMPlexSansThai-Medium", 38.5)
    pdf.drawString(0.63 * inch, content_center - 40, _t('gepp_report', data))
    pdf.setFont("IBMPlexSansThai-Regular", 16.5)
    pdf.setFillColor(colors.HexColor("#666666"))
    pdf.drawString(0.63 * inch, content_center - 60, _t('subtitle', data))
    # Draw ESG.png image instead of green rectangle
    esg_image_path = "GEPPPlatform/services/cores/reports/Assets/ESG.png"
    # Try multiple possible paths
    possible_paths = [
        esg_image_path,
        "services/cores/reports/Assets/ESG.png",
        "reports/Assets/ESG.png",
        "Assets/ESG.png",
        os.path.join(os.path.dirname(__file__), "Assets", "ESG.png"),
    ]
    image_path = None
    for path in possible_paths:
        if os.path.exists(path):
            image_path = path
            break
    if image_path:
        img_x = 4.54 * inch
        img_y = content_center - 65
        img_w = page_width_points - (4.54 * inch)
        img_h = 2.07 * inch
        # Crop 1 pixel from the left of the image
        if HAS_PIL:
            try:
                img = Image.open(image_path)
                # Crop: (left, top, right, bottom) - remove 1px from left
                cropped_img = img.crop((1, 0, img.width, img.height))
                # Save to temporary BytesIO
                temp_buffer = BytesIO()
                cropped_img.save(temp_buffer, format='PNG')
                temp_buffer.seek(0)
                pdf.drawImage(temp_buffer, img_x, img_y, width=img_w, height=img_h, mask='auto')
            except Exception:
                # Fallback to original image if cropping fails
                pdf.drawImage(image_path, img_x, img_y, width=img_w, height=img_h, mask='auto')
        else:
            # If PIL not available, draw original image
            pdf.drawImage(image_path, img_x, img_y, width=img_w, height=img_h, mask='auto')
    else:
        # Fallback to green rectangle if image not found
        pdf.setFillColor(PRIMARY)
        pdf.rect(4.54 * inch, content_center - 65, page_width_points - (4.54 * inch), 2.07 * inch, fill=1, stroke=0)

# --- Layout helpers for the redesigned pages ---------------------------------------
# Every page below lays out inside [CONTENT_BOTTOM, content_top] and measures its text
# before drawing, so nothing runs into the footer or spills onto a surprise extra page.
CONTENT_BOTTOM = 0.55 * inch
REG = "IBMPlexSansThai-Regular"
MED = "IBMPlexSansThai-Medium"
BOLD = "IBMPlexSansThai-Bold"
MUTED = colors.HexColor("#6f8a7e")
INK = colors.HexColor("#2e5c4b")
RECYCLED_COLOR = colors.HexColor("#2f8f6b")
REST_COLOR = colors.HexColor("#d9dee3")   # "the rest" in X-vs-others views: neutral
TREND_COLOR = colors.HexColor("#1f4a3a")   # same as the web trend line
RECYCLABLE_CATEGORY_ID = "1"   # material_categories "วัสดุรีไซเคิล"
ORGANIC_CATEGORY_ID = "3"      # material_categories "ขยะอินทรีย์"
RATE_ROW_MAX_BARS = 12          # the overview chart's recycling-rate row only up to this many bars
INCREASE_COLOR = colors.HexColor("#c2562e")
DECREASE_COLOR = colors.HexColor("#1f8a5e")
SECTION_COLORS = {
    "risk": colors.HexColor("#e0663a"),
    "opportunity": colors.HexColor("#2a78d6"),
    "quickwin": colors.HexColor("#2f8f6b"),
}

# Thai has no spaces between words. Lines may break between clusters, but never in front
# of a combining vowel/tone mark or a following vowel (ะ า ำ), nor right after a leading
# vowel (เ แ โ ใ ไ) — those always belong to the next consonant.
_TH_NO_BREAK_BEFORE = set("ะัาำิีึืฺุูๅ็่้๊๋์ํ๎")
_TH_NO_BREAK_AFTER = set("เแโใไ")
# Words a line may break in front of when a Thai run has no spaces. Only words that
# start words in our texts; ones that also sit inside other words (ราย in อันตราย,
# ค่า in คุ้มค่า, ที่ in พื้นที่) are left out on purpose.
_TH_SOFT_BREAK_WORDS = (
    "และ", "หรือ", "แทน", "เพื่อ", "ซึ่ง", "เพราะ", "โดย", "ตาม", "ก่อน", "ทุก", "จาก", "เมื่อ",
    "ให้", "ของ", "กับ", "เป็น", "จะ", "ต้อง", "ไม่", "แล้ว", "ช่วง", "ผ่าน", "ด้วย", "ถึง", "ได้",
    "ขยะ", "ถัง", "จุด", "ผู้", "การ", "ความ", "พื้นที่", "ส่วนกลาง", "วัสดุ", "อาคาร", "สำนักงาน",
    "พลาสติก", "กระดาษ", "กล่อง", "ขวด", "ป้าย", "ทีม", "พนักงาน", "แม่บ้าน", "ร้านค้า",
    "กิจกรรม", "ข้อมูล", "ปริมาณ", "สัดส่วน", "ชนิด", "ประเภท", "เครื่อง", "ระบบ", "ครั้ง",
    "เศษ", "ภาชนะ", "บรรจุภัณฑ์", "รีไซเคิล", "ศูนย์", "สัญญา", "เดือน", "รายงาน", "รายได้",
)


def _can_break_at(s: str, i: int) -> bool:
    if i <= 0 or i >= len(s):
        return False
    a, b = s[i - 1], s[i]
    if b in _TH_NO_BREAK_BEFORE or a in _TH_NO_BREAK_AFTER:
        return False
    if a.isascii() and b.isascii() and (a.isalnum() or a in ".,%") and b.isalnum():
        return False  # keep numbers and latin words whole
    if b in ",.;:)%" or a in "(":
        return False
    return True


def _wrap_thai(text: str, font: str, size: float, max_w: float) -> list:
    """Wrap to max_w, breaking at spaces first; a space-less run wider than the line
    (normal in Thai) is split at the last safe cluster boundary."""
    out = []
    for para in str(text or "").split("\n"):
        cur = ""
        for word in [w for w in para.split(" ") if w]:
            trial = f"{cur} {word}" if cur else word
            if stringWidth(trial, font, size) <= max_w:
                cur = trial
                continue
            if stringWidth(word, font, size) <= max_w:
                if cur:
                    out.append(cur)
                cur = word
                continue
            # A space-less run wider than a line: split it, filling what's left of the
            # current line first (so a short lead like "1." never sits alone).
            word = f"{cur} {word}" if cur else word
            cur = ""
            start = 0          # current line = word[start:i]
            last_safe = 0      # last allowed break index (> start when valid)
            last_soft = 0      # last break in front of a connective word
            for i in range(1, len(word)):
                if _can_break_at(word, i):
                    last_safe = i
                    if word.startswith(_TH_SOFT_BREAK_WORDS, i):
                        last_soft = i
                if stringWidth(word[start:i + 1], font, size) > max_w and last_safe > start:
                    # Prefer breaking in front of และ/หรือ/เพื่อ… when it sits in the back
                    # half of the line, so words like ฝังกลบ stay whole.
                    cut = last_soft if last_soft > start + (i - start) * 0.4 else last_safe
                    out.append(word[start:cut])
                    start = cut
                    if last_soft <= cut:
                        last_soft = start
                    if last_safe <= cut:
                        last_safe = start
            cur = word[start:]
        if cur:
            out.append(cur)
    return out


def _nice_top(vmax: float, steps: int = 4) -> float:
    """Axis top that splits into `steps` round ticks (0/60/120/180/240, never 62/188)."""
    if vmax <= 0:
        return float(steps)
    raw = vmax / steps
    mag = 10 ** math.floor(math.log10(raw))
    for mul in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if mul * mag >= raw:
            return mul * mag * steps
    return raw * steps


def _fmt_compact(v) -> str:
    """kg for dense tables/charts: whole numbers from 1,000 kg up, 2 decimals below."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{f:,.0f}" if abs(f) >= 1000 else f"{f:,.2f}"


def _tick_label(v: float) -> str:
    return f"{v:,.0f}" if abs(v) >= 10 or float(v).is_integer() else f"{v:,.1f}"


def _kpi_chip(pdf, x, y, w, h, title, value_text, unit_text=None):
    _rounded_card(pdf, x, y, w, h, radius=10, fill=CARD)
    pad = 14
    pdf.setFillColor(TEXT)
    pdf.setFont(REG, 8.5)
    pdf.drawString(x + pad, y + h - 18, _fit_text_to_width(title, REG, 8.5, w - 2 * pad))
    pdf.setFillColor(INK)
    pdf.setFont(MED, 16)
    pdf.drawString(x + pad, y + h - 39, _fit_text_to_width(value_text, MED, 16, w - 2 * pad))
    if unit_text:
        pdf.setFillColor(MUTED)
        pdf.setFont(REG, 7.5)
        pdf.drawString(x + pad, y + h - 52, _fit_text_to_width(unit_text, REG, 7.5, w - 2 * pad))


def _legend_swatches(pdf, right_x, y, entries):
    """Right-aligned legend: entries = [(label, color)], drawn right to left."""
    pdf.setFont(REG, 8.5)
    cur = right_x
    for label, col in reversed(entries):
        lw = stringWidth(label, REG, 8.5)
        cur -= lw
        pdf.setFillColor(TEXT)
        pdf.drawString(cur, y, label)
        cur -= 13
        pdf.setFillColor(col)
        pdf.roundRect(cur, y, 9, 9, 2, stroke=0, fill=1)
        cur -= 14


def _impact_values(data: dict) -> dict:
    """recycled kg, trees, plastic saved, waste per head. Prefer the handler's untranslated
    'impact' block; fall back to the stat cards (whose titles may be translated) by unit."""
    ov = data.get("overview_data", {}) or {}
    imp = dict(ov.get("impact") or {})
    stats = ((ov.get("overall_charts") or {}).get("chart_stat_data")) or []
    if imp.get("recycled_kg") is None:
        kg_stats = [s for s in stats if s.get("unit") == "kg"]
        imp["recycled_kg"] = (kg_stats[0].get("value") if kg_stats else 0) or 0
        if imp.get("plastic_saved_kg") is None:
            imp["plastic_saved_kg"] = (kg_stats[1].get("value") if len(kg_stats) > 1 else 0) or 0
    if imp.get("trees") is None:
        tree_stats = [s for s in stats if s.get("unit") == "trees"]
        imp["trees"] = (tree_stats[0].get("value") if tree_stats else 0) or 0
    if "waste_per_head" not in imp:
        head = [s for s in stats if "headcount" in s]
        imp["waste_per_head"] = head[0].get("value") if head else None
        imp["headcount"] = head[0].get("headcount") if head else None
    imp["recycled_kg"] = float(imp.get("recycled_kg") or 0)
    imp["trees"] = float(imp.get("trees") or 0)
    return imp


CATEGORY_FALLBACK_PALETTE = ["#2a78d6", "#eda100", "#1baf7a", "#e34948", "#eb6834", "#64748b", "#4a3aa7", "#c8553d", "#0e7490"]


def _category_meta(data: dict) -> dict:
    """category_id (str) → (display name, colour, total kg), from waste_type_proportions."""
    out = {}
    wtp = ((data.get("overview_data", {}) or {}).get("waste_type_proportions")
           or data.get("waste_type_proportions") or [])
    for i, it in enumerate(wtp):
        cid = it.get("category_id")
        if cid is None:
            continue
        name = str(it.get("category_name") or f"#{cid}")
        en = str(it.get("category_name_en") or it.get("category_name") or "")
        col = MATERIAL_COLORS.get(en) or colors.HexColor(CATEGORY_FALLBACK_PALETTE[i % len(CATEGORY_FALLBACK_PALETTE)])
        out[str(cid)] = (name, col, float(it.get("total_waste", 0) or 0))
    return out


def _chart_buckets(data: dict) -> tuple:
    """(granularity, [{label, total, recycled, by_cat}]) following the chart setting."""
    gran = (data.get("overview_chart") or "monthly")
    charts = ((data.get("overview_data", {}) or {}).get("overall_charts") or {})
    lang = data.get("language", "en") or "en"
    short = _t_months_short(data)
    months_en = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    def bucket(label, p_list):
        total = sum(float(p.get("value", 0) or 0) for p in p_list)
        rec = sum(float(p.get("recycled", 0) or 0) for p in p_list)
        by_cat: dict = {}
        for p in p_list:
            for cid, kg in (p.get("by_category") or {}).items():
                by_cat[str(cid)] = by_cat.get(str(cid), 0.0) + float(kg or 0)
        return {"label": label, "total": total, "recycled": min(total, rec), "by_cat": by_cat}

    if gran == "daily":
        out = []
        for p in charts.get("daily_data") or []:
            try:
                _y, m, d = (int(x) for x in str(p.get("date", "")).split("-"))
            except ValueError:
                continue
            out.append(bucket(f"{d} {short[m - 1]}", [p]))
        return gran, out
    chart = charts.get("chart_data") or {}
    if not isinstance(chart, dict):
        return gran, []
    years = sorted(chart.keys())
    if gran == "yearly":
        out = []
        for y in years:
            b = bucket(str(int(y) + 543) if (lang == "th" and str(y).isdigit()) else str(y), chart.get(y) or [])
            if b["total"] > 0:
                out.append(b)
        return gran, out
    multi_year = len(years) > 1
    keyed = []
    for y in years:
        for p in chart.get(y) or []:
            m = str(p.get("month", ""))
            if m not in months_en or float(p.get("value", 0) or 0) <= 0:
                continue
            idx = months_en.index(m)
            label = short[idx]
            if multi_year and str(y).isdigit():
                yy = int(y) + (543 if lang == "th" else 0)
                label = f"{label} {str(yy)[-2:]}"
            keyed.append(((int(y) if str(y).isdigit() else 0, idx), bucket(label, [p])))
    keyed.sort(key=lambda t: t[0])
    return "monthly", [b for _k, b in keyed]


def _chart_series(data: dict) -> tuple:
    """(granularity, labels, series, rate_row) for the overview chart.

    series = [(name, colour, values)] bottom → top, following the user's breakdown:
      all           every category stacked (default)
      recycled      the Recyclable category vs the rest
      category:<id> that category vs the rest

    rate_row = ("อัตรารีไซเคิล", ["xx.xx%", ...]) under the month / year labels, in every
    breakdown, when the chart has at most RATE_ROW_MAX_BARS bars (beyond that the row would
    crowd the axis and is left out). The rate is (Recyclable + Organic) ÷ the bucket's total —
    the same basis as the web chart's tooltip; a payload without per-category amounts falls
    back to the bucket's "counts as recycled" figure.
    """
    gran, buckets = _chart_buckets(data)
    labels = [b["label"] for b in buckets]
    totals = [b["total"] for b in buckets]
    mode = str(data.get("overview_breakdown") or "all")
    meta = _category_meta(data)
    other = _t('other_waste', data)
    has_by_cat = any(b["by_cat"] for b in buckets)
    # Same rules as the web: the recyclable category IS the default view (no separate
    # "category:1"), and without per-category amounts the category views fall back to it.
    if mode == f"category:{RECYCLABLE_CATEGORY_ID}" or (mode != "recycled" and not has_by_cat):
        mode = "recycled"

    rate_row = None
    if gran in ("monthly", "yearly") and 0 < len(buckets) <= RATE_ROW_MAX_BARS:
        if has_by_cat:
            recovered = [b["by_cat"].get(RECYCLABLE_CATEGORY_ID, 0.0) + b["by_cat"].get(ORGANIC_CATEGORY_ID, 0.0)
                         for b in buckets]
        else:
            recovered = [b["recycled"] for b in buckets]
        rate_row = (_t('recycling_rate_row', data),
                    [f"{(min(v, t) / t * 100.0) if t > 0 else 0:.2f}%" for v, t in zip(recovered, totals)])

    if mode.startswith("category:") and mode.split(":", 1)[1] in meta:
        cid = mode.split(":", 1)[1]
        name, col, _tot = meta[cid]
        vals = [min(b["total"], b["by_cat"].get(cid, 0.0)) for b in buckets]
        series = [(name, col, vals), (other, REST_COLOR, [t - v for t, v in zip(totals, vals)])]
        return gran, labels, series, rate_row
    if mode == "all" and meta:
        series = []
        for cid, (name, col, _tot) in sorted(meta.items(), key=lambda kv: -kv[1][2]):
            vals = [b["by_cat"].get(cid, 0.0) for b in buckets]
            if any(v > 0 for v in vals):
                series.append((name, col, vals))
        rest = [max(0.0, t - sum(sv[2][i] for sv in series)) for i, t in enumerate(totals)]
        if any(v > 0.01 for v in rest):
            series.append((_t('uncategorized', data), colors.HexColor(OTHERS_GREY), rest))
        return gran, labels, series, rate_row
    # "วัสดุรีไซเคิล เทียบอื่นๆ": the Recyclable category's own kg (organic waste NOT included),
    # in its pie colour. Without per-category amounts (older payload) it falls back to the
    # "counts as recycled" figure.
    rec_meta = meta.get(RECYCLABLE_CATEGORY_ID)
    rec_col = (rec_meta[1] if rec_meta else None) or MATERIAL_COLORS.get("Recyclable Waste") or RECYCLED_COLOR
    if has_by_cat:
        rec = [min(b["total"], b["by_cat"].get(RECYCLABLE_CATEGORY_ID, 0.0)) for b in buckets]
        name = rec_meta[0] if rec_meta else _t('recycled', data)
    else:
        rec = [b["recycled"] for b in buckets]
        name = _t('recycled', data)
    series = [(name, rec_col, rec), (other, REST_COLOR, [t - r for t, r in zip(totals, rec)])]
    return gran, labels, series, rate_row


def _stacked_month_chart(pdf, x, y, w, h, labels, series, rate_row, data):
    """Stacked bars (monthly / yearly). Every series is a band; the total sits on top."""
    left_pad, right_pad, top_pad = 64, 18, 22
    gw = w - left_pad - right_pad
    n = len(labels)
    # X labels: as many months as a long range brings must not overlap. Shrink the font
    # first, then tilt (45°, 60° if still crowded) — decided from the widest label vs the
    # space each bar has, so a normal year keeps straight 8.5pt labels.
    slot_w = gw / n if n else gw
    lab_size, lab_angle = 8.5, 0
    widest = lambda sz: max((stringWidth(str(lb), REG, sz) for lb in labels), default=0.0)
    while lab_size > 6.5 and widest(lab_size) > slot_w - 4:
        lab_size -= 0.5
    if widest(lab_size) > slot_w - 4:
        lab_angle = 45 if slot_w >= lab_size * 1.5 else 60
    lab_drop = (widest(lab_size) * math.sin(math.radians(lab_angle)) + lab_size * math.cos(math.radians(lab_angle))
                if lab_angle else lab_size)
    lab_band = 6 + lab_drop                       # space the labels take under the axis
    # The rate row under the labels gets the same treatment (its "47.1%" values crowd too).
    # same size / weight as the kg totals above the bars
    rate_size, rate_angle, rate_band = 6.5, 0, 0.0
    if rate_row:
        rate_widest = lambda sz: max((stringWidth(str(v), REG, sz) for v in rate_row[1]), default=0.0)
        while rate_size > 6.0 and rate_widest(rate_size) > slot_w - 3:
            rate_size -= 0.5
        if rate_widest(rate_size) > slot_w - 3:
            rate_angle = 45
        rate_band = 6 + (rate_widest(rate_size) * math.sin(math.radians(45)) + rate_size * 0.7 if rate_angle else rate_size)
    bottom_pad = max(30.0, lab_band + 8) + (rate_band + 4 if rate_row else 0)
    gx, gy = x + left_pad, y + bottom_pad
    gh = h - bottom_pad - top_pad
    totals = [sum(sv[2][i] for sv in series) for i in range(n)]
    if not n or gw <= 0 or gh <= 0 or max(totals or [0]) <= 0:
        pdf.setFillColor(MUTED)
        pdf.setFont(REG, 10)
        pdf.drawCentredString(x + w / 2.0, y + h / 2.0, _t('no_data', data))
        return
    top_val = _nice_top(max(totals) * 1.08)
    pdf.setLineWidth(0.5)
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        yt = gy + frac * gh
        pdf.setStrokeColor(STROKE)
        pdf.line(gx, yt, gx + gw, yt)
        pdf.setFillColor(MUTED)
        pdf.setFont(REG, 8)
        pdf.drawRightString(gx - 6, yt - 3, _tick_label(top_val * frac))
    pdf.setFont(REG, 8)
    pdf.drawRightString(gx - 6, gy + gh + 8, _t('kg', data))
    slot = gw / n
    bar_w = max(8.0, min(46.0, slot * 0.5))
    rate_y = gy - lab_band - 6 - (0 if rate_angle else rate_size)   # under the (possibly tilted) labels
    if rate_row:
        pdf.setFillColor(MUTED)
        pdf.setFont(REG, 7.5)
        pdf.drawString(x + 12, rate_y, rate_row[0])
    tops = []   # (centre x, top y) per bar: trend line + value labels go on top of all bars
    for i, label in enumerate(labels):
        cx = gx + slot * (i + 0.5)
        bx = cx - bar_w / 2.0
        radius = min(bar_w * 0.22, 5)
        heights = [sv[2][i] / top_val * gh for sv in series]
        top_idx = max((k for k, hgt in enumerate(heights) if hgt > 0.5), default=-1)
        base = gy
        for k, (sv, hgt) in enumerate(zip(series, heights)):
            if hgt <= 0:
                continue
            if k == top_idx:
                _draw_bar_top_round_rect(pdf, bx, base, bar_w, hgt, radius, sv[1])
            else:
                pdf.setFillColor(sv[1])
                pdf.rect(bx, base, bar_w, hgt, stroke=0, fill=1)
            base += hgt
        tops.append((cx, base))
        pdf.setFillColor(TEXT)
        pdf.setFont(REG, lab_size)
        if lab_angle:
            pdf.saveState()
            pdf.translate(cx + lab_size * 0.3, gy - 6)
            pdf.rotate(lab_angle)
            pdf.drawRightString(0, -lab_size * 0.75, str(label))   # ends at its tick, slopes down-left
            pdf.restoreState()
        else:
            pdf.drawCentredString(cx, gy - 6 - lab_size, str(label))
        if rate_row:
            pdf.setFillColor(MUTED)   # the same grey as the row's label
            pdf.setFont(REG, rate_size)
            if rate_angle:
                pdf.saveState()
                pdf.translate(cx + rate_size * 0.3, rate_y)
                pdf.rotate(rate_angle)
                pdf.drawRightString(0, -rate_size * 0.75, str(rate_row[1][i]))
                pdf.restoreState()
            else:
                pdf.drawCentredString(cx, rate_y, str(rate_row[1][i]))
    # Trend line through the bar totals (the user's "เส้นแนวโน้ม" switch on the web).
    if data.get("overview_trend") and len(tops) >= 2:
        pdf.setStrokeColor(TREND_COLOR)
        pdf.setLineWidth(1.2)
        path = pdf.beginPath()
        path.moveTo(*tops[0])
        for pt in tops[1:]:
            path.lineTo(*pt)
        pdf.drawPath(path, stroke=1, fill=0)
        pdf.setFillColor(TREND_COLOR)
        for (px, py) in tops:
            pdf.circle(px, py, 2.2, stroke=0, fill=1)
    # Value on top of the bar: small and muted so a full year stays readable;
    # dropped entirely once the bars get too narrow to carry a number.
    if n <= 18:
        pdf.setFont(REG, 6.5)
        for i, (px, py) in enumerate(tops):
            txt = _format_number(totals[i])
            if data.get("overview_trend"):   # keep the number readable where the line crosses it
                tw = stringWidth(txt, REG, 6.5)
                pdf.setFillColor(WHITE)
                pdf.roundRect(px - tw / 2.0 - 2, py + 2.5, tw + 4, 8, 2, stroke=0, fill=1)
            pdf.setFillColor(MUTED)
            pdf.drawCentredString(px, py + 4, txt)


def _stacked_area_chart(pdf, x, y, w, h, labels, series, data):
    """Daily view: the series stacked as bands, bottom → top."""
    left_pad, right_pad, top_pad, bottom_pad = 64, 18, 22, 30
    gx, gy = x + left_pad, y + bottom_pad
    gw, gh = w - left_pad - right_pad, h - bottom_pad - top_pad
    n = len(labels)
    totals = [sum(sv[2][i] for sv in series) for i in range(n)]
    if not n or gw <= 0 or gh <= 0 or max(totals or [0]) <= 0:
        pdf.setFillColor(MUTED)
        pdf.setFont(REG, 10)
        pdf.drawCentredString(x + w / 2.0, y + h / 2.0, _t('no_data', data))
        return
    top_val = _nice_top(max(totals) * 1.08)
    pdf.setLineWidth(0.5)
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        yt = gy + frac * gh
        pdf.setStrokeColor(STROKE)
        pdf.line(gx, yt, gx + gw, yt)
        pdf.setFillColor(MUTED)
        pdf.setFont(REG, 8)
        pdf.drawRightString(gx - 6, yt - 3, _tick_label(top_val * frac))
    pdf.drawRightString(gx - 6, gy + gh + 8, _t('kg', data))
    step = gw / max(1, n - 1) if n > 1 else 0
    xs = [gx + (i * step if n > 1 else gw / 2.0) for i in range(n)]

    def ypos(v):
        return gy + v / top_val * gh

    lower = [0.0] * n
    for _name, col, vals in series:
        upper = [lower[i] + vals[i] for i in range(n)]
        path = pdf.beginPath()
        path.moveTo(xs[0], ypos(lower[0]))
        for i in range(n):
            path.lineTo(xs[i], ypos(upper[i]))
        for i in range(n - 1, -1, -1):
            path.lineTo(xs[i], ypos(lower[i]))
        path.close()
        pdf.setFillColor(col)
        pdf.drawPath(path, stroke=0, fill=1)
        lower = upper
    pdf.setStrokeColor(colors.HexColor("#7fb49d"))
    pdf.setLineWidth(1)
    line = pdf.beginPath()
    for i in range(n):
        (line.moveTo if i == 0 else line.lineTo)(xs[i], ypos(totals[i]))
    pdf.drawPath(line, stroke=1, fill=0)
    # ~8 evenly spaced date labels
    pdf.setFillColor(TEXT)
    pdf.setFont(REG, 8)
    every = max(1, int(math.ceil(n / 8.0)))
    for i in range(0, n, every):
        pdf.drawCentredString(xs[i], gy - 14, labels[i])


def _fit_legend(pdf, right_x, y, entries, max_w, full_w=None):
    """Legend swatches, right-aligned, full names (never truncated).

    One line beside the chart title when it fits in max_w at a readable size; otherwise the
    legend wraps onto rows of up to full_w under the title. Returns the y of the lowest row,
    so the caller can start the chart below it.
    """
    gap = 27   # swatch (9) + gaps around it

    def item_w(nm, sz):
        return stringWidth(nm, REG, sz) + gap

    def draw_row(row, row_y, sz):
        pdf.setFont(REG, sz)
        cur = right_x
        for (label, col) in reversed(row):
            cur -= stringWidth(label, REG, sz)
            pdf.setFillColor(TEXT)
            pdf.drawString(cur, row_y, label)
            cur -= 13
            pdf.setFillColor(col)
            pdf.roundRect(cur, row_y, 9, 9, 2, stroke=0, fill=1)
            cur -= 14

    size = 8.5
    while size > 7.5 and sum(item_w(e[0], size) for e in entries) > max_w:
        size -= 0.5
    if not entries or sum(item_w(e[0], size) for e in entries) <= max_w or not full_w:
        draw_row(list(entries), y, size)
        return y
    # Wrap under the title in BALANCED rows (7 items → 4 + 3, not 6 + 1), each right-aligned:
    # start from the fewest rows the total width needs and add rows until every row fits.
    size = 8
    items = [(_fit_text_to_width(nm, REG, size, full_w - gap), col) for nm, col in entries]
    n_rows = max(2, math.ceil(sum(item_w(nm, size) for nm, _c in items) / full_w))
    while True:
        per = math.ceil(len(items) / n_rows)
        rows = [items[i:i + per] for i in range(0, len(items), per)]
        if per == 1 or all(sum(item_w(nm, size) for nm, _c in r) <= full_w for r in rows):
            break
        n_rows += 1
    row_y = y
    for r in rows:
        row_y -= 14
        draw_row(r, row_y, size)
    return row_y


def _rate_title_value(data: dict) -> tuple:
    """Recycling rate (or the separation rate when the scope has no measured rate)."""
    ki = (data.get("overview_data", {}) or {}).get("key_indicators", {}) or {}
    rr_raw = ki.get("recycle_rate")
    if rr_raw is not None:
        return _t('chip_recycling_rate', data), f"{float(rr_raw):.2f}"
    sep = ki.get("separation_rate")
    return _t('chip_separation_rate', data), (f"{float(sep):.2f}" if sep is not None else "—")


def draw_overview(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    """Overview (original layout): transaction chips, key indicators, the top list for the
    report mode, and the "Overall" card with the impact figures and the waste chart."""
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, _t('overview', data))
    margin = 0.78 * inch
    content_top = page_height_points - (1.96 * inch) - 24
    col_gap = 0.25 * inch
    left_col_w = 3.7 * inch
    right_col_w = page_width_points - margin - margin - left_col_w - col_gap
    chip_w = 1.78 * inch
    chip_h = 0.60 * inch
    chip_y = content_top - chip_h
    chip_gap = 8
    ov = data.get("overview_data", {}) or {}
    ki = ov.get("key_indicators", {}) or {}
    impact = _impact_values(data)
    try:
        tx_total_text = f"{int(float(ov.get('transactions_total') or 0)):,}"
    except Exception:
        tx_total_text = str(ov.get("transactions_total", "0"))
    try:
        tx_approved_text = f"{int(float(ov.get('transactions_approved') or 0)):,}"
    except Exception:
        tx_approved_text = str(ov.get("transactions_approved", "0"))
    _stat_chip(pdf, margin, chip_y, chip_w, chip_h, _t('total_transactions', data), tx_total_text)
    _stat_chip(pdf, margin + chip_w + chip_gap, chip_y, chip_w, chip_h, _t('total_approved', data), tx_approved_text)

    # Key indicators: every bar is a share of the total waste of the selected sources
    # (total = 100%). Like the dashboard card: the label on its own line, then the value on
    # the left and the share on the right, then the bar.
    ki_h = 184           # three stacked rows + the share note
    ki_y = chip_y - 8 - ki_h
    _rounded_card(pdf, margin, ki_y, left_col_w, ki_h, radius=8)
    pad = 28
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Medium", 12)
    pdf.drawString(margin + pad, ki_y + ki_h - 30, _t('key_indicators', data))
    tw = float(ki.get("total_waste", 0) or 0)
    recycled = float(impact.get("recycled_kg") or 0)
    plastic = float(impact.get("plastic_saved_kg") or 0)
    row_w = left_col_w - 2 * pad
    row_x = margin + pad
    row_y = ki_y + ki_h - 50
    ki_rows = [
        ('total_waste_kg', tw, "#84b8a3"),
        ('total_recyclables_kg', recycled, "#9ac7b5"),
        ('plastic_saved_kg', plastic, "#b6d7c9"),
    ]
    for i, (key, val, color) in enumerate(ki_rows):
        share = (val / tw) if tw > 0 else 0.0
        top = row_y - 2 - 40 * i
        pdf.setFillColor(MUTED)
        pdf.setFont(REG, 9)
        pdf.drawString(row_x, top, _fit_text_to_width(_t(key, data), REG, 9, row_w))
        pdf.setFillColor(TEXT)
        pdf.setFont(MED, 8)   # value and share the same size (was 12 / 10)
        pdf.drawString(row_x, top - 14, _format_number(val))
        pdf.setFillColor(colors.HexColor("#2f8f6b"))
        pdf.setFont(MED, 8)
        pdf.drawRightString(row_x + row_w, top - 14, f"{share * 100:.2f}%")
        _progress_bar(pdf, row_x, top - 27, row_w, 5, min(1.0, share), colors.HexColor(color), colors.HexColor("#e1e7ef"))
    pdf.setFillColor(MUTED)
    pdf.setFont(REG, 7.5)
    pdf.drawString(row_x, ki_y + 11, _fit_text_to_width(_t('key_indicators_share_note', data), REG, 7.5, row_w))

    # Top list: locations, tags ("activities") or tenants, following the report mode.
    mode = data.get("report_mode") or "location"
    tr_h = 132           # three rows; shorter so the taller key-indicator card still fits the page
    tr_y = ki_y - 8 - tr_h
    _rounded_card(pdf, margin, tr_y, left_col_w, tr_h, radius=8)
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Medium", 12)
    title_key = {'tag': 'top_recyclables_tag', 'tenant': 'top_recyclables_tenant'}.get(mode, 'top_recyclables')
    pdf.drawString(margin + pad, tr_y + tr_h - 30, _t(title_key, data))
    items = (ov.get("top_recyclables") or [])[:3]
    if items:
        max_val = max(float(it.get("total_waste", 0) or 0) for it in items) or 1.0
        y_ptr = tr_y + tr_h - 64
        for it in items:
            name = _fit_text_to_width(str(it.get("origin_name", "")), REG, 10, left_col_w - 2 * pad - 90)
            val = float(it.get("total_waste", 0) or 0)
            _label_progress(pdf, margin + pad, y_ptr, left_col_w - 2 * pad, name, _format_number(val), val / max_val, colors.HexColor("#c8ced4"), colors.HexColor("#e1e7ef"), bar_h=6)
            y_ptr -= 29
    else:
        pdf.setFillColor(MUTED)
        pdf.setFont(REG, 9.5)
        pdf.drawString(margin + pad, tr_y + tr_h - 64, _t('no_data', data))

    # Overall card: recycle rate, GHG, trees, waste per head — then the chart.
    overall_x = margin + left_col_w + col_gap
    overall_y = tr_y
    overall_h = (chip_y - overall_y) + chip_h
    _rounded_card(pdf, overall_x, overall_y, right_col_w, overall_h, radius=8, fill=WHITE)
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Medium", 12)
    pdf.drawString(overall_x + 16, overall_y + overall_h - 30, _t('overall', data))
    # Title on top, unit on the line under the value (no units in brackets in the title).
    rate_title, rate_value = _rate_title_value(data)
    per_head = impact.get("waste_per_head")
    headcount = impact.get("headcount")
    kg_short = _t('unit_kg_short', data)
    if headcount:
        try:
            per_head_sub = _t('per_head_unit', data).replace('{count}', f"{int(headcount):,}")
        except (TypeError, ValueError):
            per_head_sub = kg_short
    else:
        per_head_sub = _t('no_headcount', data)   # value is "—", so no unit to show
    stats = [
        (rate_title, rate_value, _t('unit_percent', data)),
        (_t('chip_ghg_reduction', data), _format_number(ki.get("ghg_reduction", 0) or 0), _t('unit_kgco2e', data)),
        (_t('chip_tree_equivalent', data), f"{int(round(float(impact.get('trees') or 0))):,}", _t('unit_trees', data)),
        (_t('chip_waste_per_head', data), _format_number(per_head) if per_head is not None else "—", per_head_sub),
    ]
    gap = 8
    sw = (right_col_w - 32 - gap * 3) / 4
    sh = 0.72 * inch
    sy = overall_y + overall_h - 26 - 16 - sh
    for i, (title, value, sub) in enumerate(stats):
        _stat_chip(pdf, overall_x + 16 + i * (sw + gap), sy, sw, sh, title, value, "white", subtitle=sub)

    gran, labels, series, rate_row = _chart_series(data)
    legend_y = sy - 18
    pdf.setFillColor(TEXT)
    pdf.setFont(MED, 10)
    title = _t(f'chart_{gran}', data)
    pdf.drawString(overall_x + 16, legend_y, title)
    title_w = stringWidth(title, MED, 10)
    legend_bottom = _fit_legend(pdf, overall_x + right_col_w - 16, legend_y, [(nm, col) for nm, col, _v in series],
                                right_col_w - 32 - title_w - 20, full_w=right_col_w - 32)
    cy = overall_y + 10
    ch = legend_bottom - 10 - cy
    if gran == "daily":
        _stacked_area_chart(pdf, overall_x + 8, cy, right_col_w - 16, ch, labels, series, data)
    else:
        _stacked_month_chart(pdf, overall_x + 8, cy, right_col_w - 16, ch, labels, series, rate_row, data)
    _footer(pdf, page_width_points, data)

def draw_overview_breakdown(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    """
    Overview breakdown page:
    - Left: Category proportion pie with legend
    - Right: Materials Summary table (Category, Weight (kg.), Proportion (%))
    Uses data['overview_data']['waste_type_proportions'] (or top-level 'waste_type_proportions').
    """
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, _t('overview', data))
    margin = 0.78 * inch
    # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
    content_top = page_height_points - (1.96 * inch) - 24
    gap = 0.3 * inch
    left_w = 3.7 * inch
    right_w = page_width_points - 2 * margin - left_w - gap
    card_h = 5.2 * inch
    card_y = content_top - card_h
    left_x = margin
    right_x = margin + left_w + gap
    # Left card: Category proportion
    _rounded_card(pdf, left_x, card_y, left_w, card_h, radius=8, fill=WHITE)
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Medium", 12)
    pdf.drawString(left_x + 16, card_y + card_h - 24, _t('category_proportion', data))
    # Recycling rate on this page too: customers often forward this one page on its own.
    rate_title, rate_value = _rate_title_value(data)
    rate_text = f"{rate_value} %" if rate_value != "—" else rate_value
    rv_w = stringWidth(rate_text, MED, 12)
    pdf.setFillColor(colors.HexColor("#2f8f6b"))
    pdf.setFont(MED, 12)
    pdf.drawString(left_x + left_w - 16 - rv_w, card_y + card_h - 24, rate_text)
    pdf.setFillColor(MUTED)
    pdf.setFont(REG, 8.5)
    rt_w = stringWidth(rate_title, REG, 8.5)
    pdf.drawString(left_x + left_w - 16 - rv_w - 6 - rt_w, card_y + card_h - 23, rate_title)
    # Resolve items
    wt_props = (data.get("overview_data", {}).get("waste_type_proportions")
                or data.get("waste_type_proportions") or [])
    # Normalize list of dicts with 'category_name', 'total_waste' and 'proportion_percent'
    items = []
    for it in (wt_props or []):
        try:
            name = str(it.get("category_name") or it.get("name") or it.get("category") or "")
            # Color is keyed by the ENGLISH category name; category_name may be translated for display.
            color_key = str(it.get("category_name_en") or it.get("name_en") or name)
            total = float(it.get("total_waste", it.get("value", 0)) or 0)
            perc = it.get("proportion_percent")
            perc = float(perc) if perc is not None else None
            items.append({"name": name, "color_key": color_key, "total": total, "perc": perc})
        except Exception:
            continue
    # Fallback example if empty
    if not items:
        items = [{"name": _t('general_waste', data), "color_key": "General Waste", "total": 1.0, "perc": 100.0}]
    # Values for pie: prefer totals; if all totals are zero, use percents or 1
    totals_sum = sum(max(0.0, it["total"]) for it in items)
    if totals_sum <= 0:
        values = [max(0.0, (it["perc"] or 0)) for it in items] or [1.0]
    else:
        values = [max(0.0, it["total"]) for it in items]
    colors_list = []
    for it in items:
        c = MATERIAL_COLORS.get(it.get("color_key") or it["name"], None)
        if c is None:
            c = colors.HexColor("#cfe2f3")
        colors_list.append(c)
    # Draw pie
    pie_size = 1.8 * inch  # slightly smaller
    # center horizontally inside the left card
    pie_x = left_x + (left_w - pie_size) / 2.0
    # move pie up a little
    pie_y = card_y + card_h - 40 - pie_size
    _simple_pie_chart(pdf, pie_x, pie_y, pie_size, values, colors_list, gap_width=1, gap_color=colors.white)
    # Legend on left bottom
    legend_x = left_x + 16
    legend_y_start = pie_y - 24
    row_h = 22  # add more gap between legend rows
    pdf.setFont("IBMPlexSansThai-Regular", 10)
    for i, it in enumerate(items[:10]):
        y = legend_y_start - (i * row_h)
        box_c = colors_list[i % len(colors_list)]
        pdf.setFillColor(box_c)
        # move legend square up a bit to align vertically with text
        pdf.roundRect(legend_x, y - 1, 8, 8, 2, stroke=0, fill=1)
        pdf.setFillColor(TEXT)
        pdf.drawString(legend_x + 12, y, it["name"])
        # percent display to the far right inside card
        perc_val = it["perc"]
        if perc_val is None:
            try:
                perc_val = (it["total"] / totals_sum * 100.0) if totals_sum > 0 else 0.0
            except Exception:
                perc_val = 0.0
        disp = f"{_format_number(perc_val)} %"
        dw = stringWidth(disp, "IBMPlexSansThai-Regular", 10)
        pdf.drawString(left_x + left_w - 16 - dw, y, disp)
    # Right card: Materials Summary table
    _rounded_card(pdf, right_x, card_y, right_w, card_h, radius=8, fill=WHITE)
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Medium", 12)
    pdf.drawString(right_x + 16, card_y + card_h - 24, _t('materials_summary', data))
    # Header
    header_y = card_y + card_h - 58
    pdf.setFillColor(colors.HexColor("#f5faf8"))
    draw_table(pdf, right_x + 12, header_y, right_w - 24, 24, 8, "Header")
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Medium", 9)
    col_w = (right_w - 24) / 3.0
    hx = right_x + 12
    hy = header_y + 9
    pdf.drawString(hx + 10, hy, _t('category', data))
    # Right-align the headers for Weight and Proportion to match value alignment
    _hdr_weight = _t('weight_kg', data)
    _hdr_weight_w = stringWidth(_hdr_weight, "IBMPlexSansThai-Medium", 9)
    pdf.drawString(hx + 2 * col_w - 10 - _hdr_weight_w, hy, _hdr_weight)
    _hdr_prop = _t('proportion_pct', data)
    _hdr_prop_w = stringWidth(_hdr_prop, "IBMPlexSansThai-Medium", 9)
    pdf.drawString(hx + 3 * col_w - 10 - _hdr_prop_w, hy, _hdr_prop)
    # Rows: at most 8; anything beyond is folded into one "other" row rather than dropped.
    max_rows = 8
    row_h = 32
    rows = list(items)
    if len(rows) > max_rows:
        rest = rows[max_rows - 1:]
        rest_total = sum(r["total"] for r in rest)
        rest_perc = sum((r["perc"] or 0) for r in rest) if all(r["perc"] is not None for r in rest) else None
        rows = rows[:max_rows - 1] + [{"name": _t('others', data), "color_key": "", "total": rest_total, "perc": rest_perc}]
    for i, it in enumerate(rows):
        y_row = header_y - row_h - i * row_h
        table_type = "Body"
        row_bg = WHITE if (i % 2 == 0) else colors.HexColor("#f5faf8")
        pdf.setFillColor(row_bg)
        draw_table(pdf, right_x + 12, y_row, right_w - 24, row_h, 8, table_type)
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Regular", 9)
        y_text = y_row + 12
        # category name
        pdf.drawString(hx + 10, y_text, it["name"])
        # weight
        w_text = _format_number(it["total"])
        w_w = stringWidth(w_text, "IBMPlexSansThai-Regular", 9)
        pdf.drawString(hx + col_w + col_w - 10 - w_w, y_text, w_text)
        # percent
        perc_val = it["perc"]
        if perc_val is None:
            try:
                perc_val = (it["total"] / totals_sum * 100.0) if totals_sum > 0 else 0.0
            except Exception:
                perc_val = 0.0
        p_text = f"{_format_number(perc_val)} %"
        p_w = stringWidth(p_text, "IBMPlexSansThai-Regular", 9)
        pdf.drawString(hx + 3 * col_w - 10 - p_w, y_text, p_text)
    # Total row
    y_tot = header_y - row_h - len(rows) * row_h
    pdf.setFillColor(colors.HexColor("#eaf3ef"))
    draw_table(pdf, right_x + 12, y_tot, right_w - 24, row_h, 8, "Footer")
    pdf.setFillColor(TEXT)
    pdf.setFont(MED, 9)
    pdf.drawString(hx + 10, y_tot + 12, _t('total', data))
    t_text = _format_number(sum(it["total"] for it in items))
    pdf.drawString(hx + 2 * col_w - 10 - stringWidth(t_text, MED, 9), y_tot + 12, t_text)
    tp_text = "100.00 %"
    pdf.drawString(hx + 3 * col_w - 10 - stringWidth(tp_text, MED, 9), y_tot + 12, tp_text)
    _footer(pdf, page_width_points, data)
def _perf_labels(data: dict) -> dict:
    """Titles for the performance pages by report mode (location / tag / tenant)."""
    mode = data.get("report_mode") or "location"
    if mode == "tenant":
        return {'all': _t('all_tenants', data), 'list': _t('tenant_list', data), 'pie': _t('share_by_tenant', data),
                'unassigned': _t('no_tenant', data), 'name_col': _t('tenant_name', data)}
    if mode == "tag":
        return {'all': _t('all_tags', data), 'list': _t('tag_list', data), 'pie': _t('share_by_tag', data),
                'unassigned': _t('no_tag', data), 'name_col': _t('tag_name', data)}
    return {'all': None, 'list': _t('all_building', data), 'pie': _t('total_buildings', data),
            'unassigned': None, 'name_col': _t('building_name', data)}


def draw_performance(pdf, page_width_points: float, page_height_points: float, data: dict, performance_data: dict) -> None:
    labels = _perf_labels(data)
    performance_data = dict(performance_data)
    if not performance_data.get('branchName'):
        performance_data['branchName'] = labels['all'] or ''
    # The building list ("ทุกอาคาร") can hold more rows than fit on one page. When it overflows we
    # paginate the list across multiple pages; each page REPEATS the left card (recycle rate +
    # per-type bars) and BOTH pie charts (full-data, unchanged) and shows only its slice of buildings.
    buildings = [
        dict(b, buildingName=b.get("buildingName") or labels['unassigned'] or str(b.get("id", "")))
        for b in (performance_data.get("buildings", []) or [])
    ]
    has_buildings = bool(buildings and isinstance(buildings, list) and len(buildings) > 0)
    _max_waste = 0.0
    if has_buildings:
        buildings = sorted(buildings, key=lambda b: float(b.get("totalWasteKg", 0) or 0), reverse=True)
        # Bars are scaled against the biggest building, not the origin total, so the top row is full.
        _max_waste = float(buildings[0].get("totalWasteKg", 0) or 0)

    # Assign per-building colors ONCE for the whole dataset so the list rows and the (full-data)
    # pie chart agree across every page. Computed up front, before the page loop.
    _assigned_colors = []
    if has_buildings:
        try:
            import random as _rand
            _palette = [colors.HexColor(c) for c in (BuildingColors or [])]
            if _palette:
                _shuffled = _palette[:]
                _rand.shuffle(_shuffled)
                _assigned_colors = [_shuffled[i % len(_shuffled)] for i in range(len(buildings))]
        except Exception:
            _assigned_colors = []

    # Rows per page: the list area runs from ~0.85in below the card top down to the card bottom,
    # at 0.55in per row. 7 rows fit comfortably while leaving room for the last row's progress bar.
    BUILDINGS_PER_PAGE = 7
    if has_buildings:
        _chunks = [buildings[i:i + BUILDINGS_PER_PAGE] for i in range(0, len(buildings), BUILDINGS_PER_PAGE)]
    else:
        _chunks = [[]]

    for _page_idx, _chunk in enumerate(_chunks):
        _chunk_start = _page_idx * BUILDINGS_PER_PAGE
        pdf.showPage()
        _header(pdf, page_width_points, page_height_points, data)
        _sub_header(pdf, page_width_points, page_height_points, data, _t('performance', data))
        margin = 0.78 * inch
        # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
        content_top = page_height_points - (1.96 * inch) - 24
        left_card_w = 3.22 * inch
        left_card_h = 5.0 * inch
        left_card_y = content_top - left_card_h
        _rounded_card(pdf, margin, left_card_y, left_card_w, left_card_h, radius=8, fill=WHITE)
        pdf.setFillColor(TEXT)
        # Recycle-rate block (right-aligned, ends at 3.82in). Compute its widths FIRST so the org name
        # on the left can be truncated to the free space before it — long names used to overlap it.
        label_text = _t('recycling_rate', data)
        label_width = stringWidth(label_text, "IBMPlexSansThai-Medium", 8)
        value_text = f"{_format_number(performance_data['recyclingRatePercent'])} %"
        value_width = stringWidth(value_text, "IBMPlexSansThai-Medium", 13)
        rate_block_left = 3.82 * inch - max(label_width, value_width)

        # Org / branch name (left) — bounded to the space before the recycle-rate block (6pt gap).
        pdf.setFont("IBMPlexSansThai-Medium", 12)
        name_max_w = rate_block_left - (1 * inch) - 6
        branch_name = _fit_text_to_width(str(performance_data.get('branchName', '')), "IBMPlexSansThai-Medium", 12, name_max_w)
        pdf.drawString(1 * inch, content_top - 0.4 * inch - 4, branch_name)

        pdf.setFont("IBMPlexSansThai-Regular", 8)
        pdf.drawString(3.82 * inch - label_width, content_top - 0.27 * inch - 4, label_text)
        pdf.setFont("IBMPlexSansThai-Bold", 13)
        pdf.drawString(3.82 * inch - value_width, content_top - 0.52 * inch - 4, value_text)
        # Progress bars section (first: Total Waste at 100%)
        start_y = content_top - 1.2 * inch
        bar_h = 0.08 * inch
        gap = 0.36 * inch
        # Draw Total Waste as a full bar
        total_waste_val = float(performance_data.get("totalWasteKg", 0) or 0)
        y_total = start_y
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Regular", 10)
        pdf.drawString(1 * inch, y_total + bar_h + 0.12 * inch, _t('total_waste', data))
        total_text = f"{_format_number(total_waste_val)} {_t('kg', data)}"
        total_text_w = stringWidth(total_text, "IBMPlexSansThai-Regular", 10)
        pdf.drawString(1 * inch + 2.8 * inch - total_text_w, y_total + bar_h + 0.12 * inch, total_text)
        _progress_bar(pdf, 1 * inch, y_total, 2.8 * inch, bar_h, 1.0, colors.HexColor("#c5d2da"))
        # Subsequent bars for individual waste types, largest first (as on the dashboard)
        _metrics = sorted((performance_data.get("metrics") or {}).items(), key=lambda kv: -float(kv[1] or 0))
        for idx, (label, amount) in enumerate(_metrics):
            y = start_y - (idx + 1) * (bar_h + gap)
            pdf.setFillColor(TEXT)
            pdf.setFont("IBMPlexSansThai-Regular", 10)
            _cat_map = (data or {}).get('labels', {}).get('_category_map', {})
            display_label = _cat_map.get(label, label)
            pdf.drawString(1 * inch, y + bar_h + 0.12 * inch, display_label)
            value_text = f"{_format_number(amount)} {_t('kg', data)}"
            value_width = stringWidth(value_text, "IBMPlexSansThai-Regular", 10)
            pdf.drawString(1 * inch + 2.8 * inch - value_width, y + bar_h + 0.12 * inch, value_text)
            _progress_bar(pdf, 1 * inch, y, 2.8 * inch, bar_h, (float(amount or 0) / total_waste_val) if total_waste_val > 0 else 0.0,
                          MATERIAL_COLORS.get(label, colors.HexColor("#cfe2f3")))
        gap = 1 * inch
        outer_x = gap + 3.22 * inch
        outer_y = left_card_y
        outer_w = 6.8 * inch
        outer_h = 5.0 * inch
        _rounded_card(pdf, outer_x, outer_y, outer_w, outer_h, radius=8, fill=WHITE)
        pad = 16
        inner_x = outer_x + pad
        inner_y = outer_y + pad
        inner_w = outer_w - 2 * pad
        inner_h = outer_h - 2 * pad
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Medium", 12)
        _all_building_title = labels['list']
        # When paginated, tag the section title with the page number so it's clear more follows.
        if len(_chunks) > 1:
            _lang = data.get('language', 'en') or 'en'
            if _lang == 'th':
                _pg = f"หน้าที่ {_page_idx + 1} จาก {len(_chunks)}"
            else:
                _pg = f"Page {_page_idx + 1} of {len(_chunks)}"
            _all_building_title = f"{_all_building_title} ({_pg})"
        pdf.drawString(inner_x + 16, inner_y + inner_h - 16 - 12, _all_building_title)
        pdf.setFont("IBMPlexSansThai-Regular", 10)

        pie_size = 1.20 * inch
        pie_x = inner_x + inner_w - pie_size - 16
        title1_y = inner_y + inner_h - 48

        if not has_buildings:
            # No sub-origins under this origin: explain where the building list would be,
            # and skip the (empty) building pie so the material pie moves up into its slot.
            _lang = data.get('language', 'en') or 'en'
            _origin_name = str(performance_data.get('branchName', '')).strip()
            if _lang == 'th':
                _msg = f"ไม่มีแหล่งกำเนิดของเสียอยู่ภายใต้แหล่งกำเนิด ({_origin_name})"
            else:
                _msg = f"No waste sources under origin ({_origin_name})"
            no_data_y = inner_y + inner_h - 0.85 * inch
            pdf.setFillColor(colors.HexColor("#666666"))
            pdf.setFont("IBMPlexSansThai-Regular", 10)
            # Keep the message clear of the pie column on the right.
            _msg_max_w = pie_x - (inner_x + 16) - 6
            _msg = _fit_text_to_width(_msg, "IBMPlexSansThai-Regular", 10, _msg_max_w)
            pdf.drawString(inner_x + 16, no_data_y, _msg)
        else:
            for local_idx, building in enumerate(_chunk):
                abs_idx = _chunk_start + local_idx
                y = inner_y + inner_h - 0.85 * inch - local_idx * (0.55 * inch)
                pdf.setFillColor(TEXT)
                value_text = f"{_format_number(building.get('totalWasteKg', 0))} kg"
                value_width = stringWidth(value_text, "IBMPlexSansThai-Regular", 8)
                _val_x = inner_x + 4 * inch - value_width
                _name_left = inner_x + 16
                # Bound the building name to the space before the right-aligned kg value (6pt gap).
                _bname = _fit_text_to_width(building.get("buildingName", ""), "IBMPlexSansThai-Regular", 10, _val_x - _name_left - 6)
                pdf.drawString(_name_left, y, _bname)
                pdf.drawString(_val_x, y, value_text)
                _color = _assigned_colors[abs_idx] if abs_idx < len(_assigned_colors) else colors.HexColor("#b7cbd6")
                if _max_waste > 0:
                    _progress_bar(pdf, inner_x + 16, y - 0.2 * inch, inner_x - 0.5 * inch, 0.08 * inch, float(building.get('totalWasteKg', 0) or 0) / _max_waste, _color)

        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Regular", 10)

        if has_buildings:
            # Building pie (only meaningful when there are sub-origins to break down).
            pdf.drawString(pie_x, title1_y, labels['pie'])
            buildings_values = [float(b.get("totalWasteKg", 0) or 0) for b in buildings]
            if _assigned_colors:
                building_colors_for_pie = [_assigned_colors[i % len(_assigned_colors)] for i in range(len(buildings_values))]
            else:
                mono_color = colors.HexColor("#b7cbd6")
                building_colors_for_pie = [mono_color for _ in buildings_values] or [mono_color]
            _simple_pie_chart(pdf, pie_x, title1_y - 8 - pie_size, pie_size, buildings_values, building_colors_for_pie, gap_width=1, gap_color=colors.white)
            # Material pie sits below the building pie.
            title2_y = title1_y - pie_size - 52
        else:
            # No building pie — the material pie takes the top slot.
            title2_y = title1_y
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Regular", 10)
        pdf.drawString(pie_x, title2_y, _t('all_types_of_waste', data))
        metrics_items = list(performance_data.get("metrics", {}).items())
        waste_values = [float(v or 0) for _, v in metrics_items]
        waste_colors = [MATERIAL_COLORS.get(lbl, BAR3) for lbl, _ in metrics_items]
        if not waste_colors:
            waste_colors = SERIES_COLORS
        _simple_pie_chart(pdf, pie_x, title2_y - 8 - pie_size, pie_size, waste_values, waste_colors, gap_width=1, gap_color=colors.white)
        _footer(pdf, page_width_points, data)

def draw_performance_table(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    branches_per_page = 7
    labels = _perf_labels(data)
    # Location: one row per top-level location. Tag / tenant: one row per group.
    if (data.get("report_mode") or "location") != "location":
        rows_src = [dict(g, branchName=g.get("branchName") or labels['unassigned']) for g in (data.get("performance_groups") or [])]
        # Tag / tenant lists run long (dozens of tenants); 10 rows still clear the footer.
        branches_per_page = 10
    else:
        rows_src = data.get("performance_data") or []
    total_branches = len(rows_src)
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Assets", "BranchIcon.png")
    icon_size = 10
    for page_idx in range(0, total_branches, branches_per_page):
        pdf.showPage()
        _header(pdf, page_width_points, page_height_points, data)
        _sub_header(pdf, page_width_points, page_height_points, data, _t('performance', data))
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Medium", 12)
        pdf.drawString(padding, page_height_points - (2.5 * inch), _t('detailed_performance_metrics', data))
        pdf.setFillColor(colors.HexColor("#f5faf8"))
        draw_table(pdf, padding, page_height_points - (3 * inch), page_width_points - 2 * padding, 24, 8, "Header")
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Medium", 9)
        # Column bands [start, end) from the left edge of the table. The name is left-aligned;
        # every other header AND its values are centred on the same x, so they line up.
        _table_w = page_width_points - 2 * padding
        _bands = {
            'total': (1.8 * inch, 3.2 * inch),
            'general': (3.2 * inch, 4.4 * inch),
            'recyclable': (4.4 * inch, 7.7 * inch),
            'rate': (7.7 * inch, 9.1 * inch),
            'status': (9.1 * inch, _table_w),
        }
        _cx = {k: padding + (a + b) / 2.0 for k, (a, b) in _bands.items()}
        _hy = page_height_points - (2.88 * inch)
        pdf.drawString(padding + 16, _hy, labels['name_col'])
        pdf.drawCentredString(_cx['total'], _hy, _t('total_waste_kg', data))
        pdf.drawCentredString(_cx['general'], _hy, _t('general_kg', data))
        pdf.drawCentredString(_cx['recyclable'], _hy, _t('total_recyclable_incl', data))
        pdf.drawCentredString(_cx['rate'], _hy, _t('recycling_rate_pct_header', data))
        pdf.drawCentredString(_cx['status'], _hy, _t('status', data))
        page_branches = rows_src[page_idx:page_idx + branches_per_page]
        for idx, branch in enumerate(page_branches):
            y_base = page_height_points - (3 * inch) - 32 - (idx * 32)
            table_type = "Footer" if idx == len(page_branches) - 1 else "Body"
            # Alternating row background starting with white
            row_bg = WHITE if (idx % 2 == 0) else colors.HexColor("#f5faf8")
            pdf.setFillColor(row_bg)
            draw_table(pdf, padding, y_base, page_width_points - 2 * padding, 32, 8, table_type)
            pdf.setFillColor(TEXT)
            pdf.setFont("IBMPlexSansThai-Regular", 9)
            y_text = y_base + 12
            pdf.drawImage(icon_path, padding + 16, y_base + 11, width=icon_size, height=icon_size, mask='auto')
            # Bound the name to the space before the first numeric column (total_waste at +1.8in).
            _bn = _fit_text_to_width(branch["branchName"], "IBMPlexSansThai-Regular", 9,
                                     (padding + 1.8 * inch) - (padding + 30) - 6)
            pdf.drawString(padding + 30, y_base + 12, _bn)
            general = branch.get("metrics", {}).get("General Waste") or 0
            recyclable = branch.get("metrics", {}).get("Recyclable Waste") or 0
            organic = branch.get("metrics", {}).get("Organic Waste") or 0
            pdf.drawCentredString(_cx['total'], y_text, _format_number(branch["totalWasteKg"]))
            pdf.drawCentredString(_cx['general'], y_text, _format_number(general))
            pdf.drawCentredString(_cx['recyclable'], y_text, _format_number(recyclable + organic))
            pdf.drawCentredString(_cx['rate'], y_text, f"{_format_number(branch['recyclingRatePercent'])} %")
            ok = branch["recyclingRatePercent"] > 20
            status_txt = _t('status_normal', data) if ok else _t('status_need_imprv', data)
            circle_radius = 3.5
            st_w = stringWidth(status_txt, "IBMPlexSansThai-Regular", 9)
            group_w = 2 * circle_radius + 5 + st_w
            st_x = _cx['status'] - group_w / 2.0
            pdf.setFillColor(colors.HexColor("#0bb980") if ok else colors.HexColor("#f49d0d"))
            pdf.circle(st_x + circle_radius, y_text + 3, circle_radius, stroke=0, fill=1)
            pdf.drawString(st_x + 2 * circle_radius + 5, y_text, status_txt)
        _footer(pdf, page_width_points, data)

def _advice_item_text(itm: dict, lang: str, bullet_type: str):
    """(title, bullets, reason) from a recommendation item. Reads the rules-engine shape
    and, for a render lambda deployed ahead of the platform lambda, the old CSV shape."""
    title = str(itm.get(f"title_{lang}") or itm.get(f"condition_name_{lang}") or itm.get("condition_name") or "").replace("_", " ").strip()
    bullets = itm.get(f"bullets_{lang}")
    if not isinstance(bullets, list):
        key = f"risk_bullets_{lang}" if bullet_type == "risk" else f"recommendation_bullets_{lang}"
        raw = str(itm.get(key) or itm.get("risk_problems" if bullet_type == "risk" else "recommendation") or "")
        bullets = [b.strip() for b in raw.split("|") if b.strip()]
    reason = str(itm.get(f"reason_{lang}") or "").strip()
    return title, [str(b) for b in bullets if str(b).strip()], reason


def draw_comparison_advice(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    """Risks / Opportunities / Quick wins, each card closing with a 'why we recommend this'
    block that quotes the numbers and threshold behind every item."""
    comparison_data = data.get("comparison_data", {}) or {}
    if comparison_data.get("error"):
        return
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, _t('comparison', data))
    margin = 0.78 * inch
    content_top = page_height_points - (1.96 * inch) - 24
    gap = 0.22 * inch
    card_w = (page_width_points - 2 * margin - 2 * gap) / 3.0
    card_y = CONTENT_BOTTOM
    card_h = content_top - card_y
    lang = data.get('language', 'en') or 'en'
    scores = comparison_data.get("scores", {}) or {}
    cards = [
        ("risk", _t('risks', data), scores.get("risks", []) or []),
        ("opportunity", _t('opportunities', data), scores.get("opportunities", []) or []),
        ("quickwin", _t('quick_wins', data), scores.get("quickwins", []) or []),
    ]
    pad = 16
    text_w = card_w - 2 * pad
    for ci, (section, title, raw_items) in enumerate(cards):
        x = margin + ci * (card_w + gap)
        _rounded_card(pdf, x, card_y, card_w, card_h, radius=10, fill=WHITE)
        pdf.setFillColor(SECTION_COLORS[section])
        pdf.circle(x + pad + 4, card_y + card_h - 22, 4, stroke=0, fill=1)
        pdf.setFillColor(TEXT)
        pdf.setFont(MED, 14)
        pdf.drawString(x + pad + 14, card_y + card_h - 27, title)

        parsed = [_advice_item_text(it, lang, "risk" if section == "risk" else "recommendation") for it in raw_items[:2]]
        parsed = [p for p in parsed if p[0] or p[1]]
        if not parsed:
            pdf.setFillColor(MUTED)
            pdf.setFont(REG, 9)
            pdf.drawString(x + pad, card_y + card_h - 52, _t('no_data', data))
            continue
        numbered = len(parsed) > 1
        avail = card_h - 44 - pad

        # Fit: fewer bullets first, then smaller type, never past the card edge.
        bullet_cap, t_size, b_size, r_size = 3, 10.5, 9.0, 8.2
        while True:
            item_blocks = []
            for n, (it_title, bullets, _r) in enumerate(parsed, 1):
                head = f"{n}. {it_title}" if numbered else it_title
                item_blocks.append(("title", _wrap_thai(head, MED, t_size, text_w), t_size + 3.2))
                for b in bullets[:bullet_cap]:
                    item_blocks.append(("bullet", _wrap_thai(b, REG, b_size, text_w - 11), b_size + 3.0))
                item_blocks.append(("gap", [], 7))
            reason_blocks = []
            for n, (_t_, _b, reason) in enumerate(parsed, 1):
                if reason:
                    txt = f"{n}. {reason}" if numbered else reason
                    reason_blocks.append(_wrap_thai(txt, REG, r_size, text_w))
            h_items = sum(len(lines) * lead if kind != "gap" else lead for kind, lines, lead in item_blocks)
            r_lead = r_size + 2.8
            h_reason = (18 + sum(len(ls) for ls in reason_blocks) * r_lead + 4 * max(0, len(reason_blocks) - 1)) if reason_blocks else 0
            if h_items + h_reason + 12 <= avail:
                break
            if bullet_cap > 1:
                bullet_cap -= 1
                continue
            if b_size > 7.8:
                t_size -= 0.4
                b_size -= 0.4
                r_size -= 0.3
                continue
            break

        # Items flow from the top.
        y = card_y + card_h - 50
        floor = card_y + pad + h_reason + 10
        for kind, lines, lead in item_blocks:
            if kind == "gap":
                y -= lead
                continue
            for li, line in enumerate(lines):
                if y < floor:
                    break
                if kind == "title":
                    pdf.setFillColor(INK)
                    pdf.setFont(MED, t_size)
                    pdf.drawString(x + pad, y, line)
                else:
                    pdf.setFillColor(TEXT)
                    pdf.setFont(REG, b_size)
                    if li == 0:
                        pdf.drawString(x + pad + 2, y, "•")
                    pdf.drawString(x + pad + 11, y, line)
                y -= lead

        # "Why" block anchored to the bottom of the card.
        if reason_blocks:
            top = card_y + pad + h_reason
            pdf.setStrokeColor(STROKE)
            pdf.setLineWidth(0.8)
            pdf.line(x + pad, top + 2, x + card_w - pad, top + 2)
            pdf.setFillColor(SECTION_COLORS[section])
            pdf.setFont(MED, 8.8)
            pdf.drawString(x + pad, top - 12, _t('why_recommended', data))
            ry = top - 12 - 15
            pdf.setFillColor(MUTED)
            pdf.setFont(REG, r_size)
            for lines in reason_blocks:
                for line in lines:
                    if ry < card_y + pad - 2:
                        break
                    pdf.drawString(x + pad, ry, line)
                    ry -= r_size + 2.8
                ry -= 4
    _footer(pdf, page_width_points, data)


def _draw_category_butterfly(pdf, card_x, card_y, card_w, card_h, left_mat, right_mat, left_label, right_label, data):
    """Earlier period (left) vs selected period (right), one row per waste type."""
    pad = 28
    legend_w = 2.5 * inch
    bars_w = card_w - 2 * pad - legend_w
    # Room on both sides for the value labels (≈ "44,976.74") so they never touch the legend.
    center_x = card_x + pad + bars_w / 2.0
    half_w = bars_w / 2.0 - 62
    top_y = card_y + card_h - 92
    bottom_y = card_y + 46
    cats = sorted({*left_mat.keys(), *right_mat.keys()},
                  key=lambda k: float(left_mat.get(k, 0) or 0) + float(right_mat.get(k, 0) or 0), reverse=True)[:8]
    if not cats:
        pdf.setFillColor(MUTED)
        pdf.setFont(REG, 11)
        pdf.drawCentredString(card_x + card_w / 2.0, card_y + card_h / 2.0, _t('no_comparison_data', data))
        return

    def val(d, k):
        try:
            return float(d.get(k, 0) or 0)
        except Exception:
            return 0.0
    max_val = max([1e-9] + [val(left_mat, c) for c in cats] + [val(right_mat, c) for c in cats])
    n = len(cats)
    step = (top_y - bottom_y) / max(1, n)
    bar_h = max(10.0, min(24.0, step - 12))
    pdf.setFillColor(TEXT)
    pdf.setFont(MED, 11)
    pdf.drawRightString(center_x - 8, top_y + 18, _fit_text_to_width(left_label, MED, 11, half_w))
    pdf.drawString(center_x + 8, top_y + 18, _fit_text_to_width(right_label, MED, 11, half_w + 40))
    pdf.setStrokeColor(STROKE)
    pdf.setLineWidth(1)
    pdf.line(center_x, bottom_y - 6, center_x, top_y + 10)
    cat_map = (data or {}).get('labels', {}).get('_category_map', {})
    legend_x = card_x + card_w - pad - legend_w + 12
    for i, cat in enumerate(cats):
        yc = top_y - step * (i + 0.5)
        lv, rv = val(left_mat, cat), val(right_mat, cat)
        ll = lv / max_val * half_w
        rl = rv / max_val * half_w
        r = min(bar_h / 2.0, 6)
        if ll > 0:
            pdf.setFillColor(colors.HexColor("#c9d6cf"))
            pdf.roundRect(center_x - ll, yc - bar_h / 2.0, ll, bar_h, min(r, ll / 2.0), stroke=0, fill=1)
            pdf.rect(center_x - min(ll, r), yc - bar_h / 2.0, min(ll, r), bar_h, stroke=0, fill=1)
        if rl > 0:
            pdf.setFillColor(colors.HexColor("#84b8a3"))
            pdf.roundRect(center_x, yc - bar_h / 2.0, rl, bar_h, min(r, rl / 2.0), stroke=0, fill=1)
            pdf.rect(center_x, yc - bar_h / 2.0, min(rl, r), bar_h, stroke=0, fill=1)
        pdf.setFont(REG, 8.5)
        pdf.setFillColor(INK)
        pdf.drawRightString(center_x - ll - 6, yc - 3, _format_number(lv))
        pdf.drawString(center_x + rl + 6, yc - 3, _format_number(rv))
        name = cat_map.get(cat, cat.replace(" Waste", ""))
        pdf.setFillColor(colors.HexColor("#555555"))
        pdf.setFont(REG, 10)
        pdf.drawString(legend_x, yc + 5, _fit_text_to_width(name, REG, 10, legend_w - 50))
        delta = rv - lv
        txt = f"{'+' if delta >= 0 else '-'} {_format_number(abs(delta))} {_t('kg', data)}"
        if lv > 0:
            txt += f" ({delta / lv * 100.0:+.1f}%)"
        # More recyclables is the good direction; every other stream is better when it shrinks.
        good = (delta > 0) if "recycl" in str(cat).lower() else (delta < 0)
        pdf.setFillColor(MUTED if delta == 0 else (DECREASE_COLOR if good else INCREASE_COLOR))
        pdf.setFont(REG, 8.5)
        pdf.drawString(legend_x, yc - 9, txt)


def _draw_out_of_range(pdf, card_x, card_y, card_w, card_h, oor: dict, data: dict) -> None:
    """The comparison page when the selected range can't be compared: say so, say why, and
    suggest a range (or the other comparison mode) that works. The export itself still goes
    out — every other page uses the full range."""
    lang = data.get('language', 'en') or 'en'
    mode = oor.get("compare_mode") or "yearly"
    pad = 44
    text_w = card_w - 2 * pad
    x = card_x + pad
    y = card_y + card_h - 70

    def paragraph(text, font, size, color, gap=4.0, indent=0.0):
        nonlocal y
        pdf.setFillColor(color)
        pdf.setFont(font, size)
        for line in _wrap_thai(text, font, size, text_w - indent):
            pdf.drawString(x + indent, y, line)
            y -= size + gap

    # Title with a warning dot
    pdf.setFillColor(INCREASE_COLOR)
    pdf.circle(x + 6, y + 6, 6, stroke=0, fill=1)
    pdf.setFillColor(WHITE)
    pdf.setFont(MED, 9)
    pdf.drawCentredString(x + 6, y + 3, "!")
    pdf.setFillColor(INK)
    pdf.setFont(MED, 17)
    pdf.drawString(x + 22, y, _fit_text_to_width(_t('out_of_range_title', data), MED, 17, text_w - 22))
    y -= 30
    paragraph(_t('out_of_range_selected', data).replace('{range}', str(oor.get(f"selected_{lang}") or "")), REG, 11, MUTED)
    y -= 10
    paragraph(_t('out_of_range_rule_monthly' if mode == 'monthly' else 'out_of_range_rule_yearly', data), REG, 11.5, TEXT, gap=5)
    y -= 22

    # Suggestions
    pdf.setFillColor(INK)
    pdf.setFont(MED, 13)
    pdf.drawString(x, y, _t('out_of_range_how', data))
    y -= 24
    tips = [_t('out_of_range_try_range', data).replace('{range}', str(oor.get(f"suggest_{lang}") or ""))]
    if mode == 'monthly' and oor.get("yearly_ok"):
        tips.append(_t('out_of_range_try_yearly', data).replace('{range}', str(oor.get(f"selected_{lang}") or "")))
    elif mode == 'yearly':
        tips.append(_t('out_of_range_try_monthly', data).replace('{range}', str(oor.get(f"suggest_month_{lang}") or "")))
    for i, tip in enumerate(tips):
        pdf.setFillColor(TEXT)
        pdf.setFont(MED, 11.5)
        pdf.drawString(x, y, f"{i + 1}.")
        paragraph(tip, REG, 11.5, TEXT, gap=5, indent=18)
        y -= 8

    # Footnote at the bottom of the card
    pdf.setFillColor(MUTED)
    pdf.setFont(REG, 9.5)
    pdf.drawString(x, card_y + 26, _fit_text_to_width(_t('out_of_range_other_pages', data), REG, 9.5, text_w))


def draw_comparison(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    """Comparison pages, following the user's comparison mode: the selected range against the
    same range last year (months on page 2) or the same days last month (days on page 2)."""
    padding = 0.78 * inch
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, _t('comparison', data))
    content_top = page_height_points - (1.96 * inch) - 24
    card_x = padding
    card_w = page_width_points - 2 * padding
    card_y = CONTENT_BOTTOM
    card_h = content_top - card_y
    _rounded_card(pdf, card_x, card_y, card_w, card_h, radius=10, fill=WHITE)

    comparison_data = data.get("comparison_data", {}) or {}
    error_msg = comparison_data.get("error")
    if error_msg:
        oor = comparison_data.get("out_of_range")
        if isinstance(oor, dict) and oor.get("from"):
            _draw_out_of_range(pdf, card_x, card_y, card_w, card_h, oor, data)
        else:  # payload from a platform lambda deployed before the out-of-range page
            pdf.setFillColor(TEXT)
            pdf.setFont(MED, 13)
            pdf.drawCentredString(card_x + card_w / 2.0, card_y + card_h / 2.0,
                                  _fit_text_to_width(str(error_msg), MED, 13, card_w - 40))
        _footer(pdf, page_width_points, data)
        return

    mode = comparison_data.get("compare_mode") or "yearly"
    left = comparison_data.get("left", {}) or {}
    right = comparison_data.get("right", {}) or {}
    left_label = str(left.get("period") or "")
    right_label = str(right.get("period") or "")
    title = _t('by_category_title', data).replace('{prev}', left_label).replace('{latest}', right_label)
    pdf.setFillColor(TEXT)
    pdf.setFont(MED, 12)
    pdf.drawString(card_x + 18, card_y + card_h - 26, _fit_text_to_width(title, MED, 12, card_w - 36))
    notes = []
    if comparison_data.get("clamped"):
        notes.append(_t('clamped_note', data))
    if not (left.get("material") or {}):
        notes.append(_t('no_prev_period', data))
    if notes:
        pdf.setFillColor(MUTED)
        pdf.setFont(REG, 8.5)
        pdf.drawString(card_x + 18, card_y + card_h - 42, _fit_text_to_width("  ·  ".join(notes), REG, 8.5, card_w - 36))
    _draw_category_butterfly(pdf, card_x, card_y, card_w, card_h, left.get("material", {}) or {},
                             right.get("material", {}) or {}, left_label, right_label, data)
    _footer(pdf, page_width_points, data)

    # ---- Page 2: quantity by month (yearly) or by day (monthly) ------------------------
    buckets = comparison_data.get("buckets") or []
    lang = data.get('language', 'en') or 'en'
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, _t('comparison', data))
    chart_h = 2.5 * inch
    chart_y = content_top - chart_h
    _rounded_card(pdf, card_x, chart_y, card_w, chart_h, radius=10, fill=WHITE)
    pdf.setFillColor(TEXT)
    pdf.setFont(MED, 12)
    pdf.drawString(card_x + 18, chart_y + chart_h - 24,
                   _t('quantity_by_month' if mode == 'yearly' else 'quantity_by_day', data))
    series_l = _short_period(left, mode, lang)
    series_r = _short_period(right, mode, lang)
    # Days (monthly mode) are drawn as two lines — 2 × 31 bars side by side were unreadable.
    # Months (yearly mode) stay as paired bars. The table swatches reuse these colours.
    as_lines = mode != 'yearly'
    col_l = colors.HexColor("#a8bbb1") if as_lines else colors.HexColor("#c9d6cf")
    col_r = colors.HexColor("#2f8f6b") if as_lines else colors.HexColor("#84b8a3")
    _legend_swatches(pdf, card_x + card_w - 18, chart_y + chart_h - 24, [(series_l, col_l), (series_r, col_r)])
    table_y = CONTENT_BOTTOM
    table_h = chart_y - 12 - table_y
    _rounded_card(pdf, card_x, table_y, card_w, table_h, radius=10, fill=WHITE)
    if not buckets:
        pdf.setFillColor(MUTED)
        pdf.setFont(REG, 11)
        pdf.drawCentredString(card_x + card_w / 2.0, chart_y + chart_h / 2.0, _t('no_comparison_data', data))
        _footer(pdf, page_width_points, data)
        return

    gx = card_x + 60
    gw = card_w - 60 - 24
    gy = chart_y + 30
    gh = chart_h - 30 - 50
    top_val = _nice_top(max([float(b.get("left_kg") or 0) for b in buckets] + [float(b.get("right_kg") or 0) for b in buckets]) * 1.12, steps=2)
    pdf.setLineWidth(0.5)
    for frac in (0.0, 0.5, 1.0):
        yt = gy + frac * gh
        pdf.setStrokeColor(STROKE)
        pdf.line(gx, yt, gx + gw, yt)
        pdf.setFillColor(MUTED)
        pdf.setFont(REG, 8)
        pdf.drawRightString(gx - 6, yt - 3, _tick_label(top_val * frac))
    pdf.drawRightString(gx - 6, gy + gh + 9, _t('kg', data))
    slot = gw / len(buckets)
    bar_w = max(2.5, min(18.0, slot * 0.34))
    show_values = len(buckets) <= 12
    if as_lines:
        for key, col, width in (("left_kg", col_l, 1.4), ("right_kg", col_r, 1.8)):
            pts = []
            for i, b in enumerate(buckets):
                v = b.get(key)
                if v is None:
                    continue
                pts.append((gx + slot * (i + 0.5), gy + float(v) / top_val * gh))
            if not pts:
                continue
            pdf.setStrokeColor(col)
            pdf.setLineWidth(width)
            pdf.setLineJoin(1)
            path = pdf.beginPath()
            path.moveTo(*pts[0])
            for pt in pts[1:]:
                path.lineTo(*pt)
            pdf.drawPath(path, stroke=1, fill=0)
            pdf.setFillColor(col)
            for px, py in pts:
                pdf.circle(px, py, 1.6, stroke=0, fill=1)
        pdf.setLineWidth(0.5)
    for i, b in enumerate(buckets):
        cx = gx + slot * (i + 0.5)
        if not as_lines:
            for j, (v, col) in enumerate(((float(b.get("left_kg") or 0), col_l),
                                          (float(b.get("right_kg") or 0), col_r))):
                bx = cx - bar_w - 1 + j * (bar_w + 2)
                bh = v / top_val * gh
                _draw_bar_top_round_rect(pdf, bx, gy, bar_w, bh, min(bar_w * 0.3, 4), col)
                if show_values and v > 0:
                    pdf.setFillColor(INK)
                    pdf.setFont(REG, 6.5)
                    pdf.drawCentredString(bx + bar_w / 2.0, gy + bh + 3, _fmt_compact(v))
        pdf.setFillColor(TEXT)
        pdf.setFont(REG, 8 if len(buckets) <= 16 else 6.5)
        pdf.drawCentredString(cx, gy - 12, str(b.get(f"label_{lang}") or b.get("key")))

    # Table
    pdf.setFillColor(TEXT)
    pdf.setFont(MED, 12)
    pdf.drawString(card_x + 18, table_y + table_h - 24, f"{_t('period_details', data)} : {series_l} vs {series_r}")
    tx = card_x + 12
    tw = card_w - 24
    header_y = table_y + table_h - 62
    row_h = 28
    pdf.setFillColor(colors.HexColor("#f5faf8"))
    draw_table(pdf, tx, header_y, tw, 24, 8, "Header")
    lt = float(left.get("total_waste_kg") or 0)
    rt = float(right.get("total_waste_kg") or 0)
    if mode == 'yearly':
        # Original layout: one column per month + total; rows = earlier, selected, change.
        label_w = 118
        cols = len(buckets) + 1
        col_w = (tw - label_w) / cols
        fsize = 8.5 if col_w >= 44 else 7.5
        pdf.setFillColor(TEXT)
        pdf.setFont(MED, fsize)
        pdf.drawString(tx + 12, header_y + 9, _t('period', data))
        for i, b in enumerate(buckets):
            pdf.drawCentredString(tx + label_w + col_w * (i + 0.5), header_y + 9, str(b.get(f"label_{lang}") or b.get("key")))
        pdf.drawCentredString(tx + label_w + col_w * (cols - 0.5), header_y + 9, _t('total', data))
        rows = [
            (series_l, [_fmt_compact(b.get("left_kg") or 0) for b in buckets], _fmt_compact(lt), None),
            (series_r, [_fmt_compact(b.get("right_kg") or 0) for b in buckets], _fmt_compact(rt), None),
            (_t('change_kg', data), [(f"{'+' if (b.get('change_kg') or 0) > 0 else '-'}{_fmt_compact(abs(b.get('change_kg') or 0))}" if (b.get('change_kg') or 0) else "0.00") for b in buckets],
             f"{'+' if rt - lt >= 0 else '-'}{_fmt_compact(abs(rt - lt))}", [b.get('change_kg') or 0 for b in buckets]),
        ]
        for r_i, (label, cells, total_cell, colour_by) in enumerate(rows):
            ry = header_y - row_h * (r_i + 1)
            pdf.setFillColor(WHITE if r_i % 2 == 0 else colors.HexColor("#f5faf8"))
            draw_table(pdf, tx, ry, tw, row_h, 8, "Footer" if r_i == len(rows) - 1 else "Body")
            pdf.setFillColor(TEXT)
            pdf.setFont(REG, fsize)
            lx = tx + 12
            if r_i < 2:   # colour swatch of the period, matching the chart
                pdf.setFillColor(col_l if r_i == 0 else col_r)
                pdf.roundRect(lx, ry + 10, 7, 7, 1.5, stroke=0, fill=1)
                pdf.setFillColor(TEXT)
                lx += 12
            pdf.drawString(lx, ry + 10, _fit_text_to_width(label, REG, fsize, label_w - 16 - (lx - tx - 12)))
            for i, cell in enumerate(cells):
                if colour_by is not None:
                    pdf.setFillColor(INCREASE_COLOR if colour_by[i] > 0 else (DECREASE_COLOR if colour_by[i] < 0 else TEXT))
                else:
                    pdf.setFillColor(TEXT)
                pdf.drawCentredString(tx + label_w + col_w * (i + 0.5), ry + 10, _fit_text_to_width(cell, REG, fsize, col_w - 4))
            pdf.setFillColor(INK)
            pdf.setFont(MED, fsize)
            pdf.drawCentredString(tx + label_w + col_w * (cols - 0.5), ry + 10, total_cell)
    else:
        # Up to 31 day columns won't fit a page; summarise the two periods instead.
        heads = [_t('period', data), _t('total_waste_kg', data), _t('days_with_data', data), _t('avg_per_day_kg', data)]
        col_w = tw / 4.0
        pdf.setFillColor(TEXT)
        pdf.setFont(MED, 9)
        for i, h in enumerate(heads):
            pdf.drawString(tx + 12 + col_w * i, header_y + 9, h)
        ldays = sum(1 for b in buckets if float(b.get("left_kg") or 0) > 0)
        rdays = sum(1 for b in buckets if float(b.get("right_kg") or 0) > 0)
        n_days = max(1, len(buckets))
        pct = f" ({(rt - lt) / lt * 100.0:+.1f}%)" if lt > 0 else ""
        rows = [
            (left_label, _format_number(lt), f"{ldays:,}", _format_number(lt / n_days)),
            (right_label, _format_number(rt), f"{rdays:,}", _format_number(rt / n_days)),
            (_t('change_kg', data), f"{'+' if rt - lt >= 0 else '-'}{_format_number(abs(rt - lt))}{pct}", f"{rdays - ldays:+,}",
             f"{'+' if rt - lt >= 0 else '-'}{_format_number(abs(rt - lt) / n_days)}"),
        ]
        for r_i, cells in enumerate(rows):
            ry = header_y - row_h * (r_i + 1)
            pdf.setFillColor(WHITE if r_i % 2 == 0 else colors.HexColor("#f5faf8"))
            draw_table(pdf, tx, ry, tw, row_h, 8, "Footer" if r_i == len(rows) - 1 else "Body")
            pdf.setFont(REG if r_i < 2 else MED, 9)
            for i, cell in enumerate(cells):
                cell_x = tx + 12 + col_w * i
                if i == 0 and r_i < 2:   # colour swatch of the period, matching the chart
                    pdf.setFillColor(col_l if r_i == 0 else col_r)
                    pdf.roundRect(cell_x, ry + 10, 7, 7, 1.5, stroke=0, fill=1)
                    cell_x += 12
                if r_i == 2 and i > 0:
                    pdf.setFillColor(INCREASE_COLOR if rt - lt > 0 else (DECREASE_COLOR if rt - lt < 0 else TEXT))
                else:
                    pdf.setFillColor(TEXT)
                pdf.drawString(cell_x, ry + 10, _fit_text_to_width(str(cell), REG, 9, col_w - 16))
    _footer(pdf, page_width_points, data)


def _short_period(side: dict, mode: str, lang: str) -> str:
    """Series name: the year for yearly mode ('2569'), the month for monthly ('ส.ค. 2569')."""
    iso = str(side.get("from") or "")
    try:
        y, m, _d = (int(x) for x in iso.split("-"))
    except ValueError:
        return str(side.get("period") or "")
    yy = y + 543 if lang == "th" else y
    if mode == "yearly":
        return str(yy)
    months = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'] if lang == "th" \
        else ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return f"{months[m - 1]} {yy}"

def draw_main_materials(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, _t('main_materials', data))
    margin = padding
    # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
    content_top = page_height_points - (1.96 * inch) - 24
    gap = 0.3 * inch
    bar_card = (page_width_points - 2 * margin - gap) * 0.7
    pie_card = (page_width_points - 2 * margin - gap) * 0.3
    card_h2 = 3.8 * inch
    card_y2 = content_top - card_h2
    x_left = margin
    x_right = margin + bar_card + gap
    _rounded_card(pdf, x_left, card_y2 - 0.2 * inch, bar_card, card_h2 + 0.2 * inch, radius=8, fill=WHITE)
    _rounded_card(pdf, x_right, card_y2 - 0.2 * inch, pie_card, card_h2 + 0.2 * inch, radius=8, fill=WHITE)
    items = (data.get("main_materials_data", {}) or {}).get("porportions", []) or []
    items_sorted = sorted((it for it in items if isinstance(it, dict) and "total_waste" in it), key=lambda d: float(d.get("total_waste", 0) or 0), reverse=True,)
    top_n = min(5, max(1, len(items_sorted)))
    items_top = items_sorted[:top_n]
    pad = 24
    title_y = card_y2 + card_h2 - 28
    pdf.setFont("IBMPlexSansThai-Regular", 10)
    max_label_area = bar_card * 0.45
    min_label_area = 60
    longest_word_w = max((stringWidth(w, "IBMPlexSansThai-Regular", 10) for it in items_top for w in _t_name(it, "main_material_name", data).split()), default=40)
    label_area = max(min_label_area, longest_word_w + 6)
    label_area = min(label_area, max_label_area)
    chart_left = x_left + pad + label_area + 8
    chart_right = x_left + bar_card - pad
    chart_bottom = card_y2 + 28
    chart_top = card_y2 + card_h2 - 40
    chart_w = max(1.0, chart_right - chart_left)
    chart_h = max(1.0, chart_top - chart_bottom)
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Medium", 12)
    pdf.drawString(x_left + pad, title_y, _t('top_materials_by_qty', data))
    max_val = max([1.0] + [float(it.get("total_waste", 0) or 0) for it in items_top])
    mag = 1.0
    while mag * 10 <= max_val:
        mag *= 10.0
    for mul in (1.0, 2.0, 2.5, 5.0, 10.0):
        top_val = mul * mag
        if top_val >= max_val:
            break
    # 5 ticks (0%, 25%, 50%, 75%, 100%)
    ticks = [0.0, top_val * 0.25, top_val * 0.5, top_val * 0.75, top_val]
    pdf.setStrokeColor(STROKE)
    pdf.setLineWidth(0.5)
    for tv in ticks:
        x = chart_left + (tv / top_val) * chart_w
        pdf.line(x, chart_bottom, x, chart_top)
        lbl = f"{int(round(tv))}"
        lw = stringWidth(lbl, "IBMPlexSansThai-Regular", 9)
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Regular", 9)
        pdf.drawCentredString(x, chart_bottom - 12, lbl)
    # Baseline along x-axis under tick labels
    pdf.setStrokeColor(STROKE)
    pdf.line(chart_left, chart_bottom, chart_right, chart_bottom)
    # Removed unit label "Kg."
    def _draw_right_round_rect(x, y, w, h, r, color):
        if w <= 0 or h <= 0:
            return
        rr = max(0.0, min(r, h / 2.0, w))
        p = pdf.beginPath()
        p.moveTo(x, y)
        p.lineTo(x + w - rr, y)
        p.arcTo(x + w - 2 * rr, y, x + w, y + 2 * rr, startAng=270, extent=90)
        p.lineTo(x + w, y + h - rr)
        p.arcTo(x + w - 2 * rr, y + h - 2 * rr, x + w, y + h, startAng=0, extent=90)
        p.lineTo(x, y + h)
        p.lineTo(x, y)
        pdf.setFillColor(color)
        pdf.drawPath(p, stroke=0, fill=1)
    groups = max(1, len(items_top))
    row_h = min(26.0, max(16.0, chart_h / (groups * 1.8)))
    cap_r = min(6.0, row_h * 0.4)
    step = chart_h / (groups + 1)
    for i, it in enumerate(items_top):
        center_y = chart_bottom + (groups - i) * step
        y_bar = center_y - (row_h / 2.0)
        value = float(it.get("total_waste", 0) or 0)
        w = (value / top_val) * chart_w
        bar_color = _rank_color(main_material_colorPalette, i)
        _draw_right_round_rect(chart_left, y_bar, w, row_h, cap_r, bar_color)
        name = _t_name(it, "main_material_name", data)
        label_lines = wrap_label(name, "IBMPlexSansThai-Regular", 10, label_area)
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Regular", 10)
        total_label_h = len(label_lines) * 11
        label_y_start = y_bar + (row_h - total_label_h) / 2 + 2
        for j, line in enumerate(label_lines):
            y_line = label_y_start + (len(label_lines) - 1 - j) * 11
            pdf.drawRightString(chart_left - 10, y_line, line)
        val_text = _format_number(value)
        sw = stringWidth(val_text, "IBMPlexSansThai-Regular", 10)
        inside_space = max(0.0, w - cap_r - 8)
        pdf.setFont("IBMPlexSansThai-Regular", 10)
        if sw <= inside_space and w > 0:
            pdf.setFillColor(WHITE if BAR2 != WHITE else TEXT)
            pdf.drawRightString(chart_left + w - cap_r - 6, y_bar + row_h / 2.0 - 4, val_text)
        else:
            pdf.setFillColor(TEXT)
            x_out = min(chart_right - 4 - sw, chart_left + w + 6)
            pdf.drawString(x_out, y_bar + row_h / 2.0 - 4, val_text)
    pie_values, pie_colors, others_val = _top5_pie(items_sorted, main_material_colorPalette)
    pie_size = max(60.0, min(pie_card, card_h2) * 0.55)
    pie_x = x_right + (pie_card - pie_size) / 2.0
    pie_y = card_y2 + (card_h2 - pie_size) - 36
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Medium", 12)
    pdf.drawString(pie_x - 24, title_y, _t('materials_proportion', data))
    _simple_pie_chart(pdf, pie_x, pie_y - 12, pie_size, pie_values, pie_colors, gap_width=1, gap_color=colors.white)
    top5 = items_top[:5]
    row_h = 14
    start_y = (pie_y - 12) - 22
    left_x = x_right + 12
    right_x = x_right + pie_card - 12
    box_size = 8
    pdf.setFont("IBMPlexSansThai-Regular", 10)
    legend_rows = list(top5)
    if others_val > 0:
        legend_rows.append({"_others": True, "total_waste": others_val})
    legend_step = 17 if len(legend_rows) > 5 else row_h + 6   # 6 rows (top 5 + others) must fit the card
    for i, it in enumerate(legend_rows):
        y = start_y - i * legend_step
        c = colors.HexColor(OTHERS_GREY) if it.get("_others") else _rank_color(main_material_colorPalette, i)
        pdf.setFillColor(c)
        pdf.roundRect(left_x, y - box_size + 7, box_size, box_size, 2, stroke=0, fill=1)
        name = _t('others', data) if it.get("_others") else _t_name(it, "main_material_name", data)
        pdf.setFillColor(TEXT)
        max_name_w = (right_x - left_x) - box_size - 54
        label = name
        while stringWidth(label, "IBMPlexSansThai-Regular", 10) > max_name_w and len(label) > 1:
            label = label[:-2] + "…"
        pdf.drawString(left_x + box_size + 6, y, label)
        perc = None if it.get("_others") else it.get("proportion_percent")
        if perc is None:
            total_w = float((data.get("main_materials_data", {}) or {}).get("total_waste", 0) or 0) or sum(pie_values) or 1.0
            perc = (float(it.get("total_waste", 0) or 0) / total_w) * 100.0
        perc_text = f"{_format_number(perc)}%"
        pw = stringWidth(perc_text, "IBMPlexSansThai-Regular", 10)
        pdf.drawString(right_x - pw, y, perc_text)
    _footer(pdf, page_width_points, data)

def _material_table_header(pdf, page_width_points, padding, header_y, header_text_y, first_col_label, data, cols):
    pdf.setFillColor(colors.HexColor("#f5faf8"))
    draw_table(pdf, padding, header_y, page_width_points - 2 * padding, 24, 8, "Header")
    pdf.setFillColor(TEXT)
    pdf.setFont(MED, 9)
    pdf.drawString(padding + 16, header_text_y, first_col_label)
    pdf.drawRightString(cols['total'], header_text_y, _t('total_waste_kg', data))
    pdf.drawRightString(cols['pct'], header_text_y, _t('percentage_pct', data))
    pdf.drawRightString(cols['ghg'], header_text_y, _t('ghg_reduction_kgco2e', data))


def _material_table_cols(page_width_points, padding) -> dict:
    """Right edges of the numeric columns, shared by the header and every row."""
    return {
        'total': padding + 4.6 * inch,
        'pct': padding + 6.9 * inch,
        'ghg': page_width_points - padding - 16,
    }


def _draw_material_row(pdf, page_width_points, padding, y_base, idx, row, data, cols, name_key, is_last):
    """One table row. kinds: item | group | group_cont | total."""
    kind = row.get("kind")
    tw = page_width_points - 2 * padding
    table_type = "Footer" if is_last else "Body"
    if kind in ("group", "group_cont"):
        bg = colors.HexColor("#eef6f2")
    elif kind == "total":
        bg = colors.HexColor("#e2efe9")
    else:
        bg = WHITE if (idx % 2 == 0) else colors.HexColor("#f8fbfa")
    pdf.setFillColor(bg)
    draw_table(pdf, padding, y_base, tw, 32, 8, table_type)
    y_text = y_base + 12
    bold = kind in ("group", "group_cont", "total")
    font = MED if bold else REG
    if kind == "item":
        indent = 34 if row.get("grouped") else 16
        if row.get("grouped"):   # small L connector (the font has no box-drawing glyphs)
            pdf.setStrokeColor(colors.HexColor("#b9cbc2"))
            pdf.setLineWidth(0.8)
            lx = padding + 22
            pdf.line(lx, y_text + 9, lx, y_text + 3)
            pdf.line(lx, y_text + 3, lx + 7, y_text + 3)
            pdf.setLineWidth(0.5)
        name = _t_name(row["item"], name_key, data)
        pdf.setFillColor(TEXT)
        pdf.setFont(REG, 9)
        pdf.drawString(padding + indent, y_text, _fit_text_to_width(name, REG, 9, cols['total'] - padding - indent - 1.2 * inch))
        vals = (row["item"].get("total_waste", 0), row["item"].get("proportion_percent", 0), row["item"].get("ghg_reduction", 0))
    else:
        if kind == "total":
            label = _t('total', data)
        else:
            label = str(row["name"]) + (f" {_t('continued', data)}" if kind == "group_cont" else "")
        pdf.setFillColor(TEXT)
        pdf.setFont(MED, 9.5)
        label = _fit_text_to_width(label, MED, 9.5, cols['total'] - padding - 16 - 1.6 * inch)
        pdf.drawString(padding + 16, y_text, label)
        if kind in ("group", "group_cont") and row.get("count"):
            lw = stringWidth(label, MED, 9.5)
            pdf.setFillColor(MUTED)
            pdf.setFont(REG, 8)
            pdf.drawString(padding + 16 + lw + 6, y_text, _t('items_count', data).replace('{n}', str(row["count"])))
        vals = (row.get("total_waste", 0), row.get("proportion_percent", 0), row.get("ghg_reduction", 0))
    pdf.setFillColor(TEXT)
    pdf.setFont(font, 9)
    pdf.drawRightString(cols['total'], y_text, _format_number(vals[0] or 0))
    pdf.drawRightString(cols['pct'], y_text, f"{float(vals[1] or 0):.2f}%")
    pdf.drawRightString(cols['ghg'], y_text, _format_number(vals[2] or 0))


def _material_total_row(items: list) -> dict:
    return {
        "kind": "total",
        "total_waste": sum(float(it.get("total_waste", 0) or 0) for it in items),
        "proportion_percent": 100.0 if items else 0.0,
        "ghg_reduction": sum(float(it.get("ghg_reduction", 0) or 0) for it in items),
    }


def draw_main_materials_table(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    """Main materials table: one row per main material and a closing total row. Every page
    repeats the header; the last page always carries at least two rows with the total."""
    padding = 0.78 * inch
    content_top = page_height_points - (1.96 * inch) - 24
    header_y = content_top - 24
    header_text_y = content_top - 15
    mats = (data.get("main_materials_data", {}) or {}).get("porportions", []) or []
    if not mats:
        return
    cols = _material_table_cols(page_width_points, padding)
    rows = [{"kind": "item", "item": m} for m in mats] + [_material_total_row(mats)]
    pages = _paginate_table_rows(rows, 10, is_data=lambda r: r.get("kind") == "item")
    for page_rows in pages:
        pdf.showPage()
        _header(pdf, page_width_points, page_height_points, data)
        _sub_header(pdf, page_width_points, page_height_points, data, _t('main_materials', data))
        _material_table_header(pdf, page_width_points, padding, header_y, header_text_y, _t('main_material', data), data, cols)
        for idx, row in enumerate(page_rows):
            _draw_material_row(pdf, page_width_points, padding, header_y - 32 - idx * 32, idx, row, data, cols,
                               "main_material_name", idx == len(page_rows) - 1)
        _footer(pdf, page_width_points, data)

def draw_sub_materials(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, _t('sub_materials', data))
    margin = padding
    # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
    content_top = page_height_points - (1.96 * inch) - 24
    gap = 0.3 * inch
    bar_card = (page_width_points - 2 * margin - gap) * 0.7
    pie_card = (page_width_points - 2 * margin - gap) * 0.3
    card_h2 = 3.8 * inch
    card_y2 = content_top - card_h2
    x_left = margin
    x_right = margin + bar_card + gap
    _rounded_card(pdf, x_left, card_y2 - 0.2 * inch, bar_card, card_h2 + 0.2 * inch, radius=8, fill=WHITE)
    _rounded_card(pdf, x_right, card_y2 - 0.2 * inch, pie_card, card_h2 + 0.2 * inch, radius=8, fill=WHITE)
    items = (data.get("sub_materials_data", {}) or {}).get("porportions", []) or []
    items_sorted = sorted((it for it in items if isinstance(it, dict) and "total_waste" in it), key=lambda d: float(d.get("total_waste", 0) or 0), reverse=True,)
    top_n = min(5, max(1, len(items_sorted)))
    items_top = items_sorted[:top_n]
    pad = 24
    title_y = card_y2 + card_h2 - 28
    pdf.setFont("IBMPlexSansThai-Regular", 10)
    max_label_area = bar_card * 0.45
    min_label_area = 60
    longest_word_w = max((stringWidth(w, "IBMPlexSansThai-Regular", 10) for it in items_top for w in _t_name(it, "material_name", data).split()), default=40)
    label_area = max(min_label_area, longest_word_w + 6)
    label_area = min(label_area, max_label_area)
    chart_left = x_left + pad + label_area + 8
    chart_right = x_left + bar_card - pad
    chart_bottom = card_y2 + 28
    chart_top = card_y2 + card_h2 - 40
    chart_w = max(1.0, chart_right - chart_left)
    chart_h = max(1.0, chart_top - chart_bottom)
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Medium", 12)
    pdf.drawString(x_left + pad, title_y, _t('top_materials_by_qty', data))
    max_val = max([1.0] + [float(it.get("total_waste", 0) or 0) for it in items_top])
    mag = 1.0
    while mag * 10 <= max_val:
        mag *= 10.0
    for mul in (1.0, 2.0, 2.5, 5.0, 10.0):
        top_val = mul * mag
        if top_val >= max_val:
            break
    # 5 ticks (0%, 25%, 50%, 75%, 100%)
    ticks = [0.0, top_val * 0.25, top_val * 0.5, top_val * 0.75, top_val]
    pdf.setStrokeColor(STROKE)
    pdf.setLineWidth(0.5)
    for tv in ticks:
        x = chart_left + (tv / top_val) * chart_w
        pdf.line(x, chart_bottom, x, chart_top)
        lbl = f"{int(round(tv))}"
        lw = stringWidth(lbl, "IBMPlexSansThai-Regular", 9)
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Regular", 9)
        pdf.drawCentredString(x, chart_bottom - 12, lbl)
    # Baseline along x-axis under tick labels
    pdf.setStrokeColor(STROKE)
    pdf.line(chart_left, chart_bottom, chart_right, chart_bottom)
    # Removed unit label "Kg."
    def _draw_right_round_rect(x, y, w, h, r, color):
        if w <= 0 or h <= 0:
            return
        rr = max(0.0, min(r, h / 2.0, w))
        p = pdf.beginPath()
        p.moveTo(x, y)
        p.lineTo(x + w - rr, y)
        p.arcTo(x + w - 2 * rr, y, x + w, y + 2 * rr, startAng=270, extent=90)
        p.lineTo(x + w, y + h - rr)
        p.arcTo(x + w - 2 * rr, y + h - 2 * rr, x + w, y + h, startAng=0, extent=90)
        p.lineTo(x, y + h)
        p.lineTo(x, y)
        pdf.setFillColor(color)
        pdf.drawPath(p, stroke=0, fill=1)
    groups = max(1, len(items_top))
    row_h = min(26.0, max(16.0, chart_h / (groups * 1.8)))
    cap_r = min(6.0, row_h * 0.4)
    step = chart_h / (groups + 1)
    for i, it in enumerate(items_top):
        center_y = chart_bottom + (groups - i) * step
        y_bar = center_y - (row_h / 2.0)
        value = float(it.get("total_waste", 0) or 0)
        w = (value / top_val) * chart_w
        bar_color = _rank_color(sub_material_colorPalette, i)
        _draw_right_round_rect(chart_left, y_bar, w, row_h, cap_r, bar_color)
        name = _t_name(it, "material_name", data)
        label_lines = wrap_label(name, "IBMPlexSansThai-Regular", 10, label_area)
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Regular", 10)
        total_label_h = len(label_lines) * 11
        label_y_start = y_bar + (row_h - total_label_h) / 2 + 2
        for j, line in enumerate(label_lines):
            y_line = label_y_start + (len(label_lines) - 1 - j) * 11
            pdf.drawRightString(chart_left - 10, y_line, line)
        val_text = _format_number(value)
        sw = stringWidth(val_text, "IBMPlexSansThai-Regular", 10)
        inside_space = max(0.0, w - cap_r - 8)
        pdf.setFont("IBMPlexSansThai-Regular", 10)
        if sw <= inside_space and w > 0:
            pdf.setFillColor(WHITE if BAR2 != WHITE else TEXT)
            pdf.drawRightString(chart_left + w - cap_r - 6, y_bar + row_h / 2.0 - 4, val_text)
        else:
            pdf.setFillColor(TEXT)
            x_out = min(chart_right - 4 - sw, chart_left + w + 6)
            pdf.drawString(x_out, y_bar + row_h / 2.0 - 4, val_text)
    pie_values, pie_colors, others_val = _top5_pie(items_sorted, sub_material_colorPalette)
    pie_size = max(60.0, min(pie_card, card_h2) * 0.55)
    pie_x = x_right + (pie_card - pie_size) / 2.0
    pie_y = card_y2 + (card_h2 - pie_size) - 36
    pdf.setFillColor(TEXT)
    pdf.setFont("IBMPlexSansThai-Medium", 12)
    pdf.drawString(pie_x - 24, title_y, _t('materials_proportion', data))
    _simple_pie_chart(pdf, pie_x, pie_y - 12, pie_size, pie_values, pie_colors, gap_width=1, gap_color=colors.white)
    top5 = items_top[:5]
    row_h = 14
    start_y = (pie_y - 12) - 22
    left_x = x_right + 12
    right_x = x_right + pie_card - 12
    box_size = 8
    pdf.setFont("IBMPlexSansThai-Regular", 10)
    legend_rows = list(top5)
    if others_val > 0:
        legend_rows.append({"_others": True, "total_waste": others_val})
    legend_step = 17 if len(legend_rows) > 5 else row_h + 6   # 6 rows (top 5 + others) must fit the card
    for i, it in enumerate(legend_rows):
        y = start_y - i * legend_step
        c = colors.HexColor(OTHERS_GREY) if it.get("_others") else _rank_color(sub_material_colorPalette, i)
        pdf.setFillColor(c)
        pdf.roundRect(left_x, y - box_size + 7, box_size, box_size, 2, stroke=0, fill=1)
        name = _t('others', data) if it.get("_others") else _t_name(it, "material_name", data)
        pdf.setFillColor(TEXT)
        max_name_w = (right_x - left_x) - box_size - 54
        label = name
        while stringWidth(label, "IBMPlexSansThai-Regular", 10) > max_name_w and len(label) > 1:
            label = label[:-2] + "…"
        pdf.drawString(left_x + box_size + 6, y, label)
        perc = None if it.get("_others") else it.get("proportion_percent")
        if perc is None:
            total_w = float((data.get("sub_materials_data", {}) or {}).get("total_waste", 0) or 0) or sum(pie_values) or 1.0
            perc = (float(it.get("total_waste", 0) or 0) / total_w) * 100.0
        perc_text = f"{_format_number(perc)}%"
        pw = stringWidth(perc_text, "IBMPlexSansThai-Regular", 10)
        pdf.drawString(right_x - pw, y, perc_text)
    _footer(pdf, page_width_points, data)

def draw_sub_materials_table(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    """Sub materials grouped by main material: a group row with the group's subtotal, its
    materials indented under it, and a closing total row. A group that continues on the next
    page repeats its header there "(cont.)"; a group header never ends a page."""
    padding = 0.78 * inch
    content_top = page_height_points - (1.96 * inch) - 24
    header_y = content_top - 24
    header_text_y = content_top - 15
    sm = data.get("sub_materials_data", {}) or {}
    grouped = sm.get("porportions_grouped", {}) or {}
    rows, all_items = [], []
    for group_name, items in grouped.items():
        items = [it for it in (items or []) if isinstance(it, dict)]
        if not items:
            continue
        all_items.extend(items)
        group = {
            "kind": "group", "name": group_name, "count": len(items), "keep_with_next": True,
            "total_waste": sum(float(it.get("total_waste", 0) or 0) for it in items),
            "proportion_percent": sum(float(it.get("proportion_percent", 0) or 0) for it in items),
            "ghg_reduction": sum(float(it.get("ghg_reduction", 0) or 0) for it in items),
        }
        rows.append(group)
        for it in items:
            rows.append({"kind": "item", "item": it, "grouped": True, "group": group})
    if not rows:
        flat = [it for it in (sm.get("porportions") or []) if isinstance(it, dict)]
        all_items = flat
        rows = [{"kind": "item", "item": it} for it in flat]
    if not rows:
        return
    rows.append(_material_total_row(all_items))

    def continuation(prev_page, next_row):
        g = next_row.get("group") if next_row.get("kind") == "item" else None
        return dict(g, kind="group_cont", keep_with_next=False) if g else None

    cols = _material_table_cols(page_width_points, padding)
    pages = _paginate_table_rows(rows, 10, is_data=lambda r: r.get("kind") == "item", continuation=continuation)
    for page_rows in pages:
        pdf.showPage()
        _header(pdf, page_width_points, page_height_points, data)
        _sub_header(pdf, page_width_points, page_height_points, data, _t('sub_materials', data))
        _material_table_header(pdf, page_width_points, padding, header_y, header_text_y, _t('sub_material', data), data, cols)
        for idx, row in enumerate(page_rows):
            _draw_material_row(pdf, page_width_points, padding, header_y - 32 - idx * 32, idx, row, data, cols,
                               "material_name", idx == len(page_rows) - 1)
        _footer(pdf, page_width_points, data)

def draw_waste_diversion(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    pdf.showPage()
    padding = 0.78 * inch
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, _t('waste_diversion', data))
    
    # Check for error message
    diversion_data = data.get("diversion_data", {}) or {}
    error_msg = diversion_data.get("error")
    if error_msg:
        # Display error message centered like comparison
        card_x = padding
        card_y = 0.75 * inch
        card_w = page_width_points - 2 * padding
        card_h = 5.2 * inch
        _rounded_card(pdf, card_x, card_y, card_w, card_h, radius=8, fill=WHITE)
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Medium", 14)
        error_y = card_y + card_h / 2.0
        pdf.drawCentredString(card_x + card_w / 2.0, error_y, error_msg)
        _footer(pdf, page_width_points, data)
        return
    
    card_data = diversion_data.get("card_data", {}) or {}
    total_origin = card_data.get("total_origin", 0)
    complete_transfer = card_data.get("complete_transfer", 0)
    processing_transfer = card_data.get("processing_transfer", 0)
    completed_rate = card_data.get("completed_rate", 0)
    margin = padding
    # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
    content_top = page_height_points - (1.96 * inch) - 24
    chip_gap = 12
    usable_w = (page_width_points - 2 * margin)
    chip_w = max(1.0, (usable_w - (3 * chip_gap)) / 4.0)
    chip_h = 0.60 * inch
    chip_y = content_top - chip_h
    x0 = margin
    # Total Origins without decimals
    try:
        total_origins_text = f"{int(float(total_origin or 0)):,}"
    except Exception:
        total_origins_text = str(total_origin)
    _stat_chip(pdf, x0, chip_y, chip_w, chip_h, _t('total_origins', data), total_origins_text)
    _stat_chip(pdf, x0 + (chip_w + chip_gap), chip_y, chip_w, chip_h, _t('complete_transfers', data), f"{_format_number(complete_transfer)} {_t('kg', data)}")
    _stat_chip(pdf, x0 + 2 * (chip_w + chip_gap), chip_y, chip_w, chip_h, _t('processing_transfers', data), f"{_format_number(processing_transfer)}%")
    _stat_chip(pdf, x0 + 3 * (chip_w + chip_gap), chip_y, chip_w, chip_h, _t('completed_rate', data), f"{_format_number(completed_rate)}%")
    sankey_raw = (data.get("diversion_data", {}) or {}).get("sankey_data", [])
    chart_y_top = chip_y - 30
    chart_height = chart_y_top - (1.5 * inch)
    if sankey_raw and len(sankey_raw) > 1:
        chart_y_top = chip_y - 30
        chart_height = chart_y_top - (1.5 * inch)
        # Build source color map from materials_data groups (Dangerous vs Non-Dangerous)
        source_color_map = {}
        try:
            mats_groups = diversion_data.get("materials_data") or []

            for grp in mats_groups:
                cat = (grp.get("category_name") or "").strip().lower()

                if cat == "dangerous waste":
                    col = colors.HexColor("#f4cccc")  # Dangerous (red-ish)
                elif cat == "non-dangerous waste":
                    col = colors.HexColor("#fff8c8")  # Non-dangerous (yellow-ish)
                else:
                    col = colors.HexColor("#fff8c8")  # default fallback

                for mm in grp.get("main_materials") or []:
                    name_raw = (mm.get("name") or "").strip()
                    if not name_raw:
                        continue
                    # Store multiple normalized keys to maximize match likelihood
                    keys = set()
                    keys.add(name_raw)
                    keys.add(name_raw.lower())
                    if name_raw.lower().endswith(" waste"):
                        keys.add(name_raw[:-6].strip())
                        keys.add(name_raw[:-6].strip().lower())
                    for k in keys:
                        source_color_map[k] = col

        except Exception:
            source_color_map = {}
        _draw_sankey_diagram(
            pdf,
            x=margin,
            y_top=chart_y_top,
            width=usable_w,
            height=chart_height,
            data_rows=sankey_raw,
            source_color_map=source_color_map
        )
    else:
        print("SANKEY DID NOT GOT USED")
        # Draw a friendly placeholder when there are no flows (only header present)
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Regular", 11)
        msg = "No diversion flows available for the selected period."
        tw = stringWidth(msg, "IBMPlexSansThai-Regular", 11)
        center_x = margin + (usable_w - tw) / 2.0
        center_y = (chart_y_top + (1.5 * inch)) / 2.0
        pdf.drawString(center_x, center_y, msg)
    _footer(pdf, page_width_points, data)

def _draw_sankey_diagram(pdf, x, y_top, width, height, data_rows, source_color_map=None):
    # Keyword lists for color determination
    diverted_keywords = [
        'preparation for reuse',
        'recycling (own)',
        'other recover operation',
        'recycle',
        'recycling',
        'reuse',
        'recover'
    ]
    directed_keywords = [
        'composted by municipality',
        'municipality receive',
        'incineration without energy',
        'incineration with energy',
        'composted',
        'municipality',
        'incineration',
        'disposal'
    ]
    
    def get_target_color(target_name: str):
        """Determine target color based on keywords."""
        # Normalize snake_case to spaces for keyword matching
        target_normalized = str(target_name).lower().strip().replace('_', ' ')
        # Check diverted keywords
        for keyword in diverted_keywords:
            if keyword in target_normalized:
                return colors.HexColor("#54937a")
        # Check directed keywords
        for keyword in directed_keywords:
            if keyword in target_normalized:
                return colors.HexColor("#95c9c4")
        # Default color if no match
        return colors.Color(0.3, 0.6, 0.9)
    
    rows = data_rows[1:] if data_rows[0][0] == "From" else data_rows
    sources = {}
    targets = {}
    flows = []
    for row in rows:
        s, t, w = row[0], row[1], row[2]
        w = float(w)
        if w <= 0:
            continue
        sources[s] = sources.get(s, 0) + w
        targets[t] = targets.get(t, 0) + w
        flows.append({'source': s, 'target': t, 'value': w})
    node_gap = 10
    total_source_weight = sum(sources.values())
    total_target_weight = sum(targets.values())
    if total_source_weight > 0 and total_target_weight > 0:
        scale_s = (height - ((len(sources) - 1) * node_gap if len(sources) > 0 else 0)) / total_source_weight
        scale_t = (height - ((len(targets) - 1) * node_gap if len(targets) > 0 else 0)) / total_target_weight
        scale = min(scale_s, scale_t)
    else:
        scale = 1.0
    target_names = sorted(targets.keys(), key=lambda x: "Incineration" in x)
    target_indices = {name: i for i, name in enumerate(target_names)}
    source_scores = {}
    for name in sources:
        my_flows = [f for f in flows if f['source'] == name]
        if not my_flows:
            source_scores[name] = 0
            continue
        weighted_pos = sum(f['value'] * target_indices.get(f['target'], 0) for f in my_flows)
        total_w = sum(f['value'] for f in my_flows)
        source_scores[name] = weighted_pos / total_w
    source_names = sorted(sources.keys(), key=lambda x: (source_scores.get(x, 0), -sources[x]))
    source_coords = {}
    target_coords = {}
    h_sources_total = sum(sources[n] * scale for n in sources) + ((len(sources) - 1) * node_gap if len(sources) > 0 else 0)
    h_targets_total = sum(targets[n] * scale for n in targets) + ((len(targets) - 1) * node_gap if len(targets) > 0 else 0)
    max_used_height = max(h_sources_total, h_targets_total)
    y_source_start = y_top - (max_used_height - h_sources_total) / 2
    y_target_start = y_top - (max_used_height - h_targets_total) / 2
    curr_y = y_source_start
    for name in source_names:
        h = sources[name] * scale
        source_coords[name] = {'y': curr_y, 'h': h, 'offset': 0}
        curr_y -= (h + node_gap)
    curr_y = y_target_start
    for name in target_names:
        h = targets[name] * scale
        target_coords[name] = {'y': curr_y, 'h': h, 'offset': 0}
        curr_y -= (h + node_gap)
    bar_width = 6
    link_color = colors.Color(0.85, 0.85, 0.85, alpha=0.6)
    pdf.saveState()
    for s_name in source_names:
        s_flows = sorted([f for f in flows if f['source'] == s_name], key=lambda x: target_indices.get(x['target'], 0))
        for flow in s_flows:
            t_name = flow['target']
            val = flow['value']
            link_h = val * scale
            s_node = source_coords[s_name]
            t_node = target_coords[t_name]
            y_start = s_node['y'] - s_node['offset']
            y_end = t_node['y'] - t_node['offset']
            s_node['offset'] += link_h
            t_node['offset'] += link_h
            x_start = x + bar_width 
            x_end = x + width - bar_width
            dist = (x_end - x_start) * 0.4
            cp1 = (x_start + dist, y_start)
            cp2 = (x_end - dist, y_end)
            cp1_b = (x_start + dist, y_start - link_h)
            cp2_b = (x_end - dist, y_end - link_h)
            p = pdf.beginPath()
            p.moveTo(x_start, y_start)
            p.curveTo(cp1[0], cp1[1], cp2[0], cp2[1], x_end, y_end)
            p.lineTo(x_end, y_end - link_h)
            p.curveTo(cp2_b[0], cp2_b[1], cp1_b[0], cp1_b[1], x_start, y_start - link_h)
            p.close()
            pdf.setFillColor(link_color)
            pdf.setStrokeColor(link_color)
            pdf.drawPath(p, fill=1, stroke=0)
    pdf.restoreState()
    pdf.setFont("IBMPlexSansThai-Bold", 8)
    text_color = colors.Color(0.4, 0.4, 0.4)
    source_colors = [colors.Color(0.4, 0.6, 0.9), colors.Color(0.4, 0.8, 0.5), colors.lightgrey]
    for i, name in enumerate(source_names):
        data = source_coords[name]
        bar_y = data['y'] - data['h']
        col = source_colors[i % len(source_colors)]
        try:
            if source_color_map:
                if name in source_color_map:
                    col = source_color_map[name]
                else:
                    lname = name.lower().strip()
                    if lname in source_color_map:
                        col = source_color_map[lname]
                    else:
                        # Try stripping trailing ' waste'
                        if lname.endswith(" waste"):
                            stripped = lname[:-6].strip()
                            if stripped in source_color_map:
                                col = source_color_map[stripped]
                        # Fuzzy contains match as a last resort
                        if col == source_colors[i % len(source_colors)]:
                            for k, v in (source_color_map or {}).items():
                                lk = str(k).lower().strip()
                                if lk and (lk in lname or lname in lk):
                                    col = v
                                    break
        except Exception:
            pass
        pdf.setFillColor(col)
        pdf.setStrokeColor(col)
        pdf.rect(x, bar_y, bar_width, data['h'], fill=1, stroke=0)
        pdf.setFillColor(text_color)
        pdf.drawString(x + bar_width + 8, bar_y + data['h']/2 - 3, name)
    pdf.setFont("IBMPlexSansThai-Bold", 9)
    for name in target_names:
        data = target_coords[name]
        bar_y = data['y'] - data['h']
        # Get color based on keywords
        target_bar_color = get_target_color(name)
        pdf.setFillColor(target_bar_color)
        pdf.setStrokeColor(target_bar_color)
        pdf.rect(x + width - bar_width, bar_y, bar_width, data['h'], fill=1, stroke=0)
        pdf.setFillColor(text_color)
        # Convert snake_case to Title Case for display
        display_name = snake_to_title(name)
        text_w = pdf.stringWidth(display_name, "IBMPlexSansThai-Bold", 9)
        pdf.drawString(x + width - bar_width - 8 - text_w, bar_y + data['h']/2 - 3, display_name)
        print('DONE SANKEY')

def draw_waste_diversion_table(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    # Skip rendering if there's an error in diversion data
    diversion_data = data.get("diversion_data", {}) or {}
    if diversion_data.get("error"):
        return
    
    padding = 0.78 * inch
    rows = (diversion_data.get("material_table", []) or [])
    if not isinstance(rows, list):
        rows = []
    debug = bool(((data or {}).get("_debug", False)))
    if debug:
        try:
            print(f"[waste_diversion_table] total_rows={len(rows)}")
        except Exception:
            pass
    # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
    content_top = page_height_points - (1.96 * inch) - 24
    header_y = content_top - 24
    header_h = 24
    content_x = padding
    content_w = page_width_points - 2 * padding
    # Determine which months actually appear in the data (preserve Jan..Dec order)
    _months_en = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    months_all = _t_months_short(data)
    # Map from translated display label back to English key for data lookup
    _display_to_en = {months_all[i]: _months_en[i] for i in range(12)}
    _name_to_index = {
        "jan": 0, "january": 0, "1": 0, "01": 0,
        "feb": 1, "february": 1, "2": 1, "02": 1,
        "mar": 2, "march": 2, "3": 2, "03": 2,
        "apr": 3, "april": 3, "4": 3, "04": 3,
        "may": 4, "5": 4, "05": 4,
        "jun": 5, "june": 5, "6": 5, "06": 5,
        "jul": 6, "july": 6, "7": 6, "07": 6,
        "aug": 7, "august": 7, "8": 7, "08": 7,
        "sep": 8, "sept": 8, "september": 8, "9": 8, "09": 8,
        "oct": 9, "october": 9, "10": 9,
        "nov": 10, "november": 10, "11": 10,
        "dec": 11, "december": 11, "12": 11,
    }
    def _to_month_label(m) -> str | None:
        s = str(m or "").strip()
        if not s:
            return None
        key = s.lower()
        if key in _name_to_index:
            return months_all[_name_to_index[key]]
        try:
            n = int(s)
            if 1 <= n <= 12:
                return months_all[n - 1]
        except Exception:
            pass
        return None
    months_present = set()
    for r in rows:
        try:
            for entry in (r.get("data", []) or []):
                lbl = _to_month_label((entry or {}).get("month"))
                if lbl:
                    months_present.add(lbl)
        except Exception:
            continue
    months_to_show = [m for m in months_all if m in months_present]
    # Keep Materials and Destination widths; only months area reflows evenly
    _is_th = (data or {}).get('language') == 'th'
    materials_w = content_w * (0.18 if _is_th else 0.22)
    status_w = content_w * 0.10
    original_month_w = content_w * (0.05 if _is_th else 0.045)  # wider columns for Thai month labels
    total_months_area = original_month_w * 12
    num_months = len(months_to_show)
    month_w = (total_months_area / num_months) if num_months > 0 else 0.0
    destination_w = max(1.0, content_w - (materials_w + (month_w * num_months) + status_w))
    # Pre-compute months area actual span: from after Materials to the start of Status
    status_x_pre = content_x + materials_w + (num_months * month_w)
    months_area_left = content_x + materials_w
    months_area_right = status_x_pre
    months_area_w_actual = max(0.0, months_area_right - months_area_left)
    # Compute month column x with centering when only one month is present (between materials and status)
    single_month_w = original_month_w
    def col_x_for_month(i: int) -> float:
        if num_months == 1:
            start = months_area_left + max(0.0, (months_area_w_actual - single_month_w) / 2.0)
            return start + i * single_month_w
        return months_area_left + (i * month_w)
    def fit_text(text: str, max_w: float) -> str:
        t = str(text or "")
        if stringWidth(t, "IBMPlexSansThai-Regular", 8) <= max_w:
            return t
        ell = "…"
        while t and stringWidth(t + ell, "IBMPlexSansThai-Regular", 8) > max_w:
            t = t[:-1]
        return (t + ell) if t else ell
    total_rows = len(rows)
    min_y = 1.5 * inch
    line_h = 10
    group_gap = 4
    def destination_groups(row) -> list[list[str]]:
        dest_val = row.get("destination", [])
        parts = dest_val if isinstance(dest_val, list) else [str(dest_val)]
        groups: list[list[str]] = []
        pdf.setFont("IBMPlexSansThai-Regular", 9)
        for part in (parts or ["-"]):
            # Convert snake_case to Title Case
            part_text = snake_to_title(str(part))
            wrapped = _wrap_text_lines(pdf, part_text, destination_w - 12, "IBMPlexSansThai-Regular", 9)
            groups.append(wrapped or ["-"])
        return groups
    def compute_row_height(row) -> float:
        groups = destination_groups(row)
        lines_count = sum(len(g) for g in groups)
        text_block_h = max(1, lines_count) * line_h + max(0, len(groups) - 1) * group_gap
        badge_h = 18
        return max(32, text_block_h + 12, badge_h + 12)
    idx_global = 0
    page_num = 0
    while idx_global < total_rows or (total_rows == 0 and idx_global == 0):
        page_num += 1
        pdf.showPage()
        _header(pdf, page_width_points, page_height_points, data)
        _sub_header(pdf, page_width_points, page_height_points, data, _t('waste_diversion', data))
        if debug:
            try:
                print(f"[waste_diversion_table] --- page {page_num} ---")
                if total_rows == 0:
                    print("[waste_diversion_table] no rows to render (header-only page)")
            except Exception:
                pass
        pdf.setFillColor(colors.HexColor("#f5faf8"))
        draw_table(pdf, content_x, header_y, content_w, header_h, 8, "Header")
        pdf.setFillColor(TEXT)
        pdf.setFont("IBMPlexSansThai-Medium", 9)
        header_text_y = content_top - 15
        pdf.drawString(content_x + 16, header_text_y, _t('materials', data))
        for i, m in enumerate(months_to_show):
            mx = col_x_for_month(i)
            pdf.drawString(mx + 4, header_text_y, m)
        status_x = status_x_pre
        dest_x = status_x + status_w
        pdf.drawString(status_x + 4, header_text_y, _t('status', data))
        pdf.drawString(dest_x + 4, header_text_y, _t('destination', data))
        current_y = header_y
        drew_any = False
        rows_on_page = 0
        while idx_global < total_rows:
            this_row = rows[idx_global]
            this_h = compute_row_height(this_row)
            if current_y - this_h < min_y:
                if debug:
                    try:
                        print(f"[waste_diversion_table] page break before row {idx_global} (row_h={this_h:.2f}, current_y={current_y:.2f}, min_y={min_y:.2f})")
                    except Exception:
                        pass
                break
            next_h = compute_row_height(rows[idx_global + 1]) if (idx_global + 1) < total_rows else 0
            is_last_on_page = (current_y - this_h - next_h) < min_y or (idx_global + 1) >= total_rows
            y_base = current_y - this_h
            table_type = "Footer" if is_last_on_page else "Body"
            row_bg = WHITE if (rows_on_page % 2 == 0) else colors.HexColor("#f5faf8")
            pdf.setFillColor(row_bg)
            draw_table(pdf, content_x, y_base, content_w, this_h, 8, table_type)
            pdf.setFillColor(TEXT)
            pdf.setFont("IBMPlexSansThai-Regular", 9)
            y_text = y_base + (this_h / 2) - 4
            pdf.drawString(content_x + 16, y_text, str(this_row.get("materials", "")))
            if debug:
                try:
                    print(f"[waste_diversion_table] row {idx_global + 1}/{total_rows} materials={this_row.get('materials','')} row_h={this_h:.2f}")
                except Exception:
                    pass
            month_values = {}
            try:
                for entry in (this_row.get("data", []) or []):
                    if isinstance(entry, dict):
                        month_values[str(entry.get("month"))] = float(entry.get("value", 0) or 0)
            except Exception:
                month_values = {}
            if debug:
                try:
                    months_line = ", ".join(f"{m}={month_values.get(m, 0)}" for m in months_to_show)
                    print(f"[waste_diversion_table]   months: {months_line}")
                except Exception:
                    pass
            for i, m in enumerate(months_to_show):
                mx = col_x_for_month(i)
                # normalize keys from data to our month label
                val = 0
                try:
                    # Try English key mapped from display label first
                    en_key = _display_to_en.get(m, m)
                    if en_key in month_values:
                        val = month_values.get(en_key, 0)
                    elif m in month_values:
                        val = month_values.get(m, 0)
                    else:
                        # attempt numeric key lookup
                        idx = months_all.index(m) + 1
                        for k in (str(idx), f"{idx:02d}"):
                            if k in month_values:
                                val = month_values.get(k, 0)
                                break
                except Exception:
                    val = month_values.get(_display_to_en.get(m, m), 0)
                txt = _format_number(val)
                # Dynamically reduce font size to fit the month column if too long
                try:
                    col_w = single_month_w if num_months == 1 else month_w
                except Exception:
                    col_w = month_w
                max_text_w = max(0.0, (col_w - 8))  # padding
                base_font = "IBMPlexSansThai-Regular"
                font_size = 9
                while font_size > 6 and stringWidth(txt, base_font, font_size) > max_text_w:
                    font_size -= 1
                pdf.setFont(base_font, font_size)
                pdf.drawString(mx + 4, y_text, txt)
                # Restore base font size for subsequent draws
                if font_size != 9:
                    pdf.setFont(base_font, 9)
            status_val = str(this_row.get("status", ""))
            _status_lower = status_val.lower()
            if _status_lower == "processing" or status_val == "กำลังดำเนินการ":
                badge_bg = colors.HexColor("#FFF4E5")
                badge_text = colors.HexColor("#F59E0B")
                pdf.setFont("IBMPlexSansThai-Medium", 9)
                disp = fit_text(status_val, status_w - 16)
                tw = stringWidth(disp, "IBMPlexSansThai-Medium", 9)
                pad_x = 10
                badge_w = min(status_w - 8, tw + 2 * pad_x)
                badge_h = 18
                bx = status_x + 4
                by = y_base + (this_h - badge_h) / 2
                pdf.setFillColor(badge_bg)
                pdf.setStrokeColor(badge_bg)
                pdf.roundRect(bx, by, badge_w, badge_h, badge_h / 2, stroke=0, fill=1)
                pdf.setFillColor(badge_text)
                tx = bx + (badge_w - tw) / 2
                ty = by + (badge_h / 2) - 3
                pdf.drawString(tx, ty, disp)
                pdf.setFillColor(TEXT)
                pdf.setFont("IBMPlexSansThai-Regular", 9)
            elif _status_lower.startswith("complete") or status_val == "เสร็จสิ้น":
                badge_bg = colors.HexColor("#EAF7F0")
                badge_text = colors.HexColor("#16A34A")
                pdf.setFont("IBMPlexSansThai-Medium", 9)
                disp = fit_text(status_val, status_w - 16)
                tw = stringWidth(disp, "IBMPlexSansThai-Medium", 9)
                pad_x = 10
                badge_w = min(status_w - 8, tw + 2 * pad_x)
                badge_h = 18
                bx = status_x + 4
                by = y_base + (this_h - badge_h) / 2
                pdf.setFillColor(badge_bg)
                pdf.setStrokeColor(badge_bg)
                pdf.roundRect(bx, by, badge_w, badge_h, badge_h / 2, stroke=0, fill=1)
                pdf.setFillColor(badge_text)
                tx = bx + (badge_w - tw) / 2
                ty = by + (badge_h / 2) - 3
                pdf.drawString(tx, ty, disp)
                pdf.setFillColor(TEXT)
                pdf.setFont("IBMPlexSansThai-Regular", 9)
            else:
                pdf.drawString(status_x + 4, y_text, fit_text(status_val, status_w - 8))
            pdf.setFont("IBMPlexSansThai-Regular", 9)
            groups = destination_groups(this_row)
            if debug:
                try:
                    total_lines = sum(len(g) for g in groups)
                    print(f"[waste_diversion_table]   status={status_val!r}, dest_groups={len(groups)}, total_dest_lines={total_lines}")
                except Exception:
                    pass
            dy = y_base + this_h - 12
            text_x = dest_x + 12
            bullet_x = dest_x + 6
            placeholder_only = (len(groups) == 1 and len(groups[0]) == 1 and groups[0][0] == "-")
            if placeholder_only:
                dash = "-"
                pdf.setFont("IBMPlexSansThai-Regular", 9)
                tw_dash = stringWidth(dash, "IBMPlexSansThai-Regular", 9)
                tx = dest_x + (destination_w - tw_dash) / 2
                pdf.drawString(tx, y_text, dash)
            else:
                for gi, group in enumerate(groups):
                    if group:
                        pdf.setFillColor(TEXT)
                        pdf.circle(bullet_x, dy + 3, 2, stroke=0, fill=1)
                        pdf.setFillColor(TEXT)
                        pdf.drawString(text_x, dy, group[0])
                        dy -= line_h
                        for ln in group[1:]:
                            pdf.drawString(text_x, dy, ln)
                            dy -= line_h
                    if gi < len(groups) - 1:
                        dy -= group_gap
            current_y = y_base
            idx_global += 1
            drew_any = True
            rows_on_page += 1
        _footer(pdf, page_width_points, data)
        if total_rows == 0:
            # Avoid infinite loop when no rows are present
            break


def _register_fonts() -> None:
    """
    Try to register IBMPlexSansThai fonts from common locations (repo scripts/, lambda layer /opt/fonts, cwd).
    If not found, silently continue (ReportLab will use default fonts).
    """
    # Resolve path relative to this file for bundled fonts
    _this_dir = os.path.dirname(os.path.abspath(__file__))
    _gri_fonts = os.path.join(_this_dir, '..', 'gri', 'assets', 'fonts')
    candidates = [
        ("IBMPlexSansThai-Bold",   ["scripts/IBMPlexSansThai-Bold.ttf",   "/opt/fonts/IBMPlexSansThai-Bold.ttf",   "IBMPlexSansThai-Bold.ttf",   os.path.join(_gri_fonts, "IBMPlexSansThai-Bold.ttf")]),
        ("IBMPlexSansThai-Regular",["scripts/IBMPlexSansThai-Regular.ttf","/opt/fonts/IBMPlexSansThai-Regular.ttf","IBMPlexSansThai-Regular.ttf",os.path.join(_gri_fonts, "IBMPlexSansThai-Regular.ttf")]),
        ("IBMPlexSansThai-Medium", ["scripts/IBMPlexSansThai-Medium.ttf", "/opt/fonts/IBMPlexSansThai-Medium.ttf", "IBMPlexSansThai-Medium.ttf", os.path.join(_gri_fonts, "IBMPlexSansThai-Medium.ttf")]),
    ]
    for family, paths in candidates:
        for p in paths:
            try:
                if os.path.exists(p):
                    pdfmetrics.registerFont(TTFont(family, p))
                    break
            except Exception:
                # try next path
                continue
        # If none found, we skip; ReportLab falls back to base fonts

def _has_diversion_data(data: dict) -> bool:
    """True when the waste-management section has at least one flow or table row."""
    dv = data.get("diversion_data", {}) or {}
    if dv.get("error"):
        return False
    sankey = dv.get("sankey_data") or []
    body = sankey[1:] if sankey and isinstance(sankey[0], (list, tuple)) and str(sankey[0][0]) == "From" else sankey
    for row in body:
        try:
            if float(row[-1] or 0) > 0:
                return True
        except (TypeError, ValueError, IndexError):
            continue
    for row in dv.get("material_table") or []:
        for entry in (row or {}).get("data", []) or []:
            try:
                if float((entry or {}).get("weight", (entry or {}).get("value", 0)) or 0) > 0:
                    return True
            except (TypeError, ValueError):
                continue
    return False

def generate_pdf_bytes(data: dict) -> bytes:
    """
    Generate a PDF report (same layout as scripts/generate_pdf_report.py)
    and return it as bytes suitable for HTTP response/base64 encoding.
    """
    print(f"DATA: {data}")
    width_points = PAGE_WIDTH_IN * inch
    height_points = PAGE_HEIGHT_IN * inch

    # Prepare in-memory buffer
    buffer = BytesIO()

    # Ensure fonts are registered (works both locally and in Lambda with a layer)
    _register_fonts()

    pdf = ThaiCanvas(buffer, pagesize=(width_points, height_points))

    # Draw pages (mirrors main() in scripts/generate_pdf_report.py)
    draw_cover(pdf, width_points, height_points, data)
    draw_overview(pdf, width_points, height_points, data)
    draw_overview_breakdown(pdf, width_points, height_points, data)
    for performance_data in data.get("performance_data", []) or []:
        draw_performance(pdf, width_points, height_points, data, performance_data)
    draw_performance_table(pdf, width_points, height_points, data)
    draw_comparison_advice(pdf, width_points, height_points, data)
    draw_comparison(pdf, width_points, height_points, data)
    draw_main_materials(pdf, width_points, height_points, data)
    draw_main_materials_table(pdf, width_points, height_points, data)
    draw_sub_materials(pdf, width_points, height_points, data)
    draw_sub_materials_table(pdf, width_points, height_points, data)
    # Waste-management pages only when there is something to show; an empty flow page
    # and an empty table told the reader nothing.
    if _has_diversion_data(data):
        draw_waste_diversion(pdf, width_points, height_points, data)
        draw_waste_diversion_table(pdf, width_points, height_points, data)

    pdf.save()
    return buffer.getvalue()


def lambda_handler(event, context):
    """
    AWS Lambda entrypoint.
    Accepts either:
      - Direct invoke with {'data': {...}} (recommended)
      - API Gateway proxy with string body containing JSON {'data': {...}}
    Returns base64-encoded PDF and a filename.
    """
    # Extract payload
    payload = None
    try:
        if isinstance(event, dict) and "data" in event:
            payload = event.get("data") or {}
        elif isinstance(event, dict) and "body" in event:
            body_raw = event.get("body")
            if isinstance(body_raw, str):
                body = json.loads(body_raw)
            else:
                body = body_raw or {}
            payload = (body.get("data") or body) or {}
        else:
            payload = event or {}
    except Exception:
        payload = {}

    # Render
    try:
        pdf_bytes = generate_pdf_bytes(payload)
        b64 = base64.b64encode(pdf_bytes).decode("utf-8")
        filename = f"report_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"
        response_obj = {"success": True, "pdf_base64": b64, "filename": filename, "data": payload}
    except Exception as e:
        response_obj = {"success": False, "error": str(e), "data": payload}

    # If this was API Gateway proxy, wrap in {"statusCode", "body"}
    if isinstance(event, dict) and ("httpMethod" in event or "requestContext" in event):
        return {
            "statusCode": 200 if response_obj.get("success") else 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(response_obj),
        }
    # Direct invoke return
    return response_obj