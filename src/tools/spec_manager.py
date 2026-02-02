"""
Spec Manager - YAML specification handling for RTL designs.

This module provides utilities for creating, reading, validating, and 
managing design specifications in YAML format.
"""

import os
import yaml
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class PortSpec:
    """Specification for a single port."""
    name: str
    direction: str  # 'input' or 'output'
    type: str = "logic"
    width: Optional[Any] = None  # Can be int (e.g., 8) or str (e.g., "WIDTH-1:0") for parameterized
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        d = {"name": self.name, "direction": self.direction, "type": self.type}
        # Handle both integer widths and parameterized string expressions
        if self.width is not None:
            if isinstance(self.width, int):
                if self.width > 1:
                    d["width"] = self.width
            else:
                # String expression like "WIDTH-1:0" - always include
                d["width"] = self.width
        if self.description:
            d["description"] = self.description
        return d


@dataclass 
class DesignSpec:
    """Complete design specification."""
    module_name: str
    description: str
    tech_node: str = "SkyWater 130HD"
    clock_period_ns: float = 10.0
    ports: List[PortSpec] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    module_signature: str = ""
    behavioral_description: str = ""
    sample_io: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_yaml_dict(self) -> Dict[str, Any]:
        """Convert to YAML-compatible dictionary."""
        spec_dict = {
            self.module_name: {
                "description": self.description,
                "tech_node": self.tech_node,
                "clock_period": f"{self.clock_period_ns}ns",
                "ports": [p.to_dict() for p in self.ports],
            }
        }
        
        inner = spec_dict[self.module_name]
        
        if self.parameters:
            inner["parameters"] = self.parameters
            
        if self.module_signature:
            inner["module_signature"] = self.module_signature
            
        if self.behavioral_description:
            inner["behavioral_description"] = self.behavioral_description
            
        if self.sample_io:
            inner["sample_io"] = self.sample_io
            
        inner["created_at"] = self.created_at
        
        return spec_dict
    
    def to_yaml(self) -> str:
        """Convert to YAML string."""
        return yaml.dump(self.to_yaml_dict(), default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    def generate_module_signature(self) -> str:
        """Generate Verilog module signature from ports."""
        if self.module_signature:
            return self.module_signature
            
        # Build parameter list
        param_str = ""
        if self.parameters:
            param_list = [f"parameter {k} = {v}" for k, v in self.parameters.items()]
            param_str = f" #(\n    {',\n    '.join(param_list)}\n)"
        
        # Build port list
        port_lines = []
        for p in self.ports:
            # Handle both integer widths and string expressions
            if p.width is not None:
                if isinstance(p.width, int):
                    width_str = f"[{p.width-1}:0] " if p.width > 1 else ""
                else:
                    # String expression - use as-is (e.g., "WIDTH-1:0" -> "[WIDTH-1:0]")
                    width_str = f"[{p.width}] "
            else:
                width_str = ""
            port_lines.append(f"    {p.direction} {p.type} {width_str}{p.name}")
        
        ports_str = ",\n".join(port_lines)
        
        return f"module {self.module_name}{param_str} (\n{ports_str}\n);"
    
    def generate_sdc(self) -> str:
        """Generate SDC constraints from spec."""
        # Find clock port (usually named 'clk' or 'clock')
        clock_port = "clk"
        for p in self.ports:
            if p.direction == "input" and p.name.lower() in ["clk", "clock", "clk_i"]:
                clock_port = p.name
                break
        
        return f"create_clock -period {self.clock_period_ns} [get_ports {clock_port}]"


def parse_yaml_spec(yaml_content: str) -> DesignSpec:
    """
    Parse YAML content into a DesignSpec object.
    
    Args:
        yaml_content: YAML string content
        
    Returns:
        DesignSpec object
    """
    data = yaml.safe_load(yaml_content)
    
    if not data:
        raise ValueError("Empty YAML content")
    
    # Get the top-level key (module name)
    module_name = list(data.keys())[0]
    spec_data = data[module_name]
    
    # Parse clock period (handle "1.1ns" format)
    clock_str = spec_data.get("clock_period", "10ns")
    clock_period = float(clock_str.replace("ns", "").strip())
    
    # Parse ports
    ports = []
    for port_data in spec_data.get("ports", []):
        port = PortSpec(
            name=port_data.get("name", ""),
            direction=port_data.get("direction", "input"),
            type=port_data.get("type", "logic"),
            width=port_data.get("width"),
            description=port_data.get("description", "")
        )
        ports.append(port)
    
    return DesignSpec(
        module_name=module_name,
        description=spec_data.get("description", ""),
        tech_node=spec_data.get("tech_node", "SkyWater 130HD"),
        clock_period_ns=clock_period,
        ports=ports,
        parameters=spec_data.get("parameters", {}),
        module_signature=spec_data.get("module_signature", ""),
        behavioral_description=spec_data.get("behavioral_description", ""),
        sample_io=spec_data.get("sample_io", spec_data.get("sample_usage", {})),
        created_at=spec_data.get("created_at", datetime.now().isoformat())
    )


def load_yaml_file(filepath: str) -> DesignSpec:
    """Load a YAML spec from file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return parse_yaml_spec(f.read())


def save_yaml_file(spec: DesignSpec, filepath: str) -> str:
    """Save a DesignSpec to a YAML file."""
    yaml_content = spec.to_yaml()
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    return filepath


def validate_spec(spec: DesignSpec) -> Dict[str, Any]:
    """
    Validate a design specification.
    
    Returns:
        Dict with 'valid' bool and 'errors' list
    """
    errors = []
    warnings = []
    
    # Required fields
    if not spec.module_name:
        errors.append("Module name is required")
    elif not spec.module_name[0].isalpha():
        errors.append("Module name must start with a letter")
        
    if not spec.description:
        warnings.append("Description is empty")
    
    # Port validation
    if not spec.ports:
        errors.append("At least one port is required")
    else:
        port_names = set()
        has_clock = False
        
        for port in spec.ports:
            if not port.name:
                errors.append("Port name cannot be empty")
            elif port.name in port_names:
                errors.append(f"Duplicate port name: {port.name}")
            else:
                port_names.add(port.name)
                
            if port.direction not in ["input", "output", "inout"]:
                errors.append(f"Invalid port direction for {port.name}: {port.direction}")
                
            if port.name.lower() in ["clk", "clock"]:
                has_clock = True
        
        if not has_clock:
            warnings.append("No clock port detected (expected 'clk' or 'clock')")
    
    # Clock period validation
    if spec.clock_period_ns <= 0:
        errors.append("Clock period must be positive")
    elif spec.clock_period_ns < 1:
        warnings.append(f"Very aggressive clock period: {spec.clock_period_ns}ns")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }


def spec_to_prompt(spec: DesignSpec) -> str:
    """
    Convert a DesignSpec to a natural language prompt for the RTL coder.
    
    This is used internally when the agent needs to generate RTL from a spec.
    """
    prompt_parts = [
        f"Design a Verilog module named `{spec.module_name}`.",
        f"\n**Description**: {spec.description}",
        f"\n**Target Technology**: {spec.tech_node}",
        f"\n**Clock Period**: {spec.clock_period_ns}ns",
    ]
    
    # Parameters
    if spec.parameters:
        param_str = ", ".join([f"{k}={v}" for k, v in spec.parameters.items()])
        prompt_parts.append(f"\n**Parameters**: {param_str}")
    
    # Ports
    prompt_parts.append("\n**Ports**:")
    for port in spec.ports:
        # Handle both integer widths and string expressions
        if port.width is not None:
            if isinstance(port.width, int):
                width_str = f"[{port.width-1}:0]" if port.width > 1 else ""
            else:
                width_str = f"[{port.width}]"
        else:
            width_str = ""
        desc_str = f" - {port.description}" if port.description else ""
        prompt_parts.append(f"  - `{port.direction} {port.type} {width_str} {port.name}`{desc_str}")
    
    # Module signature (if provided)
    if spec.module_signature:
        prompt_parts.append(f"\n**Required Module Signature** (MUST match exactly):\n```verilog\n{spec.module_signature}\n```")
    
    # Behavioral description
    if spec.behavioral_description:
        prompt_parts.append(f"\n**Behavioral Requirements**:\n{spec.behavioral_description}")
    
    # Sample I/O
    if spec.sample_io:
        prompt_parts.append(f"\n**Sample I/O for verification**: {spec.sample_io}")
    
    return "\n".join(prompt_parts)


def create_spec_from_dict(data: Dict[str, Any]) -> DesignSpec:
    """
    Create a DesignSpec from a dictionary (useful for tool calls).
    
    Expected format:
    {
        "module_name": "counter",
        "description": "8-bit counter",
        "clock_period_ns": 10.0,
        "ports": [
            {"name": "clk", "direction": "input"},
            {"name": "count", "direction": "output", "width": 8}
        ]
    }
    """
    ports = [
        PortSpec(
            name=p.get("name", ""),
            direction=p.get("direction", "input"),
            type=p.get("type", "logic"),
            width=p.get("width"),
            description=p.get("description", "")
        )
        for p in data.get("ports", [])
    ]
    
    return DesignSpec(
        module_name=data.get("module_name", "design"),
        description=data.get("description", ""),
        tech_node=data.get("tech_node", "SkyWater 130HD"),
        clock_period_ns=data.get("clock_period_ns", 10.0),
        ports=ports,
        parameters=data.get("parameters", {}),
        module_signature=data.get("module_signature", ""),
        behavioral_description=data.get("behavioral_description", ""),
        sample_io=data.get("sample_io", {})
    )
