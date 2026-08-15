"""Anthropic LLMProvider — used when ANTHROPIC_API_KEY is set (resolver.py)."""

import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from app.llm.base import LLMProvider

MODEL = "claude-opus-5"
MAX_TOKENS = 4096


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)

    def ask(self, prompt: str) -> str:
        response = self._client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        return next((block.text for block in response.content if block.type == "text"), "")
