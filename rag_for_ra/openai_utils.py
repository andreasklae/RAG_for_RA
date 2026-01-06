from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class OpenAiConfig:
    vector_store_id: str
    out_dir: Path
    manifest_path: Path


def require_api_key() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set. Run the chat CLI or export OPENAI_API_KEY in your shell.")


def uploads_enabled() -> None:
    if os.environ.get("OPENAI_UPLOAD_ENABLED") != "1":
        raise SystemExit(
            "Uploads are disabled by default.\n"
            "To enable uploads, set OPENAI_UPLOAD_ENABLED=1 in your shell."
        )


def load_vs_id(vs_id: str | None) -> str:
    if vs_id and vs_id.strip():
        return vs_id.strip()
    if os.environ.get("OPENAI_VECTOR_STORE_ID"):
        return os.environ["OPENAI_VECTOR_STORE_ID"].strip()
    p = REPO_ROOT / "artifacts" / "openai_pilot" / "vector_store.json"
    if not p.exists():
        raise SystemExit(
            "Missing vector store id. Pass --vector-store-id or create one with create_vector_store.py"
        )
    data = json.loads(p.read_text(encoding="utf-8"))
    return str(data["vector_store_id"])


def load_manifest(path: Path, vs_id: str) -> dict[str, Any]:
    if path.exists():
        try:
            m = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(m, dict):
                return m
        except Exception:
            pass
    return {"vector_store_id": vs_id, "uploads": []}


def manifest_has_txt(manifest: dict[str, Any], txt_path: Path) -> bool:
    uploads = manifest.get("uploads")
    if not isinstance(uploads, list):
        return False
    for u in uploads:
        if isinstance(u, dict) and u.get("txt") == str(txt_path):
            return True
    return False


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


