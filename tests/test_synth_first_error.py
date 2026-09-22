"""A failed ORFS run says what failed, not what went missing afterwards.

Found on a 16-cell counter at the default 40% utilization: the run failed in
floorplan with `[ERROR PDN-0185] Insufficient width ... to add straps on
layer met5`, but the note said "ORFS command failed; 6_finish.rpt not
found", a symptom three stages downstream. The agent had to go read logs.
"""
import src.tools.synthesis_manager as sm


def _run_dir(tmp_path):
    base = tmp_path / "orfs_logs" / "sky130hd" / "counter4" / "base"
    base.mkdir(parents=True)
    (base / "1_2_yosys.log").write_text("Warnings: 0\nEnd of script.\n")
    (base / "2_1_floorplan.log").write_text("[INFO IFP-0001] Added 12 rows\n")
    (base / "2_4_floorplan_pdn.log").write_text(
        "[INFO PDN-0001] Inserting grid: grid\n"
        "[ERROR PDN-0185] Insufficient width (27.20 um) to add straps on layer met5 in grid \"grid\".\n"
        "Error: pdn.tcl, 6 PDN-0185\n")
    (base / "6_report.log").write_text("[ERROR GUI-0001] a later, unrelated error\n")
    reports = tmp_path / "orfs_reports"
    reports.mkdir()
    (reports / "synth_stat.rpt").write_text("cells 16\n")
    return tmp_path


def test_first_error_is_found_in_stage_order(tmp_path):
    first = sm._first_orfs_error(str(_run_dir(tmp_path)))
    assert first == {"log": "2_4_floorplan_pdn.log",
                     "line": "[ERROR PDN-0185] Insufficient width (27.20 um) to add straps on layer met5 in grid \"grid\"."}


def test_failed_run_note_names_the_error(tmp_path):
    out = sm._signoff_guardrail(str(_run_dir(tmp_path)), "counter4", {"success": False})
    assert out["status"] == "fail"
    assert out["note"].startswith("ORFS failed in 2_4_floorplan_pdn.log: [ERROR PDN-0185]")


def test_yosys_errors_count_too(tmp_path):
    base = tmp_path / "orfs_logs" / "x"
    base.mkdir(parents=True)
    (base / "1_2_yosys.log").write_text("ERROR: Module `alu' referenced in module `top' is not part of the design.\n")
    assert sm._first_orfs_error(str(tmp_path))["line"].startswith("ERROR: Module `alu'")


def test_no_error_line_keeps_the_old_note(tmp_path):
    (tmp_path / "orfs_reports").mkdir()
    (tmp_path / "orfs_reports" / "a.rpt").write_text("x\n")
    out = sm._signoff_guardrail(str(tmp_path), "counter4", {"success": False})
    assert out["status"] == "fail" and out["note"].startswith("ORFS command failed; ")
