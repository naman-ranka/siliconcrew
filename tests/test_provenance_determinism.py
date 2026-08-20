"""Determinism pins + provenance stamping (Phase 2, slice 7)."""
import os

from src.platform_engines.provenance import (
    Provenance,
    collect_provenance,
    orfs_image_digest,
)


def test_provenance_collects_commit_and_pins(monkeypatch):
    monkeypatch.setenv("SILICONCREW_COMMIT", "deadbeefcafe")
    monkeypatch.setenv("ORFS_IMAGE_DIGEST", "sha256:1234")
    import src.platform_engines.provenance as prov

    prov.repo_commit.cache_clear()
    p = collect_provenance(pdk="sky130hd", num_cores=4)
    assert isinstance(p, Provenance)
    assert p.repo_commit == "deadbeefcafe"
    assert p.orfs_image_digest == "sha256:1234"
    assert p.pdk == "sky130hd"
    assert p.num_cores == 4
    # Round-trips to a JSON-friendly dict (stamped into run_meta).
    d = p.as_dict()
    assert d["repo_commit"] == "deadbeefcafe" and d["num_cores"] == 4


def test_orfs_digest_extracted_from_pinned_image(monkeypatch):
    monkeypatch.delenv("ORFS_IMAGE_DIGEST", raising=False)
    assert orfs_image_digest("repo/orfs@sha256:abc123") == "sha256:abc123"
    # A tag-only image is NOT a digest pin.
    assert orfs_image_digest("repo/orfs:latest") is None


def test_provenance_never_raises_without_git(monkeypatch):
    monkeypatch.delenv("SILICONCREW_COMMIT", raising=False)
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    import src.platform_engines.provenance as prov

    prov.repo_commit.cache_clear()
    # Force the git lookup to fail.
    monkeypatch.setattr(prov.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    p = collect_provenance()
    assert p.repo_commit == "unknown"


def test_config_mk_pins_num_cores(tmp_path, monkeypatch):
    """The generated config.mk must pin NUM_CORES for P&R determinism."""
    monkeypatch.setenv("ORFS_NUM_CORES", "1")
    from src.platform_engines.settings import reset_settings_cache

    reset_settings_cache()
    import src.tools.synthesis_manager as sm

    run_dir = tmp_path / "synth_0001"
    (run_dir / "inputs").mkdir(parents=True)
    inp = run_dir / "inputs" / "dut.v"
    inp.write_text("module dut; endmodule\n")

    cfg = sm._write_orfs_config(
        run_dir=str(run_dir), top_module="dut", platform="sky130hd",
        input_files=[str(inp)], utilization=5, aspect_ratio=1.0, core_margin=2.0,
    )
    text = open(cfg).read()
    assert "export NUM_CORES = 1" in text
    reset_settings_cache()


def test_num_cores_pin_defaults(monkeypatch):
    monkeypatch.delenv("ORFS_NUM_CORES", raising=False)
    from src.platform_engines.settings import reset_settings_cache
    import src.tools.synthesis_manager as sm

    reset_settings_cache()
    assert sm._pinned_num_cores() == 4  # sensible reproducible default
    reset_settings_cache()


# ---------------------------------------------------------------------------
# B9 / R2-6: a run must record WHAT PRODUCED IT (prompt, skills, tool set)
# ---------------------------------------------------------------------------

def _fresh_commit(monkeypatch, value="deadbeefcafe"):
    monkeypatch.setenv("SILICONCREW_COMMIT", value)
    import src.platform_engines.provenance as prov

    prov.repo_commit.cache_clear()
    return prov


def test_provenance_records_the_active_prompt(monkeypatch):
    """The real, shipped prompt is stamped by version AND content hash."""
    prov = _fresh_commit(monkeypatch)
    monkeypatch.delenv("ARCHITECT_PROMPT_VERSION", raising=False)

    d = collect_provenance(pdk="sky130hd").as_dict()
    assert d["prompt_version"] == "v2"
    assert d["prompt_sha"].startswith("sha256:") and len(d["prompt_sha"]) == 7 + 64
    # ...and it is the hash of the file load_system_prompt would actually read.
    import hashlib

    expected = hashlib.sha256(prov.active_prompt_path().read_bytes()).hexdigest()
    assert d["prompt_sha"] == "sha256:" + expected


def test_prompt_identity_matches_architect_resolution(monkeypatch):
    """Pin against drift: provenance must pick the same file as the agent does.

    provenance.py deliberately re-implements the 4-line version rule rather than
    importing the LangGraph agent stack into every worker. This test is what
    keeps the copy honest.
    """
    monkeypatch.delenv("ARCHITECT_PROMPT_VERSION", raising=False)
    import src.platform_engines.provenance as prov
    from src.agents import architect

    assert prov.active_prompt_path().resolve() == architect.PROMPT_FILE_DEFAULT.resolve()


def test_prompt_edit_moves_sha_but_not_version(tmp_path, monkeypatch):
    """A version string alone cannot attribute a run: the file changes under it."""
    import src.platform_engines.provenance as prov

    monkeypatch.delenv("ARCHITECT_PROMPT_VERSION", raising=False)
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    monkeypatch.setattr(prov, "PROMPTS_DIR", prompts)
    target = prompts / "architect_prompt_v2.md"

    target.write_text("You are the Architect.\n\nPROMPT_VERSION: v2\n", encoding="utf-8")
    v1, sha1 = prov.prompt_identity()

    target.write_text(
        "You are the Architect.\nAlways run lint first.\n\nPROMPT_VERSION: v2\n",
        encoding="utf-8",
    )
    v2, sha2 = prov.prompt_identity()

    assert v1 == v2 == "v2"          # version stays put...
    assert sha1 != sha2              # ...but the content hash moves.
    assert sha1 and sha2


def test_prompt_version_follows_env_like_load_system_prompt(tmp_path, monkeypatch):
    import src.platform_engines.provenance as prov

    prompts = tmp_path / "prompts"
    prompts.mkdir()
    monkeypatch.setattr(prov, "PROMPTS_DIR", prompts)
    (prompts / "architect_prompt_v7.md").write_text("v7 body\n", encoding="utf-8")

    monkeypatch.setenv("ARCHITECT_PROMPT_VERSION", " V7 ")
    version, sha = prov.prompt_identity()
    assert version == "v7" and sha is not None
    assert prov.active_prompt_path().name == "architect_prompt_v7.md"


def test_missing_prompt_file_records_absent_not_a_lie(tmp_path, monkeypatch):
    """A missing prompt file means load_system_prompt raises and no turn ran on
    it; never name a file that was never read."""
    import src.platform_engines.provenance as prov

    monkeypatch.setattr(prov, "PROMPTS_DIR", tmp_path / "nope")
    assert prov.prompt_identity() == (None, None)


def test_skill_and_tool_set_fields_are_present_and_absent(monkeypatch):
    """The fields must EXIST today so the later phase adds data, not schema —
    and ``None`` must read as absent, never as 'the user configured none'."""
    _fresh_commit(monkeypatch)
    d = collect_provenance(pdk="sky130hd", num_cores=4).as_dict()

    for field in ("prompt_version", "prompt_sha", "skills_loaded", "skills_sha", "tool_set"):
        assert field in d, f"{field} missing from the provenance block"
    # Absent — nothing looked, so nothing was chosen. NOT [] ("looked, found none").
    assert d["skills_loaded"] is None
    assert d["skills_sha"] is None
    assert d["tool_set"] is None


def test_collect_provenance_reads_the_bound_scope_not_its_own_lookup(monkeypatch):
    """A3-H4: the owner-scoped half is resolved once per turn and READ here."""
    prov = _fresh_commit(monkeypatch)

    bound = prov.AgentProvenance(
        prompt_version="v9",
        prompt_sha="sha256:beef",
        skills_loaded=["self-verification-standard"],
        skills_sha="sha256:cafe",
        tool_set="default@3",
    )
    with prov.agent_provenance_scope(bound):
        d = collect_provenance(pdk="sky130hd").as_dict()

    assert d["prompt_version"] == "v9"
    assert d["prompt_sha"] == "sha256:beef"
    assert d["skills_loaded"] == ["self-verification-standard"]
    assert d["skills_sha"] == "sha256:cafe"
    assert d["tool_set"] == "default@3"
    # The scope does not leak past its block.
    assert prov.current_agent_provenance() is None
    assert collect_provenance().skills_loaded is None


def test_empty_skill_set_is_recorded_as_a_choice(monkeypatch):
    """[] and None must stay distinguishable end to end."""
    prov = _fresh_commit(monkeypatch)
    names, digest = prov.skills_digest({})
    with prov.agent_provenance_scope(
        prov.AgentProvenance(skills_loaded=names, skills_sha=digest)
    ):
        d = collect_provenance().as_dict()
    assert d["skills_loaded"] == []          # a resolver looked and found none
    assert d["skills_sha"] == digest         # ...and said so with a real hash
    assert d["skills_loaded"] is not None


def test_skills_digest_is_order_stable_and_content_sensitive():
    import src.platform_engines.provenance as prov

    a_names, a = prov.skills_digest({"x": "body x", "y": "body y"})
    b_names, b = prov.skills_digest({"y": "body y", "x": "body x"})
    assert a_names == b_names == ["x", "y"]
    assert a == b                                        # load order is irrelevant
    assert prov.skills_digest({"x": "body x", "y": "EDIT"})[1] != a   # content is not
    assert prov.skills_digest({"z": "body x", "y": "body y"})[1] != a  # nor is the name


def test_request_scope_resolves_agent_provenance_once_per_turn(monkeypatch, tmp_path):
    """The writer A3-H4 asked for: request scope resolves, keyed by owner."""
    import src.platform_engines.provenance as prov
    from src.platform_engines.request_scope import session_request_scope

    monkeypatch.delenv("ARCHITECT_PROMPT_VERSION", raising=False)

    class _Provider:
        def workspace_for(self, session_id):
            path = tmp_path / session_id
            path.mkdir(parents=True, exist_ok=True)
            return str(path)

    calls = []
    real = prov.resolve_agent_provenance

    def _counting(user_id=None):
        calls.append(user_id)
        return real(user_id=user_id)

    monkeypatch.setattr(prov, "resolve_agent_provenance", _counting)
    monkeypatch.setattr(
        "src.platform_engines.request_scope.resolve_agent_provenance", _counting
    )

    assert prov.current_agent_provenance() is None
    with session_request_scope("sess_a", user_id="owner_a", provider=_Provider()):
        stamped = collect_provenance(pdk="sky130hd").as_dict()
        # A nested scope must NOT re-resolve — the outermost turn owns the stamp.
        with session_request_scope("sess_a", user_id="owner_a", provider=_Provider()):
            pass
    assert calls == ["owner_a"], f"resolved {len(calls)} times, expected once"
    assert stamped["prompt_version"] == "v2" and stamped["prompt_sha"]
    assert prov.current_agent_provenance() is None


def test_synth_run_meta_carries_the_prompt_stamp(monkeypatch):
    """End to end at the real call site: what start_synthesis writes into
    run_meta names the prompt that drove it."""
    prov = _fresh_commit(monkeypatch)
    monkeypatch.delenv("ARCHITECT_PROMPT_VERSION", raising=False)
    import src.tools.synthesis_manager as sm

    with prov.agent_provenance_scope(
        prov.AgentProvenance(prompt_version="v2", prompt_sha="sha256:abc", tool_set="t1")
    ):
        block = sm.collect_provenance(pdk="sky130hd", num_cores=sm._pinned_num_cores()).as_dict()

    assert block["repo_commit"] == "deadbeefcafe"
    assert block["pdk"] == "sky130hd"
    assert block["prompt_version"] == "v2"
    assert block["prompt_sha"] == "sha256:abc"
    assert block["tool_set"] == "t1"
    assert block["skills_loaded"] is None


def test_shipped_prompt_carries_no_absolute_author_path():
    """The v2 prompt shipped an author's Windows path to the model every turn."""
    from pathlib import Path

    text = (
        Path(__file__).resolve().parents[1]
        / "prompts" / "architect" / "architect_prompt_v2.md"
    ).read_text(encoding="utf-8")
    assert "PROMPT_SOURCE" not in text
    assert "C:\\Users" not in text
    assert "PROMPT_VERSION: v2" in text   # the version line stays
