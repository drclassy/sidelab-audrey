from __future__ import annotations

import json
import os
from typing import Iterator

import requests

DEFAULT_NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"


def _nvidia_api_key(api_key: str | None = None) -> str:
    key = (api_key or os.getenv("NVIDIA_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("NVIDIA_API_KEY belum diisi. Tambahkan ke .env untuk memakai NVIDIA NIM.")
    return key


def _nvidia_timeout() -> float:
    try:
        return float(os.getenv("NVIDIA_TIMEOUT", "600"))
    except ValueError:
        return 600.0


class NvidiaClient:
    name = "nvidia"

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = (base_url or os.getenv("NVIDIA_BASE_URL", DEFAULT_NVIDIA_BASE_URL)).rstrip("/")

    def stream_chat(self, messages: list[dict], model: str) -> Iterator[str]:
        key = _nvidia_api_key(self.api_key)
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"

        with requests.post(
            url,
            headers=headers,
            json=payload,
            stream=True,
            timeout=_nvidia_timeout(),
        ) as response:
            if response.status_code >= 400:
                detail = response.text.strip()
                try:
                    msg = json.loads(detail)
                    err = msg.get("error") or msg.get("message") or detail
                    if isinstance(err, dict):
                        err = err.get("message") or str(err)
                except json.JSONDecodeError:
                    err = detail
                raise RuntimeError(f"NVIDIA NIM error ({response.status_code}): {err}")

            for line in response.iter_lines(decode_unicode=True):
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content
