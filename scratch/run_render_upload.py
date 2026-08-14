import os
import requests
import time

API_BASE = "https://pii-redaction-tool-fbh6.onrender.com"
FILE_PATH = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\Red Herring Prospectus.docx"
DOWNLOAD_PATH = r"c:\Users\shrey\OneDrive\Desktop\PII-Redaction-Tool\output_redacted_render_rhp.docx"

def run_large_rhp_on_render():
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

    print("Uploading file to /api/redact on Render...")
    start_time = time.time()
    
    try:
        with open(FILE_PATH, "rb") as f:
            files = {"file": (os.path.basename(FILE_PATH), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
            response = requests.post(f"{API_BASE}/api/redact", files=files, timeout=300)
            
        elapsed = time.time() - start_time
        print(f"Upload and processing finished in {elapsed:.2f} seconds.")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Failed response: {response.reason}")
            print("Headers:")
            for k, v in response.headers.items():
                print(f"  {k}: {v}")
            print("Content:")
            print(response.text)
            return

        result = response.json()
        print("Success! Redaction result:")
        print(f"  File ID: {result.get('file_id')}")
        print(f"  Filename: {result.get('filename')}")
        print(f"  Expires At: {result.get('expires_at')}")
        print(f"  Total replacements: {result.get('total_replacements')}")
        print(f"  Replacements by type: {result.get('replacements_by_type')}")
        print(f"  Unique mappings count: {result.get('unique_mappings_count')}")

        file_id = result.get("file_id")
        if not file_id:
            print("Error: file_id not found in response.")
            return

        # Try to download the file
        download_url = f"{API_BASE}/api/download/{file_id}"
        print(f"Downloading redacted file from {download_url}...")
        
        dl_start = time.time()
        dl_response = requests.get(download_url, timeout=60)
        dl_elapsed = time.time() - dl_start
        
        print(f"Download finished in {dl_elapsed:.2f} seconds. Status code: {dl_response.status_code}")
        
        if dl_response.status_code == 200:
            with open(DOWNLOAD_PATH, "wb") as out_f:
                out_f.write(dl_response.content)
            print(f"Successfully saved downloaded file to: {DOWNLOAD_PATH}")
            print(f"Downloaded file size: {os.path.getsize(DOWNLOAD_PATH)} bytes")
        else:
            print(f"Download failed: {dl_response.text}")
            
    except Exception as e:
        print(f"An error occurred during API communication: {e}")

if __name__ == "__main__":
    run_large_rhp_on_render()
