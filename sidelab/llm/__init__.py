# Architected and built by classy+.
from .config import (
    AVAILABLE_DEEPSEEK_MODELS,
    AVAILABLE_NVIDIA_MODELS,
    DEFAULT_BACKEND,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_LOCAL_MODEL,
    DEFAULT_NVIDIA_MODEL,
    PROVIDER_REGISTRY,
    default_model_for_backend,
    render_mode_menu,
    resolve_backend_choice,
)
from .router import build_provider

__all__ = [
    "AVAILABLE_DEEPSEEK_MODELS",
    "AVAILABLE_NVIDIA_MODELS",
    "DEFAULT_BACKEND",
    "DEFAULT_DEEPSEEK_MODEL",
    "DEFAULT_LOCAL_MODEL",
    "DEFAULT_NVIDIA_MODEL",
    "PROVIDER_REGISTRY",
    "build_provider",
    "default_model_for_backend",
    "render_mode_menu",
    "resolve_backend_choice",
]
