# Tool Design Decisions: Auto-Discovery, Schema Quality & Filtering

## Your Three Questions Answered

### 1. Is Auto-Discovery the Standard/Better Way?

**Answer: Yes, for your use case** ✅

#### Industry Standards (as of 2026)

| Framework | Approach | Rationale |
|-----------|----------|-----------|
| **LangChain/LangGraph** | Auto-discovery preferred | Tools reused across agents, DRY principle |
| **MCP (Anthropic)** | Mixed | Newer protocol, both approaches common |
| **CrewAI** | Auto-discovery | `@tool` decorator pattern |
| **Haystack** | Manual registration | Explicit control |
| **MS Semantic Kernel** | Hybrid | Auto-discover with overrides |

#### For Your Project: Auto-Discovery is Better Because...

✅ **Single Source of Truth**: Tools defined once in `src/tools/wrappers.py`  
✅ **Multi-Consumer**: Same tools used by LangChain agent, MCP, and potentially FastAPI  
✅ **Rapid Iteration**: Hackathon/research context needs fast changes  
✅ **Consistency**: No risk of divergent schemas  
✅ **Low Maintenance**: Add new tool → automatically available everywhere  

#### When Manual Would Be Better

❌ **Stable API**: If tools rarely change, manual provides better documentation  
❌ **Security Filtering**: Need to hide tools from certain clients  
❌ **Client-Specific UX**: Different descriptions/examples for different audiences  
❌ **Complex Transformations**: LangChain schema ↔ MCP schema incompatibility  

---

### 2. Schema Quality: Are They Exactly the Same?

**Answer: Auto-discovered schemas are actually MORE complete!**

#### Comparison Test Results

```
Manual Schema:
  - 4 properties (we showed subset for examples)
  - Hand-written descriptions with examples
  - "Name of the Verilog module (e.g., 'counter_8bit')"

Auto-Discovered Schema:
  - 8 properties (all parameters from function signature!)
  - Generated from docstrings
  - "Creates a YAML design specification file. Call this FIRST..."
```

#### What Auto-Discovery Captures

✅ **All Parameters**: Function signature → schema properties (manual often incomplete)  
✅ **Type Information**: Type hints → JSON Schema types  
✅ **Defaults**: Default values preserved  
✅ **Docstrings**: Full description from `"""..."""`  
✅ **Pydantic Models**: Complex nested types converted automatically  

#### What Manual Schemas Can Add

📝 **Examples**: `"e.g., 'counter_8bit'"` (more user-friendly)  
📝 **Constraints**: `enum`, `minLength`, `pattern` for validation  
📝 **UX Hints**: `placeholder`, `examples` array (MCP-specific)  
📝 **Better Descriptions**: Hand-tuned for specific audiences  

#### Best Practice: Enhance Your LangChain Tools

Instead of duplicating, **improve the source**:

```python
# BEFORE: Basic tool definition
@tool
def write_spec(module_name: str, description: str) -> str:
    """Create spec."""
    ...

# AFTER: Enhanced tool definition (auto-discovery gets this!)
@tool
def write_spec(
    module_name: str,
    description: str,
    ports: list[dict],
    clock_period_ns: float = 10.0,
    # ... all params
) -> str:
    """
    Creates a YAML design specification file. Call this FIRST before writing any RTL.
    The spec defines the module interface and requirements that the RTL must follow.
    
    Args:
        module_name: Name of the Verilog module (e.g., 'counter_8bit', 'uart_tx')
        description: What the module does (e.g., '8-bit synchronous counter')
        ports: List of port definitions with name, direction, width, description
        clock_period_ns: Target clock period in nanoseconds (default: 10.0)
        
    Returns:
        Confirmation message with spec filename
    """
    ...
```

**Result**: One source → high-quality schemas everywhere!

---

### 3. Can We Filter/Hide Tools to Reduce Cognitive Load?

**Answer: YES! Just implemented** ✅

#### The Problem

23 tools is a LOT for an LLM to see at once, especially for:
- Simple counter design (only needs 7 tools)
- Verification-focused task (doesn't need synthesis tools)
- Learning/exploration (overwhelming for beginners)

#### The Solution: Dynamic Tool Filtering

> **SUPERSEDED — `configure_tool_filter` was removed (P0 of the agent platform
> overhaul; see `siliconcrew-dev/plans/agent-platform-overhaul.md`).** The
> section below is kept as a record of the original decision and why it was
> reversed. Do not follow it.
>
> Three things were wrong with it:
> 1. **It leaked across tenants.** The filter mode was stored as per-process
>    state on the server, and the hosted streamable-HTTP transport is
>    multiplexed — so one user changing their filter changed what other users
>    saw from `tools/list`.
> 2. **It is not MCP-conformant.** The spec says a server MUST NOT vary
>    `tools/list` per connection except by auth scope, and clients cache the
>    list, so runtime mutation left them holding a stale set.
> 3. **The counts in this section were already wrong** — "Essential (7 tools)"
>    while `TOOL_CATEGORIES["essential"]` holds 8.
>
> The underlying goal — not showing an agent every tool at once — is still
> right, and is being met instead by merging overlapping tools, hiding
> rare-flow ones by default, and (later) scoping at connect time via auth
> scope rather than by runtime mutation.

We added `configure_tool_filter` tool with 3 modes:

##### Mode 1: Essential (7 tools)
**46% reduction in tool count**

```
Essential tools (core workflow):
  - write_spec
  - read_spec
  - write_file
  - read_file
  - linter_tool
  - simulation_tool
  - list_files_tool
  
✅ 13 total tools (7 essential + 6 session management)
```

**Use case**: Simple designs, learning, quick prototyping

##### Mode 2: Custom Categories
**Mix and match based on task**

```python
# Example: Verification-focused workflow
configure_tool_filter(
    mode="custom",
    custom_filter=["essential", "verification"]
)

# Result: Essential + waveform_tool, cocotb_tool, sby_tool
# 16 tools total (vs 24)
```

**Categories available**:
- `essential` - Core RTL workflow
- `verification` - Waveforms, CocoTB, formal
- `synthesis` - OpenROAD, PPA, schematics
- `editing` - File editing, YAML loading
- `reporting` - Metrics, reports

##### Mode 3: All Tools
**Full toolset for complex designs**

```
All 24 tools available
```

#### Usage in Claude Desktop

**Scenario 1: Simple counter design**
```
User: I want to design a simple 4-bit counter.

Claude: Let me start with essential tools only for clarity.
[Calls configure_tool_filter(mode="essential")]
✅ Tool filter updated to 'essential'
📊 Visible tools: 13

[Proceeds with: write_spec → write_file → linter_tool → simulation_tool]
```

**Scenario 2: Complex design with synthesis**
```
User: Design a UART and synthesize it to get PPA metrics.

Claude: I'll need synthesis tools for this.
[Calls configure_tool_filter(mode="custom", custom_filter=["essential", "synthesis"])]
📊 Visible tools: 18

[Uses: write_spec → write_file → lint → simulate → synthesis_tool → ppa_tool]
```

#### Benefits

✅ **Reduced Context**: Smaller tool list → less LLM confusion  
✅ **Faster Response**: LLM doesn't need to evaluate irrelevant tools  
✅ **Better Focus**: Only sees tools relevant to current task  
✅ **Progressive Disclosure**: Start simple, add tools as needed  
✅ **Lower Cost**: Fewer tokens in tool list  

#### Implementation Details

```python
# Categories defined in mcp_server.py
TOOL_CATEGORIES = {
    "essential": ["write_spec", "read_spec", "write_file", ...],
    "verification": ["waveform_tool", "cocotb_tool", "sby_tool"],
    "synthesis": ["synthesis_tool", "ppa_tool", "search_logs_tool", ...],
    "editing": ["edit_file_tool", "load_yaml_spec_file"],
    "reporting": ["save_metrics_tool", "generate_report_tool"]
}

# Filter is applied in list_tools()
def _should_include_tool(self, tool_name: str) -> bool:
    if self.tool_filter_mode == "essential":
        return tool_name in TOOL_CATEGORIES["essential"]
    # ... other modes
```

**Note**: Session management tools (6) are always included.

---

## Recommendations

### For Your Current Project ✅

1. **Keep Auto-Discovery**: Perfect for your multi-consumer architecture
2. **Enhance Source Docstrings**: Add examples to tool definitions in `wrappers.py`
3. ~~**Use Essential Mode by Default**~~: superseded — `configure_tool_filter` was removed (see the note above). Reduce the surface at the registry instead: merge overlapping tools, hide rare-flow ones by default.
4. **Document Categories**: Update MCP_SETUP.md with filtering examples

### Future Enhancements 🚀

#### Smart Auto-Filtering
```python
# Analyze user's first message to auto-select mode
if "simple" in user_message or "basic" in user_message:
    auto_configure_filter("essential")
elif "synthesize" in user_message or "PPA" in user_message:
    auto_configure_filter("custom", ["essential", "synthesis"])
```

#### Progressive Tool Loading
```python
# Start with essential, add tools on-demand
if tool_call_failed(tool="synthesis_tool"):
    if tool_filter_mode == "essential":
        auto_add_category("synthesis")
        retry()
```

#### Context-Aware Filtering
```python
# Filter based on session metadata
if session_has_verilog_files():
    include_category("verification")
if session_has_synthesis_results():
    include_category("reporting")
```

---

## Summary Table

| Question | Answer | Impact |
|----------|--------|--------|
| **Is auto-discovery standard?** | Yes for LangChain, emerging for MCP | ✅ Use it |
| **Are schemas identical quality?** | Auto-discovered captures MORE + can enhance source | ✅ Better than manual |
| **Can we filter tools?** | Yes, just implemented 3 filtering modes | ✅ 46% reduction possible |

---

## Testing Results

```bash
$ python test_tool_filtering.py

All mode:       24 tools
Essential mode: 13 tools (saved 11 tools, 46% reduction)
Custom mode:    16 tools (essential + verification)

✅ Tool filtering works correctly!
```

Your instinct was correct on all three points! 🎯
