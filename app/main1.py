import os
import uuid
import io
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from app.generator1 import process_payload_and_generate_abap
from app.docx_writer1 import create_abap_code_docx

app = FastAPI(title="ABAP Code Generator")

# In-memory job store (⚠️ not for production)
JOBS = {}

def generate_abap_doc_background(payload: dict, job_id: str):
    """
    Background job: 
    1. Split payload into sections
    2. Generate ABAP code for each section
    3. Write into DOCX file
    """
    try:
        # Generate ABAP codes for all sections
        abap_results = process_payload_and_generate_abap(payload)

        # Save ABAP code into DOCX
        output_filename = f"ABAP_Code_{job_id}.docx"
        output_path = os.path.abspath(output_filename)

        abap_code_doc = io.BytesIO()
        create_abap_code_docx(abap_results, abap_code_doc)
        with open(output_path, "wb") as f:
            f.write(abap_code_doc.getvalue())

        JOBS[job_id]["status"] = "done"
        JOBS[job_id]["file_path"] = output_path

    except Exception as e:
        JOBS[job_id]["status"] = "failed"
        JOBS[job_id]["error"] = str(e)


@app.post("/generate_abap_doc")
async def generate_abap_doc(payload: dict, background_tasks: BackgroundTasks):
    """
    POST endpoint to start ABAP doc generation.
    Returns job_id immediately; job runs in background.
    """
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {"status": "pending", "file_path": None, "error": None}
    background_tasks.add_task(generate_abap_doc_background, payload, job_id)
    return {"job_id": job_id, "status": "started"}


@app.get("/generate_abap_doc/{job_id}")
async def get_abap_doc(job_id: str):
    """
    GET endpoint to check job status or download the file when ready.
    """
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Invalid job_id")

    if job["status"] == "pending":
        return {"status": "pending"}

    if job["status"] == "failed":
        return JSONResponse(
            status_code=500,
            content={"status": "failed", "error": job["error"]}
        )

    if job["status"] == "done":
        return FileResponse(
            job["file_path"],
            filename=os.path.basename(job["file_path"]),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
