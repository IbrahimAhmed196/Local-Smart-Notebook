from pathlib import Path
from app.infographic.analysis import (
    parse_report,
    call_ollama,
    find_line,
)

report = Path("city_transport_report.txt").read_text(encoding="utf-8-sig")
lines = parse_report(report)

print("\n=== REPORT LINES ===")
for section, line in lines:
    print(repr(line))

print("\n=== OLLAMA OUTPUT ===")
data = call_ollama(report)
for item in data.get("items", []):
    title = item.get("title", "")
    print(f"\nItem title: {title!r}")

    for metric in item.get("metrics", []):
        value = metric.get("value")
        print(
            f"  Metric: {metric.get('name')!r}, "
            f"value={value!r}, "
            f"matched_line={find_line(lines, title, value)!r}"
        )
