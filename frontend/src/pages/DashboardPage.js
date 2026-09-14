import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { FiVideo } from 'react-icons/fi';
import useLatestAnalyses from '../hooks/useLatestAnalyses';
import { getRiskEvents } from '../api/visionGuardApi';
import { getApiErrorMessage } from '../api/client';
import { formatDateTime, riskLevelLabels } from '../utils/riskEvent';
import './DashboardPage.css';

export function AnalysisCard({ camera }) {
  const prediction = camera.analysis?.prediction;
  const priorities = { SAFE: 0, WARNING: 1, DANGER: 2 };
  const risk = [...(prediction?.risks || [])].sort((a, b) => priorities[b.level] - priorities[a.level] || b.score - a.score)[0];
  const level = prediction?.overall_risk;
  return <article className="camera-card">
    <div className="camera-feed">
      <div className="camera-feed__top"><strong>{camera.id}</strong><span>{camera.analysis?.aiMode === 'mock' ? 'MOCK · 모의 분석' : '분석 결과'}</span></div>
      <div className="camera-feed__empty"><FiVideo /><span>영상 스트림 미제공</span></div>
    </div>
    <section className="camera-detail__section">
      {camera.loading && <p role="status">분석 결과 조회 중입니다.</p>}
      {camera.error && <p role="status">{camera.error}</p>}
      {camera.stale && <p role="status">갱신 지연 · 마지막 분석 결과입니다.</p>}
      <span className={`dashboard__status dashboard__status--${level?.toLowerCase() || 'unknown'}`}><span />{riskLevelLabels[level] || '미확인'}</span>
      {camera.analysis && <p>촬영 시각: {formatDateTime(camera.analysis.capturedAt)}</p>}
      <dl className="camera-detail__metrics">
        <div><dt>최고 위험 쌍 점수</dt><dd>{risk ? `${risk.score} / 100` : '—'}</dd></div>
        <div><dt>현재 거리</dt><dd>{risk ? `${risk.distance_px} px` : '—'}</dd></div>
        <div><dt>최근접 예상 시간</dt><dd>{risk?.time_to_closest_approach_s == null ? '—' : `${risk.time_to_closest_approach_s}초`}</dd></div>
        <div><dt>작업자 / 지게차 Tracking ID</dt><dd>{risk?.person_track_id ?? '—'} / {risk?.forklift_track_id ?? '—'}</dd></div>
        <div><dt>탐지 객체 수</dt><dd>{prediction?.detections.length ?? '—'}</dd></div>
        <div><dt>스트림 ID</dt><dd>{camera.analysis?.streamId ?? '—'}</dd></div>
      </dl>
      {risk && <p>{risk.reason}</p>}
    </section>
  </article>;
}

function RecentEvents({ cameraId }) {
  const [events, setEvents] = useState([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    setEvents([]); setError(''); setLoading(true);
    async function poll() {
      try {
        const data = await getRiskEvents({ cameraId, size: 4 }, { signal: controller.signal });
        if (!controller.signal.aborted) { setEvents(data.content); setError(''); }
      } catch (err) {
        if (!controller.signal.aborted) { setEvents([]); setError(getApiErrorMessage(err)); }
      } finally {
        if (!controller.signal.aborted) { setLoading(false); timer = setTimeout(poll, 5000); }
      }
    }
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [cameraId]);
  return <section className="camera-detail__section camera-detail__alerts"><h2>최근 위험 이력</h2>
    {loading && <p role="status">이력 조회 중입니다.</p>}
    {error && <p role="alert">{error}</p>}
    {!loading && !error && !events.length && <p>위험 이력이 없습니다.</p>}
    {events.map((event) => <Link className={`camera-detail__alert camera-detail__alert--${event.level.toLowerCase()}`} key={event.id} to={`/alerts?eventId=${event.id}`}><span>{formatDateTime(event.capturedAt)}</span><div><strong>{riskLevelLabels[event.level]}</strong><small>{event.cameraId} · #{event.id}</small></div></Link>)}
  </section>;
}

export default function DashboardPage() {
  const cameras = useLatestAnalyses();
  const [params, setParams] = useSearchParams();
  const selected = cameras.find((camera) => camera.id === params.get('cameraId')) || cameras[Number(params.get('cctv')) - 1];
  return <div className="dashboard">
    <div className="dashboard__heading"><h1>통합 관제 대시보드</h1><span className="dashboard__connection">분석 결과 3초 간격 조회 · 영상 미연결</span></div>
    <div className="dashboard__tabs"><button className={!selected ? 'is-active' : ''} onClick={() => setParams({})}>전체</button>{cameras.map((camera) => <button key={camera.id} className={selected?.id === camera.id ? 'is-active' : ''} onClick={() => setParams({ cameraId: camera.id })}>{camera.id}</button>)}</div>
    <section className="dashboard__camera-grid">{(selected ? [selected] : cameras).map((camera) => <AnalysisCard key={camera.id} camera={camera} />)}</section>
    <RecentEvents cameraId={selected?.id} />
  </div>;
}
