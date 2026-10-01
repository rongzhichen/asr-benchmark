"""ByteDance / Volcengine Doubao Turbo recording-file recognition (`volc.bigasr.auc_turbo`)."""
from __future__ import annotations

import base64
import json
import urllib.request
import uuid
from pathlib import Path

from ..http import send
from .base import Provider, ProviderResponse

ENDPOINT = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"
RESOURCE = "volc.bigasr.auc_turbo"


class Doubao(Provider):
    name = "doubao"
    model = "bigmodel (Turbo)"
    time_unit = "milliseconds"

    def options(self, language):
        return {"model_name": "bigmodel", "show_utterances": True, "enable_punc": True,
                "enable_ddc": False, "enable_itn": False, "enable_speaker_info": False}

    def transcribe(self, audio: Path, audio_info: dict, key: str, language, **settings) -> ProviderResponse:
        if audio.suffix.lower() != ".wav":
            raise ValueError("Doubao adapter sends PCM WAV; convert first (ffmpeg -i in.m4a -c:a pcm_s16le out.wav)")
        if (audio_info.get("duration_ms") or 0) > 7_200_000 or audio_info["bytes"] > 100_000_000:
            raise ValueError("Audio exceeds documented Turbo limits (2 h / 100 MB)")
        request_id = str(uuid.uuid4())
        payload = {"user": {"uid": "asr-benchmark"},
                   "audio": {"format": "wav", "data": base64.b64encode(audio.read_bytes()).decode("ascii")},
                   "request": self.options(language)}
        req = urllib.request.Request(ENDPOINT, data=json.dumps(payload).encode(), method="POST", headers={
            "Content-Type": "application/json", "X-Api-Key": key, "X-Api-Resource-Id": RESOURCE,
            "X-Api-Request-Id": request_id, "X-Api-Sequence": "-1"})
        r = send(req, timeout=300)
        api_status = r.headers.get("x-api-status-code")
        return ProviderResponse(raw=r.body, http_status=r.status, succeeded=(r.status == 200 and api_status == "20000000"),
                                elapsed_seconds=r.elapsed_seconds, provider_request_id=r.headers.get("x-tt-logid"),
                                receipts=[{"request_id": request_id, "api_status_code": api_status}])
