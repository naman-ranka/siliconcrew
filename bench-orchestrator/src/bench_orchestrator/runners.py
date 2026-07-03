from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
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
    # Stream JSON events (like codex's --json). WITHOUT --output-format stream-json, `claude -p` buffers
    # all output to the very end and can appear to hang on long agentic runs (the overnight failure mode);
    # streaming makes it complete reliably AND traceable. --verbose is required for stream-json.
    _BASE = ["-p", "--dangerously-skip-permissions", "--output-format", "stream-json", "--verbose"]

    def run(self, prompt: str, run_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        claude = _require_cli("claude")
        cmd = [claude, *self._BASE, "--model", model, "--add-dir", str(Path.cwd())]
        return _run_json_stream_agent(cmd, prompt, run_dir, "claude", timeout_sec)

    def resume(self, prompt: str, run_dir: Path, continuation_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        claude = _require_cli("claude")
        cmd = [claude, *self._BASE, "--continue", "--model", model, "--add-dir", str(Path.cwd())]
        return _run_json_stream_agent(cmd, prompt, continuation_dir, "claude_resume", timeout_sec)


class AntigravityRunner(BaseRunner):
    # agy needs: --model (added v1.0.5; e.g. gemini-3.5-flash) and --print-timeout (default is only 5m,
    # too short for a design run). KNOWN AGY LIMITATIONS (upstream, not fixable here):
    #   * `--print`/-p drops stdout in non-TTY (issue #76) -> the response isn't captured on stdout;
    #     the agent's WORKSPACE (RTL written via rtl-codex) is the gradeable artifact, not stdout.
    #   * headless runs can stall waiting on the antigravity backend (esp. consumer accounts).
    # Preflight wires MCP into ~/.gemini/config/mcp_config.json + allow-lists mcp(rtl-codex/*).
    def run(self, prompt: str, run_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        agy = _require_cli("agy")
        cmd = [agy, "--print", "--dangerously-skip-permissions", "--model", model,
               "--print-timeout", f"{timeout_sec}s", "--add-dir", str(Path.cwd()), prompt]
        return _run_agy_transcript(cmd, run_dir, "antigravity", timeout_sec)

    def resume(self, prompt: str, run_dir: Path, continuation_dir: Path, model: str, timeout_sec: int) -> RunnerResult:
        agy = _require_cli("agy")
        cmd = [agy, "--print", "--continue", "--dangerously-skip-permissions", "--model", model,
               "--print-timeout", f"{timeout_sec}s", "--add-dir", str(Path.cwd()), prompt]
        return _run_agy_transcript(cmd, continuation_dir, "antigravity_resume", timeout_sec)


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


def _kill_tree(proc: subprocess.Popen) -> None:
    """Kill the agent process AND its descendants. On Windows the agent CLIs are .cmd wrappers:
    proc.kill() terminates only the cmd.exe shell, orphaning the node/python child, which keeps the
    stdout pipe open — so the reader threads block and the timeout is silently ineffective (observed:
    a 40-min timeout run streaming for 67+ min). taskkill /T takes out the whole tree."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.kill()


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

    # Default the Claude Code output-token cap high so long agentic runs don't die mid-flight on the
    # 32000 default ("response exceeded the 32000 output token maximum" — observed truncating hdbn_codec
    # BEFORE it could verify, a pure infra fail). Respect an explicit shell override; harmless for codex/agy.
    env = {**os.environ}
    env.setdefault("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "64000")
    # Claude Code on Windows needs git-bash; if the env var is unset it intermittently fails to start with
    # an empty transcript ("requires git-bash ... set CLAUDE_CODE_GIT_BASH_PATH") — observed killing a run
    # before the agent did anything. Pin it if the default install path exists (respect an explicit override).
    if not env.get("CLAUDE_CODE_GIT_BASH_PATH"):
        _bash = r"C:\Program Files\Git\bin\bash.exe"
        if os.path.exists(_bash):
            env["CLAUDE_CODE_GIT_BASH_PATH"] = _bash

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if prompt_stdin is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        bufsize=1,
        cwd=Path.cwd(),
        env=env,
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
                _kill_tree(proc)
                exit_code = proc.wait()
            
            t_out.join()
            t_err.join()
        finally:
            if f_extra:
                f_extra.close()

    return exit_code


def _run_json_stream_agent(cmd: list[str], prompt_stdin: str | None, out_dir: Path, event_name: str, timeout_sec: int) -> RunnerResult:
    """Run a CLI that emits stream-json on stdout (claude). The JSON stream IS the event log, so it goes
    straight to agent_events.jsonl (traceable like codex). The final `result` event becomes agent_last.txt."""
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
        extra_stdout_path=events,   # the stream-json lines ARE the events
        timeout_sec=timeout_sec,
    )
    # Pull the final assistant result text out of the stream for a clean last-message file.
    final_text = ""
    try:
        for line in events.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if obj.get("type") == "result" and obj.get("result"):
                final_text = str(obj["result"])
    except Exception:
        pass
    if not final_text and stdout.exists():
        final_text = stdout.read_text(encoding="utf-8")[-20000:]
    last.write_text(final_text, encoding="utf-8", newline="\n")
    return RunnerResult(
        status="completed" if exit_code == 0 else "failed",
        exit_code=exit_code,
        events_path=events,
        last_message_path=last,
        stdout_path=stdout,
        stderr_path=stderr,
        note=f"elapsed_sec={time.time() - started:.1f}",
    )


def _run_agy_transcript(cmd: list[str], out_dir: Path, event_name: str, timeout_sec: int) -> RunnerResult:
    """Run agy --print, then recover the result from agy's transcript JSONL — a workaround for agy's
    known bug (#76) of dropping stdout in non-TTY. Transcript lives at
    ~/.gemini/antigravity-cli/brain/<conv>/.system_generated/logs/transcript.jsonl ; the final answer is
    the last {source:MODEL, type:PLANNER_RESPONSE, status:DONE} entry. We copy it to agent_events.jsonl
    (traceable) and extract the final text to agent_last.txt."""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    events = out_dir / "agent_events.jsonl"
    last = out_dir / "agent_last.txt"
    stdout = raw / "agent_stdout.log"
    stderr = raw / "agent_stderr.log"
    started = time.time()
    exit_code = _run_and_stream(cmd, None, stdout, stderr, None, timeout_sec)

    brain = Path.home() / ".gemini" / "antigravity-cli" / "brain"
    transcripts = [p for p in brain.glob("*/.system_generated/logs/transcript.jsonl")
                   if p.exists() and p.stat().st_mtime >= started - 2]
    final_text = ""
    if transcripts:
        tr = max(transcripts, key=lambda p: p.stat().st_mtime)
        try:
            shutil.copyfile(tr, events)  # the JSONL transcript IS the event log
        except Exception:
            pass
        try:
            for line in tr.read_text(encoding="utf-8", errors="ignore").splitlines():
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if (obj.get("source") == "MODEL" and obj.get("type") == "PLANNER_RESPONSE"
                        and obj.get("status") == "DONE" and obj.get("content")):
                    final_text = obj["content"]   # keep the LAST one = the answer
        except Exception:
            pass
    if not events.exists():
        _write_jsonl(events, [
            {"type": "thread.started", "thread_id": f"{event_name}-{int(started)}"},
            {"type": "agent.completed" if exit_code == 0 else "agent.failed", "agent": event_name, "exit_code": exit_code},
        ])
    last.write_text(final_text, encoding="utf-8", newline="\n")
    return RunnerResult(
        status="completed" if exit_code == 0 else "failed",
        exit_code=exit_code,
        events_path=events,
        last_message_path=last,
        stdout_path=stdout,
        stderr_path=stderr,
        note=f"elapsed_sec={time.time() - started:.1f}; transcript={'recovered' if transcripts else 'none'}",
    )


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
    command, args = _mcp_command()
    # agy loads MCP servers from ~/.gemini/config/mcp_config.json (per the antigravity docs) — NOT the
    # antigravity-cli/ folder. Writing to the wrong place is why agy never saw rtl-codex.
    ensure_antigravity_mcp_config(Path.home() / ".gemini" / "config" / "mcp_config.json", mcp_server, command, args)
    # agy only exposes MCP tools that are permission-allow-listed; --dangerously-skip-permissions alone
    # does not expose a non-allow-listed server's tools to the model.
    ensure_antigravity_permission(Path.home() / ".gemini" / "antigravity-cli" / "settings.json", mcp_server)
    print(f"agy CLI OK: {agy}")
    print(f"MCP server OK: {mcp_server}")
    print("NOTE: agy --print has a known stdout bug (#76) and headless runs can stall on the backend; "
          "grade agy via the SC workspace artifacts, not stdout.")
    return 0


def ensure_antigravity_permission(settings_path: Path, name: str) -> None:
    """Add mcp(<name>/*) to agy's permission allow-list so the model can actually call the server's tools."""
    data = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    allow = data.setdefault("permissions", {}).setdefault("allow", [])
    rule = f"mcp({name}/*)"
    if rule not in allow:
        allow.append(rule)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")


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
