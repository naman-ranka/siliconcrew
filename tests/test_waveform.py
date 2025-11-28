import os
import sys

# Add src to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.read_waveform import read_waveform

def create_dummy_vcd(filename):
    content = """$date
    Nov 27 2025
$end
$version
    Icarus Verilog
$end
$timescale
    1s
$end
$scope module tb $end
$var wire 1 ! clk $end
$var wire 1 " rst $end
$var wire 8 # count [7:0] $end
$upscope $end
$enddefinitions
$end
#0
$dumpvars
0!
1"
b00000000 #
$end
#5
1!
#10
0!
0"
#15
1!
b00000001 #
#20
0!
"""
    with open(filename, "w") as f:
        f.write(content)

def main():
    vcd_file = "test.vcd"
    create_dummy_vcd(vcd_file)
    
    print("Testing read_waveform...")
    
    # Test 1: Read all signals
    print("\n--- Test 1: All Signals ---")
    output = read_waveform(vcd_file, ["clk", "rst", "count"], start_time=0, end_time=20)
    print(output)
    
    # Test 2: Specific Window
    print("\n--- Test 2: Window 10-20 ---")
    output = read_waveform(vcd_file, ["clk", "count"], start_time=10, end_time=20)
    print(output)
    
    # Clean up
    if os.path.exists(vcd_file):
        os.remove(vcd_file)

if __name__ == "__main__":
    main()
