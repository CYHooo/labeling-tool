# 문서 안내 / 文档索引

`docs/superpowers/specs/` 는 설계(design), `docs/superpowers/plans/` 는 구현 계획입니다.
각 문서는 **작성 시점의 기록**이며, 아래 표는 그 기능이 지금도 유효한지 보여 줍니다.

| 문서 (specs/plans 공통 이름) | 기능 | 현재 상태 |
|---|---|---|
| 2026-06-12-local-labeling-tool-vapi | 로그인 → 가져오기 → 라벨링 → 업로드 (Viewer API) | 유효 |
| 2026-06-16-data-loading-rationalization | 세션 폴더 구조 / 데이터 적재 | 유효 |
| 2026-06-17-derived-mask-perf-color | 파생 마스크 성능·색상 | 유효 |
| 2026-06-17-highlight-repair15-upload | HighLight / Repair15 생성 및 업로드 | 유효 |
| 2026-06-17-integer-label-mask-format | 단일 채널 정수 라벨 마스크 | 유효 |
| 2026-06-17-login-fetch-split | 로그인 / 가져오기 화면 분리 | 유효 (로그인 화면은 이후 탭 구조로 확장) |
| 2026-06-17-remove-rebuild | rebuild 기능 제거 | 완료된 일회성 마이그레이션 |
| 2026-06-18-mobilesam-spalling / -phase1 / -phase2 | MobileSAM ONNX 추론 | 유효 |
| 2026-06-29-auto-bbox-from-15cm | 15cm 기준 자동 bbox | 유효 |
| 2026-07-01-sam-crop-around-click | 대형 이미지 SAM 크롭 | 유효 |
| 2026-09-21-windows-exe-packaging | Windows exe (lite / full) 패키징 | 유효 (§0 개정: exe 는 SAM2.1 전용) |
| 2026-09-23-installer-and-auto-update | Windows 설치 프로그램 + 인앱 자동 업데이트 | 유효 |

## archive/

더 이상 코드에 존재하지 않는 기능의 문서입니다 (기록 보존용).

- `2026-07-01-standalone-folder-labeler*` — 이미지/마스크 폴더를 직접 고르던 오프라인 라벨러.
  로그인 화면의 **「로컬 작업」 탭**(이미 받은 작업 목록)으로 대체되었습니다.
