from __future__ import annotations

from typing import Protocol


class Translatable(Protocol):
    def retranslate(self) -> None: ...


class Themeable(Protocol):
    def apply_theme(self, mode: str) -> None: ...


class PageContract(Translatable, Themeable, Protocol):
    """
    Convention for page widgets/classes.

    This is intentionally lightweight: pages can be plain QWidget instances that
    simply expose retranslate/apply_theme methods.
    """

    pass

