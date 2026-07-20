"""The post-synth *sim contract*: synthesis records it, simulation resolves it.

These lock in issue #52's core requirement — the simulation tool resolves from
the authoritative run record, not by re-discovering state — at the module seam
(``src/tools/sim_contract.py``), independent of the EDA toolchain.
"""
import json
import os

from src.tools import sim_contract as sc


def _write_synth_run(ws, run_id="synth_0001", *, contract=None, netlist_path=None,
                     platform="sky130hd", make_netlist=True):
    """Create ``<ws>/synth_runs/<run_id>/`` with a gate netlist + run_meta.json."""
    run_dir = os.path.join(ws, "synth_runs", run_id)
    results = os.path.join(run_dir, "orfs_results", platform, "top", "base")
    os.makedirs(results, exist_ok=True)
    gate_abs = os.path.join(results, "6_final.v")
    if make_netlist:
        with open(gate_abs, "w", encoding="utf-8") as f:
            f.write("module top(); endmodule\n")
    meta = {"run_id": run_id, "platform": platform, "top_module": "top"}
    if contract is not None:
        meta["sim_contract"] = contract
    if netlist_path is not None:
        meta["netlist_path"] = netlist_path
    with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    # LATEST pointer so run_id-less resolution works.
    with open(os.path.join(ws, "synth_runs", "LATEST"), "w", encoding="utf-8") as f:
        f.write(run_id)
    return run_dir, gate_abs


def test_build_sim_contract_stores_workspace_relative_netlist(tmp_path):
    ws = str(tmp_path)
    gate_abs = os.path.join(ws, "synth_runs", "synth_0001", "orfs_results", "x", "6_final.v")
    contract = sc.build_sim_contract(
        ws, netlist_abs=gate_abs, platform="sky130hd", top="top",
        stdcell_manifest_version="v1",
    )
    assert contract["schema_version"] == sc.SIM_CONTRACT_VERSION
    assert contract["mode"] == "post_synth"
    assert contract["platform"] == "sky130hd"
    assert contract["top"] == "top"
    # Portable: workspace-relative POSIX, never an absolute host path leak.
    assert contract["netlist"] == "synth_runs/synth_0001/orfs_results/x/6_final.v"
    assert not os.path.isabs(contract["netlist"])
    assert contract["stdcell_manifest_version"] == "v1"


def test_resolve_reads_gate_netlist_from_contract_not_rtl(tmp_path):
    ws = str(tmp_path)
    # An RTL source with the same top exists at the workspace root — the classic
    # netlist-vs-RTL trap. Resolution must pick the GATE netlist from the record.
    with open(os.path.join(ws, "top.v"), "w", encoding="utf-8") as f:
        f.write("module top(input a, output b); assign b = a; endmodule\n")
    run_dir, gate_abs = _write_synth_run(ws)
    contract = sc.build_sim_contract(
        ws, netlist_abs=gate_abs, platform="sky130hd", top="top",
    )
    # Re-persist meta with the built contract.
    meta_path = os.path.join(run_dir, "run_meta.json")
    meta = json.load(open(meta_path))
    meta["sim_contract"] = contract
    json.dump(meta, open(meta_path, "w"))

    resolution, err = sc.resolve_post_synth(ws, run_id="synth_0001")
    assert err is None
    # normpath both sides: contract paths are workspace-relative POSIX, so on
    # Windows the resolved absolute is mixed-separator vs a native gate_abs.
    assert os.path.normpath(resolution.netlist_abs) == os.path.normpath(gate_abs)
    assert resolution.resolved_netlist == "synth_runs/synth_0001/orfs_results/sky130hd/top/base/6_final.v"
    assert "top.v" not in resolution.resolved_netlist  # not the RTL
    assert resolution.resolved_run_id == "synth_0001"
    assert resolution.platform == "sky130hd"
    assert resolution.stdcell_source == "sky130hd"
    assert resolution.source == "contract"


def test_resolve_latest_when_run_id_omitted(tmp_path):
    ws = str(tmp_path)
    _, gate_abs = _write_synth_run(ws, run_id="synth_0002",
                                   contract={"schema_version": 1, "netlist":
                                             "synth_runs/synth_0002/orfs_results/sky130hd/top/base/6_final.v",
                                             "platform": "sky130hd", "top": "top"})
    resolution, err = sc.resolve_post_synth(ws)  # no run_id -> LATEST
    assert err is None
    assert resolution.resolved_run_id == "synth_0002"
    assert os.path.normpath(resolution.netlist_abs) == os.path.normpath(gate_abs)


def test_resolve_legacy_run_prefers_gate_netlist_over_recorded_path(tmp_path):
    """A run predating the contract resolves the gate netlist from orfs_results
    via _find_netlist — the authoritative source — even when netlist_path is set
    (older synth sometimes recorded the RTL there). source == legacy_find_netlist."""
    ws = str(tmp_path)
    run_dir, gate_abs = _write_synth_run(ws, contract=None, netlist_path=None)
    meta_path = os.path.join(run_dir, "run_meta.json")
    json.dump({"platform": "sky130hd", "top_module": "top", "netlist_path": gate_abs},
              open(meta_path, "w"))

    resolution, err = sc.resolve_post_synth(ws, run_id="synth_0001")
    assert err is None
    assert os.path.normpath(resolution.netlist_abs) == os.path.normpath(gate_abs)
    assert resolution.source == "legacy_find_netlist"


def test_resolve_unknown_run_is_typed_error(tmp_path):
    ws = str(tmp_path)
    resolution, err = sc.resolve_post_synth(ws, run_id="synth_9999")
    assert resolution is None
    assert err.code == "run_not_found"
    assert "synth_9999" in err.message


def test_resolve_missing_netlist_is_typed_error(tmp_path):
    ws = str(tmp_path)
    run_dir, gate_abs = _write_synth_run(ws, make_netlist=False,
                                         contract={"schema_version": 1,
                                                   "netlist": "synth_runs/synth_0001/orfs_results/sky130hd/top/base/6_final.v",
                                                   "platform": "sky130hd", "top": "top"})
    resolution, err = sc.resolve_post_synth(ws, run_id="synth_0001")
    assert resolution is None
    assert err.code == "netlist_not_found"


def test_stdcell_recovery_action_is_honest_infra_message_not_a_tool():
    # The cache is infra (baked on hosted, boot-bootstrapped on self-host), so
    # recovery is honest guidance — NOT a first-class registry tool.
    rec = sc.stdcell_recovery_action("asap7")
    assert rec["kind"] == "infra"
    assert "action" not in rec  # no registered-tool dispatch
    assert "asap7" in rec["label"]
    assert rec["detail"]


def test_legacy_fallback_resolves_gate_netlist_not_recorded_rtl_path(tmp_path):
    # Pre-contract run: run_meta has NO sim_contract and a WRONG netlist_path
    # (older synth code sometimes recorded the RTL input there). The resolver
    # must still find the real gate netlist from orfs_results via _find_netlist,
    # never the RTL. This is the fix that unblocks old sessions.
    ws = str(tmp_path)
    run_dir = os.path.join(ws, "synth_runs", "synth_0001")
    inputs = os.path.join(run_dir, "inputs")
    os.makedirs(inputs)
    rtl = os.path.join(inputs, "top.v")
    open(rtl, "w").write("module top; endmodule\n")
    gate_dir = os.path.join(run_dir, "orfs_results", "sky130hd", "top", "base")
    os.makedirs(gate_dir)
    gate = os.path.join(gate_dir, "6_final.v")
    open(gate, "w").write("module top; endmodule\n")
    meta = {"platform": "sky130hd", "top_module": "top", "netlist_path": rtl}
    open(os.path.join(run_dir, "run_meta.json"), "w").write(json.dumps(meta))

    res, err = sc.resolve_post_synth(ws, run_id="synth_0001")
    assert err is None
    assert res.source == "legacy_find_netlist"
    assert os.path.basename(res.netlist_abs) == "6_final.v"
    assert os.path.normpath(res.netlist_abs) != os.path.normpath(rtl)
