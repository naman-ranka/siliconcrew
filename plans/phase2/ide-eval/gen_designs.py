#!/usr/bin/env python3
"""Generate 8 increasing-difficulty RTL take-home designs + self-checking
Verilog testbenches for the IDE usability evaluation. Each design is plain
Verilog-2001 / light SV so it lints and simulates under iverilog (-g2012)."""
import os
import pathlib

HERE = pathlib.Path(__file__).parent / "designs"

# (dir, design_filename, design_src, tb_filename, tb_src, sim_top, synth_top, note)
DESIGNS = []

# 1 — 2:1 mux (pure combinational, trivial)
DESIGNS.append((
    "01_mux2", "mux2.v", """// 2:1 multiplexer — the simplest possible combinational block.
module mux2 (
    input  wire a,
    input  wire b,
    input  wire sel,
    output wire y
);
    assign y = sel ? b : a;
endmodule
""", "mux2_tb.v", """`timescale 1ns/1ps
module mux2_tb;
    reg a, b, sel; wire y;
    integer errors = 0;
    mux2 dut(.a(a), .b(b), .sel(sel), .y(y));
    task check(input exp); begin
        #1; if (y !== exp) begin errors=errors+1;
            $display("FAIL a=%b b=%b sel=%b y=%b exp=%b", a,b,sel,y,exp); end
    end endtask
    initial begin
        a=0;b=1;sel=0; check(0);
        a=0;b=1;sel=1; check(1);
        a=1;b=0;sel=0; check(1);
        a=1;b=0;sel=1; check(0);
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
""", "mux2", "mux2", "Pure combinational, 1 line of logic. Baseline."))

# 2 — 4-bit ripple-carry adder (combinational, multi-bit)
DESIGNS.append((
    "02_adder4", "adder4.v", """// 4-bit adder with carry-in/carry-out (combinational datapath).
module adder4 (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire       cin,
    output wire [3:0] sum,
    output wire       cout
);
    assign {cout, sum} = a + b + cin;
endmodule
""", "adder4_tb.v", """`timescale 1ns/1ps
module adder4_tb;
    reg [3:0] a,b; reg cin; wire [3:0] sum; wire cout;
    integer i, errors = 0; reg [4:0] exp;
    adder4 dut(.a(a), .b(b), .cin(cin), .sum(sum), .cout(cout));
    initial begin
        for (i=0;i<200;i=i+1) begin
            a=$random; b=$random; cin=$random;
            #1; exp = a + b + cin;
            if ({cout,sum} !== exp) begin errors=errors+1;
                $display("FAIL a=%0d b=%0d cin=%b got=%0d exp=%0d", a,b,cin,{cout,sum},exp); end
        end
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
""", "adder4", "adder4", "Multi-bit combinational; introduces buses and random testing."))

# 3 — D flip-flop with async reset (intro sequential)
DESIGNS.append((
    "03_dff", "dff.v", """// D flip-flop with active-low async reset — first sequential element.
module dff (
    input  wire clk,
    input  wire rst_n,
    input  wire d,
    output reg  q
);
    always @(posedge clk or negedge rst_n)
        if (!rst_n) q <= 1'b0;
        else        q <= d;
endmodule
""", "dff_tb.v", """`timescale 1ns/1ps
module dff_tb;
    reg clk, rst_n, d; wire q; integer errors=0;
    dff dut(.clk(clk), .rst_n(rst_n), .d(d), .q(q));
    always #5 clk = ~clk;
    initial begin
        clk=0; rst_n=0; d=1; #12;
        if (q!==1'b0) begin errors=errors+1; $display("FAIL reset q=%b",q); end
        rst_n=1; d=1; @(posedge clk); #1;
        if (q!==1'b1) begin errors=errors+1; $display("FAIL capture-1 q=%b",q); end
        d=0; @(posedge clk); #1;
        if (q!==1'b0) begin errors=errors+1; $display("FAIL capture-0 q=%b",q); end
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
""", "dff", "dff", "First clocked element; introduces clock + reset to the flow."))

# 4 — 8-bit up counter, enable + sync clear (sequential)
DESIGNS.append((
    "04_counter8", "counter8.v", """// 8-bit up counter with enable and synchronous clear.
module counter8 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       en,
    input  wire       clr,
    output reg  [7:0] count
);
    always @(posedge clk or negedge rst_n)
        if (!rst_n)     count <= 8'd0;
        else if (clr)   count <= 8'd0;
        else if (en)    count <= count + 8'd1;
endmodule
""", "counter8_tb.v", """`timescale 1ns/1ps
module counter8_tb;
    reg clk, rst_n, en, clr; wire [7:0] count; integer errors=0;
    counter8 dut(.clk(clk), .rst_n(rst_n), .en(en), .clr(clr), .count(count));
    always #5 clk = ~clk;
    initial begin
        clk=0; rst_n=0; en=0; clr=0; #12; rst_n=1;
        if (count!==8'd0) begin errors=errors+1; $display("FAIL reset=%0d",count); end
        en=1; repeat(5) @(posedge clk); #1;
        if (count!==8'd5) begin errors=errors+1; $display("FAIL count!=5 got=%0d",count); end
        clr=1; @(posedge clk); #1; clr=0;
        if (count!==8'd0) begin errors=errors+1; $display("FAIL clr got=%0d",count); end
        en=0; repeat(3) @(posedge clk); #1;
        if (count!==8'd0) begin errors=errors+1; $display("FAIL hold got=%0d",count); end
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
""", "counter8", "counter8", "Multi-control sequential logic; common 'hello world' for HW."))

# 5 — 8-bit shift register, load + serial shift (sequential)
DESIGNS.append((
    "05_shiftreg", "shiftreg.v", """// 8-bit shift register: parallel load, then serial shift-left with serial-in.
module shiftreg (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       load,
    input  wire [7:0] din,
    input  wire       sin,
    output reg  [7:0] q,
    output wire       sout
);
    assign sout = q[7];
    always @(posedge clk or negedge rst_n)
        if (!rst_n)     q <= 8'd0;
        else if (load)  q <= din;
        else            q <= {q[6:0], sin};
endmodule
""", "shiftreg_tb.v", """`timescale 1ns/1ps
module shiftreg_tb;
    reg clk,rst_n,load,sin; reg [7:0] din; wire [7:0] q; wire sout; integer errors=0;
    shiftreg dut(.clk(clk),.rst_n(rst_n),.load(load),.din(din),.sin(sin),.q(q),.sout(sout));
    always #5 clk=~clk;
    initial begin
        clk=0;rst_n=0;load=0;sin=0;din=8'h00;#12;rst_n=1;
        load=1; din=8'hA5; @(posedge clk); #1; load=0;
        if (q!==8'hA5) begin errors=errors+1; $display("FAIL load q=%h",q); end
        if (sout!==1'b1) begin errors=errors+1; $display("FAIL sout-after-load=%b (q[7] of A5)",sout); end
        sin=1; @(posedge clk); #1;
        if (q!==8'h4B) begin errors=errors+1; $display("FAIL shift q=%h exp=4B",q); end
        if (sout!==1'b0) begin errors=errors+1; $display("FAIL sout-after-shift=%b (q[7] of 4B)",sout); end
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
""", "shiftreg", "shiftreg", "Concatenation-based shifting; tests bus + serial I/O."))

# 6 — "1011" overlapping sequence detector (Moore FSM)
DESIGNS.append((
    "06_seqdet", "seqdet.v", """// Moore FSM: detects overlapping bit sequence 1011 on serial input `din`.
module seqdet (
    input  wire clk,
    input  wire rst_n,
    input  wire din,
    output wire found
);
    localparam S0=3'd0, S1=3'd1, S10=3'd2, S101=3'd3, S1011=3'd4;
    reg [2:0] state, nxt;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) state <= S0; else state <= nxt;
    always @(*) begin
        case (state)
            S0:    nxt = din ? S1   : S0;
            S1:    nxt = din ? S1   : S10;
            S10:   nxt = din ? S101 : S0;
            S101:  nxt = din ? S1011: S10;
            S1011: nxt = din ? S1   : S10;
            default nxt = S0;
        endcase
    end
    assign found = (state == S1011);
endmodule
""", "seqdet_tb.v", """`timescale 1ns/1ps
module seqdet_tb;
    reg clk,rst_n,din; wire found; integer errors=0, i;
    // stimulus 1 0 1 1 0 1 1  -> 'found' should pulse after the 4th and 7th bits
    reg [0:6] stim = 7'b1011011;
    reg [0:6] exp  = 7'b0001001; // found asserted in the cycle the pattern completes
    seqdet dut(.clk(clk),.rst_n(rst_n),.din(din),.found(found));
    always #5 clk=~clk;
    initial begin
        clk=0;rst_n=0;din=0;#12;rst_n=1;
        for (i=0;i<7;i=i+1) begin
            din=stim[i]; @(posedge clk); #1;
            if (found!==exp[i]) begin errors=errors+1;
                $display("FAIL i=%0d din=%b found=%b exp=%b",i,din,found,exp[i]); end
        end
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
""", "seqdet", "seqdet", "Classic two-always FSM; tests state-machine authoring + waveform reading."))

# 7 — 4-bit ALU with flags (datapath)
DESIGNS.append((
    "07_alu4", "alu4.v", """// 4-bit ALU: add/sub/and/or/xor/not/shl/shr with zero & carry flags.
module alu4 (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire [2:0] op,
    output reg  [3:0] y,
    output wire       zero,
    output reg        carry
);
    always @(*) begin
        carry = 1'b0;
        case (op)
            3'd0: {carry, y} = a + b;
            3'd1: {carry, y} = a - b;
            3'd2: y = a & b;
            3'd3: y = a | b;
            3'd4: y = a ^ b;
            3'd5: y = ~a;
            3'd6: {carry, y} = {a, 1'b0};   // shift left
            3'd7: {y, carry} = {1'b0, a};   // shift right
            default y = 4'd0;
        endcase
    end
    assign zero = (y == 4'd0);
endmodule
""", "alu4_tb.v", """`timescale 1ns/1ps
module alu4_tb;
    reg [3:0] a,b; reg [2:0] op; wire [3:0] y; wire zero; wire carry;
    integer errors=0; reg [3:0] ey; reg ec;
    alu4 dut(.a(a),.b(b),.op(op),.y(y),.zero(zero),.carry(carry));
    task chk; begin #1;
        if (y!==ey || carry!==ec) begin errors=errors+1;
            $display("FAIL op=%0d a=%h b=%h y=%h(exp %h) c=%b(exp %b)",op,a,b,y,ey,carry,ec); end
    end endtask
    initial begin
        a=4'h3;b=4'h5;op=0; {ec,ey}=a+b; chk;
        a=4'h8;b=4'h1;op=1; {ec,ey}=a-b; chk;
        a=4'hC;b=4'hA;op=2; ey=a&b; ec=0; chk;
        a=4'hC;b=4'hA;op=3; ey=a|b; ec=0; chk;
        a=4'hC;b=4'hA;op=4; ey=a^b; ec=0; chk;
        a=4'h5;b=4'h0;op=5; ey=~a; ec=0; chk;
        a=4'hF;b=4'h0;op=6; {ec,ey}={a,1'b0}; chk;
        a=4'h3;b=4'h0;op=7; ey={1'b0,a[3:1]}; ec=a[0]; chk;
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
""", "alu4", "alu4", "Op-decoded datapath with flags; tests a wider, more realistic block."))

# 8 — synchronous FIFO depth 4 (datapath + control, hardest)
DESIGNS.append((
    "08_fifo", "fifo.v", """// Synchronous FIFO, depth 4, 8-bit data, with full/empty flags.
module fifo (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       wr,
    input  wire       rd,
    input  wire [7:0] din,
    output reg  [7:0] dout,
    output wire       full,
    output wire       empty
);
    reg [7:0] mem [0:3];
    reg [2:0] count;          // 0..4
    reg [1:0] wptr, rptr;
    assign full  = (count == 3'd4);
    assign empty = (count == 3'd0);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= 0; wptr <= 0; rptr <= 0; dout <= 0;
        end else begin
            if (wr && !full) begin mem[wptr] <= din; wptr <= wptr + 1'b1; end
            if (rd && !empty) begin dout <= mem[rptr]; rptr <= rptr + 1'b1; end
            case ({wr && !full, rd && !empty})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule
""", "fifo_tb.v", """`timescale 1ns/1ps
module fifo_tb;
    reg clk,rst_n,wr,rd; reg [7:0] din; wire [7:0] dout; wire full, empty;
    integer errors=0;
    fifo dut(.clk(clk),.rst_n(rst_n),.wr(wr),.rd(rd),.din(din),.dout(dout),.full(full),.empty(empty));
    always #5 clk=~clk;
    task wpush(input [7:0] d); begin din=d; wr=1; rd=0; @(posedge clk); #1; wr=0; end endtask
    task wpop;                begin wr=0; rd=1; @(posedge clk); #1; rd=0; end endtask
    initial begin
        clk=0;rst_n=0;wr=0;rd=0;din=0;#12;rst_n=1;#1;
        if (!empty) begin errors=errors+1; $display("FAIL not empty at reset"); end
        wpush(8'h11); wpush(8'h22); wpush(8'h33); wpush(8'h44);
        if (!full) begin errors=errors+1; $display("FAIL not full after 4 writes"); end
        wpop; if (dout!==8'h11) begin errors=errors+1; $display("FAIL pop1=%h exp 11",dout); end
        wpop; if (dout!==8'h22) begin errors=errors+1; $display("FAIL pop2=%h exp 22",dout); end
        wpop; if (dout!==8'h33) begin errors=errors+1; $display("FAIL pop3=%h exp 33",dout); end
        wpop; if (dout!==8'h44) begin errors=errors+1; $display("FAIL pop4=%h exp 44",dout); end
        if (!empty) begin errors=errors+1; $display("FAIL not empty after draining"); end
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
""", "fifo", "fifo", "Memory + pointers + flags; the most realistic / hardest block."))


import re


def _inject_vcd_dump(tb_src, tb_module):
    """Insert a standard $dumpfile/$dumpvars block right after the testbench
    module declaration so the IDE's Wave viewer has a VCD to render. (The IDE
    relies on the TB to emit its own VCD; it does not auto-instrument.)"""
    dump = (f"\n    initial begin $dumpfile(\"{tb_module}.vcd\"); "
            f"$dumpvars(0, {tb_module}); end\n")
    return re.sub(rf"(module\s+{tb_module}\s*;)", r"\1" + dump, tb_src, count=1)


def main():
    index = []
    for d in DESIGNS:
        ddir, dfn, dsrc, tfn, tsrc, simtop, synthtop, note = d
        tb_module = tfn[:-2]  # strip ".v"
        tsrc = _inject_vcd_dump(tsrc, tb_module)
        out = HERE / ddir
        out.mkdir(parents=True, exist_ok=True)
        (out / dfn).write_text(dsrc)
        (out / tfn).write_text(tsrc)
        index.append({
            "dir": ddir, "design": dfn, "tb": tfn,
            "sim_top": simtop, "synth_top": synthtop, "note": note,
        })
    import json
    (HERE / "index.json").write_text(json.dumps(index, indent=2))
    print(f"Wrote {len(DESIGNS)} designs to {HERE}")
    for i in index:
        print(f"  {i['dir']:14s} {i['design']:14s} + {i['tb']:16s}  — {i['note']}")


if __name__ == "__main__":
    main()
