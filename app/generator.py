import os
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

# load_dotenv()
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path)
langchain_api_key = os.getenv("LANGCHAIN_API_KEY")
openai_api_key = os.getenv("OPENAI_API_KEY")
if langchain_api_key:
    os.environ["LANGCHAIN_API_KEY"] = langchain_api_key
if openai_api_key:
    os.environ["OPENAI_API_KEY"] = openai_api_key
os.environ["LANGCHAIN_TRACING_V2"] = "true"

def generate_abap_code_from_requirement(requirement: str) -> str:
    """
    Generate ABAP code strictly from the requirement, without using any template.
    """
    print(f"OPENAI_API_KEY: {openai_api_key}")
    prompt_template = ChatPromptTemplate.from_template(
        "You are an expert ABAP developer.\n\n"
        "REQUIREMENT:\n{requirement}\n\n"
        "Write production-ready, well-commented ABAP code to fulfill the REQUIREMENT above. "
        "Use modern, readable ABAP, include meaningful comments, and follow best practices. "
        "Only output the ABAP code. Do not use Markdown or code fences."
    )

    messages = prompt_template.format_messages(requirement=requirement)

    llm = ChatOpenAI(model="gpt-5", temperature=0.2)
    response = llm.invoke(messages)
    return response.content if hasattr(response, "content") else str(response)