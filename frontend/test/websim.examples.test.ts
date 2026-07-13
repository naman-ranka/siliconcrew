// @vitest-environment node
// REAL-engine coverage for every shipped interactive example bundle: each
// checked-in `examples/<id>/workspace/<top>.websim.json` must load in the
// actual digitaljs engine and behave like its RTL — a netlist that ships but
// cannot simulate (or simulates the wrong design) is the dishonest-dashboard
// failure mode the drift gate alone can't catch (it only proves hash
// freshness, not runnability).
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import { createWebsimSession, parseWebsimPayload, type WebsimSession } from "@/lib/websim";

const EXAMPLES = path.resolve(__dirname, "../../examples");

function loadExample(id: string, top: string) {
  const text = readFileSync(
    path.join(EXAMPLES, id, "workspace", `${top}.websim.json`),
    "utf8"
  );
  const payload = parseWebsimPayload(text);
  expect(payload, `${id}: shipped websim.json failed validation`).not.toBeNull();
  return payload!;
}

describe("lfsr8 — shipped netlist runs in the real engine", () => {
  it("seeds 0xFF on reset, shifts with en, holds without", async () => {
    const s = await createWebsimSession(loadExample("lfsr8", "lfsr8"));
    expect(s.hasClock).toBe(true);

    // async active-low reset: inputs start low → already in reset
    expect(s.readOutputs().state).toBe(0xff);

    s.setInput("rst_n", 1);
    s.setInput("en", 1);
    s.tickCycle(); // 0xFF: fb = 1^1^1^1 = 0 → 0xFE
    expect(s.readOutputs().state).toBe(0xfe);
    s.tickCycle(); // 0xFE: fb = 1^1^1^1 = 0 → 0xFC
    expect(s.readOutputs().state).toBe(0xfc);

    s.setInput("en", 0);
    s.tickCycle();
    expect(s.readOutputs().state).toBe(0xfc); // hold
    s.dispose();
  });
});

describe("seq_detector_0011 — shipped netlist runs in the real engine", () => {
  it("fires exactly when the last four bits are 0,0,1,1 (overlapping)", async () => {
    const s = await createWebsimSession(
      loadExample("seq_detector_0011", "seq_detector_0011")
    );
    s.setInput("rst_n", 1);

    const feed = (bits: number[]) =>
      bits.map((b) => {
        s.setInput("din", b);
        s.tickCycle();
        return s.readOutputs().detected;
      });

    expect(feed([0, 0, 1, 1])).toEqual([0, 0, 0, 1]);
    // overlap: ...0011 then 0011 again straight after
    expect(feed([0, 0, 1, 1])).toEqual([0, 0, 0, 1]);
    // near-miss 0101 never fires
    expect(feed([0, 1, 0, 1])).toEqual([0, 0, 0, 0]);
    s.dispose();
  });
});

describe("alu4 — shipped netlist runs in the real engine", () => {
  const OP = { ADD: 0, SUB: 1, MUL: 2, DIV: 3, AND: 4, OR: 5, XOR: 6, NOT: 7, ENC: 8 };

  async function session(): Promise<WebsimSession> {
    const s = await createWebsimSession(loadExample("alu4", "alu4"));
    s.setInput("rst_n", 1);
    return s;
  }

  function compute(s: WebsimSession, a: number, b: number, op: number) {
    s.setInput("a", a);
    s.setInput("b", b);
    s.setInput("opcode", op);
    s.tickCycle(); // registered result
    return s.readOutputs();
  }

  it("ADD produces sum + carry + signed overflow", async () => {
    const s = await session();
    const add = compute(s, 7, 5, OP.ADD);
    expect(add.result).toBe(12);
    expect(add.overflow).toBe(1); // 7+5=12 exceeds 4-bit signed +7
    const wrap = compute(s, 15, 1, OP.ADD);
    expect(wrap.result).toBe(0);
    expect(wrap.carry_out).toBe(1);
    const safe = compute(s, 3, 2, OP.ADD);
    expect(safe.result).toBe(5);
    expect(safe.overflow).toBe(0);
    s.dispose();
  });

  it("MUL widens to 8 bits; DIV packs {remainder, quotient}", async () => {
    const s = await session();
    expect(compute(s, 7, 5, OP.MUL).result).toBe(35);
    // 13 / 4 → q=3 r=1 → {0001,0011}
    expect(compute(s, 13, 4, OP.DIV).result).toBe(0x13);
    s.dispose();
  });
});

describe("sn74169 — shipped netlist runs in the real engine", () => {
  it("starts honestly undefined (no reset), loads, counts up/down, RCOB at TC", async () => {
    const s = await createWebsimSession(loadExample("sn74169", "sn74169"));
    expect(s.hasClock).toBe(true); // uppercase CLK matched by the heuristic

    // no reset pin: flops power up x → outputs must be null, never a fake 0
    expect(s.readOutputs().Q).toBeNull();

    // synchronous load (LOADB active-low)
    s.setInput("A", 10);
    s.setInput("LOADB", 0);
    s.setInput("ENPB", 1);
    s.setInput("ENTB", 1);
    s.setInput("U_DB", 1);
    s.tickCycle();
    expect(s.readOutputs().Q).toBe(10);

    // count up
    s.setInput("LOADB", 1);
    s.setInput("ENPB", 0);
    s.setInput("ENTB", 0);
    s.tickCycle();
    expect(s.readOutputs().Q).toBe(11);

    // count down
    s.setInput("U_DB", 0);
    s.tickCycle();
    s.tickCycle();
    expect(s.readOutputs().Q).toBe(9);

    // terminal count: Q=0 counting down → RCOB (active low) asserts
    for (let i = 0; i < 9; i++) s.tickCycle();
    expect(s.readOutputs().Q).toBe(0);
    expect(s.readOutputs().RCOB).toBe(0);
    s.dispose();
  });
});

describe("universal_bcd_decoder — shipped netlist runs in the real engine", () => {
  it("is clockless and decodes live on input changes", async () => {
    const s = await createWebsimSession(
      loadExample("ubcd_decoder", "universal_bcd_decoder")
    );
    expect(s.hasClock).toBe(false);
    expect(s.sequential).toBe(false);

    // display defaults: lamp-test off, not blanked, active-high, RBI high
    for (const pin of ["LT", "BI", "AL", "RBI"]) s.setInput(pin, 1);

    const segs = () => {
      const o = s.readOutputs();
      return (
        (o.Qa as number) |
        ((o.Qb as number) << 1) |
        ((o.Qc as number) << 2) |
        ((o.Qd as number) << 3) |
        ((o.Qe as number) << 4) |
        ((o.Qf as number) << 5) |
        ((o.Qg as number) << 6)
      );
    };
    const setValue = (v: number) => {
      s.setInput("A", v & 1);
      s.setInput("B", (v >> 1) & 1);
      s.setInput("C", (v >> 2) & 1);
      s.setInput("D", (v >> 3) & 1);
    };

    setValue(5);
    expect(segs()).toBe(0x6d); // '5'

    // hexadecimal family (version=111): value 10 renders 'A'
    for (const pin of ["V0", "V1", "V2"]) s.setInput(pin, 1);
    setValue(10);
    expect(segs()).toBe(0x77);

    // ripple blanking: version back to decimal, value 0 with RBI=0 blanks
    for (const pin of ["V0", "V1", "V2"]) s.setInput(pin, 0);
    setValue(0);
    expect(segs()).toBe(0x3f); // '0' while RBI=1
    s.setInput("RBI", 0);
    expect(segs()).toBe(0x00); // blanked
    expect(s.readOutputs().RBO).toBe(0);
    s.dispose();
  });
});

describe("simon_game — shipped netlist runs in the real engine", () => {
  // The browser engine sustains ~1 kHz on this netlist, nowhere near the
  // default 50 ticks/game-ms (real-time = 50 kHz). The shipped bundle is
  // therefore compiled with TICKS_PER_MILLI=1 — the tool records the
  // override and the provenance strip shows it (invariant 4).
  it("ships re-parameterized for browser speed, and says so", () => {
    const payload = loadExample("simon_game", "simon_game");
    expect(payload.parameters).toEqual({ TICKS_PER_MILLI: 1 });
  });

  it("powers on with the attract pattern and a button press starts playback", async () => {
    const s = await createWebsimSession(loadExample("simon_game", "simon_game"));
    expect(s.hasClock).toBe(true);

    // synchronous reset (module inverts rst_n internally)
    s.setInput("rst_n", 0);
    s.tickCycle();
    s.setInput("rst_n", 1);
    s.tickCycle();

    // StatePowerOn = 0: attract pattern = all LEDs on except one
    expect(s.readOutputs().dbg_state).toBe(0);
    expect(s.readOutputs().led).toBe(0b1110);
    expect(s.readOutputs().game_over).toBe(0);

    // press btn1 → seeds the sequence, enters StateInit = 1
    s.setInput("btn", 0b0001);
    s.tickCycle();
    expect(s.readOutputs().dbg_state).toBe(1);
    s.setInput("btn", 0);

    // StateInit holds 500 game-ms (= 500 cycles at TICKS_PER_MILLI=1) then
    // playback begins: StatePlay lights exactly one LED of the seeded sequence
    for (let i = 0; i < 700; i++) s.tickCycle();
    const st = s.readOutputs().dbg_state as number;
    expect([2, 3]).toContain(st); // Play / PlayWait
    const led = s.readOutputs().led as number;
    expect([1, 2, 4, 8]).toContain(led); // one-hot playback LED
    s.dispose();
  }, 60_000);
});
