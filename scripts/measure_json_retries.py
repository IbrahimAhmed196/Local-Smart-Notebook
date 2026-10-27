"""Week 6 presentation edits (LLM-02): how often does the model answer with invalid JSON?

Runs the same request several times against the REAL Ollama model, once in the old mode
(format="json") and once with the JSON schema in "format", and prints a table to paste into
docs/slide-content-contract.md.

From the repo root:
    python scripts/measure_json_retries.py                  # 10 outline requests per mode
    python scripts/measure_json_retries.py --target slide   # 10 chart-slide requests per mode
    python scripts/measure_json_retries.py --runs 5 --model qwen2.5:7b-instruct

"Bad answers" are replies that were not valid JSON or did not match the schema, i.e. the times the client
had to ask again. It needs Ollama running with the model pulled; the tests do not need this script.
"""
import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.agents.slide_content_agent import generate_slide_content  # noqa: E402
from app.llm.ollama_client import OllamaJSONClient  # noqa: E402
from app.presentations.outline import generate_outline  # noqa: E402
from app.schemas.presentations import PresentationCreate  # noqa: E402
from tests.slide_samples import mock_chunks, mock_outline, sales_source  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--runs", type=int, default=10, help="requests per mode (default 10)")
ap.add_argument("--target", choices=("outline", "slide"), default="outline")
ap.add_argument("--model", default=None, help="default: PRESENTATION_MODEL from .env")
ap.add_argument("--base-url", default=None, help="default: OLLAMA_BASE_URL from .env")
args = ap.parse_args()

outline = mock_outline()
chart_slide = next(item for item in outline.slides if item.layout_type == "chart")
options = PresentationCreate(topic="Sales review 2025 for the management team", num_slides=6).model_dump()


def one_run(client) -> bool:
    """One request; True when it ended without an error."""
    if args.target == "outline":
        try:
            generate_outline(client, options, mock_chunks(2) + mock_chunks(3), ["sample_sales.csv"])
            return True
        except Exception as exc:  # noqa: BLE001 (any failure counts as a failed run)
            print(f"    run failed: {type(exc).__name__}: {str(exc)[:120]}")
            return False
    slide = generate_slide_content(
        chart_slide,
        presentation_title=outline.presentation_title,
        audience=outline.target_audience,
        chunks=mock_chunks(chart_slide.slide_number),
        data_files=[sales_source()],
        client=client,
    )
    return not any("placeholder" in w for w in slide.warnings)  # a placeholder = the model call failed


rows = []
for label, structured in (("format=\"json\" (before)", False), ("JSON schema (after)", True)):
    client = OllamaJSONClient(model_name=args.model, base_url=args.base_url, structured_output=structured)
    print(f"{label}: model {client.model_name}")
    failed, started = 0, time.time()
    for number in range(1, args.runs + 1):
        ok = one_run(client)
        failed += 0 if ok else 1
        print(f"  run {number}/{args.runs}: {'ok' if ok else 'FAILED'}  (bad answers so far: {client.bad_answers})", flush=True)
    rows.append((label, client, failed, (time.time() - started) / args.runs))

print(f"\nTarget: {args.target}, model: {rows[0][1].model_name}, {args.runs} runs per mode\n")
print("| Mode | Requests | Bad answers (retries) | Retry rate | Failed runs | Avg seconds/run |")
print("|---|---|---|---|---|---|")
for label, client, failed, seconds in rows:
    rate = client.bad_answers / client.calls if client.calls else 0
    print(f"| {label} | {client.calls} | {client.bad_answers} | {rate:.0%} | {failed} | {seconds:.0f} |")
if not rows[1][1].structured_output:
    print("\nWARNING: this Ollama rejected the JSON schema, so the 'after' row really ran in the old mode. "
          "Update Ollama (schemas need a recent version) and measure again.")
