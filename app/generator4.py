import os
import re
import json
import logging
from typing import Dict, List, Optional
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# --------------------------
# Logger Configuration
# --------------------------
logger = logging.getLogger("abap_generator_single_output")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)

# --------------------------
# Load environment variables
# --------------------------
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path)
openai_api_key = os.getenv("OPENAI_API_KEY")

if openai_api_key:
    os.environ["OPENAI_API_KEY"] = openai_api_key
    logger.info("✅ OpenAI API key loaded successfully.")
else:
    logger.warning("⚠️ OpenAI API key not found in environment variables.")


# --------------------------
# Section Mapping Definition
# --------------------------
DEFAULT_UDD_MAPPING = {
    "global_declaration": ["SECTION: 4. User Interface", "SECTION: 5. Technical Architecture"],
    "selection_screen": ["SECTION: 4. User Interface"],
    "processing_logic": [
        "SECTION: 1. Purpose", "SECTION: 2. Scope", "SECTION: 3. Functional Requirements",
        "SECTION: 4. User Interface", "SECTION: 5. Technical Architecture",
        "SECTION: 6. Error Handling", "SECTION: 7. Performance Notes",
        "SECTION: 8. Authorization", "SECTION: 9. Sample Report Output Layouts",
        "SECTION: 10. Unit Test Plan"
    ],
    "output_display": [
        "SECTION: 4. User Interface", "SECTION: 5. Technical Architecture",
        "SECTION: 6. Error Handling", "SECTION: 7. Performance Notes",
        "SECTION: 9. Sample Report Output Layouts", "SECTION: 10. Unit Test Plan"
    ]
}


# --------------------------
# Helper: Split UDD sections
# --------------------------
def split_sections(payload: str) -> Dict[str, str]:
    """Splits the input requirement document into structured SECTION blocks."""
    logger.info("🔍 Splitting input payload into sections...")

    if isinstance(payload, str):
        data = json.loads(payload)
    elif isinstance(payload, dict):
        data = payload
    else:
        raise ValueError("Payload must be a JSON string or dict")

    document = data.get("REQUIREMENT", "")
    if not document.strip():
        logger.warning("⚠️ Empty requirement text found in payload.")

    # Normalize SECTION headers
    document = re.sub(r"(?<!\n)(SECTION\s*:?\s*\d+\.)", r"\n\1", document)
    document = re.sub(r"SECTION\s*:?\s*\n*\s*(\d+\.\s+[A-Za-z ]+)", r"SECTION: \1", document)
    document = re.sub(r"(SECTION:\s*\d+\.\s+[A-Za-z ]+)", r"\1\n", document)

    sections = re.split(r"(SECTION:\s*\d+\.\s+[A-Za-z ]+)", document)
    result = {}
    current_section = None

    for part in sections:
        part = part.strip()
        if not part:
            continue
        if part.startswith("SECTION:"):
            current_section = part
            result[current_section] = ""
        else:
            if current_section:
                result[current_section] += part.strip() + "\n"

    logger.info(f"📑 Extracted {len(result)} sections from UDD document.")
    return result


# --------------------------
# Helper: Dynamic field extraction
# --------------------------
def extract_fields_dynamic(text: str) -> List[str]:
    """Extracts likely SAP-style field names (technical identifiers)."""
    fields = re.findall(r"\b[A-Z0-9_]{4,}\b", text)
    blacklist = {
        "SELECT", "FROM", "WHERE", "TABLE", "BEGIN", "END", "LOOP", "WRITE",
        "DATA", "TYPE", "INTO", "PERFORM", "MODULE", "REPORT", "CLASS",
        "METHOD", "IF", "ELSE", "ENDIF", "EXPORTING", "IMPORTING", "CLEAR",
        "APPEND", "READ", "OPEN", "CLOSE", "FIELDS", "SET", "GET", "FIELD",
        "MOVE", "SECTION", "ABAP", "PROGRAM", "ZPROGRAM"
    }
    filtered = [f for f in fields if f not in blacklist and not f.isdigit()]
    return sorted(set(filtered))


def compare_fields(requirement_text: str, abap_code: str) -> Dict[str, List[str]]:
    """Compares required fields vs generated ABAP fields."""
    logger.info("🧩 Comparing fields between requirement and ABAP code...")
    req_fields = extract_fields_dynamic(requirement_text)
    code_fields = extract_fields_dynamic(abap_code)

    matched = [f for f in req_fields if f in code_fields]
    missing = [f for f in req_fields if f not in code_fields]
    extra = [f for f in code_fields if f not in req_fields]

    logger.info(f"✅ Matched fields: {len(matched)}, ⚠️ Missing fields: {len(missing)}, ➕ Extra fields: {len(extra)}")
    return {
        "matched_fields": matched,
        "missing_fields": missing,
        "extra_fields": extra,
        "requirement_fields": req_fields,
        "code_fields": code_fields
    }


# --------------------------
# LLM-based requirement coverage validation
# --------------------------
def validate_requirement_coverage(llm, requirements_text: str, abap_code: str) -> str:
    """Uses an LLM to analyze requirement coverage."""
    logger.info("🧠 Running LLM-based requirement coverage validation...")

    review_prompt = f"""
    You are a senior SAP ABAP solution architect performing a code validation review.
    Compare the following Functional Requirements and Generated ABAP Code.

    For each major requirement, evaluate:
    - Fully implemented
    - Partially implemented
    - Not implemented

    Provide a short justification and an overall summary.
    Return JSON in this format:
    {{
      "requirement_coverage": [
        {{
          "requirement": "<summary>",
          "status": "<Fully Implemented | Partially Implemented | Not Implemented>",
          "explanation": "<reason>"
        }}
      ],
      "final_summary": "<overall assessment>"
    }}

    Functional Requirements:
    {requirements_text}

    ABAP Code:
    {abap_code}
    """

    response = llm.invoke(review_prompt)
    output = response.content if hasattr(response, "content") else str(response)
    logger.info("📋 LLM validation completed.")
    return output.strip()


# --------------------------
# Main Logic: Generate Full ABAP Program
# --------------------------
def generate_full_abap_program(
    payload: str,
    udd_mapping: Optional[Dict[str, List[str]]] = None
) -> Dict[str, str]:
    """Generates, refines, and validates an ABAP report dynamically."""
    logger.info("🚀 Starting ABAP generation process...")

    udd_mapping = udd_mapping or DEFAULT_UDD_MAPPING
    sections_dict = split_sections(payload)

    # Collect relevant requirement text
    combined_requirements = []
    for mapped_list in udd_mapping.values():
        for section in mapped_list:
            if section in sections_dict:
                combined_requirements.append(sections_dict[section])
    logger.info(f"📚 Collected {len(combined_requirements)} relevant sections for ABAP generation.")

    all_requirements = "\n\n".join(combined_requirements).strip()
    if not all_requirements:
        logger.error("❌ No valid sections found in input payload.")
        raise ValueError("No valid sections found in input payload.")

    # Initialize LLM
    logger.info("⚙️ Initializing ChatOpenAI model...")
    llm = ChatOpenAI(
        model="gpt-5",
        temperature=0.2,
        api_key=openai_api_key,
    )

    # -----------------------
    # PASS 1: Generate ABAP draft
    # -----------------------
    logger.info("🧱 Generating initial ABAP draft from requirements...")
    draft_prompt = f"""
    You are a senior SAP ABAP developer.
    Generate a complete ABAP report program based on the following requirements.
    Use modularization, meaningful comments, and correct syntax.
    Only return ABAP code (no markdown).
    If ALV Output - you must not miss any field mentioned in the requirement.

    Functional and technical requirements:
    {all_requirements}
    """

    draft_response = llm.invoke(draft_prompt)
    draft_code = draft_response.content if hasattr(draft_response, "content") else str(draft_response)
    draft_code = re.sub(r"```(?:abap)?|```", "", draft_code).strip()
    logger.info("✅ Draft ABAP code generated successfully.")

    # -----------------------
    # PASS 2: Refine ABAP code
    # -----------------------
    logger.info("🧹 Refining ABAP code for standards, readability, and syntax...")
    refine_prompt = f"""
    You are an expert ABAP reviewer.
    Review and improve the following ABAP program:
    - Ensure indentation and spacing are consistent.
    - Use lv_, lt_, ls_ prefixes.
    - Add comments for each logic block.
    - Optimize redundant logic and fix syntax issues.
    Return only the final refined ABAP code.

    ABAP Code:
    {draft_code}
    """

    refine_response = llm.invoke(refine_prompt)
    refined_code = refine_response.content if hasattr(refine_response, "content") else str(refine_response)
    refined_code = re.sub(r"```(?:abap)?|```", "", refined_code).strip()
    logger.info("✨ ABAP code refinement completed successfully.")

    # -----------------------
    # PASS 3: Field Validation
    # -----------------------
    field_comparison = compare_fields(all_requirements, refined_code)
    if field_comparison["missing_fields"]:
        logger.warning(f"⚠️ Missing fields in ABAP Output: {field_comparison['missing_fields']}")
    else:
        logger.info("✅ All required fields are covered in ABAP output.")

    # -----------------------
    # PASS 4: Requirement Fulfillment
    # -----------------------
    validation_report = validate_requirement_coverage(llm, all_requirements, refined_code)
    logger.info("📊 Requirement coverage validation finished successfully.")

    # -----------------------
    # Return Final Structured Output
    # -----------------------
    logger.info("🏁 ABAP generation process completed successfully.")
    # return {
    #     "abap_code": refined_code,
        # "field_analysis": field_comparison,
        # "requirement_validation": validation_report
    # }
    return refined_code
