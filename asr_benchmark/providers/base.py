"""Provider adapter contract."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProviderResponse:
    """What a single provider attempt produced. `raw` is the unmodified provider payload."""
    raw: bytes
    http_status: int | None
    succeeded: bool
    elapsed_seconds: float
    provider_request_id: str | None = None
    receipts: list[dict[str, Any]] = field(default_factory=list)  # multi-step providers (upload/poll/download)
    note: str | None = None


class Provider:
    """Subclass per vendor. One attempt, no retries, no redirects, credential never written to disk."""
    name: str = "base"
    model: str = ""
    time_unit: str = "milliseconds"  # how the raw payload expresses time
    default_language: str | None = None
    key_pattern = re.compile(r"[A-Za-z0-9._-]{16,512}")

    def options(self, language: str | None) -> dict[str, Any]:
        """Request options recorded in the manifest."""
        return {}

    def transcribe(self, audio: Path, audio_info: dict, key: str, language: str | None, **settings: Any) -> ProviderResponse:
        raise NotImplementedError

    @classmethod
    def read_key(cls, key_file: Path) -> str:
        """Accept a file containing exactly one key (optionally `label: key`); refuse anything else."""
        lines = [s.strip().strip("`\"' ") for s in key_file.read_text().splitlines() if s.strip()]
        candidates = []
        for line in lines:
            value = line.split(":", 1)[1].strip() if ":" in line and " " not in line.split(":", 1)[0] else line
            if cls.key_pattern.fullmatch(value):
                candidates.append(value)
        if len(candidates) != 1:
            raise ValueError(f"{key_file}: expected exactly one API key (optionally 'label: key'), found {len(candidates)}")
        return candidates[0]
