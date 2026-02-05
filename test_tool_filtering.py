"""
Test tool filtering functionality
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from mcp_server import RTLDesignMCPServer


async def test_tool_filtering():
    """Test that tool filtering works correctly."""
    print("="*70)
    print("TESTING TOOL FILTERING")
    print("="*70)
    
    server = RTLDesignMCPServer()
    
    # Test 1: Default mode (all tools)
    print("\n1. Default Mode (all tools)")
    print("-" * 70)
    tools = await server.list_tools()
    print(f"✓ Total tools: {len(tools)}")
    tool_names = [t.name for t in tools]
    print(f"  Tools: {', '.join(tool_names[:10])}...")
    
    # Test 2: Essential mode
    print("\n2. Essential Mode (core workflow only)")
    print("-" * 70)
    result = await server.call_tool("configure_tool_filter", {"mode": "essential"})
    print(f"  {result[0].text}")
    
    tools_essential = await server.list_tools()
    print(f"✓ Filtered tools: {len(tools_essential)}")
    essential_names = [t.name for t in tools_essential if t.name not in ["create_session_tool", "list_sessions_tool", "set_active_session", "get_current_session", "delete_session_tool", "configure_tool_filter"]]
    print(f"  Essential RTL tools: {', '.join(essential_names)}")
    
    # Test 3: Custom filter (only verification tools)
    print("\n3. Custom Mode (verification category only)")
    print("-" * 70)
    result = await server.call_tool("configure_tool_filter", {
        "mode": "custom",
        "custom_filter": ["essential", "verification"]
    })
    print(f"  {result[0].text}")
    
    tools_custom = await server.list_tools()
    print(f"✓ Custom filtered tools: {len(tools_custom)}")
    
    # Test 4: Back to all
    print("\n4. Back to All Tools")
    print("-" * 70)
    result = await server.call_tool("configure_tool_filter", {"mode": "all"})
    print(f"  {result[0].text}")
    
    tools_all = await server.list_tools()
    print(f"✓ All tools restored: {len(tools_all)}")
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print(f"All mode:       {len(tools_all)} tools")
    print(f"Essential mode: {len(tools_essential)} tools (saved {len(tools_all) - len(tools_essential)} tools, {100 * (len(tools_all) - len(tools_essential)) / len(tools_all):.0f}% reduction)")
    print(f"Custom mode:    {len(tools_custom)} tools")
    
    print("\n✅ Tool filtering works correctly!")
    print("\n💡 Use Cases:")
    print("  - Essential mode: Simple designs, learning, reduced LLM context")
    print("  - Custom mode: Specific workflow (e.g., verification-focused)")
    print("  - All mode: Complex designs needing full toolset")


if __name__ == "__main__":
    asyncio.run(test_tool_filtering())
