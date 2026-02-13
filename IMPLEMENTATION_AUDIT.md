# PyDuplicate Finder Pro 기능 구현 점검 리포트

작성일: 2026-02-13  
참조 문서: `claude.md`, `README.md`

## 1) 목적과 범위

목적은 문서에 명시된 핵심 기능(스캔/캐싱/세션 재개/삭제-Undo/유사이미지/제외패턴/내보내기 등)이 실제 구현에서 안전하고 일관되게 동작하는지 점검하고, 잠재 버그 및 보강 포인트를 우선순위로 정리하는 것이다.

점검 범위:
- 스캔 엔진: `src/core/scanner.py`
- 캐시/세션: `src/core/cache_manager.py`, UI 재개 로직 `src/ui/main_window.py`
- 삭제/Undo: `src/core/history.py`, `src/core/file_ops.py`, UI 연결 `src/ui/main_window.py`
- 유사 이미지: `src/core/image_hash.py`
- UI 결과/필터/내보내기: `src/ui/components/results_tree.py`, `src/ui/main_window.py`
- 배포 관점 리스크: DB 위치, 아티팩트/중복 파일

## 2) 한줄 요약(가장 먼저 고칠 것)

- [치명적] Windows 시스템 폴더 보호 경로 생성이 잘못되어 보호가 사실상 무력화될 가능성이 큼. (`src/core/scanner.py:70-73`)
- [치명적] CSV 내보내기가 결과 키 구조를 가정하여 `NAME_ONLY`(파일명만 비교) 결과에서 오동작/예외 가능. (`src/ui/main_window.py:1329`)
- [치명적] 캐시 DB(`scan_cache.db*`)가 프로젝트 루트에 생성/존재하며 배포/권한/저장 위치 관점에서 위험. (`src/core/cache_manager.py:11`)

## 3) 구현 리스크 및 보강 포인트

### A. 치명적(Critical)

1. Windows 시스템 폴더 보호 로직 경로 생성 버그 가능성
근거:
- `src/core/scanner.py:70-73`에서 `os.path.join(sys_drive, '\\Windows')` 형태를 사용.
영향:
- `protect_system` 옵션이 켜져 있어도 `C:\Windows`, `C:\Program Files` 등의 보호가 제대로 동작하지 않아 스캔 대상에 포함될 수 있음.
권장 보강:
- Windows는 환경변수 기반으로 보호 경로를 구성: `WINDIR`, `ProgramFiles`, `ProgramFiles(x86)`, `ProgramData`.
- 보호 판정은 단순 `startswith` 대신 `commonpath` 기반으로 “상위/하위 관계”를 판정하고, 경로 구분자 단위로 안전하게 처리.

2. CSV 내보내기(export)가 결과 키 튜플 구조를 과도하게 가정
근거:
- `src/ui/main_window.py:1329`에서 `size = key[1]`를 고정 가정.
영향:
- `NAME_ONLY` 그룹 키는 `("NAME_ONLY", name_key)` 형태로 size가 없고, 유사/바이트 비교 등도 키 형태가 다양해 예외 또는 잘못된 size 기록 가능.
권장 보강:
- 내보내기 시 “키에서 size를 추출”하지 말고, 각 파일별 `os.path.getsize()`를 신뢰하거나, 키 파싱을 모드별로 분기 처리.
- Group ID 외에 “그룹 라벨(해시/NAME_ONLY/Similar#id/byte_compare 등)” 컬럼을 추가해 사람이 해석 가능하게 유지.

3. 캐시 DB 파일의 위치/권한/배포 리스크
근거:
- `src/core/cache_manager.py:11` 기본값이 `scan_cache.db`(상대 경로).
- 프로젝트 루트에 `scan_cache.db`, `scan_cache.db-wal`, `scan_cache.db-shm` 존재.
영향:
- 패키징 후 실행 위치가 읽기 전용(예: Program Files)일 경우 DB 생성/갱신 실패 가능.
- 실행 디렉토리에 따라 DB가 “예상치 못한 위치”에 생성될 수 있음.
권장 보강:
- OS별 사용자 데이터 디렉토리(AppData 등)로 DB 위치를 고정.
- “캐시 경로”를 설정에서 변경 가능하게 하거나, 최소한 안정적 기본값을 사용.

### B. 높음(High)

4. 보호 경로 판정의 `startswith` 방식은 오탐/누락 여지
근거:
- `src/core/scanner.py`의 `is_protected()`는 `norm_path.startswith(p)`.
영향:
- `C:\WindowsOld` 같은 경로가 `C:\Windows`로 잘못 판정되거나, 구분자 경계가 없는 prefix 매칭이 문제를 만들 수 있음.
권장 보강:
- `commonpath([candidate, protected]) == protected` 형태로 판정하고, 예외 처리 포함.

5. 세션 재개(resume) 구성과 실제 UI 설정이 불일치할 수 있음
근거:
- `src/ui/main_window.py:1154+`에서 `config_hash`는 `use_trash` 등을 제외한 hash_config로 계산(`_get_scan_hash_config`).
- 재개 시 기존 세션의 `config_json`과 현재 UI 설정이 다를 수 있음(특히 `use_trash` 같은 비스캔 옵션).
영향:
- “세션의 메타데이터(저장된 config)”와 실제 동작이 달라 디버깅/지원이 어려워짐.
권장 보강:
- 재개 시에도 세션 row의 `config_json`을 최신 설정으로 갱신하거나, UI에 “재개 세션 설정으로 강제 적용” 정책을 명확히.

6. 파일 작업 취소(stop) API가 있으나 실제로 취소되지 않음
근거:
- `src/core/file_ops.py:16-19`에 `stop()`이 있으나 `run()` 흐름에서 `is_running` 체크가 없음.
- UI는 파일 작업 진행 다이얼로그를 “취소 불가”로 설정.
영향:
- 대량 삭제/Undo/Redo가 시작되면 사용자가 중단할 수 없고, 장시간 작업 시 UX/안전성이 떨어짐.
권장 보강:
- 안전한 취소 요구사항을 정의(중단 시 partial 성공 처리, UI 갱신 규칙 등)한 후 워커/HistoryManager 루프에 cancel 체크를 연결.

7. 대규모 세션에서 `load_scan_files`/`load_scan_hashes`의 메모리 부담
근거:
- 캐시에서 파일 목록/해시를 통째로 로드하는 방식이 사용됨.
영향:
- 수십만 파일에서 재개 시 메모리 스파이크 가능.
권장 보강:
- 후보(candidates) 기반 selective 로드, chunking, 또는 DB 쿼리로 “존재/검증”만 수행하는 방식 검토.

8. 결과 필터링 중 삭제 로직의 정책 혼선 가능
근거:
- `src/ui/main_window.py` 삭제 시 `item.isHidden()`이면 스킵(Issue #15).
영향:
- 사용자가 체크해둔 항목이 필터로 숨겨지면 삭제 대상에서 제외되어 “왜 안 지워졌지?”가 발생할 수 있음.
권장 보강:
- 삭제 정책을 명문화: “체크된 항목은 숨김 여부와 무관하게 삭제” 또는 “보이는 항목만 삭제”.
- UI에 안내 문구/토스트로 현재 정책을 명확히 표시.

### C. 중간(Medium)

9. i18n 딕셔너리에 중복 키가 다수 존재(유지보수 리스크)
근거:
- `src/utils/i18n.py` 내 동일 키가 반복 정의되어 최종 값이 덮어써짐.
영향:
- 번역 수정 시 의도와 다르게 반영되거나, 키 관리가 어려움.
권장 보강:
- 중복 키 제거, 언어 리소스를 별도 JSON/TOML로 분리, 키 검증 스크립트 추가.

10. 제외 패턴 설명과 실제 매칭의 미세한 차이
근거:
- 제외 패턴 다이얼로그는 “glob 패턴(*, ?, **) 지원”을 표기.
- 구현은 `fnmatch.fnmatchcase` 기반이며 `**`의 의미가 전통적인 glob와 동일하진 않음.
영향:
- 사용자가 기대하는 패턴 동작과 차이가 날 수 있음.
권장 보강:
- 문서에 “fnmatch 기반”임을 명시하거나, `pathlib.Path.match`/`glob` 계열로 통일.

11. 유사 이미지 그룹 key/size의 일관성 부족 가능
근거:
- 유사 이미지 결과 키는 `(f"similar_{idx}", size)` 형태이며 size는 group[0]에서 추정.
영향:
- 그룹 내 파일 크기가 다를 경우 export/표시에서 혼동.
권장 보강:
- 그룹 표시에서 “size varies” 처리 또는 대표 size 대신 범위/다양 표시.

12. 아티팩트/중복 파일로 인한 패키징/혼선 리스크
근거:
- `src/ui/main_window (1).py`, `src/utils/i18n (1).py`, `__pycache__`, `.pyc`, `backup/`, `scan_cache.db*` 등이 존재.
영향:
- 소스 탐색/패키징/테스트에서 잘못된 파일을 참조하거나 배포 크기 증가 가능.
권장 보강:
- 중복 파일 정리, 아티팩트는 ignore, `backup/`는 별도 보관 위치로 분리하거나 ignore.

13. `.gitignore` 정책과 배포 산출물 정책 불일치
근거:
- `.gitignore`에 `*.spec`가 포함되어 있으나 `PyDuplicateFinder.spec`는 핵심 산출물 설정 파일.
영향:
- 협업/배포 시 spec 파일 관리 정책이 혼동될 수 있음.
권장 보강:
- spec 파일을 관리 대상이라면 ignore 규칙에서 제외하거나, 반대로 spec을 자동생성 산출물로 취급한다면 문서화.

### D. 낮음(Low)

14. 스캔 중 오류 출력이 “DEBUG:”로 콘솔에 찍힘
근거:
- `src/core/scanner.py`의 `_scandir_recursive`에서 OSError 시 print.
영향:
- 배포 모드에서 잡음 로그 증가 가능.
권장 보강:
- 로깅 레벨/옵션화, 또는 UI에 요약만 표시.

15. Preview 지원 확장(품질 개선)
근거:
- 현재 이미지/텍스트 위주로 보이며 특정 확장자에서 “미리보기 불가” 처리.
권장 보강:
- 큰 텍스트 파일은 일부만 로드, 바이너리는 헤더만 표시, 파일 타입별 fallback 정책 정의.

## 4) 문서(README/claude) 대비 구현 확인 체크

- Resume Scan: 구현 존재(세션/파일/해시 테이블, UI 재개 프롬프트). 다만 대용량에서 메모리/정합성 보강 필요.
- 유사 이미지(pHash + BK-Tree + Union-Find): 구현 존재. 결과 키/표시/내보내기 일관성 보강 필요.
- 시스템 보호(System Protection): 옵션은 있으나 Windows 경로 구성 버그 가능성이 높아 “실제 보호”가 불안정.
- 결과 저장/로드(JSON): UI 구현 존재. 캐시 DB 저장과의 관계(세션/파일 로드 vs JSON 로드) UX 명확화 권장.
- CSV Export: 구현 존재. 결과 키 다양성 대응이 필요.

## 5) 권장 테스트/검증 시나리오

1. Windows에서 `protect_system=True`로 `C:\` 스캔 시 `C:\Windows`/`C:\Program Files`가 실제로 제외되는지 검증.
2. `NAME_ONLY` 모드 결과가 있을 때 CSV Export가 예외 없이 동작하는지 검증.
3. 스캔 도중 중지 후 앱 재실행, “이어하기” 선택 시 stage별로 정상 재개되는지 검증.
4. 대량 결과(수만 파일)에서 결과 트리 렌더링, 필터 입력, 삭제/Undo가 UI 프리징 없이 동작하는지 관찰.
5. 유사 이미지 그룹에서 크기가 다른 파일이 섞인 케이스를 만들고 표시/내보내기 정합성 확인.
6. 필터로 일부 숨긴 상태에서 삭제 동작이 정책대로 수행되는지 확인(숨김 제외 vs 포함).

## 6) 가정 및 기본값

- 본 리포트는 “현재 코드 상태를 바탕으로 한 리스크/보강 제안”이며, 실제 사용자 운영 환경(권한/설치 경로/파일 수/스토리지 종류)에 따라 우선순위는 달라질 수 있다.
- DB 저장 위치는 “사용자 데이터 디렉토리”로 옮기는 것이 배포 안정성 측면에서 기본 권장이다.

