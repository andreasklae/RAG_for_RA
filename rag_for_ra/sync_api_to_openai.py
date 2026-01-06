from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import orjson
from tqdm import tqdm

from .arcgis import ArcGisMapServer
from .documents import arcgis_feature_to_document, feature_to_document
from .io import ensure_parent
from .ogc import OgcSource
from .openai_utils import (
    OpenAiConfig,
    REPO_ROOT,
    load_manifest,
    load_vs_id,
    manifest_has_txt,
    uploads_enabled,
    write_manifest,
)


DEFAULT_MAPSERVER = "https://kart.ra.no/arcgis/rest/services/Distribusjon/Kulturminner20180301/MapServer"


@dataclass(frozen=True)
class Produced:
    jsonl_path: Path
    txt_path: Path
    docs: int


def write_jsonl_stream(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    ensure_parent(path)
    n = 0
    with path.open("ab") as f:
        for row in rows:
            f.write(orjson.dumps(row))
            f.write(b"\n")
            n += 1
    return n


def prepare_text_from_jsonl(jsonl_path: Path, *, out_path: Path) -> int:
    # Stream conversion to avoid loading large JSONL into memory.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with jsonl_path.open("rb") as fin, out_path.open("w", encoding="utf-8") as fout:
        first = True
        for line in fin:
            line = line.strip()
            if not line:
                continue
            d = orjson.loads(line)
            src = d.get("source") or {}
            block = "\n".join(
                [
                    f"DOC_ID: {d.get('doc_id','')}",
                    f"TITLE: {d.get('title','')}",
                    f"TEXT: {d.get('text','')}",
                    f"SOURCE_URL: {src.get('web_url') or ''}",
                    f"LICENSE: {src.get('license_name') or ''} {src.get('license_url') or ''}".strip(),
                ]
            ).strip()
            if not first:
                fout.write("\n\n---\n\n")
            fout.write(block)
            first = False
            n += 1
    return n


def upload_txt_to_vector_store(cfg: OpenAiConfig, *, txt_path: Path, jsonl_path: Path, docs: int, manifest: dict[str, Any]) -> None:
    from openai import OpenAI  # type: ignore

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set in this shell.")

    if manifest_has_txt(manifest, txt_path):
        print(f"Skip (already in manifest): {txt_path}")
        return

    client = OpenAI()
    started = time.time()
    with txt_path.open("rb") as f:
        batch = client.vector_stores.file_batches.upload_and_poll(
            vector_store_id=cfg.vector_store_id,
            files=[f],
        )
    dur_s = time.time() - started

    uploads = manifest.get("uploads")
    if not isinstance(uploads, list):
        uploads = []
    uploads.append(
        {
            "jsonl": str(jsonl_path),
            "txt": str(txt_path),
            "docs": docs,
            "bytes": txt_path.stat().st_size,
            "batch_status": batch.status,
            "uploaded_at": int(time.time()),
            "duration_s": round(dur_s, 2),
        }
    )
    manifest["uploads"] = uploads
    write_manifest(cfg.manifest_path, manifest)
    print(f"Uploaded: {txt_path.name} (status={batch.status}, {dur_s:.1f}s)")


def ogc_ingest_jsonl(*, dataset: str, collection: str, bbox: str | None, max_items: int, limit: int, out_jsonl: Path) -> int:
    api_base = f"https://api.ra.no/{dataset}"
    src = OgcSource(api_base=api_base)

    license_name = None
    license_url = None
    try:
        openapi = src.http.get_json(f"{api_base}/api", params={"f": "json"})
        lic = (openapi.get("info") or {}).get("license") or {}
        license_name = lic.get("name")
        license_url = lic.get("url")
    except Exception:
        pass

    max_items_opt = None if max_items == 0 else max_items

    # Resume support: if JSONL exists, resume from its current line-count.
    start_offset = 0
    if out_jsonl.exists():
        with out_jsonl.open("rb") as f:
            start_offset = sum(1 for _ in f)

    url = f"{api_base}/collections/{collection}/items"
    offset = start_offset
    appended = 0
    yielded_total = 0
    skipped_offsets: list[int] = []

    ensure_parent(out_jsonl)
    with out_jsonl.open("ab") as f:
        pbar = tqdm(desc=f"ogc {dataset}/{collection}", unit="feat")
        try:
            while True:
                if max_items_opt is not None and yielded_total >= max_items_opt:
                    break

                cur_limit = int(limit)
                if max_items_opt is not None:
                    cur_limit = min(cur_limit, max_items_opt - yielded_total)
                cur_limit = max(1, cur_limit)

                while True:
                    params: dict[str, Any] = {"f": "json", "limit": cur_limit, "offset": offset}
                    if bbox:
                        params["bbox"] = bbox
                    try:
                        payload = src.http.get_json(url, params=params)
                        feats = payload.get("features") or []
                        break
                    except Exception as exc:
                        if cur_limit > 1:
                            cur_limit = max(1, cur_limit // 2)
                            continue
                        skipped_offsets.append(offset)
                        offset += 1
                        if len(skipped_offsets) >= 50:
                            raise RuntimeError(
                                f"Too many skipped offsets ({len(skipped_offsets)}). Last error: {exc}"
                            ) from exc
                        feats = []
                        break

                if not feats:
                    if cur_limit == int(limit):
                        break
                    continue

                for feat in feats:
                    doc = feature_to_document(
                        dataset=dataset,
                        collection=collection,
                        feature=feat,
                        license_name=license_name,
                        license_url=license_url,
                    )
                    f.write(orjson.dumps(doc.to_dict()))
                    f.write(b"\n")
                    appended += 1
                    yielded_total += 1
                    pbar.update(1)

                offset += len(feats)
        finally:
            pbar.close()

    if skipped_offsets:
        sidecar = out_jsonl.with_suffix(out_jsonl.suffix + ".skipped.json")
        sidecar.write_text(
            json.dumps(
                {
                    "dataset": dataset,
                    "collection": collection,
                    "skipped_offsets": skipped_offsets,
                    "note": "Offsets that consistently returned upstream errors (e.g., HTTP 500) during sync.",
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    return appended


def arcgis_ingest_jsonl(*, mapserver: str, layer_id: int, bbox: str | None, max_items: int, out_jsonl: Path) -> int:
    ms = ArcGisMapServer(mapserver_base=mapserver)
    layer_info = ms.layer_info(layer_id)
    layer_name = layer_info.get("name") or f"layer_{layer_id}"

    license_name = "NLOD"
    license_url = "https://data.norge.no/nlod"
    max_items_opt = None if max_items == 0 else max_items

    def row_iter():
        for feat in tqdm(
            ms.iter_layer_features(layer_id, bbox_wgs84=bbox, max_items=max_items_opt),
            desc=f"arcgis {layer_id} ({layer_name})",
        ):
            doc = arcgis_feature_to_document(
                dataset="arcgis",
                layer_name=layer_name,
                feature=feat,
                license_name=license_name,
                license_url=license_url,
            )
            yield doc.to_dict()

    return write_jsonl_stream(out_jsonl, row_iter())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch from APIs and upload to an OpenAI Vector Store (with local JSONL cache).")
    p.add_argument("--vector-store-id", default=None, help="Vector store id (vs_...).")
    p.add_argument("--out-dir", default=None, help="Base output dir. Default: artifacts/sync/")
    p.add_argument("--manifest", default=None, help="Manifest path. Default: artifacts/openai_pilot/upload_manifest.json")
    p.add_argument("--bbox", default=None, help="Optional bbox (minLon,minLat,maxLon,maxLat) applied where supported.")
    p.add_argument("--max-items", type=int, default=0, help="0 = unlimited. Otherwise max items per collection/layer.")
    p.add_argument("--limit", type=int, default=50, help="OGC page size (keep small).")
    p.add_argument("--jobs", type=int, default=1, help="Parallel jobs for ingestion/prep across targets. Recommended: 2.")
    p.add_argument(
        "--ogc",
        action="append",
        default=[],
        help="OGC spec: <dataset>:<collection>. Example: kulturmiljoer:kulturmiljoer or brukerminner:brukerminner",
    )
    p.add_argument(
        "--ogc-all",
        action="append",
        default=[],
        help="OGC dataset: ingest all collections for dataset. Example: --ogc-all kulturminner",
    )
    p.add_argument("--arcgis-mapserver", default=DEFAULT_MAPSERVER, help="ArcGIS MapServer base URL.")
    p.add_argument(
        "--arcgis-layer",
        action="append",
        default=[],
        help="ArcGIS layer id to ingest+upload (repeatable). Example: --arcgis-layer 1",
    )
    p.add_argument("--no-upload", action="store_true", help="Only ingest + prepare txt files; do not upload.")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    vs_id = load_vs_id(args.vector_store_id)
    out_dir = Path(args.out_dir) if args.out_dir else REPO_ROOT / "artifacts" / "sync"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = Path(args.manifest) if args.manifest else REPO_ROOT / "artifacts" / "openai_pilot" / "upload_manifest.json"
    cfg = OpenAiConfig(vector_store_id=vs_id, out_dir=out_dir, manifest_path=manifest_path)
    manifest = load_manifest(manifest_path, vs_id)

    # Resolve OGC targets
    ogc_targets: list[tuple[str, str]] = []
    for spec in args.ogc:
        if ":" not in spec:
            raise SystemExit(f"Invalid --ogc spec: {spec} (expected dataset:collection)")
        ds, col = spec.split(":", 1)
        ogc_targets.append((ds, col))

    for ds in args.ogc_all:
        src = OgcSource(api_base=f"https://api.ra.no/{ds}")
        for c in src.collections():
            cid = c.get("id")
            if cid:
                ogc_targets.append((ds, str(cid)))

    arc_layers = [int(x) for x in args.arcgis_layer]

    produced: list[Produced] = []

    def ingest_and_prepare_ogc(ds: str, col: str) -> Produced:
        jsonl_path = out_dir / f"ogc__{ds}__{col}.jsonl"
        txt_path = REPO_ROOT / "artifacts" / "openai_pilot" / f"ogc__{ds}__{col}.txt"
        print(f"\n[OGC] {ds}/{col}")
        n_new = ogc_ingest_jsonl(
            dataset=ds,
            collection=col,
            bbox=args.bbox,
            max_items=args.max_items,
            limit=args.limit,
            out_jsonl=jsonl_path,
        )
        docs = prepare_text_from_jsonl(jsonl_path, out_path=txt_path)
        print(f"Prepared: {txt_path} (docs={docs}, new_rows_appended={n_new})")
        return Produced(jsonl_path=jsonl_path, txt_path=txt_path, docs=docs)

    def ingest_and_prepare_arcgis(layer_id: int) -> Produced:
        jsonl_path = out_dir / f"arcgis__{layer_id}.jsonl"
        txt_path = REPO_ROOT / "artifacts" / "openai_pilot" / f"arcgis__{layer_id}.txt"
        print(f"\n[ArcGIS] layer {layer_id}")
        n_new = arcgis_ingest_jsonl(
            mapserver=args.arcgis_mapserver,
            layer_id=layer_id,
            bbox=args.bbox,
            max_items=args.max_items,
            out_jsonl=jsonl_path,
        )
        docs = prepare_text_from_jsonl(jsonl_path, out_path=txt_path)
        print(f"Prepared: {txt_path} (docs={docs}, new_rows_appended={n_new})")
        return Produced(jsonl_path=jsonl_path, txt_path=txt_path, docs=docs)

    jobs = max(1, int(args.jobs))
    if jobs == 1:
        for ds, col in ogc_targets:
            produced.append(ingest_and_prepare_ogc(ds, col))
        for layer_id in arc_layers:
            produced.append(ingest_and_prepare_arcgis(layer_id))
    else:
        with ThreadPoolExecutor(max_workers=jobs) as ex:
            futs = []
            for ds, col in ogc_targets:
                futs.append(ex.submit(ingest_and_prepare_ogc, ds, col))
            for layer_id in arc_layers:
                futs.append(ex.submit(ingest_and_prepare_arcgis, layer_id))
            for fut in as_completed(futs):
                produced.append(fut.result())

    if args.no_upload:
        print("\nDone (no upload).")
        return

    uploads_enabled()

    for p in produced:
        upload_txt_to_vector_store(cfg, txt_path=p.txt_path, jsonl_path=p.jsonl_path, docs=p.docs, manifest=manifest)

    print("\nDone.")


if __name__ == "__main__":
    main()


