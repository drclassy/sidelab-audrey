from __future__ import annotations

from .config import normalize_backend
from .deepseek_client import DeepSeekClient
from .local_client import LocalClient
from .nvidia_client import NvidiaClient


def build_provider(mode: str, api_key: str | None = None, base_url: str | None = None):
    backend = normalize_backend(mode)
    if backend == "local":
        return LocalClient()
    if backend == "nvidia":
        return NvidiaClient(api_key=api_key, base_url=base_url)
    return DeepSeekClient(api_key=api_key, base_url=base_url)
