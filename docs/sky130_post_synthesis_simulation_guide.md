# Sky130 Post-Synthesis Simulation Guide (General)

This is a general flow to run gate-level (post-synthesis) simulation for designs targeting **SkyWater 130 HD** (`sky130_fd_sc_hd`).

## 1. What You Need

- Synthesized gate-level netlist (for example `1_synth.v` or `6_final.v`)
- Testbench (`tb.v`)
- Icarus Verilog (`iverilog`) and `vvp`
- Sky130 standard-cell simulation model files (`sky130_fd_sc_hd__*.v`)

## 2. Download Sky130 Standard-Cell Models (Repo Method)

This guide uses the **GitHub repository method only** (no Docker).

Target repo:
- `https://github.com/google/skywater-pdk-libs-sky130_fd_sc_hd`

### 2.1 Clone or Download the Library

Option A: `git clone` (recommended)

```bash
git clone https://github.com/google/skywater-pdk-libs-sky130_fd_sc_hd.git
```

Option B: Download ZIP from GitHub and extract it.

### 2.2 Create a Local Simulation Library Folder

Create a folder where you will collect all simulation model files:

```text
libs/sky130hd_sim/
```

### 2.3 Collect Model Files from the Repo

You usually need model files from:
- `cells/*/*.v`
- `models/*/*.v`

Skip obvious non-simulation files:
- `*.tb.v`
- `*.blackbox.v`
- `*.symbol.v`

Linux/macOS example:

```bash
mkdir -p libs/sky130hd_sim
find skywater-pdk-libs-sky130_fd_sc_hd/cells -name "*.v" -exec cp {} libs/sky130hd_sim/ \;
find skywater-pdk-libs-sky130_fd_sc_hd/models -name "*.v" -exec cp {} libs/sky130hd_sim/ \;
rm -f libs/sky130hd_sim/*.tb.v libs/sky130hd_sim/*.blackbox.v libs/sky130hd_sim/*.symbol.v
```

Windows PowerShell example:

```powershell
New-Item -ItemType Directory -Force -Path .\libs\sky130hd_sim | Out-Null
Get-ChildItem .\skywater-pdk-libs-sky130_fd_sc_hd\cells -Recurse -Filter *.v | Copy-Item -Destination .\libs\sky130hd_sim -Force
Get-ChildItem .\skywater-pdk-libs-sky130_fd_sc_hd\models -Recurse -Filter *.v | Copy-Item -Destination .\libs\sky130hd_sim -Force
Get-ChildItem .\libs\sky130hd_sim\*.tb.v,.\libs\sky130hd_sim\*.blackbox.v,.\libs\sky130hd_sim\*.symbol.v -ErrorAction SilentlyContinue | Remove-Item -Force
```

### 2.4 Sanity Check the Downloaded Models

Confirm you have many files named like:
- `sky130_fd_sc_hd__and2_1.v`
- `sky130_fd_sc_hd__dfxtp_1.v`
- `sky130_fd_sc_hd__nor2_1.v`

PowerShell quick count:

```powershell
(Get-ChildItem .\libs\sky130hd_sim\sky130_fd_sc_hd__*.v).Count
```

Linux/macOS quick count:

```bash
ls libs/sky130hd_sim/sky130_fd_sc_hd__*.v | wc -l
```

## 3. Check DUT/TB Compatibility Before Running

Gate netlists often differ from RTL in elaboration details.

Verify:
- Top module name in netlist matches TB instantiation
- TB parameter override style is compatible
  - RTL TB style like `dut #(.WIDTH(8)) ...` may fail on gate netlist
- Port names and widths match netlist top module

If needed, create a **gate TB copy** and adjust only DUT instantiation/width declarations.

## 4. Build a Filelist (Recommended)

Create a compile filelist `gls.f`:

```text
/abs/path/to/tb.v
/abs/path/to/netlist.v
/abs/path/to/libs/sky130hd_sim/sky130_fd_sc_hd__and2_1.v
/abs/path/to/libs/sky130hd_sim/sky130_fd_sc_hd__dfxtp_1.v
...
```

You can include all `sky130_fd_sc_hd__*.v` models if you want simplicity.

## 5. Compile and Run

### Linux/macOS

```bash
iverilog -g2012 -o gls.out -f gls.f
vvp gls.out
```

### Windows PowerShell

```powershell
iverilog -g2012 -o gls.out -f gls.f
vvp gls.out
```

## 6. Optional: Direct Command Without Filelist

### Linux/macOS

```bash
iverilog -g2012 -o gls.out tb.v netlist.v libs/sky130hd_sim/sky130_fd_sc_hd__*.v
vvp gls.out
```

### Windows PowerShell

```powershell
$std = Get-ChildItem .\libs\sky130hd_sim\sky130_fd_sc_hd__*.v | ForEach-Object { $_.FullName }
iverilog -g2012 -o gls.out .\tb.v .\netlist.v $std
vvp gls.out
```

## 7. Typical Errors and Fixes

- `Unknown module type: sky130_fd_sc_hd__...`
  - Cause: Missing stdcell model files
  - Fix: Add the required `sky130_fd_sc_hd__*.v` models to compile

- `parameter ... not found in ...dut`
  - Cause: TB uses RTL parameter overrides incompatible with gate netlist
  - Fix: Remove/adjust parameterized instantiation in gate TB copy

- `Unable to bind wire/reg/memory`
  - Cause: Port name/width mismatch between TB and netlist
  - Fix: Update TB to match netlist top interface exactly

## 8. Minimal Sanity Checklist

- Netlist compiles with stdcell models
- Testbench elaborates against netlist top module
- Simulation finishes and prints expected PASS marker
- No unresolved sky130 cell modules

---

If you want, you can extend this into two versions:
- **Functional GLS** (no SDF timing)
- **Timing-annotated GLS** (with SDF back-annotation)
