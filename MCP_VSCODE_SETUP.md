# MCP Server Setup for VS Code

**Connect your RTL Design Agent to VS Code using the Model Context Protocol**

---

## Prerequisites

✅ You already have:
- MCP server implemented (`mcp_server.py`)
- Python virtual environment with `mcp[cli]` installed
- VS Code installed

---

## Installation Steps

### 1. Install GitHub Copilot Extension (if not already installed)

```
1. Open VS Code
2. Go to Extensions (Ctrl+Shift+X)
3. Search for "GitHub Copilot"
4. Install the official extension
```

**Note**: GitHub Copilot now supports MCP protocol for connecting to custom servers.

### 2. Configure MCP Server in VS Code

VS Code MCP configuration can be done in two ways:

#### Option A: Workspace Configuration (Recommended)

Create a `.vscode/mcp.json` file in your workspace root:

1. Open your RTL_AGENT workspace in VS Code
2. Create `.vscode/mcp.json` file (or use the one already created)
3. Add the following configuration:

```json
{
  "servers": {
    "rtl-design-agent": {
      "type": "stdio",
      "command": "${workspaceFolder}\\.venv\\Scripts\\python.exe",
      "args": [
        "${workspaceFolder}\\mcp_server.py"
      ],
      "cwd": "${workspaceFolder}",
      "env": {
        
      }
    }
  }
}
```

**Benefits of workspace configuration:**
- Server only loads when this workspace is open
- Configuration is committed with your project
- Easy to share with team members
- VS Code shows helpful code lenses to start/stop/restart server

#### Option B: User Settings (Global)

1. Press `Ctrl+Shift+P`
2. Type "Preferences: Open User Settings (JSON)"
3. Add the following configuration:

```json
{
  "github.copilot.chat.mcp.servers": {
    "rtl-design-agent": {
      "command": "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\mcp_server.py"
      ],
      "env": {
        "GOOGLE_API_KEY": "your_google_api_key_here"
      }
    }
  }
}
```

**Important**: Replace `your_google_api_key_here` with your actual Google API key (or use the path to your `.env` file approach below).

### 3. Alternative: Using .env File

If you prefer to keep your API key in the `.env` file:

```json
{
  "github.copilot.chat.mcp.servers": {
    "rtl-design-agent": {
      "command": "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\mcp_server.py"
      ],
      "cwd": "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT"
    }
  }
}
```

The server will automatically load the `.env` file from the working directory.

### 4. Restart VS Code

```
Close and reopen VS Code to activate the MCP server.
```

---

## Verification

### Test the Connection

1. **Open Copilot Chat**
   - Press `Ctrl+Shift+I` or click the chat icon in the sidebar

2. **Check if Server is Connected**
   - Look for "RTL Design Agent" in available tools/servers
   - You should see the system prompt available

3. **Load the Workflow Prompt**
   - Type: `@rtl-design-agent` or use the prompt selector
   - Look for "rtl_design_workflow" prompt

4. **Create a Test Session**
   ```
   Create a new RTL design session called "test_vscode"
   ```

5. **Verify Tools Are Available**
   ```
   What tools do you have access to?
   ```
   
   You should see 24 tools (or 13 if in essential mode):
   - Session management: create_session, list_sessions, etc.
   - RTL tools: write_spec, read_spec, write_file, etc.
   - Verification: linter_tool, simulation_tool, waveform_tool
   - Synthesis: synthesis_tool, ppa_tool, etc.

---

## Usage Examples

### Example 1: Create a Simple Design

```
Load the RTL Design Workflow prompt.

Create a new session called "counter_design".

Design a 4-bit synchronous counter with:
- Active high reset
- Enable signal
- Target clock period: 10ns
```

### Example 2: Switch Between Sessions

```
List all my design sessions.

Switch to session "counter_design".

Show me the files in the current session.
```

### Example 3: Use Tool Filtering

```
Configure tool filter to show only essential tools.

Now design a simple AND gate.
```

---

## VS Code-Specific Features

### Advantages of VS Code + MCP

| Feature | Benefit |
|---------|---------|
| **Inline Code Context** | Copilot can reference your open files |
| **Terminal Integration** | Can suggest commands to run in VS Code terminal |
| **Git Integration** | Aware of your repository state |
| **Multi-File Editing** | Can help edit multiple files in your workspace |
| **Debugging Context** | Can see your debug sessions and breakpoints |

### Using MCP Resources in VS Code

Your MCP server exposes resources that VS Code can access:

```
Show me all RTL design sessions (rtl://sessions)

Read the specification file from session "counter_design" 
(rtl://session/counter_design/file/design_spec.yaml)
```

---

## Troubleshooting

### Issue: MCP Server Not Showing Up

**Solution 1**: Check MCP server list
1. Press `Ctrl+Shift+P`
2. Run command: `MCP: List Servers`
3. Look for "rtl-design-agent" in the list
4. Check server status (should show "running")

**Solution 2**: Use workspace configuration (.vscode/mcp.json)
- This is the preferred method
- Easier to debug (VS Code shows code lenses to manage server)
- Configuration is project-specific

**Solution 3**: Check MCP Output Log
1. Press `Ctrl+Shift+P`
2. Run: `MCP: List Servers`
3. Select your server
4. Choose "Show Output"
5. Look for error messages

**Solution 4**: Verify paths in .vscode/mcp.json
```json
// Use ${workspaceFolder} variable instead of absolute paths
"command": "${workspaceFolder}\\.venv\\Scripts\\python.exe"
```

### Issue: Tools Not Appearing

**Check server is running:**
1. Open VS Code Output panel (`Ctrl+Shift+U`)
2. Select "GitHub Copilot" output
3. Look for "MCP server rtl-design-agent started" message

**Restart the MCP server:**
1. Press `Ctrl+Shift+P`
2. Type "Developer: Reload Window"

### Issue: API Key Not Found

**Add to settings.json env:**
```json
{
  "github.copilot.chat.mcp.servers": {
    "rtl-design-agent": {
      "command": "...",
      "args": [...],
      "env": {
        "GOOGLE_API_KEY": "your_key_here"
      }
    }
  }
}
```

---

## Comparison: Claude Desktop vs VS Code

| Feature | Claude Desktop | VS Code + Copilot |
|---------|---------------|-------------------|
| **Session Management** | ✅ Full support | ✅ Full support |
| **Tool Access** | ✅ All 24 tools | ✅ All 24 tools |
| **System Prompt** | ✅ rtl_design_workflow | ✅ rtl_design_workflow |
| **File Access** | ✅ Via resources | ✅ Via resources + workspace |
| **Code Context** | ❌ Limited | ✅ Inline code awareness |
| **Debugging** | ❌ No | ✅ Debug context available |
| **Multi-File** | ❌ Single focus | ✅ Multi-file editing |
| **UI** | ✅ Dedicated chat | ⚠️ Sidebar chat |

**Recommendation**: Use **VS Code** when:
- Editing existing RTL projects
- Working with multi-file designs
- Debugging simulation failures
- Integrating with Git workflow

Use **Claude Desktop** when:
- Starting new designs from scratch
- Focused conversation without IDE distractions
- Quick prototyping

---

## Advanced Configuration

### Multiple MCP Servers

You can run multiple MCP servers simultaneously:

```json
{
  "github.copilot.chat.mcp.servers": {
    "rtl-design-agent": {
      "command": "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\mcp_server.py"]
    },
    "other-mcp-server": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "C:\\Projects"]
    }
  }
}
```

### Custom Environment Variables

```json
{
  "github.copilot.chat.mcp.servers": {
    "rtl-design-agent": {
      "command": "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\mcp_server.py"],
      "env": {
        "GOOGLE_API_KEY": "your_key",
        "LOG_LEVEL": "DEBUG",
        "DEFAULT_SESSION": "my_default_session"
      }
    }
  }
}
```

### Logging for Debugging

Add logging to track MCP server behavior:

```json
{
  "github.copilot.chat.mcp.servers": {
    "rtl-design-agent": {
      "command": "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\.venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\mcp_server.py"],
      "env": {
        "MCP_LOG_FILE": "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\mcp_vscode.log"
      }
    }
  }
}
```

Then check the log file for detailed server activity.

---

## Next Steps

1. ✅ Configure VS Code settings.json
2. ✅ Restart VS Code
3. ✅ Open Copilot Chat (`Ctrl+Shift+I`)
4. ✅ Load "rtl_design_workflow" prompt
5. ✅ Create your first design session
6. ✅ Design something awesome! 🚀

---

## Integration with Your Existing Workflow

### Scenario: Working on Hackathon Problems

```
1. Open VS Code in your RTL_AGENT folder
2. Open Copilot Chat
3. Create session for problem: "Create session called 'p1_seq_detector'"
4. Design RTL: "Design sequence detector for pattern '0011'"
5. Check files in VS Code explorer: workspace/p1_seq_detector/
6. Run verification: "Lint and simulate the design"
7. View waveforms: "Show waveform analysis"
8. Run synthesis: "Synthesize with 1.1ns clock period"
9. Check results in VS Code: workspace/p1_seq_detector/orfs_results/
```

### Scenario: Multi-Session Development

```
Terminal 1 (VS Code): Working on "p1_seq_detector"
Terminal 2 (Claude Desktop): Working on "p5_dot_product"

Both share the same backend!
- Same workspace/ directory
- Same state.db
- Same SessionManager
- Can switch between sessions in either client
```

---

*Setup Guide for VS Code MCP Integration*  
*Date: February 5, 2026*  
*Compatible with: VS Code 1.95+, GitHub Copilot, MCP SDK 1.0+*
