import os
import sys
import time

# Add current workspace directory to python path
sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")

from src.redactor import RedactionEngine
from src.document_reader import DocumentReader

def print_memory():
    pass

def main():
    large_doc = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\Red Herring Prospectus.docx"
    output_path = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\output_redacted_large.docx"
    
    print("=== Profiling Large Document Processing ===")
    print_memory()
    
    print("1. Reading document metadata...")
    start_time = time.time()
    extracted = DocumentReader.read(large_doc)
    read_time = time.time() - start_time
    print(f"Read done in {read_time:.2f} seconds.")
    print(f"Metadata: Paragraphs: {extracted.metadata.paragraph_count}, Tables: {extracted.metadata.table_count}, Cells: {extracted.metadata.table_cell_count}, HF Blocks: {extracted.metadata.header_footer_block_count}, Total Blocks: {len(extracted.blocks)}")
    print_memory()
    
    print("2. Initializing RedactionEngine...")
    start_time = time.time()
    engine = RedactionEngine()
    init_time = time.time() - start_time
    print(f"Engine initialized in {init_time:.2f} seconds.")
    print_memory()
    
    print("3. Redacting document...")
    start_time = time.time()
    
    # Let's count how long it takes and see where the bottleneck is
    # Instead of running engine.redact directly, let's run a custom loop to see progress
    total_replacements = 0
    replacements_by_type = {}
    processed_elements = set()
    
    block_times = []
    
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
                
        block_start = time.time()
        
        block_matches = []
        for detector in engine.detectors:
            if detector.__class__.__name__ == "NLPDetector" and is_heading_or_title:
                continue
            try:
                matches = detector.detect(block.text)
                block_matches.extend(matches)
            except Exception as e:
                pass
                
        from src.detectors.base import resolve_overlaps
        from src.redactor import redact_block
        
        resolved = resolve_overlaps(block_matches)
        applied = redact_block(block, resolved, engine.mapper)
        
        block_duration = time.time() - block_start
        block_times.append((i, block.block_type, len(block.text), block_duration))
        
        total_replacements += len(applied)
        for match in applied:
            replacements_by_type[match.pii_type] = replacements_by_type.get(match.pii_type, 0) + 1
            
        if i > 0 and i % 500 == 0:
            print(f"Processed {i} blocks... replacements so far: {total_replacements}")
            print_memory()
            
    redact_time = time.time() - start_time
    print(f"Redaction loop complete in {redact_time:.2f} seconds.")
    print(f"Total replacements: {total_replacements}")
    print_memory()
    
    print("Saving redacted file...")
    extracted.doc.save(output_path)
    print("Save complete.")
    print_memory()
    
    # Sort and display slowest blocks
    print("\nSlowest 10 blocks:")
    block_times.sort(key=lambda x: x[3], reverse=True)
    for idx, b_type, b_len, dur in block_times[:10]:
        print(f"Block {idx} ({b_type}), Length: {b_len} chars, Duration: {dur:.4f} seconds")

if __name__ == "__main__":
    main()
