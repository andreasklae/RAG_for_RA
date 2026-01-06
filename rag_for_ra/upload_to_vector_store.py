from __future__ import annotations

import argparse
import json
from pathlib import Path

from .openai_utils import REPO_ROOT, uploads_enabled


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Upload a prepared text file into an OpenAI Vector Store (file_search).")
    p.add_argument("--vector-store-id", required=True, help="Vector store id.")
    p.add_argument("--file", required=True, help="Path to prepared text file (from prepare_pilot_file.py).")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    file_path = Path(args.file)
    if not file_path.exists():
        raise SystemExit(f"File does not exist: {file_path}")

    uploads_enabled()

    from openai import OpenAI  # type: ignore

    client = OpenAI()
    with file_path.open("rb") as f:
        batch = client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=args.vector_store_id,
            files=[f],
        )

    out_path = REPO_ROOT / "artifacts" / "openai_pilot" / "upload_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(batch.model_dump(), indent=2), encoding="utf-8")

    print(f"Upload batch status: {batch.status}")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()


