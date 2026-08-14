import sys
import os
sys.path.insert(0, os.path.abspath("."))

import time
import requests
import docx
from src.document_reader import DocumentReader

BASE_URL = "http://127.0.0.1:8000"
FILE_PATH = "Red Herring Prospectus.docx"

def test_cors():
    print("\n=== Testing CORS Preflight Requests ===")
    headers = {
        "Origin": "https://pii-redaction-tool.vercel.app",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"
    }
    
    # 1. OPTIONS /api/redact
    res_redact = requests.options(f"{BASE_URL}/api/redact", headers=headers)
    print(f"OPTIONS /api/redact status: {res_redact.status_code}")
    print(f"Access-Control-Allow-Origin: {res_redact.headers.get('access-control-allow-origin')}")
    print(f"Access-Control-Allow-Methods: {res_redact.headers.get('access-control-allow-methods')}")
    assert res_redact.status_code == 200 or res_redact.status_code == 204
    assert res_redact.headers.get('access-control-allow-origin') in ["*", "https://pii-redaction-tool.vercel.app"]

    # 2. OPTIONS /api/redact-async
    res_async = requests.options(f"{BASE_URL}/api/redact-async", headers=headers)
    print(f"OPTIONS /api/redact-async status: {res_async.status_code}")
    print(f"Access-Control-Allow-Origin: {res_async.headers.get('access-control-allow-origin')}")
    assert res_async.status_code == 200 or res_async.status_code == 204

def test_sync_redact():
    print("\n=== Testing Local Synchronous /api/redact ===")
    start_t = time.time()
    with open(FILE_PATH, "rb") as f:
        files = {"file": (os.path.basename(FILE_PATH), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        res = requests.post(f"{BASE_URL}/api/redact", files=files)
    
    elapsed = time.time() - start_t
    print(f"Status Code: {res.status_code}")
    assert res.status_code == 200, f"Sync upload failed: {res.text}"
    
    data = res.json()
    print(f"Response JSON: {data}")
    file_id = data["file_id"]
    filename = data["filename"]
    total_replacements = data["total_replacements"]
    print(f"Processing time: {elapsed:.2f}s | Replacements: {total_replacements}")
    
    # Download file
    dl_res = requests.get(f"{BASE_URL}/api/download/{file_id}")
    print(f"Download Status: {dl_res.status_code} | Content-Type: {dl_res.headers.get('content-type')}")
    assert dl_res.status_code == 200
    
    out_path = "output_sync_local_test.docx"
    with open(out_path, "wb") as f:
        f.write(dl_res.content)
        
    doc = DocumentReader.read(out_path)
    print(f"Sync Downloaded DOCX parsed successfully! Blocks: {len(doc.blocks)}")
    return total_replacements

def test_async_redact():
    print("\n=== Testing Local Asynchronous /api/redact-async ===")
    start_t = time.time()
    with open(FILE_PATH, "rb") as f:
        files = {"file": (os.path.basename(FILE_PATH), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        res = requests.post(f"{BASE_URL}/api/redact-async", files=files)
        
    print(f"Status Code: {res.status_code}")
    assert res.status_code == 200, f"Async upload failed: {res.text}"
    
    data = res.json()
    task_id = data.get("task_id")
    print(f"Task Created! Task ID: {task_id}")
    
    poll_start = time.time()
    task_data = None
    while time.time() - poll_start < 120:
        time.sleep(2)
        poll_res = requests.get(f"{BASE_URL}/api/tasks/{task_id}")
        assert poll_res.status_code == 200
        task_data = poll_res.json()
        status = task_data.get("status")
        print(f"Polling status: {status}...")
        if status in ["success", "error"]:
            break
            
    total_async_time = time.time() - start_t
    print(f"Task completed in {total_async_time:.2f}s. Task Result: {task_data}")
    assert task_data.get("status") == "success"
    
    result = task_data["result"]
    file_id = result["file_id"]
    filename = result["filename"]
    total_replacements = result["total_replacements"]
    
    dl_res = requests.get(f"{BASE_URL}/api/download/{file_id}")
    print(f"Download Status: {dl_res.status_code} | Size: {len(dl_res.content)} bytes")
    assert dl_res.status_code == 200
    
    out_path = "output_async_local_test.docx"
    with open(out_path, "wb") as f:
        f.write(dl_res.content)
        
    doc = DocumentReader.read(out_path)
    print(f"Async Downloaded DOCX parsed successfully! Blocks: {len(doc.blocks)}")
    return total_replacements

def main():
    print("Checking /api/health...")
    h = requests.get(f"{BASE_URL}/api/health")
    print(f"Health: {h.json()}")
    
    test_cors()
    sync_repl = test_sync_redact()
    async_repl = test_async_redact()
    
    print(f"\nALL LOCAL API TESTS PASSED! Sync Replacements: {sync_repl}, Async Replacements: {async_repl}")

if __name__ == "__main__":
    main()
