from __future__ import annotations

import argparse
import json

from .openai_utils import load_vs_id


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Show OpenAI Vector Store status (including size/usage if available).")
    p.add_argument(
        "--vector-store-id",
        default=None,
        help="Vector store id (vs_...). If omitted, reads OPENAI_VECTOR_STORE_ID or artifacts/openai_pilot/vector_store.json",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    vs_id = load_vs_id(args.vector_store_id)

    from openai import OpenAI  # type: ignore

    client = OpenAI()
    vs = client.vector_stores.retrieve(vs_id)
    print(json.dumps(vs.model_dump(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()


