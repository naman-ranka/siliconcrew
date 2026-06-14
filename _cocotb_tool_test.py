"""Standalone test for the redesigned cocotb_tool (src/tools/run_cocotb.py).

Exercises all four outcome classes in the real osvb container:
  PASS, FAIL (assertion), TIMEOUT (non-terminating), ERROR (compile failure).
"""
import os, sys, shutil
sys.path.insert(0, ".")
from src.tools.run_cocotb import run_cocotb

WS = "C:/Users/naman/Desktop/Projects/RTL_AGENT/workspace_new/_cocotb_tool_test"
shutil.rmtree(WS, ignore_errors=True)
os.makedirs(WS, exist_ok=True)

def w(rel, content):
    with open(os.path.join(WS, rel), "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

w("counter.sv", """
module counter(input clk, input rst, output reg [3:0] q);
  always @(posedge clk) if (rst) q <= 4'd0; else q <= q + 4'd1;
endmodule
""".lstrip())

w("bad.sv", """
module counter(input clk, input rst, output reg [3:0] q)   // <-- missing semicolon
  always @(posedge clk) q <= q + 4'd1;
endmodule
""".lstrip())

w("test_pass.py", """
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

@cocotb.test()
async def test_counts(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    await RisingEdge(dut.clk); await RisingEdge(dut.clk)
    dut.rst.value = 0
    for _ in range(5):
        await RisingEdge(dut.clk)
    assert int(dut.q.value) >= 1, "counter never advanced"
""".lstrip())

w("test_fail.py", """
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

@cocotb.test()
async def test_wrong(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    dut.rst.value = 1
    await RisingEdge(dut.clk); await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    assert int(dut.q.value) == 999, "deliberately impossible"
""".lstrip())

w("test_hang.py", """
import cocotb

@cocotb.test()
async def test_never_ends(dut):
    while True:        # busy-spin, never yields -> real wall-clock hang
        pass
""".lstrip())

cases = [
    ("PASS  case", ["counter.sv"], "counter", "test_pass", 110, "PASS"),
    ("FAIL  case", ["counter.sv"], "counter", "test_fail", 110, "FAIL"),
    ("HANG  case", ["counter.sv"], "counter", "test_hang", 25,  "TIMEOUT"),
    ("ERROR case", ["bad.sv"],     "counter", "test_pass", 110, "ERROR"),
]

print(f"{'case':<12}{'status':<9}{'pass/fail':<10}{'verdict'}")
print("-" * 50)
ok = 0
for label, files, top, mod, to, expect in cases:
    r = run_cocotb(files, top, mod, cwd=WS, timeout=to)
    got = r["status"]
    verdict = "OK" if got == expect else f"MISMATCH (expected {expect})"
    if got == expect: ok += 1
    print(f"{label:<12}{got:<9}{str(r['passed'])+'/'+str(r['failed']):<10}{verdict}")
    if got != expect:
        print("   tail:", (r["stderr"] or r["stdout"])[-400:])
print("-" * 50)
print(f"{ok}/{len(cases)} cases behaved as designed")
shutil.rmtree(WS, ignore_errors=True)
