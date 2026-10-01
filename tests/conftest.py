import struct
import wave
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def silent_wav(tmp_path: Path) -> Path:
    """4.2 s of 16 kHz mono silence — enough for duration/range checks, no real audio needed."""
    p = tmp_path / "clip.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(struct.pack("<h", 0) * int(16000 * 4.2))
    return p
