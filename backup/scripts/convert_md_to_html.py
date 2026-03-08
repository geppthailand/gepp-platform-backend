#!/usr/bin/env python3
"""
Convert Markdown to styled HTML with Thai language support
You can then open this HTML in a browser and use Print to PDF
"""
import markdown2
import os

def markdown_to_html(md_file, html_file):
    """Convert a Markdown file to styled HTML"""

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
            'code-friendly',
            'header-ids'
        ]
    )

    # Find and wrap JWT token with special container
    jwt_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoyNiwib3JnYW5pemF0aW9uX2lkIjo4LCJlbWFpbCI6ImJtYUBnZXBwLm1lIiwidHlwZSI6ImludGVncmF0aW9uIiwiZXhwIjoxNzYyMjM4NTA2LCJpYXQiOjE3NjE2MzM3MDZ9.q1v6QIH_14c_sNAomOYvoMYNmmlPhgPBPyTsA4KB1Oo"

    # Replace JWT token with special copyable div
    if jwt_token in html_content:
        html_content = html_content.replace(
            f"<pre><code>{jwt_token}\n</code></pre>",
            f'''<div class="jwt-container">
                <div class="jwt-token" id="jwt-token">{jwt_token}</div>
                <button class="copy-jwt-btn" onclick="copyJWT()" title="คัดลอก JWT Token">
                    📋 คัดลอก
                </button>
                <span class="copy-feedback" id="copy-feedback">✅ คัดลอกแล้ว!</span>
            </div>'''
        )

    # Create full HTML with Thai font support and beautiful styling
    full_html = f"""<!DOCTYPE html>
<html lang="th">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BMA Integration API Documentation</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Sarabun:wght@300;400;600;700&family=IBM+Plex+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Sarabun', 'Tahoma', 'Arial', sans-serif;
            line-height: 1.8;
            color: #2c3e50;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 40px 20px;
        }}

        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 60px;
            border-radius: 15px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
        }}

        h1 {{
            color: #667eea;
            font-size: 42px;
            font-weight: 700;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 4px solid #667eea;
            text-align: center;
        }}

        h2 {{
            color: #764ba2;
            font-size: 32px;
            font-weight: 600;
            margin-top: 50px;
            margin-bottom: 25px;
            padding-bottom: 15px;
            border-bottom: 3px solid #e0e0e0;
        }}

        h3 {{
            color: #667eea;
            font-size: 26px;
            font-weight: 600;
            margin-top: 35px;
            margin-bottom: 20px;
        }}

        h4 {{
            color: #555;
            font-size: 20px;
            font-weight: 600;
            margin-top: 25px;
            margin-bottom: 15px;
            padding-left: 15px;
            border-left: 4px solid #667eea;
        }}

        p {{
            margin: 15px 0;
            font-size: 16px;
            line-height: 1.8;
        }}

        code {{
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 3px 8px;
            border-radius: 4px;
            font-family: 'IBM Plex Mono', 'Monaco', 'Courier New', monospace;
            font-size: 14px;
            color: #e74c3c;
            font-weight: 600;
        }}

        pre {{
            background: #2c3e50;
            color: #ecf0f1;
            padding: 25px;
            border-radius: 8px;
            overflow-x: auto;
            overflow-wrap: break-word;
            word-wrap: break-word;
            word-break: break-all;
            white-space: pre-wrap;
            margin: 25px 0;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.2);
        }}

        pre code {{
            background: transparent;
            color: #ecf0f1;
            padding: 0;
            font-size: 14px;
            font-weight: 400;
            word-break: break-all;
            white-space: pre-wrap;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 25px 0;
            font-size: 15px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
            border-radius: 8px;
            overflow: hidden;
        }}

        thead {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }}

        th {{
            padding: 15px;
            text-align: left;
            font-weight: 600;
            font-size: 16px;
        }}

        td {{
            padding: 15px;
            border-bottom: 1px solid #e0e0e0;
        }}

        tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}

        tr:hover {{
            background-color: #f0f0f0;
            transition: background-color 0.3s;
        }}

        ul, ol {{
            margin: 15px 0;
            padding-left: 40px;
        }}

        li {{
            margin: 10px 0;
            font-size: 16px;
        }}

        hr {{
            border: none;
            border-top: 2px solid #e0e0e0;
            margin: 40px 0;
        }}

        strong {{
            font-weight: 600;
            color: #2c3e50;
        }}

        a {{
            color: #667eea;
            text-decoration: none;
            border-bottom: 2px solid transparent;
            transition: border-color 0.3s;
        }}

        a:hover {{
            border-bottom: 2px solid #667eea;
        }}

        blockquote {{
            border-left: 5px solid #667eea;
            padding-left: 20px;
            margin: 25px 0;
            color: #555;
            font-style: italic;
            background: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
        }}

        /* Print styles */
        @media print {{
            body {{
                background: white;
                padding: 0;
            }}

            .container {{
                box-shadow: none;
                padding: 40px;
            }}

            h1 {{
                page-break-before: avoid;
            }}

            h2 {{
                page-break-before: always;
            }}

            h2:first-of-type {{
                page-break-before: avoid;
            }}

            pre, table {{
                page-break-inside: avoid;
            }}

            pre {{
                overflow-x: visible;
                word-break: break-all;
                white-space: pre-wrap;
            }}

            pre code {{
                word-break: break-all;
                white-space: pre-wrap;
            }}
        }}

        /* Warning boxes */
        p:has(> strong:first-child) {{
            background: linear-gradient(135deg, #fff9e6 0%, #ffe8cc 100%);
            border-left: 5px solid #ff9800;
            padding: 20px;
            margin: 25px 0;
            border-radius: 5px;
            box-shadow: 0 2px 10px rgba(255, 152, 0, 0.2);
        }}

        /* Code examples */
        .language-json,
        .language-javascript,
        .language-python {{
            font-size: 13px;
        }}

        /* Print button */
        .print-button {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 50px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            transition: transform 0.3s, box-shadow 0.3s;
            font-family: 'Sarabun', sans-serif;
        }}

        .print-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
        }}

        /* JWT Token Container */
        .jwt-container {{
            position: relative;
            margin: 25px 0;
            background: #f8f9fa;
            border: 2px solid #667eea;
            border-radius: 8px;
            padding: 20px;
        }}

        .jwt-token {{
            font-family: 'IBM Plex Mono', 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            color: #2c3e50;
            background: white;
            padding: 15px;
            border-radius: 5px;
            border: 1px solid #e0e0e0;
            word-break: break-all;
            overflow-wrap: break-word;
            line-height: 1.8;
            user-select: all;
            -webkit-user-select: all;
            -moz-user-select: all;
            -ms-user-select: all;
        }}

        .copy-jwt-btn {{
            position: absolute;
            top: 15px;
            right: 15px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            padding: 8px 15px;
            border-radius: 5px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            font-family: 'Sarabun', sans-serif;
            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
            transition: transform 0.2s, box-shadow 0.2s;
        }}

        .copy-jwt-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(102, 126, 234, 0.5);
        }}

        .copy-jwt-btn:active {{
            transform: translateY(0);
        }}

        .copy-feedback {{
            display: none;
            position: absolute;
            top: 15px;
            right: 15px;
            background: #10b981;
            color: white;
            padding: 8px 15px;
            border-radius: 5px;
            font-size: 14px;
            font-weight: 600;
            font-family: 'Sarabun', sans-serif;
            box-shadow: 0 2px 8px rgba(16, 185, 129, 0.3);
        }}

        .copy-feedback.show {{
            display: block;
        }}

        @media print {{
            .print-button {{
                display: none;
            }}

            .copy-jwt-btn {{
                display: none;
            }}

            .copy-feedback {{
                display: none;
            }}

            .jwt-token {{
                page-break-inside: avoid;
            }}
        }}
    </style>
</head>
<body>
    <button class="print-button" onclick="window.print()">🖨️ พิมพ์เป็น PDF</button>
    <div class="container">
        {html_content}
    </div>

    <script>
        // Copy JWT Token function
        function copyJWT() {{
            const jwtToken = document.getElementById('jwt-token');
            const copyBtn = document.querySelector('.copy-jwt-btn');
            const feedback = document.getElementById('copy-feedback');

            if (jwtToken) {{
                // Get the text content (this will be without line breaks)
                const text = jwtToken.textContent;

                // Copy to clipboard
                navigator.clipboard.writeText(text).then(() => {{
                    // Show feedback
                    copyBtn.style.display = 'none';
                    feedback.classList.add('show');

                    // Hide feedback after 2 seconds
                    setTimeout(() => {{
                        feedback.classList.remove('show');
                        copyBtn.style.display = 'block';
                    }}, 2000);
                }}).catch(err => {{
                    console.error('Failed to copy:', err);
                    alert('ไม่สามารถคัดลอกได้ กรุณาลองใหม่อีกครั้ง');
                }});
            }}
        }}

        // Allow selecting JWT by clicking
        document.addEventListener('DOMContentLoaded', () => {{
            const jwtToken = document.getElementById('jwt-token');
            if (jwtToken) {{
                jwtToken.addEventListener('click', () => {{
                    const selection = window.getSelection();
                    const range = document.createRange();
                    range.selectNodeContents(jwtToken);
                    selection.removeAllRanges();
                    selection.addRange(range);
                }});
            }}
        }});

        // Smooth scroll for anchors
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {{
            anchor.addEventListener('click', function (e) {{
                e.preventDefault();
                const target = document.querySelector(this.getAttribute('href'));
                if (target) {{
                    target.scrollIntoView({{
                        behavior: 'smooth'
                    }});
                }}
            }});
        }});
    </script>
</body>
</html>"""

    # Write HTML file
    with open(html_file, 'w', encoding='utf-8') as f:
        f.write(full_html)

    print(f"✅ HTML created successfully: {html_file}")
    print(f"\n📖 วิธีการสร้าง PDF:")
    print(f"   1. เปิดไฟล์ {html_file} ใน browser (Chrome, Safari, Firefox)")
    print(f"   2. คลิกปุ่ม '🖨️ พิมพ์เป็น PDF' หรือกด Cmd+P (Mac) / Ctrl+P (Windows)")
    print(f"   3. เลือก 'Save as PDF' หรือ 'Print to PDF'")
    print(f"   4. กดบันทึกเป็น backend/bma-api-doc.pdf")
    print(f"\n🌐 หรือเปิดใน browser: file://{os.path.abspath(html_file)}")

if __name__ == "__main__":
    md_file = "backend/bma-api-doc.md"
    html_file = "backend/bma-api-doc.html"

    if not os.path.exists(md_file):
        print(f"❌ Error: {md_file} not found")
        exit(1)

    markdown_to_html(md_file, html_file)
