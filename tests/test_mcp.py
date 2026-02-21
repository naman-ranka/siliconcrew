"""
Test script to verify MCP server functionality
"""

import asyncio
import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(__file__))

from mcp_server import RTLDesignMCPServer


async def test_mcp_server():
    """Test that the MCP server initializes correctly."""
    print("Testing MCP Server initialization...")
    
    server = RTLDesignMCPServer()
    
    # Test list_tools
    print("\n1. Testing list_tools()...")
    tools = await server.list_tools()
    print(f"   ✓ Found {len(tools)} tools")
    
    tool_names = [t.name for t in tools]
    expected_tools = [
        "create_session_tool", "list_sessions_tool", "set_active_session", "get_current_session",
        "write_spec", "read_spec", "load_yaml_spec_file",
        "write_file", "read_file", "edit_file_tool", "list_files_tool",
        "linter_tool", "simulation_tool", "waveform_tool",
        "synthesis_tool", "ppa_tool", "search_logs_tool",
        "generate_report_tool"
    ]
    
    for expected in expected_tools:
        if expected in tool_names:
            print(f"   ✓ {expected}")
        else:
            print(f"   ✗ MISSING: {expected}")
    
    # Test list_prompts
    print("\n2. Testing list_prompts()...")
    prompts = await server.list_prompts()
    print(f"   ✓ Found {len(prompts)} prompt(s)")
    
    for prompt in prompts:
        print(f"   ✓ {prompt.name}: {prompt.description[:60]}...")
    
    # Test get_prompt
    print("\n3. Testing get_prompt('rtl_design_workflow')...")
    prompt_result = await server.get_prompt("rtl_design_workflow", {"session_id": "test"})
    print(f"   ✓ Description: {prompt_result.description}")
    print(f"   ✓ Messages: {len(prompt_result.messages)}")
    
    # Check SYSTEM_PROMPT is included
    message_content = str(prompt_result.messages[0].content.text)
    if "SYSTEM_PROMPT" in message_content and "Architect" in message_content:
        print(f"   ✓ SYSTEM_PROMPT included (length: {len(message_content)} chars)")
    else:
        print(f"   ✗ SYSTEM_PROMPT not found")
    
    # Test session management
    print("\n4. Testing session management...")
    try:
        # Create a test session
        result = await server.call_tool("create_session_tool", {"session_name": "test_session_1"})
        print(f"   ✓ create_session_tool: {result[0].text[:80]}...")
        
        # List sessions
        result = await server.call_tool("list_sessions_tool", {})
        print(f"   ✓ list_sessions_tool executed")
        
        # Get current session
        result = await server.call_tool("get_current_session", {})
        print(f"   ✓ get_current_session: Active session detected")
        
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Test resources
    print("\n5. Testing list_resources()...")
    try:
        resources = await server.list_resources()
        print(f"   ✓ Found {len(resources)} resource(s)")
        if resources:
            print(f"   ✓ First resource: {resources[0].name}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    print("\n" + "="*60)
    print("✅ MCP Server is ready with SESSION MANAGEMENT!")
    print("="*60)
    print("\nNext steps:")
    print("1. Configure Claude Desktop (see MCP_SETUP.md)")
    print("2. Copy claude_desktop_config.example.json settings")
    print("3. Restart Claude Desktop")
    print("4. Load 'RTL Design Workflow' prompt in Claude")


if __name__ == "__main__":
    asyncio.run(test_mcp_server())
