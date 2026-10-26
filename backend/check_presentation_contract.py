"""Check the sample deck without starting FastAPI, the database, or Ollama."""

from pathlib import Path

from app.schemas.slide_content import PresentationContent, SLIDE_LAYOUTS


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = PROJECT_ROOT / "docs" / "samples" / "sample_deck.json"


def main() -> None:
    deck = PresentationContent.model_validate_json(
        SAMPLE_PATH.read_text(encoding="utf-8")
    )

    if not deck.slides:
        raise ValueError("The presentation contains no slides.")

    numbers = [slide.slide_number for slide in deck.slides]
    expected = list(range(1, len(deck.slides) + 1))

    if numbers != expected:
        raise ValueError(
            f"Slides must be ordered and numbered {expected}; got {numbers}."
        )

    print(f"Presentation: {deck.presentation_title}")
    print(f"Audience: {deck.target_audience}")
    print(f"Slide count: {len(deck.slides)}")

    for slide in deck.slides:
        prefix = f"Slide {slide.slide_number}"

        if slide.layout_type not in SLIDE_LAYOUTS:
            print(
                f"WARNING: {prefix} uses '{slide.layout_type}'. "
                "The current contract specifies a bullet_points fallback."
            )

        # Check that each bullet's source ID has a citation entry.
        citation_ids = {
            citation.source_id for citation in slide.citations
        }

        for bullet in [*slide.bullets, *slide.right_bullets]:
            missing = set(bullet.source_ids) - citation_ids
            if missing:
                raise ValueError(
                    f"{prefix}: missing citation entries for {sorted(missing)}."
                )

        if slide.layout_type == "chart":
            chart = slide.chart

            if chart is None:
                raise ValueError(f"{prefix}: chart data is missing.")

            if not chart.categories or not chart.series:
                raise ValueError(f"{prefix}: chart data is empty.")

            for series in chart.series:
                if len(series.values) != len(chart.categories):
                    raise ValueError(
                        f"{prefix}: series '{series.name}' has "
                        f"{len(series.values)} values but "
                        f"{len(chart.categories)} categories."
                    )

            if chart.chart_type == "pie" and len(chart.series) != 1:
                raise ValueError(
                    f"{prefix}: a pie chart requires exactly one series."
                )

        if slide.layout_type == "table":
            table = slide.table

            if table is None or not table.columns:
                raise ValueError(f"{prefix}: table columns are missing.")

            for row_number, row in enumerate(table.rows, start=1):
                if len(row) != len(table.columns):
                    raise ValueError(
                        f"{prefix}: table row {row_number} has "
                        f"{len(row)} cells but "
                        f"{len(table.columns)} columns."
                    )

        print(f"  {slide.slide_number}. [{slide.layout_type}] {slide.title}")

    print("\nSample deck contract check passed.")


if __name__ == "__main__":
    main()