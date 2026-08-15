"""Unit test for app/llm/resolver.py — no network calls to /api/ask (doesn't exist yet)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.llm.resolver import resolve_llm_provider


def test_resolver_returns_none_with_no_api_key_and_no_ollama(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Point at a port nothing listens on, so the Ollama probe fails fast and deterministically.
    monkeypatch.setattr("app.llm.resolver.OLLAMA_BASE_URL", "http://localhost:1")

    provider = resolve_llm_provider()

    assert provider is None
