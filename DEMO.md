# 1차 시연 실행

## 현재 연결된 실제 모델로 실행

운영 모델: `AI/models/production/best.pt`.
원본: `AI/models/checkpoints/visionguard-yolo11n-00001-00003-v1/weights/best.pt` (2026-09-07 체크포인트).
모델의 클래스는 `person`, `forklift`입니다. 원본을 보존하고 운영 경로에 복사했습니다.
Windows의 `D:\VisionGuardData\nvidia\best.pt`와도 SHA-256이 동일한 모델입니다.

저장소 루트에서 터미널을 각각 열어 실행합니다:
```bash
# 터미널 1: 실제 AI 추론 서버 (기본 CPU)
bash scripts/start-ai.sh
```
```bash
# 터미널 2: 실제 AI를 사용하는 백엔드 + 로컬 파일 DB
bash scripts/start-backend-ai.sh
```
```bash
# 터미널 3: 웹 화면
cd frontend
npm start
```

- 웹 화면: http://localhost:3000
- 백엔드: http://localhost:8080
- AI 서버: http://localhost:8000 (상태 확인: `/health`, API 문서: `/docs`)

웹 화면 → 백엔드 → AI 서버 순서로 요청합니다. 프론트의 API 주소는 백엔드 주소이며 AI 서버 주소로 변경하지 않습니다.
대시보드의 새 분석 결과에 `AI 분석`이 표시되어야 합니다. 기존 MOCK 이력은 DB에 남아 있습니다.
현재 환경은 PyTorch에서 CUDA를 사용할 수 없어 CPU로 실행합니다.
검증: 샘플 영상 12프레임 분석 및 스트림 종료 성공, `/health`의 `model_loaded=true` 확인. 해당 구간은 모두 SAFE이며 모델 정확도 평가는 별도입니다.


## 모델 없이 화면과 API 전체 연결 확인

터미널 1:
```bash
cd backend
bash gradlew bootRun --args='--spring.profiles.active=demo'
```

터미널 2:
```bash
cd frontend
npm start
```

http://localhost:3000 접속 → 대시보드에서 영상 파일 선택 → 분석 시작 → 분석 중지 → 이벤트 상세 링크 → 객체 위치 → 위험구역 히트맵 → 우측 상단 알림.
예제 영상: `AI/references/data/collision2.mp4`. 브라우저에서 재생 가능한 MP4를 사용합니다.

- `demo` 프로필은 Docker 없이 H2 파일 DB(`backend/data/demo`)에 저장합니다. MySQL과 분리되며 재시작해도 유지됩니다.
- 기본 AI는 MOCK이며 영상 내용과 무관한 고정 경고를 반환합니다. 실제 모델 성능 시연은 아래 설정이 필요합니다.
- 영상은 0.5초 간격으로 추출하고 이전 API 응답을 받은 후 다음 프레임을 보냅니다. 빠른 실시간 재생이 아니라 순차 분석입니다.
- 페이지를 이동하면 현재 요청 완료 후 분석을 종료합니다. 탭 강제 종료나 서버 연결 끊김 시 종료 처리가 보장되지 않습니다.
- 화면에 종료 재시도가 표시되면 재시도 후 새 분석을 시작합니다.
- 영상 자체는 서버에 저장하지 않습니다. 저장된 이력에는 판정과 객체 좌표만 있습니다.
- 도면 좌표 보정 정보가 없어 객체 위치는 영상 좌표로 표시하고, 히트맵은 실제 이벤트의 시간별 빈도와 영상 좌표 분포로 표시합니다. 좌표 분포는 최근 최대 100건의 마지막 위험 프레임을 사용합니다.
- 서버는 한 카메라와 한 분석 클라이언트를 전제로 합니다.

## 학습된 AI 연결

저장소 루트에서 학습된 person/forklift 모델 경로를 지정하고 실행:
```bash
VISIONGUARD_MODEL_PATH=/absolute/path/best.pt AI/.venv/bin/python -m uvicorn AI.inference.app:app --host 127.0.0.1 --port 8000
```

백엔드를 다음과 같이 실행:
```bash
cd backend
AI_MODE=http bash gradlew bootRun --args='--spring.profiles.active=demo'
```

AI가 다른 PC에 있으면 `AI_BASE_URL=http://서버주소:8000`도 설정합니다.
MySQL을 사용하려면 `--args='--spring.profiles.active=demo'`를 제거하고 기존 DB 환경 변수를 설정합니다.
새 분석 스트림마다 백엔드가 AI 추적기를 초기화합니다. AI 서버 재시작 후에는 새 분석을 시작하세요.
