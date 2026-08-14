import sys
sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")

import time
from scratch.test_clean_prechecks import (
    SafeEmailDetector,
    SafePhoneDetector,
    SafeIPAddressDetector,
    SafeSSNDetector,
    SafeCreditCardDetector,
    SafeDateOfBirthDetector,
    SafeNLPDetector
)
from src.document_reader import DocumentReader
from src.detectors.base import resolve_overlaps
from src.redactor import RedactionMapper, redact_block

def main():
    large_doc = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\Red Herring Prospectus.docx"
    
    print("Reading document...")
    start_time = time.time()
    extracted = DocumentReader.read(large_doc)
    print(f"Read done in {time.time() - start_time:.2f} seconds.")
    
    print("Initializing safe detectors...")
    start_time = time.time()
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
    print(f"Initialized in {time.time() - start_time:.2f} seconds.")
    
    print("Running safe pre-check redaction loop...")
    start_time = time.time()
    
    total_replacements = 0
    processed_elements = set()
    
    for i, block in enumerate(extracted.blocks):
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
        
        if i > 0 and i % 500 == 0:
            print(f"Processed {i} blocks... replacements so far: {total_replacements}")
            
    print(f"Redaction loop done in {time.time() - start_time:.2f} seconds!")
    print(f"Total replacements: {total_replacements}")

if __name__ == "__main__":
    main()
