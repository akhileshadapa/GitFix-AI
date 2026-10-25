"""config.py - reads secret settings (API keys) safely.

Keys are NEVER written in the code. We look for them in two places:
1. Streamlit secrets  (.streamlit/secrets.toml locally, or the Secrets box on Streamlit Cloud)
2. Environment variables (handy for terminals and servers)
"""

import os


def get_secret(name, default=""):
    """Return the secret called `name`, or `default` if it is not set."""
    # Streamlit is imported inside the function so this file also works
    # (and can be tested) without Streamlit installed.
    try:
        import streamlit as st

        value = st.secrets.get(name)  # raises an error if no secrets file exists
        if value:
            return str(value)
    except Exception:
        # No secrets file, or Streamlit not available: fall through to env vars.
        pass

    return os.environ.get(name, default)
