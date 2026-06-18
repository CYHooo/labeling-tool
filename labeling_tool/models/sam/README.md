# MobileSAM ONNX 모델

이 폴더에는 SAM(박리) 분할용 ONNX 모델 2개가 들어갑니다 (git 으로 함께 배포):

- `mobile_sam_encoder.onnx`  (이미지 인코더, ~30–40MB)
- `mobile_sam_decoder.onnx`  (포인트 디코더, ~16MB)

## 생성 방법 (torch 가 있는 머신에서 1회)

```bash
pip install -r requirements-export.txt
python scripts/export_mobilesam_onnx.py        # 두 .onnx 를 이 폴더에 생성
git add labeling_tool/models/sam/*.onnx
git commit -m "chore: add MobileSAM ONNX models"
```

생성 후에는 torch 없이 onnxruntime 만으로 동작합니다.
