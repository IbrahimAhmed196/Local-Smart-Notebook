"""PowerPoint rendering entry point."""

from .builder import build_pptx
from .themes import THEMES

__all__ = ["THEMES", "build_pptx"]
