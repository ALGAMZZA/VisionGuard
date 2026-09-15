import { Link, useSearchParams } from 'react-router-dom';
import { FiClock, FiMapPin, FiMaximize2, FiTruck, FiUser, FiVideo } from 'react-icons/fi';
import useLatestAnalyses from '../hooks/useLatestAnalyses';
import useRecentEvents from '../hooks/useRecentEvents';
import { formatDateTime, riskLevelLabels } from '../utils/riskEvent';
import './DashboardPage.css';

const cameraLayout = [
  { id: 1, name: 'CCTV 01', zone: 'ZONE A', location: '자재 적재 구역' },
  { id: 2, name: 'CCTV 02', zone: 'ZONE B', location: '제품 이동 통로' },
  { id: 3, name: 'CCTV 03', zone: 'DOCK C', location: '하역장' },
  { id: 4, name: 'CCTV 04', zone: 'LINE D', location: '생산 라인' },
];

function bindCamera(layout, state) {
  const prediction = state?.analysis?.prediction;
  const priority = { SAFE: 0, WARNING: 1, DANGER: 2 };
  const risk = [...(prediction?.risks || [])].sort((a, b) => priority[b.level] - priority[a.level] || b.score - a.score)[0];
  return { ...layout, ...state, id: layout.id, cameraId: state?.id,
    riskLevel: prediction?.overall_risk?.toLowerCase() || 'unknown',
    riskScore: risk?.score ?? '—',
    timeToCpa: risk?.time_to_closest_approach_s == null ? '—' : risk.time_to_closest_approach_s + '초',
    distance: risk?.distance_px == null ? '—' : risk.distance_px + ' px',
    workerId: risk?.person_track_id ?? '—', forkliftId: risk?.forklift_track_id ?? '—',
    box: risk ? prediction.detections[risk.forklift_index]?.bbox : null,
    imageWidth: prediction?.image_width, imageHeight: prediction?.image_height,
    status: !state ? '카메라 미설정' : state.loading ? '조회 중' : state.error || (state.stale ? '갱신 지연 · 마지막 분석 결과입니다.' : state.analysis?.aiMode === 'mock' ? 'MOCK · 모의 분석' : '최근 분석'),
  };
}

function StatusBadge({ camera }) {
  return <span className={`dashboard__status dashboard__status--${camera.riskLevel}`}><span />{riskLevelLabels[camera.riskLevel.toUpperCase()] || '미확인'}</span>;
}

function CameraFeed({ camera, large = false }) {
  return (
    <div className={`camera-feed camera-feed--${camera.id}${large ? ' camera-feed--large' : ''}`}>
      <div className="camera-feed__top">
        <div><strong>{camera.name}</strong><span>{camera.zone}</span></div>
        <span className="camera-feed__live">{camera.status}</span>
      </div>
      <div className="camera-feed__empty"><FiVideo /><span>영상 미연결</span></div>
      {camera.box && camera.imageWidth > 0 && camera.imageHeight > 0 && (
        <div className={`camera-feed__bounding-box camera-feed__bounding-box--${camera.riskLevel}`} style={{ left: `${camera.box.x1 / camera.imageWidth * 100}%`, top: `${camera.box.y1 / camera.imageHeight * 100}%`, width: `${(camera.box.x2 - camera.box.x1) / camera.imageWidth * 100}%`, height: `${(camera.box.y2 - camera.box.y1) / camera.imageHeight * 100}%` }}><span>지게차 · {camera.forkliftId}</span></div>
      )}
      <span className="camera-feed__expand"><FiMaximize2 /></span>
    </div>
  );
}

function CameraCard({ camera, onSelect }) {
  return (
    <article className="camera-card">
      <button className="camera-card__feed-button" type="button" onClick={onSelect}><CameraFeed camera={camera} /></button>
      <div className="camera-card__summary">
        <StatusBadge camera={camera} />
        <dl>
          <div><dt>최근접 예상 시간</dt><dd>{camera.timeToCpa}</dd></div>
          <div><dt>현재 거리</dt><dd>{camera.distance}</dd></div>
          <div><dt>최고 위험 객체</dt><dd>{camera.forkliftId} · {camera.workerId}</dd></div>
        </dl>
      </div>
    </article>
  );
}

function DetailPanel({ camera }) {
  const { events: recentAlerts, loading, error } = useRecentEvents(camera.cameraId);

  return (
    <aside className="camera-detail">
      <section className="camera-detail__section">
        <p className="camera-detail__eyebrow">위험 점수</p>
        <div className={`camera-detail__score camera-detail__score--${camera.riskLevel}`}><strong>{camera.riskScore}</strong><span>/ 100</span><StatusBadge camera={camera} /></div>
        <div className="camera-detail__gauge"><i style={{ width: `${Number(camera.riskScore) || 0}%` }} /></div>
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
          <div><dt>발생 위치</dt><dd>{camera.location}</dd></div><div><dt>위험 단계</dt><dd>{riskLevelLabels[camera.riskLevel.toUpperCase()] || '미확인'}</dd></div>
        </dl>
      </section>
      <section className="camera-detail__section camera-detail__alerts">
        <p className="camera-detail__eyebrow">알림 이력</p>
        {loading && <p role="status">이력 조회 중입니다.</p>}
        {error && <p role="alert">{error}</p>}
        {!loading && !error && !recentAlerts.length && <p>위험 이력이 없습니다.</p>}
        {recentAlerts.map((alert) => (
          <div className={`camera-detail__alert camera-detail__alert--${alert.level.toLowerCase()}`} key={alert.id}>
            <span><FiClock />{new Date(alert.capturedAt).toLocaleTimeString('ko-KR')}</span><div><strong><Link to={`/alerts?eventId=${alert.id}`}>{riskLevelLabels[alert.level]}</Link></strong><small>{alert.cameraId} · #{alert.id}</small></div>
          </div>
        ))}
      </section>
    </aside>
  );
}

function DashboardPage() {
  const states = useLatestAnalyses();
  const cameras = Array.from({ length: Math.max(4, states.length) }, (_, index) => bindCamera(cameraLayout[index] || { id: index + 1, name: 'CCTV ' + (index + 1), zone: '', location: '위치 미설정' }, states[index]));
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedCamera = Number(searchParams.get('cctv'));
  const activeTab = cameras.find((camera) => camera.cameraId && camera.cameraId === searchParams.get('cameraId'))?.id || (requestedCamera >= 1 && requestedCamera <= cameras.length ? requestedCamera : 'all');
  function setActiveTab(id) { setSearchParams(id === 'all' ? {} : { cctv: String(id) }); }
  const selectedCamera = cameras.find((camera) => camera.id === activeTab);
  return (
    <div className="dashboard">
      <div className="dashboard__heading">
        <div><h1>통합 관제 대시보드</h1></div>
        <span className="dashboard__connection"><i /> 분석 연동 · 영상 미연결</span>
      </div>
      <div className="dashboard__tabs" role="tablist">
        <button className={activeTab === 'all' ? 'is-active' : ''} onClick={() => setActiveTab('all')}>전체</button>
        {cameras.map((camera) => <button className={activeTab === camera.id ? 'is-active' : ''} key={camera.id} onClick={() => setActiveTab(camera.id)}>CCTV {camera.id}</button>)}
      </div>
      {activeTab === 'all' ? (
        <section className="dashboard__camera-grid">{cameras.map((camera) => <CameraCard camera={camera} key={camera.id} onSelect={() => setActiveTab(camera.id)} />)}</section>
      ) : (
        <section className="dashboard__single-view">
          <div className="dashboard__main-feed"><CameraFeed camera={selectedCamera} large /><div className="dashboard__feed-footer"><span><FiMapPin /> {selectedCamera.location}</span><span title={formatDateTime(selectedCamera.analysis?.capturedAt)}>Tracking: {selectedCamera.forkliftId}, {selectedCamera.workerId}</span></div></div>
          <DetailPanel camera={selectedCamera} />
        </section>
      )}
    </div>
  );
}

export default DashboardPage;
