"""위험 동작 확인 (경로 B).

KTrain ``MessageBox`` 확인과 같은 위치의 안전 절차를 고정한다:
확인 모달 → preflight → operation queue → 결과 표시. 본 모듈은 첫 단계
(확인 모달에 표시할 대상 요약 + 기본-취소 모달)만 담당하고,
preflight·큐 실행은 기존 ``OperationFlowController`` 가 그대로 수행한다.

핵심 규칙: 필터로 보이는 항목 수와 전체 체크된 항목 수가 다를 수 있으므로,
반드시 두 수량을 함께 명시한다.
"""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QWidget


def summarize_destructive_target(
    *,
    checked_count: int,
    visible_count: int | None = None,
    group_count: int | None = None,
    recoverable: str = "",
) -> str:
    """확인 모달 본문. 수량 불일치 시 경고를 포함한 문자열을 반환한다."""
    checked = max(0, int(checked_count or 0))
    lines = [f"선택된 파일: {checked}개"]
    if group_count is not None:
        lines.append(f"관련 그룹: {max(0, int(group_count))}개")
    if visible_count is not None and int(visible_count) != checked:
        lines.append(
            f"주의: 현재 화면에 보이는 항목({int(visible_count)}개)과 "
            f"실제 처리 대상({checked}개)이 다릅니다. "
            "필터로 숨겨진 항목도 처리됩니다."
        )
    if recoverable:
        lines.append(recoverable)
    return "\n".join(lines)


def confirm_destructive(
    parent: QWidget | None,
    title: str,
    detail: str,
) -> bool:
    """위험 동작 확인 모달. 기본값은 취소이며, 확인 선택 시에만 True."""
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(detail)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setStandardButtons(
        QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
    )
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    box.setEscapeButton(QMessageBox.StandardButton.Cancel)
    return box.exec() == QMessageBox.StandardButton.Accepted


__all__ = ["confirm_destructive", "summarize_destructive_target"]
