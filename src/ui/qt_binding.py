"""Qt binding diagnostic for the PyDuplicateFinder GUI (경로 B, 순수 PySide6).

KTrain의 ``ktrain/gui/qt_binding.py`` 가 해결한 것과 같은 문제를 다룬다:
``PyQt6-Fluent-Widgets`` 계열 패키지는 ``PySide6-Fluent-Widgets`` 와 동일한
``qfluentwidgets`` 네임스페이스를 사용하므로, 같은 환경에 섞여 있으면
``No module named 'PyQt6'`` 형태의 실행·빌드 실패를 일으킨다.
본 모듈은 그 원리를 독립적으로 구현한 것으로, KTrain 코드를 복사하지 않았다.

규칙:
- 제품 코드는 ``qfluentwidgets`` 를 import하지 않는다 (Gate 0, 경로 B).
  본 모듈은 import 없이 ``importlib`` 메타데이터·소스 텍스트만 검사한다.
- 검사는 진단을 위한 것으로, 패키지 설치·제거를 수행하지 않는다.
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
from dataclasses import dataclass
from pathlib import Path

#: 같은 ``qfluentwidgets`` 네임스페이스를 두고 PySide6 에디션과 충돌하는 배포명.
CONFLICTING_DIST_NAMES: frozenset[str] = frozenset(
    {
        "pyqt6-fluent-widgets",
        "pyqt5-fluent-widgets",
        "pyqt-fluent-widgets",
        "pyqt6-frameless-window",
        "pyqt5-frameless-window",
    }
)

_FIX_HINT = (
    "해결:\n"
    '  pip uninstall PyQt6-Fluent-Widgets PyQt6-Frameless-Window PyQt5-Fluent-Widgets PyQt5-Frameless-Window\n'
    '  pip install -r requirements.txt'
)


def binding_from_source(text: str) -> str:
    """소스 텍스트에서 Qt 바인딩 이름을 판별한다."""
    if "from PyQt6" in text or "import PyQt6" in text:
        return "PyQt6"
    if "from PyQt5" in text or "import PyQt5" in text:
        return "PyQt5"
    if "from PySide6" in text or "import PySide6" in text:
        return "PySide6"
    if "from PySide2" in text or "import PySide2" in text:
        return "PySide2"
    return "unknown"


def is_pyside6_binding(name: str | None) -> bool:
    return name == "PySide6"


@dataclass(frozen=True)
class QtBindingReport:
    ok: bool
    skipped: bool
    errors: tuple[str, ...]
    fluent_path: str | None
    fluent_binding: str | None
    frameless_path: str | None
    frameless_binding: str | None
    conflicting_dists: tuple[str, ...]


def _resolved_source(module_name: str) -> Path | None:
    try:
        spec = importlib.util.find_spec(module_name)
    except Exception:
        return None
    if spec is None or not spec.origin:
        return None
    origin = Path(spec.origin)
    if module_name == "qfluentwidgets":
        cfg = origin.parent / "common" / "config.py"
        if cfg.is_file():
            return cfg
    return origin if origin.is_file() else None


def installed_conflicting_dists() -> tuple[str, ...]:
    names: list[str] = []
    seen: set[str] = set()
    for dist in importlib.metadata.distributions():
        try:
            raw = dist.metadata.get("Name")
        except Exception:
            continue
        if not raw:
            continue
        key = raw.lower()
        if key in CONFLICTING_DIST_NAMES and key not in seen:
            seen.add(key)
            names.append(raw)
    return tuple(sorted(names, key=str.lower))


def inspect_qt_bindings(*, check_conflicting_dists: bool = True) -> QtBindingReport:
    """현재 환경의 Fluent/Frameless 패키지 바인딩을 검사한다.

    ``qfluentwidgets`` 가 아예 없으면 경로 B 정상 상태이므로 ``ok=True`` 를
    반환한다 (없음을 오류로 취급하지 않는다).
    """
    fluent_path = _resolved_source("qfluentwidgets")
    frameless_path = _resolved_source("qframelesswindow")
    conflicts = installed_conflicting_dists() if check_conflicting_dists else ()

    if fluent_path is None and frameless_path is None and not conflicts:
        return QtBindingReport(
            ok=True,
            skipped=True,
            errors=(),
            fluent_path=None,
            fluent_binding=None,
            frameless_path=None,
            frameless_binding=None,
            conflicting_dists=(),
        )

    errors: list[str] = []
    fluent_binding: str | None = None
    frameless_binding: str | None = None

    if fluent_path is not None:
        try:
            fluent_binding = binding_from_source(
                fluent_path.read_text(encoding="utf-8", errors="replace")
            )
        except Exception:
            fluent_binding = "unknown"
        if not is_pyside6_binding(fluent_binding):
            errors.append(
                f"qfluentwidgets 가 {fluent_binding} 에디션입니다: {fluent_path}"
            )
        # PySide6 에디션이 설치되어 있어도 경로 B 제품 코드는 이를 import하지
        # 않으므로 정상이다. 존재 사실은 report.fluent_binding 으로만 전달한다.
    if frameless_path is not None:
        try:
            frameless_binding = binding_from_source(
                frameless_path.read_text(encoding="utf-8", errors="replace")
            )
        except Exception:
            frameless_binding = "unknown"
        if not is_pyside6_binding(frameless_binding):
            errors.append(
                f"qframelesswindow 가 {frameless_binding} 에디션입니다: {frameless_path}"
            )
    if conflicts:
        errors.append("충돌 패키지 설치됨: " + ", ".join(conflicts))

    return QtBindingReport(
        ok=not errors,
        skipped=False,
        errors=tuple(errors),
        fluent_path=str(fluent_path) if fluent_path else None,
        fluent_binding=fluent_binding,
        frameless_path=str(frameless_path) if frameless_path else None,
        frameless_binding=frameless_binding,
        conflicting_dists=conflicts,
    )


def format_qt_binding_error(report: QtBindingReport) -> str:
    lines = [
        "PyDuplicateFinder GUI 는 순수 PySide6 로 동작합니다 (경로 B).",
        "PyQt6-Fluent-Widgets 계열이 같은 환경에 있으면 Qt 바인딩 충돌이 발생할 수 있습니다.",
        "",
        *report.errors,
        "",
        _FIX_HINT,
    ]
    return "\n".join(lines)


__all__ = [
    "CONFLICTING_DIST_NAMES",
    "QtBindingReport",
    "binding_from_source",
    "format_qt_binding_error",
    "inspect_qt_bindings",
    "installed_conflicting_dists",
    "is_pyside6_binding",
]
