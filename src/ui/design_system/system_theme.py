"""OS system-theme detection and watcher (srtgo pattern, dependency-light).

``darkdetect`` is an optional hard dependency declared in requirements.txt,
but every entry point here degrades gracefully to ``"light"`` when the
import or backend call fails (e.g. minimal containers, headless CI).
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

_POLL_MS = 3000


def system_theme() -> str:
    """Return ``"dark"`` or ``"light"`` from the OS setting."""
    try:
        import darkdetect

        return "dark" if darkdetect.theme() == "Dark" else "light"
    except Exception:
        return "light"


def normalize_bool(value: object, default: bool = True) -> bool:
    """Normalize QSettings bool-ish values (bool, "true"/"1", 0/1)."""
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() not in ("0", "false", "no", "off", "")


def resolve_startup_theme(settings) -> str:
    """Startup theme: follow the OS while follow-mode is on, else stored pref."""
    try:
        follow = normalize_bool(settings.value("app/follow_system_theme", True), True)
    except Exception:
        follow = True
    if follow:
        try:
            theme = system_theme()
            settings.setValue("app/theme", theme)
            return theme
        except Exception:
            pass
    try:
        stored = settings.value("app/theme", "light")
        return str(stored or "light")
    except Exception:
        return "light"


class SystemThemeWatcher(QObject):
    """Emit ``theme_changed`` when the OS theme flips (poll + native signal)."""

    theme_changed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._last = system_theme()
        self._timer = QTimer(self)
        self._timer.setInterval(_POLL_MS)
        self._timer.timeout.connect(self._poll)

    def start(self) -> None:
        try:
            from PySide6.QtGui import QGuiApplication

            hints = QGuiApplication.styleHints()
            changed = getattr(hints, "colorSchemeChanged", None)
            if changed is not None:
                try:
                    changed.connect(lambda _scheme: self._poll())
                except Exception:
                    pass
        except Exception:
            pass
        self._timer.start()

    def stop(self) -> None:
        try:
            self._timer.stop()
        except Exception:
            pass

    def _poll(self) -> None:
        current = system_theme()
        if current != self._last:
            self._last = current
            self.theme_changed.emit(current)


__all__ = [
    "SystemThemeWatcher",
    "normalize_bool",
    "resolve_startup_theme",
    "system_theme",
]
