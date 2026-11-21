"""Small JSON file cache with TTL and optional stale reads."""
from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

class JsonFileCache:
    def __init__(self, directory: str | Path, ttl_seconds: float = 3600) -> None:
        self.directory = Path(directory)
        self.ttl_seconds = float(ttl_seconds)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(str(key).encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    def get(self, key: str, allow_stale: bool = False) -> Any | None:
        path = self._path(key)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - float(payload["cached_at"])
            if not allow_stale and age > self.ttl_seconds:
                return None
            return payload["value"]
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def set(self, key: str, value: Any) -> None:
        path = self._path(key)
        temporary = path.with_suffix(".tmp")
        payload = {"cached_at": time.time(), "value": value}
        temporary.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, path)

    def clear(self) -> None:
        for path in self.directory.glob("*.json"):
            path.unlink(missing_ok=True)
