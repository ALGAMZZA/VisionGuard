import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiAlertTriangle, FiCamera, FiRadio, FiTruck, FiUser, FiWifi } from 'react-icons/fi';
import useLatestAnalyses from '../hooks/useLatestAnalyses';
import { riskLevelLabels } from '../utils/riskEvent';
import { getUnityGroundTruth, verifiedDetections } from '../utils/unityGroundTruth';
import './LiveMapPage.css';

const cctvs = [
  { id: 1, cameraId: 'camera-1', x: 8, y: 9, zone: 'ZONE_01', groundTruthUrl: 'http://127.0.0.1:8080/ground-truth.json', bounds: { left: 4, top: 5, width: 44, height: 42 } },
  { id: 2, cameraId: 'camera-2', x: 57, y: 9, zone: 'ZONE_02', groundTruthUrl: 'http://127.0.0.1:8081/ground-truth.json', bounds: { left: 52, top: 5, width: 44, height: 42 } },
  { id: 3, cameraId: 'camera-3', x: 8, y: 56, zone: 'ZONE_03', groundTruthUrl: 'http://127.0.0.1:8083/ground-truth.json', bounds: { left: 4, top: 53, width: 44, height: 42 } },
  { id: 4, cameraId: 'camera-4', x: 57, y: 56, zone: 'ZONE_04', groundTruthUrl: 'http://127.0.0.1:8084/ground-truth.json', bounds: { left: 52, top: 53, width: 44, height: 42 } },
];

const riskRank = { safe: 0, warning: 1, danger: 2 };

function objectsFromAnalyses(analyses, groundTruths) {
  return Object.values(analyses).flatMap((analysis) => {
    const prediction = analysis?.prediction || {};
    const risks = Array.isArray(prediction.risks) ? prediction.risks : [];
    const camera = cctvs.find((item) => item.cameraId === analysis.cameraId);
    if (!camera) return [];
    return verifiedDetections(prediction, groundTruths[analysis.cameraId]).map((detection, index) => {
      const type = detection.class_name === 'forklift' ? 'forklift' : 'worker';
      const trackId = detection.track_id;
      const related = risks.filter((risk) => type === 'forklift'
        ? risk.forklift_track_id === trackId : risk.person_track_id === trackId);
      const highest = related.reduce((best, risk) => (
        !best || riskRank[String(risk.level).toLowerCase()] > riskRank[String(best.level).toLowerCase()] ? risk : best
      ), null);
      const position = detection.local_position || {};
      const normalizedX = Math.max(0, Math.min(1, (Number(position.x) + 16) / 32));
      const normalizedY = Math.max(0, Math.min(1, (14 - Number(position.z)) / 26));
      return {
        id: `${camera.cameraId}-${type === 'forklift' ? 'F' : 'W'}-${trackId ?? index + 1}`,
        label: `${type === 'forklift' ? 'F' : 'W'}-${trackId ?? index + 1}`,
        type,
        x: camera.bounds.left + normalizedX * camera.bounds.width,
        y: camera.bounds.top + normalizedY * camera.bounds.height,
        location: `${camera.zone} · ${camera.cameraId}`,
        risk: String(highest?.level || 'SAFE').toLowerCase(),
      };
    });
  });
}

function FloorPlan() {
  return (
    <svg className="live-map__blueprint" viewBox="0 0 900 560" aria-label="실시간 공장 도면">
      <g className="live-map__walls"><rect x="25" y="25" width="850" height="510" /><path d="M450 25v510M25 280h850" /></g>
      <g className="live-map__equipment">
        <path d="M80 90h100v36H80zm0 70h100v36H80zm215-70h100v36H295zm0 70h100v36H295zM110 345h90v34h-90zm0 62h90v34h-90zm190-62h90v34h-90zm0 62h90v34h-90z" />
        <path d="M520 92h125v42H520zm150 72h125v42H670zM520 350h105v44H520zm155 0h105v44H675zm-75 90h105v44H600z" />
      </g>
      <g className="live-map__zone-labels"><text x="48" y="52">ZONE_01 · FACTORY</text><text x="473" y="52">ZONE_02 · TRANSIT</text><text x="48" y="307">ZONE_03 · NARROW AISLE</text><text x="473" y="307">ZONE_04 · OPEN YARD</text></g>
    </svg>
  );
}

function LiveMapPage() {
  const [filter, setFilter] = useState('all');
  const analysisStates = useLatestAnalyses();
  const [groundTruths, setGroundTruths] = useState({});
  const analyses = useMemo(() => Object.fromEntries(
    analysisStates.filter((state) => state.analysis).map((state) => [state.id, state.analysis]),
  ), [analysisStates]);
  const connected = analysisStates.some((state) => state.analysis);
  useEffect(() => {
    let active = true;
    async function refreshGroundTruth() {
      const results = await Promise.allSettled(cctvs.map((camera) => getUnityGroundTruth(camera.groundTruthUrl)));
      if (!active) return;
      const next = {};
      results.forEach((result, index) => {
        if (result.status === 'fulfilled') next[cctvs[index].cameraId] = result.value;
      });
      setGroundTruths(next);
    }
    refreshGroundTruth();
    const timer = window.setInterval(refreshGroundTruth, 1000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);
  const objects = useMemo(() => objectsFromAnalyses(analyses, groundTruths), [analyses, groundTruths]);
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
            {visibleObjects.map((object) => <button className={`live-map__object live-map__object--${object.type} live-map__object--${object.risk}`} key={object.id} style={{ left: `${object.x}%`, top: `${object.y}%` }} type="button" title={`${object.label} · ${riskLevelLabels[object.risk.toUpperCase()]}`}>{object.type === 'forklift' ? <FiTruck /> : <FiUser />}<span>{object.label}</span></button>)}
          </div>
          <div className="live-map__legend"><span><i className="forklift" />지게차</span><span><i className="worker" />작업자</span><span><i className="danger" />위험 발생</span><b>{connected ? 'Backend 실시간 데이터' : '데이터 연결 대기'}</b></div>
        </section>

        <aside className="telemetry">
          <section className="telemetry__risk"><div className="telemetry__title"><strong><FiAlertTriangle /> 최고 위험 근접 쌍</strong><em>{highestRisk?.level || 'SAFE'}</em></div><h2>{dangerPair[0]} ↔ {dangerPair[1]}<span>{highestRisk ? `${Math.round(highestRisk.score)}점` : '—'}</span></h2><div className="telemetry__metrics"><div><span>현재 거리</span><b>{highestRisk ? `${Math.round(highestRisk.distance_px)} px` : '—'}</b></div><div><span>최근접 예상 시간</span><b>{highestRisk?.time_to_closest_approach_s == null ? '—' : `${highestRisk.time_to_closest_approach_s.toFixed(1)}초`}</b></div></div><p>{highestRisk?.reason || '현재 위험 쌍이 없습니다.'}</p></section>
          <section className="telemetry__objects"><div className="telemetry__tabs"><b>전체 ({objects.length})</b><span>위험 ({objects.filter((item) => item.risk !== 'safe').length})</span></div>{visibleObjects.map((object) => <article className={`telemetry-object telemetry-object--${object.risk}`} key={object.id}><div><i />{object.type === 'forklift' ? <FiTruck /> : <FiUser />}<strong>{object.label}</strong><em>{riskLevelLabels[object.risk.toUpperCase()]}</em></div><p>위치: {object.location}</p></article>)}</section>
          <div className="telemetry__notice"><FiRadio /> Unity ZONE별 CCTV 좌표 매핑</div>
        </aside>
      </div>
    </div>
  );
}

export default LiveMapPage;
