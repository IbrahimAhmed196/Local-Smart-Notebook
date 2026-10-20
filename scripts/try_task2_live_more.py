"""More live checks for Task 2 (run after try_task2_live.py passes).

  Test 2  hard inputs   : no source text, Arabic sources, an Excel file with two sheets, a chart with no data file
  Test 3  consistency   : the whole 5-slide deck 3 times, to see how often the real model gets it right

From the repo root:   python scripts/try_task2_live_more.py          # real Qwen via Ollama (about 5 minutes)
                      python scripts/try_task2_live_more.py --fake   # checks the script itself, no Ollama
"""
import argparse
import re
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

import pandas as pd  # noqa: E402

from app.agents.slide_content_agent import generate_presentation_content, generate_slide_content  # noqa: E402
from app.schemas.slide_content import Bullet, ChartSpec, SlideContentDraft, SourceChunk  # noqa: E402
from app.schemas.slides import SlideOutlineItem  # noqa: E402
from app.tools.chart_tool import DataSource  # noqa: E402
from tests.slide_samples import FakeClient, mock_chunks, mock_outline, sales_source, sample_client  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--fake", action="store_true")
args = ap.parse_args()

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail else ""))


def fake_responder(prompt: str) -> SlideContentDraft:
    """Only used with --fake: a plausible answer for each case, so the script itself can be checked."""
    arabic = bool(re.search(r"[\u0600-\u06FF]", prompt))
    if "LAYOUT: chart" in prompt:
        return SlideContentDraft(
            bullets=[Bullet(text="Costs by department", source_ids=[])],
            speaker_notes="Notes.",
            chart=ChartSpec(chart_type="bar", title="Costs", document_id=7, sheet="Costs",
                            x_column="Department", y_columns=["Cost"]),
        )
    text = "نمت الإيرادات بنسبة 12 في المئة" if arabic else "Revenue grew 12 percent"
    ids = ["S1"] if "[S1]" in prompt else []
    return SlideContentDraft(bullets=[Bullet(text=text, source_ids=ids)], speaker_notes="Notes.")


if args.fake:
    def make_client():
        return FakeClient(fake_responder)
else:
    from app.llm.ollama_client import OllamaJSONClient

    def make_client():
        return OllamaJSONClient()


def item(number, title, purpose, layout):
    return SlideOutlineItem(slide_number=number, title=title, purpose=purpose, layout_type=layout)


def one_slide(it, chunks=(), data_files=(), audience="Management team"):
    return generate_slide_content(it, presentation_title="Test deck", audience=audience, style=None,
                                  chunks=list(chunks), data_files=list(data_files), client=make_client())


def failed(slide):
    return any("placeholder" in w for w in slide.warnings)


print("=== TEST 2: hard inputs ===")

# 2a. no source text at all
s = one_slide(item(1, "Why this matters", "Explain the topic in general", "bullet_points"))
check("2a no source text: bullets written, nothing cited, no crash",
      not failed(s) and len(s.bullets) > 0 and not s.citations and all(not b.source_ids for b in s.bullets),
      f"{len(s.bullets)} bullets")

# 2b. Arabic sources -> Arabic answer
arabic_chunks = [
    SourceChunk(chunk_id="ar-1", document_id=5, filename="تقرير.pdf", page=1,
                text="نمت الإيرادات بنسبة 12 في المئة خلال عام 2025، وكانت المنطقة الشمالية الأقوى."),
    SourceChunk(chunk_id="ar-2", document_id=5, filename="تقرير.pdf", page=2,
                text="تأخرت مبيعات الهواتف في المنطقة الغربية بسبب مشاكل في الإمداد."),
]
s = one_slide(item(2, "النتائج الرئيسية", "تلخيص أهم النتائج", "bullet_points"), arabic_chunks)
arabic_text = " ".join(b.text for b in s.bullets)
check("2b Arabic sources: bullets are written in Arabic", not failed(s) and bool(re.search(r"[\u0600-\u06FF]", arabic_text)),
      arabic_text[:60])
check("2b Arabic sources: cited ids are real chunk ids",
      {c.source_id for c in s.citations} <= {"ar-1", "ar-2"})

# 2c. Excel workbook with two sheets: the chart must use the right sheet and real numbers
tmp = Path(tempfile.mkdtemp())
book = tmp / "company.xlsx"
with pd.ExcelWriter(book) as writer:
    pd.DataFrame({"Region": ["North", "South", "North", "South"], "Revenue": [100, 200, 50, 70]}).to_excel(
        writer, sheet_name="Sales", index=False)
    pd.DataFrame({"Department": ["IT", "HR", "IT", "Ops"], "Cost": [30, 20, 15, 40]}).to_excel(
        writer, sheet_name="Costs", index=False)
excel = DataSource(document_id=7, filename="company.xlsx", path=book)
s = one_slide(item(3, "Costs by Department", "Show which department costs the most", "chart"),
              mock_chunks(2), [excel])
if s.chart is None:
    check("2c Excel with two sheets: chart built", False, "; ".join(s.warnings)[:200])
else:
    frames = pd.read_excel(book, sheet_name=None)
    right = False
    for df in frames.values():
        for cat in df.select_dtypes(exclude="number").columns:
            for ser in s.chart.series:
                if ser.name in df.columns:
                    exp = df.groupby(cat)[ser.name].sum()
                    got = dict(zip(s.chart.categories, ser.values))
                    if got and set(got) <= set(exp.index) and all(abs(exp[k] - v) < 1e-6 for k, v in got.items()):
                        right = True
    check("2c Excel with two sheets: chart numbers equal the workbook's real sums", right, s.chart.source)

# 2d. chart requested but no spreadsheet exists: must not invent numbers
s = one_slide(item(4, "Revenue by Region", "Show revenue", "chart"), mock_chunks(2), [])
check("2d chart with no data file: falls back to bullets, no chart, warning given",
      s.chart is None and s.layout_type == "bullet_points" and any("spreadsheet" in w for w in s.warnings))

print("\n=== TEST 3: consistency (whole deck x3) ===")
runs = 3
perfect = 0
times = []
for n in range(1, runs + 1):
    start = time.time()
    client = sample_client() if args.fake else make_client()
    deck = generate_presentation_content(
        mock_outline(), chunks_for_slide=lambda it: mock_chunks(it.slide_number),
        data_files=[sales_source()], client=client)
    took = time.time() - start
    times.append(took)
    bad = [x.slide_number for x in deck.slides if failed(x)]
    charts_ok = all(x.chart is not None for x in deck.slides if x.layout_type == "chart")
    tables_ok = all(x.table is not None for x in deck.slides if x.layout_type == "table")
    ok = not bad and charts_ok and tables_ok
    perfect += ok
    print(f"  run {n}: {took:.0f}s, placeholder slides: {bad or 'none'}, chart ok: {charts_ok}, table ok: {tables_ok}")
check(f"3 consistency: {perfect}/{runs} runs had no placeholder and a real chart and table", perfect == runs,
      f"average {sum(times) / len(times):.0f}s per deck")

print("\nRESULT:", "ALL PASS" if all(results) else "SOME CHECKS FAILED")
sys.exit(0 if all(results) else 1)
