from __future__ import annotations

import os

DEFAULT_BACKEND = "deepseek"
DEFAULT_LOCAL_MODEL = "medgemma:4b"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
AVAILABLE_DEEPSEEK_MODELS = ("deepseek-v4-flash", "deepseek-v4-pro")


def normalize_backend(value: str | None) -> str:
    backend = (value or "").strip().lower()
    if backend in {"deepseek", "cloud", "remote", "1"}:
        return "deepseek"
    if backend in {"local", "ollama", "2"}:
        return "local"
    return DEFAULT_BACKEND


def resolve_backend_choice(raw: str | None) -> str:
    return normalize_backend(raw)


def default_model_for_backend(backend: str | None) -> str:
    if normalize_backend(backend) == "local":
        return os.getenv("AUDREY_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)
    return os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)


def render_mode_menu() -> str:
    local_model = os.getenv("AUDREY_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)
    deepseek_model = os.getenv("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    return (
        "Pilih backend inference untuk sesi ini.\n"
        f"1. DeepSeek (Recommended) — {deepseek_model}\n"
        f"2. Local Ollama — {local_model}\n"
        "Tekan Enter untuk DeepSeek."
    )
