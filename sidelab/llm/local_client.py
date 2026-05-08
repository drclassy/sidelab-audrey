# Architected and built by classy+.
from __future__ import annotations

from typing import Iterator


class LocalClient:
    name = "local"

    def stream_chat(self, messages: list[dict], model: str) -> Iterator[str]:
        try:
            import ollama
        except ImportError as exc:
            raise RuntimeError("Ollama package belum tersedia. Install dependencies untuk memakai mode Local.") from exc

        try:
            stream = ollama.chat(model=model, messages=messages, stream=True)
            for chunk in stream:
                token = chunk.get("message", {}).get("content", "")
                if token:
                    yield token
        except Exception as exc:
            raise RuntimeError(f"Local Ollama error: {exc}") from exc


def available_models() -> list[str]:
    try:
        import ollama
    except ImportError:
        return []

    try:
        return [m.model for m in ollama.list().models]
    except Exception:
        return []
