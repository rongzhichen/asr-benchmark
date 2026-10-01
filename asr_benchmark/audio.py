"""Audio inspection without decoding: WAV via the standard library, otherwise ffprobe if present."""
from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

from .provenance import sha256_file

CONTENT_TYPES = {".wav": "audio/wav", ".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".ogg": "audio/ogg"}


def describe(path: Path) -> dict:
    info: dict = {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path),
                  "content_type": CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream"),
                  "duration_ms": None, "sample_rate": None, "channels": None}
    if path.suffix.lower() == ".wav":
        with wave.open(str(path)) as w:
            info.update(sample_rate=w.getframerate(), channels=w.getnchannels(), sample_width_bytes=w.getsampwidth(),
                        frames=w.getnframes(), duration_ms=w.getnframes() * 1000 / w.getframerate())
        return info
    try:
        out = subprocess.check_output(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
                                      text=True, stderr=subprocess.DEVNULL)
        probe = json.loads(out)
        stream = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), {})
        duration = probe.get("format", {}).get("duration") or stream.get("duration")
        info.update(duration_ms=float(duration) * 1000 if duration else None,
                    sample_rate=int(stream["sample_rate"]) if stream.get("sample_rate") else None,
                    channels=stream.get("channels"), probed_with="ffprobe")
    except Exception:  # noqa: BLE001
        info["duration_note"] = "ffprobe unavailable; duration unknown, range checks skipped"
    return info
