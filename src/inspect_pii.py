import logging
import re
import sys
from collections import Counter
from typing import List

from src.document_reader import DocumentReader
from src.models import PIIMatch
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

# Configure simple logging
logging.basicConfig(level=logging.WARNING)


def mask_pii(text: str, pii_type: str) -> str:
    """Safely masks sensitive PII values for CLI display without printing them to logs."""
    if pii_type == "EMAIL":
        if "@" in text:
            parts = text.split("@", 1)
            user, domain = parts[0], parts[1]
            if len(user) <= 2:
                return f"*@{domain}"
            return f"{user[0]}***{user[-1]}@{domain}"
        return "***"
        
    elif pii_type == "PHONE":
        if len(text) <= 6:
            return "***"
        return f"{text[:3]}***{text[-3:]}"
        
    elif pii_type == "IP_ADDRESS":
        parts = text.split('.')
        if len(parts) == 4:
            return f"{parts[0]}.{parts[1]}.***.***"
        return "***"
        
    elif pii_type == "SSN":
        if "-" in text:
            parts = text.split("-")
            return f"***-**-{parts[-1]}"
        return "***"
        
    elif pii_type == "CREDIT_CARD":
        clean_text = text.replace("-", "").replace(" ", "")
        if len(clean_text) >= 4:
            return f"****-****-****-{clean_text[-4:]}"
        return "****"
        
    elif pii_type == "DATE_OF_BIRTH":
        if len(text) >= 4:
            return f"**/**/{text[-4:]}"
        return "**/**/****"

    elif pii_type == "PERSON" or pii_type == "COMPANY":
        # Mask middle characters of each name/word token
        parts = text.split()
        masked_parts = []
        for p in parts:
            # Strip punctuation attached to word if any
            clean_word = re.sub(r'[^\w]', '', p)
            if not clean_word:
                masked_parts.append(p)
                continue
            if len(clean_word) <= 2:
                masked_p = clean_word[0] + "*"
            else:
                masked_p = clean_word[0] + "***" + clean_word[-1]
            # preserve punctuation around it
            masked_parts.append(p.replace(clean_word, masked_p))
        return " ".join(masked_parts)

    elif pii_type == "ADDRESS":
        # Keep first 5 and last 5 characters
        if len(text) <= 10:
            return "***"
        return f"{text[:5]}***{text[-5:]}"
        
    return "***"


def main():
    doc_path = "Red Herring Prospectus.docx"
    print(f"Reading document: {doc_path} ...")
    
    try:
        extracted = DocumentReader.read(doc_path)
    except FileNotFoundError:
        print(f"Error: Could not find '{doc_path}' in the workspace root.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading document: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Extraction successful. Total text blocks: {len(extracted.blocks)}")
    
    # Initialize all detectors (Structured and NLP)
    detectors = [
        EmailDetector(),
        PhoneDetector(),
        IPAddressDetector(),
        SSNDetector(),
        CreditCardDetector(),
        DateOfBirthDetector(),
        NLPDetector(),
    ]

    all_matches: List[PIIMatch] = []
    
    # Run detectors block-by-block
    for block in extracted.blocks:
        block_matches: List[PIIMatch] = []
        for det in detectors:
            try:
                matches = det.detect(block.text)
                block_matches.extend(matches)
            except Exception as e:
                # Log error but do not swallow silently or crash pipeline
                print(f"Error running detector {det.__class__.__name__} on block {block.block_id}: {e}", file=sys.stderr)
        
        # Resolve overlaps inside this block
        resolved_block_matches = resolve_overlaps(block_matches)
        all_matches.extend(resolved_block_matches)

    # Aggregate counts by PII type
    counts = Counter(m.pii_type for m in all_matches)
    
    structured_types = ["EMAIL", "PHONE", "IP_ADDRESS", "SSN", "CREDIT_CARD", "DATE_OF_BIRTH"]
    nlp_types = ["PERSON", "COMPANY", "ADDRESS"]

    print("\n=== STRUCTURED PII DETECTION COUNTS ===")
    for pii_type in structured_types:
        print(f"  {pii_type}: {counts[pii_type]}")

    print("\n=== NLP PII DETECTION COUNTS ===")
    for pii_type in nlp_types:
        print(f"  {pii_type}: {counts[pii_type]}")

    print("\n=== MASKED DETECTION EXAMPLES ===")
    # Group examples by type to show a few sample masks
    grouped_examples = {t: [] for t in structured_types + nlp_types}
    for m in all_matches:
        grouped_examples[m.pii_type].append(m)

    import re  # needed for regex formatting in mask helper

    for pii_type in (structured_types + nlp_types):
        matches = grouped_examples[pii_type]
        print(f"\nCategory: {pii_type} (First 5 examples):")
        if not matches:
            print("  No examples detected.")
            continue
            
        seen_masked = set()
        count = 0
        for m in matches:
            masked = mask_pii(m.text, m.pii_type)
            if masked not in seen_masked:
                seen_masked.add(masked)
                print(f"  - Match: '{masked}' (confidence: {m.confidence}, detector: {m.detector})")
                count += 1
                if count >= 5:
                    break


if __name__ == "__main__":
    main()
