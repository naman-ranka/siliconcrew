"""The architect must never run on a prompt it did not intend to load.

Both behaviours asserted here replaced *silent* fallbacks. The old code served a
stale embedded prompt when the file was missing, and swallowed a
``create_react_agent`` signature mismatch into an agent with no prompt and no
pre-model hook. Both failures produced an agent that still answered, so nothing
looked broken while the wrong instructions ran.
"""
import pytest

from src.agents import architect
from src.agents.architect import PromptUnavailable, load_system_prompt


def test_loads_the_real_prompt_file():
    text = load_system_prompt()
    assert text.strip(), "the shipped prompt file must be non-empty"


def test_missing_prompt_file_raises_rather_than_falling_back(tmp_path):
    with pytest.raises(PromptUnavailable) as exc:
        load_system_prompt(tmp_path / "does_not_exist.md")
    # The message must name the env var, or a bad ARCHITECT_PROMPT_VERSION is
    # an unexplained crash at boot.
    assert "ARCHITECT_PROMPT_VERSION" in str(exc.value)


def test_empty_prompt_file_raises(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("   \n\n  ", encoding="utf-8")
    with pytest.raises(PromptUnavailable):
        load_system_prompt(empty)


def test_unreadable_prompt_file_raises(tmp_path):
    d = tmp_path / "a_directory.md"
    d.mkdir()
    with pytest.raises(PromptUnavailable):
        load_system_prompt(d)


def test_agent_construction_passes_prompt_and_hook(monkeypatch):
    """A signature mismatch must surface, not degrade.

    Guards the deleted ``except TypeError`` fallback: it used to build a
    promptless, hookless agent whenever any kwarg was wrong.
    """
    captured = {}

    def fake_create_react_agent(**kwargs):
        captured.update(kwargs)
        return "AGENT"

    monkeypatch.setattr(architect, "create_react_agent", fake_create_react_agent)
    monkeypatch.setattr(architect, "create_llm", lambda **kwargs: "LLM")

    assert architect.create_architect_agent() == "AGENT"
    assert captured["prompt"].strip(), "prompt must reach the agent"
    assert captured["pre_model_hook"] is architect._strip_reasoning_blocks


def test_signature_mismatch_is_not_swallowed(monkeypatch):
    def rejecting_create_react_agent(**kwargs):
        raise TypeError("unexpected keyword argument 'pre_model_hook'")

    monkeypatch.setattr(architect, "create_react_agent", rejecting_create_react_agent)
    monkeypatch.setattr(architect, "create_llm", lambda **kwargs: "LLM")

    with pytest.raises(TypeError):
        architect.create_architect_agent()
