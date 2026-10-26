"""A cold ComplyEdge instance still gets its verdict and Log ID through.

A ComplyEdge instance that has to start up answers in about 8 s (measured
2026-10-26: 3.2-3.7 s start-up plus ~4 s for the first check). With a 5 s
wait the check was skipped: the record existed on ComplyEdge's side, but the
caller got no Log ID and a block would have been missed (fail-open). These
tests answer slowly from a local stub of POST /v1/check.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from eif.mcp_server import compliance

SLOW_S = 6  # slower than the old 5 s default, faster than a cold start


@pytest.fixture
def slow_stub(monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers["Content-Length"]))
            time.sleep(SLOW_S)
            out = json.dumps(
                {"event_id": "evt-cold", "allowed": False, "violations": [{"rule_id": "r-1"}]}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("COMPLYEDGE_API_KEY", "ce_test_key_for_stub")
    monkeypatch.setenv("COMPLYEDGE_API_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.delenv("COMPLYEDGE_TIMEOUT_S", raising=False)
    yield
    server.shutdown()


def test_slow_answer_within_the_default_wait_is_used(slow_stub):
    v = compliance.check("hello", "prompt", {})
    assert v.checked and v.error is None
    assert v.event_id == "evt-cold"
    assert v.allowed is False  # the block is not lost to a timeout


def test_timeout_override_still_applies(slow_stub, monkeypatch):
    monkeypatch.setenv("COMPLYEDGE_TIMEOUT_S", "1")
    v = compliance.check("hello", "prompt", {})
    assert not v.checked and v.allowed and v.event_id is None
