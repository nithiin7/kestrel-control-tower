"""LLM provider resolution: ANTHROPIC_API_KEY -> Ollama probe -> None.

Never raises and never blocks app startup — the Ollama probe uses a short
timeout, and any construction/probe failure is swallowed and treated as
"provider unavailable" rather than propagated. `/api/ask` (a later task)
must be able to call resolve_llm_provider() unconditionally and get either
a working provider or None, nothing else.
"""

import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.ollama_provider import OllamaProvider
from config.settings import OLLAMA_BASE_URL, OLLAMA_MODEL

OLLAMA_PROBE_TIMEOUT_SECONDS = 1.0


def resolve_llm_provider() -> LLMProvider | None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            return AnthropicProvider(api_key=api_key)
        except Exception:
            return None

    try:
        response = httpx.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=OLLAMA_PROBE_TIMEOUT_SECONDS)
        if response.status_code == 200:
            return OllamaProvider(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL)
    except Exception:
        pass

    return None
