import os
import sys
import re

sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")

from src.document_reader import DocumentReader

def has_ner_candidate(text):
    if not text or not any(c.isupper() for c in text):
        return False
    
    # Common PII keywords
    keywords = (
        r"\b(?:Mr|Ms|Mrs|Dr|Director|Chairman|Secretary|Officer|Auditor|Promoter|CEO|CFO|Managing|Compliance|"
        r"Limited|Ltd|LLP|Private|Pvt|Corporation|Inc|Co|Bank|Securities|Capital|Technologies|Solutions|Enterprises|Group|"
        r"Plot|Flat|Survey|Floor|Building|Road|Street|Nagar|District|State|Opposite|Opp|Behind|Lane|Apartment|Society|Park|Complex|Residency|Taluka|PIN|"
        r"Mumbai|Pune|Bangalore|Delhi|India|Maharashtra|Karnataka)\b"
    )
    if re.search(keywords, text, re.IGNORECASE):
        return True
        
    cap_words = re.findall(r"\b[A-Z][a-zA-Z0-9]*\b", text)
    if len(cap_words) >= 2:
        return True
        
    # Split sentences and check for capitalized words that are not the first word of a sentence
    sentences = re.split(r"[.!?]\s+", text)
    for sentence in sentences:
        words = re.findall(r"\b[a-zA-Z0-9]+\b", sentence)
        if len(words) > 1:
            for w in words[1:]:
                if w and w[0].isupper():
                    return True
    return False

def main():
    doc = DocumentReader.read("Red Herring Prospectus.docx")
    total = len(doc.blocks)
    passed = sum(1 for b in doc.blocks if b.text and has_ner_candidate(b.text))
    print(f"Total blocks: {total}")
    print(f"Blocks passing refined pre-check: {passed}")

if __name__ == "__main__":
    main()
