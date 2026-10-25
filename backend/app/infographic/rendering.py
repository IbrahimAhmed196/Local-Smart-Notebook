"""Rendering: validated InfographicPlan -> HTML (Jinja2 + CSS) -> PNG (headless Chromium).

    plan --build_view_model--> dict --Jinja2 template--> one self-contained HTML string
                                                           |--> .html  (as is)
                                                           '--> .png   (Playwright screenshot)

Everything is local/offline: no CDN fonts, no remote assets.
"""

from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
import asyncio
import sys
from markupsafe import Markup
from playwright.sync_api import sync_playwright

from app.infographic.schema import InfographicPlan
from app.infographic.view_model import build_view_model

import logging

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
SUPPORTED_FORMATS = ("png", "html")
MAX_IMAGE_PIXELS = 16000

_MEDIA_TYPES = {
    "png": "image/png",
    "html": "text/html; charset=utf-8",
}


class RenderingError(RuntimeError):
    """Raised when an infographic cannot be rendered."""


@dataclass(frozen=True)
class RenderedInfographic:
    content: bytes
    media_type: str
    extension: str


_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _css() -> Markup:
    """Load trusted CSS and inline it into the generated HTML."""
    css_path = TEMPLATES_DIR / "styles.css"

    try:
        return Markup(css_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RenderingError(
            f"Could not read infographic CSS: {exc}"
        ) from exc


def _render(plan: InfographicPlan) -> tuple[str, int]:
    """Render the selected Jinja template and return its HTML and width."""
    try:
        vm = build_view_model(plan)
        template = _env.get_template(f"{vm['kind']}.html")
        html = template.render(vm=vm, css=_css())
        return html, int(vm["width"])
    except RenderingError:
        raise
    except Exception as exc:
        raise RenderingError(
            f"Could not render infographic HTML: {exc}"
        ) from exc


def render_html(plan: InfographicPlan) -> str:
    """Return a self-contained HTML document."""
    return _render(plan)[0]






    # Keep your existing Playwright rendering code below.
def _render_html_to_png_sync(
    html: str,
    width: int = 1200,
    scale: float = 2.0,
) -> bytes:
    """Render HTML to PNG using synchronous Playwright in a worker thread."""

    with sync_playwright() as p:
        browser = p.chromium.launch()

        try:
            page = browser.new_page(
                viewport={"width": width, "height": 1000},
                device_scale_factor=scale,
            )

            page.set_content(html, wait_until="networkidle")

            dimensions = page.evaluate("""
                () => ({
                    width: Math.max(
                        document.documentElement.scrollWidth,
                        document.body.scrollWidth
                    ),
                    height: Math.max(
                        document.documentElement.scrollHeight,
                        document.body.scrollHeight
                    )
                })
            """)

            image_height = dimensions["height"]

            if image_height * scale > MAX_IMAGE_PIXELS:
                raise RenderingError(
                    f"Infographic is too tall: {image_height}px at "
                    f"scale {scale}. Maximum allowed height is "
                    f"{MAX_IMAGE_PIXELS}px."
                )

            return page.screenshot(
                type="png",
                full_page=True,
                scale="device",
            )

        finally:
            browser.close()


async def render_html_to_png(
    html: str,
    width: int = 1200,
    scale: float = 2.0,
) -> bytes:
    """Run synchronous Playwright outside FastAPI's event loop."""

    return await asyncio.to_thread(
        _render_html_to_png_sync,
        html,
        width,
        scale,
    )
async def render_infographic(
    plan: InfographicPlan,
    output_format: str = "png",
    scale: float = 2.0,
) -> RenderedInfographic:
    """Render an infographic as HTML or PNG."""
    fmt = output_format.lower()

    if fmt == "html":
        return RenderedInfographic(
            content=render_html(plan).encode("utf-8"),
            media_type=_MEDIA_TYPES["html"],
            extension="html",
        )

    if fmt == "png":
        html, width = _render(plan)

        png_bytes = await render_html_to_png(
            html,
            width=width,
            scale=scale,
        )

        return RenderedInfographic(
            content=png_bytes,
            media_type=_MEDIA_TYPES["png"],
            extension="png",
        )

    raise RenderingError(
        f"Unsupported output format '{output_format}'. "
        f"Use one of: {', '.join(SUPPORTED_FORMATS)}."
    )


async def render_to_file(
    plan: InfographicPlan,
    path: str | Path,
    scale: float = 2.0,
) -> Path:
    """Render an infographic and save it using the file extension."""
    path = Path(path)
    output_format = path.suffix.lstrip(".").lower()

    result = await render_infographic(
        plan,
        output_format=output_format,
        scale=scale,
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result.content)

    return path

