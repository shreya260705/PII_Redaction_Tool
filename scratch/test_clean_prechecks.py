import sys
sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")

import re
from typing import List
from src.models import PIIMatch
from src.detectors.base import BaseDetector, resolve_overlaps
from src.detectors.structured import (
    EmailDetector,
    PhoneDetector,
    IPAddressDetector,
    SSNDetector,
    CreditCardDetector,
    DateOfBirthDetector,
)
from src.detectors.nlp import NLPDetector
from src.document_reader import DocumentReader
from src.redactor import RedactionMapper, redact_block

# Let's subclass and add the safe pre-checks preserving the original logic
class SafeEmailDetector(EmailDetector):
    def detect(self, text: str) -> List[PIIMatch]:
        if "@" not in text:
            return []
        return super().detect(text)

class SafePhoneDetector(PhoneDetector):
    def detect(self, text: str) -> List[PIIMatch]:
        digit_count = 0
        for c in text:
            if c.isdigit():
                digit_count += 1
                if digit_count >= 8:
                    break
        if digit_count < 8:
            return []
        return super().detect(text)

class SafeIPAddressDetector(IPAddressDetector):
    def detect(self, text: str) -> List[PIIMatch]:
        if "." not in text:
            return []
        return super().detect(text)

class SafeSSNDetector(SSNDetector):
    def detect(self, text: str) -> List[PIIMatch]:
        digit_count = 0
        for c in text:
            if c.isdigit():
                digit_count += 1
                if digit_count >= 9:
                    break
        if digit_count < 9:
            return []
        return super().detect(text)

class SafeCreditCardDetector(CreditCardDetector):
    def detect(self, text: str) -> List[PIIMatch]:
        digit_count = 0
        for c in text:
            if c.isdigit():
                digit_count += 1
                if digit_count >= 13:
                    break
        if digit_count < 13:
            return []
        return super().detect(text)

class SafeDateOfBirthDetector(DateOfBirthDetector):
    def detect(self, text: str) -> List[PIIMatch]:
        # Reset context if we see another section header
        text_clean = text.strip().upper()
        other_headers = {"PERSON", "EMAIL", "PHONE", "IP_ADDRESS", "SSN", "CREDIT_CARD", "COMPANY", "ADDRESS"}
        if text_clean in other_headers:
            self.dob_context_active = False

        # Check for context keyword with underscores replaced
        text_for_context = text.replace('_', ' ')
        if self.DOB_CONTEXT_REGEX.search(text_for_context):
            self.dob_context_active = True
            self.blocks_since_dob_context = 0
        else:
            if self.dob_context_active:
                self.blocks_since_dob_context += 1
                if self.blocks_since_dob_context > 10:
                    self.dob_context_active = False

        has_digits = any(c.isdigit() for c in text)
        if not has_digits and not self.dob_context_active:
            return []
            
        # Call the original DateOfBirthDetector parent logic, but bypass its context update since we did it above
        matches = []
        scans = [
            (self.D1_REGEX, self._parse_d1),
            (self.D2_REGEX, self._parse_d2),
            (self.D3_REGEX, self._parse_d3),
        ]

        for regex, parse_fn in scans:
            for m in regex.finditer(text):
                date_str = m.group()
                parsed = parse_fn(date_str)
                if not parsed:
                    continue

                day, month, year = parsed
                from src.detectors.validators import parse_and_validate_date
                if not parse_and_validate_date(day, month, year):
                    continue

                if self._has_dob_context_nearby(text, m.start(), m.end()) or (self.dob_context_active and len(text.strip()) <= 20):
                    matches.append(
                        PIIMatch(
                            pii_type="DATE_OF_BIRTH",
                            text=date_str,
                            start=m.start(),
                            end=m.end(),
                            confidence=0.98,
                            detector="dob_context_proximity"
                        )
                    )
        return matches

class SafeNLPDetector(NLPDetector):
    def detect(self, text: str) -> List[PIIMatch]:
        if not text or not any(c.isupper() for c in text):
            return []
        return super().detect(text)

def main():
    input_path = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\PII_Strict_Accuracy_Test.docx"
    extracted = DocumentReader.read(input_path)
    
    email_det = SafeEmailDetector()
    phone_det = SafePhoneDetector()
    ip_det = SafeIPAddressDetector()
    ssn_det = SafeSSNDetector()
    cc_det = SafeCreditCardDetector()
    dob_det = SafeDateOfBirthDetector()
    nlp_det = SafeNLPDetector()
    
    detectors = [email_det, phone_det, ip_det, ssn_det, cc_det, dob_det, nlp_det]
    validators = [
        ("EMAIL", email_det),
        ("PHONE", phone_det),
        ("IP_ADDRESS", ip_det),
        ("SSN", ssn_det),
        ("CREDIT_CARD", cc_det),
        ("DATE_OF_BIRTH", dob_det),
        ("PERSON", nlp_det),
        ("COMPANY", nlp_det),
        ("ADDRESS", nlp_det),
    ]
    mapper = RedactionMapper(validators=validators)
    
    total_replacements = 0
    replacements_by_type = {}
    processed_elements = set()
    
    for block in extracted.blocks:
        if not block.text or not block.text.strip():
            continue
            
        if block.element is not None:
            element = getattr(block.element, "_element", block.element)
            element_id = id(element)
            if element_id in processed_elements:
                continue
            processed_elements.add(element_id)
            
        is_heading_or_title = False
        if block.block_type in ("paragraph", "header_paragraph", "footer_paragraph") and block.element is not None:
            try:
                style_name = block.element.style.name
                if style_name in ("Title", "Heading 1", "Heading 2", "Heading 3", "Heading 4", "Heading 5", "Heading 6", "Heading 7", "Heading 8", "Heading 9"):
                    is_heading_or_title = True
            except Exception:
                pass
                
        block_matches = []
        for detector in detectors:
            if isinstance(detector, SafeNLPDetector) and is_heading_or_title:
                continue
            try:
                matches = detector.detect(block.text)
                block_matches.extend(matches)
            except Exception as e:
                pass
                
        resolved = resolve_overlaps(block_matches)
        applied = redact_block(block, resolved, mapper)
        total_replacements += len(applied)
        for match in applied:
            replacements_by_type[match.pii_type] = replacements_by_type.get(match.pii_type, 0) + 1
            
    expected_counts = {
        "PERSON": 7,
        "EMAIL": 8,
        "PHONE": 6,
        "IP_ADDRESS": 6,
        "SSN": 6,
        "CREDIT_CARD": 6,
        "DATE_OF_BIRTH": 6,
        "COMPANY": 6,
        "ADDRESS": 6
    }
    
    print("--- DETECTIONS AND REPLACEMENTS ---")
    all_matched = True
    for k, expected in expected_counts.items():
        actual = replacements_by_type.get(k, 0)
        print(f"{k:<15} {actual}/{expected}")
        if actual != expected:
            all_matched = False
            
    print(f"Total Replacements: {total_replacements}/57")
    if total_replacements != 57 or not all_matched:
        print("FAILED: Counts do not match expected strict accuracy test counts!")
    else:
        print("SUCCESS: Safe pre-checks passed strict accuracy verification!")

if __name__ == "__main__":
    main()
