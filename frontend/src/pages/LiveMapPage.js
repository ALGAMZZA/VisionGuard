import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiAlertTriangle, FiCamera, FiRadio, FiTruck, FiUser, FiWifi } from 'react-icons/fi';
import { riskLevelLabels } from '../utils/riskEvent';
import { getLatestAnalysis } from '../api/visionGuardApi';
import './LiveMapPage.css';

const cctvs = [
  { id: 1, cameraId: 'camera-1', x: 25, y: 35, zone: 'ZONE_01' },
  { id: 2, cameraId: 'camera-2', x: 70, y: 35, zone: 'ZONE_02' },
];

const riskRank = { safe: 0, warning: 1, danger: 2 };

function objectsFromAnalyses(analyses) {
  return Object.values(analyses).flatMap((analysis) => {
    const prediction = analysis?.prediction || {};
    const width = Number(prediction.image_width) || 1;
    const height = Number(prediction.image_height) || 1;
    const risks = Array.isArray(prediction.risks) ? prediction.risks : [];
    return (prediction.detections || []).map((detection, index) => {
      const type = detection.class_name === 'forklift' ? 'forklift' : 'worker';
      const trackId = detection.track_id;
      const related = risks.filter((risk) => type === 'forklift'
        ? risk.forklift_track_id === trackId : risk.person_track_id === trackId);
      const highest = related.reduce((best, risk) => (
        !best || riskRank[String(risk.level).toLowerCase()] > riskRank[String(best.level).toLowerCase()] ? risk : best
      ), null);
      const bbox = detection.bbox || {};
      return {
        id: `${type === 'forklift' ? 'F' : 'W'}-${trackId ?? index + 1}`,
        type,
        x: Math.max(3, Math.min(97, ((Number(bbox.x1) + Number(bbox.x2)) / 2 / width) * 100)),
        y: Math.max(5, Math.min(95, (Number(bbox.y2) / height) * 100)),
        location: analysis.cameraId,
        risk: String(highest?.level || 'SAFE').toLowerCase(),
      };
    });
  });
}

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
  const [analyses, setAnalyses] = useState({});
  const [connected, setConnected] = useState(false);
  useEffect(() => {
    let active = true;
    async function refresh() {
      const results = await Promise.allSettled(cctvs.map((camera) => getLatestAnalysis(camera.cameraId)));
      if (!active) return;
      const next = {};
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') next[cctvs[index].cameraId] = result.value;
      });
      setAnalyses(next);
      setConnected(results.some((result) => result.status === 'fulfilled'));
    }
    refresh();
    const timer = window.setInterval(refresh, 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);
  const objects = useMemo(() => objectsFromAnalyses(analyses), [analyses]);
  const visibleObjects = filter === 'all' ? objects : filter === 'risk' ? objects.filter((object) => object.risk !== 'safe') : objects.filter((object) => object.type === filter);
  const risks = Object.values(analyses).flatMap((analysis) => analysis.prediction?.risks || []);
  const highestRisk = risks.reduce((best, risk) => !best || Number(risk.score) > Number(best.score) ? risk : best, null);
  const dangerPair = highestRisk ? [`F-${highestRisk.forklift_track_id ?? '—'}`, `W-${highestRisk.person_track_id ?? '—'}`] : ['—', '—'];
  const highestLevel = String(highestRisk?.level || 'SAFE').toLowerCase();

  return (
    <div className="live-control">
      <header className="live-control__heading"><div><h1>실시간 도면 관제</h1></div><span><FiWifi /> {connected ? 'LIVE' : '연결 대기'}</span></header>
      <div className="live-control__summary"><article><span>현재 탐지 객체</span><strong>{objects.length}<small>개체</small></strong><p>지게차 {objects.filter((object) => object.type === 'forklift').length} · 작업자 {objects.filter((object) => object.type === 'worker').length}</p></article><article className={highestLevel === 'danger' ? 'is-danger' : ''}><span>위험 근접 객체</span><strong>{objects.filter((object) => object.risk !== 'safe').length}<small>개체</small></strong><p>{highestRisk ? `최고 위험 점수 ${Math.round(highestRisk.score)}점` : '현재 위험 객체가 없습니다'}</p></article></div>
      <section className="live-control__filters"><span>표시 항목</span>{[['all', '전체'], ['forklift', '지게차'], ['worker', '작업자'], ['risk', '위험 발생']].map(([key, label]) => <button className={filter === key ? 'is-active' : ''} key={key} onClick={() => setFilter(key)}>{label}</button>)}</section>

      <div className="live-control__layout">
        <section className="live-map-panel">
          <div className="live-map-panel__top"><span>FACILITY BLUEPRINT</span><b>실시간 연동</b></div>
          <div className="live-map">
            <FloorPlan />
            {highestRisk && <div className="live-map__danger-zone"><FiAlertTriangle /><strong>{riskLevelLabels[String(highestRisk.level)]}</strong><span>최근접 예상 시간 {highestRisk.time_to_closest_approach_s == null ? '—' : `${highestRisk.time_to_closest_approach_s.toFixed(1)}초`}</span></div>}
            {cctvs.map((camera) => <Link className="live-map__cctv" key={camera.id} to={`/?cctv=${camera.id}`} style={{ left: `${camera.x}%`, top: `${camera.y}%` }} title={`CCTV ${camera.id} 상세 화면으로 이동`}><FiCamera /><span>CAM-{String(camera.id).padStart(2, '0')}</span></Link>)}
            {visibleObjects.map((object) => <button className={`live-map__object live-map__object--${object.type} live-map__object--${object.risk}`} key={object.id} style={{ left: `${object.x}%`, top: `${object.y}%` }} type="button" title={`${object.id} · ${riskLevelLabels[object.risk.toUpperCase()]}`}>{object.type === 'forklift' ? <FiTruck /> : <FiUser />}<span>{object.id}</span></button>)}
          </div>
          <div className="live-map__legend"><span><i className="forklift" />지게차</span><span><i className="worker" />작업자</span><span><i className="danger" />위험 발생</span><b>{connected ? 'Backend 실시간 데이터' : '데이터 연결 대기'}</b></div>
        </section>

        <aside className="telemetry">
          <section className="telemetry__risk"><div className="telemetry__title"><strong><FiAlertTriangle /> 최고 위험 근접 쌍</strong><em>{highestRisk?.level || 'SAFE'}</em></div><h2>{dangerPair[0]} ↔ {dangerPair[1]}<span>{highestRisk ? `${Math.round(highestRisk.score)}점` : '—'}</span></h2><div className="telemetry__metrics"><div><span>현재 거리</span><b>{highestRisk ? `${Math.round(highestRisk.distance_px)} px` : '—'}</b></div><div><span>최근접 예상 시간</span><b>{highestRisk?.time_to_closest_approach_s == null ? '—' : `${highestRisk.time_to_closest_approach_s.toFixed(1)}초`}</b></div></div><p>{highestRisk?.reason || '현재 위험 쌍이 없습니다.'}</p></section>
          <section className="telemetry__objects"><div className="telemetry__tabs"><b>전체 ({objects.length})</b><span>위험 ({objects.filter((item) => item.risk !== 'safe').length})</span></div>{visibleObjects.map((object) => <article className={`telemetry-object telemetry-object--${object.risk}`} key={object.id}><div><i />{object.type === 'forklift' ? <FiTruck /> : <FiUser />}<strong>{object.id}</strong><em>{riskLevelLabels[object.risk.toUpperCase()]}</em></div><p>예시 위치: {object.location}</p></article>)}</section>
          <div className="telemetry__notice"><FiRadio /> 객체 위치는 CCTV 화면 좌표 기준</div>
        </aside>
      </div>
    </div>
  );
}

export default LiveMapPage;
