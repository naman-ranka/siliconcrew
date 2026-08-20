"""The skill store: discovered, portable, and named nowhere in the code.

Three properties are worth a test each, and they are the three that would rot
silently:

1. **The shipped pack is valid Agent Skills.** A non-spec frontmatter key is a
   HARD ERROR in other clients — they refuse the file — so a stray key would
   quietly make our pack unusable in the exact places portability was the point.
2. **Nothing enumerates skills.** The moment a skill name is typed into Python
   or TypeScript there are two lists, and the one in code wins while the
   directory says otherwise.
3. **The always-loaded skill really is always loaded, on every runtime.** Its
   failure mode is silence: nothing in the environment ever says "your test was
   too easy", so a runtime that quietly composed without it would look fine.
"""
from __future__ import annotations

import os
import re

import pytest

from src.utils import skills as sk

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _write_skill(root, name, description="Does a thing when a thing is needed.",
                 body="# Body\n\nDo the thing.", extra_frontmatter=""):
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n{extra_frontmatter}---\n\n{body}\n",
        encoding="utf-8",
    )
    return directory


# =============================================================================
# 1. The shipped pack
# =============================================================================

def _shipped():
    """The BUILT-IN pack, scanned at its root.

    Explicitly the root, not the default: with no root ``discover_skills``
    answers with the active set — built-ins layered with the caller's own
    skills — and these tests are about what SiliconCrew ships. Collection runs
    before fixtures, so this cannot lean on the layer isolation in conftest.
    """
    return sk.discover_skills(sk.SKILLS_ROOT)


def test_the_shipped_pack_is_not_empty():
    """Guards a vacuous suite: an empty store makes every assertion below pass
    by accident, and would silently ship an agent with no knowledge at all."""
    assert len(_shipped()) >= 5


@pytest.mark.parametrize("skill", _shipped(), ids=lambda s: s.name)
def test_every_shipped_skill_uses_only_spec_frontmatter(skill):
    """Re-parsed from disk, because that is what a foreign client does."""
    reparsed = sk.parse_skill_file(skill.path)
    assert reparsed.name == skill.path.parent.name
    assert 0 < len(reparsed.description) <= 1024
    assert reparsed.body.strip()


def test_a_non_spec_frontmatter_key_is_refused(tmp_path):
    """Claude Code answers a stray key with 'Unexpected key(s) in SKILL.md
    frontmatter'. Ours must fail here, in CI, not there."""
    _write_skill(tmp_path, "gadget", extra_frontmatter="when_to_use: always\n")
    with pytest.raises(sk.SkillError) as exc:
        sk.discover_skills(tmp_path)
    assert "when_to_use" in str(exc.value)


def test_a_name_that_disagrees_with_its_directory_is_refused(tmp_path):
    d = _write_skill(tmp_path, "gadget")
    (d / "SKILL.md").write_text(
        "---\nname: widget\ndescription: x\n---\n\nbody\n", encoding="utf-8"
    )
    with pytest.raises(sk.SkillError):
        sk.discover_skills(tmp_path)


def test_an_empty_body_is_refused(tmp_path):
    d = tmp_path / "gadget"
    d.mkdir()
    (d / "SKILL.md").write_text("---\nname: gadget\ndescription: x\n---\n", encoding="utf-8")
    with pytest.raises(sk.SkillError):
        sk.discover_skills(tmp_path)


def test_a_directory_without_a_skill_file_is_simply_not_a_skill(tmp_path):
    (tmp_path / "references").mkdir()
    _write_skill(tmp_path, "gadget")
    assert [s.name for s in sk.discover_skills(tmp_path)] == ["gadget"]


# =============================================================================
# 2. Discovery, not enumeration
# =============================================================================

def test_adding_a_directory_adds_a_skill_with_no_code_change(tmp_path):
    _write_skill(tmp_path, "alpha")
    assert [s.name for s in sk.discover_skills(tmp_path)] == ["alpha"]
    _write_skill(tmp_path, "beta")
    assert [s.name for s in sk.discover_skills(tmp_path)] == ["alpha", "beta"]


def test_no_source_file_names_a_skill():
    """The failure this wave exists to remove. A skill name written into code is
    a second list: rename or retire the skill and the code keeps asserting the
    old name, or worse keeps loading it.

    Prose is exempt (docs and the pack's own README describe the pack), as is
    this file, which must name them to prove the rule."""
    names = [s.name for s in _shipped()]
    assert names
    skip_dirs = {".git", "node_modules", ".next", "__pycache__", ".venv", "venv",
                 "dist", "build", "out", "coverage", ".pytest_cache", "site-packages"}
    offenders = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for filename in filenames:
            if not filename.endswith((".py", ".ts", ".tsx")):
                continue
            path = os.path.join(dirpath, filename)
            rel = os.path.relpath(path, REPO_ROOT)
            if rel == os.path.join("tests", os.path.basename(__file__)):
                continue
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
            for name in names:
                if re.search(r"['\"]" + re.escape(name) + r"['\"]", text):
                    offenders.append(f"{rel}: {name}")
    assert not offenders, (
        "skill name(s) hardcoded in source — discovery must be the only list:\n  "
        + "\n  ".join(sorted(offenders))
    )


# =============================================================================
# 3. The always-loaded skill
# =============================================================================

def test_exactly_one_shipped_skill_is_always_loaded():
    always = [s.name for s in _shipped() if s.always_load]
    assert len(always) == 1, f"always-loaded skills: {always}"


def test_the_always_load_flag_is_read_from_the_file(tmp_path):
    """A3-M3, decided: the designation lives in the skill's own frontmatter,
    under the spec's ``metadata`` map, not in a Python constant. Proof: the same
    code reads it both ways depending only on the file."""
    _write_skill(tmp_path, "quiet")
    assert sk.discover_skills(tmp_path)[0].always_load is False
    _write_skill(
        tmp_path, "quiet",
        extra_frontmatter=f'metadata:\n  {sk.ALWAYS_LOAD_KEY}: "true"\n',
    )
    assert sk.discover_skills(tmp_path)[0].always_load is True


def test_the_composed_block_carries_the_index_and_only_always_loaded_bodies(tmp_path):
    _write_skill(tmp_path, "quiet", body="QUIET-BODY")
    _write_skill(tmp_path, "loud", body="LOUD-BODY",
                 extra_frontmatter=f'metadata:\n  {sk.ALWAYS_LOAD_KEY}: "true"\n')
    block = sk.compose_skills_block(sk.discover_skills(tmp_path))

    assert "- quiet:" in block and "- loud:" in block   # both in the index...
    assert "LOUD-BODY" in block                          # ...one body pasted...
    assert "QUIET-BODY" not in block                     # ...the other on demand


def test_an_absent_store_composes_to_nothing(tmp_path):
    assert sk.compose_skills_block(sk.discover_skills(tmp_path / "nope")) == ""


# =============================================================================
# 4. Delivery — every runtime gets the same bytes
# =============================================================================

def _always_loaded_body():
    return next(s.body for s in _shipped() if s.always_load)


def test_the_system_prompt_carries_the_index_and_the_always_loaded_body():
    from src.utils.architect_prompt import load_system_prompt

    prompt = load_system_prompt()
    for skill in _shipped():
        assert f"- {skill.name}:" in prompt
    assert _always_loaded_body().splitlines()[0] in prompt


def test_the_prompt_file_itself_names_no_skill():
    """The index is composed, never typed into the prompt — otherwise the prompt
    is the second list."""
    from src.utils.architect_prompt import load_system_prompt, prompt_path

    file_only = load_system_prompt(prompt_path(), with_skills=False)
    for skill in _shipped():
        assert skill.name not in file_only


def test_the_codex_runtime_composes_the_same_block():
    """A3-H2: Codex has none of our middleware, so a block composed only on the
    native side would leave the runtime the stranger test measures without the
    one skill that has no trigger."""
    from src.agents.codex.codex_runtime import CodexRuntimeHandler
    from src.utils.architect_prompt import load_system_prompt

    handler = CodexRuntimeHandler(
        codex_store=None, session_manager=None,
        llm_key_resolve=lambda uid, model: None,
        account_home_for=lambda uid: None,
        system_prompt_loader=load_system_prompt,
        default_model="m", normalize_model=lambda m: m,
        enabled=False,
    )
    composed = handler._system_prompt()
    assert composed.startswith(load_system_prompt())
    assert _always_loaded_body().splitlines()[0] in composed


def test_api_wires_the_composing_loader_into_the_codex_runtime():
    """The composition rides the prompt loader, so the wiring IS the guarantee."""
    with open(os.path.join(REPO_ROOT, "api.py"), encoding="utf-8-sig") as fh:
        source = fh.read()
    assert "system_prompt_loader=load_system_prompt" in source


def test_the_drift_guard_actually_scans_the_skill_bodies():
    """A3-H5: a skill telling the agent to call a tool that no longer exists is
    the same silent rot as a stale prompt. It is covered because SKILL.md is
    markdown inside the repo — pinned here so a future scope change to the
    scanner cannot drop the pack without a red test."""
    from tests.test_tool_name_drift import iter_repo_files

    scanned = {rel for rel, _ in iter_repo_files()}
    for skill in _shipped():
        rel = os.path.relpath(str(skill.path), REPO_ROOT)
        assert rel in scanned, f"{rel} is outside the tool-name drift scan"


# =============================================================================
# 5. Reading a skill
# =============================================================================

def test_read_skill_returns_the_file_and_its_references(tmp_path):
    directory = _write_skill(tmp_path, "gadget", body="GADGET-BODY")
    (directory / "references").mkdir()
    (directory / "references" / "extra.md").write_text("EXTRA", encoding="utf-8")

    assert "GADGET-BODY" in sk.read_skill_file("gadget", root=tmp_path)
    assert sk.read_skill_file("gadget", "references/extra.md", root=tmp_path) == "EXTRA"


def test_read_skill_refuses_to_leave_the_skill_directory(tmp_path):
    _write_skill(tmp_path, "gadget")
    (tmp_path / "secret.md").write_text("SECRET", encoding="utf-8")
    with pytest.raises(sk.SkillError):
        sk.read_skill_file("gadget", "../secret.md", root=tmp_path)


def test_read_skill_names_what_exists_when_asked_for_what_does_not(tmp_path):
    _write_skill(tmp_path, "gadget")
    with pytest.raises(sk.SkillError) as exc:
        sk.read_skill_file("nope", root=tmp_path)
    assert "gadget" in str(exc.value)


def test_the_tools_serve_discovery_not_a_copy_of_it():
    from src.tools.wrappers import list_skills, read_skill

    listed = list_skills.invoke({})
    assert listed == sk.skill_index()
    for skill in _shipped():
        assert f"- {skill.name}:" in listed
        assert skill.body.splitlines()[0] in read_skill.invoke({"name": skill.name})


# =============================================================================
# 6. Provenance
# =============================================================================

def test_provenance_records_the_pack_by_content(tmp_path):
    names, digest = sk.skills_provenance(sk.discover_skills(tmp_path))
    assert names == [] and digest.startswith("sha256:")

    _write_skill(tmp_path, "gadget", body="ONE")
    names_one, digest_one = sk.skills_provenance(sk.discover_skills(tmp_path))
    _write_skill(tmp_path, "gadget", body="TWO")
    names_two, digest_two = sk.skills_provenance(sk.discover_skills(tmp_path))

    assert names_one == names_two == ["gadget"]   # the name says nothing...
    assert digest_one != digest_two               # ...the content does


def test_a_turn_stamps_the_skills_it_ran_under():
    import src.platform_engines.provenance as prov

    stamp = prov.resolve_agent_provenance(user_id="owner_a")
    assert stamp.skills_loaded == [s.name for s in _shipped()]
    assert stamp.skills_sha == sk.skills_provenance()[1]
