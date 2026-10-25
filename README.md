# GitFix AI: AI-Powered GitHub Issue Helper

GitFix AI fetches open issues from any **public** GitHub repository and asks an AI model (via [OpenRouter](https://openrouter.ai/)) to suggest how to fix the one you pick.

Live demo: https://app-issue-solver.streamlit.app/

## What it does

- Fetches open issues from a public GitHub repo (up to 50 per fetch). Pull requests are removed.
- **Label filter:** pick a label (bug, good first issue, help wanted, documentation, enhancement) and GitHub returns only issues with that label.
- **Title search:** type a word to narrow the fetched issues by title (not case-sensitive).
- **AI suggestion** for the selected issue: root cause, fix plan, files likely to edit, code hint, testing steps.
- Download the suggestion as a `.txt` file.
- Friendly error messages for an invalid URL, repo not found, GitHub rate limit, timeouts, a missing or wrong API key, and unexpected API responses.

## Limitations (honest list)

- The AI only reads the **issue title and description**. It does not see the repository's code, so "Files Likely To Edit" is an educated guess, not a verified answer. Treat the output as a starting point.
- Only the **first 50 open issues** are fetched, and title search only looks inside those 50.
- The label dropdown has a fixed list of common labels. A repo that uses different label names will return no results for those.
- Public repositories only.
- Without a GitHub token, GitHub allows about 60 requests per hour.

## Project structure

```
app.py              Streamlit screen (UI only)
github_client.py    GitHub API: parse URL, fetch issues, filter by title
ai_solver.py        OpenRouter API: build the prompt, get the AI answer
config.py           Reads API keys from Streamlit secrets or environment variables
tests/              pytest unit tests (API calls are mocked)
.streamlit/secrets.toml.example   Template for your secret keys
```

`github_client.py` and `ai_solver.py` do not import Streamlit, which keeps them easy to test.

## Run it locally

```bash
git clone https://github.com/akhileshadapa/GitFix-AI.git
cd GitFix-AI
python -m venv venv
venv\Scripts\activate          # Windows;  on Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
```

Add your keys:

1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`
2. Put your free OpenRouter key in it (get one at https://openrouter.ai/). `secrets.toml` is in `.gitignore`, so it is never uploaded.

```bash
streamlit run app.py
```

### Optional settings (in `secrets.toml` or as environment variables)

| Name | Purpose |
|------|---------|
| `OPENROUTER_API_KEY` | **Required** for AI suggestions |
| `GITHUB_TOKEN` | Optional. Raises the GitHub limit to 5000 requests/hour |
| `OPENROUTER_MODEL` | Optional. Choose a different OpenRouter model |

## Deploy on Streamlit Community Cloud

In the app's **Settings → Secrets** box, paste the same lines you would put in `secrets.toml`, for example `OPENROUTER_API_KEY = "your-key"`.

## Run the tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests replace `requests.get` and `requests.post` with fakes, so they run offline, instantly, and never use a real API key.

## Tech stack

- Python and Streamlit (UI)
- `requests` (HTTP calls)
- GitHub REST API (issues)
- OpenRouter API (AI model access)
- pytest (tests)
