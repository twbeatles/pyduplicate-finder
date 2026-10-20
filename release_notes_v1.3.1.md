# PyDuplicate Finder Pro v1.3.1 — Rust 2024 Backend Upgrade

PyDuplicate Finder Pro v1.3.1은 Native Rust 백엔드(`pydup_core`)를 **Rust Edition 2024**로 마이그레이션하고 의존성을 전면 업그레이드한 백엔드 유지보수 릴리스입니다. 사용자 기능 변경은 없으며, 스캔 hot-path의 read-only 원칙과 Python fallback 계약은 그대로 유지됩니다.

---

## 🔧 주요 변경 사항 (What's Changed)

### 1. Rust Edition 2024 마이그레이션
- `edition 2021` → `2024`, `rust-version = "1.88"` 명시, `license` 추가.
- `rust/pydup_core/rust-toolchain.toml` 신설 (stable + rustfmt/clippy 고정).
- Edition 2024 대응: 중첩 `if let` 10곳 → let-chain 변환, `CancellationToken`에 `Debug` derive.
- `[lints]` (`unsafe_op_in_unsafe_fn` warn, clippy `correctness` deny) + release `strip = true` 추가.

### 2. 의존성 전면 업그레이드
| 크레이트 | 이전 | 이후 |
|---|---:|---:|
| pyo3 | 0.29.3 | **0.30.1** |
| globset | 0.4.19 | **0.4.20** |
| ctutils | 0.4.2 | **0.4.3** |
| rayon | 1.10 | **1.12** |
| tempfile | 3.10 | **3.12** (lock 3.27) |

### 3. 스캔 취소 토큰 재사용 버그 수정
- 취소된 네이티브 토큰이 같은 워커의 재스캔에 재사용되면 결과가 비어 fail-closed되던 문제 수정.
- discovery/hashing/byte-compare 페이즈 진입 3곳에서 정지 상태가 아니면 토큰 `reset()`.
- 기존 `test_dup06_cancel_then_clean_rescan_matches`가 Rust 백엔드에서도 통과.

---

## ✅ 검증
- `cargo test` 4 passed, `clippy --all-targets --all-features -- -D warnings` 0건, `fmt --check` clean.
- `cargo audit` 취약점 0건, `cargo machete` 미사용 의존성 0건.
- `tests/rust_parity/` 25 passed, `pytest` 255 passed + 2 skipped.
- `tests/test_gui_fluent_shell.py` 6건 실패는 변경 전 베이스에서도 동일한 Qt 환경 기존 문제로 이번 릴리스 범위에서 제외.

---

## 📦 다운로드 및 실행
- **Rust 네이티브 휠**: 첨부된 `pydup_core-*-abi3-win_amd64.whl`을 `pip install`로 설치하면 Rust 고속 백엔드가 활성화됩니다. 미설치 시 기존 Python 백엔드로 자동 fallback됩니다.
