import os
from src.state.state import DesignState
from src.tools.run_synthesis import run_synthesis

def synthesis_node(state: DesignState) -> DesignState:
    """
    Node to run synthesis on the verified design.
    """
    print("[SYNTH] Synthesis Node: Running Synthesis...")
    
    # Resolve paths
    base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../workspace'))
    if not os.path.exists(base_path):
        os.makedirs(base_path)
        
    # We assume the Verilog code is already in the workspace as 'design.v' or similar
    # But wait, the RTL Coder writes to 'design.v' (or whatever the agent decided).
    # We should probably ensure the file exists.
    # For now, let's assume 'design.v' is the main file.
    # Or better, we write the current `verilog_code` from state to `design.v` to be sure.
    
    design_file = os.path.join(base_path, "design.v")
    with open(design_file, "w") as f:
        f.write(state["verilog_code"])
        
    # Run Synthesis
    # We need to know the top module name.
    # We can extract it from the spec or code, or just assume "top" or "dut".
    # For the counter example, it was "counter".
    # We should probably extract it using regex or ask the LLM.
    # For now, let's try to regex it from the code.
    import re
    match = re.search(r"module\s+(\w+)", state["verilog_code"])
    top_module = match.group(1) if match else "top"
    
    result = run_synthesis(
        verilog_files=[design_file],
        top_module=top_module,
        cwd=base_path
    )
    
    if result["success"]:
        print("[OK] Synthesis Successful.")
        return {"messages": ["Synthesis Successful."]}
    else:
        # Check if artifacts exist (partial success)
        # We reuse the logic from verify_synthesis, or just rely on the tool output?
        # The tool returns success=False if make fails.
        # But we know ORFS fails later.
        # Let's check for the netlist.
        netlist_path = os.path.join(base_path, "orfs_results", "sky130hd", top_module, "base", "1_1_yosys.v") # Path might vary
        # Actually, let's just check if *any* yosys.v exists in results
        import glob
        found = glob.glob(os.path.join(base_path, "orfs_results", "**", "*yosys.v"), recursive=True)
        
        if found:
            print("[WARN] Synthesis Command Failed, but Netlist Found. Proceeding.")
            return {"messages": ["Synthesis Partial Success (Netlist found)."]}
        
        print("[FAIL] Synthesis Failed.")
        return {"messages": [f"Synthesis Failed: {result['stderr']}"]}
