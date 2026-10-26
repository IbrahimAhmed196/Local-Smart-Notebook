import pytest
from requests.exceptions import Timeout

from app.schemas.slide_content import SlideContentDraft
from tests.fake_llm import ScriptedLLMClient


def test_client_consumes_responses_and_records_calls(scripted_llm):
    client = scripted_llm(
        '{"subtitle": "First"}',
        {"subtitle": "Second"},
        SlideContentDraft(subtitle="Third"),
    )

    for number, expected in enumerate(["First", "Second", "Third"]):
        result = client.generate_json(
            f"Prompt {number}",
            SlideContentDraft,
            temperature=0.1,
            num_ctx=4096,
        )
        assert result.subtitle == expected

    assert [call["prompt"] for call in client.calls] == [
        "Prompt 0",
        "Prompt 1",
        "Prompt 2",
    ]
    assert all(
        call["schema"] is SlideContentDraft
        and call["temperature"] == 0.1
        and call["num_ctx"] == 4096
        for call in client.calls
    )


@pytest.mark.parametrize(
    ("response", "exception_type", "message"),
    [
        ("bad JSON", RuntimeError, "JSONDecodeError"),
        (
            {"bullets": [{"text": 123}]},
            RuntimeError,
            "ValidationError",
        ),
        (Timeout("Model timed out"), Timeout, "Model timed out"),
    ],
)
def test_client_reports_scripted_failures(
    scripted_llm, response, exception_type, message
):
    client = scripted_llm(response)

    with pytest.raises(exception_type, match=message):
        client.generate_json("Prompt", SlideContentDraft)

    assert len(client.calls) == 1


def test_unexpected_calls_remain_detectable_after_being_caught():
    # Use the class directly because this deliberately violates the script.
    client = ScriptedLLMClient()

    with pytest.raises(AssertionError, match="No scripted"):
        client.generate_json("Unexpected", SlideContentDraft)

    with pytest.raises(AssertionError, match="after its scripted"):
        client.assert_finished()


def test_unused_responses_are_detected():
    client = ScriptedLLMClient({})

    with pytest.raises(AssertionError, match="not consumed"):
        client.assert_finished()