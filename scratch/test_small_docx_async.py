import sys
import os
sys.path.insert(0, os.path.abspath("."))

import time
import requests
import json
import docx
from src.document_reader import DocumentReader

LOCAL_URL = "http://127.0.0.1:8000"
RENDER_URL = "https://pii-redaction-tool-fbh6.onrender.com"
SMALL_FILE = "PII_Strict_Accuracy_Test.docx"

def test_async_lifecycle(target_url, target_name):
    print(f"\n==================================================")
    print(f"Testing Async Lifecycle on [{target_name}]: {target_url}")
    print(f"Input Document: {SMALL_FILE} ({os.path.getsize(SMALL_FILE)} bytes)")
    print(f"==================================================")

    # 1. Health check
    h = requests.get(f"{target_url}/api/health", timeout=30)
    print(f"Health Status: {h.status_code} ({h.json()})")
    assert h.status_code == 200

    # 2. Upload /api/redact-async
    print("\n1. Submitting POST /api/redact-async...")
    start_t = time.time()
    with open(SMALL_FILE, "rb") as f:
        files = {"file": (os.path.basename(SMALL_FILE), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
        res = requests.post(f"{target_url}/api/redact-async", files=files, timeout=30)

    upload_t = time.time() - start_t
    print(f"Upload Response Status: {res.status_code} (took {upload_t:.2f}s)")
    assert res.status_code == 200, f"Upload failed: {res.text}"
    
    upload_data = res.json()
    task_id = upload_data.get("task_id")
    print(f"Task Created! Task ID: {task_id}")
    assert task_id, "No task_id returned in response!"

    # 3. Poll /api/tasks/{task_id}
    print(f"\n2. Polling /api/tasks/{task_id}...")
    poll_start = time.time()
    task_result = None
    poll_count = 0

    while time.time() - poll_start < 60:
        time.sleep(1)
        poll_count += 1
        poll_res = requests.get(f"{target_url}/api/tasks/{task_id}", timeout=10)
        print(f"  [Poll #{poll_count}] HTTP {poll_res.status_code} -> Data: {poll_res.json()}")
        assert poll_res.status_code == 200, f"Polling returned status {poll_res.status_code}!"
        
        data = poll_res.json()
        status = data.get("status")
        if status in ["success", "error"]:
            task_result = data
            break

    total_proc_t = time.time() - start_t
    print(f"\n3. Task Finished in {total_proc_t:.2f}s!")
    assert task_result and task_result.get("status") == "success", f"Task failed: {task_result}"

    result_info = task_result["result"]
    file_id = result_info["file_id"]
    filename = result_info["filename"]
    total_replacements = result_info["total_replacements"]
    types_breakdown = result_info["replacements_by_type"]

    print(f"\n4. Task Result Contract Verification:")
    print(f"  File ID: {file_id}")
    print(f"  Filename: {filename}")
    print(f"  Total Replacements: {total_replacements}")
    print(f"  Breakdown: {types_breakdown}")
    assert total_replacements == 57, f"Expected 57 replacements on strict accuracy test, got {total_replacements}"

    # 5. Query task status AGAIN after completion to verify persistent availability
    print(f"\n5. Re-verifying GET /api/tasks/{task_id} after completion...")
    recheck_res = requests.get(f"{target_url}/api/tasks/{task_id}", timeout=10)
    print(f"Re-check Status Code: {recheck_res.status_code}")
    assert recheck_res.status_code == 200, "Completed task result disappeared!"
    print(f"Task status remains persistently queryable: {recheck_res.json()['status']}")

    # 6. Download generated DOCX
    print(f"\n6. Downloading /api/download/{file_id}...")
    dl_res = requests.get(f"{target_url}/api/download/{file_id}", timeout=30)
    print(f"Download HTTP Status: {dl_res.status_code} | Size: {len(dl_res.content)} bytes")
    assert dl_res.status_code == 200, "Download failed!"

    out_file = f"output_small_async_{target_name}.docx"
    with open(out_file, "wb") as f:
        f.write(dl_res.content)

    doc = DocumentReader.read(out_file)
    print(f"Downloaded DOCX read successfully! Blocks: {len(doc.blocks)}")

    print(f"\n>>> SMALL DOCX ASYNC LIFECYCLE PASSED PERFECTLY ON [{target_name}] <<<")
    return True

if __name__ == "__main__":
    test_async_lifecycle(RENDER_URL, "Render_Production")
