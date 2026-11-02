import React, { useState, useEffect, useRef } from "react";
import axios from "axios";

// API base URL — set VITE_BACKEND_URL=http://localhost:5000 in frontend/.env
const BASE_URL =
  import.meta.env.VITE_BACKEND_URL?.replace(/\/upload$/, "") ||
  "http://localhost:5000";

const ALLOWED_ACCEPT = "image/*,.pdf,.txt,.doc,.docx,.csv,.xlsx,.mp4,.mp3,.zip";

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function formatDate(iso) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function FileUpload() {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState(null);
  const [uploadError, setUploadError] = useState("");
  const [files, setFiles] = useState([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deletingFile, setDeletingFile] = useState(null);
  const [backendStatus, setBackendStatus] = useState("checking"); // 'healthy' | 'error' | 'checking'
  const [emulatorMode, setEmulatorMode] = useState(false);
  const fileInputRef = useRef(null);

  // ── Health check on mount ──────────────────────────────────────────────
  useEffect(() => {
    axios
      .get(`${BASE_URL}/health`)
      .then((r) => {
        setBackendStatus(r.data.status === "healthy" ? "healthy" : "error");
        setEmulatorMode(r.data.emulator_mode === true);
      })
      .catch(() => setBackendStatus("error"));
  }, []);

  // ── Load file list on mount ────────────────────────────────────────────
  useEffect(() => {
    fetchFiles();
  }, []);

  async function fetchFiles() {
    setLoadingFiles(true);
    try {
      const res = await axios.get(`${BASE_URL}/files`);
      setFiles(res.data.files || []);
    } catch (err) {
      console.warn("Could not load file list:", err.message);
      setFiles([]);
    } finally {
      setLoadingFiles(false);
    }
  }

  // ── Upload ─────────────────────────────────────────────────────────────
  const handleFileChange = (e) => {
    setFile(e.target.files[0] || null);
    setUploadError("");
    setUploadResult(null);
  };

  const handleUpload = async () => {
    if (!file) {
      setUploadError("Please select a file first.");
      return;
    }
    if (file.size > 50 * 1024 * 1024) {
      setUploadError("File exceeds the 50 MB limit.");
      return;
    }

    setUploading(true);
    setUploadError("");
    setUploadResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const res = await axios.post(`${BASE_URL}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      setUploadResult(res.data);
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      // Refresh file list
      fetchFiles();
    } catch (err) {
      setUploadError(
        err.response?.data?.error || "Upload failed. Check the console for details."
      );
    } finally {
      setUploading(false);
    }
  };

  // ── Delete ─────────────────────────────────────────────────────────────
  const handleDelete = async (filename) => {
    if (!window.confirm(`Delete "${filename}"?`)) return;
    setDeletingFile(filename);
    setDeleteError("");
    try {
      await axios.delete(`${BASE_URL}/delete/${encodeURIComponent(filename)}`);
      setFiles((prev) => prev.filter((f) => f.name !== filename));
    } catch (err) {
      setDeleteError(
        err.response?.data?.error || `Failed to delete "${filename}".`
      );
    } finally {
      setDeletingFile(null);
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="container mt-5 mb-5">
      {/* Backend status badges */}
      <div className="text-center mb-3 d-flex gap-2 justify-content-center flex-wrap">
        <span
          className={`badge fs-6 ${
            backendStatus === "healthy"
              ? "bg-success"
              : backendStatus === "error"
              ? "bg-danger"
              : "bg-secondary"
          }`}
        >
          {backendStatus === "healthy"
            ? "✅ Backend Connected"
            : backendStatus === "error"
            ? "❌ Backend Unreachable"
            : "⏳ Checking backend…"}
        </span>
        {backendStatus === "healthy" && (
          <span className={`badge fs-6 ${emulatorMode ? "bg-warning text-dark" : "bg-info"}`}>
            {emulatorMode ? "🧪 Local Emulator (fake-gcs-server)" : "☁️ Google Cloud Storage"}
          </span>
        )}
      </div>

      <div className="row justify-content-center">
        <div className="col-md-8">

          {/* ── Upload card ── */}
          <div className="card mb-4">
            <div className="card-body p-5">
              <h2 className="card-title text-center mb-4">📤 Upload a File</h2>

              <div className="mb-3">
                <label htmlFor="fileInput" className="form-label fw-semibold">
                  Choose File
                </label>
                <input
                  type="file"
                  className="form-control"
                  id="fileInput"
                  ref={fileInputRef}
                  onChange={handleFileChange}
                  disabled={uploading}
                  accept={ALLOWED_ACCEPT}
                />
                <small className="text-muted">
                  Supported: Images, PDF, TXT, DOC/DOCX, CSV, XLSX, MP4, MP3, ZIP — max 50 MB
                </small>
              </div>

              {file && (
                <div className="alert alert-secondary py-2 small mb-3">
                  <strong>{file.name}</strong> — {formatBytes(file.size)}
                </div>
              )}

              <div className="d-grid">
                <button
                  className="btn btn-primary btn-lg"
                  id="uploadBtn"
                  onClick={handleUpload}
                  disabled={!file || uploading}
                >
                  {uploading ? (
                    <>
                      <span className="spinner-border spinner-border-sm me-2" />
                      Uploading…
                    </>
                  ) : (
                    "☁️ Upload to Cloud"
                  )}
                </button>
              </div>

              {uploadError && (
                <div className="alert alert-danger mt-4" role="alert">
                  <strong>Error:</strong> {uploadError}
                </div>
              )}

              {uploadResult && (
                <div className="alert alert-success mt-4" role="alert">
                  <strong>✅ Uploaded!</strong>
                  <p className="mb-1 mt-2">
                    <strong>File:</strong> {uploadResult.original_name}
                  </p>
                  <p className="mb-1">
                    <strong>Size:</strong> {formatBytes(uploadResult.size)}
                  </p>
                  <p className="mb-2">
                    <strong>Link:</strong>{" "}
                    <a
                      href={uploadResult.url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Download / View
                    </a>
                  </p>
                  <button
                    className="btn btn-sm btn-outline-success"
                    onClick={() => {
                      navigator.clipboard.writeText(uploadResult.url);
                      alert("Link copied!");
                    }}
                  >
                    📋 Copy Link
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* ── File list card ── */}
          <div className="card">
            <div className="card-header d-flex justify-content-between align-items-center">
              <h5 className="mb-0">📂 Files in Bucket</h5>
              <button
                className="btn btn-sm btn-outline-secondary"
                id="refreshBtn"
                onClick={fetchFiles}
                disabled={loadingFiles}
              >
                {loadingFiles ? "Refreshing…" : "🔄 Refresh"}
              </button>
            </div>
            <div className="card-body p-0">
              {deleteError && (
                <div className="alert alert-danger m-3">{deleteError}</div>
              )}

              {loadingFiles ? (
                <div className="text-center py-4">
                  <span className="spinner-border text-primary" />
                </div>
              ) : files.length === 0 ? (
                <p className="text-muted text-center py-4 mb-0">
                  No files found in the bucket.
                </p>
              ) : (
                <div className="table-responsive">
                  <table className="table table-hover mb-0 align-middle">
                    <thead className="table-light">
                      <tr>
                        <th>Name</th>
                        <th>Size</th>
                        <th>Uploaded</th>
                        <th className="text-end">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {files.map((f) => (
                        <tr key={f.name}>
                          <td
                            className="text-truncate"
                            style={{ maxWidth: "200px" }}
                            title={f.original_name}
                          >
                            {f.original_name}
                          </td>
                          <td>{formatBytes(f.size)}</td>
                          <td className="small text-muted">
                            {formatDate(f.created)}
                          </td>
                          <td className="text-end">
                            <a
                              href={f.url}
                              className="btn btn-sm btn-outline-primary me-2"
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              ⬇ Download
                            </a>
                            <button
                              className="btn btn-sm btn-outline-danger"
                              onClick={() => handleDelete(f.name)}
                              disabled={deletingFile === f.name}
                            >
                              {deletingFile === f.name ? "…" : "🗑 Delete"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>

          {/* How it works */}
          <div className="mt-4 pt-3 border-top small text-muted">
            <h6>How it works</h6>
            <ol>
              <li>Select a file and click <em>Upload to Cloud</em></li>
              <li>
                The file is sent to the Flask backend and stored in{" "}
                {emulatorMode
                  ? "the local GCS emulator (fake-gcs-server)"
                  : "Google Cloud Storage"}
              </li>
              <li>
                {emulatorMode
                  ? "A backend download URL is returned (emulator mode — no signed URLs needed)"
                  : "A signed download URL is returned — valid for 1 hour"}
              </li>
              <li>Use <em>Files in Bucket</em> to browse, download, or delete uploaded files</li>
            </ol>
          </div>
        </div>
      </div>
    </div>
  );
}
