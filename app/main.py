from fastapi import FastAPI, Form
from fastapi.responses import StreamingResponse
import io
from pydantic import BaseModel
from app.generator import generate_abap_code_from_requirement
from app.docx_writer import  create_abap_code_docx

class RequirementInput(BaseModel):
    REQUIREMENT: str

app = FastAPI()
@app.post("/generate-bundle/")
async def generate_fs_ts_abapcode(input_data: RequirementInput):
    requirement = input_data.REQUIREMENT

    abap_code_text = generate_abap_code_from_requirement(requirement)

    abap_code_doc = io.BytesIO()
    create_abap_code_docx(abap_code_text, abap_code_doc)
    abap_code_doc.seek(0)

    print("ABAP bytes:", abap_code_doc.getbuffer().nbytes)

    return StreamingResponse(
        abap_code_doc,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": "attachment; filename=abap_code.docx"}
    )