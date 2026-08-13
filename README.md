# PII Shield — PII Redaction Tool

A full-stack document security application that automatically detects and
redacts Personally Identifiable Information (PII) from DOCX documents,
replacing sensitive values with deterministic synthetic alternatives.

The project provides both a Python redaction engine and a web interface
for uploading documents, processing them through a FastAPI backend, and
securely downloading the generated redacted document.

---

## 1. Problem Statement

Documents such as legal documents, prospectuses, HR records, and support
logs can contain sensitive personally identifiable information.

Manually identifying and removing this information is time-consuming and
error-prone. The objective of this project is to automate the process by
detecting common PII categories and replacing them with safe synthetic
values while preserving the document structure and usability.

---

## 2. Key Features

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
- Redaction statistics returned to the frontend
- Temporary download links
- Two-minute download expiry
- Multiple downloads allowed before expiry
- Live frontend countdown for file expiration
- Automated regression and accuracy testing
- Strict synthetic evaluation fixture
- Swagger/OpenAPI API documentation

---

## 3. System Architecture

The application is divided into three main layers:

    ┌─────────────────────┐
    │   React Frontend    │
    │     PII Shield      │
    └──────────┬──────────┘
               │ HTTP
               ▼
    ┌─────────────────────┐
    │   FastAPI Backend    │
    │  Upload / Download   │
    │  Expiry Management   │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │  Redaction Engine    │
    │ Detection + Mapping  │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │    Redacted DOCX    │
    └─────────────────────┘

### Processing Flow

    DOCX Upload
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
    Redacted DOCX
        ↓
    Temporary File Storage
        ↓
    Download with Expiry

---

## 4. Detection Approach

The redaction engine uses a combination of structured pattern detection,
NLP and contextual rules rather than relying on a single detection
technique.

### Regex / Structured Detection

Regular expressions are used for PII with predictable formats:

- Email addresses
- Phone numbers
- IP addresses
- SSNs
- Credit card numbers
- Dates

Credit card detection also supports commonly formatted 16-digit values
using grouped spaces or hyphens.

### NLP-Based Detection

spaCy NLP is used for natural-language entities where regex alone is
not sufficient, particularly:

- PERSON
- COMPANY / organization-related entities
- Address-related entities

Additional candidate matching is used for person names where required.

### Context-Aware Detection

Some values are ambiguous when considered without context.

For example, a date such as:

    15/04/1995

could simply be a document date rather than a person's date of birth.

The Date of Birth detector therefore uses contextual information such as
DOB/date-of-birth headers before treating a date as a DATE_OF_BIRTH entity.

---

## 5. Entity Validation and Conflict Handling

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

## 6. Deterministic Redaction

The system does not simply delete PII.

Every detected value is replaced with a synthetic alternative.

Replacement mappings are deterministic, meaning that repeated
occurrences of the same original value receive the same replacement
throughout the document.

For example:

    Rohan Sharma
        ↓
    Synthetic Person Name

    rohan.sharma@example.com
        ↓
    Synthetic Email

    +91 9876543210
        ↓
    Synthetic Phone Number

This makes the redacted document easier to read while preventing the
original sensitive value from remaining in the output.

---

## 7. DOCX Processing

The project uses `python-docx` for reading and writing DOCX files.

The document is processed block-by-block, including document
paragraphs and table content.

The implementation takes into account that DOCX text can be divided
across multiple runs because of formatting such as bold, italic,
font changes, etc.

The redaction process is designed to modify the relevant text while
preserving the surrounding document structure and formatting as much
as possible.

---

## 8. Supported PII Categories

The current implementation supports:

| Category | Detection Method |
|----------|------------------|
| PERSON | NLP + name candidate rules |
| EMAIL | Regex |
| PHONE | Regex |
| COMPANY | NLP + contextual detection |
| ADDRESS | Context / NLP-based detection |
| SSN | Regex |
| CREDIT_CARD | Regex + format validation |
| DATE_OF_BIRTH | Context-aware date detection |
| IP_ADDRESS | Regex |

---

# 9. Backend — FastAPI

The Python redaction engine is exposed through a FastAPI REST API.

### Health Check

    GET /api/health

Used to verify that the backend is running.

### Redact Document

    POST /api/redact

Accepts a DOCX document, runs the redaction engine, and returns
information about the generated redacted file.

The response includes:

- File identifier
- Redaction counts
- Download information
- Expiration timestamp

### Download Redacted File

    GET /api/download/{file_id}

Downloads the generated redacted document while it is still within its
valid download period.

### API Documentation

When running locally, FastAPI automatically provides Swagger/OpenAPI
documentation at:

    http://127.0.0.1:8000/docs

---

# 10. Temporary Download Security

Generated documents are not permanently exposed through the download
endpoint.

Each generated file receives a temporary two-minute download window.

The backend returns an `expires_at` timestamp to the frontend.

During this period:

- The user can download the document multiple times.
- Downloading the file does not reset the expiry timer.
- The frontend displays a live countdown.

After the expiration time:

- The backend rejects the download request.
- The temporary file is cleaned up.
- The frontend disables the download button.
- The user is shown that the file is no longer available.

This provides a simple mechanism to reduce the lifetime of generated
sensitive documents.

---

# 11. Frontend — PII Shield

The project includes a React frontend designed as a document-security
interface rather than a generic AI interface.

The frontend provides:

- DOCX drag-and-drop upload
- File selection and removal
- Upload / processing state
- Redaction result summary
- Number of detected/redacted PII items
- Download button
- Download expiry countdown
- Expired-file state
- Error handling
- Responsive layout

The UI uses a clean security-oriented visual design with a neutral
background, dark typography, restrained accent colors, structured
document cards, and minimal visual decoration.

---

# 12. Evaluation Methodology

Evaluation was performed using a controlled synthetic DOCX fixture with
known ground-truth PII values.

The fixture contains:

| PII Type | Expected |
|----------|---------:|
| PERSON | 7 |
| EMAIL | 8 |
| PHONE | 6 |
| IP_ADDRESS | 6 |
| SSN | 6 |
| CREDIT_CARD | 6 |
| DATE_OF_BIRTH | 6 |
| COMPANY | 6 |
| ADDRESS | 6 |
| **TOTAL** | **57** |

The evaluation verifies two separate properties:

### Detection Accuracy

Whether all expected PII values were detected.

### Redaction Accuracy

Whether the detected PII was actually removed/replaced in the generated
DOCX.

This distinction is important because a detector reporting a match does
not by itself prove that the value was successfully replaced in the
output document.

---

# 13. Evaluation Results

The strict accuracy test produced:

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

The generated DOCX was additionally checked to ensure that the original
PII values were no longer present.

    Detected PII:              57/57
    Successfully redacted:    57/57
    Original PII remaining:    0

### Metrics

    True Positives (TP):   57
    False Positives (FP):   0
    False Negatives (FN):   0

    Precision = TP / (TP + FP)
              = 57 / 57
              = 100%

    Recall = TP / (TP + FN)
           = 57 / 57
           = 100%

    F1 Score = 100%

These metrics are based on the controlled synthetic fixture and should
not be interpreted as universal performance guarantees for arbitrary
real-world documents.

---

# 14. Automated Testing

The project contains unit, integration and redaction verification tests.

The complete test suite currently passes:

    70 passed

The strict accuracy test independently verifies:

- Expected detection counts
- All supported PII categories
- Actual replacement in the output DOCX
- Absence of original PII values after redaction

---

# 15. Tradeoffs and Known Limitations

### Regex Detection

Regex provides strong precision for structured formats such as emails,
phone numbers and IP addresses, but unusual formatting may cause
false negatives.

### NLP Detection

NLP improves detection of names, companies and addresses but natural
language is ambiguous and can produce false positives.

### Date Detection

Dates are inherently ambiguous. The implementation uses contextual
detection so that ordinary dates are not automatically classified as
dates of birth.

### DOCX Images

The current implementation primarily processes textual DOCX content.
PII contained inside scanned images or image-only documents is not
currently OCR-redacted.

### Ground Truth

The synthetic benchmark has explicit ground truth. The real Red Herring
Prospectus does not have complete manually annotated ground truth, so
formal precision/recall for that document cannot be claimed without
additional annotation.

---

# 16. Project Structure

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
    ├── output/
    │
    ├── PII_Strict_Accuracy_Test.docx
    ├── Red Herring Prospectus.docx
    ├── requirements.txt
    └── README.md

---

# 17. Local Setup

### Backend

Install Python dependencies:

    pip install -r requirements.txt

Run the FastAPI server:

    uvicorn backend.main:app --reload

The API will be available at:

    http://127.0.0.1:8000

Swagger documentation:

    http://127.0.0.1:8000/docs

### Frontend

Open another terminal:

    cd frontend
    npm install
    npm run dev

The frontend will then be available through the Vite development
server.

---

# 18. CLI Usage

The redaction engine can also be used directly without the web
application:

    python -m src.redactor \
        --input "input.docx" \
        --output "output.docx"

Example:

    python -m src.redactor \
        --input "Red Herring Prospectus.docx" \
        --output "output/redacted.docx"

---

# 19. Running Tests

From the project root:

    python -m pytest -q

Expected current result:

    70 passed

To run only the strict accuracy verification:

    python -m pytest tests/test_redactor.py \
        -k test_strict_accuracy_verification

---

# 20. Technology Stack

### Backend

- Python
- FastAPI
- Uvicorn
- python-docx
- spaCy
- Pytest

### Frontend

- React
- Vite
- JavaScript
- CSS

### Document Processing

- DOCX parsing and generation
- Regex-based structured detection
- NLP / Named Entity Recognition
- Context-aware entity detection
- Deterministic replacement mapping

---

# 21. Future Improvements

Possible future improvements include:

- OCR-based detection for scanned documents
- Support for additional international PII formats
- Larger manually annotated evaluation datasets
- Background cleanup and stronger temporary-file isolation
- Authentication and access control for production deployments
- More advanced document-format preservation
- Additional export formats such as PDF