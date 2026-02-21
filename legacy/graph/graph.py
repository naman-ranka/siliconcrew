from langgraph.graph import StateGraph, END
from src.state.state import DesignState
from src.agents.rtl_coder import rtl_coder_node
from src.agents.verifier import verifier_node

from src.agents.synthesis_agent import synthesis_node
from src.agents.ppa_analyst import ppa_analyst_node

def increment_iteration(state: DesignState) -> DesignState:
    """Updates the iteration count."""
    return {"iteration_count": state["iteration_count"] + 1}

def route_after_verifier(state: DesignState):
    """
    Decides the next step after verification.
    """
    if state["functional_valid"]:
        print("[OK] Design Verified! Proceeding to Synthesis.")
        return "synthesis"
    
    if state["iteration_count"] >= state["max_iterations"]:
        print("[STOP] Max iterations reached. Stopping.")
        return END
        
    print(f"[RETRY] Verification Failed. Iteration {state['iteration_count']}/{state['max_iterations']}. Routing back to Coder.")
    return "rtl_coder"

def create_graph():
    workflow = StateGraph(DesignState)
    
    # Add Nodes
    workflow.add_node("rtl_coder", rtl_coder_node)
    workflow.add_node("verifier", verifier_node)
    workflow.add_node("update_iter", increment_iteration)
    workflow.add_node("synthesis", synthesis_node)
    workflow.add_node("ppa_analyst", ppa_analyst_node)
    
    # Define Edges
    # Start -> Coder
    workflow.set_entry_point("rtl_coder")
    
    # Coder -> Verifier
    workflow.add_edge("rtl_coder", "verifier")
    
    # Verifier -> Update Iteration -> Router
    workflow.add_edge("verifier", "update_iter")
    
    # Conditional Edge from Verifier (via update_iter)
    workflow.add_conditional_edges(
        "update_iter",
        route_after_verifier,
        {
            "rtl_coder": "rtl_coder",
            "synthesis": "synthesis",
            END: END
        }
    )
    
    # Synthesis -> PPA Analyst
    workflow.add_edge("synthesis", "ppa_analyst")
    
    # PPA Analyst -> End (for now)
    workflow.add_edge("ppa_analyst", END)
    
    return workflow.compile()
