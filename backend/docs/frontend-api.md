# VisionGuard 프론트엔드 API 연동 명세

2026-09-09 현재 백엔드 구현 기준입니다. 타입은 JavaScript/JSON 기준이며 `?`는 null 가능을 뜻합니다.

## 공통 규칙

| 항목 | 규칙 |
| --- | --- |
| 로컬 기본 주소 | `http://localhost:8080` (백엔드가 실행 중인 컴퓨터 기준) |
| 팀원 PC에서 접근 | 팀원의 `localhost`는 팀원 자신의 PC입니다. 공유 서버 주소와 접근 가능한 포트는 별도 전달 필요 |
| 성공 HTTP 코드 | 아래 API 모두 `200` |
| 응답 형식 | JSON |
| 필드명 | 백엔드 필드: camelCase, `prediction` 내부: snake_case |
| 날짜 요청 | UTC 오프셋 포함 ISO 8601 문자열. 예: `2026-09-08T09:00:00+09:00` 또는 `2026-09-08T00:00:00Z` |
| 날짜 응답 | UTC ISO 8601 문자열. 소수 초 자릿수는 고정되지 않음 |
| 인증 | 현재 토큰 인증 미구현 |
| CORS | 기본 허용: `http://localhost:3000`, `http://localhost:5173`. `CORS_ALLOWED_ORIGINS`로 변경 |
| 카메라 | 단일 카메라만 지원. 기본 `camera-1` (`CAMERA_ID` 설정으로 변경 가능) |
| AI 모드 | 기본 `mock`: 고정 WARNING 결과. 실제 모델 연결 시 `http` |
| 숫자 ID | 현재 JSON number. Java Long ID를 사용하므로 장기적으로 JS 안전 정수 범위를 넘을 경우 문자열 계약 변경 필요 |

## API 목록

| 기능 | Method | URL | 요청 방식 |
| --- | --- | --- | --- |
| 프레임 분석 | POST | `/api/analyses` | multipart/form-data |
| 위험 이력 목록 | GET | `/api/risk-events` | Query parameters |
| 위험 이력 상세 | GET | `/api/risk-events/{id}` | Path parameter |
| 영상 스트림 종료 | POST | `/api/streams/end` | application/json |

## 1. 프레임 분석

### 요청: POST /api/analyses

| 필드 | 타입 | 필수 | 설명 / 제한 |
| --- | --- | --- | --- |
| `file` | File 또는 Blob | O | 이미지 한 장, 최대 25 MiB. 전체 MP4 업로드 API가 아님 |
| `cameraId` | string | O | 1~100자, 기본 서버에서는 `camera-1`만 허용 |
| `frameId` | string | O | 1~100자, 스트림 내 프레임 고유 ID. 예: `0`, `1` |
| `capturedAt` | string (datetime) | O | 실제 촬영 시각. 같은 스트림의 새 프레임은 직전 처리 프레임보다 늦어야 함 |
| `streamId` | string | X | 1~100자, 기본 `default`. 새 영상마다 새 UUID 등 사용 권장 |
| `fps` | number | X | 기본 30, 0 초과 240 이하. 실제 AI 처리 프레임 간격의 FPS |

FormData에 숫자를 넣을 때는 문자열로 변환합니다. FormData의 Content-Type은 브라우저가 boundary와 함께 설정하므로 직접 지정하지 않습니다.

### 응답

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `eventId` | number? | 첫 위험 이벤트 ID. 위험이 없으면 null. 전체 결과에는 eventIds 사용 |
| `eventIds` | number[] | 이번 프레임에서 생성 또는 갱신한 모든 위험 이벤트 ID. 위험이 없으면 빈 배열 |
| `cameraId` | string | 요청 카메라 ID |
| `streamId` | string | 요청 스트림 ID |
| `capturedAt` | string (datetime) | 요청 촬영 시각, 마이크로초 정밀도로 정규화 |
| `aiMode` | string | `mock` 또는 `http` |
| `prediction` | Prediction | 아래 AI 결과 객체 |

### Prediction 객체

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `frame_id` | string? | AI 결과의 프레임 ID |
| `image_width` | number | 원본 분석 이미지 가로 픽셀 수 |
| `image_height` | number | 원본 분석 이미지 세로 픽셀 수 |
| `detections` | Detection[] | 탐지 객체 목록. 탐지가 없으면 빈 배열 |
| `risks` | Risk[] | 사람·지게차 쌍별 위험 판정. 빈 배열 가능 |
| `overall_risk` | string | `SAFE`, `WARNING`, `DANGER` |
| `processing_time_ms` | number | AI 추론 처리 시간(ms). 네트워크와 백엔드 DB 처리 시간을 포함한 전체 요청 시간이 아님 |

### Detection 객체: prediction.detections[i]

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `class_id` | number | 객체 클래스 ID. 현재 모델은 person=0, forklift=1 |
| `class_name` | string | `person` 또는 `forklift` |
| `confidence` | number | 탐지 신뢰도, 0~1 |
| `track_id` | number? | 추적 ID. 아직 추적 ID가 없으면 null |
| `bbox.x1` | number | 박스 왼쪽 X, 원본 이미지 픽셀 좌표 |
| `bbox.y1` | number | 박스 위쪽 Y, 원본 이미지 픽셀 좌표 |
| `bbox.x2` | number | 박스 오른쪽 X, 원본 이미지 픽셀 좌표 |
| `bbox.y2` | number | 박스 아래쪽 Y, 원본 이미지 픽셀 좌표 |

화면 크기가 원본과 다르면 좌표를 표시 이미지 크기에 맞춰 변환해야 합니다.
여백 없이 표시할 때 `화면 x = 원본 x × 표시 너비 / image_width`이며 y도 동일합니다.
`object-fit: contain` 등으로 여백이 생기면 표시 이미지 영역의 여백 오프셋도 더해야 합니다.

### Risk 객체: prediction.risks[i]

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `level` | string | 이 쌍의 `SAFE`, `WARNING`, `DANGER` |
| `person_index` | number | detections 배열에서 사람 객체의 인덱스 (0부터) |
| `forklift_index` | number | detections 배열에서 지게차 객체의 인덱스 (0부터) |
| `person_track_id` | number? | 사람 추적 ID |
| `forklift_track_id` | number? | 지게차 추적 ID |
| `distance_px` | number | 현재 거리, 픽셀 단위 |
| `future_distance_px` | number | 예측 거리, 픽셀 단위 |
| `time_to_closest_approach_s` | number? | 최근접 예상 시간, 초 단위 |
| `score` | number | 위험 점수, 0~100. 탐지 confidence와 다른 값 |
| `reason` | string | 판정 이유. 표시 가능한 설명이며 고정 코드로 분기하지 않는 것을 권장 |

## 2. 위험 이력 목록

### 요청: GET /api/risk-events

| Query 필드 | 타입 | 필수 | 기본값 / 설명 |
| --- | --- | --- | --- |
| `cameraId` | string | X | 생략하면 전체 카메라 이력 |
| `from` | string (datetime) | X | 위험 시작 시각(capturedAt) 필터의 하한, 해당 시각 포함 |
| `to` | string (datetime) | X | 위험 시작 시각 필터의 상한, 해당 시각 포함. from보다 빠르면 400 |
| `page` | number | X | 기본 0, 0 이상의 정수 |
| `size` | number | X | 기본 20, 1~100 정수 |

정렬은 위험 시작 시각 내림차순, 같은 시각이면 ID 내림차순입니다.
기간 필터는 이벤트 시작 시각에 적용됩니다. 기간과 겹치는 모든 이벤트를 찾는 조건은 아닙니다.
streamId, level, status 필터는 현재 지원하지 않습니다.
Query 문자열은 URLSearchParams 등으로 인코딩하세요. 날짜의 `+09:00`에서 `+`를 그대로 넣지 않습니다.

### 응답

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `content` | EventSummary[] | 현재 페이지의 이벤트 목록 |
| `page` | number | 현재 페이지 번호, 0부터 |
| `size` | number | 요청 페이지 크기 |
| `totalElements` | number | 필터에 맞는 전체 이벤트 수 |
| `totalPages` | number | 전체 페이지 수 |

### EventSummary 객체

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `id` | number | 위험 이벤트 ID |
| `cameraId` | string | 카메라 ID |
| `streamId` | string? | 스트림 ID. LEGACY 이벤트는 null |
| `frameId` | string | 이벤트 시작 프레임 ID |
| `capturedAt` | string (datetime) | 위험 시작 시각 |
| `createdAt` | string (datetime) | 최초 DB 저장 시각 |
| `level` | string | 이벤트 전체의 최고 위험도. 새 이벤트는 WARNING 또는 DANGER |
| `personTrackId` | number? | 사람 추적 ID |
| `forkliftTrackId` | number? | 지게차 추적 ID |
| `lastSeenAt` | string (datetime)? | 마지막 위험 감지 시각. LEGACY는 null |
| `endedAt` | string (datetime)? | 종료 시각. OPEN/LEGACY이면 null |
| `frameCount` | number? | 위험으로 감지된 프레임 수. 재요청은 증가하지 않음. LEGACY는 null |
| `status` | string | `OPEN`, `CLOSED`, `LEGACY` |
| `endReason` | string? | 종료 이유. 미종료/LEGACY이면 null |

| status 값 | 의미 |
| --- | --- |
| `OPEN` | 진행 중인 위험 이벤트 |
| `CLOSED` | 종료된 위험 이벤트 |
| `LEGACY` | 수명 관리 기능 도입 전 데이터. 일부 추가 필드가 null |

| endReason 값 | 의미 |
| --- | --- |
| `NOT_OBSERVED` | 다음 프레임에서 해당 쌍의 위험이 확인되지 않음 |
| `FRAME_GAP` | 위험 프레임 간격이 설정된 최대 간격을 초과함 (기본 2초) |
| `STREAM_CHANGED` | 다른 스트림의 새 프레임이 처리됨 |
| `UNTRACKED` | 추적 ID가 없어 개별 프레임 이벤트로 저장·종료 |
| `STREAM_ENDED` | 영상 종료 API로 종료 |

## 3. 위험 이력 상세

### 요청: GET /api/risk-events/{id}

| Path 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | number | O | 목록의 id 또는 분석 응답의 eventIds에 있는 ID |

### 응답

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `event` | EventSummary | 위 이벤트 요약 객체 |
| `prediction` | Prediction | 마지막 위험 감지 프레임의 해당 쌍 결과. detections는 인덱스 참조를 위해 전체 배열 유지 |

`event.level`은 누적 최고 위험도, `prediction.overall_risk`는 최근 저장된 판정이므로 서로 다를 수 있습니다.
LEGACY 데이터에는 예전 방식의 프레임 전체 결과가 들어 있을 수 있습니다.
이미지/영상 원본은 저장하지 않으므로 재생 URL이나 썸네일 URL은 응답에 없습니다.

## 4. 영상 스트림 종료

### 요청: POST /api/streams/end (JSON)

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `cameraId` | string | O | 1~100자, 분석 요청과 같은 카메라 |
| `streamId` | string | O | 1~100자, 종료할 스트림 |
| `endedAt` | string (datetime) | O | 마지막 처리 프레임 촬영 시각 이상 |

### 응답

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `cameraId` | string | 카메라 ID |
| `streamId` | string | 종료한 스트림 ID |
| `endedAt` | string (datetime) | 종료 시각 |
| `closedEventIds` | number[] | 이번 종료에서 닫은 이벤트 ID 목록. 닫을 이벤트가 없으면 빈 배열 |

## 5. 오류 처리

| HTTP 코드 | 의미 | 프론트 처리 |
| --- | --- | --- |
| `400` | 필수 입력 누락, 잘못된 이미지·FPS·날짜·페이지 등 | 입력 확인 및 detail 표시 |
| `404` | 존재하지 않는 이벤트 또는 처리한 프레임이 없는 스트림 | 없는 데이터/스트림 안내 |
| `409` | 동일 프레임 ID의 내용 충돌, 촬영 순서 오류, 종료한 스트림의 새 프레임, 잘못된 종료 시각 등 | 요청 정보 확인. 새로운 영상이면 새 streamId 사용 |
| `413` | 이미지/전체 multipart 요청 크기 초과 | 이미지 크기 줄이기 |
| `502` | AI 연결 또는 AI 응답 처리 실패 | 분석 실패 안내 |
| `500` | 기타 서버 내부 오류 | 일반 오류 안내 |

검증·AI 오류 등은 Problem Detail JSON을 반환합니다. 일반 500 오류는 다른 형식일 수 있으므로 detail이 없을 때의 기본 메시지도 준비하세요.

| 오류 응답 필드 | 타입 | 설명 |
| --- | --- | --- |
| `type` | string | 문제 유형 URI (일반적으로 about:blank, 생략될 수 있음) |
| `title` | string | 오류 제목 |
| `status` | number | HTTP 상태 코드 |
| `detail` | string | 사람이 읽을 오류 설명 |
| `instance` | string | 요청 경로 |

## 6. 연동 순서와 주의사항

| 순서 / 항목 | 규칙 |
| --- | --- |
| 영상 시작 | 새 streamId 생성. 동일 영상 동안 유지 |
| 실제 AI 새 영상 | AI 추적기 reset이 별도로 필요함. 백엔드 종료 API는 AI reset을 수행하지 않음. 서버 운영 측과 연결 절차 합의 필요 |
| 프레임 전송 | 같은 스트림의 프레임을 순서대로, 이전 응답 완료 후 다음 요청 전송 |
| 재시도 | 동일 cameraId/streamId/frameId, 이미지 bytes, 촬영 시각, FPS를 그대로 사용. 저장 완료된 요청은 기존 응답 반환 |
| 촬영 간격 | 샘플링하면 fps도 조정. 예: 원본 30 FPS에서 매 3프레임 전송이면 fps=10 |
| 실시간 화면 | 분석 응답의 prediction으로 갱신 |
| 위험 이력 화면 | 목록 API의 content와 페이지 정보 사용 |
| 영상 종료 | 마지막 요청 완료 후 /api/streams/end 호출 |
| 종료 재시도 | 동일 cameraId/streamId/endedAt으로 호출. 최초 종료 응답 재사용 |
| 종료한 영상 재시작 | 새 streamId 사용. 기존 스트림의 새 프레임은 409 |
| 알림 수신 | 현재 SSE/WebSocket/푸시 알림 API 없음 |
| API 문서 UI | `/swagger-ui.html` 또는 `/swagger-ui/index.html`. OpenAPI JSON: `/v3/api-docs` |

## 7. CORS와 Swagger 사용

| 항목 | 설정 |
| --- | --- |
| Swagger UI | `http://localhost:8080/swagger-ui.html` |
| OpenAPI JSON | `http://localhost:8080/v3/api-docs` |
| 기본 프론트 origin | `http://localhost:3000`, `http://localhost:5173` |
| 허용 범위 | `/api/**`, GET/POST/OPTIONS, Content-Type/Accept 헤더 |
| 쿠키 인증 | credentials 미허용. Axios에 `withCredentials: true`를 설정하지 않음 |
| 다른 프론트 주소 | `CORS_ALLOWED_ORIGINS`에 쉼표로 구분한 origin 목록 지정. 기본 목록을 대체함 |
| origin 형식 | 프로토콜 + 호스트 + 포트. 경로나 끝의 `/` 제외. `127.0.0.1`과 `localhost`는 다른 origin |

예를 들어 프론트 주소를 추가할 때 백엔드를 다음과 같이 실행합니다.

```bash
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173,http://192.168.0.20:5173 bash gradlew bootRun
```

Swagger에서 API 선택 → **Try it out** → 입력 → **Execute**로 테스트할 수 있습니다.
POST 요청은 실제 DB를 변경합니다. mock 모드는 실제 탐지 대신 고정 WARNING을 반환합니다.
기본 분석 예시의 촬영 시각·frameId는 다음 프레임을 보낼 때 갱신하고, 새 영상에는 새 streamId를 사용하세요.
Swagger는 접속한 백엔드와 같은 origin을 사용합니다. 다른 PC에서 접속할 공유 서버 주소 및 네트워크 설정은 별도입니다.

Axios 기본 설정 예시:

```javascript
import axios from 'axios';

export const api = axios.create({
  baseURL: 'http://localhost:8080', // 팀에서 공유하는 서버 주소로 변경
  timeout: 45000,
});

// FormData 요청에는 Content-Type을 직접 지정하지 않습니다.
// GET 파라미터는 axios의 params를 사용해 날짜의 + 문자도 인코딩합니다.
const { data } = await api.get('/api/risk-events', {
  params: { cameraId: 'camera-1', page: 0, size: 20 },
});
```
