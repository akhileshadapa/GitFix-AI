"""github_client.py - everything that talks to the GitHub API.

This file does NOT import Streamlit. It only returns data or raises
GitHubError, and app.py decides how to show errors on screen.
That keeps it simple to test.
"""

import re

import requests

GITHUB_API = "https://api.github.com"
REQUEST_TIMEOUT = 10  # seconds to wait before giving up


class GitHubError(Exception):
    """Raised when something goes wrong while talking to GitHub.

    The message is written to be shown directly to the user.
    """


def parse_repo_url(url):
    """Turn 'https://github.com/owner/repo' into ('owner', 'repo').

    Also handles a trailing '.git', '/issues', or '?tab=...'.
    Raises GitHubError if the text is not a GitHub repository URL.
    """
    match = re.search(r"github\.com/([^/\s]+)/([^/\s?#]+)", (url or "").strip())
    if not match:
        raise GitHubError("Enter a valid GitHub repository URL, like https://github.com/owner/repo")

    owner, repo = match.groups()
    if repo.endswith(".git"):
        repo = repo[: -len(".git")]
    return owner, repo


def _error_message(response):
    """Pull a readable message out of a failed GitHub response."""
    try:
        return response.json().get("message", "Unknown error")
    except (ValueError, AttributeError):
        # The body was not JSON (or not a JSON object), so use a generic text.
        return "GitHub returned an unreadable response"


def fetch_issues(owner, repo, label=None, token=None, per_page=50):
    """Fetch open issues for owner/repo and return them as a list of dicts.

    label:    optional label name. GitHub filters on its side (server-side).
    token:    optional GitHub token. Raises the rate limit from 60 to 5000/hour.
    per_page: how many results to ask for (GitHub allows up to 100).

    Pull requests are removed, because GitHub's issues endpoint also returns them.
    """
    params = {"state": "open", "per_page": per_page}
    if label:
        params["labels"] = label

    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        response = requests.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/issues",
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        raise GitHubError("GitHub took too long to respond. Please try again.")
    except requests.exceptions.RequestException:
        raise GitHubError("Could not reach GitHub. Check your internet connection.")

    if response.status_code == 404:
        raise GitHubError(f"Repository '{owner}/{repo}' was not found (or it is private).")

    if response.status_code in (403, 429):
        if response.headers.get("X-RateLimit-Remaining") == "0":
            raise GitHubError(
                "GitHub rate limit reached (60 requests/hour without a token). "
                "Wait a while, or add a GITHUB_TOKEN."
            )
        raise GitHubError(f"GitHub refused the request: {_error_message(response)}")

    if response.status_code != 200:
        raise GitHubError(f"GitHub error {response.status_code}: {_error_message(response)}")

    try:
        data = response.json()
    except ValueError:
        raise GitHubError("GitHub returned an unreadable response.")

    return [issue for issue in data if "pull_request" not in issue]


def filter_by_title(issues, query):
    """Keep only issues whose title contains `query` (ignores UPPER/lower case).

    An empty query returns every issue.
    """
    query = (query or "").strip().lower()
    if not query:
        return issues
    return [issue for issue in issues if query in issue.get("title", "").lower()]
