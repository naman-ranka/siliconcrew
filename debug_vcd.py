from vcdvcd import VCDVCD
import os

vcd_path = r"c:\Users\naman\Desktop\Projects\RTL_AGENT\workspace\level1\waveform.vcd"

if not os.path.exists(vcd_path):
    print(f"File not found: {vcd_path}")
    # Try finding any vcd
    for root, dirs, files in os.walk(r"c:\Users\naman\Desktop\Projects\RTL_AGENT"):
        for f in files:
            if f.endswith(".vcd"):
                vcd_path = os.path.join(root, f)
                print(f"Found alternative: {vcd_path}")
                break
        if vcd_path: break

try:
    vcd = VCDVCD(vcd_path)
    signals = vcd.get_signals()
    print(f"Signals found: {len(signals)}")
    
    # Find a bus signal (likely 'count' or brackets)
    bus_sig = None
    for s in signals:
        if "[" in s:
            bus_sig = s
            break
            
    if bus_sig:
        print(f"Inspecting Bus: {bus_sig}")
        tv = vcd[bus_sig].tv
        print(f"First 5 values: {tv[:5]}")
        
        # Check type of value
        val = tv[0][1]
        print(f"Value type: {type(val)}")
        print(f"Value example: '{val}'")
    else:
        print("No bus signal found.")
        
except Exception as e:
    print(f"Error: {e}")
