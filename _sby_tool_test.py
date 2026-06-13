"""Test the hardened run_sby in the solver-equipped image: real PASS/FAIL + timeout/no-orphan."""
import os, shutil, sys, subprocess, time
sys.path.insert(0, ".")
from src.tools.run_sby import run_sby

WS = "C:/Users/naman/Desktop/Projects/RTL_AGENT/workspace_new/_sby_test"
shutil.rmtree(WS, ignore_errors=True)
os.makedirs(WS)

def w(rel, content):
    with open(os.path.join(WS, rel), "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

# PASS design: the only assertion is always true for a 4-bit counter.
w("dut_pass.sv", """
module dut_pass(input clk);
  reg [3:0] cnt;
  initial cnt = 0;
  always @(posedge clk) cnt <= cnt + 4'd1;
`ifdef FORMAL
  always @(posedge clk) assert (cnt <= 4'd15);   // always true
`endif
endmodule
""".lstrip())

# FAIL design: the assertion is violated once the counter reaches 7.
w("dut_fail.sv", """
module dut_fail(input clk);
  reg [3:0] cnt;
  initial cnt = 0;
  always @(posedge clk) cnt <= cnt + 4'd1;
`ifdef FORMAL
  always @(posedge clk) assert (cnt != 4'd7);    // false: cnt reaches 7
`endif
endmodule
""".lstrip())

def sby(name, top, src, depth=12):
    w(name, f"""[options]
mode bmc
depth {depth}

[engines]
smtbmc z3

[script]
read -formal {src}
prep -top {top}

[files]
{src}
""")

sby("prove_pass.sby", "dut_pass", "dut_pass.sv")
sby("prove_fail.sby", "dut_fail", "dut_fail.sv")
w("broken.sby", "not a valid sby file\n[options]\ngarbage\n")

def orphans():
    p = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True)
    return [n for n in p.stdout.split() if n.startswith("sc_sby_")]

def last(r):
    t = ((r["stdout"] or "") + (r["stderr"] or "")).strip().splitlines()
    return t[-1][:58] if t else ""

print(f"{'case':<14}{'status':<10}{'expect':<9}{'verdict':<10}{'note'}")
print("-" * 78)
ok = 0
for label, args, expect in [
    ("PASS  proof", ("prove_pass.sby", 110), "PASS"),
    ("FAIL  proof", ("prove_fail.sby", 110), "FAIL"),
    ("TIMEOUT",     ("prove_pass.sby", 0.5), "TIMEOUT"),
    ("ERROR (bad)", ("broken.sby",     60),  "ERROR"),
]:
    r = run_sby(os.path.join(WS, args[0]), timeout=args[1])
    got = r["status"]
    v = "OK" if got == expect else "MISMATCH"
    if got == expect: ok += 1
    print(f"{label:<14}{got:<10}{expect:<9}{v:<10}{last(r)}")

time.sleep(2)
left = orphans()
print("-" * 78)
print(f"{ok}/4 cases OK   |   orphan containers: {left if left else 'NONE'}")
shutil.rmtree(WS, ignore_errors=True)
