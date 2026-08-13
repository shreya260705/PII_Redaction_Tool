import React, { useState, useRef, useEffect } from "react";
import "./App.css";

const API_BASE = import.meta.env.VITE_API_URL || 
  (window.location.hostname === "127.0.0.1" ? "http://127.0.0.1:8000" : "http://localhost:8000");

export default function App() {
  const [file, setFile] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [status, setStatus] = useState("idle"); // idle | processing | success | error
  const [errorMsg, setErrorMsg] = useState("");
  const [redactResult, setRedactResult] = useState(null);

  // Expiry states
  const [timeLeft, setTimeLeft] = useState("");
  const [expired, setExpired] = useState(false);

  const fileInputRef = useRef(null);
  const timerRef = useRef(null);

  // Effect to manage countdown timer based on server-provided expires_at
  useEffect(() => {
    if (status === "success" && redactResult && redactResult.expires_at) {
      const targetTime = new Date(redactResult.expires_at).getTime();

      const updateTimer = () => {
        const now = new Date().getTime();
        const diff = targetTime - now;

        if (diff <= 0) {
          setExpired(true);
          setTimeLeft("00:00");
          if (timerRef.current) {
            clearInterval(timerRef.current);
            timerRef.current = null;
          }
        } else {
          const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
          const seconds = Math.floor((diff % (1000 * 60)) / 1000);
          const mm = String(minutes).padStart(2, "0");
          const ss = String(seconds).padStart(2, "0");
          setTimeLeft(`${mm}:${ss}`);
          setExpired(false);
        }
      };

      updateTimer();
      timerRef.current = setInterval(updateTimer, 1000);
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [status, redactResult]);

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
    setExpired(false);
    setTimeLeft("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
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
    if (!redactResult || !redactResult.file_id || expired) return;

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
      a.download = redactResult.filename || "Redacted_Document.docx";
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
        <div className="logo-container">
          <svg className="shield-logo" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          </svg>
          <span className="logo-text">PII Shield</span>
        </div>
      </header>

      <section className="hero-section">
        <h1>Secure Document Redaction</h1>
        <p>Safely remove sensitive PII from your Word documents with deterministic synthetic replacements.</p>
      </section>

      <main className="content-card slide-up">
        {/* Error Alert */}
        {status === "error" && errorMsg && (
          <div className="error-alert fade-in">
            <svg className="error-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <div className="error-content">
              <h4>Redaction Error</h4>
              <p>{errorMsg}</p>
            </div>
            <button className="close-alert-btn" onClick={() => setErrorMsg("")}>&times;</button>
          </div>
        )}

        {/* Processing State */}
        {status === "processing" ? (
          <div className="status-container processing-state">
            <div className="spinner"></div>
            <h3>Redacting Document</h3>
            <p>Scanning text runs, tables, headers, and footers...</p>
          </div>
        ) : status === "success" && redactResult ? (
          /* Success View */
          <div className="status-container success-state fade-in">
            <div className="success-header">
              <div className="success-icon-container">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <h3>Redaction Complete</h3>
              <p className="success-subtitle">{redactResult.total_replacements} PII instances removed</p>
            </div>

            <div className="result-details">
              <div className="detail-row">
                <span className="detail-label">Filename:</span>
                <span className="detail-val" title={file ? file.name : "Document.docx"}>
                  {file ? file.name : "Document.docx"}
                </span>
              </div>

              {/* Statistics Grid */}
              <div className="stats-grid">
                <div className="stat-item total">
                  <span className="stat-count">{redactResult.total_replacements}</span>
                  <span className="stat-label">Total Redacted</span>
                </div>
                <div className="stat-item unique">
                  <span className="stat-count">{redactResult.unique_mappings_count}</span>
                  <span className="stat-label">Unique Mappings</span>
                </div>
                {Object.entries(redactResult.replacements_by_type || {}).map(([type, count]) => (
                  <div className="stat-item type-badge" key={type} data-type={type}>
                    <span className="stat-count">{count}</span>
                    <span className="stat-label">{type}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Action download section */}
            <div className="download-section">
              {!expired ? (
                <>
                  <button className="action-btn download-btn button-press" onClick={handleDownload}>
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                    Download Redacted Document
                  </button>
                  <div className="timer-badge">
                    <svg className="clock-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                      <circle cx="12" cy="12" r="10" />
                      <polyline points="12 6 12 12 16 14" />
                    </svg>
                    <span>Expires in <span className="countdown-timer">{timeLeft}</span></span>
                  </div>
                </>
              ) : (
                <div className="expired-container">
                  <button className="action-btn download-btn expired" disabled>
                    Download Expired
                  </button>
                  <p className="expired-label">This file expired and is no longer available.</p>
                </div>
              )}
            </div>

            <button className="action-btn secondary-btn" onClick={removeFile}>
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
                <div className="upload-icon-container">
                  <svg className="upload-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                    <polyline points="14 2 14 8 20 8" />
                    <line x1="12" y1="18" x2="12" y2="12" />
                    <polyline points="9 15 12 12 15 15" />
                  </svg>
                </div>
                <h3>Select document</h3>
                <p>Drag & drop your DOCX file here, or <span className="browse-link">browse</span></p>
                <span className="file-size-hint">Max size 20MB</span>
                <input
                  ref={fileInputRef}
                  type="file"
                  className="file-input"
                  accept=".docx"
                  onChange={handleFileChange}
                />
              </div>
            ) : (
              <div className="selected-file-container fade-in">
                <div className="selected-file-card">
                  <div className="file-info">
                    <div className="file-icon-wrapper">
                      <svg className="doc-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                        <polyline points="14 2 14 8 20 8" />
                      </svg>
                    </div>
                    <div className="file-details">
                      <span className="file-name" title={file.name}>{file.name}</span>
                      <span className="file-size">{formatBytes(file.size)}</span>
                    </div>
                  </div>
                  <button className="remove-btn" onClick={removeFile} title="Remove file">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <line x1="18" y1="6" x2="6" y2="18" />
                      <line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                  </button>
                </div>

                <button className="action-btn redact-action-btn button-press" onClick={handleUploadAndRedact}>
                  <svg className="lock-icon-btn" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                    <path d="M7 11V7a5 5 0 0 1 10 0v4" />
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
          <div className="info-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
              <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            </svg>
          </div>
          <div className="info-text">
            <h4>Private Processing</h4>
            <p>Documents are processed in ephemeral memory and deleted automatically after 2 minutes.</p>
          </div>
        </div>
        <div className="info-card">
          <div className="info-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
              <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
              <line x1="12" y1="22.08" x2="12" y2="12" />
            </svg>
          </div>
          <div className="info-text">
            <h4>Consistent Mapping</h4>
            <p>Identified entities are replaced with deterministic synthetic alternatives, keeping formatting intact.</p>
          </div>
        </div>
      </section>
    </div>
  );
}
