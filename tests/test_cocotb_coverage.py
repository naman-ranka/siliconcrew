"""cocotb_tool coverage=True: measured code coverage, not a testbench's own count.

The runner script is executed for real, against a stand-in `cocotb_tools`
package whose runner writes a results.xml and a Verilator coverage.dat, so the
parsing that runs inside the container is the code under test.
"""
import json
import os
import subprocess
import sys
import textwrap

import pytest

import src.tools.run_cocotb as rc

SOH, STX = "\x01", "\x02"


def _point(f, line, page, count, sig="x"):
    keys = f"{SOH}f{STX}/workspace/{f}{SOH}l{STX}{line}{SOH}page{STX}{page}{SOH}o{STX}{sig}"
    return f"C '{keys}' {count}\n"


FAKE_RUNNER = textwrap.dedent('''
    import os
    class _R:
        def build(self, build_dir, build_args=None, **kw):
            os.makedirs(build_dir, exist_ok=True)
            with open(os.path.join(build_dir, "args.txt"), "w") as f:
                f.write(" ".join(build_args or []))
        def test(self, build_dir, **kw):
            with open(os.path.join(build_dir, "results.xml"), "w") as f:
                f.write('<testsuites><testsuite><testcase name="t"/></testsuite></testsuites>')
            src = os.environ.get("FAKE_COVERAGE_DAT")
            if src:
                with open(src) as i, open(os.path.join(build_dir, "coverage.dat"), "w") as o:
                    o.write(i.read())
    def get_runner(sim):
        return _R()
''')


def _run_runner(tmp_path, coverage, dat_text=None):
    pkg = tmp_path / "fake" / "cocotb_tools"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "runner.py").write_text(FAKE_RUNNER)
    runner = tmp_path / "runner.py"
    runner.write_text(rc._RUNNER)
    env = dict(os.environ, PYTHONPATH=str(tmp_path / "fake"),
               SC_SOURCES=json.dumps(["rtl/fifo.v"]), SC_TOPLEVEL="fifo", SC_TEST_MODULE="t",
               SC_BUILD_DIR=str(tmp_path / "build"), SC_SIM="verilator",
               SC_COVERAGE="1" if coverage else "0")
    if dat_text is not None:
        dat = tmp_path / "coverage.dat"
        dat.write_text("# SystemC::Coverage-3\n" + dat_text)
        env["FAKE_COVERAGE_DAT"] = str(dat)
    out = subprocess.run([sys.executable, str(runner)], cwd=tmp_path, env=env,
                         capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
    return out.stdout, (tmp_path / "build" / "args.txt").read_text()


def test_coverage_run_builds_with_verilator_coverage_and_reports_measured_numbers(tmp_path):
    dat = (_point("fifo.v", 10, "v_line/fifo", 3)
           + _point("fifo.v", 20, "v_line/fifo", 0)
           + _point("fifo.v", 21, "v_branch/fifo", 0)
           + _point("fifo.v", 5, "v_toggle/fifo", 0, sig="mem[3][1]")
           + _point("fifo.v", 4, "v_toggle/fifo", 0, sig="full")
           + _point("fifo.v", 4, "v_toggle/fifo", 7, sig="empty")
           + _point("tb_helper.v", 1, "v_line/tb_helper", 0))      # not a listed source
    stdout, args = _run_runner(tmp_path, coverage=True, dat_text=dat)
    assert "--coverage-line" in args and "--coverage-toggle" in args
    cov = rc._parse_coverage(stdout)
    assert cov["measured"] is True
    assert cov["summary"]["line"] == {"covered": 1, "total": 2, "pct": 50.0}
    assert cov["summary"]["branch"] == {"covered": 0, "total": 1, "pct": 0.0}
    assert cov["summary"]["toggle"] == {"covered": 1, "total": 3, "pct": 33.3}
    assert cov["uncoveredLines"] == ["fifo.v:20", "fifo.v:21"]
    assert cov["uncoveredToggles"][0].startswith("full "), "ports before memory bits"


def test_plain_run_has_no_coverage_flags_or_report(tmp_path):
    stdout, args = _run_runner(tmp_path, coverage=False)
    assert args == "" and "SC_COCOTB_COVERAGE" not in stdout


def test_coverage_requested_but_no_dat_is_reported_unmeasured(tmp_path):
    stdout, _ = _run_runner(tmp_path, coverage=True)
    assert rc._parse_coverage(stdout) == {"measured": False, "summary": {},
                                          "uncoveredLines": [], "uncoveredToggles": []}


def test_run_cocotb_coverage_uses_the_coverage_image_and_verilator(monkeypatch, tmp_path):
    (tmp_path / "fifo.v").write_text("module fifo; endmodule\n")
    seen = {}

    class Engine:
        def run(self, image, command, cwd, env, timeout, name_prefix, base_env=None):
            seen.update(image=image, env=env)
            return {"success": True, "stdout": "SC_COCOTB_RESULT pass=1 fail=0 xml=yes\n"
                    'SC_COCOTB_COVERAGE {"measured": true, "summary": {}}', "stderr": ""}

    monkeypatch.setattr(rc, "get_tool_engine", lambda: Engine())
    r = rc.run_cocotb(["fifo.v"], "fifo", "t", cwd=str(tmp_path), coverage=True)
    assert seen["image"] == "siliconcrew/cocotb-coverage:1"
    assert seen["env"]["SC_SIM"] == "verilator" and seen["env"]["SC_COVERAGE"] == "1"
    assert r["status"] == "PASS" and r["coverage"]["measured"] is True


def test_missing_coverage_image_says_how_to_build_it(monkeypatch, tmp_path):
    (tmp_path / "fifo.v").write_text("module fifo; endmodule\n")

    class Engine:
        def run(self, **kw):
            return {"success": False, "stdout": "",
                    "stderr": "Unable to find image 'siliconcrew/cocotb-coverage:1' locally\n"
                              "docker: Error response from daemon: pull access denied"}

    monkeypatch.setattr(rc, "get_tool_engine", lambda: Engine())
    r = rc.run_cocotb(["fifo.v"], "fifo", "t", cwd=str(tmp_path), coverage=True)
    assert r["status"] == "ERROR" and "Dockerfile.cocotb-coverage" in r["stderr"]


def test_default_run_stays_on_the_grader_image(monkeypatch, tmp_path):
    (tmp_path / "fifo.v").write_text("module fifo; endmodule\n")
    seen = {}

    class Engine:
        def run(self, image, env, **kw):
            seen.update(image=image, env=env)
            return {"success": True, "stdout": "SC_COCOTB_RESULT pass=1 fail=0 xml=yes", "stderr": ""}

    monkeypatch.setattr(rc, "get_tool_engine", lambda: Engine())
    r = rc.run_cocotb(["fifo.v"], "fifo", "t", cwd=str(tmp_path))
    assert seen["image"] == rc.DEFAULT_OSVB_IMAGE and seen["env"]["SC_SIM"] == "icarus"
    assert "coverage" not in r
