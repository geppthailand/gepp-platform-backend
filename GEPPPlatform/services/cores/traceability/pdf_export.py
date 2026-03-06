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
PRIMARY = colors.HexColor("#54937a")
padding = 0.50 * inch

# Card row: (header_text, icon_filename). Value row comes from data["card_values"][i] or "-"
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
    candidates = [
        ("IBMPlexSansThai-Bold",   ["scripts/IBMPlexSansThai-Bold.ttf",   "/opt/fonts/IBMPlexSansThai-Bold.ttf",   "IBMPlexSansThai-Bold.ttf"]),
        ("IBMPlexSansThai-Regular",["scripts/IBMPlexSansThai-Regular.ttf","/opt/fonts/IBMPlexSansThai-Regular.ttf","IBMPlexSansThai-Regular.ttf"]),
        ("IBMPlexSansThai-Medium", ["scripts/IBMPlexSansThai-Medium.ttf", "/opt/fonts/IBMPlexSansThai-Medium.ttf", "IBMPlexSansThai-Medium.ttf"]),
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
    header_text = "เส้นทางของเสียและวัสดุรีไซเคิล"
    location_data = data.get("location")
    if location_data is None:
        location_text = "ทั้งหมด"
    elif isinstance(location_data, list):
        location_text = ", ".join(map(str, location_data)) if location_data else "ทั้งหมด"
    else:
        location_text = str(location_data) if location_data else "ทั้งหมด"
    date_from = data.get("date_from") or ""
    date_to = data.get("date_to") or ""
    if date_from and date_to:
        date_text = f"{date_from} - {date_to}"
    elif date_from:
        date_text = date_from
    elif date_to:
        date_text = date_to
    else:
        date_text = "ทั้งหมด"
    pdf.setFillColor(PRIMARY)
    pdf.setFont("IBMPlexSansThai-Bold", 42)
    pdf.drawString(padding, page_height_points - (1.08 * inch), header_text)
    pdf.setFont("IBMPlexSansThai-Regular", 12)
    pdf.setFillColor(colors.HexColor("#656565"))
    pdf.drawString(padding, page_height_points - (1.35 * inch), f"สถานที่: {_safe(location_text)}")
    pdf.drawString(padding, page_height_points - (1.56 * inch), f"วันที่: {_safe(date_text)}")


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
    for i in range(4):
        x = padding + i * (card_width + gap)
        pdf.setFillColor(fill_color)
        pdf.setStrokeColor(stroke_color)
        pdf.setLineWidth(1)
        pdf.roundRect(x, row_top_y, card_width, card_height, radius)
        # Icon on the left (centered vertically in card)
        icon_y = row_top_y + (card_height - icon_size) / 2
        icon_path = _asset_path(CARD_CONFIG[i][1])
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
        pdf.drawString(text_x, header_y, _safe(CARD_CONFIG[i][0]))
        pdf.setFont("IBMPlexSansThai-Bold", 16)
        pdf.setFillColor(PRIMARY)
        pdf.drawString(text_x, value_y, _fmt_num(card_values[i]) + " กก.")
    return row_top_y - (0.25 * inch)


# Layout constants for flow chart (used for pagination and drawing)
_FLOW_ROW_H = 0.85 * inch
_FLOW_ROW_GAP = 0.38 * inch
_FLOW_INNER_PAD = 0.4 * inch


def _flow_content_height(n_rows: int) -> float:
    """Total vertical content height for n flow chart rows."""
    if n_rows <= 0:
        return 0.0
    return n_rows * _FLOW_ROW_H + (n_rows - 1) * _FLOW_ROW_GAP


def _rows_that_fit_in_box(box_height: float) -> int:
    """Max number of rows that fit in the diagram box (with inner padding)."""
    available = box_height - 2 * _FLOW_INNER_PAD
    if available <= 0:
        return 1
    n = int((available + _FLOW_ROW_GAP) / (_FLOW_ROW_H + _FLOW_ROW_GAP))
    return max(1, n)


def _build_flow_chart_pages(groups: list, n_rows: int, rows_per_page: int) -> list:
    """
    Split flow chart rows across pages. Can split within an origin (same origin redrawn on next page).
    Returns list of pages; each page is dict: global_indices (list of row indices), page_groups (list of list of indices into that page).
    """
    if n_rows <= 0 or rows_per_page <= 0:
        return []
    # Which group each global row belongs to
    group_of_row = [None] * n_rows
    for gi, g in enumerate(groups):
        for global_idx in g:
            group_of_row[global_idx] = gi
    pages = []
    row_start = 0
    while row_start < n_rows:
        row_end = min(row_start + rows_per_page, n_rows)
        page_global_indices = list(range(row_start, row_end))
        # Split this page's rows by group (contiguous segments)
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


def _build_chart_rows(hierarchy_data: list):
    """Build flat rows and origin-groups from hierarchy data for the flow chart.
    Returns (rows, groups) where rows is a flat list of dicts and groups is a list of lists of indices (grouped by origin).
    """
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
            rows.append({
                "origin": origin_node.get("origin") or {"display_name": origin_node.get("name", "-")},
                "origin_id": origin_node.get("origin_id"),
                "origin_weight": origin_node.get("weight", 0),
                "material": group_node.get("material") or {},
                "weight": group_node.get("weight") or group_node.get("total_weight_kg") or 0,
                "is_managed": _all_leaves_managed(group_node.get("children") or []),
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
) -> None:
    """
    Draw flowchart inside the box: Origin | Group/Material | In Transit | Status.
    records: flat list of dicts from _build_chart_rows (origin, material, weight, is_managed).
    groups_override: list of lists of indices grouped by origin.
    """
    if not records:
        try:
            pdf.setFont("IBMPlexSansThai-Regular", 10)
        except Exception:
            pdf.setFont("Helvetica", 10)
        pdf.setFillColor(colors.HexColor("#656565"))
        pdf.drawString(box_left + 0.2 * inch, box_bottom + box_height / 2 - 0.05 * inch, "ไม่มีข้อมูล")
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
    row_h = _FLOW_ROW_H
    node_h = row_h - 0.08 * inch
    origin_extra_h = 0.40 * inch
    origin_h = node_h + origin_extra_h
    total_content_h = n * row_h + (n - 1) * row_gap if n > 1 else row_h
    content_bottom = box_bottom + (box_height - total_content_h) / 2
    y_start = content_bottom + (n - 1) * (row_h + row_gap)
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
        row_ys = [y_start - i * (row_h + row_gap) for i in group]
        mid_ys = [row_y + node_h / 2 for row_y in row_ys]
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
        weight_label = f"Total quantity  {_fmt_num(total_weight)} kg"
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
                mat_name = _safe(mat.get("name_th") or mat.get("name_en") or "-")
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
            pdf.drawString(cx1 + accent_w + 0.12 * inch, row_y + node_h / 2 - 0.04 * inch, mat_name[:20])
            # Weight pill upper-right
            pill_text = f"{_fmt_num(w)} kg"
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

            # --- Column 2: In Transit (smaller rectangle) ---
            transit_h = node_h * 0.5
            transit_y = row_y + (node_h - transit_h) / 2
            pdf.setFillColor(fill_white)
            pdf.setStrokeColor(stroke_orange)
            pdf.setLineWidth(0.5)
            pdf.roundRect(cx2, transit_y, col_w_rest, transit_h, node_radius)
            pdf.setFillColor(stroke_orange)
            try:
                pdf.setFont("IBMPlexSansThai-Bold", 7)
            except Exception:
                pdf.setFont("Helvetica-Bold", 7)
            transit_label = "In Transit"
            try:
                tw = pdf.stringWidth(transit_label, "IBMPlexSansThai-Bold", 7)
            except Exception:
                tw = pdf.stringWidth(transit_label, "Helvetica-Bold", 7)
            pdf.drawString(cx2 + (col_w_rest - tw) / 2, transit_y + transit_h / 2 - 0.04 * inch, transit_label)

            # --- Column 3: Status (same size as transit node) ---
            status_h = transit_h
            status_y = row_y + (node_h - status_h) / 2
            status_border = colors.HexColor("#a4e1af")
            status_text_color = colors.HexColor("#7bbfa5")
            if is_managed:
                pdf.setFillColor(fill_white)
                pdf.setStrokeColor(status_border)
                pdf.setLineWidth(0.5)
                pdf.roundRect(cx3, status_y, col_w_rest, status_h, node_radius)
                # Icon on the left, text on the right
                status_icon_sz = status_h * 0.6
                status_icon_x = cx3 + 0.08 * inch
                status_icon_y = status_y + (status_h - status_icon_sz) / 2
                if os.path.exists(recycle_path):
                    try:
                        pdf.drawImage(recycle_path, status_icon_x, status_icon_y, width=status_icon_sz, height=status_icon_sz, mask="auto")
                    except Exception:
                        pass
                pdf.setFillColor(status_text_color)
                try:
                    pdf.setFont("IBMPlexSansThai-Bold", 7)
                except Exception:
                    pdf.setFont("Helvetica-Bold", 7)
                pdf.drawString(status_icon_x + status_icon_sz + 0.06 * inch, status_y + status_h / 2 - 0.04 * inch, "Done Managing")
            else:
                pdf.setDash(3, 3)
                pdf.setFillColor(fill_white)
                pdf.setStrokeColor(status_border)
                pdf.setLineWidth(0.5)
                pdf.roundRect(cx3, status_y, col_w_rest, status_h, node_radius)
                pdf.setDash()
                pdf.setFillColor(status_text_color)
                try:
                    pdf.setFont("IBMPlexSansThai-Regular", 7)
                except Exception:
                    pdf.setFont("Helvetica", 7)
                status_label = "Waiting for Management"
                try:
                    sw = pdf.stringWidth(status_label, "IBMPlexSansThai-Regular", 7)
                except Exception:
                    sw = pdf.stringWidth(status_label, "Helvetica", 7)
                pdf.drawString(cx3 + (col_w_rest - sw) / 2, status_y + status_h / 2 - 0.04 * inch, status_label)

            # --- Connector lines: Material -> In Transit -> Status ---
            pdf.setStrokeColor(stroke_green)
            pdf.setLineWidth(0.8)
            pdf.line(x_end1, mid_y, x_start2, mid_y)
            if is_managed:
                pdf.line(x_end2, mid_y, x_start3, mid_y)
            else:
                pdf.setStrokeColor(stroke_grey)
                pdf.setDash(3, 3)
                pdf.line(x_end2, mid_y, x_start3, mid_y)
                pdf.setDash()


# Item details table: full hierarchy tree
TABLE_HEADER_BG = colors.HexColor("#ededed")
TABLE_ROW_WHITE = colors.white
TABLE_ROW_ALT = colors.HexColor("#f9f9f9")
TABLE_ROW_HEIGHT = 0.32 * inch
TABLE_TITLE_GAP = 0.2 * inch
TABLE_CORNER_RADIUS = 0.08 * inch
TABLE_HEADERS = ["Material Type", "Weight kg.", "Origin", "Destination", "Delivered By", "Disposal method", "Status"]
TABLE_COL_RATIOS = [3.0, 0.8, 1.8, 1.5, 1.5, 1.8, 0.8]
_STATUS_PILLS = {
    "completed": (colors.HexColor("#d4edda"), colors.HexColor("#155724"), "Completed"),
    "in_transit": (colors.HexColor("#cce5ff"), colors.HexColor("#004085"), "In transit"),
    "idle":       (colors.HexColor("#e2e3e5"), colors.HexColor("#383d41"), "Idle"),
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


def _flatten_hierarchy_for_table(hierarchy_data: list) -> list:
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
            mat_name = _safe(mat.get("name_th") or mat.get("name_en") or "-") if isinstance(mat, dict) else _safe(mat)
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
                        "disposal_method": t.get("disposal_method") or "-",
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
    flat_rows = _flatten_hierarchy_for_table(hierarchy_data)
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
        pdf.drawString(table_left, y, "รายละเอียดรายการ")
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
        for i, h in enumerate(TABLE_HEADERS):
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
        pill_info = _STATUS_PILLS.get(status_key)
        if pill_info:
            pill_bg, pill_fg, pill_label = pill_info
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
    section_title = "แผนภาพเส้นทางของเสียและวัสดุรีไซเคิล"
    section_gap = 0.3 * inch
    radius = 0.12 * inch
    box_left = padding
    box_width = page_width_points - 2 * padding
    hierarchy_data = data.get("hierarchy") or []
    records, origin_groups = _build_chart_rows(hierarchy_data)

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
        _draw_flow_chart(pdf, box_left, box_bottom, box_width, box_height, [])
        return (box_bottom, records)

    original_indices = list(range(len(records)))
    n_rows = len(records)
    header_y_first = y_below_cards - 0.15 * inch
    box_top_first = header_y_first - section_gap
    box_bottom_first = padding
    box_height_first = box_top_first - box_bottom_first
    rows_per_page = _rows_that_fit_in_box(box_height_first)
    pages = _build_flow_chart_pages(origin_groups, n_rows, rows_per_page)
    last_box_bottom = box_bottom_first

    for page_idx, page_info in enumerate(pages):
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
            n_page_rows = len(page_info["global_indices"])
            content_h = _flow_content_height(n_page_rows)
            box_height_page = content_h + 2 * _FLOW_INNER_PAD
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
            n_page_rows = len(page_info["global_indices"])
            content_h = _flow_content_height(n_page_rows)
            box_height = content_h + 2 * _FLOW_INNER_PAD
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
        )

    return (last_box_bottom, records)


_DIVERTED_METHODS = {
    "Preparation for reuse", "Recycling (Own)", "Other recover operation", "Recycle",
}
_DIRECTED_METHODS = {
    "Composted by municipality", "Municipality receive",
    "Incineration without energy", "Incineration with energy",
}


def _compute_card_values_from_hierarchy(hierarchy_data: list, summary: dict) -> list:
    """Compute [total_waste, total_managed, diverted, directed] from leaf transports in the hierarchy."""
    total_waste = summary.get("total_waste_weight", 0) if isinstance(summary, dict) else 0
    diverted = 0.0
    directed = 0.0

    def _walk_leaves(transports):
        nonlocal diverted, directed
        for t in transports:
            if not isinstance(t, dict):
                continue
            children = t.get("children") or []
            if children:
                _walk_leaves(children)
            else:
                method = t.get("disposal_method") or ""
                w = float(t.get("weight") or 0)
                if method in _DIVERTED_METHODS:
                    diverted += w
                elif method in _DIRECTED_METHODS:
                    directed += w

    for origin_node in hierarchy_data:
        if not isinstance(origin_node, dict):
            continue
        for group_node in origin_node.get("children") or []:
            if not isinstance(group_node, dict):
                continue
            _walk_leaves(group_node.get("children") or [])

    total_managed = diverted + directed
    return [total_waste, total_managed, diverted, directed]


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
    summary = data.get("summary") or {}
    data["card_values"] = _compute_card_values_from_hierarchy(hierarchy, summary)
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
