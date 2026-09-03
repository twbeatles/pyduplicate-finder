# PyDuplicate Finder Pro — Rust Core 점진 이관 계획

> 대상 저장소: `twbeatles/pyduplicate-finder`  
> 목표: **PySide6 GUI와 기존 Python 애플리케이션 구조는 유지하면서, 성능 민감한 정확 중복 탐색 코어만 Rust로 점진 이관한다.**  
> 상태: **COMPLETED (모든 Phase 및 마일스톤 A~C, Discovery, 파이프라인 통합, 패키징 완료 - v1.3.0)**  
> 검증: pytest 170 passed (100%), Rust cargo test/clippy 100%, 10k 파일 2.03배 속도 향상 달성  
> 원칙: 기능 parity와 데이터/파일 안전성을 성능보다 우선한다. 전면 재작성은 하지 않는다.

---

## 0. 에이전트 실행 지시

이 문서를 구현 지시서로 사용한다.

구현을 시작하기 전에 반드시 다음 순서로 작업한다.

1. `README.md`, `claude.md`, `gemini.md`를 먼저 읽는다.
2. 현재 브랜치와 작업 트리 상태를 확인한다.
3. `src/core/scanner/`, `src/core/cache_manager/`, `src/core/scan_engine.py`, `src/core/result_schema.py`, `src/core/result_groups.py`, `src/core/operation_queue.py`, `src/core/preflight.py`, `src/core/quarantine_manager.py`, `tests/`를 구조적으로 확인한다.
4. 현재 테스트를 먼저 실행해 baseline을 기록한다.
5. `tests/benchmarks/bench_perf.py`로 Rust 적용 전 성능 baseline을 기록한다.
6. 이후 아래 Phase 순서대로 구현한다.
7. 각 Phase가 끝날 때마다 Python backend와 Rust backend 결과가 동일한지 검증한다.
8. parity가 깨진 상태에서 다음 Phase로 넘어가지 않는다.

### 절대 안전 규칙

이 저장소는 삭제, 격리, 하드링크 통합 기능을 포함한다. 자동 구현 및 테스트 중 다음 규칙을 반드시 지킨다.

- 실제 사용자 파일/폴더를 대상으로 삭제, 이동, 격리, 하드링크 생성 테스트를 하지 않는다.
- 테스트는 반드시 `tempfile`, pytest `tmp_path`, Rust `tempfile` crate 등 임시 디렉터리 안에서만 수행한다.
- `rm -rf`, `rmdir /s`, `Remove-Item -Recurse -Force` 등 광범위한 재귀 삭제 명령을 저장소 외부 경로에 실행하지 않는다.
- 드라이브 루트(`C:\`, `D:\`, `/`)를 테스트 입력으로 사용하지 않는다.
- 저장소 상위 디렉터리 또는 사용자 홈 전체를 스캔 대상으로 사용하지 않는다.
- destructive operation 코드는 이번 Rust 이관 범위에 포함하지 않는다.
- Rust 코드에서 파일 삭제/rename/hardlink API를 추가하지 않는다.
- Rust 코드가 쓰기 권한을 필요로 하지 않도록 설계한다. **Rust scan core는 원칙적으로 read-only**다.
- 실제 파일 조작 관련 기존 Python 코드(`operation_queue`, `quarantine`, `history`, `preflight`)는 변경 최소화 및 Python 유지가 원칙이다.

---

# 1. 현재 구조 분석

현재 정확 중복 탐색의 핵심 경로는 다음과 같다.

```text
PySide6 UI
    ↓
ScanConfig / ScanWorker(QThread)
    ↓
Python scanner
    ├─ os.scandir 재귀 탐색
    ├─ include / exclude / system protection
    ├─ stat + inode/dev 중복 제거
    ├─ 크기별 grouping
    ↓
Python hashing orchestrator
    ├─ SQLite hash cache 확인
    ├─ ThreadPoolExecutor
    ├─ BLAKE2b partial hash
    ├─ BLAKE2b full hash
    └─ optional byte-by-byte verify
    ↓
duplicate grouping
    ↓
Python 후처리
    ├─ exemptions / safelist
    ├─ collection role
    ├─ session metadata
    ├─ result schema
    └─ UI rendering
```

현재 확인된 중요한 동작은 반드시 보존한다.

## 1.1 Discovery semantics

`src/core/scanner/discovery.py`

- `os.scandir()` 기반 재귀 탐색
- `follow_symlinks` 옵션 지원
- inode/device 기반 동일 물리 파일 중복 제외
- extension filter
- include/exclude glob
- system protection
- hidden/system-name skip
- scan error 수집
- 파일 메타데이터 `(path, size, mtime)` 유지
- 크기별 `size_map` 구성
- scan session DB batch 저장
- 이미지/문서 유사도 후보 별도 수집

## 1.2 Hashing semantics

`src/core/scanner/hashing.py`

현재 정확히 다음 규칙을 사용한다.

```text
algorithm     = BLAKE2b
digest_size   = 32 bytes
buffer_size   = 1 MiB
quick threshold = 10 MiB
```

10 MiB 이상 파일의 quick hash는:

```text
first 4096 bytes
+
last 4096 bytes
```

를 BLAKE2b에 넣는다.

Quick hash가 같은 파일들만 full hash 대상으로 올라간다.

Full hash는 파일 전체를 1 MiB block 단위로 읽는다.

기존 cache key semantics:

```text
path
size
mtime
hash_partial
hash_full
```

를 그대로 보존한다.

## 1.3 Exact duplicate pipeline

현재 기본 흐름:

```text
filesystem discovery
    ↓
size grouping
    ↓
size duplicate candidate only
    ↓
quick hash
    ↓
collision group
    ↓
full hash
    ↓
optional same-name condition
    ↓
optional byte-by-byte confirmation
    ↓
final duplicate groups
```

이 순서를 Rust 이관 후에도 유지한다.

## 1.4 이번에 Rust로 옮기지 않는 영역

다음 영역은 Python에 남긴다.

- PySide6 UI 전체
- UI controller
- `ScanWorker`의 Qt Signal/QThread integration
- SQLite schema 및 migration
- scan session 관리
- quarantine
- delete / restore
- hardlink consolidation 실행
- undo / redo history
- preflight
- operation log
- scheduler
- watchdog 기반 watch mode
- JSON result schema
- selection rule UI
- image similarity (`Pillow` / `imagehash`)
- document similarity (`pypdf` / Python text normalization)
- i18n
- export
- updater / packaging orchestration

특히 **삭제·격리·하드링크는 이번 Rust 모듈에 넣지 않는다.**

---

# 2. 최종 목표 아키텍처

```text
┌──────────────────────────────────────┐
│ Python / PySide6                     │
│                                      │
│ MainWindow                           │
│ Controllers                          │
│ ScanWorker(QThread)                  │
│ CacheManager(SQLite)                 │
│ Session / Result / Safety / Ops      │
└──────────────────┬───────────────────┘
                   │ PyO3
                   ▼
┌──────────────────────────────────────┐
│ pydup_core (Rust native extension)   │
│                                      │
│ discovery                            │
│ metadata / physical file identity    │
│ candidate grouping                   │
│ BLAKE2b partial/full hashing         │
│ byte compare                         │
│ exact duplicate grouping             │
│ cancellation                         │
│ native metrics                       │
└──────────────────────────────────────┘
```

중요한 설계 원칙:

> Python은 orchestration과 안전 정책을 담당하고 Rust는 read-only scan hot path를 담당한다.

FFI를 파일 하나마다 호출하지 않는다.

잘못된 구조:

```text
Python
for file:
    rust.hash(file)
```

권장 구조:

```text
Python
    ↓ batch
Rust
    ├─ file 1
    ├─ file 2
    ├─ ...
    └─ file N
    ↓ batch result
Python
```

---

# 3. 권장 디렉터리 구조

다음 구조를 추가한다.

```text
pyduplicate-finder/
├─ rust/
│  └─ pydup_core/
│     ├─ Cargo.toml
│     ├─ pyproject.toml
│     ├─ src/
│     │  ├─ lib.rs
│     │  ├─ config.rs
│     │  ├─ models.rs
│     │  ├─ cancellation.rs
│     │  ├─ hashing.rs
│     │  ├─ discovery.rs
│     │  ├─ file_identity.rs
│     │  ├─ grouping.rs
│     │  ├─ byte_compare.rs
│     │  ├─ errors.rs
│     │  └─ metrics.rs
│     └─ tests/
│
├─ src/
│  └─ core/
│     ├─ native/
│     │  ├─ __init__.py
│     │  ├─ bridge.py
│     │  ├─ models.py
│     │  └─ parity.py
│     ├─ scanner/
│     └─ scan_engine.py
│
├─ scripts/
│  ├─ build_rust_core.ps1
│  └─ test_rust_core.ps1
│
└─ tests/
   ├─ rust_parity/
   └─ benchmarks/
```

`pydup_core`는 PyO3 extension module로 빌드한다.

개발 빌드는 `maturin`을 사용한다.

예시:

```powershell
cd rust/pydup_core
maturin develop
```

성능 측정 시 반드시 release build를 사용한다.

```powershell
maturin develop --release
```

PyO3/maturin 버전은 구현 시점 공식 stable 문서를 확인한 뒤 고정한다. 무작정 오래된 예제 버전을 복사하지 않는다.

---

# 4. Backend 선택 구조

Rust 적용과 동시에 기존 Python 구현을 삭제하지 않는다.

`ScanConfig` 또는 내부 runtime config에 다음 backend 개념을 추가한다.

```python
scan_backend: Literal["auto", "python", "rust"] = "auto"
```

개발용으로만:

```text
PYDUP_SCAN_BACKEND=python
PYDUP_SCAN_BACKEND=rust
PYDUP_SCAN_BACKEND=auto
```

를 지원해도 된다.

정책:

```text
python
→ 항상 기존 Python 구현

rust
→ Rust extension 필수
→ import 실패 시 명시적 오류

auto
→ Rust 사용 가능하면 Rust
→ 아니면 Python fallback
```

초기 릴리스에서는 기본값을 `python`으로 유지해도 된다.

Rust parity와 benchmark가 통과한 뒤 `auto`로 변경한다.

### 금지

Rust import 실패 시 앱 전체가 실행 불가능해지면 안 된다.

```python
try:
    import pydup_core
except ImportError:
    pydup_core = None
```

형태의 capability detection을 둔다.

---

# 5. Phase 0 — Baseline 및 경계 추출

Rust 코드를 작성하기 전에 먼저 현재 Python 동작을 고정한다.

## 5.1 기존 테스트

실행:

```powershell
pytest
pyright .
```

실패가 있으면 Rust 작업 전에 원인을 기록한다.

기존 실패를 Rust 변경 때문에 발생한 실패와 섞지 않는다.

## 5.2 성능 baseline

현재 존재하는:

```text
tests/benchmarks/bench_perf.py
```

를 사용한다.

최소 다음을 기록한다.

```powershell
python tests/benchmarks/bench_perf.py --files 10000 --groups 500 --output bench_python_10k.json
python tests/benchmarks/bench_perf.py --files 100000 --groups 2500 --output bench_python_100k.json
python tests/benchmarks/bench_perf.py --files 200000 --groups 5000 --output bench_python_200k.json
```

다음 값 보존:

- scan_time_sec
- render_time_sec
- filter_time_sec
- result_groups
- result_files_meta

Rust migration의 성능 비교에서는 **render_time과 filter_time은 Rust 평가 대상이 아니다.**

## 5.3 Golden parity fixture 추가

`tests/rust_parity/`에 deterministic fixture generator를 만든다.

최소 케이스:

1. 완전히 동일한 작은 파일
2. 크기만 같은 다른 파일
3. 같은 이름 + 다른 내용
4. 다른 이름 + 같은 내용
5. zero-byte 파일
6. Unicode 파일명
7. 한글 파일명
8. 긴 경로
9. nested directory
10. excluded directory
11. included extension
12. excluded extension
13. dot-hidden name
14. `Thumbs.db`
15. hardlink
16. symlink (`follow_symlinks=False`)
17. symlink (`follow_symlinks=True`)
18. 10 MiB 경계 직전
19. 10 MiB 경계 직후
20. 첫/마지막 4 KiB는 같지만 중간 내용이 다른 대형 파일
21. byte-compare mode
22. scan 중 파일 변경/삭제
23. permission/read error 가능한 플랫폼 fixture
24. duplicate folder fixture

Golden 결과를 정렬/정규화하여 Python 구현의 결과를 저장한다.

dict의 tuple key 순서에 의존하지 않도록 canonical representation을 만든다.

예:

```python
[
    {
        "key": [...],
        "paths": [...]
    }
]
```

path와 group을 정렬하고 비교한다.

---

# 6. Phase 1 — Rust hashing core

가장 먼저 hashing만 Rust로 옮긴다.

이 단계에서는 discovery, filter, cache DB, session은 Python 그대로 둔다.

## 6.1 Rust API

첫 API는 작게 시작한다.

개념 예:

```python
pydup_core.hash_files(
    items,
    mode="partial" | "full",
    max_workers=N,
    cancel_token=token,
)
```

`items`:

```python
[
    (path, size, mtime),
    ...
]
```

return:

```python
[
    {
        "path": str,
        "size": int,
        "mtime": float,
        "digest": str | None,
        "status": "ok" | "cancelled" | "error",
        "error": str | None,
    }
]
```

FFI 구조체 이름은 자유롭게 개선해도 되지만 Python에 노출되는 데이터 계약을 명확하게 유지한다.

## 6.2 Hash parity

Rust 구현은 기존 Python과 byte-for-byte 동일해야 한다.

### Full hash

```text
BLAKE2b
digest_size = 32
entire file
```

결과는 lowercase hex string.

### Partial hash

10 MiB 이상 파일에 대해서만 기존 orchestration이 partial mode를 요청한다.

내용:

```text
first 4096 bytes
last 4096 bytes (size > 8192일 때)
```

기존 Python 결과와 정확히 같은 digest를 생성해야 한다.

### Buffer

full hash read buffer 기본:

```text
1 MiB
```

필요하면 Rust 내부에서 벤치마크를 통해 변경 가능하지만, Phase 1에서는 parity를 위해 동일하게 유지한다.

## 6.3 Parallelism

Rust 내부 parallel hashing은 `rayon` 등의 검증된 thread pool 사용을 우선 검토한다.

Python `ThreadPoolExecutor`를 Rust와 이중으로 중첩하지 않는다.

Rust backend 사용 시:

```text
Python ThreadPoolExecutor
    ↓
Rust Rayon
```

구조가 되지 않게 한다.

Python orchestration이 Rust에 batch를 넘기고 Rust가 내부 parallelism을 담당하도록 한다.

## 6.4 GIL

long-running Rust-only hashing 구간은 PyO3의 현재 공식 API를 사용하여 Python interpreter에서 detach한다.

현재 PyO3 계열에서는 `Python::detach` 계열 API가 사용되므로 구현 시 stable 문서를 확인한다.

목표:

- Rust hashing 중 Python UI thread가 막히지 않음
- QThread 동작과 충돌하지 않음
- Rust worker thread가 Python object를 직접 장기간 보유하지 않음

## 6.5 Cache

**Phase 1에서는 SQLite cache를 Rust로 옮기지 않는다.**

Python이 현재처럼:

1. cache 조회
2. cache miss만 Rust batch로 전달
3. Rust 결과 회수
4. 기존 `update_cache_batch`
5. 기존 `save_scan_hashes_batch`

를 수행한다.

이렇게 하면 DB schema와 session semantics를 바꾸지 않고 hashing만 안전하게 교체할 수 있다.

## 6.6 `_calculate_hashes_parallel` 변경

기존 함수의 public/internal contract는 유지한다.

권장:

```python
def _calculate_hashes_parallel(...):
    if self._use_rust_hashing():
        return self._calculate_hashes_rust(...)
    return self._calculate_hashes_python(...)
```

기존 구현을 `_calculate_hashes_python()`으로 보존한다.

Rust path와 Python path가 같은 `hash_map` 형태를 반환하게 한다.

---

# 7. Phase 2 — Rust byte-by-byte compare

`compare_files_byte_by_byte()`를 Rust로 이관한다.

Rust API 예:

```python
pydup_core.files_equal(path_a, path_b, cancel_token)
```

또는 batch:

```python
pydup_core.partition_equal_files(paths, cancel_token)
```

가능하면 group 단위 batch API를 우선한다.

목표:

```text
FFI 횟수 최소화
```

Python의 현재 `_byte_compare_group()` 결과 grouping semantics를 변경하지 않는다.

### 주의

hash equality만으로 기존 byte compare 옵션을 생략하지 않는다.

사용자가 `byte_compare=True`를 선택하면 기존처럼 실제 byte compare를 수행한다.

---

# 8. Phase 3 — Rust filesystem discovery

Hash parity가 완전히 확보된 뒤 discovery를 Rust로 옮긴다.

## 8.1 Rust discovery input

Python이 Rust에 다음 설정을 전달한다.

```text
folders
extensions
min_size
protect_system
protected_paths
include_patterns
exclude_patterns
skip_hidden
follow_symlinks
ignore path rules
```

system protected root 계산 자체는 Python에 남겨도 된다.

Rust는 Python이 넘긴 protected path list를 사용한다.

## 8.2 Hidden semantics 변경 금지

현재 `skip_hidden`은 완전한 OS hidden attribute 탐지가 아니다.

현재 의미:

- 이름이 `.`으로 시작
- `thumbs.db`
- `desktop.ini`
- `.ds_store`

따라서 Rust에서 Windows FILE_ATTRIBUTE_HIDDEN까지 자동 적용하여 동작을 확장하지 않는다.

동작 개선은 별도 PR에서 한다.

Rust migration PR은 parity만 수행한다.

## 8.3 Physical file identity

현재 Python은 `(st_dev, st_ino)`를 사용한다.

Rust에서도 플랫폼별 동일한 목적의 physical identity를 만든다.

Unix:

```text
device id + inode
```

Windows:

- stable Rust API만으로 parity가 부족하면 Windows file identity API 또는 검증된 crate를 사용한다.
- path string만으로 hardlink identity를 판단하지 않는다.
- junction/reparse point/symlink behavior를 명시적으로 테스트한다.

`unsafe` Windows API가 필요하면 작은 모듈 하나로 격리하고 안전 wrapper를 만든다.

가능하면 검증된 crate를 우선 사용한다.

## 8.4 Discovery result

Rust 결과에는 최소:

```text
path
size
mtime
physical identity(optional/debug)
```

가 있어야 한다.

Python에서는 이후 기존 로직을 유지한다.

```text
_file_meta
_image_files
_document_files
_path_collection_roles
_path_exemption_status
scan session DB batch
```

즉 **Rust는 파일을 발견하고 metadata를 읽지만 업무 정책/DB 상태는 Python이 소유**한다.

## 8.5 mtime parity

중요:

현재 cache가 floating-point `st_mtime` 비교를 사용한다.

Rust `SystemTime` → Python float 변환이 기존 `os.stat().st_mtime`과 동일한지 Windows/Linux에서 반드시 parity test한다.

조금이라도 차이가 있어 cache miss가 대량 발생하면 Rust discovery를 기본값으로 전환하지 않는다.

이 문제를 해결하기 위해 cache schema를 바로 `mtime_ns`로 바꾸지 않는다.

schema 변경은 별도 migration으로 분리한다.

---

# 9. Phase 4 — Rust size grouping + exact duplicate pipeline

Discovery와 hashing이 각각 안정화되면 exact duplicate hot path를 하나의 Rust engine으로 묶는 것을 검토한다.

목표:

```text
Rust discovery
→ size group
→ partial hash
→ full hash
→ exact group
```

Python은 최종 result를 받아 기존 후처리를 수행한다.

Rust result 모델 예:

```text
ExactDuplicateGroup
- digest
- size
- paths
```

Python adapter가 기존 dict key 형태를 재구성한다.

예:

```python
final_duplicates[(digest, size)] = paths
```

### same-name 옵션

기존 `check_name=True` semantics를 정확히 유지한다.

### name-only mode

기존 name-only scan은 정확 duplicate hash scan과 별개의 의미를 가진다.

Phase 4에서 동시에 바꾸지 않아도 된다.

처음에는 Python 유지 가능하다.

### post filter

다음은 계속 Python:

- exemption matching
- safelist
- collection role
- compare collections
- selection reason
- review state

---

# 10. Phase 5 — Duplicate folder signature (선택)

`src/core/scanner/folder_duplicates.py`는 다음을 수행한다.

1. directory membership 구성
2. relative path + size quick signature
3. candidate directory 안 파일 full hash 확보
4. relative path + full hash final signature
5. duplicate folder grouping

이 부분도 Rust 적합도가 높지만 Phase 1~4보다 우선순위가 낮다.

정확 duplicate core가 안정화된 이후 별도 작업으로 이관한다.

### 금지

Phase 1 PR에서 duplicate folder까지 한 번에 바꾸지 않는다.

---

# 11. Incremental scan 전략

`src/core/scanner/incremental.py`는 cache/session과 강하게 결합되어 있다.

따라서 초기 Rust migration에서는 Python 유지한다.

현재 로직:

```text
base session file list
→ stat 재검증
→ revalidated / changed / missing
→ filesystem에서 new path 발견
→ session 저장
```

Phase 3 discovery가 안정화된 후 다음 정도만 Rust helper로 사용할 수 있다.

```text
bulk stat/revalidate
new file discovery
```

하지만:

- delta map
- session id
- DB write
- baseline metadata
- UI/session progress

는 Python에 유지한다.

---

# 12. Cancellation 설계

현재 Python은 `threading.Event`를 사용한다.

Rust에는 별도 cancellation token을 만든다.

개념:

```rust
AtomicBool
```

Python wrapper:

```python
token.cancel()
```

`ScanWorker.stop()`에서는:

```python
self._stop_event.set()
if self._rust_cancel_token:
    self._rust_cancel_token.cancel()
```

Rust는 다음 위치에서 cancellation을 확인한다.

- directory iteration
- candidate iteration
- file read loop
- hash batch
- byte compare loop

cancel latency 목표:

```text
일반적인 로컬 SSD workload에서 250 ms 이내
```

대형 단일 파일 hashing에서도 매 read block마다 확인한다.

---

# 13. Progress 설계

Rust가 Qt Signal을 직접 알 필요는 없다.

Qt 의존성을 Rust core에 넣지 않는다.

선택지:

### 권장 1차

Rust batch가 끝날 때 Python이 progress를 갱신한다.

### 이후 필요 시

Rust progress callback을 추가한다.

단 callback 호출은 throttling한다.

```text
최대 약 10회/초
```

Python callback에서 Qt Signal을 emit한다.

파일 하나마다 Python callback을 호출하지 않는다.

---

# 14. Error model

Rust 오류로 앱 전체 scan을 즉시 panic시키지 않는다.

Rust 내부 `panic`이 Python boundary를 넘지 않도록 한다.

파일 단위 오류:

```text
permission denied
file disappeared
read error
metadata error
symlink error
```

는 structured error로 반환한다.

예:

```text
ScanError
- path
- stage
- operation
- kind
- message
```

Python adapter가 기존 `_record_scan_error()` semantics로 변환한다.

Rust library 내부에서 `unwrap()` / `expect()` 사용은 테스트 코드 외 최소화한다.

---

# 15. Rust dependency 원칙

가능하면 dependency를 작게 유지한다.

검토 후보:

```text
pyo3
rayon
blake2
thiserror
globset
```

필요한 경우에만:

```text
walkdir
same-file
windows
serde
```

를 추가한다.

### 선택 기준

- filesystem traversal semantics가 현재 Python과 달라지면 `walkdir`을 억지로 사용하지 않는다.
- `std::fs::read_dir` 재귀가 parity에 더 적합하면 직접 구현한다.
- Windows file identity 때문에 `windows` crate가 필요하면 해당 모듈에만 한정한다.
- Rust SQLite(`rusqlite`)는 초기 Phase에서 추가하지 않는다.

---

# 16. Python/Rust data contract

FFI 경계에서 거대한 Python object graph를 만들지 않는다.

초기 구현은 명확성을 우선하되 benchmark한다.

권장 모델:

```text
FileRecord
- path: String
- size: u64
- mtime: f64

HashRecord
- path: String
- size: u64
- mtime: f64
- digest: Option<String>
- status
```

가능하면 batch 단위 반환.

200k 파일 기준 Python object allocation이 병목이 되면 그때 compact representation을 검토한다.

Phase 1부터 custom binary protocol 등을 도입하지 않는다.

---

# 17. Python adapter

`src/core/native/bridge.py`에서만 PyO3 module을 직접 import하게 한다.

예:

```python
class RustCoreUnavailable(RuntimeError):
    pass


def is_available() -> bool:
    ...


def hash_files(...):
    ...


def discover_files(...):
    ...
```

scanner 본체 곳곳에서 직접:

```python
import pydup_core
```

하지 않는다.

FFI 변경을 한 파일에서 흡수하도록 한다.

---

# 18. Compatibility 보존 항목

Rust migration 중 다음 public behavior는 바꾸지 않는다.

- 기존 설정 파일
- 기존 SQLite DB
- 기존 scan session
- 기존 result JSON v3
- 기존 operation plan
- 기존 quarantine
- 기존 undo
- 기존 shortcuts
- 기존 CLI 옵션
- existing translations
- watch mode
- scheduled jobs
- hardlink eligibility
- collection role
- safelist / ignore
- review state
- incremental comparison
- Python fallback

Rust 적용 전 저장한 cache와 session을 Rust backend에서도 사용할 수 있어야 한다.

---

# 19. Test 전략

## 19.1 Rust unit test

최소:

```text
hash_small_file
hash_large_file
partial_hash_matches_python_vector
full_hash_matches_python_vector
partial_collision_full_mismatch
byte_compare_equal
byte_compare_not_equal
cancel_hash
unicode_path
zero_byte
```

## 19.2 Python integration test

같은 fixture를:

```text
backend=python
backend=rust
```

두 번 실행한다.

canonical result가 완전히 동일해야 한다.

## 19.3 Golden hash vectors

Python 구현으로 deterministic fixture의 hash를 생성하여 test vector로 고정한다.

Rust 테스트가 동일 digest를 요구하도록 한다.

## 19.4 Cache parity

1. Python backend scan
2. cache 생성
3. Rust backend scan
4. cache hit 여부 확인

반대 방향도 수행한다.

1. Rust backend scan
2. Python backend scan
3. 기존 cache가 정상 재사용되는지 확인

## 19.5 Cancellation

Rust scan 중 cancel:

- 앱 crash 없음
- Python QThread 종료 가능
- session status 일관
- partial result가 기존 정책과 동일
- DB corruption 없음

---

# 20. Benchmark 전략

기존 `bench_perf.py`를 유지하고 backend 옵션을 추가한다.

예:

```powershell
python tests/benchmarks/bench_perf.py --backend python --files 200000 ...
python tests/benchmarks/bench_perf.py --backend rust --files 200000 ...
```

동일 dataset을 사용해야 한다.

최소 5회 수행 후 median 비교.

측정 대상:

```text
discovery time
hashing time
total scan time
peak RSS
CPU utilization
result parity
cache hit scan
cache miss scan
```

가능하면 stage timing을 추가한다.

예:

```json
{
  "backend": "rust",
  "discovery_sec": 1.2,
  "partial_hash_sec": 0.8,
  "full_hash_sec": 2.3,
  "total_scan_sec": 4.7
}
```

### Rust default 전환 gate

다음 조건을 모두 만족하기 전에는 Rust를 강제 기본값으로 하지 않는다.

1. parity test 100% 통과
2. 전체 pytest 통과
3. Rust `cargo test` 통과
4. `cargo clippy` 주요 경고 없음
5. PyInstaller 배포본 실행 성공
6. cancellation 정상
7. 기존 cache/session 호환
8. 대표 benchmark에서 유의미한 회귀 없음

성능 목표는 I/O 환경마다 달라지므로 “무조건 N배”를 요구하지 않는다.

권장 판단 기준:

```text
median total scan time이 Python보다 최소 10% 이상 개선
또는
CPU/메모리/응답성이 명백하게 개선
```

그렇지 않으면 Python backend를 기본으로 유지한다.

---

# 21. Packaging

개발:

```powershell
maturin develop
```

성능/릴리스 확인:

```powershell
maturin develop --release
```

wheel:

```powershell
maturin build --release
```

PyInstaller가 `.pyd` native extension을 포함하는지 실제 빌드 결과로 검증한다.

필요하면 `PyDuplicateFinder.spec`에:

- native extension hidden import
- binary collection

을 명시한다.

단 추측으로 spec을 수정하지 말고 먼저 PyInstaller analysis 결과를 확인한다.

### Windows 우선

현재 실제 주요 사용 환경을 고려해:

```text
Windows x86_64
```

를 우선 완성한다.

기존 Linux 지원을 깨지 않도록 platform guard를 둔다.

Windows 전용 구현이 있으면:

```rust
#[cfg(windows)]
```

로 격리한다.

Unix:

```rust
#[cfg(unix)]
```

로 분리한다.

---

# 22. CI 권장

Rust CI 단계:

```text
cargo fmt --check
cargo test
cargo clippy --all-targets --all-features
```

Python:

```text
pytest
pyright .
```

통합:

```text
maturin build
install wheel
pytest tests/rust_parity
```

가능하면 Windows runner를 필수로 둔다.

---

# 23. PR 분할

한 PR에서 전체 코어를 변경하지 않는다.

권장 PR:

### PR 1 — architecture / baseline

- backend abstraction
- parity fixture
- benchmark backend option
- Python behavior 변경 없음

### PR 2 — Rust crate skeleton

- PyO3
- maturin
- hello/capability
- packaging test
- no production path activation

### PR 3 — Rust BLAKE2b hashing

- partial/full hashing
- Python fallback
- hash parity tests

### PR 4 — Rust byte compare

- exact byte verification
- cancellation

### PR 5 — Rust discovery

- traversal
- stat
- physical identity
- filters
- parity

### PR 6 — exact pipeline integration

- size grouping
- quick/full orchestration
- final exact groups
- benchmark

### PR 7 — optional duplicate folder engine

별도 판단 후 진행.

---

# 24. 구현 중 금지사항

다음은 하지 않는다.

- PySide6 → Rust GUI 재작성
- Tauri 도입
- SQLite 전체 Rust 재작성
- result schema 변경
- 기존 cache schema 변경
- 삭제 기능 Rust 이관
- quarantine Rust 이관
- hardlink operation Rust 이관
- image pHash Rust 재작성
- PDF/document similarity Rust 재작성
- updater 변경
- UI redesign
- unrelated refactor
- 기존 Python scanner 즉시 삭제
- 성능 근거 없이 Rust backend 강제
- 테스트 없이 hash algorithm 변경
- BLAKE3로 임의 변경
- partial hash algorithm 변경

특히 BLAKE3가 더 빠르다는 이유로 BLAKE2b를 바꾸지 않는다.

기존 cache와 결과 compatibility가 깨진다.

---

# 25. 완료 정의

이번 migration은 다음 상태를 목표로 한다.

```text
PyDuplicate Finder Pro
├─ Python / PySide6
│  ├─ UI
│  ├─ workflow
│  ├─ cache/session
│  ├─ safety
│  ├─ quarantine
│  ├─ operations
│  ├─ image/document similarity
│  └─ result handling
│
└─ Rust pydup_core
   ├─ filesystem discovery
   ├─ metadata
   ├─ physical identity
   ├─ exact candidate grouping
   ├─ BLAKE2b partial hashing
   ├─ BLAKE2b full hashing
   ├─ byte comparison
   └─ cancellation
```

사용자 관점에서는:

```text
UI 변화 없음
설정 변화 없음
결과 변화 없음
cache/session 호환
안전 정책 변화 없음
```

이어야 한다.

내부적으로만 exact duplicate hot path가 Rust로 교체된다.

---

# 26. 첫 구현에서 실제로 해야 할 일

에이전트는 우선 아래까지만 구현한다.

## Milestone A

- [ ] README/CLAUDE/GEMINI 검토
- [ ] baseline pytest/pyright
- [ ] benchmark baseline 저장
- [ ] backend abstraction 추가
- [ ] Rust subcrate 생성
- [ ] maturin/PyO3 import 성공
- [ ] Python fallback 유지
- [ ] hash golden fixture 추가

## Milestone B

- [ ] full BLAKE2b Rust 구현
- [ ] partial BLAKE2b Rust 구현
- [ ] Python/Rust digest 완전 일치
- [ ] Rust batch hashing
- [ ] Python cache 연계
- [ ] cancellation
- [ ] progress 정상
- [ ] 전체 pytest 통과

## Milestone C

- [ ] Rust byte compare
- [ ] parity test
- [ ] benchmark

여기까지 완료한 뒤 결과와 benchmark를 검토한다.

**Discovery Rust 이관은 Milestone A~C가 안정적으로 완료된 이후에 진행한다.**

---

# 27. 에이전트 최종 보고 형식

각 Milestone 종료 시 다음 형식으로 보고한다.

```markdown
## 구현 결과

### 변경 파일
- ...

### 구현 내용
- ...

### 기존 동작과의 호환성
- ...

### 테스트
- pytest:
- pyright:
- cargo test:
- cargo clippy:
- parity:

### Benchmark
| 항목 | Python | Rust | 차이 |
|---|---:|---:|---:|
| ... | ... | ... | ... |

### 안전성 확인
- 실제 사용자 파일 삭제 없음
- destructive operation 변경 없음
- temp fixture만 사용

### 남은 문제
- ...

### 다음 단계
- ...
```

성능이 예상보다 낮으면 숨기지 말고 원인을 분석한다.

예:

```text
disk I/O bound
Python hashlib가 이미 native C
FFI object conversion overhead
SQLite cache overhead
filesystem metadata bottleneck
```

를 구분해서 보고한다.

---

# 28. 핵심 판단 기준

이 작업의 성공 기준은 “Rust 코드 비율”이 아니다.

성공 기준은:

1. 기존 기능을 깨지 않는다.
2. 안전 관련 Python 코드를 건드리지 않는다.
3. exact duplicate hot path를 명확한 native module로 분리한다.
4. Python↔Rust interface가 작고 안정적이다.
5. Python fallback이 존재한다.
6. benchmark로 이득을 증명한다.
7. Rust가 이득 없는 영역까지 무리하게 확장되지 않는다.

최종적으로 이 프로젝트는 포트폴리오에서 다음 구조를 보여주는 것이 목적이다.

> **Python/PySide6 데스크톱 제품에 PyO3 기반 Rust native core를 도입하고, 파일시스템 탐색·병렬 해싱·중복 판별 hot path만 최적화한 하이브리드 아키텍처. 기존 SQLite/session/UI/safety layer와의 하위 호환성을 유지하고 Python/Rust dual backend benchmark로 효과를 검증한다.**
