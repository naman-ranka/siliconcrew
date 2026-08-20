import os
import sys
from dotenv import load_dotenv

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from langchain_core.messages import SystemMessage
from src.agents.architect import create_architect_agent, load_system_prompt

def main():
    load_dotenv()
    if not os.environ.get("GOOGLE_API_KEY"):
        print("❌ GOOGLE_API_KEY not found.")
        sys.exit(1)
        
    print("Verifying The Architect (Autonomous Agent)...")
    
    agent_graph = create_architect_agent()
    
    # Goal: A simple design that is easy to verify and synthesize
    goal = "Design a 2-to-1 Multiplexer (module mux2) and a self-checking testbench. Verify it, then synthesize it and report the area."
    
    print(f"Goal: {goal}")
    print("---------------------------------------------------")
    
    try:
        # Run the agent
        # We use a recursion limit to prevent infinite loops
        events = agent_graph.stream(
            {"messages": [SystemMessage(content=load_system_prompt()), ("user", goal)]},
            {"recursion_limit": 50}
        )
        
        for event in events:
            for key, value in event.items():
                if key == "agent":
                    # Print the agent's thought/action
                    # The last message is usually the AIMessage
                    last_msg = value["messages"][-1]
                    print(f"🤖 Architect: {last_msg.content[:200]}...") # Truncate for readability
                elif key == "tools":
                    # Print tool output
                    last_msg = value["messages"][-1]
                    print(f"🛠️ Tool Output: {last_msg.content[:200]}...")
                    
        print("\n---------------------------------------------------")
        print("✅ Architect Execution Finished.")
        
        # Verify artifacts
        workspace = os.path.abspath(os.path.join(os.path.dirname(__file__), '../workspace'))
        design_file = os.path.join(workspace, "design.v")
        tb_file = os.path.join(workspace, "tb.v")
        
        if os.path.exists(design_file) and os.path.exists(tb_file):
            print("✅ Verilog files created.")
        else:
            print("❌ Verilog files missing.")
            
    except Exception as e:
        print(f"❌ Execution Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
