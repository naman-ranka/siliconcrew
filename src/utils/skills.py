"""The skill store — discovery, the index, and the one composed block.

A skill is hard-won procedure that the agent needs only sometimes: how to
diagnose a physical-design failure, how to earn a passing testbench, how to
sweep a Pareto frontier. Keeping that text in the system prompt taxes every
turn of every session with knowledge most turns never use, and the prompt it
came out of proved the cost — 128 lines of which 12 were identity and 27 were
dead. Skills are the on-demand half: the model sees a name and one line, and
reads the body when the situation matches.

Format: the Agent Skills standard (``<name>/SKILL.md`` with YAML frontmatter),
adopted verbatim. Only the six SPEC fields are accepted — ``name``,
``description``, ``license``, ``compatibility``, ``metadata``,
``allowed-tools`` — and :func:`parse_skill_file` REJECTS anything else, because
a non-spec key is a hard error in other clients (Claude Code refuses the file
outright) and portability is the entire reason for adopting someone else's
format instead of inventing one.

Location: ``skills/`` at the repo root, deliberately NOT the magic
``.agents/skills/``. A foreign client whose own scanner walks parent
directories would load a magic directory directly, bypassing our merge rules
and provenance — a skill recorded as inactive would still be running, which is
the honest-state invariant broken by a directory name. The magic layout belongs
only in a copy a user clones into their own project.

Always-loaded (finding A3-M3, decided here). ``self-verification-standard`` is
the one skill that must be in force with no trigger: every other skill has a
loud one (WNS < 0, ``test_failed``, "sweep the frontier"), but nothing in the
environment ever says "your test was too easy", so its failure mode is silent.
The flag lives in the SKILL FILE, as ``metadata.siliconcrew-always-load:
"true"`` — a spec frontmatter field, namespaced, ignored by any client that
does not know it. The alternative was a constant in Python, and a constant is a
hardcoded skill name: the exact second list this wave exists to delete. Nothing
in this module, or anywhere in the repo, names a skill.

Discovery is a directory scan. Add a directory with a valid ``SKILL.md`` and it
is in the index; delete it and it is gone. There is no registration step and no
list to update.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import yaml

from src.utils.paths import is_within

_REPO_ROOT = Path(__file__).resolve().parents[2]

#: The built-in pack that ships with SiliconCrew. One store, workspace
#: independent: a skill is the same text for every session and every user, so
#: there is no per-workspace copy to drift and nothing to seed on fork.
SKILLS_ROOT = _REPO_ROOT / "skills"

SKILL_FILENAME = "SKILL.md"

#: The Agent Skills specification's complete frontmatter vocabulary.
SPEC_FRONTMATTER_KEYS = frozenset(
    {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
)

#: Our one extension, and it lives inside ``metadata`` where the spec puts
#: client-specific extras. See the module docstring for why it is a file field
#: and not a Python constant.
ALWAYS_LOAD_KEY = "siliconcrew-always-load"


class SkillError(RuntimeError):
    """A shipped skill file is malformed.

    Loud on purpose. The pack is part of the build, so a broken file is a bad
    deploy, not a user mistake — and a silently skipped skill is a rule the
    agent stops following with nothing to show for it. ``tests/test_skills.py``
    validates every shipped file, so this cannot reach a release.
    """


@dataclass(frozen=True)
class Skill:
    """One discovered skill. ``body`` is the markdown after the frontmatter."""

    name: str
    description: str
    body: str
    path: Path
    always_load: bool
    sha256: str

    @property
    def directory(self) -> Path:
        return self.path.parent


def _split_frontmatter(text: str, path: Path) -> tuple[dict, str]:
    """``(frontmatter mapping, body)`` for a ``SKILL.md``."""
    if not text.startswith("---"):
        raise SkillError(f"{path}: no YAML frontmatter (a SKILL.md must start with '---')")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SkillError(f"{path}: frontmatter is not closed by a second '---'")
    try:
        data = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError as exc:
        raise SkillError(f"{path}: frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SkillError(f"{path}: frontmatter must be a mapping, got {type(data).__name__}")
    return data, parts[2].strip()


def parse_skill_file(path: Path) -> Skill:
    """Read and validate one ``SKILL.md``.

    Validation is the spec's, not ours: the name is the directory name, the
    description is non-empty and within 1024 characters, and no key outside
    :data:`SPEC_FRONTMATTER_KEYS` may appear. That last rule is what keeps this
    pack loadable by Codex, Cursor, Gemini CLI and Claude Code unchanged.
    """
    path = Path(path)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SkillError(f"{path}: could not be read: {exc}") from exc
    text = raw.decode("utf-8")
    data, body = _split_frontmatter(text, path)

    unknown = sorted(set(data) - SPEC_FRONTMATTER_KEYS)
    if unknown:
        raise SkillError(
            f"{path}: non-spec frontmatter key(s) {unknown}. Allowed: "
            f"{sorted(SPEC_FRONTMATTER_KEYS)}. Client-specific values go under 'metadata'."
        )

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SkillError(f"{path}: 'name' is required and must be a non-empty string")
    name = name.strip()
    directory = path.parent.name
    if name != directory:
        raise SkillError(f"{path}: name {name!r} must match its directory name {directory!r}")

    description = data.get("description")
    if not isinstance(description, str) or not description.strip():
        raise SkillError(f"{path}: 'description' is required and must be a non-empty string")
    description = " ".join(description.split())
    if len(description) > 1024:
        raise SkillError(f"{path}: 'description' is {len(description)} chars; the spec allows 1024")

    metadata = data.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise SkillError(f"{path}: 'metadata' must be a mapping of strings")
    always = str(metadata.get(ALWAYS_LOAD_KEY, "")).strip().lower() in ("1", "true", "yes")

    if not body:
        raise SkillError(f"{path}: the body is empty; a skill with no procedure is not a skill")

    return Skill(
        name=name,
        description=description,
        body=body,
        path=path,
        always_load=always,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def discover_skills(root: Optional[Path] = None) -> List[Skill]:
    """Every skill under ``root``, sorted by name. No list, no registration.

    A directory with no ``SKILL.md`` is not a skill and is ignored silently
    (``references/`` and friends live under a skill, never beside it). A
    directory WITH one that fails validation raises — see :class:`SkillError`.
    """
    base = Path(root) if root is not None else SKILLS_ROOT
    if not base.is_dir():
        return []
    found: List[Skill] = []
    for entry in sorted(base.iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        skill_file = entry / SKILL_FILENAME
        if not skill_file.is_file():
            continue
        found.append(parse_skill_file(skill_file))
    return sorted(found, key=lambda s: s.name)


def skills_by_name(root: Optional[Path] = None) -> Dict[str, Skill]:
    return {s.name: s for s in discover_skills(root)}


def skill_index(skills: Optional[Sequence[Skill]] = None) -> str:
    """The progressive-disclosure index: one line per skill, nothing else.

    This is tier one of the three-tier loading model — roughly a hundred tokens
    that let the model decide whether a body is worth reading.
    """
    skills = discover_skills() if skills is None else skills
    lines = [f"- {s.name}: {s.description}" for s in skills]
    return "\n".join(lines)


def compose_skills_block(skills: Optional[Sequence[Skill]] = None) -> str:
    """The ONE block every runtime appends to the system prompt.

    Native agent, Codex runtime and any later composition call THIS function and
    get identical bytes. Three compositions would be three lists drifting apart,
    and the always-loaded skill would go missing on whichever one nobody
    remembered — which is precisely how it would go missing on the runtime the
    stranger test measures (finding A3-H2).

    Contents: the index, then the FULL BODY of every skill flagged always-load.
    Returns "" when the store is empty, so a build shipped without the pack adds
    nothing rather than an empty heading promising skills that do not exist.
    """
    skills = discover_skills() if skills is None else list(skills)
    if not skills:
        return ""
    parts = [
        "\n\n# Skills",
        "\nThese are available on demand. Read one with `read_skill(name)` when "
        "its description matches the situation you are in; `list_skills` "
        "re-lists them at any time.\n",
        skill_index(skills),
    ]
    for skill in skills:
        if not skill.always_load:
            continue
        # Always-loaded skills are pasted in full: their trigger is silence.
        parts.append(f"\n\n## Skill: {skill.name} (always in force)\n")
        parts.append(skill.body)
    return "\n".join(parts) + "\n"


def skills_provenance(skills: Optional[Sequence[Skill]] = None) -> tuple[List[str], str]:
    """``(names, "sha256:<hex>")`` for the skill set a turn ran under.

    The hash is over CONTENT — the same recipe
    :func:`src.platform_engines.provenance.skills_digest` fixes for every reader
    — never over a version string a file could claim and fail to match. Two
    benchmark numbers produced under different digests are not comparable, and
    this is what lets anyone tell.
    """
    from src.platform_engines.provenance import skills_digest

    skills = discover_skills() if skills is None else list(skills)
    return skills_digest({s.name: s.body for s in skills})


def read_skill_file(name: str, relative: str = "", root: Optional[Path] = None) -> str:
    """The text of one skill's ``SKILL.md``, or a file under its directory.

    ``relative`` serves tier three (``references/``, ``scripts/``, ``assets/``).
    It is resolved inside the skill's own directory and refused otherwise: this
    tool reads outside the session workspace by design, so it does its own
    containment rather than borrowing the workspace guard.
    """
    skills = skills_by_name(root)
    skill = skills.get(name)
    if skill is None:
        known = ", ".join(sorted(skills)) or "none"
        raise SkillError(f"no skill named {name!r}. Available: {known}")
    if not relative:
        return skill.path.read_text(encoding="utf-8")
    target = (skill.directory / relative).resolve()
    if not is_within(str(skill.directory), str(target)) or not target.is_file():
        raise SkillError(
            f"{relative!r} is not a file inside skill {name!r}. "
            f"Reference files live under {os.path.join(name, 'references')}/."
        )
    return target.read_text(encoding="utf-8")
