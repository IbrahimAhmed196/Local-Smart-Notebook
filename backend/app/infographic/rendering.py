"""Rendering: validated InfographicPlan -> HTML (Jinja2 + CSS) -> PNG (headless Chromium).

    plan --build_view_model--> dict --Jinja2 template--> one self-contained HTML string
                                                           |--> .html  (as is)
                                                           '--> .png   (Playwright screenshot)

Everything is local/offline: no CDN fonts, no remote assets.
"""
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from app.infographic.schema import InfographicPlan
from app.infographic.view_model import build_view_model

TEMPLATES_DIR = Path(__file__).parent / "templates"
SUPPORTED_FORMATS = ("png", "html")
MAX_IMAGE_PIXELS = 16000          # Chromium refuses screenshots much taller than this (after scaling)

_MEDIA_TYPES = {"png": "image/png", "html": "text/html; charset=utf-8"}


class RenderingError(RuntimeError):
    """Raised when an infographic cannot be rendered (RuntimeError so router.py maps it to HTTP 502)."""


@dataclass(frozen=True)
class RenderedInfographic:
    content: bytes
    media_type: str
    extension: str


# autoescape=True is a security requirement: text comes from an LLM, and must never become markup.
_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _css() -> Markup:
    # Static file shipped with the app (trusted), inlined so the output is ONE self-contained file.
    return Markup((TEMPLATES_DIR / "styles.css").read_text(encoding="utf-8"))


def _render(plan: InfographicPlan) -> tuple[str, int]:
    vm = build_view_model(plan)
    html = _env.get_template(f"{vm['kind']}.html").render(vm=vm, css=_css())
    return html, vm["width"]


# ----------------------------------------------------------------------------
def render_html(plan: InfographicPlan) -> str:
    """Self-contained HTML document for the infographic."""
    return _render(plan)[0]


def render_png(plan: InfographicPlan, scale: float = 2.0) -> bytes:
    """Screenshot of the infographic. scale=2 gives a sharp "retina" image."""
    html, width = _render(plan)

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RenderingError(
            "PNG export needs Playwright. Install it with:  pip install playwright  "
            "and then:  playwright install chromium"
        ) from exc

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=scale)
                page.set_content(html, wait_until="load")
                page.evaluate("document.fonts.ready.then(() => true)")
                height = page.locator("#infographic").bounding_box()["height"]

                if height * scale > MAX_IMAGE_PIXELS:         # very long infographic: lower the scale
                    page.close()
                    scale = max(1.0, MAX_IMAGE_PIXELS / height)
                    page = browser.new_page(viewport={"width": width, "height": 900}, device_scale_factor=scale)
                    page.set_content(html, wait_until="load")

                return page.locator("#infographic").screenshot(type="png")
            finally:
                browser.close()
    except PlaywrightError as exc:
        raise RenderingError(
            f"Could not render the PNG ({str(exc).splitlines()[0]}). "
            "If Chromium is missing, run:  playwright install chromium"
        ) from exc


def render_infographic(plan: InfographicPlan, output_format: str = "png", scale: float = 2.0) -> RenderedInfographic:
    """Main entry point used by the API."""
    fmt = output_format.lower()
    if fmt == "html":
        return RenderedInfographic(render_html(plan).encode("utf-8"), _MEDIA_TYPES["html"], "html")
    if fmt == "png":
        return RenderedInfographic(render_png(plan, scale), _MEDIA_TYPES["png"], "png")
    raise RenderingError(f"Unsupported output format '{output_format}'. Use one of: {', '.join(SUPPORTED_FORMATS)}.")


def render_to_file(plan: InfographicPlan, path: str | Path, scale: float = 2.0) -> Path:
    """Render and save; the format comes from the file extension (.png / .html)."""
    path = Path(path)
    result = render_infographic(plan, path.suffix.lstrip("."), scale)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(result.content)
    return path
