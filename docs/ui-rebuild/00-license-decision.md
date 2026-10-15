# UI Rebuild — 00 License Decision (Gate 0, 2026-10-15, 경로 A로 변경 2026-10-15)

## 판정: 경로 A (PySide6-Fluent-Widgets 기반, 사용자 승인) — 배포 시 의무 준수 필요

2026-10-15 사용자가 `PySide6-Fluent-Widgets` 포함 구현을 명시적으로 승인했으므로
Gate 0을 경로 A로 전환한다. 아래 의무는 승인 후에도 유효하며 배포 전 재확인한다.

## 근거

1. `PySide6-Fluent-Widgets` 는 듀얼 라이선스 (비상업 GPLv3 / 상업 유료)이다.
   공급자 안내: <https://pyqt-fluent-widgets.readthedocs.io/en/latest/license.html>
2. 대상 저장소의 `README.md` 는 MIT를 표기하지만, 저장소 루트에 `LICENSE` 파일이 없다.
   계획서 §2.1이 지적한 그대로이며, 본 작업 시작 시점에도 해소되지 않았다.
3. 따라서 GPLv3 의존성을 번들·배포하는 결합의 법적 적합성을 확정할 수 없다.
   `README` 의 MIT 표기만으로 호환을 단정하지 않는다.

## 결정 내용 (경로 A, 2026-10-15 갱신)

- 제품 의존성에 `PySide6-Fluent-Widgets>=1.11.3` 을 추가한다 (검증된 설치 버전이 하한).
  배포 빌드(`PyDuplicateFinder.spec`)에도 Fluent 리소스·`QtSvg`를 포함한다.
- 새 Fluent 셸(`src/ui/shell/fluent_window.py`, `python main.py --fluent`)에서
  `MSFluentWindow` + Fluent 위젯을 사용한다. 기존 레거지 셸(`python main.py`)은
  그대로 동작하며, 두 셸은 `QMainWindow` 이중 상속 없이 core 부팅을 공유한다.
- 순수 PySide6 `design_system` 은 레거지 셸용으로 유지한다 (회귀 방지, 이중 유지보수는
  등가성 입증 후 정리).
- 상용 배포 시에는 `PySide6-Fluent-Widgets` 상용 라이선스가 별도로 필요하고,
  비상용 배포는 GPLv3 의무(소스 제공·고지)를 따른다. 최종 배포 전 재확인한다.
- `src/ui/qt_binding.py` 진단은 PySide6 전용 실행 + 충돌 패키지 진단을 계속 제공한다.

## 경로 A 재진입 조건 (후속 별도 검토)

1. 저장소 루트 `LICENSE` 확정 (MIT 전문 포함) 및 배포 형태·상업 사용 계획 정리
2. `PySide6-Fluent-Widgets` 상용 라이선스 확보 또는 GPLv3 배포 의무 수용의 명시적 결정
3. 위 1·2가 문서로 확정된 뒤에 한해 `requirements` + `.spec` + 번들 스모크를 경로 A로 전환

위 조건이 충족되기 전에는 경로 A 릴리스 PR을 완료 처리하지 않는다.
