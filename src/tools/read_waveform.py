import os
import sys
from typing import Any, Dict, Optional

# Removing the old end_time=1000 default means an unbounded VCD can produce an
# unbounded table; cap the rows and say what was withheld rather than silently
# dropping the tail (as the t=1000 bound used to) or flooding the reader.
MAX_OUTPUT_ROWS = 2000


def _parse_vcd_header(lines: list[str]) -> tuple[list[tuple[str, str]], int]:
    """Parse a VCD header into ``([(code, full_dotted_path), ...], header_end)``.

    THE header parser — shared by :func:`read_waveform` and
    :func:`scan_vcd_for_x` so there is exactly one reading of the $scope/$var
    grammar. A list, not a dict: one VCD identifier code legitimately appears
    under several paths when a signal is connected across the hierarchy, and a
    dict keyed either way would drop half the story.
    """
    var_paths: list[tuple[str, str]] = []
    header_end = 0
    scope_stack: list[str] = []
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith("$scope"):
            # $scope <type> <name> $end — push for EVERY scope type (module,
            # begin, task, function, fork). Pushing only on `module` makes a
            # named block's $upscope pop its parent, and every later $var gets
            # a wrong path.
            parts = line.split()
            if len(parts) >= 3:
                scope_stack.append(parts[2])
        elif line.startswith("$upscope"):
            if scope_stack:
                scope_stack.pop()
        elif line.startswith("$var"):
            # $var type size code ref $end
            parts = line.split()
            # parts[3] is code, parts[4] is ref
            if len(parts) >= 6:
                code = parts[3]
                ref = parts[4]
                var_paths.append((code, ".".join(scope_stack + [ref])))
        if line.startswith("$enddefinitions"):
            header_end = i
            break
    return var_paths, header_end


# Bound on the post-run X scan (sc dev#76). A VCD past this is skipped with an
# explicit "skipped (size)" — an honest refusal, never a partial scan
# pretending to be a full one. 64 MiB keeps the line-split cost in the tens of
# milliseconds-to-seconds range on the sim path that every run pays.
X_SCAN_MAX_BYTES = 64 * 1024 * 1024
# The sample of affected signal paths carried on the run record stays small —
# it is a pointer for waveform_tool, not a dump.
X_SCAN_MAX_SIGNAL_SAMPLE = 10
_XZ_CHARS = set("xXzZ")


def scan_vcd_for_x(vcd_file: str, max_bytes: int = X_SCAN_MAX_BYTES) -> Dict[str, Any]:
    """Scan a VCD for x/z value changes AFTER time 0 — a warning surface.

    Why (dev#76): ``x !== x`` evaluates FALSE, so a testbench comparing an
    undefined expected value against an undefined output silently counts the
    vector as checked and still prints its pass marker. The VCD is the one
    artifact that shows the undefinedness, and this scan turns it into honest
    fields on the run record. It is NOT a verdict: the pass/fail stays what
    the testbench printed.

    The t=0 initial dump is excluded on purpose: every uninitialized reg dumps
    as x there, so counting it would flag literally every 4-state run and the
    warning would mean nothing. Known limit, stated honestly: a signal that is
    x from t=0 and NEVER changes emits no later value change and is not seen
    here.

    Returns one of:
      * ``{"status": "scanned", "xDetected": bool, "xEventCount": int,
          "xSignalCount": int, "xSignals": [dotted paths, bounded sample]}``
      * ``{"status": "skipped (size)", "sizeBytes": int, "maxBytes": int}``
      * ``{"status": "skipped (unreadable)"}``
    """
    try:
        size = os.path.getsize(vcd_file)
    except OSError:
        return {"status": "skipped (unreadable)"}
    if size > max_bytes:
        return {"status": "skipped (size)", "sizeBytes": size, "maxBytes": max_bytes}
    try:
        with open(vcd_file, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return {"status": "skipped (unreadable)"}

    var_paths, header_end = _parse_vcd_header(lines)
    path_by_code: Dict[str, str] = {}
    for code, path in var_paths:
        path_by_code.setdefault(code, path)  # first (outermost) path per code

    current_time = 0
    event_count = 0
    seen_codes: list[str] = []
    seen: set[str] = set()
    for i in range(header_end + 1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        if line[0] == "#":
            try:
                current_time = int(line[1:])
            except ValueError:
                pass
            continue
        if current_time <= 0 or line[0] == "$":
            continue
        code = None
        if line[0] in "bB":
            # Vector: b<bits> <code>
            parts = line.split()
            if len(parts) >= 2 and _XZ_CHARS.intersection(parts[0][1:]):
                code = parts[1]
        elif line[0] in _XZ_CHARS:
            # Scalar: <value><code>, value one of 0 1 x z (case-insensitive)
            code = line[1:]
        if code:
            event_count += 1
            if code not in seen:
                seen.add(code)
                seen_codes.append(code)

    return {
        "status": "scanned",
        "xDetected": event_count > 0,
        "xEventCount": event_count,
        "xSignalCount": len(seen_codes),
        "xSignals": [
            path_by_code.get(c, c) for c in seen_codes[:X_SCAN_MAX_SIGNAL_SAMPLE]
        ],
    }


def read_waveform(vcd_file: str, signals: list[str], start_time: int = 0,
                  end_time: Optional[int] = None) -> str:
    """
    Reads a VCD file and extracts the values of specified signals within a time window.
    Pure Python implementation (no external dependencies).

    Args:
        vcd_file: Path to the .vcd file.
        signals: List of signal names to extract (e.g., ['clk', 'rst', 'count']).
        start_time: Start of the time window.
        end_time: End of the time window; None (default) reads to the end of the VCD.

    Returns:
        A string representation of the signal changes.
    """
    if not os.path.exists(vcd_file):
        return f"Error: File {vcd_file} does not exist."

    try:
        with open(vcd_file, 'r') as f:
            lines = f.readlines()
    except Exception as e:
        return f"Error reading file: {e}"

    # 1. Parse Header (shared grammar — see _parse_vcd_header)
    var_paths, header_end = _parse_vcd_header(lines)

    # Resolve wanted signals
    final_codes = {} # code -> user_friendly_name

    # Strategy:
    # 1. Exact full-path match ('tb.dut.clk')
    # 2. Unique suffix/leaf match ('clk' when only one scope has one)
    # A leaf matching several DISTINCT codes is ambiguous: returning the first
    # would be returning a signal the caller did not ask for.

    for req in signals:
        matches = [(c, p) for c, p in var_paths if p == req]
        if not matches:
            matches = [(c, p) for c, p in var_paths if p.endswith("." + req)]
        codes = {c for c, _ in matches}
        if not codes:
            continue
        if len(codes) > 1:
            candidates = ", ".join(sorted({p for _, p in matches})[:10])
            return (f"Error: Ambiguous signal '{req}': matches {candidates}. "
                    f"Use a full hierarchical path.")
        final_codes[matches[0][0]] = req

    if not final_codes:
        available = sorted({p for _, p in var_paths})[:20]
        return f"Error: Signals {signals} not found. Available signals: {available}..."

    # 2. Parse Body
    # We need to track state because VCD only stores changes.
    current_time = 0
    current_vals = {name: "x" for name in final_codes.values()}
    
    # We will store snapshots at every time step where something interesting happens.
    # Only MAX_OUTPUT_ROWS are kept in memory — with no end_time an unbounded
    # list would hold every change in the VCD; total_matches feeds the footer.
    events = []
    total_matches = 0

    # Helper to record event
    def record_event(time, sig_name, val):
        nonlocal total_matches
        total_matches += 1
        if len(events) < MAX_OUTPUT_ROWS:
            events.append((time, sig_name, val))

    for i in range(header_end + 1, len(lines)):
        line = lines[i].strip()
        if not line: continue
        
        if line.startswith("#"):
            try:
                current_time = int(line[1:])
            except:
                continue
                
            if end_time is not None and current_time > end_time:
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
        
    shown = events
    out_str = "Time\tSignal\tValue\n"
    for t, s, v in shown:
        out_str += f"{t}\t{s}\t{v}\n"

    if total_matches > len(shown):
        out_str += (
            f"... showing first {len(shown)} of {total_matches} changes "
            f"(up to t={shown[-1][0]}); narrow the window with start_time/end_time.\n"
        )

    return out_str
