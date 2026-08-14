import os
import sys
import time
import tracemalloc

sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")

from src.redactor import RedactionEngine

def print_memory(label):
    current, peak = tracemalloc.get_traced_memory()
    print(f"[{label}] Current: {current / (1024 * 1024):.2f} MB, Peak: {peak / (1024 * 1024):.2f} MB")

def main():
    tracemalloc.start()
    
    large_doc = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\Red Herring Prospectus.docx"
    output_path = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\output_redacted_large.docx"
    
    print("Starting memory measurement...")
    print_memory("Initial")
    
    start = time.time()
    engine = RedactionEngine()
    print_memory("After Engine Initialization")
    
    result = engine.redact(large_doc, output_path)
    print_memory("After Redaction Complete")
    
    elapsed = time.time() - start
    print(f"Total time: {elapsed:.2f}s")
    print(f"Total replacements: {result['total_replacements']}")
    
    tracemalloc.stop()

if __name__ == "__main__":
    main()
