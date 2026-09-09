import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { FiClock, FiMapPin, FiMaximize2, FiTruck, FiUser, FiVideo } from 'react-icons/fi';
import './DashboardPage.css';

const cameras = [
  { id: 1, name: 'CCTV 01', zone: 'ZONE A', location: '자재 적재 구역', risk: '위험', riskLevel: 'danger', riskScore: 72, ttc: '1.2초', distance: '0.7m', workerId: 'W-04', forkliftId: 'F-02' },
  { id: 2, name: 'CCTV 02', zone: 'ZONE B', location: '제품 이동 통로', risk: '주의', riskLevel: 'warning', riskScore: 45, ttc: '3.4초', distance: '1.8m', workerId: 'W-07', forkliftId: 'F-05' },
  { id: 3, name: 'CCTV 03', zone: 'DOCK C', location: '하역장', risk: '안전', riskLevel: 'safe', riskScore: 18, ttc: '8.7초', distance: '4.6m', workerId: 'W-01', forkliftId: 'F-08' },
  { id: 4, name: 'CCTV 04', zone: 'LINE D', location: '생산 라인', risk: '안전', riskLevel: 'safe', riskScore: 12, ttc: '12.1초', distance: '6.2m', workerId: 'W-11', forkliftId: 'F-03' },
];

const recentAlerts = [
  { time: '14:02:11', title: '근접 위험 경보', detail: 'F-02 · W-04 / ZONE A', level: 'danger' },
  { time: '13:41:45', title: '지게차 과속 감지', detail: 'F-01 / ZONE B', level: 'warning' },
  { time: '13:38:20', title: '안전 구역 이탈', detail: 'W-01 / DOCK C', level: 'normal' },
];

function StatusBadge({ camera }) {
  return <span className={`dashboard__status dashboard__status--${camera.riskLevel}`}><span />{camera.risk}</span>;
}

function CameraFeed({ camera, large = false }) {
  return (
    <div className={`camera-feed camera-feed--${camera.id}${large ? ' camera-feed--large' : ''}`}>
      <div className="camera-feed__top">
        <div><strong>{camera.name}</strong><span>{camera.zone}</span></div>
        <span className="camera-feed__live"><i /> LIVE</span>
      </div>
      <div className="camera-feed__empty"><FiVideo /><span>실시간 영상 연결 대기 중</span></div>
      {(camera.id === 1 || (large && camera.riskLevel !== 'safe')) && (
        <div className={`camera-feed__bounding-box camera-feed__bounding-box--${camera.riskLevel}`}><span>지게차 · {camera.forkliftId}</span></div>
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
          <div><dt>TTC</dt><dd>{camera.ttc}</dd></div>
          <div><dt>최소 거리</dt><dd>{camera.distance}</dd></div>
          <div><dt>최고 위험 객체</dt><dd>{camera.forkliftId} · {camera.workerId}</dd></div>
        </dl>
      </div>
    </article>
  );
}

function DetailPanel({ camera }) {
  return (
    <aside className="camera-detail">
      <section className="camera-detail__section">
        <p className="camera-detail__eyebrow">현재 종합 위험도</p>
        <div className={`camera-detail__score camera-detail__score--${camera.riskLevel}`}><strong>{camera.riskScore}</strong><span>%</span><StatusBadge camera={camera} /></div>
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
        <p className="camera-detail__eyebrow">실시간 객체 데이터</p>
        <dl className="camera-detail__metrics">
          <div><dt>최소 접근 거리</dt><dd>{camera.distance}</dd></div><div><dt>현재 TTC</dt><dd>{camera.ttc}</dd></div>
          <div><dt>발생 위치</dt><dd>{camera.location}</dd></div><div><dt>위험 단계</dt><dd>{camera.risk}</dd></div>
        </dl>
      </section>
      <section className="camera-detail__section camera-detail__alerts">
        <p className="camera-detail__eyebrow">최근 알림 이력</p>
        {recentAlerts.map((alert) => (
          <div className={`camera-detail__alert camera-detail__alert--${alert.level}`} key={alert.time}>
            <span><FiClock />{alert.time}</span><div><strong>{alert.title}</strong><small>{alert.detail}</small></div>
          </div>
        ))}
      </section>
    </aside>
  );
}

function DashboardPage() {
  const [searchParams] = useSearchParams();
  const requestedCamera = Number(searchParams.get('cctv'));
  const [activeTab, setActiveTab] = useState(requestedCamera >= 1 && requestedCamera <= 4 ? requestedCamera : 'all');
  const selectedCamera = cameras.find((camera) => camera.id === activeTab);
  return (
    <div className="dashboard">
      <div className="dashboard__heading">
        <div><h1>통합 관제 대시보드</h1></div>
        <span className="dashboard__connection"><i /> CCTV 4/4 ONLINE</span>
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
          <DetailPanel camera={selectedCamera} />
        </section>
      )}
    </div>
  );
}

export default DashboardPage;
