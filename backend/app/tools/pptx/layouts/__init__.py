"""Load built-in renderers and verify registry coverage."""
from .title import _render_title
from .text import _render_bullets, _render_closing, _render_two_columns
from .chart import _render_chart
from .table import _render_table
from ..registry import _RENDERERS, validate_renderers

# Sources is an internal planned slide, not a selectable ARC-06 layout.
_RENDERERS["sources"] = _render_bullets
validate_renderers()
