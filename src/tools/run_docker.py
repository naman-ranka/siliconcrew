import subprocess
import os
import sys

def run_docker_command(command, image="openroad/orfs:latest", cwd="/OpenROAD-flow-scripts/flow", workspace_path=None):
    """
    Executes a command inside the OpenROAD Docker container.
    
    Args:
        command (str or list): The command to run inside the container.
        image (str): The Docker image to use.
        cwd (str): Working directory inside the container.
        workspace_path (str): Absolute path to the local workspace directory. 
                              If None, defaults to ../../workspace relative to this file.
        
    Returns:
        dict: {
            "success": bool,
            "stdout": str,
            "stderr": str,
            "command": str
        }
    """
    
    # Resolve workspace path
    if workspace_path is None:
        # Assuming this file is in src/tools/
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        workspace_path = os.path.join(base_path, "workspace")
    
    # Ensure workspace exists
    if not os.path.exists(workspace_path):
        os.makedirs(workspace_path)

    # Convert command list to string if necessary
    if isinstance(command, list):
        command = " ".join(command)

    # Construct Docker command
    # We use --rm to clean up the container after exit
    # We mount the workspace to /workspace
    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{workspace_path}:/workspace",
        "-w", cwd,
        image,
        "bash", "-c", command
    ]

    try:
        # Run the command
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": " ".join(docker_cmd)
        }
        
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Docker Execution Error: {str(e)}",
            "command": " ".join(docker_cmd)
        }
