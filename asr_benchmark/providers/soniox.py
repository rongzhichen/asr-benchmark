"""Soniox asynchronous transcription (stt-async-v5): upload → create → poll → download → delete."""
from __future__ import annotations

import json
import time
import urllib.request
import uuid
from pathlib import Path

from ..http import multipart, send
from .base import Provider, ProviderResponse

BASE = "https://api.soniox.com"


class Soniox(Provider):
    name = "soniox"
    model = "stt-async-v5"
    time_unit = "milliseconds"
    key_pattern = Provider.key_pattern

    def options(self, language):
        return {"model": self.model, "enable_speaker_diarization": False, "enable_language_identification": True}

    def transcribe(self, audio: Path, audio_info: dict, key: str, language, **settings) -> ProviderResponse:
        receipts: list[dict] = []
        started = time.monotonic()
        file_id = task_id = None
        stage = "upload"

        def call(method: str, path: str, data: bytes | None = None, ctype: str = "application/json") -> dict:
            req = urllib.request.Request(BASE + path, data=data, method=method,
                                         headers={"Authorization": "Bearer " + key, "Content-Type": ctype})
            r = send(req, timeout=90)
            receipts.append({"stage": stage, "method": method, "path": path, "status": r.status,
                             "elapsed_seconds": r.elapsed_seconds})
            if r.status >= 300:
                raise RuntimeError(f"{stage}: HTTP {r.status}: {r.body[:200]!r}")
            return json.loads(r.body) if r.body.strip() else {}

        raw, ok, note = b"", False, None
        try:
            body, ctype = multipart({}, "file", audio.name, audio_info["content_type"], audio.read_bytes())
            file_id = call("POST", "/v1/files", body, ctype)["id"]
            stage = "create"
            config = {**self.options(language), "file_id": file_id, "client_reference_id": str(uuid.uuid4())}
            task_id = call("POST", "/v1/transcriptions", json.dumps(config).encode())["id"]
            stage = "poll"
            delay, deadline = 2.0, time.monotonic() + 600
            while True:
                task = call("GET", f"/v1/transcriptions/{task_id}")
                if task.get("status") in ("completed", "error"):
                    break
                if time.monotonic() + delay > deadline:
                    raise TimeoutError("polling deadline reached")
                time.sleep(delay)
                delay = min(delay * 1.5, 15)
            if task.get("status") != "completed":
                raise RuntimeError("provider reported error: " + json.dumps(task)[:300])
            stage = "download"
            req = urllib.request.Request(f"{BASE}/v1/transcriptions/{task_id}/transcript",
                                         headers={"Authorization": "Bearer " + key})
            r = send(req, timeout=90)
            receipts.append({"stage": stage, "method": "GET", "status": r.status, "elapsed_seconds": r.elapsed_seconds})
            raw, ok = r.body, r.status == 200
        except Exception as error:  # noqa: BLE001 - recorded, not retried
            note = f"{type(error).__name__}: {error}"
        finally:
            stage = "cleanup"
            for kind, ident in (("transcriptions", task_id), ("files", file_id)):
                if ident:
                    try:
                        call("DELETE", f"/v1/{kind}/{ident}")
                    except Exception as error:  # noqa: BLE001
                        receipts.append({"stage": "cleanup", "resource": kind, "deleted": False, "error": type(error).__name__})
        return ProviderResponse(raw=raw, http_status=None, succeeded=ok, elapsed_seconds=time.monotonic() - started,
                                provider_request_id=task_id, receipts=receipts, note=note)
