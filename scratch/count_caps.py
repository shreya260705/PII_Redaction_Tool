import sys
sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")
import docx
from src.document_reader import DocumentReader

large_doc = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\Red Herring Prospectus.docx"
extracted = DocumentReader.read(large_doc)

total = len(extracted.blocks)
with_caps = 0
empty = 0

for block in extracted.blocks:
    if not block.text or not block.text.strip():
        empty += 1
        continue
    # Check if there is at least one uppercase letter (A-Z)
    if any(c.isupper() for c in block.text):
        with_caps += 1

print(f"Total blocks: {total}")
print(f"Empty/whitespace blocks: {empty}")
print(f"Blocks with capital letters: {with_caps}")
print(f"Blocks without capital letters: {total - empty - with_caps}")
print(f"Percentage of non-empty blocks that can skip NLP: {(total - empty - with_caps) / (total - empty) * 100:.2f}%")
