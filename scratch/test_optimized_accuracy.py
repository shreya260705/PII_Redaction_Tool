import sys
sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")

from scratch.profile_optimized import (
    OptimizedEmailDetector,
    OptimizedPhoneDetector,
    OptimizedIPAddressDetector,
    OptimizedSSNDetector,
    OptimizedCreditCardDetector,
    OptimizedDateOfBirthDetector,
    OptimizedNLPDetector
)
from src.document_reader import DocumentReader
from src.detectors.base import resolve_overlaps
from src.redactor import RedactionMapper, redact_block

def main():
    input_path = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\PII_Strict_Accuracy_Test.docx"
    extracted = DocumentReader.read(input_path)
    
    email_det = OptimizedEmailDetector()
    phone_det = OptimizedPhoneDetector()
    ip_det = OptimizedIPAddressDetector()
    ssn_det = OptimizedSSNDetector()
    cc_det = OptimizedCreditCardDetector()
    dob_det = OptimizedDateOfBirthDetector()
    nlp_det = OptimizedNLPDetector()
    
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
            if isinstance(detector, OptimizedNLPDetector) and is_heading_or_title:
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
        print("SUCCESS: Optimized implementation passed strict accuracy verification!")

if __name__ == "__main__":
    main()
