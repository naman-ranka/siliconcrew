import { describe, it, expect } from "vitest";
import { artifactKeyForToolCall } from "@/lib/toolArtifacts";
import { artifactKeyForFile } from "@/lib/openArtifact";

describe("dashboard artifact keys agree across every entry point", () => {
  const FILE = "simon.dashboard.html";

  it("write_file, edit_file_tool, apply_patch_tool and the file tree all yield ONE key", () => {
    const expected = `interactive:${FILE}`;
    expect(artifactKeyForToolCall("write_file", { filename: FILE })).toBe(expected);
    expect(artifactKeyForToolCall("edit_file_tool", { filename: FILE })).toBe(expected);
    // apply_patch must not reintroduce the dual-tab-key bug (code: vs interactive:)
    expect(artifactKeyForToolCall("apply_patch_tool", { filename: FILE })).toBe(expected);
    expect(
      artifactKeyForToolCall("apply_patch_tool", {
        unified_diff: `--- a/${FILE}\n+++ b/${FILE}\n@@ -1 +1 @@\n-x\n+y\n`,
      })
    ).toBe(expected);
    expect(artifactKeyForFile(FILE)).toBe(expected);
  });

  it("non-dashboard writes still open as code", () => {
    expect(artifactKeyForToolCall("write_file", { filename: "alu.v" })).toBe("code:alu.v");
    expect(artifactKeyForToolCall("apply_patch_tool", { filename: "alu.v" })).toBe("code:alu.v");
  });

  it("build_interactive_sim derives the websim key from args, not result prose", () => {
    expect(
      artifactKeyForToolCall("build_interactive_sim", { top_module: "simon" }, "any prose at all")
    ).toBe("data:simon.websim.json");
    expect(artifactKeyForToolCall("build_interactive_sim", {}, "no args")).toBeNull();
  });
});
