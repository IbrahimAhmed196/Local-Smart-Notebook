from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches
from app.tools.pptx_themes import Theme
from .constants import MARGIN, SLIDE_W
from .helpers import _mx, _para, _rect, _rgb, _textbox
from .planning import Planned


def _background(slide, color):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = _rgb(color)


def _content_slide(prs, p: Planned, th: Theme, rtl: bool, number: int):
    s = p.slide
    slide = prs.slides.add_slide(
        prs.slide_layouts[5]
    )  # "Title Only": a real title placeholder
    _background(slide, th.background)
    _rect(slide, MARGIN, 0.55, 0.1, 0.8, th.accent, rtl)
 
    title = slide.shapes.title
    w = SLIDE_W - 2 * MARGIN - 0.3
    title.left, title.top = Inches(_mx(MARGIN + 0.3, w, rtl)), Inches(0.4)
    title.width, title.height = Inches(w), Inches(1.1)
    tf = title.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    size = 34 if len(s.title) <= 55 else 28
    _para(tf, True, s.title, size, th.heading, th.font_heading, rtl, bold=True)
 
    # footer: slide number + sources
    _, nf = _textbox(slide, SLIDE_W - MARGIN - 0.8, 6.98, 0.8, 0.35, rtl)
    _para(
        nf,
        True,
        str(number),
        12,
        th.muted,
        th.font_body,
        rtl,
        align=PP_ALIGN.LEFT if rtl else PP_ALIGN.RIGHT,
    )
    footer = p.footer
    if footer:
        _, sf = _textbox(slide, MARGIN, 6.98, SLIDE_W - 2 * MARGIN - 1.0, 0.35, rtl)
        _para(sf, True, footer, 11, th.muted, th.font_body, rtl, italic=True)
 
    if s.speaker_notes:
        slide.notes_slide.notes_text_frame.text = s.speaker_notes
    return slide
