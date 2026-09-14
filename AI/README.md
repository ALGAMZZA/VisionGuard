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

## 환경 설정

현재 프로젝트는 WSL/Ubuntu의 Python 가상환경 사용을 기준으로 합니다. Ubuntu에
`pip`와 `venv`가 없다면 최초 한 번 설치합니다.

```bash
sudo apt update
sudo apt install -y python3-pip python3-venv

cd /home/sanghyun/VisionGuard
python3 -m venv AI/.venv
source AI/.venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r AI/requirements-dev.txt
```

영상 저장과 `--display` 실행을 함께 지원하기 위해 OpenCV 기본 패키지를 사용합니다.

기본 운영 모델 경로는 `AI/models/production/best.pt`입니다. 학습 전 구조 확인용으로
`AI/references/yolov8n.pt`를 지정할 수 있지만, COCO 기본 모델에는 `forklift` 클래스가
없으므로 사람-지게차 충돌 판정에는 학습된 VisionGuard 모델이 필요합니다.

## 영상 추론

모듈화된 YOLO + DeepSORT + 충돌 판정 파이프라인은 다음처럼 실행합니다.

```bash
python -m AI.inference.predictor \
  --source AI/references/data/collision2.mp4 \
  --model AI/models/production/best.pt \
  --save AI/reports/collision2-result.mp4
```

기본 탐지 신뢰도는 `0.35`이며 DeepSORT는 두 프레임에서 확인된 객체만 트랙으로
확정합니다. 현재 프레임에서 YOLO가 관측하지 않은 예측 트랙은 충돌 판정과 결과
영상에서 제외합니다. 필요하면 `--conf`로 영상 환경에 맞게 조정합니다.

화면에도 표시하려면 `--display`를 추가합니다.

## 예측 API

환경 변수 예시는 `AI/configs/inference.env.example`에 있습니다. API는 모델을 첫
요청 때 지연 로딩하므로 가중치가 없어도 `/health` 확인은 가능합니다.

```bash
uvicorn AI.inference.app:app --host 0.0.0.0 --port 8000

curl -X POST "http://localhost:8000/predict?frame_id=1&fps=30" \
  -F "file=@frame.jpg"

curl -X POST http://localhost:8000/reset
```

`/predict`는 한 영상 스트림의 프레임이 순서대로 들어온다고 가정합니다. 새로운 영상
또는 카메라로 전환할 때 `/reset`을 호출해 DeepSORT와 이동 이력을 초기화합니다.

## 테스트

실제 모델 없이 가짜 YOLO/DeepSORT 결과를 사용해 모듈 경계를 테스트할 수 있습니다.

```bash
pytest AI/tests
ruff check AI/inference AI/tests --ignore N999
```

## NVIDIA artifacts를 YOLO 데이터셋으로 변환

`nearmiss-artifacts-*.tar`에는 RGB 영상과 프레임별 2D 바운딩박스가 함께
들어 있습니다. 전체 TAR를 풀지 않고 학습에 필요한 RGB, 객체 탐지 JSONL,
시나리오 메타데이터만 선별 추출합니다. 원본 TAR와 생성 데이터는 C:가 아닌
D:에 유지합니다.

```bash
python -m AI.training.extract_artifacts \
  --archive /mnt/d/VisionGuardData/nvidia/nearmiss-artifacts-00001.tar \
  --output /mnt/d/VisionGuardData/nvidia/artifacts-00001-selected
```

추출된 `*.rgb.mp4`와 같은 이름의 `*.object_detection.jsonl`을 YOLO 형식으로
변환합니다. 기본값은 5 FPS 샘플링, 시나리오 단위 train/val 80:20 분할입니다.
같은 시나리오의 여러 카메라 영상은 항상 같은 split에 들어갑니다.

```bash
python -m AI.training.preprocess \
  --source /mnt/d/VisionGuardData/nvidia/artifacts-00001-selected \
  --output /mnt/d/VisionGuardData/yolo-nearmiss-00001 \
  --sample-fps 5 \
  --train-ratio 0.67 \
  --val-ratio 0.33
```

변환기는 `Worker/character`를 `person(0)`, `forklift`를 `forklift(1)`로
매핑하고 `bounding_box_2d_tight_fast` 좌표를 사용합니다. 출력 폴더에는
학습용 `images/`, `labels/`, `dataset.yaml`과 변환 통계 `manifest.json`이
생성됩니다. 기존 데이터가 섞이는 것을 방지하기 위해 이미 이미지나 라벨이
있는 출력 폴더는 사용하지 않습니다.

변환 후 이미지/라벨 대응과 YOLO 좌표를 검사하고 무작위 라벨 미리보기를
생성합니다.

```bash
python -m AI.training.dataset \
  --config /mnt/d/VisionGuardData/yolo-nearmiss-00001-v2/dataset.yaml \
  --preview-dir AI/reports/dataset-preview \
  --preview-count 24
```

## Unity 캡처를 YOLO 데이터셋으로 변환

Unity의 `YoloDatasetCapture`가 생성한 `images/`, `labels/`, `classes.txt`가
들어 있는 한 개의 녹화 take는 별도 전처리기로 변환합니다. 연속 프레임이
train/val에 무작위로 섞여 평가 점수가 부풀려지지 않도록 시간 순서의 연속 구간으로
분할합니다. 아래 예시는 10 FPS 원본을 3 FPS 수준으로 줄입니다.

```bash
python -m AI.training.preprocess_unity \
  --source /mnt/d/VisionGuardData/unity/raw/train_take_01 \
  --output /mnt/d/VisionGuardData/unity/yolo-train-take-01-v1 \
  --source-fps 10 \
  --sample-fps 3 \
  --train-ratio 0.8 \
  --val-ratio 0.2
```

녹화 중 시뮬레이션이 멈추거나 특정 객체가 사라진 구간은 `--start-frame`과
`--end-frame`으로 제외할 수 있습니다. 두 값은 양 끝 프레임을 모두 포함합니다.

변환 중 이미지/라벨 stem, 클래스 순서, JPEG 읽기, YOLO 좌표 범위를 검사합니다.
출력에는 `dataset.yaml`과 프레임·클래스 분포를 기록한 `manifest.json`이 함께
생성됩니다. 시연용 영상과 최종 테스트 영상은 이 데이터셋에 포함하지 않습니다.

## NVIDIA와 Unity 데이터셋 병합

각 데이터셋의 기존 train/val 구분을 유지하면서 하나의 학습 데이터셋으로
병합합니다. 입력별 접두사를 파일명에 붙이므로 동일한 stem도 충돌하지 않습니다.

```bash
python -m AI.training.merge_datasets \
  --dataset nvidia=/mnt/d/VisionGuardData/yolo-nearmiss-00001-00003-v1/dataset.yaml \
  --dataset unity=/mnt/d/VisionGuardData/unity/yolo-train-take-04-v1/dataset.yaml \
  --output /mnt/d/VisionGuardData/yolo-nearmiss-unity-v1
```

입력 데이터셋을 먼저 검증한 뒤 이미지와 라벨을 복사하며, 결과 폴더에 출처별
통계를 담은 `manifest.json`과 학습용 `dataset.yaml`을 생성합니다.

학습과 평가는 아래 진입점을 사용합니다.

```bash
python -m AI.training.train \
  --data /mnt/d/VisionGuardData/yolo-nearmiss-00001-v2/dataset.yaml
python -m AI.training.evaluate \
  --model AI/models/checkpoints/visionguard/weights/best.pt \
  --data /mnt/d/VisionGuardData/yolo-nearmiss-00001-v2/dataset.yaml
```

기본 학습 설정은 `AI/configs/training.yaml.example`에 있으며 `--epochs`,
`--batch`, `--device`, `--model` 등의 CLI 옵션으로 필요한 값만 덮어쓸 수
있습니다. 실행 전에 `dataset.py` 검사를 수행하고 학습 완료 후 `weights/best.pt`와
`weights/last.pt`가 실제로 생성됐는지 확인합니다.

평가 기준은 `AI/configs/evaluation.yaml.example`에서 관리합니다. 평가 결과와
Precision-Recall 곡선, confusion matrix 등의 그래프는 `AI/reports/evaluation/`
아래에 저장되며, `evaluation_report.json`의 `passed`와 `failures`에서 운영 기준
통과 여부와 미달 항목을 확인할 수 있습니다.
