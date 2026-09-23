"""pytest setup: tests must never call the real Groq API.

Runs before any test module imports backend.main; real env vars win over
.env, so this keeps the LLM off even if a developer's .env enables it.
Tests that exercise the LLM path inject a fake client explicitly.
"""

import os

os.environ["ENABLE_LLM_EXPLANATIONS"] = "false"
os.environ["ENABLE_LLM_INTENT"] = "false"
