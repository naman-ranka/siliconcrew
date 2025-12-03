import os
from src.tools.run_docker import run_docker_command

def test_schematic_gen():
    # Path to the synthesized file (relative to workspace root)
    # The user provided: workspace/level1/orfs_results/sky130hd/up_down_counter/base/1_2_yosys.v
    # Inside container, workspace is mounted at /workspace
    
    input_file = "/workspace/keyword/design.v"
    output_file = "/workspace/schematic.json"
    
    # Yosys command to read verilog and write JSON
    # We use -p to pass a script string
    # We might need to read the liberty file or just let it blackbox the cells
    yosys_cmd = f"yosys -p 'read_verilog {input_file}; hierarchy -top moving_average; proc; opt; write_json {output_file}'"
    
    print(f"Running: {yosys_cmd}")
    
    cwd = os.path.abspath("workspace")
    
    result = run_docker_command(
        command=yosys_cmd,
        workspace_path=cwd
    )
    
    print("STDOUT:", result['stdout'])
    print("STDERR:", result['stderr'])
    
    if result['success']:
        print("Success! Checking for output file...")
        local_output = os.path.join(cwd, "schematic.json")
        if os.path.exists(local_output):
            print(f"Generated: {local_output}")
            print(f"Size: {os.path.getsize(local_output)} bytes")
        else:
            print("Output file not found locally.")
    else:
        print("Failed.")

if __name__ == "__main__":
    test_schematic_gen()
