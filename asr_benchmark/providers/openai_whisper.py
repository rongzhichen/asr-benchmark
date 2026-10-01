"""OpenAI audio transcription (whisper-1) with verbose JSON and word timestamps."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from ..http import multipart, send
from .base import Provider, ProviderResponse

ENDPOINT = "https://api.openai.com/v1/audio/transcriptions"


class OpenAIWhisper(Provider):
    name = "whisper"
    model = "whisper-1"
    time_unit = "seconds"

    def options(self, language):
        o = {"model": self.model, "response_format": "verbose_json", "timestamp_granularities[]": "word"}
        if language:
            o["language"] = language.split("-")[0]
        return o

    def transcribe(self, audio: Path, audio_info: dict, key: str, language, **settings) -> ProviderResponse:
        opts = self.options(language)
        # timestamp_granularities[] must be repeated for both segment and word
        fields = {k: v for k, v in opts.items() if k != "timestamp_granularities[]"}
        body, ctype = multipart(fields, "file", audio.name, audio_info["content_type"], audio.read_bytes())
        # append granularity fields manually (multipart() takes a dict; keys must be unique)
        boundary = ctype.split("boundary=")[1]
        extra = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="timestamp_granularities[]"\r\n\r\n{g}\r\n'.encode()
                         for g in ("segment", "word"))
        body = body.replace(f"\r\n--{boundary}--\r\n".encode(), b"\r\n" + extra + f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                     headers={"Authorization": "Bearer " + key, "Content-Type": ctype})
        r = send(req, timeout=300)
        ok = r.status == 200 and "text" in json.loads(r.body or b"{}")
        return ProviderResponse(raw=r.body, http_status=r.status, succeeded=ok, elapsed_seconds=r.elapsed_seconds,
                                provider_request_id=r.headers.get("x-request-id"))
