"""Offline provider for tests and demos: returns a saved raw payload instead of calling a network."""
from __future__ import annotations

from pathlib import Path

from .base import Provider, ProviderResponse


class Fake(Provider):
    name = "fake"
    model = "fixture"
    time_unit = "milliseconds"
    key_pattern = Provider.key_pattern

    def options(self, language):
        return {"source": "fixture"}

    def transcribe(self, audio: Path, audio_info: dict, key: str, language, *, fixture: str = "", **settings) -> ProviderResponse:
        payload = Path(fixture).read_bytes() if fixture else b'{"result": {"text": "", "utterances": []}}'
        return ProviderResponse(raw=payload, http_status=200, succeeded=True, elapsed_seconds=0.001, provider_request_id="fake")
