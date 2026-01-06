from __future__ import annotations

import argparse
import datetime as dt
import os
from getpass import getpass
from pathlib import Path

from .state import load_json, save_json


DEFAULT_MODEL = "gpt-4.1-mini"
DEFAULT_K = 5

REPO_ROOT = Path(__file__).resolve().parents[1]
STATE_FILE = REPO_ROOT / ".rag_state.json"


def _ensure_api_key() -> None:
    """
    Safe enough for a local CLI:
    - Prompt via hidden input (not echoed)
    - Store only in process env for the lifetime of this process
    - Never write it to logs
    """
    if os.environ.get("OPENAI_API_KEY"):
        return
    key = getpass("OpenAI API key (input hidden): ").strip()
    if not key:
        raise SystemExit("No API key provided. Set OPENAI_API_KEY or paste it when prompted.")
    os.environ["OPENAI_API_KEY"] = key


def _prompt_vector_store_id() -> str:
    vs = input("OpenAI Vector Store ID (vs_...): ").strip()
    if not vs:
        raise SystemExit("No Vector Store ID provided. Set OPENAI_VECTOR_STORE_ID or pass --vector-store-id.")
    return vs


def _get_vector_store_id(arg_vs_id: str | None) -> str:
    """
    Resolution order:
    1) --vector-store-id
    2) OPENAI_VECTOR_STORE_ID env var
    3) local .rag_state.json (created by this script; gitignored)
    4) prompt the user (VS id is not a secret, just a pointer to the existing store)
    """
    if arg_vs_id and arg_vs_id.strip():
        return arg_vs_id.strip()
    if os.environ.get("OPENAI_VECTOR_STORE_ID"):
        return os.environ["OPENAI_VECTOR_STORE_ID"].strip()

    state = load_json(STATE_FILE)
    vs_id = state.get("vector_store_id")
    if isinstance(vs_id, str) and vs_id.strip():
        return vs_id.strip()

    new_id = _prompt_vector_store_id()
    os.environ["OPENAI_VECTOR_STORE_ID"] = new_id
    save_json(STATE_FILE, {"vector_store_id": new_id})
    return new_id


def _extract_sources_from_hit_text(text: str) -> list[str]:
    sources: list[str] = []
    for line in text.splitlines():
        if line.startswith("SOURCE_URL:"):
            url = line.replace("SOURCE_URL:", "").strip()
            if url:
                sources.append(url)
    # Dedupe while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for s in sources:
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _build_prompt(question: str, contexts: list[str], sources: list[str]) -> str:
    context_blob = "\n\n---\n\n".join(contexts)
    src_blob = "\n".join(sources)
    return (
        "You are a careful cultural heritage guide.\n"
        "Answer in English.\n"
        "Use ONLY the CONTEXT below. If the context is insufficient, say so and ask a follow-up question.\n"
        "Always include a 'Sources:' section listing the SOURCE_URLs you used.\n\n"
        f"SPØRSMÅL:\n{question}\n\n"
        f"CONTEXT:\n{context_blob}\n\n"
        f"AVAILABLE_SOURCES:\n{src_blob}\n"
    )


def _default_log_path() -> Path:
    # Include microseconds to avoid collisions when starting multiple runs quickly.
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    return REPO_ROOT / "artifacts" / "chat_logs" / f"chat-{ts}.md"


def _append_log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(text)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only chat against an OpenAI Vector Store (retrieval + grounded answers).")
    p.add_argument("--vector-store-id", default=None, help="OpenAI Vector Store id (vs_...).")
    p.add_argument("--model", default=DEFAULT_MODEL, help="OpenAI model for answering (only used in answer mode).")
    p.add_argument("--k", type=int, default=DEFAULT_K, help="How many retrieved hits to use.")
    p.add_argument(
        "--mode",
        choices=["answer", "search"],
        default="answer",
        help="answer = retrieval + grounded answer. search = retrieval-only (no LLM).",
    )
    p.add_argument(
        "--show-context",
        action="store_true",
        help="Print the retrieved context blocks (useful for debugging/evaluation).",
    )
    p.add_argument(
        "--log-file",
        default=None,
        help="Path to append a full chat transcript. Default: RAG_for_RA/artifacts/chat_logs/<timestamp>.md",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    _ensure_api_key()
    vs_id = _get_vector_store_id(args.vector_store_id)

    # Lazy import: only required at runtime.
    try:
        from openai import OpenAI  # type: ignore
    except Exception as exc:
        raise SystemExit("Missing dependency 'openai'. Install with: pip install -r requirements.txt") from exc

    client = OpenAI()

    log_path = Path(args.log_file) if args.log_file else _default_log_path()
    header = (
        f"# RAG chat transcript\n\n"
        f"- Started: {dt.datetime.now().isoformat(timespec='seconds')}\n"
        f"- Vector store: `{vs_id}`\n"
        f"- Mode: `{args.mode}`\n"
        f"- Model: `{args.model}`\n"
        f"- k: {args.k}\n\n"
        f"---\n\n"
    )
    _append_log(log_path, header)

    print("Interactive chat. Type 'quit' (or 'exit') to stop.")
    print(f"Vector store: {vs_id}")
    print(f"Logging to: {log_path}\n")

    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            _append_log(log_path, f"\n---\n\nEnded: {dt.datetime.now().isoformat(timespec='seconds')}\n")
            return

        if not q:
            continue
        if q.lower() in {"quit", "exit", ":q"}:
            print("Bye.")
            _append_log(log_path, f"\n---\n\nEnded: {dt.datetime.now().isoformat(timespec='seconds')}\n")
            return

        _append_log(log_path, f"## User ({dt.datetime.now().isoformat(timespec='seconds')})\n\n{q}\n\n")

        # Retrieval (read-only)
        results = client.vector_stores.search(vector_store_id=vs_id, query=q)
        hits = (results.data or [])[: max(1, int(args.k))]

        contexts: list[str] = []
        sources: list[str] = []
        for h in hits:
            for part in (h.content or []):
                txt = part.get("text") if isinstance(part, dict) else getattr(part, "text", None)
                if not txt:
                    continue
                t = str(txt).strip()
                if not t:
                    continue
                contexts.append(t)
                sources.extend(_extract_sources_from_hit_text(t))

        # Dedupe sources while preserving order
        seen: set[str] = set()
        sources_deduped: list[str] = []
        for s in sources:
            if s in seen:
                continue
            seen.add(s)
            sources_deduped.append(s)

        if args.show_context:
            print("\n[retrieved]")
            for i, c in enumerate(contexts, start=1):
                print(f"\n--- hit {i} ---\n{c}")
            print("\n[/retrieved]\n")
            _append_log(log_path, "### Retrieved context\n\n" + "\n\n---\n\n".join(contexts[: args.k]) + "\n\n")

        if args.mode == "search":
            if not contexts:
                out = "Ingen treff (tom kontekst)."
            else:
                out = "\n\n---\n\n".join(contexts[: args.k])
            print("\n" + out + "\n")
            _append_log(log_path, f"## Assistant ({dt.datetime.now().isoformat(timespec='seconds')})\n\n{out}\n\n")
            continue

        # Answer mode (LLM)
        prompt = _build_prompt(q, contexts[: args.k], sources_deduped)
        resp = client.responses.create(model=args.model, input=prompt)
        answer = (getattr(resp, "output_text", "") or "").strip()

        # Ensure sources are present even if the model forgets.
        if "Kilder:" not in answer and sources_deduped:
            answer = answer.rstrip() + "\n\nKilder:\n" + "\n".join(sources_deduped)

        print("\n" + (answer or "(tomt svar)") + "\n")
        _append_log(log_path, f"## Assistant ({dt.datetime.now().isoformat(timespec='seconds')})\n\n{answer}\n\n")


if __name__ == "__main__":
    main()


