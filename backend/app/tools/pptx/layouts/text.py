from ..constants import BODY_H, BODY_TOP, MARGIN, SLIDE_W
from ..frames import _content_slide
from ..helpers import _bullet_size, _para, _rect, _textbox
from ..registry import register_renderer


@register_renderer("bullet_points")
def _render_bullets(prs, p, th, rtl, number):
    s = p.slide
    slide = _content_slide(prs, p, th, rtl, number)
    texts = [b.text for b in s.bullets]
    _, tf = _textbox(slide, MARGIN + 0.1, BODY_TOP, SLIDE_W - 2 * MARGIN - 0.2, BODY_H, rtl)
    size = _bullet_size(texts)
    for i, text in enumerate(texts):
        _para(
            tf, i == 0, text, size, th.text, th.font_body, rtl, bullet=True, space_after=14
        )


@register_renderer("closing")
def _render_closing(prs, p, th, rtl, number):
    s = p.slide
    slide = _content_slide(prs, p, th, rtl, number)
    texts = [b.text for b in s.bullets]
    _rect(slide, MARGIN, BODY_TOP, SLIDE_W - 2 * MARGIN, BODY_H, th.card, rtl)
    _rect(slide, MARGIN, BODY_TOP, 0.12, BODY_H, th.accent2, rtl)
    _, tf = _textbox(
        slide, MARGIN + 0.5, BODY_TOP + 0.3, SLIDE_W - 2 * MARGIN - 0.9, BODY_H - 0.6, rtl
    )
    size = _bullet_size(texts, base=26)
    for i, text in enumerate(texts):
        _para(
            tf, i == 0, text, size, th.text, th.font_body, rtl, bullet=True, space_after=16
        )


@register_renderer("two_columns")
def _render_two_columns(prs, p, th, rtl, number):
    s = p.slide
    slide = _content_slide(prs, p, th, rtl, number)
    gap, col_w = 0.4, (SLIDE_W - 2 * MARGIN - 0.4) / 2
    columns = [[b.text for b in s.bullets], [b.text for b in s.right_bullets]]
    size = _bullet_size([t for col in columns for t in col], base=22)
    for i, texts in enumerate(columns):
        x = MARGIN + i * (col_w + gap)
        _rect(slide, x, BODY_TOP, col_w, BODY_H, th.card, rtl)
        _rect(slide, x, BODY_TOP, col_w, 0.1, th.accent if i == 0 else th.accent2, rtl)
        _, tf = _textbox(slide, x + 0.3, BODY_TOP + 0.35, col_w - 0.6, BODY_H - 0.6, rtl)
        for j, text in enumerate(texts):
            _para(
                tf,
                j == 0,
                text,
                size,
                th.text,
                th.font_body,
                rtl,
                bullet=True,
                space_after=12,
            )
