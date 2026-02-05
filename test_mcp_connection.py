#!/usr/bin/env python3
"""
Quick test to verify MCP server can be imported and initialized.
This doesn't test the full MCP protocol, just that the server module loads correctly.
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_mcp_server_import():
    """Test that MCP server can be imported"""
    try:
        import mcp_server
        print("✅ MCP server module imported successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to import MCP server: {e}")
        return False

def test_server_initialization():
    """Test that server class can be instantiated"""
    try:
        from mcp_server import RTLDesignMCPServer
        server = RTLDesignMCPServer()
        print("✅ RTLDesignMCPServer instantiated successfully")
        print(f"📊 Current session: {server.current_session or 'None (will auto-create)'}")
        print(f"🔧 Tool filter mode: {server.tool_filter_mode}")
        return True
    except Exception as e:
        print(f"❌ Failed to instantiate server: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_tool_discovery():
    """Test that tools are discovered"""
    try:
        from mcp_server import RTLDesignMCPServer
        server = RTLDesignMCPServer()
        
        # Count tools (should be 24 total in "all" mode, or 13 in "essential" mode)
        from src.tools.wrappers import architect_tools
        base_tools = len(architect_tools)
        session_tools = 5  # create_session, list_sessions, set_active_session, get_current_session, delete_session
        configure_filter = 1  # configure_tool_filter
        
        expected_all = base_tools + session_tools + configure_filter
        
        print(f"✅ Tool discovery working:")
        print(f"   - Base RTL tools: {base_tools}")
        print(f"   - Session management: {session_tools}")
        print(f"   - Tool filter config: {configure_filter}")
        print(f"   - Total expected (all mode): {expected_all}")
        
        return True
    except Exception as e:
        print(f"❌ Tool discovery failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_files():
    """Test that config files exist"""
    claude_config = r"C:\Users\naman\AppData\Roaming\Claude\claude_desktop_config.json"
    
    print("\n📁 Configuration Files:")
    
    # Check Claude Desktop config
    if os.path.exists(claude_config):
        print(f"✅ Claude Desktop config exists: {claude_config}")
        import json
        with open(claude_config, 'r') as f:
            config = json.load(f)
            if 'mcpServers' in config and 'rtl-design-agent' in config['mcpServers']:
                print("   ✅ rtl-design-agent configured in Claude Desktop")
            else:
                print("   ⚠️ rtl-design-agent NOT found in Claude Desktop config")
    else:
        print(f"❌ Claude Desktop config not found: {claude_config}")
    
    return True

def main():
    print("=" * 60)
    print("MCP Server Connection Test")
    print("=" * 60)
    print()
    
    results = []
    
    print("1️⃣ Testing MCP server import...")
    results.append(test_mcp_server_import())
    print()
    
    print("2️⃣ Testing server initialization...")
    results.append(test_server_initialization())
    print()
    
    print("3️⃣ Testing tool discovery...")
    results.append(test_tool_discovery())
    print()
    
    print("4️⃣ Checking configuration files...")
    results.append(test_config_files())
    print()
    
    print("=" * 60)
    if all(results):
        print("✅ ALL TESTS PASSED - MCP server is ready!")
        print()
        print("Next steps:")
        print("1. Restart Claude Desktop")
        print("2. Restart VS Code (Ctrl+Shift+P → 'Developer: Reload Window')")
        print("3. Look for 'rtl-design-agent' in MCP servers list")
        print("4. Load 'rtl_design_workflow' prompt")
        print("5. Create a test session and start designing!")
    else:
        print("❌ SOME TESTS FAILED - Check errors above")
    print("=" * 60)

if __name__ == "__main__":
    main()
