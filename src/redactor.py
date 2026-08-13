import os
import re
import sys
import hashlib
import random
import argparse
import logging
from typing import List, Dict, Any, Optional

import docx
from docx.text.run import Run

from src.document_reader import DocumentReader
from src.detectors.base import resolve_overlaps
from src.detectors.structured import (
    EmailDetector,
    PhoneDetector,
    IPAddressDetector,
    SSNDetector,
    CreditCardDetector,
    DateOfBirthDetector,
)
from src.detectors.nlp import NLPDetector
from src.models import PIIMatch, DocumentBlock

# ---------------------------------------------------------
# Windows UTF-8 Console Safety
# ---------------------------------------------------------
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------
# Synthetic Pool Constants
# ---------------------------------------------------------
FIRST_NAMES = [
    "Rahul", "Amit", "Sanjay", "Vijay", "Anil",
    "John", "Jane", "Robert", "Mary", "William",
    "David", "Aditya", "Rohan", "Arjun", "Karan",
    "Priya", "Neha", "Anjali", "Ritu", "Pooja",
    "Thomas", "Daniel", "Matthew", "Sarah", "Emily",
    "Rajesh", "Vikram", "Sunil", "Deepak"
]

LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Mehta", "Joshi",
    "Patel", "Shah", "Singh", "Kumar", "Smith",
    "Johnson", "Williams", "Brown", "Jones", "Miller",
    "Davis", "Rao", "Nair", "Iyer", "Kulkarni",
    "Deshmukh", "Das", "Sen", "Banerjee",
    "Chatterjee", "Mishra", "Pandey"
]

COMPANY_FIRST = [
    "Acme", "Apex", "Global", "Delta", "Summit",
    "Vanguard", "Horizon", "Quantum", "Nexus",
    "Vertex", "Infinity", "Pinnacle", "Synergy",
    "Meridian", "Alpha", "Omni", "Nova",
    "Genesis", "Matrix", "Echo"
]

COMPANY_SECOND = [
    "Industries", "Technologies", "Solutions",
    "Holdings", "Enterprises", "Systems", "Group",
    "Dynamics", "Partners", "Capital", "Services",
    "International", "Labs", "Logistics", "Ventures"
]

ADDR_STREETS = [
    "Plot No. 45",
    "Flat 302, Green Layout",
    "Building 4B, Tech Park",
    "5th Floor, Trade Center",
    "Survey No. 112"
]

ADDR_ROADS = [
    "MG Road",
    "Baner Road",
    "Senapati Bapat Road",
    "Link Road",
    "Outer Ring Road",
    "JVLR"
]

ADDR_AREAS = [
    "Koramangala",
    "Baner",
    "Andheri West",
    "Whitefield",
    "Hinjawadi",
    "Bandra"
]

ADDR_CITIES = [
    "Pune",
    "Mumbai",
    "Bangalore",
    "Delhi",
    "Hyderabad",
    "Chennai"
]

ADDR_STATES = [
    "Maharashtra",
    "Karnataka",
    "Delhi",
    "Tamil Nadu",
    "Telangana"
]

# ---------------------------------------------------------
# Redaction Mapper
# ---------------------------------------------------------
class RedactionMapper:
    """
    Generates deterministic synthetic replacements using SHA256.
    Ensures that identical text and PII type always generate
    the identical replacement value.
    """

    def __init__(self, validators: Optional[List[tuple]] = None) -> None:
        self.mappings: Dict[str, str] = {}
        self.validators = validators or []

    def get_replacement(self, original_text: str, pii_type: str) -> str:
        normalized = original_text.strip().lower()
        key = f"{pii_type}:{normalized}"

        if key in self.mappings:
            return self.mappings[key]

        # Deterministic mapping using SHA-256
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        base_seed = int.from_bytes(digest[:8], byteorder="big")

        for attempt in range(100):
            attempt_seed = (base_seed + attempt) % (2 ** 64)
            rnd = random.Random(attempt_seed)
            replacement = self._generate_synthetic(original_text, pii_type, rnd)
            if self._is_safe_replacement(replacement, pii_type):
                self.mappings[key] = replacement
                return replacement

        # Fallback if no safe candidate is generated
        replacement = self._fallback(original_text, pii_type, base_seed)
        self.mappings[key] = replacement
        return replacement

    def _is_safe_replacement(self, replacement: str, target_type: str) -> bool:
        """
        Ensures a synthetic value does not trigger detectors for other types.
        """
        for detector_type, detector in self.validators:
            if detector_type == target_type:
                continue
            try:
                matches = detector.detect(replacement)
                # Only check if it matched the validator's own type
                type_matches = [m for m in matches if m.pii_type == detector_type]
                if type_matches:
                    return False
            except Exception:
                continue
        return True

    def _generate_synthetic(self, original: str, pii_type: str, rnd: random.Random) -> str:
        if pii_type == "PERSON":
            words = original.split()
            if len(words) <= 1:
                return rnd.choice(FIRST_NAMES)
            if len(words) == 2:
                return f"{rnd.choice(FIRST_NAMES)} {rnd.choice(LAST_NAMES)}"
            middle = rnd.choice(FIRST_NAMES)
            return f"{rnd.choice(FIRST_NAMES)} {middle[0]}. {rnd.choice(LAST_NAMES)}"

        elif pii_type == "EMAIL":
            first = rnd.choice(FIRST_NAMES).lower()
            last = rnd.choice(LAST_NAMES).lower()
            return f"{first}.{last}@example.com"

        elif pii_type == "PHONE":
            # Deterministic synthetic Indian mobile prefix
            digits = "".join(str(rnd.randint(0, 9)) for _ in range(7))
            return f"+91 555{digits}"

        elif pii_type == "IP_ADDRESS":
            return f"10.{rnd.randint(0, 255)}.{rnd.randint(0, 255)}.{rnd.randint(1, 254)}"

        elif pii_type == "SSN":
            first = rnd.randint(100, 899)
            while first == 666:
                first = rnd.randint(100, 899)
            second = rnd.randint(10, 99)
            third = rnd.randint(1000, 9999)
            return f"{first:03d}-{second:02d}-{third:04d}"

        elif pii_type == "CREDIT_CARD":
            separator = ""
            if "-" in original:
                separator = "-"
            elif " " in original:
                separator = " "

            # Generate 15 digits starting with 4111
            digits = [4, 1, 1, 1] + [rnd.randint(0, 9) for _ in range(11)]
            # Luhn calculation
            total = 0
            for i, d in enumerate(digits):
                if i % 2 == 0:
                    val = d * 2
                    if val > 9:
                        val -= 9
                    total += val
                else:
                    total += d
            check_digit = (10 - (total % 10)) % 10
            digits.append(check_digit)

            digits_str = "".join(str(d) for d in digits)
            if separator == "-":
                return f"{digits_str[0:4]}-{digits_str[4:8]}-{digits_str[8:12]}-{digits_str[12:16]}"
            elif separator == " ":
                return f"{digits_str[0:4]} {digits_str[4:8]} {digits_str[8:12]} {digits_str[12:16]}"
            else:
                return digits_str

        elif pii_type == "DATE_OF_BIRTH":
            months = [
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December"
            ]
            original_lower = original.lower()
            has_month_name = any(m[:3].lower() in original_lower for m in months)

            day = rnd.randint(1, 28)
            month_idx = rnd.randint(1, 12)
            year = rnd.randint(1970, 2005)

            if has_month_name:
                month_name = months[month_idx - 1]
                words = original.split()
                # Check year length
                year_len = 4
                if words and len(words[-1].strip(",").strip()) == 2:
                    year_len = 2

                year_formatted = year if year_len == 4 else year % 100
                if original.strip() and original.strip()[0].isdigit():
                    return f"{day:02d} {month_name} {year_formatted:02d}" if year_len == 2 else f"{day:02d} {month_name} {year_formatted}"
                else:
                    return f"{month_name} {day:02d}, {year_formatted:02d}" if year_len == 2 else f"{month_name} {day:02d}, {year_formatted}"

            # Numeric date separator formatting
            separator = "/"
            if "-" in original:
                separator = "-"
            elif "." in original:
                separator = "."

            parts = original.split(separator)
            year_len = 4
            if len(parts) == 3:
                if len(parts[0].strip()) == 4:
                    year_len = 4
                    return f"{year}{separator}{month_idx:02d}{separator}{day:02d}"
                elif len(parts[2].strip()) == 4:
                    year_len = 4
                elif len(parts[0].strip()) == 2:
                    year_len = 2
                    if len(parts[2].strip()) == 2:
                        year_len = 2

            year_str = f"{year}" if year_len == 4 else f"{year % 100:02d}"
            if len(parts) == 3 and len(parts[0].strip()) == 4:
                return f"{year_str}{separator}{month_idx:02d}{separator}{day:02d}"
            return f"{day:02d}{separator}{month_idx:02d}{separator}{year_str}"

        elif pii_type == "COMPANY":
            suffixes = [
                "private limited", "private ltd", "pvt limited", "pvt ltd",
                "limited", "ltd", "llp", "corporation", "corp", "inc"
            ]
            original_lower = original.lower()
            matched_suffix = None
            for suffix in suffixes:
                if original_lower.endswith(suffix):
                    matched_suffix = original[-len(suffix):]
                    break

            first = rnd.choice(COMPANY_FIRST)
            second = rnd.choice(COMPANY_SECOND)
            if matched_suffix:
                return f"{first} {second} {matched_suffix}"
            return f"{first} {second}"

        elif pii_type == "ADDRESS":
            street = rnd.choice(ADDR_STREETS)
            road = rnd.choice(ADDR_ROADS)
            area = rnd.choice(ADDR_AREAS)
            city = rnd.choice(ADDR_CITIES)
            state = rnd.choice(ADDR_STATES)
            pin = f"{rnd.randint(100, 999)} {rnd.randint(100, 999)}"
            return f"{street}, {road}, {area}, {city}, {state} - {pin}"

        return "***"

    def _fallback(self, original: str, pii_type: str, seed: int) -> str:
        rnd = random.Random(seed ^ 0xABCDEF)
        if pii_type == "EMAIL":
            return f"dummy{rnd.randint(1000, 9999)}@example.com"
        elif pii_type == "IP_ADDRESS":
            return "10.20.30.40"
        elif pii_type == "PERSON":
            return "John Smith"
        elif pii_type == "COMPANY":
            return "Acme Technologies"
        elif pii_type == "ADDRESS":
            return "Example Street, Example City"
        elif pii_type == "DATE_OF_BIRTH":
            return "01/01/1990"
        elif pii_type == "PHONE":
            return "+91 5550000000"
        elif pii_type == "SSN":
            return "000-00-0000"
        elif pii_type == "CREDIT_CARD":
            return "4111-2222-3333-4444"
        return "***"

# ---------------------------------------------------------
# Run Helpers
# ---------------------------------------------------------
def get_paragraph_runs(paragraph) -> List[Run]:
    """
    Finds all Runs nested inside paragraphs, including hyperlinks
    or other structural Word elements, and wraps them properly.
    """
    try:
        run_elements = paragraph._element.xpath(".//w:r")
        if run_elements:
            return [Run(el, paragraph) for el in run_elements]
    except Exception:
        pass
    return paragraph.runs

def build_run_segments(block: DocumentBlock) -> List[Dict[str, Any]]:
    """
    Builds run segments based on the block's original snapshot text.
    """
    segments = []
    current_idx = 0

    if block.block_type in ("paragraph", "header_paragraph", "footer_paragraph"):
        paragraph = block.element
        runs = get_paragraph_runs(paragraph)
        if not runs:
            if paragraph.text:
                segments.append({
                    "run": paragraph,
                    "is_paragraph_fallback": True,
                    "is_newline": False,
                    "start": 0,
                    "end": len(paragraph.text),
                    "text": paragraph.text
                })
            return segments

        for run in runs:
            run_text = run.text or ""
            run_len = len(run_text)
            segments.append({
                "run": run,
                "is_paragraph_fallback": False,
                "is_newline": False,
                "start": current_idx,
                "end": current_idx + run_len,
                "text": run_text
            })
            current_idx += run_len

    elif block.block_type in ("table_cell", "header_table_cell", "footer_table_cell"):
        cell = block.element
        for paragraph_index, paragraph in enumerate(cell.paragraphs):
            if paragraph_index > 0:
                segments.append({
                    "run": None,
                    "is_paragraph_fallback": False,
                    "is_newline": True,
                    "start": current_idx,
                    "end": current_idx + 1,
                    "text": "\n"
                })
                current_idx += 1

            runs = get_paragraph_runs(paragraph)
            paragraph_start = current_idx

            if not runs:
                if paragraph.text:
                    segments.append({
                        "run": paragraph,
                        "is_paragraph_fallback": True,
                        "is_newline": False,
                        "start": paragraph_start,
                        "end": paragraph_start + len(paragraph.text),
                        "text": paragraph.text
                    })
                    current_idx += len(paragraph.text)
            else:
                for run in runs:
                    run_text = run.text or ""
                    run_len = len(run_text)
                    segments.append({
                        "run": run,
                        "is_paragraph_fallback": False,
                        "is_newline": False,
                        "start": current_idx,
                        "end": current_idx + run_len,
                        "text": run_text
                    })
                    current_idx += run_len

    return segments

# ---------------------------------------------------------
# Block Redaction Logic
# ---------------------------------------------------------
def redact_block(
    block: DocumentBlock,
    matches: List[PIIMatch],
    mapper: RedactionMapper
) -> List[PIIMatch]:
    """
    Applies the resolved matches to the block's run structure right-to-left.
    Returns the list of matches that were actually successfully applied.
    """
    applied_matches = []
    if not matches:
        return applied_matches

    run_segments = build_run_segments(block)

    # Direct fallback if we have no run structure but can set text directly
    if not run_segments:
        if hasattr(block.element, "text"):
            text = block.element.text or ""
            sorted_matches = sorted(matches, key=lambda m: m.start, reverse=True)
            for match in sorted_matches:
                replacement = mapper.get_replacement(match.text, match.pii_type)
                text = text[:match.start] + replacement + text[match.end:]
                applied_matches.append(match)
            block.element.text = text
            return applied_matches
        return applied_matches

    # Sort matches from right-to-left
    sorted_matches = sorted(matches, key=lambda m: m.start, reverse=True)

    for match in sorted_matches:
        replacement = mapper.get_replacement(match.text, match.pii_type)

        overlapping = [
            seg
            for seg in run_segments
            if max(seg["start"], match.start) < min(seg["end"], match.end)
        ]

        if not overlapping:
            continue

        first_editable = None
        for seg in overlapping:
            if not seg["is_newline"]:
                first_editable = seg
                break

        if first_editable is None:
            continue

        for seg in overlapping:
            if seg["is_newline"]:
                continue

            local_start = max(seg["start"], match.start) - seg["start"]
            local_end = min(seg["end"], match.end) - seg["start"]
            original_segment_text = seg["text"]

            if seg is first_editable:
                new_text = (
                    original_segment_text[:local_start]
                    + replacement
                    + original_segment_text[local_end:]
                )
            else:
                new_text = (
                    original_segment_text[:local_start]
                    + original_segment_text[local_end:]
                )

            seg["run"].text = new_text
            seg["text"] = new_text

        applied_matches.append(match)

    return applied_matches

# ---------------------------------------------------------
# Redaction Pipeline Engine
# ---------------------------------------------------------
class RedactionEngine:
    """
    Main PII Redaction Pipeline. Handles extraction, single-pass
    detection, overlap resolution, run-aware modification,
    duplicate element protection, and input file integrity checking.
    """

    def __init__(self) -> None:
        self.detectors = [
            EmailDetector(),
            PhoneDetector(),
            IPAddressDetector(),
            SSNDetector(),
            CreditCardDetector(),
            DateOfBirthDetector(),
            NLPDetector(),
        ]

        # Validators used in RedactionMapper to ensure safety
        validators = [
            ("EMAIL", EmailDetector()),
            ("PHONE", PhoneDetector()),
            ("IP_ADDRESS", IPAddressDetector()),
            ("SSN", SSNDetector()),
            ("CREDIT_CARD", CreditCardDetector()),
            ("DATE_OF_BIRTH", DateOfBirthDetector()),
            ("PERSON", NLPDetector()),
            ("COMPANY", NLPDetector()),
            ("ADDRESS", NLPDetector()),
        ]
        self.mapper = RedactionMapper(validators=validators)

    def redact(self, input_path: str, output_path: str) -> Dict[str, Any]:
        # Validate that we do not overwrite the input
        if os.path.abspath(input_path) == os.path.abspath(output_path):
            raise ValueError("Input and Output paths must be different. Cannot overwrite input file.")

        logger.info(f"Checking input file integrity: {input_path}")
        input_sha_before = self.sha256_file(input_path)

        # Load Document via DocumentReader exactly once
        extracted = DocumentReader.read(input_path)
        root_doc = extracted.doc
        if root_doc is None:
            raise RuntimeError("Document reference was not returned in ExtractedDocument.")

        total_replacements = 0
        replacements_by_type: Dict[str, int] = {}
        processed_elements = set()

        # Iterate through block structures
        for block in extracted.blocks:
            # Skip empty or whitespace-only blocks
            if not block.text or not block.text.strip():
                continue

            # Skip duplicate XML element nodes
            if block.element is not None:
                element = getattr(block.element, "_element", block.element)
                element_id = id(element)
                if element_id in processed_elements:
                    continue
                processed_elements.add(element_id)

            # Determine if this block is a document title or heading style
            is_heading_or_title = False
            if block.block_type in ("paragraph", "header_paragraph", "footer_paragraph") and block.element is not None:
                try:
                    style_name = block.element.style.name
                    if style_name in ("Title", "Heading 1", "Heading 2", "Heading 3", "Heading 4", "Heading 5", "Heading 6", "Heading 7", "Heading 8", "Heading 9"):
                        is_heading_or_title = True
                except Exception:
                    pass

            block_matches: List[PIIMatch] = []
            # Single-pass detection on the original block text
            for detector in self.detectors:
                # Skip running NLPDetector on headings/titles to prevent false positive PERSON matches
                if isinstance(detector, NLPDetector) and is_heading_or_title:
                    continue
                try:
                    matches = detector.detect(block.text)
                    block_matches.extend(matches)
                except Exception as exc:
                    logger.error(
                        f"Detector {detector.__class__.__name__} failed on block {block.block_id}: {exc}"
                    )

            # Resolve overlaps on original detections
            resolved = resolve_overlaps(block_matches)

            # Apply right-to-left edits to run structures
            applied = redact_block(block, resolved, self.mapper)

            total_replacements += len(applied)
            for match in applied:
                replacements_by_type[match.pii_type] = (
                    replacements_by_type.get(match.pii_type, 0) + 1
                )

        # Confirm count consistency before saving
        assert sum(replacements_by_type.values()) == total_replacements, "Consistency error: Replacements counts mismatch!"

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        # Save the in-memory modified document to separate output path
        root_doc.save(output_path)
        logger.info(f"Redacted document successfully saved to: {output_path}")

        # Assert that the input file remains completely unchanged
        input_sha_after = self.sha256_file(input_path)
        assert input_sha_before == input_sha_after, "Input file was modified during processing!"

        return {
            "output_path": output_path,
            "total_replacements": total_replacements,
            "replacements_by_type": replacements_by_type,
            "unique_mappings_count": len(self.mapper.mappings),
            "input_sha256": input_sha_after
        }

    @staticmethod
    def sha256_file(filepath: str) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

# ---------------------------------------------------------
# Command Line Interface Entry point
# ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Redact PII from a DOCX document.")
    parser.add_argument("--input", required=True, help="Path to the original DOCX file.")
    parser.add_argument("--output", required=True, help="Path to save the redacted DOCX file.")
    args = parser.parse_args()

    engine = RedactionEngine()
    try:
        results = engine.redact(args.input, args.output)
        print("Redaction complete.")
        print(f"Output File: {results['output_path']}")
        print(f"Total Replacements Applied: {results['total_replacements']}")
        print("Replacements by PII Type:")
        for pii_type, count in results["replacements_by_type"].items():
            print(f"  {pii_type}: {count}")
        print(f"Unique Mappings Created: {results['unique_mappings_count']}")
    except Exception as exc:
        print(f"Error executing redaction: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()