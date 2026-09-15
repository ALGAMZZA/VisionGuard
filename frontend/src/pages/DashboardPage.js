import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { FiClock, FiMapPin, FiMaximize2, FiTruck, FiUser, FiVideo } from 'react-icons/fi';
import useLatestAnalyses from '../hooks/useLatestAnalyses';
import useRecentEvents from '../hooks/useRecentEvents';
import { riskLevelLabels } from '../utils/riskEvent';
import { getUnityGroundTruth, verifiedDetections } from '../utils/unityGroundTruth';
import './DashboardPage.css';

const cameraDefinitions = [
  { id: 1, cameraId: 'camera-1', name: 'CCTV 01', zone: 'ZONE_01', location: '자재 적재 구역', snapshotUrl: 'http://127.0.0.1:8080/snapshot.jpg', groundTruthUrl: 'http://127.0.0.1:8080/ground-truth.json' },
  { id: 2, cameraId: 'camera-2', name: 'CCTV 02', zone: 'ZONE_02', location: '제품 이동 통로', snapshotUrl: 'http://127.0.0.1:8081/snapshot.jpg', groundTruthUrl: 'http://127.0.0.1:8081/ground-truth.json' },
  { id: 3, cameraId: 'camera-3', name: 'CCTV 03', zone: 'ZONE_03', location: '창고 통로 구역', snapshotUrl: 'http://127.0.0.1:8083/snapshot.jpg', groundTruthUrl: 'http://127.0.0.1:8083/ground-truth.json' },
  { id: 4, cameraId: 'camera-4', name: 'CCTV 04', zone: 'ZONE_04', location: '적재 작업 구역', snapshotUrl: 'http://127.0.0.1:8084/snapshot.jpg', groundTruthUrl: 'http://127.0.0.1:8084/ground-truth.json' },
];

const emptyCamera = (definition) => ({
  ...definition,
  riskLevel: 'safe',
  riskScore: 0,
  timeToCpa: '—',
  distance: '—',
  workerId: '—',
  forkliftId: '—',
  prediction: null,
});

function formatTrackId(prefix, value) {
  return value === null || value === undefined ? '—' : `${prefix}-${value}`;
}

function cameraFromAnalysis(definition, analysis) {
  const prediction = analysis?.prediction || {};
  const risks = Array.isArray(prediction.risks) ? prediction.risks : [];
  const detections = Array.isArray(prediction.detections) ? prediction.detections : [];
  const highestRisk = risks.reduce((highest, risk) => (
    !highest || Number(risk.score || 0) > Number(highest.score || 0) ? risk : highest
  ), null);
  const person = detections.find((item) => item.class_name === 'person');
  const forklift = detections.find((item) => item.class_name === 'forklift');
  const level = String(prediction.overall_risk || highestRisk?.level || 'SAFE').toLowerCase();
  const timeToCpa = highestRisk?.time_to_closest_approach_s;
  const distance = highestRisk?.distance_px;

  return {
    ...definition,
    riskLevel: ['safe', 'warning', 'danger'].includes(level) ? level : 'safe',
    riskScore: Math.max(0, Math.min(100, Math.round(Number(highestRisk?.score || 0)))),
    timeToCpa: Number.isFinite(timeToCpa) ? `${timeToCpa.toFixed(1)}초` : '—',
    distance: Number.isFinite(distance) ? `${Math.round(distance)} px` : '—',
    workerId: formatTrackId('W', highestRisk?.person_track_id ?? person?.track_id),
    forkliftId: formatTrackId('F', highestRisk?.forklift_track_id ?? forklift?.track_id),
    prediction,
  };
}

function alertFromEvent(event) {
  const capturedAt = event.capturedAt ? new Date(event.capturedAt) : null;
  const level = String(event.level || 'WARNING').toLowerCase();
  return {
    id: event.id,
    time: capturedAt && !Number.isNaN(capturedAt.valueOf())
      ? capturedAt.toLocaleTimeString('ko-KR', { hour12: false })
      : '—',
    title: level === 'danger' ? '근접 위험 경보' : '근접 위험 경고',
    detail: `${formatTrackId('F', event.forkliftTrackId)} · ${formatTrackId('W', event.personTrackId)} / ${event.cameraId || '—'}`,
    level: level === 'danger' ? 'danger' : 'warning',
  };
}

function StatusBadge({ camera }) {
  return <span className={`dashboard__status dashboard__status--${camera.riskLevel}`}><span />{riskLevelLabels[camera.riskLevel.toUpperCase()]}</span>;
}

function CameraFeed({ camera, large = false }) {
  const [imageAvailable, setImageAvailable] = useState(true);
  const [imageVersion, setImageVersion] = useState(Date.now());
  const [groundTruth, setGroundTruth] = useState(null);

  useEffect(() => {
    if (!camera.snapshotUrl) return undefined;
    const timer = window.setInterval(() => setImageVersion(Date.now()), 1500);
    return () => window.clearInterval(timer);
  }, [camera.snapshotUrl]);

  useEffect(() => {
    if (!camera.groundTruthUrl) return undefined;
    let active = true;
    setGroundTruth(null);
    async function refreshGroundTruth() {
      try {
        const value = await getUnityGroundTruth(camera.groundTruthUrl);
        if (active) setGroundTruth(value);
      } catch (_) {
        if (active) setGroundTruth(null);
      }
    }
    refreshGroundTruth();
    const timer = window.setInterval(refreshGroundTruth, 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, [camera.groundTruthUrl]);

  return (
    <div className={`camera-feed camera-feed--${camera.id}${large ? ' camera-feed--large' : ''}`}>
      {camera.snapshotUrl && (
        <img
          className="camera-feed__image"
          src={`${camera.snapshotUrl}?t=${imageVersion}`}
          alt={`${camera.name} 실시간 영상`}
          onLoad={() => setImageAvailable(true)}
          onError={() => setImageAvailable(false)}
        />
      )}
      {imageAvailable && camera.prediction && groundTruth && (
        <DetectionOverlay prediction={camera.prediction} groundTruth={groundTruth} />
      )}
      <div className="camera-feed__top">
        <div><strong>{camera.name}</strong><span>{camera.zone}</span></div>
        <span className="camera-feed__live"><i /> LIVE</span>
      </div>
      {(!camera.snapshotUrl || !imageAvailable) && <div className="camera-feed__empty"><FiVideo /><span>영상 연결 대기 중</span></div>}
      <span className="camera-feed__expand"><FiMaximize2 /></span>
    </div>
  );
}

function DetectionOverlay({ prediction, groundTruth }) {
  const width = Number(prediction.image_width) || 1280;
  const height = Number(prediction.image_height) || 720;
  const detections = verifiedDetections(prediction, groundTruth);

  return (
    <svg className="camera-feed__detections" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      {detections.map((detection, index) => {
        const box = detection.bbox || {};
        const x = Math.max(0, Number(box.x1) || 0);
        const y = Math.max(0, Number(box.y1) || 0);
        const boxWidth = Math.max(0, (Number(box.x2) || 0) - x);
        const boxHeight = Math.max(0, (Number(box.y2) || 0) - y);
        const type = detection.class_name;
        const label = `${type} ${detection.object_id || `#${detection.track_id ?? index + 1}`} ${Math.round(Number(detection.confidence || 0) * 100)}%`;
        return (
          <g className={`camera-feed__detection camera-feed__detection--${type}`} key={`${type}-${detection.track_id ?? index}`}>
            <rect x={x} y={y} width={boxWidth} height={boxHeight} />
            <text x={x + 4} y={Math.max(16, y - 5)}>{label}</text>
          </g>
        );
      })}
    </svg>
  );
}

function CameraCard({ camera, onSelect }) {
  return (
    <article className="camera-card">
      <button className="camera-card__feed-button" type="button" onClick={onSelect}><CameraFeed camera={camera} /></button>
      <div className="camera-card__summary">
        <StatusBadge camera={camera} />
        <dl>
          <div><dt>위험 점수</dt><dd>{camera.riskScore} / 100</dd></div>
          <div><dt>최근접 예상 시간</dt><dd>{camera.timeToCpa}</dd></div>
          <div><dt>현재 거리</dt><dd>{camera.distance}</dd></div>
          <div><dt>최고 위험 객체</dt><dd>{camera.forkliftId} · {camera.workerId}</dd></div>
        </dl>
      </div>
    </article>
  );
}

function DetailPanel({ camera, recentAlerts }) {
  return (
    <aside className="camera-detail">
      <section className="camera-detail__section">
        <p className="camera-detail__eyebrow">위험 점수</p>
        <div className={`camera-detail__score camera-detail__score--${camera.riskLevel}`}><strong>{camera.riskScore}</strong><span>/ 100</span><StatusBadge camera={camera} /></div>
        <div className="camera-detail__gauge"><i style={{ width: `${camera.riskScore}%` }} /></div>
      </section>
      <section className="camera-detail__section">
        <p className="camera-detail__eyebrow">최고 위험 객체</p>
        <div className="camera-detail__objects">
          <div><FiTruck /><span>지게차<strong>{camera.forkliftId}</strong></span></div>
          <b>{camera.distance}</b>
          <div><FiUser /><span>작업자<strong>{camera.workerId}</strong></span></div>
        </div>
      </section>
      <section className="camera-detail__section">
        <p className="camera-detail__eyebrow">객체 데이터</p>
        <dl className="camera-detail__metrics">
          <div><dt>현재 거리</dt><dd>{camera.distance}</dd></div><div><dt>최근접 예상 시간</dt><dd>{camera.timeToCpa}</dd></div>
          <div><dt>발생 위치</dt><dd>{camera.location}</dd></div><div><dt>위험 단계</dt><dd>{riskLevelLabels[camera.riskLevel.toUpperCase()]}</dd></div>
        </dl>
      </section>
      <section className="camera-detail__section camera-detail__alerts">
        <p className="camera-detail__eyebrow">알림 이력</p>
        {recentAlerts.map((alert) => (
          <div className={`camera-detail__alert camera-detail__alert--${alert.level}`} key={alert.id || `${alert.time}-${alert.detail}`}>
            <span><FiClock />{alert.time}</span><div><strong>{alert.title}</strong><small>{alert.detail}</small></div>
          </div>
        ))}
      </section>
    </aside>
  );
}

function DashboardPage() {
  const analysisStates = useLatestAnalyses();
  const [searchParams] = useSearchParams();
  const requestedCamera = Number(searchParams.get('cctv'));
  const [activeTab, setActiveTab] = useState(requestedCamera >= 1 && requestedCamera <= 4 ? requestedCamera : 'all');
  const cameras = useMemo(() => cameraDefinitions.map((definition) => (
    analysisStates.find((state) => state.id === definition.cameraId)?.analysis
      ? cameraFromAnalysis(definition, analysisStates.find((state) => state.id === definition.cameraId).analysis)
      : emptyCamera(definition)
  )), [analysisStates]);
  const selectedCamera = cameras.find((camera) => camera.id === activeTab);
  const recentEventState = useRecentEvents(selectedCamera?.cameraId);
  const recentAlerts = (recentEventState.events || []).slice(0, 3).map(alertFromEvent);
  const backendConnected = analysisStates.some((state) => state.analysis || state.error);

  return (
    <div className="dashboard">
      <div className="dashboard__heading">
        <div><h1>통합 관제 대시보드</h1></div>
        <span className="dashboard__connection"><i /> {backendConnected ? 'LIVE · 서버 연결됨' : '서버 연결 대기 중'}</span>
      </div>
      <div className="dashboard__tabs" role="tablist">
        <button className={activeTab === 'all' ? 'is-active' : ''} onClick={() => setActiveTab('all')}>전체</button>
        {cameras.map((camera) => <button className={activeTab === camera.id ? 'is-active' : ''} key={camera.id} onClick={() => setActiveTab(camera.id)}>CCTV {camera.id}</button>)}
      </div>
      {activeTab === 'all' ? (
        <section className="dashboard__camera-grid">{cameras.map((camera) => <CameraCard camera={camera} key={camera.id} onSelect={() => setActiveTab(camera.id)} />)}</section>
      ) : (
        <section className="dashboard__single-view">
          <div className="dashboard__main-feed"><CameraFeed camera={selectedCamera} large /><div className="dashboard__feed-footer"><span><FiMapPin /> {selectedCamera.location}</span><span>Tracking: {selectedCamera.forkliftId}, {selectedCamera.workerId}</span></div></div>
          <DetailPanel camera={selectedCamera} recentAlerts={recentAlerts} />
        </section>
      )}
    </div>
  );
}

export default DashboardPage;
