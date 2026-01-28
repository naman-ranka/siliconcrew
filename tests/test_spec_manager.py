"""
Tests for the spec_manager module.
"""

import os
import unittest
import tempfile
import shutil
from src.tools.spec_manager import (
    PortSpec,
    DesignSpec,
    parse_yaml_spec,
    load_yaml_file,
    save_yaml_file,
    validate_spec,
    create_spec_from_dict,
    spec_to_prompt
)


class TestPortSpec(unittest.TestCase):
    """Tests for PortSpec dataclass."""
    
    def test_basic_port(self):
        port = PortSpec(name="clk", direction="input")
        self.assertEqual(port.name, "clk")
        self.assertEqual(port.direction, "input")
        self.assertEqual(port.type, "logic")
        self.assertIsNone(port.width)
    
    def test_port_with_width(self):
        port = PortSpec(name="data", direction="output", width=8)
        d = port.to_dict()
        self.assertEqual(d["name"], "data")
        self.assertEqual(d["width"], 8)
    
    def test_port_to_dict_excludes_width_1(self):
        port = PortSpec(name="clk", direction="input", width=1)
        d = port.to_dict()
        self.assertNotIn("width", d)  # Width 1 is default, shouldn't be included


class TestDesignSpec(unittest.TestCase):
    """Tests for DesignSpec dataclass."""
    
    def setUp(self):
        self.ports = [
            PortSpec(name="clk", direction="input", description="Clock"),
            PortSpec(name="rst", direction="input", description="Reset"),
            PortSpec(name="count", direction="output", width=8, description="Counter output")
        ]
        self.spec = DesignSpec(
            module_name="counter",
            description="8-bit counter",
            tech_node="SkyWater 130HD",
            clock_period_ns=10.0,
            ports=self.ports
        )
    
    def test_to_yaml_dict(self):
        d = self.spec.to_yaml_dict()
        self.assertIn("counter", d)
        self.assertEqual(d["counter"]["description"], "8-bit counter")
        self.assertEqual(d["counter"]["clock_period"], "10.0ns")
        self.assertEqual(len(d["counter"]["ports"]), 3)
    
    def test_to_yaml(self):
        yaml_str = self.spec.to_yaml()
        self.assertIn("counter:", yaml_str)
        self.assertIn("description:", yaml_str)
        self.assertIn("clock_period:", yaml_str)
    
    def test_generate_module_signature(self):
        sig = self.spec.generate_module_signature()
        self.assertIn("module counter", sig)
        self.assertIn("input logic clk", sig)
        self.assertIn("output logic [7:0] count", sig)
    
    def test_generate_sdc(self):
        sdc = self.spec.generate_sdc()
        self.assertIn("create_clock", sdc)
        self.assertIn("-period 10.0", sdc)
        self.assertIn("clk", sdc)


class TestParseYamlSpec(unittest.TestCase):
    """Tests for YAML parsing."""
    
    def test_parse_basic_yaml(self):
        yaml_content = """
counter:
  description: Simple 8-bit counter
  tech_node: SkyWater 130HD
  clock_period: 10ns
  ports:
    - name: clk
      direction: input
    - name: count
      direction: output
      width: 8
"""
        spec = parse_yaml_spec(yaml_content)
        self.assertEqual(spec.module_name, "counter")
        self.assertEqual(spec.clock_period_ns, 10.0)
        self.assertEqual(len(spec.ports), 2)
    
    def test_parse_with_parameters(self):
        yaml_content = """
parameterized_counter:
  description: Parameterized counter
  clock_period: 5ns
  parameters:
    WIDTH: 8
    MAX_COUNT: 255
  ports:
    - name: clk
      direction: input
"""
        spec = parse_yaml_spec(yaml_content)
        self.assertEqual(spec.parameters["WIDTH"], 8)
        self.assertEqual(spec.parameters["MAX_COUNT"], 255)
    
    def test_parse_empty_yaml_raises(self):
        with self.assertRaises(ValueError):
            parse_yaml_spec("")
    
    def test_parse_with_module_signature(self):
        yaml_content = """
adder:
  description: Simple adder
  clock_period: 10ns
  module_signature: |
    module adder(
        input [7:0] a,
        input [7:0] b,
        output [8:0] sum
    );
  ports:
    - name: a
      direction: input
      width: 8
"""
        spec = parse_yaml_spec(yaml_content)
        self.assertIn("module adder", spec.module_signature)


class TestFileOperations(unittest.TestCase):
    """Tests for file save/load operations."""
    
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, "test_spec.yaml")
        
        self.spec = DesignSpec(
            module_name="test_module",
            description="Test module for unit tests",
            clock_period_ns=5.0,
            ports=[
                PortSpec(name="clk", direction="input"),
                PortSpec(name="data", direction="output", width=16)
            ]
        )
    
    def tearDown(self):
        shutil.rmtree(self.test_dir)
    
    def test_save_and_load_yaml(self):
        # Save
        save_yaml_file(self.spec, self.test_file)
        self.assertTrue(os.path.exists(self.test_file))
        
        # Load
        loaded = load_yaml_file(self.test_file)
        self.assertEqual(loaded.module_name, "test_module")
        self.assertEqual(loaded.clock_period_ns, 5.0)
        self.assertEqual(len(loaded.ports), 2)
    
    def test_save_creates_valid_yaml(self):
        save_yaml_file(self.spec, self.test_file)
        
        with open(self.test_file, 'r') as f:
            content = f.read()
        
        self.assertIn("test_module:", content)
        self.assertIn("description:", content)


class TestValidateSpec(unittest.TestCase):
    """Tests for spec validation."""
    
    def test_valid_spec(self):
        spec = DesignSpec(
            module_name="counter",
            description="A counter",
            ports=[
                PortSpec(name="clk", direction="input"),
                PortSpec(name="out", direction="output")
            ]
        )
        result = validate_spec(spec)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["errors"]), 0)
    
    def test_missing_module_name(self):
        spec = DesignSpec(
            module_name="",
            description="Missing name",
            ports=[PortSpec(name="clk", direction="input")]
        )
        result = validate_spec(spec)
        self.assertFalse(result["valid"])
        self.assertIn("Module name is required", result["errors"])
    
    def test_invalid_module_name_start(self):
        spec = DesignSpec(
            module_name="1counter",  # Starts with number
            description="Bad name",
            ports=[PortSpec(name="clk", direction="input")]
        )
        result = validate_spec(spec)
        self.assertFalse(result["valid"])
        self.assertIn("Module name must start with a letter", result["errors"])
    
    def test_no_ports(self):
        spec = DesignSpec(
            module_name="empty",
            description="No ports",
            ports=[]
        )
        result = validate_spec(spec)
        self.assertFalse(result["valid"])
        self.assertIn("At least one port is required", result["errors"])
    
    def test_duplicate_port_names(self):
        spec = DesignSpec(
            module_name="dup",
            description="Duplicate ports",
            ports=[
                PortSpec(name="clk", direction="input"),
                PortSpec(name="clk", direction="input")  # Duplicate
            ]
        )
        result = validate_spec(spec)
        self.assertFalse(result["valid"])
        self.assertIn("Duplicate port name: clk", result["errors"])
    
    def test_invalid_port_direction(self):
        spec = DesignSpec(
            module_name="bad_dir",
            description="Bad direction",
            ports=[PortSpec(name="x", direction="sideways")]  # Invalid
        )
        result = validate_spec(spec)
        self.assertFalse(result["valid"])
    
    def test_negative_clock_period(self):
        spec = DesignSpec(
            module_name="neg_clk",
            description="Negative clock",
            clock_period_ns=-5.0,
            ports=[PortSpec(name="clk", direction="input")]
        )
        result = validate_spec(spec)
        self.assertFalse(result["valid"])
        self.assertIn("Clock period must be positive", result["errors"])
    
    def test_warning_no_clock_port(self):
        spec = DesignSpec(
            module_name="no_clk",
            description="No clock detected",
            ports=[PortSpec(name="data", direction="input")]
        )
        result = validate_spec(spec)
        self.assertTrue(result["valid"])  # Still valid, just warning
        self.assertTrue(any("clock" in w.lower() for w in result["warnings"]))


class TestCreateSpecFromDict(unittest.TestCase):
    """Tests for creating spec from dictionary."""
    
    def test_basic_dict(self):
        data = {
            "module_name": "adder",
            "description": "Simple adder",
            "clock_period_ns": 8.0,
            "ports": [
                {"name": "a", "direction": "input", "width": 8},
                {"name": "b", "direction": "input", "width": 8},
                {"name": "sum", "direction": "output", "width": 9}
            ]
        }
        spec = create_spec_from_dict(data)
        self.assertEqual(spec.module_name, "adder")
        self.assertEqual(spec.clock_period_ns, 8.0)
        self.assertEqual(len(spec.ports), 3)
        self.assertEqual(spec.ports[2].width, 9)
    
    def test_dict_with_defaults(self):
        data = {
            "module_name": "minimal",
            "description": "Minimal spec",
            "ports": [{"name": "clk", "direction": "input"}]
        }
        spec = create_spec_from_dict(data)
        self.assertEqual(spec.tech_node, "SkyWater 130HD")  # Default
        self.assertEqual(spec.clock_period_ns, 10.0)  # Default


class TestSpecToPrompt(unittest.TestCase):
    """Tests for converting spec to natural language prompt."""
    
    def test_basic_prompt(self):
        spec = DesignSpec(
            module_name="counter",
            description="8-bit up counter",
            clock_period_ns=10.0,
            ports=[
                PortSpec(name="clk", direction="input", description="Clock"),
                PortSpec(name="count", direction="output", width=8)
            ]
        )
        prompt = spec_to_prompt(spec)
        self.assertIn("counter", prompt)
        self.assertIn("8-bit up counter", prompt)
        self.assertIn("10.0ns", prompt)
        self.assertIn("clk", prompt)
    
    def test_prompt_with_parameters(self):
        spec = DesignSpec(
            module_name="param_mod",
            description="Parameterized module",
            parameters={"WIDTH": 16, "DEPTH": 32},
            ports=[PortSpec(name="clk", direction="input")]
        )
        prompt = spec_to_prompt(spec)
        self.assertIn("WIDTH=16", prompt)
        self.assertIn("DEPTH=32", prompt)


if __name__ == "__main__":
    unittest.main()
