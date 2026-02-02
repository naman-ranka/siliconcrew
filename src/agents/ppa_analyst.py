import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv
from src.state.state import DesignState
from src.tools.get_ppa import get_ppa_metrics
from src.config import DEFAULT_MODEL

load_dotenv()

# Initialize LLM
llm = ChatGoogleGenerativeAI(model=DEFAULT_MODEL, google_api_key=os.environ.get("GOOGLE_API_KEY"))

SYSTEM_PROMPT = """You are an expert Digital Design Engineer specializing in PPA (Power, Performance, Area) Optimization.
Your goal is to analyze the synthesis results of a Verilog design and provide insights.

Input:
1. Design Specification
2. Extracted PPA Metrics (Area, Cell Count, Timing, Power)
3. Synthesis Log/Report Snippets (if available)

Output:
A concise analysis of the design's quality.
- If the design meets typical expectations for such a spec.
- Identify any obvious issues (e.g., zero area, huge cell count for simple logic).
- Suggest 1-2 potential optimizations if applicable.

Format your response as a structured summary.
"""

def ppa_analyst_node(state: DesignState) -> DesignState:
    """
    Agent node that extracts PPA metrics and analyzes them.
    """
    print("[PPA] PPA Analyst: Extracting and Analyzing Metrics...")
    
    # 1. Extract Metrics using the Tool
    # We assume logs are in workspace/orfs_logs relative to the project root
    # We need to resolve the path dynamically
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../workspace'))
    logs_dir = os.path.join(base_path, "orfs_logs")
    
    metrics = get_ppa_metrics(logs_dir)
    
    # 2. Construct Prompt for LLM Analysis
    metrics_str = f"""
    Area: {metrics.get('area_um2', 'N/A')} um^2
    Cell Count: {metrics.get('cell_count', 'N/A')}
    WNS (Timing): {metrics.get('wns_ns', 'N/A')} ns
    Power: {metrics.get('power_uw', 'N/A')} uW
    Errors: {metrics.get('errors', [])}
    """
    
    user_message = f"""
    Design Spec: {state['design_spec']}
    
    Measured PPA Metrics:
    {metrics_str}
    
    Please analyze these results.
    """
    
    # 3. Call LLM
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_message)
    ])
    
    analysis = response.content
    print(f"[PPA] Analysis:\n{analysis}")
    
    # 4. Update State
    # We update ppa_metrics and append the analysis to messages
    return {
        "ppa_metrics": metrics,
        "messages": [f"PPA Analysis: {analysis}"]
    }
