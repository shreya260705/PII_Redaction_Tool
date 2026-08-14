import os
import sys
import re

sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")

from src.document_reader import DocumentReader

PII_KEYWORDS = (
    r"\b(?:Mr|Ms|Mrs|Dr|Director|Chairman|Secretary|Officer|Auditor|Promoter|CEO|CFO|Managing|Compliance|"
    r"Limited|Ltd|LLP|Private|Pvt|Corporation|Inc|Co|Bank|Securities|Capital|Technologies|Solutions|Enterprises|Group|"
    r"Plot|Flat|Survey|Floor|Building|Road|Street|Nagar|District|State|Opposite|Opp|Behind|Lane|Apartment|Society|Park|Complex|Residency|Taluka|PIN|"
    r"Mumbai|Pune|Bangalore|Delhi|India|Maharashtra|Karnataka)\b"
)
CANDIDATE_RX = re.compile(
    rf"{PII_KEYWORDS}|(?<!^)\b[A-Z][a-zA-Z0-9]*\b|\b[A-Z][a-zA-Z0-9]*\b.*?\b[A-Z][a-zA-Z0-9]*\b",
    re.IGNORECASE | re.DOTALL
)

def has_ner_candidate(text):
    if not text or not any(c.isupper() for c in text):
        return False
    return bool(CANDIDATE_RX.search(text))

def main():
    doc = DocumentReader.read("Red Herring Prospectus.docx")
    total = len(doc.blocks)
    passed = sum(1 for b in doc.blocks if b.text and has_ner_candidate(b.text))
    print(f"Total blocks: {total}")
    print(f"Blocks passing fast regex pre-check: {passed}")

if __name__ == "__main__":
    main()
