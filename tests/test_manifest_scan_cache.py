"""The module-scan sweep must not re-read the tree on every read (S3).

`read_manifest` sits under GET /files, GET /code, every write_file and every
dispatch. A sweep that re-reads every rtl/tb file each time turned a ~0.01s
steady-state read into ~0.2s on a 200-file workspace. Process memory is a cache
of disk truth (invariant 5) — keyed by a fingerprint, so an edit invalidates it.
"""
import os
import time

from src.tools import manifest as m


DUT = "module m{i} (input a, output b); assign b = a; endmodule\n"


def _write(ws, rel, text):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _seed(ws, n=12):
    for i in range(n):
        _write(ws, f"rtl/m{i}.v", DUT.format(i=i))
    _write(ws, "top_tb.v", "module top_tb; m0 d(); initial #1 $finish; endmodule\n")


def _counting_read_text(monkeypatch):
    calls = []
    original = m._read_text

    def counted(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(m, "_read_text", counted)
    return calls


def test_second_read_does_not_reopen_the_design_files(tmp_path, monkeypatch):
    ws = str(tmp_path)
    _seed(ws)
    m.read_manifest(ws, session_id="s1")  # warm

    calls = _counting_read_text(monkeypatch)
    m.read_manifest(ws, session_id="s1")
    assert calls == [], f"second read re-opened {len(calls)} files"


def test_editing_a_file_invalidates_the_cache(tmp_path, monkeypatch):
    ws = str(tmp_path)
    _seed(ws)
    m.read_manifest(ws, session_id="s1")

    # Edit an existing file in place so it now declares m1 as well — same file
    # set, so only the CONTENT fingerprint can catch this.
    time.sleep(0.01)
    _write(ws, "rtl/m0.v", DUT.format(i=1))

    calls = _counting_read_text(monkeypatch)
    manifest = m.read_manifest(ws, session_id="s1")
    assert calls, "an edited file must force a rescan"
    # A derived field recomputed from the new content: m1 is now a duplicate.
    assert len(manifest.warnings) == 1
    assert "rtl/m0.v" in manifest.warnings[0] and "rtl/m1.v" in manifest.warnings[0]


def test_a_new_file_invalidates_the_cache(tmp_path, monkeypatch):
    ws = str(tmp_path)
    _seed(ws)
    m.read_manifest(ws, session_id="s1")

    _write(ws, "rtl/dup.v", DUT.format(i=0))  # declares m0 a second time

    warnings = m.read_manifest(ws, session_id="s1").warnings
    assert len(warnings) == 1 and "rtl/dup.v" in warnings[0]


def test_build_manifest_reads_each_file_once(tmp_path, monkeypatch):
    """Role derivation and the sweep used to read the same files separately."""
    ws = str(tmp_path)
    _seed(ws, n=5)
    m._SCAN_CACHE.clear()

    calls = _counting_read_text(monkeypatch)
    m.build_manifest(ws, session_id="s1")
    assert len(calls) == len(set(calls)), f"duplicate reads: {calls}"
