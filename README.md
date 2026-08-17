
````markdown
# PII Shield — PII Redaction Tool

A full-stack document security application that automatically detects and
redacts Personally Identifiable Information (PII) from DOCX documents,
replacing sensitive values with deterministic synthetic alternatives.

The project provides both a Python redaction engine and a web interface
for uploading documents, processing them through a FastAPI backend, and
securely downloading the generated redacted document.

---

## Live Deployment

### Frontend

PII Shield is deployed as a React/Vite application on Vercel.

**Frontend:**  
https://pii-redaction-tool-c777.vercel.app

### Backend

The FastAPI redaction backend is deployed on Render.

**Backend:**  
https://pii-redaction-tool-fbh6.onrender.com

### API Documentation

The FastAPI backend provides Swagger/OpenAPI documentation at:

https://pii-redaction-tool-fbh6.onrender.com/docs

---

# 1. Problem Statement

Documents such as legal documents, prospectuses, HR records, and support
logs can contain sensitive personally identifiable information.

Manually identifying and removing this information is time-consuming and
error-prone. The objective of this project is to automate the process by
detecting common PII categories and replacing them with safe synthetic
values while preserving the document structure and usability.

The system is designed to process DOCX documents containing both structured
PII and natural-language PII.

---

# 2. Key Features

- Automatic PII detection in DOCX documents
- Detection of names, emails, phone numbers, companies, addresses,
  SSNs, credit cards, dates of birth, and IP addresses
- Combination of regex-based and NLP-based detection
- Context-aware Date of Birth detection
- Deterministic replacement mapping
- Protection against cross-category replacements
- DOCX paragraph and table processing
- Preservation of document headings and titles
- FastAPI REST backend
- React-based web frontend
- DOCX file upload and redaction
- Asynchronous processing for longer-running document redaction
- Frontend polling for asynchronous task status
- Redaction statistics returned to the frontend
- Temporary download links
- Two-minute download expiry
- Multiple downloads allowed before expiry
- Live frontend countdown for file expiration
- Automated regression and accuracy testing
- Strict synthetic evaluation fixture
- Docker support
- Swagger/OpenAPI API documentation
- Vercel frontend deployment
- Render backend deployment

---

# 3. System Architecture

The application consists of the following major components:

```text
                    User
                      │
                      ▼
          ┌──────────────────────┐
          │   React Frontend     │
          │       Vercel         │
          └──────────┬───────────┘
                     │
                     │ HTTPS
                     ▼
          ┌──────────────────────┐
          │   FastAPI Backend    │
          │       Render         │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │ Async Redaction Task │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │   Redaction Engine   │
          │ Detection + Mapping  │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │    Redacted DOCX     │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │ Temporary File Store │
          └──────────┬───────────┘
                     │
                     ▼
          ┌──────────────────────┐
          │ Frontend Download    │
          └──────────────────────┘
````

---

## Processing Flow

For asynchronous processing:

```text
DOCX Upload
     ↓
POST /api/redact-async
     ↓
Task ID returned
     ↓
Background Redaction Task
     ↓
Document Extraction
     ↓
PII Detection
     ↓
Entity Resolution / Validation
     ↓
Deterministic Replacement Mapping
     ↓
DOCX Redaction
     ↓
Task Status = success
     ↓
Redacted DOCX
     ↓
Temporary File Storage
     ↓
Frontend Download
```

The frontend polls the backend for task status rather than keeping one
long-running HTTP request open for the entire redaction process.

This is particularly useful for larger DOCX documents that require more
processing time.

---

# 4. Detection Approach

The redaction engine uses a combination of structured pattern detection,
NLP and contextual rules rather than relying on a single detection
technique.

## Regex / Structured Detection

Regular expressions are used for PII with predictable formats:

* Email addresses
* Phone numbers
* IP addresses
* SSNs
* Credit card numbers
* Dates

Credit card detection also supports commonly formatted 16-digit values
using grouped spaces or hyphens.

---

## NLP-Based Detection

spaCy NLP is used for natural-language entities where regex alone is
not sufficient, particularly:

* PERSON
* COMPANY / organization-related entities
* Address-related entities

Additional candidate matching is used for person names where required.

---

## Context-Aware Detection

Some values are ambiguous when considered without context.

For example:

```text
15/04/1995
```

could simply be a document date rather than a person's date of birth.

The Date of Birth detector therefore uses contextual information such as
DOB/date-of-birth headers before treating a date as a
DATE_OF_BIRTH entity.

---

# 5. Entity Validation and Conflict Handling

Multiple detectors can sometimes identify overlapping text.

The redaction pipeline therefore validates detected matches before
applying replacements.

Cross-category replacement conflicts are prevented so that a value
detected as one PII category cannot incorrectly receive a replacement
belonging to another category.

PERSON detection also applies filtering rules to avoid treating document
headings, section labels, or other non-person text as names.

Document titles and heading styles are protected from unnecessary NLP
redaction.

---

# 6. Deterministic Redaction

The system does not simply delete PII.

Every detected value is replaced with a synthetic alternative.

Replacement mappings are deterministic, meaning that repeated
occurrences of the same original value receive the same replacement
throughout the document.

For example:

```text
Rohan Sharma
      ↓
Synthetic Person Name
```

```text
rohan.sharma@example.com
      ↓
Synthetic Email
```

```text
+91 9876543210
      ↓
Synthetic Phone Number
```

This makes the redacted document easier to read while preventing the
original sensitive value from remaining in the output.

---

# 7. DOCX Processing

The project uses `python-docx` for reading and writing DOCX files.

The document is processed block-by-block, including document paragraphs
and table content.

The implementation takes into account that DOCX text can be divided
across multiple runs because of formatting such as bold, italic,
font changes, etc.

The redaction process is designed to modify the relevant text while
preserving the surrounding document structure and formatting as much
as possible.

---

# 8. Supported PII Categories

The current implementation supports:

| Category      | Detection Method              |
| ------------- | ----------------------------- |
| PERSON        | NLP + name candidate rules    |
| EMAIL         | Regex                         |
| PHONE         | Regex                         |
| COMPANY       | NLP + contextual detection    |
| ADDRESS       | Context / NLP-based detection |
| SSN           | Regex                         |
| CREDIT_CARD   | Regex + format validation     |
| DATE_OF_BIRTH | Context-aware date detection  |
| IP_ADDRESS    | Regex                         |

---

# 9. Backend — FastAPI

The Python redaction engine is exposed through a FastAPI REST API.

## Health Check

```http
GET /api/health
```

Used to verify that the backend is running.

---

## Synchronous Redaction

```http
POST /api/redact
```

Accepts a DOCX document, runs the redaction engine, and returns
information about the generated redacted file.

The response includes:

* File identifier
* Redaction counts
* Download information
* Expiration timestamp

---

## Asynchronous Redaction

```http
POST /api/redact-async
```

Creates a background redaction task for the uploaded document.

The endpoint returns a task identifier that can be used to monitor
processing.

Example flow:

```text
POST /api/redact-async
        ↓
task_id
        ↓
GET /api/tasks/{task_id}
```

---

## Task Status

```http
GET /api/tasks/{task_id}
```

Used by the frontend to monitor asynchronous document processing.

The frontend periodically polls this endpoint until the task reaches
a completed or failed state.

---

## Download Redacted File

```http
GET /api/download/{file_id}
```

Downloads the generated redacted document while it is still within
its valid download period.

---

## API Documentation

FastAPI automatically provides Swagger/OpenAPI documentation.

Local:

```text
http://127.0.0.1:8000/docs
```

Production:

```text
https://pii-redaction-tool-fbh6.onrender.com/docs
```

---

# 10. Temporary Download Security

Generated documents are not permanently exposed through the download
endpoint.

Each generated file receives a temporary two-minute download window.

The backend returns an `expires_at` timestamp to the frontend.

During this period:

* The user can download the document multiple times.
* Downloading the file does not reset the expiry timer.
* The frontend displays a live countdown.

After the expiration time:

* The backend rejects the download request.
* The temporary file is cleaned up.
* The frontend disables the download button.
* The user is shown that the file is no longer available.

This provides a simple mechanism to reduce the lifetime of generated
sensitive documents.

---

# 11. Frontend — PII Shield

The project includes a React frontend designed as a document-security
interface rather than a generic AI interface.

The frontend provides:

* DOCX drag-and-drop upload
* File selection and removal
* Upload / processing state
* Asynchronous processing status
* Redaction result summary
* Number of detected/redacted PII items
* Download button
* Download expiry countdown
* Expired-file state
* Error handling
* Responsive layout

The UI uses a clean security-oriented visual design with a neutral
background, dark typography, restrained accent colors, structured
document cards, and minimal visual decoration.

---

# 12. Evaluation Methodology

Evaluation was performed using a controlled synthetic DOCX fixture with
known ground-truth PII values.

The fixture contains:

| PII Type      | Expected |
| ------------- | -------: |
| PERSON        |        7 |
| EMAIL         |        8 |
| PHONE         |        6 |
| IP_ADDRESS    |        6 |
| SSN           |        6 |
| CREDIT_CARD   |        6 |
| DATE_OF_BIRTH |        6 |
| COMPANY       |        6 |
| ADDRESS       |        6 |
| **TOTAL**     |   **57** |

The evaluation verifies two separate properties:

## Detection Accuracy

Whether all expected PII values were detected.

## Redaction Accuracy

Whether the detected PII was actually removed/replaced in the generated
DOCX.

This distinction is important because a detector reporting a match does
not by itself prove that the value was successfully replaced in the
output document.

---

# 13. Controlled Evaluation Results

The strict synthetic accuracy test produced:

```text
PERSON        7/7
EMAIL         8/8
PHONE         6/6
IP_ADDRESS    6/6
SSN           6/6
CREDIT_CARD   6/6
DATE_OF_BIRTH 6/6
COMPANY       6/6
ADDRESS       6/6
-------------------
TOTAL         57/57
```

The generated DOCX was additionally checked to ensure that the original
PII values were no longer present.

```text
Detected PII:             57/57
Successfully redacted:   57/57
Original PII remaining:    0
```

### Controlled Benchmark Metrics

For this synthetic evaluation fixture:

```text
True Positives (TP):   57
False Positives (FP):   0
False Negatives (FN):   0
```

Therefore:

```text
Precision = TP / (TP + FP)
          = 57 / 57
          = 100%
```

```text
Recall = TP / (TP + FN)
       = 57 / 57
       = 100%
```

```text
F1 Score = 100%
```

### Important Interpretation

These 100% Precision, Recall and F1 values apply **only to the controlled
synthetic 57-PII evaluation fixture with known ground truth**.

They should NOT be interpreted as a universal 100% accuracy guarantee for
arbitrary real-world documents.

---

# 14. Red Herring Prospectus Evaluation

A large Red Herring Prospectus DOCX was also used for large-document
processing and performance validation.

The document is approximately:

```text
1.76 MB
```

The system is able to process large DOCX documents and report the number
of replacements performed by the redaction engine.

However, the Red Herring Prospectus does **not** have a complete,
manually annotated ground-truth PII dataset.

Therefore, the number of replacements reported by the engine for the
Red Herring Prospectus cannot by itself be interpreted as:

* Accuracy
* Precision
* Recall
* F1 score

For example, if the engine reports a certain number of replacements,
that does not prove that every replacement is correct or that every PII
value in the document was detected.

A formal Precision/Recall evaluation for the Red Herring Prospectus
would require a manually annotated ground-truth dataset containing the
complete set of PII values.

Therefore:

```text
Synthetic Evaluation:
Precision = 100%
Recall    = 100%
F1        = 100%

Red Herring Prospectus:
Exact PII ground truth = Not available
Formal Precision       = Not calculated
Formal Recall          = Not calculated
Formal F1              = Not calculated
```

This distinction is intentional and prevents the project from making
unsupported accuracy claims about a real-world document.

---

# 15. Automated Testing

The project contains unit, integration and redaction verification tests.

Run the complete test suite using:

```bash
python -m pytest -q
```

The strict accuracy test independently verifies:

* Expected detection counts
* All supported PII categories
* Actual replacement in the output DOCX
* Absence of original PII values after redaction

Run the strict accuracy test using:

```bash
python -m pytest tests/test_redactor.py -k test_strict_accuracy_verification
```

The controlled test fixture contains 57 known PII values.

---

# 16. Large Document Processing

Large DOCX files require substantially more processing and memory than
small test documents.

The application therefore includes optimizations for longer-running
redaction workloads, including asynchronous task processing and frontend
polling.

The backend can process the document in the background while the
frontend periodically checks the task status.

This avoids relying entirely on one long-lived synchronous browser
request.

The application also includes memory-management measures in the
redaction workflow where supported by the deployment environment.

These optimizations improve handling of large documents but do not imply
unlimited file size or unlimited infrastructure capacity.

---

# 17. Docker

The project includes a `Dockerfile` for containerized execution.

## Build the Docker Image

From the project root:

```bash
docker build -t pii-redaction-tool .
```

## Run the Container

Use the port and startup command defined by the current Dockerfile.

For the standard FastAPI configuration:

```bash
docker run -p 8000:8000 pii-redaction-tool
```

The API can then be accessed at:

```text
http://127.0.0.1:8000
```

Swagger:

```text
http://127.0.0.1:8000/docs
```

Docker provides a consistent environment for running the backend and
its Python dependencies.

---

# 18. Deployment

The project uses a separated frontend/backend deployment architecture.

## Frontend — Vercel

The React/Vite frontend is deployed on Vercel.

```text
https://pii-redaction-tool-c777.vercel.app
```

## Backend — Render

The FastAPI backend is deployed on Render.

```text
https://pii-redaction-tool-fbh6.onrender.com
```

The frontend communicates with the deployed backend over HTTPS.

The production architecture is:

```text
Browser
   │
   ▼
Vercel
React Frontend
   │
   │ HTTPS API Requests
   ▼
Render
FastAPI Backend
   │
   ▼
Python Redaction Engine
```

---

# 19. Local Setup

## Backend

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Run the FastAPI server:

```bash
uvicorn backend.main:app --reload
```

The API will be available at:

```text
http://127.0.0.1:8000
```

Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

---

## Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend will then be available through the Vite development
server.

---

# 20. CLI Usage

The redaction engine can also be used directly without the web
application:

```bash
python -m src.redactor \
    --input "input.docx" \
    --output "output.docx"
```

Example:

```bash
python -m src.redactor \
    --input "Red Herring Prospectus.docx" \
    --output "output/redacted.docx"
```

---

# 21. Project Structure

```text
PII-Redaction-Tool/
│
├── src/
│   ├── detectors/
│   │   ├── structured.py
│   │   └── nlp.py
│   └── redactor.py
│
├── backend/
│   └── main.py
│
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── App.css
│   │   └── index.css
│   ├── package.json
│   └── vite.config.js
│
├── tests/
│
├── evaluation/
│
├── scratch/
│
├── output/
│
├── PII_Strict_Accuracy_Test.docx
├── Red Herring Prospectus.docx
├── requirements.txt
├── Dockerfile
├── .dockerignore
└── README.md
```

Temporary scratch scripts are used during development and debugging and
are not part of the production redaction pipeline.

---

# 22. Technology Stack

## Backend

* Python
* FastAPI
* Uvicorn
* python-docx
* spaCy
* Presidio
* Pytest

## Frontend

* React
* Vite
* JavaScript
* CSS

## Document Processing

* DOCX parsing and generation
* Regex-based structured detection
* NLP / Named Entity Recognition
* Context-aware entity detection
* Deterministic replacement mapping

## Deployment / Infrastructure

* Docker
* Vercel
* Render

---

# 23. Tradeoffs and Known Limitations

## Regex Detection

Regex provides strong precision for structured formats such as emails,
phone numbers and IP addresses, but unusual formatting may cause
false negatives.

## NLP Detection

NLP improves detection of names, companies and addresses but natural
language is ambiguous and can produce false positives.

## Date Detection

Dates are inherently ambiguous. The implementation uses contextual
detection so that ordinary dates are not automatically classified as
dates of birth.

## DOCX Images

The current implementation primarily processes textual DOCX content.
PII contained inside scanned images or image-only documents is not
currently OCR-redacted.

## Large Documents

Large documents require more CPU time and memory than small documents.
Processing time and infrastructure behavior therefore depend on the
deployment environment and available resources.

## Ground Truth

The synthetic benchmark has explicit ground truth.

The Red Herring Prospectus does not have complete manually annotated
ground truth. Therefore formal Precision, Recall and F1 metrics cannot
be calculated for that document without additional annotation.

## Real-World Accuracy

The controlled benchmark demonstrates the behavior of the detector on
the included synthetic evaluation fixture. It does not establish a
universal 100% detection rate for arbitrary real-world documents.

---

# 24. Security Considerations

The application is designed to minimize the lifetime of generated
redacted documents.

Generated output files are temporary and have a limited download window.

The redaction process replaces detected sensitive values with synthetic
alternatives rather than simply deleting them.

For production use, additional controls such as authentication,
authorization, persistent secure storage policies, audit logging and
stronger isolation may be appropriate depending on the deployment
requirements.

---

# 25. Future Improvements

Possible future improvements include:

* OCR-based detection for scanned documents
* Support for additional international PII formats
* Larger manually annotated evaluation datasets
* Formal evaluation on real-world annotated documents
* Background cleanup and stronger temporary-file isolation
* Authentication and access control for production deployments
* More advanced document-format preservation
* Additional export formats such as PDF
* Improved large-document resource management
* More scalable background task infrastructure

---

# 26. Summary

PII Shield is a full-stack DOCX PII redaction system combining:

```text
Regex Detection
       +
NLP Detection
       +
Context-Aware Validation
       +
Deterministic Replacement
       +
DOCX Preservation
       +
Asynchronous Processing
       +
Temporary Secure Downloads
```

The controlled synthetic evaluation fixture contains 57 known PII values
and currently demonstrates:

```text
Detection:       57/57
Redaction:       57/57
Precision:       100%
Recall:          100%
F1 Score:        100%
```

These metrics apply specifically to the controlled synthetic fixture.

For the Red Herring Prospectus, the system can report detected/replaced
values, but a formal Accuracy, Precision, Recall or F1 score is not
claimed because the document does not have a complete manually annotated
PII ground-truth dataset.

The project is deployed using:

```text
React/Vite
     ↓
Vercel
     ↓
FastAPI
     ↓
Render
     ↓
Python Redaction Engine
```

The application also supports Docker-based execution for a consistent
backend runtime environment.

```

