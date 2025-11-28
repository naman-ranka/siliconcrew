import os
import sys

def read_waveform(vcd_file: str, signals: list[str], start_time: int = 0, end_time: int = 1000) -> str:
    """
    Reads a VCD file and extracts the values of specified signals within a time window.
    Pure Python implementation (no external dependencies).
    
    Args:
        vcd_file: Path to the .vcd file.
        signals: List of signal names to extract (e.g., ['clk', 'rst', 'count']).
        start_time: Start of the time window.
        end_time: End of the time window.
        
    Returns:
        A string representation of the signal changes.
    """
    if not os.path.exists(vcd_file):
        return f"Error: File {vcd_file} does not exist."
        
    id_map = {} # code -> name
    
    try:
        with open(vcd_file, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        return f"Error reading file: {e}"
        
    # 1. Parse Header
    header_end = 0
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith("$var"):
            # $var type size code ref $end
            parts = line.split()
            # parts[3] is code, parts[4] is ref
            if len(parts) >= 6:
                code = parts[3]
                ref = parts[4]
                id_map[code] = ref
        if line.startswith("$enddefinitions"):
            header_end = i
            break
            
    # Resolve wanted signals
    final_codes = {} # code -> user_friendly_name
    
    # Strategy:
    # 1. Exact match
    # 2. Suffix match (e.g. user asks 'clk', VCD has 'tb.dut.clk')
    
    for req in signals:
        found = False
        # Exact match
        for code, ref in id_map.items():
            if ref == req:
                final_codes[code] = req
                found = True
                break
        
        if not found:
            # Suffix match
            for code, ref in id_map.items():
                if ref.endswith("." + req) or ref == req:
                    final_codes[code] = req
                    found = True
                    break
                    
    if not final_codes:
        return f"Error: Signals {signals} not found. Available signals: {list(id_map.values())[:20]}..."

    # 2. Parse Body
    # We need to track state because VCD only stores changes.
    current_time = 0
    current_vals = {name: "x" for name in final_codes.values()}
    
    # We will store snapshots at every time step where something interesting happens
    events = []
    
    # Helper to record event
    def record_event(time, sig_name, val):
        events.append((time, sig_name, val))

    for i in range(header_end + 1, len(lines)):
        line = lines[i].strip()
        if not line: continue
        
        if line.startswith("#"):
            try:
                current_time = int(line[1:])
            except:
                continue
                
            if current_time > end_time:
                break
                
        elif current_time >= start_time:
            # Value change
            if line.startswith("b"):
                # Vector: b101 code
                parts = line.split()
                if len(parts) >= 2:
                    val = parts[0][1:] # Remove 'b'
                    code = parts[1]
                    if code in final_codes:
                        record_event(current_time, final_codes[code], val)
            elif not line.startswith("$"):
                # Scalar: 1code or 0code
                # But wait, code can be multiple chars!
                # Format: <value><code>
                # Value is 0, 1, x, z (1 char)
                val = line[0]
                code = line[1:]
                if code in final_codes:
                    record_event(current_time, final_codes[code], val)

    # Format output
    if not events:
        return "No events found in this time window."
        
    out_str = "Time\tSignal\tValue\n"
    for t, s, v in events:
        out_str += f"{t}\t{s}\t{v}\n"
        
    return out_str
