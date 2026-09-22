"""Lint engine resolution, unavailable engines, and Windows paths.

Found running the Codex agent on a Windows host:
- verilator missing -> the agent tool said "Lint FAILED — 1 error" for a correct
  design; every agent spent a call on it.
- verilator from MSYS2 -> `verilator` is a Perl script CreateProcess can't run,
  so `auto` picked it and every lint failed (WinError 193).
- verilator diagnostics and -MMD depfiles on Windows carry drive colons
  (`C:\\...:3:5:`), which the parsers read as separators.
"""
import json
import os

import pytest

import src.tools.run_linter as rl


def _msys_layout(tmp_path):
    bin_dir = tmp_path / "ucrt64" / "bin"
    share = tmp_path / "ucrt64" / "share" / "verilator"
    bin_dir.mkdir(parents=True)
    share.mkdir(parents=True)
    (bin_dir / "verilator").write_text("#!/usr/bin/perl\n")      # the Perl wrapper
    (bin_dir / "verilator_bin.exe").write_text("")
    return bin_dir, share


def test_msys2_verilator_runs_verilator_bin_with_its_root(monkeypatch, tmp_path):
    bin_dir, share = _msys_layout(tmp_path)
    monkeypatch.setattr(rl, "_IS_WINDOWS", True)
    monkeypatch.delenv("VERILATOR_ROOT", raising=False)
    monkeypatch.setattr(rl.shutil, "which", lambda name: {
        "verilator": str(bin_dir / "verilator"),
        "verilator_bin": str(bin_dir / "verilator_bin.exe"),
    }.get(name))
    cmd = rl._verilator_command()
    assert cmd == {"exe": str(bin_dir / "verilator_bin.exe"), "env": {"VERILATOR_ROOT": str(share)}}


def test_an_existing_verilator_root_is_left_alone(monkeypatch, tmp_path):
    bin_dir, _ = _msys_layout(tmp_path)
    monkeypatch.setattr(rl, "_IS_WINDOWS", True)
    monkeypatch.setenv("VERILATOR_ROOT", "C:/somewhere/else")
    monkeypatch.setattr(rl.shutil, "which", lambda name: {
        "verilator": str(bin_dir / "verilator"),
        "verilator_bin": str(bin_dir / "verilator_bin.exe"),
    }.get(name))
    assert rl._verilator_command()["env"] == {}


def test_a_runnable_verilator_is_called_by_name_as_before(monkeypatch):
    monkeypatch.setattr(rl.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert rl._verilator_command() == {"exe": "verilator", "env": {}}


def test_no_verilator_means_none_even_if_other_binaries_exist(monkeypatch):
    monkeypatch.setattr(rl.shutil, "which", lambda name: None if name == "verilator" else f"/usr/bin/{name}")
    assert rl._verilator_command() is None


def test_unavailable_engine_is_flagged_not_a_verdict(monkeypatch, tmp_path):
    monkeypatch.setattr(rl.shutil, "which", lambda name: None if name == "verilator" else "/usr/bin/iverilog")
    (tmp_path / "a.v").write_text("module a; endmodule\n")
    r = rl.run_linter([str(tmp_path / "a.v")], cwd=str(tmp_path), engine="verilator")
    assert r["unavailable"] is True and r["success"] is False and "not installed" in r["stderr"]


def test_rest_lint_returns_engine_unavailable_not_a_failed_lint(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api.actions import build_actions_router

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.v").write_text("module a; endmodule\n")
    (ws / "manifest.json").write_text(json.dumps({"files": [{"path": "a.v", "role": "rtl"}]}))

    def resolve(session_id):
        return str(ws)

    app = FastAPI()
    app.include_router(build_actions_router(resolve))
    monkeypatch.setattr(rl.shutil, "which", lambda name: None if name == "verilator" else "/usr/bin/iverilog")
    res = TestClient(app).post("/api/workspace/s1/lint", json={"engine": "verilator"})
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["error"]["code"] == "engine_unavailable"


def test_unknown_engine_is_invalid_not_unavailable(tmp_path):
    (tmp_path / "a.v").write_text("module a; endmodule\n")
    r = rl.run_linter([str(tmp_path / "a.v")], cwd=str(tmp_path), engine="foo")
    assert r["invalid_engine"] is True and r["unavailable"] is False


def test_rest_lint_unknown_engine_is_a_400(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.api.actions import build_actions_router

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "a.v").write_text("module a; endmodule\n")
    (ws / "manifest.json").write_text(json.dumps({"files": [{"path": "a.v", "role": "rtl"}]}))
    app = FastAPI()
    app.include_router(build_actions_router(lambda sid: str(ws)))
    res = TestClient(app).post("/api/workspace/s1/lint", json={"engine": "foo"})
    assert res.status_code == 400 and res.json()["detail"]["error"]["code"] == "invalid_engine"


def test_posix_single_letter_file_with_a_column_still_parses_as_before():
    # The drive prefix needs a path separator after the colon, so `a:3:5:` is
    # file `a`, line 3 — not file `a:3`, line 5.
    [d] = rl.parse_verilator_diagnostics("%Error: a:3:5: bad")
    assert (d["file"], d["line"]) == ("a", 3)
    [d] = rl.parse_iverilog_diagnostics("b:10:3: syntax error")
    assert (d["file"], d["line"]) == ("b", 10)


def test_verilator_diagnostic_with_a_windows_drive_parses():
    out = r"%Error-MODMISSING: C:\ws\rtl\top.v:2:3: Cannot find file containing module: 'alu'"
    [d] = rl.parse_verilator_diagnostics(out, cwd=r"C:\ws" if os.name == "nt" else None)
    assert d["line"] == 2 and d["code"] == "MODMISSING"
    assert d["message"].startswith("Cannot find file containing module")
    assert d["file"].replace("\\", "/").endswith("rtl/top.v")


def test_iverilog_diagnostic_with_a_windows_drive_parses():
    [d] = rl.parse_iverilog_diagnostics(r"C:\ws\top.v:7: syntax error")
    assert d["line"] == 7 and d["severity"] == "error"


def test_depfile_rule_splits_at_the_separator_not_a_drive_colon():
    text = r"C:\tmp\lint_deps_x\Vtop__ver.d nul  : C:\tools\verilator_bin.exe top.v" + "\n"
    deps = rl.parse_verilator_depfile(text, cwd=os.getcwd())
    names = [os.path.basename(d.replace("\\", "/")) for d in deps]
    assert "top.v" in names and "verilator_bin.exe" in names
    assert not any("Vtop__ver.d" in d or d.endswith("nul") for d in deps)
