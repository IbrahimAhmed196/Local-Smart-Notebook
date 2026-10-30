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
| **names** the file, sheet and columns of a chart or table | reads the real file with pandas and computes every number (`tools/chart_tool.py`); the model sees a short description of each column (below) and, after the chart or table is built, the data facts (below), but never a number it could use without a citation |

A wrong chart or table choice (unknown file, sheet or column) is dropped and the slide becomes `bullet_points`; a failed LLM call gives a
placeholder slide. Either way the deck is still complete, and the reason is written in the slide's `warnings`.

## Chart and table checks (`check_chart`, `check_table` in `tools/chart_tool.py`)
*Week 6 presentation edits (DAT-02).* The checks return a `CheckResult`: the chart (or table) plus a list of `Issue(code, severity, message, hint)`
instead of stopping at the first problem. An **error** means nothing can be drawn (`result.ok` is false, `result.data` is `None`; this is what
GEN-06 can feed back to the model). A **warning** means it is drawn, but the reader should know; the slide writer adds the message and the hint to
the slide's `warnings`. `build_chart_data` / `build_table_data` still exist and raise `ChartToolError` (now with `.code` and `.hint`) on an error.

| code | severity | rule |
|---|---|---|
| `unknown_document`, `unknown_sheet`, `unknown_column`, `unreadable_file` | error | the spec does not match the file |
| `no_value_column`, `no_numbers`, `empty_result` | error | nothing numeric to draw (after cleaning, and after removing empty cells) |
| `pie_negative`, `pie_total_zero` | error | a pie needs values that are not negative and a total above 0 |
| `too_few_points` | error | a line needs at least 2 points, a pie at least 2 slices |
| `invalid_chart_data`, `invalid_table_data` | error | the built data fails the schema checks (for example two series with the same name) |
| `categories_truncated`, `points_truncated` | warning | more categories (bar 12, pie 8) or line points (24) than the limit: the biggest / first are kept |
| `too_many_series`, `pie_extra_series` | warning | more value columns than `chart_max_series` (4), or more than one on a pie: the first are kept |
| `scale_mismatch` | warning | one series is `chart_scale_ratio_warning` (100) times bigger than another: the small one looks flat |
| `x_looks_like_id` | warning | a bar / pie x column with almost as many different values as rows (and over the limit) |
| `duplicate_x` | warning | aggregation `none` but an x value repeats |
| `column_mostly_empty` | warning | a value column has numbers in fewer than half of its rows (the other rows are left out) |
| `line_x_not_ordered` | warning | a line whose x column is text; a date or number x column is sorted instead |
| `columns_truncated`, `rows_truncated` | warning | a table over `table_max_columns` (6) / `table_max_rows` (15) |
| `empty_column`, `long_cells` | warning | a table column empty in the rows shown; cells over `table_max_cell_chars` (60) characters |
| `formulas_not_calculated` | error | an Excel column of formulas that were never calculated (open the file in Excel, save it, upload it again) |

## The data catalog the model reads (`describe_sources`)
*Week 6 presentation edits (DAT-05).* The slide writer **and the outline step** get the same `DATA FILES` text. Each sheet shows its row count,
and each column its kind plus, in square brackets, the number of distinct values and example labels (text) or the smallest and biggest value
(number, date). Whatever a limit left out is counted ("2 more columns of this sheet are not listed"). Example:

```
DATA FILES (spreadsheets you may use; column kinds are in parentheses, details about the values are in square brackets and are not part of the column name):
- document_id=1, file "sample_sales.csv"
    (single table), 8 rows: Region (text) [4 distinct, e.g. North, South, East, West], Revenue (number) [8 distinct, 45000 to 120000], ...
```

The kind of a column is still detected from the first `catalog_sample_rows` (50) rows; the row count, distinct counts and ranges look at the whole
sheet. The catalog describes the data; it never holds a **computed** value (a sum, an average): those reach the model only as data facts.
Note that a range shows the smallest and biggest real cell value, and example labels are real labels from the file.

## Data facts for chart and table slides
*Week 6 presentation edits (DAT-06).* The model chooses a chart without seeing it, so its bullets used to be vague or invented. Now, once the chart
or table is built, Python computes simple facts from its numbers: the count, the total, the average, the highest (with its share of the total) and
the lowest category, and, for a line, the change from the first to the last point. For a table, the total and the highest / lowest row of its number
columns. They describe the categories or rows **shown**, and each says so. A total or an average is skipped for aggregation `mean`.

```
[D2] Total Revenue across the 4 categories shown: 632,000.
[D4] Highest Revenue: North with 200,000 (31.6% of the total).
```

The slide is then written a second time (a short extra model call; `SLIDE_DATA_FACTS=false` skips it) with the facts as citable sources
`D1`, `D2` ...; only the bullets and speaker notes of the second answer are used, the chart or table stays the first answer's choice. A bullet
that cites a fact but quotes a number found in none of its cited sources gets a warning. In the finished slide:

- the bullet's `source_ids` hold real ids such as `s4-D4` (the slide number keeps them unique);
- `citations` has one entry per cited fact: `source_id` `s4-D4`, `filename` the chart's source label, and **`text`** the fact itself (a new optional
  field of `Citation`; it is `null` for a document citation);
- if the second call fails, the first bullets are kept and a warning says so. The facts are plain `DataFact(fact_id, text)` objects, ready for
  OUT-04 (stat highlight) to reuse.

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
| Chart / table checks (DAT-02) | `chart_max_series`, `chart_scale_ratio_warning`, `table_max_cell_chars` | 4, 100, 60 |
| Example labels per text column (DAT-05) | `catalog_example_labels` (0 = none) | 5 |
| The facts pass (DAT-06) | `slide_data_facts` (`false` = no second call per chart / table slide) | true |
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

