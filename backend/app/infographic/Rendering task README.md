# Infographic - Task 3: Rendering & Templates

Pipeline:  `analysis.py` (LLM) -> `schema.py` (validate) -> `data_validation.py` (verify) -> **rendering (this task)**

    InfographicPlan --view_model--> dict --Jinja2 + CSS--> HTML --Chromium--> PNG

## Install
    pip install -r requirements-rendering.txt
    playwright install chromium

## Try it without the LLM
    python -m app.infographic.render_samples out/      # renders samples/*.json to PNG + HTML

## Use it in code
    from app.infographic.rendering import render_infographic, render_to_file
    render_to_file(plan, "output/report.png")           # or .html
    result = render_infographic(plan, "png")            # -> .content / .media_type / .extension

## New API endpoints (added to router.py)
    POST /api/infographic/render?format=png|html&scale=2      body = InfographicPlan JSON
    POST /api/infographic/generate-image?format=png|html      upload .txt -> full pipeline -> image

## Files
Placed under `app/infographic/` (tests under `tests/`). Your existing analysis.py, schema.py,
pipeline.py and data_validation.py are NOT included and need no changes.
See the chat explanation for what each file does. Run tests:  `python -m pytest -q`
