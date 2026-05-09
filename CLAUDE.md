# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dev server (port 8084, debug mode, auto-reload)
python3 app.py
```

No tests or linters are configured.

## Architecture

A single-file Flask app that extracts embedded JPEG previews from RAW photo files using `rawpy` (libraw bindings).

**Conversion pipeline:** RAW upload → `rawpy.imread()` → `raw.extract_thumb()` → JPEG (or BMP→JPEG via Pillow if the thumbnail is a bitmap).

**Routes:**
- `GET /` — upload page
- `POST /extract` — single file: converts and returns the JPG blob directly
- `POST /batch/extract` — multi-file: converts all, returns JSON manifest with per-file status and a `batch_id`
- `GET /batch/<batch_id>/download/<file_id>` — download one JPG from a batch
- `GET /batch/<batch_id>/zip` — download all JPGs from a batch as a ZIP
- `GET /health` — liveness check

**File storage:** Uploaded RAWs and converted JPGs live under `$TMPDIR/raw2jpg_uploads/`. Single-file uploads delete the RAW immediately in `finally`. Batch uploads persist JPGs under `{batch_id}/jpg/` for later download; stale batch directories are purged on startup and lazily (30-minute TTL) when a new batch is submitted.

**Key libraries:** `flask`, `rawpy` (wraps libraw), `Pillow`. ZIP creation uses stdlib `zipfile`.
