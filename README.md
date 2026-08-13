# PII Redaction Tool

A production-quality web application to automatically detect and redact Personally Identifiable Information (PII) from Microsoft Word (`.docx`) documents, replacing detected values with deterministic, mathematically valid synthetic replacements.

---

## 1. Overview
This tool allows users to upload a DOCX document, processes it through a high-precision Python PII redaction pipeline in the backend, displays a summary of the redactions, and enables downloading the redacted DOCX with preserved layouts and styling.

---

## 2. Features
- **In-Place Segmented Redaction**: Operates directly on the document's XML runs to preserve formatting (bold, italic, fonts, sizes).
- **Split Redact & Download**: Statistics are generated and returned in a metadata payload first, followed by a separate secure download request.
- **Robust Security Policies**: Replaces sensitive data with realistic, deterministic synthetic data (e.g. Luhn-compliant credit cards, phone numbers, and month-preserving dates).
- **Temporary File Protection**: Safe directory sandboxing under the OS temporary folder. Temporary files and mapping entries are cleared immediately after download or automatically pruned after 30 minutes.

---

## 3. Architecture

```
React (Vercel) → FastAPI (Render) → RedactionEngine → Redacted DOCX
```

1. **Frontend (React + Vite)**: Sends the DOCX file to the FastAPI backend using `multipart/form-data`.
2. **Backend (FastAPI)**: Saves the file temporarily, instantiates the `RedactionEngine`, redacts the document, stores the output path against a secure UUID `file_id` mapping, and returns statistics.
3. **Download**: The frontend requests the file via `/api/download/{file_id}`, which serves it as a `FileResponse` and registers a background task to safely delete the file from the server.

---

## 4. Supported PII Types
- **EMAIL**: Detected via standard RFC-compliant regexes.
- **PHONE**: Indian mobile and landline patterns requiring structural prefixes (`+91`/`0`) or sentence-bound keywords.
- **IP_ADDRESS**: IPv4 octet bounds ($0 \le octet \le 255$).
- **SSN**: Hyphenated and unhyphenated SSN formats.
- **CREDIT_CARD**: 13-19 digit candidates validated by the Luhn algorithm.
- **DATE_OF_BIRTH**: Verified using date structures proximity-linked to birth keywords.
- **PERSON**: Boosted by designation/professional keywords in the same sentence.
- **COMPANY**: Filters out public bodies and legally mandated regulators (e.g. SEBI, BSE, NSE) while matching commercial ORG entities.
- **ADDRESS**: Complex address structures matching multiple elements and Indian PIN codes.

---

## 5. How the Redaction Engine Works
1. **Extraction**: `DocumentReader` extracts paragraphs, tables, cells, headers, and footers in document layout order.
2. **Detection**: Runs the regex and spaCy/Presidio detectors against block text.
3. **Overlap Resolution**: A greedy interval scheduler resolves overlaps by sorting by confidence, type priority, and length.
4. **Redaction Slicing**: Slices paragraph XML runs right-to-left using original offsets to safely insert replacements without shifting unmutated spans.

---

## 6. Local Setup

### Prerequisites
- Python 3.10+
- Node.js 18+

### Setup Python Backend
1. Install requirements:
   ```bash
   pip install -r requirements.txt
   ```
2. Download the spaCy model:
   ```bash
   python -m spacy download en_core_web_sm
   ```

### Setup React Frontend
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install Node modules:
   ```bash
   npm install
   ```

---

## 7. Running Backend
From the root directory, run:
```bash
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```
API Documentation will be available at `http://127.0.0.1:8000/docs`.

---

## 8. Running Frontend
From the `frontend` directory, run:
```bash
npm run dev
```
Open `http://localhost:5173` in your browser.

---

## 9. API Endpoints
- **GET `/api/health`**: Liveness probe returning `{"status": "ok"}`.
- **POST `/api/redact`**: Accepts `.docx` document, returns `file_id` and replacements statistics.
- **GET `/api/download/{file_id}`**: Downloads the redacted document and triggers background file deletion.

---

## 10. Testing
Run the complete test suite (includes 62 engine tests and 7 backend tests):
```bash
pytest -q
```
Currently, **69 automated tests** are passing.

---

## 11. Render & Vercel Deployment

### Backend (Render)
- **Service Type**: Web Service
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- **Environment Variables**:
  - `FRONTEND_URL` = `https://<your-vercel-domain>.vercel.app`

### Frontend (Vercel)
- **Root Directory**: `frontend`
- **Build Command**: `npm run build`
- **Output Directory**: `dist`
- **Environment Variables**:
  - `VITE_API_URL` = `https://<your-render-subdomain>.onrender.com`

---

## 12. Security Considerations
- **No Path Traversal**: Files are mapped only via UUIDs, completely decoupling client input from the filesystem.
- **Ephemeral Storage**: All files are stored under a sandboxed directory in the OS temp folder. Input files are cleared immediately after redaction; output files are cleared post-download or pruned after 30 minutes of inactivity.
- **Leaked PII Prevention**: Metadata payloads do not contain original PII values or mapped tables, returning only counts and the random file identifier.

---

## 13. Example Usage
```bash
# Redact document via API (Returns JSON metadata)
curl -X POST -F "file=@prospectus.docx" http://127.0.0.1:8000/api/redact

# Download the redacted output
curl -O -J http://127.0.0.1:8000/api/download/a4d33a9b-3c48-43e8-8a8b-11752b2f6bc4
```
