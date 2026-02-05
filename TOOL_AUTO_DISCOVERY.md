# Tool Auto-Discovery in MCP

## What Changed

The MCP server now uses **automatic tool discovery** instead of manually redefining all 18 tools.

### Before (Manual Duplication)
```python
async def list_tools(self):
    return [
        Tool(name="write_spec", description="...", inputSchema={...}),  # 50 lines
        Tool(name="read_spec", description="...", inputSchema={...}),   # 30 lines
        Tool(name="write_file", description="...", inputSchema={...}),  # 25 lines
        # ... 18 tools = ~600 lines of duplicated schemas
    ]
```

### After (Auto-Discovery)
```python
async def list_tools(self):
    mcp_tools = []
    
    # Session tools (MCP-specific, manually defined)
    mcp_tools.extend([...])  # 5 tools, ~40 lines
    
    # AUTO-DISCOVER all LangChain tools
    for langchain_tool in architect_tools:
        mcp_tool = langchain_to_mcp_schema(langchain_tool)
        mcp_tools.append(mcp_tool)
    
    return mcp_tools
```

**Result**: ~600 lines → ~80 lines (88% reduction!)

---

## How Auto-Discovery Works

### Helper Function
```python
def langchain_to_mcp_schema(langchain_tool) -> Tool:
    """
    Automatically convert a LangChain tool to MCP Tool format.
    Extracts schema from the LangChain @tool decorator.
    """
    # Get input schema from Pydantic model or function signature
    input_schema = {}
    
    if hasattr(langchain_tool, 'args_schema') and langchain_tool.args_schema:
        # Pydantic model - convert to JSON Schema
        input_schema = langchain_tool.args_schema.model_json_schema()
    
    return Tool(
        name=langchain_tool.name,
        description=langchain_tool.description,
        inputSchema=input_schema
    )
```

### Example: write_spec Tool

**Defined once in** [src/tools/wrappers.py](src/tools/wrappers.py):
```python
@tool
def write_spec(
    module_name: str,
    description: str,
    ports: list[dict],
    clock_period_ns: float = 10.0,
    # ... other params
) -> str:
    """
    Creates a YAML design specification file. Call this FIRST before writing any RTL.
    
    Args:
        module_name: Name of the Verilog module (e.g., 'counter_8bit')
        description: What the module does
        ...
    """
    # Implementation
```

**Automatically exposed to MCP** with:
- ✅ Same name: `write_spec`
- ✅ Same description from docstring
- ✅ Schema auto-generated from function signature
- ✅ Parameter types and defaults preserved

---

## Benefits

### 1. Single Source of Truth ✅
```
src/tools/wrappers.py
   ↓
   ├─→ LangChain (for Architect agent)
   ├─→ MCP (for Claude Desktop)
   └─→ FastAPI (could expose as REST endpoints)

Change once → works everywhere!
```

### 2. No Duplication ✅
**Before:**
- Define tool in `wrappers.py` (LangChain format)
- Redefine in `mcp_server.py` (MCP format)
- Update both when changing parameters

**After:**
- Define tool once in `wrappers.py`
- Auto-exposed to MCP
- Change once, done!

### 3. Less Maintenance ✅
**Adding a new tool:**

**Before:**
1. Create tool in `src/tools/wrappers.py`
2. Add to `architect_tools` list
3. Manually create MCP schema in `mcp_server.py`
4. Add to tool_map for execution
5. Test both LangChain and MCP

**After:**
1. Create tool in `src/tools/wrappers.py`
2. Add to `architect_tools` list
3. Done! Automatically available in MCP

### 4. Consistency ✅
Same descriptions, same parameter names, same defaults across all interfaces.

---

## When Auto-Discovery Might Be "Bad"

There are legitimate cases where you might NOT want auto-discovery:

### Case 1: MCP-Specific Customization
If you need different descriptions/schemas for MCP clients:

```python
# LangChain version (for Architect agent)
@tool
def synthesis_tool(...):
    """Run OpenROAD synthesis."""
    
# MCP version might want MORE detail for human users
Tool(
    name="synthesis_tool",
    description="""Run logic synthesis using OpenROAD Flow Scripts.
    
    This executes the full RTL-to-GDS flow including:
    - Logic synthesis (Yosys + ABC)
    - Floorplanning
    - Placement
    - Clock tree synthesis
    - Routing
    - GDSII generation
    
    Typical runtime: 30-120 seconds depending on design size.""",
    inputSchema={...}  # Maybe add examples
)
```

### Case 2: Security/Filtering
Only expose a subset of tools via MCP:

```python
# Don't auto-discover - manually choose which tools
safe_tools = ["write_spec", "read_spec", "linter_tool", "simulation_tool"]
return [langchain_to_mcp(t) for t in architect_tools if t.name in safe_tools]
```

### Case 3: Schema Incompatibility
LangChain and MCP have slightly different schema formats. Sometimes conversion isn't perfect:

```python
# LangChain might use complex Pydantic models
class PortSpec(BaseModel):
    name: str
    direction: Literal["input", "output", "inout"]
    width: Optional[Union[int, str]]  # Could be 8 or "WIDTH-1:0"

# MCP JSON Schema might need simplification
{
    "type": "object",
    "properties": {
        "width": {"type": ["integer", "string"]}  # Lost the parametric info
    }
}
```

### Case 4: MCP-Specific Parameters
Add MCP-only features like progress reporting:

```python
Tool(
    name="synthesis_tool",
    inputSchema={
        ...existing params...
        "report_progress": {  # MCP-specific
            "type": "boolean",
            "description": "Send progress notifications every 10 seconds"
        }
    }
)
```

---

## Best Practices

### When to Use Auto-Discovery ✅
- Tools are primarily defined in code (LangChain, functions, etc.)
- Same interface needed across multiple consumers
- Rapid prototyping / iteration speed matters
- **Your current use case!**

### When to Use Manual Schemas ❌
- Need significant customization per client type
- Security-sensitive tool filtering
- Complex schema transformations required
- Documentation/examples more important than DRY

---

## Hybrid Approach (Best of Both Worlds)

You can also mix both approaches:

```python
async def list_tools(self):
    mcp_tools = []
    
    # 1. Session tools - MCP-specific, manually defined
    mcp_tools.extend([
        Tool(name="create_session_tool", ...),
        Tool(name="list_sessions_tool", ...),
    ])
    
    # 2. Core workflow tools - auto-discovered
    core_tools = ["write_spec", "read_spec", "linter_tool", "simulation_tool"]
    for tool in architect_tools:
        if tool.name in core_tools:
            mcp_tools.append(langchain_to_mcp_schema(tool))
    
    # 3. Synthesis tool - manually override for better UX
    mcp_tools.append(Tool(
        name="synthesis_tool",
        description="...[detailed description for humans]...",
        inputSchema={...}  # Enhanced with examples
    ))
    
    return mcp_tools
```

---

## Comparison Table

| Aspect | Manual Definition | Auto-Discovery | Hybrid |
|--------|-------------------|----------------|--------|
| **Code Size** | ~600 lines | ~80 lines | ~150 lines |
| **Maintenance** | High (2x changes) | Low (1x change) | Medium |
| **Customization** | Full control | Limited | Selective |
| **Consistency** | Can diverge | Always in sync | Mostly in sync |
| **Schema Quality** | Hand-tuned | Generated | Mix |
| **Best For** | Stable APIs | Rapid dev | Production |

---

## Your Current Implementation

**Choice**: Auto-Discovery ✅

**Rationale**:
1. Your tools are already well-defined in `wrappers.py`
2. LangChain `@tool` decorator provides good schemas
3. You want consistency across FastAPI and MCP
4. Tools change frequently (hackathon iteration)
5. Low maintenance burden matters

**Only manually defined**: 5 session management tools (MCP-specific, no LangChain equivalent)

---

## Performance Impact

**Auto-discovery is done once at server startup:**

```python
# This runs ONCE when server starts
async def list_tools(self):
    for tool in architect_tools:  # Loop runs once
        mcp_tool = langchain_to_mcp_schema(tool)
```

**Not at call time:**
- Tool list is cached
- No runtime overhead
- Same performance as manual definition

---

## Summary

**Auto-discovery is BETTER for your use case because:**

✅ **DRY Principle** - Define once, use everywhere  
✅ **Low Maintenance** - Add new tools without touching MCP code  
✅ **Consistency** - Same interface across all clients  
✅ **Rapid Iteration** - Matches your hackathon/research needs  

**Manual definition would be better if:**

❌ You needed radically different MCP schemas  
❌ Security filtering was critical  
❌ MCP-specific features were required  
❌ API was stable and rarely changed  

Your original question was spot-on - we were duplicating unnecessarily! 🎯
