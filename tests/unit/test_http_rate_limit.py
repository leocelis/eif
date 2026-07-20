"""Rate limiter regression tests for the hosted HTTP server.

Found during a review of misuse-protection on the hosted endpoint: the TOS
prohibits DoS-volume usage, but nothing technically enforced it - every
request costs CPU, and requests reaching the P1 evidence tier spawn a
subprocess. _RateLimiter adds a basic per-key fixed-window cap.
"""

from eif.mcp_server.http_server import _RateLimiter


class TestRateLimiter:
    def test_allows_up_to_the_limit(self):
        rl = _RateLimiter(limit_per_minute=3)
        results = [rl.check("key1") for _ in range(3)]
        assert results == [True, True, True]

    def test_blocks_over_the_limit_in_the_same_window(self):
        rl = _RateLimiter(limit_per_minute=3)
        for _ in range(3):
            rl.check("key1")
        assert rl.check("key1") is False
        assert rl.check("key1") is False

    def test_keys_are_isolated(self):
        rl = _RateLimiter(limit_per_minute=1)
        assert rl.check("key1") is True
        assert rl.check("key1") is False
        assert rl.check("key2") is True

    def test_window_resets(self, monkeypatch):
        import time

        rl = _RateLimiter(limit_per_minute=1)
        assert rl.check("key1") is True
        assert rl.check("key1") is False

        real_monotonic = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: real_monotonic() + 61)
        assert rl.check("key1") is True
