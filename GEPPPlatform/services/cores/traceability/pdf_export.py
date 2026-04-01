"""
Traceability PDF export. Generates a PDF report from hierarchy data (origin -> group -> transport tree).
Used by pdf_export_hub with export_type="traceability". No DB or service imports.
"""
import os
from io import BytesIO
from datetime import datetime

from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

PAGE_WIDTH_IN = 11.69
PAGE_HEIGHT_IN = 8.27

_THAI_MONTHS = [
    "", "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]


_EN_MONTHS = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

def _format_en_date(date_str: str) -> str:
    """Convert date string (YYYY-MM-DD or YYYY-MM) to English month+year format."""
    if not date_str:
        return ""
    try:
        parts = date_str.strip().split("-")
        y = int(parts[0])
        m = int(parts[1]) if len(parts) >= 2 else 0
        if 1 <= m <= 12:
            return f"{_EN_MONTHS[m]} {y}"
        return str(y)
    except (ValueError, IndexError):
        return date_str

def _format_thai_date(date_str: str) -> str:
    """Convert date string (YYYY-MM-DD or YYYY-MM) to Thai month+year format."""
    if not date_str:
        return ""
    try:
        parts = date_str.strip().split("-")
        y = int(parts[0])
        m = int(parts[1]) if len(parts) >= 2 else 0
        thai_year = y + 543
        if 1 <= m <= 12:
            return f"{_THAI_MONTHS[m]} {thai_year}"
        return str(thai_year)
    except (ValueError, IndexError):
        return date_str
PRIMARY = colors.HexColor("#54937a")
padding = 0.50 * inch

# --- i18n ---
_TR = {
    'en': {
        'header_title': 'Waste Traceability',
        'location_label': 'Location',
        'date_label': 'Date',
        'all': 'All',
        'kg': 'kg.',
        'card_total_waste': 'Total Waste',
        'card_managed': 'Managed Waste',
        'card_treatment': 'Treatment',
        'card_disposal': 'Disposal',
        'no_data': 'No data',
        'total_weight': 'Total Weight',
        'deliverer': 'Deliverer',
        'pending': 'Pending management',
        'more': 'more',
        'destination_label': 'Destination',
        'method_label': 'Method',
        'item_details': 'Item Details',
        'table_headers': ['Material Type', 'Weight (kg.)', 'Origin', 'Destination', 'Delivered By', 'Disposal Method', 'Status'],
        'status_arrived': 'Arrived',
        'status_pending': 'Pending',
    },
    'th': {
        'header_title': 'เส้นทางของเสียและวัสดุรีไซเคิล',
        'location_label': 'สถานที่',
        'date_label': 'วันที่',
        'all': 'ทั้งหมด',
        'kg': 'กก.',
        'card_total_waste': 'ปริมาณทั้งหมด',
        'card_managed': 'ของเสียถูกจัดการแล้ว',
        'card_treatment': 'นำไปใช้ประโยชน์',
        'card_disposal': 'นำไปฝังกลบ/เผากำจัด',
        'no_data': 'ไม่มีข้อมูล',
        'total_weight': 'ปริมาณรวม',
        'deliverer': 'ชื่อผู้จัดส่ง',
        'pending': 'กำลังรอการจัดการ',
        'more': 'เพิ่มเติม',
        'destination_label': 'ปลายทาง',
        'method_label': 'วิธีการจัดการ',
        'item_details': 'รายละเอียดรายการ',
        'table_headers': ['ประเภทวัสดุ', 'น้ำหนัก (กก.)', 'ต้นทาง', 'ปลายทาง', 'จัดส่งโดย', 'วิธีการกำจัด', 'สถานะ'],
        'status_arrived': 'มาถึงแล้ว',
        'status_pending': 'รอดำเนินการ',
    },
}

_DISPOSAL_METHOD_TH = {
    "Recycle": "รีไซเคิล",
    "Recycling (Own)": "รีไซเคิล (ด้วยตนเอง)",
    "Preparation for reuse": "เตรียมเพื่อนำกลับมาใช้ใหม่",
    "Other recover operation": "การนำกลับคืนอื่นๆ",
    "Composted by municipality": "หมักปุ๋ยโดยเทศบาล",
    "Municipality receive": "เทศบาลรับ",
    "Incineration without energy": "เผาทำลายโดยไม่ผลิตพลังงาน",
    "Incineration with energy": "เผาทำลายโดยผลิตพลังงาน",
    "Composted": "หมักปุ๋ย",
    "Landfill": "ฝังกลบ",
}

def _translate_method(method: str, lang: str) -> str:
    if lang == 'th' and method in _DISPOSAL_METHOD_TH:
        return _DISPOSAL_METHOD_TH[method]
    return method

def _t(key: str, data: dict) -> str:
    lang = (data or {}).get('language', 'th') or 'th'
    return _TR.get(lang, _TR['th']).get(key, _TR['th'].get(key, key))

def _t_card_config(data: dict) -> list:
    return [
        (_t('card_total_waste', data), "totalWaste.png"),
        (_t('card_managed', data), "totalManaged.png"),
        (_t('card_treatment', data), "totalRecycle.png"),
        (_t('card_disposal', data), "totalLandfill.png"),
    ]

# Legacy constant (kept for backward compat, overridden by _t_card_config at runtime)
CARD_CONFIG = [
    ("ปริมาณทั้งหมด", "totalWaste.png"),
    ("ของเสียถูกจัดการแล้ว", "totalManaged.png"),
    ("นำไปใช้ประโยชน์", "totalRecycle.png"),
    ("นำไปฝังกลบ/เผากำจัด", "totalLandfill.png"),
]

def _asset_path(filename: str) -> str:
    """Resolve path to asset: same dir as this module, then assets/."""
    base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "assets", filename)


def _safe(s):
    if s is None:
        return ""
    return str(s)[:80]


def _fmt_num(value):
    """Format a number with comma as thousand separator. Non-numeric returns '-' or string."""
    if value is None:
        return "-"
    try:
        n = float(value)
        if n != n:  # NaN
            return "-"
        s = f"{n:,.2f}"
        return s.rstrip("0").rstrip(".")  # 1,234.00 -> 1,234; 1,234.50 -> 1,234.5
    except (TypeError, ValueError):
        return str(value) if value != "" else "-"

def _register_fonts() -> None:
    """
    Try to register IBMPlexSansThai fonts from common locations (repo scripts/, lambda layer /opt/fonts, cwd).
    If not found, silently continue (ReportLab will use default fonts).
    """
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

def _draw_header(pdf, page_width_points: float, page_height_points: float, data: dict) -> None:
    """Draw header at top of page: title เส้นทางของเสียและวัสดุรีไซเคิล, location, and date range."""
    header_text = _t('header_title', data)
    _all_text = _t('all', data)
    location_data = data.get("location")
    if location_data is None:
        location_text = _all_text
    elif isinstance(location_data, list):
        location_text = ", ".join(map(str, location_data)) if location_data else _all_text
    else:
        location_text = str(location_data) if location_data else _all_text
    date_from = data.get("date_from") or ""
    date_to = data.get("date_to") or ""
    lang = (data or {}).get('language', 'th') or 'th'
    if lang == 'th':
        fmt_from = _format_thai_date(date_from)
        fmt_to = _format_thai_date(date_to)
    else:
        fmt_from = _format_en_date(date_from)
        fmt_to = _format_en_date(date_to)
    if fmt_from and fmt_to:
        date_text = f"{fmt_from} - {fmt_to}" if fmt_from != fmt_to else fmt_from
    elif fmt_from:
        date_text = fmt_from
    elif fmt_to:
        date_text = fmt_to
    else:
        date_text = _all_text
    pdf.setFillColor(PRIMARY)
    pdf.setFont("IBMPlexSansThai-Bold", 42)
    pdf.drawString(padding, page_height_points - (1.08 * inch), header_text)
    pdf.setFont("IBMPlexSansThai-Regular", 12)
    pdf.setFillColor(colors.HexColor("#656565"))
    pdf.drawString(padding, page_height_points - (1.35 * inch), f"{_t('location_label', data)}: {_safe(location_text)}")
    pdf.drawString(padding, page_height_points - (1.56 * inch), f"{_t('date_label', data)}: {_safe(date_text)}")


def _draw_card_row(pdf, page_width_points: float, page_height_points: float, data: dict) -> float:
    """
    Draw a row of 4 rounded-rectangle cards. Each card: icon on the left, two rows of text on the right
    (row1 = header, row2 = value). Border #d9d9d9, fill #f6f8fb. Returns the y position below the row.
    """
    gap = 0.12 * inch
    card_height = 1.0 * inch
    radius = 0.12 * inch
    available_width = page_width_points - 2 * padding
    card_width = (available_width - 3 * gap) / 4
    row_top_y = page_height_points - (1.75 * inch) - (0.2 * inch) - card_height
    fill_color = colors.HexColor("#f6f8fb")
    stroke_color = colors.HexColor("#d9d9d9")
    card_values = data.get("card_values")
    if not isinstance(card_values, (list, tuple)) or len(card_values) < 4:
        card_values = ["0", "0", "0", "0"]
    else:
        card_values = [str(card_values[i]) if i < len(card_values) else "-" for i in range(4)]
    icon_size = 0.6 * inch
    card_pad = 0.1 * inch
    text_left = icon_size + card_pad * 2
    _cards = _t_card_config(data)
    _kg = _t('kg', data)
    for i in range(4):
        x = padding + i * (card_width + gap)
        pdf.setFillColor(fill_color)
        pdf.setStrokeColor(stroke_color)
        pdf.setLineWidth(1)
        pdf.roundRect(x, row_top_y, card_width, card_height, radius)
        # Icon on the left (centered vertically in card)
        icon_y = row_top_y + (card_height - icon_size) / 2
        icon_path = _asset_path(_cards[i][1])
        if os.path.exists(icon_path):
            try:
                pdf.drawImage(icon_path, x + card_pad, icon_y, width=icon_size, height=icon_size, mask="auto")
            except Exception:
                pass
        # Two rows of text on the right: header (small, gray), value (larger, dark)
        text_x = x + text_left
        mid_y = row_top_y + card_height / 2
        header_y = mid_y + 0.08 * inch
        value_y = mid_y - 0.16 * inch
        pdf.setFont("IBMPlexSansThai-Regular", 10)
        pdf.setFillColor(colors.HexColor("#656565"))
        pdf.drawString(text_x, header_y, _safe(_cards[i][0]))
        pdf.setFont("IBMPlexSansThai-Bold", 16)
        pdf.setFillColor(PRIMARY)
        pdf.drawString(text_x, value_y, _fmt_num(card_values[i]) + f" {_kg}")
    return row_top_y - (0.25 * inch)


# Layout constants for flow chart (used for pagination and drawing)
_FLOW_ROW_H = 0.85 * inch
_FLOW_ROW_GAP = 0.20 * inch
_FLOW_INNER_PAD = 0.20 * inch
_FLOW_MIN_INNER_PAD = 0.12 * inch


def _flow_content_height_for_rows(row_heights: list) -> float:
    """Total vertical content height given a list of per-row heights."""
    if not row_heights:
        return 0.0
    return sum(row_heights) + (len(row_heights) - 1) * _FLOW_ROW_GAP


def _flow_content_height(n_rows: int) -> float:
    """Total vertical content height for n uniform flow chart rows (fallback)."""
    if n_rows <= 0:
        return 0.0
    return n_rows * _FLOW_ROW_H + (n_rows - 1) * _FLOW_ROW_GAP


def _rows_that_fit_in_box_var(box_height: float, row_heights: list) -> int:
    """Max number of rows that fit given variable per-row heights."""
    available = box_height - 2 * _FLOW_INNER_PAD
    if available <= 0 or not row_heights:
        return 1
    total = 0.0
    for i, rh in enumerate(row_heights):
        needed = rh if i == 0 else rh + _FLOW_ROW_GAP
        if total + needed > available:
            return max(1, i)
        total += needed
    return len(row_heights)


def _build_flow_chart_pages(groups: list, n_rows: int, rows_per_page: int, row_heights: list = None, page_available: float = None) -> list:
    """
    Split flow chart rows across pages using variable row heights when available.
    Returns list of pages; each page is dict: global_indices, page_groups.
    """
    if n_rows <= 0:
        return []
    group_of_row = [None] * n_rows
    for gi, g in enumerate(groups):
        for global_idx in g:
            group_of_row[global_idx] = gi

    use_var = row_heights is not None and page_available is not None
    pages = []
    row_start = 0
    while row_start < n_rows:
        if use_var:
            remaining_heights = row_heights[row_start:]
            count = _rows_that_fit_in_box_var(page_available + 2 * _FLOW_INNER_PAD, remaining_heights)
            row_end = min(row_start + count, n_rows)
        else:
            row_end = min(row_start + max(1, rows_per_page), n_rows)
        page_global_indices = list(range(row_start, row_end))
        page_groups = []
        current_group = None
        segment = []
        for pos, gidx in enumerate(page_global_indices):
            grp = group_of_row[gidx]
            if grp != current_group:
                if segment:
                    page_groups.append(segment)
                segment = [pos]
                current_group = grp
            else:
                segment.append(pos)
        if segment:
            page_groups.append(segment)
        pages.append({"global_indices": page_global_indices, "page_groups": page_groups})
        row_start = row_end
    return pages


def _all_leaves_managed(transport_children: list) -> bool:
    """Return True if every leaf node in the transport tree has status='arrived' and a disposal_method."""
    if not transport_children:
        return False

    def _collect_leaves(nodes: list) -> list:
        leaves = []
        for node in nodes:
            children = node.get("children") or []
            if not children:
                leaves.append(node)
            else:
                leaves.extend(_collect_leaves(children))
        return leaves

    leaves = _collect_leaves(transport_children)
    if not leaves:
        return False
    return all(
        leaf.get("status") == "arrived" and leaf.get("disposal_method")
        for leaf in leaves
    )


def _collect_transit_info(transports: list) -> list:
    """Collect unique 'messenger (vehicle)' strings from all nodes in a transport tree."""
    seen = set()
    results = []

    def _walk(nodes):
        for t in nodes:
            if not isinstance(t, dict):
                continue
            meta = t.get("meta_data") or {}
            if isinstance(meta, str):
                try:
                    import json as _json
                    meta = _json.loads(meta)
                except Exception:
                    meta = {}
            if not isinstance(meta, dict):
                meta = {}
            raw_m = meta.get("messenger_info")
            if isinstance(raw_m, str):
                m_name = raw_m
            elif isinstance(raw_m, dict):
                m_name = raw_m.get("name") or raw_m.get("messenger_name") or ""
            else:
                m_name = ""
            raw_v = meta.get("vehicle_info")
            if isinstance(raw_v, str):
                v_plate = raw_v
            elif isinstance(raw_v, dict):
                v_plate = raw_v.get("license_plate") or raw_v.get("plate") or raw_v.get("name") or ""
            else:
                v_plate = ""
            if m_name or v_plate:
                if m_name and v_plate:
                    info = f"{m_name} ({v_plate})"
                elif m_name:
                    info = m_name
                else:
                    info = v_plate
                if info not in seen:
                    seen.add(info)
                    results.append(info)
            if t.get("children"):
                _walk(t["children"])

    _walk(transports)
    return results


def _collect_disposal_methods(transports: list, group_weight: float = 0, lang: str = 'th') -> list:
    """Collect unique (material, destination, disposal_method) combos from leaf nodes with summed percentage and weight.
    Leaves without a disposal_method are summed into a 'pending' entry.
    Returns list of dicts with method (label), percentage_of_group, weight, pending.
    """
    combo_data: dict = {}
    pending_pct = 0.0
    pending_weight = 0.0

    def _loc_label(t: dict, field: str) -> str:
        obj = t.get(field)
        if isinstance(obj, dict):
            return obj.get("display_name") or obj.get("name_en") or obj.get("name_th") or ""
        return ""

    def _mat_label(t: dict) -> str:
        mat = t.get("material")
        if isinstance(mat, dict):
            return mat.get(f"name_{lang}") or mat.get("name_th") or mat.get("name_en") or ""
        return ""

    def _walk(nodes):
        nonlocal pending_pct, pending_weight
        for t in nodes:
            if not isinstance(t, dict):
                continue
            children = t.get("children") or []
            if children:
                _walk(children)
            else:
                method = t.get("disposal_method") or ""
                pct = float(t.get("percentage_of_group") or 0)
                w = float(t.get("weight") or 0)
                if method:
                    mat_id = t.get("material_id")
                    dest_id = t.get("destination_id")
                    key = (mat_id, dest_id, method)
                    if key not in combo_data:
                        combo_data[key] = {
                            "pct": 0.0, "weight": 0.0,
                            "material": _mat_label(t),
                            "destination": _loc_label(t, "destination"),
                            "method": _translate_method(method, lang),
                            "method_en": method,
                        }
                    combo_data[key]["pct"] += pct
                    combo_data[key]["weight"] += w
                else:
                    pending_pct += pct
                    pending_weight += w

    _walk(transports)
    assigned_pct = sum(d["pct"] for d in combo_data.values()) + pending_pct
    unaccounted = round(100.0 - assigned_pct, 2) if assigned_pct < 99.99 else 0.0
    total_pending_pct = round(pending_pct + max(unaccounted, 0), 2)

    assigned_weight = sum(d["weight"] for d in combo_data.values()) + pending_weight
    unaccounted_weight = round(group_weight - assigned_weight, 2) if group_weight > assigned_weight else 0.0
    total_pending_weight = round(pending_weight + max(unaccounted_weight, 0), 2)

    results = []
    for d in combo_data.values():
        results.append({
            "method_name": d["method"],
            "method_name_en": d["method_en"],
            "material_name": d["material"],
            "destination_name": d["destination"],
            "percentage_of_group": round(d["pct"], 2),
            "weight": round(d["weight"], 2),
            "pending": False,
        })
    if total_pending_pct > 0:
        results.append({
            "method_name": _TR.get(lang, _TR['th']).get('pending', 'กำลังรอการจัดการ'),
            "material_name": "",
            "destination_name": "",
            "percentage_of_group": total_pending_pct,
            "weight": total_pending_weight,
            "pending": True,
        })
    return results


def _method_stack_height(disposal_methods: list) -> float:
    """Compute the total vertical height needed for the disposal method nodes."""
    if not disposal_methods:
        return 0.0
    line_h = 0.10 * inch
    top_pad = 0.10 * inch
    bot_pad = 0.08 * inch
    gap = 0.06 * inch
    heights = []
    for dm in disposal_methods:
        n_lines = 2  # material+weight title line + method line
        if dm.get("destination_name"):
            n_lines += 1
        heights.append(top_pad + n_lines * line_h + bot_pad)
    return sum(heights) + (len(heights) - 1) * gap


def _build_chart_rows(hierarchy_data: list, data: dict = None):
    """Build flat rows and origin-groups from hierarchy data for the flow chart.
    Returns (rows, groups) where rows is a flat list of dicts and groups is a list of lists of indices (grouped by origin).
    """
    _lang = (data or {}).get('language', 'th') or 'th'
    rows = []
    groups = []
    for origin_node in hierarchy_data:
        if not isinstance(origin_node, dict):
            continue
        group_indices = []
        for group_node in origin_node.get("children") or []:
            if not isinstance(group_node, dict):
                continue
            idx = len(rows)
            group_indices.append(idx)
            group_transports = group_node.get("children") or []
            group_w = float(group_node.get("weight") or group_node.get("total_weight_kg") or 0)
            dmethods = _collect_disposal_methods(group_transports, group_w, lang=_lang)
            methods_h = _method_stack_height(dmethods)
            rh = max(_FLOW_ROW_H, methods_h + 0.08 * inch)
            rows.append({
                "origin": origin_node.get("origin") or {"display_name": origin_node.get("name", "-")},
                "origin_id": origin_node.get("origin_id"),
                "origin_weight": origin_node.get("weight", 0),
                "material": group_node.get("material") or {},
                "weight": group_w,
                "is_managed": _all_leaves_managed(group_transports),
                "transit_info": _collect_transit_info(group_transports),
                "disposal_methods": dmethods,
                "row_height": rh,
            })
        if group_indices:
            groups.append(group_indices)
    return rows, groups


def _draw_flow_chart(
    pdf,
    box_left: float,
    box_bottom: float,
    box_width: float,
    box_height: float,
    records: list,
    groups_override: list = None,
    original_indices_override: list = None,
    data: dict = None,
) -> None:
    """
    Draw flowchart inside the box: Origin | Group/Material | Delivered By | Status.
    records: flat list of dicts from _build_chart_rows (origin, material, weight, is_managed).
    groups_override: list of lists of indices grouped by origin.
    """
    if not records:
        try:
            pdf.setFont("IBMPlexSansThai-Regular", 10)
        except Exception:
            pdf.setFont("Helvetica", 10)
        pdf.setFillColor(colors.HexColor("#656565"))
        pdf.drawString(box_left + 0.2 * inch, box_bottom + box_height / 2 - 0.05 * inch, _t('no_data', data))
        return
    n = len(records)
    if groups_override is not None and original_indices_override is not None:
        groups = groups_override
        original_indices = original_indices_override
    else:
        groups = [list(range(n))]
        original_indices = list(range(n))

    inner_pad = _FLOW_INNER_PAD
    col_gap = 0.12 * inch
    row_gap = _FLOW_ROW_GAP
    n_cols = 4
    usable_width = box_width - 2 * inner_pad - (n_cols - 1) * col_gap
    col_w = usable_width / n_cols
    shrink_rest = 0.4 * inch
    col_w0 = col_w
    col_w_rest = col_w - shrink_rest
    col_gap_plus = col_gap + shrink_rest
    per_row_h = [rec.get("row_height", _FLOW_ROW_H) for rec in records]
    node_h = _FLOW_ROW_H - 0.08 * inch
    origin_extra_h = 0.40 * inch
    origin_h = node_h + origin_extra_h
    raw_content_h = sum(per_row_h) + (n - 1) * row_gap if n > 1 else per_row_h[0]

    top_overflow = 0.0
    bottom_overflow = 0.0
    if groups:
        first_grp = groups[0]
        first_span = sum(per_row_h[i] for i in first_grp) + max(0, len(first_grp) - 1) * row_gap
        top_overflow = max(0, (origin_h - first_span) / 2)
        last_grp = groups[-1]
        last_span = sum(per_row_h[i] for i in last_grp) + max(0, len(last_grp) - 1) * row_gap
        bottom_overflow = max(0, (origin_h - last_span) / 2)

    total_content_h = raw_content_h + top_overflow + bottom_overflow
    content_bottom = box_bottom + (box_height - total_content_h) / 2

    row_mid_y_map = {}
    _y_cursor = content_bottom + total_content_h - top_overflow
    for _idx in range(n):
        _y_cursor -= per_row_h[_idx]
        row_mid_y_map[_idx] = _y_cursor + per_row_h[_idx] / 2
        _y_cursor -= row_gap
    stroke_green = colors.HexColor("#85bbae")
    stroke_grey = colors.HexColor("#d9d9d9")
    fill_white = colors.HexColor("#ffffff")

    stroke_orange = colors.HexColor("#fd7e14")
    node_radius = 0.06 * inch
    pin_path = _asset_path("pinPointIcon.png")
    recycle_path = _asset_path("totalRecycle.png")
    cx0 = box_left + inner_pad
    cx1 = box_left + inner_pad + col_w0 + col_gap_plus
    cx2 = cx1 + col_w_rest + col_gap_plus
    cx3 = cx2 + col_w_rest + col_gap_plus
    x_end0 = cx0 + col_w0
    x_junction = (x_end0 + cx1) / 2
    x_start1 = cx1
    x_end1 = cx1 + col_w_rest
    x_start2 = cx2
    x_end2 = cx2 + col_w_rest
    x_start3 = cx3

    for group in groups:
        mid_ys = [row_mid_y_map[i] for i in group]
        row_ys = [m - node_h / 2 for m in mid_ys]
        top_mid_y = mid_ys[0]
        bottom_mid_y = mid_ys[-1]
        origin_center_y = (top_mid_y + bottom_mid_y) / 2
        origin_y = origin_center_y - origin_h / 2

        rec0 = records[group[0]]
        orig = rec0.get("origin") or {}
        orig_name = _loc_name(orig)
        total_weight = sum(records[i].get("weight") or 0 for i in group)

        # --- Origin card (vertical layout: circle icon, name, divider, label) ---
        pdf.setFillColor(fill_white)
        pdf.setStrokeColor(stroke_grey)
        pdf.setLineWidth(0.5)
        pdf.roundRect(cx0, origin_y, col_w0, origin_h, node_radius)

        # Pin icon (already includes circle background), centered near top
        pin_sz = 0.38 * inch
        pin_cx = cx0 + col_w0 / 2
        pin_top = origin_y + origin_h - 0.10 * inch
        pin_cy = pin_top - pin_sz / 2
        if os.path.exists(pin_path):
            try:
                pdf.drawImage(pin_path, pin_cx - pin_sz / 2, pin_top - pin_sz, width=pin_sz, height=pin_sz, mask="auto")
            except Exception:
                pass

        # Bold origin name centered below icon
        name_y = pin_top - pin_sz - 0.2 * inch
        try:
            pdf.setFont("IBMPlexSansThai-Bold", 10)
        except Exception:
            pdf.setFont("Helvetica-Bold", 10)
        pdf.setFillColor(colors.HexColor("#333333"))
        try:
            name_w = pdf.stringWidth(orig_name[:20], "IBMPlexSansThai-Bold", 10)
        except Exception:
            name_w = pdf.stringWidth(orig_name[:20], "Helvetica-Bold", 10)
        pdf.drawString(cx0 + (col_w0 - name_w) / 2, name_y, orig_name[:20])

        # Thin horizontal divider
        divider_y = name_y - 0.10 * inch
        inset = 0.15 * inch
        pdf.setStrokeColor(stroke_grey)
        pdf.setLineWidth(0.3)
        pdf.line(cx0 + inset, divider_y, cx0 + col_w0 - inset, divider_y)

        # Total weight centered below divider
        weight_label = f"{_t('total_weight', data or {})}  {_fmt_num(total_weight)} {_t('kg', data or {})}"
        label_y = divider_y - 0.14 * inch
        try:
            pdf.setFont("IBMPlexSansThai-Regular", 7)
        except Exception:
            pdf.setFont("Helvetica", 7)
        pdf.setFillColor(colors.HexColor("#999999"))
        try:
            label_w = pdf.stringWidth(weight_label, "IBMPlexSansThai-Regular", 7)
        except Exception:
            label_w = pdf.stringWidth(weight_label, "Helvetica", 7)
        pdf.drawString(cx0 + (col_w0 - label_w) / 2, label_y, weight_label)

        pdf.setStrokeColor(stroke_green)
        pdf.setLineWidth(0.8)
        if len(group) > 1:
            pdf.line(x_end0, origin_center_y, x_junction, origin_center_y)
            pdf.line(x_junction, bottom_mid_y, x_junction, top_mid_y)

        for k, i in enumerate(group):
            rec = records[i]
            orig_idx = original_indices[i]
            row_y = row_ys[k]
            mid_y = mid_ys[k]
            w = rec.get("weight") or 0
            is_managed = rec.get("is_managed", False)

            if len(group) > 1:
                pdf.line(x_junction, mid_y, x_start1, mid_y)
            else:
                pdf.line(x_end0, mid_y, x_start1, mid_y)

            # --- Column 1: Group / Material (white card, #85bbae left accent, name + pill upper-right) ---
            mat = rec.get("material") or {}
            if isinstance(mat, str):
                mat_name = _safe(mat)
            elif isinstance(mat, dict):
                _lang = (data or {}).get('language', 'th') or 'th'
                mat_name = _safe(mat.get(f"name_{_lang}") or mat.get("name_th") or mat.get("name_en") or "-")
            else:
                mat_name = "-"
            accent_color = colors.HexColor("#85bbae")
            # White card with grey border
            pdf.setFillColor(fill_white)
            pdf.setStrokeColor(stroke_grey)
            pdf.setLineWidth(0.5)
            pdf.roundRect(cx1, row_y, col_w_rest, node_h, node_radius)
            # Left accent bar
            accent_w = 0.05 * inch
            pdf.setFillColor(accent_color)
            pdf.roundRect(cx1, row_y, accent_w + node_radius, node_h, node_radius, fill=1, stroke=0)
            pdf.rect(cx1 + node_radius, row_y, accent_w, node_h, fill=1, stroke=0)
            # Material name left-aligned, vertically centered
            pdf.setFillColor(colors.HexColor("#595959"))
            try:
                pdf.setFont("IBMPlexSansThai-Regular", 8)
            except Exception:
                pdf.setFont("Helvetica", 8)
            mat_display = mat_name
            mat_font = "IBMPlexSansThai-Regular"
            mat_font_size = 8
            mat_max_w = col_w_rest - accent_w - 0.12 * inch - 0.52 * inch - 0.20 * inch
            try:
                while pdf.stringWidth(mat_display, mat_font, mat_font_size) > mat_max_w and len(mat_display) > 1:
                    mat_display = mat_display[:-1]
            except Exception:
                mat_display = mat_name[:15]
            if len(mat_display) < len(mat_name):
                mat_display = mat_display.rstrip() + "..."
            pdf.drawString(cx1 + accent_w + 0.12 * inch, row_y + node_h / 2 - 0.04 * inch, mat_display)
            # Weight pill upper-right
            pill_text = f"{_fmt_num(w)} {_t('kg', data or {})}"
            pill_w = 0.52 * inch
            pill_h_m = 0.20 * inch
            pill_x = cx1 + col_w_rest - pill_w - 0.08 * inch
            pill_y_m = row_y + node_h - pill_h_m - 0.06 * inch
            pdf.setFillColor(accent_color)
            pdf.roundRect(pill_x, pill_y_m, pill_w, pill_h_m, pill_h_m / 2, fill=1, stroke=0)
            pdf.setFillColor(fill_white)
            try:
                pdf.setFont("IBMPlexSansThai-Bold", 7)
            except Exception:
                pdf.setFont("Helvetica-Bold", 7)
            try:
                ptw = pdf.stringWidth(pill_text, "IBMPlexSansThai-Bold", 7)
            except Exception:
                ptw = pdf.stringWidth(pill_text, "Helvetica-Bold", 7)
            pdf.drawString(pill_x + (pill_w - ptw) / 2, pill_y_m + 0.07 * inch, pill_text)

            # --- Column 2: Delivered By (per group, height fits content) ---
            transit_info_list = rec.get("transit_info") or []
            n_info = len(transit_info_list)
            max_display = min(n_info, 8)
            has_overflow = n_info > max_display
            line_spacing_t = 0.12 * inch
            top_pad_t = 0.20 * inch
            bottom_pad_t = 0.20 * inch
            title_gap_t = 0.16 * inch
            if max_display > 0:
                n_lines = max_display + (1 if has_overflow else 0)
                content_h = title_gap_t + (n_lines - 1) * line_spacing_t
                transit_card_h = top_pad_t + content_h + bottom_pad_t
            else:
                transit_card_h = 0.35 * inch
            transit_card_y = mid_y - transit_card_h / 2
            pdf.setFillColor(fill_white)
            pdf.setStrokeColor(stroke_orange)
            pdf.setLineWidth(0.5)
            pdf.roundRect(cx2, transit_card_y, col_w_rest, transit_card_h, node_radius)
            pdf.setFillColor(stroke_orange)
            try:
                pdf.setFont("IBMPlexSansThai-Bold", 7)
            except Exception:
                pdf.setFont("Helvetica-Bold", 7)
            transit_title = _t('deliverer', data or {})
            title_y_t = transit_card_y + transit_card_h - top_pad_t
            pdf.drawString(cx2 + 0.08 * inch, title_y_t, transit_title)
            if max_display > 0:
                try:
                    pdf.setFont("IBMPlexSansThai-Regular", 6)
                except Exception:
                    pdf.setFont("Helvetica", 6)
                pdf.setFillColor(colors.HexColor("#595959"))
                line_y_t = title_y_t - title_gap_t
                for ti in range(max_display):
                    pdf.drawString(cx2 + 0.08 * inch, line_y_t, f"\u2022 {_safe(transit_info_list[ti])[:28]}")
                    line_y_t -= line_spacing_t
                if has_overflow:
                    pdf.setFillColor(colors.HexColor("#999999"))
                    pdf.drawString(cx2 + 0.08 * inch, line_y_t, f"+{n_info - max_display} {_t('more', data or {})}")

            # --- Column 3: Disposal Method(s) ---
            disposal_methods = rec.get("disposal_methods") or []
            status_border = colors.HexColor("#a4e1af")
            status_text_color = colors.HexColor("#7bbfa5")
            accent_method = colors.HexColor("#85bbae")
            method_gap_v = 0.06 * inch
            method_line_h = 0.10 * inch
            method_top_pad = 0.10 * inch
            method_bot_pad = 0.08 * inch
            accent_bar_w = 0.04 * inch

            pending_border = colors.HexColor("#c0c0c0")
            pending_text = colors.HexColor("#999999")
            pending_pill_bg = colors.HexColor("#d9d9d9")

            if not disposal_methods:
                status_h = node_h * 0.5
                status_y = row_y + (node_h - status_h) / 2
                pdf.setDash(3, 3)
                pdf.setFillColor(fill_white)
                pdf.setStrokeColor(pending_border)
                pdf.setLineWidth(0.5)
                pdf.roundRect(cx3, status_y, col_w_rest, status_h, node_radius)
                pdf.setDash()
                pdf.setFillColor(pending_text)
                try:
                    pdf.setFont("IBMPlexSansThai-Regular", 7)
                except Exception:
                    pdf.setFont("Helvetica", 7)
                status_label = _t('pending', data or {})
                try:
                    sw = pdf.stringWidth(status_label, "IBMPlexSansThai-Regular", 7)
                except Exception:
                    sw = pdf.stringWidth(status_label, "Helvetica", 7)
                pdf.drawString(cx3 + (col_w_rest - sw) / 2, status_y + status_h / 2 - 0.04 * inch, status_label)
            else:
                node_heights = []
                for dm in disposal_methods:
                    n_lines = 2  # material+weight title line + method line
                    if dm.get("destination_name"):
                        n_lines += 1
                    node_heights.append(method_top_pad + n_lines * method_line_h + method_bot_pad)
                n_methods = len(disposal_methods)
                total_methods_h = sum(node_heights) + (n_methods - 1) * method_gap_v
                methods_top_y = mid_y + total_methods_h / 2
                method_mid_ys = []
                cursor_y = methods_top_y

                for mi, dm in enumerate(disposal_methods):
                    m_h = node_heights[mi]
                    m_y = cursor_y - m_h
                    m_mid = m_y + m_h / 2
                    method_mid_ys.append(m_mid)
                    cursor_y = m_y - method_gap_v

                    meth_name = _safe(dm.get("method_name", "-"))
                    meth_name_en = dm.get("method_name_en") or meth_name
                    mat_name = _safe(dm.get("material_name", ""))
                    dest_name = _safe(dm.get("destination_name", ""))
                    pct = dm.get("percentage_of_group", 0)
                    dm_weight = dm.get("weight", 0)
                    is_pending = dm.get("pending", False)

                    if is_pending:
                        node_border = pending_border
                        node_accent = pending_border
                        node_title_color = pending_text
                        node_pill_bg = pending_pill_bg
                    elif meth_name_en in _DIRECTED_METHODS:
                        node_border = colors.HexColor("#eb7170")
                        node_accent = colors.HexColor("#eb7170")
                        node_title_color = colors.HexColor("#eb7170")
                        node_pill_bg = colors.HexColor("#eb7170")
                    elif meth_name_en in _DIVERTED_METHODS:
                        node_border = colors.HexColor("#c6dcf9")
                        node_accent = colors.HexColor("#c6dcf9")
                        node_title_color = colors.HexColor("#7ba3d4")
                        node_pill_bg = colors.HexColor("#c6dcf9")
                    else:
                        node_border = status_border
                        node_accent = accent_method
                        node_title_color = status_text_color
                        node_pill_bg = status_border

                    pdf.setFillColor(fill_white)
                    pdf.setStrokeColor(node_border)
                    pdf.setLineWidth(0.5)
                    if is_pending:
                        pdf.setDash(3, 3)
                    pdf.roundRect(cx3, m_y, col_w_rest, m_h, node_radius)
                    if is_pending:
                        pdf.setDash()

                    if not is_pending:
                        pdf.setFillColor(node_accent)
                        pdf.roundRect(cx3, m_y, accent_bar_w + node_radius, m_h, node_radius, fill=1, stroke=0)
                        pdf.rect(cx3 + node_radius, m_y, accent_bar_w, m_h, fill=1, stroke=0)

                    pct_text = f"{pct}%"
                    pill_w_s = 0.38 * inch
                    pill_h_s = 0.14 * inch
                    pill_x_s = cx3 + col_w_rest - pill_w_s - 0.05 * inch
                    pill_y_s = m_y + m_h - pill_h_s - 0.05 * inch
                    text_x = cx3 + accent_bar_w + 0.10 * inch
                    max_text_w = pill_x_s - text_x - 0.04 * inch
                    line_y = m_y + m_h - method_top_pad - method_line_h + 0.04 * inch

                    def _draw_clipped(txt, font, size, color, y_pos):
                        pdf.setFillColor(color)
                        try:
                            pdf.setFont(font, size)
                        except Exception:
                            pdf.setFont("Helvetica", size)
                        disp = txt
                        try:
                            while pdf.stringWidth(disp, font, size) > max_text_w and len(disp) > 1:
                                disp = disp[:-1]
                        except Exception:
                            disp = txt[:35]
                        pdf.drawString(text_x, y_pos, disp)

                    _kg_l = _t('kg', data or {})
                    mat_weight_label = f"{mat_name} ({_fmt_num(dm_weight)} {_kg_l})" if mat_name else f"{_fmt_num(dm_weight)} {_kg_l}"
                    _draw_clipped(f"\u25B8 {mat_weight_label}", "IBMPlexSansThai-Bold", 6, node_title_color, line_y)
                    line_y -= method_line_h

                    if dest_name:
                        _draw_clipped(f"\u25B8 {_t('destination_label', data or {})} : {dest_name}", "IBMPlexSansThai-Regular", 5.5, colors.HexColor("#595959"), line_y)
                        line_y -= method_line_h

                    _draw_clipped(f"\u25B8 {_t('method_label', data or {})} : {meth_name}", "IBMPlexSansThai-Regular", 5.5, colors.HexColor("#595959"), line_y)

                    pdf.setFillColor(node_pill_bg)
                    pdf.roundRect(pill_x_s, pill_y_s, pill_w_s, pill_h_s, pill_h_s / 2, fill=1, stroke=0)
                    pdf.setFillColor(fill_white)
                    try:
                        pdf.setFont("IBMPlexSansThai-Bold", 6)
                    except Exception:
                        pdf.setFont("Helvetica-Bold", 6)
                    try:
                        pw = pdf.stringWidth(pct_text, "IBMPlexSansThai-Bold", 6)
                    except Exception:
                        pw = pdf.stringWidth(pct_text, "Helvetica-Bold", 6)
                    pdf.drawString(pill_x_s + (pill_w_s - pw) / 2, pill_y_s + 0.04 * inch, pct_text)

                if n_methods > 1:
                    x_junc_s = (x_end2 + cx3) / 2
                    pdf.setStrokeColor(stroke_green)
                    pdf.setLineWidth(0.8)
                    pdf.line(x_junc_s, method_mid_ys[-1], x_junc_s, method_mid_ys[0])
                    for mi_c, m_mid in enumerate(method_mid_ys):
                        if disposal_methods[mi_c].get("pending"):
                            pdf.setStrokeColor(stroke_grey)
                            pdf.setDash(3, 3)
                            pdf.line(x_junc_s, m_mid, cx3, m_mid)
                            pdf.setDash()
                            pdf.setStrokeColor(stroke_green)
                        else:
                            pdf.line(x_junc_s, m_mid, cx3, m_mid)

            # --- Connector lines: Material -> Delivered By -> Status ---
            pdf.setStrokeColor(stroke_green)
            pdf.setLineWidth(0.8)
            pdf.line(x_end1, mid_y, x_start2, mid_y)
            if not disposal_methods:
                pdf.setStrokeColor(stroke_grey)
                pdf.setDash(3, 3)
                pdf.line(x_end2, mid_y, x_start3, mid_y)
                pdf.setDash()
            elif len(disposal_methods) == 1:
                if disposal_methods[0].get("pending"):
                    pdf.setStrokeColor(stroke_grey)
                    pdf.setDash(3, 3)
                    pdf.line(x_end2, mid_y, cx3, mid_y)
                    pdf.setDash()
                else:
                    pdf.line(x_end2, mid_y, cx3, mid_y)
            else:
                pdf.line(x_end2, mid_y, x_junc_s, mid_y)


# Item details table: full hierarchy tree
TABLE_HEADER_BG = colors.HexColor("#ededed")
TABLE_ROW_WHITE = colors.white
TABLE_ROW_ALT = colors.HexColor("#f9f9f9")
TABLE_ROW_HEIGHT = 0.32 * inch
TABLE_TITLE_GAP = 0.2 * inch
TABLE_CORNER_RADIUS = 0.08 * inch
TABLE_HEADERS = ["ประเภทวัสดุ", "น้ำหนัก (กก.)", "ต้นทาง", "ปลายทาง", "จัดส่งโดย", "วิธีการกำจัด", "สถานะ"]  # default Thai, overridden at runtime
TABLE_COL_RATIOS = [3.0, 0.8, 1.8, 1.5, 1.5, 1.8, 0.8]
_STATUS_PILLS_COLORS = {
    "completed": (colors.HexColor("#d4edda"), colors.HexColor("#155724")),
    "in_transit": (colors.HexColor("#cce5ff"), colors.HexColor("#004085")),
    "idle":       (colors.HexColor("#e2e3e5"), colors.HexColor("#383d41")),
}
_STATUS_PILLS_LABELS = {
    'en': {"completed": "Completed", "in_transit": "In Transit", "idle": "Pending"},
    'th': {"completed": "เสร็จสิ้น", "in_transit": "กำลังขนส่ง", "idle": "รอดำเนินการ"},
}
_INDENT_STEP = 0.18 * inch
_ACCENT_COLOR = colors.HexColor("#85bbae")


def _loc_name(loc) -> str:
    if not loc:
        return "-"
    if isinstance(loc, str):
        return _safe(loc)
    if not isinstance(loc, dict):
        return "-"
    return _safe(loc.get("display_name") or loc.get("name_en") or loc.get("name_th") or "-")


def _transport_status_key(t) -> str:
    if not isinstance(t, dict):
        return ""
    status = t.get("status") or ""
    if status == "arrived" and t.get("disposal_method"):
        return "completed"
    if status == "arrived":
        return "idle"
    return "in_transit" if status else ""


def _flatten_hierarchy_for_table(hierarchy_data: list, data: dict = None) -> list:
    """Flatten hierarchy into table rows with indent/type metadata."""
    rows = []
    for origin_node in hierarchy_data:
        if not isinstance(origin_node, dict):
            continue
        origin = origin_node.get("origin") or {}
        rows.append({
            "type": "origin", "indent": 0,
            "label": _loc_name(origin) if origin else (origin_node.get("name") or "-"),
            "weight": origin_node.get("weight", 0),
            "origin": "-", "destination": "-",
            "delivered_by": "-", "disposal_method": "-", "status_key": "",
        })
        for group_node in origin_node.get("children") or []:
            if not isinstance(group_node, dict):
                continue
            mat = group_node.get("material") or {}
            if isinstance(mat, str):
                mat = {"name_th": mat}
            _lang = (data or {}).get('language', 'th') or 'th'
            mat_name = _safe(mat.get(f"name_{_lang}") or mat.get("name_th") or mat.get("name_en") or "-") if isinstance(mat, dict) else _safe(mat)
            g_origin = group_node.get("origin") or origin
            rows.append({
                "type": "group", "indent": 1,
                "label": mat_name,
                "weight": group_node.get("weight") or group_node.get("total_weight_kg") or 0,
                "origin": _loc_name(g_origin), "destination": "-",
                "delivered_by": "-", "disposal_method": "-", "status_key": "",
            })

            def _flatten_transports(transports, depth):
                for t in transports:
                    if not isinstance(t, dict):
                        continue
                    t_origin = t.get("origin") or {}
                    t_dest = t.get("destination") or {}
                    o_name = _loc_name(t_origin)
                    d_name = _loc_name(t_dest)
                    label = f"{o_name} \u2192 {d_name}" if d_name != "-" else o_name
                    meta = t.get("meta_data") or {}
                    if isinstance(meta, str):
                        try:
                            import json as _json
                            meta = _json.loads(meta)
                        except Exception:
                            meta = {}
                    if not isinstance(meta, dict):
                        meta = {}
                    raw_m = meta.get("messenger_info")
                    if isinstance(raw_m, str):
                        m_name = raw_m
                    elif isinstance(raw_m, dict):
                        m_name = raw_m.get("name") or raw_m.get("messenger_name") or ""
                    else:
                        m_name = ""
                    raw_v = meta.get("vehicle_info")
                    if isinstance(raw_v, str):
                        v_plate = raw_v
                    elif isinstance(raw_v, dict):
                        v_plate = raw_v.get("license_plate") or raw_v.get("plate") or raw_v.get("name") or ""
                    else:
                        v_plate = ""
                    if m_name and v_plate:
                        delivered = f"{m_name} ({v_plate})"
                    elif m_name:
                        delivered = m_name
                    elif v_plate:
                        delivered = v_plate
                    else:
                        delivered = "-"
                    is_leaf = not t.get("children")
                    rows.append({
                        "type": "transport", "indent": depth,
                        "label": label,
                        "weight": t.get("weight") or 0,
                        "origin": o_name, "destination": d_name,
                        "delivered_by": delivered,
                        "disposal_method": _translate_method(t.get("disposal_method") or "", _lang) or "-",
                        "status_key": _transport_status_key(t) if is_leaf else "",
                    })
                    if not is_leaf:
                        _flatten_transports(t["children"], depth + 1)

            _flatten_transports(group_node.get("children") or [], 2)
    return rows


def _draw_item_details_table(
    pdf,
    page_width_points: float,
    page_height_points: float,
    records: list,
    start_y: float,
    data: dict,
) -> None:
    """
    Draw full hierarchy table below the chart. Origin -> Group -> Transport tree with indentation.
    If rows overflow, continue on new pages.
    """
    hierarchy_data = data.get("hierarchy") or []
    flat_rows = _flatten_hierarchy_for_table(hierarchy_data, data=data)
    if not flat_rows:
        return
    table_left = padding
    table_width = page_width_points - 2 * padding
    bottom_margin = padding
    row_height = TABLE_ROW_HEIGHT
    total_ratio = sum(TABLE_COL_RATIOS)
    col_widths = [table_width * (r / total_ratio) for r in TABLE_COL_RATIOS]
    cell_pad = 0.05 * inch
    cell_pad_left = 0.14 * inch
    radius = TABLE_CORNER_RADIUS
    text_color = colors.HexColor("#595959")

    def draw_row_rect(y: float, bg_color, bottom_rounded: bool) -> None:
        bottom = y - row_height
        if not bottom_rounded:
            pdf.setFillColor(bg_color)
            pdf.rect(table_left, bottom, table_width, row_height, fill=1, stroke=0)
            return
        pdf.setFillColor(bg_color)
        pdf.roundRect(table_left, bottom, table_width, row_height, radius, stroke=0, fill=1)
        top_square_y = y - radius
        pdf.rect(table_left, top_square_y, radius, radius, fill=1, stroke=0)
        pdf.rect(table_left + table_width - radius, top_square_y, radius, radius, fill=1, stroke=0)

    def draw_table_title(y: float) -> float:
        pdf.setFillColor(PRIMARY)
        try:
            pdf.setFont("IBMPlexSansThai-Bold", 16)
        except Exception:
            pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(table_left, y, _t('item_details', data))
        return y - TABLE_TITLE_GAP

    def draw_header_row(y: float) -> float:
        pdf.setFillColor(TABLE_HEADER_BG)
        pdf.roundRect(table_left, y - row_height, table_width, row_height, radius, stroke=0, fill=1)
        pdf.rect(table_left, y - row_height, radius, radius, fill=1, stroke=0)
        pdf.rect(table_left + table_width - radius, y - row_height, radius, radius, fill=1, stroke=0)
        pdf.setFillColor(PRIMARY)
        try:
            pdf.setFont("IBMPlexSansThai-Bold", 8)
        except Exception:
            pdf.setFont("Helvetica-Bold", 8)
        x = table_left + cell_pad_left
        _headers = _t('table_headers', data) if isinstance(_t('table_headers', data), list) else TABLE_HEADERS
        for i, h in enumerate(_headers):
            pdf.drawString(x, y - row_height / 2 - 0.03 * inch, h)
            x += col_widths[i]
        pdf.setStrokeColor(colors.HexColor("#d9d9d9"))
        pdf.setLineWidth(0.5)
        pdf.line(table_left, y - row_height, table_left + table_width, y - row_height)
        return y - row_height

    def draw_data_row(y: float, row: dict) -> None:
        indent = row.get("indent", 0)
        rtype = row.get("type", "transport")
        x0 = table_left + cell_pad_left + indent * _INDENT_STEP
        mid_y = y - row_height / 2

        # --- Column 0: Material Type (with indicator) ---
        label = _safe(row.get("label", "-"))
        if rtype == "origin":
            # Small circle indicator for origin
            circle_r = 0.04 * inch
            pdf.setFillColor(colors.HexColor("#d9d9d9"))
            pdf.circle(x0 + circle_r, mid_y, circle_r, fill=1, stroke=0)
            pdf.setFillColor(_ACCENT_COLOR)
            pdf.circle(x0 + circle_r, mid_y, circle_r * 0.5, fill=1, stroke=0)
            pdf.setFillColor(text_color)
            try:
                pdf.setFont("IBMPlexSansThai-Bold", 7)
            except Exception:
                pdf.setFont("Helvetica-Bold", 7)
            pdf.drawString(x0 + circle_r * 2 + 0.04 * inch, mid_y - 0.03 * inch, label[:28])
        else:
            # Colored accent bar for group/transport
            bar_w = 0.03 * inch
            bar_h = row_height * 0.55
            pdf.setFillColor(_ACCENT_COLOR)
            pdf.rect(x0, mid_y - bar_h / 2, bar_w, bar_h, fill=1, stroke=0)
            pdf.setFillColor(text_color)
            try:
                pdf.setFont("IBMPlexSansThai-Regular", 7)
            except Exception:
                pdf.setFont("Helvetica", 7)
            pdf.drawString(x0 + bar_w + 0.05 * inch, mid_y - 0.03 * inch, label[:32])

        # --- Columns 1-5: Weight, Origin, Destination, Delivered By, Disposal method ---
        col_keys = ["weight", "origin", "destination", "delivered_by", "disposal_method"]
        x = table_left + cell_pad_left + col_widths[0]
        try:
            pdf.setFont("IBMPlexSansThai-Regular", 7)
        except Exception:
            pdf.setFont("Helvetica", 7)
        for ci, key in enumerate(col_keys):
            val = row.get(key, "-")
            if key == "weight":
                display = _fmt_num(val) if val and val != "-" else "-"
            else:
                display = _safe(val) if val and val != "-" else "\u2014"
            pdf.setFillColor(text_color)
            pdf.drawString(x, mid_y - 0.03 * inch, display[:25])
            x += col_widths[ci + 1]

        # --- Column 6: Status pill ---
        status_key = row.get("status_key", "")
        _pill_colors = _STATUS_PILLS_COLORS.get(status_key)
        if _pill_colors:
            _lang = (data or {}).get('language', 'th') or 'th'
            pill_bg, pill_fg = _pill_colors
            pill_label = _STATUS_PILLS_LABELS.get(_lang, _STATUS_PILLS_LABELS['th']).get(status_key, status_key)
            pill_w = 0.58 * inch
            pill_h = 0.15 * inch
            pill_left = x
            pill_bottom = mid_y - pill_h / 2
            pdf.setFillColor(pill_bg)
            pdf.setStrokeColor(pill_fg)
            pdf.setLineWidth(0.3)
            pdf.roundRect(pill_left, pill_bottom, pill_w, pill_h, pill_h / 2, fill=1, stroke=1)
            pdf.setFillColor(pill_fg)
            try:
                pdf.setFont("IBMPlexSansThai-Bold", 6)
            except Exception:
                pdf.setFont("Helvetica-Bold", 6)
            try:
                sw = pdf.stringWidth(pill_label, "IBMPlexSansThai-Bold", 6)
            except Exception:
                sw = pdf.stringWidth(pill_label, "Helvetica-Bold", 6)
            pdf.drawString(pill_left + (pill_w - sw) / 2, pill_bottom + 0.05 * inch, pill_label)
        else:
            pdf.setFillColor(text_color)
            try:
                pdf.setFont("IBMPlexSansThai-Regular", 7)
            except Exception:
                pdf.setFont("Helvetica", 7)
            pdf.drawString(x, mid_y - 0.03 * inch, "\u2014")

    y = start_y
    need_title = True
    is_continuation_page = False
    row_index_global = 0
    page_row_index = 0
    min_y_for_row = bottom_margin + row_height

    # Only start the table on this page if there is space for at least the
    # title + header + one data row; otherwise jump to a new page first.
    min_space_needed = TABLE_TITLE_GAP + row_height + row_height  # title gap + header + 1 row
    if y - min_space_needed < min_y_for_row:
        pdf.showPage()
        pdf.setPageSize((page_width_points, page_height_points))
        _draw_header(pdf, page_width_points, page_height_points, data)
        y = page_height_points - (1.8 * inch)
        is_continuation_page = True

    while row_index_global < len(flat_rows):
        if need_title:
            if is_continuation_page:
                y = y - 0.15 * inch
            y = draw_table_title(y)
            y = draw_header_row(y)
            need_title = False
            page_row_index = 0
        while row_index_global < len(flat_rows) and y - row_height >= min_y_for_row:
            row = flat_rows[row_index_global]
            bg = TABLE_ROW_WHITE if (page_row_index % 2 == 0) else TABLE_ROW_ALT
            is_last_on_page = (row_index_global + 1 == len(flat_rows)) or (y - 2 * row_height < min_y_for_row)
            draw_row_rect(y, bg, bottom_rounded=is_last_on_page)
            if not is_last_on_page:
                pdf.setStrokeColor(colors.HexColor("#d9d9d9"))
                pdf.setLineWidth(0.3)
                pdf.line(table_left, y - row_height, table_left + table_width, y - row_height)
            draw_data_row(y, row)
            y -= row_height
            row_index_global += 1
            page_row_index += 1
        if row_index_global < len(flat_rows):
            pdf.showPage()
            pdf.setPageSize((page_width_points, page_height_points))
            _draw_header(pdf, page_width_points, page_height_points, data)
            y = page_height_points - (1.8 * inch)
            is_continuation_page = True
            need_title = True


def _draw_diagram_section(pdf, page_width_points: float, page_height_points: float, y_below_cards: float, data: dict):
    """
    Section title + rounded box with flow chart from hierarchy data.
    Returns (y_bottom_of_diagram_box_on_current_page, chart_rows) for table to start below.
    """
    section_title = _t('header_title', data)
    section_gap = 0.3 * inch
    radius = 0.12 * inch
    box_left = padding
    box_width = page_width_points - 2 * padding
    hierarchy_data = data.get("hierarchy") or []
    records, origin_groups = _build_chart_rows(hierarchy_data, data=data)

    if not records:
        header_y = y_below_cards - 0.15 * inch
        pdf.setFillColor(PRIMARY)
        try:
            pdf.setFont("IBMPlexSansThai-Bold", 16)
        except Exception:
            pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(padding, header_y, section_title)
        box_top = header_y - section_gap
        box_bottom = padding
        box_height = box_top - box_bottom
        pdf.setFillColor(colors.HexColor("#fafafa"))
        pdf.setStrokeColor(colors.HexColor("#d9d9d9"))
        pdf.setLineWidth(1)
        pdf.roundRect(box_left, box_bottom, box_width, box_height, radius)
        _draw_flow_chart(pdf, box_left, box_bottom, box_width, box_height, [], data=data)
        return (box_bottom, records)

    original_indices = list(range(len(records)))
    n_rows = len(records)
    all_row_heights = [rec.get("row_height", _FLOW_ROW_H) for rec in records]
    header_y_first = y_below_cards - 0.15 * inch
    box_top_first = header_y_first - section_gap
    box_bottom_first = padding
    box_height_first = box_top_first - box_bottom_first

    all_content_h = _flow_content_height_for_rows(all_row_heights)
    if all_content_h + 2 * _FLOW_MIN_INNER_PAD <= box_height_first:
        pages = _build_flow_chart_pages(origin_groups, n_rows, n_rows)
    else:
        rows_per_page = _rows_that_fit_in_box_var(box_height_first, all_row_heights)
        pages = _build_flow_chart_pages(
            origin_groups, n_rows, rows_per_page,
            row_heights=all_row_heights,
            page_available=box_height_first - 2 * _FLOW_INNER_PAD,
        )
    last_box_bottom = box_bottom_first

    for page_idx, page_info in enumerate(pages):
        page_rh = [all_row_heights[i] for i in page_info["global_indices"]]
        page_content_h = _flow_content_height_for_rows(page_rh)

        if page_idx > 0:
            pdf.showPage()
            pdf.setPageSize((page_width_points, page_height_points))
            _draw_header(pdf, page_width_points, page_height_points, data)
            y_below_header = page_height_points - (1.8 * inch) - 0.15 * inch
            pdf.setFillColor(PRIMARY)
            try:
                pdf.setFont("IBMPlexSansThai-Bold", 16)
            except Exception:
                pdf.setFont("Helvetica-Bold", 16)
            pdf.drawString(padding, y_below_header, section_title)
            box_height_page = page_content_h + 2 * _FLOW_INNER_PAD
            box_top_page = y_below_header - section_gap
            box_bottom_page = box_top_page - box_height_page
            last_box_bottom = box_bottom_page
            pdf.setFillColor(colors.HexColor("#fafafa"))
            pdf.setStrokeColor(colors.HexColor("#d9d9d9"))
            pdf.setLineWidth(1)
            pdf.roundRect(box_left, box_bottom_page, box_width, box_height_page, radius)
            page_records = [records[i] for i in page_info["global_indices"]]
            page_orig = [original_indices[i] for i in page_info["global_indices"]]
            _draw_flow_chart(
                pdf, box_left, box_bottom_page, box_width, box_height_page,
                page_records, groups_override=page_info["page_groups"], original_indices_override=page_orig,
                data=data,
            )
            continue

        pdf.setFillColor(PRIMARY)
        try:
            pdf.setFont("IBMPlexSansThai-Bold", 16)
        except Exception:
            pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(padding, header_y_first, section_title)
        if len(pages) == 1:
            box_height = box_height_first
            box_bottom = box_bottom_first
        else:
            box_height = page_content_h + 2 * _FLOW_INNER_PAD
            box_bottom = box_top_first - box_height
        last_box_bottom = box_bottom
        pdf.setFillColor(colors.HexColor("#fafafa"))
        pdf.setStrokeColor(colors.HexColor("#d9d9d9"))
        pdf.setLineWidth(1)
        pdf.roundRect(box_left, box_bottom, box_width, box_height, radius)
        page_records = [records[i] for i in page_info["global_indices"]]
        page_orig = [original_indices[i] for i in page_info["global_indices"]]
        _draw_flow_chart(
            pdf, box_left, box_bottom, box_width, box_height,
            page_records, groups_override=page_info["page_groups"], original_indices_override=page_orig,
            data=data,
        )

    return (last_box_bottom, records)


_DIVERTED_METHODS = {
    "Preparation for reuse", "Recycling (Own)", "Other recover operation", "Recycle",
}
_DIRECTED_METHODS = {
    "Composted by municipality", "Municipality receive",
    "Incineration without energy", "Incineration with energy",
}


def _compute_card_values_from_hierarchy(hierarchy_data: list) -> list:
    """Compute [total_waste, total_managed, treatment, disposal] from leaf transports in the hierarchy.

    Mirrors the logic in GET /api/traceability: only counts arrived leaves
    using raw weight.
    """
    treatment_w = 0.0
    disposal_w = 0.0
    total_group_weight = 0.0

    def _sum_leaves(nodes):
        nonlocal treatment_w, disposal_w
        for t in nodes:
            if not isinstance(t, dict):
                continue
            children = t.get("children") or []
            if children:
                _sum_leaves(children)
            else:
                status = t.get("status") or ""
                method = t.get("disposal_method") or ""
                if status != "arrived" or not method:
                    continue
                w = float(t.get("weight") or 0)
                if method in _DIVERTED_METHODS:
                    treatment_w += w
                elif method in _DIRECTED_METHODS:
                    disposal_w += w

    for origin_node in hierarchy_data:
        if not isinstance(origin_node, dict):
            continue
        for group_node in origin_node.get("children") or []:
            if not isinstance(group_node, dict):
                continue
            gw = float(group_node.get("weight") or group_node.get("total_weight_kg") or 0)
            total_group_weight += gw
            _sum_leaves(group_node.get("children") or [])

    total_waste = round(total_group_weight, 2)
    total_treatment = round(treatment_w, 2)
    total_disposal = round(disposal_w, 2)
    total_managed = round(total_treatment + total_disposal, 2)
    return [total_waste, total_managed, total_treatment, total_disposal]


def generate_pdf_bytes(data: dict) -> bytes:
    """
    Generate a traceability PDF from hierarchy data.
    data = {
        "hierarchy": list of origin nodes from get_traceability_hierarchy,
        "date_from": optional str,
        "date_to": optional str,
        "location": optional str or list (display in header; default "ทั้งหมด"),
        "card_values": optional [v1, v2, v3, v4] for the 4 cards.
        "summary": optional { total_waste_weight, total_managed_waste, total_treatment, total_disposal }.
    }
    """
    data = dict(data)
    hierarchy = data.get("hierarchy") or []
    data["card_values"] = _compute_card_values_from_hierarchy(hierarchy)
    _register_fonts()
    width_pt = PAGE_WIDTH_IN * inch
    height_pt = PAGE_HEIGHT_IN * inch
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width_pt, height_pt))

    _draw_header(c, width_pt, height_pt, data)
    y_below_cards = _draw_card_row(c, width_pt, height_pt, data)
    y_below_diagram, chart_rows = _draw_diagram_section(c, width_pt, height_pt, y_below_cards, data)
    table_start_y = y_below_diagram - 0.35 * inch
    _draw_item_details_table(c, width_pt, height_pt, chart_rows, table_start_y, data)

    c.save()
    return buffer.getvalue()
