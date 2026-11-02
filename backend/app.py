"""
Cloud File Uploader - Flask Backend
Original repository: https://github.com/kdrd004/cloud-file-uploader
Modified to support:
  - Full CRUD endpoints (upload, list, download, delete)
  - Local GCS emulator mode via fake-gcs-server (fsouza/fake-gcs-server)
  - Production GCS mode with Application Default Credentials or service account
  - Environment-variable-driven configuration (no hardcoded values)
  - Secure filenames, file-type validation, 50 MB size cap
  - Backend /download/<filename> proxy for emulator-compatible downloads
"""

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from google.cloud import storage
from google.api_core.exceptions import NotFound
from google.auth.credentials import AnonymousCredentials
from dotenv import load_dotenv
import os
import uuid
import traceback
import io
from datetime import timedelta
from werkzeug.utils import secure_filename

load_dotenv()

app = Flask(__name__)

# ─── Configuration ────────────────────────────────────────────────────────────
GCS_BUCKET_NAME        = os.environ.get("GCS_BUCKET_NAME", "")
GOOGLE_CLOUD_PROJECT   = os.environ.get("GOOGLE_CLOUD_PROJECT", "cloudvault-local")
STORAGE_EMULATOR_HOST  = os.environ.get("STORAGE_EMULATOR_HOST", "")       # e.g. http://localhost:4443
EMULATOR_MODE          = os.environ.get("STORAGE_EMULATOR_MODE", "false").lower() == "true"

MAX_CONTENT_LENGTH = 50 * 1024 * 1024   # 50 MB
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

ALLOWED_EXTENSIONS = {
    "png", "jpg", "jpeg", "gif", "webp",
    "pdf", "txt", "doc", "docx",
    "csv", "xlsx", "xls",
    "mp4", "mp3", "zip",
}

# ─── CORS ─────────────────────────────────────────────────────────────────────
ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://file-uploader-frontend-zeta.vercel.app",
]
extra_origins = os.environ.get("ALLOWED_ORIGINS", os.environ.get("CORS_ORIGIN", ""))
if extra_origins:
    ALLOWED_ORIGINS.extend([o.strip() for o in extra_origins.split(",") if o.strip()])

CORS(app, resources={r"/*": {"origins": ALLOWED_ORIGINS}})


# ─── Storage client factory ───────────────────────────────────────────────────

def _make_client() -> storage.Client:
    """
    Return a configured GCS storage.Client.

    - In EMULATOR mode  → AnonymousCredentials + custom API endpoint pointing
                          at fake-gcs-server (no real GCP needed).
    - In PRODUCTION mode → standard Application Default Credentials or the
                          service-account key set via GOOGLE_APPLICATION_CREDENTIALS.
    """
    if EMULATOR_MODE:
        host = STORAGE_EMULATOR_HOST.rstrip("/")
        if not host:
            raise RuntimeError(
                "STORAGE_EMULATOR_MODE=true but STORAGE_EMULATOR_HOST is not set. "
                "Add STORAGE_EMULATOR_HOST=http://localhost:4443 to backend/.env"
            )
        # fake-gcs-server exposes a JSON API compatible with the GCS SDK when
        # you override client_options.api_endpoint.
        client = storage.Client(
            project=GOOGLE_CLOUD_PROJECT,
            credentials=AnonymousCredentials(),
            client_options={"api_endpoint": host},
        )
        return client

    # Production path — uses ADC or GOOGLE_APPLICATION_CREDENTIALS
    return storage.Client(project=GOOGLE_CLOUD_PROJECT)


def get_bucket() -> storage.Bucket:
    """Return the configured bucket object. Raises ValueError if not configured."""
    if not GCS_BUCKET_NAME:
        raise ValueError(
            "GCS_BUCKET_NAME is not set. Add it to backend/.env."
        )
    client = _make_client()
    return client.bucket(GCS_BUCKET_NAME)


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _download_url_for(blob_name: str) -> str:
    """
    Return the URL the frontend should use to download a file.

    - Emulator mode  → backend /download/<blob_name> proxy  (signed URLs are
                        not supported by fake-gcs-server in the same way)
    - Production mode → v4 signed URL (1-hour expiry), falling back to
                        public_url if signing credentials are unavailable.
    """
    if EMULATOR_MODE:
        # Proxy through our own Flask /download endpoint so the browser
        # never needs to talk to the emulator directly.
        return f"{request.host_url}download/{blob_name}"

    # Production: generate a signed URL
    try:
        bucket = get_bucket()
        blob = bucket.blob(blob_name)
        return blob.generate_signed_url(
            version="v4",
            expiration=timedelta(hours=1),
            method="GET",
        )
    except Exception:
        # Fall back to public URL (works when the bucket is public or ADC lacks
        # the Token Creator role needed for signed URLs)
        bucket = get_bucket()
        blob = bucket.blob(blob_name)
        return blob.public_url


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    return jsonify({
        "message": "Cloud File Uploader backend is running!",
        "emulator_mode": EMULATOR_MODE,
    })


@app.route("/health")
def health():
    """Health check — also reports emulator vs production mode."""
    return jsonify({
        "status": "healthy",
        "bucket_configured": bool(GCS_BUCKET_NAME),
        "bucket": GCS_BUCKET_NAME or None,
        "emulator_mode": EMULATOR_MODE,
        "emulator_host": STORAGE_EMULATOR_HOST if EMULATOR_MODE else None,
    })


@app.route("/upload", methods=["POST"])
def upload_file():
    """
    POST /upload
    Body: multipart/form-data  { file: <binary> }
    Response: { url, filename, original_name, size }
    """
    try:
        if "file" not in request.files:
            return jsonify({"error": "No 'file' field in request"}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"error": "No file selected (empty filename)"}), 400

        if not allowed_file(file.filename):
            return jsonify({
                "error": (
                    f"File type not allowed. "
                    f"Allowed types: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
                )
            }), 400

        # Build a unique, safe object name
        original_name = secure_filename(file.filename)
        unique_name   = f"{uuid.uuid4().hex}_{original_name}"

        bucket = get_bucket()
        blob   = bucket.blob(unique_name)
        blob.upload_from_file(file, rewind=True)

        # Reload to get server-side metadata (size, content_type, etc.)
        blob.reload()
        size = blob.size or 0

        download_url = _download_url_for(unique_name)

        return jsonify({
            "url":           download_url,
            "filename":      unique_name,
            "original_name": original_name,
            "size":          size,
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        print("UPLOAD ERROR:", e)
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/files", methods=["GET"])
def list_files():
    """
    GET /files
    Response: { files: [{ name, original_name, url, size, created, content_type }] }
    """
    try:
        bucket = get_bucket()
        blobs  = list(bucket.list_blobs())

        files = []
        for blob in blobs:
            # Strip the UUID prefix added during upload (32 hex chars + "_")
            parts    = blob.name.split("_", 1)
            original = parts[1] if (len(parts) == 2 and len(parts[0]) == 32) else blob.name

            files.append({
                "name":         blob.name,
                "original_name": original,
                "url":          _download_url_for(blob.name),
                "size":         blob.size,
                "created":      blob.time_created.isoformat() if blob.time_created else None,
                "content_type": blob.content_type,
            })

        return jsonify({"files": files})

    except ValueError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        print("LIST ERROR:", e)
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/download/<path:filename>", methods=["GET"])
def download_file(filename):
    """
    GET /download/<filename>
    Streams the object back to the client through the Flask backend.
    Used in emulator mode (where browser-level signed URLs are unavailable)
    and works in production mode too as a direct proxy.
    Prevents path-traversal: only the GCS object name is used, no local FS access.
    """
    try:
        # Reject any attempt to traverse paths (should not happen with GCS names,
        # but guard defensively)
        safe_name = filename.replace("..", "").lstrip("/\\")
        if not safe_name:
            return jsonify({"error": "Invalid filename"}), 400

        bucket = get_bucket()
        blob   = bucket.blob(safe_name)

        # Download into memory (fine for files ≤ 50 MB)
        data = blob.download_as_bytes()
        content_type = blob.content_type or "application/octet-stream"

        # Use only the last path segment as the download filename
        display_name = safe_name.split("/")[-1]
        # Strip UUID prefix if present
        parts = display_name.split("_", 1)
        if len(parts) == 2 and len(parts[0]) == 32:
            display_name = parts[1]

        return send_file(
            io.BytesIO(data),
            mimetype=content_type,
            as_attachment=True,
            download_name=display_name,
        )

    except NotFound:
        return jsonify({"error": f"File '{filename}' not found in bucket"}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        print("DOWNLOAD ERROR:", e)
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route("/delete/<path:filename>", methods=["DELETE"])
def delete_file(filename):
    """
    DELETE /delete/<filename>
    Response: { message: string }
    """
    try:
        bucket = get_bucket()
        blob   = bucket.blob(filename)
        blob.delete()
        return jsonify({"message": f"File '{filename}' deleted successfully"})

    except NotFound:
        return jsonify({"error": f"File '{filename}' not found in bucket"}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        print("DELETE ERROR:", e)
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port  = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    mode  = "EMULATOR" if EMULATOR_MODE else "PRODUCTION"
    print(f"Starting Flask on port {port}  |  Mode: {mode}  |  Bucket: {GCS_BUCKET_NAME or 'NOT SET'}")
    if EMULATOR_MODE:
        print(f"  -> Emulator: {STORAGE_EMULATOR_HOST}")
    app.run(host="0.0.0.0", port=port, debug=debug)
