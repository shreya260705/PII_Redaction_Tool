import sys
import os
sys.path.insert(0, os.path.abspath("."))

import time
import requests
import json
import docx
from src.document_reader import DocumentReader

RENDER_URL = "https://pii-redaction-tool-fbh6.onrender.com"
FILE_PATH = "Red Herring Prospectus.docx"

def check_render_debug():
    print(f"=== Checking Deployed Render /api/debug ===")
    try:
        res = requests.get(f"{RENDER_URL}/api/debug", timeout=120)
        print(f"Render /api/debug Status: {res.status_code}")
        if res.status_code == 200:
            print("Render /api/debug Output:")
            print(json.dumps(res.json(), indent=2))
        else:
            print(f"Render debug error response: {res.text}")
    except Exception as e:
        print(f"Failed to fetch /api/debug from Render: {e}")

def test_render_async_rhp():
    print(f"\n=== Testing Deployed Render /api/redact-async ===")
    start_t = time.time()
    
    with open(FILE_PATH, "rb") as f:
        files = {"file": (os.path.basename(FILE_PATH), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        print(f"Sending large file ({os.path.getsize(FILE_PATH)/(1024*1024):.2f} MB) to Render...")
        res = requests.post(f"{RENDER_URL}/api/redact-async", files=files, timeout=120)
        
    print(f"Render Async Upload Status: {res.status_code}")
    assert res.status_code == 200, f"Render upload failed: {res.text}"
    
    data = res.json()
    task_id = data.get("task_id")
    print(f"Task Created on Render! Task ID: {task_id}")
    
    poll_start = time.time()
    task_data = None
    poll_count = 0
    while time.time() - poll_start < 400: # 6.6 minutes max
        time.sleep(3)
        poll_count += 1
        try:
            poll_res = requests.get(f"{RENDER_URL}/api/tasks/{task_id}", timeout=30)
            if poll_res.status_code == 200:
                task_data = poll_res.json()
                status = task_data.get("status")
                print(f"  [Poll #{poll_count}] Status: {status} ({time.time() - poll_start:.1f}s)")
                if status in ["success", "error"]:
                    break
            else:
                print(f"  [Poll #{poll_count}] Non-200 status code: {poll_res.status_code}")
        except Exception as poll_err:
            print(f"  [Poll #{poll_count}] Network hiccup: {poll_err}")
            
    total_async_time = time.time() - start_t
    print(f"Render task completed in {total_async_time:.2f}s. Task Result: {task_data}")
    assert task_data and task_data.get("status") == "success", f"Render task failed with status: {task_data}"
    
    result = task_data["result"]
    file_id = result["file_id"]
    total_replacements = result["total_replacements"]
    
    # Download file from Render
    dl_res = requests.get(f"{RENDER_URL}/api/download/{file_id}", timeout=60)
    print(f"Render Download Status: {dl_res.status_code} | Size: {len(dl_res.content)} bytes")
    assert dl_res.status_code == 200
    
    out_path = "output_render_rhp_test.docx"
    with open(out_path, "wb") as f:
        f.write(dl_res.content)
        
    doc = DocumentReader.read(out_path)
    print(f"Render Downloaded DOCX parsed successfully! Blocks: {len(doc.blocks)}")
    return total_replacements, total_async_time

def main():
    print("Waking up Render backend /api/health (timeout 120s for cold start)...")
    for attempt in range(1, 4):
        try:
            h = requests.get(f"{RENDER_URL}/api/health", timeout=120)
            print(f"Render Health (Attempt {attempt}): {h.status_code} {h.json()}")
            if h.status_code == 200:
                break
        except Exception as e:
            print(f"Health check attempt {attempt} failed: {e}. Retrying in 5s...")
            time.sleep(5)
            
    check_render_debug()
    repl_count, proc_time = test_render_async_rhp()
    
    print("\nRe-checking Render /api/debug after processing:")
    check_render_debug()
    
    print(f"\nDEPLOYED RENDER TEST PASSED SUCCESSFULLY!")
    print(f"Replacements: {repl_count} | Processing Time: {proc_time:.2f}s")

if __name__ == "__main__":
    main()
