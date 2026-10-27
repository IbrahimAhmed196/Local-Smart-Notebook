# Slide content (Task 2): what it takes, what it returns

`agents/slide_content_agent.py` turns the **outline** (Task 1) into the **deck JSON** that the renderer (Task 3) draws.
It writes one slide at a time with the local model (Qwen2.5-7B-Instruct through `llm/ollama_client.py`, temperature 0.1).

```python
from app.agents.slide_content_agent import generate_presentation_content

deck = generate_presentation_content(
    outline,                       # PresentationOutlineResponse from Task 1
    chunks_for_slide=my_adapter,   # callable(SlideOutlineItem) -> list[SourceChunk]   (RAG, or plain text for now)
    data_files=sources_from_documents(spreadsheet_documents),   # CSV/XLSX of the notebook (tools/chart_tool.py)
    style="professional",          # optional
    on_progress=lambda done, total: ...,   # optional: lets a background job report "slide 3 of 8"
)                                  # -> PresentationContent
```

## Who does what
| The LLM | The code |
|---|---|
| writes subtitle, bullets, speaker notes | checks that every cited id is one of the sources given for that slide (`agents/citation_validator.py`), retries once, then removes what is still invalid |
| cites sources with short ids (`S1`, `S2` ...) | maps them back to the real `chunk_id`s and builds the slide's `citations` list |
| **names** the file, sheet and columns of a chart or table | reads the real file with pandas and computes every number (`tools/chart_tool.py`); the model never sees a cell value |

A wrong chart or table choice (unknown file, sheet or column) is dropped and the slide becomes `bullet_points`; a failed LLM call gives a
placeholder slide. Either way the deck is still complete, and the reason is written in the slide's `warnings`.

## Layouts (the registry in `schemas/layouts.py`)
*Week 6 presentation edits (ARC-06).* One registry (`LAYOUTS`) holds every layout's name, aliases, bullet limits, word limit and required
fields. The schema, the outline, the prompt, the slide agent and the renderer all read it, so they cannot disagree any more
(`SLIDE_LAYOUTS` in `schemas/slide_content.py` is just the registry's list of layouts the model may choose).

| layout | fields used | bullets (the prompt asks for this, the agent trims to the max) | aliases |
|---|---|---|---|
| `title` | `subtitle` | none | |
| `bullet_points` | `bullets` | 3 to 5 | `bullets`, `bullet_point`, `bullet` |
| `two_columns` | `bullets` = left column, `right_bullets` = right column | 2 to 4 per column | `two_column`, `two_cols`, `comparison` |
| `chart` | `chart` (categories + series, already computed) and `bullets` | 1 to 3 | |
| `table` | `table` (columns + rows, already read) and `bullets` | 1 to 3 | |
| `closing` | `bullets` | 3 to 5 | `conclusion` |

`closing` is a look the renderer gives to the last text slide; the outline and the model never choose it (`selectable=False`).
Every bullet may have at most 18 words (also from the registry). Every slide also has `speaker_notes`, `citations` and `warnings`.
The renderer treats an unknown layout, or a `chart` / `table` slide without its data, as `bullet_points`.

**To add a layout:** add one `LayoutSpec` in `schemas/layouts.py`, one rule in `LAYOUT_RULES` (`llm/prompts/slide_content.py`) and one
render function in `_RENDERERS` (`tools/pptx_tool.py`). `tests/test_layouts.py` fails if the rule or the renderer is missing.

## Sample files (Task 3 can start from these)
`docs/samples/sample_outline.json`, `sample_deck.json` (one slide of every layout) and `sample_sales.csv` (the file behind the chart and table).
They are produced by `tests/slide_samples.py`; a test fails if the schema or the agent changes without rewriting them
(`python tests/slide_samples.py`).

## Running with the real model
```bash
ollama pull qwen2.5:7b-instruct      # about 4.7 GB, once
ollama serve                         # if it is not already running
```
The tests do not need Ollama: they use a fake client.

## Settings (`core/config.py`, set them in `.env`)
*Week 6 presentation edits (ARC-07).* Nothing a deployer may want to tune is hard-coded any more. Every value below has a default
equal to the old hard-coded one, so nothing changes until you set it; the full list with comments is in `.env.example`.

| What | Setting (env var, upper case) | Default |
|---|---|---|
| Model for the outline and the slides | `presentation_model` (`PRESENTATION_MODEL`) | `qwen2.5:3b` (the docs above recommend `qwen2.5:7b-instruct`) |
| Ollama URL | `ollama_base_url` (`OLLAMA_BASE_URL`, shared with chat) | `http://localhost:11434` |
| Temperatures | `outline_temperature`, `slide_temperature` | 0.3, 0.1 |
| Context window | `presentation_num_ctx` | 8192 |
| Attempts | `ollama_json_max_attempts` (bad JSON), `slide_max_attempts` (unknown source ids) | 2, 2 |
| Chart limits | `chart_max_bar_categories`, `chart_max_pie_slices`, `chart_max_line_points` | 12, 8, 24 |
| Table limits | `table_max_rows`, `table_max_columns` | 15, 6 |
| What the model is told about spreadsheets | `catalog_max_files`, `catalog_max_sheets`, `catalog_max_columns`, `catalog_sample_rows` | 5, 5, 15, 50 |

A nonsense value (for example `SLIDE_TEMPERATURE=9` or zero attempts) stops the app at start with a clear message. The limits are read
when the app starts, so restart it after changing `.env`. Not moved yet: `infographic/analysis.py` has its own Ollama call and model
constant (align it later), and the source-text limits in the slide agent (`MAX_SOURCES_PER_SLIDE`, `MAX_SOURCE_CHARS`).

## Structured output (JSON schema in Ollama's `format`)
*Week 6 presentation edits (LLM-02).* `llm/ollama_client.py` now sends the response schema itself in Ollama's `format` field instead of
the word `"json"`. Ollama then cannot produce text that is not valid JSON for that schema, and enums are respected: the outline's
`layout_type` is one of the registry layouts, and a chart's `chart_type` / `aggregation` are real values. The schema is still written in
the system prompt too.

- **Old Ollama:** a server that answers HTTP 400 to a schema is detected once, logged, and the same request is repeated with
  `format="json"` (the old mode). That repeat does not use up one of the retry attempts.
- **Switch it off:** `OLLAMA_STRUCTURED_OUTPUT=false` forces the old mode.
- **The pydantic models are unchanged**, so their tolerant validators (a string for a list, `"average"` for `"mean"`) still work in the old mode.
  The schema itself is stricter than those validators, on purpose.
- `tests/test_ollama_structured_output.py` checks that our two response schemas stay valid constraints (every `$ref` resolves, `Optional`
  fields stay nullable, fields with defaults stay optional, valid sample answers pass `jsonschema`).

### Retry rate before / after
The number of invalid-JSON retries has to be measured with the real model; the tests cannot do that. Run, with Ollama running:

```bash
python scripts/measure_json_retries.py                  # 10 outline requests per mode
python scripts/measure_json_retries.py --target slide   # 10 chart-slide requests per mode
```

and paste the tables it prints here (not measured yet):

| Target | Mode | Requests | Bad answers (retries) | Retry rate | Failed runs |
|---|---|---|---|---|---|
| outline | `format="json"` (before) | | | | |
| outline | JSON schema (after) | | | | |
| slide | `format="json"` (before) | | | | |
| slide | JSON schema (after) | | | | |

