# PII Redaction Tool - Detection Foundation

This repository contains the foundation for a high-precision PII Redaction Tool built for a corporate DOCX financial prospectus document.

---

## Project Architecture

The pipeline consists of the following modular layers:

1.  **Document Extraction Layer (`src/document_reader.py`)**:
    *   Reads paragraphs, tables (including rows and cells), headers, and footers from a DOCX file without modifying the source.
    *   Iterates XML children in physical order to preserve document layout order.
    *   Stores results in typed dataclasses (`DocumentBlock` and `BlockLocation`) preserving stable, absolute structural indices.
2.  **Structured PII Detectors (`src/detectors/structured.py` & `src/detectors/validators.py`)**:
    *   **EMAIL**: Standard regular expression.
    *   **PHONE**: Indian mobile and landline patterns requiring structural prefixes (`+91`/`0`) or nearby sentence-bounded keywords.
    *   **IP_ADDRESS**: IPv4 octet bounds ($0 \le octet \le 255$) excluding dotted section titles.
    *   **SSN**: Hyphenated format; unhyphenated format matches ONLY if a strong context keyword is in the same sentence.
    *   **CREDIT_CARD**: 13-19 digit candidates validated by the Luhn algorithm.
    *   **DATE_OF_BIRTH**: Matches date layouts ONLY if a birth keyword (`dob`, `born`, `birth`) is found within a 50-character distance in the same sentence.
3.  **NLP PII Detectors (`src/detectors/nlp.py`)**:
    *   Utilizes a single-loaded **spaCy** (`en_core_web_sm`) model and **Microsoft Presidio Analyzer** engine.
    *   **PERSON**: Extracts PERSON entities, boosted by designation keywords (e.g. `Chairman`, `Managing Director`, `Company Secretary`) within the same sentence.
    *   **COMPANY**: Filters spaCy `ORG` entities using a custom policy.
    *   **ADDRESS**: Merges spaCy location entities, structural keywords, and 6-digit Indian PIN codes, filtering out standalone references.
4.  **Deterministic Overlap Resolver (`src/detectors/base.py`)**:
    *   Resolves overlapping entities using a greedy interval scheduler. Prioritizes matches by: (1) higher confidence, (2) explicit semantic type priority (`CREDIT_CARD` > `SSN` > `EMAIL` > `COMPANY` > `PERSON` > `ADDRESS` > `PHONE` > `IP_ADDRESS` > `DATE_OF_BIRTH`), (3) longer span length, and (4) earlier start offset.

---

## Explicit Classification Policies

### 1. COMPANY Boundary Policy
In the context of a public corporate prospectus:
*   **Redacted as COMPANY**: Commercial entities, sponsor/commercial banks, lead managers, underwriters, law firms, and auditing partnerships. These represent proprietary third-party partners.
*   **Not Redacted (Excluded)**: Public exchanges (BSE, NSE), government ministries, departments, and statutory regulators (SEBI, Registrar of Companies). These are public entities whose presence is legally mandated and non-proprietary.

### 2. ADDRESS Strategy
*   An address is matched ONLY if it contains multiple supporting structural elements (e.g. `Flat No.`, `Plot No.`, `Building`, `Road`) and/or GPE entities, and optionally a 6-digit PIN code.
*   Standalone geographic words (e.g. `"India"`, `"Pune"`, `"Maharashtra"` alone) or standalone PIN codes are **never** classified as `ADDRESS`.

---

## Installation & Setup

1.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Download the spaCy NLP Model**:
    ```bash
    python -m spacy download en_core_web_sm
    ```
3.  **Run the Inspection CLI**:
    ```bash
    python -m src.inspect_pii
    ```
4.  **Run unit tests**:
    ```bash
    python -m pytest
    ```
