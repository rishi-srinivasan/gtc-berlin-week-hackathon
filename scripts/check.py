"""Readiness check: which settings are filled in, and do Langfuse and distil accept our credentials."""
import os
import shutil
import subprocess

import pii  # noqa: F401  (loads .env and ENV_FILE)

GROUPS = {
    "Langfuse": ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"],
    "Teacher": ["TEACHER_MODEL", "TEACHER_BASE_URL", "TEACHER_API_KEY"],
    "Student (distil endpoint)": ["STUDENT_BASE_URL", "STUDENT_MODEL", "STUDENT_API_KEY"],
    "Frontier (demo)": ["FRONTIER_MODEL", "FRONTIER_BASE_URL", "FRONTIER_API_KEY"],
}

for group, keys in GROUPS.items():
    print(f"{group:17}" + "  ".join(f"{k}={'ok' if os.getenv(k) else '-'}" for k in keys))

try:
    from langfuse import get_client
    print("Langfuse auth:   ", "ok" if get_client().auth_check() else "FAILED")
except Exception as e:  # missing keys raise or warn depending on SDK version
    print("Langfuse auth:    FAILED", type(e).__name__)

if shutil.which("distil"):
    r = subprocess.run(["distil", "whoami"], capture_output=True, text=True)
    print("distil:          ", (r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr) else "?")
else:
    print("distil:           CLI not installed (make setup installs it)")
