#!/bin/bash
# Call any SiliconCrew MCP tool over the committed .mcp.json HTTP endpoint,
# without needing the native mcp__siliconcrew__* tools loaded in the session.
# Requires SILICONCREW_MCP_TOKEN in the environment (same var .mcp.json uses).
#
# Usage: mcp_call.sh <tool_name> ['<json-args>']
#   e.g. mcp_call.sh list_sessions_tool
#        mcp_call.sh create_session_tool '{"session_id":"demo"}'
#        mcp_call.sh linter_tool '{"verilog_files":"foo.v"}'
set -euo pipefail
URL="https://siliconcrew-backend-psp2dkllmq-uc.a.run.app/mcp"
TOOL="${1:?usage: mcp_call.sh <tool_name> [json-args]}"
ARGS="${2:-{}}"

body=$(mktemp)
trap 'rm -f "$body"' EXIT
# Write the JSON-RPC request to a file and send with --data-binary so the shell
# never appends a stray byte (a plain -d/--data-raw of the var can corrupt it).
printf '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"%s","arguments":%s}}' "$TOOL" "$ARGS" > "$body"

raw=""
for attempt in 1 2 3; do
  raw=$(curl -s -m90 \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Authorization: Bearer ${SILICONCREW_MCP_TOKEN:?SILICONCREW_MCP_TOKEN not set}" \
    -X POST "$URL" --data-binary @"$body") && [ -n "$raw" ] && break
  sleep 2
done

printf '%s' "$raw" | python3 -c "
import sys, json
raw = sys.stdin.read()
lines = [l[6:] for l in raw.splitlines() if l.startswith('data: ')]
if not lines:
    print('EMPTY / non-SSE response:'); print(raw[:800]); sys.exit(1)
d = json.loads(lines[-1])
if 'error' in d:
    print('ERROR:', json.dumps(d['error'])); sys.exit(1)
r = d.get('result', {})
print('isError:', r.get('isError'))
for c in r.get('content', []):
    print(c.get('text', json.dumps(c)))
"
