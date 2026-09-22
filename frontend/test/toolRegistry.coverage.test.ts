import { describe, expect, it } from "vitest";

import { TOOL_KIND_MAP } from "@/lib/activityFilters";
import { COMMANDS, RUN_ORDER } from "@/lib/commands";
import { CORE_TWIN_TOOLS, buildSurfaceCommands, categoryLabel } from "@/lib/commandSurface";
import {
  RUN_DIR_PREFIX,
  SIM_TOOLS,
  SYNTH_DISPATCH_TOOLS,
  TOOL,
  WORKSPACE_MUTATING_TOOLS,
} from "@/lib/toolNames";
import { TOOL_ARTIFACT_RESOLVERS } from "@/lib/toolArtifacts";
import { SURFACE_ICONS } from "@/components/workbench/CommandSurface";
import { TOOL_LABELS } from "@/components/workbench/LivePill";
import { backendToolNames, backendTools, uiCatalogTools } from "./support/backendToolRegistry";
import type { ToolCatalogEntry } from "@/types";

/**
 * The frontend keeps a handful of tool-name-keyed maps. Each one degrades
 * SILENTLY when a tool is renamed, merged or deleted: no exception, no failing
 * test, just a missing icon, a tool that drops out of a filter, an artifact
 * button that stops appearing. This file is the red test that replaces that
 * silence — it reads the real backend registry (see ./support) and holds every
 * surviving map to it.
 *
 * Two shapes of assertion:
 *   LIVENESS  — every key names a tool that still exists. Applies to all maps.
 *   TOTALITY  — every catalog tool has an entry. Applies only where an omission
 *               visibly degrades the UI; where "no entry" is an honest answer
 *               (no artifact to open, no pill of its own), only liveness holds
 *               and the reason is written down in the map itself.
 */

const live = backendToolNames();
const uiTools = uiCatalogTools();

const expectAllLive = (names: Iterable<string>, what: string) => {
  const dead = Array.from(names).filter((n) => !live.has(n));
  expect(dead, `${what} names tool(s) the backend registry no longer has`).toEqual([]);
};

describe("liveness — every hardcoded tool name still exists", () => {
  it("the registry parse itself found the real tools", () => {
    // Guards against a vacuous suite: an empty/short registry would make every
    // liveness assertion below pass by accident.
    expect(backendTools().length).toBeGreaterThan(30);
    expect(live.has(TOOL.startSynthesis)).toBe(true);
  });

  it("lib/toolNames TOOL constants", () => expectAllLive(Object.values(TOOL), "TOOL"));
  it("lib/toolNames WORKSPACE_MUTATING_TOOLS", () =>
    expectAllLive(WORKSPACE_MUTATING_TOOLS, "WORKSPACE_MUTATING_TOOLS"));
  it("lib/toolNames RUN_DIR_PREFIX", () =>
    expectAllLive(Object.keys(RUN_DIR_PREFIX), "RUN_DIR_PREFIX"));
  it("lib/toolNames SYNTH_DISPATCH_TOOLS / SIM_TOOLS", () => {
    expectAllLive(SYNTH_DISPATCH_TOOLS, "SYNTH_DISPATCH_TOOLS");
    expectAllLive(SIM_TOOLS, "SIM_TOOLS");
  });
  it("lib/activityFilters TOOL_KIND_MAP", () =>
    expectAllLive(Object.keys(TOOL_KIND_MAP), "TOOL_KIND_MAP"));
  it("lib/toolArtifacts TOOL_ARTIFACT_RESOLVERS", () =>
    expectAllLive(Object.keys(TOOL_ARTIFACT_RESOLVERS), "TOOL_ARTIFACT_RESOLVERS"));
  it("components/workbench/LivePill TOOL_LABELS", () =>
    expectAllLive(Object.keys(TOOL_LABELS), "TOOL_LABELS"));
  it("lib/commands COMMANDS tools", () => {
    expectAllLive(
      RUN_ORDER.map((id) => COMMANDS[id].tool),
      "COMMANDS"
    );
    expectAllLive(CORE_TWIN_TOOLS, "CORE_TWIN_TOOLS");
  });
  it("CommandSurface SURFACE_ICONS (core command ids aside)", () => {
    const coreIds = new Set<string>(RUN_ORDER);
    expectAllLive(
      Object.keys(SURFACE_ICONS).filter((k) => !coreIds.has(k)),
      "SURFACE_ICONS"
    );
  });
});

describe("totality — an omission here would quietly blunt the UI", () => {
  it("every catalog tool has an icon (no silent Terminal fallback)", () => {
    const missing = uiTools
      .filter((t) => !CORE_TWIN_TOOLS.has(t.name)) // core four render by command id
      .map((t) => t.name)
      .filter((n) => !(n in SURFACE_ICONS));
    expect(
      missing,
      "tool(s) with no entry in SURFACE_ICONS — they render a generic Terminal glyph"
    ).toEqual([]);
  });

  it("every mutating tool invalidates the file tree", () => {
    const missing = backendTools()
      .filter((t) => t.mutates && !WORKSPACE_MUTATING_TOOLS.has(t.name))
      .map((t) => t.name);
    expect(
      missing,
      "tool(s) the backend marks `mutates` that leave the client's file tree stale"
    ).toEqual([]);
  });

  it("nothing is claimed to mutate that the backend says does not", () => {
    const byName = new Map(backendTools().map((t) => [t.name, t]));
    const wrong = Array.from(WORKSPACE_MUTATING_TOOLS).filter((n) => byName.get(n)?.mutates === false);
    expect(wrong, "tool(s) listed as mutating that the backend says are read-only").toEqual([]);
  });

  it("every synthesis-category tool answers to the Synth filter pill", () => {
    const missing = uiTools
      .filter((t) => t.category === "synthesis" && TOOL_KIND_MAP[t.name] !== "synth")
      .map((t) => t.name);
    expect(missing, "synthesis tool(s) missing from the Activity feed's Synth pill").toEqual([]);
  });

  it("the core commands' async flag agrees with the tool's policy", () => {
    const byName = new Map(backendTools().map((t) => [t.name, t]));
    for (const id of RUN_ORDER) {
      const def = COMMANDS[id];
      expect(def.async, `${id} (${def.tool})`).toBe(byName.get(def.tool)!.asyncJob);
    }
  });
});

describe("the catalog's category ORDER is the palette's group order", () => {
  const entry = (name: string, category: string): ToolCatalogEntry => ({
    name,
    description: "",
    category,
    argsSchema: { type: "object", properties: {} },
    requiresSignIn: false,
    async: false,
    mutates: false,
  });
  const ctx = { manifest: null, runs: [], wsPaths: [], wsPathsTruncated: false };

  it("renders backend categories in first-seen order, Flow pinned first", () => {
    // The backend emits the catalog already sorted by its CATEGORY_ORDER; the
    // surface must not re-sort, dedupe through a Set, or hang the grouping off
    // an object literal whose key order it controls.
    const catalog = uiTools.map((t) => entry(t.name, t.category));
    const seen: string[] = [];
    for (const t of uiTools) if (!seen.includes(t.category)) seen.push(t.category);

    const groups = buildSurfaceCommands(catalog, ctx).groups.map((g) => g.label);
    expect(groups).toEqual(["Flow", ...seen.map(categoryLabel)]);
  });

  it("preserves an unfamiliar order rather than imposing its own", () => {
    const catalog = [entry("z_tool", "synthesis"), entry("a_tool", "essential")];
    expect(buildSurfaceCommands(catalog, ctx).groups.map((g) => g.label)).toEqual([
      "Flow",
      "Synthesis",
      "Essential",
    ]);
  });

  it("labels every backend category non-trivially", () => {
    for (const t of uiTools) {
      expect(categoryLabel(t.category), t.category).toMatch(/^[A-Z]/);
    }
  });
});
