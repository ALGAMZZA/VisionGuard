# VisionGuard Backend

단일 카메라의 프레임을 분석하고 WARNING/DANGER 결과를 MySQL에 저장하는 Spring Boot API입니다.
Java 17이 필요합니다. 기본 AI 모드는 `mock`이며 이미지 내용에 관계없이 고정 WARNING 결과를 반환합니다.
실제 위험 판정으로 사용하지 마세요. 분석 응답의 `aiMode`에서 모드를 확인할 수 있습니다.

## 실행

```bash
# backend 디렉터리에서 실행 (Docker Compose 필요)
docker compose up -d --wait
bash gradlew bootRun
```

기본 포트는 8080입니다. Flyway가 DB 스키마를 생성·변경하고 Hibernate는 `ddl-auto=validate`로 구조를 검사합니다.
기존 Hibernate DB는 최초 한 번 버전 등록이 필요합니다. [DB 마이그레이션 안내](docs/migrations.md)를 따라 주세요.
운영 배포 전에는 인증/접근 제어가 필요합니다.

| 환경 변수 | 기본값 | 설명 |
| --- | --- | --- |
| DB_URL | jdbc:mysql://localhost:3306/visionguard | MySQL JDBC 주소 |
| DB_USERNAME | visionguard | DB 사용자 |
| DB_PASSWORD | visionguard | 로컬 개발 비밀번호 |
| CAMERA_ID | camera-1 | 이 서버가 허용하는 단일 카메라 |
| AI_MODE | mock | mock 또는 http |
| AI_BASE_URL | http://localhost:8000 | AI 서버 주소 |
| AI_TIMEOUT_MS | 30000 | 연결 및 응답 타임아웃(ms) |
| EVENT_MAX_GAP_MS | 2000 | 같은 위험을 이어 붙일 최대 촬영 간격(ms) |

실제 AI 서버를 별도로 실행한 뒤 연결합니다.

```bash
AI_MODE=http bash gradlew bootRun
```

## 분석 요청

```bash
curl -X POST 'http://localhost:8080/api/analyses' \
  -F 'file=@frame.jpg' \
  -F 'cameraId=camera-1' \
  -F 'streamId=video-20260907-1' \
  -F 'frameId=1' \
  -F 'capturedAt=2026-09-07T09:00:00+09:00' \
  -F 'fps=30'
```

- `file`: 이미지(최대 25 MiB). mock 모드는 JPEG/PNG 사용을 권장합니다.
- `cameraId`, `frameId`: 필수, 1~100자.
- `streamId`: 1~100자, 기본 `default`. 새 영상이나 AI 추적기 초기화/재시작마다 새로운 값을 사용합니다.
- 새 프레임은 같은 스트림의 직전 프레임보다 촬영 시각이 늦어야 합니다. 시각은 마이크로초 정밀도로 저장합니다.
- `capturedAt`: 필수, UTC 오프셋을 포함한 ISO 8601 촬영 시각.
- `fps`: 기본 30, 0 초과 240 이하. AI가 연속해서 처리하는 프레임의 실제 간격에 맞춥니다.
- 응답: `eventId`, `eventIds`, `cameraId`, `streamId`, `capturedAt`, `aiMode`, `prediction`.
- `eventIds`는 이번 프레임의 모든 위험 이벤트 ID입니다. 기존 `eventId`는 첫 ID이며 위험이 없으면 null입니다.
- `prediction`은 AI의 snake_case 응답 형식을 유지합니다.
- SAFE는 위험 이벤트를 생성하지 않습니다. 재요청 처리를 위한 프레임 응답 기록은 SAFE도 저장합니다.
- WARNING/DANGER는 사람·지게차 쌍마다 이벤트를 생성하거나 기존 이벤트를 갱신합니다.
- 이미지 원본은 저장하지 않습니다. 거리 단위는 픽셀이며 미터가 아닙니다.

## 위험 이력 조회

```bash
curl 'http://localhost:8080/api/risk-events?cameraId=camera-1&page=0&size=20'
curl 'http://localhost:8080/api/risk-events?from=2026-09-01T00:00:00Z&to=2026-09-30T23:59:59Z'
curl 'http://localhost:8080/api/risk-events/1'
```

목록은 `content`, `page`, `size`, `totalElements`, `totalPages`를 반환합니다.
카메라와 촬영 기간 필터는 선택 사항이고, 기간 양 끝을 포함합니다.
페이지는 0부터 시작하고 size는 1~100입니다. 촬영 시각, ID 내림차순으로 정렬합니다.
상세 응답은 `event` 요약과 전체 `prediction`입니다.
잘못된 입력은 400, 없는 이벤트는 404, 프레임 ID 충돌·촬영 순서 오류는 409, 용량 초과는 413, AI 연결/응답 실패는 502입니다.

## 위험 이벤트 수명과 재요청

- 카메라·streamId·personTrackId·forkliftTrackId가 같고 촬영 간격이 최대 간격 이내이면 같은 이벤트를 갱신합니다.
- `capturedAt`/`frameId`: 시작 프레임의 시각/ID. `lastSeenAt`: 마지막 위험 감지 시각. `frameCount`: 위험 감지 프레임 수.
- `level`: 이벤트 전체의 최고 위험도. 상세 `prediction`은 가장 최근 위험 프레임의 해당 쌍 판정이며, 탐지 배열은 인덱스 참조를 위해 유지합니다.
- 다음 프레임에서 해당 쌍의 위험이 없으면 `endedAt`을 그 프레임 촬영 시각으로 설정합니다 (`NOT_OBSERVED`). 일시적인 미탐지도 종료로 처리합니다.
- 촬영 간격이 2초(설정 가능)를 초과하면 마지막 감지 시각 + 최대 간격에 종료합니다 (`FRAME_GAP`). 다시 나타난 위험은 새 이벤트입니다.
- 다른 스트림의 새 프레임을 받으면 기존 스트림 이벤트를 마지막 감지 시각에 종료합니다 (`STREAM_CHANGED`).
- 추적 ID가 하나라도 없으면 합치지 않고 해당 프레임에 종료된 개별 이벤트로 저장합니다 (`UNTRACKED`).
- `status`: OPEN/CLOSED. 이전 버전에서 만든 이벤트는 LEGACY로 보존하며 새 이벤트와 합치지 않습니다.
- 일반 종료 판단은 **다음 프레임을 처리할 때** 합니다. 영상이 끝나면 아래 종료 API를 호출합니다. 입력 중단을 감지하는 자동 타이머는 없습니다.
- 동일 cameraId/streamId/frameId와 동일 이미지·촬영 시각·fps의 재요청은 DB에 저장된 최초 응답을 반환하며 AI를 다시 호출하지 않습니다. 더 최신 프레임 처리 후에도 원래 응답을 반환합니다.
- 같은 키에 다른 내용을 보내면 409입니다. 다른 ID에 같은 이미지를 보낸 요청은 별도 프레임입니다.
- `processed_frames`의 SHA-256 키를 PK로 사용합니다. 이벤트 변경과 응답 기록은 한 DB 트랜잭션으로 저장하며, 단일 서버 내 동시 요청은 커밋까지 직렬화합니다.
- DB 재시작/백엔드 재시작 후에도 기록이 유지되는 한 재요청을 구분합니다. 기록 자동 삭제 정책은 아직 없습니다.
- AI 추적기는 외부 프로세스여서 DB 롤백으로 되돌릴 수 없습니다. AI 호출 후 DB 저장이 실패하면 재시도에서 추론이 다시 실행될 수 있습니다.

## 영상 종료 API

```bash
curl -X POST http://localhost:8080/api/streams/end \
  -H 'Content-Type: application/json' \
  -d '{"cameraId":"camera-1","streamId":"video-20260907-1","endedAt":"2026-09-07T00:00:01Z"}'
```

- cameraId/streamId/endedAt은 필수입니다. 종료 시각은 해당 스트림의 마지막 처리 프레임 촬영 시각 이상이어야 합니다.
- 응답: `cameraId`, `streamId`, `endedAt`, `closedEventIds`. 열린 이벤트를 `STREAM_ENDED`로 종료합니다.
- SAFE만 처리한 스트림도 종료할 수 있습니다. 처리된 프레임이 없는 스트림은 404입니다.
- 동일 종료 요청은 저장된 응답을 반환합니다. 종료 시각 변경 또는 종료된 스트림의 새 프레임은 409입니다.
- 종료 후에도 이미 처리한 동일 프레임의 재요청은 원래 응답을 반환합니다.
- 종료 기록은 `stream_completions`에 저장합니다. 이벤트 종료와 완료 기록은 하나의 트랜잭션이며 분석 요청과 직렬화합니다.
- 이 API는 AI의 `/reset`을 호출하지 않습니다. 늦게 도착한 이전 스트림의 종료가 현재 AI 추적 상태를 지우지 않도록 합니다.

## 프론트 없이 영상으로 전체 흐름 검증

백엔드와 MySQL이 실행 중인 상태에서 backend 디렉터리에서 실행합니다.
OpenCV가 설치된 기존 AI 가상환경을 사용하며 학습 프로세스를 변경하지 않습니다.

```bash
../AI/.venv/bin/python scripts/video_smoke.py ../AI/references/data/collision2.mp4 \
  --stride 3 --max-frames 30
```

도구는 로컬 영상을 읽고 JPEG 프레임을 **하나씩 순서대로** 전송합니다. 기본 `AI_MODE=mock`에서는
항상 WARNING이므로 실제 모델 성능 평가가 아닌 API/DB 연결 검증입니다.

- `--stride 3`: 0, 3, 6번 등 매 3프레임을 전송. 원본이 30 FPS이면 AI에는 10 FPS를 전달합니다.
- 촬영 시각은 `시작 시각 + 원본 프레임 번호 / 원본 FPS`입니다. 재생 속도로 기다리지 않고 응답 완료 후 다음 프레임을 전송합니다.
- 일정 FPS 영상용입니다. 가변 FPS 영상의 실제 프레임 타임스탬프는 지원하지 않습니다.
- `--max-frames 30`: 최대 30개만 전송한 뒤 스트림 종료. 생략하면 영상 전체를 처리합니다.
- `--stream-id`: 생략하면 실행마다 새 UUID. `--start-time`: 생략하면 실행 시작 UTC 시각.
- `--source-fps`: 영상 FPS를 읽지 못하거나 메타데이터가 잘못됐을 때 원본 FPS 지정.
- `--base-url`, `--camera-id`, `--timeout`으로 대상 서버 및 대기 시간을 지정할 수 있습니다.
- 종료 API를 호출한 뒤 이번 실행의 위험 이벤트를 상세 조회해 모두 CLOSED인지 확인합니다.
- 종료 시각은 마지막으로 전송을 시도한 프레임의 촬영 시각입니다. 영상의 나머지 구간에 위험이 지속됐다고 추정하지 않습니다.
- 네트워크 응답 연결 실패에는 동일 요청을 최대 2회 재전송합니다 (`--retries`). HTTP 오류에는 자동 재시도하지 않습니다.
- 오류/Ctrl+C가 나도 가능한 경우 종료를 시도합니다. SIGKILL·터미널 강제 종료 등에서는 보장하지 않습니다.
- 결과는 `reports/video-smoke-<UUID>.json`에 저장됩니다. `--report`로 경로를 지정할 수 있고 기존 파일은 덮어쓰지 않습니다.
- JSON에 전송 수, 위험도별 프레임 수, 이벤트 ID, 종료 요청/결과, 상세 이벤트와 실패 원인을 기록합니다.
- 종료 실패 시 보고서의 `completionRequest`를 종료 API에 다시 보내 복구할 수 있습니다.
- 프로세스 종료 코드: 검증 성공 0, 실패 1, Ctrl+C 130. 입력 오류는 2입니다.
- 중단된 실행을 이어 보내는 기능은 없습니다. 다시 실행할 때는 새 streamId를 사용합니다.

학습이 완료되면 실제 AI 서버를 실행하고 백엔드를 `AI_MODE=http`로 시작한 뒤 같은 도구를 사용합니다.
새 영상 전에 AI 추적기를 초기화하려면 명시적으로 다음 옵션을 지정합니다.
해당 AI 서버를 다른 클라이언트가 사용하지 않는 상태에서 실행하세요.

```bash
../AI/.venv/bin/python scripts/video_smoke.py ../AI/references/data/collision2.mp4 \
  --stride 3 --max-frames 30 --reset-ai-url http://localhost:8000
```

`--reset-ai-url`은 지정한 서버의 `/reset`을 최초 한 번 호출합니다. 종료 API는 AI를 초기화하지 않습니다.

## 현재 범위

AI 서버는 추적 상태를 하나만 유지합니다. 백엔드를 한 인스턴스로 실행하고,
클라이언트는 이전 요청 완료 후 다음 프레임을 촬영 순서대로 보내야 합니다.
다른 클라이언트가 같은 AI 서버에 직접 추론 요청을 보내지 않도록 구성하세요.
새 영상을 시작할 때 진행 중인 요청이 없는 상태에서 AI의 `POST /reset`을 호출하고 새로운 `streamId`를 사용해야 합니다.
`streamId` 자체가 AI 추적기를 초기화하지는 않습니다. 백엔드만 재시작하면 기존 streamId를 유지할 수 있으나 AI를 재시작했다면 새 streamId가 필요합니다.
카메라 관리 CRUD와 실시간 알림은 아직 없습니다.
mock 이벤트는 DB에 저장되므로 실제 데이터 수집에는 별도 DB를 사용하세요.

## 검증

```bash
bash gradlew test
python -m unittest discover -s scripts/tests -v
```

테스트는 H2의 MySQL 호환 모드를 사용하므로 MySQL이나 학습된 모델 없이 실행됩니다.
실제 HTTP 분석·이력 조회, 입력 검증, 위험 병합/종료, 다중 객체 쌍, 동시 재요청, 순서·ID 충돌, DB 롤백, 기존 데이터 보존, 스트림 종료/재요청을 검증합니다.
Python 단위 테스트는 OpenCV 설치 없이 FPS·시각 계산, 프레임 제한, 실패/중단 시 종료, 재시도 요청 일치 여부를 검증합니다.

## 기술 스택

- Backend: Java 17, Spring Boot 4.1.1, Spring MVC (REST API)
- Persistence: Spring Data JPA / Hibernate, MySQL 8.4, Flyway
- Build & local environment: Gradle, Docker Compose
- Tests: JUnit, Mockito, H2
- AI inference server (별도 구성): Python, FastAPI

## Swagger와 프론트 CORS

- Swagger UI: `http://localhost:8080/swagger-ui.html`
- OpenAPI JSON: `http://localhost:8080/v3/api-docs`
- 기본 허용 origin: `http://localhost:3000`, `http://localhost:5173`
- 환경 변수 `CORS_ALLOWED_ORIGINS`에 쉼표로 구분한 origin을 지정하면 기본 목록을 대체합니다.
- `/api/**`의 GET/POST/OPTIONS와 Content-Type/Accept 헤더를 허용하며 쿠키 credentials는 허용하지 않습니다.
- Swagger의 Try it out으로 보낸 POST는 실제 DB에 기록됩니다.

```bash
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173 bash gradlew bootRun
```

[프론트 API 명세](docs/frontend-api.md)에 Axios 예시와 상세 규칙을 정리했습니다.
Swagger 연동에는 [springdoc-openapi 공식 안내](https://springdoc.org/getting-started.html)의 WebMVC UI starter 3.1.1을 사용합니다.
