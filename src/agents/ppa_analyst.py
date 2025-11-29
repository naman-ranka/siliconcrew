import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage
from dotenv import load_dotenv
from src.state.state import DesignState
from src.tools.run_synthesis import run_synthesis
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
    Agent node that runs Synthesis, extracts PPA metrics, and analyzes them.
    """
    print("🚀 PPA Analyst: Running Synthesis and Analyzing Metrics...")
    
    # 0. Setup Workspace
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../workspace'))
    design_file = os.path.join(workspace_dir, "design.v")
    
    # 1. Run Synthesis
    # We assume top module is 'design' or we need to infer it.
    # Ideally, we should parse the code to find top module, or ask State.
    # For now, let's assume the Architect named the top module based on spec or standard 'design'
    # Hack: We grep the file for 'module <name>'
    top_module = "design" # Default
    if os.path.exists(design_file):
        with open(design_file, "r") as f:
            for line in f:
                if line.strip().startswith("module"):
                    parts = line.split()
                    if len(parts) > 1:
                        top_module = parts[1].split("(")[0].split(";")[0]
                        break

    print(f"   Synthesis Target: {top_module}")
    synth_result = run_synthesis([design_file], top_module=top_module, cwd=workspace_dir)

    if not synth_result["success"]:
        print("❌ Synthesis Failed.")
        return {
            "messages": [f"Synthesis Failed. Log: {synth_result['stderr'][-500:]}"]
        }

    # 2. Extract Metrics using the Tool
    logs_dir = os.path.join(workspace_dir, "orfs_logs")
    metrics = get_ppa_metrics(logs_dir)
    
    # 3. Construct Prompt for LLM Analysis
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
    
    # 4. Call LLM
    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_message)
    ])
    
    analysis = response.content
    print(f"📊 Analysis:\n{analysis}")
    
    # 5. Update State
    return {
        "ppa_metrics": metrics,
        "messages": [f"PPA Analysis: {analysis}"]
    }
