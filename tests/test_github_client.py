"""Tests for github_client.py.

We never call the real GitHub. `patch` swaps requests.get for a fake,
so the tests are fast and work offline.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from github_client import GitHubError, fetch_issues, filter_by_title, parse_repo_url


def fake_response(status_code=200, json_data=None, headers=None, json_error=False):
    """Build a pretend `requests` response."""
    response = MagicMock()
    response.status_code = status_code
    response.headers = headers or {}
    if json_error:
        response.json.side_effect = ValueError("not json")
    else:
        response.json.return_value = json_data
    return response


# ---------- parse_repo_url ----------

def test_parse_repo_url_normal():
    assert parse_repo_url("https://github.com/octocat/Hello-World") == ("octocat", "Hello-World")


def test_parse_repo_url_strips_git_suffix_and_extra_path():
    assert parse_repo_url("https://github.com/octocat/Hello-World.git") == ("octocat", "Hello-World")
    assert parse_repo_url("https://github.com/octocat/Hello-World/issues") == ("octocat", "Hello-World")


def test_parse_repo_url_invalid_raises():
    with pytest.raises(GitHubError):
        parse_repo_url("not a url")
    with pytest.raises(GitHubError):
        parse_repo_url("")


# ---------- fetch_issues ----------

@patch("github_client.requests.get")
def test_fetch_issues_removes_pull_requests(mock_get):
    mock_get.return_value = fake_response(
        json_data=[
            {"number": 1, "title": "Real issue"},
            {"number": 2, "title": "A pull request", "pull_request": {"url": "x"}},
        ]
    )
    issues = fetch_issues("octocat", "Hello-World")
    assert [i["number"] for i in issues] == [1]


@patch("github_client.requests.get")
def test_fetch_issues_sends_label_filter(mock_get):
    mock_get.return_value = fake_response(json_data=[])
    fetch_issues("octocat", "Hello-World", label="good first issue")
    assert mock_get.call_args.kwargs["params"]["labels"] == "good first issue"


@patch("github_client.requests.get")
def test_fetch_issues_no_label_means_no_label_param(mock_get):
    mock_get.return_value = fake_response(json_data=[])
    fetch_issues("octocat", "Hello-World")
    assert "labels" not in mock_get.call_args.kwargs["params"]


@patch("github_client.requests.get")
def test_fetch_issues_sends_token_when_given(mock_get):
    mock_get.return_value = fake_response(json_data=[])
    fetch_issues("octocat", "Hello-World", token="abc123")
    assert mock_get.call_args.kwargs["headers"]["Authorization"] == "Bearer abc123"


@patch("github_client.requests.get")
def test_fetch_issues_no_token_means_no_auth_header(mock_get):
    mock_get.return_value = fake_response(json_data=[])
    fetch_issues("octocat", "Hello-World")
    assert "Authorization" not in mock_get.call_args.kwargs["headers"]


@patch("github_client.requests.get")
def test_fetch_issues_404_gives_friendly_error(mock_get):
    mock_get.return_value = fake_response(status_code=404, json_data={"message": "Not Found"})
    with pytest.raises(GitHubError, match="not found"):
        fetch_issues("octocat", "nope")


@patch("github_client.requests.get")
def test_fetch_issues_rate_limit_message(mock_get):
    mock_get.return_value = fake_response(
        status_code=403,
        json_data={"message": "API rate limit exceeded"},
        headers={"X-RateLimit-Remaining": "0"},
    )
    with pytest.raises(GitHubError, match="rate limit"):
        fetch_issues("octocat", "Hello-World")


@patch("github_client.requests.get")
def test_fetch_issues_timeout_gives_friendly_error(mock_get):
    mock_get.side_effect = requests.exceptions.Timeout()
    with pytest.raises(GitHubError, match="too long"):
        fetch_issues("octocat", "Hello-World")


@patch("github_client.requests.get")
def test_fetch_issues_connection_error_gives_friendly_error(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError()
    with pytest.raises(GitHubError, match="Could not reach"):
        fetch_issues("octocat", "Hello-World")


@patch("github_client.requests.get")
def test_fetch_issues_non_json_error_does_not_crash(mock_get):
    mock_get.return_value = fake_response(status_code=500, json_error=True)
    with pytest.raises(GitHubError, match="500"):
        fetch_issues("octocat", "Hello-World")


# ---------- filter_by_title ----------

ISSUES = [
    {"number": 1, "title": "App crashes on Login"},
    {"number": 2, "title": "Fix typo in README"},
    {"number": 3, "title": "Login page is slow"},
]


def test_filter_by_title_ignores_case():
    result = filter_by_title(ISSUES, "login")
    assert [i["number"] for i in result] == [1, 3]


def test_filter_by_title_empty_query_returns_everything():
    assert filter_by_title(ISSUES, "") == ISSUES
    assert filter_by_title(ISSUES, "   ") == ISSUES
    assert filter_by_title(ISSUES, None) == ISSUES


def test_filter_by_title_no_match_returns_empty_list():
    assert filter_by_title(ISSUES, "database") == []
