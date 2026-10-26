"""Mock outline, source chunks, spreadsheet and fake LLM for the Task 2 (slide content) tests.

`python tests/slide_samples.py` rewrites docs/samples/sample_outline.json and sample_deck.json.
Those two files are the sample Task 3 starts from; a test fails if they drift from the schema.
"""
import json
import re
from pathlib import Path
from typing import Callable, Dict, List

from app.schemas.slide_content import Bullet, ChartSpec, SlideContentDraft, SourceChunk, TableSpec
from app.schemas.slides import PresentationOutlineResponse, SlideOutlineItem
from app.tools.chart_tool import DataSource
from tests.fake_llm import ScriptedLLMClient as FakeClient

SAMPLES_DIR = Path(__file__).resolve().parents[1] / "docs" / "samples"
SALES_CSV = SAMPLES_DIR / "sample_sales.csv"
SALES_DOCUMENT_ID = 1
REPORT_DOCUMENT_ID = 2


def mock_outline() -> PresentationOutlineResponse:
    """What Task 1 produces: title, purpose and layout for each slide (no content)."""
    return PresentationOutlineResponse(
        presentation_title="Sales Review 2025",
        target_audience="Management team",
        slides=[
            SlideOutlineItem(slide_number=1, title="Sales Review 2025", purpose="Introduce the review", layout_type="title"),
            SlideOutlineItem(slide_number=2, title="Key Findings", purpose="Summarise the main results", layout_type="bullet_points"),
            SlideOutlineItem(slide_number=3, title="Strengths and Risks", purpose="Contrast what works with what does not", layout_type="two_columns"),
            SlideOutlineItem(slide_number=4, title="Revenue by Region", purpose="Show which regions earn the most", layout_type="chart"),
            SlideOutlineItem(slide_number=5, title="Sample of the Data", purpose="Show the underlying rows", layout_type="table"),
        ],
    )


def mock_chunks(slide_number: int) -> List[SourceChunk]:
    """Two report chunks per content slide (real chunk ids, as the retrieval side will give them)."""
    if slide_number == 1:
        return []
    return [
        SourceChunk(
            chunk_id=f"doc{REPORT_DOCUMENT_ID}-s{slide_number}-a",
            document_id=REPORT_DOCUMENT_ID,
            filename="sales_report.pdf",
            page=slide_number,
            text="Revenue grew 12 percent in 2025, led by laptops. The north region was the strongest market.",
        ),
        SourceChunk(
            chunk_id=f"doc{REPORT_DOCUMENT_ID}-s{slide_number}-b",
            document_id=REPORT_DOCUMENT_ID,
            filename="sales_report.pdf",
            page=slide_number + 1,
            text="Phone sales in the west region fell short of the target because of supply delays.",
        ),
    ]


def sales_source() -> DataSource:
    return DataSource(document_id=SALES_DOCUMENT_ID, filename="sample_sales.csv", path=SALES_CSV)


def slide_number_of(prompt: str) -> int:
    return int(re.search(r"^SLIDE (\d+):", prompt, re.MULTILINE).group(1))


def sample_drafts() -> Dict[int, SlideContentDraft]:
    """Realistic answers for the mock outline (the cited ids are the S1/S2 aliases)."""
    return {
        1: SlideContentDraft(
            subtitle="How the business performed in 2025",
            speaker_notes="Welcome everyone. Today we review how sales performed across our regions in 2025.",
        ),
        2: SlideContentDraft(
            bullets=[
                Bullet(text="Revenue grew 12 percent in 2025", source_ids=["S1"]),
                Bullet(text="Laptops drove most of the growth", source_ids=["S1"]),
                Bullet(text="The north region is the strongest market", source_ids=["S1"]),
            ],
            speaker_notes="Revenue grew twelve percent. Laptops were the main driver, and the north region led.",
        ),
        3: SlideContentDraft(
            bullets=[
                Bullet(text="Laptop sales led the growth", source_ids=["S1"]),
                Bullet(text="North region is the strongest market", source_ids=["S1"]),
            ],
            right_bullets=[
                Bullet(text="West phone sales missed the target", source_ids=["S2"]),
                Bullet(text="Supply delays caused the shortfall", source_ids=["S2"]),
            ],
            speaker_notes="On the left, what worked. On the right, where we fell short and why.",
        ),
        4: SlideContentDraft(
            bullets=[Bullet(text="North earns the most revenue", source_ids=["S1"])],
            speaker_notes="This chart compares total revenue by region, computed from the sales file.",
            chart=ChartSpec(
                chart_type="bar", title="Revenue by region", document_id=SALES_DOCUMENT_ID,
                x_column="Region", y_columns=["Revenue"], aggregation="sum",
            ),
        ),
        5: SlideContentDraft(
            bullets=[Bullet(text="Laptops outsell phones in most regions", source_ids=["S1"])],
            speaker_notes="Here are the first rows of the sales data behind the previous chart.",
            table=TableSpec(
                title="Sales rows", document_id=SALES_DOCUMENT_ID,
                columns=["Region", "Product", "Revenue"], max_rows=5,
            ),
        ),
    }


def sample_client() -> FakeClient:
    drafts = sample_drafts()
    return FakeClient.sequence(
        *(drafts[number] for number in sorted(drafts))
    )


def build_sample_deck():
    from app.agents.slide_content_agent import generate_presentation_content

    outline = mock_outline()
    by_number = {slide.slide_number: slide for slide in outline.slides}
    client = sample_client()

    deck = generate_presentation_content(
        outline,
        chunks_for_slide=lambda item: mock_chunks(
            by_number[item.slide_number].slide_number
        ),
        data_files=[sales_source()],
        style="professional",
        client=client,
    )

    client.assert_finished()
    return outline, deck


if __name__ == "__main__":
    outline, deck = build_sample_deck()
    (SAMPLES_DIR / "sample_outline.json").write_text(outline.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (SAMPLES_DIR / "sample_deck.json").write_text(deck.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print("Wrote", SAMPLES_DIR / "sample_outline.json", "and", SAMPLES_DIR / "sample_deck.json")
