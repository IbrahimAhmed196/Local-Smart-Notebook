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

## Layouts (`SLIDE_LAYOUTS` in `schemas/slide_content.py`)
| layout | fields used |
|---|---|
| `title` | `subtitle` |
| `bullet_points` | `bullets` (up to 6) |
| `two_columns` | `bullets` = left column, `right_bullets` = right column (up to 4 each) |
| `chart` | `chart` (categories + series, already computed) and up to 3 `bullets` |
| `table` | `table` (columns + rows, already read) and up to 3 `bullets` |

Every slide also has `speaker_notes`, `citations` and `warnings`. The renderer should treat an unknown layout as `bullet_points`.

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
