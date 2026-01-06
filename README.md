# RAG_for_RA — Reproducible RAG pipeline + chat client (OpenAI Vector Store)

This directory is intended to be a **public repo**: it contains a small Python CLI and ingestion tooling that lets **any user**:

- fetch public Riksantikvaren data (OGC API + optional ArcGIS MapServer)
- normalize records into text “documents”
- **populate their own OpenAI Vector Store** (upload documents so OpenAI builds a managed index)
- run an interactive **chat CLI** that answers using retrieval + explicit sources

## Security model (important)

- **No secrets in this repo**: no API keys are stored or committed.
- Tools **prompt the user for an OpenAI API key** (input hidden) if `OPENAI_API_KEY` is not already set.
- Uploading is supported (to populate **your own** vector store), but **deletion is intentionally not implemented** in this repo.

**Limitation**: The OpenAI platform controls what an API key can do. This repo can avoid providing destructive commands, but it cannot enforce permissions beyond what OpenAI supports for that key/project.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## What does “populate the vector store” mean?

OpenAI Vector Stores are a **managed retrieval index**. “Populating” means:

1) downloading public records (RA APIs)
2) converting each record into a normalized document
3) generating an uploadable text file (document blocks with `TITLE/TEXT/SOURCE_URL`)
4) uploading that file to your **own** vector store so OpenAI can chunk + embed + index it

The repo stores reproducible artifacts locally (gitignored):
- `RAG_for_RA/artifacts/` (downloaded/normalized JSONL caches, prepared upload text files, logs, manifests)

## Environment variables

Use `env.example` as a template.

- `OPENAI_API_KEY`: required for any OpenAI calls (prompted for if missing)
- `OPENAI_VECTOR_STORE_ID`: recommended (so you don’t have to paste `vs_...` every run)
- `OPENAI_UPLOAD_ENABLED=1`: required to enable uploads (safety switch; prevents accidental uploads)

## Workflow A (recommended): automated sync (API → cache → prepare → upload)

1) Create a vector store:

```bash
python -m rag_for_ra.create_vector_store --name "rag-for-ra-pilot"
```

2) Sync datasets (OGC + ArcGIS supported), optionally constrain with bbox:

```bash
export OPENAI_UPLOAD_ENABLED=1
python -m rag_for_ra.sync_api_to_openai \
  --ogc brukerminner:brukerminner \
  --ogc kulturmiljoer:kulturmiljoer \
  --arcgis-layer 1 \
  --bbox "10.6,59.8,10.9,60.0" \
  --max-items 2000 \
  --jobs 2
```

Notes:
- Use `--no-upload` to only build local caches + prepared `.txt` files.
- Use `--max-items 0` for full ingestion (can be very large).

## Workflow B: manual, step-by-step population

This is the “same steps, but explicit” version.

1) Ingest OGC to JSONL:

```bash
python -m rag_for_ra.ingest_ogc --dataset kulturminner --collection kulturminner --max-items 2000 --bbox "10.6,59.8,10.9,60.0"
```

2) Ingest ArcGIS to JSONL (optional):

```bash
python -m rag_for_ra.ingest_arcgis --layer-id 1 --max-items 2000 --bbox "10.6,59.8,10.9,60.0"
```

3) Prepare a chunk-friendly upload file from a JSONL:

```bash
python -m rag_for_ra.prepare_pilot_file --docs artifacts/kulturminner__kulturminner.jsonl
```

4) Create a vector store:

```bash
python -m rag_for_ra.create_vector_store
```

5) Upload the prepared file (uploads require the safety switch):

```bash
export OPENAI_UPLOAD_ENABLED=1
python -m rag_for_ra.upload_to_vector_store --vector-store-id vs_... --file artifacts/openai_pilot/kulturminner__kulturminner.txt
```

Alternative upload method: bulk upload multiple JSONLs (each becomes its own prepared `.txt`):

```bash
export OPENAI_UPLOAD_ENABLED=1
python -m rag_for_ra.bulk_upload_jsonl artifacts/kulturminner__kulturminner.jsonl artifacts/arcgis__1__FredaBygninger.jsonl
```

## Inspect your vector store

List files:

```bash
python -m rag_for_ra.list_vector_store_files
```

Status:

```bash
python -m rag_for_ra.vector_store_status
```

## Chat (interface to your populated Vector Store)

```bash
python -m rag_for_ra.chat --k 5
```

## Configuration

You need a **Vector Store ID** (`vs_...`). Resolution order:

1) `--vector-store-id vs_...`
2) `OPENAI_VECTOR_STORE_ID` environment variable
3) local state file: `RAG_for_RA/.rag_state.json` (auto-created, gitignored)
4) prompt the user

Create an env file from `env.example` and export variables in your shell as needed.

## Usage examples

Chat (retrieval + answer):

```bash
python -m rag_for_ra.chat --k 5
```

Retrieval-only (no model call):

```bash
python -m rag_for_ra.chat --mode search
```

Show retrieved context blocks:

```bash
python -m rag_for_ra.chat --show-context
```

## Cost notes

Vector store population can cost money (embeddings/indexing + storage). For a rough estimate of an upload file:

```bash
python -m rag_for_ra.estimate_cost --file artifacts/openai_pilot/kulturminner__kulturminner.txt
```


