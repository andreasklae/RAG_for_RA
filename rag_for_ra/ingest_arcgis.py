from __future__ import annotations

import argparse
from pathlib import Path

from tqdm import tqdm

from .arcgis import ArcGisMapServer
from .documents import arcgis_feature_to_document
from .io import write_jsonl
from .openai_utils import REPO_ROOT


DEFAULT_MAPSERVER = "https://kart.ra.no/arcgis/rest/services/Distribusjon/Kulturminner20180301/MapServer"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest ArcGIS REST MapServer layer into normalized RAG documents (JSONL).")
    p.add_argument("--mapserver", default=DEFAULT_MAPSERVER, help="ArcGIS MapServer base URL (no trailing slash).")
    p.add_argument("--layer-id", type=int, required=True, help="Feature layer id (see MapServer?f=pjson).")
    p.add_argument("--layer-name", default=None, help="Optional human name for the layer (used in doc IDs).")
    p.add_argument("--bbox", default=None, help="Optional bbox filter (WGS84): minLon,minLat,maxLon,maxLat.")
    p.add_argument("--page-size", type=int, default=2000, help="ArcGIS page size (resultRecordCount).")
    p.add_argument("--max-items", type=int, default=5000, help="Max features to ingest (safety default). Use 0 for unlimited.")
    p.add_argument("--out", default=None, help="Output JSONL path. Default: artifacts/arcgis__<layerId>__<layerName>.jsonl")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    ms = ArcGisMapServer(mapserver_base=args.mapserver)

    # Best-effort license inference: described as NLOD via GeoNorge in email (verify if needed per-layer).
    license_name = "NLOD"
    license_url = "https://data.norge.no/nlod"

    layer_info = ms.layer_info(args.layer_id)
    layer_name = args.layer_name or layer_info.get("name") or f"layer_{args.layer_id}"

    out_path = Path(args.out) if args.out else REPO_ROOT / "artifacts" / f"arcgis__{args.layer_id}__{layer_name}.jsonl"

    max_items = None if args.max_items == 0 else args.max_items

    def row_iter():
        for feat in tqdm(
            ms.iter_layer_features(
                args.layer_id,
                bbox_wgs84=args.bbox,
                page_size=args.page_size,
                max_items=max_items,
            ),
            desc=f"arcgis layer {args.layer_id} ({layer_name})",
        ):
            doc = arcgis_feature_to_document(
                dataset="arcgis",
                layer_name=layer_name,
                feature=feat,
                license_name=license_name,
                license_url=license_url,
            )
            yield doc.to_dict()

    n = write_jsonl(out_path, row_iter())
    print(f"Wrote {n} documents to {out_path}")


if __name__ == "__main__":
    main()


