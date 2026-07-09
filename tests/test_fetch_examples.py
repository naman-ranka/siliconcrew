"""Item 1 — the binary fetch script (scripts/fetch_examples.py).

Drives the script against a locally built ``binaries.tar.gz`` served over a
``file://`` base URL (stdlib ``urllib`` handles both file:// and https), and
covers: per-file sha256 verify (corrupt file -> hard error), idempotent re-run
(no re-download), and the honest missing-archive path (skip vs --strict).
No network, no cloud SDK — matching the sacred self-host constraint.
"""
import io
import json
import os
import pathlib
import tarfile

import pytest

from scripts import fetch_examples as F
from scripts import split_bundle_binaries as S


def _write(path, content=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(content, (bytes, bytearray)) else "w"
    with open(path, mode) as f:
        f.write(content)


def _publish_binaries(served_root, template_id, ws_with_binaries):
    """Build the served ``official/bundles/<id>/binaries.tar.gz`` from a dir that
    holds the binary files at their workspace-relative paths."""
    manifest = json.load(open(os.path.join(ws_with_binaries, S.SC_BINARIES_NAME), encoding="utf-8"))
    out = os.path.join(served_root, "official", "bundles", template_id)
    os.makedirs(out, exist_ok=True)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for entry in manifest["files"]:
            src = os.path.join(ws_with_binaries, entry["path"].replace("/", os.sep))
            tar.add(src, arcname=entry["path"])
    with open(os.path.join(out, "binaries.tar.gz"), "wb") as f:
        f.write(buf.getvalue())


def _base_url(served_root):
    return pathlib.Path(served_root).as_uri()  # file:///... form urllib accepts


_BINARIES = {
    "synth_runs/s1/orfs_results/sky130hd/top/base/6_final.gds": b"GDSDATA" * 500,
    "synth_runs/s1/orfs_results/sky130hd/top/base/6_final.v": b"module top(); endmodule\n",
    "synth_runs/s1/orfs_reports/sky130hd/top/base/final_all.webp": b"WEBPDATA" * 100,
}


@pytest.fixture
def scenario(tmp_path):
    """A split bundle (manifest, no binaries) + a matching published archive.

    Returns ``(bundle_dir, workspace_dir, file:// base url)``. The archive is
    built from a pristine copy of the binaries at their workspace-relative paths
    (what Item 2's publish script produces from a pre-split ref).
    """
    # 1) The bundle: write binaries + a kept file, then split (deletes binaries).
    bundle = os.path.join(str(tmp_path), "examples", "demo")
    ws = os.path.join(bundle, "workspace")
    for rel, data in _BINARIES.items():
        _write(os.path.join(ws, rel.replace("/", os.sep)), data)
    _write(os.path.join(ws, "synth_runs/s1/orfs_results/sky130hd/top/base/5_route.sdc"), "create_clock\n")
    S.split_bundle(bundle, apply=True)

    # 2) A pristine dir holding the binaries + the manifest, to publish from.
    pub_ws = os.path.join(str(tmp_path), "pub", "workspace")
    for rel, data in _BINARIES.items():
        _write(os.path.join(pub_ws, rel.replace("/", os.sep)), data)
    import shutil
    shutil.copy(os.path.join(ws, S.SC_BINARIES_NAME), os.path.join(pub_ws, S.SC_BINARIES_NAME))

    served = os.path.join(str(tmp_path), "served")
    _publish_binaries(served, "demo", pub_ws)
    return bundle, ws, _base_url(served)


def test_fetch_downloads_and_verifies(scenario):
    bundle, ws, base_url = scenario
    gds = os.path.join(ws, "synth_runs/s1/orfs_results/sky130hd/top/base/6_final.gds")
    assert not os.path.exists(gds)  # split removed it
    assert F.fetch_bundle(bundle, base_url) == "fetched"
    assert os.path.isfile(gds)
    assert os.path.isfile(os.path.join(ws, "synth_runs/s1/orfs_reports/sky130hd/top/base/final_all.webp"))


def test_fetch_is_idempotent(scenario):
    bundle, ws, base_url = scenario
    assert F.fetch_bundle(bundle, base_url) == "fetched"
    # All files now present + matching -> no re-download.
    assert F.fetch_bundle(bundle, base_url) == "up-to-date"


def test_fetch_detects_corruption(scenario, tmp_path):
    bundle, ws, base_url = scenario
    # Corrupt the published archive so an extracted file mismatches its sha256.
    served = os.path.join(str(tmp_path), "served")
    out = os.path.join(served, "official", "bundles", "demo", "binaries.tar.gz")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        bad = b"CORRUPT"
        info = tarfile.TarInfo("synth_runs/s1/orfs_results/sky130hd/top/base/6_final.gds")
        info.size = len(bad)
        tar.addfile(info, io.BytesIO(bad))
        for name, data in [
            ("synth_runs/s1/orfs_results/sky130hd/top/base/6_final.v", b"module top(); endmodule\n"),
            ("synth_runs/s1/orfs_reports/sky130hd/top/base/final_all.webp", b"WEBPDATA" * 100),
        ]:
            i = tarfile.TarInfo(name)
            i.size = len(data)
            tar.addfile(i, io.BytesIO(data))
    with open(out, "wb") as f:
        f.write(buf.getvalue())

    with pytest.raises(F.VerifyError):
        F.fetch_bundle(bundle, base_url)


def test_fetch_missing_archive_is_honest(scenario, tmp_path):
    bundle, ws, _base = scenario
    os.makedirs(os.path.join(str(tmp_path), "empty"), exist_ok=True)
    empty_base = pathlib.Path(str(tmp_path), "empty").as_uri()
    with pytest.raises(F.NotPublished):
        F.fetch_bundle(bundle, empty_base)


def test_main_missing_is_zero_unless_strict(scenario, tmp_path, capsys):
    bundle, ws, _base = scenario
    examples_dir = os.path.dirname(bundle)
    empty_base = pathlib.Path(str(tmp_path), "empty2").as_uri()
    os.makedirs(os.path.join(str(tmp_path), "empty2"), exist_ok=True)
    rc = F.main(["--examples-dir", examples_dir, "--base-url", empty_base])
    assert rc == 0
    rc_strict = F.main(["--examples-dir", examples_dir, "--base-url", empty_base, "--strict"])
    assert rc_strict == 1


def test_main_fetches_and_verifies(scenario):
    bundle, ws, base_url = scenario
    examples_dir = os.path.dirname(bundle)
    rc = F.main(["--examples-dir", examples_dir, "--base-url", base_url])
    assert rc == 0
    assert os.path.isfile(os.path.join(ws, "synth_runs/s1/orfs_results/sky130hd/top/base/6_final.gds"))
