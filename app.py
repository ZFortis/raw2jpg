import json
import os
import io
import shutil
import tempfile
import time
import uuid
import zipfile
from pathlib import Path

from flask import Flask, render_template, request, send_file, jsonify
import rawpy
from PIL import Image

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB

UPLOAD_DIR = Path(tempfile.gettempdir()) / "raw2jpg_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Clear stale batch directories from previous runs
for entry in UPLOAD_DIR.iterdir():
    if entry.is_dir():
        shutil.rmtree(entry, ignore_errors=True)

STALE_TTL_SECONDS = 30 * 60


def _purge_stale_batches():
    now = time.time()
    for entry in UPLOAD_DIR.iterdir():
        if entry.is_dir():
            mtime = entry.stat().st_mtime
            if now - mtime > STALE_TTL_SECONDS:
                shutil.rmtree(entry, ignore_errors=True)


def _convert_raw(raw_path, jpg_path):
    """Convert a RAW file to JPEG. Returns None on success, error string on failure."""
    with rawpy.imread(str(raw_path)) as raw:
        thumb = raw.extract_thumb()
    if thumb.format == rawpy.ThumbFormat.JPEG:
        with open(str(jpg_path), "wb") as f:
            f.write(thumb.data)
    elif thumb.format == rawpy.ThumbFormat.BITMAP:
        img = Image.fromarray(thumb.data)
        img.save(str(jpg_path), "JPEG", quality=95)
    else:
        return "该RAW文件不包含可提取的预览图"
    return None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extract", methods=["POST"])
def extract():
    if "file" not in request.files:
        return jsonify({"error": "没有上传文件"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "没有选择文件"}), 400

    raw_path = None
    jpg_path = None

    try:
        suffix = Path(file.filename).suffix.lower()
        file_id = uuid.uuid4().hex
        raw_path = UPLOAD_DIR / f"{file_id}{suffix}"
        jpg_path = UPLOAD_DIR / f"{file_id}.jpg"
        file.save(str(raw_path))

        err = _convert_raw(raw_path, jpg_path)
        if err:
            return jsonify({"error": err}), 400

        return send_file(
            str(jpg_path),
            mimetype="image/jpeg",
            as_attachment=True,
            download_name=f"{Path(file.filename).stem}.jpg",
        )

    except rawpy.LibRawError as e:
        return jsonify({"error": f"RAW解析失败: {str(e)}"}), 400
    except Exception as e:
        return jsonify({"error": f"处理失败: {str(e)}"}), 500
    finally:
        if raw_path and raw_path.exists():
            raw_path.unlink(missing_ok=True)


@app.route("/batch/extract", methods=["POST"])
def batch_extract():
    _purge_stale_batches()

    files = request.files.getlist("files")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "没有上传文件"}), 400

    batch_id = uuid.uuid4().hex
    batch_dir = UPLOAD_DIR / batch_id
    raw_dir = batch_dir / "raw"
    jpg_dir = batch_dir / "jpg"
    raw_dir.mkdir(parents=True, exist_ok=True)
    jpg_dir.mkdir(parents=True, exist_ok=True)

    results = []
    file_mapping = {}

    for idx, file in enumerate(files):
        file_id = f"{idx:04d}"
        original_name = file.filename or "unknown"
        result = {"id": file_id, "original_name": original_name}

        if original_name == "":
            result["status"] = "error"
            result["error"] = "文件名为空"
            results.append(result)
            continue

        raw_path = None
        try:
            suffix = Path(file.filename).suffix.lower()
            raw_path = raw_dir / f"{file_id}{suffix}"
            file.save(str(raw_path))

            output_name = f"{Path(file.filename).stem}.jpg"
            jpg_path = jpg_dir / f"{file_id}.jpg"

            err = _convert_raw(raw_path, jpg_path)
            if err:
                result["status"] = "error"
                result["error"] = err
            else:
                result["status"] = "success"
                result["output_name"] = output_name
                result["size_kb"] = round(jpg_path.stat().st_size / 1024, 1)
                file_mapping[file_id] = output_name

        except rawpy.LibRawError as e:
            result["status"] = "error"
            result["error"] = f"RAW解析失败: {str(e)}"
        except Exception as e:
            result["status"] = "error"
            result["error"] = f"处理失败: {str(e)}"
        finally:
            if raw_path and raw_path.exists():
                raw_path.unlink(missing_ok=True)

        results.append(result)

    # Clean up empty raw dir
    try:
        raw_dir.rmdir()
    except OSError:
        pass

    # Write metadata
    success_count = sum(1 for r in results if r["status"] == "success")
    meta = {
        "file_mapping": file_mapping,
        "created_at": time.time(),
    }
    with open(str(batch_dir / "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)

    return jsonify({
        "batch_id": batch_id,
        "files": results,
        "total_count": len(results),
        "success_count": success_count,
        "error_count": len(results) - success_count,
    })


@app.route("/batch/<batch_id>/download/<file_id>")
def batch_download(batch_id, file_id):
    batch_dir = UPLOAD_DIR / batch_id
    if not batch_dir.is_dir():
        return jsonify({"error": "批次不存在或已过期"}), 404

    jpg_path = batch_dir / "jpg" / f"{file_id}.jpg"
    if not jpg_path.exists():
        return jsonify({"error": "文件不存在或已过期"}), 404

    download_name = request.args.get("name", f"{file_id}.jpg")
    return send_file(
        str(jpg_path),
        mimetype="image/jpeg",
        as_attachment=True,
        download_name=download_name,
    )


@app.route("/batch/<batch_id>/zip")
def batch_zip(batch_id):
    batch_dir = UPLOAD_DIR / batch_id
    if not batch_dir.is_dir():
        return jsonify({"error": "批次不存在或已过期"}), 404

    jpg_dir = batch_dir / "jpg"
    jpg_files = sorted(jpg_dir.glob("*.jpg")) if jpg_dir.is_dir() else []
    if not jpg_files:
        return jsonify({"error": "没有可下载的文件"}), 404

    # Load metadata for original filenames
    meta_path = batch_dir / "meta.json"
    file_mapping = {}
    if meta_path.exists():
        try:
            with open(str(meta_path), "r", encoding="utf-8") as f:
                meta = json.load(f)
            file_mapping = meta.get("file_mapping", {})
        except Exception:
            pass

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for jpg_file in jpg_files:
            fid = jpg_file.stem
            arcname = file_mapping.get(fid, f"{fid}.jpg")
            zf.write(str(jpg_file), arcname)

    buf.seek(0)
    return send_file(
        buf,
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"raw2jpg_{batch_id[:8]}.zip",
    )


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8084, debug=True)
