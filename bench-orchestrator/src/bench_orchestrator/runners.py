from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import shutil
import subprocess
import sys
import threading
import time


@dataclass
class RunnerResult:
    status: str
    exit_code: int
    events_path: Path
    last_message_path: Path | None = None
    stdout_path: Path | None = None
    stderr_path: Path | None = None
    note: str = ""


class BaseRunner:
    def run(self, prompt: str, run_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        raise NotImplementedError

    def resume(self, prompt: str, run_dir: Path, continuation_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        raise NotImplementedError


class FakeRunner(BaseRunner):
    def run(self, prompt: str, run_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        events = run_dir / "agent_events.jsonl"
        last = run_dir / "agent_last.txt"
        workspace = run_dir / "raw" / "fake_sc_workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        _write_jsonl(events, [
            {"type": "thread.started", "thread_id": "fake-thread"},
            {"type": "item.completed", "item": {"type": "mcp_tool_call", "tool": "create_session_tool", "status": "completed"}},
            {"type": "item.completed", "item": {"type": "mcp_tool_call", "tool": "simulation_tool", "status": "completed"}},
        ])
        last.write_text("FAKE RUN COMPLETE\nRTL sim: pass\n", encoding="utf-8", newline="\n")
        _write_fake_workspace(workspace)
        return RunnerResult(status="completed", exit_code=0, events_path=events, last_message_path=last, note="fake runner")

    def resume(self, prompt: str, run_dir: Path, continuation_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        continuation_dir.mkdir(parents=True, exist_ok=True)
        events = continuation_dir / "agent_events.jsonl"
        last = continuation_dir / "agent_last.txt"
        workspace = run_dir / "raw" / "fake_sc_workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        _write_jsonl(events, [
            {"type": "thread.started", "thread_id": "fake-thread-resume"},
            {"type": "item.completed", "item": {"type": "mcp_tool_call", "tool": "set_active_session", "status": "completed"}},
            {"type": "item.completed", "item": {"type": "mcp_tool_call", "tool": "get_synthesis_metrics", "status": "completed"}},
        ])
        last.write_text("FAKE RESUME COMPLETE\nFollow-up applied.\n", encoding="utf-8", newline="\n")
        _append_fake_resume_workspace(workspace)
        return RunnerResult(status="completed", exit_code=0, events_path=events, last_message_path=last, note="fake resume")


class CodexRunner(BaseRunner):
    def run(self, prompt: str, run_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        codex = shutil.which("codex.cmd") or shutil.which("codex")
        if not codex:
            raise RuntimeError("codex CLI not found in PATH.")
        events = run_dir / "agent_events.jsonl"
        last = run_dir / "agent_last.txt"
        stdout = run_dir / "raw" / "agent_stdout.log"
        stderr = run_dir / "raw" / "agent_stderr.log"
        cmd = [
            codex,
            "-C", str(Path.cwd()),
            "exec",
            "--model", model,
            _codex_auth_flag(),
            "--dangerously-bypass-hook-trust",
            "--json",
            "--output-last-message", str(last),
            "-"
        ]
        started = time.time()
        exit_code = _run_and_stream(
            cmd=cmd,
            prompt_stdin=prompt,
            stdout_path=stdout,
            stderr_path=stderr,
            extra_stdout_path=events,
            timeout_sec=timeout_sec,
        )
        status = "completed" if exit_code == 0 else "failed"
        return RunnerResult(
            status=status,
            exit_code=exit_code,
            events_path=events,
            last_message_path=last,
            stdout_path=stdout,
            stderr_path=stderr,
            note=f"elapsed_sec={time.time() - started:.1f}"
        )

    def resume(self, prompt: str, run_dir: Path, continuation_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        codex = shutil.which("codex.cmd") or shutil.which("codex")
        if not codex:
            raise RuntimeError("codex CLI not found in PATH.")
        continuation_dir.mkdir(parents=True, exist_ok=True)
        events = continuation_dir / "agent_events.jsonl"
        last = continuation_dir / "agent_last.txt"
        stdout = continuation_dir / "agent_stdout.log"
        stderr = continuation_dir / "agent_stderr.log"
        cmd = [
            codex,
            "-C", str(Path.cwd()),
            "exec",
            "resume",
            "--last",
            "--model", model,
            _codex_auth_flag(),
            "--dangerously-bypass-hook-trust",
            "--json",
            "--output-last-message", str(last),
            "-"
        ]
        started = time.time()
        exit_code = _run_and_stream(
            cmd=cmd,
            prompt_stdin=prompt,
            stdout_path=stdout,
            stderr_path=stderr,
            extra_stdout_path=events,
            timeout_sec=timeout_sec,
        )
        status = "completed" if exit_code == 0 else "failed"
        return RunnerResult(
            status=status,
            exit_code=exit_code,
            events_path=events,
            last_message_path=last,
            stdout_path=stdout,
            stderr_path=stderr,
            note=f"elapsed_sec={time.time() - started:.1f}"
        )


class ClaudeRunner(BaseRunner):
    def run(self, prompt: str, run_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        claude = _require_cli("claude")
        cmd = [claude, "-p", "--model", model, "--dangerously-skip-permissions", "--add-dir", str(Path.cwd())]
        return _run_text_agent(cmd, prompt, run_dir, "claude", timeout_sec)

    def resume(self, prompt: str, run_dir: Path, continuation_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        claude = _require_cli("claude")
        cmd = [claude, "-p", "--continue", "--model", model, "--dangerously-skip-permissions", "--add-dir", str(Path.cwd())]
        return _run_text_agent(cmd, prompt, continuation_dir, "claude_resume", timeout_sec)


class AntigravityRunner(BaseRunner):
    def run(self, prompt: str, run_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        agy = _require_cli("agy")
        cmd = [agy, "--print", "--dangerously-skip-permissions", "--add-dir", str(Path.cwd()), prompt]
        return _run_text_agent(cmd, None, run_dir, "antigravity", timeout_sec)

    def resume(self, prompt: str, run_dir: Path, continuation_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        agy = _require_cli("agy")
        cmd = [agy, "--print", "--continue", "--dangerously-skip-permissions", "--add-dir", str(Path.cwd()), prompt]
        return _run_text_agent(cmd, None, continuation_dir, "antigravity_resume", timeout_sec)


def get_runner(name: str) -> BaseRunner:
    if name == "fake":
        return FakeRunner()
    if name == "codex":
        return CodexRunner()
    if name == "claude":
        return ClaudeRunner()
    if name == "antigravity":
        return AntigravityRunner()
    raise ValueError(f"Unsupported runner: {name}")


def preflight(agent: str, mcp_server: str) -> int:
    if agent == "fake":
        print(f"preflight: agent '{agent}' has no external CLI checks")
        return 0
    if agent == "claude":
        return _preflight_claude(mcp_server)
    if agent == "antigravity":
        return _preflight_antigravity(mcp_server)
    codex = shutil.which("codex.cmd") or shutil.which("codex")
    if not codex:
        print("codex CLI not found in PATH", file=sys.stderr)
        return 1
    proc = subprocess.run([codex, "mcp", "get", mcp_server], encoding="utf-8", capture_output=True)
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr, file=sys.stderr)
        return proc.returncode
    print(f"codex CLI OK: {codex}")
    print(f"MCP server OK: {mcp_server}")
    return 0


def _stream_reader(pipe, *out_files):
    try:
        for line in pipe:
            for f in out_files:
                f.write(line)
                f.flush()
    except Exception:
        pass


def _run_and_stream(
    cmd: list[str],
    prompt_stdin: str | None,
    stdout_path: Path,
    stderr_path: Path,
    extra_stdout_path: Path | None,
    timeout_sec: int,
) -> int:
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    if extra_stdout_path:
        extra_stdout_path.parent.mkdir(parents=True, exist_ok=True)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if prompt_stdin is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        bufsize=1,
        cwd=Path.cwd(),
    )

    if prompt_stdin is not None:
        try:
            proc.stdin.write(prompt_stdin)
            proc.stdin.close()
        except Exception:
            pass

    with open(stdout_path, "w", encoding="utf-8", newline="\n") as f_out, \
         open(stderr_path, "w", encoding="utf-8", newline="\n") as f_err:
        
        stdout_files = [f_out]
        f_extra = None
        if extra_stdout_path:
            f_extra = open(extra_stdout_path, "w", encoding="utf-8", newline="\n")
            stdout_files.append(f_extra)

        try:
            t_out = threading.Thread(target=_stream_reader, args=(proc.stdout, *stdout_files))
            t_err = threading.Thread(target=_stream_reader, args=(proc.stderr, f_err))
            
            t_out.start()
            t_err.start()
            
            try:
                exit_code = proc.wait(timeout=timeout_sec)
            except subprocess.TimeoutExpired:
                proc.kill()
                exit_code = proc.wait()
            
            t_out.join()
            t_err.join()
        finally:
            if f_extra:
                f_extra.close()

    return exit_code


def _run_text_agent(cmd: list[str], prompt_stdin: str | None, out_dir: Path, event_name: str, timeout_sec: int) -> RunnerResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    events = out_dir / "agent_events.jsonl"
    last = out_dir / "agent_last.txt"
    stdout = raw / "agent_stdout.log"
    stderr = raw / "agent_stderr.log"
    started = time.time()
    exit_code = _run_and_stream(
        cmd=cmd,
        prompt_stdin=prompt_stdin,
        stdout_path=stdout,
        stderr_path=stderr,
        extra_stdout_path=None,
        timeout_sec=timeout_sec,
    )
    if stdout.exists():
        try:
            content = stdout.read_text(encoding="utf-8")
            last.write_text(content[-20000:], encoding="utf-8", newline="\n")
        except Exception:
            pass
    _write_jsonl(events, [
        {"type": "thread.started", "thread_id": f"{event_name}-{int(started)}"},
        {"type": "agent.completed" if exit_code == 0 else "agent.failed", "agent": event_name, "exit_code": exit_code},
    ])
    return RunnerResult(
        status="completed" if exit_code == 0 else "failed",
        exit_code=exit_code,
        events_path=events,
        last_message_path=last,
        stdout_path=stdout,
        stderr_path=stderr,
        note=f"elapsed_sec={time.time() - started:.1f}",
    )


def _require_cli(name: str) -> str:
    exe = shutil.which(f"{name}.cmd") or shutil.which(name)
    if not exe:
        raise RuntimeError(f"{name} CLI not found in PATH.")
    return exe


def _codex_auth_flag() -> str:
    # Matches codex-automate/run_codex_two_step_batch.ps1 -AllowBypass mode.
    # Recent Codex CLI builds may still ask for MCP tool approval under --full-auto.
    return "--dangerously-bypass-approvals-and-sandbox"


def _mcp_command() -> tuple[str, list[str]]:
    repo = Path.cwd()
    py = repo / ".venv" / "Scripts" / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    server = repo / "mcp_server.py"
    return str(py), [str(server), "--codex-tools"]


def _preflight_claude(mcp_server: str) -> int:
    claude = shutil.which("claude.cmd") or shutil.which("claude")
    if not claude:
        print("claude CLI not found in PATH", file=sys.stderr)
        return 1
    get_proc = subprocess.run([claude, "mcp", "get", mcp_server], encoding="utf-8", capture_output=True)
    if get_proc.returncode != 0:
        command, args = _mcp_command()
        add_proc = subprocess.run(
            [claude, "mcp", "add", "-s", "user", mcp_server, "--", command, *args],
            encoding="utf-8",
            capture_output=True,
        )
        if add_proc.returncode != 0:
            print(add_proc.stdout)
            print(add_proc.stderr, file=sys.stderr)
            return add_proc.returncode
    print(f"claude CLI OK: {claude}")
    print(f"MCP server OK: {mcp_server}")
    return 0


def _preflight_antigravity(mcp_server: str) -> int:
    agy = shutil.which("agy.cmd") or shutil.which("agy")
    if not agy:
        print("agy CLI not found in PATH", file=sys.stderr)
        return 1
    config = Path.home() / ".gemini" / "antigravity-cli" / "mcp_config.json"
    command, args = _mcp_command()
    ensure_antigravity_mcp_config(config, mcp_server, command, args)
    print(f"agy CLI OK: {agy}")
    print(f"MCP server OK: {mcp_server}")
    return 0


def ensure_antigravity_mcp_config(config_path: Path, name: str, command: str, args: list[str]) -> dict:
    data = {}
    if config_path.exists():
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    servers = data.setdefault("mcpServers", {})
    current = servers.get(name)
    desired = {"command": command, "args": args}
    if current != desired:
        servers[name] = desired
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")
    return data


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")


def _write_fake_workspace(workspace: Path) -> None:
    _write_jsonl(workspace / "attempt_events.jsonl", [
        {"event_type": "tool_call", "tool": "write_file", "status": None, "arguments": {"filename": "demo.v"}},
        {"event_type": "tool_result", "tool": "write_file", "status": "success", "result": "ok"},
        {"event_type": "tool_call", "tool": "simulation_tool", "arguments": {"mode": "rtl"}},
        {"event_type": "tool_result", "tool": "simulation_tool", "status": "success", "result": "RTL_SIM_PASS"},
    ])
    (workspace / "attempt_log.json").write_text(json.dumps({"attempt_count": 1, "attempts": [{"rtl_sim": "pass", "synth_status": "completed"}]}, indent=2), encoding="utf-8")
    (workspace / "demo.v").write_text("module demo(input a, output y); assign y = a; endmodule\n", encoding="utf-8")
    synth = workspace / "synth_runs" / "synth_0001"
    synth.mkdir(parents=True, exist_ok=True)
    (workspace / "synth_runs" / "LATEST").write_text("synth_0001", encoding="utf-8")
    (synth / "run_meta.json").write_text(json.dumps({
        "run_id": "synth_0001",
        "job_id": "job_fake",
        "status": "completed",
        "top_module": "demo",
        "auto_checks": {"constraints": "pass", "signoff": "pass", "equiv": "skip"},
        "summary_metrics": {"area_um2": 1.0, "cell_count": 1, "wns_ns": 0.1, "tns_ns": 0.0, "power_uw": 2.0},
    }, indent=2), encoding="utf-8")


def _append_fake_resume_workspace(workspace: Path) -> None:
    events = workspace / "attempt_events.jsonl"
    with events.open("a", encoding="utf-8", newline="\n") as f:
        for row in [
            {"event_type": "tool_call", "tool": "set_active_session", "arguments": {}},
            {"event_type": "tool_result", "tool": "set_active_session", "status": "success"},
            {"event_type": "tool_call", "tool": "get_synthesis_metrics", "arguments": {}},
            {"event_type": "tool_result", "tool": "get_synthesis_metrics", "status": "success"},
        ]:
            f.write(json.dumps(row) + "\n")
    demo = workspace / "demo.v"
    demo.write_text((demo.read_text(encoding="utf-8") if demo.exists() else "") + "// fake resume touched source\n", encoding="utf-8", newline="\n")
    synth = workspace / "synth_runs" / "synth_0002"
    synth.mkdir(parents=True, exist_ok=True)
    (workspace / "synth_runs" / "LATEST").write_text("synth_0002", encoding="utf-8")
    (synth / "run_meta.json").write_text(json.dumps({
        "run_id": "synth_0002",
        "job_id": "job_fake_resume",
        "status": "completed",
        "top_module": "demo",
        "auto_checks": {"constraints": "pass", "signoff": "pass", "equiv": "skip"},
        "summary_metrics": {"area_um2": 1.1, "cell_count": 2, "wns_ns": 0.2, "tns_ns": 0.0, "power_uw": 1.5},
    }, indent=2), encoding="utf-8")
