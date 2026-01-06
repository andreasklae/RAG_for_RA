from __future__ import annotations

import argparse
from pathlib import Path

from .io import read_jsonl
from .openai_utils import REPO_ROOT


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Convert normalized JSONL docs into a single chunk-friendly text file for OpenAI Vector Store upload."
    )
    p.add_argument("--docs", required=True, help="Path to normalized documents JSONL.")
    p.add_argument(
        "--out",
        default=None,
        help="Output text file. Default: artifacts/openai_pilot/<stem>.txt",
    )
    p.add_argument("--max-docs", type=int, default=0, help="0 = all docs in the input file.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    docs_path = Path(args.docs)
    out_path = Path(args.out) if args.out else REPO_ROOT / "artifacts" / "openai_pilot" / f"{docs_path.stem}.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    docs = read_jsonl(docs_path)
    if args.max_docs and args.max_docs > 0:
        docs = docs[: args.max_docs]

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

    out_path.write_text("\n\n---\n\n".join(blocks), encoding="utf-8")
    print(f"Wrote {len(docs)} docs to {out_path}")


if __name__ == "__main__":
    main()


