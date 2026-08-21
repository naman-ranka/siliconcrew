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


def test_editing_a_reference_file_moves_the_digest(tmp_path):
    """A skill can be a pointer, and the thing it points at drives the run.

    ``pd-diagnosis`` is a procedure whose knob table lives in
    ``references/pd_knob_catalog.md``, and a sweep child follows the pointer
    with ``read_skill``. Hashing only ``SKILL.md`` bodies left an edit to that
    table invisible: two runs tuned by different instructions recorded the same
    ``skills_sha``, which is the one thing that field exists to prevent.
    """
    root = tmp_path / "pack"
    directory = root / "pointing-skill"
    (directory / "references").mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: pointing-skill\ndescription: Follow the catalogue.\n---\n\n"
        "Read references/catalogue.md and do what it says.\n",
        encoding="utf-8",
    )
    catalogue = directory / "references" / "catalogue.md"
    catalogue.write_text("Set utilisation to 60%.\n", encoding="utf-8")

    before = sk.skills_provenance(sk.discover_skills(root))[1]
    catalogue.write_text("Set utilisation to 5%.\n", encoding="utf-8")
    after = sk.skills_provenance(sk.discover_skills(root))[1]

    assert before != after, (
        "the reference file changed what the agent would do and the digest did "
        "not move: two runs under different instructions are indistinguishable"
    )
    # The body alone is unchanged — so a body-only digest could not have moved.
    assert sk.discover_skills(root)[0].body == (
        "Read references/catalogue.md and do what it says."
    )


def test_editing_frontmatter_that_reaches_the_model_moves_the_digest(tmp_path):
    """The frontmatter is not metadata about the prompt; it is IN the prompt.

    ``compose_skills_block`` renders every ``description`` into the index each
    turn sees, and ``metadata.siliconcrew-always-load`` decides whether a body
    is pasted in full. Hashing the parsed body alone let either change the
    system prompt while ``skills_sha`` stood still — so a skill whose one-line
    description had been rewritten to say the opposite of its procedure would
    produce runs indistinguishable from runs made before the rewrite.
    """
    root = tmp_path / "pack"
    directory = root / "a-skill"
    directory.mkdir(parents=True)
    skill_file = directory / "SKILL.md"

    def write(description: str, always: bool) -> None:
        meta = '\nmetadata:\n  siliconcrew-always-load: "true"\n' if always else "\n"
        skill_file.write_text(
            f"---\nname: a-skill\ndescription: {description}{meta}---\n\nThe procedure.\n",
            encoding="utf-8",
        )

    write("Do the careful thing.", False)
    base_digest = sk.skills_provenance(sk.discover_skills(root))[1]
    base_block = sk.compose_skills_block(sk.discover_skills(root))

    write("Skip every check.", False)
    assert sk.compose_skills_block(sk.discover_skills(root)) != base_block
    assert sk.skills_provenance(sk.discover_skills(root))[1] != base_digest, (
        "the description reaches the model through the index, and the digest "
        "did not move"
    )

    write("Do the careful thing.", True)
    assert sk.compose_skills_block(sk.discover_skills(root)) != base_block
    assert sk.skills_provenance(sk.discover_skills(root))[1] != base_digest, (
        "always-load decides whether the whole body is pasted into the prompt, "
        "and the digest did not move"
    )
    # The parsed body never changed across any of it — a body-only digest
    # could not have caught either edit.
    assert sk.discover_skills(root)[0].body == "The procedure."


def test_repointing_a_readable_symlink_moves_the_digest(tmp_path):
    """``read_skill`` serves a link that stays inside the skill directory.

    The first version of this hash skipped every symlink, reasoning that a link
    OUT of the directory is refused by ``_read_reference``. True, and it
    quietly generalised to links that point back INSIDE — which are served. A
    stable name like ``references/live.md`` could be repointed from one
    catalogue to another, changing what the agent read, with nothing in the
    record moving.
    """
    root = tmp_path / "pack"
    references = root / "s" / "references"
    references.mkdir(parents=True)
    (root / "s" / "SKILL.md").write_text(
        "---\nname: s\ndescription: d\n---\n\nRead references/live.md and obey it.\n",
        encoding="utf-8",
    )
    (references / "careful.md").write_text("Set utilisation to 60%.\n", encoding="utf-8")
    (references / "reckless.md").write_text("Set utilisation to 5%.\n", encoding="utf-8")
    os.symlink("careful.md", references / "live.md")

    before = sk.skills_provenance(sk.discover_skills(root))[1]
    # What the tool serves through that name really does change.
    assert "60%" in sk.read_skill_file("s", "references/live.md", root=root)

    (references / "live.md").unlink()
    os.symlink("reckless.md", references / "live.md")

    assert "5%" in sk.read_skill_file("s", "references/live.md", root=root)
    assert sk.skills_provenance(sk.discover_skills(root))[1] != before, (
        "the link was repointed at different instructions and the digest did "
        "not move"
    )


def test_a_symlinked_directory_does_not_hang_discovery(tmp_path):
    """A link to its own ancestor is a loop; the walk must not follow it."""
    root = tmp_path / "pack"
    directory = root / "s"
    directory.mkdir(parents=True)
    (directory / "SKILL.md").write_text(
        "---\nname: s\ndescription: d\n---\n\nBody.\n", encoding="utf-8"
    )
    os.symlink(directory, directory / "loop")

    skills = sk.discover_skills(root)  # must terminate
    assert [s.name for s in skills] == ["s"]
    assert any(rel.startswith("loop") for rel, _ in skills[0].files)


def test_a_reference_file_is_named_in_the_skill_it_belongs_to():
    """The digest is over content, but what was hashed must be inspectable."""
    by_name = {s.name: s for s in sk.discover_skills(sk.SKILLS_ROOT)}
    withref = [s for s in by_name.values() if s.files]
    assert withref, "the shipped pack has a skill with a reference file"
    for skill in withref:
        for relative, digest in skill.files:
            assert not relative.startswith("/") and ".." not in relative
            assert len(digest) == 64
            # Every hashed path is one read_skill can actually serve.
            assert sk.read_skill_file(skill.name, relative, root=sk.SKILLS_ROOT)

