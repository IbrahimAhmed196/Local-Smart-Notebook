"""Run Task 2 against the REAL Ollama model (or --fake) and check the result.

From the repo root:   python scripts/try_task2_live.py          # real Qwen via Ollama
                      python scripts/try_task2_live.py --fake   # no Ollama needed
Writes the deck to docs/samples/live_deck.json so you can read it.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

import pandas as pd  # noqa: E402

from app.agents.slide_content_agent import generate_presentation_content  # noqa: E402
from app.schemas.slide_content import PresentationContent  # noqa: E402
from tests.slide_samples import SALES_CSV, mock_chunks, mock_outline, sales_source, sample_client  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--fake", action="store_true", help="use the fake client instead of Ollama")
args = ap.parse_args()

outline = mock_outline()
if args.fake:
    client = sample_client()
else:
    from app.llm.ollama_client import OllamaJSONClient
    client = OllamaJSONClient()

times = []
start = time.time()


def progress(done, total):
    times.append(time.time() - start)
    print(f"  slide {done}/{total} done at {times[-1]:.0f}s", flush=True)


deck = generate_presentation_content(
    outline,
    chunks_for_slide=lambda item: mock_chunks(item.slide_number),
    data_files=[sales_source()],
    client=client,
    on_progress=progress,
)
total = time.time() - start

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + (f"  ({detail})" if detail else ""))


# 1. valid JSON that re-parses against the schema
check("deck re-validates against PresentationContent", bool(PresentationContent.model_validate(deck.model_dump())))
# 2. one slide per outline item, in order
check("slide count and order match the outline",
      [s.slide_number for s in deck.slides] == sorted(i.slide_number for i in outline.slides),
      f"{len(deck.slides)} of {len(outline.slides)}")
# 3. no placeholders (a placeholder means the model call failed)
failed = [s.slide_number for s in deck.slides if any("placeholder" in w for w in s.warnings)]
check("no slide fell back to a placeholder", not failed, f"failed slides: {failed}" if failed else "")
# 4. every cited id was supplied for that slide
bad = []
for s in deck.slides:
    allowed = {c.chunk_id for c in mock_chunks(s.slide_number)}
    cited = {i for b in s.bullets + s.right_bullets for i in b.source_ids} | {c.source_id for c in s.citations}
    if not cited <= allowed:
        bad.append((s.slide_number, sorted(cited - allowed)))
check("every cited source id exists among that slide's chunks", not bad, str(bad) if bad else "")
# 5. chart numbers equal an independent pandas computation
frame = pd.read_csv(SALES_CSV)
for s in deck.slides:
    if s.chart:
        x = s.chart.categories
        ok = True
        for ser in s.chart.series:
            if ser.name in frame.columns and s.chart.categories and frame.columns[0] != ser.name:
                for col in frame.columns:
                    if set(map(str, frame[col])) >= set(x):
                        expected = frame.groupby(col)[ser.name].sum()
                        ok &= all(abs(expected[c] - v) < 1e-6 for c, v in zip(x, ser.values) if c in expected)
                        break
        check(f"slide {s.slide_number} chart numbers match the CSV", ok, s.chart.source)
    if s.table:
        check(f"slide {s.slide_number} table has real rows", len(s.table.rows) > 0, s.table.source)
# 6. text limits the renderer relies on
check("no slide has more than 6 bullets", all(len(s.bullets) <= 6 for s in deck.slides))
check("every content slide has speaker notes",
      all(s.speaker_notes for s in deck.slides if s.layout_type != "title"))

out = ROOT / "docs" / "samples" / "live_deck.json"
out.write_text(deck.model_dump_json(indent=2), encoding="utf-8")
print(f"\nTotal {total:.0f}s for {len(deck.slides)} slides. Warnings:")
for s in deck.slides:
    for w in s.warnings:
        print("  -", w)
print(f"Deck written to {out}")
print("\nRESULT:", "ALL PASS" if all(results) else "SOME CHECKS FAILED")
sys.exit(0 if all(results) else 1)
