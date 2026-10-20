import json

import pandas as pd
import pytest

from app.schemas.slide_content import ChartSpec, TableSpec
from app.tools.chart_tool import (
    MAX_BAR_CATEGORIES,
    MAX_LINE_POINTS,
    MAX_PIE_SLICES,
    MAX_TABLE_COLUMNS,
    MAX_TABLE_ROWS,
    ChartToolError,
    DataSource,
    build_chart_data,
    build_table_data,
    describe_sources,
)

SALES = pd.DataFrame(
    {
        "Region": ["North", "South", "North", "East", "South"],
        "Revenue": [100, 200, 300, 400, 500],
        "Units": [1, 2, 3, 4, 5],
        "Month": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01", "2024-05-01"]),
    }
)


@pytest.fixture()
def xlsx(tmp_path):
    path = tmp_path / "sales.xlsx"
    with pd.ExcelWriter(path) as writer:
        SALES.to_excel(writer, sheet_name="Q1", index=False)
        pd.DataFrame({"Item": ["a", "b"], "Cost": [7, 9]}).to_excel(writer, sheet_name="Costs", index=False)
    return [DataSource(document_id=1, filename="sales.xlsx", path=path)]


def chart(**kw):
    base = dict(chart_type="bar", title="T", document_id=1, sheet="Q1", x_column="Region", y_columns=["Revenue"])
    return ChartSpec(**{**base, **kw})


def test_describe_sources_lists_sheets_and_column_kinds_but_never_values(xlsx):
    (source,) = describe_sources(xlsx)
    assert source.document_id == 1 and source.filename == "sales.xlsx"
    assert [s.name for s in source.sheets] == ["Q1", "Costs"]
    assert source.sheets[0].columns == [
        ("Region", "text"), ("Revenue", "number"), ("Units", "number"), ("Month", "date"),
    ]
    assert "500" not in repr(source) and "North" not in repr(source)


def test_describe_sources_reads_semicolon_csv_and_skips_unreadable_and_other_files(tmp_path):
    csv = tmp_path / "a.csv"
    csv.write_text("city;sales\nCairo;10\nGiza;20\n", encoding="utf-8")
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"not a workbook")
    txt = tmp_path / "notes.txt"
    txt.write_text("hello")
    sources = [DataSource(1, "a.csv", csv), DataSource(2, "bad.xlsx", bad), DataSource(3, "notes.txt", txt)]
    catalog = describe_sources(sources)
    assert [c.document_id for c in catalog] == [1]
    assert catalog[0].sheets[0].name is None
    assert catalog[0].sheets[0].columns == [("city", "text"), ("sales", "number")]


@pytest.mark.parametrize(
    "aggregation, expected",
    [
        ("sum", {"North": 400, "South": 700, "East": 400}),
        ("mean", {"North": 200, "South": 350, "East": 400}),
        ("count", {"North": 2, "South": 2, "East": 1}),
    ],
)
def test_aggregations_are_computed_from_the_file(xlsx, aggregation, expected):
    data = build_chart_data(chart(aggregation=aggregation), xlsx)
    assert dict(zip(data.categories, data.series[0].values)) == {k: float(v) for k, v in expected.items()}
    assert data.source == "sales.xlsx / Q1"


def test_aggregation_none_uses_the_rows_as_they_are(xlsx):
    data = build_chart_data(chart(aggregation="none", chart_type="line", x_column="Month"), xlsx)
    assert data.categories == ["2024-01-01", "2024-02-01", "2024-03-01", "2024-04-01", "2024-05-01"]
    assert data.series[0].values == [100.0, 200.0, 300.0, 400.0, 500.0]


def test_several_series_and_names_in_a_different_case(xlsx):
    data = build_chart_data(chart(sheet="q1", x_column="region", y_columns=["REVENUE", " units "]), xlsx)
    assert [s.name for s in data.series] == ["Revenue", "Units"]
    assert data.series[1].values == [4.0, 7.0, 4.0]


def test_the_default_sheet_is_the_first_one_and_a_csv_needs_no_sheet(xlsx, tmp_path):
    assert build_chart_data(chart(sheet=None), xlsx).source == "sales.xlsx / Q1"
    csv = tmp_path / "c.csv"
    csv.write_text("k,v\na,1\nb,2\n")
    data = build_chart_data(chart(sheet="ignored", x_column="k", y_columns=["v"]), [DataSource(1, "c.csv", csv)])
    assert data.categories == ["a", "b"] and data.source == "c.csv"


@pytest.mark.parametrize(
    "override",
    [
        dict(document_id=99),
        dict(sheet="Nope"),
        dict(x_column="Nope"),
        dict(y_columns=["Nope"]),
        dict(y_columns=["Region"]),  # text column: no numbers
        dict(y_columns=["Region"], x_column="Region"),  # nothing left once x is removed
    ],
)
def test_a_spec_that_does_not_match_the_file_is_rejected_not_guessed(xlsx, override):
    with pytest.raises(ChartToolError):
        build_chart_data(chart(**override), xlsx)


def test_count_works_on_a_text_column(xlsx):
    data = build_chart_data(chart(aggregation="count", y_columns=["Region"], x_column="Month"), xlsx)
    assert data.series[0].values == [1.0] * 5


def test_big_charts_keep_the_biggest_categories_and_pies_use_one_series(tmp_path):
    csv = tmp_path / "big.csv"
    pd.DataFrame({"k": [f"c{i}" for i in range(30)], "v": list(range(30)), "w": [1] * 30}).to_csv(csv, index=False)
    src = [DataSource(1, "big.csv", csv)]
    bar = build_chart_data(chart(sheet=None, x_column="k", y_columns=["v"]), src)
    assert len(bar.categories) == MAX_BAR_CATEGORIES and bar.categories[0] == "c29"
    pie = build_chart_data(chart(chart_type="pie", sheet=None, x_column="k", y_columns=["v", "w"]), src)
    assert len(pie.categories) == MAX_PIE_SLICES and len(pie.series) == 1
    line = build_chart_data(chart(chart_type="line", aggregation="none", sheet=None, x_column="k", y_columns=["v"]), src)
    assert len(line.categories) == MAX_LINE_POINTS and line.categories[0] == "c0"


def test_missing_numbers_are_dropped_never_replaced_by_zero(tmp_path):
    csv = tmp_path / "gaps.csv"
    csv.write_text("k,v\na,1\nb,\nc,3\n")
    data = build_chart_data(chart(sheet=None, x_column="k", y_columns=["v"], aggregation="none"), [DataSource(1, "gaps.csv", csv)])
    assert data.categories == ["a", "c"] and data.series[0].values == [1.0, 3.0]


def test_a_pie_cannot_show_negative_values(tmp_path):
    csv = tmp_path / "neg.csv"
    csv.write_text("k,v\na,5\nb,-2\n")
    with pytest.raises(ChartToolError):
        build_chart_data(chart(chart_type="pie", sheet=None, x_column="k", y_columns=["v"]), [DataSource(1, "neg.csv", csv)])


def test_chart_and_table_data_are_plain_json(xlsx):
    chart_json = build_chart_data(chart(aggregation="none", x_column="Month"), xlsx).model_dump()
    table_json = build_table_data(TableSpec(title="t", document_id=1, sheet="Q1", columns=["Region", "Month", "Revenue"]), xlsx).model_dump()
    json.dumps(chart_json)
    json.dumps(table_json)  # fails if a numpy / pandas type slipped through


def test_table_reads_the_real_cells(xlsx):
    spec = TableSpec(title="Rows", document_id=1, sheet="Q1", columns=["region", "Revenue", "Month"], max_rows=2)
    data = build_table_data(spec, xlsx)
    assert data.columns == ["Region", "Revenue", "Month"]
    assert data.rows == [["North", 100, "2024-01-01"], ["South", 200, "2024-02-01"]]
    assert data.source == "sales.xlsx / Q1"


def test_table_keeps_empty_cells_as_none_and_whole_numbers_as_numbers(tmp_path):
    csv = tmp_path / "t.csv"
    csv.write_text("name,score,ratio\nann,90,0.5\nbob,,2.25\n")
    data = build_table_data(TableSpec(title="t", document_id=1, columns=["name", "score", "ratio"]), [DataSource(1, "t.csv", csv)])
    assert data.rows == [["ann", 90, 0.5], ["bob", None, 2.25]]


def test_table_limits_rows_and_columns(tmp_path):
    csv = tmp_path / "wide.csv"
    pd.DataFrame({f"c{i}": range(40) for i in range(10)}).to_csv(csv, index=False)
    spec = TableSpec(title="t", document_id=1, columns=[f"c{i}" for i in range(10)], max_rows=500)
    data = build_table_data(spec, [DataSource(1, "wide.csv", csv)])
    assert len(data.columns) == MAX_TABLE_COLUMNS and len(data.rows) == MAX_TABLE_ROWS
    assert len(build_table_data(spec.model_copy(update={"max_rows": 0}), [DataSource(1, "wide.csv", csv)]).rows) == 1


def test_table_with_an_unknown_column_is_rejected(xlsx):
    with pytest.raises(ChartToolError):
        build_table_data(TableSpec(title="t", document_id=1, sheet="Q1", columns=["Region", "Nope"]), xlsx)
