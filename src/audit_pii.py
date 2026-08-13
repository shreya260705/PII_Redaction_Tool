import logging
import os
import re
import sys
from collections import defaultdict
from typing import List, Tuple

from src.document_reader import DocumentReader
from src.models import PIIMatch, DocumentBlock
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

# SuppressPresidio and spacy warnings
logging.basicConfig(level=logging.WARNING)
logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)


def mask_pii(text: str, pii_type: str) -> str:
    """Masks matched text for safe display using robust token-based masking."""
    if pii_type == "EMAIL":
        if "@" in text:
            parts = text.split("@", 1)
            user, domain = parts[0], parts[1]
            if len(user) <= 2:
                return "*" * len(user) + "@" + domain
            return f"{user[0]}{'*' * (len(user) - 2)}{user[-1]}@{domain}"
        return "***"
    elif pii_type in ("PHONE", "IP_ADDRESS", "SSN", "CREDIT_CARD", "DATE_OF_BIRTH"):
        # Replace digits with *
        return re.sub(r'\d', '*', text)
    elif pii_type in ("PERSON", "COMPANY"):
        # Split by non-word characters to avoid leakages across slashes/dashes
        tokens = re.split(r'(\W+)', text)
        masked_tokens = []
        for token in tokens:
            if re.match(r'^[A-Za-z0-9]+$', token):
                if token.isdigit():
                    masked_tokens.append('*' * len(token))
                elif len(token) <= 2:
                    masked_tokens.append(token[0] + "*")
                else:
                    masked_tokens.append(token[0] + "*" * (len(token) - 2) + token[-1])
            else:
                masked_tokens.append(token)
        return "".join(masked_tokens)
    elif pii_type == "ADDRESS":
        # Specific output format requested: e.g. "Taluk***India"
        if len(text) <= 10:
            return "***"
        return f"{text[:5]}***{text[-5:]}"
    return "***"


def mask_pii_for_context(text: str, pii_type: str) -> str:
    """Masks matched text word-by-word for contextual display, preserving address structural layout."""
    if pii_type == "ADDRESS":
        # Split by tokens, mask each word except common structural/prepositional words
        STRUCTURAL_WORDS = {"no", "no.", "nos", "nos.", "and", "of", "the", "in", "at", "on", "to", "by", "with", "from", "for"}
        tokens = re.split(r'(\W+)', text)
        masked_tokens = []
        for token in tokens:
            if re.match(r'^[A-Za-z0-9]+$', token):
                if token.isdigit():
                    masked_tokens.append('*' * len(token))
                elif token.lower() in STRUCTURAL_WORDS:
                    masked_tokens.append(token)
                elif len(token) <= 2:
                    masked_tokens.append(token[0] + "*")
                else:
                    masked_tokens.append(token[0] + "*" * (len(token) - 2) + token[-1])
            else:
                masked_tokens.append(token)
        return "".join(masked_tokens)
    return mask_pii(text, pii_type)


def clean_and_mask_context(block_text: str, target_match: PIIMatch, all_block_matches: List[PIIMatch]) -> str:
    """
    Masks the context around the target match.
    All detected PII in the block must be masked.
    Emails, phone numbers, and digits must be masked.
    Other capitalized words (that are not PII) are preserved to retain structural readability.
    """
    # Sort all matches in the block in descending order of start offset
    sorted_matches = sorted(all_block_matches, key=lambda x: x.start, reverse=True)
    
    # We will replace each match with its masked version.
    # To identify the target match after masking, we temporarily wrap it with marker tags.
    masked_text = block_text
    for m in sorted_matches:
        # Get masked text for this match using the word-by-word masking for context
        m_masked = mask_pii_for_context(m.text, m.pii_type)
        if m.start == target_match.start and m.end == target_match.end and m.text == target_match.text:
            replacement = f"[[TARGET_START]]{m_masked}[[TARGET_END]]"
        else:
            replacement = m_masked
        masked_text = masked_text[:m.start] + replacement + masked_text[m.end:]
        
    # Split by target markers to apply generic regex-based masking to the rest of the context
    if "[[TARGET_START]]" in masked_text and "[[TARGET_END]]" in masked_text:
        parts = masked_text.split("[[TARGET_START]]", 1)
        before_target = parts[0]
        rest = parts[1].split("[[TARGET_END]]", 1)
        target_part = rest[0]
        after_target = rest[1]
    else:
        before_target = masked_text
        target_part = mask_pii_for_context(target_match.text, target_match.pii_type)
        after_target = ""
        
    # Mask all remaining digits in before and after parts
    before_target = re.sub(r'\d', '*', before_target)
    after_target = re.sub(r'\d', '*', after_target)
    
    # Mask any remaining emails or phone numbers in before and after parts
    email_rx = re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b')
    phone_rx = re.compile(r'\b(?:\+?91|0)?[-\s]?[6-9]\d{9}\b|\b\d{3}[-\s]?\d{3}[-\s]?\d{4}\b')
    
    before_target = email_rx.sub(lambda m: mask_pii_for_context(m.group(), "EMAIL"), before_target)
    after_target = email_rx.sub(lambda m: mask_pii_for_context(m.group(), "EMAIL"), after_target)
    
    before_target = phone_rx.sub(lambda m: mask_pii_for_context(m.group(), "PHONE"), before_target)
    after_target = phone_rx.sub(lambda m: mask_pii_for_context(m.group(), "PHONE"), after_target)
    
    # Slice the context to prevent overly long outputs, keeping up to 80 chars before and after
    if len(before_target) > 80:
        before_target = "... " + before_target[-80:]
    if len(after_target) > 80:
        after_target = after_target[:80] + " ..."
        
    # Combine back without target tags
    return f"{before_target.strip()} {target_part} {after_target.strip()}".strip()


def get_location_string(loc) -> str:
    if loc.part_type == "header":
        return f"Header Block (Section: {loc.section_index}, Type: {loc.header_footer_type})"
    elif loc.part_type == "footer":
        return f"Footer Block (Section: {loc.section_index}, Type: {loc.header_footer_type})"
    elif loc.table_index is not None:
        return f"Table Cell (Table Index: {loc.table_index}, Row: {loc.row_index}, Cell: {loc.cell_index})"
    return f"Paragraph (Index: {loc.paragraph_index})"


def select_representative_samples(matches_with_blocks: List[Tuple[PIIMatch, DocumentBlock]], pii_type: str) -> List[Tuple[PIIMatch, DocumentBlock]]:
    """Selects up to 30 highly representative samples across multiple confidence bands, detectors, and locations."""
    # Sort candidates by confidence descending
    candidates = sorted(matches_with_blocks, key=lambda x: x[0].confidence, reverse=True)
    
    selected = []
    selected_keys = set()
    
    # Define targeted criteria mapping
    criteria = {}
    if pii_type == "PERSON":
        criteria = {
            "designation": lambda m, b: bool(re.search(r'\b(?:director|secretary|officer|auditor|chairman|ceo|cfo|promoter|partner)\b', b.text, re.IGNORECASE)),
            "contact": lambda m, b: bool(re.search(r'\b(?:contact|email|phone|tel|mobile|fax|call)\b', b.text, re.IGNORECASE)),
            "table": lambda m, b: b.location.table_index is not None,
            "prose": lambda m, b: b.location.table_index is None and b.location.part_type == "body",
            "low_conf": lambda m, b: m.confidence < 0.90
        }
    elif pii_type == "COMPANY":
        criteria = {
            "ltd": lambda m, b: any(suffix in m.text.lower() for suffix in ["limited", "ltd"]),
            "llp": lambda m, b: "llp" in m.text.lower(),
            "org_nlp": lambda m, b: m.detector == "nlp_presidio_company",
            "regex_fallback": lambda m, b: m.detector == "regex_company_fallback",
            "financial": lambda m, b: any(k in m.text.lower() for k in ["bank", "finance", "capital", "mutual", "insurance", "securities"]),
            "professional": lambda m, b: any(k in m.text.lower() for k in ["associates", "partners", "consultants", "auditors", "solicitors", "legal"]),
            "commercial": lambda m, b: not any(k in m.text.lower() for k in ["bank", "finance", "capital", "mutual", "insurance", "securities", "associates", "partners", "consultants", "auditors", "solicitors"]),
            "borderline": lambda m, b: m.confidence < 0.95
        }
    elif pii_type == "ADDRESS":
        criteria = {
            "full_address": lambda m, b: m.text.count(',') >= 3 or len(m.text) > 40,
            "pin": lambda m, b: bool(re.search(r'\b\d{3}\s?\d{3}\b|\b\d{6}\b', m.text)),
            "no_pin": lambda m, b: not bool(re.search(r'\b\d{3}\s?\d{3}\b|\b\d{6}\b', m.text)),
            "table": lambda m, b: b.location.table_index is not None,
            "suspicious_pin": lambda m, b: bool(re.search(r'\b\d{3}\s?\d{3}\b|\b\d{6}\b', m.text)) and len(m.text) < 25,
            "low_conf": lambda m, b: m.confidence <= 0.85
        }
        
    # First pass: try to pick at least 2-3 representatives for each criterion
    for crit_name, crit_fn in criteria.items():
        count_picked = 0
        for m, b in candidates:
            if len(selected) >= 30:
                break
            key = (m.start, m.end, m.text, b.block_id)
            if key not in selected_keys and crit_fn(m, b):
                selected.append((m, b))
                selected_keys.add(key)
                count_picked += 1
                if count_picked >= 3:
                    break
                    
    # Second pass: if we have fewer than 30, fill with remaining candidates from across the list
    if len(selected) < 30 and len(candidates) > len(selected):
        for m, b in candidates:
            if len(selected) >= 30:
                break
            key = (m.start, m.end, m.text, b.block_id)
            if key not in selected_keys:
                selected.append((m, b))
                selected_keys.add(key)
                
    # Sort selected by confidence descending
    selected.sort(key=lambda x: x[0].confidence, reverse=True)
    return selected


def main():
    doc_path = "Red Herring Prospectus.docx"
    print(f"Reading document for audit: {doc_path} ...")
    
    try:
        extracted = DocumentReader.read(doc_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
        
    detectors = [
        EmailDetector(),
        PhoneDetector(),
        IPAddressDetector(),
        SSNDetector(),
        CreditCardDetector(),
        DateOfBirthDetector(),
        NLPDetector(),
    ]
    
    # Store block-level candidates and matches
    block_matches_dict = {}
    all_audit_matches = []
    
    detector_counts = defaultdict(int)
    confidence_counts = defaultdict(int)
    
    print("Running PII scan across all blocks...")
    for block in extracted.blocks:
        block_matches = []
        for det in detectors:
            try:
                matches = det.detect(block.text)
                block_matches.extend(matches)
            except Exception:
                pass
                
        resolved = resolve_overlaps(block_matches)
        block_matches_dict[block.block_id] = resolved
        
        for m in resolved:
            # Track statistics
            detector_counts[f"{m.pii_type}:{m.detector}"] += 1
            
            # Confidence distribution
            c = m.confidence
            if c >= 0.90:
                confidence_counts["0.90-1.00"] += 1
            elif c >= 0.80:
                confidence_counts["0.80-0.89"] += 1
            elif c >= 0.70:
                confidence_counts["0.70-0.79"] += 1
            else:
                confidence_counts["below 0.70"] += 1
                
            if m.pii_type in ("PERSON", "COMPANY", "ADDRESS"):
                all_audit_matches.append((m, block))

    print(f"\nTotal audit candidates found: {len(all_audit_matches)}")
    
    # Group by pii_type
    grouped = defaultdict(list)
    for m, b in all_audit_matches:
        grouped[m.pii_type].append((m, b))
        
    # Select representative samples
    representative_samples = {}
    for pii_type in ("PERSON", "COMPANY", "ADDRESS"):
        representative_samples[pii_type] = select_representative_samples(grouped[pii_type], pii_type)

    # Write output report to output/audit_report.txt
    os.makedirs("output", exist_ok=True)
    report_path = os.path.join("output", "audit_report.txt")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=== PII DETECTION AUDIT REPORT ===\n\n")
        
        f.write("=== DETECTOR DISTRIBUTION ===\n")
        for key, count in sorted(detector_counts.items()):
            f.write(f"  {key}: {count}\n")
        f.write("\n")
        
        f.write("=== CONFIDENCE DISTRIBUTION ===\n")
        for range_str in ["0.90-1.00", "0.80-0.89", "0.70-0.79", "below 0.70"]:
            f.write(f"  {range_str}: {confidence_counts[range_str]}\n")
        f.write("\n")
        
        for pii_type in ("PERSON", "COMPANY", "ADDRESS"):
            f.write(f"\n=== REPRESENTATIVE SAMPLES FOR {pii_type} ===\n")
            samples = representative_samples[pii_type]
            f.write(f"Displaying {len(samples)} representative matches:\n\n")
            
            for idx, (m, b) in enumerate(samples):
                loc_str = get_location_string(b.location)
                is_table = b.location.table_index is not None
                masked_text = mask_pii(m.text, m.pii_type)
                
                # Fetch all resolved matches in this block for context masking
                all_block_matches = block_matches_dict[b.block_id]
                masked_ctx = clean_and_mask_context(b.text, m, all_block_matches)
                
                signal = "N/A"
                if m.detector == "nlp_presidio_person":
                    signal = "spaCy PERSON NER + contextual proximity boost if available"
                elif m.detector == "nlp_presidio_company":
                    signal = "spaCy ORG NER + company suffix/context filters"
                elif m.detector == "regex_company_fallback":
                    signal = "Regex fallback match for corporate suffixes"
                elif m.detector == "custom_address_rules":
                    signal = "PIN code + structural keywords + GPE alignment scoring"
                    
                f.write(f"Sample #{idx+1}:\n")
                f.write(f"  PII Type: {m.pii_type}\n")
                f.write(f"  Masked Text: {masked_text}\n")
                f.write(f"  Confidence: {m.confidence}\n")
                f.write(f"  Detector: {m.detector}\n")
                f.write(f"  Block Type: {b.block_type}\n")
                f.write(f"  Location: {loc_str}\n")
                f.write(f"  Inside Table: {is_table}\n")
                f.write(f"  Detector Signal: {signal}\n")
                f.write(f"  Surrounding Context: {masked_ctx}\n")
                f.write("-" * 50 + "\n")

    print(f"\nAudit complete. Full report written to: {report_path}")
    
    # Print short summary to stdout
    print("\n=== DETECTOR DISTRIBUTION ===")
    for key, count in sorted(detector_counts.items()):
        print(f"  {key}: {count}")
        
    print("\n=== CONFIDENCE DISTRIBUTION ===")
    for range_str in ["0.90-1.00", "0.80-0.89", "0.70-0.79", "below 0.70"]:
        print(f"  {range_str}: {confidence_counts[range_str]}")


if __name__ == "__main__":
    main()
