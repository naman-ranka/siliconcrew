"""E6 (onboarding wave): recursion-limit and provider-error disposition.

The chat loop's terminal-frame logic must (a) turn a step-budget death into
an honest continue nudge + a real done frame, never the raw LangGraph error,
and (b) map provider billing errors to actionable messages. These test the
pure helpers; the frame sequence itself is exercised by
tests/test_chat_recursion_frames.py against the real WS loop.
"""
import api


def test_recursion_error_detected_by_message():
    exc = RuntimeError(
        "Recursion limit of 80 reached without hitting a stop condition. "
        "You can increase the limit by setting the `recursion_limit` config key."
    )
    assert api._is_recursion_limit_error(exc)


def test_recursion_error_detected_by_type():
    try:
        from langgraph.errors import GraphRecursionError
    except Exception:  # env without langgraph — message fallback covers it
        return
    assert api._is_recursion_limit_error(GraphRecursionError("boom"))


def test_ordinary_errors_are_not_recursion():
    assert not api._is_recursion_limit_error(ValueError("No key available for Anthropic."))


def test_billing_errors_get_actionable_mapping():
    exc = RuntimeError(
        'Error code: 400 - {"error": {"message": "Your credit balance is too low '
        'to access the Anthropic API."}}'
    )
    msg = api._friendly_agent_error(exc, key_source="byok")
    assert "Add a different key in Settings" in msg
    assert "free model" in msg
    assert "credit balance" in msg  # the provider's own words stay visible


def test_platform_key_billing_errors_never_blame_the_user():
    # Adversarial-review finding: a keyless free-tier user whose turn ran on
    # the PLATFORM key must not be told "your API key" failed or to "switch
    # to the free model" they are already on.
    exc = RuntimeError("429 You exceeded your current quota, please check your plan and billing details.")
    msg = api._friendly_agent_error(exc, key_source="hosted")
    assert "free tier is temporarily unavailable" in msg
    assert "Your API key" not in msg
    assert "switch to the free model" not in msg


def test_non_billing_errors_pass_through_unchanged():
    exc = RuntimeError("model produced malformed tool call")
    assert api._friendly_agent_error(exc) == str(exc)


def test_recursion_limit_is_config():
    from src.platform_engines.settings import get_settings

    assert get_settings().chat_recursion_limit >= 50
