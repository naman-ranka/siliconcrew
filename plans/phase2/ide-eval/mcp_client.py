#!/usr/bin/env python3
"""Reliable SiliconCrew MCP client for driving the DEPLOYED backend as the
user's own AI app would. Builds the JSON-RPC body in Python (safe for Verilog
content with quotes/newlines) and sends via curl (which correctly traverses the
agent HTTPS proxy). Parses the SSE result and prints the tool's text output.

Usage:
  python mcp_client.py <tool_name> '<json-args>'
  python mcp_client.py write_file @args.json      # read args from a JSON file
Examples:
  python mcp_client.py create_session_tool '{"session_name":"adder8_mcp"}'
  python mcp_client.py linter_tool '{"verilog_files":"adder8.v"}'
"""
import json, os, subprocess, sys, tempfile

URL = "https://siliconcrew-backend-psp2dkllmq-uc.a.run.app/mcp"
TOKEN = os.environ.get("SILICONCREW_MCP_TOKEN")
if not TOKEN:
    sys.exit("SILICONCREW_MCP_TOKEN not set")

tool = sys.argv[1]
arg_in = sys.argv[2] if len(sys.argv) > 2 else "{}"
if arg_in.startswith("@"):
    with open(arg_in[1:]) as f:
        args = json.load(f)
else:
    args = json.loads(arg_in)

body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": tool, "arguments": args}})
with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tf:
    tf.write(body)
    path = tf.name

try:
    out = subprocess.run(
        ["curl", "-s", "-m", "180",
         "-H", "Content-Type: application/json",
         "-H", "Accept: application/json, text/event-stream",
         "-H", f"Authorization: Bearer {TOKEN}",
         "-X", "POST", URL, "--data-binary", f"@{path}"],
        capture_output=True, text=True, timeout=200).stdout
finally:
    os.unlink(path)

data_lines = [l[6:] for l in out.splitlines() if l.startswith("data: ")]
if not data_lines:
    print("EMPTY / non-SSE response:\n" + out[:800]); sys.exit(1)
d = json.loads(data_lines[-1])
if "error" in d:
    print("ERROR:", json.dumps(d["error"])); sys.exit(1)
r = d.get("result", {})
if r.get("isError"):
    print("[tool isError=true]")
for c in r.get("content", []):
    print(c.get("text", json.dumps(c)))
