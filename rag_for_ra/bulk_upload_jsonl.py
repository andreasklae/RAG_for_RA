from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from .io import read_jsonl
from .openai_utils import load_vs_id, uploads_enabled


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Bulk upload one or more normalized JSONL corpora to an OpenAI Vector Store (prepare text + upload + manifest)."
    )
    p.add_argument(
        "--vector-store-id",
        default=None,
        help="Vector store id (vs_...). If omitted, reads OPENAI_VECTOR_STORE_ID or artifacts/openai_pilot/vector_store.json",
    )
    p.add_argument("jsonl", nargs="+", help="One or more normalized JSONL files (produced by ingestion scripts).")
    p.add_argument(
        "--out-dir",
        default=None,
        help="Where to write prepared txt files. Default: artifacts/openai_pilot/",
    )
    p.add_argument(
        "--manifest",
        default=None,
        help="Manifest JSON path. Default: artifacts/openai_pilot/upload_manifest.json",
    )
    p.add_argument("--max-docs", type=int, default=0, help="0 = all docs, else limit per JSONL file.")
    return p.parse_args()


def prepare_text_from_jsonl(jsonl_path: Path, *, out_path: Path, max_docs: int) -> int:
    docs = read_jsonl(jsonl_path)
    if max_docs and max_docs > 0:
        docs = docs[:max_docs]

    blocks: list[str] = []
    for d in docs:
        src = d.get("source") or {}
        blocks.append(
            "\n".join(
                [
                    f"DOC_ID: {d.get('doc_id','')}",
                    f"TITLE: {d.get('title','')}",
                    f"TEXT: {d.get('text','')}",
                    f"SOURCE_URL: {src.get('web_url') or ''}",
                    f"LICENSE: {src.get('license_name') or ''} {src.get('license_url') or ''}".strip(),
                ]
            ).strip()
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n\n---\n\n".join(blocks), encoding="utf-8")
    return len(docs)


def main() -> None:
    args = parse_args()
    vs_id = load_vs_id(args.vector_store_id)

    uploads_enabled()
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set.")

    out_dir = Path(args.out_dir) if args.out_dir else Path(__file__).resolve().parents[1] / "artifacts" / "openai_pilot"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(args.manifest) if args.manifest else out_dir / "upload_manifest.json"
    manifest: dict[str, object] = {"vector_store_id": vs_id, "uploads": []}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    from openai import OpenAI  # type: ignore

    client = OpenAI()

    uploads = manifest.get("uploads")
    if not isinstance(uploads, list):
        uploads = []

    for jsonl_str in args.jsonl:
        jsonl_path = Path(jsonl_str)
        if not jsonl_path.exists():
            raise SystemExit(f"JSONL file not found: {jsonl_path}")

        txt_name = f"{jsonl_path.stem}.txt"
        txt_path = out_dir / txt_name

        n_docs = prepare_text_from_jsonl(jsonl_path, out_path=txt_path, max_docs=args.max_docs)
        size_bytes = txt_path.stat().st_size
        print(f"Prepared: {txt_path} ({n_docs} docs, {size_bytes} bytes)")

        started = time.time()
        with txt_path.open("rb") as f:
            batch = client.vector_stores.file_batches.upload_and_poll(
                vector_store_id=vs_id,
                files=[f],
            )
        dur_s = time.time() - started
        print(f"Uploaded: {txt_name} (batch status={batch.status}, {dur_s:.1f}s)")

        uploads.append(
            {
                "jsonl": str(jsonl_path),
                "txt": str(txt_path),
                "docs": n_docs,
                "bytes": size_bytes,
                "batch_status": batch.status,
                "created_at": int(time.time()),
            }
        )

        manifest["uploads"] = uploads
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Updated manifest: {manifest_path}")


if __name__ == "__main__":
    main()


