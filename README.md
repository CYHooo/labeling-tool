# Labeling Tool (로컬 균열 라벨링 도구)

AI 서버가 만든 스티칭 이미지/마스크를 **로컬 PC**에서 사람이 직접 보정하는 도구입니다.
균열 마스크 편집, 보수 구역(OBB) 생성, px/cm 스케일 측정을 한 뒤, Viewer API 로
EC2에 다시 업로드합니다.

전체 흐름: **로그인 → 데이터 가져오기(다운로드) → 라벨링 → EC2 업로드**

---

## 요구 사항

- **Python 3.10 이상** (타입 표기 `X | None` 사용)
- OS: Windows / macOS / Linux (PyQt5 GUI)
- 패키지: `PyQt5`, `opencv-python`, `numpy`, `scikit-image`, `requests`, `onnxruntime`
  (SAM 추론은 `onnxruntime`(CPU)로 동작하며 **torch 는 필요 없습니다**. ONNX 모델은
  저장소에 포함되어 clone 시 바로 사용 가능 — 모델 생성은 `requirements-export.txt` 참고)

---

## 설치

```bash
# 저장소를 클론한 폴더(이 README가 있는 위치)에서:
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 실행

**반드시 이 README가 있는 폴더(= `labeling_tool/` 의 상위)에서** 실행하세요.

```bash
python -m labeling_tool.app
```

---

## 사용 방법

### 1) 로그인 / 데이터 가져오기 (시작 시 팝업)

시작하면 **로그인 화면**과 **데이터 가져오기 화면**이 차례로 뜹니다.

**로그인 화면**
- `BASE URL`, `X-Viewer-Api-Key` 를 입력하고 **「다음」** 을 누릅니다.
  (값은 `labeling_tool/config.json` 에 저장되어 다음부터 자동 입력됩니다. 네트워크 검증은 하지 않습니다.)
- 이미 받은 세션은 하단 **「이미 받은 세션 열기」** 드롭다운에서 골라 오프라인으로 바로 열 수 있습니다 (로그인 불필요).

**데이터 가져오기 화면**
- `sessionId` 는 서버에서 받아온 **드롭다운**으로 고릅니다 (세션 이름 · 사진 수 표시).
  목록 조회에 실패하면 직접 입력으로 전환됩니다.
- `fromNum`/`toNum` 으로 받을 **범위**를 지정합니다 (`reportPhotoNum` 기준). **0 = 열림**:
  `fromNum=0` 이면 처음부터, `toNum=0` 이면 끝까지. 예) `toNum=15` → 앞 15장,
  `fromNum=5 toNum=15` → 5~15번, 둘 다 0 → 전체. 한 칸만 채워도 동작합니다
  (여러 명이 나눠 작업할 때 자기 구역만 받기).
- **「가져오기」** → 사진 목록 조회 → 선택 범위의 스티칭/마스크만
  `labeling_tool/data/session_{id}/` 로 다운로드 후 라벨링 화면 진입.
- **「← 로그인」** 으로 로그인 화면으로 돌아갈 수 있습니다.

### 2) 라벨링

- **브러시(균열)**: 굵게 대충 그려도 마우스를 떼는 순간 **1px 중심선으로 자동 세선화**됩니다.
  → 정확한 폭이 아니라 **위치/형태만** 거칠게 표시하면 됩니다 (이때 폭 계측값 ≈ 1px).
  - **「정밀 주석 (굵기 유지)」 체크박스**: 켜면 세선화를 건너뛰어 **그린 굵기가 그대로 유지**됩니다.
    실제 균열 폭을 반영해야 할 때 사용하세요 (폭 계측값 = 그린 폭). 기본값은 꺼짐(1px).
- **스케일(px/cm)**: 이미지의 ArUco 마커(한 변 **7cm**)를 자동 검출합니다.
  검출이 안 되면 **「수동 측정」** → 기준선 양 끝 2점 클릭 → 실제 길이(기본 7cm) 입력으로 대체합니다.
- **보수 구역(BBox)**: 회전 가능한 OBB 로 보수 영역을 표시합니다. 여러 OBB 가 겹쳐도 면적은
  **합집합(겹친 부분 1회만)** 으로 계산됩니다.
- **하이라이트 / 15cm 경계 표시**: 두 토글로 캔버스 오버레이를 켜고 끕니다 — 균열 둘레의
  **노란 광륜**, 보수 구역 둘레의 **청록 15cm 경계선** (웹 뷰어용 보조 마스크 미리보기).
- **SAM 분할 (박리)**: 「SAM 분할」 토글을 켜고 박리 영역을 **좌클릭(포함)·우클릭(제외)** 하면
  MobileSAM 이 영역 마스크를 즉시 예측해 **초록 미리보기**로 보여줍니다. **「확정」** 시 박리
  레이어에 기록, **「취소」** 시 버립니다 (브러시와 보완 — SAM 으로 대략 잡고 브러시로 다듬기).
  점 하나로 전체가 잡히면 **Esc(또는 「되돌리기」)** 로 마지막 점을 취소하거나 우클릭으로 영역을 좁히세요.
  로컬 `onnxruntime` 추론(첫 클릭 시 이미지 인코딩 ~0.5–1.5s, 이후 즉시). 브러시/BBox/측정과
  상호 배타적이며, `models/sam/*.onnx` 또는 onnxruntime 이 없으면 토글이 자동 비활성화됩니다.
- 저장은 자동(이미지 전환 시) 또는 **저장 [S]** 버튼. 마스크는 `Labeling/`, 파생 마스크
  (하이라이트·15cm 경계)는 `HighLight/`·`Repair15/` 에 저장됩니다. 파생 마스크 생성은
  **백그라운드 스레드**에서 처리되어 저장·이미지 전환 시 화면이 멈추지 않습니다.

### 3) EC2 업로드

- 사이드 패널의 **「EC2에 업로드」** 버튼 → 편집·저장한 사진만, **마스크 + 균열 하이라이트 +
  15cm 경계** 3종을 함께 일괄 업로드합니다 (Viewer API v1.0.8).
- 버튼 아래 **진행률 막대**(준비 → 업로드)와 상태바에 진행 상황이 표시됩니다.
- 편집하지 않은 사진은 업로드하지 않습니다(서버의 AI 결과 유지).
- 업로드는 백그라운드 스레드에서 실행되어 화면이 멈추지 않습니다. 일부 배치가 실패하면
  **실패 원인과 `vapi.log` 경로가 팝업에 표시**되며, 자세한 내용은 `vapi.log` 에서 확인할 수 있습니다.

---

## 데이터 / 로그 위치

세션별로 아래 폴더에 저장됩니다 (`labeling_tool/data/session_{id}/`):

```
session_{id}/
├── Origin/      스티칭 원본 (stitched_{ts}.jpg)
├── Detected/    AI 마스크 (stitched_{ts}_mask.png)
├── Labeling/    편집 결과 마스크 (단일 채널 정수 라벨 0/1/2) + .bbox.json
├── HighLight/   균열 하이라이트 마스크 (업로드 high_{ts}.png)
├── Repair15/    15cm 경계 검증 마스크 (업로드 15_{ts}.png)
├── manifest.json
└── vapi.log     요청 / 다운로드 / 업로드 / 실패 원인 로그
```

---

## 테스트

```bash
pip install -r requirements-dev.txt
python -m pytest labeling_tool/tests -q
```

---

## 문제 해결

- **GUI 가 안 뜨거나 Qt 플러그인 오류**: `opencv-python` 의 번들 Qt 와 충돌일 수 있습니다.
  `app.py` 가 `QT_QPA_PLATFORM_PLUGIN_PATH` 를 비우도록 처리하지만, 그래도 문제가 있으면
  `pip install opencv-python-headless` 로 바꿔 보세요.
- **업로드 시 "스케일 없음"**: 해당 사진에 ArUco 가 검출되지 않았고 수동 측정도 안 한 경우입니다.
  「수동 측정」으로 px/cm 를 먼저 설정하세요 (업로드에는 pxPerCm 가 필수).
- **`labeling_tool` 모듈을 못 찾음**: 반드시 이 README 가 있는 폴더(= `labeling_tool/` 의 상위)에서
  `python -m labeling_tool.app` 으로 실행해야 합니다.

---

## 폴더 구조

```
.
├── README.md
├── requirements.txt / requirements-dev.txt
└── labeling_tool/
    ├── app.py              진입점
    ├── core/               라벨링 코어(브러시·OBB·ArUco·파생 마스크·계측)
    ├── api/                Viewer API 클라이언트 / 다운로드 / 업로드
    ├── session/            작업 폴더 · manifest · 파일명 규칙
    ├── ui/                 로그인 · 데이터 가져오기 다이얼로그 · 메인 윈도우 · 업로드 워커
    ├── scripts/            헤드리스 업로드 CLI
    └── tests/              단위 테스트
```
