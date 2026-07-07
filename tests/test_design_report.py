"""
Tests for the design_report module.
"""

import os
import unittest
import tempfile
import shutil
import json
from src.tools.design_report import (
    save_metrics,
    load_metrics,
    generate_design_report,
    save_design_report,
    METRICS_FILENAME
)
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file, load_yaml_file


class TestSaveMetrics(unittest.TestCase):
    """Tests for metrics persistence."""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_save_metrics_creates_file(self):
        metrics = {
            "area_um2": 123.45,
            "cell_count": 50,
            "wns_ns": 0.5
        }
        path = save_metrics(self.test_dir, metrics)
        
        self.assertTrue(os.path.exists(path))
        
        with open(path, 'r') as f:
            saved = json.load(f)
        
        self.assertEqual(saved["area_um2"], 123.45)
        self.assertEqual(saved["cell_count"], 50)
        self.assertIn("updated_at", saved)
    
    def test_save_metrics_merges_existing(self):
        # Save initial metrics
        save_metrics(self.test_dir, {"area_um2": 100.0})
        
        # Save more metrics
        save_metrics(self.test_dir, {"cell_count": 25})
        
        # Check merged
        metrics_path = os.path.join(self.test_dir, METRICS_FILENAME)
        with open(metrics_path, 'r') as f:
            saved = json.load(f)
        
        self.assertEqual(saved["area_um2"], 100.0)
        self.assertEqual(saved["cell_count"], 25)
    
    def test_save_metrics_skips_none(self):
        save_metrics(self.test_dir, {"area_um2": 100.0, "cell_count": None})
        
        metrics_path = os.path.join(self.test_dir, METRICS_FILENAME)
        with open(metrics_path, 'r') as f:
            saved = json.load(f)
        
        self.assertEqual(saved["area_um2"], 100.0)
        self.assertNotIn("cell_count", saved)  # None values not saved


class TestLoadMetrics(unittest.TestCase):
    """Tests for loading metrics."""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_load_metrics_from_file(self):
        # Create metrics file
        metrics_path = os.path.join(self.test_dir, METRICS_FILENAME)
        with open(metrics_path, 'w') as f:
            json.dump({"area_um2": 200.0, "wns_ns": -0.1}, f)
        
        loaded = load_metrics(self.test_dir)
        
        self.assertEqual(loaded["area_um2"], 200.0)
        self.assertEqual(loaded["wns_ns"], -0.1)
    
    def test_load_metrics_empty_dir(self):
        loaded = load_metrics(self.test_dir)
        self.assertEqual(loaded, {})
    
    def test_load_metrics_handles_corrupt_json(self):
        # Create corrupt file
        metrics_path = os.path.join(self.test_dir, METRICS_FILENAME)
        with open(metrics_path, 'w') as f:
            f.write("not valid json {{{")
        
        # Should not raise, just return empty
        loaded = load_metrics(self.test_dir)
        self.assertEqual(loaded, {})


class TestGenerateDesignReport(unittest.TestCase):
    """Tests for report generation."""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
        # Create a sample spec file
        self.spec = DesignSpec(
            module_name="test_counter",
            description="A test counter for unit testing",
            tech_node="SkyWater 130HD",
            clock_period_ns=10.0,
            ports=[
                PortSpec(name="clk", direction="input", description="Clock"),
                PortSpec(name="rst", direction="input", description="Reset"),
                PortSpec(name="count", direction="output", width=8, description="Count output")
            ]
        )
        spec_path = os.path.join(self.test_dir, "test_counter_spec.yaml")
        save_yaml_file(self.spec, spec_path)
        
        # Create a dummy RTL file
        rtl_path = os.path.join(self.test_dir, "test_counter.v")
        with open(rtl_path, 'w') as f:
            f.write("module test_counter(); endmodule")
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_report_includes_header(self):
        report = generate_design_report(self.test_dir)
        self.assertIn("# Design Report", report)
        self.assertIn("Generated:", report)
    
    def test_report_includes_spec_summary(self):
        report = generate_design_report(self.test_dir)
        self.assertIn("Specification Summary", report)
        self.assertIn("test_counter", report)
        self.assertIn("10.0 ns", report)
    
    def test_report_includes_ports(self):
        report = generate_design_report(self.test_dir)
        self.assertIn("Port List", report)
        self.assertIn("clk", report)
        self.assertIn("count", report)
    
    def test_report_includes_files(self):
        report = generate_design_report(self.test_dir)
        self.assertIn("Generated Files", report)
        self.assertIn("test_counter.v", report)
    
    def test_report_includes_verification(self):
        report = generate_design_report(self.test_dir)
        self.assertIn("Verification Results", report)
    
    def test_report_with_metrics(self):
        # Add metrics
        save_metrics(self.test_dir, {
            "area_um2": 150.25,
            "cell_count": 42,
            "wns_ns": 1.5,
            "power_uw": 0.05
        })
        
        report = generate_design_report(self.test_dir)
        
        self.assertIn("150.25", report)  # Area
        self.assertIn("42", report)      # Cell count
        self.assertIn("1.5", report)     # WNS
        self.assertIn("Met", report)     # Timing met
    
    def test_report_with_timing_violation(self):
        save_metrics(self.test_dir, {"wns_ns": -0.5})
        
        report = generate_design_report(self.test_dir)
        
        self.assertIn("Violated", report)
    
    def test_report_no_spec(self):
        # Create empty directory
        empty_dir = tempfile.mkdtemp()
        try:
            report = generate_design_report(empty_dir)
            self.assertIn("No specification file found", report)
        finally:
            shutil.rmtree(empty_dir)


class TestSaveDesignReport(unittest.TestCase):
    """Tests for saving report to file."""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
        # Create a sample spec
        spec = DesignSpec(
            module_name="my_design",
            description="Test design",
            ports=[PortSpec(name="clk", direction="input")]
        )
        save_yaml_file(spec, os.path.join(self.test_dir, "my_design_spec.yaml"))
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_save_creates_report_file(self):
        path = save_design_report(self.test_dir)
        
        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith("_report.md"))
    
    def test_save_report_uses_module_name(self):
        path = save_design_report(self.test_dir)
        
        self.assertIn("my_design", path)
    
    def test_saved_report_is_markdown(self):
        path = save_design_report(self.test_dir)
        
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn("# Design Report", content)
        self.assertIn("---", content)  # Markdown separator

    def test_save_report_to_synthesis_run(self):
        run_dir = os.path.join(self.test_dir, "synth_runs", "synth_0001")
        os.makedirs(run_dir, exist_ok=True)
        with open(os.path.join(self.test_dir, "synth_runs", "LATEST"), "w", encoding="utf-8") as f:
            f.write("synth_0001")
        with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": "synth_0001", "top_module": "my_design", "platform": "sky130hd"}, f)

        path = save_design_report(self.test_dir, run_id="synth_0001")

        self.assertTrue(os.path.exists(path))
        self.assertTrue(path.endswith(os.path.join("synth_0001", "design_report.md")))


class TestReportWithSimulationResults(unittest.TestCase):
    """Tests for report with simulation log parsing."""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
        spec = DesignSpec(
            module_name="sim_test",
            description="Simulation test",
            ports=[PortSpec(name="clk", direction="input")]
        )
        save_yaml_file(spec, os.path.join(self.test_dir, "sim_test_spec.yaml"))
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_report_detects_pass(self):
        # Create simulation log with PASS
        with open(os.path.join(self.test_dir, "simulation.log"), 'w') as f:
            f.write("Running test...\nAll tests PASS\n")
        
        report = generate_design_report(self.test_dir)
        
        self.assertIn("✅ Pass", report)
    
    def test_report_detects_fail(self):
        # Create simulation log with FAIL
        with open(os.path.join(self.test_dir, "sim.out"), 'w') as f:
            f.write("Test 1: FAIL\n")
        
        report = generate_design_report(self.test_dir)
        
        self.assertIn("❌ Fail", report)

class TestRunScopedMetrics(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        spec = DesignSpec(
            module_name="run_demo",
            description="Run scoped report",
            ports=[PortSpec(name="clk", direction="input")]
        )
        save_yaml_file(spec, os.path.join(self.test_dir, "run_demo_spec.yaml"))

        self.run_dir = os.path.join(self.test_dir, "synth_runs", "synth_0002")
        os.makedirs(self.run_dir, exist_ok=True)
        save_yaml_file(spec, os.path.join(self.run_dir, "run_demo_spec.yaml"))
        report_dir = os.path.join(self.run_dir, "orfs_reports", "sky130hd", "run_demo", "base")
        os.makedirs(report_dir, exist_ok=True)

        with open(os.path.join(self.test_dir, "synth_runs", "LATEST"), "w", encoding="utf-8") as f:
            f.write("synth_0002")
        with open(os.path.join(self.run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
            json.dump({"run_id": "synth_0002", "top_module": "run_demo", "platform": "sky130hd"}, f)

        with open(os.path.join(report_dir, "6_finish.rpt"), "w", encoding="utf-8") as f:
            f.write(
                "tns max 0.00\n"
                "wns max 0.25\n"
                "setup violation count 0\n"
                "hold violation count 0\n"
                "Total                  1.00e-03   1.00e-03   1.00e-09   2.00e-03 100.0%\n"
            )
        with open(os.path.join(report_dir, "synth_stat.txt"), "w", encoding="utf-8") as f:
            f.write(
                "      100 1.23E+03 cells\n"
                "Chip area for module '\\run_demo': 1234.000000\n"
            )

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_load_metrics_for_run(self):
        metrics = load_metrics(self.test_dir, run_id="synth_0002")
        self.assertEqual(metrics["area_um2"], 1234.0)
        self.assertEqual(metrics["cell_count"], 100)
        self.assertEqual(metrics["wns_ns"], 0.25)

    def test_generate_report_for_run(self):
        report = generate_design_report(self.test_dir, run_id="synth_0002")
        self.assertIn("synth_0002", report)
        self.assertIn("1234.00", report)
        self.assertIn("Run Spec Snapshot", report)

    def test_run_local_spec_is_preferred(self):
        root_spec = os.path.join(self.test_dir, "run_demo_spec.yaml")
        run_spec = os.path.join(self.run_dir, "run_demo_spec.yaml")

        root = load_yaml_file(root_spec)
        root.description = "workspace root spec"
        save_yaml_file(root, root_spec)

        scoped = load_yaml_file(run_spec)
        scoped.description = "run-local spec"
        save_yaml_file(scoped, run_spec)

        report = generate_design_report(self.test_dir, run_id="synth_0002")
        self.assertIn("run-local spec", report)

    def test_run_clock_is_preferred_over_spec_clock(self):
        meta_path = os.path.join(self.run_dir, "run_meta.json")
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        meta["requested_clock_period_ns"] = 6.0
        meta["effective_clock_period_ns"] = 7.5
        meta["clock_period_ns"] = 7.5
        meta["clock_source"] = "requested"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f)

        root_spec = os.path.join(self.test_dir, "run_demo_spec.yaml")
        run_spec = os.path.join(self.run_dir, "run_demo_spec.yaml")

        root = load_yaml_file(root_spec)
        root.clock_period_ns = 20.0
        save_yaml_file(root, root_spec)

        scoped = load_yaml_file(run_spec)
        scoped.clock_period_ns = 15.0
        save_yaml_file(scoped, run_spec)

        report = generate_design_report(self.test_dir, run_id="synth_0002")
        self.assertIn("| Requested Clock | 6.0 ns |", report)
        self.assertIn("| Target Clock | 7.5 ns |", report)
        self.assertIn("| Timing Target Source | requested |", report)


class TestReportHonestyX2U2(unittest.TestCase):
    """X2U-2: the report must reflect the truth the session already holds —
    sim status from the isolated sim_runs, and a present markdown spec — instead
    of "Not Run" / "No specification file found"."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        rtl = os.path.join(self.test_dir, "widget.v")
        with open(rtl, "w", encoding="utf-8") as f:
            f.write("module widget(); endmodule")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def _seed_sim_run(self, run_id, status, created_at):
        run_dir = os.path.join(self.test_dir, "sim_runs", run_id)
        os.makedirs(run_dir, exist_ok=True)
        meta = {
            "id": run_id, "kind": "sim", "status": status,
            "createdAt": created_at, "top": "widget_tb",
            "passMarkerFound": status == "passed", "pinned": False,
        }
        with open(os.path.join(run_dir, "run_meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f)
        idx_path = os.path.join(self.test_dir, "sim_runs", "index.json")
        idx = {"runs": []}
        if os.path.exists(idx_path):
            with open(idx_path, "r", encoding="utf-8") as f:
                idx = json.load(f)
        idx["runs"] = [r for r in idx["runs"] if r.get("run_id") != run_id]
        idx["runs"].append({"run_id": run_id, "status": status,
                            "created_at": created_at, "pinned": False})
        with open(idx_path, "w", encoding="utf-8") as f:
            json.dump(idx, f)

    def test_sim_status_reads_passing_isolated_run(self):
        self._seed_sim_run("sim_0001", "passed", "2026-07-06T10:00:00+00:00")
        report = generate_design_report(self.test_dir)
        self.assertIn("| Simulation | ✅ Pass", report)
        self.assertNotIn("Not Run", report)
        self.assertIn("sim_0001", report)

    def test_sim_status_reads_failing_isolated_run(self):
        self._seed_sim_run("sim_0001", "failed", "2026-07-06T10:00:00+00:00")
        report = generate_design_report(self.test_dir)
        self.assertIn("| Simulation | ❌ Fail", report)
        self.assertNotIn("Not Run", report)

    def test_sim_status_reports_latest_of_several_runs(self):
        self._seed_sim_run("sim_0001", "failed", "2026-07-06T10:00:00+00:00")
        self._seed_sim_run("sim_0003", "passed", "2026-07-06T11:00:00+00:00")
        report = generate_design_report(self.test_dir)
        # Latest (sim_0003, passed) wins, and the count is disclosed.
        self.assertIn("| Simulation | ✅ Pass", report)
        self.assertIn("sim_0003", report)
        self.assertIn("latest of 2 runs", report)

    def test_sim_status_not_run_only_when_truly_absent(self):
        report = generate_design_report(self.test_dir)
        self.assertIn("| Simulation | ⏳ Not Run |", report)

    def test_markdown_spec_is_recognized(self):
        with open(os.path.join(self.test_dir, "spec.md"), "w", encoding="utf-8") as f:
            f.write("# Widget spec\n\nAn 8-bit widget.\n")
        report = generate_design_report(self.test_dir)
        self.assertNotIn("No specification file found", report)
        self.assertIn("spec.md", report)

    def test_no_spec_message_when_nothing_present(self):
        report = generate_design_report(self.test_dir)
        self.assertIn("No specification file found", report)


if __name__ == "__main__":
    unittest.main()
