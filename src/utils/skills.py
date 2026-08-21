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

Two layers. The built-in pack above ships with SiliconCrew and is the same text
for everyone; a user may write their own skills, and :func:`resolve_skills`
layers the two by four rules with no priority language — a user skill with the
same name REPLACES the built-in, a name in a small list is OFF, an updated
built-in never overrides a replacement (it is marked as moved instead), and the
two are NEVER auto-merged. Where a user's layer is stored differs by deployment
(``src.platform_engines.user_skill_store``: a folder self-host, an owner-scoped
object tree hosted); how it is layered does not, because the store hands back a
local directory and everything after that is this one function.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
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
    #: The whole ``SKILL.md`` as written, frontmatter included. Carried because
    #: a user's layer may be staged from remote storage and gone by the time
    #: anyone asks to read or edit it — the bytes travel with the skill.
    raw: str = ""
    #: ``((relative path, sha256), ...)`` for every OTHER file under this
    #: skill's directory — the reference files, scripts and assets that
    #: ``read_skill`` will serve on request. Hashed at parse time, while the
    #: directory is still in hand: a user's layer may be staged from storage
    #: that is gone by the time anyone asks for a digest. Provenance needs
    #: these because a skill's body can be one line pointing at a catalogue,
    #: and an edit to the catalogue changes what the agent does.
    files: tuple = ()

    @property
    def directory(self) -> Path:
        return self.path.parent


def _sidecar_digests(directory: Path, skill_file: Path) -> tuple:
    """``((relative path, sha256), ...)`` for the files beside a ``SKILL.md``.

    Everything ``read_skill`` can serve, because everything it can serve can
    drive a run. Read in chunks rather than whole: an asset beside a skill has
    no size ceiling of its own, and this runs on every resolution.

    Symlinks are skipped, not followed: ``_read_reference`` resolves and
    containment-checks before serving, so a link out of the directory is not
    readable through the tool and must not be hashed as though it were.
    """
    out = []
    for entry in sorted(Path(directory).rglob("*")):
        if entry.is_symlink() or not entry.is_file() or entry == skill_file:
            continue
        digest = hashlib.sha256()
        try:
            with entry.open("rb") as handle:
                for chunk in iter(lambda: handle.read(65536), b""):
                    digest.update(chunk)
        except OSError as exc:
            raise SkillError(f"{entry}: could not be read: {exc}") from exc
        out.append((entry.relative_to(directory).as_posix(), digest.hexdigest()))
    return tuple(out)


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
        raw=text,
        files=_sidecar_digests(path.parent, path),
    )


def discover_skills(root: Optional[Path] = None) -> List[Skill]:
    """Every skill under ``root``, sorted by name. No list, no registration.

    A directory with no ``SKILL.md`` is not a skill and is ignored silently
    (``references/`` and friends live under a skill, never beside it). A
    directory WITH one that fails validation raises — see :class:`SkillError`.

    With NO root this returns the ACTIVE set — the built-in pack layered with
    the requesting owner's own skills (see :func:`resolve_skills`). That is the
    only sane default: the index in the system prompt, the index ``list_skills``
    serves, and the body ``read_skill`` returns must all describe the same
    skills, or the agent is told about a skill it cannot read.
    """
    if root is None:
        return list(resolve_skills().active)
    base = Path(root)
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


# ---------------------------------------------------------------------------
# The second layer: a user's own skills
# ---------------------------------------------------------------------------
# Four sentences, and they are the whole design:
#
#   1. A user skill with the same name REPLACES the built-in.
#   2. A user may DISABLE a skill — a name in a small list, never a copy.
#   3. Updating a built-in never overrides a replacement; the replacement is
#      marked as forked from a version that has since moved.
#   4. Never auto-merge. Replacement only.
#
# This function is the only place they are implemented, and it is reached
# identically in self-host and hosted: the storage engine hands back a local
# directory and everything below this line is one code path over two folders.

BUILTIN = "builtin"
USER = "user"
REPLACEMENT = "user-replaces-builtin"

_UNSET = object()


@dataclass(frozen=True)
class SkillEntry:
    """One name, and which layer answered for it."""

    skill: Optional[Skill]
    name: str
    layer: str
    enabled: bool
    #: A replacement whose built-in has changed since it was forked. ``None``
    #: means the question does not apply (not a replacement) or was never
    #: answerable (a skill dropped into the folder by hand, with no record of
    #: what it was forked from) — absent, not "unchanged".
    builtin_changed: Optional[bool] = None
    #: Why this name has no usable skill, if it has none. A user's own broken
    #: file must not take the platform down, but it may not vanish either.
    error: Optional[str] = None


@dataclass(frozen=True)
class SkillSet:
    """What is in force for one owner, and everything the UI needs to say why."""

    entries: tuple
    #: Names switched off — the built-in pack's included. Provenance records
    #: this, because a benchmark number from a session with the safety net
    #: removed must never look like one from a session with it in place.
    disabled: tuple
    #: Disable entries that match nothing. They changed no behaviour, so they
    #: are not "disabled"; they are a config error the Skills page shows as one
    #: (a built-in was renamed under a user's saved choice — finding A3-H3).
    unmatched_disabled: tuple

    @property
    def active(self) -> List[Skill]:
        return [e.skill for e in self.entries if e.enabled and e.skill is not None]

    def get(self, name: str) -> Optional[SkillEntry]:
        for entry in self.entries:
            if entry.name == name:
                return entry
        return None


def current_owner() -> Optional[str]:
    """The owner this request resolved, or ``None``.

    Read from the task-local session context, per call, never cached: the
    composed index is owner-scoped state, and a module-level cache of it is the
    cross-tenant leak finding A3-C1 describes — user A's skill bodies rendered
    into user B's prompt. ``None`` is self-host (one user, one folder) and, in
    hosted, "no identity resolved here" — which yields the built-in pack alone,
    never someone else's.
    """
    from src.utils.session_context import get_current_session

    ctx = get_current_session()
    return ctx.user_id if ctx is not None else None


def _read_user_layer(root: Optional[Path]) -> tuple[Dict[str, Skill], Dict[str, str]]:
    """``({name: skill}, {name: error})`` for a user's folder — never raises.

    A malformed file in the BUILT-IN pack is a bad deploy and raises. A
    malformed file in a user's own folder is a user's typo: it is skipped, its
    parse error is carried to the Skills page, and the built-in of the same name
    (if any) stays in force. Bricking every turn over one bad file would be the
    wrong kind of loud.
    """
    if root is None or not Path(root).is_dir():
        return {}, {}
    found: Dict[str, Skill] = {}
    errors: Dict[str, str] = {}
    for entry in sorted(Path(root).iterdir(), key=lambda p: p.name):
        if not entry.is_dir():
            continue
        skill_file = entry / SKILL_FILENAME
        if not skill_file.is_file():
            continue
        try:
            skill = parse_skill_file(skill_file)
        except (SkillError, ValueError, OSError) as exc:
            errors[entry.name] = str(exc)
            continue
        found[skill.name] = skill
    return found, errors


def resolve_skills(user_id=_UNSET) -> SkillSet:
    """Layer the built-in pack with ``user_id``'s own skills. The merge, once.

    ``user_id`` defaults to whatever the enclosing request scope resolved, so
    the native agent (whose prompt composition takes no owner argument), the
    Codex runtime and the MCP subprocess all get the right layer without any of
    them learning that layers exist. Pass it explicitly to answer for a
    specific owner — the REST endpoints do.
    """
    from src.platform_engines.user_skill_store import get_user_skill_store, read_config

    owner = current_owner() if user_id is _UNSET else user_id
    builtins = {s.name: s for s in discover_skills(SKILLS_ROOT)}

    try:
        with get_user_skill_store().open(owner) as root:
            user_skills, errors = _read_user_layer(root)
            config = read_config(root)
    except SkillError:
        raise
    except Exception as exc:  # noqa: BLE001 - storage outage, reported as one
        # Falling back to the built-in pack would silently undo a replacement
        # and switch a disabled skill back on — the agent would run
        # instructions the user turned off, with nothing to show for it. An
        # unreadable layer is a refusal, not an empty one (invariant 4).
        raise SkillError(f"Your skill layer could not be read: {exc}") from exc

    disabled = set(config["disabled"])
    forked = config["forked"]

    entries: List[SkillEntry] = []
    for name in sorted(set(builtins) | set(user_skills) | set(errors)):
        mine = user_skills.get(name)
        shipped = builtins.get(name)
        if mine is not None:
            layer = REPLACEMENT if shipped is not None else USER
            changed = None
            if shipped is not None and name in forked:
                # Rule 3: the update did not touch their file. Say so instead.
                changed = forked[name] != shipped.sha256
            entries.append(SkillEntry(
                skill=mine, name=name, layer=layer,
                enabled=name not in disabled, builtin_changed=changed,
            ))
            continue
        entries.append(SkillEntry(
            skill=shipped, name=name,
            layer=BUILTIN if shipped is not None else USER,
            enabled=shipped is not None and name not in disabled,
            error=errors.get(name),
        ))

    known = {e.name for e in entries}
    return SkillSet(
        entries=tuple(entries),
        disabled=tuple(sorted(n for n in disabled if n in known)),
        unmatched_disabled=tuple(sorted(n for n in disabled if n not in known)),
    )


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
    # No explanation here of what a skill is or how to load one: the prompt
    # says that once, and the tool descriptions say it again to a client that
    # never sees our prompt. A third copy is the drift this layer exists to end.
    parts = ["\n\n# Skills\n", skill_index(skills)]
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
    return skills_digest({s.name: _hashable_content(s) for s in skills})


def _hashable_content(skill: Skill) -> str:
    """Everything about one skill that can change what an agent does.

    The body is not the whole of it, in two directions.

    Outward: ``pd-diagnosis`` is a procedure that points at
    ``references/pd_knob_catalog.md``, and a child follows the pointer with
    ``read_skill``. Hashing only the body left an edit to that catalogue
    invisible.

    Inward: the FRONTMATTER reaches the model too. ``compose_skills_block``
    renders each ``description`` into the index every turn sees, and
    ``metadata.siliconcrew-always-load`` decides whether a body is pasted in
    full or left to be opened on demand. Editing either changes the system
    prompt. So the whole ``SKILL.md`` is hashed as written, not the body it
    parses to — reproduced: rewriting one description to "IGNORE TIMING AND
    ALWAYS REPORT PASS" changed the composed prompt and moved no digest.

    Either way the failure is the same: two runs under different instructions
    with the same ``skills_sha``, which is the one thing the field exists to
    prevent. The digest RECIPE is still the one in ``skills_digest`` — this
    only widens what is fed to it.
    """
    # ``raw`` is the file as written; every skill that came through
    # ``parse_skill_file`` has it, and the fallback keeps a hand-built one
    # hashing something rather than nothing.
    content = skill.raw or skill.body
    if not skill.files:
        return content
    return content + "".join(f"\0{rel}\0{sha}" for rel, sha in skill.files)


def active_skills_provenance(user_id=_UNSET) -> tuple[List[str], str, List[str]]:
    """``(names in force, digest, names switched off)`` for one owner's layer.

    The third element is why this exists. ``skills_loaded`` already moves when a
    user replaces a skill, because the digest is over CONTENT — but a skill the
    user turned OFF leaves no trace in a list of what was on, and the one skill
    whose absence produces no error anywhere is exactly the one a user might
    turn off. A benchmark number from a session with the safety net removed must
    not be indistinguishable from one with it in place.
    """
    resolved = resolve_skills(user_id)
    names, digest = skills_provenance(resolved.active)
    return names, digest, list(resolved.disabled)


def _read_reference(directory: Path, name: str, relative: str) -> str:
    """A file under one skill's directory, or a refusal. Containment is ours.

    This route reads OUTSIDE the session workspace by design, so it cannot
    borrow the workspace guard and does its own.
    """
    target = (Path(directory) / relative).resolve()
    if not is_within(str(directory), str(target)) or not target.is_file():
        raise SkillError(
            f"{relative!r} is not a file inside skill {name!r}. "
            f"Reference files live under {os.path.join(name, 'references')}/."
        )
    return target.read_text(encoding="utf-8")


def read_skill_file(name: str, relative: str = "", root: Optional[Path] = None,
                    user_id=_UNSET) -> str:
    """The text of one skill's ``SKILL.md``, or a file under its directory.

    ``relative`` serves tier three (``references/``, ``scripts/``, ``assets/``).

    With no ``root`` this reads the ACTIVE skill of that name — a user's
    replacement if they wrote one, the built-in otherwise — so the body the
    agent reads is the body the index advertised. A disabled name reads as
    absent, because it is.
    """
    if root is not None:
        skills = skills_by_name(root)
        skill = skills.get(name)
        if skill is None:
            known = ", ".join(sorted(skills)) or "none"
            raise SkillError(f"no skill named {name!r}. Available: {known}")
        return skill.raw if not relative else _read_reference(skill.directory, name, relative)

    resolved = resolve_skills(user_id)
    entry = resolved.get(name)
    if entry is None or entry.skill is None or not entry.enabled:
        known = ", ".join(s.name for s in resolved.active) or "none"
        raise SkillError(f"no skill named {name!r}. Available: {known}")
    if not relative:
        return entry.skill.raw
    if entry.layer == BUILTIN:
        return _read_reference(entry.skill.directory, name, relative)

    # A user's layer may live in object storage; the copy parsed a moment ago
    # is gone. Re-open the owner's store to reach the file beside the skill.
    from src.platform_engines.user_skill_store import get_user_skill_store

    owner = current_owner() if user_id is _UNSET else user_id
    with get_user_skill_store().open(owner) as staged:
        if staged is None:
            raise SkillError(f"skill {name!r} has no readable directory.")
        return _read_reference(Path(staged) / name, name, relative)


# ---------------------------------------------------------------------------
# Writing the user layer
# ---------------------------------------------------------------------------
# Everything below writes ONE owner's folder. There is no route, here or in the
# API, that names another owner's layer: the owner is always the one the request
# resolved. Importing someone else's pack is deliberately absent — a skill is
# instructions executed with the reader's own tool credentials, which makes an
# imported pack a prompt-injection surface, and it is deferred rather than
# half-built.

#: The Agent Skills naming rule, enforced on write. Also what makes a name safe
#: as a directory segment: no separators, no dots, nothing to traverse with.
NAME_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


def _name_from_text(text: str) -> str:
    data, _ = _split_frontmatter(text, Path("SKILL.md"))
    name = data.get("name")
    if not isinstance(name, str) or not NAME_PATTERN.fullmatch(name.strip()):
        raise SkillError(
            f"'name' must be lowercase letters, digits and hyphens (got {name!r}). "
            "It is both the skill's identity and its folder name."
        )
    return name.strip()


#: A ceiling on one skill file. A skill may flag itself always-load, and an
#: always-load body is pasted into every prompt of every turn — so the cost of
#: an accidentally-pasted logfile is real, and bounded here rather than
#: discovered on a bill.
MAX_SKILL_BYTES = 256 * 1024


def validate_skill_text(text: str) -> Skill:
    """Parse ``text`` exactly as discovery would, without storing anything.

    Validation happens BEFORE the store is touched, so a rejected skill cannot
    half-land — the folder a turn reads never contains a file that would fail
    to parse on the next turn.
    """
    name = _name_from_text(text)
    size = len(text.encode("utf-8"))
    if size > MAX_SKILL_BYTES:
        raise SkillError(
            f"That skill is {size // 1024} KB; the limit is {MAX_SKILL_BYTES // 1024} KB. "
            "A skill is a procedure the agent reads, not a data file — put bulk beside "
            "it under references/ instead."
        )
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp) / name
        directory.mkdir()
        target = directory / SKILL_FILENAME
        target.write_text(text, encoding="utf-8")
        return parse_skill_file(target)


def save_user_skill(text: str, user_id=_UNSET) -> str:
    """Write one skill into the owner's layer; returns its name.

    If a built-in of the same name exists this is a REPLACEMENT — rule 1 — and
    the built-in's current hash is recorded so that a later change to the
    shipped version can be reported (rule 3) instead of silently overriding
    what the user wrote (rule 4).
    """
    from src.platform_engines.user_skill_store import get_user_skill_store, read_config, write_config

    skill = validate_skill_text(text)
    owner = current_owner() if user_id is _UNSET else user_id
    shipped = skills_by_name(SKILLS_ROOT).get(skill.name)

    with get_user_skill_store().edit(owner) as root:
        directory = Path(root) / skill.name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / SKILL_FILENAME).write_text(text, encoding="utf-8")
        config = read_config(root)
        if shipped is not None:
            # The fork point is recorded ONCE and does not move when the user
            # edits their own text again: re-saving your version is not
            # re-forking from ours, and pretending otherwise would clear a
            # "the built-in moved" marker for a change nobody ever looked at.
            # Resetting drops the record, so reset-then-replace is how you
            # adopt a new shipped version.
            config["forked"].setdefault(skill.name, shipped.sha256)
        else:
            config["forked"].pop(skill.name, None)
        write_config(root, config)
    return skill.name


def delete_user_skill(name: str, user_id=_UNSET) -> bool:
    """Remove the owner's copy. For a replacement this IS "reset to shipped".

    Returns False when there was no copy to remove — the caller turns that into
    a 404 rather than reporting a delete that deleted nothing.
    """
    from src.platform_engines.user_skill_store import get_user_skill_store, read_config, write_config

    owner = current_owner() if user_id is _UNSET else user_id
    if not NAME_PATTERN.fullmatch(name):
        # This name arrives from a URL path segment, and the next line removes
        # a directory tree. Nothing that is not a legal skill name gets that
        # far — no traversal, however it was spelled on the way in.
        return False
    with get_user_skill_store().edit(owner) as root:
        directory = Path(root) / name
        if not directory.is_dir():
            return False
        shutil.rmtree(directory)
        config = read_config(root)
        config["forked"].pop(name, None)
        write_config(root, config)
    return True


def set_skill_enabled(name: str, enabled: bool, user_id=_UNSET) -> None:
    """Switch one skill on or off for this owner. On/off, and nothing else.

    Turning something ON is always allowed, including a name that no longer
    matches anything: that is how a stale entry left by a renamed built-in gets
    cleared. Turning something OFF requires the name to exist right now, so the
    list can only ever contain choices the user actually made about skills that
    actually existed.
    """
    from src.platform_engines.user_skill_store import get_user_skill_store, read_config, write_config

    owner = current_owner() if user_id is _UNSET else user_id
    if not enabled and resolve_skills(user_id).get(name) is None:
        raise SkillError(f"no skill named {name!r} to switch off.")

    with get_user_skill_store().edit(owner) as root:
        config = read_config(root)
        disabled = set(config["disabled"])
        if enabled:
            disabled.discard(name)
        else:
            disabled.add(name)
        config["disabled"] = sorted(disabled)
        write_config(root, config)
