"""PanelRegistry — decorator-based registration of panel types."""

from __future__ import annotations

from typing import Type

from jig.panels.base import PanelBase


class PanelRegistry:
    """Central registry mapping panel type names to their classes.

    Usage::

        @PanelRegistry.register
        class ChartPanel(PanelBase):
            panel_type_name = "Chart"
            ...

        # Later:
        cls = PanelRegistry.get("Chart")
        panel = cls(ctx)
    """

    _registry: dict[str, Type[PanelBase]] = {}

    @classmethod
    def register(cls, panel_cls: Type[PanelBase]) -> Type[PanelBase]:
        """Class decorator that registers a PanelBase subclass."""
        name = panel_cls.panel_type_name
        if name in cls._registry:
            raise ValueError(f"Panel type '{name}' already registered")
        cls._registry[name] = panel_cls
        return panel_cls

    @classmethod
    def get(cls, name: str) -> Type[PanelBase] | None:
        return cls._registry.get(name)

    @classmethod
    def all_names(cls) -> list[str]:
        return sorted(cls._registry.keys())

    @classmethod
    def all_panels(cls) -> dict[str, Type[PanelBase]]:
        return dict(cls._registry)
