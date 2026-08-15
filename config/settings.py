"""Central paths, ports, and config for the Kestrel Control Tower.

LLM provider resolution order (stub — implemented fully in app/llm/resolver.py):
  1. ANTHROPIC_API_KEY env var -> Anthropic provider
  2. Probe localhost:11434 (Ollama) -> Ollama provider
  3. Neither available -> None (ask-anything reports "no_llm_configured", never a 500)
"""

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = REPO_ROOT / "data"
SOURCE_DB_PATH = DATA_DIR / "kestrel_ops.db"
ANALYTICS_DB_PATH = DATA_DIR / "analytics.db"
REF_DIR = DATA_DIR / "ref"
RAW_CACHE_DIR = DATA_DIR / "raw_cache"
CITY_NAME_MAP_PATH = REF_DIR / "city_name_map.csv"

API_HOST = "0.0.0.0"
API_PORT = 8000
FRONTEND_PORT = 3000

# Mock services (assignment pack)
FREIGHT_API_BASE_URL = os.environ.get("FREIGHT_API_BASE_URL", "http://localhost:8088")
BAZAARPULSE_BASE_URL = os.environ.get("BAZAARPULSE_BASE_URL", "http://localhost:8080")

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")


def resolve_llm_provider_name() -> str | None:
    """Return which LLM provider is available, without instantiating one.

    Full provider construction (app/llm/resolver.py, a later task) follows this
    same order: env var -> Ollama probe -> None.
    """
    if ANTHROPIC_API_KEY:
        return "anthropic"
    # Real Ollama probe (HTTP GET /api/tags) lands in app/llm/resolver.py.
    # Stubbed here as "unavailable" so downstream code has a stable shape to call.
    return None
