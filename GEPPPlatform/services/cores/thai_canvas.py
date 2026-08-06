"""
Thai-aware ReportLab canvas.

ReportLab has no OpenType mark positioning (GPOS), so a tone mark that follows an upper
vowel — ที่, ทั้ง, ปั๊ม — is drawn at its default height, right on top of the vowel.
ThaiCanvas redraws those marks with a text rise so they stack correctly.

Drop-in: use ThaiCanvas(...) wherever canvas.Canvas(...) was used.
"""
from reportlab.pdfgen import canvas

_THAI_TONES = "่้๊๋์"          # ่ ้ ๊ ๋ ์
_THAI_UPPER = "ิีึืั็ํ"      # ิ ี ึ ื ั ็ ํ
_THAI_TONE_RISE = 0.22          # em above the vowel; tuned by eye


def thai_stacked(text) -> bool:
    """True when text has a tone mark sitting on an upper vowel."""
    return bool(text) and isinstance(text, str) and any(
        c in _THAI_TONES and i and text[i - 1] in _THAI_UPPER for i, c in enumerate(text)
    )


class ThaiCanvas(canvas.Canvas):
    """Canvas that lifts Thai tone marks off the upper vowel underneath them."""

    def _font(self):
        return getattr(self, "_fontname"), getattr(self, "_fontsize")

    def _draw_thai(self, x: float, y: float, text: str) -> None:
        name, size = self._font()
        t = self.beginText(x, y)
        t.setFont(name, size)
        for i, ch in enumerate(text):
            if ch in _THAI_TONES and i and text[i - 1] in _THAI_UPPER:
                # ponytail: one hand-tuned rise instead of real GPOS mark attachment.
                # Swap in a shaper (uharfbuzz) if these ever need to be per-glyph exact.
                t.setRise(_THAI_TONE_RISE * size)
                t.textOut(ch)
                t.setRise(0)
            else:
                t.textOut(ch)
        self.drawText(t)

    def drawString(self, x, y, text, *a, **kw):
        if thai_stacked(text):
            return self._draw_thai(x, y, text)
        return super().drawString(x, y, text, *a, **kw)

    def drawRightString(self, x, y, text, *a, **kw):
        if thai_stacked(text):
            return self._draw_thai(x - self.stringWidth(text, *self._font()), y, text)
        return super().drawRightString(x, y, text, *a, **kw)

    def drawCentredString(self, x, y, text, *a, **kw):
        if thai_stacked(text):
            return self._draw_thai(x - self.stringWidth(text, *self._font()) / 2.0, y, text)
        return super().drawCentredString(x, y, text, *a, **kw)
