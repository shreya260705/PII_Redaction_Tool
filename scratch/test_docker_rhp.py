import sys
import os
sys.path.insert(0, os.path.abspath("."))

import time
import requests
import docx
from src.document_reader import DocumentReader

BASE_URL = "http://127.0.0.1:8001"
FILE_PATH = "Red Herring Prospectus.docx"

def test_docker_sync():
    print("\n=== Testing Docker Synchronous /api/redact ===")
    start_t = time.time()
    with open(FILE_PATH, "rb") as f:
        files = {"file": (os.path.basename(FILE_PATH), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        res = requests.post(f"{BASE_URL}/api/redact", files=files)
    
    elapsed = time.time() - start_t
    print(f"Docker Sync Upload Status: {res.status_code}")
    assert res.status_code == 200, f"Docker sync upload failed: {res.text}"
    
    data = res.json()
    file_id = data["file_id"]
    total_replacements = data["total_replacements"]
    print(f"Docker Sync Response JSON: {data}")
    print(f"Processing time inside Docker: {elapsed:.2f}s | Replacements: {total_replacements}")
    
    dl_res = requests.get(f"{BASE_URL}/api/download/{file_id}")
    print(f"Download Status: {dl_res.status_code} | Content-Length: {len(dl_res.content)} bytes")
    assert dl_res.status_code == 200
    
    out_path = "output_docker_sync_rhp.docx"
    with open(out_path, "wb") as f:
        f.write(dl_res.content)
        
    doc = DocumentReader.read(out_path)
    print(f"Docker Sync Output DOCX parsed successfully! Blocks: {len(doc.blocks)}")
    return total_replacements, elapsed

def test_docker_async():
    print("\n=== Testing Docker Asynchronous /api/redact-async ===")
    start_t = time.time()
    with open(FILE_PATH, "rb") as f:
        files = {"file": (os.path.basename(FILE_PATH), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        res = requests.post(f"{BASE_URL}/api/redact-async", files=files)
        
    print(f"Docker Async Upload Status: {res.status_code}")
    assert res.status_code == 200, f"Docker async upload failed: {res.text}"
    
    data = res.json()
    task_id = data.get("task_id")
    print(f"Task Created! Task ID: {task_id}")
    
    poll_start = time.time()
    task_data = None
    while time.time() - poll_start < 180:
        time.sleep(2)
        poll_res = requests.get(f"{BASE_URL}/api/tasks/{task_id}")
        assert poll_res.status_code == 200
        task_data = poll_res.json()
        status = task_data.get("status")
        print(f"Polling Docker task status: {status}...")
        if status in ["success", "error"]:
            break
            
    total_async_time = time.time() - start_t
    print(f"Docker task completed in {total_async_time:.2f}s. Task Result: {task_data}")
    assert task_data.get("status") == "success"
    
    result = task_data["result"]
    file_id = result["file_id"]
    total_replacements = result["total_replacements"]
    
    dl_res = requests.get(f"{BASE_URL}/api/download/{file_id}")
    print(f"Download Status: {dl_res.status_code} | Size: {len(dl_res.content)} bytes")
    assert dl_res.status_code == 200
    
    out_path = "output_docker_async_rhp.docx"
    with open(out_path, "wb") as f:
        f.write(dl_res.content)
        
    doc = DocumentReader.read(out_path)
    print(f"Docker Async Output DOCX parsed successfully! Blocks: {len(doc.blocks)}")
    return total_replacements, total_async_time

def main():
    print("Checking Docker container /api/health...")
    h = requests.get(f"{BASE_URL}/api/health")
    print(f"Docker Health: {h.json()}")
    
    sync_repl, sync_t = test_docker_sync()
    async_repl, async_t = test_docker_async()
    
    # Check debug after tests to verify container memory & stability
    debug_res = requests.get(f"{BASE_URL}/api/debug").json()
    print("\nDocker /api/debug after processing large files:")
    print(f"VmRSS: {debug_res.get('mem_info', {}).get('VmRSS')}")
    print(f"VmHWM (Peak Memory): {debug_res.get('mem_info', {}).get('VmHWM')}")

    print(f"\nALL DOCKER TESTS PASSED SUCCESSFULLY!")
    print(f"Sync Replacements: {sync_repl} ({sync_t:.2f}s)")
    print(f"Async Replacements: {async_repl} ({async_t:.2f}s)")

if __name__ == "__main__":
    main()
