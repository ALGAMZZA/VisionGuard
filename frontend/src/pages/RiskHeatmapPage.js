import { useEffect, useMemo, useState } from 'react';
import { FiAlertTriangle, FiCalendar, FiMap, FiMapPin, FiTrendingUp } from 'react-icons/fi';
import { riskLevelLabels } from '../utils/riskEvent';
import { getRiskEvents } from '../api/visionGuardApi';
import './RiskHeatmapPage.css';

const hotspotDefinitions = [
  { id: 1, cameraId: 'camera-1', x: 26, y: 27, zone: 'ZONE_01 · 공장 작업 구역', cctv: 'CCTV 01' },
  { id: 2, cameraId: 'camera-2', x: 74, y: 27, zone: 'ZONE_02 · 제품 이동 통로', cctv: 'CCTV 02' },
  { id: 3, cameraId: 'camera-3', x: 26, y: 73, zone: 'ZONE_03 · 좁은 창고 통로', cctv: 'CCTV 03' },
  { id: 4, cameraId: 'camera-4', x: 74, y: 73, zone: 'ZONE_04 · 넓은 작업장', cctv: 'CCTV 04' },
];

const levelRank = { safe: 0, warning: 1, danger: 2 };

function rangeStart(period) {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  if (period === 'week') start.setDate(start.getDate() - 6);
  if (period === 'month') start.setDate(start.getDate() - 29);
  return start.toISOString();
}

function FactoryFloorPlan({ spots, period }) {
  const max = Math.max(...spots.map((spot) => spot[period]), 1);
  return (
    <div className="heatmap-map">
      <svg className="heatmap-map__plan" viewBox="0 0 900 510" aria-label="공장 도면">
        <g className="floor-walls"><rect x="24" y="24" width="852" height="462" /><path d="M450 24v462M24 255h852" /></g>
        <g className="floor-machines"><path d="M65 70h105v34H65zm0 60h105v34H65zm210-60h105v34H275zm0 60h105v34H275zM520 72h125v42H520zm145 65h145v42H665zM75 312h100v32H75zm0 57h100v32H75zm205-57h100v32H280zm0 57h100v32H280zM520 315h110v42H520zm155 0h110v42H675zm-78 72h110v42H597z" /></g>
        <g className="floor-labels"><text x="48" y="48">ZONE_01 · FACTORY</text><text x="474" y="48">ZONE_02 · TRANSIT</text><text x="48" y="279">ZONE_03 · NARROW AISLE</text><text x="474" y="279">ZONE_04 · OPEN YARD</text></g>
      </svg>
      {spots.map((spot) => {
        const strength = 0.55 + (spot[period] / max) * 0.75;
        return <button className={`heatmap-spot heatmap-spot--${spot.level}`} key={spot.id} style={{ left: `${spot.x}%`, top: `${spot.y}%`, '--spot-scale': strength }} type="button"><i /><span>{spot.zone}<b>{spot[period]}건</b></span></button>;
      })}
      <div className="heatmap-map__legend"><span><i className="low" />낮음</span><span><i className="medium" />보통</span><span><i className="high" />높음</span></div>
    </div>
  );
}

function RiskHeatmapPage() {
  const [period, setPeriod] = useState('today');
  const [level, setLevel] = useState('all');
  const [events, setEvents] = useState([]);
  useEffect(() => {
    const controller = new AbortController();
    getRiskEvents({ from: rangeStart(period), page: 0, size: 100 }, { signal: controller.signal })
      .then((page) => setEvents(page.content || []))
      .catch(() => setEvents([]));
    return () => controller.abort();
  }, [period]);
  const hotspots = useMemo(() => hotspotDefinitions.map((spot) => {
    const related = events.filter((event) => event.cameraId === spot.cameraId);
    const highest = related.reduce((best, event) => {
      const candidate = String(event.level || 'SAFE').toLowerCase();
      return levelRank[candidate] > levelRank[best] ? candidate : best;
    }, 'safe');
    return { ...spot, level: highest, [period]: related.length };
  }), [events, period]);
  const visibleSpots = useMemo(() => level === 'all' ? hotspots : hotspots.filter((spot) => spot.level === level), [hotspots, level]);
  const rankedSpots = useMemo(() => [...visibleSpots].sort((a, b) => b[period] - a[period]), [visibleSpots, period]);
  const total = visibleSpots.reduce((sum, spot) => sum + spot[period], 0);
  const bucketCount = period === 'today' ? 12 : period === 'week' ? 7 : 10;
  const chartValues = Array.from({ length: bucketCount }, () => 0);
  events.forEach((event) => {
    const date = new Date(event.capturedAt);
    if (Number.isNaN(date.valueOf())) return;
    const index = period === 'today'
      ? Math.floor(date.getHours() / 2)
      : period === 'week'
        ? Math.max(0, 6 - Math.floor((Date.now() - date.valueOf()) / 86400000))
        : Math.max(0, 9 - Math.floor((Date.now() - date.valueOf()) / (3 * 86400000)));
    if (index >= 0 && index < chartValues.length) chartValues[index] += 1;
  });
  const chartMax = Math.max(...chartValues, 1);

  return (
    <div className="risk-heatmap">
      <header className="risk-heatmap__heading"><div><h1>위험구역 히트맵</h1></div><span><FiMapPin /> 조회 기간 위험 발생 <strong>{total}건</strong></span></header>
      <section className="heatmap-filters">
        <div className="heatmap-filter"><FiCalendar /><span>조회 기간</span>{[['today', '오늘'], ['week', '7일'], ['month', '30일']].map(([key, label]) => <button className={period === key ? 'is-active' : ''} key={key} onClick={() => setPeriod(key)}>{label}</button>)}</div>
        <label className="heatmap-filter"><FiAlertTriangle /><span>위험 단계</span><select value={level} onChange={(event) => setLevel(event.target.value)}><option value="all">전체 단계</option>{Object.entries(riskLevelLabels).map(([key, label]) => <option key={key} value={key.toLowerCase()}>{label}</option>)}</select></label>
      </section>
      <div className="risk-heatmap__layout">
        <div className="risk-heatmap__main">
          <section className="heatmap-panel"><div className="heatmap-panel__title"><strong><FiMap /> 공장 위험 발생 분포</strong><span>위험 빈도가 높을수록 진하게 표시됩니다</span></div><FactoryFloorPlan spots={visibleSpots} period={period} /></section>
          <section className="heatmap-chart"><div className="heatmap-panel__title"><strong><FiTrendingUp /> 위험 발생 추이</strong><span>{period === 'today' ? '시간별' : '기간별'} 집계</span></div><div className="heatmap-chart__body">{chartValues.map((value, index) => <div className="heatmap-chart__bar" key={index}><i style={{ height: `${value ? Math.max(12, value / chartMax * 100) : 0}%` }} /><span>{period === 'today' ? `${index * 2}:00` : period === 'week' ? `${index + 1}일` : `${index * 3 + 1}일`}</span></div>)}</div></section>
        </div>
        <aside className="hotspot-ranking">
          <div className="heatmap-panel__title"><strong><FiAlertTriangle /> 위험 구역 순위</strong><span>{rankedSpots.length}개 구역</span></div>
          <div className="hotspot-ranking__list">{rankedSpots.map((spot, index) => { const value = spot[period]; const width = rankedSpots[0] ? value / Math.max(rankedSpots[0][period], 1) * 100 : 0; return <article className="hotspot-rank" key={spot.id}><div><span className="hotspot-rank__number">{String(index + 1).padStart(2, '0')}</span><div><strong>{spot.zone}</strong><small>{spot.cctv}</small></div><em className={`hotspot-rank__level hotspot-rank__level--${spot.level}`}>{riskLevelLabels[spot.level.toUpperCase()]}</em></div><div className="hotspot-rank__count"><span>사건 수: <b>{value}건</b></span><span>{Math.round(value / Math.max(total, 1) * 100)}%</span></div><div className={`hotspot-rank__progress hotspot-rank__progress--${spot.level}`}><i style={{ width: `${width}%` }} /></div></article>; })}{!rankedSpots.length && <p className="hotspot-ranking__empty">선택한 위험 단계의 기록이 없습니다.</p>}</div>
        </aside>
      </div>
    </div>
  );
}

export default RiskHeatmapPage;
