from typing import TypedDict, List, Optional, Dict, Any

class DesignState(TypedDict):
    """
    Represents the state of the design process in the multi-agent system.
    """
    # Input Specification
    design_spec: str
    
    # Current Artifacts
    verilog_code: str
    testbench_code: str
    
    # Feedback & History
    iteration_count: int
    max_iterations: int
    error_logs: List[str]  # Linter or Simulation errors
    
    # Status Flags
    syntax_valid: bool
    functional_valid: bool
    
    # Physical Design Metrics (Phase 3)
    ppa_metrics: Dict[str, Any] # { "area": float, "slack": float, "power": float }
    
    # Agent Communication
    current_agent: str
    messages: List[Any] # LangChain messages
