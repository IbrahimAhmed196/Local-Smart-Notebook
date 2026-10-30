"""Compatibility imports for the modular PowerPoint renderer."""
from app.tools.pptx import build_pptx
from app.tools.pptx.language import detect_language, detect_rtl
from app.tools.pptx.planning import Planned, _layout_of, plan_slides
from app.tools.pptx.registry import _RENDERERS
