"""Week 6 presentation edits (DAT-05): the data catalog the model sees has row counts, distinct counts, example labels and ranges."""
import pandas as pd
import pytest

from app.llm.prompts.slide_content import build_slide_prompt, render_data_files
from app.presentations.outline import generate_outline
from app.schemas.presentations import PresentationCreate
from app.presentations import generator as deck_generator
from app.tools import chart_tool
from app.tools.chart_tool import Catalog, ColumnProfile, DataSource, clear_sheet_cache, describe_sources
from tests.slide_samples import FakeClient, sales_source


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_sheet_cache()
    yield
    clear_sheet_cache()


def csv_source(tmp_path, frame, name="d.csv", document_id=1):
    path = tmp_path / name
    frame.to_csv(path, index=False)
    return DataSource(document_id, name, path)


def only_sheet(sources):
    (catalog,) = describe_sources(sources)
    (sheet,) = catalog.sheets
    return sheet


# ---------------------------------------------------------------- what is in the catalog

def test_the_sheet_has_its_row_count_from_the_whole_sheet_not_the_sample(tmp_path):
    frame = pd.DataFrame({"k": [f"c{i}" for i in range(120)], "v": range(120)})
    sheet = only_sheet([csv_source(tmp_path, frame)])
    assert sheet.rows == 120  # CATALOG_SAMPLE_ROWS is 50: it only limits the rows used to detect the kinds
    assert sheet.profiles["v"].high == "119"  # ... and the range looks at every row


def test_a_text_column_has_its_distinct_count_and_its_most_common_labels(tmp_path):
    frame = pd.DataFrame({"region": ["north"] * 5 + ["south"] * 3 + ["east"] * 2 + ["west"], "v": range(11)})
    profile = only_sheet([csv_source(tmp_path, frame)]).profiles["region"]
    assert profile.distinct == 4
    assert profile.examples == ("north", "south", "east", "west")  # most common first
    assert profile.low is None and profile.high is None


def test_the_number_of_example_labels_is_a_setting_and_labels_are_shortened(tmp_path, monkeypatch):
    frame = pd.DataFrame({"name": [f"label {i}" for i in range(10)] + ["x" * 100], "v": range(11)})
    monkeypatch.setattr(chart_tool, "CATALOG_EXAMPLE_LABELS", 3)
    assert len(only_sheet([csv_source(tmp_path, frame)]).profiles["name"].examples) == 3
    clear_sheet_cache()
    monkeypatch.setattr(chart_tool, "CATALOG_EXAMPLE_LABELS", 20)
    labels = only_sheet([csv_source(tmp_path, frame)]).profiles["name"].examples
    assert max(len(label) for label in labels) == chart_tool.CATALOG_LABEL_CHARS


def test_no_example_labels_when_the_setting_is_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_tool, "CATALOG_EXAMPLE_LABELS", 0)
    profile = only_sheet([csv_source(tmp_path, pd.DataFrame({"k": list("abc"), "v": [1, 2, 3]}))]).profiles["k"]
    assert profile.examples == () and profile.distinct == 3


def test_a_number_column_has_its_distinct_count_and_its_range(tmp_path):
    profile = only_sheet([csv_source(tmp_path, pd.DataFrame({"k": list("abcd"), "v": [5, 5, 9, 1.5]}))]).profiles["v"]
    assert (profile.distinct, profile.low, profile.high, profile.examples) == (3, "1.5", "9", ())


def test_text_that_holds_numbers_gets_a_numeric_range(tmp_path):
    frame = pd.DataFrame({"k": list("abc"), "price": ["$1,200", "$800", "$300"]})
    sheet = only_sheet([csv_source(tmp_path, frame)])
    assert ("price", "number") in sheet.columns
    assert (sheet.profiles["price"].low, sheet.profiles["price"].high) == ("300", "1200")


def test_a_date_column_has_its_first_and_last_date(tmp_path):
    frame = pd.DataFrame({"k": list("abc"), "day": ["2024-03-05", "2024-01-15", "2024-02-01"]})
    sheet = only_sheet([csv_source(tmp_path, frame)])
    assert ("day", "date") in sheet.columns
    assert (sheet.profiles["day"].low, sheet.profiles["day"].high) == ("2024-01-15", "2024-03-05")


def test_the_catalog_never_holds_a_computed_value(tmp_path):
    frame = pd.DataFrame({"k": ["a", "b", "c"], "v": [10, 20, 33]})  # sum 63, average 21
    source = csv_source(tmp_path, frame)
    text = repr(describe_sources([source])) + render_data_files(describe_sources([source]))
    assert "63" not in text and "21" not in text


def test_old_code_that_reads_the_columns_still_works(tmp_path):
    sheet = only_sheet([csv_source(tmp_path, pd.DataFrame({"k": list("ab"), "v": [1, 2]}))])
    assert sheet.columns == [("k", "text"), ("v", "number")]  # the same (name, kind) pairs as before


def test_a_column_that_cannot_be_profiled_is_still_listed(tmp_path, monkeypatch):
    def broken(series, kind):
        raise RuntimeError("boom")

    monkeypatch.setattr(chart_tool, "_profile", broken)
    sheet = only_sheet([csv_source(tmp_path, pd.DataFrame({"k": list("ab"), "v": [1, 2]}))])
    assert sheet.columns == [("k", "text"), ("v", "number")] and sheet.profiles == {}
    text = render_data_files([chart_tool.SourceCatalog(1, "d.csv", [sheet])])
    assert "k (text), v (number)" in text and "[" not in text.split("not part of the column name):")[1]  # no details, no crash


# ---------------------------------------------------------------- a note when something was left out

def test_columns_over_the_limit_are_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_tool, "CATALOG_MAX_COLUMNS", 3)
    frame = pd.DataFrame({f"c{i}": range(4) for i in range(5)})
    sheet = only_sheet([csv_source(tmp_path, frame)])
    assert [name for name, _ in sheet.columns] == ["c0", "c1", "c2"] and sheet.columns_left_out == 2


def test_sheets_over_the_limit_are_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_tool, "CATALOG_MAX_SHEETS", 2)
    path = tmp_path / "book.xlsx"
    with pd.ExcelWriter(path) as writer:
        for name in ("A", "B", "C", "D"):
            pd.DataFrame({"k": ["a"], "v": [1]}).to_excel(writer, sheet_name=name, index=False)
    (catalog,) = describe_sources([DataSource(1, "book.xlsx", path)])
    assert [s.name for s in catalog.sheets] == ["A", "B"] and catalog.sheets_left_out == 2


def test_files_over_the_limit_are_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_tool, "CATALOG_MAX_FILES", 2)
    sources = [csv_source(tmp_path, pd.DataFrame({"k": ["a"], "v": [1]}), f"f{i}.csv", document_id=i) for i in range(5)]
    catalog = describe_sources(sources)
    assert isinstance(catalog, Catalog) and isinstance(catalog, list)  # still a plain list for old callers
    assert [c.document_id for c in catalog] == [0, 1] and catalog.files_left_out == 3


def test_a_catalog_with_nothing_left_out_says_nothing_about_it(tmp_path):
    text = render_data_files(describe_sources([csv_source(tmp_path, pd.DataFrame({"k": ["a"], "v": [1]}))]))
    assert "not listed" not in text


# ---------------------------------------------------------------- the text the model reads

def test_the_catalog_text_shows_rows_distinct_counts_labels_and_ranges():
    text = render_data_files(describe_sources([sales_source()]))
    assert 'document_id=1, file "sample_sales.csv"' in text
    assert "(single table), 8 rows:" in text
    assert "Region (text) [4 distinct, e.g. North, South, East, West]" in text
    assert "Revenue (number) [8 distinct, 45000 to 120000]" in text
    assert "Units (number) [8 distinct, 180 to 400]" in text


def test_the_column_name_and_kind_keep_their_old_form_and_the_header_says_the_brackets_are_not_names():
    text = render_data_files(describe_sources([sales_source()]))
    assert "Region (text)" in text and "Revenue (number)" in text
    assert text.splitlines()[1].startswith("DATA FILES (spreadsheets you may use")
    assert "not part of the column name" in text.splitlines()[1]


def test_the_catalog_text_says_what_was_left_out(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_tool, "CATALOG_MAX_COLUMNS", 2)
    monkeypatch.setattr(chart_tool, "CATALOG_MAX_FILES", 1)
    sources = [csv_source(tmp_path, pd.DataFrame({f"c{i}": range(3) for i in range(4)}), f"f{i}.csv", i) for i in range(3)]
    text = render_data_files(describe_sources(sources))
    assert "(2 more columns of this sheet are not listed)" in text
    assert "(2 more spreadsheets are not listed)" in text


def test_a_sheet_with_a_hand_made_old_style_catalog_still_renders():
    old = chart_tool.SourceCatalog(1, "a.csv", [chart_tool.SheetCatalog(None, [("k", "text")])])  # no rows, no profiles
    assert render_data_files([old]).splitlines()[-1] == "    (single table): k (text)"


def test_the_slide_prompt_shows_the_catalog_text():
    prompt = build_slide_prompt(
        presentation_title="Deck", audience="Team", style=None, slide_number=4, title="Revenue", purpose="Show revenue",
        layout="chart", sources={}, catalog=describe_sources([sales_source()]),
    )
    assert "(single table), 8 rows:" in prompt and "Revenue (number) [8 distinct, 45000 to 120000]" in prompt


def test_a_profile_is_a_small_immutable_value():
    profile = ColumnProfile(4, ("a", "b"))
    assert profile.low is None and profile.examples == ("a", "b")
    with pytest.raises(AttributeError):
        profile.distinct = 5


# ---------------------------------------------------------------- the outline step receives it

OUTLINE = {
    "presentation_title": "T", "target_audience": "A",
    "slides": [
        {"slide_number": 1, "title": "Intro", "purpose": "p", "layout_type": "title"},
        {"slide_number": 2, "title": "End", "purpose": "p", "layout_type": "bullet_points"},
    ],
}


def options():
    return PresentationCreate(topic="Sales review", num_slides=3, include_sources_slide=True).model_dump()


def test_the_outline_prompt_contains_the_catalog(scripted_llm):
    client = scripted_llm(OUTLINE)
    generate_outline(client, options(), chunks=[], data_names=["sample_sales.csv"], catalog=describe_sources([sales_source()]))
    prompt = client.calls[0]["prompt"]
    assert "DATA FILES (spreadsheets you may use" in prompt
    assert "(single table), 8 rows:" in prompt and "Region (text) [4 distinct" in prompt
    assert "name in its purpose the columns of DATA FILES" in prompt
    assert prompt.index("DATA FILES") < prompt.index("DOCUMENT EXCERPTS:")  # the catalog is not inside the excerpts


def test_the_outline_prompt_is_unchanged_when_no_catalog_is_given(scripted_llm):
    client = scripted_llm(OUTLINE)
    generate_outline(client, options(), chunks=[], data_names=["sample_sales.csv"])
    prompt = client.calls[0]["prompt"]
    assert "Use chart or table only to show numbers from: sample_sales.csv." in prompt and "DATA FILES" not in prompt


def test_no_spreadsheet_means_no_catalog_in_the_outline_prompt(scripted_llm):
    client = scripted_llm(OUTLINE)
    generate_outline(client, options(), chunks=[], data_names=[], catalog=describe_sources([]))
    assert "DATA FILES" not in client.calls[0]["prompt"]


def test_the_deck_generator_describes_the_spreadsheets_and_gives_them_to_the_outline(monkeypatch):
    seen = {}

    class Stop(Exception):
        pass

    def spy(client, options, chunks, data_names, catalog=(), *, cancel_event=None):
        seen.update(names=list(data_names), catalog=catalog)
        raise Stop

    monkeypatch.setattr(deck_generator, "generate_outline", spy)
    monkeypatch.setattr(deck_generator, "sources_from_documents", lambda documents: [sales_source()])
    monkeypatch.setattr(deck_generator.presentation_context, "build_chunks", lambda documents: [])
    generator = deck_generator.LocalLlmDeckGenerator(client=FakeClient.sequence(), check_ready=False)

    with pytest.raises(Stop):
        generator.generate(notebook=None, options=options(), documents=[], progress=lambda message: None)

    assert seen["names"] == ["sample_sales.csv"]
    assert [c.filename for c in seen["catalog"]] == ["sample_sales.csv"] and seen["catalog"][0].sheets[0].rows == 8
