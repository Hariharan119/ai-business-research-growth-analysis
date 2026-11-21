"""Simple asynchronous request rate limiter."""

import asyncio
import time


class AsyncRateLimiter:
    def __init__(self, min_interval_seconds: float):
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds cannot be negative")

        self.min_interval_seconds = min_interval_seconds
        self._lock = asyncio.Lock()
        self._last_request = 0.0

    async def wait(self):
        async with self._lock:
            elapsed = time.monotonic() - self._last_request
            remaining = self.min_interval_seconds - elapsed

            if remaining > 0:
                await asyncio.sleep(remaining)

            self._last_request = time.monotonic()
