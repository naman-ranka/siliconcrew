"""The second layer: a user's own skills over the built-in pack.

Four rules and no priority language — a user skill with the same name replaces
the built-in, a name in a small list is off, an updated built-in never
overrides a replacement, and the two are never auto-merged. What is worth a
test is what would rot silently:

1. The rules themselves, including the one that says nothing merges.
2. That the SAME layering code runs in both deployment modes — the whole claim
   of the engine seam is that only storage differs.
3. That the always-loaded safety skill can be switched off, and that a run made
   with it off says so. A benchmark number from a session with the safety net
   removed must never be indistinguishable from one with it in place.
4. That one owner's skills cannot reach another owner's agent.
"""
from __future__ import annotations

import json

import pytest

from src.platform_engines import user_skill_store as store_mod
from src.platform_engines.user_skill_store import (
    LocalUserSkillStore,
    ObjectUserSkillStore,
    set_user_skill_store,
)
from src.utils import skills as sk


def _text(name, description="Does a thing when a thing is needed.", body="MINE"):
    return f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"


def _builtins():
    return sk.discover_skills(sk.SKILLS_ROOT)


def _a_builtin():
    return _builtins()[0].name


def _the_always_loaded():
    return next(s.name for s in _builtins() if s.always_load)


@pytest.fixture
def local(tmp_path):
    set_user_skill_store(LocalUserSkillStore(tmp_path / "layer"))
    return tmp_path / "layer"


# =============================================================================
# 1. The four rules
# =============================================================================

def test_a_user_skill_with_the_same_name_replaces_the_builtin(local):
    name = _a_builtin()
    shipped = sk.read_skill_file(name, user_id=None)
    sk.save_user_skill(_text(name, body="MINE-BODY"), user_id=None)

    entry = sk.resolve_skills(None).get(name)
    assert entry.layer == sk.REPLACEMENT
    assert "MINE-BODY" in sk.read_skill_file(name, user_id=None)
    assert sk.read_skill_file(name, user_id=None) != shipped


def test_nothing_is_merged_only_replaced(local):
    """Rule 4. The built-in's text must be GONE, not blended in."""
    name = _a_builtin()
    shipped_body = next(s.body for s in _builtins() if s.name == name)
    sk.save_user_skill(_text(name, body="MINE-BODY"), user_id=None)

    active = {s.name: s for s in sk.resolve_skills(None).active}
    assert active[name].body.strip() == "MINE-BODY"
    assert shipped_body.splitlines()[0] not in active[name].body


def test_a_new_name_is_added_beside_the_pack_not_over_it(local):
    sk.save_user_skill(_text("my-own-thing"), user_id=None)
    resolved = sk.resolve_skills(None)
    assert resolved.get("my-own-thing").layer == sk.USER
    assert {e.name for e in resolved.entries} == {s.name for s in _builtins()} | {"my-own-thing"}


def test_disabling_is_a_name_in_a_list_never_a_copy(local):
    """Rule 2. Switching a built-in off must not fork it."""
    name = _a_builtin()
    sk.set_skill_enabled(name, False, user_id=None)

    resolved = sk.resolve_skills(None)
    assert name in resolved.disabled
    assert name not in [s.name for s in resolved.active]
    assert not (local / name).exists()          # no copy was made...
    assert json.loads((local / store_mod.CONFIG_FILENAME).read_text())["disabled"] == [name]

    sk.set_skill_enabled(name, True, user_id=None)
    assert name in [s.name for s in sk.resolve_skills(None).active]


def test_a_disabled_skill_is_neither_advertised_nor_readable(local):
    name = _a_builtin()
    sk.set_skill_enabled(name, False, user_id=None)
    assert f"- {name}:" not in sk.skill_index()
    assert f"- {name}:" not in sk.compose_skills_block()
    with pytest.raises(sk.SkillError):
        sk.read_skill_file(name, user_id=None)


def test_updating_a_builtin_never_overrides_a_replacement(local):
    """Rule 3. The user's text stays; the change is REPORTED, not applied."""
    name = _a_builtin()
    sk.save_user_skill(_text(name, body="MINE-BODY"), user_id=None)
    assert sk.resolve_skills(None).get(name).builtin_changed is False

    # A deploy edits the shipped file: same recipe as recording the fork, so
    # simulate it by moving the recorded hash instead of writing to the repo.
    config = json.loads((local / store_mod.CONFIG_FILENAME).read_text())
    config["forked"][name] = "0" * 64
    (local / store_mod.CONFIG_FILENAME).write_text(json.dumps(config))

    entry = sk.resolve_skills(None).get(name)
    assert entry.builtin_changed is True
    assert entry.skill.body.strip() == "MINE-BODY"        # ...and nothing moved


def test_a_skill_written_by_hand_reports_no_verdict_on_the_builtin(local):
    """Absent, not "unchanged": nobody recorded what it was forked from."""
    name = _a_builtin()
    directory = local / name
    directory.mkdir(parents=True)
    (directory / sk.SKILL_FILENAME).write_text(_text(name), encoding="utf-8")
    assert sk.resolve_skills(None).get(name).builtin_changed is None


def test_resetting_a_replacement_restores_the_shipped_text(local):
    name = _a_builtin()
    shipped = sk.read_skill_file(name, root=sk.SKILLS_ROOT)
    sk.save_user_skill(_text(name, body="MINE-BODY"), user_id=None)
    assert sk.delete_user_skill(name, user_id=None) is True

    assert sk.resolve_skills(None).get(name).layer == sk.BUILTIN
    assert sk.read_skill_file(name, user_id=None) == shipped
    assert sk.delete_user_skill(name, user_id=None) is False   # nothing left to reset


# =============================================================================
# 2. A stale entry is surfaced, never silently honoured or dropped
# =============================================================================

def test_a_disable_entry_that_matches_nothing_is_reported(local):
    """A3-H3: a built-in renamed under a saved choice. Dropping the entry turns
    a skill the user switched off back on with nothing to show for it."""
    store_mod.write_config(local, {"disabled": ["a-skill-that-was-renamed"], "forked": {}})
    resolved = sk.resolve_skills(None)
    assert resolved.unmatched_disabled == ("a-skill-that-was-renamed",)
    assert resolved.disabled == ()                       # it disabled nothing...
    assert len(resolved.active) == len(_builtins())      # ...and nothing is off

    # Turning it back on is how it gets cleared — the one gesture the page has.
    sk.set_skill_enabled("a-skill-that-was-renamed", True, user_id=None)
    assert sk.resolve_skills(None).unmatched_disabled == ()


def test_a_name_that_exists_nowhere_cannot_be_switched_off(local):
    with pytest.raises(sk.SkillError):
        sk.set_skill_enabled("no-such-skill", False, user_id=None)


def test_a_users_broken_file_is_shown_not_obeyed_and_not_fatal(local):
    """The built-in pack raises on a bad file — that is a bad deploy. A user's
    own typo may not take every turn down with it."""
    name = _a_builtin()
    directory = local / name
    directory.mkdir(parents=True)
    (directory / sk.SKILL_FILENAME).write_text("no frontmatter here", encoding="utf-8")

    entry = sk.resolve_skills(None).get(name)
    assert entry.layer == sk.BUILTIN and entry.error
    assert name in [s.name for s in sk.resolve_skills(None).active]


def test_a_skill_is_validated_before_anything_is_stored(local):
    with pytest.raises(sk.SkillError):
        sk.save_user_skill("---\nname: bad\ndescription: x\nnot_a_spec_key: 1\n---\n\nbody\n",
                           user_id=None)
    assert not (local / "bad").exists()


@pytest.mark.parametrize("name", ["../escape", "nested/name", ".hidden", "Upper"])
def test_a_skill_name_cannot_leave_its_folder(local, name):
    with pytest.raises(sk.SkillError):
        sk.save_user_skill(_text(name), user_id=None)


# =============================================================================
# 3. The safety skill: disableable, and never quietly
# =============================================================================

def test_the_always_loaded_skill_can_be_turned_off(local):
    """Forcing it secretly would be dishonest. It is a choice, and it works."""
    name = _the_always_loaded()
    body = next(s.body for s in _builtins() if s.name == name)
    assert body.splitlines()[0] in sk.compose_skills_block()

    sk.set_skill_enabled(name, False, user_id=None)
    assert body.splitlines()[0] not in sk.compose_skills_block()


def test_provenance_records_that_the_safety_net_was_off(local):
    from src.platform_engines.provenance import collect_provenance, resolve_agent_provenance

    name = _the_always_loaded()
    sk.set_skill_enabled(name, False, user_id=None)

    stamp = resolve_agent_provenance(user_id=None)
    assert stamp.skills_disabled == [name]
    assert name not in stamp.skills_loaded
    assert collect_provenance(agent=stamp).as_dict()["skills_disabled"] == [name]


def test_provenance_says_nothing_is_off_rather_than_saying_nothing(local):
    """``[]`` is a resolver that looked; ``None`` would be "nobody asked"."""
    from src.platform_engines.provenance import resolve_agent_provenance

    stamp = resolve_agent_provenance(user_id=None)
    assert stamp.skills_disabled == []


def test_an_edited_skill_moves_the_digest_under_an_unchanged_name(local):
    from src.platform_engines.provenance import resolve_agent_provenance

    before = resolve_agent_provenance(user_id=None)
    sk.save_user_skill(_text(_a_builtin(), body="MINE-BODY"), user_id=None)
    after = resolve_agent_provenance(user_id=None)

    assert after.skills_loaded == before.skills_loaded    # the names say nothing...
    assert after.skills_sha != before.skills_sha          # ...the content does


# =============================================================================
# 4. Tenancy — one owner's skills never reach another owner's agent
# =============================================================================

def test_two_owners_never_see_each_others_layer(tmp_path):
    set_user_skill_store(LocalUserSkillStore(tmp_path / "layer"))
    sk.save_user_skill(_text("owner-a-private", body="A-SECRET"), user_id="owner_a")
    sk.set_skill_enabled(_a_builtin(), False, user_id="owner_a")

    b = sk.resolve_skills("owner_b")
    assert "owner-a-private" not in [e.name for e in b.entries]
    assert "owner-a-private" not in sk.compose_skills_block(b.active)
    assert b.disabled == ()
    assert [e.name for e in b.entries] == [s.name for s in _builtins()]


def test_the_owner_comes_from_the_request_scope_not_a_cached_index(tmp_path):
    """A3-C1: the composition points take no owner, so the owner is read from
    the task-local session context on EVERY call. A cached index would render
    one user's skill bodies into another's prompt."""
    from src.utils.session_context import SessionContext, session_scope

    set_user_skill_store(LocalUserSkillStore(tmp_path / "layer"))
    sk.save_user_skill(_text("owner-a-private", body="A-SECRET"), user_id="owner_a")

    # The index carries names; ``read_skill`` carries bodies. Both are A's, and
    # neither may cross.
    with session_scope(SessionContext(session_id="s", workspace=str(tmp_path), user_id="owner_a")):
        assert "owner-a-private" in sk.compose_skills_block()
        assert "A-SECRET" in sk.read_skill_file("owner-a-private")
    with session_scope(SessionContext(session_id="s", workspace=str(tmp_path), user_id="owner_b")):
        assert "owner-a-private" not in sk.compose_skills_block()
        with pytest.raises(sk.SkillError):
            sk.read_skill_file("owner-a-private")
    # No scope at all resolves to no owner: the built-in pack, never someone's.
    assert "owner-a-private" not in sk.compose_skills_block()


def test_the_hosted_key_is_derived_from_the_owner_alone(tmp_path):
    """No caller-supplied path segment, so no traversal and no collision: two
    owners cannot be talked into the same tree by anything they can send."""
    hosted = ObjectUserSkillStore(_RecordingStore(tmp_path))
    assert hosted.key_for("owner_a") != hosted.key_for("owner_b")
    assert "/" not in store_mod.owner_key("../../etc/passwd")
    assert store_mod.owner_key("owner_a") == store_mod.owner_key("owner_a")


# =============================================================================
# 5. One layering code path, two storage engines
# =============================================================================

class _RecordingStore:
    """A stand-in for GCS: tar-free, but the same get_tree/put_tree contract.

    There is no live bucket in CI, so the hosted leg is proven against a
    recording fake — stated plainly rather than claimed as coverage.
    """

    def __init__(self, root):
        self.root = root
        self.trees = {}

    def get_tree(self, key, local_dir):
        import os
        import shutil

        os.makedirs(local_dir, exist_ok=True)
        saved = self.trees.get(key)
        if saved is not None:
            shutil.copytree(saved, local_dir, dirs_exist_ok=True)

    def put_tree(self, key, local_dir):
        import shutil

        target = self.root / "stored" / key.replace("/", "_")
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(local_dir, target)
        self.trees[key] = target


def _layering_story(user_id):
    """The same sequence of gestures, whichever engine is installed."""
    name = _a_builtin()
    sk.save_user_skill(_text(name, body="MINE-BODY"), user_id=user_id)
    sk.save_user_skill(_text("my-own-thing", body="OWN-BODY"), user_id=user_id)
    sk.set_skill_enabled(_the_always_loaded(), False, user_id=user_id)
    resolved = sk.resolve_skills(user_id)
    return (
        [(e.name, e.layer, e.enabled) for e in resolved.entries],
        list(resolved.disabled),
        sk.read_skill_file(name, user_id=user_id),
    )


def test_the_layering_is_identical_in_both_storage_modes(tmp_path):
    set_user_skill_store(LocalUserSkillStore(tmp_path / "local"))
    self_host = _layering_story(None)

    set_user_skill_store(ObjectUserSkillStore(_RecordingStore(tmp_path)))
    hosted = _layering_story("owner_a")

    assert self_host == hosted


def test_the_hosted_store_pushes_only_a_clean_edit(tmp_path):
    recording = _RecordingStore(tmp_path)
    set_user_skill_store(ObjectUserSkillStore(recording))

    with pytest.raises(sk.SkillError):
        sk.save_user_skill(_text("../escape"), user_id="owner_a")
    assert recording.trees == {}

    sk.save_user_skill(_text("my-own-thing"), user_id="owner_a")
    assert list(recording.trees) == [ObjectUserSkillStore(recording).key_for("owner_a")]


def test_hosted_with_no_resolved_owner_gets_the_pack_and_nothing_else(tmp_path):
    set_user_skill_store(ObjectUserSkillStore(_RecordingStore(tmp_path)))
    assert [e.name for e in sk.resolve_skills(None).entries] == [s.name for s in _builtins()]
    with pytest.raises(PermissionError):
        sk.save_user_skill(_text("my-own-thing"), user_id=None)


def test_the_store_is_chosen_by_configuration_not_by_call_site(monkeypatch, tmp_path):
    """The engine-selection idiom: one factory, chosen once from settings."""
    set_user_skill_store(None)
    monkeypatch.setenv("USER_SKILLS_ENGINE", "local")
    monkeypatch.setenv("SILICONCREW_USER_SKILLS_DIR", str(tmp_path / "explicit"))
    assert isinstance(store_mod.get_user_skill_store(), LocalUserSkillStore)

    set_user_skill_store(None)
    monkeypatch.setenv("USER_SKILLS_ENGINE", "object")
    monkeypatch.setenv("WORKSPACE_BUCKET", "a-bucket")
    from src.platform_engines.settings import get_settings

    get_settings.cache_clear()
    try:
        assert isinstance(store_mod.get_user_skill_store(), ObjectUserSkillStore)
    finally:
        get_settings.cache_clear()
        set_user_skill_store(None)


# =============================================================================
# 6. The REST surface — owner-scoped by identity, never by anything sent
# =============================================================================

@pytest.fixture
def client(tmp_path, monkeypatch):
    """A TestClient whose caller identity is switchable, hosted-style.

    ``scoped_user_id`` is patched rather than the settings flag so the routes
    are exercised with a REAL tenant id — self-host's ``None`` owner would make
    every cross-tenant assertion below vacuously true.
    """
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    import api
    from src.platform_engines.identity import Identity

    set_user_skill_store(LocalUserSkillStore(tmp_path / "layer"))
    caller = {"id": "owner_a"}
    monkeypatch.setattr(api.auth_engine, "scoped_user_id", lambda identity: caller["id"])
    api.app.dependency_overrides[api.get_identity] = lambda: Identity(user_id=caller["id"])
    api.app.dependency_overrides[api.require_signed_in] = lambda: Identity(user_id=caller["id"])
    try:
        c = TestClient(api.app)
        c.become = lambda uid: caller.__setitem__("id", uid)
        yield c
    finally:
        api.app.dependency_overrides.clear()


def test_the_page_is_told_which_layer_answered(client):
    body = client.get("/api/skills").json()
    assert {s["layer"] for s in body["skills"]} == {sk.BUILTIN}
    assert [s["name"] for s in body["skills"]] == [s.name for s in _builtins()]
    assert sum(1 for s in body["skills"] if s["always_load"]) == 1

    name = _a_builtin()
    assert client.put(f"/api/skills/{name}", json={"text": _text(name)}).status_code == 200
    after = {s["name"]: s for s in client.get("/api/skills").json()["skills"]}
    assert after[name]["layer"] == sk.REPLACEMENT and after[name]["builtin_changed"] is False


def test_reading_one_skill_carries_the_shipped_text_beside_it(client):
    name = _a_builtin()
    client.put(f"/api/skills/{name}", json={"text": _text(name, body="MINE-BODY")})
    body = client.get(f"/api/skills/{name}").json()
    assert "MINE-BODY" in body["text"]
    assert body["builtin_text"] and "MINE-BODY" not in body["builtin_text"]

    client.delete(f"/api/skills/{name}")
    assert client.get(f"/api/skills/{name}").json()["text"] == body["builtin_text"]


def test_a_skill_saved_under_the_wrong_name_is_refused(client):
    assert client.put("/api/skills/one-name", json={"text": _text("another-name")}).status_code == 400
    assert client.put("/api/skills/x", json={"text": "not a skill"}).status_code == 400
    assert client.get("/api/skills/one-name").status_code == 404


def test_one_owners_skills_are_invisible_to_another_over_rest(client):
    client.put("/api/skills/my-own-thing", json={"text": _text("my-own-thing", body="A-SECRET")})
    client.put(f"/api/skills/{_a_builtin()}/enabled", json={"enabled": False})

    client.become("owner_b")
    names = [s["name"] for s in client.get("/api/skills").json()["skills"]]
    assert "my-own-thing" not in names
    assert names == [s.name for s in _builtins()]
    assert client.get("/api/skills/my-own-thing").status_code == 404
    # ...and B cannot reset or switch off something that is not theirs.
    assert client.delete("/api/skills/my-own-thing").status_code == 404


def test_the_page_can_clear_a_choice_that_no_longer_matches_anything(client, tmp_path):
    store_mod.write_config(
        tmp_path / "layer" / store_mod.owner_key("owner_a"),
        {"disabled": ["a-skill-that-was-renamed"], "forked": {}},
    )
    assert client.get("/api/skills").json()["unmatched_disabled"] == ["a-skill-that-was-renamed"]
    assert client.put("/api/skills/a-skill-that-was-renamed/enabled",
                      json={"enabled": True}).status_code == 200
    assert client.get("/api/skills").json()["unmatched_disabled"] == []
