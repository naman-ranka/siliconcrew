# MCP Session Management Guide

## Overview

The MCP server now has **full session management** - just like your FastAPI backend! Each session gets an isolated workspace, and you can have multiple concurrent design sessions.

---

## How It Works

### Architecture

```
Claude Desktop
    ↓
MCP Server (mcp_server.py)
    ↓
SessionManager (shared with FastAPI!)
    ↓
workspace/
    ├── session1/          ← Isolated workspace
    │   ├── counter_spec.yaml
    │   ├── counter.v
    │   └── ...
    ├── session2/          ← Different design
    │   ├── uart_spec.yaml
    │   └── uart.v
    └── mcp_session_20260205_143022/  ← Auto-created
        └── ...
```

### Key Features

✅ **Auto-created sessions** - Loading a prompt creates a new session automatically  
✅ **Manual session control** - Create, switch, list, delete sessions via tools  
✅ **Shared with FastAPI** - Same workspace/database as your web frontend  
✅ **MCP Resources** - Browse sessions and files directly in MCP clients  
✅ **Session persistence** - Context maintained across tool calls  

---

## Usage Patterns

### Pattern 1: Quick Start (Automatic Session)

**User in Claude Desktop:**
```
[Loads "RTL Design Workflow" prompt - no arguments]
```

**What happens:**
- MCP server creates: `mcp_session_20260205_143530`
- Sets it as active
- All tools use this workspace
- User can start designing immediately

**Example:**
```
User: Design a 4-bit counter

Claude: [Uses auto-created session]
        [Calls write_spec with session workspace]
        [Calls write_file to session workspace]
        [All artifacts in mcp_session_20260205_143530/]
```

---

### Pattern 2: Named Session (Organized)

**User in Claude Desktop:**
```
[Loads "RTL Design Workflow" prompt]
Session ID: counter_project
↓ [Then asks:]

Design a 4-bit synchronous counter
```

**What happens:**
- MCP server uses session: `counter_project`
- Creates workspace: `workspace/counter_project/`
- User can return to this session later

**Benefits:**
- Descriptive names
- Easy to find later
- Can work on multiple projects

---

### Pattern 3: Multi-Session Workflow (Advanced)

**Scenario:** Design counter and UART in parallel

**User in Claude:**
```
Create a session for my counter design
[Claude calls: create_session_tool("counter_design")]

✅ Created session 'counter_design'

Now create a session for my UART
[Claude calls: create_session_tool("uart_design")]  

✅ Created session 'uart_design'

List my sessions
[Claude calls: list_sessions_tool()]

[Shows both sessions]

Switch to counter_design
[Claude calls: set_active_session("counter_design")]

✅ Switched to counter_design

Design a 4-bit counter
[All work goes to workspace/counter_design/]

Switch to uart_design  
[Claude calls: set_active_session("uart_design")]

Design a UART transmitter
[All work goes to workspace/uart_design/]
```

---

## Session Management Tools

### 5 New Tools Added

#### 1. `create_session_tool`
**Purpose:** Create a new isolated workspace

**Input:**
```json
{
  "session_name": "my_project",
  "model_name": "claude-via-mcp"  // optional
}
```

**Output:**
```
✅ Created session 'my_project'
Workspace: C:\...\workspace\my_project
This session is now active.
```

**When to use:**
- Starting a new design project
- Organizing multiple designs
- Creating isolated test environments

---

#### 2. `list_sessions_tool`
**Purpose:** See all available sessions

**Input:** None

**Output:**
```json
[
  {
    "id": "counter_design",
    "model": "claude-via-mcp",
    "created": "2026-02-05 14:30:00",
    "tokens": 1250,
    "active": "← ACTIVE"
  },
  {
    "id": "uart_design",
    "model": "claude-via-mcp",
    "created": "2026-02-05 15:45:00",
    "tokens": 3400,
    "active": ""
  }
]
```

**When to use:**
- Checking which designs exist
- Finding a specific project
- Reviewing token usage

---

#### 3. `set_active_session`
**Purpose:** Switch to a different session

**Input:**
```json
{
  "session_id": "uart_design"
}
```

**Output:**
```
✅ Switched to session 'uart_design'
Workspace: C:\...\workspace\uart_design
All tools will now use this workspace.
```

**When to use:**
- Switching between projects
- Resuming previous work
- Comparing different designs

---

#### 4. `get_current_session`
**Purpose:** See which session is active

**Input:** None

**Output:**
```json
{
  "session_id": "counter_design",
  "workspace": "C:\\...\\workspace\\counter_design",
  "metadata": {
    "model_name": "claude-via-mcp",
    "created_at": "2026-02-05 14:30:00",
    "total_tokens": 1250
  }
}
```

**When to use:**
- Confirming active session
- Checking workspace path
- Verifying session metadata

---

#### 5. `delete_session_tool`
**Purpose:** Delete a session and all files

**Input:**
```json
{
  "session_id": "old_project"
}
```

**Output:**
```
✅ Deleted session 'old_project' and all its files.
```

**When to use:**
- Cleaning up old projects
- Freeing disk space
- Removing failed experiments

**Note:** Cannot delete active session (switch first)

---

## MCP Resources

The MCP server exposes sessions as **browsable resources** that MCP clients can display.

### Available Resources

#### 1. `rtl://sessions`
**Lists all sessions with metadata**

```json
[
  {
    "id": "counter_design",
    "model_name": "claude-via-mcp",
    "created_at": "2026-02-05",
    "total_tokens": 1250,
    "total_cost": 0.0
  }
]
```

#### 2. `rtl://session/{session_id}`
**Session details and file list**

```json
{
  "session_id": "counter_design",
  "workspace": "C:\\...\\workspace\\counter_design",
  "files": [
    "counter_spec.yaml",
    "counter.v",
    "counter_tb.v",
    "waveform.vcd"
  ]
}
```

#### 3. `rtl://session/{session_id}/file/{filename}`
**Read specific file content**

Returns the actual file content (Verilog code, YAML spec, etc.)

---

## Integration with FastAPI Backend

### Shared Database

Both MCP server and FastAPI backend use the **same SQLite database** (`state.db`):

```
state.db
├── session_metadata table     ← Shared!
│   ├── counter_design
│   ├── uart_design  
│   └── mcp_session_...
└── checkpoints table          ← LangGraph state
```

### Shared Workspace

Both use the **same workspace directory**:

```
workspace/
├── counter_design/        ← Created by MCP or FastAPI
├── frontend_session_1/    ← Created by Next.js frontend
└── mcp_session_20260205/  ← Created by MCP prompt
```

### Cross-Access

You can:
- ✅ Create a session in MCP, view in Next.js frontend
- ✅ Create a session in frontend, access via MCP
- ✅ Switch between interfaces seamlessly
- ✅ Share designs with collaborators

**Example:**
```
1. User creates "counter_project" in Claude Desktop (MCP)
2. Designs counter using MCP tools
3. Opens Next.js frontend
4. Sees "counter_project" in session list
5. Views waveforms/GDS in browser
6. Continues in Claude Desktop
```

---

## Example Conversations

### Example 1: Single Project

**User:**
```
[Loads RTL Design Workflow prompt with session_id: my_counter]

Design a 4-bit synchronous counter with enable and active-high reset.
Target: 10ns clock period
```

**Claude:**
```
I'll design this counter in session 'my_counter'. Let me start with the specification.

[Calls: write_spec]
✅ Spec created: my_counter_spec.yaml

[Calls: write_file for RTL]
✅ Created: counter_4bit.v

[Calls: write_file for testbench]
✅ Created: counter_4bit_tb.v

[Calls: linter_tool]
✅ Syntax OK

[Calls: simulation_tool]
✅ TEST PASSED

[Calls: synthesis_tool]
✅ Synthesis complete

All artifacts are in workspace/my_counter/
```

---

### Example 2: Multi-Project

**User:**
```
I want to work on two designs: a counter and a UART. 
Create separate sessions for each.
```

**Claude:**
```
[Calls: create_session_tool("counter_project")]
✅ Created session 'counter_project'

[Calls: create_session_tool("uart_project")]  
✅ Created session 'uart_project'

I've created two isolated sessions:
1. counter_project (currently active)
2. uart_project

Which design would you like to work on first?
```

**User:**
```
Start with the counter. Make it 8-bit with enable.
```

**Claude:**
```
[Confirms active session: counter_project]
[Calls: write_spec with 8-bit ports...]
[Generates RTL in workspace/counter_project/]
```

**User:**
```
Now switch to UART and design the transmitter.
```

**Claude:**
```
[Calls: set_active_session("uart_project")]
✅ Switched to uart_project

[Calls: write_spec for UART...]
[Generates RTL in workspace/uart_project/]
```

---

### Example 3: Resume Previous Work

**User:**
```
[Days later, loads RTL Design Workflow prompt]

List my previous sessions
```

**Claude:**
```
[Calls: list_sessions_tool]

You have 3 sessions:
1. counter_project (created Feb 5, 1,250 tokens)
2. uart_project (created Feb 5, 3,400 tokens) ← ACTIVE
3. old_test (created Feb 3, 450 tokens)
```

**User:**
```
Switch to counter_project and add a reset synchronizer
```

**Claude:**
```
[Calls: set_active_session("counter_project")]
✅ Switched to counter_project

[Calls: read_file("counter_4bit.v") to see existing code]
[Calls: edit_file_tool to add synchronizer]
✅ Updated counter_4bit.v with reset synchronizer
```

---

## Best Practices

### 1. Use Descriptive Session Names
✅ Good: `uart_9600_baud`, `fifo_async_16x8`, `cpu_alu_module`  
❌ Bad: `test1`, `design`, `thing`

### 2. One Design Per Session
Each session should contain a **single cohesive design** (may have multiple files, but one top-level module).

### 3. Check Active Session
Before starting work, verify you're in the right session:
```
What's my current session?
[Claude calls: get_current_session]
```

### 4. Clean Up Old Sessions
Periodically delete experimental/failed sessions:
```
Delete the session 'failed_experiment'
[Claude calls: delete_session_tool]
```

### 5. Use Resources for Browsing
MCP clients can browse sessions as resources - use this to explore files without tool calls.

---

## Comparison: MCP vs FastAPI Sessions

| Feature | FastAPI Backend | MCP Server | Shared? |
|---------|----------------|------------|---------|
| **Session Creation** | REST API `/api/sessions` | `create_session_tool` | ✅ Same DB |
| **Workspace** | `workspace/{id}/` | `workspace/{id}/` | ✅ Same folder |
| **Metadata** | SQLite `state.db` | SQLite `state.db` | ✅ Same DB |
| **File Access** | REST endpoints | MCP resources + tools | ✅ Same files |
| **Session Switching** | Client-side (UI) | `set_active_session` | ✅ Both work |
| **Auto-creation** | Manual via UI | Auto on prompt load | Different UX |

---

## Troubleshooting

### Issue: "No active session"

**Cause:** Prompt not loaded or session not created

**Fix:**
```
Load the "RTL Design Workflow" prompt, or:
Create a session with create_session_tool
```

### Issue: "Session already exists"

**Cause:** Trying to create a session with duplicate name

**Fix:**
```
Use set_active_session to switch to it, or:
Choose a different session name
```

### Issue: Files not found in session

**Cause:** Tools might be using wrong workspace

**Fix:**
```
Check active session: get_current_session
Confirm workspace path matches
```

### Issue: Can't delete active session

**Cause:** Safety feature prevents deleting current workspace

**Fix:**
```
Switch to another session first:
set_active_session("different_session")
Then delete:
delete_session_tool("old_session")
```

---

## Summary

Session management in the MCP server provides:

✅ **Isolation** - Each design in its own workspace  
✅ **Organization** - Named sessions for clarity  
✅ **Flexibility** - Switch between projects easily  
✅ **Persistence** - Sessions saved across restarts  
✅ **Integration** - Shared with FastAPI backend  
✅ **Resources** - Browse via MCP protocol  

You now have **feature parity** with your Next.js frontend, plus the convenience of Claude's natural language interface! 🚀
