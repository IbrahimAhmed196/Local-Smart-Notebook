

from pydantic import ValidationError

from app.infographic.analysis import analyze_report
from app.infographic.schema import InfographicPlan
from app.infographic.data_validation import validate_infographic_data


def generate_infographic_plan(report: str) -> InfographicPlan:
    if not report or not report.strip():
        raise ValueError("The source report is empty.")

    # Step 1: Extract JSON using the local Ollama model.
    data = analyze_report(report)

    # Step 2: Validate JSON structure and types.
    try:
        plan = InfographicPlan.model_validate(data)
    except ValidationError as exc:
        raise ValueError(
            f"Schema validation failed:\n{exc}"
        ) from exc

    # Step 3: Verify facts against the original report.
    errors = validate_infographic_data(plan, report)

    if errors:
        details = "\n".join(f"- {error}" for error in errors)
        raise ValueError(f"Data verification failed:\n{details}")

    return plan
