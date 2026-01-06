from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .http import HttpClient


@dataclass(frozen=True)
class OgcSource:
    """
    Minimal client for OGC API Features endpoints like:
      - https://api.ra.no/kulturminner/collections
      - https://api.ra.no/kulturminner/collections/kulturminner/items?f=json&limit=100&offset=0
    """

    api_base: str  # e.g. "https://api.ra.no/kulturminner"
    http: HttpClient = HttpClient()

    def collections(self) -> list[dict[str, Any]]:
        payload = self.http.get_json(f"{self.api_base}/collections", params={"f": "json"})
        return list(payload.get("collections", []))

    def iter_items(
        self,
        collection_id: str,
        *,
        limit: int = 50,
        max_items: int | None = None,
        bbox: str | None = None,
        start_offset: int = 0,
    ) -> Iterable[dict[str, Any]]:
        """
        Iterates GeoJSON features for a collection using OGC paging via `offset`.

        Note: Some api.ra.no responses become invalid/truncated when `limit` is too large
        (even with HTTP 200). We therefore default to a conservative page size.
        """
        url = f"{self.api_base}/collections/{collection_id}/items"
        params: dict[str, Any] = {"f": "json", "limit": int(limit), "offset": int(start_offset)}
        if bbox:
            params["bbox"] = bbox

        yielded = 0
        while True:
            payload = None
            cur_limit = int(params.get("limit", limit))
            for _attempt in range(4):
                try:
                    payload = self.http.get_json(url, params=params)
                    break
                except Exception as exc:
                    cur_limit = max(5, cur_limit // 2)
                    params["limit"] = cur_limit
                    if _attempt >= 3:
                        raise exc

            assert payload is not None
            feats = payload.get("features") or []
            for feat in feats:
                yield feat
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return

            if not feats:
                return
            params["offset"] = int(params.get("offset", 0)) + len(feats)


