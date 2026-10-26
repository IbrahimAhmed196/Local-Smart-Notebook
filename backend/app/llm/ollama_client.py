"""Task1: in presentation Ollama integration (Stage 2).om"""
import json
import requests
from pydantic import BaseModel
from typing import Type

class OllamaJSONClient:
    def __init__(self, model_name: str = "qwen2.5:3b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url

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
        
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": temperature}
        }
        if num_ctx:
            payload["options"]["num_ctx"] = num_ctx

        last_error = None
        for _ in range(2):
            try:
                response = requests.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                content = response.json()["message"]["content"]
                data = json.loads(content)
                return response_schema(**data)
            except (Exception, ValueError) as exc:
                last_error = exc
                continue

        # Keep the real reason (bad JSON, schema error, connection problem) so it can be read in the logs.
        raise RuntimeError(
            "Failed to generate valid JSON matching schema from Ollama. "
            f"Last error: {type(last_error).__name__}: {str(last_error)[:600]}"
        )



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
