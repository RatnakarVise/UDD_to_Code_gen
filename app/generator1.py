import os
import re
import json
import logging
from typing import Dict, List, Optional
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

logger = logging.getLogger("abap_generator")
logging.basicConfig(level=logging.INFO)

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path)
langchain_api_key = os.getenv("LANGCHAIN_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")
if langchain_api_key:
    os.environ["LANGCHAIN_API_KEY"] = langchain_api_key
if openai_api_key:
    os.environ["OPENAI_API_KEY"] = openai_api_key
os.environ["LANGCHAIN_TRACING_V2"] = "true"

ABAP_SECTIONS = [
    "global_declaration",
    "selection_screen",
    "processing_logic",
    "output_display",
]

DEFAULT_UDD_MAPPING = {
    "selection_screen": ["SECTION: 4. User Interface"],
    "global_declaration": ["SECTION: 4. User Interface", "SECTION: 5. Technical Architecture"],
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

def split_sections(payload: str) -> Dict[str, str]:
    if isinstance(payload, str):
        data = json.loads(payload)
    elif isinstance(payload, dict):
        data = payload
    else:
        raise ValueError("Payload must be a JSON string or dict")

    document = data.get("REQUIREMENT", "")

    # 1️⃣ Ensure SECTION headers always start on a new line
    document = re.sub(r"(?<!\n)(SECTION\s*:?\s*\d+\.)", r"\n\1", document)

    # 2️⃣ Normalize SECTION header variants (handles SECTION:1. Purpose, SECTION 1. Purpose, etc.)
    document = re.sub(
        r"SECTION\s*:?\s*\n*\s*(\d+\.\s+[A-Za-z ]+)",
        r"SECTION: \1",
        document
    )

    # 3️⃣ Ensure newline right after SECTION headers
    document = re.sub(
        r"(SECTION:\s*\d+\.\s+[A-Za-z ]+)",
        r"\1\n",
        document
    )

    # 4️⃣ Split into sections
    sections = re.split(r"(SECTION:\s*\d+\.\s+[A-Za-z ]+)", document)

    result = {}
    current_section = None
    for part in sections:
        part = part.strip()
        if not part:
            continue
        if part.startswith("SECTION:"):
            match = re.match(r"(SECTION:\s*\d+\.\s+[A-Za-z ]+)", part)
            if match:
                current_section = match.group(1).strip()
                if current_section not in result:
                    result[current_section] = ""
        else:
            if current_section:
                result[current_section] += part.strip() + "\n"
    return result


def process_payload_and_generate_abap(
    payload: str,
    udd_mapping: Optional[Dict[str, List[str]]] = None
) -> Dict[str, str]:
    udd_mapping = udd_mapping or DEFAULT_UDD_MAPPING
    sections_dict = split_sections(payload)

    abap_result = {}
    llm = ChatOpenAI(model="gpt-5", temperature=0.2)

    for abap_section in ABAP_SECTIONS:
        mapped_sections = udd_mapping.get(abap_section, [])
        combined_requirements = "\n\n".join(
            sections_dict.get(sec, "") for sec in mapped_sections if sec in sections_dict
        )

        if not combined_requirements:
            abap_result[abap_section] = "[Error: No requirements found]"
            continue

        # ✅ Progressive context passing
        context_parts = []
        if abap_section == "selection_screen":
            context_parts.append(abap_result.get("global_declaration", ""))
        elif abap_section == "processing_logic":
            context_parts.append(abap_result.get("global_declaration", ""))
            context_parts.append(abap_result.get("selection_screen", ""))
        elif abap_section == "output_display":
            context_parts.append(abap_result.get("global_declaration", ""))
            context_parts.append(abap_result.get("selection_screen", ""))
            context_parts.append(abap_result.get("processing_logic", ""))

        context_code = "\n\n".join([c for c in context_parts if c])

        prompt = f"""
You are an expert ABAP developer.
Generate ONLY the **{abap_section.replace('_',' ')}** part of the ABAP program.

Rules:
- Do NOT include REPORT statement.
- Do NOT include unrelated sections.
- Only return ABAP code for this section.
- No explanations, only ABAP code.

{"Here is the code from previous sections:\n" + context_code if context_code else ""}

Requirements:
{combined_requirements}
"""

        response = llm.invoke(prompt)
        output = response.content if hasattr(response, "content") else str(response)
        abap_result[abap_section] = output.strip()

    return abap_result


def assemble_program(abap_parts: Dict[str, str]) -> str:
    return "\n\n".join([
        abap_parts.get("global_declaration", ""),
        abap_parts.get("selection_screen", ""),
        abap_parts.get("processing_logic", ""),
        abap_parts.get("output_display", ""),
    ])
