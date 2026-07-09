"""Item 2 — the TemplateSource engine, GCS index gallery, and honest 503.

Covers ``GcsTemplateSource`` over the in-memory object store (list/get from a
published index, last-good TTL behavior, materialize + the net-new post-extract
ceiling, all-or-nothing binaries), the settings engine-resolution matrix, and
the REST surface (503 on an unreachable store, read-only listing). No live GCS
and no ``google-cloud`` import — the store is injected directly.
"""
import json
import os

import pytest

from src.platform_engines import template_source as TS
from src.platform_engines.settings import get_settings, reset_settings_cache
from src.platform_engines.workspace_provider import InMemoryObjectStore
from src.utils.bundles import BundleTooLarge
from src.utils.templates import TemplateNotFound


@pytest.fixture(autouse=True)
def _isolate():
    """Reset the process-wide source singleton + settings cache around each test."""
    TS.set_template_source(None)
    reset_settings_cache()
    yield
    TS.set_template_source(None)
    reset_settings_cache()


# ---------------------------------------------------------------------------
# Helpers: publish a bundle into an InMemoryObjectStore exactly as the publish
# script does (suffix-less keys; index.json as a raw object).
# ---------------------------------------------------------------------------


def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content if isinstance(content, str) else json.dumps(content))


def _publish_bundle(store, tmp_path, template_id="demo_fifo", *, with_binaries=True):
    """Stage a source (+ optional binaries) tree and return the index entry."""
    src = tmp_path / f"src_{template_id}"
    _write(str(src / "fifo.v"), "module fifo(); endmodule\n")
    _write(str(src / "manifest.json"), {"sessionId": "", "synthTop": "fifo"})
    store.put_tree(TS._SOURCE_KEY.format(id=template_id), str(src))
    if with_binaries:
        binaries = tmp_path / f"bin_{template_id}"
        gds = "synth_runs/synth_0001/orfs_results/sky130hd/fifo/base/6_final.gds"
        _write(str(binaries / gds.replace("/", os.sep)), "GDS-BYTES")
        store.put_tree(TS._BINARIES_KEY.format(id=template_id), str(binaries))
    return {
        "id": template_id,
        "name": "Demo FIFO",
        "description": "A tiny FIFO.",
        "highlights": ["Lints clean"],
        "file_count": 2,
        "run_count": 1,
        "files": ["fifo.v", "manifest.json"],
        "conversations": [],
        "tier": "official",
        "source": {"key": TS._SOURCE_KEY.format(id=template_id), "bytes": 10, "sha256": "x"},
        "binaries": {"key": TS._BINARIES_KEY.format(id=template_id), "bytes": 9, "sha256": "y"},
    }


def _put_index(store, entries):
    tmp = os.path.join(os.environ.get("TEMP") or ".", "sc_test_index.json")
    _write(tmp, {"version": 1, "generated_at": "2026-07-08T00:00:00+00:00", "templates": entries})
    store.put_file(TS.INDEX_KEY, tmp)
    os.remove(tmp)


# ---------------------------------------------------------------------------
# GcsTemplateSource — list / get from the index
# ---------------------------------------------------------------------------


def test_list_and_get_from_published_index(tmp_path):
    store = InMemoryObjectStore()
    entry = _publish_bundle(store, tmp_path)
    _put_index(store, [entry])

    src = TS.GcsTemplateSource(bucket="unused", store=store)
    listed = src.list()
    assert [t["id"] for t in listed] == ["demo_fifo"]
    assert listed[0]["file_count"] == 2
    got = src.get("demo_fifo")
    assert got["name"] == "Demo FIFO"
    assert got["files"] == ["fifo.v", "manifest.json"]


def test_get_unknown_id_raises_not_found(tmp_path):
    store = InMemoryObjectStore()
    _put_index(store, [_publish_bundle(store, tmp_path)])
    src = TS.GcsTemplateSource(bucket="unused", store=store)
    with pytest.raises(TemplateNotFound):
        src.get("ghost")


def test_suffixless_keys_match_store_round_trip(tmp_path):
    """A3: the keys the source reads are exactly what put_tree/get_tree store."""
    assert TS._SOURCE_KEY.format(id="x") == "bundles/x/source"
    assert TS._BINARIES_KEY.format(id="x") == "bundles/x/binaries"
    store = InMemoryObjectStore()
    _publish_bundle(store, tmp_path, template_id="x")
    assert store.exists("bundles/x/source")
    assert store.exists("bundles/x/binaries")


# ---------------------------------------------------------------------------
# Last-good TTL cache — honest offline (A14)
# ---------------------------------------------------------------------------


class _FlakyStore(InMemoryObjectStore):
    """An InMemoryObjectStore whose get_file can be flipped to raise."""

    def __init__(self):
        super().__init__()
        self.fail = False

    def get_file(self, key, local_path):
        if self.fail:
            raise RuntimeError("simulated GCS outage")
        return super().get_file(key, local_path)


def test_ttl_serves_last_good_after_a_read_failure(tmp_path):
    store = _FlakyStore()
    _put_index(store, [_publish_bundle(store, tmp_path)])
    src = TS.GcsTemplateSource(bucket="unused", store=store, ttl_seconds=60.0)

    # Prime the cache with a good read.
    assert [t["id"] for t in src.list()] == ["demo_fifo"]
    # Store goes down; within TTL the last-good list is still served (not empty).
    store.fail = True
    assert [t["id"] for t in src.list()] == ["demo_fifo"]


def test_ttl_expiry_raises_unavailable(tmp_path):
    store = _FlakyStore()
    _put_index(store, [_publish_bundle(store, tmp_path)])
    # ttl=0 → the cached copy is already stale by the time the next read fails.
    src = TS.GcsTemplateSource(bucket="unused", store=store, ttl_seconds=0.0)
    assert src.list()  # primes cache
    store.fail = True
    with pytest.raises(TS.TemplateStoreUnavailable):
        src.list()


def test_fresh_instance_with_dead_store_raises_not_empty():
    """No cache + unreachable store → 503, NEVER an empty gallery (invariant 4)."""
    store = _FlakyStore()
    store.fail = True
    src = TS.GcsTemplateSource(bucket="unused", store=store)
    with pytest.raises(TS.TemplateStoreUnavailable):
        src.list()
    with pytest.raises(TS.TemplateStoreUnavailable):
        src.get("demo_fifo")


def test_absent_index_raises_unavailable():
    """A store that is up but has no index.json yet is still unreachable, not empty."""
    src = TS.GcsTemplateSource(bucket="unused", store=InMemoryObjectStore())
    with pytest.raises(TS.TemplateStoreUnavailable):
        src.list()


# ---------------------------------------------------------------------------
# materialize — extract source + binaries, enforce the post-extract ceiling
# ---------------------------------------------------------------------------


def test_materialize_extracts_source_and_binaries(tmp_path):
    store = InMemoryObjectStore()
    _publish_bundle(store, tmp_path)
    src = TS.GcsTemplateSource(bucket="unused", store=store)
    dst = str(tmp_path / "dst")
    src.materialize("demo_fifo", dst)
    assert os.path.isfile(os.path.join(dst, "fifo.v"))
    assert os.path.isfile(os.path.join(dst, "manifest.json"))
    gds = os.path.join(dst, "synth_runs", "synth_0001", "orfs_results", "sky130hd", "fifo", "base", "6_final.gds")
    assert os.path.isfile(gds)


def test_materialize_enforces_post_extract_ceiling(tmp_path):
    store = InMemoryObjectStore()
    _publish_bundle(store, tmp_path)
    src = TS.GcsTemplateSource(bucket="unused", store=store)
    dst = str(tmp_path / "dst")
    with pytest.raises(BundleTooLarge):
        src.materialize("demo_fifo", dst, max_files=1)


def test_materialize_missing_binaries_is_all_or_nothing(tmp_path):
    """A6: a gcs source promised binaries — a missing archive fails the fork."""
    store = InMemoryObjectStore()
    _publish_bundle(store, tmp_path, with_binaries=False)
    src = TS.GcsTemplateSource(bucket="unused", store=store)
    with pytest.raises(TS.TemplateStoreUnavailable):
        src.materialize("demo_fifo", str(tmp_path / "dst"))


def test_materialize_missing_source_is_not_found(tmp_path):
    src = TS.GcsTemplateSource(bucket="unused", store=InMemoryObjectStore())
    with pytest.raises(TemplateNotFound):
        src.materialize("ghost", str(tmp_path / "dst"))


# ---------------------------------------------------------------------------
# LocalTemplateSource — behavior-identical delegation
# ---------------------------------------------------------------------------


def test_local_source_lists_and_materializes(tmp_path):
    examples = tmp_path / "examples"
    _write(str(examples / "demo" / "template.json"), {"id": "demo", "name": "Demo"})
    _write(str(examples / "demo" / "workspace" / "top.v"), "module top(); endmodule\n")
    src = TS.LocalTemplateSource(examples_dir=str(examples))
    assert [t["id"] for t in src.list()] == ["demo"]
    dst = str(tmp_path / "dst")
    src.materialize("demo", dst)
    assert os.path.isfile(os.path.join(dst, "top.v"))
    with pytest.raises(TemplateNotFound):
        src.materialize("ghost", str(tmp_path / "dst2"))


# ---------------------------------------------------------------------------
# Settings engine-resolution matrix
# ---------------------------------------------------------------------------


def test_settings_bucket_set_selects_gcs(monkeypatch):
    monkeypatch.setenv("TEMPLATES_BUCKET", "my-bucket")
    monkeypatch.delenv("TEMPLATES_ENGINE", raising=False)
    reset_settings_cache()
    s = get_settings()
    assert s.templates_engine == "gcs"
    assert s.templates_bucket == "my-bucket"


def test_settings_unset_selects_local(monkeypatch):
    monkeypatch.delenv("TEMPLATES_BUCKET", raising=False)
    monkeypatch.delenv("TEMPLATES_ENGINE", raising=False)
    reset_settings_cache()
    assert get_settings().templates_engine == "local"


def test_settings_explicit_engine_overrides_bucket(monkeypatch):
    monkeypatch.setenv("TEMPLATES_BUCKET", "my-bucket")
    monkeypatch.setenv("TEMPLATES_ENGINE", "local")
    reset_settings_cache()
    assert get_settings().templates_engine == "local"


def test_factory_gcs_empty_bucket_raises_at_first_use(monkeypatch):
    monkeypatch.setenv("TEMPLATES_ENGINE", "gcs")
    monkeypatch.delenv("TEMPLATES_BUCKET", raising=False)
    reset_settings_cache()
    TS.set_template_source(None)
    with pytest.raises(TS.TemplateStoreUnavailable):
        TS.get_template_source()


def test_factory_builds_local_by_default(monkeypatch):
    monkeypatch.delenv("TEMPLATES_BUCKET", raising=False)
    monkeypatch.delenv("TEMPLATES_ENGINE", raising=False)
    reset_settings_cache()
    TS.set_template_source(None)
    assert isinstance(TS.get_template_source(), TS.LocalTemplateSource)


# ---------------------------------------------------------------------------
# REST surface — 503 on an unreachable store, read-only listing
# ---------------------------------------------------------------------------

pytest.importorskip("fastapi")
from starlette.testclient import TestClient  # noqa: E402
import api  # noqa: E402
from src.utils.session_manager import SessionManager  # noqa: E402


class _FailingSource:
    def list(self):
        raise TS.TemplateStoreUnavailable("down")

    def get(self, template_id):
        raise TS.TemplateStoreUnavailable("down")

    def materialize(self, *a, **k):
        raise TS.TemplateStoreUnavailable("down")


def test_rest_list_returns_503_when_store_unavailable(tmp_path, monkeypatch):
    sm = SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "s.db"))
    monkeypatch.setattr(api, "session_manager", sm)
    TS.set_template_source(_FailingSource())
    client = TestClient(api.app)

    r = client.get("/api/templates")
    assert r.status_code == 503
    assert r.json()["detail"] == "Template gallery is unreachable"

    r = client.get("/api/templates/demo_fifo")
    assert r.status_code == 503
    assert r.json()["detail"] == "Template gallery is unreachable"

    # READ-ONLY: a failed (or any) listing must never materialize a session row.
    assert sm.get_all_sessions() == []


def test_rest_list_ok_through_gcs_source(tmp_path, monkeypatch):
    store = InMemoryObjectStore()
    _put_index(store, [_publish_bundle(store, tmp_path)])
    TS.set_template_source(TS.GcsTemplateSource(bucket="unused", store=store))
    client = TestClient(api.app)

    r = client.get("/api/templates")
    assert r.status_code == 200
    assert r.json()["templates"][0]["id"] == "demo_fifo"
    r = client.get("/api/templates/demo_fifo")
    assert r.status_code == 200
    assert r.json()["name"] == "Demo FIFO"
