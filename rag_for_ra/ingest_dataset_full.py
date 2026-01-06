from __future__ import annotations

import argparse
from pathlib import Path

from tqdm import tqdm

from .documents import feature_to_document
from .io import write_jsonl
from .ogc import OgcSource
from .openai_utils import REPO_ROOT


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ingest ALL collections for an api.ra.no dataset into separate JSONL files.")
    p.add_argument(
        "--dataset",
        required=True,
        choices=["kulturminner", "brukerminner", "kulturmiljoer"],
        help="Dataset on api.ra.no.",
    )
    p.add_argument("--out-dir", default=None, help="Output dir. Default: artifacts/full_<dataset>/")
    p.add_argument(
        "--collections",
        default=None,
        help="Comma-separated list of collection ids to ingest. Default: all collections in /collections.",
    )
    p.add_argument("--limit", type=int, default=50, help="Paging size (keep small; see truncation note).")
    p.add_argument("--max-items-per-collection", type=int, default=0, help="0 = unlimited (full).")
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

    collections = src.collections()
    all_ids = [c.get("id") for c in collections if c.get("id")]
    if args.collections:
        wanted = {c.strip() for c in args.collections.split(",") if c.strip()}
        collection_ids = [cid for cid in all_ids if cid in wanted]
    else:
        collection_ids = all_ids

    out_dir = Path(args.out_dir) if args.out_dir else REPO_ROOT / "artifacts" / f"full_{args.dataset}"
    out_dir.mkdir(parents=True, exist_ok=True)

    max_items = None if args.max_items_per_collection == 0 else args.max_items_per_collection

    for cid in collection_ids:
        out_path = out_dir / f"{args.dataset}__{cid}.jsonl"
        print(f"\nIngesting {args.dataset}/{cid} → {out_path}")

        def row_iter():
            for feat in tqdm(
                src.iter_items(str(cid), limit=args.limit, max_items=max_items),
                desc=f"{args.dataset}/{cid}",
            ):
                doc = feature_to_document(
                    dataset=args.dataset,
                    collection=str(cid),
                    feature=feat,
                    license_name=license_name,
                    license_url=license_url,
                )
                yield doc.to_dict()

        n = write_jsonl(out_path, row_iter())
        print(f"Wrote {n} documents to {out_path}")


if __name__ == "__main__":
    main()


