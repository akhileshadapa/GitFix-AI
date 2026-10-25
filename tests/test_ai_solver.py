"""Tests for ai_solver.py.

We never call the real OpenRouter. `patch` swaps requests.post for a fake.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from ai_solver import MAX_BODY_CHARS, AIError, build_prompt, solve_issue


def fake_response(status_code=200, json_data=None, json_error=False):
    """Build a pretend `requests` response."""
    response = MagicMock()
    response.status_code = status_code
    response.text = "raw text"
    if json_error:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = json_data
    return response


GOOD_ANSWER = {"choices": [{"message": {"content": "Here is the fix plan."}}]}


# ---------- build_prompt ----------

def test_build_prompt_contains_title_and_body():
    prompt = build_prompt("Crash on start", "Steps to reproduce...")
    assert "Crash on start" in prompt
    assert "Steps to reproduce..." in prompt


def test_build_prompt_handles_missing_body():
    assert "No description provided" in build_prompt("Title", None)


def test_build_prompt_cuts_very_long_body():
    prompt = build_prompt("Title", "x" * (MAX_BODY_CHARS + 5000))
    assert "x" * (MAX_BODY_CHARS + 1) not in prompt
    assert "cut short" in prompt


# ---------- solve_issue ----------

@patch("ai_solver.requests.post")
def test_solve_issue_returns_ai_text(mock_post):
    mock_post.return_value = fake_response(json_data=GOOD_ANSWER)
    assert solve_issue("Title", "Body", api_key="test-key") == "Here is the fix plan."


@patch("ai_solver.requests.post")
def test_solve_issue_sends_key_and_model(mock_post):
    mock_post.return_value = fake_response(json_data=GOOD_ANSWER)
    solve_issue("Title", "Body", api_key="test-key", model="some/model")
    call = mock_post.call_args.kwargs
    assert call["headers"]["Authorization"] == "Bearer test-key"
    assert call["json"]["model"] == "some/model"


@patch("ai_solver.requests.post")
def test_solve_issue_without_key_never_calls_api(mock_post):
    with pytest.raises(AIError, match="API key"):
        solve_issue("Title", "Body", api_key="")
    mock_post.assert_not_called()


@patch("ai_solver.requests.post")
def test_solve_issue_401_mentions_key(mock_post):
    mock_post.return_value = fake_response(status_code=401, json_data={"error": {"message": "bad"}})
    with pytest.raises(AIError, match="rejected the API key"):
        solve_issue("Title", "Body", api_key="wrong")


@patch("ai_solver.requests.post")
def test_solve_issue_other_error_shows_provider_message(mock_post):
    mock_post.return_value = fake_response(
        status_code=429, json_data={"error": {"message": "Rate limit hit"}}
    )
    with pytest.raises(AIError, match="Rate limit hit"):
        solve_issue("Title", "Body", api_key="test-key")


@patch("ai_solver.requests.post")
def test_solve_issue_non_json_error_does_not_crash(mock_post):
    mock_post.return_value = fake_response(status_code=502, json_error=True)
    with pytest.raises(AIError, match="502"):
        solve_issue("Title", "Body", api_key="test-key")


@patch("ai_solver.requests.post")
def test_solve_issue_unexpected_shape_gives_friendly_error(mock_post):
    mock_post.return_value = fake_response(json_data={"something": "else"})
    with pytest.raises(AIError, match="unexpected format"):
        solve_issue("Title", "Body", api_key="test-key")


@patch("ai_solver.requests.post")
def test_solve_issue_empty_answer_is_an_error(mock_post):
    mock_post.return_value = fake_response(json_data={"choices": [{"message": {"content": "  "}}]})
    with pytest.raises(AIError, match="empty"):
        solve_issue("Title", "Body", api_key="test-key")


@patch("ai_solver.requests.post")
def test_solve_issue_timeout_gives_friendly_error(mock_post):
    mock_post.side_effect = requests.exceptions.Timeout()
    with pytest.raises(AIError, match="too long"):
        solve_issue("Title", "Body", api_key="test-key")
