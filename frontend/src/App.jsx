import React, { useState, useRef } from "react";
import "./App.css";

const API_BASE = import.meta.env.VITE_API_URL || 
  (window.location.hostname === "127.0.0.1" ? "http://127.0.0.1:8000" : "http://localhost:8000");

export default function App() {
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [status, setStatus] = useState("idle"); // idle | processing | success | error
  const [errorMsg, setErrorMsg] = useState("");
  const [redactResult, setRedactResult] = useState(null);

  const fileInputRef = useRef(null);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const validateAndSetFile = (selectedFile) => {
    setErrorMsg("");
    if (!selectedFile) return;

    // Validate DOCX
    const isDocx = selectedFile.name.toLowerCase().endsWith(".docx");
    if (!isDocx) {
      setErrorMsg("Unsupported file format. Please upload a .docx document.");
      setStatus("error");
      return;
    }

    // Validate size (20 MB)
    if (selectedFile.size > 20 * 1024 * 1024) {
      setErrorMsg("File too large. Maximum allowed size is 20 MB.");
      setStatus("error");
      return;
    }

    setFile(selectedFile);
    setStatus("idle");
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSetFile(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0]);
    }
  };

  const removeFile = () => {
    setFile(null);
    setRedactResult(null);
    setStatus("idle");
    setErrorMsg("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleUploadAndRedact = async () => {
    if (!file) return;

    setStatus("processing");
    setErrorMsg("");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_BASE}/api/redact`, {
        method: "POST",
        body: formData,
        // Browser sets Content-Type header with multipart boundary automatically
      });

      if (!response.ok) {
        const errData = await response.json().catch(() => ({ detail: "Redaction failed on server." }));
        throw new Error(errData.detail || "An unexpected server error occurred.");
      }

      const result = await response.json();
      setRedactResult(result);
      setStatus("success");
    } catch (err) {
      setErrorMsg(err.message || "Network error. Please check your connection and try again.");
      setStatus("error");
    }
  };

  const handleDownload = async () => {
    if (!redactResult || !redactResult.file_id) return;

    try {
      const downloadUrl = `${API_BASE}/api/download/${redactResult.file_id}`;
      const response = await fetch(downloadUrl);
      if (!response.ok) {
        throw new Error("Failed to download file. It may have expired.");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = redactResult.filename || "Redacted.docx";
      document.body.appendChild(a);
      a.click();
      
      // Cleanup
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      setErrorMsg(err.message || "Failed to initiate download.");
      setStatus("error");
    }
  };

  const formatBytes = (bytes, decimals = 2) => {
    if (bytes === 0) return "0 Bytes";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["Bytes", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>PII Redaction Engine</h1>
        <p>
          Upload a DOCX document and automatically remove personally identifiable information 
          with deterministic synthetic replacements.
        </p>
      </header>

      <main className="glass-card">
        {/* Error State */}
        {status === "error" && errorMsg && (
          <div className="error-alert">
            <svg className="error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div className="error-content">
              <h4>Action Failed</h4>
              <p>{errorMsg}</p>
            </div>
          </div>
        )}

        {/* Processing State */}
        {status === "processing" ? (
          <div className="status-container">
            <div className="spinner"></div>
            <h3>Detecting and redacting PII...</h3>
            <p>Scanning runs, cells, headers, and footers for sensitive information.</p>
          </div>
        ) : status === "success" && redactResult ? (
          /* Success / Statistics View */
          <div className="status-container" style={{ padding: "10px 0" }}>
            <div className="success-header">
              <div className="success-icon-container">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <h2>Redaction Complete</h2>
              <p>Generated safe synthetic mappings successfully.</p>
            </div>

            <div style={{ width: "100%", margin: "20px 0" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "15px", fontSize: "0.95rem" }}>
                <span style={{ color: "var(--text-secondary)" }}>File Name:</span>
                <span style={{ fontWeight: 500 }}>{file ? file.name : "Document.docx"}</span>
              </div>
              
              {/* Statistics Grid */}
              <div className="stats-grid">
                <div className="stat-item total">
                  <div className="stat-count">{redactResult.total_replacements}</div>
                  <div className="stat-label">Total Replacements</div>
                </div>
                <div className="stat-item">
                  <div className="stat-count">{redactResult.unique_mappings_count}</div>
                  <div className="stat-label">Unique Mappings</div>
                </div>
                
                {/* Dynamically render replacements_by_type from backend */}
                {Object.entries(redactResult.replacements_by_type || {}).map(([type, count]) => (
                  <div className="stat-item" key={type}>
                    <div className="stat-count">{count}</div>
                    <div className="stat-label">{type}</div>
                  </div>
                ))}
              </div>
            </div>

            <button className="action-btn" onClick={handleDownload}>
              <svg style={{ width: "22px", height: "22px" }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="7 10 12 15 17 10" />
                <line x1="12" y1="15" x2="12" y2="3" />
              </svg>
              Download Redacted Document
            </button>

            <button className="action-btn secondary-btn" onClick={removeFile} style={{ marginTop: "10px" }}>
              Redact Another Document
            </button>
          </div>
        ) : (
          /* Upload State */
          <>
            {!file ? (
              <div
                className={`upload-zone ${dragActive ? "dragging" : ""}`}
                onDragEnter={handleDrag}
                onDragOver={handleDrag}
                onDragLeave={handleDrag}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current.click()}
              >
                <svg className="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                <h3>Drag & Drop your DOCX here</h3>
                <p>or click to browse your files (Max 20MB)</p>
                <button
                  type="button"
                  className="upload-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    fileInputRef.current.click();
                  }}
                >
                  Choose DOCX
                </button>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="file-input"
                  accept=".docx"
                  onChange={handleFileChange}
                />
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "25px" }}>
                <div className="selected-file-card">
                  <div className="file-info">
                    <svg className="doc-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                      <line x1="16" y1="13" x2="8" y2="13" />
                      <line x1="16" y1="17" x2="8" y2="17" />
                      <polyline points="10 9 9 9 8 9" />
                    </svg>
                    <div className="file-details">
                      <div className="file-name" title={file.name}>
                        {file.name}
                      </div>
                      <div className="file-size">{formatBytes(file.size)}</div>
                    </div>
                  </div>
                  <button className="remove-btn" onClick={removeFile} title="Remove file">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>

                <button className="action-btn" onClick={handleUploadAndRedact}>
                  <svg style={{ width: "22px", height: "22px" }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                  </svg>
                  Redact Document
                </button>
              </div>
            )}
          </>
        )}
      </main>

      <section className="info-section">
        <div className="info-card">
          <h4>What does this tool do?</h4>
          <p>
            The engine detects personally identifiable information such as names, email addresses, 
            phone numbers, IP addresses, SSNs, credit cards, and company names, then replaces them 
            with safe, deterministic synthetic alternatives.
          </p>
        </div>
        <div className="info-card">
          <h4>Security & Safety</h4>
          <p>
            Your original document is never overwritten by the redaction process. File processing occurs 
            entirely inside secure, ephemeral temporary directories, and generated outputs are pruned from 
            the server disk immediately after download or expiration.
          </p>
        </div>
      </section>
    </div>
  );
}
