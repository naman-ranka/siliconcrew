import { describe, it, expect } from "vitest";

import {
  basicOrAdvanced,
  buildFormModel,
  conventionOptions,
  defaultFor,
  editorFor,
  manifestFileSet,
  manifestSetPlaceholder,
  manifestValueFor,
  paramSourceFor,
  shortDescription,
  suggestionSubtitles,
  unwrapOptional,
  valueKindFor,
} from "@/lib/schemaForm";
import type { SurfaceCtx } from "@/lib/commandSurface";
import type { RunSummary, SchemaProperty, ToolCatalogEntry } from "@/types";

// ---- fixtures -----------------------------------------------------------------

const synthRun = (id: string): RunSummary => ({
  id,
  kind: "synth",
  status: "passed",
  createdAt: null,
  top: "alu",
  pinned: false,
});

const simRun = (id: string, vcdPath?: string): RunSummary => ({
  id,
  kind: "sim",
  status: "failed",
  createdAt: null,
  top: "tb",
  pinned: false,
  ...(vcdPath ? { vcdPath } : {}),
});

// Runs arrive newest-first from the backend — synth_0002 is the latest.
const CTX: SurfaceCtx = {
  manifest: {
    sessionId: "s1",
    files: [
      { name: "alu.v", role: "rtl", path: "alu.v" },
      { name: "top.v", role: "rtl", path: "top.v" },
      // Nested rtl — `path` differs from display-only `name` (A11: options
      // must be ws-relative paths, or nested files silently break).
      { name: "nested.v", role: "rtl", path: "rtl/nested.v" },
      { name: "defs.vh", role: "include", path: "inc/defs.vh" },
      { name: "tb.v", role: "tb", path: "tb.v" },
      { name: "tb2.v", role: "tb", path: "sub/tb2.v" },
    ],
    synthTop: "alu",
    simTop: "tb",
    clockPeriodNs: 12.5,
    platform: "asap7",
    testbenches: [
      { file: "tb.v", module: "tb" },
      { file: "sub/tb2.v", module: "tb2" },
    ],
  },
  runs: [
    synthRun("synth_0002"),
    simRun("sim_0002", "sim_runs/sim_0002/dump.vcd"),
    synthRun("synth_0001"),
    simRun("sim_0001", "sim_runs/sim_0001/dump.vcd"),
    simRun("sim_0000"), // no vcd — must not appear in vcd options
  ],
  // The recursive path index (W2/A8) — nested paths included.
  wsPaths: [
    "alu.v",
    "tb.v",
    "rtl/nested.v",
    "check.sby",
    "adder.x",
    "hls/mul.x",
    "spec.md",
    "scripts/gen_vectors.py",
    "specs/counter_spec.yaml",
    "legacy_spec.yml",
    "ir/adder.ir",
    "ir/adder.opt.ir",
    "cpp/design.cc",
  ],
  wsPathsTruncated: false,
};

const EMPTY_CTX: SurfaceCtx = {
  manifest: null,
  runs: [],
  wsPaths: [],
  wsPathsTruncated: false,
};

const optionalString = (def: unknown = null): SchemaProperty => ({
  anyOf: [{ type: "string" }, { type: "null" }],
  default: def,
});

// ---- unwrapOptional -------------------------------------------------------------

describe("unwrapOptional", () => {
  it("unwraps pydantic Optional (anyOf [{type:X},{type:'null'}]) to inner type + nullable", () => {
    const { prop, nullable } = unwrapOptional(optionalString());
    expect(nullable).toBe(true);
    expect(prop.type).toBe("string");
    expect(prop.default).toBeNull(); // wrapper's default survives the merge
  });

  it("keeps the wrapper's description on the unwrapped prop", () => {
    const { prop } = unwrapOptional({ ...optionalString(), description: "the run" });
    expect(prop.description).toBe("the run");
  });

  it("unwraps Optional[int]", () => {
    const { prop, nullable } = unwrapOptional({ anyOf: [{ type: "integer" }, { type: "null" }] });
    expect(nullable).toBe(true);
    expect(prop.type).toBe("integer");
  });

  it("passes plain props through untouched (nullable false)", () => {
    const raw: SchemaProperty = { type: "boolean", default: false };
    const { prop, nullable } = unwrapOptional(raw);
    expect(nullable).toBe(false);
    expect(prop).toBe(raw);
  });
});

// ---- editorFor --------------------------------------------------------------------

describe("editorFor", () => {
  it("string + enum → enum", () => {
    expect(editorFor("mode", { type: "string", enum: ["rtl", "post_synth"] })).toBe("enum");
  });
  it("boolean → bool", () => {
    expect(editorFor("run_lint", { type: "boolean", default: true })).toBe("bool");
  });
  it("integer and number → number", () => {
    expect(editorFor("stages", { type: "integer", default: 0 })).toBe("number");
    expect(editorFor("period", { type: "number" })).toBe("number");
  });
  it("array of strings → multi", () => {
    expect(editorFor("signals", { type: "array", items: { type: "string" } })).toBe("multi");
  });
  it("array of non-strings → text (no chip editor for it)", () => {
    expect(editorFor("nums", { type: "array", items: { type: "integer" } })).toBe("text");
  });
  it("dict and list[dict] → json textarea (W7/A24)", () => {
    expect(editorFor("parameters", { type: "object" })).toBe("json");
    expect(editorFor("ports", { type: "array", items: { type: "object" } })).toBe("json");
    // Optional[dict] unwraps first.
    expect(
      editorFor("parameters", { anyOf: [{ type: "object" }, { type: "null" }], default: null })
    ).toBe("json");
  });
  it("plain string → text", () => {
    expect(editorFor("query", { type: "string" })).toBe("text");
  });
  it("unwraps Optionals before deciding (Optional[int] → number)", () => {
    expect(editorFor("end_time", { anyOf: [{ type: "integer" }, { type: "null" }], default: null })).toBe("number");
  });
});

// ---- conventionOptions ---------------------------------------------------------------

describe("conventionOptions", () => {
  it("run-id keys → synth run ids, newest first", () => {
    for (const key of ["run_id", "child_run_id", "parent_run_id", "source_run_id"]) {
      expect(conventionOptions(key, CTX)).toEqual(["synth_0002", "synth_0001"]);
    }
  });
  it("vcd_file → sim runs' vcd paths (runs without a vcd excluded)", () => {
    expect(conventionOptions("vcd_file", CTX)).toEqual([
      "sim_runs/sim_0002/dump.vcd",
      "sim_runs/sim_0001/dump.vcd",
    ]);
  });
  it("verilog_file → manifest rtl PATHS (nested files keep their path, A11)", () => {
    expect(conventionOptions("verilog_file", CTX)).toEqual(["alu.v", "top.v", "rtl/nested.v"]);
  });
  it("verilog_files → manifest rtl + include paths (the compile set)", () => {
    expect(conventionOptions("verilog_files", CTX)).toEqual([
      "alu.v",
      "top.v",
      "rtl/nested.v",
      "inc/defs.vh",
    ]);
  });
  it("sby_file / dslx_file → recursive workspace paths by extension", () => {
    expect(conventionOptions("sby_file", CTX)).toEqual(["check.sby"]);
    expect(conventionOptions("dslx_file", CTX)).toEqual(["adder.x", "hls/mul.x"]);
  });
  it("script_file → *.py paths only", () => {
    expect(conventionOptions("script_file", CTX)).toEqual(["scripts/gen_vectors.py"]);
  });
  it("spec_filename / yaml_path → *.yaml/*.yml paths", () => {
    for (const key of ["spec_filename", "yaml_path"]) {
      expect(conventionOptions(key, CTX)).toEqual(["specs/counter_spec.yaml", "legacy_spec.yml"]);
    }
  });
  it("ir_filename → *.ir excluding *.opt.ir; opt_ir_filename → *.opt.ir", () => {
    expect(conventionOptions("ir_filename", CTX)).toEqual(["ir/adder.ir"]);
    expect(conventionOptions("opt_ir_filename", CTX)).toEqual(["ir/adder.opt.ir"]);
  });
  it("filename → the whole recursive index by default", () => {
    expect(conventionOptions("filename", CTX)).toEqual(CTX.wsPaths);
  });
  it("filename is tool-aware: DSLX tools see *.x, xlscc sees *.cc (A9)", () => {
    for (const tool of ["run_dslx_interpreter", "compile_dslx_to_ir"]) {
      expect(conventionOptions("filename", CTX, tool)).toEqual(["adder.x", "hls/mul.x"]);
    }
    expect(conventionOptions("filename", CTX, "experimental_compile_cpp_to_ir")).toEqual([
      "cpp/design.cc",
    ]);
  });
  it("dead keys (spec_file / file_path / toplevel) have NO convention anymore", () => {
    for (const key of ["spec_file", "file_path", "toplevel"]) {
      expect(conventionOptions(key, CTX)).toBeNull();
    }
  });
  it("sim_top → the manifest's derived testbench modules", () => {
    expect(conventionOptions("sim_top", CTX)).toEqual(["tb", "tb2"]);
    expect(conventionOptions("sim_top", EMPTY_CTX)).toEqual([]);
  });
  it("top_module → synthTop first, then testbench modules, deduped", () => {
    expect(conventionOptions("top_module", CTX)).toEqual(["alu", "tb", "tb2"]);
    // synthTop that is also a TB module appears once.
    const ctx: SurfaceCtx = {
      ...CTX,
      manifest: { ...CTX.manifest!, synthTop: "tb" },
    };
    expect(conventionOptions("top_module", ctx)).toEqual(["tb", "tb2"]);
    expect(conventionOptions("top_module", EMPTY_CTX)).toEqual([]);
  });
  it("HLS top_module gets NO Verilog-top suggestions (free text, A9)", () => {
    for (const tool of ["run_xls_flow", "compile_dslx_to_ir"]) {
      expect(conventionOptions("top_module", CTX, tool)).toBeNull();
    }
    // Non-HLS tools keep the manifest tops.
    expect(conventionOptions("top_module", CTX, "schematic_tool")).toEqual(["alu", "tb", "tb2"]);
  });
  it("returns null when no convention applies (falls back to enum/free input)", () => {
    expect(conventionOptions("query", CTX)).toBeNull();
    expect(conventionOptions("signals", CTX)).toBeNull();
  });
  it("run conventions still apply (empty list) with no runs", () => {
    expect(conventionOptions("run_id", EMPTY_CTX)).toEqual([]);
  });
});

// ---- valueKindFor / suggestionSubtitles ------------------------------------------

describe("valueKindFor", () => {
  it("labels file-valued and module-valued keys; undefined otherwise", () => {
    for (const key of ["filename", "verilog_file", "verilog_files", "vcd_file", "spec_filename", "script_file"]) {
      expect(valueKindFor(key)).toBe("file");
    }
    for (const key of ["sim_top", "top_module", "module_name"]) {
      expect(valueKindFor(key)).toBe("module");
    }
    expect(valueKindFor("query")).toBeUndefined();
    expect(valueKindFor("run_id")).toBeUndefined();
  });
});

describe("suggestionSubtitles", () => {
  it("module keys → module → defining file (from manifest.testbenches)", () => {
    expect(suggestionSubtitles("sim_top", CTX)).toEqual({ tb: "tb.v", tb2: "sub/tb2.v" });
    expect(suggestionSubtitles("top_module", CTX)).toEqual({ tb: "tb.v", tb2: "sub/tb2.v" });
  });
  it("file keys → path → manifest role", () => {
    const subs = suggestionSubtitles("verilog_files", CTX);
    expect(subs["alu.v"]).toBe("rtl");
    expect(subs["inc/defs.vh"]).toBe("include");
    expect(subs["sub/tb2.v"]).toBe("tb");
  });
  it("empty without a manifest; unknown keys empty", () => {
    expect(suggestionSubtitles("sim_top", EMPTY_CTX)).toEqual({});
    expect(suggestionSubtitles("query", CTX)).toEqual({});
  });
});

// ---- paramSourceFor --------------------------------------------------------------------

describe("paramSourceFor", () => {
  it("run-ish keys with convention options → run", () => {
    expect(paramSourceFor("run_id", optionalString(), true)).toBe("run");
    expect(paramSourceFor("child_run_id", { type: "string" }, true)).toBe("run");
  });
  it("manifest keys → manifest when the default comes from the manifest, else choice", () => {
    expect(paramSourceFor("platform", { type: "string" }, false, true)).toBe("manifest");
    expect(paramSourceFor("clock_period_ns", { type: "number" }, false, true)).toBe("manifest");
    expect(paramSourceFor("top_module", { type: "string" }, false, false)).toBe("choice");
  });
  it("schema enum → choice", () => {
    expect(paramSourceFor("stage", { type: "string", enum: ["route", "cts"] }, false)).toBe("choice");
  });
  it("workspace-supplied options (vcd_file etc.) → choice", () => {
    expect(paramSourceFor("vcd_file", { type: "string" }, true)).toBe("choice");
  });
  it("schema default → default; bare field → text", () => {
    expect(paramSourceFor("end_time", { type: "integer", default: 1000 }, false)).toBe("default");
    expect(paramSourceFor("query", { type: "string" }, false)).toBe("text");
  });
});

// ---- defaultFor ------------------------------------------------------------------------

describe("defaultFor", () => {
  it("REQUIRED run_id defaults to the newest synth run", () => {
    expect(defaultFor("run_id", { type: "string" }, CTX, true)).toBe("synth_0002");
    expect(defaultFor("child_run_id", { type: "string" }, CTX, true)).toBe("synth_0002");
  });
  it("optional run_id (default null) defaults to '' → omitted from the payload", () => {
    expect(defaultFor("run_id", optionalString(), CTX, false)).toBe("");
  });
  it("REQUIRED vcd_file defaults to the newest sim vcd", () => {
    expect(defaultFor("vcd_file", { type: "string" }, CTX, true)).toBe("sim_runs/sim_0002/dump.vcd");
  });
  it("manifest-sourced keys pull the manifest value", () => {
    expect(defaultFor("platform", { type: "string", default: "sky130hd" }, CTX, false)).toBe("asap7");
    expect(defaultFor("clock_period_ns", { type: "number" }, CTX, false)).toBe(12.5);
    expect(defaultFor("clockPeriodNs", { type: "number" }, CTX, false)).toBe(12.5);
    expect(defaultFor("top_module", { type: "string" }, CTX, true)).toBe("alu");
    expect(defaultFor("sim_top", { type: "string" }, CTX, false)).toBe("tb");
  });
  it("falls back to the schema default when the manifest has no value", () => {
    expect(defaultFor("platform", { type: "string", default: "sky130hd" }, EMPTY_CTX, false)).toBe("sky130hd");
    expect(defaultFor("end_time", { type: "integer", default: 1000 }, EMPTY_CTX, false)).toBe(1000);
    expect(defaultFor("run_lint", { type: "boolean", default: true }, EMPTY_CTX, false)).toBe(true);
  });
  it("type-appropriate empties when nothing supplies a value", () => {
    expect(defaultFor("query", { type: "string" }, EMPTY_CTX, true)).toBe("");
    expect(defaultFor("stages", { type: "integer" }, EMPTY_CTX, false)).toBe(0);
    expect(defaultFor("flag", { type: "boolean" }, EMPTY_CTX, false)).toBe(false);
    expect(defaultFor("signals", { type: "array", items: { type: "string" } }, EMPTY_CTX, true)).toEqual([]);
  });
  it("a null schema default is treated as empty, not null", () => {
    expect(defaultFor("content", optionalString(null), EMPTY_CTX, false)).toBe("");
  });
  it("required ARRAY fields never take a single suggestion, and plural file fields start EMPTY", () => {
    // Owner refinement (2026-08-14): pre-filling the manifest set produced a
    // wall of chips the user had to prune. The field starts empty; the set is
    // what "empty" MEANS (placeholder + payload injection), not a value.
    const arrProp: SchemaProperty = { type: "array", items: { type: "string" } };
    expect(defaultFor("verilog_files", arrProp, CTX, true)).toEqual([]);
    expect(defaultFor("verilog_files", arrProp, EMPTY_CTX, true)).toEqual([]);
  });
});

// ---- manifestValueFor / manifestFileSet / basicOrAdvanced -----------------------------------

describe("manifestValueFor", () => {
  it("resolves platform/clock/top/sim_top; undefined otherwise or without a manifest", () => {
    expect(manifestValueFor("platform", CTX)).toBe("asap7");
    expect(manifestValueFor("top_module", CTX)).toBe("alu");
    expect(manifestValueFor("query", CTX)).toBeUndefined();
    expect(manifestValueFor("platform", EMPTY_CTX)).toBeUndefined();
  });
  it("plural file keys are NOT scalar manifest values (they never pre-fill a field)", () => {
    expect(manifestValueFor("verilog_files", CTX)).toBeUndefined();
  });
});

describe("manifestFileSet", () => {
  it("verilog_files → the manifest's rtl + include paths; undefined when empty", () => {
    expect(manifestFileSet("verilog_files", CTX)).toEqual([
      "alu.v",
      "top.v",
      "rtl/nested.v",
      "inc/defs.vh",
    ]);
    expect(manifestFileSet("verilog_files", EMPTY_CTX)).toBeUndefined();
    expect(manifestFileSet("verilog_file", CTX)).toBeUndefined(); // singular: a plain combo
  });
  it("the placeholder states what an empty field runs, with honest pluralization", () => {
    expect(manifestSetPlaceholder(["a.v", "b.v"])).toBe(
      "manifest set (2 files) — type to override"
    );
    expect(manifestSetPlaceholder(["a.v"])).toBe("manifest set (1 file) — type to override");
  });
});

describe("basicOrAdvanced", () => {
  it("required → basic", () => {
    expect(basicOrAdvanced("anything", true, false)).toBe("basic");
  });
  it("convention options → basic", () => {
    expect(basicOrAdvanced("run_id", false, true)).toBe("basic");
  });
  it("whitelisted keys (query/stage/mode/generator) → basic", () => {
    for (const key of ["query", "stage", "mode", "generator"]) {
      expect(basicOrAdvanced(key, false, false)).toBe("basic");
    }
  });
  it("optional, unconventional keys → advanced", () => {
    expect(basicOrAdvanced("use_system_verilog", false, false)).toBe("advanced");
  });
});

// ---- shortDescription ------------------------------------------------------------------------

describe("shortDescription", () => {
  it("cuts at the Args: section", () => {
    expect(
      shortDescription("Writes content to a file in the workspace.\nArgs:\n  filename: Name.")
    ).toBe("Writes content to a file in the workspace.");
  });
  it("cuts at an indented Args:", () => {
    expect(shortDescription("Does things.\n    Args:\n        x: y")).toBe("Does things.");
  });
  it("cuts at the first blank line", () => {
    expect(shortDescription("Summary line.\n\nLong details follow.")).toBe("Summary line.");
  });
  it("keeps multi-line summaries without Args/blank line, trimmed", () => {
    expect(shortDescription("  Returns metrics.\nParses ORFS outputs.  ")).toBe(
      "Returns metrics.\nParses ORFS outputs."
    );
  });
  it("handles empty input", () => {
    expect(shortDescription("")).toBe("");
  });
});

// ---- buildFormModel (end to end) ------------------------------------------------------------------

const WAVEFORM_ENTRY: ToolCatalogEntry = {
  name: "waveform_tool",
  description:
    "Reads a VCD waveform file to inspect signal values.\nArgs:\n  vcd_file: Name of the .vcd file.",
  category: "verification",
  argsSchema: {
    type: "object",
    properties: {
      vcd_file: { type: "string" },
      signals: { type: "array", items: { type: "string" } },
      start_time: { type: "integer", default: 0 },
      end_time: { type: "integer", default: 1000 },
    },
    required: ["vcd_file", "signals"],
  },
  requiresSignIn: false,
  async: false,
  mutates: false,
};

const METRICS_ENTRY: ToolCatalogEntry = {
  name: "get_synthesis_metrics",
  description: "Returns structured synthesis metrics for a run.",
  category: "synthesis",
  argsSchema: {
    type: "object",
    properties: { run_id: { anyOf: [{ type: "string" }, { type: "null" }], default: null } },
    required: [],
  },
  requiresSignIn: true,
  async: false,
  mutates: false,
};

describe("buildFormModel", () => {
  it("waveform_tool: required vcd_file upgrades to a combobox with the newest vcd as default", () => {
    const params = buildFormModel(WAVEFORM_ENTRY, CTX);
    const vcd = params.find((p) => p.key === "vcd_file")!;
    expect(vcd.editor).toBe("combo"); // text → suggestions, free entry allowed
    expect(vcd.options).toEqual(["sim_runs/sim_0002/dump.vcd", "sim_runs/sim_0001/dump.vcd"]);
    expect(vcd.def).toBe("sim_runs/sim_0002/dump.vcd");
    expect(vcd.optional).toBe(false);
    expect(vcd.adv).toBe(false);
    expect(vcd.source).toBe("choice");
  });

  it("plain string fields with workspace choices map to combo (free entry stays honest)", () => {
    const entry: ToolCatalogEntry = {
      ...METRICS_ENTRY,
      name: "t_combo",
      argsSchema: {
        type: "object",
        properties: {
          filename: { type: "string" },
          sim_top: { type: "string" },
          top_module: { type: "string" },
        },
        required: ["filename"],
      },
    };
    const params = buildFormModel(entry, CTX);
    const byKey = Object.fromEntries(params.map((p) => [p.key, p]));
    expect(byKey.filename.editor).toBe("combo");
    expect(byKey.sim_top.editor).toBe("combo");
    expect(byKey.sim_top.options).toEqual(["tb", "tb2"]);
    expect(byKey.sim_top.def).toBe("tb"); // manifest simTop backs the default
    expect(byKey.top_module.editor).toBe("combo");
    expect(byKey.top_module.options).toEqual(["alu", "tb", "tb2"]);
    // Combos never get the "(omit)" sentinel entry — clearing the text omits.
    expect(byKey.sim_top.options).not.toContain("");
  });

  it("run_id-family fields KEEP the closed enum (runs are a closed set)", () => {
    const [runId] = buildFormModel(METRICS_ENTRY, CTX);
    expect(runId.editor).toBe("enum");
  });

  it("waveform_tool: required signals is a freeform multi (no options), default []", () => {
    const params = buildFormModel(WAVEFORM_ENTRY, CTX);
    const signals = params.find((p) => p.key === "signals")!;
    expect(signals.editor).toBe("multi");
    expect(signals.options).toBeUndefined();
    expect(signals.def).toEqual([]);
    expect(signals.adv).toBe(false); // required → basic
  });

  it("waveform_tool: optional integers land in advanced with integer step", () => {
    const params = buildFormModel(WAVEFORM_ENTRY, CTX);
    const end = params.find((p) => p.key === "end_time")!;
    expect(end.editor).toBe("number");
    expect(end.def).toBe(1000);
    expect(end.step).toBe(1);
    expect(end.adv).toBe(true);
    expect(end.optional).toBe(true);
  });

  it("get_synthesis_status(run_id): the RUN_ID_KEYS convention gives it the run picker", () => {
    // The Wave-9 status tool (get_synthesis_job's replacement) takes run_id —
    // the convention hands it the closed run combobox automatically, with the
    // newest run as the required default. No per-tool code.
    const statusEntry: ToolCatalogEntry = {
      name: "get_synthesis_status",
      description: "Returns the self-healing status of a synthesis run.",
      category: "synthesis",
      argsSchema: {
        type: "object",
        properties: { run_id: { type: "string" } },
        required: ["run_id"],
      },
      requiresSignIn: true,
      async: false,
      mutates: false,
    };
    const [runId] = buildFormModel(statusEntry, CTX);
    expect(runId).toMatchObject({
      key: "run_id",
      editor: "enum",
      source: "run",
      def: "synth_0002", // newest run pre-selected
      optional: false,
      adv: false,
    });
    expect(runId.options).toEqual(["synth_0002", "synth_0001"]);
  });

  it("get_synthesis_metrics: optional run_id → run-sourced picker with an (omit) entry", () => {
    const [runId] = buildFormModel(METRICS_ENTRY, CTX);
    expect(runId.key).toBe("run_id");
    expect(runId.label).toBe("run_id");
    expect(runId.editor).toBe("enum");
    expect(runId.source).toBe("run");
    expect(runId.options).toEqual(["", "synth_0002", "synth_0001"]);
    expect(runId.def).toBe(""); // omitted from the payload by default
    expect(runId.optional).toBe(true);
    expect(runId.adv).toBe(false);
  });

  it("number bounds come from the schema (minimum/exclusiveMinimum/multipleOf)", () => {
    const entry: ToolCatalogEntry = {
      ...METRICS_ENTRY,
      name: "t",
      argsSchema: {
        type: "object",
        properties: {
          a: { type: "number", exclusiveMinimum: 0 },
          b: { type: "number", minimum: 1, multipleOf: 0.5 },
        },
        required: [],
      },
    };
    const [a, b] = buildFormModel(entry, EMPTY_CTX);
    expect(a.min).toBe(0);
    expect(a.step).toBe(0.1); // sensible float step when multipleOf absent
    expect(b.min).toBe(1);
    expect(b.step).toBe(0.5);
  });

  it("per-property descriptions become hints; enums become choice options", () => {
    const entry: ToolCatalogEntry = {
      ...METRICS_ENTRY,
      name: "t2",
      argsSchema: {
        type: "object",
        properties: {
          stage: { type: "string", enum: ["floorplan", "route"], description: "PD stage to read" },
        },
        required: ["stage"],
      },
    };
    const [stage] = buildFormModel(entry, EMPTY_CTX);
    expect(stage.editor).toBe("enum");
    expect(stage.options).toEqual(["floorplan", "route"]);
    expect(stage.hint).toBe("PD stage to read");
    expect(stage.source).toBe("choice");
  });

  it("tolerates an empty/missing argsSchema", () => {
    const entry = { ...METRICS_ENTRY, name: "t3", argsSchema: {} } as ToolCatalogEntry;
    expect(buildFormModel(entry, EMPTY_CTX)).toEqual([]);
  });

  const COCOTB_ENTRY: ToolCatalogEntry = {
    ...METRICS_ENTRY,
    name: "cocotb_tool",
    argsSchema: {
      type: "object",
      properties: {
        verilog_files: { type: "array", items: { type: "string" } },
        top_module: { type: "string" },
        python_module: { type: "string" },
      },
      required: ["verilog_files", "top_module", "python_module"],
    },
  };

  it("cocotb-style verilog_files: EMPTY multi-combo, manifest badge, set behind the placeholder", () => {
    const byKey = Object.fromEntries(buildFormModel(COCOTB_ENTRY, CTX).map((p) => [p.key, p]));
    expect(byKey.verilog_files.editor).toBe("multi");
    // The SUGGESTED tier is still the manifest compile set…
    expect(byKey.verilog_files.options).toEqual(["alu.v", "top.v", "rtl/nested.v", "inc/defs.vh"]);
    expect(byKey.verilog_files.source).toBe("manifest");
    // …but the FIELD starts empty — no 13-chip wall (owner, 2026-08-14).
    expect(byKey.verilog_files.def).toEqual([]);
    expect(byKey.verilog_files.placeholder).toBe(
      "manifest set (4 files) — type to override"
    );
    // The tool REQUIRES the list, so empty is filled at payload time.
    expect(byKey.verilog_files.fillFromManifest).toBe(true);
    expect(byKey.verilog_files.manifestDefault?.(CTX)).toEqual([
      "alu.v",
      "top.v",
      "rtl/nested.v",
      "inc/defs.vh",
    ]);
    expect(byKey.verilog_files.valueKind).toBe("file");
    // File-role subtitles ride along for the combo rows.
    expect(byKey.verilog_files.subtitles?.(CTX)).toMatchObject({ "alu.v": "rtl" });
    expect(byKey.top_module.valueKind).toBe("module");
  });

  it("no manifest set → no placeholder, no injection promise (honest empty field)", () => {
    const byKey = Object.fromEntries(
      buildFormModel(COCOTB_ENTRY, EMPTY_CTX).map((p) => [p.key, p])
    );
    expect(byKey.verilog_files.def).toEqual([]);
    expect(byKey.verilog_files.placeholder).toBeUndefined();
    expect(byKey.verilog_files.manifestDefault).toBeUndefined();
    expect(byKey.verilog_files.source).toBe("choice"); // nothing manifest-backed to claim
  });

  it("an OPTIONAL plural file field keeps 'empty = omit the key' (no injection)", () => {
    const optionalPlural: ToolCatalogEntry = {
      ...COCOTB_ENTRY,
      name: "some_optional_tool",
      argsSchema: {
        type: "object",
        properties: { verilog_files: { type: "array", items: { type: "string" } } },
        required: [],
      },
    };
    const [files] = buildFormModel(optionalPlural, CTX);
    expect(files.def).toEqual([]);
    expect(files.fillFromManifest).toBeUndefined();
    // The placeholder still tells the truth about what empty runs.
    expect(files.placeholder).toBe("manifest set (4 files) — type to override");
  });

  it("json params carry jsonKind and a STRING default (structured defaults pretty-print)", () => {
    const entry: ToolCatalogEntry = {
      ...METRICS_ENTRY,
      name: "t_json",
      argsSchema: {
        type: "object",
        properties: {
          parameters: { anyOf: [{ type: "object" }, { type: "null" }], default: null },
          ports: { type: "array", items: { type: "object" } },
          preset: { type: "object", default: { WIDTH: 8 } },
        },
        required: ["ports"],
      },
    };
    const byKey = Object.fromEntries(buildFormModel(entry, EMPTY_CTX).map((p) => [p.key, p]));
    expect(byKey.parameters).toMatchObject({ editor: "json", jsonKind: "object", def: "" });
    expect(byKey.ports).toMatchObject({ editor: "json", jsonKind: "array", def: "" });
    // A structured schema default becomes editable JSON text.
    expect(byKey.preset.def).toBe(JSON.stringify({ WIDTH: 8 }, null, 2));
  });

  it("HLS tools: filename filters to *.x and top_module is free text with an honest hint (A9)", () => {
    const entry: ToolCatalogEntry = {
      ...METRICS_ENTRY,
      name: "compile_dslx_to_ir",
      argsSchema: {
        type: "object",
        properties: {
          filename: { type: "string" },
          top_module: { type: "string" },
        },
        required: ["filename", "top_module"],
      },
    };
    const byKey = Object.fromEntries(buildFormModel(entry, CTX).map((p) => [p.key, p]));
    expect(byKey.filename.editor).toBe("combo");
    expect(byKey.filename.options).toEqual(["adder.x", "hls/mul.x"]);
    // No Verilog tops suggested — a DSLX function is not in the manifest —
    // and the manifest's synthTop must NOT leak in as its default or badge.
    expect(byKey.top_module.editor).toBe("text");
    expect(byKey.top_module.options).toBeUndefined();
    expect(byKey.top_module.def).toBe("");
    expect(byKey.top_module.source).toBe("text");
    expect(byKey.top_module.hint).toMatch(/not tracked by the manifest/);
  });
});
