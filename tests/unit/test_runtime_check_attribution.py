"""The runtime probe names who each check acts for.

Every /v1/check the probe sent left user_id, user_role and session_id blank
on the audit record. It now sends them: the GitHub actor, role "ci" and the
workflow run in CI; $USER and role "maintainer" locally. Runs the real
script against a local stub of the API.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "compliance" / "runtime_check.sh"


def _run(extra_env: dict) -> dict:
    seen: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append(json.loads(body))
            out = json.dumps({"allowed": True, "violations": [], "latency_ms": 1}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("GITHUB_", "COMPLYEDGE_"))}
    env.update({"COMPLYEDGE_API_KEY": "ce_test",
                "COMPLYEDGE_API_URL": f"http://127.0.0.1:{server.server_port}"})
    env.update(extra_env)
    try:
        proc = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)
    finally:
        server.shutdown()
    assert proc.returncode == 0, proc.stderr
    assert len(seen) == 1
    return seen[0]


def test_ci_run_sends_actor_role_and_run():
    body = _run({"GITHUB_ACTIONS": "true", "GITHUB_ACTOR": "octocat",
                 "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2"})
    assert body["context"] == {"user_id": "octocat", "user_role": "ci", "session_id": "123-2"}


def test_local_run_sends_the_login_user_as_maintainer():
    body = _run({"USER": "alice"})
    assert body["context"] == {"user_id": "alice", "user_role": "maintainer"}


def test_overrides_win():
    body = _run({"GITHUB_ACTIONS": "true", "GITHUB_ACTOR": "octocat", "GITHUB_RUN_ID": "1",
                 "COMPLYEDGE_USER_ID": "release-bot", "COMPLYEDGE_USER_ROLE": "release",
                 "COMPLYEDGE_SESSION_ID": "v1.2.3"})
    assert body["context"] == {"user_id": "release-bot", "user_role": "release", "session_id": "v1.2.3"}
