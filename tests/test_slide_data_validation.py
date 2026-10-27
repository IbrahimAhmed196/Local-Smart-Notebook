"""Week 6 presentation edits (DAT-01): ChartData / TableData reject data the renderer cannot draw."""
import pytest
from pydantic import ValidationError

from app.schemas.slide_content import ChartData, TableData
from tests.test_presentations_api import created_presentation  # noqa: F401  (fixture for the PUT test)


def chart(**changes):
    base = dict(
        chart_type="bar",
        title="Revenue",
        categories=["North", "South"],
        series=[{"name": "Revenue", "values": [1.0, 2.0]}],
        source="sales.xlsx",
    )
    return ChartData(**{**base, **changes})


def table(**changes):
    base = dict(title="Rows", columns=["Region", "Revenue"], rows=[["North", 1], ["South", None]], source="sales.xlsx")
    return TableData(**{**base, **changes})


def test_valid_chart_and_table_are_accepted():
    assert chart().series[0].values == [1.0, 2.0]
    assert table().rows[1] == ["South", None]  # an empty cell is allowed
    assert chart(series=[{"name": "A", "values": [1, 2]}, {"name": "B", "values": [3, 4]}])


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"series": [{"name": "Revenue", "values": [1.0]}]}, "1 values but the chart has 2 categories"),
        ({"series": [{"name": "Revenue", "values": [1.0, 2.0, 3.0]}]}, "3 values but the chart has 2 categories"),
        ({"series": [{"name": "Revenue", "values": [1.0, float("nan")]}]}, "no NaN or infinity"),
        ({"series": [{"name": "Revenue", "values": [1.0, float("inf")]}]}, "no NaN or infinity"),
        ({"categories": [], "series": [{"name": "Revenue", "values": []}]}, "at least one category"),
        ({"categories": ["North", "  "]}, "no empty category names"),
        ({"series": []}, "at least one series"),
        (
            {"series": [{"name": "Revenue", "values": [1, 2]}, {"name": " revenue ", "values": [3, 4]}]},
            "series names must be different",
        ),
    ],
)
def test_invalid_chart_data_is_rejected_with_a_readable_message(changes, message):
    with pytest.raises(ValidationError, match=message):
        chart(**changes)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"rows": [["North", 1], ["South"]]}, "row 2 has 1 cells but the table has 2 columns"),
        ({"rows": [["North", 1, "extra"]]}, "row 1 has 3 cells but the table has 2 columns"),
        ({"rows": [["North", float("nan")]]}, "row 1 contains NaN or infinity"),
        ({"columns": []}, "at least one column"),
        ({"columns": ["Region", ""], }, "no empty column names"),
    ],
)
def test_invalid_table_data_is_rejected_with_a_readable_message(changes, message):
    with pytest.raises(ValidationError, match=message):
        table(**changes)


def test_put_deck_with_a_broken_chart_is_a_422_and_the_old_deck_stays(client, auth, created_presentation):
    url = f"/presentations/{created_presentation['id']}"
    deck = client.get(f"{url}/deck", headers=auth).json()
    deck["slides"][0]["chart"] = {
        "chart_type": "bar",
        "title": "Broken",
        "categories": ["a", "b", "c"],
        "series": [{"name": "x", "values": [1, 2]}],
        "source": "hand edited",
    }
    response = client.put(f"{url}/deck", headers=auth, json=deck)
    assert response.status_code == 422
    assert "2 values but the chart has 3 categories" in response.text
    assert client.get(f"{url}/deck", headers=auth).json()["slides"][0]["chart"] != deck["slides"][0]["chart"]
