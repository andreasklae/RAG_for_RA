from __future__ import annotations

import argparse
import json
from pathlib import Path

from .openai_utils import REPO_ROOT


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Create an OpenAI Vector Store (user-owned).")
    p.add_argument("--name", default="rag-for-ra-pilot", help="Vector store name.")
    p.add_argument(
        "--out",
        default=None,
        help="Where to write the created vector_store_id (json). Default: artifacts/openai_pilot/vector_store.json",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    out_path = Path(args.out) if args.out else REPO_ROOT / "artifacts" / "openai_pilot" / "vector_store.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    from openai import OpenAI  # type: ignore

    client = OpenAI()
    vs = client.vector_stores.create(name=args.name)

    payload = {"vector_store_id": vs.id, "name": args.name}
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Created vector store: {vs.id}")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()


