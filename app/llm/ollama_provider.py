"""Ollama LLMProvider — used when localhost:11434 is reachable (resolver.py)."""

import httpx

from app.llm.base import LLMProvider

REQUEST_TIMEOUT_SECONDS = 60.0


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def ask(self, prompt: str) -> str:
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return response.json().get("response", "")
