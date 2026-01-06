from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .http import HttpClient


@dataclass(frozen=True)
class ArcGisMapServer:
    """
    Minimal ArcGIS REST MapServer client.

    Example base URL:
      https://kart.ra.no/arcgis/rest/services/Distribusjon/Kulturminner20180301/MapServer
    """

    mapserver_base: str
    http: HttpClient = HttpClient()

    def service_info(self) -> dict[str, Any]:
        return self.http.get_json(self.mapserver_base, params={"f": "pjson"})

    def layer_info(self, layer_id: int) -> dict[str, Any]:
        return self.http.get_json(f"{self.mapserver_base}/{layer_id}", params={"f": "pjson"})

    def iter_layer_features(
        self,
        layer_id: int,
        *,
        where: str = "1=1",
        out_fields: str = "*",
        bbox_wgs84: str | None = None,  # "minLon,minLat,maxLon,maxLat"
        page_size: int = 2000,
        max_items: int | None = None,
    ) -> Iterable[dict[str, Any]]:
        url = f"{self.mapserver_base}/{layer_id}/query"
        offset = 0
        yielded = 0

        base_params: dict[str, Any] = {
            "f": "json",
            "where": where,
            "outFields": out_fields,
            "returnGeometry": "true",
            "outSR": 4326,
        }

        if bbox_wgs84:
            base_params.update(
                {
                    "geometryType": "esriGeometryEnvelope",
                    "geometry": bbox_wgs84,
                    "inSR": 4326,
                    "spatialRel": "esriSpatialRelIntersects",
                }
            )

        while True:
            params = dict(base_params)
            params["resultOffset"] = offset
            params["resultRecordCount"] = page_size

            payload = self.http.get_json(url, params=params)
            feats = payload.get("features") or []
            for feat in feats:
                yield feat
                yielded += 1
                if max_items is not None and yielded >= max_items:
                    return

            if not feats:
                return
            offset += len(feats)


