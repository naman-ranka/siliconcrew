# MCP Server Setup Guide

## What This Does

The MCP server exposes your RTL design tools to **any MCP-compatible client** (Claude Desktop, VS Code, etc.) while preserving your expert workflow through **MCP Prompts**.

### Architecture

```
Claude Desktop
    ↓ (loads prompt)
    ↓ "RTL Design Workflow" → SYSTEM_PROMPT injected
    ↓ (uses tools)
    ↓ write_spec → linter_tool → simulation_tool → synthesis_tool
    ↓
MCP Server (mcp_server.py)
    ↓
Your Existing Tools (src/tools/wrappers.py)
    ↓
Shared Workspace
```

**Key Feature**: Claude gets your **entire SYSTEM_PROMPT** (500+ lines of RTL design expertise) when the user loads the "RTL Design Workflow" prompt!

---

## Installation

### 1. Install MCP SDK

```powershell
# Activate your venv first
.\.venv\Scripts\Activate.ps1

# Install MCP
pip install mcp
```

Or update all dependencies:
```powershell
pip install -r requirements.txt
```

### 2. Test the MCP Server

```powershell
python mcp_server.py
```

It should start and wait for stdin (this is correct - MCP uses stdio communication).

Press `Ctrl+C` to stop.

---

## Claude Desktop Configuration

### 1. Find Claude Desktop Config

The config file location depends on your OS:

**Windows**:
```
%APPDATA%\Claude\claude_desktop_config.json
```

Typically:
```
C:\Users\<YourUsername>\AppData\Roaming\Claude\claude_desktop_config.json
```

**macOS**:
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

**Linux**:
```
~/.config/Claude/claude_desktop_config.json
```

### 2. Edit Configuration

Open `claude_desktop_config.json` and add:

```json
{
  "mcpServers": {
    "rtl-design-agent": {
      "command": "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\mcp_server.py"
      ],
      "env": {
        "GOOGLE_API_KEY": "your-gemini-api-key-here"
      }
    }
  }
}
```

**Important**: 
- Use **absolute paths**
- Escape backslashes in Windows paths (use `\\`)
- Replace `your-gemini-api-key-here` with your actual API key (or remove if already in `.env`)

### 3. Alternative: Use .env for API Key

If you prefer to keep the API key in your `.env` file:

```json
{
  "mcpServers": {
    "rtl-design-agent": {
      "command": "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\Users\\naman\\Desktop\\Projects\\RTL_AGENT\\mcp_server.py"
      ]
    }
  }
}
```

The server will automatically load from `.env` via `load_dotenv()`.

### 4. Restart Claude Desktop

Close and reopen Claude Desktop completely.

---

## How to Use

### Step 1: Load the Expert Workflow Prompt

In Claude Desktop:

1. Click the **📎 attachment icon** in the chat input
2. Select **"Choose an MCP Prompt"**
3. Select **"rtl_design_workflow"**
4. (Optional) Set `session_id` to a custom name (e.g., "counter_project")
   - If omitted, auto-creates a timestamped session like `mcp_session_20260205_143530`

Claude now has your **entire SYSTEM_PROMPT** in context!

### Step 2: Design Something

Just ask Claude to design hardware:

```
Design a 4-bit synchronous counter with enable and reset.
Target clock period: 10ns
```

Claude will:
1. ✅ Call `write_spec` first (as instructed by SYSTEM_PROMPT)
2. ✅ Generate RTL following best practices
3. ✅ Write testbench with VCD dumping
4. ✅ Lint the code
5. ✅ Run simulation
6. ✅ Use `waveform_tool` if it fails
7. ✅ Run synthesis
8. ✅ Generate report

### Step 3: Manage Sessions (Optional)

**Create a new session:**
```
Create a session called "uart_transmitter"
```
Claude calls: `create_session_tool("uart_transmitter")`

**List all sessions:**
```
What sessions do I have?
```
Claude calls: `list_sessions_tool()`

**Switch sessions:**
```
Switch to my counter_project session
```
Claude calls: `set_active_session("counter_project")`

**See current session:**
```
What session am I in?
```
Claude calls: `get_current_session()`

See [MCP_SESSION_GUIDE.md](MCP_SESSION_GUIDE.md) for detailed session management docs.

### Step 4: View Artifacts

All files are stored in:
```
workspace/<session_id>/
```

Example session "default":
```
workspace/default/
├── counter_4bit_spec.yaml
├── counter_4bit.v
├── counter_4bit_tb.v
├── waveform.vcd
├── constraints.sdc
├── counter_4bit_report.md
└── orfs_results/
    └── sky130hd/
        └── counter_4bit/
            └── base/
                └── 6_final.gds
```

---

## Available Tools

Claude has access to all 23 tools:

### Session Management (5 tools)
- `create_session_tool` - Create new isolated workspace
- `list_sessions_tool` - List all sessions with metadata
- `set_active_session` - Switch to different session
- `get_current_session` - Get active session info
- `delete_session_tool` - Delete session and files

### Specification Tools (3 tools)
- `write_spec` - Create YAML spec (ALWAYS first!)
- `read_spec` - Load existing spec
- `load_yaml_spec_file` - Import external YAML

### File Management (4 tools)
- `write_file` - Create files
- `read_file` - Read files
- `edit_file_tool` - Surgical edits
- `list_files_tool` - List workspace

### Verification Tools
- `linter_tool` - Check syntax (iverilog)
- `simulation_tool` - Run testbench
- `waveform_tool` - Debug with VCD
- `cocotb_tool` - Python testbenches (optional)
- `sby_tool` - Formal verification (optional)

### Synthesis Tools
- `synthesis_tool` - OpenROAD flow
- `ppa_tool` - Extract metrics
- `search_logs_tool` - Search synthesis logs
- `schematic_tool` - Generate SVG

### Reporting Tools
- `save_metrics_tool` - Save manual metrics
- `generate_report_tool` - Create final report

---

## Testing the Workflow

### Example Session

**User in Claude Desktop:**
```
[Loads "RTL Design Workflow" prompt with session_id="test1"]

Design a simple 2-bit counter with synchronous reset.
```

**Claude (following SYSTEM_PROMPT):**
```
I'll design a 2-bit counter following the expert workflow.

[Calls write_spec with proper port definitions]
[Calls write_file for RTL with correct coding style]
[Calls write_file for testbench with VCD dumping]
[Calls linter_tool on RTL]
[Calls linter_tool on testbench]
[Calls simulation_tool]
[If pass: calls synthesis_tool]
[Calls generate_report_tool]
```

All following the **exact best practices from SYSTEM_PROMPT**!
23 tools | Same 23 tools |
| **Workflow** | Your Gemini agent | Claude + SYSTEM_PROMPT |
| **Sessions** | REST API management | MCP tools + resources |
| **UI** | Custom React tabs | Claude's chat UI |
| **Artifacts** | Browser viewer | File system + Claude artifacts |
| **Workspace** | Shared `workspace/` | Shared `workspace/` |
| **Database** | Shared `state.db` | Shared `state.db` |
| **Best For** | Custom UX, demos | Quick iteration, Claude's strengths |

**Key Point:** Both use the **same backend infrastructure** - sessions created in MCP appear in the Next.js frontend and vice versa!
|---------|------------------|----------------------|
| **Tools** | Same 18 tools | Same 18 tools |
| **Workflow** | Your Gemini agent | Claude + SYSTEM_PROMPT |
| **UI** | Custom React tabs | Claude's chat UI |
| **Artifacts** | Browser viewer | File system + Claude artifacts |
| **Workspace** | Shared | Shared |
| **Best For** | Custom UX, demos | Quick iteration, Claude's strengths |

---

## Troubleshooting

### MCP Server Not Appearing in Claude

1. Check config file syntax (valid JSON?)
2. Check paths are absolute and correct
3. Restart Claude Desktop **completely**
4. Check Claude Desktop logs:
   - Windows: `%APPDATA%\Claude\logs`
   - macOS: `~/Library/Logs/Claude`

### Tool Execution Fails

1. Ensure Python venv is activated in the command path
2. Check workspace directory exists and is writable
3. For synthesis: Ensure Docker is running

### Workspace Isolation

Each session gets its own folder:
- Default session: `workspace/default/`
- Custom session: `workspace/<session_id>/`

Both MCP and FastAPI can share sessions safely!

---

## Advanced: Cloud Desktop Setup

To use from a remote machine:

### 1. Run MCP Server on Cloud

```bash
# On cloud machine
cd /path/to/RTL_AGENT
source .venv/bin/activate
python mcp_server.py
```

### 2. SSH Tunnel (Optional)

For secure remote access, you can use SSH tunneling or run the MCP server with SSE transport instead of stdio.

### 3. Configure Local Claude Desktop

```json
{
  "mcpServers": {
    "rtl-design-agent-cloud": {
      "command": "ssh",
      "args": [
        "user@cloud-server",
        "cd /path/to/RTL_AGENT && .venv/bin/python mcp_server.py"
      ]
    }
  }
}
```

Now you run OpenROAD synthesis on the cloud from your local Claude Desktop!

---

## SYSTEM_PROMPT in Action

When Claude loads the "RTL Design Workflow" prompt, it receives:

```
You are "The Architect", an expert autonomous agent specialized in 
digital hardware design.

You have deep expertise in:
- Verilog-2001 and SystemVerilog (IEEE 1800-2017)
- Digital logic design patterns (FSMs, pipelines, memories, arithmetic)
- Verification methodologies (self-checking testbenches, assertions, coverage)
- Physical design concepts (timing, area, power tradeoffs)
- OpenROAD/ORFS synthesis flow
- ASIC design for SkyWater 130nm PDK

[... 500+ lines of best practices, workflows, anti-patterns ...]

## STANDARD WORKFLOW

### Phase 1: SPECIFICATION (Always First!)
1. Parse the request
2. Call `write_spec`
3. Inform the user to review

### Phase 2: IMPLEMENTATION
5. Call `read_spec` to load confirmed specification
6. Write the RTL file
7. Write the testbench

[... detailed instructions ...]
```

This ensures Claude follows **your exact methodology** even though it's using its own intelligence to orchestrate the tools!

---

## Next Steps

Want to extend this further?

1. **Add MCP Resources** - Expose workspace files as browsable resources
2. **Add More Prompts** - Specialized prompts for verification-only, synthesis-only, etc.
3. **Streaming Results** - Use MCP progress notifications for long-running synthesis
4. **VS Code Integration** - Use the same MCP server with GitHub Copilot in VS Code

The MCP server is production-ready and preserves your entire expert workflow! 🚀
