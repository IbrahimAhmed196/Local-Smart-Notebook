"""Week 6 presentation edits (DAT-06): facts computed from a finished chart / table, cited by the slide's bullets as D1, D2 ..."""
import pytest

from app.agents.slide_content_agent import generate_slide_content
from app.core.config import settings
from app.llm.prompts.slide_content import build_slide_prompt, render_data_facts
from app.schemas.slide_content import Bullet, ChartData, ChartSpec, SeriesData, SlideContentDraft, TableData, TableSpec
from app.schemas.slides import SlideOutlineItem
from app.tools import chart_tool
from app.tools.chart_tool import DataFact, clear_sheet_cache, compute_chart_facts, compute_table_facts
from tests.slide_samples import SALES_DOCUMENT_ID, FakeClient, mock_chunks, sales_source


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_sheet_cache()
    yield
    clear_sheet_cache()


def bar(values, cats=None, chart_type="bar", name="Revenue"):
    cats = cats or [f"c{i}" for i in range(len(values))]
    return ChartData(chart_type=chart_type, title="T", categories=cats, series=[SeriesData(name=name, values=values)], source="s.csv")


def texts(facts):
    return [fact.text for fact in facts]


# ---------------------------------------------------------------- chart facts

def test_a_bar_chart_gets_count_total_average_highest_with_share_and_lowest():
    facts = compute_chart_facts(bar([200, 155, 122, 155], ["North", "South", "East", "West"]), "sum")
    assert [f.fact_id for f in facts] == ["D1", "D2", "D3", "D4", "D5"]
    assert texts(facts) == [
        "The chart shows 4 categories: from North to West.",
        "Total Revenue across the 4 categories shown: 632.",
        "Average Revenue per category: 158.",
        "Highest Revenue: North with 200 (31.6% of the total).",
        "Lowest Revenue: East with 122.",
    ]


def test_numbers_are_formatted_with_thousands_separators_and_two_decimals():
    facts = compute_chart_facts(bar([1234567.891, 2.5]), "sum")
    assert "Total Revenue across the 2 categories shown: 1,234,570.39." in texts(facts)
    assert "Highest Revenue: c0 with 1,234,567.89 (100.0% of the total)." in texts(facts)  # 99.9998% rounds to 100.0%
    assert "Lowest Revenue: c1 with 2.50." in texts(facts)


def test_a_mean_aggregation_gets_no_total_average_or_share():
    facts = compute_chart_facts(bar([10, 20, 30]), "mean")
    assert not any(t.startswith(("Total", "Average")) for t in texts(facts))
    assert "Highest Revenue: c2 with 30." in texts(facts)  # no "(x% of the total)": a sum of averages means nothing


def test_a_count_aggregation_says_it_is_a_count():
    facts = compute_chart_facts(bar([4, 2, 1], name="Region"), "count")
    assert "Total count of Region across the 3 categories shown: 7." in texts(facts)


def test_there_is_no_share_when_a_value_is_negative():
    facts = compute_chart_facts(bar([50, -20, 10]), "sum")
    assert "Highest Revenue: c0 with 50." in texts(facts)


def test_a_line_chart_gets_the_change_from_the_first_to_the_last_point():
    rising = compute_chart_facts(bar([100, 150, 250], ["Jan", "Feb", "Mar"], "line"), "none")
    assert "Revenue changed from 100 (Jan) to 250 (Mar): +150 (+150.0%)." in texts(rising)
    assert texts(rising)[0] == "The chart shows 3 points: from Jan to Mar."
    falling = compute_chart_facts(bar([200, 150], ["Q1", "Q2"], "line"), "none")
    assert "Revenue changed from 200 (Q1) to 150 (Q2): -50 (-25.0%)." in texts(falling)
    from_zero = compute_chart_facts(bar([0, 40], ["Q1", "Q2"], "line"), "none")
    assert "Revenue changed from 0 (Q1) to 40 (Q2): +40." in texts(from_zero)  # no percentage of zero


def test_a_bar_chart_has_no_change_fact_because_its_categories_have_no_order():
    assert not any("changed from" in t for t in texts(compute_chart_facts(bar([1, 2, 3]), "sum")))


def test_a_pie_chart_gets_the_share_of_its_biggest_slice():
    facts = compute_chart_facts(bar([50, 30, 20], ["a", "b", "c"], "pie"), "sum")
    assert "Highest Revenue: a with 50 (50.0% of the total)." in texts(facts)


def test_a_chart_with_one_category_has_no_average_lowest_or_change():
    assert texts(compute_chart_facts(bar([7], ["only"], "line"), "none")) == [
        "The chart shows 1 points: from only to only.",
        "Total Revenue across the 1 points shown: 7.",
        "Highest Revenue: only with 7 (100.0% of the total).",
    ]


def test_only_the_first_two_series_get_facts_and_the_total_number_is_capped():
    chart = ChartData(
        chart_type="bar", title="T", categories=["a", "b"], source="s.csv",
        series=[SeriesData(name=n, values=[1, 2]) for n in ("S1", "S2", "S3")],
    )
    facts = compute_chart_facts(chart, "sum")
    assert any("S1" in t for t in texts(facts)) and any("S2" in t for t in texts(facts))
    assert not any("S3" in t for t in texts(facts))
    assert len(facts) <= chart_tool.MAX_FACTS


def test_facts_are_the_same_every_time():
    chart = bar([3, 1, 2])
    assert compute_chart_facts(chart, "sum") == compute_chart_facts(chart, "sum")


# ---------------------------------------------------------------- table facts

def table(rows, columns=("Region", "Revenue", "Units")):
    return TableData(title="T", columns=list(columns), rows=rows, source="s.csv")


def test_a_table_gets_a_count_and_totals_highest_and_lowest_rows_named_by_the_first_column():
    data = table([["North", 120, 3], ["South", 60, 5], ["East", 90, 4]])
    assert texts(compute_table_facts(data)) == [
        "The table shows 3 rows and 3 columns: Region, Revenue, Units.",
        "Total Revenue of the 3 rows shown: 270.",
        "Highest Revenue in the rows shown: North with 120.",
        "Lowest Revenue in the rows shown: South with 60.",
        "Total Units of the 3 rows shown: 12.",
        "Highest Units in the rows shown: South with 5.",
        "Lowest Units in the rows shown: North with 3.",
    ]


def test_a_table_fact_says_it_is_about_the_rows_shown_not_the_whole_sheet():
    first, *others = texts(compute_table_facts(table([["North", 1, 2], ["South", 3, 4]])))
    assert first.startswith("The table shows 2 rows")
    assert others and all("shown" in t for t in others)  # totals and extremes are about the rows on the slide


def test_empty_cells_are_ignored_and_text_that_looks_like_a_number_is_not_one():
    data = table([["North", 10, "$1,200"], ["South", None, "$800"], ["East", 30, "$300"]])
    found = texts(compute_table_facts(data))
    assert "Total Revenue of the 2 rows shown: 40." in found
    assert not any("Units" in t and t.startswith("Total") for t in found)  # '$1,200' stays text: the cell is shown as written


def test_a_table_without_number_columns_has_only_the_count_fact():
    assert texts(compute_table_facts(table([["a", "b", "c"]]))) == ["The table shows 1 rows and 3 columns: Region, Revenue, Units."]


def test_rows_of_a_table_whose_first_column_is_a_number_are_called_row_n():
    data = TableData(title="T", columns=["Year", "Sales"], rows=[[2023, 10], [2024, 30]], source="s.csv")
    assert "Highest Sales in the rows shown: row 2 with 30." in texts(compute_table_facts(data))


def test_a_table_with_no_rows_has_no_facts():
    assert compute_table_facts(table([])) == []


def test_a_table_gets_facts_for_at_most_two_number_columns():
    data = TableData(title="T", columns=["k", "a", "b", "c"], rows=[["x", 1, 2, 3], ["y", 4, 5, 6]], source="s.csv")
    found = texts(compute_table_facts(data))
    assert any(" a " in t for t in found) and any(" b " in t for t in found) and not any(" c " in t for t in found)


# ---------------------------------------------------------------- the prompt

def test_the_facts_block_lists_every_fact_with_its_id_and_the_rules():
    block = render_data_facts([DataFact("D1", "Total X: 5."), DataFact("D2", "Highest X: a with 3.")])
    assert "DATA FACTS (computed by Python" in block and "[D1] Total X: 5." in block and "[D2] Highest X: a with 3." in block
    assert 'leave "chart" and "table" null' in block and "may use only the numbers in DATA FACTS" in block
    assert render_data_facts([]) == ""


def prompt(**kw):
    base = dict(presentation_title="D", audience="A", style=None, slide_number=4, title="T", purpose="P", layout="chart", sources={})
    return build_slide_prompt(**{**base, **kw})


def test_a_prompt_without_facts_has_no_facts_block_and_with_facts_it_comes_after_the_sources():
    assert "DATA FACTS" not in prompt()
    with_facts = prompt(facts=[DataFact("D1", "Total X: 5.")])
    assert with_facts.index("SOURCES:") < with_facts.index("DATA FACTS") < with_facts.index("FINAL CHECK")


# ---------------------------------------------------------------- the slide writer

SPEC = ChartSpec(chart_type="bar", title="Revenue by region", document_id=SALES_DOCUMENT_ID, x_column="Region", y_columns=["Revenue"], aggregation="sum")
TABLE = TableSpec(title="Rows", document_id=SALES_DOCUMENT_ID, columns=["Region", "Product", "Revenue"], max_rows=5)
# the facts of SPEC: D1 count, D2 total 632,000, D3 average 158,000, D4 highest North 200,000, D5 lowest East 122,000


def item(layout="chart"):
    return SlideOutlineItem(slide_number=4, title="Revenue by Region", purpose="Show which regions earn the most", layout_type=layout)


def answer(*bullets, notes="", **kw):
    return SlideContentDraft(bullets=[Bullet(text=t, source_ids=ids) for t, ids in bullets], speaker_notes=notes, **kw)


def write(client, layout="chart", data_files=None, chunks=None):
    return generate_slide_content(
        item(layout), presentation_title="Sales Review", audience="Management",
        chunks=mock_chunks(4) if chunks is None else chunks,
        data_files=[sales_source()] if data_files is None else data_files, client=client,
    )


def test_a_chart_slide_is_written_a_second_time_from_the_data_facts():
    client = FakeClient.sequence(
        answer(("North leads", ["S1"]), notes="first notes", chart=SPEC),
        answer(("North earns 200,000", ["D4"]), ("The regions total 632,000", ["D2"]), notes="second notes"),
    )
    slide = write(client)
    first_prompt, second_prompt = client.calls[0]["prompt"], client.calls[1]["prompt"]
    assert "DATA FACTS" not in first_prompt  # the model has not seen the chart yet
    assert "[D4] Highest Revenue: North with 200,000 (31.6% of the total)." in second_prompt
    assert [b.text for b in slide.bullets] == ["North earns 200,000", "The regions total 632,000"]
    assert slide.speaker_notes == "second notes"
    assert slide.layout_type == "chart" and slide.chart.categories == ["North", "South", "East", "West"]  # the first answer's choice
    assert slide.warnings == []


def test_the_facts_appear_in_the_slides_citations_and_the_bullets_cite_them():
    slide = write(FakeClient.sequence(
        answer(("x", ["S1"]), chart=SPEC),
        answer(("North earns 200,000", ["D4"]), ("The regions total 632,000", ["D2"])),
    ))
    assert [b.source_ids for b in slide.bullets] == [["s4-D4"], ["s4-D2"]]  # real ids: the slide number keeps them unique
    by_id = {c.source_id: c for c in slide.citations}
    assert by_id["s4-D4"].text == "Highest Revenue: North with 200,000 (31.6% of the total)."
    assert by_id["s4-D2"].text == "Total Revenue across the 4 categories shown: 632,000."
    assert by_id["s4-D4"].filename == slide.chart.source == "sample_sales.csv" and by_id["s4-D4"].document_id == SALES_DOCUMENT_ID
    assert by_id["s4-D4"].page is None


def test_a_bullet_may_cite_a_document_source_and_a_data_fact_together():
    slide = write(FakeClient.sequence(
        answer(("x", ["S1"]), chart=SPEC),
        answer(("North led the 12 percent growth with 200,000", ["S1", "D4"])),
    ))
    assert slide.warnings == []  # 12 comes from the report chunk S1, 200,000 from the fact
    assert [c.source_id for c in slide.citations] == ["doc2-s4-a", "s4-D4"]


def test_a_bullet_quoting_a_number_that_is_not_in_its_facts_gets_a_warning():
    slide = write(FakeClient.sequence(
        answer(("x", ["S1"]), chart=SPEC),
        answer(("North earns 250,000", ["D4"]), ("The regions total 632,000", ["D2"])),
    ))
    warnings = [w for w in slide.warnings if "not in its data facts" in w]
    assert len(warnings) == 1 and "250000" in warnings[0] and "North earns 250,000" in warnings[0]
    assert len(slide.bullets) == 2  # a warning, not a deleted bullet


def test_a_percentage_from_the_fact_text_is_allowed():
    slide = write(FakeClient.sequence(answer(("x", ["S1"]), chart=SPEC), answer(("North has 31.6% of the revenue", ["D4"]))))
    assert slide.warnings == []


def test_bullets_that_cite_only_documents_are_not_checked_against_the_facts():
    slide = write(FakeClient.sequence(answer(("x", ["S1"]), chart=SPEC), answer(("Revenue grew 12 percent", ["S1"]))))
    assert slide.warnings == []


def test_a_made_up_fact_id_in_the_second_answer_is_removed_with_a_warning():
    slide = write(FakeClient.sequence(answer(("x", ["S1"]), chart=SPEC), answer(("North leads", ["D4", "D99"]))))
    assert slide.bullets[0].source_ids == ["s4-D4"]
    assert any("Removed source ids" in w and "D99" in w for w in slide.warnings)


def test_if_the_second_call_fails_the_first_bullets_are_kept_and_no_fact_is_cited():
    slide = write(FakeClient.sequence(answer(("North leads", ["S1"]), chart=SPEC), RuntimeError("model is busy")))
    assert [b.text for b in slide.bullets] == ["North leads"] and slide.chart is not None
    assert any("data facts could not be used" in w and "model is busy" in w for w in slide.warnings)
    assert all(c.text is None for c in slide.citations)


def test_if_the_second_answer_has_no_bullets_the_first_ones_stay():
    slide = write(FakeClient.sequence(answer(("North leads", ["S1"]), notes="first", chart=SPEC), SlideContentDraft()))
    assert [b.text for b in slide.bullets] == ["North leads"] and slide.speaker_notes == "first"


def test_a_chart_that_cannot_be_built_costs_no_second_call():
    broken = ChartSpec(chart_type="bar", title="x", document_id=SALES_DOCUMENT_ID, x_column="Region", y_columns=["Profit"])
    client = FakeClient.sequence(answer(("North leads", ["S1"]), chart=broken))
    slide = write(client)
    assert len(client.calls) == 1 and slide.chart is None and slide.layout_type == "bullet_points"
    assert any("Chart dropped" in w for w in slide.warnings)


def test_the_facts_pass_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(settings, "slide_data_facts", False)
    client = FakeClient.sequence(answer(("North leads", ["S1"]), chart=SPEC))
    slide = write(client)
    assert len(client.calls) == 1 and slide.chart is not None and slide.citations[0].text is None


@pytest.mark.parametrize("layout", ["bullet_points", "two_columns", "title"])
def test_slides_without_a_chart_or_table_are_written_once(layout):
    client = FakeClient.sequence(answer(("A point", ["S1"])))
    write(client, layout)
    assert len(client.calls) == 1


def test_a_table_slide_is_written_a_second_time_from_its_facts():
    client = FakeClient.sequence(
        answer(("Rows", ["S1"]), table=TABLE),
        answer(("The five rows shown add up to 425,000", ["D2"]), ("The biggest row is North at 120,000", ["D3"])),
    )
    slide = write(client, "table")
    assert "[D2] Total Revenue of the 5 rows shown: 425,000." in client.calls[1]["prompt"]
    assert slide.layout_type == "table" and slide.table is not None and slide.warnings == []
    assert {c.source_id: c.text for c in slide.citations}["s4-D3"] == "Highest Revenue in the rows shown: North with 120,000."


def test_a_mean_chart_shows_the_model_no_total():
    mean = SPEC.model_copy(update={"aggregation": "mean"})
    client = FakeClient.sequence(answer(("x", ["S1"]), chart=mean), answer(("North is highest", ["D2"])))
    write(client)
    assert "Total Revenue" not in client.calls[1]["prompt"] and "Highest Revenue: North with 100,000." in client.calls[1]["prompt"]


def test_a_fact_citation_names_the_spreadsheet_of_the_data_that_was_built_not_of_the_other_spec(tmp_path):
    import pandas as pd

    from app.tools.chart_tool import DataSource

    other = tmp_path / "other.csv"
    pd.DataFrame({"Region": ["A", "B"], "Revenue": [5, 7]}).to_csv(other, index=False)
    sources = [sales_source(), DataSource(2, "other.csv", other)]
    table_of_doc2 = TableSpec(title="Rows", document_id=2, columns=["Region", "Revenue"], max_rows=2)
    # a table slide whose answer also contains a chart spec for document 1
    first = answer(("Rows", ["S1"]), chart=SPEC, table=table_of_doc2)
    slide = write(FakeClient.sequence(first, answer(("The two rows add up to 12", ["D2"]))), "table", data_files=sources)
    (citation,) = [c for c in slide.citations if c.text]
    assert citation.document_id == 2 and citation.filename == "other.csv"


def test_if_the_chart_cannot_be_built_after_all_no_bullet_keeps_a_fact_id(monkeypatch):
    from app.agents import slide_content_agent as agent

    real, calls = agent.check_chart, []

    def flaky(spec, sources):  # fine when the facts are computed, an error when the slide is finished
        calls.append(1)
        return real(spec, sources) if len(calls) == 1 else chart_tool.CheckResult(None, [chart_tool.Issue("empty_result", "error", "gone", "Try again.")])

    monkeypatch.setattr(agent, "check_chart", flaky)
    slide = write(FakeClient.sequence(answer(("x", ["S1"]), chart=SPEC), answer(("North leads", ["D4"]))))
    assert slide.layout_type == "bullet_points" and slide.chart is None
    assert slide.bullets[0].source_ids == [] and all(c.text is None for c in slide.citations)
    assert any("Chart dropped: gone Try again." in w for w in slide.warnings)


# ---- Week 6 presentation edits (DAT-06 + cancellation): the data-facts call can be cancelled too ----

def test_cancelling_during_the_data_facts_call_stops_the_slide_instead_of_keeping_the_first_bullets():
    from app.core.exceptions import GenerationCancelled

    client = FakeClient.sequence(answer(("North leads", ["S1"]), chart=SPEC), GenerationCancelled())
    with pytest.raises(GenerationCancelled):
        write(client)  # it must not be turned into a "the data facts could not be used" warning


def test_the_data_facts_call_gets_the_cancel_event_and_is_not_started_when_already_cancelled():
    from threading import Event

    from app.core.exceptions import GenerationCancelled

    cancel = Event()
    client = FakeClient.sequence(
        answer(("North leads", ["S1"]), chart=SPEC), answer(("North earns 200,000", ["D4"]))
    )
    generate_slide_content(
        item("chart"), presentation_title="Sales Review", audience="Management", chunks=mock_chunks(4),
        data_files=[sales_source()], client=client, cancel_event=cancel,
    )
    assert [call["cancel_event"] for call in client.calls] == [cancel, cancel]  # both calls can be interrupted

    class CancelAfterFirstAnswer(FakeClient):
        def generate_json(self, *args, **kwargs):
            result = super().generate_json(*args, **kwargs)
            kwargs["cancel_event"].set()  # the user pressed cancel while the first answer was being written
            return result

    stopped = CancelAfterFirstAnswer.sequence(answer(("North leads", ["S1"]), chart=SPEC))
    with pytest.raises(GenerationCancelled):
        generate_slide_content(
            item("chart"), presentation_title="Sales Review", audience="Management", chunks=mock_chunks(4),
            data_files=[sales_source()], client=stopped, cancel_event=Event(),
        )
    assert len(stopped.calls) == 1  # no second model call was started after the cancel
