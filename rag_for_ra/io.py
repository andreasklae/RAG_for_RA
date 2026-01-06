from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import orjson


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    ensure_parent(path)
    n = 0
    with path.open("wb") as f:
        for row in rows:
            f.write(orjson.dumps(row))
            f.write(b"\n")
            n += 1
    return n


def write_jsonl_stream_append(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    ensure_parent(path)
    n = 0
    with path.open("ab") as f:
        for row in rows:
            f.write(orjson.dumps(row))
            f.write(b"\n")
            n += 1
    return n


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("rb") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(orjson.loads(line))
    return rows


