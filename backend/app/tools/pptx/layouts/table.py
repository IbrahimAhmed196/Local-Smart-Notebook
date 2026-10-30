from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches
from ..constants import BODY_H, BODY_TOP, MARGIN, SLIDE_W
from ..frames import _content_slide
from ..helpers import _fmt_cell, _is_number, _mx, _para, _rgb, _textbox
from ..registry import register_renderer


@register_renderer("table")
def _render_table(prs, p, th, rtl, number):
    s = p.slide
    slide = _content_slide(prs, p, th, rtl, number)
    t = s.table
    w = SLIDE_W - 2 * MARGIN
    top = BODY_TOP
    if t.title:  # a small caption above the table
        _, cf = _textbox(slide, MARGIN, top - 0.05, w, 0.4, rtl)
        _para(
            cf, True, t.title, 14, th.muted, th.font_body, rtl, italic=True, space_after=0
        )
        top += 0.45
    texts = [s_.text for s_ in s.bullets]
    bullets_h = 1.2 if texts else 0
    n_rows, n_cols = len(t.rows) + 1, len(t.columns)
    row_h = min(0.55, (BODY_TOP + BODY_H - top - bullets_h) / n_rows)
    frame = slide.shapes.add_table(
        n_rows,
        n_cols,
        Inches(_mx(MARGIN, w, rtl)),
        Inches(top),
        Inches(w),
        Inches(row_h * n_rows),
    )
    table = frame.table
    if rtl:
        frame._element.graphic.graphicData.tbl.tblPr.set("rtl", "1")
    size = 16 if n_cols <= 3 else 14 if n_cols <= 5 else 12
    for c in range(n_cols):
        table.columns[c].width = Inches(w / n_cols)
    for r in range(n_rows):
        table.rows[r].height = Inches(row_h)
        for c in range(n_cols):
            cell = table.cell(r, c)
            header = r == 0
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(
                th.primary if header else (th.card if r % 2 else th.background)
            )
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_top = cell.margin_bottom = Inches(0.03)
            value = t.columns[c] if header else t.rows[r - 1][c]
            numeric = not header and _is_number(value)
            align = (
                PP_ALIGN.LEFT if (numeric and rtl) else PP_ALIGN.RIGHT if numeric else None
            )
            _para(
                cell.text_frame,
                True,
                value if header else _fmt_cell(value),
                size,
                "FFFFFF" if header else th.text,
                th.font_body,
                rtl,
                bold=header,
                align=align,
                space_after=0,
            )
    if texts:
        y = top + row_h * n_rows + 0.2
        _, tf = _textbox(slide, MARGIN + 0.1, y, w - 0.2, BODY_TOP + BODY_H - y, rtl)
        for i, text in enumerate(texts):
            _para(
                tf, i == 0, text, 18, th.text, th.font_body, rtl, bullet=True, space_after=6
            )
