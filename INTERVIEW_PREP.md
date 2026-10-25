# GitFix AI: Interview Prep Guide

Goal: after one day with this file you can open any file in the project and explain it line by line, in simple English.

---

## 1. The 30-second pitch (memorize this)

> "GitFix AI is a Streamlit app where you paste a public GitHub repo URL, filter issues by label, search them by title, pick one, and get an AI-written fix plan from OpenRouter. I split it into separate files for the GitHub calls, the AI calls and the screen, added proper error handling and secret management, and wrote pytest tests with mocked API calls. The AI only reads the issue text, not the code, so I treat its answer as a starting point."

The 10-second version: *"It reads GitHub issues and suggests how to fix them using AI."*

---

## 2. How the whole app works (big picture)

```
 You type a repo URL, pick a label, click "Fetch Issues"
                    |
                    v
   app.py  --calls-->  github_client.py  --HTTP GET-->  GitHub API
                              |
          returns a list of issues (pull requests removed)
                    v
   You search by title, pick an issue, click "Generate Solution"
                    |
                    v
   app.py  --calls-->  ai_solver.py  --HTTP POST-->  OpenRouter API
                              |
                 returns the AI's text answer
                    v
   app.py shows it + a Download button
```

**The one rule behind the design:** each file has one job.

| File | Its one job | Imports Streamlit? |
|------|-------------|--------------------|
| `app.py` | Show the screen, react to clicks | Yes |
| `github_client.py` | Talk to GitHub | No |
| `ai_solver.py` | Talk to OpenRouter | No |
| `config.py` | Find secret keys safely | Only inside one function |

Why this matters: files that do not import Streamlit can be tested without opening a web page, and each file can be understood on its own.

---

## 3. File by file, function by function

### 3.1 `config.py` (finds secret keys)

**Purpose:** API keys must never be written in code, because code goes to GitHub and anyone could copy them. This file looks for a key in two safe places.

```python
def get_secret(name, default=""):
```
Give it a name like `"OPENROUTER_API_KEY"`. It returns the secret, or `default` if nothing is found.

Step by step:
1. `import streamlit as st` is *inside* the function. That way `config.py` still works if Streamlit isn't installed.
2. `value = st.secrets.get(name)` looks in Streamlit's secrets (`.streamlit/secrets.toml` on your computer, or the Secrets box on Streamlit Cloud). If no secrets file exists, Streamlit raises an error.
3. The `try / except Exception: pass` catches that error and carries on instead of crashing.
4. `if value: return str(value)` returns the secret if one was found.
5. `return os.environ.get(name, default)` is the fallback: look in environment variables, else return the default.

**Say in the interview:** *"Secrets live outside the code. `secrets.toml` is in `.gitignore`, and I committed only an example file with fake values."*

---

### 3.2 `github_client.py` (talks to GitHub)

**Constants at the top**
- `GITHUB_API`: the base address of GitHub's API.
- `REQUEST_TIMEOUT = 10`: if GitHub does not answer in 10 seconds, give up instead of freezing the app.

**`class GitHubError(Exception)`**
A custom error type with no extra code. It lets this file say "something went wrong with GitHub" in a way `app.py` can catch specifically. The message is written for the user to read directly.

**`parse_repo_url(url)`**: turns a URL into `(owner, repo)`
```python
re.search(r"github\.com/([^/\s]+)/([^/\s?#]+)", (url or "").strip())
```
Read the pattern in plain English:
- `github\.com/` find the text "github.com/" (the `\.` means a real dot)
- `([^/\s]+)` group 1, the **owner**: one or more characters that are not `/` and not whitespace
- `/` then a slash
- `([^/\s?#]+)` group 2, the **repo**: one or more characters that are not `/`, whitespace, `?` or `#`

Other lines:
- `(url or "").strip()` handles `None` and removes spaces around the text.
- If nothing matches, it raises `GitHubError` with a helpful example.
- `if repo.endswith(".git")` removes a trailing `.git`, so `.../Hello-World.git` still works.
- `/issues` or `?tab=...` after the repo name are ignored automatically because the pattern stops at `/`, `?`, `#`.

**`_error_message(response)`**: reads GitHub's error text safely
The leading underscore is a Python habit meaning "private helper, only used inside this file". GitHub normally sends errors as JSON like `{"message": "Not Found"}`. `.json()` crashes if the body is not JSON, so `try / except (ValueError, AttributeError)` returns a generic text instead of crashing.

**`fetch_issues(owner, repo, label=None, token=None, per_page=50)`**: the main function
1. Builds `params`: `state=open` (only open issues) and `per_page=50`. If a label was given it adds `labels=<label>`, so **GitHub does the filtering on its server** (server-side filtering).
2. Builds `headers`: always `Accept: application/vnd.github+json`. If a token was given it adds `Authorization: Bearer <token>`, which raises the rate limit from 60 to 5000 requests/hour.
3. `requests.get(..., timeout=10)` makes the call inside a `try`:
   - `except requests.exceptions.Timeout` means it took too long.
   - `except requests.exceptions.RequestException` means any other network problem.
   - **Order matters:** `Timeout` is a more specific kind of `RequestException`, so it must be listed first. Otherwise the general one would catch everything and the timeout message would never show.
4. Checks the status code:
   - `404` means the repo does not exist (or is private).
   - `403` or `429` means a rate limit or a refusal. If the header `X-RateLimit-Remaining` equals `"0"`, we say you hit the rate limit. Otherwise we show GitHub's own message.
   - anything else that is not `200` shows a generic error with the code.
5. `response.json()` is wrapped in `try / except ValueError`, in case a 200 response is not valid JSON.
6. Last line: `[issue for issue in data if "pull_request" not in issue]`. GitHub's issues endpoint also returns pull requests, and PRs have a `pull_request` key, so we keep only items without it.

**`filter_by_title(issues, query)`**: title search
- `(query or "").strip().lower()` cleans the text (handles `None`, spaces, capital letters).
- If the query is empty, return all issues.
- Otherwise `[issue for issue in issues if query in issue.get("title", "").lower()]` keeps issues whose lowercase title contains the query.
- This is **client-side filtering**: it searches the issues we already downloaded and makes no new API call.

---

### 3.3 `ai_solver.py` (talks to OpenRouter)

**Constants**
- `OPENROUTER_URL`: the chat endpoint.
- `DEFAULT_MODEL = "openrouter/free"`: which AI model to use (can be overridden with `OPENROUTER_MODEL`).
- `REQUEST_TIMEOUT = 30`: AI answers are slow, so we wait longer than for GitHub.
- `MAX_BODY_CHARS = 4000`: long issue texts are cut so the request stays a reasonable size.

**`class AIError(Exception)`**: same idea as `GitHubError`.

**`build_prompt(title, body)`**
- `body = body or "(No description provided)"`: many issues have no description (`None`), so we substitute text.
- If the body is longer than 4000 characters it is cut and `...(description cut short)` is added.
- Returns a text containing the title, the description and the 5 sections we want back: Root Cause, Fix Plan, Files Likely To Edit, Example Code Hint, Testing Steps.
- The `f"""..."""` is an f-string: `{title}` and `{body}` get replaced with the real values.

**`_error_message(response)`**: same job as in `github_client.py`, but OpenRouter nests the error as `{"error": {"message": "..."}}`.

**`solve_issue(title, body, api_key, model=DEFAULT_MODEL)`**
1. `if not api_key: raise AIError(...)` stops immediately with a clear message if there is no key, so we never send a pointless request.
2. `requests.post(...)` sends:
   - `headers`: `Authorization: Bearer <key>` (proves who we are) and `Content-Type: application/json`.
   - `json`: the model name and `messages`, a list with one message from the "user" containing our prompt.
3. Same `Timeout` / `RequestException` handling as GitHub.
4. `401` means the key was rejected (wrong or expired key).
5. Any other non-200 status shows OpenRouter's own message.
6. `response.json()["choices"][0]["message"]["content"]` digs the answer out of the response. It is in a `try` that catches `ValueError, KeyError, IndexError, TypeError`, which are the four things that can go wrong if the response has an unexpected shape.
7. If the text is empty or only spaces, raise an error. Otherwise return the text.

**Key design point:** the `api_key` is a *parameter*. This file never reads secrets itself. `app.py` reads them and hands the key in. That keeps the file simple and easy to test.

---

### 3.4 `app.py` (the screen)

Streamlit runs the **whole file from top to bottom on every click**. This is the single most important thing to understand about Streamlit.

**Top section**
- `st.set_page_config(page_title="GitFix AI")` sets the browser tab title.
- Three `config.get_secret(...)` calls read the keys once. `GITHUB_TOKEN` and `OPENROUTER_MODEL` are optional.
- `ANY_LABEL` and `COMMON_LABELS` define the dropdown choices.

**Session state block**
```python
defaults = {"issues": [], "fetched": False, "solution": "", "solution_for": None}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value
```
Because the file re-runs on every click, normal variables are wiped each time. `st.session_state` is Streamlit's memory that survives re-runs. We store:
- `issues`: the downloaded issue list
- `fetched`: True after a successful fetch (so we can say "no issues found" vs. "haven't fetched yet")
- `solution`: the AI answer
- `solution_for`: the issue number the answer belongs to
The `if key not in ...` check means we set them only the first time.

**Step 1: Fetch**
- `st.text_input` and `st.selectbox` collect the URL and label.
- `if st.button("Fetch Issues"):` is True only for the one re-run right after the click.
- Inside a `try`: `parse_repo_url` then `fetch_issues(...)`. `label = None if label_choice == ANY_LABEL else label_choice` turns "Any label" into no filter. `GITHUB_TOKEN or None` turns an empty string into `None`.
- `except GitHubError as error:` clears the issues and shows `st.error(str(error))`, a friendly message instead of a crash.
- After any fetch, the old AI answer is cleared because it no longer matches.
- `if fetched and not issues:` shows an info message for a repo with no matching issues.

**Step 2: Search and choose**
- `filter_by_title(...)` applies the search box.
- `st.selectbox("Choose an Issue", range(len(visible_issues)), format_func=...)`: we give it plain numbers `0, 1, 2...` and `format_func` turns each number into the text `#12 - Title`. The selectbox returns the chosen number, so `visible_issues[position]` is the issue.
- Labels and the description are shown from the issue's data.

**Step 3: Generate**
- `if st.button("Generate Solution"):` calls `solve_issue(...)` inside `try / except AIError`.
- The answer is saved in `session_state` together with the issue number.
- The answer is displayed only if `solution_for == selected_issue["number"]`. So if you switch to a different issue, the old answer disappears instead of being shown under the wrong issue.
- Because the answer lives in `session_state` (not inside the button's `if`), it **stays on screen** after other clicks such as typing in the search box. In the original version it would vanish. This was a real bug I fixed.

---

### 3.5 The tests (`tests/`)

**What a unit test is:** a tiny function that calls one piece of code and checks the result with `assert`. Names start with `test_` so pytest finds them.

**Why mock:** a real API call is slow, needs internet and a key, and can fail randomly. Tests should be fast and repeatable, so we replace the real `requests.get` and `requests.post` with fakes.

Key pieces:
- `@patch("github_client.requests.get")` temporarily swaps `requests.get` for a fake during that test. We patch it **where it is used** (inside `github_client`), not where it is defined.
- The fake is passed into the test function as `mock_get` (or `mock_post`).
- `fake_response(...)` is a helper that builds a pretend response with a `status_code` and `.json()` result. `MagicMock` is an object that accepts any attribute or call.
- `mock_get.return_value = fake_response(...)` says "when called, return this".
- `mock_get.side_effect = requests.exceptions.Timeout()` says "when called, raise this error".
- `with pytest.raises(GitHubError, match="not found"):` passes only if that error is raised and its message contains the text.
- `mock_get.call_args.kwargs["params"]` lets us check **what our code sent**, such as the label or the Authorization header.
- `mock_post.assert_not_called()` proves no request was made when the key is missing.

What is covered:
- URL parsing: normal, `.git`, extra path, invalid.
- Issues: pull requests removed, label sent or not sent, token sent or not sent, 404, rate limit, timeout, connection error, non-JSON error.
- Title search: ignores case, empty query, no match.
- Prompt building: title and body included, missing body, long body cut.
- AI calls: success, key and model sent, missing key, 401, other errors, non-JSON error, bad response shape, empty answer, timeout.

Run them: `pytest`. Run with details: `pytest -v`.

**Not tested (say this honestly):** the Streamlit screen itself and real network calls.

---

### 3.6 Other files

| File | What it is |
|------|-----------|
| `requirements.txt` | Packages the app needs (`streamlit`, `requests`) |
| `requirements-dev.txt` | Adds `pytest` for development (`-r requirements.txt` pulls in the first file) |
| `pytest.ini` | Tells pytest to look in `tests/` and to treat the project folder as importable, so `import github_client` works |
| `.gitignore` | Lists files Git must never upload: secrets, caches, virtual environments |
| `.streamlit/secrets.toml.example` | Safe template showing which secrets exist, with fake values |
| `README.md` | Public documentation |

---

## 4. Concepts you must be able to explain

**Why separate files?** One file per job is easier to read, test and change. If GitHub's API changes, I only touch `github_client.py`.

**Why custom errors (`GitHubError`, `AIError`)?** The helper files describe *what* went wrong; the UI decides *how* to show it. The helper files never call `st.error`, so they can be tested without Streamlit.

**Why timeouts?** Without one, `requests` can wait forever and freeze the app.

**Server-side vs client-side filtering.** Label filtering is server-side: GitHub only sends matching issues. Title search is client-side: I search the 50 issues already downloaded. Server-side is more accurate for big repos; client-side is instant and uses no extra API calls.

**Rate limits.** GitHub allows about 60 unauthenticated requests per hour; a token gives 5000. I detect the limit using the `X-RateLimit-Remaining` header and show a clear message.

**How secrets are protected.** Never in code. Read from Streamlit secrets or environment variables. `secrets.toml` is git-ignored. Only a fake-valued example file is committed.

**What mocking is.** Replacing a real dependency with a controlled fake so a test is fast, offline and predictable.

**Streamlit re-runs the script on every interaction.** That is why `session_state` exists.

---

## 5. Honest limitations and next steps

Limitations (say them before the interviewer finds them):
- The AI only sees the issue text, not the repository code, so file suggestions are guesses.
- Only 50 issues are fetched; no pagination.
- The label list is fixed to common names.
- No tests for the UI.

What I would do next:
1. Add pagination or use GitHub's search API so title search covers the whole repo.
2. Give the AI more context (the repo's README or file list) so its suggestions are grounded.
3. Add a GitHub Actions workflow that runs `pytest` on every push.
4. Cache results to save API calls.

---

## 6. Likely interview questions (practice out loud)

1. **Walk me through your project.** (Use the pitch in section 1, then the diagram.)
2. **What was the hardest part?** Suggested true answer: keeping the AI answer on screen. Streamlit re-runs the file on every click, so the answer vanished until I stored it in `session_state`.
3. **What did you change from your first version?** Split one 115-line file into modules, added working label filter and title search (the README originally claimed label filtering that didn't exist in the code), added error handling, secrets handling and tests.
4. **How do you handle errors?** Custom exceptions with user-friendly messages; timeouts; checks for 404, rate limit, 401, non-JSON bodies and unexpected response shapes.
5. **How do you keep API keys safe?** Section 4.
6. **How do you test code that calls an API?** Mock `requests.get` and `requests.post`.
7. **What is `session_state`?** Streamlit's memory between re-runs.
8. **Why does the `Timeout` except come before `RequestException`?** It is a subclass; the general one would swallow it.
9. **Why filter pull requests?** GitHub's issues endpoint returns PRs as well, and they have a `pull_request` key.
10. **What if the repo has 5000 issues?** Only the first 50 are fetched. I'd add pagination or use the search API.
11. **Is the AI answer reliable?** No. It only sees the issue text, so it is a hint, not a verified fix.
12. **What is the GitHub rate limit?** About 60 requests/hour unauthenticated, 5000 with a token.
13. **Why `f"..."` strings?** They insert variables into text.
14. **What does `[x for x in items if cond]` do?** Builds a new list with only the items that pass the condition. Show the PR filter.
15. **What would you add with more time?** Section 5.
16. **How would you deploy it?** Streamlit Community Cloud, with the keys in its Secrets box.
17. **Why not a bigger framework or a database?** The app is small; extra tools would add complexity without benefit.

---

## 7. How to talk about using AI help

Be honest and confident. A good answer:

> "I built the first version myself. For this refactor I used Claude to help me restructure the code and write the tests, and then I went through every file until I could explain it. I can walk you through any part, and I can change something live if you want."

Do **not** claim you wrote every line alone. Interviewers care that you understand the code, can explain the decisions and can modify it.

**Prove it:** before the interview, make one small change yourself without help (for example, add a new label to `COMMON_LABELS`, or change the timeout and update a test). Then you can say "I tweaked X myself".

---

## 8. One-day study plan

| Block | Time | Do this |
|-------|------|---------|
| 1 | 1 hr | Run the app locally. Click everything. Try a bad URL, a repo with no issues, a label filter, a search. Break it on purpose (remove the API key) and watch the error. |
| 2 | 1.5 hr | Read `github_client.py` with section 3.2 beside it. Close the file and explain each function out loud. |
| 3 | 1 hr | Same for `ai_solver.py` and `config.py`. |
| 4 | 1.5 hr | `app.py` with section 3.4. Focus on re-runs and `session_state`. Add a `st.write(st.session_state)` line temporarily to watch it change, then remove it. |
| 5 | 1 hr | Tests. Run `pytest -v`. Then break the code on purpose (for example remove the PR filter) and see a test fail. Put it back. |
| 6 | 1 hr | Make your own small change (section 7) and run the tests. |
| 7 | 1 hr | Answer all questions in section 6 out loud, ideally recorded. |
| 8 | 30 min | Practice the 2-minute live demo (below). |

**Live demo script (2 minutes):**
1. Paste a public repo URL (pick a busy one and test it beforehand), choose "good first issue", click Fetch.
2. Type a word in the search box to show filtering.
3. Pick an issue, click Generate, read the answer.
4. Mention the limits: it sees only the issue text.
5. Show the file structure and run `pytest`.

---

## 9. Command cheat sheet

```bash
# run the app
streamlit run app.py

# run all tests
pytest

# run tests with names and details
pytest -v

# run one test file
pytest tests/test_github_client.py

# install everything for development
pip install -r requirements-dev.txt
```
