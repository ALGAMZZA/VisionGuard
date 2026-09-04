import { useState } from 'react';
import { Link } from 'react-router-dom';
import { FiAlertTriangle, FiCamera, FiRadio, FiTruck, FiUser, FiWifi } from 'react-icons/fi';
import './LiveMapPage.css';

const cctvs = [
  { id: 1, x: 15, y: 29, zone: 'ZONE A', status: 'online' },
  { id: 2, x: 67, y: 24, zone: 'ZONE B', status: 'online' },
  { id: 3, x: 20, y: 72, zone: 'DOCK C', status: 'online' },
  { id: 4, x: 80, y: 69, zone: 'LINE D', status: 'online' },
];

const objects = [
  { id: 'F-02', type: 'forklift', x: 47, y: 48, speed: '14.2 km/h', location: 'B구역 교차로', risk: 'critical', battery: 99 },
  { id: 'W-04', type: 'worker', x: 52, y: 55, speed: '1.1 m/s', location: 'B구역 통로', risk: 'critical', battery: 88 },
  { id: 'F-01', type: 'forklift', x: 72, y: 68, speed: '6.0 km/h', location: 'D구역 도크', risk: 'safe', battery: 84 },
  { id: 'W-02', type: 'worker', x: 21, y: 59, speed: '0.8 m/s', location: 'A구역 라인 1', risk: 'safe', battery: 92 },
  { id: 'F-03', type: 'forklift', x: 64, y: 37, speed: '6.5 km/h', location: 'C구역 자재장', risk: 'warning', battery: 61 },
  { id: 'W-01', type: 'worker', x: 18, y: 31, speed: '0.4 m/s', location: 'A구역 검사실', risk: 'safe', battery: 95 },
];

const riskLabels = { critical: '고위험', warning: '주의', safe: '안전' };

function FloorPlan() {
  return (
    <svg className="live-map__blueprint" viewBox="0 0 900 560" aria-label="실시간 공장 도면">
      <g className="live-map__walls"><rect x="25" y="25" width="850" height="510" /><path d="M210 25v165H25M210 125h220V25M430 25v260M25 285h405M430 190h220V25M650 25v510M430 370h220M25 425h230v110M255 285v250M650 335h225M765 190v145" /></g>
      <g className="live-map__equipment"><rect x="55" y="60" width="120" height="45" /><rect x="55" y="125" width="120" height="38" /><rect x="250" y="55" width="135" height="70" /><rect x="250" y="150" width="135" height="90" /><rect x="470" y="55" width="135" height="45" /><rect x="470" y="125" width="135" height="45" /><rect x="690" y="55" width="145" height="90" /><rect x="690" y="220" width="55" height="75" /><rect x="785" y="220" width="50" height="75" /><rect x="690" y="390" width="145" height="95" /><path d="M55 330h150v52H55zM290 325h95v155h-95zM470 420h135v60H470z" /></g>
      <g className="live-map__zone-labels"><text x="48" y="48">ZONE A · ASSEMBLY</text><text x="235" y="48">ZONE B · TRANSIT AISLE</text><text x="455" y="48">ZONE C · STORAGE</text><text x="680" y="48">ZONE D · LOADING</text></g>
    </svg>
  );
}

function LiveMapPage() {
  const [filter, setFilter] = useState('all');
  const visibleObjects = filter === 'all' ? objects : filter === 'risk' ? objects.filter((object) => object.risk !== 'safe') : objects.filter((object) => object.type === filter);
  const criticalPair = objects.slice(0, 2);

  return (
    <div className="live-control">
      <header className="live-control__heading"><div><h1>실시간 도면 관제</h1><p>공장 내 CCTV 및 이동 객체 실시간 위치 추적</p></div><span><FiWifi /> LIVE TELEMETRY</span></header>
      <div className="live-control__summary"><article><span>실시간 위치 객체</span><strong>{objects.length + 16}<small>개체</small></strong><p>지게차 4 · 작업자 18</p></article><article className="is-danger"><span>위험 근접 경보</span><strong>1<small>건 감지</small></strong><p>즉시 확인이 필요합니다</p></article></div>
      <section className="live-control__filters"><span>표시 항목</span>{[['all', '전체'], ['forklift', '지게차'], ['worker', '작업자'], ['risk', '위험 발생']].map(([key, label]) => <button className={filter === key ? 'is-active' : ''} key={key} onClick={() => setFilter(key)}>{label}</button>)}</section>

      <div className="live-control__layout">
        <section className="live-map-panel">
          <div className="live-map-panel__top"><span>FACILITY BLUEPRINT · REAL-TIME</span><b>SYNC 16/16 LOCKED</b></div>
          <div className="live-map">
            <FloorPlan />
            <div className="live-map__danger-zone"><FiAlertTriangle /><strong>충돌 위험</strong><span>TTC 1.2초</span></div>
            {cctvs.map((camera) => <Link className="live-map__cctv" key={camera.id} to={`/?cctv=${camera.id}`} style={{ left: `${camera.x}%`, top: `${camera.y}%` }} title={`CCTV ${camera.id} 상세 화면으로 이동`}><FiCamera /><span>CAM-{String(camera.id).padStart(2, '0')}</span></Link>)}
            {visibleObjects.map((object) => <button className={`live-map__object live-map__object--${object.type} live-map__object--${object.risk}`} key={object.id} style={{ left: `${object.x}%`, top: `${object.y}%` }} type="button" title={`${object.id} · ${riskLabels[object.risk]}`}>{object.type === 'forklift' ? <FiTruck /> : <FiUser />}<span>{object.id}</span></button>)}
          </div>
          <div className="live-map__legend"><span><i className="forklift" />지게차</span><span><i className="worker" />작업자</span><span><i className="danger" />위험 발생</span><b>업데이트: 0.05초</b></div>
        </section>

        <aside className="telemetry">
          <section className="telemetry__risk"><div className="telemetry__title"><strong><FiAlertTriangle /> 최고 위험 근접 쌍</strong><em>CRITICAL</em></div><h2>{criticalPair[0].id} ↔ {criticalPair[1].id}<span>0.7m</span></h2><div className="telemetry__metrics"><div><span>상대 속도</span><b>14.2 km/h</b></div><div><span>충돌 예상 (TTC)</span><b>1.2초</b></div></div><p>비상 감속 판단 송신 완료</p></section>
          <section className="telemetry__objects"><div className="telemetry__tabs"><b>전체 ({objects.length})</b><span>위험 ({objects.filter((item) => item.risk !== 'safe').length})</span></div>{visibleObjects.map((object) => <article className={`telemetry-object telemetry-object--${object.risk}`} key={object.id}><div><i />{object.type === 'forklift' ? <FiTruck /> : <FiUser />}<strong>{object.id}</strong><em>{riskLabels[object.risk]}</em></div><p>속도: <b>{object.speed}</b><span>위치: {object.location}</span></p><small>배터리 {object.battery}%</small></article>)}</section>
          <div className="telemetry__notice"><FiRadio /> B구역 비상 경광등 및 사이렌 감지 구동</div>
        </aside>
      </div>
    </div>
  );
}

export default LiveMapPage;
