"""Reusable Ollama clients for validated JSON generation and plain-text chat."""
import json
import logging
from typing import TypeVar
import requests
from pydantic import BaseModel, ValidationError
from app.core.config import settings
from app.llm.errors import LlmUnavailableError

T = TypeVar("T", bound=BaseModel)
log = logging.getLogger(__name__)

class OllamaError(RuntimeError):
    """Base error raised by the Ollama JSON client."""

class OllamaUnreachableError(OllamaError):
    """Ollama is unreachable or the requested model is missing."""

class OllamaTimeoutError(OllamaError):
    """Ollama did not answer within the configured timeout."""

class OllamaInvalidJSONError(OllamaError):
    """The model returned invalid JSON."""

class OllamaSchemaError(OllamaError):
    """The model returned JSON that does not match the requested schema."""

class OllamaFormatRejectedError(OllamaError):
    """The server rejected a JSON schema in the format field."""

class OllamaJSONClient:
    def __init__(
        self,
        model_name: str | None = None,
        base_url: str | None = None,
        connect_timeout: float | None = None,
        read_timeout: float | None = None,
        structured_output: bool | None = None,
    ):
        # Features supply their own model; otherwise use the generic default.
        self.model_name = model_name or settings.ollama_model
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.max_attempts = settings.ollama_json_max_attempts
        self.structured_output = (
            settings.ollama_structured_output
            if structured_output is None else structured_output
        )
        self.calls = 0
        self.bad_answers = 0
        self.timeout = (
            connect_timeout or settings.ollama_connect_timeout_seconds,
            read_timeout or settings.ollama_read_timeout_seconds,
        )

    def check_ready(self) -> None:
        """Fail before generation if Ollama or the requested model is missing."""
        try:
            reply = requests.get(f"{self.base_url}/api/tags", timeout=3)
            reply.raise_for_status()
        except requests.RequestException as exc:
            raise LlmUnavailableError(
                f"Cannot reach Ollama at {self.base_url}. Start it with: ollama serve"
            ) from exc
        try:
            payload = reply.json()
            models = payload["models"]
            if not isinstance(models, list):
                raise TypeError("models must be a list")
            names = [model["name"] for model in models]
            if not all(isinstance(name, str) for name in names):
                raise TypeError("model names must be strings")
        except (ValueError, KeyError, TypeError) as exc:
            raise LlmUnavailableError(
                "Ollama returned an unreadable model list. Check the Ollama server."
            ) from exc
        wanted = self.model_name
        if wanted not in names and f"{wanted}:latest" not in names:
            raise LlmUnavailableError(
                f"The model '{wanted}' is not installed. Run: ollama pull {wanted}"
            )

    def generate_json(
        self,
        prompt: str,
        response_schema: type[T],
        temperature: float = 0.3,
        num_ctx: int | None = None,
    ) -> T:
        schema = response_schema.model_json_schema()
        system_prompt = (
            "You are an AI assistant that outputs strictly valid JSON matching this Pydantic schema: "
            f"{schema}"
        )
        options = {"temperature": temperature}
        if num_ctx:
            options["num_ctx"] = num_ctx

        self.calls += 1
        user_prompt = prompt
        last_error: OllamaError | None = None
        attempt = 1
        while attempt <= self.max_attempts:
            payload = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "format": schema if self.structured_output else "json",
                "stream": False,
                "options": options,
            }
            try:
                content = self._post(payload)
                return self._parse(content, response_schema)
            except OllamaFormatRejectedError:
                log.warning(
                    "Ollama does not accept a JSON schema in 'format' (old version?); using format='json'"
                )
                self.structured_output = False
                continue
            except (OllamaInvalidJSONError, OllamaSchemaError) as exc:
                log.warning("Ollama attempt %s/%s failed: %s", attempt, self.max_attempts, exc)
                self.bad_answers += 1
                attempt += 1
                last_error = exc
                user_prompt = (
                    f"{prompt}\n\nYour previous answer was rejected: {exc}\n"
                    "Answer again with ONLY corrected JSON that matches the schema."
                )
            except OllamaError as exc:
                log.warning("Ollama attempt %s/%s failed: %s", attempt, self.max_attempts, exc)
                raise
        raise type(last_error)(
            f"The AI model did not return valid JSON after {self.max_attempts} attempts. "
            f"Last error: {type(last_error.__cause__ or last_error).__name__}: {str(last_error)[:600]}"
        ) from last_error.__cause__

    def _post(self, payload: dict) -> str:
        """Make one HTTP request and return the model's text."""
        try:
            response = requests.post(f"{self.base_url}/api/chat", json=payload, timeout=self.timeout)
            response.raise_for_status()
        except requests.ConnectionError as exc:
            raise OllamaUnreachableError(
                f"Cannot reach Ollama at {self.base_url}. Start it with: ollama serve"
            ) from exc
        except requests.Timeout as exc:
            raise OllamaTimeoutError(
                f"The AI model did not answer within {self.timeout[1]:.0f} seconds."
            ) from exc
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            if status == 400 and payload.get("format") != "json":
                raise OllamaFormatRejectedError(
                    "The server does not accept a JSON schema in 'format'."
                ) from exc
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
            raise OllamaInvalidJSONError(
                f"Ollama sent an unreadable reply ({type(exc).__name__})."
            ) from exc

    @staticmethod
    def _parse(content: str, response_schema: type[T]) -> T:
        try:
            data = json.loads(content)
        except (ValueError, TypeError) as exc:
            raise OllamaInvalidJSONError(f"The answer is not valid JSON ({exc}).") from exc
        try:
            return response_schema.model_validate(data)
        except ValidationError as exc:
            raise OllamaSchemaError(f"The JSON does not match the schema: {exc}") from exc

class OllamaChatClient:
    """Reusable plain-text chat client."""

    def __init__(
        self,
        model_name: str | None = None,
        base_url: str | None = None,
        timeout: float = 180,
    ):
        self.model_name = model_name or settings.ollama_model
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
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
    """The chat model could not answer."""
