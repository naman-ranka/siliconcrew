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
from src.tools.spec_manager import DesignSpec, PortSpec, save_yaml_file


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


if __name__ == "__main__":
    unittest.main()
