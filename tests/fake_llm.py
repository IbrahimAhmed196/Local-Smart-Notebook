"""Shared scripted LLM client for offline tests."""

import json
from collections import deque
from copy import deepcopy
from threading import Event
from app.llm.cancellation import raise_if_cancelled
from pydantic import BaseModel, ValidationError


class ScriptedLLMClient:
    model_name = "scripted-test-model"
    def __init__(self, *responses):
        self._responses = deque(deepcopy(responses))
        self.calls = []
        self.unexpected_calls = 0
        self.ready_checks = 0

    def check_ready(self) -> None:
        self.ready_checks += 1
        
    @classmethod
    def sequence(cls, *responses):
        """Compatibility with existing FakeClient.sequence(...) calls."""
        return cls(*responses)

    @property
    def remaining(self):
        return len(self._responses)

    def assert_finished(self):
        # Agents may catch exceptions, so also check unexpected calls here.
        assert self.unexpected_calls == 0, (
            f"LLM was called {self.unexpected_calls} time(s) "
            "after its scripted responses ran out."
        )
        assert self.remaining == 0, (
            f"{self.remaining} scripted LLM response(s) were not consumed."
        )

    def generate_json(
        self,
        prompt,
        response_schema,
        temperature=0.3,
        num_ctx=None,
        cancel_event: Event | None = None,
    ):
        raise_if_cancelled(cancel_event)
        self.calls.append({
            "prompt": prompt,
            "schema": response_schema,
            "temperature": temperature,
            "num_ctx": num_ctx,
            "cancel_event": cancel_event,
        })

        if not self._responses:
            self.unexpected_calls += 1
            raise AssertionError("No scripted LLM response remains.")

        response = self._responses.popleft()

        if isinstance(response, Exception):
            raise response

        try:
            if isinstance(response, BaseModel):
                data = response.model_dump(mode="json")
            elif isinstance(response, str):
                data = json.loads(response)
            else:
                data = deepcopy(response)

            return response_schema.model_validate(data)

        except (json.JSONDecodeError, ValidationError) as exc:
            # Match the current client's public failure type.
            raise RuntimeError(
                "Scripted LLM returned invalid content. "
                f"Last error: {type(exc).__name__}: {exc}"
            ) from exc