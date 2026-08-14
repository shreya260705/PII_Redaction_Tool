import os
import sys
import time
import subprocess

sys.path.insert(0, r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool")

from src.redactor import RedactionEngine

def print_rss(label):
    pid = os.getpid()
    try:
        # Run tasklist to get memory usage of this process
        out = subprocess.check_output(f'tasklist /FI "PID eq {pid}" /NH', shell=True).decode('utf-8', errors='ignore')
        # Format of tasklist output: Image Name  PID  Session Name  Session#  Mem Usage
        # e.g., python.exe  12345  Console  1  120,400 K
        parts = out.strip().split()
        if len(parts) >= 5:
            mem_str = parts[-2].replace(',', '').replace('.', '')
            mem_mb = float(mem_str) / 1024
            print(f"[{label}] Process RSS Memory: {mem_mb:.2f} MB")
        else:
            print(f"[{label}] Raw tasklist output: {out.strip()}")
    except Exception as e:
        print(f"[{label}] Failed to get memory: {e}")

def main():
    large_doc = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\Red Herring Prospectus.docx"
    output_path = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\output_redacted_large.docx"
    
    print("Starting physical memory measurement...")
    print_rss("Initial")
    
    start = time.time()
    engine = RedactionEngine()
    print_rss("After Engine Initialization")
    
    result = engine.redact(large_doc, output_path)
    print_rss("After Redaction Complete")
    
    elapsed = time.time() - start
    print(f"Total time: {elapsed:.2f}s")
    print(f"Total replacements: {result['total_replacements']}")

if __name__ == "__main__":
    main()
