# VisionGuard AI

AI 코드는 실행 주기에 따라 학습 영역과 예측 서버 영역으로 분리합니다.

```text
AI/
├── configs/                 # 데이터셋 및 학습 설정 예시
├── data/                    # 로컬 원본/가공 데이터 (Git 제외)
│   ├── raw/                 # MP4 등 원본 데이터
│   ├── images/{train,val,test}/
│   └── labels/{train,val,test}/
├── inference/               # 서비스 운영 중 상시 실행
│   ├── detector.py
│   ├── collision_detector.py
│   ├── predictor.py
│   ├── schemas.py            # AI 내부 및 API 응답 데이터 형식
│   └── app.py
├── models/                  # 가중치 및 모델 산출물 (Git 제외)
│   ├── base/                # YOLO 기본 모델
│   ├── checkpoints/         # 학습 중간 결과와 best.pt
│   ├── production/          # 현재 운영 모델
│   └── archive/             # 이전 모델
├── references/              # 실험/참고 코드와 샘플
├── reports/                 # 평가 지표 및 그래프
└── training/                # 필요할 때 실행하는 오프라인 작업
    ├── dataset.py
    ├── preprocess.py
    ├── train.py
    ├── evaluate.py
    └── model_manager.py
```

`data/`, `models/`, `reports/`의 실행 산출물은 저장소에 커밋하지 않습니다.
각 디렉터리의 `.gitkeep`만 구조 유지를 위해 추적합니다.

## 실행 위치

모듈 간 import가 안정적으로 동작하도록 프로젝트 루트에서 모듈 방식으로 실행합니다.

```bash
python -m AI.training.preprocess
python -m AI.training.train
python -m AI.training.evaluate
uvicorn AI.inference.app:app --host 0.0.0.0 --port 8000
```
