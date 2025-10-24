import os
import re
import json
import logging
from typing import Dict, List, Optional
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

logger = logging.getLogger("abap_generator_single_output")
logging.basicConfig(level=logging.INFO)

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path)
openai_api_key = os.getenv("OPENAI_API_KEY")

if openai_api_key:
    os.environ["OPENAI_API_KEY"] = openai_api_key

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
# Helper: Split document into UDD sections
# --------------------------
def split_sections(payload: str) -> Dict[str, str]:
    """Splits the input requirement document into structured SECTION blocks."""
    if isinstance(payload, str):
        data = json.loads(payload)
    elif isinstance(payload, dict):
        data = payload
    else:
        raise ValueError("Payload must be a JSON string or dict")

    document = data.get("REQUIREMENT", "")

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

    return result


def validate_requirement_coverage(llm, requirements_text: str, abap_code: str) -> str:
    """
    Uses an LLM to analyze whether the ABAP code fully meets the given requirements.
    Returns a structured JSON-like summary.
    """
    review_prompt = f"""
    You are a senior SAP ABAP solution architect performing a code validation review.
    Your task: Compare the following **Functional Requirements** and the **Generated ABAP Code**.
    For each major requirement, evaluate:
    - Fully implemented
    - Partially implemented
    - Not implemented

    Then provide:
    1. A brief justification for each item.
    2. A final overall summary stating whether the ABAP program fully fulfills all requirements.

    Return your answer in JSON format with this schema:
    {{
      "requirement_coverage": [
        {{
          "requirement": "<summary>",
          "status": "<Fully Implemented | Partially Implemented | Not Implemented>",
          "explanation": "<short reason>"
        }}
      ],
      "final_summary": "<overall statement>"
    }}

    Functional Requirements: {requirements_text}
    ABAP Code: {abap_code}
    """

    review_response = llm.invoke(review_prompt)
    output = review_response.content if hasattr(review_response, "content") else str(review_response)
    return output.strip()


# --------------------------
# Main Logic: Generate Full ABAP Code
# --------------------------
def generate_full_abap_program(
    payload: str,
    udd_mapping: Optional[Dict[str, List[str]]] = None
) -> str:
    """Generates and refines a unified ABAP program using a two-pass LLM pipeline."""
    udd_mapping = udd_mapping or DEFAULT_UDD_MAPPING
    sections_dict = split_sections(payload)

    # Collect relevant UDD content
    combined_requirements = []
    for mapped_list in udd_mapping.values():
        for section in mapped_list:
            if section in sections_dict:
                combined_requirements.append(sections_dict[section])

    all_requirements = "\n\n".join(combined_requirements).strip()
    if not all_requirements:
        raise ValueError("No valid sections found in input payload.")

    # Initialize the LLM
    llm = ChatOpenAI(
        model="gpt-5",
        temperature=0.2,
        api_key=openai_api_key,
        # base_url="https://genai-sharedservice-americas.pwcinternal.com"
    )

    # -----------------------
    # PASS 1: Generate initial draft
    # -----------------------
    draft_prompt = f"""
    You are a senior SAP ABAP developer.
    Generate a complete ABAP report program based on the following requirements.
    Use clear modularization, meaningful comments, and correct syntax.
    Only return ABAP code, no markdown or explanations.
    If ALV Output - you should not miss a single field mentioned in the requirement. This is Mandatory.

    Functional and technical requirements:
    {all_requirements}
    """

    draft_response = llm.invoke(draft_prompt)
    draft_code = draft_response.content if hasattr(draft_response, "content") else str(draft_response)
    draft_code = re.sub(r"```(?:abap)?|```", "", draft_code).strip()

    # -----------------------
    # PASS 2: Refine the code
    # -----------------------
    refine_prompt = f"""
    You are an expert ABAP reviewer.
    Review and improve the following ABAP program:
    - Ensure indentation and spacing are consistent.
    - Use proper naming conventions (lv_, lt_, ls_ prefixes).
    - Add or refine comments for each major logic block.
    - Optimize redundant logic and fix minor syntax errors.
    - Do not change program intent.
    - Return only the final, refined ABAP code (no explanations or markdown).

    ABAP Code:
    {draft_code}
    """

    # refine_response = llm.invoke(refine_prompt)
    # refined_code = refine_response.content if hasattr(refine_response, "content") else str(refine_response)
    # refined_code = re.sub(r"```(?:abap)?|```", "", refined_code).strip()

    # Pass 3: Validate Requirement Fulfillment
    # validation_report = validate_requirement_coverage(llm, all_requirements, refined_code)
    # print(validation_report)
    return draft_code
    # return refined_code
