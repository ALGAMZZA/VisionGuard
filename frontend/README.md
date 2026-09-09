# VisionGuard 프론트엔드

## 백엔드 연동

개발 시 `npm start`로 실행하면 `/api` 요청을 `http://localhost:8080`으로 프록시합니다.
공유 서버를 사용하려면 `package.json`의 `proxy`를 변경하고 개발 서버를 재시작하세요.
`.env.example`을 참고해 `REACT_APP_API_BASE_URL`(예: `https://server.example/api`)과
`REACT_APP_CAMERA_ID`를 설정할 수도 있습니다. 직접 다른 origin에 요청할 때는 백엔드 CORS 설정이 필요합니다.
운영 환경에서는 `/api` 역방향 프록시 또는 API 주소와 CORS 설정이 필요합니다.

`src/api/visionGuardApi.js`의 함수는 Axios 응답의 `data`를 반환하고 오류는 그대로 전달합니다.
화면에서는 `getApiErrorMessage(error)`로 Problem Detail 또는 기본 오류 메시지를 표시합니다.

| 함수 | API |
| --- | --- |
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
대시보드·도면·히트맵은 아직 데모 데이터입니다. 프레임 입력/추출 UI는 구현되어 있지 않습니다.

분석 호출 시 이미지 한 장(최대 25 MiB)을 전달하고 같은 스트림은 이전 요청을 `await`한 뒤 다음 프레임을 전송하세요.
새 영상은 새 `streamId`를 생성하고, `capturedAt`은 촬영 시각, `fps`는 실제 전송 간격 기준으로 지정하세요.
재시도는 이미지 bytes와 모든 메타데이터를 유지해야 합니다. 마지막 요청 완료 후 `endStream`을 호출하고,
`endedAt`은 마지막 프레임의 `capturedAt` 이상이어야 합니다. 종료 재시도에도 같은 값을 사용하세요.
자동 재시도는 수행하지 않습니다. 실제 AI 추적기 reset은 서버 운영 측과 별도로 연동해야 합니다.

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
