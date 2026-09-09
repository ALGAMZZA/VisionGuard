import { useState } from 'react';
import { Link } from 'react-router-dom';
import { FiAlertTriangle, FiCamera, FiRadio, FiTruck, FiUser, FiWifi } from 'react-icons/fi';
import { riskLevelLabels } from '../utils/riskEvent';
import './LiveMapPage.css';

const cctvs = [
  { id: 1, x: 15, y: 29, zone: 'ZONE A', status: 'demo' },
  { id: 2, x: 67, y: 24, zone: 'ZONE B', status: 'demo' },
  { id: 3, x: 20, y: 72, zone: 'DOCK C', status: 'demo' },
  { id: 4, x: 80, y: 69, zone: 'LINE D', status: 'demo' },
];

const objects = [
  { id: 'F-02', type: 'forklift', x: 47, y: 48, location: 'B구역 교차로', risk: 'danger' },
  { id: 'W-04', type: 'worker', x: 52, y: 55, location: 'B구역 통로', risk: 'danger' },
  { id: 'F-01', type: 'forklift', x: 72, y: 68, location: 'D구역 도크', risk: 'safe' },
  { id: 'W-02', type: 'worker', x: 21, y: 59, location: 'A구역 라인 1', risk: 'safe' },
  { id: 'F-03', type: 'forklift', x: 64, y: 37, location: 'C구역 자재장', risk: 'warning' },
  { id: 'W-01', type: 'worker', x: 18, y: 31, location: 'A구역 검사실', risk: 'safe' },
];

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
  const dangerPair = objects.slice(0, 2);

  return (
    <div className="live-control">
      <header className="live-control__heading"><div><h1>실시간 도면 관제</h1><p>데모 화면 · 위치와 위험 정보는 예시이며 실시간 데이터가 아닙니다.</p></div><span><FiWifi /> DEMO</span></header>
      <div className="live-control__summary"><article><span>예시 위치 객체</span><strong>{objects.length}<small>개체</small></strong><p>지게차 {objects.filter((object) => object.type === 'forklift').length} · 작업자 {objects.filter((object) => object.type === 'worker').length}</p></article><article className="is-danger"><span>위험 근접 경보</span><strong>1<small>건 예시</small></strong><p>예시 근접 위험 상황입니다</p></article></div>
      <section className="live-control__filters"><span>표시 항목</span>{[['all', '전체'], ['forklift', '지게차'], ['worker', '작업자'], ['risk', '위험 발생']].map(([key, label]) => <button className={filter === key ? 'is-active' : ''} key={key} onClick={() => setFilter(key)}>{label}</button>)}</section>

      <div className="live-control__layout">
        <section className="live-map-panel">
          <div className="live-map-panel__top"><span>FACILITY BLUEPRINT · DEMO</span><b>실시간 연동 예정</b></div>
          <div className="live-map">
            <FloorPlan />
            <div className="live-map__danger-zone"><FiAlertTriangle /><strong>충돌 위험</strong><span>최근접 예상 시간 1.2초</span></div>
            {cctvs.map((camera) => <Link className="live-map__cctv" key={camera.id} to={`/?cctv=${camera.id}`} style={{ left: `${camera.x}%`, top: `${camera.y}%` }} title={`CCTV ${camera.id} 상세 화면으로 이동`}><FiCamera /><span>CAM-{String(camera.id).padStart(2, '0')}</span></Link>)}
            {visibleObjects.map((object) => <button className={`live-map__object live-map__object--${object.type} live-map__object--${object.risk}`} key={object.id} style={{ left: `${object.x}%`, top: `${object.y}%` }} type="button" title={`${object.id} · ${riskLevelLabels[object.risk.toUpperCase()]}`}>{object.type === 'forklift' ? <FiTruck /> : <FiUser />}<span>{object.id}</span></button>)}
          </div>
          <div className="live-map__legend"><span><i className="forklift" />지게차</span><span><i className="worker" />작업자</span><span><i className="danger" />위험 발생</span><b>고정 예시 데이터</b></div>
        </section>

        <aside className="telemetry">
          <section className="telemetry__risk"><div className="telemetry__title"><strong><FiAlertTriangle /> 최고 위험 근접 쌍</strong><em>DANGER</em></div><h2>{dangerPair[0].id} ↔ {dangerPair[1].id}<span>70 px</span></h2><div className="telemetry__metrics"><div><span>현재 거리 (예시)</span><b>70 px</b></div><div><span>최근접 예상 시간</span><b>1.2초</b></div></div><p>거리와 시간은 예시입니다.</p></section>
          <section className="telemetry__objects"><div className="telemetry__tabs"><b>전체 ({objects.length})</b><span>위험 ({objects.filter((item) => item.risk !== 'safe').length})</span></div>{visibleObjects.map((object) => <article className={`telemetry-object telemetry-object--${object.risk}`} key={object.id}><div><i />{object.type === 'forklift' ? <FiTruck /> : <FiUser />}<strong>{object.id}</strong><em>{riskLevelLabels[object.risk.toUpperCase()]}</em></div><p>예시 위치: {object.location}</p></article>)}</section>
          <div className="telemetry__notice"><FiRadio /> 경광등·사이렌 제어 미연동</div>
        </aside>
      </div>
    </div>
  );
}

export default LiveMapPage;
