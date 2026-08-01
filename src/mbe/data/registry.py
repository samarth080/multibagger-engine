"""Small dependency registry for explicit provider selection and test swaps."""

from __future__ import annotations

from typing import Any

from mbe.data.provider import UnsupportedProviderOperation


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, dict[str, Any]] = {}
        self._defaults: dict[str, str] = {}

    def register(self, capability: str, name: str, provider: Any, *, default: bool = False) -> None:
        names = self._providers.setdefault(capability, {})
        if name in names:
            raise ValueError(f"provider {name!r} already registered for {capability!r}")
        names[name] = provider
        if default or capability not in self._defaults:
            self._defaults[capability] = name

    def get(self, capability: str, name: str | None = None) -> Any:
        selected = name or self._defaults.get(capability)
        provider = self._providers.get(capability, {}).get(selected or "")
        if provider is None:
            raise UnsupportedProviderOperation(
                f"no {capability!r} provider configured" + (f" as {selected!r}" if selected else "")
            )
        return provider

    def health(self) -> list[dict]:
        rows = []
        for capability, providers in sorted(self._providers.items()):
            for name, provider in sorted(providers.items()):
                detail = provider.health() if hasattr(provider, "health") else {"status": "configured"}
                rows.append({
                    "capability": capability,
                    "name": name,
                    "default": self._defaults.get(capability) == name,
                    **detail,
                })
        return rows


def default_registry() -> ProviderRegistry:
    from mbe.data.market import YahooChartQuoteProvider

    registry = ProviderRegistry()
    registry.register("quotes", "yahoo", YahooChartQuoteProvider(), default=True)
    return registry
