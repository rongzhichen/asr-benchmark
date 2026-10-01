"""Provenance helpers: hashing, redacted JSON writes, checksums, tool versions."""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from pathlib import Path
from typing import Any

from . import __version__


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


class Redactor:
    """Replaces a credential wherever it might leak into files we write."""

    def __init__(self, secret: str | None):
        self.secret = secret or ""

    def text(self, s: str) -> str:
        return s.replace(self.secret, "[REDACTED]") if self.secret else s

    def data(self, b: bytes) -> tuple[bytes, bool]:
        if self.secret and self.secret.encode() in b:
            return b.replace(self.secret.encode(), b"[REDACTED]"), True
        return b, False


def save_json(path: Path, value: Any, redactor: Redactor | None = None) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if redactor:
        text = redactor.text(text)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path, default: Any = None) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def tool_versions() -> dict[str, Any]:
    info: dict[str, Any] = {"asr_benchmark": __version__, "python": platform.python_version(),
                            "platform": platform.platform()}
    for name, cmd in {"ffmpeg": ["ffmpeg", "-version"], "git_commit": ["git", "rev-parse", "HEAD"]}.items():
        try:
            info[name] = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).splitlines()[0]
        except Exception:  # noqa: BLE001 - absence is informative, not fatal
            info[name] = None
    return info


def write_checksums(root: Path) -> dict[str, str]:
    hashes = {str(p.relative_to(root)): sha256_file(p)
              for p in sorted(root.rglob("*")) if p.is_file() and p.name != "checksums.json"}
    save_json(root / "checksums.json", hashes)
    return hashes


def verify_checksums(root: Path) -> list[str]:
    """Return the list of files whose hash no longer matches checksums.json."""
    recorded = load_json(root / "checksums.json", {})
    return [rel for rel, h in recorded.items() if not (root / rel).exists() or sha256_file(root / rel) != h]
