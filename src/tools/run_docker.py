import subprocess
import os
import sys

def run_docker_command(command, image="openroad/orfs:latest", cwd="/OpenROAD-flow-scripts/flow", workspace_path=None, volumes=None, timeout=600):
    """
    Executes a command inside the OpenROAD Docker container.
    
    Args:
        command (str or list): The command to run inside the container.
        image (str): The Docker image to use.
        cwd (str): Working directory inside the container.
        workspace_path (str): Absolute path to the local workspace directory. 
                              If None, defaults to ../../workspace relative to this file.
        volumes (list): Optional list of volume mappings ["host_path:container_path"].
        timeout (int): Timeout in seconds (default 600s = 10m).
        
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
        "-v", f"{workspace_path}:/workspace"
    ]
    
    # Add custom volumes
    if volumes:
        for vol in volumes:
            docker_cmd.extend(["-v", vol])

    docker_cmd.extend([
        "-w", cwd,
        image,
        "bash", "-c", command
    ])

    proc = None
    try:
        # Run the command
        proc = subprocess.Popen(
            docker_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        
        return {
            "success": proc.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "command": " ".join(docker_cmd)
        }
        
    except subprocess.TimeoutExpired:
        if proc: proc.kill()
        return {
            "success": False,
            "stdout": "",
            "stderr": "Error: Docker command timed out.",
            "command": " ".join(docker_cmd)
        }
    except Exception as e:
        if proc: proc.kill()
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Docker Execution Error: {str(e)}",
            "command": " ".join(docker_cmd)
        }
    finally:
        if proc and proc.poll() is None:
            proc.kill()
