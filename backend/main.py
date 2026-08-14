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

# Instantiate engine globally at startup so NLP models are loaded once
engine = RedactionEngine()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
@app.get("/")
async def mainPage():
    return "Welcome to the first page of the PII Redaction Engine API"

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.get("/api/debug")
async def debug():
    import os
    import sys
    
    # Read memory info on Linux
    mem_info = {}
    try:
        if os.path.exists("/proc/self/status"):
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("Vm"):
                        parts = line.strip().split(":")
                        if len(parts) == 2:
                            mem_info[parts[0].strip()] = parts[1].strip()
    except Exception as e:
        mem_info["error"] = str(e)

    # Get active process info
    cmd_line = []
    try:
        if os.path.exists("/proc/self/cmdline"):
            with open("/proc/self/cmdline", "r") as f:
                cmd_line = f.read().split("\x00")
    except Exception:
        pass

    return {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "argv": sys.argv,
        "cmd_line": cmd_line,
        "mem_info": mem_info,
        "env": {k: v for k, v in os.environ.items() if "KEY" not in k.upper() and "SECRET" not in k.upper() and "PASSWORD" not in k.upper() and "TOKEN" not in k.upper()}
    }

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

    mapping = load_file_mapping(file_id)
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File ID not found or has expired."
        )

    filepath, original_filename, created_at = mapping

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

tasks: Dict[str, Dict] = {}

# File-backed helper utilities for multi-process / restart safety
def save_task(task_id: str, data: dict):
    tasks[task_id] = data
    try:
        task_file = os.path.join(TEMP_BASE_DIR, f"task_{task_id}.json")
        import json
        with open(task_file, "w") as f:
            json.dump(data, f)
    except Exception:
        pass

def load_task(task_id: str) -> dict:
    if task_id in tasks:
        return tasks[task_id]
    task_file = os.path.join(TEMP_BASE_DIR, f"task_{task_id}.json")
    if os.path.exists(task_file):
        try:
            import json
            with open(task_file, "r") as f:
                data = json.load(f)
                tasks[task_id] = data
                return data
        except Exception:
            pass
    return None

def save_file_mapping(file_id: str, output_path: str, filename: str, created_at: float):
    file_mappings[file_id] = (output_path, filename, created_at)
    try:
        map_file = os.path.join(TEMP_BASE_DIR, f"map_{file_id}.json")
        import json
        with open(map_file, "w") as f:
            json.dump({"output_path": output_path, "filename": filename, "created_at": created_at}, f)
    except Exception:
        pass

def load_file_mapping(file_id: str):
    if file_id in file_mappings:
        return file_mappings[file_id]
    map_file = os.path.join(TEMP_BASE_DIR, f"map_{file_id}.json")
    if os.path.exists(map_file):
        try:
            import json
            with open(map_file, "r") as f:
                d = json.load(f)
                res = (d["output_path"], d["filename"], d["created_at"])
                file_mappings[file_id] = res
                return res
        except Exception:
            pass
    return None

def run_redaction_task(task_id: str, input_path: str, output_path: str, filename: str):
    try:
        # Run Redaction
        result = engine.redact(input_path, output_path)
        
        if not os.path.exists(output_path):
            raise Exception("Redacted document could not be generated.")
            
        file_id = str(uuid.uuid4())
        created_at = time.time()
        save_file_mapping(file_id, output_path, filename, created_at)
        
        base, _ = os.path.splitext(filename)
        sanitized_name = "".join(c for c in base if c.isalnum() or c in "._- ")
        if not sanitized_name:
            sanitized_name = "Redacted"
        download_filename = f"{sanitized_name}_Redacted.docx"
        
        from datetime import datetime, timezone
        expires_at = datetime.fromtimestamp(created_at + 120.0, tz=timezone.utc).isoformat()
        
        save_task(task_id, {
            "status": "success",
            "result": {
                "success": True,
                "file_id": file_id,
                "filename": download_filename,
                "expires_at": expires_at,
                "total_replacements": result["total_replacements"],
                "replacements_by_type": result["replacements_by_type"],
                "unique_mappings_count": result["unique_mappings_count"]
            }
        })
    except Exception as e:
        save_task(task_id, {
            "status": "error",
            "error": str(e)
        })
    finally:
        # Clean up input file after redaction
        try:
            if os.path.exists(input_path):
                os.remove(input_path)
        except Exception:
            pass
        # Trim memory back to the OS
        import gc
        import platform
        gc.collect()
        if platform.system() == "Linux":
            try:
                import ctypes
                libc = ctypes.CDLL("libc.so.6")
                libc.malloc_trim(0)
            except Exception:
                pass

@app.post("/api/redact-async")
def redact_document_async(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    # Prune expired files on every request
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

    # Create safe unique temporary file names
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

    task_id = str(uuid.uuid4())
    save_task(task_id, {"status": "processing"})
    
    # Run the redaction in the background task
    background_tasks.add_task(run_redaction_task, task_id, input_path, output_path, filename)
    
    return {"task_id": task_id}

@app.get("/api/tasks/{task_id}")
def get_task_status(task_id: str):
    task_data = load_task(task_id)
    if not task_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found."
        )
    return task_data

