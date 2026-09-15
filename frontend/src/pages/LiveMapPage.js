import { useState } from 'react';
import { Link } from 'react-router-dom';
import { FiAlertTriangle, FiCamera, FiRadio, FiTruck, FiUser, FiWifi } from 'react-icons/fi';
import useLatestAnalyses from '../hooks/useLatestAnalyses';
import { riskLevelLabels } from '../utils/riskEvent';
import './LiveMapPage.css';

const cctvs = [
  { id: 1, cameraId: 'camera-1', x: 25, y: 35, zone: 'ZONE_01' },
  { id: 2, cameraId: 'camera-2', x: 70, y: 35, zone: 'ZONE_02' },
];

const demoObjects = [
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
  const cameras = useLatestAnalyses();
  const priority = { SAFE: 0, WARNING: 1, DANGER: 2 };
  const risks = cameras.flatMap((camera) => (camera.analysis?.prediction.risks || []).map((risk) => ({ ...risk, cameraId: camera.id })));
  const highest = [...risks].sort((a, b) => priority[b.level] - priority[a.level] || b.score - a.score)[0];
  const objects = cameras.flatMap((camera) => (camera.analysis?.prediction.detections || []).map((object, index) => {
    const level = (camera.analysis.prediction.risks || []).filter((risk) => risk.person_index === index || risk.forklift_index === index).reduce((level, risk) => priority[risk.level] > priority[level] ? risk.level : level, 'SAFE');
    return { id: camera.id + ':' + object.class_name + ':' + (object.track_id ?? index),
      label: (object.class_name === 'person' ? 'W-' : 'F-') + (object.track_id ?? '미확정'),
      type: object.class_name === 'person' ? 'worker' : 'forklift', risk: level.toLowerCase(),
      location: camera.id + ' · 영상 좌표 (' + Math.round((object.bbox.x1 + object.bbox.x2) / 2) + ', ' + Math.round(object.bbox.y2) + ')',
    };
  }));
  const mapObjects = filter === 'all' ? demoObjects : filter === 'risk' ? demoObjects.filter((object) => object.risk !== 'safe') : demoObjects.filter((object) => object.type === filter);
  const visibleObjects = filter === 'all' ? objects : filter === 'risk' ? objects.filter((object) => object.risk !== 'safe') : objects.filter((object) => object.type === filter);
  const dangerPair = [{ id: highest?.person_track_id ?? '—' }, { id: highest?.forklift_track_id ?? '—' }];

  return (
    <div className="live-control">
      <header className="live-control__heading"><div><h1>실시간 도면 관제</h1></div><span><FiWifi /> 분석 연동</span></header>
      <div className="live-control__summary"><article><span>탐지 객체</span><strong>{objects.length}<small>개체</small></strong><p>지게차 {objects.filter((object) => object.type === 'forklift').length} · 작업자 {objects.filter((object) => object.type === 'worker').length}</p></article><article className="is-danger"><span>위험 근접 경보</span><strong>{risks.filter((risk) => risk.level !== 'SAFE').length}<small>건</small></strong><p>카메라별 최근 분석 기준</p></article></div>
      <section className="live-control__filters"><span>표시 항목</span>{[['all', '전체'], ['forklift', '지게차'], ['worker', '작업자'], ['risk', '위험 발생']].map(([key, label]) => <button className={filter === key ? 'is-active' : ''} key={key} onClick={() => setFilter(key)}>{label}</button>)}</section>

      <div className="live-control__layout">
        <section className="live-map-panel">
          <div className="live-map-panel__top"><span>FACILITY BLUEPRINT</span><b>도면 위치 예시</b></div>
          <div className="live-map">
            <FloorPlan />
            <div className="live-map__danger-zone"><FiAlertTriangle /><strong>충돌 위험</strong><span>예시 · 최근접 예상 시간 1.2초</span></div>
            {cctvs.map((camera) => <Link className="live-map__cctv" key={camera.id} to={`/?cctv=${camera.id}`} style={{ left: `${camera.x}%`, top: `${camera.y}%` }} title={`CCTV ${camera.id} 상세 화면으로 이동`}><FiCamera /><span>CAM-{String(camera.id).padStart(2, '0')}</span></Link>)}
            {mapObjects.map((object) => <button className={`live-map__object live-map__object--${object.type} live-map__object--${object.risk}`} key={object.id} style={{ left: `${object.x}%`, top: `${object.y}%` }} type="button" title={`${object.id} · ${riskLevelLabels[object.risk.toUpperCase()]}`}>{object.type === 'forklift' ? <FiTruck /> : <FiUser />}<span>{object.id}</span></button>)}
          </div>
          <div className="live-map__legend"><span><i className="forklift" />지게차</span><span><i className="worker" />작업자</span><span><i className="danger" />위험 발생</span><b>도면 위치는 예시 · 우측은 분석 결과</b></div>
        </section>

        <aside className="telemetry">
          <section className="telemetry__risk"><div className="telemetry__title"><strong><FiAlertTriangle /> 최고 위험 근접 쌍</strong><em>{highest?.level || '—'}</em></div><h2>{dangerPair[0].id} ↔ {dangerPair[1].id}<span>{highest ? highest.distance_px + ' px' : '—'}</span></h2><div className="telemetry__metrics"><div><span>현재 거리</span><b>{highest ? highest.distance_px + ' px' : '—'}</b></div><div><span>최근접 예상 시간</span><b>{highest?.time_to_closest_approach_s == null ? '—' : highest.time_to_closest_approach_s + '초'}</b></div></div><p>{highest ? highest.cameraId + ' · ' + highest.reason : '분석 결과 대기 중'}</p></section>
          <section className="telemetry__objects"><div className="telemetry__tabs"><b>전체 ({objects.length})</b><span>위험 ({objects.filter((item) => item.risk !== 'safe').length})</span></div>{visibleObjects.map((object) => <article className={`telemetry-object telemetry-object--${object.risk}`} key={object.id}><div><i />{object.type === 'forklift' ? <FiTruck /> : <FiUser />}<strong>{object.label}</strong><em>{riskLevelLabels[object.risk.toUpperCase()]}</em></div><p>{object.location}</p></article>)}</section>
          <div className="telemetry__notice">{cameras.map((camera) => <p key={camera.id} role="status">{camera.id}: {camera.loading ? '조회 중' : camera.error || (camera.stale ? '갱신 지연 · 마지막 분석 결과입니다.' : camera.analysis?.aiMode === 'mock' ? 'MOCK · 모의 분석' : '최근 분석')}</p>)}<FiRadio /> 경광등·사이렌 제어 미연동</div>
        </aside>
      </div>
    </div>
  );
}

export default LiveMapPage;
