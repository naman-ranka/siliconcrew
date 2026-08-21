"""A pooled worker must not carry one job's identity into the next.

`_submit_with_quota_release` rebinds the dispatching request's session context
and provenance stamp inside the worker thread, because contextvars do not cross
`Executor.submit`. It used to bind them and never unbind: the job executor
reuses threads, so the binding outlived the job. A later job on that same worker
with nothing of its own read the previous job's session and stamp — and once
skills are populated, a stamp carries owner-specific data.

Reported by review on the PR, reproduced here before fixing.
"""
from concurrent.futures import ThreadPoolExecutor

from src.platform_engines.provenance import (
    AgentProvenance,
    current_agent_provenance,
    reset_agent_provenance,
    set_agent_provenance,
)

ALICE = AgentProvenance(
    prompt_version="v3",
    prompt_sha="sha256:alice",
    skills_loaded=["alice-private-skill"],
    skills_sha="sha256:aaa",
    tool_set=None,
)


def _runner_like_the_job_executor(stamp, *, reset: bool):
    """The shape of the real runner: bind, work, optionally unbind."""
    token = set_agent_provenance(stamp)
    try:
        return current_agent_provenance()
    finally:
        if reset:
            reset_agent_provenance(token)


def test_a_stamp_does_not_survive_into_the_next_job_on_that_worker():
    pool = ThreadPoolExecutor(max_workers=1)  # force reuse
    try:
        first = pool.submit(_runner_like_the_job_executor, ALICE, reset=True).result()
        assert first.skills_loaded == ["alice-private-skill"]

        second = pool.submit(_runner_like_the_job_executor, None, reset=True).result()
        assert second is None, (
            "a job with no stamp of its own inherited the previous job's: "
            f"{second}"
        )
    finally:
        pool.shutdown()


def _runner_as_it_was(stamp):
    """The ORIGINAL shape: bind only when there is something to bind, never unbind.

    Both halves matter. Conditional binding means a job with no stamp does not
    overwrite what is there; no reset means what is there is the last job's.
    """
    if stamp is not None:
        set_agent_provenance(stamp)
    return current_agent_provenance()


def test_the_original_shape_really_did_leak():
    """Pins WHY both halves of the fix exist, so undoing either fails loudly."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        pool.submit(_runner_as_it_was, ALICE).result()
        leaked = pool.submit(_runner_as_it_was, None).result()
        assert leaked is not None and leaked.skills_loaded == ["alice-private-skill"], (
            "the leak this test documents no longer reproduces — if the binding "
            "mechanism changed, rewrite this test rather than deleting it"
        )
    finally:
        pool.shutdown()


def test_binding_none_is_what_clears_a_stale_value():
    """The real runner binds unconditionally, including None."""
    outer = set_agent_provenance(ALICE)
    try:
        token = set_agent_provenance(None)
        try:
            assert current_agent_provenance() is None
        finally:
            reset_agent_provenance(token)
        assert current_agent_provenance() is ALICE
    finally:
        reset_agent_provenance(outer)
