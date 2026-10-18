
from app.infographic.schema import InfographicPlan
from app.infographic.data_validation import validate_infographic_data

# Replace these values with your actual report and generated JSON.
report = """
CITY TRANSPORT REPORT (2025)
Survey of 1,000 residents in a fictional city

Transport Mode
Bus: 320 people (32%)
Metro: 280 people (28%)
Car: 220 people (22%)
Bicycle: 100 people (10%)
Walking: 80 people (8%)

Average One-Way Commute
Bus: 38 minutes
Metro: 29 minutes
Car: 34 minutes
Bicycle: 24 minutes
Walking: 18 minutes

Monthly Cost Per Person
Bus: $30
Metro: $42
Car: $160
Bicycle: $12
Walking: $0
"""

# Minimal example: replace with your actual generated plan.
data = {
    "schema_version": "1.0",
    "title": "Transport Report",
    "subtitle": "Survey of residents",
    "type": "comparison",
    "summary": "Comparison of transport modes.",
    "items": [
        {
            "id": "item_1",
            "title": "Bus",
            "description": "320 people (32%)",
            "date": None,
            "metrics": [
                {"name": "Usage Percentage", "value": 32, "unit": "%"},
                {
                    "name": "Average One-Way Commute",
                    "value": 48,
                    "unit": "minutes",
                },
                {"name": "Monthly Cost", "value": 30, "unit": "$"},
            ],
            "source_refs": ["src_1", "src_2", "src_3"],
        }
    ],
    "sources": [
        {
            "id": "src_1",
            "label": "Transport Mode",
            "page": None,
            "excerpt": "Bus: 320 people (32%)",
        },
        {
            "id": "src_2",
            "label": "Average One-Way Commute",
            "page": None,
            "excerpt": "Bus: 38 minutes",
        },
        {
            "id": "src_3",
            "label": "Monthly Cost Per Person",
            "page": None,
            "excerpt": "Bus: $30",
        },
    ],
}

plan = InfographicPlan.model_validate(data)
errors = validate_infographic_data(plan, report)

if errors:
    print("FAIL: Data verification failed")
    for error in errors:
        print("-", error)
else:
    print("PASS: All implemented data checks passed")
