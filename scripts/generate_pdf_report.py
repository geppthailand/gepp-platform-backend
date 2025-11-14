from datetime import datetime
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth


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

def _header(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    text = data["users"]
    font_name = "Poppins-Regular"
    font_size = 12
    padding = 0.78 * inch  # whatever padding you want from right edge

    # 🧮 measure how wide the text is
    text_width = stringWidth(text, font_name, font_size)

    # 💡 calculate x-position = total width - text width - padding
    x = page_width_points - text_width - padding
    y = page_height_points - (0.7 * inch)  # your vertical position

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

    # background
    pdf.setFillColor(back_color)
    pdf.roundRect(x, y, w, h, radius, stroke=0, fill=1)

    # foreground
    pdf.setFillColor(bar_color)
    bar_width = max(h, w * ratio)  # prevent ugly cut for small ratio
    pdf.roundRect(x, y, bar_width, h, radius, stroke=0, fill=1)


def _label_progress(pdf, x, y, w, label, value_text, ratio, bar_color, back_color):
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 10)
    pdf.drawString(x, y + 16, label)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 10)
    txt_w = stringWidth(value_text, "Poppins-Regular", 10)
    pdf.drawString(x + w - txt_w, y + 16, value_text)
    _progress_bar(pdf, x, y, w, 8, ratio, bar_color, back_color)

def _simple_bar_chart(pdf, x, y, w, h, chart_series):
    left_pad, bottom_pad, right_pad, top_pad = 32, 36, 24, 20
    gx = x + left_pad
    gy = y + bottom_pad
    gw = w - left_pad - right_pad
    gh = h - bottom_pad - top_pad

    # axes
    pdf.setStrokeColor(STROKE)
    pdf.line(gx, gy, gx, gy + gh)
    pdf.line(gx, gy, gx + gw, gy)

    # bars (grouped by month across all series)
    if not chart_series:
        return
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    # Determine up to 3 series (prefer most recent numeric years if possible)
    try:
        sorted_years = sorted([int(k) for k in chart_series.keys()])
        series_keys = [str(y) for y in sorted_years[-3:]]
    except Exception:
        # Fallback: preserve insertion order, take last 3
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

    n_months = 12
    gap = 10
    slot_w = (gw - (n_months + 1) * gap) / max(1, n_months)
    group_scale = 0.86
    group_w = slot_w * group_scale
    s_count = max(1, len(series_keys))
    inner_gap_ratio = 0.06
    total_inner_gap = (s_count - 1) * group_w * inner_gap_ratio
    bar_w = (group_w - total_inner_gap) / s_count

    for mi in range(n_months):
        slot_x = gx + gap + mi * (slot_w + gap)
        group_x = slot_x + (slot_w - group_w) / 2
        for si, key in enumerate(series_keys):
            color = SERIES_COLORS[si % len(SERIES_COLORS)]
            pdf.setFillColor(color)
            v = values_by_series[key][mi]
            bh = (v / vmax) * (gh - 10)
            bx = group_x + si * (bar_w + group_w * inner_gap_ratio)
            pdf.rect(bx, gy, bar_w, bh, stroke=0, fill=1)
        # month label centered in slot
        lbl = months[mi]
        pdf.setFillColor(TEXT)
        pdf.setFont("Poppins-Regular", 8)
        lw = stringWidth(lbl, "Poppins-Regular", 8)
        pdf.drawString(slot_x + (slot_w - lw) / 2, gy - 14, lbl)

    # y-axis unit
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 9)
    pdf.drawString(gx - 18, gy + gh + 6, "kg")

    # legend for each series (years), right-aligned
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
    pdf.drawString((page_width_points - tw) / 2, 0.5 * inch, text)

def draw_cover(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    _header(pdf, page_width_points, page_height_points, data)
    middle = page_height_points / 2
    pdf.setFillColor(PRIMARY)  # set text color
    pdf.setFont("Poppins-Bold", 100) # set font and size
    pdf.drawString(0.63 * inch, middle + 20, "2025") 
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Regular", 38.5)
    pdf.drawString(0.63 * inch, middle - 20, "GEPP REPORT")
    pdf.setFont("Poppins-Regular", 16.5)
    pdf.drawString(0.63 * inch, middle - 40, "Data-Driven Transaformation")

    # 💡 Accent rectangle at the bottom
    pdf.setFillColor(PRIMARY)
    pdf.rect(4.54 * inch, middle - 45, page_width_points - (4.54 * inch), 2.07 * inch, fill=1, stroke=0)

def draw_overview(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    pdf.showPage() # New page
    _header(pdf, page_width_points, page_height_points, data)
    _sub_header(pdf, page_width_points, page_height_points, data, "Overview")
    # layout measurements
    margin = 0.78 * inch
    content_top = page_height_points - (2.2 * inch)
    col_gap = 0.3 * inch
    left_col_w = 3.7 * inch
    right_col_w = page_width_points - margin - margin - left_col_w - col_gap

    # small stat chips (top-left row)
    chip_w = 1.78 * inch
    chip_h = 0.60 * inch
    chip_y = content_top - chip_h
    _stat_chip(pdf, margin, chip_y, chip_w, chip_h, "Total Transactions", data["data"]["transactions_total"])
    _stat_chip(pdf, margin + chip_w + 12, chip_y, chip_w, chip_h, "Total Approved", data["data"]["transactions_approved"])

    # left column cards
    # Key Indicators
    ki_h = 2.2 * inch
    ki_y = chip_y - 16 - ki_h
    _rounded_card(pdf, margin, ki_y, left_col_w, ki_h, radius=8)
    pad = 20
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(margin + pad, page_height_points - (3.42 * inch), "Key Indicators")

    ki = data["data"]["key_indicators"]
    tw = float(ki.get("total_waste", 0) or 0)
    rr = float(ki.get("recycle_rate", 0) or 0)
    ghg = float(ki.get("ghg_reduction", 0) or 0)
    # normalize non-percentage bars against max of tw & ghg
    norm_base = max(tw, ghg, 1.0)
    row_w = left_col_w - 2 * pad
    row_x = margin + pad
    row_y = ki_y + ki_h - 50
    _label_progress(pdf, row_x, row_y - 24, row_w, "Total Waste (kg)", _format_number(tw), tw / norm_base, colors.HexColor("#b7c6cc"), colors.HexColor("#e1e7ef"))
    _label_progress(pdf, row_x, row_y - 58, row_w, "Recycle rate (%)", f"{rr:,.2f}", rr / 100.0, colors.HexColor("#8fcfc6"), colors.HexColor("#e1e7ef"))
    _label_progress(pdf, row_x, row_y - 92, row_w, "GHG Reduction (kgCO2e)", _format_number(ghg), ghg / norm_base, colors.HexColor("#77b9d8"), colors.HexColor("#e1e7ef"))

    # Top Recyclables
    tr_h = 2.15 * inch
    tr_y = ki_y - 18 - tr_h
    _rounded_card(pdf, margin, tr_y, left_col_w, tr_h, radius=8)

    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(margin + pad, tr_y + tr_h - 30, "Top Recyclables")
    items = data["data"].get("top_recyclables", [])[:3]
    if items:
        max_val = max(float(it.get("total_waste", 0) or 0) for it in items) or 1.0
        y_ptr = tr_y + tr_h - 72
        for it in items:
            name = str(it.get("origin_name", ""))
            val = float(it.get("total_waste", 0) or 0)
            ratio = val / max_val
            _label_progress(pdf, margin + pad, y_ptr, left_col_w - 2 * pad, name, _format_number(val), ratio, colors.HexColor("#c8ced4"), colors.HexColor("#e1e7ef"))
            y_ptr -= 32

    # Right column: Overall card with small stats and chart
    overall_x = margin + left_col_w + col_gap
    overall_y = tr_y
    overall_h = (chip_y - overall_y) + chip_h  # span to top row baseline
    _rounded_card(pdf, overall_x, overall_y, right_col_w, overall_h, radius=8, fill=WHITE)
    pdf.setFillColor(TEXT)
    pdf.setFont("Poppins-Medium", 12)
    pdf.drawString(overall_x + 16, overall_y + overall_h - 30, "Overall")

    # top stat chips in overall card
    stats = data["data"]["overall_charts"]["chart_stat_data"]
    sw = 1.78 * inch
    sh = 0.60 * inch
    sy = overall_y + overall_h - 26 - 16 - sh
    for i, st in enumerate(stats[:3]):
        sx = overall_x + 16 + i * (sw + 8)
        _stat_chip(pdf, sx, sy, sw, sh, st["title"], st["value"], "white")

    # bar chart (supports multiple years)
    chart_data = data["data"]["overall_charts"]["chart_data"]
    cy = overall_y + 16
    ch = sy - cy - 16
    _simple_bar_chart(pdf, overall_x + 12, cy, right_col_w - 24, ch, chart_data)

    _footer(pdf, page_width_points)

def main() -> None:
    width_points = PAGE_WIDTH_IN * inch
    height_points = PAGE_HEIGHT_IN * inch
    pdfmetrics.registerFont(TTFont('Poppins-Bold', 'scripts/Poppins-Bold.ttf'))
    pdfmetrics.registerFont(TTFont('Poppins-Regular', 'scripts/Poppins-Regular.ttf'))
    pdfmetrics.registerFont(TTFont('Poppins-Medium', 'scripts/Poppins-Medium.ttf'))

    data = {
        "users" : "John Doe",
        "profile_img" : "https://placehold.co/600x400",
        "location" : ["Bangkok", "Nonthaburi"],
        "date_from" : "01 Jan 2025",
        "date_to" : "31 Dec 2025",
        "data" : {
    "transactions_total": 88,
    "transactions_approved": 35,
    "key_indicators": {
        "total_waste": 11121.053899999999,
        "recycle_rate": 51.03881296717751,
        "ghg_reduction": 7720.828229899999
    },
    "top_recyclables": [
        {
            "origin_id": 2444,
            "origin_name": "Floor 1",
            "total_waste": 2473
        },
        {
            "origin_id": 2462,
            "origin_name": "Building 2",
            "total_waste": 922
        },
        {
            "origin_id": 2499,
            "origin_name": "Room 5",
            "total_waste": 668.536
        },
        {
            "origin_id": 2481,
            "origin_name": "Building 3",
            "total_waste": 650
        },
        {
            "origin_id": 2469,
            "origin_name": "Floor 2",
            "total_waste": 500
        }
    ],
    "overall_charts": {
        "chart_stat_data": [
            {
                "title": "Total Recyclables",
                "value": 5676.0539
            },
            {
                "title": "Number of Trees",
                "value": 81271.87610421052
            },
            {
                "title": "Plastic Saved",
                "value": 1917.0357
            }
        ],
        "chart_data": {
            "2024": [
                {
                    "month": "Jan",
                    "value": 1206
                },
                {
                    "month": "Feb",
                    "value": 728
                },
                {
                    "month": "Mar",
                    "value": 229
                },
                {
                    "month": "Apr",
                    "value": 29
                },
                {
                    "month": "May",
                    "value": 362
                },
                {
                    "month": "Jun",
                    "value": 430
                },
                {
                    "month": "Jul",
                    "value": 201
                },
                {
                    "month": "Aug",
                    "value": 167
                },
                {
                    "month": "Sep",
                    "value": 828
                },
                {
                    "month": "Oct",
                    "value": 13
                },
                {
                    "month": "Nov",
                    "value": 126
                },
                {
                    "month": "Dec",
                    "value": 231
                }
            ],
            "2025": [
                {
                    "month": "Jan",
                    "value": 68
                },
                {
                    "month": "Feb",
                    "value": 464
                },
                {
                    "month": "Mar",
                    "value": 433
                },
                {
                    "month": "Apr",
                    "value": 500
                },
                {
                    "month": "May",
                    "value": 846
                },
                {
                    "month": "Jun",
                    "value": 1003
                },
                {
                    "month": "Jul",
                    "value": 379
                },
                {
                    "month": "Aug",
                    "value": 53
                },
                {
                    "month": "Sep",
                    "value": 724
                },
                {
                    "month": "Oct",
                    "value": 455
                },
                {
                    "month": "Nov",
                    "value": 1646.05
                }
            ],
            "2026": [
                {
                    "month": "Jan",
                    "value": 68
                },
                {
                    "month": "Feb",
                    "value": 464
                },
                {
                    "month": "Mar",
                    "value": 433
                },
                {
                    "month": "Apr",
                    "value": 500
                },
                {
                    "month": "May",
                    "value": 846
                },
                {
                    "month": "Jun",
                    "value": 1003
                },
                {
                    "month": "Jul",
                    "value": 379
                },
                {
                    "month": "Aug",
                    "value": 53
                },
                {
                    "month": "Sep",
                    "value": 724
                },
                {
                    "month": "Oct",
                    "value": 455
                },
                {
                    "month": "Nov",
                    "value": 1646.05
                }
            ]
        }
    },
    "waste_type_proportions": [
        {
            "category_id": 3,
            "category_name": "Organic Waste",
            "total_waste": 2939,
            "proportion_percent": 26.427351458120352
        },
        {
            "category_id": 1,
            "category_name": "Recyclable Waste",
            "total_waste": 2737.0539,
            "proportion_percent": 24.611461509057158
        },
        {
            "category_id": 7,
            "category_name": "Construction Waste",
            "total_waste": 2580,
            "proportion_percent": 23.19924013676438
        },
        {
            "category_id": 4,
            "category_name": "General Waste",
            "total_waste": 1720,
            "proportion_percent": 15.466160091176251
        },
        {
            "category_id": 2,
            "category_name": "Electronic Waste",
            "total_waste": 578,
            "proportion_percent": 5.197349146918532
        },
        {
            "category_id": 5,
            "category_name": "Hazardous Waste",
            "total_waste": 287,
            "proportion_percent": 2.5806906663765026
        },
        {
            "category_id": 9,
            "category_name": "Waste To Energy",
            "total_waste": 275,
            "proportion_percent": 2.4727872238799242
        },
        {
            "category_id": 6,
            "category_name": "Bio-Hazardous Waste",
            "total_waste": 5,
            "proportion_percent": 0.04495976770690771
        }
    ],
    "material_summary": []
}
    }
    output_dir = Path("notebooks") / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    pdf = canvas.Canvas(str(output_path), pagesize=(width_points, height_points))
    # Draw cover content
    draw_cover(pdf, width_points, height_points, data)
    draw_overview(pdf, width_points, height_points, data)
    pdf.save()

    print(f"Saved: {output_path} ({PAGE_WIDTH_IN}in x {PAGE_HEIGHT_IN}in)")


if __name__ == "__main__":
    main()


