import json
from types import SimpleNamespace

import pandas as pd
import pytest

from app.agents.slide_content_agent import (
    MAX_ATTEMPTS,
    MAX_BULLETS,
    NUM_CTX,
    TEMPERATURE,
    generate_presentation_content,
    generate_slide_content,
)
from app.core.config import settings
from app.llm import ollama_client
from app.schemas.slide_content import (
    SLIDE_LAYOUTS,
    Bullet,
    ChartSpec,
    PresentationContent,
    SlideContentDraft,
    SourceChunk,
    TableSpec,
)
from app.schemas.slides import PresentationOutlineResponse, SlideOutlineItem
from app.tools.chart_tool import DataSource, sources_from_documents
from tests.slide_samples import (
    SAMPLES_DIR,
    SALES_DOCUMENT_ID,
    FakeClient,
    build_sample_deck,
    mock_chunks,
    mock_outline,
    sales_source,
    slide_number_of,
)
from requests.exceptions import Timeout


def item(layout="bullet_points", number=2, title="Key Findings", purpose="Summarise the results"):
    return SlideOutlineItem(slide_number=number, title=title, purpose=purpose, layout_type=layout)


def write(item_, client, chunks=None, data_files=(), **kw):
    return generate_slide_content(
        item_,
        presentation_title="Sales Review 2025",
        audience="Management team",
        chunks=mock_chunks(item_.slide_number) if chunks is None else chunks,
        data_files=data_files,
        client=client,
        **kw,
    )


def draft(*bullets, **kw):
    return SlideContentDraft(bullets=[Bullet(text=t, source_ids=ids) for t, ids in bullets], **kw)


# ---------------------------------------------------------------- bullets, citations, ids

def test_bullet_slide_keeps_the_text_and_turns_aliases_into_real_chunk_ids():
    client = FakeClient.sequence(
        draft(("Revenue grew 12 percent", ["S1"]), ("Phones missed the target", ["S2", "S1"]), speaker_notes="  Say this.  ")
    )
    slide = write(item(), client)

    assert [b.text for b in slide.bullets] == ["Revenue grew 12 percent", "Phones missed the target"]
    assert slide.bullets[0].source_ids == ["doc2-s2-a"]
    assert slide.bullets[1].source_ids == ["doc2-s2-b", "doc2-s2-a"]
    assert [(c.source_id, c.filename, c.page) for c in slide.citations] == [
        ("doc2-s2-a", "sales_report.pdf", 2),
        ("doc2-s2-b", "sales_report.pdf", 3),
    ]
    assert slide.speaker_notes == "Say this."
    assert slide.warnings == [] and slide.layout_type == "bullet_points"

    (call,) = client.calls
    assert "[S1]" in call["prompt"] and "[S2]" in call["prompt"]
    assert "doc2-s2-a" not in call["prompt"]  # the model only ever sees short ids
    assert call["schema"] is SlideContentDraft
    assert call["temperature"] == TEMPERATURE == 0.1 and call["num_ctx"] == NUM_CTX


def test_a_cited_id_that_does_not_exist_makes_the_agent_ask_once_more(
    scripted_llm,
):
    client = scripted_llm(
        draft(("Wrong", ["S9"])),
        draft(("Right", ["S1"])),
    )

    slide = write(item(), client)

    assert len(client.calls) == 2
    assert "CORRECTION" not in client.calls[0]["prompt"]
    assert "CORRECTION" in client.calls[1]["prompt"]
    assert "S9" in client.calls[1]["prompt"]

    assert [bullet.text for bullet in slide.bullets] == ["Right"]
    assert slide.bullets[0].source_ids == ["doc2-s2-a"]
    assert slide.warnings == []

def test_ids_that_are_still_invalid_after_the_retry_are_removed_and_reported():
    client = FakeClient.sequence(draft(("A", ["S9", "S1"])), draft(("B", ["S9", "S1"])))
    slide = write(item(), client)

    assert len(client.calls) == MAX_ATTEMPTS == 2
    assert slide.bullets[0].text == "B" and slide.bullets[0].source_ids == ["doc2-s2-a"]
    assert any("S9" in w for w in slide.warnings)
    real_ids = {c.chunk_id for c in mock_chunks(2)}
    assert {i for b in slide.bullets for i in b.source_ids} <= real_ids
    assert {c.source_id for c in slide.citations} <= real_ids


def test_a_bullet_without_a_citation_is_kept_but_reported():
    slide = write(item(), FakeClient.sequence(draft(("Cited", ["S1"]), ("Not cited", []))))
    assert [b.text for b in slide.bullets] == ["Cited", "Not cited"]
    assert len(slide.warnings) == 1 and slide.warnings[0].startswith("Slide 2 ('Key Findings'): ")
    assert slide.warnings[0].endswith("1 bullet(s) have no citation.")


def test_with_no_sources_nothing_can_be_cited_and_the_model_is_told_so():
    client = FakeClient.sequence(draft(("General", ["S1"])), draft(("General", ["S1"])))
    slide = write(item(), client, chunks=[])
    assert "No source text was found" in client.calls[0]["prompt"]
    assert slide.bullets[0].source_ids == [] and slide.citations == []


def test_only_the_first_chunks_are_shown_and_long_text_is_cut():
    many = [SourceChunk(chunk_id=f"c{i}", document_id=1, filename="f.txt", text="x" * 5000) for i in range(20)]
    client = FakeClient.sequence(draft(("ok", ["S1"])))
    write(item(), client, chunks=many)
    prompt = client.calls[0]["prompt"]
    assert "[S6]" in prompt and "[S7]" not in prompt
    assert "x" * 900 in prompt and "x" * 901 not in prompt  # each chunk is cut to 900 characters


# ---------------------------------------------------------------- layouts

def test_title_slide_has_only_a_subtitle():
    client = FakeClient.sequence(draft(("ignored", ["S1"]), subtitle=" Big picture ", speaker_notes="Welcome."))
    slide = write(item("title", 1, "Sales Review 2025"), client, chunks=[])
    assert slide.subtitle == "Big picture" and slide.bullets == [] and slide.layout_type == "title"


def test_two_columns_keeps_both_columns_and_other_layouts_drop_the_right_one():
    two = SlideContentDraft(
        bullets=[Bullet(text="L", source_ids=["S1"])], right_bullets=[Bullet(text="R", source_ids=["S2"])]
    )
    slide = write(item("two_columns", 3), FakeClient.sequence(two))
    assert [b.text for b in slide.bullets] == ["L"] and [b.text for b in slide.right_bullets] == ["R"]
    assert [c.source_id for c in slide.citations] == ["doc2-s3-a", "doc2-s3-b"]

    single = write(item("bullet_points"), FakeClient.sequence(two))
    assert single.right_bullets == []


def test_bullets_are_trimmed_to_the_layout_limit_and_blank_ones_dropped():
    many = draft(*[(f"point {i}", ["S1"]) for i in range(12)], ("   ", ["S1"]), ("• dotted", ["S1"]))
    many.bullets.insert(0, Bullet(text="   "))
    slide = write(item("bullet_points"), FakeClient.sequence(many))
    assert len(slide.bullets) == MAX_BULLETS["bullet_points"] == 6
    assert slide.bullets[0].text == "point 0"
    assert all(b.text.strip() for b in slide.bullets)
    dotted = write(item(), FakeClient.sequence(draft(("• dotted", ["S1"]))))
    assert dotted.bullets[0].text == "dotted"


@pytest.mark.parametrize("raw", ["Bullets", "two column", "TWO-COLUMNS", "bullet_points"])
def test_layout_names_are_tolerated(raw):
    slide = write(item(raw), FakeClient.sequence(draft(("x", ["S1"]))))
    assert slide.layout_type in SLIDE_LAYOUTS and slide.warnings == []


def test_an_unknown_layout_becomes_bullet_points_with_a_warning():
    slide = write(item("timeline"), FakeClient.sequence(draft(("x", ["S1"]))))
    assert slide.layout_type == "bullet_points"
    assert any("timeline" in w for w in slide.warnings)


# ---------------------------------------------------------------- charts and tables

def test_chart_values_come_from_the_file_and_the_model_never_sees_them():
    spec = ChartSpec(chart_type="bar", title="Revenue", document_id=SALES_DOCUMENT_ID, x_column="region", y_columns=["revenue"])
    client = FakeClient.sequence(draft(("North leads", ["S1"]), chart=spec))
    slide = write(item("chart", 4), client, data_files=[sales_source()])

    assert slide.layout_type == "chart" and slide.table is None
    assert slide.chart.categories == ["North", "South", "East", "West"]
    assert slide.chart.series[0].values == [200000.0, 155000.0, 122000.0, 155000.0]  # computed by pandas
    prompt = client.calls[0]["prompt"]
    assert 'document_id=1, file "sample_sales.csv"' in prompt and "Region (text)" in prompt and "Revenue (number)" in prompt
    assert "120000" not in prompt and "200000" not in prompt and "Laptops" not in prompt  # no cell values


def test_a_chart_naming_a_missing_column_is_dropped_and_the_slide_still_works():
    spec = ChartSpec(chart_type="bar", title="x", document_id=SALES_DOCUMENT_ID, x_column="Region", y_columns=["Profit"])
    slide = write(item("chart", 4), FakeClient.sequence(draft(("North leads", ["S1"]), chart=spec)), data_files=[sales_source()])
    assert slide.chart is None and slide.layout_type == "bullet_points"
    assert slide.bullets[0].text == "North leads"
    assert any("Chart dropped" in w and "Profit" in w and w.startswith("Slide ") for w in slide.warnings)


def test_a_chart_slide_without_any_chart_choice_falls_back_to_bullets():
    slide = write(item("chart", 4, purpose="Show revenue"), FakeClient.sequence(SlideContentDraft()), data_files=[sales_source()])
    assert slide.layout_type == "bullet_points" and slide.chart is None
    assert [b.text for b in slide.bullets] == ["Show revenue"]  # never an empty slide
    assert any("did not choose" in w for w in slide.warnings)


@pytest.mark.parametrize("layout", ["chart", "table"])
def test_a_data_slide_without_a_spreadsheet_falls_back_to_bullets(layout):
    client = FakeClient.sequence(draft(("x", ["S1"])))

    slide = write(item(layout, 4), client, data_files=[])

    assert slide.layout_type == "bullet_points"
    assert slide.chart is None
    assert slide.table is None

    prompt = client.calls[0]["prompt"]
    lines = prompt.splitlines()

    assert "LAYOUT: bullet_points" in lines

    # General instructions may mention DATA FILES,
    # but no spreadsheet catalog should be included.
    assert not any(
        line.startswith("DATA FILES (spreadsheets you may use")
        for line in lines
    )

    assert any("No spreadsheet" in warning for warning in slide.warnings)


def test_table_cells_come_from_the_file():
    spec = TableSpec(title="Rows", document_id=SALES_DOCUMENT_ID, columns=["Region", "Revenue"], max_rows=2)
    slide = write(item("table", 5), FakeClient.sequence(draft(("Rows", ["S1"]), table=spec)), data_files=[sales_source()])
    assert slide.layout_type == "table" and slide.chart is None
    assert slide.table.columns == ["Region", "Revenue"]
    assert slide.table.rows == [["North", 120000], ["North", 80000]]


def test_a_chart_on_a_slide_that_is_not_a_chart_slide_is_ignored():
    spec = ChartSpec(chart_type="bar", title="x", document_id=SALES_DOCUMENT_ID, x_column="Region", y_columns=["Revenue"])
    slide = write(item("bullet_points"), FakeClient.sequence(draft(("x", ["S1"]), chart=spec)), data_files=[sales_source()])
    assert slide.chart is None and slide.table is None


# ---------------------------------------------------------------- failures

def test_a_failed_llm_call_gives_a_valid_placeholder_slide_instead_of_an_error():
    slide = write(item(purpose="Summarise the results"), FakeClient.sequence(RuntimeError("Ollama is down")))
    assert slide.bullets == [Bullet(text="Summarise the results")]
    assert slide.layout_type == "bullet_points"
    assert any("Ollama is down" in w for w in slide.warnings)


def test_a_failed_title_slide_stays_a_title_slide():
    slide = write(item("title", 1, "Sales Review 2025"), FakeClient.sequence(RuntimeError("down")), chunks=[])
    assert slide.layout_type == "title" and slide.bullets == []


def test_if_the_retry_fails_the_first_draft_is_kept():
    client = FakeClient.sequence(draft(("First", ["S9", "S1"])), RuntimeError("down"))
    slide = write(item(), client)
    assert slide.bullets[0].text == "First" and slide.bullets[0].source_ids == ["doc2-s2-a"]


# ---------------------------------------------------------------- the whole deck

def test_the_deck_is_written_one_slide_at_a_time_in_slide_order_with_only_that_slides_sources(
    scripted_llm,
):
    outline = mock_outline()
    outline.slides.reverse()

    marks = {
        number: f"UNIQUE-TEXT-FOR-SLIDE-{number}"
        for number in range(1, 6)
    }

    def chunks_for(slide):
        return [
            SourceChunk(
                chunk_id=f"c{slide.slide_number}",
                document_id=2,
                filename="r.pdf",
                text=marks[slide.slide_number],
            )
        ]

    client = scripted_llm(
        *(draft(("x", ["S1"])) for _ in range(5))
    )
    progress = []

    deck = generate_presentation_content(
        outline,
        chunks_for_slide=chunks_for,
        data_files=[sales_source()],
        client=client,
        on_progress=lambda done, total: progress.append((done, total)),
    )

    assert [
        slide_number_of(call["prompt"]) for call in client.calls
    ] == [1, 2, 3, 4, 5]

    assert [slide.slide_number for slide in deck.slides] == [1, 2, 3, 4, 5]
    assert progress == [(1, 5), (2, 5), (3, 5), (4, 5), (5, 5)]

    for call in client.calls:
        number = slide_number_of(call["prompt"])
        assert marks[number] in call["prompt"]
        assert all(
            marks[other] not in call["prompt"]
            for other in marks
            if other != number
        )

    assert deck.presentation_title == "Sales Review 2025"
    assert deck.target_audience == "Management team"


def test_one_failed_slide_does_not_lose_the_deck(scripted_llm):
    client = scripted_llm(
        # Slide 1 has no sources: return a title draft without citations.
        SlideContentDraft(
            subtitle="Sales overview",
            speaker_notes="Welcome.",
        ),
        draft(("x", ["S1"])),       # Slide 2
        RuntimeError("bad json"),  # Slide 3
        draft(("x", ["S1"])),       # Slide 4
        draft(("x", ["S1"])),       # Slide 5
    )

    deck = generate_presentation_content(
        mock_outline(),
        chunks_for_slide=lambda slide: mock_chunks(slide.slide_number),
        client=client,
    )

    assert len(deck.slides) == 5

    # Exactly one call per slide, with no unexpected citation retries.
    assert [
        slide_number_of(call["prompt"])
        for call in client.calls
    ] == [1, 2, 3, 4, 5]

    assert any(
        "bad json" in warning
        for warning in deck.slides[2].warnings
    )
    assert any(
        "placeholder slide" in warning
        for warning in deck.slides[2].warnings
    )

    # The other slides must survive without model-call failures.
    for index in (0, 1, 3, 4):
        assert all(
            "model call failed" not in warning
            for warning in deck.slides[index].warnings
        )

def test_the_finished_deck_is_valid_json_that_round_trips():
    _, deck = build_sample_deck()
    again = PresentationContent.model_validate_json(deck.model_dump_json())
    assert again == deck
    json.dumps(deck.model_dump())


def test_the_style_is_passed_to_the_model():
    client = FakeClient.sequence(draft(("x", ["S1"])))
    write(item(), client, style="playful")
    assert "STYLE: playful" in client.calls[0]["prompt"]


# ---------------------------------------------------------------- the samples Task 3 starts from

def test_sample_files_match_what_the_code_produces():
    outline, deck = build_sample_deck()
    saved_outline = (SAMPLES_DIR / "sample_outline.json").read_text(encoding="utf-8")
    saved_deck = (SAMPLES_DIR / "sample_deck.json").read_text(encoding="utf-8")
    assert PresentationOutlineResponse.model_validate_json(saved_outline) == outline
    assert PresentationContent.model_validate_json(saved_deck) == deck, (
        "The schema or the agent changed: run `python tests/slide_samples.py` to rewrite docs/samples/"
    )
    assert {s.layout_type for s in deck.slides} == set(SLIDE_LAYOUTS)  # the sample uses every layout


# ---------------------------------------------------------------- glue

def test_documents_become_data_sources_only_for_spreadsheets_that_exist(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    folder = settings.uploads_dir / "notebook_1"
    folder.mkdir(parents=True)
    pd.DataFrame({"a": [1]}).to_csv(folder / "one.csv", index=False)
    docs = [
        SimpleNamespace(id=1, filename="sales.csv", file_path="notebook_1/one.csv", file_type="csv"),
        SimpleNamespace(id=2, filename="gone.csv", file_path="notebook_1/gone.csv", file_type="csv"),
        SimpleNamespace(id=3, filename="notes.pdf", file_path="notebook_1/one.csv", file_type="pdf"),
    ]
    sources = sources_from_documents(docs)
    assert sources == [DataSource(document_id=1, filename="sales.csv", path=folder / "one.csv")]


class FakeResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"message": {"content": self._content}}


def test_the_ollama_client_sends_the_new_options_and_keeps_its_old_defaults(monkeypatch):
    sent = []
    monkeypatch.setattr(ollama_client.requests, "post", lambda url, json, **kw: (sent.append(json), FakeResponse("{}"))[1])
    client = ollama_client.OllamaJSONClient()

    client.generate_json("p", SlideContentDraft)
    assert sent[-1]["options"] == {"temperature": 0.3}  # unchanged for Task 1's callers

    client.generate_json("p", SlideContentDraft, temperature=0.1, num_ctx=8192)
    assert sent[-1]["options"] == {"temperature": 0.1, "num_ctx": 8192}
    assert sent[-1]["model"] == client.model_name  # (the default model name is not this test's business)


# ---- tolerance for the small mistakes a 7B model makes (found in a real Ollama run) ----

def test_draft_accepts_common_model_mistakes():
    draft = SlideContentDraft.model_validate(
        {
            "bullets": ["A plain string bullet", {"text": "A normal bullet", "source_ids": "S1"}],
            "speaker_notes": ["First sentence.", "Second sentence."],
            "chart": {
                "chart_type": "Bar Chart",
                "document_id": "1",
                "sheet": "null",
                "x_column": "Region",
                "y_columns": "Revenue",
                "aggregation": "total",
            },
        }
    )
    assert [b.text for b in draft.bullets] == ["A plain string bullet", "A normal bullet"]
    assert draft.bullets[1].source_ids == ["S1"]
    assert draft.speaker_notes == "First sentence. Second sentence."
    chart = draft.chart
    assert (chart.chart_type, chart.document_id, chart.sheet, chart.y_columns, chart.aggregation) == (
        "bar", 1, None, ["Revenue"], "sum",
    )


def test_table_spec_accepts_a_column_string_and_clamps_rows():
    spec = TableSpec.model_validate({"document_id": "1", "columns": "Region, Revenue", "max_rows": "500"})
    assert spec.columns == ["Region", "Revenue"] and spec.document_id == 1 and spec.max_rows == 15


def test_empty_chart_and_table_become_none():
    draft = SlideContentDraft.model_validate({"chart": {}, "table": "null"})
    assert draft.chart is None and draft.table is None


def test_client_error_message_keeps_the_real_reason(monkeypatch):
    class Bad:
        def raise_for_status(self):
            pass

        def json(self):
            return {"message": {"content": "this is not json"}}

    monkeypatch.setattr(ollama_client.requests, "post", lambda *a, **k: Bad())
    try:
        ollama_client.OllamaJSONClient().generate_json("x", SlideContentDraft)
    except RuntimeError as exc:
        assert "Last error:" in str(exc) and "JSONDecodeError" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")

@pytest.mark.parametrize(
    "response",
    [
        "this is not JSON",
        '{"bullets": [{"text": 123}]}',
        Timeout("Model timed out"),
    ],
    ids=["invalid-json", "invalid-schema", "timeout"],
)
def test_scripted_llm_failures_produce_placeholder_slides(
    scripted_llm, response
):
    client = scripted_llm(response)

    slide = write(
        item(purpose="Summarise the results"),
        client,
    )

    assert len(client.calls) == 1
    assert slide.layout_type == "bullet_points"
    assert slide.bullets == [Bullet(text="Summarise the results")]
    assert any(
        "placeholder slide" in warning
        for warning in slide.warnings
    )