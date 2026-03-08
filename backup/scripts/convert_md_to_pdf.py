#!/usr/bin/env python3
"""
Convert Markdown to PDF with Thai language support
"""
import markdown2
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
import os

def markdown_to_pdf(md_file, pdf_file):
    """Convert a Markdown file to PDF with Thai font support"""

    # Read markdown file
    with open(md_file, 'r', encoding='utf-8') as f:
        md_content = f.read()

    # Convert markdown to HTML
    html_content = markdown2.markdown(
        md_content,
        extras=[
            'fenced-code-blocks',
            'tables',
            'break-on-newline',
            'code-friendly'
        ]
    )

    # Create full HTML with Thai font support and styling
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600;700&display=swap');

            body {{
                font-family: 'Sarabun', 'Tahoma', 'Arial', sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 1000px;
                margin: 0 auto;
                padding: 20px;
                font-size: 14px;
            }}

            h1 {{
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
                font-size: 32px;
                font-weight: 700;
                margin-top: 30px;
                margin-bottom: 20px;
            }}

            h2 {{
                color: #34495e;
                border-bottom: 2px solid #95a5a6;
                padding-bottom: 8px;
                font-size: 26px;
                font-weight: 600;
                margin-top: 25px;
                margin-bottom: 15px;
            }}

            h3 {{
                color: #2c3e50;
                font-size: 22px;
                font-weight: 600;
                margin-top: 20px;
                margin-bottom: 12px;
            }}

            h4 {{
                color: #555;
                font-size: 18px;
                font-weight: 600;
                margin-top: 15px;
                margin-bottom: 10px;
            }}

            code {{
                background-color: #f4f4f4;
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Monaco', 'Courier New', monospace;
                font-size: 13px;
                color: #e74c3c;
            }}

            pre {{
                background-color: #2c3e50;
                color: #ecf0f1;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
                font-size: 12px;
                line-height: 1.4;
                margin: 15px 0;
            }}

            pre code {{
                background-color: transparent;
                color: #ecf0f1;
                padding: 0;
                font-size: 12px;
            }}

            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 15px 0;
                font-size: 13px;
            }}

            th, td {{
                border: 1px solid #ddd;
                padding: 10px;
                text-align: left;
            }}

            th {{
                background-color: #3498db;
                color: white;
                font-weight: 600;
            }}

            tr:nth-child(even) {{
                background-color: #f9f9f9;
            }}

            blockquote {{
                border-left: 4px solid #3498db;
                padding-left: 15px;
                margin: 15px 0;
                color: #555;
                font-style: italic;
            }}

            a {{
                color: #3498db;
                text-decoration: none;
            }}

            a:hover {{
                text-decoration: underline;
            }}

            ul, ol {{
                margin: 10px 0;
                padding-left: 30px;
            }}

            li {{
                margin: 5px 0;
            }}

            hr {{
                border: none;
                border-top: 2px solid #ecf0f1;
                margin: 25px 0;
            }}

            strong {{
                font-weight: 600;
                color: #2c3e50;
            }}

            /* Page breaks for PDF */
            h1 {{
                page-break-before: always;
            }}

            h1:first-of-type {{
                page-break-before: avoid;
            }}

            /* Prevent breaking inside elements */
            pre, table, blockquote {{
                page-break-inside: avoid;
            }}

            /* Warning/Important boxes */
            p:has(strong:first-child) {{
                background-color: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 10px 15px;
                margin: 15px 0;
            }}
        </style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """

    # Configure fonts
    font_config = FontConfiguration()

    # Convert HTML to PDF
    print(f"Converting {md_file} to {pdf_file}...")
    HTML(string=full_html, base_url='.').write_pdf(
        pdf_file,
        font_config=font_config
    )

    print(f"✅ PDF created successfully: {pdf_file}")

    # Get file size
    size = os.path.getsize(pdf_file)
    size_mb = size / (1024 * 1024)
    print(f"📄 File size: {size_mb:.2f} MB")

if __name__ == "__main__":
    md_file = "backend/bma-api-doc.md"
    pdf_file = "backend/bma-api-doc.pdf"

    if not os.path.exists(md_file):
        print(f"❌ Error: {md_file} not found")
        exit(1)

    markdown_to_pdf(md_file, pdf_file)
