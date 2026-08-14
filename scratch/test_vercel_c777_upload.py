import requests
import os
import time

url = "https://pii-redaction-tool-fbh6.onrender.com/api/redact-async"
file_path = "Red Herring Prospectus.docx"

headers = {
    "Origin": "https://pii-redaction-tool-c777.vercel.app",
    "Referer": "https://pii-redaction-tool-c777.vercel.app/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

print(f"Testing direct POST to {url} with headers:")
print(headers)
print(f"File size: {os.path.getsize(file_path)/(1024*1024):.2f} MB")

start_t = time.time()
with open(file_path, "rb") as f:
    files = {"file": (os.path.basename(file_path), f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    res = requests.post(url, files=files, headers=headers, timeout=120)

elapsed = time.time() - start_t
print(f"Status Code: {res.status_code}")
print(f"Time Taken for Upload Request: {elapsed:.2f}s")
print(f"Response Headers: {dict(res.headers)}")
print(f"Response Text: {res.text}")
