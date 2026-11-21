"""Reusable asynchronous retry helper."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    *,
    attempts: int,
    base_delay: float,
    retry_on: tuple[type[BaseException], ...],
    description: str = "operation",
) -> T:
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    for attempt in range(attempts):
        try:
            return await operation()
        except retry_on:
            if attempt == attempts - 1:
                raise

            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)

    raise RuntimeError(f"{description} failed unexpectedly")
