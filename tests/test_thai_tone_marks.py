"""ThaiCanvas lifts tone marks off upper vowels (ReportLab has no GPOS mark positioning)."""
from io import BytesIO

from GEPPPlatform.services.cores.thai_canvas import ThaiCanvas, thai_stacked
from GEPPPlatform.services.cores.reports.pdf_export import _register_fonts


def test_detects_only_stacked_marks():
    assert thai_stacked("ที่นี่")      # tone on top of ◌ี
    assert thai_stacked("ทั้งหมด")     # tone on top of ◌ั
    assert not thai_stacked("ขยะ")     # no marks
    assert not thai_stacked("น้ำ")     # tone sits on the consonant, already fine
    assert not thai_stacked("Recycle")
    assert not thai_stacked(None) and not thai_stacked("")


def test_stacked_text_is_drawn_with_a_rise():
    _register_fonts()
    c = ThaiCanvas(BytesIO(), pagesize=(200, 100))
    c.setFont("IBMPlexSansThai-Regular", 10)
    c.drawString(10, 50, "ที่นี่")
    stream = c.getCurrentPageContent()
    assert " Ts" in stream, "expected a text-rise op for the lifted tone mark"


if __name__ == "__main__":
    test_detects_only_stacked_marks()
    test_stacked_text_is_drawn_with_a_rise()
    print("ok")
