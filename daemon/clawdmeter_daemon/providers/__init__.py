"""Provider plugin registry.

Each adapter registers a factory keyed by `provider.id` (anthropic, codex,
langdock, opencode, bedrock). The polling loop instantiates only the providers
that are enabled in the user's config — missing optional dependencies (boto3
etc.) are imported lazily so a user without AWS can still run the daemon.
"""

from __future__ import annotations

from typing import Callable

from ..config import ProviderConfig
from .base import Provider, Snapshot

_FACTORIES: dict[str, Callable[[ProviderConfig], Provider]] = {}


def register(provider_id: str, factory: Callable[[ProviderConfig], Provider]) -> None:
    _FACTORIES[provider_id] = factory


def create(cfg: ProviderConfig) -> Provider | None:
    """Instantiate the adapter for one ProviderConfig, or None on import error.

    Errors are swallowed and logged at the call site — we don't want an
    optional dependency missing for one adapter to crash the whole daemon.
    """
    factory = _FACTORIES.get(cfg.id)
    if factory is None:
        return None
    return factory(cfg)


def known_provider_ids() -> list[str]:
    return sorted(_FACTORIES.keys())


# Adapter modules self-register on import. Import them all so register()
# runs before the polling loop walks the config.
from . import anthropic as _anthropic  # noqa: F401
from . import codex as _codex  # noqa: F401
from . import langdock as _langdock  # noqa: F401
from . import opencode as _opencode  # noqa: F401
from . import bedrock as _bedrock  # noqa: F401

__all__ = ["Provider", "Snapshot", "register", "create", "known_provider_ids"]
