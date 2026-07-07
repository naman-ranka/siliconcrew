"""F2: MCP workspace sync is gated to MUTATING tools.

Every MCP tool call used to re-tar+upload the whole workspace to object storage
on exit (``session_request_scope``'s ``finally`` → ``provider.sync``), even for
read-only tools — the primary "codex tool calls are slow" cause. The fix threads
a ``sync`` flag through ``run_in_session``/``session_request_scope`` and the MCP
server passes ``sync=(name in MUTATING_TOOLS)``.

These tests pin the mechanism (read → no sync, write → sync) and the policy set
(every workspace-writing tool is in MUTATING_TOOLS, so gating never silently
drops a writer's output). They fail on pre-fix code: ``run_in_session`` had no
``sync`` kwarg, so ``sync=False`` raises ``TypeError``.
"""
import asyncio
import os

from src.platform_engines.request_scope import run_in_session
from src.api.tool_catalog import MUTATING_TOOLS


class _RecordingProvider:
    """Local workspace provider that also records every sync() call."""

    def __init__(self, base):
        self._base = base
        self.synced = []

    def workspace_for(self, session_id):
        ws = os.path.join(self._base, session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    def sync(self, session_id):
        self.synced.append(session_id)


def test_read_only_call_does_not_sync(tmp_path):
    """A read-only tool call (sync=False) must NOT trigger a workspace upload."""
    provider = _RecordingProvider(str(tmp_path))

    async def main():
        return await run_in_session(
            "sess_read", lambda _a: "ok", {}, user_id="u1",
            provider=provider, sync=False,
        )

    assert asyncio.run(main()) == "ok"
    assert provider.synced == []  # no upload for a read


def test_mutating_call_syncs(tmp_path):
    """A mutating tool call (sync=True, the default) uploads exactly once."""
    provider = _RecordingProvider(str(tmp_path))

    async def main():
        return await run_in_session(
            "sess_write", lambda _a: "ok", {}, user_id="u1",
            provider=provider,  # sync defaults to True
        )

    assert asyncio.run(main()) == "ok"
    assert provider.synced == ["sess_write"]  # uploaded once


def test_mcp_sync_decision_matches_mutating_set():
    """The MCP server's gate is exactly ``name in MUTATING_TOOLS`` — encode the
    read/write classification so a future writer added without MUTATING
    membership (→ silent data loss on hosted) trips this test.
    """
    writers = {
        "write_spec", "write_file", "apply_patch_tool", "edit_file_tool",
        "load_yaml_spec_file", "update_manifest",
        "simulation_tool", "run_isolated_simulation", "cocotb_tool", "sby_tool",
        "start_synthesis", "retry_pd",
        "save_metrics_tool", "generate_report_tool", "schematic_tool",
        "run_xls_flow", "run_dslx_interpreter", "compile_dslx_to_ir",
        "optimize_xls_ir", "codegen_xls", "benchmark_xls",
        "experimental_compile_cpp_to_ir",
    }
    # Pure reads (or reads whose only writes persist via an INDEPENDENT durable
    # channel — get_synthesis_status/wait_for_synthesis reconcile run_meta via
    # _persist_run_meta_durable → the run store, not the workspace tarball).
    readers = {
        "read_spec", "read_file", "list_files_tool", "get_manifest",
        "waveform_tool", "search_logs_tool", "linter_tool",
        "get_synthesis_status", "wait_for_synthesis", "get_synthesis_metrics",
        "read_stage_report", "get_route_drc_summary", "get_cts_summary",
        "get_congestion_summary", "compare_pd_runs",
    }

    missing = writers - MUTATING_TOOLS
    assert not missing, f"writers missing from MUTATING_TOOLS (would lose writes): {missing}"

    misclassified = readers & MUTATING_TOOLS
    assert not misclassified, f"readers wrongly in MUTATING_TOOLS (needless upload): {misclassified}"
