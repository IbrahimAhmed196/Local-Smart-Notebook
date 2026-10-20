"""Task1: in presentation Ollama integration (Stage 2).om"""
import json
import requests
from pydantic import BaseModel
from typing import Type

class OllamaJSONClient:
    def __init__(self, model_name: str = "qwen2.5:7b-instruct", base_url: str = "http://localhost:11434"):
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

        for _ in range(2):
            try:
                response = requests.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                content = response.json()["message"]["content"]
                data = json.loads(content)
                return response_schema(**data)
            except (Exception, ValueError):
                continue
        
        raise RuntimeError("Failed to generate valid JSON matching schema from Ollama.")

