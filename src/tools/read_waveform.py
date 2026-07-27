import os
import sys

def read_waveform(vcd_file: str, signals: list[str], start_time: int = 0, end_time: int = 1000) -> str:
    """
    Reads a VCD file and extracts the values of specified signals within a time window.
    Pure Python implementation (no external dependencies).

    Signal naming: the VCD header is parsed with its `$scope`/`$upscope` nesting,
    so every declared signal has a full hierarchical name (e.g. 'tb.dut.count').
    A requested name resolves by: exact full-path match, then unique suffix match
    (a bare leaf name like 'count' works whenever it is unique in the file).
    An ambiguous bare name is NEVER guessed — it is reported with its candidates.

    Args:
        vcd_file: Path to the .vcd file.
        signals: List of signal names to extract. Either full hierarchical paths
            (e.g. ['tb.dut.count']) or bare leaf names when unique (e.g. ['clk']).
        start_time: Start of the time window.
        end_time: End of the time window.

    Returns:
        A string representation of the signal changes.
    """
    if not os.path.exists(vcd_file):
        return f"Error: File {vcd_file} does not exist."

    # (full_hierarchical_name, code) in declaration order. A code may carry more
    # than one name (VCD aliases connected nets onto a single identifier).
    declared: list[tuple[str, str]] = []

    try:
        with open(vcd_file, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        return f"Error reading file: {e}"

    # 1. Parse Header (tracking scope nesting so names are hierarchical)
    header_end = 0
    scope_stack: list[str] = []
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith("$scope"):
            # $scope <type> <name> $end
            parts = line.split()
            if len(parts) >= 3:
                scope_stack.append(parts[2])
        elif line.startswith("$upscope"):
            if scope_stack:
                scope_stack.pop()
        elif line.startswith("$var"):
            # $var type size code ref [range] $end
            parts = line.split()
            # parts[3] is code, parts[4] is ref
            if len(parts) >= 6:
                code = parts[3]
                ref = parts[4]
                declared.append((".".join(scope_stack + [ref]), code))
        if line.startswith("$enddefinitions"):
            header_end = i
            break

    all_names = [name for name, _ in declared]

    # Resolve wanted signals.
    # 1. Exact full-path match ('tb.dut.clk', or a bare name in the top scope).
    # 2. Unique suffix match (user asks 'clk', VCD has 'tb.dut.clk').
    # Ambiguity is reported, never guessed.
    final_codes = {}  # code -> display name (the resolved full path)
    ambiguous = []    # (requested, [candidate full names])
    missing = []

    for req in signals:
        exact = [(name, code) for name, code in declared if name == req]
        candidates = exact
        if not candidates:
            candidates = [
                (name, code) for name, code in declared
                if name.endswith("." + req) or name == req
            ]

        if not candidates:
            missing.append(req)
            continue

        # Aliases of one identifier carry identical values — not real ambiguity.
        distinct_codes = {code for _, code in candidates}
        if len(distinct_codes) > 1:
            ambiguous.append((req, [name for name, _ in candidates]))
            continue

        name, code = candidates[0]
        final_codes[code] = name

    if ambiguous:
        details = "; ".join(
            f"'{req}' matches {cands}" for req, cands in ambiguous
        )
        return (
            f"Error: Ambiguous signal name(s): {details}. "
            "Re-request using the full hierarchical path."
        )

    if not final_codes:
        return (
            f"Error: Signals {missing or signals} not found. "
            f"Available signals: {all_names[:20]}..."
        )

    warning = ""
    if missing:
        warning = (
            f"Note: not found: {missing}. "
            f"Available signals: {all_names[:20]}...\n"
        )

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
        return warning + "No events found in this time window."

    out_str = warning + "Time\tSignal\tValue\n"
    for t, s, v in events:
        out_str += f"{t}\t{s}\t{v}\n"
        
    return out_str
