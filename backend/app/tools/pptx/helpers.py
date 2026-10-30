from lxml import etree
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt
from .constants import SLIDE_W


def _rgb(hex_color: str) -> RGBColor:
    return RGBColor.from_string(hex_color)


def _mx(x: float, w: float, rtl: bool) -> float:
    """Mirror a horizontal position for right-to-left decks."""
    return SLIDE_W - x - w if rtl else x


def _style_run(run, size, color, font, bold=False, italic=False):
    f = run.font
    f.size, f.bold, f.italic, f.name = Pt(size), bold, italic, font
    f.color.rgb = _rgb(color)
    rpr = run._r.get_or_add_rPr()  # complex-script font, so Arabic text keeps a real font
    if rpr.find(qn("a:cs")) is None:
        cs = etree.SubElement(rpr, qn("a:cs"))
        cs.set("typeface", "Arial")
        latin = rpr.find(qn("a:latin"))
        if latin is not None:
            latin.addnext(cs)


def _para(
    tf,
    first,
    text,
    size,
    color,
    font,
    rtl,
    bold=False,
    italic=False,
    bullet=False,
    align=None,
    space_after=8,
):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    run = p.add_run()
    run.text = text
    _style_run(run, size, color, font, bold, italic)
    p.space_after = Pt(space_after)
    p.alignment = align or (PP_ALIGN.RIGHT if rtl else PP_ALIGN.LEFT)
    ppr = p._p.get_or_add_pPr()
    if rtl:
        ppr.set("rtl", "1")
    if bullet:
        indent = Inches(0.35)
        ppr.set("marR" if rtl else "marL", str(int(indent)))
        ppr.set("indent", str(-int(indent)))
        bu = etree.SubElement(ppr, qn("a:buChar"))
        bu.set("char", "\u2022")
    return p


def _textbox(slide, x, y, w, h, rtl, anchor=MSO_ANCHOR.TOP):
    box = slide.shapes.add_textbox(Inches(_mx(x, w, rtl)), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.auto_size = MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE  # safety net; sizes are chosen below
    return box, tf


def _rect(slide, x, y, w, h, fill, rtl, shape=MSO_SHAPE.RECTANGLE):
    shp = slide.shapes.add_shape(
        shape, Inches(_mx(x, w, rtl)), Inches(y), Inches(w), Inches(h)
    )
    shp.fill.solid()
    shp.fill.fore_color.rgb = _rgb(fill)
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def _bullet_size(texts: list[str], base: int = 24) -> int:
    """Pick a font size from the amount of text, so it fits without overflowing."""
    n, total = len(texts), sum(len(t) for t in texts)
    size = base
    if n > 4 or total > 360:
        size = base - 4
    if n > 5 or total > 520:
        size = base - 6
    if total > 700:
        size = base - 8
    return max(size, 14)


def _fmt_cell(value) -> str:
    """Table cells arrive as str / int / float / None from Task 2's file reader."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, float):
        return f"{int(value):,}" if value.is_integer() else f"{value:,.2f}"
    return str(value)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
