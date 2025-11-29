from typing import Literal
from langgraph.graph import StateGraph, END
from src.state.state import DesignState
from src.agents.architect import architect_node
from src.agents.verifier import verifier_node
from src.agents.ppa_analyst import ppa_analyst_node

def route_verifier(state: DesignState) -> Literal["architect", "ppa_analyst"]:
    """
    Routing logic after verification.
    If valid -> Go to PPA Analyst.
    If invalid -> Go back to Architect to fix bugs.
    """
    # Check if we exceeded max iterations to prevent infinite loops
    if state.get("iteration_count", 0) > state.get("max_iterations", 5):
        return "ppa_analyst" # Force exit (or handle failure)

    if state.get("functional_valid", False):
        return "ppa_analyst"
    else:
        return "architect"

def create_workflow_graph():
    """
    Constructs the Multi-Agent State Graph.
    """
    workflow = StateGraph(DesignState)

    # 1. Add Nodes
    workflow.add_node("architect", architect_node)
    workflow.add_node("verifier", verifier_node)
    workflow.add_node("ppa_analyst", ppa_analyst_node)

    # 2. Add Edges
    # Start -> Architect
    workflow.set_entry_point("architect")

    # Architect -> Verifier (Always)
    workflow.add_edge("architect", "verifier")

    # Verifier -> (Conditional) -> Architect or Analyst
    workflow.add_conditional_edges(
        "verifier",
        route_verifier,
        {
            "architect": "architect",
            "ppa_analyst": "ppa_analyst"
        }
    )

    # Analyst -> End
    workflow.add_edge("ppa_analyst", END)

    return workflow.compile()
