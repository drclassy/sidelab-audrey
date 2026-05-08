from __future__ import annotations

import json
import os
from typing import Iterator

import requests

from .config import AVAILABLE_DEEPSEEK_MODELS, DEFAULT_DEEPSEEK_MODEL


def _deepseek_base_url() -> str:
    return os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")


def _deepseek_api_key(api_key: str | None = None) -> str:
    key = (api_key or os.getenv("DEEPSEEK_API_KEY", "")).strip()
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY belum diisi. Tambahkan ke .env untuk memakai DeepSeek.")
    return key


def _deepseek_timeout() -> float:
    raw = os.getenv("DEEPSEEK_TIMEOUT", "600").strip()
    try:
        return float(raw)
    except ValueError:
        return 600.0


def _format_error(status_code: int, text: str) -> str:
    detail = text.strip()
    if not detail:
        return f"DeepSeek API error ({status_code})"
    try:
        payload = json.loads(detail)
    except json.JSONDecodeError:
        return f"DeepSeek API error ({status_code}): {detail}"
    if isinstance(payload, dict):
        message = payload.get("error") or payload.get("message") or payload.get("detail")
        if isinstance(message, dict):
            message = message.get("message") or message.get("type") or str(message)
        if message:
            return f"DeepSeek API error ({status_code}): {message}"
    return f"DeepSeek API error ({status_code}): {detail}"


class DeepSeekClient:
    name = "deepseek"
    model_choices = AVAILABLE_DEEPSEEK_MODELS

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = (base_url or _deepseek_base_url()).rstrip("/")

    def stream_chat(self, messages: list[dict], model: str) -> Iterator[str]:
        key = _deepseek_api_key(self.api_key)
        selected_model = model or DEFAULT_DEEPSEEK_MODEL
        payload = {
            "model": selected_model,
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
            timeout=_deepseek_timeout(),
        ) as response:
            if response.status_code >= 400:
                raise RuntimeError(_format_error(response.status_code, response.text))

            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                if line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                choices = payload.get("choices", [])
                for choice in choices:
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield content
