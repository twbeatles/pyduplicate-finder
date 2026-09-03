# PyDuplicate Finder Pro v1.3.0 — High-Performance Native Rust Core

PyDuplicate Finder Pro v1.3.0은 핵심 스캔, 해싱, 바이트 비교 엔진을 Native Rust(`pydup_core`)로 점진 이관하여 **스캔 속도를 2.03배 고속화(소요 시간 50.7% 단축)**한 주요 성능 릴리스입니다.

---

## 🚀 주요 변경 사항 (What's New)

### 1. Native Rust Core (`pydup_core`) 탑재
- **Rayon 병렬 BLAKE2b 해싱**: 64비트 최적화 BLAKE2b (32바이트 digest) 스트리밍 해싱을 Rust Rayon 스레드 풀에서 GIL 없이 병렬 처리합니다. 대용량 파일 해싱 중에도 UI 끊김이 없습니다.
- **1MiB 스트리밍 바이트 비교 (`files_equal`)**: 해시 충돌 위험을 배제하기 위해 두 파일을 바이트 단위로 고속 검증합니다.
- **Native Filesystem Discovery**: Rust 재귀 순회 및 컴파일된 `globset` 패턴 매칭으로 파일 및 디렉토리 인덱싱을 가속화합니다.
- **고속 스캔 취소**: `AtomicBool` 기반 `CancellationToken`으로 사용자의 스캔 중단 요청 시 즉각 응답합니다.

### 2. 압도적인 성능 벤치마크 (10,000 파일 기준)
| 측정 지표 | Python Backend (v1.2.0) | Native Rust Backend (v1.3.0) | 속도 향상 |
|---|---:|---:|---:|
| **스캔 소요 시간** | **4.411 s** | **2.176 s** | **50.7% 단축 (2.03배 고속화)** |
| **결과 트리 렌더링** | 0.960 s | 0.906 s | UI 반응성 향상 |
| **중복 그룹 검출** | 500 그룹 | 500 그룹 | 100% 동일 (0 오차) |
| **인덱싱 파일 수** | 10,000 파일 | 10,000 파일 | 100% 동일 (0 오차) |

### 3. 무손실 Python Fallback & 철저한 안전성
- **Zero-Crash Python Fallback**: Rust 모듈 부재 또는 비호환 런타임 환경 시 순수 Python 백엔드로 부드럽게 자동 전환됩니다.
- **Read-Only 코어 원칙**: Rust 확장은 오직 파일 읽기/해싱/비교만 수행하며, 파일 삭제/격리/복구/하드링크 등 파괴적 작업은 기존 Python 계층에서 엄격하게 통제됩니다.
- **Parity 검증 완료**: 25종의 Rust Parity 단위 테스트 및 기존 145개 회귀 테스트를 포함한 총 170개 pytest 전체 100% 통과.

---

## 📦 다운로드 및 실행
- **Windows 실행 파일**: 첨부된 `PyDuplicateFinderPro.exe`를 다운로드하여 별도의 Python 설치 없이 바로 실행할 수 있습니다.
