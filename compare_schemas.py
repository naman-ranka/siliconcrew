"""
Compare manual vs auto-discovered MCP schemas
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from mcp_server import RTLDesignMCPServer, langchain_to_mcp_schema
from src.tools.wrappers import write_spec


async def compare_schemas():
    """Compare manual vs auto-discovered schema for write_spec."""
    
    print("="*70)
    print("SCHEMA COMPARISON: write_spec tool")
    print("="*70)
    
    # Auto-discovered schema
    auto_tool = langchain_to_mcp_schema(write_spec)
    
    print("\n1. AUTO-DISCOVERED SCHEMA")
    print("-" * 70)
    print(f"Name: {auto_tool.name}")
    print(f"Description: {auto_tool.description[:200]}...")
    print(f"\nInput Schema Keys: {list(auto_tool.inputSchema.keys())}")
    
    if 'properties' in auto_tool.inputSchema:
        print(f"Properties: {list(auto_tool.inputSchema['properties'].keys())}")
        
        # Check a specific parameter
        if 'module_name' in auto_tool.inputSchema['properties']:
            print(f"\nExample Property (module_name):")
            import json
            print(json.dumps(auto_tool.inputSchema['properties']['module_name'], indent=2))
    
    # Manual schema (what we had before)
    manual_schema = {
        "type": "object",
        "properties": {
            "module_name": {
                "type": "string",
                "description": "Name of the Verilog module (e.g., 'counter_8bit')"
            },
            "description": {
                "type": "string",
                "description": "What the module does (e.g., '8-bit synchronous counter with enable')"
            },
            "ports": {
                "type": "array",
                "description": "List of port definitions",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "direction": {"type": "string", "enum": ["input", "output", "inout"]},
                        "type": {"type": "string", "default": "logic"},
                        "width": {"type": ["integer", "null"], "description": "Bit width (omit for 1-bit)"},
                        "description": {"type": "string"}
                    },
                    "required": ["name", "direction"]
                }
            },
            "clock_period_ns": {
                "type": "number",
                "description": "Target clock period in nanoseconds (default: 10.0)",
                "default": 10.0
            },
        },
        "required": ["module_name", "description", "ports"]
    }
    
    print("\n\n2. MANUAL SCHEMA (what we had before)")
    print("-" * 70)
    print(f"Properties: {list(manual_schema['properties'].keys())}")
    print(f"\nExample Property (module_name):")
    import json
    print(json.dumps(manual_schema['properties']['module_name'], indent=2))
    
    print("\n\n3. DIFFERENCES")
    print("-" * 70)
    
    # Check if schemas match
    auto_props = auto_tool.inputSchema.get('properties', {}).keys()
    manual_props = manual_schema['properties'].keys()
    
    print(f"Auto-discovered has {len(auto_props)} properties")
    print(f"Manual had {len(manual_props)} properties (we only showed subset)")
    
    print("\n✅ WHY AUTO-DISCOVERY WORKS:")
    print("  - LangChain @tool decorator captures function signature")
    print("  - Type hints → JSON Schema types")
    print("  - Docstrings → descriptions")
    print("  - Default values preserved")
    
    print("\n⚠️  POTENTIAL CONCERNS:")
    print("  - Complex nested types might lose detail")
    print("  - Manual schemas can add examples, constraints")
    print("  - Hand-tuned descriptions can be more user-friendly")
    
    print("\n" + "="*70)


if __name__ == "__main__":
    asyncio.run(compare_schemas())
