"""Render every JSON in samples/ to PNG + HTML - handy for designing templates without the LLM.

    python -m app.infographic.render_samples [output_dir]      (default: ./infographic_output)
"""
import json
import sys
from pathlib import Path

from app.infographic.rendering import render_to_file
from app.infographic.schema import InfographicPlan

SAMPLES_DIR = Path(__file__).parent / "samples"


def main(out_dir: str = "infographic_output") -> None:
    for path in sorted(SAMPLES_DIR.glob("*.json")):
        plan = InfographicPlan.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for ext in ("png", "html"):
            target = render_to_file(plan, Path(out_dir) / f"{path.stem}.{ext}")
        print(f"rendered {path.stem:<16} -> {target.parent}")


if __name__ == "__main__":
    main(*sys.argv[1:2])
