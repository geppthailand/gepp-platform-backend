from io import BytesIO
import os
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas


PAGE_WIDTH_IN = 11.69
PAGE_HEIGHT_IN = 8.27
MARGIN_IN = 0.75

# Color constants
TEXT = colors.HexColor("#5b6e8c")

BASE_DIR = os.path.dirname(__file__)
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
LEAF_COVER_PATH = os.path.join(ASSETS_DIR, "LeafCover.png")
GEPP_LOGO_PATH = os.path.join(ASSETS_DIR, "GeppLogo.png")
GEPP_LOGO_OUTRO_PATH = os.path.join(ASSETS_DIR, "GeppLogoOutro.png")
TEL_ICON_PATH = os.path.join(ASSETS_DIR, "Tel.png")
EMAIL_ICON_PATH = os.path.join(ASSETS_DIR, "Email.png")
WEBSITE_ICON_PATH = os.path.join(ASSETS_DIR, "Website.png")
FACEBOOK_ICON_PATH = os.path.join(ASSETS_DIR, "Facebook.png")


def _register_fonts() -> None:
    """
    Register IBM Plex Sans Thai fonts from assets/fonts folder.
    If not found, silently continue (ReportLab will use default fonts).
    """
    font_files = {
        "IBMPlexSansThai-Bold": "IBMPlexSansThai-Bold.ttf",
        "IBMPlexSansThai-Regular": "IBMPlexSansThai-Regular.ttf",
        "IBMPlexSansThai-Medium": "IBMPlexSansThai-Medium.ttf",
        "IBMPlexSansThai-Light": "IBMPlexSansThai-Light.ttf",
        "IBMPlexSansThai-ExtraLight": "IBMPlexSansThai-ExtraLight.ttf",
        "IBMPlexSansThai-Thin": "IBMPlexSansThai-Thin.ttf",
        "IBMPlexSansThai-SemiBold": "IBMPlexSansThai-SemiBold.ttf",
    }
    
    for family, filename in font_files.items():
        font_path = os.path.join(FONTS_DIR, filename)
        try:
            if os.path.exists(font_path):
                pdfmetrics.registerFont(TTFont(family, font_path))
        except Exception:
            # If registration fails, continue silently
            continue


def _get_font_name(preferred: str, fallback: str) -> str:
    """Return preferred font if registered, otherwise a safe fallback."""
    try:
        pdfmetrics.getFont(preferred)
        return preferred
    except Exception:
        return fallback

def _footer(pdf: canvas.Canvas, page_width_points: float) -> None:
    """Draw footer on every page with copyright text."""
    text = "Copyright © 2018–2023 GEPP Sa-Ard Co., Ltd. ALL RIGHTS RESERVED"
    pdf.setFillColor(TEXT)
    # Try Poppins-Regular, fallback to Helvetica
    font_name = _get_font_name("Poppins-Regular", "Helvetica")
    pdf.setFont(font_name, 9)
    tw = stringWidth(text, font_name, 9)
    pdf.drawString((page_width_points - tw) / 2, 0.25 * inch, text)

def _footer(pdf: canvas.Canvas, page_width_points: float) -> None:
    """Draw footer on every page with copyright text."""
    text = "Copyright © 2018–2023 GEPP Sa-Ard Co., Ltd. ALL RIGHTS RESERVED"
    pdf.setFillColor(TEXT)
    # Try Poppins-Regular, fallback to Helvetica
    font_name = _get_font_name("Poppins-Regular", "Helvetica")
    pdf.setFont(font_name, 9)
    tw = stringWidth(text, font_name, 9)
    pdf.drawString((page_width_points - tw) / 2, 0.25 * inch, text)

def _draw_cover_page(pdf: canvas.Canvas, data: dict) -> None:
    """
    Draw the cover page to visually match the provided design:
    - Title top-left
    - Subtitle below
    - Leaf illustration centered
    - GEPP logo bottom-right
    """
    width_points = PAGE_WIDTH_IN * inch
    height_points = PAGE_HEIGHT_IN * inch
    margin_points = MARGIN_IN * inch

    # Extract year if available
    year = (
        data.get("year")
        or data.get("data", {}).get("data", {}).get("year")
        or ""
    )

    # Fonts - use IBM Plex Sans Thai from assets/fonts
    title_font = _get_font_name("IBMPlexSansThai-Medium", "Helvetica-Bold")
    subtitle_font = _get_font_name("IBMPlexSansThai-Light", "Helvetica")

    # Colors
    dark_green = colors.HexColor("#52947a")

    # Title
    title_text = f"GRI REPORT {year}" if year else "GRI REPORT"
    subtitle_text = "| Sustainability & Annual Progress"

    pdf.setFillColor(dark_green)

    pdf.setFont(title_font, 30)
    title_x = margin_points
    title_y = height_points - (margin_points * 1.1)
    pdf.drawString(title_x, title_y, title_text)

    # Subtitle slightly below title
    pdf.setFont(subtitle_font, 16.5)
    subtitle_y = title_y - (0.4 * inch)
    pdf.drawString(title_x, subtitle_y, subtitle_text)

    # Draw leaf cover image centered
    if os.path.exists(LEAF_COVER_PATH):
        try:
            # Read image to get aspect ratio
            img = ImageReader(LEAF_COVER_PATH)
            img_width, img_height = img.getSize()
            if img_width and img_height:
                aspect = float(img_height) / float(img_width)
            else:
                aspect = 1.0

            # Stretch from left-most across the page, maintain aspect ratio
            target_leaf_width = width_points
            target_leaf_height = target_leaf_width * aspect

            leaf_x = 0  # left-most
            leaf_y = (height_points - target_leaf_height) / 2.0

            pdf.drawImage(
                img,
                leaf_x,
                leaf_y,
                width=target_leaf_width,
                height=target_leaf_height,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            # If anything goes wrong, we silently skip the image
            pass

    # Draw GEPP logo at bottom-right
    if os.path.exists(GEPP_LOGO_PATH):
        logo_width = 1.0 * inch
        logo_height = 1.0 * inch
        logo_x = width_points - margin_points - logo_width
        logo_y = margin_points - (0.15 * inch)  # nudge slightly towards edge

        try:
            pdf.drawImage(
                GEPP_LOGO_PATH,
                logo_x,
                logo_y,
                width=logo_width,
                height=logo_height,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass


def _draw_outro_cover_page(pdf: canvas.Canvas, data: dict) -> None:
    """
    Draw the outro cover page with:
    - GEPP logo (smaller, positioned upper)
    - "Thank you" text
    - "for your continued support." text
    - Contact information with icons at the bottom
    """
    width_points = PAGE_WIDTH_IN * inch
    height_points = PAGE_HEIGHT_IN * inch
    margin_points = MARGIN_IN * inch

    # Fonts
    title_font = _get_font_name("IBMPlexSansThai-Bold", "Helvetica-Bold")
    body_font = _get_font_name("IBMPlexSansThai-Regular", "Helvetica")
    
    # Colors
    dark_green = colors.HexColor("#52947a")
    dark_gray = colors.HexColor("#616161")

    # Draw GEPP outro logo (smaller, positioned upper)
    logo_width = 1.5 * inch  # Smaller logo
    logo_height = logo_width  # Default, will be updated if image exists
    logo_y_top = height_points * 0.7  # Position top of logo at 70% from bottom (upper area)
    
    if os.path.exists(GEPP_LOGO_OUTRO_PATH):
        try:
            # Read image to get aspect ratio
            img = ImageReader(GEPP_LOGO_OUTRO_PATH)
            img_width, img_height = img.getSize()
            if img_width and img_height:
                aspect = float(img_height) / float(img_width)
            else:
                aspect = 1.0

            logo_height = logo_width * aspect
            logo_x = (width_points - logo_width) / 2.0
            logo_y = logo_y_top - logo_height  # Position from top

            pdf.drawImage(
                img,
                logo_x,
                logo_y,
                width=logo_width,
                height=logo_height,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            # If anything goes wrong, we silently skip the image
            pass

    # "Thank you" text (large, bold, dark green) - below logo
    thank_you_y = logo_y_top - logo_height - (0.9 * inch)
    pdf.setFillColor(dark_green)
    pdf.setFont(title_font, 48)
    thank_you_text = "Thank you"
    thank_you_width = pdf.stringWidth(thank_you_text, title_font, 48)
    thank_you_x = (width_points - thank_you_width) / 2.0
    pdf.drawString(thank_you_x, thank_you_y, thank_you_text)

    # "for your continued support." text (smaller, dark gray) - below "Thank you"
    support_text = "for your continued support."
    pdf.setFillColor(dark_gray)
    pdf.setFont(body_font, 22)
    support_width = pdf.stringWidth(support_text, body_font, 22)
    support_x = (width_points - support_width) / 2.0
    support_y = thank_you_y - (0.6 * inch)
    pdf.drawString(support_x, support_y, support_text)

    # Contact information section at the bottom
    contact_section_y = margin_points * 2.5
    icon_size = 0.5 * inch
    icon_text_gap = 0.15 * inch  # Gap between icon and text
    contact_items = [
        {"icon": TEL_ICON_PATH, "text": "+66 64 043 7166"},
        {"icon": EMAIL_ICON_PATH, "text": "hell@gepp.me"},
        {"icon": WEBSITE_ICON_PATH, "text": "hell@gepp.me"},
        {"icon": FACEBOOK_ICON_PATH, "text": "facebook.com/geppthailand"},
    ]
    
    # Calculate evenly spaced positions for contact items
    # Each item consists of icon + gap + text
    # We need to estimate item widths for better spacing
    pdf.setFont(body_font, 10)
    item_widths = []
    for item in contact_items:
        text_width = pdf.stringWidth(item["text"], body_font, 10)
        item_width = icon_size + icon_text_gap + text_width
        item_widths.append(item_width)
    
    total_items_width = sum(item_widths)
    available_width = width_points - (margin_points * 2)
    # Reduced fixed spacing between items
    spacing_between_items = 0.4 * inch
    
    # Start position (centered)
    total_spacing_width = spacing_between_items * (len(contact_items) - 1)
    total_group_width = total_items_width + total_spacing_width
    start_x = margin_points + (available_width - total_group_width) / 2.0
    current_x = start_x
    
    for idx, item in enumerate(contact_items):
        # Draw icon
        icon_y = contact_section_y  # Align icon bottom with text baseline
        if os.path.exists(item["icon"]):
            try:
                icon_img = ImageReader(item["icon"])
                pdf.drawImage(
                    icon_img,
                    current_x,
                    icon_y,
                    width=icon_size,
                    height=icon_size,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            except Exception:
                pass
        
        # Draw text to the right of icon
        text_x = current_x + icon_size + icon_text_gap
        text_y = contact_section_y + (icon_size / 2.0) - 3  # Center vertically with icon
        pdf.setFillColor(dark_gray)
        pdf.setFont(body_font, 10)
        pdf.drawString(text_x, text_y, item["text"])
        
        # Move to next item position
        current_x += item_widths[idx] + spacing_between_items


def _draw_page_header(pdf: canvas.Canvas, year: str, width_points: float, height_points: float, margin_points: float) -> None:
    """Draw the page header with rounded box, title and subtitle"""
    # Fonts
    title_font = _get_font_name("IBMPlexSansThai-Bold", "Helvetica-Bold")
    subtitle_font = _get_font_name("IBMPlexSansThai-Light", "Helvetica")
    
    # Colors
    dark_green = colors.HexColor("#52947a")
    
    # Rounded Box
    title_x = margin_points + 12
    title_y = height_points - (margin_points * 1.5)
    subtitle_y = title_y - (0.35 * inch)
    pdf.setFillColor(colors.HexColor("#e3f2ec"))
    pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
    pdf.setLineWidth(1)
    pdf.roundRect(title_x - 12, subtitle_y - 0.2 * inch, width_points - margin_points * 2, 1.08*inch, 12, fill=1, stroke=1)
    
    # Title
    pdf.setFillColor(dark_green)
    pdf.setFont(title_font, 32)
    title_text = "Full Disclosure Report"
    pdf.drawString(title_x, title_y, title_text)
    
    # Subtitle
    pdf.setFillColor(dark_green)
    pdf.setFont(subtitle_font, 14)
    # Format date range - assuming full year
    if year:
        subtitle_text = f"All Location • Jan 1 - Dec 31, {year}"
    else:
        subtitle_text = "All Location • Jan 1 - Dec 31, 2024"
    pdf.drawString(title_x, subtitle_y, subtitle_text)


def _draw_table_rows(
    pdf: canvas.Canvas,
    page_categories: list,
    start_row_num: int,
    row_start_y_pos: float,
    row_height: float,
    margin_points: float,
    width_points: float,
    table_title_x: float,
    dark_green,
    light_green,
    card_font: str,
    table_header_font: str,
    totals: dict = None,
    is_last_page: bool = False,
    is_first_row_on_page: bool = False
) -> None:
    """Draw table rows for a given page"""
    row_start_y = row_start_y_pos
    
    # Font for table rows
    pdf.setFillColor(dark_green)
    pdf.setFont(card_font, 11)
    
    # Draw data rows
    for idx, category in enumerate(page_categories):
        row_num = start_row_num + idx
        row_y = row_start_y - idx * row_height
        # Last data row if it's the last in the list (whether or not totals follows)
        is_last_data_row = (idx == len(page_categories) - 1)
        # First row on page (for subsequent pages, no top border)
        is_first_row = (idx == 0) and is_first_row_on_page
        
        # Draw row border
        pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
        pdf.setLineWidth(0.5)
        if is_last_data_row and not is_first_row:
            # Draw only top and sides (no bottom)
            pdf.line(margin_points, row_y, margin_points + (width_points - margin_points * 2), row_y)  # Top
            pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
            pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                    margin_points + (width_points - margin_points * 2), row_y)  # Right
        elif is_first_row:
            # Draw only sides and bottom (no top border)
            pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
            pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                    margin_points + (width_points - margin_points * 2), row_y)  # Right
            pdf.line(margin_points, row_y - row_height, margin_points + (width_points - margin_points * 2), row_y - row_height)  # Bottom
        elif is_last_data_row and is_first_row:
            # First and last row (only one row) - only sides, no top or bottom
            pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
            pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                    margin_points + (width_points - margin_points * 2), row_y)  # Right
        else:
            # Draw full border
            pdf.rect(margin_points, row_y - row_height, width_points - margin_points * 2, row_height, fill=0, stroke=1)
        
        # Row data
        pdf.setFillColor(dark_green)
        text_y = row_y - (row_height / 2) - 3  # Center vertically
        
        # Draw row number
        pdf.drawString(table_title_x, text_y, str(row_num))
        
        # Draw category name
        category_name = category.get("category_name", "")
        pdf.drawString(table_title_x + 0.4 * inch, text_y, category_name)
        
        # Draw generated value
        generated = category.get("generated", 0.0)
        pdf.drawString(table_title_x + 5 * inch, text_y, f"{generated:,.2f}")
        
        # Draw diverted value
        diverted = category.get("diverted", 0.0)
        pdf.drawString(table_title_x + 6.9 * inch, text_y, f"{diverted:,.2f}")
        
        # Draw directed value
        directed = category.get("directed", 0.0)
        pdf.drawString(table_title_x + 8.8 * inch, text_y, f"{directed:,.2f}")
    
    # Draw totals row only on the last page
    if is_last_page and totals:
        total_row_y = row_start_y - len(page_categories) * row_height
        
        # Draw border - same style as regular rows, exclude bottom border
        pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
        pdf.setLineWidth(0.5)
        # Draw only top and sides (no bottom)
        pdf.line(margin_points, total_row_y, margin_points + (width_points - margin_points * 2), total_row_y)  # Top
        pdf.line(margin_points, total_row_y - row_height, margin_points, total_row_y)  # Left
        pdf.line(margin_points + (width_points - margin_points * 2), total_row_y - row_height, 
                margin_points + (width_points - margin_points * 2), total_row_y)  # Right
        
        # Totals data - same font and color as regular rows
        pdf.setFillColor(dark_green)
        pdf.setFont(_get_font_name("IBMPlexSansThai-SemiBold", "Helvetica-Bold"), 11)
        text_y = total_row_y - (row_height / 2) - 3
        
        # Draw "Total" label - aligned with row number column
        pdf.drawString(table_title_x, text_y, "Total")
        
        # Draw total generated
        total_generated = totals.get("generated", 0.0)
        pdf.drawString(table_title_x + 5 * inch, text_y, f"{total_generated:,.2f}")
        
        # Draw total diverted
        total_diverted = totals.get("diverted", 0.0)
        pdf.drawString(table_title_x + 6.9 * inch, text_y, f"{total_diverted:,.2f}")
        
        # Draw total directed
        total_directed = totals.get("directed", 0.0)
        pdf.drawString(table_title_x + 8.8 * inch, text_y, f"{total_directed:,.2f}")


def _draw_full_disclosure_page(pdf: canvas.Canvas, data: dict) -> None:
    """
    Draw the Full Disclosure Report page with:
    - Title and subtitle
    - Four summary cards (Waste Generated, Diverted, Directed, Total Spills)
    - Waste composition table
    """
    width_points = PAGE_WIDTH_IN * inch
    height_points = PAGE_HEIGHT_IN * inch
    margin_points = MARGIN_IN * inch

    # Extract data
    report_data = data.get("data", {}).get("data", {}) or data.get("data", {}) or data
    year = report_data.get("year", "")
    table_summary = report_data.get("table_summary", {})
    waste_composition = report_data.get("waste_composition", {})
    
    # Fonts
    title_font = _get_font_name("IBMPlexSansThai-Bold", "Helvetica-Bold")
    subtitle_font = _get_font_name("IBMPlexSansThai-Light", "Helvetica")
    card_font = _get_font_name("IBMPlexSansThai-Light", "Helvetica-Bold")
    table_title_font = _get_font_name("IBMPlexSansThai-Bold", "Helvetica-Bold")
    table_header_font = _get_font_name("IBMPlexSansThai-SemiBold", "Helvetica-Bold")
    
    # Colors - All colors defined here
    dark_green = colors.HexColor("#52947a")
    light_green = colors.HexColor("#b7d7c8")
    badge_pill_bg = colors.HexColor("#e7f2f1")

    # Draw page header
    _draw_page_header(pdf, year, width_points, height_points, margin_points)
    
    # Calculate subtitle_y for positioning cards
    title_x = margin_points + 12
    title_y = height_points - (margin_points * 1.5)
    subtitle_y = title_y - (0.35 * inch)
    
    # Summary Cards
    card_start_y = subtitle_y - (0.65 * inch)
    card_height = 2 * inch
    card_width = (width_points - (margin_points * 2) - (0.3 * inch * 3)) / 4  # 4 cards with 3 gaps
    card_gap = 0.3 * inch
    
    cards = [
        {
            "label": "Waste Generated",
            "value": table_summary.get("waste_generated", 0.0),
            "unit": "t",
            "table_tag": "Table 1"
        },
        {
            "label": "Diverted",
            "value": table_summary.get("diverted_from_disposal", 0.0),
            "unit": "t",
            "table_tag": "Table 2"
        },
        {
            "label": "Directed",
            "value": table_summary.get("directed_to_disposal", 0.0),
            "unit": "t",
            "table_tag": "Table 3"
        },
        {
            "label": "Total Spills",
            "value": table_summary.get("total_spills", 0.0),
            "unit": "Liters",
            "table_tag": "Table 4"
        }
    ]
    
    for i, card in enumerate(cards):
        card_x = margin_points + (i * (card_width + card_gap))
        card_y = card_start_y - card_height
        
        # Draw card background
        pdf.setFillColor(colors.HexColor("#ffffff"))
        pdf.setStrokeColor(light_green)
        pdf.setLineWidth(1)
        pdf.roundRect(card_x, card_y, card_width, card_height, 12, fill=1, stroke=1)
        
        # Draw circular icon (simplified as a circle)
        icon_size = 0.4 * inch
        icon_x = card_x + 0.2 * inch
        icon_y = card_y + card_height - 0.6 * inch
        pdf.setFillColor(light_green)
        pdf.circle(icon_x + icon_size/2, icon_y + icon_size/2, icon_size/2, fill=1)
        
        # Table tag with badge pill background
        pdf.setFont(subtitle_font, 6)
        tag_text = card["table_tag"]
        tag_text_width = pdf.stringWidth(tag_text, subtitle_font, 6)
        tag_padding_x = 0.1 * inch
        tag_bg_width = tag_text_width + (tag_padding_x * 2)
        tag_bg_height = 0.2 * inch
        tag_x = card_x + card_width - tag_bg_width - 0.2 * inch
        tag_y = card_y + card_height - 0.4 * inch
        
        # Draw badge pill background
        pdf.setFillColor(badge_pill_bg)
        pdf.setStrokeColor(badge_pill_bg)
        pdf.roundRect(tag_x, tag_y, tag_bg_width, tag_bg_height, tag_bg_height / 2, fill=1, stroke=0)
        
        # Draw tag text
        pdf.setFillColor(dark_green)
        text_x = tag_x + tag_padding_x
        text_y = tag_y + (tag_bg_height / 2) - 3  # Center vertically
        pdf.drawString(text_x, text_y + 1, tag_text)
        
        # Card label
        pdf.setFillColor(dark_green)
        pdf.setFont(card_font, 13)
        label_x = card_x + 0.2 * inch
        label_y = card_y + card_height - 0.9 * inch
        pdf.drawString(label_x, label_y, card["label"])
        
        # Card value - same x position as label, with more spacing
        pdf.setFillColor(dark_green)
        pdf.setFont(table_header_font, 18)
        value_text = f"{card['value']:.2f} {card['unit']}"
        value_x = label_x  # Same x position as label
        value_y = label_y - 0.4 * inch  # Increased spacing from bottom
        pdf.drawString(value_x, value_y, value_text)
    
    # Table
    table_start_y = 62
    table_height = 4 * inch - 82
    pdf.setFillColor(colors.HexColor("#ffffff"))
    pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
    pdf.setLineWidth(1)
    pdf.roundRect(margin_points, table_start_y, width_points - margin_points * 2, table_height, 12, fill=1, stroke=1)

    # Table title
    pdf.setFillColor(dark_green)
    pdf.setFont(table_title_font, 12)
    table_title_x = margin_points + 12 + 4
    table_title_y = table_height + table_start_y - 0.35 * inch
    table_title = "Table 1: Waste by composition"
    pdf.drawString(table_title_x, table_title_y, table_title)

    table_header_start_y = table_title_y - 0.5 * inch - 0.17 * inch
    pdf.setFillColor(colors.HexColor("#f3f3f3"))
    pdf.rect(margin_points, table_header_start_y, width_points - margin_points * 2, 0.4 * inch, fill=1, stroke=0)
    pdf.setFillColor(dark_green)
    pdf.setFont(card_font, 9)
    table_header_y = table_header_start_y + 0.16 * inch
    pdf.drawString(table_title_x, table_header_y, "#")
    pdf.drawString(table_title_x + 0.4 * inch, table_header_y, "Waste Composition")
    pdf.drawString(table_title_x + 5 * inch, table_header_y, "Generated (T)")
    pdf.drawString(table_title_x + 6.9 * inch, table_header_y, "Diverted (T)")
    pdf.drawString(table_title_x + 8.8 * inch, table_header_y, "Directed (T)")
    
    # Draw table rows with pagination
    categories = waste_composition.get("categories", [])
    totals = waste_composition.get("totals", {})
    row_height = 0.6 * inch
    
    # Pagination: First page max 3 rows, subsequent pages max 8 rows
    if len(categories) <= 3:
        # All rows fit on first page
        _draw_table_rows(
            pdf, categories, start_row_num=1, row_start_y_pos=table_header_start_y,
            row_height=row_height, margin_points=margin_points, width_points=width_points,
            table_title_x=table_title_x, dark_green=dark_green, light_green=light_green,
            card_font=card_font, table_header_font=table_header_font, totals=totals,
            is_last_page=True, is_first_row_on_page=False
        )
    else:
        # First page: 3 rows
        first_page_categories = categories[:3]
        _draw_table_rows(
            pdf, first_page_categories, start_row_num=1, row_start_y_pos=table_header_start_y,
            row_height=row_height, margin_points=margin_points, width_points=width_points,
            table_title_x=table_title_x, dark_green=dark_green, light_green=light_green,
            card_font=card_font, table_header_font=table_header_font, totals=None,
            is_last_page=False, is_first_row_on_page=False
        )
        
        # Remaining categories
        remaining_categories = categories[3:]
        
        # Process remaining in chunks of 8
        page_num = 2
        for i in range(0, len(remaining_categories), 8):
            chunk = remaining_categories[i:i+8]
            is_last_chunk = (i + 8 >= len(remaining_categories))
            
            # Calculate dynamic table height based on number of rows
            num_rows = len(chunk)
            # Add 1 row height if totals row will be shown
            if is_last_chunk and totals:
                num_rows += 1
            
            # Calculate dynamic table height
            dynamic_table_height = num_rows * row_height
            
            # Calculate table_start_y from top (with some margin from top)
            table_start_y_dynamic = height_points - margin_points - dynamic_table_height - 96
            
            # Add footer before creating new page
            _footer(pdf, width_points)
            # Create new page
            pdf.showPage()
            
            # Draw page header on new page
            _draw_page_header(pdf, year, width_points, height_points, margin_points)
            
            # Draw table container on new page with dynamic height
            pdf.setFillColor(colors.HexColor("#ffffff"))
            pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
            pdf.setLineWidth(1)
            pdf.roundRect(margin_points, table_start_y_dynamic, width_points - margin_points * 2, dynamic_table_height, 12, fill=1, stroke=1)
            
            # Calculate starting y position from top of table container
            # Start from top of table container (table_start_y + table_height)
            top_start_y = table_start_y_dynamic + dynamic_table_height
            
            # Draw rows for this page - start from the top
            start_row_num = 4 + i  # Continue numbering from where first page left off (3 rows + i)
            _draw_table_rows(
                pdf, chunk, start_row_num=start_row_num, row_start_y_pos=top_start_y,
                row_height=row_height, margin_points=margin_points, width_points=width_points,
                table_title_x=table_title_x, dark_green=dark_green, light_green=light_green,
                card_font=card_font, table_header_font=table_header_font, totals=totals if is_last_chunk else None,
                is_last_page=is_last_chunk, is_first_row_on_page=True
            )
            
            page_num += 1
    
    # Draw diverted data table on a new page
    diverted_data = report_data.get("diverted_data", {})
    if diverted_data:
        _draw_diverted_data_table(pdf, diverted_data, year, width_points, height_points, margin_points)
    
    # Draw directed data table on a new page
    directed_data = report_data.get("directed_data", {})
    if directed_data:
        _draw_directed_data_table(pdf, directed_data, year, width_points, height_points, margin_points)
    
    # Draw spill data table on a new page
    spill_data = report_data.get("spill_data", {})
    if spill_data:
        _draw_spill_data_table(pdf, spill_data, year, width_points, height_points, margin_points)


def _draw_diverted_data_table(pdf: canvas.Canvas, diverted_data: dict, year: str, width_points: float, height_points: float, margin_points: float) -> None:
    """Draw the diverted data table on a new page with pagination"""
    # Fonts
    table_title_font = _get_font_name("IBMPlexSansThai-Bold", "Helvetica-Bold")
    card_font = _get_font_name("IBMPlexSansThai-Light", "Helvetica-Bold")
    
    # Colors
    dark_green = colors.HexColor("#52947a")
    
    # Table dimensions
    row_height = 0.6 * inch
    header_row_height = 0.4 * inch  # Same as column header
    table_title_x = margin_points + 12 + 4
    
    # Prepare data rows (including section headers)
    hazardous_data = diverted_data.get("hazardous", {})
    non_hazardous_data = diverted_data.get("non_hazardous", {})
    methods = list(hazardous_data.keys()) if hazardous_data else list(non_hazardous_data.keys())
    
    # Build rows list with section headers
    all_rows = []
    data_row_num = 1
    
    if hazardous_data:
        all_rows.append({"type": "header", "label": "Hazardous"})
        hazardous_totals = {"onsite": 0.0, "offsite": 0.0, "total": 0.0}
        for method in methods:
            method_data = hazardous_data.get(method, {})
            all_rows.append({
                "type": "data",
                "num": data_row_num,
                "method": method,
                "data": method_data
            })
            # Accumulate totals
            hazardous_totals["onsite"] += method_data.get("onsite", 0.0)
            hazardous_totals["offsite"] += method_data.get("offsite", 0.0)
            hazardous_totals["total"] += method_data.get("total", 0.0)
            data_row_num += 1
        # Add total row for hazardous
        all_rows.append({
            "type": "total",
            "label": "Total",
            "data": hazardous_totals
        })
    
    if non_hazardous_data:
        all_rows.append({"type": "header", "label": "Non-Hazardous"})
        non_hazardous_totals = {"onsite": 0.0, "offsite": 0.0, "total": 0.0}
        for method in methods:
            method_data = non_hazardous_data.get(method, {})
            all_rows.append({
                "type": "data",
                "num": data_row_num,
                "method": method,
                "data": method_data
            })
            # Accumulate totals
            non_hazardous_totals["onsite"] += method_data.get("onsite", 0.0)
            non_hazardous_totals["offsite"] += method_data.get("offsite", 0.0)
            non_hazardous_totals["total"] += method_data.get("total", 0.0)
            data_row_num += 1
        # Add total row for non-hazardous
        all_rows.append({
            "type": "total",
            "label": "Total",
            "data": non_hazardous_totals
        })
    
    # Helper function to draw rows on a page
    def draw_diverted_rows(page_rows, row_start_y_pos, is_first_row_on_page=False):
        """Draw diverted data rows for a given page"""
        row_start_y = row_start_y_pos
        
        for idx, row in enumerate(page_rows):
            is_first_row = (idx == 0) and is_first_row_on_page
            
            # Calculate cumulative height of previous rows
            prev_height = sum(
                header_row_height if page_rows[i]["type"] == "header" 
                else row_height  # for both "data" and "total" types
                for i in range(idx)
            )
            
            if row["type"] == "header":
                # Section header row - same height as column header
                row_y = row_start_y - prev_height
                
                # Draw header row border
                pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
                pdf.setLineWidth(0.5)
                if is_first_row:
                    # Draw only sides and bottom (no top border)
                    pdf.line(margin_points, row_y - header_row_height, margin_points, row_y)  # Left
                    pdf.line(margin_points + (width_points - margin_points * 2), row_y - header_row_height, 
                            margin_points + (width_points - margin_points * 2), row_y)  # Right
                    pdf.line(margin_points, row_y - header_row_height, margin_points + (width_points - margin_points * 2), row_y - header_row_height)  # Bottom
                else:
                    pdf.rect(margin_points, row_y - header_row_height, width_points - margin_points * 2, header_row_height, fill=0, stroke=1)
                
                # Header row background
                pdf.setFillColor(colors.HexColor("#fafafa"))
                pdf.rect(margin_points, row_y - header_row_height, width_points - margin_points * 2, header_row_height, fill=1, stroke=0)
                
                pdf.setFillColor(dark_green)
                pdf.setFont(card_font, 9)
                text_y = row_y - (header_row_height / 2) - 3
                pdf.drawString(table_title_x + 0.4 * inch, text_y, row["label"])
            elif row["type"] == "total":
                # Total row - same styling as data rows
                row_y = row_start_y - prev_height
                is_last_row = (idx == len(page_rows) - 1)
                
                # Draw total row background
                pdf.setFillColor(colors.HexColor("#f5faf8"))
                pdf.rect(margin_points, row_y - row_height, width_points - margin_points * 2, row_height, fill=1, stroke=0)
                
                # Draw row border
                pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
                pdf.setLineWidth(0.5)
                if is_last_row:
                    # Draw only top and sides (no bottom)
                    pdf.line(margin_points, row_y, margin_points + (width_points - margin_points * 2), row_y)  # Top
                    pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
                    pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                            margin_points + (width_points - margin_points * 2), row_y)  # Right
                elif is_first_row:
                    # Draw only sides and bottom (no top border)
                    pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
                    pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                            margin_points + (width_points - margin_points * 2), row_y)  # Right
                    pdf.line(margin_points, row_y - row_height, margin_points + (width_points - margin_points * 2), row_y - row_height)  # Bottom
                else:
                    pdf.rect(margin_points, row_y - row_height, width_points - margin_points * 2, row_height, fill=0, stroke=1)
                
                # Total row data
                pdf.setFillColor(dark_green)
                pdf.setFont(card_font, 11)
                text_y = row_y - (row_height / 2) - 3
                
                pdf.drawString(table_title_x, text_y, "")  # Empty number column
                pdf.drawString(table_title_x + 0.4 * inch, text_y, row["label"])
                pdf.drawString(table_title_x + 5 * inch, text_y, f"{row['data'].get('onsite', 0.0):,.2f}")
                pdf.drawString(table_title_x + 6.9 * inch, text_y, f"{row['data'].get('offsite', 0.0):,.2f}")
                pdf.drawString(table_title_x + 8.8 * inch, text_y, f"{row['data'].get('total', 0.0):,.2f}")
            else:  # row["type"] == "data"
                # Data row
                row_y = row_start_y - prev_height
                is_last_row = (idx == len(page_rows) - 1)
                
                # Draw row border
                pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
                pdf.setLineWidth(0.5)
                if is_last_row:
                    # Draw only top and sides (no bottom)
                    pdf.line(margin_points, row_y, margin_points + (width_points - margin_points * 2), row_y)  # Top
                    pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
                    pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                            margin_points + (width_points - margin_points * 2), row_y)  # Right
                elif is_first_row:
                    # Draw only sides and bottom (no top border)
                    pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
                    pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                            margin_points + (width_points - margin_points * 2), row_y)  # Right
                    pdf.line(margin_points, row_y - row_height, margin_points + (width_points - margin_points * 2), row_y - row_height)  # Bottom
                else:
                    pdf.rect(margin_points, row_y - row_height, width_points - margin_points * 2, row_height, fill=0, stroke=1)
                
                # Row data
                pdf.setFillColor(dark_green)
                pdf.setFont(card_font, 11)
                text_y = row_y - (row_height / 2) - 3
                
                pdf.drawString(table_title_x, text_y, str(row["num"]))
                pdf.drawString(table_title_x + 0.4 * inch, text_y, row["method"])
                pdf.drawString(table_title_x + 5 * inch, text_y, f"{row['data'].get('onsite', 0.0):,.2f}")
                pdf.drawString(table_title_x + 6.9 * inch, text_y, f"{row['data'].get('offsite', 0.0):,.2f}")
                pdf.drawString(table_title_x + 8.8 * inch, text_y, f"{row['data'].get('total', 0.0):,.2f}")
    
    # Pagination: First page max 3 rows, subsequent pages max 8 rows
    if len(all_rows) <= 3:
        # All rows fit on first page
        _footer(pdf, width_points)
        pdf.showPage()
        _draw_page_header(pdf, year, width_points, height_points, margin_points)
        
        # Calculate dynamic table height
        total_height = sum(
            header_row_height if r["type"] == "header" 
            else row_height  # for both "data" and "total" types
            for r in all_rows
        ) - 26
        table_start_y_dynamic = height_points - margin_points - total_height - 0.4 * inch - 0.5 * inch - 0.17 * inch - 0.35 * inch - 96  # Account for title and header
        
        # Draw table container
        pdf.setFillColor(colors.HexColor("#ffffff"))
        pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
        pdf.setLineWidth(1)
        pdf.roundRect(margin_points, table_start_y_dynamic, width_points - margin_points * 2, total_height + 0.4 * inch + 0.5 * inch + 0.17 * inch + 0.35 * inch, 12, fill=1, stroke=1)
        
        # Table title
        pdf.setFillColor(dark_green)
        pdf.setFont(table_title_font, 12)
        table_title_y = table_start_y_dynamic + total_height + 0.4 * inch + 0.5 * inch + 0.17 * inch + 0.35 * inch - 0.35 * inch
        pdf.drawString(table_title_x, table_title_y, "Table 2: Diverted from Disposal")
        
        # Table header
        table_header_start_y = table_title_y - 0.5 * inch - 0.17 * inch
        pdf.setFillColor(colors.HexColor("#f3f3f3"))
        pdf.rect(margin_points, table_header_start_y, width_points - margin_points * 2, 0.4 * inch, fill=1, stroke=0)
        pdf.setFillColor(dark_green)
        pdf.setFont(card_font, 9)
        table_header_y = table_header_start_y + 0.16 * inch
        pdf.drawString(table_title_x, table_header_y, "#")
        pdf.drawString(table_title_x + 0.4 * inch, table_header_y, "Method")
        pdf.drawString(table_title_x + 5 * inch, table_header_y, "Onsite (T)")
        pdf.drawString(table_title_x + 6.9 * inch, table_header_y, "Offsite (T)")
        pdf.drawString(table_title_x + 8.8 * inch, table_header_y, "Total (T)")
        
        # Draw rows
        top_start_y = table_header_start_y
        draw_diverted_rows(all_rows, top_start_y, is_first_row_on_page=False)
    else:
        # First page: 3 rows
        first_page_rows = all_rows[:8]
        remaining_rows = all_rows[8:]
        
        # First page
        _footer(pdf, width_points)
        pdf.showPage()
        _draw_page_header(pdf, year, width_points, height_points, margin_points)
        
        # Calculate dynamic table height for first page
        total_height = sum(
            header_row_height if r["type"] == "header" 
            else row_height  # for both "data" and "total" types
            for r in first_page_rows
        ) - 26
        table_start_y_dynamic = height_points - margin_points - total_height - 0.4 * inch - 0.5 * inch - 0.17 * inch - 0.35 * inch - 96
        
        # Draw table container
        pdf.setFillColor(colors.HexColor("#ffffff"))
        pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
        pdf.setLineWidth(1)
        pdf.roundRect(margin_points, table_start_y_dynamic, width_points - margin_points * 2, total_height + 0.4 * inch + 0.5 * inch + 0.17 * inch + 0.35 * inch, 12, fill=1, stroke=1)
        
        # Table title
        pdf.setFillColor(dark_green)
        pdf.setFont(table_title_font, 12)
        table_title_y = table_start_y_dynamic + total_height + 0.4 * inch + 0.5 * inch + 0.17 * inch + 0.35 * inch - 0.35 * inch
        pdf.drawString(table_title_x, table_title_y, "Table 2: Diverted from Disposal")
        
        # Table header
        table_header_start_y = table_title_y - 0.5 * inch - 0.17 * inch
        pdf.setFillColor(colors.HexColor("#f3f3f3"))
        pdf.rect(margin_points, table_header_start_y, width_points - margin_points * 2, 0.4 * inch, fill=1, stroke=0)
        pdf.setFillColor(dark_green)
        pdf.setFont(card_font, 9)
        table_header_y = table_header_start_y + 0.16 * inch
        pdf.drawString(table_title_x, table_header_y, "#")
        pdf.drawString(table_title_x + 0.4 * inch, table_header_y, "Method")
        pdf.drawString(table_title_x + 5 * inch, table_header_y, "Onsite (T)")
        pdf.drawString(table_title_x + 6.9 * inch, table_header_y, "Offsite (T)")
        pdf.drawString(table_title_x + 8.8 * inch, table_header_y, "Total (T)")
        
        # Draw first page rows
        top_start_y = table_header_start_y
        draw_diverted_rows(first_page_rows, top_start_y, is_first_row_on_page=False)
        
        # Process remaining in chunks of 8
        for i in range(0, len(remaining_rows), 8):
            chunk = remaining_rows[i:i+8]
            
            # Calculate dynamic table height
            num_rows = len(chunk)
            total_height = sum(
                header_row_height if r["type"] == "header" 
                else row_height  # for both "data" and "total" types
                for r in chunk
            )
            table_start_y_dynamic = height_points - margin_points - total_height - 96
            
            # Create new page
            _footer(pdf, width_points)
            pdf.showPage()
            _draw_page_header(pdf, year, width_points, height_points, margin_points)
            
            # Draw table container
            pdf.setFillColor(colors.HexColor("#ffffff"))
            pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
            pdf.setLineWidth(1)
            pdf.roundRect(margin_points, table_start_y_dynamic, width_points - margin_points * 2, total_height, 12, fill=1, stroke=1)
            
            # Draw rows - start from the top
            top_start_y = table_start_y_dynamic + total_height
            draw_diverted_rows(chunk, top_start_y, is_first_row_on_page=True)


def _draw_directed_data_table(pdf: canvas.Canvas, directed_data: dict, year: str, width_points: float, height_points: float, margin_points: float) -> None:
    """Draw the directed data table on a new page with pagination"""
    # Fonts
    table_title_font = _get_font_name("IBMPlexSansThai-Bold", "Helvetica-Bold")
    card_font = _get_font_name("IBMPlexSansThai-Light", "Helvetica-Bold")
    
    # Colors
    dark_green = colors.HexColor("#52947a")
    
    # Table dimensions
    row_height = 0.6 * inch
    header_row_height = 0.4 * inch  # Same as column header
    table_title_x = margin_points + 12 + 4
    
    # Prepare data rows (including section headers)
    hazardous_data = directed_data.get("hazardous", {})
    non_hazardous_data = directed_data.get("non_hazardous", {})
    methods = list(hazardous_data.keys()) if hazardous_data else list(non_hazardous_data.keys())
    
    # Build rows list with section headers
    all_rows = []
    data_row_num = 1
    
    if hazardous_data:
        all_rows.append({"type": "header", "label": "Hazardous"})
        hazardous_totals = {"onsite": 0.0, "offsite": 0.0, "total": 0.0}
        for method in methods:
            method_data = hazardous_data.get(method, {})
            all_rows.append({
                "type": "data",
                "num": data_row_num,
                "method": method,
                "data": method_data
            })
            # Accumulate totals
            hazardous_totals["onsite"] += method_data.get("onsite", 0.0)
            hazardous_totals["offsite"] += method_data.get("offsite", 0.0)
            hazardous_totals["total"] += method_data.get("total", 0.0)
            data_row_num += 1
        # Add total row for hazardous
        all_rows.append({
            "type": "total",
            "label": "Total",
            "data": hazardous_totals
        })
    
    if non_hazardous_data:
        all_rows.append({"type": "header", "label": "Non-Hazardous"})
        non_hazardous_totals = {"onsite": 0.0, "offsite": 0.0, "total": 0.0}
        for method in methods:
            method_data = non_hazardous_data.get(method, {})
            all_rows.append({
                "type": "data",
                "num": data_row_num,
                "method": method,
                "data": method_data
            })
            # Accumulate totals
            non_hazardous_totals["onsite"] += method_data.get("onsite", 0.0)
            non_hazardous_totals["offsite"] += method_data.get("offsite", 0.0)
            non_hazardous_totals["total"] += method_data.get("total", 0.0)
            data_row_num += 1
        # Add total row for non-hazardous
        all_rows.append({
            "type": "total",
            "label": "Total",
            "data": non_hazardous_totals
        })
    
    # Helper function to draw rows on a page
    def draw_directed_rows(page_rows, row_start_y_pos, is_first_row_on_page=False):
        """Draw directed data rows for a given page"""
        row_start_y = row_start_y_pos
        
        for idx, row in enumerate(page_rows):
            is_first_row = (idx == 0) and is_first_row_on_page
            
            # Calculate cumulative height of previous rows
            prev_height = sum(
                header_row_height if page_rows[i]["type"] == "header" 
                else row_height  # for both "data" and "total" types
                for i in range(idx)
            )
            
            if row["type"] == "header":
                # Section header row - same height as column header
                row_y = row_start_y - prev_height
                
                # Draw header row border
                pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
                pdf.setLineWidth(0.5)
                if is_first_row:
                    # Draw only sides and bottom (no top border)
                    pdf.line(margin_points, row_y - header_row_height, margin_points, row_y)  # Left
                    pdf.line(margin_points + (width_points - margin_points * 2), row_y - header_row_height, 
                            margin_points + (width_points - margin_points * 2), row_y)  # Right
                    pdf.line(margin_points, row_y - header_row_height, margin_points + (width_points - margin_points * 2), row_y - header_row_height)  # Bottom
                else:
                    pdf.rect(margin_points, row_y - header_row_height, width_points - margin_points * 2, header_row_height, fill=0, stroke=1)
                
                # Header row background
                pdf.setFillColor(colors.HexColor("#fafafa"))
                pdf.rect(margin_points, row_y - header_row_height, width_points - margin_points * 2, header_row_height, fill=1, stroke=0)
                
                pdf.setFillColor(dark_green)
                pdf.setFont(card_font, 9)
                text_y = row_y - (header_row_height / 2) - 3
                pdf.drawString(table_title_x + 0.4 * inch, text_y, row["label"])
            elif row["type"] == "total":
                # Total row - same styling as data rows
                row_y = row_start_y - prev_height
                is_last_row = (idx == len(page_rows) - 1)
                
                # Draw total row background
                pdf.setFillColor(colors.HexColor("#f5faf8"))
                pdf.rect(margin_points, row_y - row_height, width_points - margin_points * 2, row_height, fill=1, stroke=0)
                
                # Draw row border
                pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
                pdf.setLineWidth(0.5)
                if is_last_row:
                    # Draw only top and sides (no bottom)
                    pdf.line(margin_points, row_y, margin_points + (width_points - margin_points * 2), row_y)  # Top
                    pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
                    pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                            margin_points + (width_points - margin_points * 2), row_y)  # Right
                elif is_first_row:
                    # Draw only sides and bottom (no top border)
                    pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
                    pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                            margin_points + (width_points - margin_points * 2), row_y)  # Right
                    pdf.line(margin_points, row_y - row_height, margin_points + (width_points - margin_points * 2), row_y - row_height)  # Bottom
                else:
                    pdf.rect(margin_points, row_y - row_height, width_points - margin_points * 2, row_height, fill=0, stroke=1)
                
                # Total row data
                pdf.setFillColor(dark_green)
                pdf.setFont(card_font, 11)
                text_y = row_y - (row_height / 2) - 3
                
                pdf.drawString(table_title_x, text_y, "")  # Empty number column
                pdf.drawString(table_title_x + 0.4 * inch, text_y, row["label"])
                pdf.drawString(table_title_x + 5 * inch, text_y, f"{row['data'].get('onsite', 0.0):,.2f}")
                pdf.drawString(table_title_x + 6.9 * inch, text_y, f"{row['data'].get('offsite', 0.0):,.2f}")
                pdf.drawString(table_title_x + 8.8 * inch, text_y, f"{row['data'].get('total', 0.0):,.2f}")
            else:  # row["type"] == "data"
                # Data row
                row_y = row_start_y - prev_height
                is_last_row = (idx == len(page_rows) - 1)
                
                # Draw row border
                pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
                pdf.setLineWidth(0.5)
                if is_last_row:
                    # Draw only top and sides (no bottom)
                    pdf.line(margin_points, row_y, margin_points + (width_points - margin_points * 2), row_y)  # Top
                    pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
                    pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                            margin_points + (width_points - margin_points * 2), row_y)  # Right
                elif is_first_row:
                    # Draw only sides and bottom (no top border)
                    pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
                    pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                            margin_points + (width_points - margin_points * 2), row_y)  # Right
                    pdf.line(margin_points, row_y - row_height, margin_points + (width_points - margin_points * 2), row_y - row_height)  # Bottom
                else:
                    pdf.rect(margin_points, row_y - row_height, width_points - margin_points * 2, row_height, fill=0, stroke=1)
                
                # Row data
                pdf.setFillColor(dark_green)
                pdf.setFont(card_font, 11)
                text_y = row_y - (row_height / 2) - 3
                
                pdf.drawString(table_title_x, text_y, str(row["num"]))
                pdf.drawString(table_title_x + 0.4 * inch, text_y, row["method"])
                pdf.drawString(table_title_x + 5 * inch, text_y, f"{row['data'].get('onsite', 0.0):,.2f}")
                pdf.drawString(table_title_x + 6.9 * inch, text_y, f"{row['data'].get('offsite', 0.0):,.2f}")
                pdf.drawString(table_title_x + 8.8 * inch, text_y, f"{row['data'].get('total', 0.0):,.2f}")
    
    # Pagination: First page max 8 rows, subsequent pages max 8 rows
    if len(all_rows) <= 8:
        # All rows fit on first page
        _footer(pdf, width_points)
        pdf.showPage()
        _draw_page_header(pdf, year, width_points, height_points, margin_points)
        
        # Calculate dynamic table height
        total_height = sum(
            header_row_height if r["type"] == "header" 
            else row_height  # for both "data" and "total" types
            for r in all_rows
        ) - 26
        table_start_y_dynamic = height_points - margin_points - total_height - 0.4 * inch - 0.5 * inch - 0.17 * inch - 0.35 * inch - 96
        
        # Draw table container
        pdf.setFillColor(colors.HexColor("#ffffff"))
        pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
        pdf.setLineWidth(1)
        pdf.roundRect(margin_points, table_start_y_dynamic, width_points - margin_points * 2, total_height + 0.4 * inch + 0.5 * inch + 0.17 * inch + 0.35 * inch, 12, fill=1, stroke=1)
        
        # Table title
        pdf.setFillColor(dark_green)
        pdf.setFont(table_title_font, 12)
        table_title_y = table_start_y_dynamic + total_height + 0.4 * inch + 0.5 * inch + 0.17 * inch + 0.35 * inch - 0.35 * inch
        pdf.drawString(table_title_x, table_title_y, "Table 3: Waste Directed from Disposal")
        
        # Table header
        table_header_start_y = table_title_y - 0.5 * inch - 0.17 * inch
        pdf.setFillColor(colors.HexColor("#f3f3f3"))
        pdf.rect(margin_points, table_header_start_y, width_points - margin_points * 2, 0.4 * inch, fill=1, stroke=0)
        pdf.setFillColor(dark_green)
        pdf.setFont(card_font, 9)
        table_header_y = table_header_start_y + 0.16 * inch
        pdf.drawString(table_title_x, table_header_y, "#")
        pdf.drawString(table_title_x + 0.4 * inch, table_header_y, "Method")
        pdf.drawString(table_title_x + 5 * inch, table_header_y, "Onsite (T)")
        pdf.drawString(table_title_x + 6.9 * inch, table_header_y, "Offsite (T)")
        pdf.drawString(table_title_x + 8.8 * inch, table_header_y, "Total (T)")
        
        # Draw rows
        top_start_y = table_header_start_y
        draw_directed_rows(all_rows, top_start_y, is_first_row_on_page=False)
    else:
        # First page: 8 rows
        first_page_rows = all_rows[:8]
        remaining_rows = all_rows[8:]
        
        # First page
        _footer(pdf, width_points)
        pdf.showPage()
        _draw_page_header(pdf, year, width_points, height_points, margin_points)
        
        # Calculate dynamic table height for first page
        total_height = sum(
            header_row_height if r["type"] == "header" 
            else row_height  # for both "data" and "total" types
            for r in first_page_rows
        ) - 26
        table_start_y_dynamic = height_points - margin_points - total_height - 0.4 * inch - 0.5 * inch - 0.17 * inch - 0.35 * inch - 96
        
        # Draw table container
        pdf.setFillColor(colors.HexColor("#ffffff"))
        pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
        pdf.setLineWidth(1)
        pdf.roundRect(margin_points, table_start_y_dynamic, width_points - margin_points * 2, total_height + 0.4 * inch + 0.5 * inch + 0.17 * inch + 0.35 * inch, 12, fill=1, stroke=1)
        
        # Table title
        pdf.setFillColor(dark_green)
        pdf.setFont(table_title_font, 12)
        table_title_y = table_start_y_dynamic + total_height + 0.4 * inch + 0.5 * inch + 0.17 * inch + 0.35 * inch - 0.35 * inch
        pdf.drawString(table_title_x, table_title_y, "Table 3: Waste Directed from Disposal")
        
        # Table header
        table_header_start_y = table_title_y - 0.5 * inch - 0.17 * inch
        pdf.setFillColor(colors.HexColor("#f3f3f3"))
        pdf.rect(margin_points, table_header_start_y, width_points - margin_points * 2, 0.4 * inch, fill=1, stroke=0)
        pdf.setFillColor(dark_green)
        pdf.setFont(card_font, 9)
        table_header_y = table_header_start_y + 0.16 * inch
        pdf.drawString(table_title_x, table_header_y, "#")
        pdf.drawString(table_title_x + 0.4 * inch, table_header_y, "Method")
        pdf.drawString(table_title_x + 5 * inch, table_header_y, "Onsite (T)")
        pdf.drawString(table_title_x + 6.9 * inch, table_header_y, "Offsite (T)")
        pdf.drawString(table_title_x + 8.8 * inch, table_header_y, "Total (T)")
        
        # Draw first page rows
        top_start_y = table_header_start_y
        draw_directed_rows(first_page_rows, top_start_y, is_first_row_on_page=False)
        
        # Process remaining in chunks of 8
        for i in range(0, len(remaining_rows), 8):
            chunk = remaining_rows[i:i+8]
            
            # Calculate dynamic table height
            num_rows = len(chunk)
            total_height = sum(
                header_row_height if r["type"] == "header" 
                else row_height  # for both "data" and "total" types
                for r in chunk
            )
            table_start_y_dynamic = height_points - margin_points - total_height - 96
            
            # Create new page
            _footer(pdf, width_points)
            pdf.showPage()
            _draw_page_header(pdf, year, width_points, height_points, margin_points)
            
            # Draw table container
            pdf.setFillColor(colors.HexColor("#ffffff"))
            pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
            pdf.setLineWidth(1)
            pdf.roundRect(margin_points, table_start_y_dynamic, width_points - margin_points * 2, total_height, 12, fill=1, stroke=1)
            
            # Draw rows - start from the top
            top_start_y = table_start_y_dynamic + total_height
            draw_directed_rows(chunk, top_start_y, is_first_row_on_page=True)


def _draw_spill_data_table(pdf: canvas.Canvas, spill_data: dict, year: str, width_points: float, height_points: float, margin_points: float) -> None:
    """Draw the spill data table on a new page with pagination"""
    # Fonts
    table_title_font = _get_font_name("IBMPlexSansThai-Bold", "Helvetica-Bold")
    card_font = _get_font_name("IBMPlexSansThai-Light", "Helvetica-Bold")
    
    # Colors
    dark_green = colors.HexColor("#52947a")
    
    # Table dimensions
    row_height = 0.6 * inch
    table_title_x = margin_points + 12 + 4
    
    # Get spill records
    records = spill_data.get("records", [])
    totals = spill_data.get("totals", {})
    
    # Helper function to draw rows on a page
    def draw_spill_rows(page_records, start_row_num, row_start_y_pos, is_last_page=False, is_first_row_on_page=False):
        """Draw spill data rows for a given page"""
        row_start_y = row_start_y_pos
        
        for idx, record in enumerate(page_records):
            row_num = start_row_num + idx
            row_y = row_start_y - idx * row_height
            is_first_row = (idx == 0) and is_first_row_on_page
            is_last_row = (idx == len(page_records) - 1)
            
            # Draw row border
            pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
            pdf.setLineWidth(0.5)
            if is_last_row and not is_first_row:
                # Draw only top and sides (no bottom)
                pdf.line(margin_points, row_y, margin_points + (width_points - margin_points * 2), row_y)  # Top
                pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
                pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                        margin_points + (width_points - margin_points * 2), row_y)  # Right
            elif is_first_row:
                # Draw only sides and bottom (no top border)
                pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
                pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                        margin_points + (width_points - margin_points * 2), row_y)  # Right
                pdf.line(margin_points, row_y - row_height, margin_points + (width_points - margin_points * 2), row_y - row_height)  # Bottom
            elif is_last_row and is_first_row:
                # First and last row (only one row) - only sides, no top or bottom
                pdf.line(margin_points, row_y - row_height, margin_points, row_y)  # Left
                pdf.line(margin_points + (width_points - margin_points * 2), row_y - row_height, 
                        margin_points + (width_points - margin_points * 2), row_y)  # Right
            else:
                # Draw full border
                pdf.rect(margin_points, row_y - row_height, width_points - margin_points * 2, row_height, fill=0, stroke=1)
            
            # Row data
            pdf.setFillColor(dark_green)
            pdf.setFont(card_font, 11)
            text_y = row_y - (row_height / 2) - 3
            
            pdf.drawString(table_title_x, text_y, str(row_num))
            pdf.drawString(table_title_x + 0.4 * inch, text_y, record.get("spill_type", ""))
            pdf.drawString(table_title_x + 2.5 * inch, text_y, record.get("surface_type", ""))
            pdf.drawString(table_title_x + 4.5 * inch, text_y, record.get("location", ""))
            pdf.drawString(table_title_x + 6.5 * inch, text_y, f"{record.get('volume', 0.0):,.2f}")
            pdf.drawString(table_title_x + 8.5 * inch, text_y, f"{record.get('cleanup_cost', 0.0):,.2f}")
        
        # Draw totals row only on the last page
        if is_last_page and totals:
            total_row_y = row_start_y - len(page_records) * row_height
            
            # Draw total row background
            pdf.setFillColor(colors.HexColor("#f5faf8"))
            pdf.rect(margin_points, total_row_y - row_height, width_points - margin_points * 2, row_height, fill=1, stroke=0)
            
            # Draw border - exclude bottom border
            pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
            pdf.setLineWidth(0.5)
            # Draw only top and sides (no bottom)
            pdf.line(margin_points, total_row_y, margin_points + (width_points - margin_points * 2), total_row_y)  # Top
            pdf.line(margin_points, total_row_y - row_height, margin_points, total_row_y)  # Left
            pdf.line(margin_points + (width_points - margin_points * 2), total_row_y - row_height, 
                    margin_points + (width_points - margin_points * 2), total_row_y)  # Right
            
            # Totals data
            pdf.setFillColor(dark_green)
            pdf.setFont(card_font, 11)
            text_y = total_row_y - (row_height / 2) - 3
            
            pdf.drawString(table_title_x, text_y, "")  # Empty number column
            pdf.drawString(table_title_x + 0.4 * inch, text_y, "Total")
            pdf.drawString(table_title_x + 2.5 * inch, text_y, "")  # Empty surface type
            pdf.drawString(table_title_x + 4.5 * inch, text_y, "")  # Empty location
            pdf.drawString(table_title_x + 6.5 * inch, text_y, f"{totals.get('total_volume', 0.0):,.2f}")
            pdf.drawString(table_title_x + 8.5 * inch, text_y, f"{totals.get('total_cleanup_cost', 0.0):,.2f}")
    
    # Pagination: First page max 8 rows, subsequent pages max 9 rows
    if len(records) <= 7:
        # All rows fit on first page
        _footer(pdf, width_points)
        pdf.showPage()
        _draw_page_header(pdf, year, width_points, height_points, margin_points)
        
        # Calculate dynamic table height
        total_height = len(records) * row_height
        if totals:
            total_height += row_height  # Add space for totals row
        total_height = total_height - 26
        table_start_y_dynamic = height_points - margin_points - total_height - 0.4 * inch - 0.5 * inch - 0.17 * inch - 0.35 * inch - 96
        
        # Draw table container
        pdf.setFillColor(colors.HexColor("#ffffff"))
        pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
        pdf.setLineWidth(1)
        pdf.roundRect(margin_points, table_start_y_dynamic, width_points - margin_points * 2, total_height + 0.4 * inch + 0.5 * inch + 0.17 * inch + 0.35 * inch, 12, fill=1, stroke=1)
        
        # Table title
        pdf.setFillColor(dark_green)
        pdf.setFont(table_title_font, 12)
        table_title_y = table_start_y_dynamic + total_height + 0.4 * inch + 0.5 * inch + 0.17 * inch + 0.35 * inch - 0.35 * inch
        pdf.drawString(table_title_x, table_title_y, "Table 4: Significant Spills")
        
        # Table header
        table_header_start_y = table_title_y - 0.5 * inch - 0.17 * inch
        pdf.setFillColor(colors.HexColor("#f3f3f3"))
        pdf.rect(margin_points, table_header_start_y, width_points - margin_points * 2, 0.4 * inch, fill=1, stroke=0)
        pdf.setFillColor(dark_green)
        pdf.setFont(card_font, 9)
        table_header_y = table_header_start_y + 0.16 * inch
        pdf.drawString(table_title_x, table_header_y, "#")
        pdf.drawString(table_title_x + 0.4 * inch, table_header_y, "Material Type")
        pdf.drawString(table_title_x + 2.5 * inch, table_header_y, "Surface Type")
        pdf.drawString(table_title_x + 4.5 * inch, table_header_y, "Location")
        pdf.drawString(table_title_x + 6.5 * inch, table_header_y, "Volume (Liters)")
        pdf.drawString(table_title_x + 8.5 * inch, table_header_y, "Cleanup Cost (THB)")
        
        # Draw rows
        top_start_y = table_header_start_y
        draw_spill_rows(records, start_row_num=1, row_start_y_pos=top_start_y, is_last_page=True, is_first_row_on_page=False)
    else:
        # First page: 8 rows
        first_page_records = records[:7]
        remaining_records = records[7:]
        
        # First page
        _footer(pdf, width_points)
        pdf.showPage()
        _draw_page_header(pdf, year, width_points, height_points, margin_points)
        
        # Calculate dynamic table height for first page
        total_height = len(first_page_records) * row_height - 26
        table_start_y_dynamic = height_points - margin_points - total_height - 0.4 * inch - 0.5 * inch - 0.17 * inch - 0.35 * inch - 96
        
        # Draw table container
        pdf.setFillColor(colors.HexColor("#ffffff"))
        pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
        pdf.setLineWidth(1)
        pdf.roundRect(margin_points, table_start_y_dynamic, width_points - margin_points * 2, total_height + 0.4 * inch + 0.5 * inch + 0.17 * inch + 0.35 * inch, 12, fill=1, stroke=1)
        
        # Table title
        pdf.setFillColor(dark_green)
        pdf.setFont(table_title_font, 12)
        table_title_y = table_start_y_dynamic + total_height + 0.4 * inch + 0.5 * inch + 0.17 * inch + 0.35 * inch - 0.35 * inch
        pdf.drawString(table_title_x, table_title_y, "Table 4: Significant Spills")
        
        # Table header
        table_header_start_y = table_title_y - 0.5 * inch - 0.17 * inch
        pdf.setFillColor(colors.HexColor("#f3f3f3"))
        pdf.rect(margin_points, table_header_start_y, width_points - margin_points * 2, 0.4 * inch, fill=1, stroke=0)
        pdf.setFillColor(dark_green)
        pdf.setFont(card_font, 9)
        table_header_y = table_header_start_y + 0.16 * inch
        pdf.drawString(table_title_x, table_header_y, "#")
        pdf.drawString(table_title_x + 0.4 * inch, table_header_y, "Material Type")
        pdf.drawString(table_title_x + 2.5 * inch, table_header_y, "Surface Type")
        pdf.drawString(table_title_x + 4.5 * inch, table_header_y, "Location")
        pdf.drawString(table_title_x + 6.5 * inch, table_header_y, "Volume (Liters)")
        pdf.drawString(table_title_x + 8.5 * inch, table_header_y, "Cleanup Cost (THB)")
        
        # Draw first page rows
        top_start_y = table_header_start_y
        draw_spill_rows(first_page_records, start_row_num=1, row_start_y_pos=top_start_y, is_last_page=False, is_first_row_on_page=False)
        
        # Process remaining in chunks of 9
        for i in range(0, len(remaining_records), 9):
            chunk = remaining_records[i:i+9]
            is_last_chunk = (i + 9 >= len(remaining_records))
            
            # Calculate dynamic table height
            num_rows = len(chunk)
            if is_last_chunk and totals:
                num_rows += 1  # Add space for totals row
            total_height = num_rows * row_height
            table_start_y_dynamic = height_points - margin_points - total_height - 96
            
            # Create new page
            _footer(pdf, width_points)
            pdf.showPage()
            _draw_page_header(pdf, year, width_points, height_points, margin_points)
            
            # Draw table container
            pdf.setFillColor(colors.HexColor("#ffffff"))
            pdf.setStrokeColor(colors.HexColor("#e3f2ec"))
            pdf.setLineWidth(1)
            pdf.roundRect(margin_points, table_start_y_dynamic, width_points - margin_points * 2, total_height, 12, fill=1, stroke=1)
            
            # Draw rows - start from the top
            top_start_y = table_start_y_dynamic + total_height
            draw_spill_rows(chunk, start_row_num=9 + i, row_start_y_pos=top_start_y, is_last_page=is_last_chunk, is_first_row_on_page=True)


def generate_pdf_bytes(data: dict) -> bytes:
    """
    Generate a PDF report and return it as bytes suitable for HTTP response/base64 encoding.
    Currently, this renders the cover page that matches the provided design.
    """
    width_points = PAGE_WIDTH_IN * inch
    height_points = PAGE_HEIGHT_IN * inch

    # Prepare in-memory buffer
    buffer = BytesIO()

    # Ensure fonts are registered (works both locally and in Lambda with a layer)
    _register_fonts()

    pdf = canvas.Canvas(buffer, pagesize=(width_points, height_points))

    _draw_cover_page(pdf, data)
    pdf.showPage()
    _draw_full_disclosure_page(pdf, data)
    _footer(pdf, width_points)  # Add footer to full disclosure page
    pdf.showPage()
    _draw_outro_cover_page(pdf, data)
    pdf.save()
    return buffer.getvalue()
    
    print("Generating test PDF...")
    pdf_bytes = generate_pdf_bytes(dummy_data)
    
    output_filename = "test_gri_report.pdf"
    with open(output_filename, "wb") as f:
        f.write(pdf_bytes)
        
    print(f"PDF generated successfully: {output_filename}")
