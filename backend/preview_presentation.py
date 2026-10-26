"""Render and check all five layouts in the sample deck."""

from io import BytesIO
from pathlib import Path

from pptx import Presentation

from app.schemas.slide_content import Bullet, PresentationContent, SlideContent
from app.tools.pptx_tool import THEMES, render_presentation


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    sample_path = PROJECT_ROOT / "docs" / "samples" / "sample_deck.json"

    deck = PresentationContent.model_validate_json(
        sample_path.read_text(encoding="utf-8")
    )

    comparison = deck.slides[2].model_copy(
        deep=True, update={"slide_number": 6, "layout_type": "comparison"},
    )
    highlight = deck.slides[1].model_copy(
        deep=True, update={"slide_number": 7, "layout_type": "stat_highlight"},
    )
    conclusion = deck.slides[1].model_copy(
        deep=True, update={"slide_number": 8, "title": "Conclusions", "layout_type": "conclusion"},
    )

    references, data_sources = {}, {}
    for item in deck.slides:
        for citation in item.citations:
            references.setdefault((citation.document_id, citation.source_id), citation)
        for data in (item.chart, item.table):
            if data is not None and data.source:
                data_sources.setdefault(data.source, None)

    sources = SlideContent(
        slide_number=9, title="Sources", layout_type="sources",
        citations=list(references.values()),
        bullets=[Bullet(text=f"Data: {source}") for source in data_sources],
        speaker_notes="References used in this sample presentation.",
    )
    deck.slides.extend([comparison, highlight, conclusion, sources])    

    pptx_bytes = render_presentation(deck, theme=THEMES["professional"])
    reopened = Presentation(BytesIO(pptx_bytes))

    expected_slides = sorted(
        deck.slides,
        key=lambda slide: slide.slide_number,
    )

    assert len(reopened.slides) == len(expected_slides)

    for expected, actual in zip(expected_slides, reopened.slides):
        text = "\n".join(
            shape.text
            for shape in actual.shapes
            if shape.has_text_frame
        )

        assert expected.title in text
        assert expected.speaker_notes in (
            actual.notes_slide.notes_text_frame.text
        )

        if expected.layout_type in {
            "bullet_points", "two_columns", "comparison", "stat_highlight", "conclusion", "chart", "table",
        }:
            for bullet in expected.bullets:
                assert bullet.text in text

        if expected.layout_type in {"two_columns", "comparison"}:
            for bullet in expected.right_bullets:
                assert bullet.text in text

        if expected.layout_type == "chart":
            charts = [
                shape.chart
                for shape in actual.shapes
                if shape.has_chart
            ]

            assert len(charts) == 1
            chart = charts[0]

            assert [
                category.label
                for category in chart.plots[0].categories
            ] == expected.chart.categories

            assert len(chart.series) == len(expected.chart.series)

            for actual_series, expected_series in zip(
                chart.series, expected.chart.series
            ):
                assert actual_series.name == expected_series.name
                assert list(actual_series.values) == expected_series.values

        if expected.layout_type == "table":
            tables = [
                shape.table
                for shape in actual.shapes
                if shape.has_table
            ]

            assert len(tables) == 1
            table = tables[0]

            expected_rows = [
                expected.table.columns,
                *expected.table.rows,
            ]

            assert len(table.rows) == len(expected_rows)
            assert len(table.columns) == len(expected.table.columns)

            for row_index, row in enumerate(expected_rows):
                for column_index, value in enumerate(row):
                    expected_text = "" if value is None else str(value)
                    assert (
                        table.cell(row_index, column_index).text
                        == expected_text
                    )

    output_path = (
        PROJECT_ROOT / "data" / "temporary" / "presentation_step4a.pptx"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(pptx_bytes)

    print(f"Created: {output_path}")
    print(f"Slides: {len(reopened.slides)}")
    print("Content, notes, chart values, and table cells checked.")


if __name__ == "__main__":
    main()