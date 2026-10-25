"""app.py - the Streamlit screen (UI only).

All the real work happens in other files:
  github_client.py -> talks to GitHub
  ai_solver.py     -> talks to OpenRouter
  config.py        -> reads API keys safely
This file just collects input, calls those functions, and shows results.
"""

import streamlit as st

import config
from ai_solver import DEFAULT_MODEL, AIError, solve_issue
from github_client import GitHubError, fetch_issues, filter_by_title, parse_repo_url

st.set_page_config(page_title="GitFix AI")

# Read secrets once. They are never shown on screen.
OPENROUTER_API_KEY = config.get_secret("OPENROUTER_API_KEY")
OPENROUTER_MODEL = config.get_secret("OPENROUTER_MODEL", DEFAULT_MODEL)
GITHUB_TOKEN = config.get_secret("GITHUB_TOKEN")  # optional

ANY_LABEL = "Any label"
COMMON_LABELS = [ANY_LABEL, "bug", "good first issue", "help wanted", "documentation", "enhancement"]

# Streamlit re-runs this whole file on every click, so anything we want to
# remember between clicks must be stored in st.session_state.
defaults = {"issues": [], "fetched": False, "solution": "", "solution_for": None}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

st.title("GitFix AI")
st.write("Fetch open GitHub issues and get AI-generated fix suggestions.")

# ---------- Step 1: fetch issues ----------
repo_url = st.text_input("GitHub Repository URL", placeholder="https://github.com/owner/repo")
label_choice = st.selectbox("Filter by label (optional)", COMMON_LABELS)

if st.button("Fetch Issues"):
    try:
        owner, repo = parse_repo_url(repo_url)
        label = None if label_choice == ANY_LABEL else label_choice
        with st.spinner("Fetching issues..."):
            st.session_state.issues = fetch_issues(
                owner, repo, label=label, token=GITHUB_TOKEN or None
            )
        st.session_state.fetched = True
    except GitHubError as error:
        st.session_state.issues = []
        st.session_state.fetched = False
        st.error(str(error))
    # A new fetch means any old AI answer no longer applies.
    st.session_state.solution = ""
    st.session_state.solution_for = None

if st.session_state.fetched and not st.session_state.issues:
    st.info("No open issues found for that repository and label.")

# ---------- Step 2: search and choose an issue ----------
if st.session_state.issues:
    search_text = st.text_input("Search issue titles", placeholder="e.g. crash, login, typo")
    visible_issues = filter_by_title(st.session_state.issues, search_text)

    if not visible_issues:
        st.info("No issues match your search.")
    else:
        st.caption(f"Showing {len(visible_issues)} of {len(st.session_state.issues)} issues")

        position = st.selectbox(
            "Choose an Issue",
            range(len(visible_issues)),
            format_func=lambda i: f"#{visible_issues[i]['number']} - {visible_issues[i]['title']}",
        )
        selected_issue = visible_issues[position]

        label_names = [lbl["name"] for lbl in selected_issue.get("labels", [])]
        if label_names:
            st.caption("Labels: " + ", ".join(label_names))

        with st.expander("Issue Details"):
            st.markdown(selected_issue.get("body") or "_No description provided._")

        # ---------- Step 3: ask the AI ----------
        if st.button("Generate Solution"):
            try:
                with st.spinner("Analyzing issue..."):
                    st.session_state.solution = solve_issue(
                        selected_issue["title"],
                        selected_issue.get("body"),
                        api_key=OPENROUTER_API_KEY,
                        model=OPENROUTER_MODEL,
                    )
                st.session_state.solution_for = selected_issue["number"]
            except AIError as error:
                st.error(str(error))

        # Show the saved answer only if it belongs to the issue currently selected.
        if st.session_state.solution and st.session_state.solution_for == selected_issue["number"]:
            st.subheader("AI Solution")
            st.markdown(st.session_state.solution)
            st.download_button(
                "Download Solution",
                data=st.session_state.solution,
                file_name=f"issue_{selected_issue['number']}_solution.txt",
                mime="text/plain",
            )
