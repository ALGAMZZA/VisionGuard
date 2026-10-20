# VisionGuard 프론트엔드

## 백엔드 연동

개발 시 `npm start`로 실행하면 `/api` 요청을 `http://localhost:8082`으로 프록시합니다.
공유 서버를 사용하려면 `package.json`의 `proxy`를 변경하고 개발 서버를 재시작하세요.
`.env.example`을 참고해 `REACT_APP_API_BASE_URL`(예: `https://server.example/api`)과
`REACT_APP_CAMERA_ID`를 설정할 수도 있습니다. `REACT_APP_CAMERA_IDS=camera-1,camera-2`로 관제 및 이력 필터의 카메라 목록을 지정합니다.
카메라 목록 API가 없어 이 목록은 실제 브리지 설정과 맞춰야 합니다. 환경설정 변경 후 개발 서버를 재시작하세요.
직접 다른 origin에 요청할 때는 백엔드 CORS 설정이 필요합니다.
운영 환경에서는 `/api` 역방향 프록시 또는 API 주소와 CORS 설정이 필요합니다.

`src/api/visionGuardApi.js`의 함수는 Axios 응답의 `data`를 반환하고 오류는 그대로 전달합니다.
화면에서는 `getApiErrorMessage(error)`로 Problem Detail 또는 기본 오류 메시지를 표시합니다.

| 함수 | API |
| --- | --- |
| `getLatestAnalysis(cameraId)` | GET /api/analyses/latest |
| `analyzeFrame({ file, cameraId, frameId, capturedAt, streamId?, fps? })` | POST /api/analyses |
| `getRiskEvents({ cameraId?, from?, to?, page?, size? })` | GET /api/risk-events |
| `getRiskEvent(id)` | GET /api/risk-events/{id} |
| `endStream({ cameraId, streamId, endedAt })` | POST /api/streams/end |

모든 함수는 두 번째 인자로 `{ signal }`을 받을 수 있습니다.
`prediction` 내부는 snake_case, 이벤트는 camelCase 필드명을 그대로 사용합니다.
`cctv` → `cameraId`, `workerId` → `personTrackId`, `forkliftId` → `forkliftTrackId`,
`date/time` → `capturedAt`, `levelKey` → `level`로 이력 화면을 변경했습니다.
위험 단계는 SAFE/WARNING/DANGER이고, 거리 단위는 px입니다. 위험 점수는 충돌 확률이 아닙니다.

위험 이력과 헤더 최근 알림은 실제 API를 사용합니다. 날짜 필터는 브라우저 로컬 날짜의 시작/끝을 UTC로 변환합니다.
영상 URL, 위치, 읽음 상태, 사고 통계 및 위험 단계 서버 필터는 현재 API에 없어 표시하지 않습니다.
대시보드와 도면 화면은 최신 분석 결과를 3초 간격으로 조회합니다. 촬영 후 15초가 지난 결과는 갱신 지연으로 표시합니다.
404는 분석 대기, 통신 오류는 연결 실패로 구분하며 mock 분석에는 모의 분석 표시를 붙입니다.
대시보드는 기존 CCTV 4분할 및 확대 상세 패널을 유지하고, 설정된 카메라의 실제 분석값을 표시합니다. 미설정 CCTV는 데이터 없음으로 표시합니다.
도면 화면은 기존 공장 도면과 우측 패널을 유지합니다. 도면 위치 표시는 예시이며, 우측 객체 목록·위험 지표·영상 좌표는 최신 분석 결과입니다.
히트맵은 기존 도면·차트·순위 구성을 유지합니다. 도면의 분포는 예시이며, 추이·총건수·순위는 실제 위험 이력입니다.
영상 URL과 공장 좌표는 아직 제공되지 않습니다. 화면에 남아 있는 구역명과 도면 배치는 기존 UI 예시입니다.
히트맵 화면의 추이와 카메라별 순위는 기간 내 위험 이력을 모든 페이지에서 조회해 집계합니다.
오늘/7일/30일은 브라우저 로컬 날짜 기준이며 오늘을 포함합니다. 집계는 시작 시각과 누적 최고 위험도 기준입니다.
30일 추이는 기존 차트 크기에 맞춰 3일 단위로 묶어 표시합니다.
전용 집계 API 및 스냅샷 페이지 조회가 없어 대량 이력에서는 느릴 수 있고, 조회 중 새 이력이 들어오면 집계가 달라질 수 있습니다.
프레임 입력/추출은 기존 브리지를 사용합니다. 실제 AI 분석에는 백엔드 `AI_MODE=http` 설정이 필요합니다.

분석 호출 시 이미지 한 장(최대 25 MiB)을 전달하고 같은 스트림은 이전 요청을 `await`한 뒤 다음 프레임을 전송하세요.
새 영상은 새 `streamId`를 생성하고, `capturedAt`은 촬영 시각, `fps`는 실제 전송 간격 기준으로 지정하세요.
재시도는 이미지 bytes와 모든 메타데이터를 유지해야 합니다. 마지막 요청 완료 후 `endStream`을 호출하고,
`endedAt`은 마지막 프레임의 `capturedAt` 이상이어야 합니다. 종료 재시도에도 같은 값을 사용하세요.
분석 POST의 자동 재시도는 수행하지 않습니다. 현재 백엔드의 HTTP 모드는 스트림 종료 시 해당 AI 추적기를 reset합니다.

# Getting Started with Create React App

This project was bootstrapped with [Create React App](https://github.com/facebook/create-react-app).

## Available Scripts

In the project directory, you can run:

### `yarn start`

Runs the app in the development mode.\
Open [http://localhost:3000](http://localhost:3000) to view it in your browser.

The page will reload when you make changes.\
You may also see any lint errors in the console.

### `yarn test`

Launches the test runner in the interactive watch mode.\
See the section about [running tests](https://facebook.github.io/create-react-app/docs/running-tests) for more information.

### `yarn build`

Builds the app for production to the `build` folder.\
It correctly bundles React in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.\
Your app is ready to be deployed!

See the section about [deployment](https://facebook.github.io/create-react-app/docs/deployment) for more information.

### `yarn eject`

**Note: this is a one-way operation. Once you `eject`, you can't go back!**

If you aren't satisfied with the build tool and configuration choices, you can `eject` at any time. This command will remove the single build dependency from your project.

Instead, it will copy all the configuration files and the transitive dependencies (webpack, Babel, ESLint, etc) right into your project so you have full control over them. All of the commands except `eject` will still work, but they will point to the copied scripts so you can tweak them. At this point you're on your own.

You don't have to ever use `eject`. The curated feature set is suitable for small and middle deployments, and you shouldn't feel obligated to use this feature. However we understand that this tool wouldn't be useful if you couldn't customize it when you are ready for it.

## Learn More

You can learn more in the [Create React App documentation](https://facebook.github.io/create-react-app/docs/getting-started).

To learn React, check out the [React documentation](https://reactjs.org/).

### Code Splitting

This section has moved here: [https://facebook.github.io/create-react-app/docs/code-splitting](https://facebook.github.io/create-react-app/docs/code-splitting)

### Analyzing the Bundle Size

This section has moved here: [https://facebook.github.io/create-react-app/docs/analyzing-the-bundle-size](https://facebook.github.io/create-react-app/docs/analyzing-the-bundle-size)

### Making a Progressive Web App

This section has moved here: [https://facebook.github.io/create-react-app/docs/making-a-progressive-web-app](https://facebook.github.io/create-react-app/docs/making-a-progressive-web-app)

### Advanced Configuration

This section has moved here: [https://facebook.github.io/create-react-app/docs/advanced-configuration](https://facebook.github.io/create-react-app/docs/advanced-configuration)

### Deployment

This section has moved here: [https://facebook.github.io/create-react-app/docs/deployment](https://facebook.github.io/create-react-app/docs/deployment)

### `yarn build` fails to minify

This section has moved here: [https://facebook.github.io/create-react-app/docs/troubleshooting#npm-run-build-fails-to-minify](https://facebook.github.io/create-react-app/docs/troubleshooting#npm-run-build-fails-to-minify)
