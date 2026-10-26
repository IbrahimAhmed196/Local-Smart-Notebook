"""Target interface for JSON language-model clients."""

import threading
from typing import Protocol, TypeVar

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


class LlmClient(Protocol):
    model_name: str

    def check_ready(self) -> None:
        """Raise LlmUnavailableError if the server or model is unavailable."""
        ...

    def generate_json(
        self,
        prompt: str,
        response_schema: type[T],
        temperature: float = 0.3,
        num_ctx: int | None = None,
        cancel_event: threading.Event | None = None,
    ) -> T:
        """Return a validated object.

        Raise LlmError for model failures.
        Raise GenerationCancelled when cancellation is implemented.
        """
        ...
