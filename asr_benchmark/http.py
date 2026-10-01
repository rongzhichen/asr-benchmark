"""One guarded HTTP boundary: no redirects, no retries, timing and status captured."""
from __future__ import annotations

import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None


@dataclass
class HttpResult:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)
    elapsed_seconds: float = 0.0


def send(request: urllib.request.Request, timeout: float) -> HttpResult:
    """Send exactly one request. HTTP errors are returned, not raised; network errors propagate."""
    opener = urllib.request.build_opener(NoRedirects())
    started = time.monotonic()
    try:
        response = opener.open(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read()
        status = response.code
        headers = {k.lower(): v for k, v in response.headers.items()}
    return HttpResult(status=status, body=body, headers=headers, elapsed_seconds=time.monotonic() - started)


def multipart(fields: dict[str, str], file_field: str, filename: str, content_type: str, data: bytes) -> tuple[bytes, str]:
    boundary = "asrbench-" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
                 f"Content-Type: {content_type}\r\n\r\n".encode())
    parts.append(data)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"
