# Python Analysis Tool and Rich Artifacts Plan

## Intent

SiliconCrew should add a workspace-scoped Python analysis capability and improve artifact viewing so generated analysis outputs are visible and useful in the IDE. The goal is not to replace RTL simulation, cocotb verification, formal tools, or synthesis flows. The goal is to give agents and users a lightweight way to generate and inspect supporting engineering artifacts around those flows.

This plan captures the product intent and high-level direction. It intentionally avoids strict implementation details so the final design can fit the evolving backend, MCP, and frontend architecture.

## Why This Matters

Hardware design work often requires more than RTL files and simulator pass/fail logs. Engineers routinely create reference data, plots, lookup tables, memory images, packet traces, and numerical summaries while developing and verifying a design. SiliconCrew should support that workflow directly.

A Python analysis tool would help with tasks such as:

- generating golden reference outputs for RTL tests;
- creating stimulus vectors, memory initialization files, and lookup tables;
- validating fixed-point arithmetic, CRCs, encoders, filters, and DSP blocks;
- plotting simulation results or expected waveforms;
- post-processing logs, CSV files, VCD-derived data, and generated reports;
- producing visual proof artifacts that make debugging and review easier.

This is especially useful for designs where correctness depends on mathematical behavior, protocol encoding, signal quality, or comparison against a reference model.

## Relationship to Cocotb

The Python analysis capability should complement `cocotb_tool`, not duplicate it.

`cocotb_tool` should remain the authoritative way to run Python-based RTL verification against a simulator. It answers the question: did this RTL pass this cocotb testbench?

The Python analysis tool should answer a different question: can we run a small workspace-local Python script to generate, inspect, or summarize supporting artifacts?

Examples of good separation:

| Need | Preferred Capability |
| --- | --- |
| Run RTL with a cocotb testbench | `cocotb_tool` |
| Generate golden vectors before simulation | Python analysis tool |
| Plot collected output samples | Python analysis tool |
| Generate `.mem`, `.hex`, `.csv`, or `.json` artifacts | Python analysis tool |
| Debug waveform signal values | Waveform tooling |
| Run synthesis or collect PPA | Synthesis/reporting tooling |

Keeping this boundary clear prevents the Python tool from becoming a substitute for simulator-backed verification.

## Expected Python Capability

The tool should be workspace-scoped and intended for small analysis jobs. It should be useful for numerical computing and artifact generation while remaining constrained enough to preserve reproducibility and safety.

The expected library posture is:

- allow Python standard-library modules useful for math, parsing, binary data, JSON, CSV, and file generation;
- allow already-supported analysis libraries such as NumPy and Matplotlib for numerical work and plotting;
- allow structured-data helpers such as YAML support where useful;
- consider VCD and GDS helper libraries where they support analysis or visualization workflows;
- avoid package installation, network access, broad shell execution, or arbitrary host filesystem access by default.

The tool should produce clear output and ideally report any generated artifacts so the UI can surface them immediately.

## Rich Artifact Viewing

A Python analysis tool is only fully useful if the generated files are visible and understandable in the IDE. SiliconCrew should improve artifact viewing beyond the current core EDA artifact set.

The artifact experience should support common engineering outputs such as:

- images: `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`, `.svg`;
- tables and data: `.csv`, `.tsv`, `.json`, `.yaml`;
- vector and memory files: `.hex`, `.mem`, `.coe`, `.bin` metadata/download;
- text outputs: `.txt`, `.log`, `.rpt`, `.md`;
- existing EDA artifacts: `.v`, `.sv`, `.vcd`, `.gds`, `.sdc`, reports, schematics, and layout views.

The intent is to make artifacts feel like first-class engineering evidence rather than hidden files in the workspace. A generated sine-wave PNG, golden-vector CSV, or fixed-point error plot should be easy to open, inspect, and download.

## Product Direction

The recommended product direction is:

1. Add a Python analysis capability for small workspace-local scripts.
2. Keep simulator-backed verification in cocotb and other verification tools.
3. Have the Python tool report generated artifacts explicitly.
4. Improve backend artifact metadata so files have accurate MIME types and kinds.
5. Improve the frontend artifact viewer to render images, JSON, CSV/table-like data, text, and unknown binaries appropriately.
6. Keep the tool outside the minimal/essential tool set so it does not distract from simple RTL workflows.

## Success Criteria

This effort is successful when a user or agent can:

- generate a golden reference file with Python;
- run RTL verification separately using cocotb or simulation tooling;
- generate a plot from collected or expected data;
- see the plot directly in the artifact viewer;
- inspect CSV/JSON/vector artifacts without leaving the IDE;
- download generated artifacts for external review;
- understand from the UI which artifacts were produced by a tool call.

## Non-Goals

This plan does not aim to:

- replace `cocotb_tool`;
- replace waveform debugging tools;
- provide unrestricted shell access;
- install arbitrary Python packages at runtime;
- turn the artifact viewer into a full notebook environment;
- define final implementation APIs or UI component structure.

## High-Level Rationale

The combination of a constrained Python analysis tool and richer artifact viewing would make SiliconCrew more useful for realistic hardware development. It would support the natural loop of generate reference data, verify RTL, inspect outputs, visualize behavior, and preserve reviewable evidence.

This is a natural extension of the current tool-based architecture because it builds around existing ideas: session workspaces, tool execution, generated artifacts, and IDE artifact viewers. The change is primarily about broadening what kinds of supporting engineering artifacts SiliconCrew can create and display.
