from __future__ import annotations

import argparse
from pathlib import Path

from tqdm import tqdm

from .documents import feature_to_document
from .io import write_jsonl, write_jsonl_stream_append
from .ogc import OgcSource
from .openai_utils import REPO_ROOT


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest OGC API Features into normalized RAG documents (JSONL).")
    p.add_argument(
        "--dataset",
        required=True,
        choices=["kulturminner", "brukerminner", "kulturmiljoer"],
        help="Dataset base on api.ra.no (used as API base prefix).",
    )
    p.add_argument(
        "--collection",
        required=True,
        help="Collection id under the dataset (see /collections). Example: kulturminner, brukerminner, sikringssoner.",
    )
    p.add_argument("--bbox", default=None, help="Optional bbox filter: minLon,minLat,maxLon,maxLat (CRS84).")
    p.add_argument("--limit", type=int, default=50, help="Page size for OGC paging (keep small to avoid truncation).")
    p.add_argument(
        "--max-items",
        type=int,
        default=5000,
        help="Max features to ingest. Use 0 for unlimited (full dataset).",
    )
    p.add_argument("--append", action="store_true", help="Append to output file instead of overwriting (manual resume).")
    p.add_argument(
        "--out",
        default=None,
        help="Output JSONL path. Default: artifacts/<dataset>__<collection>.jsonl",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    api_base = f"https://api.ra.no/{args.dataset}"
    src = OgcSource(api_base=api_base)

    # Best-effort license from OpenAPI.
    license_name = None
    license_url = None
    try:
        openapi = src.http.get_json(f"{api_base}/api", params={"f": "json"})
        lic = (openapi.get("info") or {}).get("license") or {}
        license_name = lic.get("name")
        license_url = lic.get("url")
    except Exception:
        pass

    out_path = Path(args.out) if args.out else REPO_ROOT / "artifacts" / f"{args.dataset}__{args.collection}.jsonl"
    max_items = None if args.max_items == 0 else args.max_items

    def row_iter():
        for feat in tqdm(
            src.iter_items(args.collection, limit=args.limit, max_items=max_items, bbox=args.bbox),
            desc=f"{args.dataset}/{args.collection}",
        ):
            doc = feature_to_document(
                dataset=args.dataset,
                collection=args.collection,
                feature=feat,
                license_name=license_name,
                license_url=license_url,
            )
            yield doc.to_dict()

    if args.append:
        n = write_jsonl_stream_append(out_path, row_iter())
    else:
        n = write_jsonl(out_path, row_iter())

    print(f"Wrote {n} documents to {out_path}")


if __name__ == "__main__":
    main()


