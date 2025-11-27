import os
import sys

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.run_docker import run_docker_command

def main():
    print("Verifying Docker Bridge (OpenROAD)...")
    
    # 1. Setup a marker file in the workspace
    workspace_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../workspace'))
    if not os.path.exists(workspace_dir):
        os.makedirs(workspace_dir)
        
    marker_file = "docker_test_marker.txt"
    with open(os.path.join(workspace_dir, marker_file), "w") as f:
        f.write("I am inside the workspace!")
        
    print(f"Created marker file: {os.path.join(workspace_dir, marker_file)}")
    
    # 2. Run 'ls /workspace' inside Docker
    print("Running 'ls /workspace' inside Docker container...")
    result = run_docker_command("ls /workspace", workspace_path=workspace_dir)
    
    print(f"Command: {result['command']}")
    
    if result['success']:
        print("✅ Docker Command Executed Successfully")
        print(f"Output:\n{result['stdout']}")
        
        if marker_file in result['stdout']:
            print(f"✅ Volume Mount Verified: Found '{marker_file}' inside container.")
            print("\n🎉 Docker Bridge Verification PASSED!")
            
            # Cleanup
            os.remove(os.path.join(workspace_dir, marker_file))
            sys.exit(0)
        else:
            print("❌ Volume Mount Failed: Marker file not found in output.")
            sys.exit(1)
    else:
        print("❌ Docker Execution Failed")
        print(f"Stderr: {result['stderr']}")
        # Check if it's a daemon issue
        if "daemon is not running" in result['stderr']:
            print("💡 Hint: Is Docker Desktop running?")
        sys.exit(1)

if __name__ == "__main__":
    main()
