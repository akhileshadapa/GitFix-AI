"""ai_solver.py - everything that talks to the OpenRouter AI API.

Like github_client.py, this file does NOT import Streamlit.
The API key is passed in as an argument, never written in the code.
"""

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"
REQUEST_TIMEOUT = 30  # AI answers are slower than normal API calls
MAX_BODY_CHARS = 4000  # cut very long issue texts so the request stays small


class AIError(Exception):
    """Raised when something goes wrong while talking to OpenRouter.

    The message is written to be shown directly to the user.
    """


def build_prompt(title, body):
    """Create the text we send to the AI for one issue."""
    body = body or "(No description provided)"
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + "\n...(description cut short)"

    return f"""You are an experienced open-source contributor.

Issue Title:
{title}

Issue Description:
{body}

Provide:
1. Root Cause
2. Fix Plan
3. Files Likely To Edit
4. Example Code Hint
5. Testing Steps
"""


def _error_message(response):
    """Pull a readable message out of a failed OpenRouter response."""
    try:
        return response.json().get("error", {}).get("message", "Unknown error")
    except (ValueError, AttributeError):
        # Body was not JSON, or "error" was not a dictionary.
        return "OpenRouter returned an unreadable response"


def solve_issue(title, body, api_key, model=DEFAULT_MODEL):
    """Ask the AI for a fix plan and return its answer as text.

    Raises AIError with a friendly message if anything goes wrong.
    """
    if not api_key:
        raise AIError("No OpenRouter API key found. Add OPENROUTER_API_KEY to your secrets.")

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": build_prompt(title, body)}],
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        raise AIError("The AI took too long to respond. Please try again.")
    except requests.exceptions.RequestException:
        raise AIError("Could not reach OpenRouter. Check your internet connection.")

    if response.status_code == 401:
        raise AIError("OpenRouter rejected the API key. Check OPENROUTER_API_KEY.")

    if response.status_code != 200:
        raise AIError(f"OpenRouter error {response.status_code}: {_error_message(response)}")

    try:
        text = response.json()["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise AIError("OpenRouter sent a response in an unexpected format.")

    if not text or not text.strip():
        raise AIError("The AI returned an empty answer. Please try again.")

    return text
