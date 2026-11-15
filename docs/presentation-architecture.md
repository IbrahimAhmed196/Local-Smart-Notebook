# Presentation feature: architecture and developer guide

Status: current as of the ARC-08 to ARC-11 refactor (DOC-01). It replaces the ARC-01 *target* structure with the structure that
exists in the code. The decisions of ARC-01 (approved 26 October 2026) still hold and are kept in sections 4 and 5.

Related documents: `docs/presentations.md` (using the feature and its HTTP API), `docs/presentation-jobs.md` (job states, JOB-01),
`docs/slide-content-contract.md` (what the slide writer takes and returns), `docs/backend-structure.md` (the whole backend, and an
old-to-new table of every file that moved).

## 1. The idea in one paragraph

A presentation is made in a background job. The job reads the notebook's documents, asks the local model for an **outline** (which
slides, which layout each), then writes the **content of each slide** one at a time, and finally **draws** a `.pptx`. The model
never produces a number for a chart or table: it only *names* a file, a sheet and columns, and pandas computes the values
(`presentations/data/`). Everything the model cites is mapped back to a real source. Each step sits behind a small interface
(section 5), so it can be replaced or tested with a fake.

## 2. Where everything lives

```
backend/app/
  api/presentations.py            HTTP routes and ownership checks only
  schemas/presentations.py        request / response models of the HTTP API (not the slide models)
  services/presentation_service.py  use-cases: create, list, get, get_deck, get_download, update_deck, delete
  presentations/                  the whole generation pipeline
    runner.py                     the background job: status, stage, errors, restart recovery
    generator.py                  runs the steps in order; get_generator() is the one override point
    interfaces.py                 the Protocols (the contract between the steps)
    outline.py                    generate_outline(), clean_outline()
    slide_content_agent.py        the slide writer: one LLM call per slide, checks, retries, fallbacks
    citation_validator.py         every cited id must be a source given to that slide
    rendering.py                  render_deck(): saved options -> build_pptx -> artifact path
    repository.py                 selected_documents(): the DB helper shared by service and runner
    context/                      documents -> source chunks (chunks.py); context schemas (schemas.py)
    prompts/                      outline.py and slide_content.py (the prompt texts; LAYOUT_RULES lives here)
    schemas/                      layouts.py (the layout registry), slides.py (outline), slide_content.py (slide content)
    data/                         spreadsheet data: limits, models, reader, cleaning, catalog, chart_builder, table_builder, facts
    pptx/                         the renderer: build_pptx, themes, charts, registry, planning, layouts/
  llm/                            shared with chat: LlmClient Protocol, Ollama client, errors, cancellation
  jobs/manager.py                 the single-worker job queue
tests/presentations/              every presentation test (section 9)
```

Modules are kept small on purpose: nothing in `presentations/data/` or `presentations/pptx/` is over about 200 lines, so one file is
one idea. `slide_content_agent.py` (about 390 lines) is the largest and is a candidate for a later split.

## 3. How a request flows

```
POST /notebooks/{id}/presentations
  api/presentations.py
   └ presentation_service.create_presentation()     validate, insert the row as PENDING, submit the job
      └ jobs.manager.submit(runner.run_generation, id)
         └ runner.run_generation(id)                 owns the DB session; every step below updates status and stage
            ├ generator.get_generator()              <- the single override point for tests
            ├ generator.prepare(...)                 readiness check of Ollama and the model
            ├ generator.read_context(documents)      chunks of the documents + the CSV/XLSX sources
            ├ generator.outline(options, sources)    outline.generate_outline(...)  -> PresentationOutlineResponse
            ├ generator.write_slides(...)            slide_content_agent.generate_presentation_content(...)
            │    └ per slide: LLM draft -> checks (data, citations, limits) -> SlideContent
            └ rendering.render_deck(p, deck)         pptx.build_pptx(...) -> data/artifacts/...
```

On any exception the runner sets `FAILED` and stores the message (`generation_error_message`). At start-up
`runner.fail_interrupted_jobs()` marks jobs left over from a restart. Editing a deck by hand (`PUT .../deck`) also goes through
`rendering.render_deck`. The job states and the planned cancel / resume / regenerate behaviour are in `docs/presentation-jobs.md`.

## 4. Dependency rules (ARC-01, still in force)

1. One direction: `api > service > runner > generator > (context, outline, slide writer, data, renderer) > llm`. Nothing imports upwards.
2. Only the API layer (`api/presentations.py` and `schemas/presentations.py`), the service, `main.py` (start-up recovery) and tests import `app.presentations`. The service must not import
   `requests`, `llm`, `tools` or the pipeline internals; it may import the runner only to submit a job.
3. Only `generator.get_generator()` creates a concrete client. Outline, context and the slide writer receive an `LlmClient`.
4. The pipeline is database-free: generator, outline, context and the slide writer receive plain data. Only the runner and the
   service open sessions or commit.
5. Call override points through the module: the runner uses `generator.get_generator()` at call time, never
   `from ... import get_generator`, so `monkeypatch.setattr(generator, "get_generator", ...)` keeps working.
6. Cancellation is never an LLM error: `GenerationCancelled` is not an `LlmError`.
7. Limits of the data layer are read as `limits.NAME` when they are used, never copied with `from .limits import NAME`.
   Then a test (or the settings) changes a limit in one place.
8. `presentations/pptx/` and `presentations/data/` know nothing about the LLM. `presentations/schemas/layouts.py` imports nothing from
   the app, so every layer can use it without a circular import.

## 5. The interfaces (`presentations/interfaces.py`, `llm/base.py`)

| Protocol | Boundary | Implemented by | Called by |
|---|---|---|---|
| `LlmClient` | steps <-> model | `OllamaJSONClient`; `ScriptedLLMClient` (test fake) | outline, slide writer |
| `ContextProvider` | generator <-> context | planned (CTX-*, RAG-*); `context/chunks.py` does the job today | generator |
| `OutlineGenerator` | generator <-> outline | `outline.generate_outline` | generator |
| `SlideWriter` | generator <-> slide agent | `generate_presentation_content` | generator |
| `DeckGenerator` | runner <-> generator | `LocalLlmDeckGenerator`; the fake in `tests/presentations/conftest.py` | runner |

`DeckGenerator` has the stage methods the runner calls (`prepare`, `read_context`, `outline`, `write_slides`) and `generate(...)`, the
whole deck in one call, for direct callers. **Change rule:** a Protocol changes only in the same pull request that updates every
implementation, every caller and the test fakes. Optional arguments that a later task activates (such as `cancel_event`) are declared
in advance and are not passed before then.

## 6. The three models that travel through the pipeline

| Model | File | Made by | Meaning |
|---|---|---|---|
| `PresentationOutlineResponse` / `SlideOutlineItem` | `schemas/slides.py` | outline step | title, purpose and `layout_type` per slide, no content |
| `SlideContentDraft` | `schemas/slide_content.py` | the LLM (JSON-schema constrained) | what the model writes for one slide, with short source ids (`S1`) and chart / table *specs* |
| `SlideContent` / `PresentationContent` | `schemas/slide_content.py` | the slide writer | the finished slide: real chunk ids, computed chart / table data, `warnings`; this is what the renderer draws and what is stored |

`docs/samples/sample_outline.json` and `sample_deck.json` show each of them with one slide of every layout.

## 7. The registries

**Layouts** (`schemas/layouts.py`): `LAYOUTS` holds, per layout, its name, aliases, bullet limits, word limit, columns and the fields it
`required`. The schema, the outline prompt, the slide prompt, the slide writer and the renderer all read it. `selectable=False` marks a
look the renderer gives to a slide that the model never chooses (`closing`). A layout whose `required` contains `chart` or `table` is a
data layout (`DATA_LAYOUTS`) automatically. A layout without a renderer fails when the app starts
(`RuntimeError: Renderer mismatch: missing={...}`, from `validate_renderers()`), and `tests/presentations/test_layouts.py` fails if a
selectable layout has no prompt rule.

**Renderers** (`pptx/registry.py`): `@register_renderer("name")` puts a draw function in `_RENDERERS`. The modules in
`pptx/layouts/` register themselves when they are imported, which `pptx/layouts/__init__.py` does for each of them.

**Themes** (`pptx/themes.py`): the `THEMES` dictionary. The API validates the `theme` option against it and `GET .../options`
lists it, so nothing else needs to know a theme's name.

**Chart types** have no registry yet. The names are `Literal["bar", "line", "pie"]` in two models and a few branches (section 8.3).

## 8. How to extend it

Each checklist below was carried out on a scratch copy and finished with the test suite run. The layout one ended with all 433 tests
passing; adding a chart type left one expected failure (the pinned enum, step 5 of 8.3); adding a theme left none. The test edits are
part of the job: they keep the sample files and the pinned numbers honest.

### 8.1 Add a layout

Say the new layout is `key_point` (one or two short sentences, shown large). First decide which kind it is:

- **Renderer-only** (`selectable=False`, like `closing`): the model never picks it. Do steps 1 and 3 only.
- **Public** (the model may choose it): do everything.

Steps, in order:

1. **Registry**: add one `LayoutSpec` to `LAYOUTS` in `presentations/schemas/layouts.py`, before `closing`:
   `LayoutSpec("key_point", aliases=("takeaway",), min_bullets=1, max_bullets=2)`. `SLIDE_LAYOUTS` and `DATA_LAYOUTS` are derived;
   do not edit them. `required=(...)` lists the `SlideContent` fields that must be filled, otherwise the slide is drawn as a bullet
   slide; a layout built from a spreadsheet puts `"chart"` or `"table"` there.
2. **Prompt rule** (public layouts only): add a key to `LAYOUT_RULES` in `presentations/prompts/slide_content.py`. Write the numbers as
   `{min}` and `{max}` placeholders (for example `Write {min} to {max} short sentences ...`); they are filled from the registry, and a
   test checks that the text contains them. Tell the model which fields to leave empty.
3. **Renderer**: write a function in a module of `presentations/pptx/layouts/` (for a text layout, `text.py`) with the decorator
   `@register_renderer("key_point")` and the same signature as its neighbours, `(prs, p, th, rtl, number)`. If you created a new
   module, import its function in `presentations/pptx/layouts/__init__.py`, otherwise it is never registered. Use the helpers in
   `pptx/helpers.py` and `pptx/frames.py` so the slide gets the theme, the title, the footer and right-to-left support.
4. **Pinned layout list**: update the tuple in `test_the_registry_defines_the_layouts_the_rest_of_the_app_already_used`
   (`tests/presentations/test_layouts.py`).
5. **Sample deck**: a test requires the sample deck to contain one slide of every public layout. In
   `tests/presentations/slide_samples.py` add a `SlideOutlineItem` to `mock_outline()` and a `SlideContentDraft` for the same slide
   number to `sample_drafts()`. Then regenerate the two JSON files from the repository root:
   `PYTHONPATH=.:backend python tests/presentations/slide_samples.py`, and commit them (`docs/samples/`).
6. **Tests that count the sample slides**: the sample deck is 5 slides today, and a few tests pin that number. After step 5 run the
   suite and raise each one: `content 0/5` in `test_presentation_runner.py`; in `test_slide_content.py` the scripted answers
   (`range(5)` and the failed-slide sequence), the slide-number lists (`[1, 2, 3, 4, 5]` and the `(n, 5)` progress pairs), the `marks`
   range and the `len(deck.slides) == 5` checks; in `test_pptx_tool.py` the number and count of the slide it appends. The failures
   name the exact lines, and none of them needs more than a number changed.

The model sees the new layout without any further change: the outline prompt and the JSON schema list `SLIDE_LAYOUTS`. A layout that
needs a **new content field** (beyond `subtitle`, `bullets`, `right_bullets`, `chart`, `table`) is a bigger change: add the field to
`SlideContentDraft` and `SlideContent` in `schemas/slide_content.py`, copy it in `_finish_slide` in `slide_content_agent.py`, and
extend `docs/slide-content-contract.md`. Try to reuse an existing field first.

### 8.2 Add a theme

Add one `Theme(...)` entry to `THEMES` in `presentations/pptx/themes.py` (copy an existing one and change the colours and fonts). The
API validation and the options endpoint read the dictionary. To have the renderer test cover it, add the name to the theme parameters
in `tests/presentations/test_pptx_tool.py`. No other file changes.

### 8.3 Add a chart type

Say the new type is `area`. There is no registry, so these are the places that know the three existing types:

1. `presentations/schemas/slide_content.py`: the `Literal[...]` of `ChartSpec.chart_type` **and** of `ChartData.chart_type`, and the
   synonym table `_CHART_TYPES` (so that the model's `"area chart"` is accepted).
2. `presentations/pptx/charts.py`: add the PowerPoint type to `_KINDS` (`"area": XL_CHART_TYPE.AREA`). Type-specific styling
   (`pie`, `bar`) is in `add_chart`.
3. `presentations/data/chart_builder.py`: `check_chart` has branches per type (limits for `pie` and `bar`, ordering and the point limit
   for `line`, the minimum number of points). A type that should behave like `bar` needs nothing here; anything else needs its own
   branch and, if it has its own limit, a new entry in `presentations/data/limits.py` plus a setting in `core/config.py`.
4. Prompts: the slide prompt (`prompts/slide_content.py`, the line about `chart_type`) and the outline prompt
   (`prompts/outline.py`) list `bar, line, or pie` in words.
5. Tests: `tests/test_ollama_structured_output.py` pins the enum of `chart_type`, and the builder tests are in
   `tests/presentations/test_chart_tool.py` and `test_chart_validation.py`. Add a case for the new type.

Checked on a scratch copy: with steps 1 and 2 only, an `area` chart was built from a CSV by `build_chart_data` and drawn by
`build_pptx` as a real PowerPoint area chart; the only test that failed was the pinned enum of step 5. Steps 3 and 4 are read from the
code, not exercised.

### 8.4 Change a limit or a setting

| What | Where |
|---|---|
| chart / table size limits, data catalog limits, check thresholds | `presentations/data/limits.py` (the settings-backed ones come from `core/config.py` / `.env`) |
| model, temperature, context size, retries of the slide writer | `core/config.py`: `presentation_model`, `slide_temperature`, `presentation_num_ctx`, `slide_max_attempts` |
| bullet counts and word limit per layout | the `LayoutSpec` in `presentations/schemas/layouts.py` |
| skip the extra "data facts" model call | `presentation_slide_data_facts` in `core/config.py` |

In tests, patch the limit on the module that holds it: `monkeypatch.setattr(limits, "MAX_TABLE_ROWS", 3)`.

## 9. Tests

All presentation tests are in `tests/presentations/`. The LLM client tests (`test_ollama_client.py`,
`test_ollama_structured_output.py`, `test_llm_*.py`, `test_shared_llm_defaults.py`, `test_fake_llm.py`) stay in `tests/` because the
client is shared with chat; `tests/fake_llm.py` (the scripted fake) is shared too.

| File(s) in `tests/presentations/` | What they pin |
|---|---|
| `test_presentation_service.py`, `test_presentations_api.py` | use-cases and the HTTP API |
| `test_presentation_runner.py`, `test_presentation_generator.py`, `test_presentation_outline.py` | the job, the stage order, the outline |
| `test_presentation_job_migration.py` | the job-columns migration (DB-01) |
| `test_presentation_settings.py` | that limits follow the environment (runs a subprocess) |
| `test_slide_content.py`, `test_citation_validator.py`, `test_slide_data_validation.py` | the slide writer, citations, data checks |
| `test_chart_tool.py`, `test_chart_validation.py`, `test_data_catalog.py`, `test_data_facts.py` | the `presentations/data/` package |
| `test_layouts.py`, `test_pptx_tool.py` | the layout registry and the renderer |
| `slide_samples.py`, `conftest.py` | shared samples and the fixtures `sample_deck` and `fake_generator` |

Run them from the repository root: `python -m pytest -q` (all) or `python -m pytest tests/presentations -q` (this feature only).
Useful patch points: `generator.get_generator` (the fake generator), `limits.NAME` (limits), `catalog._profile`,
`reader._SHEET_CACHE` and `reader.pd` (spreadsheet reading), `registry._RENDERERS`, `planning._layout_of`, `generator.chunks`.

Two things to know when you add a test: use `Path(__file__).resolve().parents[2]` to reach the repository root from this folder, and
a test that runs Alembic must restore the logging configuration afterwards (see `_restore_logging` in
`test_presentation_job_migration.py`), because Alembic's `fileConfig` disables loggers that other tests read through `caplog`.

## 10. Code style

`pyproject.toml` configures ruff (lint, import order and formatter; `black` gives the same result). From the repository root run
`ruff format .` and `ruff check .`. For now the configuration covers only the files of this feature; to bring another area in, add
its paths to `include` in `pyproject.toml`. Line endings are kept as each file has them.

## 11. Known gaps (planned, not done)

- Progress is still a free-text stage string and a restart marks a job `FAILED`; `docs/presentation-jobs.md` describes the target.
- `ContextProvider` is declared but the pipeline still uses `context/chunks.py` directly (CTX-*, RAG-*).
- Chart types are not a registry (section 8.3).
- `slide_content_agent.py` is long and could be split by responsibility.

## 12. History

ARC-01 module structure and interfaces; ARC-02 outline extraction; ARC-03 LLM readiness and errors; ARC-04 generator; ARC-05 runner and
repository; ARC-06 layout registry; ARC-07 settings; **ARC-11** presentation-only code moved into `presentations/`;
**ARC-10** renderer completed (`charts` and `themes` moved, the `pptx_tool` shim deleted); **ARC-09** `chart_tool.py` split into
`presentations/data/`; **ARC-08** placeholders removed, stray comments fixed, formatter configured; **DOC-01** this guide.
