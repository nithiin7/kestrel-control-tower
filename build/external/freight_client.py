"""httpx-based client for the partner freight/billing API.

Sends X-API-Key on every /v1/* call except /v1/health (the only endpoint
that doesn't require auth on the mock server). Retries on:
  - 429: sleeps for the server's Retry-After header (seconds) if present,
    else falls back to exponential backoff.
  - 503: no Retry-After is ever given for this status, so backs off
    exponentially from BACKOFF_BASE_SECONDS.

Chaos (429/503) is only injected on /v1/freight_invoices and
/v1/shipment_events (~15.1% combined) — /v1/health, /v1/carriers, and
/v1/fuel_surcharge never fail. The retry logic still lives here rather
than being scoped to just the chaotic endpoints, since T11's cursor-walk
ingest of /v1/freight_invoices reuses this same client.
"""

import random
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from config.settings import FREIGHT_API_BASE_URL

API_KEY = "kp_live_7f3a9c21"
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_ATTEMPTS = 6
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_MAX_SECONDS = 16.0


class FreightAPIError(RuntimeError):
    """Raised when a request exhausts all retry attempts."""


def _exponential_backoff(attempt: int) -> float:
    base = min(BACKOFF_BASE_SECONDS * (2 ** (attempt - 1)), BACKOFF_MAX_SECONDS)
    return base + random.uniform(0, base * 0.25)


class FreightAPIClient:
    def __init__(
        self,
        base_url: str = FREIGHT_API_BASE_URL,
        api_key: str = API_KEY,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "FreightAPIClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _get(self, path: str, params: dict | None = None, auth: bool = True) -> dict:
        url = f"{self.base_url}{path}"
        headers = {"X-API-Key": self.api_key} if auth else {}

        last_response: httpx.Response | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            response = self._client.get(url, params=params, headers=headers)
            last_response = response

            if response.status_code == 429:
                if attempt == MAX_ATTEMPTS:
                    break
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after is not None else _exponential_backoff(attempt)
                time.sleep(wait)
                continue

            if response.status_code == 503:
                if attempt == MAX_ATTEMPTS:
                    break
                time.sleep(_exponential_backoff(attempt))
                continue

            response.raise_for_status()
            return response.json()

        raise FreightAPIError(
            f"GET {path} failed after {MAX_ATTEMPTS} attempts, last status {last_response.status_code}"
        )

    def health(self) -> dict:
        return self._get("/v1/health", auth=False)

    def carriers(self) -> list[dict]:
        return self._get("/v1/carriers")["data"]

    def fuel_surcharge(self, month: str) -> dict:
        return self._get("/v1/fuel_surcharge", params={"month": month})

    def freight_invoices(
        self,
        cursor: str | None = None,
        limit: int = 200,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict:
        params: dict = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        if date_from:
            params["from"] = date_from
        if date_to:
            params["to"] = date_to
        return self._get("/v1/freight_invoices", params=params)

    def shipment_events(self, invoice_id: str) -> dict:
        return self._get("/v1/shipment_events", params={"invoice_id": invoice_id})
