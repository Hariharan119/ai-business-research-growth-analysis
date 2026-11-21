"""Connectivity check for the configured language model provider."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from pydantic import BaseModel  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.exceptions import ApplicationError  # noqa: E402
from app.services.llm_client import LlmClient, TokenUsage  # noqa: E402

EXCLUDED_MARKERS = ("whisper", "tts", "guard", "orpheus", "embed")


class Ping(BaseModel):
    status: str
    answer: int


async def main() -> int:
    settings = get_settings()
    try:
        async with LlmClient(settings) as client:
            models = [m for m in await client.list_models() if not any(x in m.lower() for x in EXCLUDED_MARKERS)]
            print("Active chat models:")
            for model in models:
                print(f"  {model}")
            if not settings.llm_model:
                print("\nLLM_MODEL is not set.")
                return 0
            usage = TokenUsage()
            result = await client.complete_json(
                system="You return JSON only.",
                user="Return status ok and the answer to 2+2.",
                schema=Ping,
                usage=usage,
            )
            print(f"\nModel {settings.llm_model} responded: {result.model_dump()}")
            print(f"Token usage: {usage.total_tokens}")
            return 0
    except ApplicationError as exc:
        print(f"\n{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
