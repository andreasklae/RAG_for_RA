from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import requests
from requests.exceptions import HTTPError
from requests.exceptions import JSONDecodeError as RequestsJSONDecodeError


@dataclass(frozen=True)
class HttpClient:
    """
    Small resilient JSON HTTP client.

    Note: `api.ra.no` occasionally returns truncated/invalid JSON even with HTTP 200.
    We use retries and request identity encoding to reduce compression-related truncation issues.
    """

    timeout_s: float = 60.0
    user_agent: str = "rag-for-ra/0.1"
    retries: int = 5
    backoff_s: float = 1.0

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        }
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=self.timeout_s)
                resp.raise_for_status()
                return resp.json()
            except (RequestsJSONDecodeError, ValueError) as exc:
                last_exc = exc
                if attempt >= self.retries:
                    break
                time.sleep(self.backoff_s * (2**attempt))
            except HTTPError as exc:
                last_exc = exc
                status = getattr(exc.response, "status_code", None)
                if status in {429, 500, 502, 503, 504} and attempt < self.retries:
                    time.sleep(self.backoff_s * (2**attempt))
                    continue
                break
            except Exception as exc:  # noqa: BLE001 - boundary retry wrapper
                last_exc = exc
                if attempt >= self.retries:
                    break
                time.sleep(self.backoff_s * (2**attempt))
        assert last_exc is not None
        raise last_exc


