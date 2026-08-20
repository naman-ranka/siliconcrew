"""Provenance + determinism stamp (Phase 2, slice 7).

Every run is meant to be a pure function of (manifest subset + pinned toolchain)
in an isolated dir (see data-model.md). To make a run *reproducible* and
*auditable*, we stamp the toolchain identity onto it:

  * ``repo_commit``   — the SiliconCrew commit that produced the run
  * ``orfs_image_digest`` — the pinned ORFS image (``@sha256:...``), not a tag
  * ``pdk``           — the platform / PDK (e.g. sky130hd)
  * ``iverilog_version`` — the simulator build
  * ``num_cores``     — the pinned P&R parallelism (the only real nondeterminism
                        source; see config.mk pinning in synthesis_manager)

That answers "what toolchain built this". It does NOT answer "what *drove*
this" — which prompt, which knowledge, which tools were visible — so no
benchmark number could ever be attributed to a prompt version (finding B9). The
``AgentProvenance`` half below closes that gap:

  * ``prompt_version`` — the active architect prompt version (``v3``, ...)
  * ``prompt_sha``     — content hash of the prompt file actually used (a
                         version string alone is not enough: the file changes
                         without the version changing)
  * ``skills_loaded``  — names of the skill files in force
  * ``skills_sha``     — stable content hash of those skills
  * ``tool_set``       — identifier of the tool set the agent could see
  * ``context_edit``   — the context-compaction settings the turn ran under

The skill pair is filled in: a run made with a different set of skills, or with
one of them edited, is not the same experiment, and nothing else in the stamp
would show it. ``tool_set`` is still present and ABSENT — nothing resolves one
yet, and the later phase fills it with data rather than a new field.

``context_edit`` is filled in: once compaction is on, a long run reaches the
model with older tool results replaced by a placeholder, so it is not the same
experiment as the same prompt on an uncompacted run. Comparing two benchmark
numbers without knowing which side compacted would be comparing two different
inputs.

Collection is best-effort and never raises: a missing git binary or unpinned
image degrades to ``None``/``"unknown"`` rather than failing a synth run.
"""
from __future__ import annotations

import hashlib
import os
import re
import subprocess
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterator, List, Mapping, Optional, Tuple

# Where versioned architect prompts live — the same tree
# ``src.agents.architect`` resolves ``PROMPT_FILE_DEFAULT`` from. Kept here
# dependency-free on purpose: importing the agent module would drag LangGraph
# and the whole tool registry into every worker that stamps a run.
# ``test_prompt_identity_matches_architect_resolution`` pins the two together
# so this copy cannot drift.
PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "architect"


@dataclass(frozen=True)
class AgentProvenance:
    """What DROVE a turn: the prompt, the knowledge, the visible tool set.

    Empty-value convention — read this before writing any of these fields:

    * ``None`` means **absent**: nothing resolved this. For ``skills_loaded``
      that reads "this build has no skill layer, or no request scope resolved
      one", NOT "the user chose to load no skills".
    * ``[]`` means **recorded and empty**: a resolver actually looked and found
      nothing enabled — a choice was made. Only a resolver that really looked
      may write it.

    ``tool_set`` is ``None`` on every run today, and that is the honest
    reading: tool sets are not implemented yet.
    """

    prompt_version: Optional[str] = None
    prompt_sha: Optional[str] = None
    skills_loaded: Optional[List[str]] = None
    skills_sha: Optional[str] = None
    tool_set: Optional[str] = None
    context_edit: Optional[str] = None


@dataclass(frozen=True)
class Provenance:
    repo_commit: str
    orfs_image_digest: Optional[str] = None
    pdk: Optional[str] = None
    iverilog_version: Optional[str] = None
    num_cores: Optional[int] = None
    # --- what drove the run (B9 / R2-6); see AgentProvenance for the
    # None-vs-[] convention. Absent on runs recorded before this existed.
    prompt_version: Optional[str] = None
    prompt_sha: Optional[str] = None
    skills_loaded: Optional[List[str]] = None
    skills_sha: Optional[str] = None
    tool_set: Optional[str] = None
    context_edit: Optional[str] = None

    def as_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def repo_commit() -> str:
    """The current repo commit — env override first, then git, then 'unknown'."""
    env = os.environ.get("SILICONCREW_COMMIT") or os.environ.get("GIT_COMMIT")
    if env:
        return env.strip()
    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


@lru_cache(maxsize=1)
def iverilog_version() -> Optional[str]:
    try:
        out = subprocess.run(["iverilog", "-V"], capture_output=True, text=True, timeout=5)
        first = (out.stdout or out.stderr or "").splitlines()
        if first:
            m = re.search(r"version\s+(\S+)", first[0])
            return m.group(1) if m else first[0].strip()
    except Exception:
        pass
    return None


def orfs_image_digest(image: Optional[str] = None) -> Optional[str]:
    """Return the pinned image digest if the configured image is digest-pinned."""
    image = image or os.environ.get("ORFS_IMAGE", "")
    explicit = os.environ.get("ORFS_IMAGE_DIGEST")
    if explicit:
        return explicit.strip()
    if image and "@sha256:" in image:
        return image.split("@", 1)[1]
    return None


# ---------------------------------------------------------------------------
# Prompt identity
# ---------------------------------------------------------------------------

def active_prompt_version() -> str:
    """The architect prompt version in force — same rule as ``load_system_prompt``.

    Read at call time rather than import time so a process that changes the env
    stamps what it will actually use.
    """
    version = (os.environ.get("ARCHITECT_PROMPT_VERSION", "v3") or "v3").strip().lower()
    return version or "v3"


def active_prompt_path(version: Optional[str] = None) -> Path:
    """The prompt file ``load_system_prompt`` would read for ``version``."""
    return PROMPTS_DIR / f"architect_prompt_{version or active_prompt_version()}.md"


def prompt_identity(prompt_path: Optional[Path] = None) -> Tuple[Optional[str], Optional[str]]:
    """``(prompt_version, prompt_sha)`` for the prompt actually on disk.

    ``prompt_sha`` is ``sha256:<hex>`` over the file's exact bytes, so an edit
    that leaves ``PROMPT_VERSION`` untouched still moves the hash — the whole
    point of carrying both.

    If the file is missing, unreadable or empty, ``load_system_prompt`` raises
    ``PromptUnavailable`` — no agent turn ran on it — so we cannot attribute
    anything to a prompt file and BOTH come back ``None`` (absent) rather than
    naming a file that was never read. Stamping a run must never be the thing
    that fails a run, so unlike ``load_system_prompt`` this never raises.
    """
    version = active_prompt_version()
    path = Path(prompt_path) if prompt_path is not None else active_prompt_path(version)
    try:
        data = path.read_bytes()
    except Exception:
        return None, None
    if not data.strip():
        # An empty file is the same fallback path in load_system_prompt.
        return None, None
    return version, "sha256:" + hashlib.sha256(data).hexdigest()


def context_edit_identity() -> str:
    """The context-compaction settings this process would run a turn under.

    Compaction is process-wide config, not owner state — the same argument that
    lets the prompt pair be resolved here — so this reads the settings directly
    and carries no tenancy risk.

    The string is deliberately flat and greppable rather than a nested block:
    ``"off"`` or ``"clear_tool_uses:trigger=<tokens>,keep=<n>"``. It is built
    from the SAME two settings ``src.agents.architect.context_compaction_middleware``
    builds the middleware from, and this module stays free of the LangGraph
    import (the reason ``active_prompt_version`` re-implements its rule too);
    ``test_provenance_context_edit_matches_the_middleware_actually_shipped``
    is what keeps the two honest.

    Never raises: stamping a run must not be the thing that fails a run.
    """
    try:
        from src.platform_engines.settings import get_settings

        settings = get_settings()
        trigger = int(settings.chat_context_edit_trigger)
        if trigger <= 0:
            return "off"
        return f"clear_tool_uses:trigger={trigger},keep={int(settings.chat_context_edit_keep)}"
    except Exception:
        return "unknown"


def skills_digest(skills: Mapping[str, str]) -> Tuple[List[str], str]:
    """``(sorted names, sha256:<hex>)`` for a set of ``name -> body`` skills.

    The recipe is fixed here, once, so the phase that adds skills and any later
    reader hash the same way: sort by name, hash ``name\\0sha256(body)\\n`` per
    entry. Order of loading therefore cannot change the digest, but a rename or
    any body edit does. An empty mapping is a legitimate input and hashes to the
    digest of nothing — see the ``None`` vs ``[]`` convention on
    ``AgentProvenance``.
    """
    names = sorted(skills)
    h = hashlib.sha256()
    for name in names:
        body = skills[name]
        body_bytes = body.encode("utf-8") if isinstance(body, str) else bytes(body)
        h.update(name.encode("utf-8"))
        h.update(b"\0")
        h.update(hashlib.sha256(body_bytes).hexdigest().encode("ascii"))
        h.update(b"\n")
    return names, "sha256:" + h.hexdigest()


# ---------------------------------------------------------------------------
# Request-scoped agent provenance (A3-H4)
# ---------------------------------------------------------------------------
# ``collect_provenance`` is called deep inside the synthesis worker, which has
# no owner and no skill context (finding A3-H4). Resolving owner-scoped state
# down there would also be the exact tenancy hazard A3-C1 describes. So the
# owner-scoped half is resolved ONCE per turn, in request scope, and parked in a
# contextvar; ``collect_provenance`` only reads what is already resolved.

_AGENT_PROVENANCE: ContextVar[Optional[AgentProvenance]] = ContextVar(
    "siliconcrew_agent_provenance", default=None
)


def current_agent_provenance() -> Optional[AgentProvenance]:
    """What the enclosing request scope resolved, or ``None`` if unbound."""
    return _AGENT_PROVENANCE.get()


def set_agent_provenance(agent: Optional[AgentProvenance]):
    """Bind ``agent`` to the current context; returns the reset token.

    Used to re-bind a dispatching request's stamp inside a worker thread —
    contextvars do not cross ``Executor.submit`` on their own (the same reason
    ``_submit_with_quota_release`` re-binds the session context).
    """
    return _AGENT_PROVENANCE.set(agent)


@contextmanager
def agent_provenance_scope(agent: AgentProvenance) -> Iterator[AgentProvenance]:
    token = _AGENT_PROVENANCE.set(agent)
    try:
        yield agent
    finally:
        _AGENT_PROVENANCE.reset(token)


def resolve_agent_provenance(user_id: Optional[str] = None) -> AgentProvenance:
    """Resolve, once per turn, what is driving this turn.

    ``user_id`` is the owner whose skill set / tool set would be composed. The
    built-in skill pack is the same for everyone, so today it changes nothing —
    but the resolution stays HERE, in request scope where the owner is known,
    because the moment a user layer exists, composing it deeper down (inside
    ``collect_provenance``, or in any module-level cache) is the cross-tenant
    leak finding A3-C1 describes.

    ``skills_loaded`` names the skills IN FORCE for the turn — the pack the
    agent could read, with the always-loaded one already in its prompt. It is
    deliberately not "the bodies the model chose to open": this stamp is
    resolved before the turn runs, and the synthesis worker that writes
    ``run_meta.json`` could not observe that choice anyway. Claiming otherwise
    would be a more precise-sounding number that is not true. ``skills_sha``
    hashes their CONTENT, so an edited skill moves the digest even under an
    unchanged name — the same reason ``prompt_sha`` rides beside
    ``prompt_version``.

    ``tool_set`` stays ``None`` = absent: nothing resolves one yet.
    """
    version, sha = prompt_identity()
    names, digest = _skills_identity()
    return AgentProvenance(
        prompt_version=version,
        prompt_sha=sha,
        skills_loaded=names,
        skills_sha=digest,
        context_edit=context_edit_identity(),
    )


def _skills_identity() -> Tuple[Optional[List[str]], Optional[str]]:
    """``(names, digest)`` for the active skill store, or ``(None, None)``.

    ``None`` when discovery could not run at all — a build shipped without the
    pack, or a malformed file — because "nothing looked" and "looked, found
    none" must stay distinguishable (see :class:`AgentProvenance`). An empty
    store that parses cleanly is ``([], <digest of nothing>)``: a real answer.
    Never raises; stamping a run must not be the thing that fails a run.
    """
    try:
        from src.utils.skills import skills_provenance

        return skills_provenance()
    except Exception:
        return None, None


def collect_provenance(
    pdk: Optional[str] = None,
    num_cores: Optional[int] = None,
    orfs_image: Optional[str] = None,
    agent: Optional[AgentProvenance] = None,
) -> Provenance:
    """Gather the full provenance stamp for a run (best-effort, never raises).

    ``agent`` defaults to whatever the enclosing request scope resolved. With no
    bound scope (a direct tool call, a worker that lost the context) the prompt
    pair is still resolved here — the active prompt is process-wide config, not
    owner state, so reading it carries no tenancy risk — while the owner-scoped
    fields stay absent rather than being guessed.
    """
    if agent is None:
        agent = current_agent_provenance()
    if agent is None:
        version, sha = prompt_identity()
        agent = AgentProvenance(
            prompt_version=version, prompt_sha=sha, context_edit=context_edit_identity()
        )
    return Provenance(
        repo_commit=repo_commit(),
        orfs_image_digest=orfs_image_digest(orfs_image),
        pdk=pdk,
        iverilog_version=iverilog_version(),
        num_cores=num_cores,
        prompt_version=agent.prompt_version,
        prompt_sha=agent.prompt_sha,
        skills_loaded=list(agent.skills_loaded) if agent.skills_loaded is not None else None,
        skills_sha=agent.skills_sha,
        tool_set=agent.tool_set,
        context_edit=agent.context_edit,
    )
