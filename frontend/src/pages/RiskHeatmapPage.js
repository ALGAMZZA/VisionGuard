import { useEffect, useMemo, useState } from 'react';
import { getApiErrorMessage } from '../api/client';
import { riskLevelLabels } from '../utils/riskEvent';
import { loadStatisticsEvents, statisticsRange, summarizeEvents } from '../utils/riskStatistics';
import './RiskHeatmapPage.css';

export default function RiskHeatmapPage() {
  const [period, setPeriod] = useState('today');
  const [level, setLevel] = useState('all');
  const [refresh, setRefresh] = useState(0);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    const range = statisticsRange(period);
    setResult(null); setError(''); setLoading(true);
    loadStatisticsEvents(range, { signal: controller.signal })
      .then((events) => { if (!controller.signal.aborted) setResult({ events, range }); })
      .catch((err) => { if (!controller.signal.aborted) setError(getApiErrorMessage(err)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [period, refresh]);
  const summary = useMemo(() => result ? summarizeEvents(result.events, period, result.range, level) : null, [result, period, level]);
  const max = Math.max(1, ...(summary?.buckets.map((bucket) => bucket.count) || []));
  return <div className="risk-heatmap">
    <header className="risk-heatmap__heading"><h1>위험구역 히트맵</h1><span>조회 기간 위험 발생 <strong>{summary ? `${summary.total}건` : '—'}</strong></span></header>
    <section className="heatmap-filters">
      <div className="heatmap-filter"><span>조회 기간</span>{[['today', '오늘'], ['week', '7일'], ['month', '30일']].map(([key, label]) => <button key={key} className={period === key ? 'is-active' : ''} onClick={() => setPeriod(key)}>{label}</button>)}</div>
      <label className="heatmap-filter">위험 단계<select value={level} onChange={(event) => setLevel(event.target.value)}><option value="all">전체 단계</option>{['WARNING', 'DANGER'].map((key) => <option key={key} value={key}>{riskLevelLabels[key]}</option>)}</select></label>
      <button type="button" onClick={() => setRefresh((value) => value + 1)}>새로고침</button>
    </section>
    <p>위험 시작 시각 기준 집계 · 위험도는 이벤트의 누적 최고 단계입니다.</p>
    {loading && <p role="status">기간 내 위험 이력을 집계하고 있습니다.</p>}
    {error && <p role="alert">{error}</p>}
    <section className="heatmap-panel"><div className="heatmap-panel__title"><strong>공장 위험 발생 분포</strong></div><p>도면 좌표 정보가 없어 공간 히트맵은 아직 표시할 수 없습니다. 카메라별 발생 건수를 아래에서 확인하세요.</p></section>
    {summary && <div className="risk-heatmap__layout">
      <section className="heatmap-chart"><div className="heatmap-panel__title"><strong>위험 발생 추이</strong><span>{period === 'today' ? '2시간별' : '일별'} 집계</span></div><div className="heatmap-chart__body">{summary.buckets.map((bucket) => <div className="heatmap-chart__bar" key={bucket.start} title={`${bucket.label} ${bucket.count}건`}><b>{bucket.count}</b><i style={{ height: `${bucket.count / max * 80}%` }} /><span>{bucket.label}</span></div>)}</div></section>
      <aside className="hotspot-ranking"><div className="heatmap-panel__title"><strong>카메라별 발생 순위</strong></div><div className="hotspot-ranking__list">{summary.cameras.map(([id, count], index) => <article className="hotspot-rank" key={id}><div><span className="hotspot-rank__number">{index + 1}</span><strong>{id}</strong></div><div className="hotspot-rank__count"><span>사건 수: <b>{count}건</b></span></div></article>)}{!summary.total && <p>선택한 조건의 위험 이력이 없습니다.</p>}</div></aside>
    </div>}
  </div>;
}
