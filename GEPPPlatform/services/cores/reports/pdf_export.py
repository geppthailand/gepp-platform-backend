"""
Reusable PDF export for Reports.
This module adapts scripts/generate_pdf_report.py drawing functions for API usage.
"""
from __future__ import annotations

from io import BytesIO
from datetime import datetime
import json
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

# --- Colors and constants (vendored from scripts/generate_pdf_report.py) ---
MATERIAL_COLORS = {
    "Recyclable Waste": colors.HexColor("#fff8c8"),
    "Organic Waste": colors.HexColor("#b0dad6"),
    "Electronic Waste": colors.HexColor("#e8e5ef"),
    "Bio-Hazardous Waste": colors.HexColor("#e6b8af"),
    "Hazardous Waste": colors.HexColor("#f4cccc"),
    "Waste To Energy": colors.HexColor("#fce5cd"),
    "General Waste": colors.HexColor("#cfe2f3"),
    "Construction Waste": colors.HexColor("#e8e5ef"),
    "Electronic Waste": colors.HexColor("#d9d9d9"),
}
main_material_colorPalette = [
  "#180055","#1a1662","#1b296d","#1c3b77","#1d4c81","#215d8b","#2880a0",
  "#3091aa","#44a2b1","#58b4b9","#6cc5c0","#85d5ca","#a7e3d7","#c9f1e4","#eafff1"
]
sub_material_colorPalette = [
    "#00313a","#073f3e","#0e4d41","#155b45","#1e6a48","#1e6a48","#3b9752",
    "#4ca658","#62b55e","#79c365","#8fd16c","#a6df73","#c5ea99","#e2f5bd","#ffffe0"
]

PAGE_WIDTH_IN = 11.69
PAGE_HEIGHT_IN = 8.27
PRIMARY = colors.HexColor("#95c9c4")
TEXT = colors.HexColor("#5b6e8c")
CARD = colors.HexColor("#f6f8fb")
STROKE = colors.HexColor("#e6edf4")
BAR = colors.HexColor("#a9d5d0")
WHITE = colors.white
BLACK = colors.black
BAR2 = colors.HexColor("#77b9d8")
BAR3 = colors.HexColor("#c8ced4")
BAR4 = colors.HexColor("#8fcfc6")
SERIES_COLORS = [BAR, BAR2, BAR4, BAR3, TEXT]

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

def _header(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    text = data["users"]
    font_name = "Poppins-Regular"
    font_size = 12
    padding = 0.78 * inch
    text_width = stringWidth(text, font_name, font_size)
    x = page_width_points - text_width - padding
    y = page_height_points - (0.7 * inch)
    pdf.setFillColor(TEXT)
    pdf.setFont(font_name, font_size)
    pdf.drawString(x, y, text)

def _sub_header(pdf, page_width_points: float, page_height_points: float, data: dict, header_text: str) -> None:
    padding = 0.78 * inch
    location_data = data.get("location", [])
    if isinstance(location_data, list):
        location_text = ", ".join(map(str, location_data))
    else:
        location_text = str(location_data)
    pdf.setFillColor(PRIMARY)
    pdf.setFont("Poppins-Bold", 48)
    pdf.drawString(padding, page_height_points - (1.38 * inch), header_text)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 12)
    pdf.drawString(padding, page_height_points - (1.75 * inch), f"Location: {location_text}")
    pdf.drawString(padding, page_height_points - (1.96 * inch), f"Date: {data['date_from']} - {data['date_to']}")

def _format_number(value) -> str:
    try:
        if isinstance(value, (int,)) or abs(value - int(value)) < 1e-9:
            return f"{value:,.0f}"
        return f"{value:,.2f}"
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

def _stat_chip(pdf, x, y, w, h, title, value, variant="gray"):
    fill_color = WHITE if variant == "white" else CARD
    _rounded_card(pdf, x, y, w, h, radius=8, fill=fill_color)
    pad_x = 12 if variant == "white" else 20
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 8)
    pdf.drawString(x + pad_x, y + h - 18, title)
    pdf.setFont("Poppins-Regular", 12)
    pdf.drawString(x + pad_x, y + h - 32, _format_number(value))

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
    pdf.setFont("Poppins-Regular", 10)
    pdf.drawString(x, y + 16, label)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 10)
    txt_w = stringWidth(value_text, "Poppins-Regular", 10)
    pdf.drawString(x + w - txt_w, y + 16, value_text)
    _progress_bar(pdf, x, y, w, bar_h, ratio, bar_color, back_color)

def _simple_bar_chart(pdf, x, y, w, h, chart_series, allowed_months: set[int] | None = None, allowed_years: set[str] | None = None):
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
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
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
    for key in series_keys:
        arr = [0.0] * 12
        for pt in chart_series.get(key, []):
            m = str(pt.get("month", ""))
            if m in months:
                idx = months.index(m)
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
    # Determine which months to render based on allowed_months (1..12)
    if allowed_months:
        month_numbers = sorted([m for m in allowed_months if 1 <= int(m) <= 12])
        if not month_numbers:
            month_numbers = list(range(1, 13))
    else:
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
            bh = (v / vmax) * (gh - 10)
            bx = group_x + si * (bar_w + group_w * inner_gap_ratio)
            pdf.rect(bx, gy, bar_w, bh, stroke=0, fill=1)
        lbl = months[mi]
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        lw = stringWidth(lbl, "Poppins-Regular", 8)
        pdf.drawString(slot_x + (slot_w - lw) / 2, gy - 14, lbl)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 9)
    pdf.drawString(gx - 18, gy + gh + 6, "kg")
    if series_keys:
        sq = 8
        cur_x = x + w - 10
        pdf.setFont("Poppins-Regular", 9)
        for si in reversed(range(len(series_keys))):
            label = str(series_keys[si])
            lw = stringWidth(label, "Poppins-Regular", 9)
            entry_w = sq + 6 + lw + 12
            cur_x -= entry_w
            pdf.setFillColor(SERIES_COLORS[si % len(SERIES_COLORS)])
            pdf.rect(cur_x, y + h - 18, sq, sq, stroke=0, fill=1)
            pdf.setFillColor(TEXT)
            pdf.drawString(cur_x + sq + 6, y + h - 18, label)

def _footer(pdf, page_width_points: float):
    text = "Copyright © 2018–2023 GEPP Sa-Ard Co., Ltd. ALL RIGHTS RESERVED"
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 9)
    tw = stringWidth(text, "Poppins-Regular", 9)
    pdf.drawString((page_width_points - tw) / 2, 0.25 * inch, text)

def _parse_date_to_date(value) -> datetime.date | None:
    """
    Parse various incoming date strings to a date (no timezone effects).
    Supports:
      - '01 Jan 2025' (d Mon YYYY)
      - '2025-01-01' (ISO date)
      - '2025/01/01'
      - '01/01/2025'
      - ISO datetime variants, e.g. '2025-01-01T00:00:00Z' or with offsets
    Returns None if parsing fails.
    """
    try:
        if isinstance(value, datetime):
            return value.date()
    except Exception:
        pass
    s = str(value or "").strip()
    if not s:
        return None
    # Fast-path: ISO date in first 10 chars
    try:
        if len(s) >= 10 and s[4] == "-" and s[7] == "-":
            ymd = s[:10]
            # datetime.fromisoformat accepts 'YYYY-MM-DD'
            return datetime.fromisoformat(ymd).date()
    except Exception:
        pass
    # ISO datetime variants
    try:
        iso_norm = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_norm)
        return dt.date()
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
    d = Drawing(size, size)
    pie = Pie()
    pie.x = 0
    pie.y = 0
    pie.width = size
    pie.height = size
    pie.data = vals
    pie.labels = None
    pie.strokeWidth = 0
    pie.slices.strokeWidth = max(0, int(gap_width))
    pie.slices.strokeColor = gap_color
    for i in range(len(vals)):
        pie.slices[i].fillColor = colors_list[i % len(colors_list)]
    d.add(pie)
    renderPDF.draw(d, pdf, x, y)

def draw_table(pdf, x, y, w, h, r=6, type="Header"):
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
    middle = page_height_points / 2
    pdf.setFillColor(PRIMARY)
    pdf.setFont("Poppins-Bold", 100)
    pdf.drawString(0.63 * inch, middle + 20, "2025")
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 38.5)
    pdf.drawString(0.63 * inch, middle - 20, "GEPP REPORT")
    pdf.setFont("Poppins-Regular", 16.5)
    pdf.drawString(0.63 * inch, middle - 40, "Data-Driven Transaformation")
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
        img_y = middle - 45
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
        pdf.rect(4.54 * inch, middle - 45, page_width_points - (4.54 * inch), 2.07 * inch, fill=1, stroke=0)

def draw_overview(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Overview")
    margin = 0.78 * inch
    # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
    content_top = page_height_points - (1.96 * inch) - 24
    col_gap = 0.25 * inch
    left_col_w = 3.7 * inch
    right_col_w = page_width_points - margin - margin - left_col_w - col_gap
    chip_w = 1.78 * inch
    chip_h = 0.60 * inch
    chip_y = content_top - chip_h
    chip_gap = 8
    _stat_chip(pdf, margin, chip_y, chip_w, chip_h, "Total Transactions", data["overview_data"]["transactions_total"])
    _stat_chip(pdf, margin + chip_w + chip_gap, chip_y, chip_w, chip_h, "Total Approved", data["overview_data"]["transactions_approved"])
    ki_h = 2.2 * inch
    ki_y = chip_y - 8 - ki_h
    _rounded_card(pdf, margin, ki_y, left_col_w, ki_h, radius=8)
    pad = 20
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(margin + pad, ki_y + ki_h - 30, "Key Indicators")
    ki = data["overview_data"]["key_indicators"]
    tw = float(ki.get("total_waste", 0) or 0)
    rr = float(ki.get("recycle_rate", 0) or 0)
    ghg = float(ki.get("ghg_reduction", 0) or 0)
    norm_base = max(tw, ghg, 1.0)
    row_w = left_col_w - 2 * pad
    row_x = margin + pad
    row_y = ki_y + ki_h - 50
    _label_progress(pdf, row_x, row_y - 24, row_w, "Total Waste (kg)", _format_number(tw), tw / norm_base, colors.HexColor("#b7c6cc"), colors.HexColor("#e1e7ef"), bar_h=6)
    _label_progress(pdf, row_x, row_y - 58, row_w, "Recycle rate (%)", f"{rr:,.2f}", rr / 100.0, colors.HexColor("#8fcfc6"), colors.HexColor("#e1e7ef"), bar_h=6)
    _label_progress(pdf, row_x, row_y - 92, row_w, "GHG Reduction (kgCO2e)", _format_number(ghg), ghg / norm_base, colors.HexColor("#77b9d8"), colors.HexColor("#e1e7ef"), bar_h=6)
    tr_h = 2.15 * inch
    tr_y = ki_y - 8 - tr_h
    _rounded_card(pdf, margin, tr_y, left_col_w, tr_h, radius=8)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(margin + pad, tr_y + tr_h - 30, "Top Recyclables")
    items = data["overview_data"].get("top_recyclables", [])[:3]
    if items:
        max_val = max(float(it.get("total_waste", 0) or 0) for it in items) or 1.0
        y_ptr = tr_y + tr_h - 72
        for it in items:
            name = str(it.get("origin_name", ""))
            val = float(it.get("total_waste", 0) or 0)
            ratio = val / max_val
            _label_progress(pdf, margin + pad, y_ptr, left_col_w - 2 * pad, name, _format_number(val), ratio, colors.HexColor("#c8ced4"), colors.HexColor("#e1e7ef"), bar_h=6)
            y_ptr -= 32
    overall_x = margin + left_col_w + col_gap
    overall_y = tr_y
    overall_h = (chip_y - overall_y) + chip_h
    _rounded_card(pdf, overall_x, overall_y, right_col_w, overall_h, radius=8, fill=WHITE)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(overall_x + 16, overall_y + overall_h - 30, "Overall")
    stats = data["overview_data"]["overall_charts"]["chart_stat_data"]
    sw = 1.78 * inch
    sh = 0.60 * inch
    sy = overall_y + overall_h - 26 - 16 - sh
    for i, st in enumerate(stats[:3]):
        sx = overall_x + 16 + i * (sw + 8)
        _stat_chip(pdf, sx, sy, sw, sh, st["title"], st["value"], "white")
    chart_data = data["overview_data"]["overall_charts"]["chart_data"]
    cy = overall_y + 16
    ch = (sy - cy - 16) * 0.85
    # Filter bars to only months within the date range (robust parsing)
    allowed_months: set[int] | None = None
    allowed_years: set[str] | None = None
    df_date = _parse_date_to_date(data.get("date_from"))
    dt_date = _parse_date_to_date(data.get("date_to"))
    if df_date and not dt_date:
        dt_date = df_date
    if dt_date and not df_date:
        df_date = dt_date
    if df_date and dt_date:
        if dt_date < df_date:
            df_date, dt_date = dt_date, df_date
        y_from = df_date.year
        y_to = dt_date.year
        months_set: set[int] = set()
        for y in range(y_from, y_to + 1):
            m_start = 1 if y > y_from else df_date.month
            m_end = 12 if y < y_to else dt_date.month
            for m in range(m_start, m_end + 1):
                months_set.add(int(m))
        allowed_months = months_set
        allowed_years = {str(y) for y in range(y_from, y_to + 1)}
    _simple_bar_chart(pdf, overall_x + 12, cy, right_col_w - 24, ch, chart_data, allowed_months, allowed_years)
    _footer(pdf, page_width_points)

def draw_performance(pdf, page_width_points: float, page_height_points: float, data: dict, performance_data: dict) -> None:
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Performance")
    margin = 0.78 * inch
    # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
    content_top = page_height_points - (1.96 * inch) - 24
    left_card_w = 3.22 * inch
    left_card_h = 4.54 * inch
    left_card_y = content_top - left_card_h
    _rounded_card(pdf, margin, left_card_y, left_card_w, left_card_h, radius=8, fill=WHITE)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    # Position text relative to card top (content_top)
    pdf.drawString(1 * inch, content_top - 0.4 * inch, f"{performance_data['branchName']}")
    pdf.setFont("Poppins-Regular", 8)
    label_text = "Recycling Rate"
    label_width = stringWidth(label_text, "Poppins-Medium", 8)
    pdf.drawString(3.82 * inch - label_width, content_top - 0.27 * inch, label_text)
    pdf.setFont("Poppins-Bold", 13)
    value_text = f"{performance_data['recyclingRatePercent']} %"
    value_width = stringWidth(value_text, "Poppins-Medium", 13)
    pdf.drawString(3.82 * inch - value_width, content_top - 0.52 * inch, value_text)
    for idx, (label, amount) in enumerate(performance_data["metrics"].items()):
        start_y = content_top - 0.96 * inch
        bar_h = 0.08 * inch
        gap = 0.36 * inch
        y = start_y - idx * (bar_h + gap)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        pdf.drawString(1 * inch, y + bar_h + 0.12 * inch, label)
        value_text = f"{amount} kg"
        value_width = stringWidth(value_text, "Poppins-Regular", 8)
        pdf.drawString(1 * inch + 2.8 * inch - value_width, y + bar_h + 0.12 * inch, value_text)
        _progress_bar(pdf, 1 * inch, y, 2.8 * inch, bar_h, amount / performance_data["totalWasteKg"], MATERIAL_COLORS[label])
    gap = 1 * inch
    outer_x = gap + 3.22 * inch
    outer_y = left_card_y
    outer_w = 6.8 * inch
    outer_h = 4.54 * inch
    _rounded_card(pdf, outer_x, outer_y, outer_w, outer_h, radius=8, fill=colors.HexColor("#f1f5f9"))
    pad = 16
    inner_x = outer_x + pad
    inner_y = outer_y + pad
    inner_w = outer_w - 2 * pad
    inner_h = outer_h - 2 * pad
    _rounded_card(pdf, inner_x, inner_y, inner_w, inner_h, radius=8, fill=WHITE)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(inner_x + 16, inner_y + inner_h - 16 - 12, "All Building")
    pdf.setFont("Poppins-Regular", 10)
    for idx, building in enumerate(performance_data["buildings"]):
        y = inner_y + inner_h - 0.85 * inch - idx * (0.55 * inch)
        pdf.setFillColor(TEXT)
        pdf.drawString(inner_x + 16, y, building["buildingName"])
        value_text = f"{building['totalWasteKg']} kg"
        value_width = stringWidth(value_text, "Poppins-Regular", 8)
        pdf.drawString(inner_x + 4 * inch - value_width, y, value_text)
        _progress_bar(pdf, inner_x + 16, y - 0.2 * inch, inner_x - 0.5 * inch, 0.08 * inch, building['totalWasteKg'] / performance_data["totalWasteKg"], colors.HexColor("#b7cbd6"))
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 10)
    pie_size = 1.20 * inch
    pie_x = inner_x + inner_w - pie_size - 16
    title1_y = inner_y + inner_h - 48
    pdf.drawString(pie_x, title1_y, "Total Buildings")
    buildings_values = [float(b.get("totalWasteKg", 0) or 0) for b in performance_data.get("buildings", [])]
    mono_color = colors.HexColor("#b7cbd6")
    mono_colors_list = [mono_color for _ in buildings_values] or [mono_color]
    _simple_pie_chart(pdf, pie_x, title1_y - 8 - pie_size, pie_size, buildings_values, mono_colors_list, gap_width=1, gap_color=colors.white)
    title2_y = title1_y - pie_size - 32
    pdf.drawString(pie_x, title2_y, "All Types of Waste")
    metrics_items = list(performance_data.get("metrics", {}).items())
    waste_values = [float(v or 0) for _, v in metrics_items]
    waste_colors = [MATERIAL_COLORS.get(lbl, BAR3) for lbl, _ in metrics_items]
    if not waste_colors:
        waste_colors = SERIES_COLORS
    _simple_pie_chart(pdf, pie_x, title2_y - 8 - pie_size, pie_size, waste_values, waste_colors, gap_width=1, gap_color=colors.white)
    _footer(pdf, page_width_points)

def draw_performance_table(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    branches_per_page = 7
    total_branches = len(data["performance_data"])
    icon_path = "scripts/BranchIcon.png"
    icon_size = 10
    for page_idx in range(0, total_branches, branches_per_page):
        pdf.showPage()
        _header(pdf, page_width_points, page_height_points, data)
        _sub_header(pdf, page_width_points, page_height_points, data, "Performance")
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Medium", 12)
        pdf.drawString(padding, page_height_points - (2.5 * inch), "Detailed Performance Metrics")
        pdf.setFillColor(colors.HexColor("#f1f5f9"))
        draw_table(pdf, padding, page_height_points - (3 * inch), page_width_points - 2 * padding, 24, 8, "Header")
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        pdf.drawString(padding + 16, page_height_points - (2.88 * inch), "Building Name")
        pdf.drawString(padding + 1.8 * inch, page_height_points - (2.88 * inch), "Total Waste (kg)")
        pdf.drawString(padding + 3.2 * inch, page_height_points - (2.88 * inch), "General (kg)")
        pdf.drawString(padding + 4.4 * inch, page_height_points - (2.88 * inch), "Total Recyclable incl. Recycled Organic Waste (kg)")
        pdf.drawString(padding + 7.7 * inch, page_height_points - (2.88 * inch), "Recycling Rate (%)")
        pdf.drawString(padding + 9.3 * inch, page_height_points - (2.88 * inch), "Status")
        page_branches = data["performance_data"][page_idx:page_idx + branches_per_page]
        for idx, branch in enumerate(page_branches):
            y_base = page_height_points - (3 * inch) - 32 - (idx * 32)
            table_type = "Footer" if idx == len(page_branches) - 1 else "Body"
            pdf.setFillColor(WHITE)
            draw_table(pdf, padding, y_base, page_width_points - 2 * padding, 32, 8, table_type)
            pdf.setFillColor(TEXT)
            pdf.setFont("Poppins-Regular", 8)
            y_text = y_base + 12
            pdf.drawImage(icon_path, padding + 16, y_base + 11, width=icon_size, height=icon_size, mask='auto')
            pdf.drawString(padding + 30, y_base + 12, branch["branchName"])
            pdf.drawString(padding + 1.8 * inch, y_text, _format_number(branch["totalWasteKg"]))
            general = branch.get("metrics", {}).get("General Waste") or 0
            pdf.drawString(padding + 3.2 * inch, y_text, _format_number(general))
            recyclable = branch.get("metrics", {}).get("Recyclable Waste") or 0
            organic = branch.get("metrics", {}).get("Organic Waste") or 0

            pdf.drawString(
                padding + 4.4 * inch,
                y_text,
                _format_number(recyclable + organic)
            )

            pdf.drawString(padding + 7.7 * inch, y_text, f"{branch['recyclingRatePercent']} %")
            color = colors.HexColor("#0bb980") if branch["recyclingRatePercent"] > 20 else colors.HexColor("#f49d0d")
            pdf.setFillColor(color)
            circle_radius = 3.5
            circle_x = padding + 9.2 * inch
            pdf.circle(circle_x, y_text + 3, circle_radius, stroke=0, fill=1)
            pdf.drawString(padding + 9.3 * inch, y_text, "Normal" if branch["recyclingRatePercent"] > 20 else "Need Imprv")

def draw_comparison_advice(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    # Skip rendering if there's an error in comparison data
    comparison_data = data.get("comparison_data", {}) or {}
    if comparison_data.get("error"):
        return
    
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Comparison")
    margin = 0.78 * inch
    # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
    content_top = page_height_points - (1.96 * inch) - 24
    gap = 0.3 * inch
    card_w = (page_width_points - 2 * margin - 2 * gap) / 3.0
    card_h = 5 * inch
    card_y = content_top - card_h
    cards = [
        {"x": margin, "title": "Opportunities", "data": comparison_data.get("scores", {}).get("opportunities", [])},
        {"x": margin + card_w + gap, "title": "Quick Wins", "data": comparison_data.get("scores", {}).get("quickwins", [])},
        {"x": margin + 2 * (card_w + gap), "title": "Risks", "data": comparison_data.get("scores", {}).get("risks", [])}
    ]
    for card in cards:
        _rounded_card(pdf, card["x"], card_y, card_w, card_h, radius=8, fill=WHITE)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Medium", 14)
        pdf.drawString(card["x"] + 16, card_y + card_h - 24, card["title"])
    body_font = "Poppins-Regular"
    body_size = 10
    leading = 12
    pad = 16
    paragraph_gap = 8
    label_font = "Poppins-Medium"
    label_size = 11
    def _draw_recommendations(items, x_left):
        y_cursor = card_y + card_h - 50
        max_w = card_w - 2 * pad
        pdf.setFillColor(TEXT)
        pdf.setFont(body_font, body_size)
        for itm in items[:2]:
            rec = str(itm.get("recommendation", "")).strip()
            if not rec:
                continue
            crit_name = str(itm.get("criteria_name") or itm.get("condition_name") or itm.get("name") or "").strip()
            display_name = crit_name.replace("_", " ") if crit_name else ""
            # Build text without header prefix for wrapping (just the recommendation text)
            rec_text = rec
            text_x_offset = 0
            usable_w = max_w
            pdf.setFont(body_font, body_size)
            lines = _wrap_text_lines(pdf, rec_text, usable_w, body_font, body_size)
            if not lines:
                continue
            if y_cursor < (card_y + pad):
                return
            first_line_x = x_left + pad + text_x_offset
            header_prefix = f"{display_name}:" if display_name else ""
            if header_prefix:
                # Draw the header prefix in medium font on its own line
                pdf.setFont(label_font, label_size)
                pdf.drawString(first_line_x, y_cursor, header_prefix)
                y_cursor -= leading
            # Draw all recommendation text lines in body font on new line(s)
            if lines:
                pdf.setFont(body_font, body_size)
                for line in lines:
                    if y_cursor < (card_y + pad):
                        return
                    pdf.drawString(first_line_x, y_cursor, line)
                    y_cursor -= leading
            else:
                pdf.setFont(body_font, body_size)
                pdf.drawString(first_line_x, y_cursor, rec)
                y_cursor -= leading
            y_cursor -= paragraph_gap
            if y_cursor < (card_y + pad):
                return
    for card in cards:
        _draw_recommendations(card["data"], card["x"])
    _footer(pdf, page_width_points)

def draw_comparison(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Comparison")
    # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
    content_top = page_height_points - (1.96 * inch) - 24
    card_x = padding
    card_h = 5.2 * inch
    card_y = content_top - card_h
    card_w = page_width_points - 2 * padding
    _rounded_card(pdf, card_x, card_y, card_w, card_h, radius=8, fill=WHITE)
    
    # Check for error message
    comparison_data = data.get("comparison_data", {}) or {}
    error_msg = comparison_data.get("error")
    if error_msg:
        # Display error message
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Medium", 14)
        error_y = card_y + card_h / 2.0
        pdf.drawCentredString(card_x + card_w / 2.0, error_y, error_msg)
        return
    
    pad = 20
    legend_w = 3.0 * inch
    bars_w = card_w - 2 * pad - legend_w
    bars_center_x = card_x + pad + (bars_w / 2.0)
    top_y = card_y + card_h - 48
    bottom_y = card_y + 28
    left_mat = (comparison_data.get("left", {}) or {}).get("material", {}) or {}
    right_mat = (comparison_data.get("right", {}) or {}).get("material", {}) or {}
    left_period = str((data.get("comparison_data", {}).get("left", {}) or {}).get("period", ""))
    right_period = str((data.get("comparison_data", {}).get("right", {}) or {}).get("period", ""))
    # Prefer categories present in data; fallback to predefined list
    categories_default = [
        "Organic Waste","Recyclable Waste","Construction Waste","General Waste",
        "Electronic Waste","Hazardous Waste","Waste To Energy","Bio-Hazardous Waste",
    ]
    data_keys = []
    try:
        data_keys = list({*(left_mat.keys() if isinstance(left_mat, dict) else []), *(right_mat.keys() if isinstance(right_mat, dict) else [])})
    except Exception:
        data_keys = []
    # Use default categories that actually appear; else use any data keys; else fallback to default list
    categories = [k for k in categories_default if (k in left_mat) or (k in right_mat)]
    if not categories:
        categories = (data_keys[:8] if data_keys else categories_default)
    def get_val(d, k):
        try:
            return float(d.get(k, 0) or 0)
        except Exception:
            return 0.0
    max_val = max([1.0] + [get_val(left_mat, c) for c in categories] + [get_val(right_mat, c) for c in categories])
    half_w = (bars_w / 2.0) - 6
    bar_h = 26
    row_gap = 40
    cap_r = min(bar_h * 0.35, bar_h / 2.0)
    pdf.setStrokeColor(STROKE)
    pdf.setLineWidth(1)
    pdf.line(bars_center_x, bottom_y, bars_center_x, top_y + 8)
    # Extract years for display
    def extract_year_from_period(period_str: str) -> str:
        if not period_str:
            return ""
        # Try to extract year from date range format "DD MMM YYYY - DD MMM YYYY"
        parts = period_str.split(" - ")
        if len(parts) >= 1:
            date_part = parts[0].strip()
            # Extract year (last 4 digits)
            words = date_part.split()
            for word in reversed(words):
                if word.isdigit() and len(word) == 4:
                    return word
        return ""
    
    left_period = str((data.get("comparison_data", {}).get("left", {}) or {}).get("period", ""))
    right_period = str((data.get("comparison_data", {}).get("right", {}) or {}).get("period", ""))
    left_year = extract_year_from_period(left_period) or "Last Year"
    right_year = extract_year_from_period(right_period) or "Current Year"
    
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 14)
    lpw = stringWidth(left_year, "Poppins-Medium", 14)
    pdf.drawString(bars_center_x - 8 - lpw, top_y + 20, left_year)
    pdf.drawString(bars_center_x + 8, top_y + 20, right_year)
    left_color = colors.HexColor("#d3dbe3")
    right_color = colors.HexColor("#c9e7df")
    def draw_right_bar(center_x, y_mid, length, height, color):
        if length <= 0:
            return 0.0
        r = min(cap_r, height / 2.0, length)
        rect_len = max(0.0, length - r)
        left = center_x
        right = center_x + length
        bottom = y_mid - height / 2.0
        top = y_mid + height / 2.0
        p = pdf.beginPath()
        p.moveTo(left, bottom)
        p.lineTo(right - r, bottom)
        p.arcTo(right - 2 * r, bottom, right, bottom + 2 * r, startAng=270, extent=90)
        p.lineTo(right, top - r)
        p.arcTo(right - 2 * r, top - 2 * r, right, top, startAng=0, extent=90)
        p.lineTo(left, top)
        p.lineTo(left, bottom)
        pdf.setFillColor(color)
        pdf.drawPath(p, stroke=0, fill=1)
        return rect_len
    def draw_left_bar(center_x, y_mid, length, height, color):
        if length <= 0:
            return 0.0
        r = min(cap_r, height / 2.0, length)
        rect_len = max(0.0, length - r)
        right = center_x
        left = center_x - length
        bottom = y_mid - height / 2.0
        top = y_mid + height / 2.0
        p = pdf.beginPath()
        p.moveTo(right, bottom)
        p.lineTo(left + r, bottom)
        p.arcTo(left, bottom, left + 2 * r, bottom + 2 * r, startAng=270, extent=-90)
        p.lineTo(left, top - r)
        p.arcTo(left, top - 2 * r, left + 2 * r, top, startAng=180, extent=-90)
        p.lineTo(right, top)
        p.lineTo(right, bottom)
        pdf.setFillColor(color)
        pdf.drawPath(p, stroke=0, fill=1)
        return rect_len
    pdf.setFont("Poppins-Medium", 11)
    for idx, cat in enumerate(categories):
        y = top_y - idx * row_gap
        left_v = get_val(left_mat, cat)
        right_v = get_val(right_mat, cat)
        left_len = max(0.0, min(half_w, (left_v / max_val) * half_w))
        right_len = max(0.0, min(half_w, (right_v / max_val) * half_w))
        left_rect = draw_left_bar(bars_center_x, y, left_len, bar_h, left_color)
        right_rect = draw_right_bar(bars_center_x, y, right_len, bar_h, right_color)
        txt_left = _format_number(left_v)
        txt_right = _format_number(right_v)
        pdf.setFillColor(TEXT)
        sw_left = stringWidth(txt_left, "Poppins-Medium", 11)
        avail_left = max(0.0, left_rect - 16)
        if left_rect > 0 and sw_left <= avail_left:
            x_text = bars_center_x - left_rect + 8
            pdf.drawString(x_text, y - 4, txt_left)
        else:
            x_out = max(card_x + 6, bars_center_x - left_len - sw_left - 8)
            pdf.drawString(x_out, y - 4, txt_left)
        sw_right = stringWidth(txt_right, "Poppins-Medium", 11)
        avail_right = max(0.0, right_rect - 16)
        if right_rect > 0 and sw_right <= avail_right:
            x_text = bars_center_x + right_rect - sw_right - 8
            pdf.drawString(x_text, y - 4, txt_right)
        else:
            x_out_candidate = bars_center_x + right_len + 8
            x_max = (card_x + card_w - legend_w + 8) - sw_right - 4
            x_out = min(x_out_candidate, x_max)
            pdf.drawString(max(bars_center_x + 4, x_out), y - 4, txt_right)
    legend_x = card_x + card_w - legend_w + 8
    y_legend = top_y
    pdf.setFillColor(TEXT)
    for idx, cat in enumerate(categories):
        y = y_legend - idx * row_gap
        pdf.setFont("Poppins-Medium", 12)
        display_name = cat.replace(" Waste", "")
        display_name = display_name.replace("Bio-Hazardous", "Bio-Hazardous")
        pdf.drawString(legend_x, y + 8, display_name if display_name != "Waste To Energy" else "Waste To Energy")
        lval = get_val(left_mat, cat)
        rval = get_val(right_mat, cat)
        delta = rval - lval
        sign = "+" if delta >= 0 else "-"
        abs_delta = abs(delta)
        if abs(abs_delta - round(abs_delta)) < 1e-6:
            delta_str = f"{int(round(abs_delta))}"
        else:
            delta_str = f"{abs_delta:,.1f}"
        pdf.setFont("Poppins-Regular", 11)
        pdf.drawString(legend_x, y - 8, f"{sign} {delta_str} kg.")
    _footer(pdf, page_width_points)
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Comparison")
    margin = padding
    # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
    content_top = page_height_points - (1.96 * inch) - 24
    gap = 0.3 * inch
    card_w2 = (page_width_points - 2 * margin)
    card_h2 = 2.2 * inch
    # Position upper card starting at content_top
    upper_card_y = content_top - card_h2
    lower_card_y = upper_card_y - card_h2 - gap
    card_y2 = upper_card_y
    x_left = margin
    _rounded_card(pdf, x_left, card_y2, card_w2, card_h2, radius=8, fill=WHITE)
    _rounded_card(pdf, x_left, lower_card_y, card_w2, card_h2, radius=8, fill=WHITE)
    left_months = (data.get("comparison_data", {}).get("left", {}) or {}).get("month", {}) or {}
    right_months = (data.get("comparison_data", {}).get("right", {}) or {}).get("month", {}) or {}
    # Extract years from date_from and date_to, or from period strings
    def extract_year(period_str: str) -> str:
        if not period_str:
            return ""
        # Try to extract year from date range format "DD MMM YYYY - DD MMM YYYY"
        parts = period_str.split(" - ")
        if len(parts) >= 1:
            date_part = parts[0].strip()
            # Extract year (last 4 digits)
            words = date_part.split()
            for word in reversed(words):
                if word.isdigit() and len(word) == 4:
                    return word
        return ""
    
    left_period = (data.get("comparison_data", {}).get("left", {}) or {}).get("period", "") or ""
    right_period = (data.get("comparison_data", {}).get("right", {}) or {}).get("period", "") or ""
    series_a_label = extract_year(left_period) or "Last Year"
    series_b_label = extract_year(right_period) or "Current Year"
    _months_short = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    _map_idx = {m.lower(): i for i, m in enumerate(_months_short)}
    _map_idx.update({
        "january": 0, "february": 1, "march": 2, "april": 3, "may": 4, "june": 5,
        "july": 6, "august": 7, "september": 8, "october": 9, "november": 10, "december": 11
    })
    def _month_index(k):
        s = str(k).strip()
        lower = s.lower()
        if lower in _map_idx:
            return _map_idx[lower]
        try:
            n = int(s)
            if 1 <= n <= 12:
                return n - 1
        except Exception:
            pass
        return 99
    def _month_label(k):
        idx = _month_index(k)
        return _months_short[idx] if 0 <= idx < 12 else str(k)
    month_keys = sorted(set(list(left_months.keys()) + list(right_months.keys())), key=_month_index)
    pad2 = 16
    title_y2 = card_y2 + card_h2 - 20
    chart_left2 = x_left + 44
    chart_right2 = x_left + card_w2 - pad2
    chart_bottom2 = card_y2 + 24
    chart_top2 = card_y2 + card_h2 - 36
    chart_w2 = max(1.0, chart_right2 - chart_left2)
    chart_h2 = max(1.0, chart_top2 - chart_bottom2)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(x_left + pad2, title_y2, "Quantity Comparison")
    sw2 = 10
    sh2 = 6
    s1w2 = stringWidth(series_a_label, "Poppins-Regular", 9)
    s2w2 = stringWidth(series_b_label, "Poppins-Regular", 9)
    total_legend_w2 = sw2 + 6 + s1w2 + 14 + sw2 + 6 + s2w2
    lx2 = chart_right2 - pad2 - total_legend_w2 + pad2
    ly2 = title_y2 + 1
    pdf.setFillColor(BAR)
    pdf.roundRect(lx2, ly2, sw2, sh2, 3, stroke=0, fill=1)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 9)
    pdf.drawString(lx2 + sw2 + 6, ly2 - 1, series_a_label)
    lx2b = lx2 + sw2 + 6 + s1w2 + 14
    pdf.setFillColor(BAR2)
    pdf.roundRect(lx2b, ly2, sw2, sh2, 3, stroke=0, fill=1)
    pdf.setFillColor(TEXT)
    pdf.drawString(lx2b + sw2 + 6, ly2 - 1, series_b_label)
    max_val2 = 1.0
    for mk in month_keys:
        lv = float(left_months.get(mk, 0) or 0)
        rv = float(right_months.get(mk, 0) or 0)
        if lv > max_val2:
            max_val2 = lv
        if rv > max_val2:
            max_val2 = rv
    mag2 = 1.0
    while mag2 * 10 <= max_val2:
        mag2 *= 10.0
    for mul in (1.0, 2.0, 2.5, 5.0, 10.0):
        top_val2 = mul * mag2
        if top_val2 >= max_val2:
            break
    ticks2 = [0.0, top_val2 / 2.0, top_val2]
    pdf.setStrokeColor(STROKE)
    pdf.setLineWidth(0.5)
    for tv in ticks2:
        y = chart_bottom2 + (tv / top_val2) * chart_h2
        pdf.line(chart_left2, y, chart_right2, y)
        lbl = _format_number(round(tv))
        lw = stringWidth(lbl, "Poppins-Regular", 8)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        pdf.drawString(chart_left2 - 6 - lw, y - 3, lbl)
    pdf.saveState()
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 9)
    pdf.translate(x_left + 12, (chart_bottom2 + chart_top2) / 2.0)
    pdf.rotate(90)
    pdf.drawCentredString(0, 0, "Kg.")
    pdf.restoreState()
    def _draw_top_round_rect(x, y, w, h, r, color):
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
    groups2 = max(1, len(month_keys))
    group_gap2 = min(22, max(8, chart_w2 / max(3.0, groups2 * 4.0)))
    group_w2 = max(1.0, (chart_w2 - (groups2 - 1) * group_gap2) / groups2)
    bar_gap2 = min(10, max(5, group_w2 * 0.18))
    bar_w2 = max(5, min(24, (group_w2 - bar_gap2) / 2.0))
    for i, mk in enumerate(month_keys):
        gx = chart_left2 + i * (group_w2 + group_gap2)
        inner_offset2 = (group_w2 - (2 * bar_w2 + bar_gap2)) / 2.0
        lv = float(left_months.get(mk, 0) or 0)
        lh = (lv / top_val2) * chart_h2
        _draw_top_round_rect(gx + inner_offset2, chart_bottom2, bar_w2, lh, min(bar_w2 * 0.25, 5), BAR)
        rv = float(right_months.get(mk, 0) or 0)
        rh = (rv / top_val2) * chart_h2
        _draw_top_round_rect(gx + inner_offset2 + bar_w2 + bar_gap2, chart_bottom2, bar_w2, rh, min(bar_w2 * 0.25, 5), BAR2)
        mlabel = _month_label(mk)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 9)
        mw2 = stringWidth(mlabel, "Poppins-Regular", 9)
        pdf.drawString(gx + (group_w2 - mw2) / 2.0, card_y2 + 8, mlabel)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(x_left + pad2, lower_card_y + card_h2 - 24, f"Period Details : {series_a_label} vs {series_b_label}")
    pdf.setFillColor(colors.HexColor("#f1f5f9"))
    draw_table(pdf, padding, lower_card_y + card_h2 - 58, page_width_points - 2 * padding, 24, 8, "Header")
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 8)
    months_for_header = (month_keys or [])[:12]
    col_count = max(2, len(months_for_header) + 2)
    header_x0 = padding
    header_w = page_width_points - 2 * padding
    col_w = header_w / float(col_count)
    header_y = lower_card_y + card_h2 - 50
    pdf.drawCentredString(header_x0 + (0.5 * col_w), header_y, "Period")
    for idx, mk in enumerate(months_for_header, start=1):
        pdf.drawCentredString(header_x0 + (idx + 0.5) * col_w, header_y, _month_label(mk))
    pdf.drawCentredString(header_x0 + (col_count - 0.5) * col_w, header_y, "Total")
    row_h = 32
    first_row_y = (lower_card_y + card_h2 - 58) - row_h
    second_row_y = first_row_y - row_h
    third_row_y = second_row_y - row_h
    pdf.setFillColor(WHITE)
    draw_table(pdf, padding, first_row_y, page_width_points - 2 * padding, row_h, 8, "Body")
    draw_table(pdf, padding, second_row_y, page_width_points - 2 * padding, row_h, 8, "Body")
    draw_table(pdf, padding, third_row_y, page_width_points - 2 * padding, row_h, 8, "Footer")
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 8)
    y_text_1 = first_row_y + 12
    y_text_2 = second_row_y + 12
    y_text_3 = third_row_y + 12
    pdf.drawString(header_x0 + 16, y_text_1, str(series_a_label or "Left"))
    pdf.drawString(header_x0 + 16, y_text_2, str(series_b_label or "Right"))
    pdf.drawString(header_x0 + 16, y_text_3, "Total")
    left_total = 0.0
    right_total = 0.0
    for idx, mk in enumerate(months_for_header, start=1):
        lv = float(left_months.get(mk, 0) or 0)
        rv = float(right_months.get(mk, 0) or 0)
        left_total += lv
        right_total += rv
        cx = header_x0 + (idx + 0.5) * col_w
        pdf.drawCentredString(cx, y_text_1, _format_number(lv))
        pdf.drawCentredString(cx, y_text_2, _format_number(rv))
        delta = rv - lv
        abs_delta = abs(delta)
        sign = "+" if delta >= 0 else "-"
        pdf.drawCentredString(cx, y_text_3, f"{sign}{_format_number(abs_delta)}")
    cx_total = header_x0 + (col_count - 0.5) * col_w
    pdf.drawCentredString(cx_total, y_text_1, _format_number(left_total))
    pdf.drawCentredString(cx_total, y_text_2, _format_number(right_total))
    total_delta = right_total - left_total
    abs_total_delta = abs(total_delta)
    sign_total = "+" if total_delta >= 0 else "-"
    pdf.drawCentredString(cx_total, y_text_3, f"{sign_total}{_format_number(abs_total_delta)}")
    _footer(pdf, page_width_points)

def draw_main_materials(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Main Materials")
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
    pdf.setFont("Poppins-Regular", 10)
    max_label_area = bar_card * 0.45
    min_label_area = 60
    longest_word_w = max((stringWidth(w, "Poppins-Regular", 10) for it in items_top for w in str(it.get("main_material_name", "")).split()), default=40)
    label_area = max(min_label_area, longest_word_w + 6)
    label_area = min(label_area, max_label_area)
    chart_left = x_left + pad + label_area + 8
    chart_right = x_left + bar_card - pad
    chart_bottom = card_y2 + 28
    chart_top = card_y2 + card_h2 - 40
    chart_w = max(1.0, chart_right - chart_left)
    chart_h = max(1.0, chart_top - chart_bottom)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(x_left + pad, title_y, "Top Materials by Quantity")
    max_val = max([1.0] + [float(it.get("total_waste", 0) or 0) for it in items_top])
    mag = 1.0
    while mag * 10 <= max_val:
        mag *= 10.0
    for mul in (1.0, 2.0, 2.5, 5.0, 10.0):
        top_val = mul * mag
        if top_val >= max_val:
            break
    ticks = [0.0, top_val / 2.0, top_val]
    pdf.setStrokeColor(STROKE)
    pdf.setLineWidth(0.5)
    for tv in ticks:
        x = chart_left + (tv / top_val) * chart_w
        pdf.line(x, chart_bottom, x, chart_top)
        lbl = _format_number(round(tv))
        lw = stringWidth(lbl, "Poppins-Regular", 9)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 9)
        pdf.drawCentredString(x, chart_bottom - 12, lbl)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 10)
    pdf.drawRightString(chart_right + 12, chart_bottom - 26, "Kg.")
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
        bar_color = colors.HexColor(main_material_colorPalette[i % len(main_material_colorPalette)])
        _draw_right_round_rect(chart_left, y_bar, w, row_h, cap_r, bar_color)
        name = str(it.get("main_material_name", ""))
        label_lines = wrap_label(name, "Poppins-Regular", 10, label_area)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 10)
        total_label_h = len(label_lines) * 11
        label_y_start = y_bar + (row_h - total_label_h) / 2 + 2
        for j, line in enumerate(label_lines):
            y_line = label_y_start + (len(label_lines) - 1 - j) * 11
            pdf.drawRightString(chart_left - 10, y_line, line)
        val_text = _format_number(value)
        sw = stringWidth(val_text, "Poppins-Regular", 10)
        inside_space = max(0.0, w - cap_r - 8)
        pdf.setFont("Poppins-Regular", 10)
        if sw <= inside_space and w > 0:
            pdf.setFillColor(WHITE if BAR2 != WHITE else TEXT)
            pdf.drawRightString(chart_left + w - cap_r - 6, y_bar + row_h / 2.0 - 4, val_text)
        else:
            pdf.setFillColor(TEXT)
            x_out = min(chart_right - 4 - sw, chart_left + w + 6)
            pdf.drawString(x_out, y_bar + row_h / 2.0 - 4, val_text)
    items_all = items_sorted
    pie_values = [float(it.get("total_waste", 0) or 0) for it in items_all] or [1.0]
    pie_colors = [colors.HexColor(main_material_colorPalette[i % len(main_material_colorPalette)]) for i in range(len(items_all))] or [BAR2]
    pie_size = max(60.0, min(pie_card, card_h2) * 0.6)
    pie_x = x_right + (pie_card - pie_size) / 2.0
    pie_y = card_y2 + (card_h2 - pie_size) - 36
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(pie_x - 24, title_y, "Materials Proportion")
    _simple_pie_chart(pdf, pie_x, pie_y - 12, pie_size, pie_values, pie_colors, gap_width=1, gap_color=colors.white)
    top5 = items_top[:5]
    row_h = 14
    start_y = (pie_y - 12) - 22
    left_x = x_right + 12
    right_x = x_right + pie_card - 12
    box_size = 8
    pdf.setFont("Poppins-Regular", 10)
    for i, it in enumerate(top5):
        y = start_y - i * (row_h + 6)
        c = colors.HexColor(main_material_colorPalette[i % len(main_material_colorPalette)])
        pdf.setFillColor(c)
        pdf.roundRect(left_x, y - box_size + 7, box_size, box_size, 2, stroke=0, fill=1)
        name = str(it.get("main_material_name", ""))
        pdf.setFillColor(TEXT)
        max_name_w = (right_x - left_x) - box_size - 54
        label = name
        while stringWidth(label, "Poppins-Regular", 10) > max_name_w and len(label) > 1:
            label = label[:-2] + "…"
        pdf.drawString(left_x + box_size + 6, y, label)
        perc = it.get("proportion_percent")
        if perc is None:
            total_w = float((data.get("main_materials_data", {}) or {}).get("total_waste", 0) or 0) or sum(pie_values) or 1.0
            perc = (float(it.get("total_waste", 0) or 0) / total_w) * 100.0
        perc_text = f"{float(perc):.2f}%"
        pw = stringWidth(perc_text, "Poppins-Regular", 10)
        pdf.drawString(right_x - pw, y, perc_text)
    _footer(pdf, page_width_points)

def draw_main_materials_table(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    mats_per_page = 10
    total_mats = len(data["main_materials_data"]["porportions"])
    # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
    content_top = page_height_points - (1.96 * inch) - 24
    header_y = content_top - 24
    header_text_y = content_top - 15
    for page_idx in range(0, total_mats, mats_per_page):
        pdf.showPage()
        _header(pdf, page_width_points, page_height_points, data)
        _sub_header(pdf, page_width_points, page_height_points, data, "Main Materials")
        pdf.setFillColor(colors.HexColor("#f1f5f9"))
        draw_table(pdf, padding, header_y, page_width_points - 2 * padding, 24, 8, "Header")
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        pdf.drawString(padding + 16, header_text_y, "Main Material")
        pdf.drawString(padding + 3.2 * inch, header_text_y, "Total Waste (kg)")
        pdf.drawString(padding + 5.8 * inch, header_text_y, "Percentage (%)")
        pdf.drawString(padding + 8.5 * inch, header_text_y, "GHG Reduction (kgCO2e)")
        page_mats = data["main_materials_data"]["porportions"][page_idx:page_idx + mats_per_page]
        for idx, mat in enumerate(page_mats):
            y_base = header_y - 32 - (idx * 32)
            table_type = "Footer" if idx == len(page_mats) - 1 else "Body"
            pdf.setFillColor(WHITE)
            draw_table(pdf, padding, y_base, page_width_points - 2 * padding, 32, 8, table_type)
            pdf.setFillColor(TEXT)
            pdf.setFont("Poppins-Regular", 8)
            y_text = y_base + 12
            pdf.drawString(padding + 16, y_text, mat["main_material_name"])
            pdf.drawString(padding + 3.2 * inch, y_text, _format_number(mat["total_waste"]))
            pdf.drawString(padding + 5.8 * inch, y_text, f"{mat['proportion_percent']:.2f}%")
            pdf.drawString(padding + 8.5 * inch, y_text, _format_number(mat["ghg_reduction"]))
        _footer(pdf, page_width_points)

def draw_sub_materials(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    pdf.showPage()
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Sub Materials")
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
    pdf.setFont("Poppins-Regular", 10)
    max_label_area = bar_card * 0.45
    min_label_area = 60
    longest_word_w = max((stringWidth(w, "Poppins-Regular", 10) for it in items_top for w in str(it.get("material_name", "")).split()), default=40)
    label_area = max(min_label_area, longest_word_w + 6)
    label_area = min(label_area, max_label_area)
    chart_left = x_left + pad + label_area + 8
    chart_right = x_left + bar_card - pad
    chart_bottom = card_y2 + 28
    chart_top = card_y2 + card_h2 - 40
    chart_w = max(1.0, chart_right - chart_left)
    chart_h = max(1.0, chart_top - chart_bottom)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(x_left + pad, title_y, "Top Materials by Quantity")
    max_val = max([1.0] + [float(it.get("total_waste", 0) or 0) for it in items_top])
    mag = 1.0
    while mag * 10 <= max_val:
        mag *= 10.0
    for mul in (1.0, 2.0, 2.5, 5.0, 10.0):
        top_val = mul * mag
        if top_val >= max_val:
            break
    ticks = [0.0, top_val / 2.0, top_val]
    pdf.setStrokeColor(STROKE)
    pdf.setLineWidth(0.5)
    for tv in ticks:
        x = chart_left + (tv / top_val) * chart_w
        pdf.line(x, chart_bottom, x, chart_top)
        lbl = _format_number(round(tv))
        lw = stringWidth(lbl, "Poppins-Regular", 9)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 9)
        pdf.drawCentredString(x, chart_bottom - 12, lbl)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 10)
    pdf.drawRightString(chart_right + 12, chart_bottom - 26, "Kg.")
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
        bar_color = colors.HexColor(sub_material_colorPalette[i % len(sub_material_colorPalette)])
        _draw_right_round_rect(chart_left, y_bar, w, row_h, cap_r, bar_color)
        name = str(it.get("material_name", ""))
        label_lines = wrap_label(name, "Poppins-Regular", 10, label_area)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 10)
        total_label_h = len(label_lines) * 11
        label_y_start = y_bar + (row_h - total_label_h) / 2 + 2
        for j, line in enumerate(label_lines):
            y_line = label_y_start + (len(label_lines) - 1 - j) * 11
            pdf.drawRightString(chart_left - 10, y_line, line)
        val_text = _format_number(value)
        sw = stringWidth(val_text, "Poppins-Regular", 10)
        inside_space = max(0.0, w - cap_r - 8)
        pdf.setFont("Poppins-Regular", 10)
        if sw <= inside_space and w > 0:
            pdf.setFillColor(WHITE if BAR2 != WHITE else TEXT)
            pdf.drawRightString(chart_left + w - cap_r - 6, y_bar + row_h / 2.0 - 4, val_text)
        else:
            pdf.setFillColor(TEXT)
            x_out = min(chart_right - 4 - sw, chart_left + w + 6)
            pdf.drawString(x_out, y_bar + row_h / 2.0 - 4, val_text)
    items_all = items_sorted
    pie_values = [float(it.get("total_waste", 0) or 0) for it in items_all] or [1.0]
    pie_colors = [colors.HexColor(sub_material_colorPalette[i % len(sub_material_colorPalette)]) for i in range(len(items_all))] or [BAR2]
    pie_size = max(60.0, min(pie_card, card_h2) * 0.6)
    pie_x = x_right + (pie_card - pie_size) / 2.0
    pie_y = card_y2 + (card_h2 - pie_size) - 36
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(pie_x - 24, title_y, "Materials Proportion")
    _simple_pie_chart(pdf, pie_x, pie_y - 12, pie_size, pie_values, pie_colors, gap_width=1, gap_color=colors.white)
    top5 = items_top[:5]
    row_h = 14
    start_y = (pie_y - 12) - 22
    left_x = x_right + 12
    right_x = x_right + pie_card - 12
    box_size = 8
    pdf.setFont("Poppins-Regular", 10)
    for i, it in enumerate(top5):
        y = start_y - i * (row_h + 6)
        c = colors.HexColor(sub_material_colorPalette[i % len(sub_material_colorPalette)])
        pdf.setFillColor(c)
        pdf.roundRect(left_x, y - box_size + 7, box_size, box_size, 2, stroke=0, fill=1)
        name = str(it.get("material_name", ""))
        pdf.setFillColor(TEXT)
        max_name_w = (right_x - left_x) - box_size - 54
        label = name
        while stringWidth(label, "Poppins-Regular", 10) > max_name_w and len(label) > 1:
            label = label[:-2] + "…"
        pdf.drawString(left_x + box_size + 6, y, label)
        perc = it.get("proportion_percent")
        if perc is None:
            total_w = float((data.get("sub_materials_data", {}) or {}).get("total_waste", 0) or 0) or sum(pie_values) or 1.0
            perc = (float(it.get("total_waste", 0) or 0) / total_w) * 100.0
        perc_text = f"{float(perc):.2f}%"
        pw = stringWidth(perc_text, "Poppins-Regular", 10)
        pdf.drawString(right_x - pw, y, perc_text)
    _footer(pdf, page_width_points)

def draw_sub_materials_table(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    padding = 0.78 * inch
    rows_per_page = 10
    # Sub header ends at page_height_points - (1.96 * inch), content starts 24 points below
    content_top = page_height_points - (1.96 * inch) - 24
    header_y = content_top - 24
    header_text_y = content_top - 15
    grouped = (data.get("sub_materials_data", {}) or {}).get("porportions_grouped", {}) or {}
    flat_rows = []
    for group_name, items in grouped.items():
        flat_rows.append(("group", group_name))
        for item in items or []:
            flat_rows.append(("item", item))
    total_rows = len(flat_rows)
    start_idx = 0
    while start_idx < total_rows:
        # Determine how many rows can fit on this page
        # Check if we need to skip a group header that can't fit with at least one member
        page_rows = []
        current_idx = start_idx
        min_y = 1.5 * inch  # Minimum y position for content
        
        while current_idx < total_rows and len(page_rows) < rows_per_page:
            row_type, payload = flat_rows[current_idx]
            
            # If this is a group header, check if at least one member can fit after it
            if row_type == "group":
                # Check if there's at least one item after this group header
                if current_idx + 1 < total_rows and flat_rows[current_idx + 1][0] == "item":
                    # Check if we have room for both the group header and at least one item
                    rows_needed = 2  # group header + at least 1 item
                    if len(page_rows) + rows_needed <= rows_per_page:
                        page_rows.append((row_type, payload))
                        current_idx += 1
                    else:
                        # Not enough room, break to start new page
                        break
                else:
                    # No items after this group, skip it (orphaned group header)
                    current_idx += 1
                    continue
            else:
                # Regular item, add it
                page_rows.append((row_type, payload))
                current_idx += 1
        
        # If no rows were added, skip to next item to avoid infinite loop
        if not page_rows:
            start_idx += 1
            continue
        
        pdf.showPage()
        _header(pdf, page_width_points, page_height_points, data)
        _sub_header(pdf, page_width_points, page_height_points, data, "Sub Materials")
        pdf.setFillColor(colors.HexColor("#f1f5f9"))
        draw_table(pdf, padding, header_y, page_width_points - 2 * padding, 24, 8, "Header")
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        pdf.drawString(padding + 16, header_text_y, "Sub Material")
        pdf.drawString(padding + 3.2 * inch, header_text_y, "Total Waste (kg)")
        pdf.drawString(padding + 5.8 * inch, header_text_y, "Percentage (%)")
        pdf.drawString(padding + 8.5 * inch, header_text_y, "GHG Reduction (kgCO2e)")
        for idx, (row_type, payload) in enumerate(page_rows):
            y_base = header_y - 32 - (idx * 32)
            table_type = "Footer" if idx == len(page_rows) - 1 else "Body"
            if row_type == "group":
                pdf.setFillColor(colors.HexColor("#f1f5f9"))
                draw_table(pdf, padding, y_base, page_width_points - 2 * padding, 32, 8, table_type)
                pdf.setFillColor(TEXT)
                pdf.setFont("Poppins-Medium", 9)
                pdf.drawString(padding + 16, y_base + 12, str(payload))
            else:
                mat = payload
                pdf.setFillColor(WHITE)
                draw_table(pdf, padding, y_base, page_width_points - 2 * padding, 32, 8, table_type)
                pdf.setFillColor(TEXT)
                pdf.setFont("Poppins-Regular", 8)
                y_text = y_base + 12
                pdf.drawString(padding + 16, y_text, str(mat.get("material_name", "")))
                pdf.drawString(padding + 3.2 * inch, y_text, _format_number(mat.get("total_waste", 0)))
                pdf.drawString(padding + 5.8 * inch, y_text, f"{float(mat.get('proportion_percent', 0) or 0):.2f}%")
                pdf.drawString(padding + 8.5 * inch, y_text, _format_number(mat.get("ghg_reduction", 0)))
        _footer(pdf, page_width_points)
        # Update start_idx to continue from where we left off
        start_idx = current_idx

def draw_waste_diversion(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    pdf.showPage()
    padding = 0.78 * inch
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Waste Diversion")
    
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
        pdf.setFont("Poppins-Medium", 14)
        error_y = card_y + card_h / 2.0
        pdf.drawCentredString(card_x + card_w / 2.0, error_y, error_msg)
        _footer(pdf, page_width_points)
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
    _stat_chip(pdf, x0, chip_y, chip_w, chip_h, "Total Origins", total_origin)
    _stat_chip(pdf, x0 + (chip_w + chip_gap), chip_y, chip_w, chip_h, "Complete Transfers", f"{float(complete_transfer or 0):.0f}%")
    _stat_chip(pdf, x0 + 2 * (chip_w + chip_gap), chip_y, chip_w, chip_h, "Processing Transfers", f"{float(processing_transfer or 0):.0f}%")
    _stat_chip(pdf, x0 + 3 * (chip_w + chip_gap), chip_y, chip_w, chip_h, "Completed Rate", f"{float(completed_rate or 0):.0f}%")
    sankey_raw = (data.get("diversion_data", {}) or {}).get("sankey_data", [])
    chart_y_top = chip_y - 30
    chart_height = chart_y_top - (1.5 * inch)
    if sankey_raw and len(sankey_raw) > 1:
        print("SANKEY GOT USED")
        chart_y_top = chip_y - 30
        chart_height = chart_y_top - (1.5 * inch)
        _draw_sankey_diagram(
            pdf,
            x=margin,
            y_top=chart_y_top,
            width=usable_w,
            height=chart_height,
            data_rows=sankey_raw
        )
    else:
        print("SANKEY DID NOT GOT USED")
        # Draw a friendly placeholder when there are no flows (only header present)
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 11)
        msg = "No diversion flows available for the selected period."
        tw = stringWidth(msg, "Poppins-Regular", 11)
        center_x = margin + (usable_w - tw) / 2.0
        center_y = (chart_y_top + (1.5 * inch)) / 2.0
        pdf.drawString(center_x, center_y, msg)
    _footer(pdf, page_width_points)

def _draw_sankey_diagram(pdf, x, y_top, width, height, data_rows):
    rows = data_rows[1:] if data_rows[0][0] == "From" else data_rows
    sources = {}
    targets = {}
    flows = []
    for s, t, w in rows:
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
    pdf.setFont("Helvetica-Bold", 8)
    text_color = colors.Color(0.4, 0.4, 0.4)
    source_colors = [colors.Color(0.4, 0.6, 0.9), colors.Color(0.4, 0.8, 0.5), colors.lightgrey]
    for i, name in enumerate(source_names):
        data = source_coords[name]
        bar_y = data['y'] - data['h']
        col = source_colors[i % len(source_colors)]
        pdf.setFillColor(col)
        pdf.setStrokeColor(col)
        pdf.rect(x, bar_y, bar_width, data['h'], fill=1, stroke=0)
        pdf.setFillColor(text_color)
        pdf.drawString(x + bar_width + 8, bar_y + data['h']/2 - 3, name)
    pdf.setFont("Helvetica-Bold", 9)
    target_bar_color = colors.Color(0.3, 0.6, 0.9)
    for name in target_names:
        data = target_coords[name]
        bar_y = data['y'] - data['h']
        pdf.setFillColor(target_bar_color)
        pdf.setStrokeColor(target_bar_color)
        pdf.rect(x + width - bar_width, bar_y, bar_width, data['h'], fill=1, stroke=0)
        pdf.setFillColor(text_color)
        text_w = pdf.stringWidth(name, "Helvetica-Bold", 9)
        pdf.drawString(x + width - bar_width - 8 - text_w, bar_y + data['h']/2 - 3, name)
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
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    materials_w = content_w * 0.22
    month_w = content_w * 0.045
    status_w = content_w * 0.10
    destination_w = max(1.0, content_w - (materials_w + month_w * 12 + status_w))
    def col_x_for_month(i: int) -> float:
        return content_x + materials_w + (i * month_w)
    def fit_text(text: str, max_w: float) -> str:
        t = str(text or "")
        if stringWidth(t, "Poppins-Regular", 8) <= max_w:
            return t
        ell = "…"
        while t and stringWidth(t + ell, "Poppins-Regular", 8) > max_w:
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
        pdf.setFont("Poppins-Regular", 8)
        for part in (parts or ["-"]):
            wrapped = _wrap_text_lines(pdf, str(part), destination_w - 12, "Poppins-Regular", 8)
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
        _sub_header(pdf, page_width_points, page_height_points, data, "Waste Diversion")
        if debug:
            try:
                print(f"[waste_diversion_table] --- page {page_num} ---")
                if total_rows == 0:
                    print("[waste_diversion_table] no rows to render (header-only page)")
            except Exception:
                pass
        pdf.setFillColor(colors.HexColor("#f1f5f9"))
        draw_table(pdf, content_x, header_y, content_w, header_h, 8, "Header")
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        header_text_y = content_top - 15
        pdf.drawString(content_x + 16, header_text_y, "Materials")
        for i, m in enumerate(months):
            mx = col_x_for_month(i)
            pdf.drawString(mx + 4, header_text_y, m)
        status_x = content_x + materials_w + (len(months) * month_w)
        dest_x = status_x + status_w
        pdf.drawString(status_x + 4, header_text_y, "Status")
        pdf.drawString(dest_x + 4, header_text_y, "Destination")
        current_y = header_y
        drew_any = False
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
            pdf.setFillColor(WHITE)
            draw_table(pdf, content_x, y_base, content_w, this_h, 8, table_type)
            pdf.setFillColor(TEXT)
            pdf.setFont("Poppins-Regular", 8)
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
                    months_line = ", ".join(f"{m}={month_values.get(m, 0)}" for m in months)
                    print(f"[waste_diversion_table]   months: {months_line}")
                except Exception:
                    pass
            for i, m in enumerate(months):
                mx = col_x_for_month(i)
                val = month_values.get(m, 0)
                txt = _format_number(val)
                pdf.drawString(mx + 4, y_text, txt)
            status_val = str(this_row.get("status", ""))
            if status_val.lower() == "processing":
                badge_bg = colors.HexColor("#FFF4E5")
                badge_text = colors.HexColor("#F59E0B")
                pdf.setFont("Poppins-Medium", 8)
                disp = fit_text(status_val, status_w - 16)
                tw = stringWidth(disp, "Poppins-Medium", 8)
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
                pdf.setFont("Poppins-Regular", 8)
            elif status_val.lower().startswith("complete"):
                badge_bg = colors.HexColor("#EAF7F0")
                badge_text = colors.HexColor("#16A34A")
                pdf.setFont("Poppins-Medium", 8)
                disp = fit_text(status_val, status_w - 16)
                tw = stringWidth(disp, "Poppins-Medium", 8)
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
                pdf.setFont("Poppins-Regular", 8)
            else:
                pdf.drawString(status_x + 4, y_text, fit_text(status_val, status_w - 8))
            pdf.setFont("Poppins-Regular", 8)
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
                pdf.setFont("Poppins-Regular", 8)
                tw_dash = stringWidth(dash, "Poppins-Regular", 8)
                tx = dest_x + (destination_w - tw_dash) / 2
                pdf.drawString(tx, y_text, dash)
            else:
                for gi, group in enumerate(groups):
                    if group:
                        pdf.setFillColor(TEXT)
                        pdf.circle(bullet_x, dy - 3, 2, stroke=0, fill=1)
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
        _footer(pdf, page_width_points)
        if total_rows == 0:
            # Avoid infinite loop when no rows are present
            break


def _register_fonts() -> None:
    """
    Try to register Poppins fonts from common locations (repo scripts/, lambda layer /opt/fonts, cwd).
    If not found, silently continue (ReportLab will use default fonts).
    """
    candidates = [
        ("Poppins-Bold",   ["scripts/Poppins-Bold.ttf",   "/opt/fonts/Poppins-Bold.ttf",   "Poppins-Bold.ttf"]),
        ("Poppins-Regular",["scripts/Poppins-Regular.ttf","/opt/fonts/Poppins-Regular.ttf","Poppins-Regular.ttf"]),
        ("Poppins-Medium", ["scripts/Poppins-Medium.ttf", "/opt/fonts/Poppins-Medium.ttf", "Poppins-Medium.ttf"]),
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

    pdf = canvas.Canvas(buffer, pagesize=(width_points, height_points))

    # Draw pages (mirrors main() in scripts/generate_pdf_report.py)
    draw_cover(pdf, width_points, height_points, data)
    draw_overview(pdf, width_points, height_points, data)
    for performance_data in data.get("performance_data", []) or []:
        draw_performance(pdf, width_points, height_points, data, performance_data)
    draw_performance_table(pdf, width_points, height_points, data)
    draw_comparison_advice(pdf, width_points, height_points, data)
    draw_comparison(pdf, width_points, height_points, data)
    draw_main_materials(pdf, width_points, height_points, data)
    draw_main_materials_table(pdf, width_points, height_points, data)
    draw_sub_materials(pdf, width_points, height_points, data)
    draw_sub_materials_table(pdf, width_points, height_points, data)
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


