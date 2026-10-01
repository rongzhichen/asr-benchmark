"""Azure AI Speech fast transcription with LLM Speech enhanced mode (REST api-version 2025-10-15)."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from ..http import multipart, send
from .base import Provider, ProviderResponse

API_VERSION = "2025-10-15"


def endpoint_url(endpoint: str) -> str:
    p = urllib.parse.urlsplit(endpoint)
    host = p.hostname or ""
    if (p.scheme != "https" or p.username or p.password or p.query or p.fragment
            or p.port not in (None, 443) or p.path not in ("", "/") or not host.endswith(".cognitiveservices.azure.com")):
        raise ValueError("--endpoint must be your HTTPS Azure Speech resource root (https://<name>.cognitiveservices.azure.com)")
    return endpoint.rstrip("/") + "/speechtotext/transcriptions:transcribe?api-version=" + API_VERSION


class Microsoft(Provider):
    name = "microsoft"
    model = "LLM Speech (enhanced mode)"
    time_unit = "milliseconds"
    default_language = "zh-CN"

    def options(self, language):
        return {"locales": [language or self.default_language], "enhancedMode": {"enabled": True, "task": "transcribe"}}

    def transcribe(self, audio: Path, audio_info: dict, key: str, language, *, endpoint: str = "", **settings) -> ProviderResponse:
        url = endpoint_url(endpoint)
        body, ctype = multipart({"definition": json.dumps(self.options(language))}, "audio", audio.name,
                                audio_info["content_type"], audio.read_bytes())
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": ctype})
        r = send(req, timeout=180)
        return ProviderResponse(raw=r.body, http_status=r.status, succeeded=200 <= r.status < 300,
                                elapsed_seconds=r.elapsed_seconds,
                                provider_request_id=r.headers.get("apim-request-id") or r.headers.get("x-requestid"),
                                note="Confidence is documented as unavailable for LLM Speech; a raw 0 is not a score.")
