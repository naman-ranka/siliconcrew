import os
import sys
from dotenv import load_dotenv

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.graph.workflow import create_workflow_graph

def main():
    load_dotenv()
    if not os.environ.get("GOOGLE_API_KEY"):
        print("❌ GOOGLE_API_KEY not found.")
        sys.exit(1)

    print("🚀 Initializing SiliconCrew Multi-Agent System...")

    # 1. Create the Graph
    workflow = create_workflow_graph()

    # 2. Define the Goal
    goal = "Design a 4-bit Up-Counter with asynchronous reset and enable."
    
    print(f"🎯 Goal: {goal}")
    print("---------------------------------------------------")
    
    # 3. Initialize State
    initial_state = {
        "design_spec": goal,
        "iteration_count": 0,
        "max_iterations": 5, # Safety limit
        "error_logs": [],
        "messages": []
    }
    
    # 4. Run the Graph
    try:
        # stream() yields events as the graph transitions
        events = workflow.stream(initial_state)
        
        for event in events:
            # event is a dict like {'architect': {updated_state_subset}}
            for node_name, state_update in event.items():
                print(f"\n🔄 Node '{node_name}' Finished.")
                if "error_logs" in state_update and state_update["error_logs"]:
                     print(f"   Errors: {len(state_update['error_logs'])}")
                if "functional_valid" in state_update:
                     print(f"   Functional Valid: {state_update['functional_valid']}")

        print("\n---------------------------------------------------")
        print("✅ Workflow Execution Finished.")
            
    except Exception as e:
        print(f"❌ Execution Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
