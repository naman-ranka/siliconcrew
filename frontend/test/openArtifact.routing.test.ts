import { describe, it, expect } from "vitest";

import { artifactKeyForFile, artifactLabel } from "@/lib/openArtifact";

describe("artifactKeyForFile — rich viewer routing (PA8)", () => {
  it("routes raster images to image:, leaving svg with the schematic viewer", () => {
    expect(artifactKeyForFile("out/plot.png")).toBe("image:out/plot.png");
    expect(artifactKeyForFile("wave.JPG")).toBe("image:wave.JPG");
    expect(artifactKeyForFile("fig.webp")).toBe("image:fig.webp");
    // standalone svg (not run-scoped) stays a schematic
    expect(artifactKeyForFile("cpu_top.svg")).toBe("schematic:cpu_top.svg");
  });

  it("routes data files to data: (but keeps *_spec.yaml as the spec singleton)", () => {
    expect(artifactKeyForFile("vectors.csv")).toBe("data:vectors.csv");
    expect(artifactKeyForFile("golden.tsv")).toBe("data:golden.tsv");
    expect(artifactKeyForFile("meta.json")).toBe("data:meta.json");
    expect(artifactKeyForFile("config.yaml")).toBe("data:config.yaml");
    expect(artifactKeyForFile("alu_spec.yaml")).toBe("spec");
  });

  it("routes plain text families to text:, everything else to code:", () => {
    expect(artifactKeyForFile("run.log")).toBe("text:run.log");
    expect(artifactKeyForFile("notes.txt")).toBe("text:notes.txt");
    expect(artifactKeyForFile("timing.rpt")).toBe("text:timing.rpt");
    expect(artifactKeyForFile("alu.v")).toBe("code:alu.v");
  });

  it("run-scoped artifacts keep their dedicated viewers over the extension map", () => {
    expect(artifactKeyForFile("sim_runs/sim_0001/dump.vcd")).toBe("wave:sim_0001");
    expect(artifactKeyForFile("synth_runs/synth_0002/6_final.gds")).toBe("layout:synth_0002");
    expect(artifactKeyForFile("synth_runs/synth_0002/report.md")).toBe("report:synth_0002");
  });

  it("loose VCDs (outside run dirs) open in the waveform viewer via wavefile:", () => {
    expect(artifactKeyForFile("dump.vcd")).toBe("wavefile:dump.vcd");
    expect(artifactKeyForFile("scratch/tb_alu.VCD")).toBe("wavefile:scratch/tb_alu.VCD");
  });
});

describe("artifactLabel — new kinds label by basename (PA8)", () => {
  it("labels image/data/text/wavefile by filename", () => {
    expect(artifactLabel("image:out/plot.png")).toBe("plot.png");
    expect(artifactLabel("data:sub/vectors.csv")).toBe("vectors.csv");
    expect(artifactLabel("text:run.log")).toBe("run.log");
    expect(artifactLabel("wavefile:scratch/dump.vcd")).toBe("dump.vcd");
  });
});
