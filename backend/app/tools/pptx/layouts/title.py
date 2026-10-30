from pptx.enum.text import MSO_ANCHOR
from pptx.util import Inches
from ..constants import MARGIN, SLIDE_W
from ..frames import _background
from ..helpers import _mx, _para, _rect
from ..registry import register_renderer


@register_renderer("title")
def _render_title(prs, p, th, rtl, number):
    s = p.slide
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    _background(slide, th.title_background)
    _rect(slide, MARGIN, 3.55, 1.6, 0.08, th.accent2, rtl)
    w = SLIDE_W - 2 * MARGIN
    title, sub = slide.shapes.title, slide.placeholders[1]
    for shp, y, h in ((title, 1.6, 1.8), (sub, 3.85, 1.3)):
        shp.left, shp.top = Inches(_mx(MARGIN, w, rtl)), Inches(y)
        shp.width, shp.height = Inches(w), Inches(h)
        shp.text_frame.word_wrap = True
    title.text_frame.vertical_anchor = MSO_ANCHOR.BOTTOM
    size = 46 if len(s.title) <= 50 else 36
    _para(
        title.text_frame,
        True,
        s.title,
        size,
        th.title_text,
        th.font_heading,
        rtl,
        bold=True,
    )
    _para(sub.text_frame, True, s.subtitle or "", 24, th.title_text, th.font_body, rtl)
    if s.speaker_notes:
        slide.notes_slide.notes_text_frame.text = s.speaker_notes
