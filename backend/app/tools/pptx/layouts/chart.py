from pptx.util import Inches
from app.tools import pptx_charts
from ..constants import BODY_H, BODY_TOP, MARGIN, SLIDE_W
from ..frames import _content_slide
from ..helpers import _bullet_size, _mx, _para, _textbox
from ..registry import register_renderer


@register_renderer("chart")
def _render_chart(prs, p, th, rtl, number):
    s = p.slide
    slide = _content_slide(prs, p, th, rtl, number)
    texts = [b.text for b in s.bullets]
    full_w = SLIDE_W - 2 * MARGIN
    chart_w = full_w * 0.62 if texts else full_w
    pptx_charts.add_chart(
        slide,
        s.chart,
        th,
        Inches(_mx(MARGIN, chart_w, rtl)),
        Inches(BODY_TOP),
        Inches(chart_w),
        Inches(BODY_H),
    )
    if texts:
        x = MARGIN + chart_w + 0.35
        w = full_w - chart_w - 0.35
        _, tf = _textbox(slide, x, BODY_TOP + 0.2, w, BODY_H - 0.4, rtl)
        size = _bullet_size(texts, base=20)
        for i, text in enumerate(texts):
            _para(
                tf,
                i == 0,
                text,
                size,
                th.text,
                th.font_body,
                rtl,
                bullet=True,
                space_after=12,
            )
