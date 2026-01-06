from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rough cost estimate for an OpenAI Vector Store upload.")
    p.add_argument("--file", required=True, help="Prepared upload text file.")
    p.add_argument(
        "--embed-price-per-1k-tokens",
        type=float,
        default=0.0004,
        help="Embedding price per 1k tokens (example: text-embedding-3-small).",
    )
    p.add_argument(
        "--file-search-price-per-1k-calls",
        type=float,
        default=2.50,
        help="File Search tool price per 1k calls (per current pricing page).",
    )
    p.add_argument(
        "--vector-store-price-per-gb-day",
        type=float,
        default=0.10,
        help="Vector store storage price per GB per day beyond free tier (per current pricing page).",
    )
    p.add_argument("--queries", type=int, default=1000, help="How many file_search calls you expect.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.file)
    b = path.read_bytes()
    n_bytes = len(b)
    n_mb = n_bytes / (1024 * 1024)

    # Token estimate heuristic (no tokenizer dependency):
    # common rough heuristic is ~4 chars/token.
    text = b.decode("utf-8", errors="replace")
    approx_tokens = max(1, int(len(text) / 4))

    embed_cost = (approx_tokens / 1000.0) * float(args.embed_price_per_1k_tokens)
    query_cost = (float(args.queries) / 1000.0) * float(args.file_search_price_per_1k_calls)

    n_gb = n_bytes / (1024 * 1024 * 1024)
    storage_cost_per_day = max(0.0, (n_gb - 1.0)) * float(args.vector_store_price_per_gb_day)

    print(f"File: {path}")
    print(f"Size: {n_mb:.2f} MB ({n_bytes} bytes)")
    print(f"Approx tokens: {approx_tokens:,}")
    print()
    print(f"Estimated one-time embedding cost: ${embed_cost:.4f}")
    print(f"Estimated query cost for {args.queries} file_search calls: ${query_cost:.2f}")
    print(f"Estimated storage cost per day beyond 1GB free tier: ${storage_cost_per_day:.4f}/day")
    print()
    print("Notes:")
    print("- Token estimate is rough; actual tokenization may differ.")
    print("- Vector store size after chunking/embedding may differ from raw file size.")


if __name__ == "__main__":
    main()


