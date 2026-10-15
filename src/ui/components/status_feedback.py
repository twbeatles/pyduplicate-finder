"""상태 피드백 단일 통로 (경로 B).

KTrain이 ``InfoBar`` + 상태 라벨로 상태를 전달하는 것과 같은 위치의 대책:
sticky notice(InfoBar) / transient 알림(toast) / 진행 상태가 서로 다른
문구로 동시에 표시되는 중복·충돌을 방지한다. 동일 문구 반복은 1회로 합치고,
window에 해당 위젯이 없으면 조용히 no-op 한다 (호출자 분기 금지).
"""

from __future__ import annotations

from typing import Any


class StatusFeedback:
    def __init__(self, window: Any) -> None:
        self._window = window
        self._last_status = ""
        self._last_notice = ("", "", "")

    def show_status(self, text: str) -> bool:
        """하단 상태 라벨 갱신. 동일 문구 반복이면 갱신을 건너뛰고 False."""
        text = str(text or "")
        if text == self._last_status:
            return False
        self._last_status = text
        label = getattr(self._window, "status_label", None)
        try:
            if label is not None:
                label.setText(text)
                return True
        except Exception:
            pass
        return False

    def show_notice(self, severity: str, title: str, message: str = "") -> bool:
        """sticky 안내 (InfoBar 우선, 없으면 toast). 동일 내용 반복은 False."""
        key = (str(severity), str(title), str(message))
        if key == self._last_notice:
            return False
        self._last_notice = key
        bar = getattr(self._window, "scan_notice_bar", None)
        try:
            if bar is not None and hasattr(bar, "show_notice"):
                bar.show_notice(severity, title, message)
                return True
        except Exception:
            pass
        toast = getattr(self._window, "toast_manager", None)
        try:
            if toast is not None:
                kind = {"success": "success", "warning": "warning", "error": "error"}.get(
                    severity, "info"
                )
                getattr(toast, kind)(f"{title} {message}".strip())
                return True
        except Exception:
            pass
        return False

    def clear_notice(self) -> None:
        bar = getattr(self._window, "scan_notice_bar", None)
        try:
            if bar is not None and hasattr(bar, "dismiss"):
                bar.dismiss()
        except Exception:
            pass
        self._last_notice = ("", "", "")


__all__ = ["StatusFeedback"]
