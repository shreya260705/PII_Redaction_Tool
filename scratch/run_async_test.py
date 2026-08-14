import os
import requests
import time

API_BASE = "https://pii-redaction-tool-fbh6.onrender.com"
FILE_PATH = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\Red Herring Prospectus.docx"
DOWNLOAD_PATH = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\output_redacted_render_rhp.docx"

def test_async_workflow():
    print(f"Checking health of Render backend at {API_BASE}/api/health...")
    try:
        r = requests.get(f"{API_BASE}/api/health", timeout=60)
        print(f"Health check status: {r.status_code}, Response: {r.json()}")
    except Exception as e:
        print(f"Health check failed: {e}")
        return

    if not os.path.exists(FILE_PATH):
        print(f"Error: Large document not found at {FILE_PATH}")
        return

    file_size = os.path.getsize(FILE_PATH)
    print(f"File found: {FILE_PATH} ({file_size / (1024*1024):.2f} MB)")

    print("Uploading file to /api/redact-async on Render...")
    start_time = time.time()
    
    try:
        with open(FILE_PATH, "rb") as f:
            files = {"file": (os.path.basename(FILE_PATH), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
            response = requests.post(f"{API_BASE}/api/redact-async", files=files, timeout=60)
            
        print(f"Upload finished in {time.time() - start_time:.2f} seconds.")
        print(f"Upload Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Upload failed: {response.text}")
            return

        upload_result = response.json()
        task_id = upload_result.get("task_id")
        print(f"Success! Task ID: {task_id}")
        
        if not task_id:
            print("Error: task_id not found in response.")
            return

        # Poll the status endpoint
        poll_url = f"{API_BASE}/api/tasks/{task_id}"
        print(f"Polling task status at {poll_url}...")
        
        poll_start = time.time()
        completed = False
        
        while time.time() - poll_start < 400: # 6.6 minutes max timeout
            time.sleep(5)
            try:
                poll_response = requests.get(poll_url, timeout=10)
                if poll_response.status_code != 200:
                    print(f"Poll request failed with status: {poll_response.status_code}")
                    continue
                
                task_data = poll_response.json()
                status = task_data.get("status")
                print(f"[{time.time() - poll_start:.1f}s] Task status: {status}")
                
                if status == "success":
                    completed = True
                    result = task_data.get("result")
                    print("Success! Redaction complete.")
                    print(f"  File ID: {result.get('file_id')}")
                    print(f"  Filename: {result.get('filename')}")
                    print(f"  Total replacements: {result.get('total_replacements')}")
                    print(f"  Replacements by type: {result.get('replacements_by_type')}")
                    
                    # Try to download the file
                    file_id = result.get("file_id")
                    download_url = f"{API_BASE}/api/download/{file_id}"
                    print(f"Downloading redacted file from {download_url}...")
                    
                    dl_response = requests.get(download_url, timeout=60)
                    if dl_response.status_code == 200:
                        with open(DOWNLOAD_PATH, "wb") as out_f:
                            out_f.write(dl_response.content)
                        print(f"Successfully saved downloaded file to: {DOWNLOAD_PATH}")
                        print(f"Downloaded file size: {os.path.getsize(DOWNLOAD_PATH)} bytes")
                    else:
                        print(f"Download failed: {dl_response.text}")
                    break
                elif status == "error":
                    print(f"Task failed on server: {task_data.get('error')}")
                    break
            except Exception as poll_e:
                print(f"Poll error: {poll_e}")
                
        if not completed:
            print("Task polling timed out or failed.")
            
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    test_async_workflow()
