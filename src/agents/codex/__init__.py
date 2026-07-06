"""Codex runtime — a removable agent-runtime extension.

Everything Codex-specific lives under this package. The shared/LangChain path
never imports it (enforced by tests/test_runtime_registry.py's import-graph
check); removing this directory + dropping the codex-owned tables removes Codex
cleanly. See plans/codex-runtime-extension.md and plans/codex-engine-reference.md.
"""
