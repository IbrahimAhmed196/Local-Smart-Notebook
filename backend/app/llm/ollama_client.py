"""Task1: in presentation Ollama integration (Stage 2).om"""
import json
import logging
import requests
from pydantic import BaseModel, ValidationError
from typing import Type

from app.core.config import settings

log = logging.getLogger(__name__)

# Week 6 presentation edits (LLM-01): the JSON client now has timeouts, separate error types,
# a log line for every failed attempt, and a retry that tells the model what was wrong.
MAX_ATTEMPTS = 2  # first try + one retry with the validation error in the prompt


class OllamaError(RuntimeError):
    """Base class: callers can catch this (or RuntimeError, as before) and show the message."""


class OllamaUnreachableError(OllamaError):
    """Ollama is not running / not reachable, or the model is not installed."""


class OllamaTimeoutError(OllamaError):
    """Ollama accepted the request but did not answer in time."""


class OllamaInvalidJSONError(OllamaError):
    """The model answered with text that is not valid JSON."""


class OllamaSchemaError(OllamaError):
    """The model answered with valid JSON that does not match the expected schema."""


class OllamaJSONClient:
    def __init__(
        self,
        model_name: str = "qwen2.5:3b",
        base_url: str = "http://localhost:11434",
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
    ):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout = (
            connect_timeout or settings.ollama_connect_timeout_seconds,
            read_timeout or settings.ollama_read_timeout_seconds,
        )

    def generate_json(
        self,
        prompt: str,
        response_schema: Type[BaseModel],
        temperature: float = 0.3,
        num_ctx: int | None = None,
    ) -> BaseModel:
        system_prompt = (
            f"You are an AI assistant that outputs strictly valid JSON matching this Pydantic schema: "
            f"{response_schema.model_json_schema()}"
        )
        options = {"temperature": temperature}
        if num_ctx:
            options["num_ctx"] = num_ctx

        user_prompt = prompt
        last_error: OllamaError | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "format": "json",
                "stream": False,
                "options": options,
            }
            try:
                content = self._post(payload)
                return self._parse(content, response_schema)
            except (OllamaInvalidJSONError, OllamaSchemaError) as exc:
                # The model can fix this if it is told what was wrong; asking again with the
                # identical prompt would usually give the identical mistake.
                log.warning("Ollama attempt %s/%s failed: %s", attempt, MAX_ATTEMPTS, exc)
                last_error = exc
                user_prompt = (
                    f"{prompt}\n\nYour previous answer was rejected: {exc}\n"
                    "Answer again with ONLY corrected JSON that matches the schema."
                )
            except OllamaError as exc:
                # Not running / timeout / HTTP error: retrying would only wait again.
                log.warning("Ollama attempt %s/%s failed: %s", attempt, MAX_ATTEMPTS, exc)
                raise

        # Keep the real reason (bad JSON or schema error) so it can be read in the logs and the UI.
        raise type(last_error)(
            f"The AI model did not return valid JSON after {MAX_ATTEMPTS} attempts. "
            f"Last error: {type(last_error.__cause__ or last_error).__name__}: {str(last_error)[:600]}"
        ) from last_error.__cause__

    def _post(self, payload: dict) -> str:
        """One HTTP call. Returns the model's text or raises a readable OllamaError."""
        try:
            response = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.ConnectionError as exc:  # also covers a connect timeout
            raise OllamaUnreachableError(
                f"Cannot reach Ollama at {self.base_url}. Start it with: ollama serve"
            ) from exc
        except requests.Timeout as exc:
            raise OllamaTimeoutError(
                f"The AI model did not answer within {self.timeout[1]:.0f} seconds."
            ) from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            if status == 404:
                raise OllamaUnreachableError(
                    f"The model '{self.model_name}' is not installed. Run: ollama pull {self.model_name}"
                ) from exc
            raise OllamaError(f"The AI model returned an error (HTTP {status}).") from exc
        except requests.RequestException as exc:
            raise OllamaError(f"Could not call the AI model: {exc}") from exc

        try:
            return response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise OllamaInvalidJSONError(f"Ollama sent an unreadable reply ({type(exc).__name__}).") from exc

    @staticmethod
    def _parse(content: str, response_schema: Type[BaseModel]) -> BaseModel:
        try:
            data = json.loads(content)
        except (ValueError, TypeError) as exc:
            raise OllamaInvalidJSONError(f"The answer is not valid JSON ({exc}).") from exc
        try:
            return response_schema.model_validate(data)
        except ValidationError as exc:
            raise OllamaSchemaError(f"The JSON does not match the schema: {exc}") from exc


class OllamaChatClient:
    """Plain-text chat with the local Ollama model (used by the notebook chat).

    `messages` is the usual list of {"role": "system" | "user" | "assistant", "content": str}.
    Raises LlmChatError with a readable message when Ollama or the model is not available.
    """

    def __init__(
        self,
        model_name: str = "qwen2.5:3b",
        base_url: str = "http://localhost:11434",
        timeout: float = 180,
    ):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
        num_ctx: int | None = None,
    ) -> str:
        options: dict = {"temperature": temperature}
        if num_ctx:
            options["num_ctx"] = num_ctx
        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
            "options": options,
        }
        try:
            response = requests.post(
                f"{self.base_url}/api/chat", json=payload, timeout=self.timeout
            )
        except requests.ConnectionError:
            raise LlmChatError(
                f"Cannot reach Ollama at {self.base_url}. Start it with: ollama serve"
            )
        except requests.Timeout:
            raise LlmChatError("The AI model took too long to answer. Please try again.")
        except requests.RequestException as exc:
            raise LlmChatError(f"Could not call the AI model: {exc}")

        if response.status_code == 404:
            raise LlmChatError(
                f"The model '{self.model_name}' is not installed. "
                f"Run: ollama pull {self.model_name}"
            )
        if not response.ok:
            raise LlmChatError(f"The AI model returned an error ({response.status_code}).")

        try:
            answer = (response.json().get("message") or {}).get("content", "")
        except ValueError:
            raise LlmChatError("The AI model returned an unreadable answer.")
        answer = answer.strip()
        if not answer:
            raise LlmChatError("The AI model returned an empty answer.")
        return answer


class LlmChatError(RuntimeError):
    """The chat model could not answer (Ollama down, model missing, timeout ...)."""
