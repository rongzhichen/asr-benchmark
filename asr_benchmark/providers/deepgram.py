"""Deepgram pre-recorded transcription (Nova-3)."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from ..http import send
from .base import Provider, ProviderResponse


class Deepgram(Provider):
    name = "deepgram"
    model = "nova-3"
    time_unit = "seconds"
    default_language = "zh-CN"

    def options(self, language):
        return {"model": self.model, "language": language or self.default_language, "punctuate": "true",
                "smart_format": "false", "numerals": "false", "utterances": "true", "diarize": "false",
                "multichannel": "false", "mip_opt_out": "true"}

    def transcribe(self, audio: Path, audio_info: dict, key: str, language, **settings) -> ProviderResponse:
        url = "https://api.deepgram.com/v1/listen?" + urllib.parse.urlencode(self.options(language))
        req = urllib.request.Request(url, data=audio.read_bytes(), method="POST",
                                     headers={"Authorization": "Token " + key, "Content-Type": audio_info["content_type"]})
        r = send(req, timeout=180)
        try:
            ok = r.status == 200 and bool(json.loads(r.body).get("results", {}).get("channels"))
            rid = json.loads(r.body).get("metadata", {}).get("request_id")
        except ValueError:
            ok, rid = False, None
        return ProviderResponse(raw=r.body, http_status=r.status, succeeded=ok, elapsed_seconds=r.elapsed_seconds,
                                provider_request_id=rid)
