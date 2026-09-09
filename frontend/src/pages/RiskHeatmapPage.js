import { useMemo, useState } from 'react';
import { FiAlertTriangle, FiCalendar, FiMap, FiMapPin, FiTrendingUp } from 'react-icons/fi';
import './RiskHeatmapPage.css';

const hotspots = [
  { id: 1, x: 26, y: 56, zone: '자재 적재 구역', cctv: 'CCTV 01', level: 'critical', today: 38, week: 142, month: 486 },
  { id: 2, x: 72, y: 32, zone: '교차로 B', cctv: 'CCTV 04', level: 'critical', today: 31, week: 118, month: 392 },
  { id: 3, x: 48, y: 43, zone: '생산 라인 2', cctv: 'CCTV 02', level: 'warning', today: 19, week: 89, month: 267 },
  { id: 4, x: 65, y: 68, zone: '정문 입구', cctv: 'CCTV 02', level: 'warning', today: 12, week: 56, month: 181 },
  { id: 5, x: 18, y: 23, zone: '하역장', cctv: 'CCTV 03', level: 'caution', today: 8, week: 34, month: 102 },
  { id: 6, x: 83, y: 61, zone: '후계실 앞', cctv: 'CCTV 04', level: 'safe', today: 3, week: 12, month: 41 },
];

const levelLabels = { critical: '심각', warning: '경고', caution: '주의', safe: '안전' };

function FactoryFloorPlan({ spots, period }) {
  const max = Math.max(...spots.map((spot) => spot[period]), 1);
  return (
    <div className="heatmap-map">
      <svg className="heatmap-map__plan" viewBox="0 0 900 510" aria-label="공장 도면">
        <g className="floor-walls"><rect x="24" y="24" width="852" height="462" /><path d="M190 24v145H24M190 118h190V24M380 24v245M24 269h356M380 184h230V24M610 24v160h266M610 184v302M380 345h230M24 392h200v94M224 269v217M610 327h266M747 184v143" /></g>
        <g className="floor-machines"><rect x="57" y="57" width="98" height="35" /><rect x="57" y="112" width="98" height="34" /><rect x="234" y="55" width="105" height="58" /><rect x="234" y="135" width="105" height="88" /><rect x="420" y="55" width="145" height="38" /><rect x="420" y="113" width="145" height="38" /><rect x="649" y="53" width="190" height="72" /><rect x="649" y="212" width="60" height="78" /><rect x="775" y="212" width="62" height="78" /><rect x="655" y="365" width="180" height="73" /><path d="M50 310h135v42H50zM265 305h74v135h-74zM420 386h145v54H420z" /></g>
        <g className="floor-labels"><text x="52" y="46">LOADING DOCK</text><text x="225" y="46">STORAGE A</text><text x="413" y="46">ASSEMBLY LINE</text><text x="642" y="46">WAREHOUSE B</text><text x="51" y="296">MATERIAL ZONE</text><text x="644" y="350">SHIPPING AREA</text></g>
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
  const visibleSpots = useMemo(() => level === 'all' ? hotspots : hotspots.filter((spot) => spot.level === level), [level]);
  const rankedSpots = useMemo(() => [...visibleSpots].sort((a, b) => b[period] - a[period]), [visibleSpots, period]);
  const total = visibleSpots.reduce((sum, spot) => sum + spot[period], 0);
  const chartValues = period === 'today' ? [4, 9, 6, 18, 11, 7, 13, 21, 15, 10, 6, 3] : period === 'week' ? [32, 45, 38, 64, 51, 43, 72] : [42, 58, 76, 63, 81, 69, 92, 74, 88, 67, 55, 79];

  return (
    <div className="risk-heatmap">
      <header className="risk-heatmap__heading"><div><h1>위험구역 히트맵</h1><p>공장 내 위험 발생 위치 및 빈도 분석</p></div><span><FiMapPin /> 누적 위험 발생 <strong>{total}건</strong></span></header>
      <section className="heatmap-filters">
        <div className="heatmap-filter"><FiCalendar /><span>조회 기간</span>{[['today', '오늘'], ['week', '7일'], ['month', '30일']].map(([key, label]) => <button className={period === key ? 'is-active' : ''} key={key} onClick={() => setPeriod(key)}>{label}</button>)}</div>
        <label className="heatmap-filter"><FiAlertTriangle /><span>위험 단계</span><select value={level} onChange={(event) => setLevel(event.target.value)}><option value="all">전체 단계</option><option value="critical">심각</option><option value="warning">경고</option><option value="caution">주의</option><option value="safe">안전</option></select></label>
      </section>
      <div className="risk-heatmap__layout">
        <div className="risk-heatmap__main">
          <section className="heatmap-panel"><div className="heatmap-panel__title"><strong><FiMap /> 공장 위험 발생 분포</strong><span>위험 빈도가 높을수록 진하게 표시됩니다</span></div><FactoryFloorPlan spots={visibleSpots} period={period} /></section>
          <section className="heatmap-chart"><div className="heatmap-panel__title"><strong><FiTrendingUp /> 위험 발생 추이</strong><span>{period === 'today' ? '시간별' : '기간별'} 집계</span></div><div className="heatmap-chart__body">{chartValues.map((value, index) => <div className="heatmap-chart__bar" key={index}><i style={{ height: `${Math.max(12, value)}%` }} /><span>{period === 'today' ? `${index * 2}:00` : period === 'week' ? `${index + 1}일` : `${index * 3 + 1}일`}</span></div>)}</div></section>
        </div>
        <aside className="hotspot-ranking">
          <div className="heatmap-panel__title"><strong><FiAlertTriangle /> 위험 구역 순위</strong><span>{rankedSpots.length}개 구역</span></div>
          <div className="hotspot-ranking__list">{rankedSpots.map((spot, index) => { const value = spot[period]; const width = rankedSpots[0] ? value / rankedSpots[0][period] * 100 : 0; return <article className="hotspot-rank" key={spot.id}><div><span className="hotspot-rank__number">{String(index + 1).padStart(2, '0')}</span><div><strong>{spot.zone}</strong><small>{spot.cctv}</small></div><em className={`hotspot-rank__level hotspot-rank__level--${spot.level}`}>{levelLabels[spot.level]}</em></div><div className="hotspot-rank__count"><span>사건 수: <b>{value}건</b></span><span>{Math.round(value / Math.max(total, 1) * 100)}%</span></div><div className={`hotspot-rank__progress hotspot-rank__progress--${spot.level}`}><i style={{ width: `${width}%` }} /></div></article>; })}{!rankedSpots.length && <p className="hotspot-ranking__empty">선택한 위험 단계의 기록이 없습니다.</p>}</div>
        </aside>
      </div>
    </div>
  );
}

export default RiskHeatmapPage;
