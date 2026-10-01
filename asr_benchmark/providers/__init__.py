from .base import Provider, ProviderResponse
from .deepgram import Deepgram
from .doubao import Doubao
from .fake import Fake
from .microsoft import Microsoft
from .openai_whisper import OpenAIWhisper
from .soniox import Soniox

REGISTRY: dict[str, type[Provider]] = {p.name: p for p in (Doubao, OpenAIWhisper, Microsoft, Deepgram, Soniox, Fake)}

__all__ = ["Provider", "ProviderResponse", "REGISTRY"]
