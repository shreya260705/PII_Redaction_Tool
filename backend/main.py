import os
import shutil
import tempfile
import uuid
import time
from typing import Dict, Tuple
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from src.redactor import RedactionEngine

app = FastAPI(title="PII Redaction Engine API")

# Configure CORS
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://pii-redaction-tool-c777.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20 MB

# Dedicated temporary storage directory created safely under OS temp directory
TEMP_BASE_DIR = os.path.join(tempfile.gettempdir(), "pii_redactor_temp")
os.makedirs(TEMP_BASE_DIR, exist_ok=True)

# In-memory mapping: file_id -> (output_filepath, original_filename, created_at)
file_mappings: Dict[str, Tuple[str, str, float]] = {}

def clean_temp_file(filepath: str, file_id: str = None):
    """Deletes a file on disk and removes its mapping entry."""
    try:
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
    except Exception:
        pass
    if file_id and file_id in file_mappings:
        file_mappings.pop(file_id, None)

def prune_expired_files(max_age_seconds: int = 1800):
    """Deletes temporary files and mapping entries older than 30 minutes."""
    now = time.time()
    expired_ids = []
    
    for fid, (fpath, _, created_at) in list(file_mappings.items()):
        if now - created_at > max_age_seconds:
            expired_ids.append(fid)
            try:
                if os.path.exists(fpath):
                    os.remove(fpath)
            except Exception:
                pass
                
    for fid in expired_ids:
        file_mappings.pop(fid, None)

    try:
        for f in os.listdir(TEMP_BASE_DIR):
            fpath = os.path.join(TEMP_BASE_DIR, f)
            if os.path.isfile(fpath):
                if now - os.path.getmtime(fpath) > max_age_seconds:
                    try:
                        os.remove(fpath)
                    except Exception:
                        pass
    except Exception:
        pass

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.post("/api/redact")
def redact_document(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    # Prune expired files in the background on every request
    background_tasks.add_task(prune_expired_files, 120)

    # 1. Validate file extension
    filename = file.filename or ""
    if not filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Only .docx files are allowed."
        )

    # 2. Enforce file size limit
    contents = file.file.read(1024)
    size = len(contents)
    rest = []
    while True:
        chunk = file.file.read(8192)
        if not chunk:
            break
        size += len(chunk)
        if size > MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB."
            )
        rest.append(chunk)

    all_contents = contents + b"".join(rest)

    # Create safe unique temporary file names in our dedicated temp folder
    unique_id = uuid.uuid4().hex
    input_path = os.path.join(TEMP_BASE_DIR, f"in_{unique_id}.docx")
    output_path = os.path.join(TEMP_BASE_DIR, f"out_{unique_id}.docx")

    # Save uploaded file
    try:
        with open(input_path, "wb") as f:
            f.write(all_contents)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file."
        )

    # Register temporary input cleanup immediately after processing
    background_tasks.add_task(clean_temp_file, input_path)

    # Run Redaction
    try:
        engine = RedactionEngine()
        result = engine.redact(input_path, output_path)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while redacting the document."
        )

    if not os.path.exists(output_path):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Redacted document could not be generated."
        )

    # Generate a secure cryptographically random file_id
    file_id = str(uuid.uuid4())
    created_at = time.time()
    file_mappings[file_id] = (output_path, filename, created_at)

    # Build clean sanitized output filename
    base, _ = os.path.splitext(filename)
    sanitized_name = "".join(c for c in base if c.isalnum() or c in "._- ")
    if not sanitized_name:
        sanitized_name = "Redacted"
    download_filename = f"{sanitized_name}_Redacted.docx"

    from datetime import datetime, timezone
    expires_at = datetime.fromtimestamp(created_at + 120.0, tz=timezone.utc).isoformat()

    return {
        "success": True,
        "file_id": file_id,
        "filename": download_filename,
        "expires_at": expires_at,
        "total_replacements": result["total_replacements"],
        "replacements_by_type": result["replacements_by_type"],
        "unique_mappings_count": result["unique_mappings_count"]
    }

@app.get("/api/download/{file_id}")
async def download_file(
    file_id: str,
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    try:
        uuid.UUID(file_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid file ID structure."
        )

    if file_id not in file_mappings:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File ID not found or has expired."
        )

    filepath, original_filename, created_at = file_mappings[file_id]

    # Verify if expired (older than 120 seconds)
    if time.time() - created_at > 120.0:
        # File has expired! Clean it up
        clean_temp_file(filepath, file_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File ID not found or has expired."
        )

    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File no longer exists on server."
        )

    base, _ = os.path.splitext(original_filename)
    sanitized_name = "".join(c for c in base if c.isalnum() or c in "._- ")
    if not sanitized_name:
        sanitized_name = "Redacted"
    download_filename = f"{sanitized_name}_Redacted.docx"

    return FileResponse(
        path=filepath,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=download_filename
    )
