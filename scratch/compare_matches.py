import sys
sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")

from src.redactor import RedactionEngine
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

def main():
    input_path = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\PII_Strict_Accuracy_Test.docx"
    extracted = DocumentReader.read(input_path)
    
    # 1. Original Engine
    orig_engine = RedactionEngine()
    
    # 2. Optimized Engine
    email_det = OptimizedEmailDetector()
    phone_det = OptimizedPhoneDetector()
    ip_det = OptimizedIPAddressDetector()
    ssn_det = OptimizedSSNDetector()
    cc_det = OptimizedCreditCardDetector()
    dob_det = OptimizedDateOfBirthDetector()
    nlp_det = OptimizedNLPDetector()
    
    opt_detectors = [email_det, phone_det, ip_det, ssn_det, cc_det, dob_det, nlp_det]
    
    print("=== Original Detections ===")
    orig_matches = []
    for block in extracted.blocks:
        if not block.text or not block.text.strip():
            continue
        for det in orig_engine.detectors:
            orig_matches.extend(det.detect(block.text))
            
    for m in orig_matches:
        if m.pii_type in ("PERSON", "DATE_OF_BIRTH", "ADDRESS"):
            print(f"Original: Type={m.pii_type}, Text={repr(m.text)}")
            
    print("\n=== Optimized Detections ===")
    opt_matches = []
    for block in extracted.blocks:
        if not block.text or not block.text.strip():
            continue
        for det in opt_detectors:
            opt_matches.extend(det.detect(block.text))
            
    for m in opt_matches:
        if m.pii_type in ("PERSON", "DATE_OF_BIRTH", "ADDRESS"):
            print(f"Optimized: Type={m.pii_type}, Text={repr(m.text)}")

if __name__ == "__main__":
    main()
