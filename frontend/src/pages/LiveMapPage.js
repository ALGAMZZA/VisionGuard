import { useState } from 'react';
import { Link } from 'react-router-dom';
import useLatestAnalyses from '../hooks/useLatestAnalyses';
import { formatDateTime, riskLevelLabels } from '../utils/riskEvent';
import './LiveMapPage.css';

export default function LiveMapPage() {
  const cameras = useLatestAnalyses();
  const [filter, setFilter] = useState('all');
  return <div className="live-control">
    <header className="live-control__heading"><h1>실시간 도면 관제</h1><span>분석 결과 3초 간격 조회</span></header>
    <p>공장 도면 좌표가 제공되지 않아 카메라 영상 좌표 기준으로 탐지 객체를 표시합니다. 배경 영상은 제공되지 않습니다.</p>
    <section className="live-control__filters"><span>표시 항목</span>{[['all', '전체'], ['forklift', '지게차'], ['person', '작업자']].map(([key, label]) => <button key={key} className={filter === key ? 'is-active' : ''} onClick={() => setFilter(key)}>{label}</button>)}</section>
    {cameras.map((camera) => {
      const prediction = camera.analysis?.prediction;
      const objects = (prediction?.detections || []).filter((object) => filter === 'all' || object.class_name === filter);
      return <section className="live-map-panel" key={camera.id}>
        <div className="live-map-panel__top"><Link to={`/?cameraId=${encodeURIComponent(camera.id)}`}>{camera.id}</Link><b>{camera.analysis?.aiMode === 'mock' ? 'MOCK · 모의 분석' : '카메라 영상 좌표'}</b></div>
        {camera.loading && <p role="status">분석 결과 조회 중입니다.</p>}
        {camera.error && <p role="status">{camera.error}</p>}
        {camera.stale && <p role="status">갱신 지연 · 마지막 분석 결과입니다.</p>}
        {prediction && <>
          <p>{formatDateTime(camera.analysis.capturedAt)} · {riskLevelLabels[prediction.overall_risk]} · 표시 객체 {objects.length}개</p>
          <svg className="live-map__detections" viewBox={`0 0 ${prediction.image_width} ${prediction.image_height}`} aria-label={`${camera.id} 탐지 객체 위치`}>
            {objects.map((object, index) => <g key={index} stroke={object.class_name === 'person' ? '#56b8ff' : '#ffb35a'} fill="none" strokeWidth="2">
              <rect x={object.bbox.x1} y={object.bbox.y1} width={object.bbox.x2 - object.bbox.x1} height={object.bbox.y2 - object.bbox.y1} />
              <text x={object.bbox.x1} y={Math.max(18, object.bbox.y1 - 5)} fill="currentColor" stroke="none" fontSize="18">{object.class_name === 'person' ? '작업자' : '지게차'} #{object.track_id ?? '미확정'}{object.is_predicted ? ' (예측)' : ''}</text>
            </g>)}
          </svg>
          {!objects.length && <p>표시할 탐지 객체가 없습니다.</p>}
        </>}
      </section>;
    })}
  </div>;
}
