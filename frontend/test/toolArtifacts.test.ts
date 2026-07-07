import { describe, it, expect } from "vitest";
import {
  artifactKeyForToolCall,
  artifactKeyForActivity,
  runIdFromText,
} from "@/lib/toolArtifacts";

// S5-1 mapping matrix: every tool family + the unmappable cases (null → the
// "Open <kind> →" button simply doesn't render).

describe("runIdFromText", () => {
  it("extracts the (sim|synth)_\\d+ convention from result blobs", () => {
    expect(runIdFromText("Run sim_0007 passed at 240ns")).toBe("sim_0007");
    expect(runIdFromText('{"run_id": "synth_0042", "status": "ok"}')).toBe("synth_0042");
    expect(runIdFromText("no run here")).toBeNull();
    expect(runIdFromText(null)).toBeNull();
    expect(runIdFromText(undefined)).toBeNull();
  });
});

describe("artifactKeyForToolCall — file family → code:<file>", () => {
  it("write_file / edit_file_tool key by the filename arg", () => {
    expect(artifactKeyForToolCall("write_file", { filename: "alu.v", content: "x" })).toBe(
      "code:alu.v"
    );
    expect(
      artifactKeyForToolCall("edit_file_tool", {
        filename: "fifo.v",
        target_text: "a",
        replacement_text: "b",
      })
    ).toBe("code:fifo.v");
  });

  it("apply_patch_tool extracts the +++ target from the unified diff", () => {
    const diff = "--- a/alu.v\n+++ b/alu.v\n@@ -1 +1 @@\n-x\n+y\n";
    expect(artifactKeyForToolCall("apply_patch_tool", { unified_diff: diff })).toBe("code:alu.v");
    // Bare (no a/ b/ prefix) headers work too.
    const bare = "--- alu.v\n+++ alu.v\n@@ -1 +1 @@\n";
    expect(artifactKeyForToolCall("apply_patch_tool", { unified_diff: bare })).toBe("code:alu.v");
  });

  it("null when the file is unknowable (no arg / deletion diff)", () => {
    expect(artifactKeyForToolCall("write_file", {})).toBeNull();
    expect(
      artifactKeyForToolCall("apply_patch_tool", {
        unified_diff: "--- a/alu.v\n+++ /dev/null\n",
      })
    ).toBeNull();
  });
});

describe("artifactKeyForToolCall — spec family → spec", () => {
  it.each(["write_spec", "read_spec", "load_yaml_spec_file"])("%s → spec", (tool) => {
    expect(artifactKeyForToolCall(tool, {})).toBe("spec");
  });
});

describe("artifactKeyForToolCall — sim family → wave:<runId from result>", () => {
  it("keys by the run id in the result text", () => {
    expect(
      artifactKeyForToolCall(
        "run_isolated_simulation",
        { design_files: ["alu.v"] },
        "PASS. Run ID: sim_0003 (sim_runs/sim_0003)"
      )
    ).toBe("wave:sim_0003");
    expect(
      artifactKeyForToolCall("simulation_tool", {}, "sim_0011 failed @ 320ns")
    ).toBe("wave:sim_0011");
  });

  it("null when the result names no run", () => {
    expect(artifactKeyForToolCall("simulation_tool", {}, "compile error")).toBeNull();
    expect(artifactKeyForToolCall("run_isolated_simulation", {})).toBeNull();
  });
});

describe("artifactKeyForToolCall — synth family → report:<runId>", () => {
  it("prefers the run_id arg, falls back to the result text", () => {
    expect(
      artifactKeyForToolCall("get_synthesis_metrics", { run_id: "synth_0042" }, "ok")
    ).toBe("report:synth_0042");
    expect(
      artifactKeyForToolCall("start_synthesis", {}, "synth_0001 dispatched (job job_abc)")
    ).toBe("report:synth_0001");
    expect(
      artifactKeyForToolCall("read_stage_report", { stage: "cts", run_id: "synth_0002" })
    ).toBe("report:synth_0002");
    expect(
      artifactKeyForToolCall("retry_pd", {}, "retrying as synth_0005")
    ).toBe("report:synth_0005");
    expect(
      artifactKeyForToolCall("generate_report_tool", {}, "report saved for synth_0009")
    ).toBe("report:synth_0009");
  });

  it("null runId → null", () => {
    expect(artifactKeyForToolCall("start_synthesis", {}, "queue full")).toBeNull();
    expect(artifactKeyForToolCall("get_synthesis_metrics", { run_id: null })).toBeNull();
  });
});

describe("artifactKeyForToolCall — schematic_tool → schematic:<svg>", () => {
  it("keys by the svg name when extractable from the result", () => {
    expect(
      artifactKeyForToolCall(
        "schematic_tool",
        { verilog_file: "alu.v", top_module: "alu" },
        "Schematic written to alu_schematic.svg"
      )
    ).toBe("schematic:alu_schematic.svg");
  });

  it("null when no svg name is extractable", () => {
    expect(
      artifactKeyForToolCall("schematic_tool", { verilog_file: "alu.v" }, "yosys failed")
    ).toBeNull();
  });
});

describe("artifactKeyForToolCall — waveform_tool → wave:<runId from vcd path>", () => {
  it("maps only when vcd_file lives in a run directory", () => {
    expect(
      artifactKeyForToolCall("waveform_tool", {
        vcd_file: "sim_runs/sim_0003/dump.vcd",
        signals: ["clk"],
      })
    ).toBe("wave:sim_0003");
  });

  it("a bare dump.vcd is ambiguous across runs → null", () => {
    expect(
      artifactKeyForToolCall("waveform_tool", { vcd_file: "dump.vcd", signals: [] })
    ).toBeNull();
  });
});

describe("artifactKeyForToolCall — unmappable tools", () => {
  it.each(["linter_tool", "read_file", "list_files_tool", "search_logs_tool", "get_manifest"])(
    "%s → null",
    (tool) => {
      expect(artifactKeyForToolCall(tool, { filename: "alu.v" }, "sim_0001")).toBeNull();
    }
  );
});

describe("artifactKeyForActivity", () => {
  it("the event's structured runId completes the mapping when the summary lacks one", () => {
    expect(
      artifactKeyForActivity({
        tool: "start_synthesis",
        args: {},
        resultSummary: "dispatched",
        runId: "synth_0009",
      })
    ).toBe("report:synth_0009");
    expect(
      artifactKeyForActivity({
        tool: "run_isolated_simulation",
        args: {},
        resultSummary: "passed",
        runId: "sim_0002",
      })
    ).toBe("wave:sim_0002");
  });

  it("unmappable events stay null", () => {
    expect(
      artifactKeyForActivity({
        tool: "linter_tool",
        args: {},
        resultSummary: "passed · 0 errors",
        runId: null,
      })
    ).toBeNull();
  });
});

describe("artifactKeyForToolCall — run_python_analysis (PA9)", () => {
  const result = (artifacts: unknown[]) => JSON.stringify({ ok: true, artifacts });

  it("prefers the first image, then data, then text artifact", () => {
    expect(
      artifactKeyForToolCall("run_python_analysis", { script_file: "gen.py" }, result([
        { path: "notes.txt", kind: "text", bytes: 10 },
        { path: "out/plot.png", kind: "image", bytes: 100 },
        { path: "vectors.csv", kind: "data", bytes: 50 },
      ]))
    ).toBe("image:out/plot.png");

    expect(
      artifactKeyForToolCall("run_python_analysis", { script_file: "gen.py" }, result([
        { path: "vectors.csv", kind: "data", bytes: 50 },
        { path: "log.txt", kind: "text", bytes: 10 },
      ]))
    ).toBe("data:vectors.csv");

    expect(
      artifactKeyForToolCall("run_python_analysis", { script_file: "gen.py" }, result([
        { path: "run.log", kind: "text", bytes: 10 },
      ]))
    ).toBe("text:run.log");
  });

  it("falls back to the input script when only vector/file artifacts (no rich viewer) exist", () => {
    expect(
      artifactKeyForToolCall("run_python_analysis", { script_file: "gen.py" }, result([
        { path: "rom.hex", kind: "vector", bytes: 8 },
      ]))
    ).toBe("code:gen.py");
  });

  it("falls back to the script when the result isn't parseable, and is null without a script", () => {
    expect(
      artifactKeyForToolCall("run_python_analysis", { script_file: "gen.py" }, "not json")
    ).toBe("code:gen.py");
    expect(artifactKeyForToolCall("run_python_analysis", {}, "not json")).toBeNull();
  });
});
