"""Shared separators — single replacement for duplicated local helpers."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame


def create_hseparator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep


def create_vseparator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    return sep


__all__ = ["create_hseparator", "create_vseparator"]
