from __future__ import annotations

import argparse
import json
from pathlib import Path

from .openai_utils import load_vs_id


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="List files attached to an OpenAI Vector Store.")
    p.add_argument(
        "--vector-store-id",
        default=None,
        help="Vector store id (vs_...). If omitted, reads OPENAI_VECTOR_STORE_ID or artifacts/openai_pilot/vector_store.json",
    )
    p.add_argument("--out", default=None, help="Optional path to write JSON output.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    vs_id = load_vs_id(args.vector_store_id)

    from openai import OpenAI  # type: ignore

    client = OpenAI()
    files = client.vector_stores.files.list(vector_store_id=vs_id)

    payload = files.model_dump()
    if args.out:
        Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote: {args.out}")
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()


