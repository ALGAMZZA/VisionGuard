import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  FiAlertTriangle,
  FiCalendar,
  FiCamera,
  FiClock,
  FiMapPin,
  FiPlay,
  FiTruck,
  FiUser,
} from 'react-icons/fi';
import './AlertHistoryPage.css';
import { alerts } from '../data/alerts';

function SummaryCard({ label, value, unit, icon: Icon, tone }) {
  return (
    <article className={`alert-summary alert-summary--${tone}`}>
      <div><span>{label}</span><Icon /></div>
      <strong>{value}<small>{unit}</small></strong>
    </article>
  );
}

function VideoPanel({ alert }) {
  return (
    <section className="alert-video">
      <div className="alert-video__title"><span><FiCamera /> {alert.cctv}_{alert.date}_{alert.time}.mp4</span><span>10 SEC CLIP</span></div>
      <div className="alert-video__screen">
        {alert.videoUrl ? <video key={alert.videoUrl} src={alert.videoUrl} controls /> : <div className="alert-video__placeholder"><FiCamera /><strong>위험 발생 영상</strong><span>Firebase 영상 연결 대기 중</span></div>}
        <span className="alert-video__rec">● REC · AI TRACKING</span>
        <div className="alert-video__box alert-video__box--worker"><span>{alert.workerId}</span></div>
        <div className="alert-video__box alert-video__box--forklift"><span>{alert.forkliftId}</span></div>
      </div>
      <div className="alert-video__timeline"><i style={{ left: '50%' }} /><span /></div>
      <div className="alert-video__controls"><FiPlay /><b>00:05 / 00:10</b><span>위험 발생 시점</span></div>
    </section>
  );
}

function AlertHistoryPage() {
  const [searchParams] = useSearchParams();
  const requestedAlertId = Number(searchParams.get('alert'));
  const [selectedId, setSelectedId] = useState(alerts.some((alert) => alert.id === requestedAlertId) ? requestedAlertId : alerts[0].id);
  const [levelFilter, setLevelFilter] = useState('all');

  useEffect(() => {
    if (alerts.some((alert) => alert.id === requestedAlertId)) {
      setSelectedId(requestedAlertId);
    }
  }, [requestedAlertId]);

  const selectedAlert = alerts.find((alert) => alert.id === selectedId) || alerts[0];
  const filteredAlerts = useMemo(() => levelFilter === 'all' ? alerts : alerts.filter((alert) => alert.levelKey === levelFilter), [levelFilter]);

  return (
    <div className="alert-history">
      <div className="alert-history__heading"><div><h1>알림 이력</h1><p>위험 이벤트 기록 및 영상 분석</p></div><span><i /> Firebase 연결됨</span></div>

      <section className="alert-history__summaries">
        <SummaryCard label="오늘 위험 상황" value="12" unit="건" icon={FiAlertTriangle} tone="warning" />
        <SummaryCard label="오늘 사고" value="01" unit="건" icon={FiAlertTriangle} tone="danger" />
        <SummaryCard label="평균 위험도" value="64" unit="%" icon={FiCamera} tone="yellow" />
        <SummaryCard label="최근 발생" value="14:32:18" unit="" icon={FiClock} tone="neutral" />
      </section>

      <section className="alert-history__filters">
        <label><FiCalendar /><input type="date" defaultValue="2026-09-04" /></label>
        <label><FiCamera /><select defaultValue="all"><option value="all">전체 CCTV</option>{[1, 2, 3, 4].map((id) => <option value={id} key={id}>CCTV {id}</option>)}</select></label>
        <label><FiAlertTriangle /><select value={levelFilter} onChange={(event) => setLevelFilter(event.target.value)}><option value="all">전체 위험 단계</option><option value="critical">충돌 위험</option><option value="accident">사고</option><option value="warning">근접 위험</option><option value="caution">주의</option></select></label>
      </section>

      <div className="alert-history__workspace">
        <aside className="alert-list">
          <div className="alert-list__header"><strong>사건 목록</strong><span>Total: {filteredAlerts.length}</span></div>
          {filteredAlerts.map((alert) => (
            <button className={`alert-list__item alert-list__item--${alert.levelKey}${selectedId === alert.id ? ' is-active' : ''}`} type="button" key={alert.id} onClick={() => setSelectedId(alert.id)}>
              <div className="alert-list__thumbnail"><FiPlay /></div>
              <div className="alert-list__content"><div><b>{alert.level}</b><time>{alert.time}</time></div><strong>{alert.cctv}</strong><span>{alert.zone}</span></div>
              <em>{alert.score}%</em>
            </button>
          ))}
        </aside>

        <main className="alert-detail">
          <VideoPanel alert={selectedAlert} />
          <section className="alert-analysis">
            <h2><FiAlertTriangle /> 위험 이벤트 상세</h2>
            <div className="alert-analysis__grid">
              <dl><div><dt>위험 단계</dt><dd>{selectedAlert.level} · {selectedAlert.score}%</dd></div><div><dt>충돌 예상 시간 (TTC)</dt><dd>{selectedAlert.ttc}</dd></div><div><dt>최소 접근 거리</dt><dd>{selectedAlert.distance}</dd></div><div><dt>발생 시간</dt><dd>{selectedAlert.date} {selectedAlert.time}</dd></div></dl>
              <dl><div><dt><FiUser /> 작업자 Tracking ID</dt><dd>{selectedAlert.workerId}</dd></div><div><dt><FiTruck /> 지게차 Tracking ID</dt><dd>{selectedAlert.forkliftId}</dd></div><div><dt><FiCamera /> CCTV 번호</dt><dd>{selectedAlert.cctv}</dd></div><div><dt><FiMapPin /> 발생 위치</dt><dd>{selectedAlert.location}</dd></div></dl>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}

export default AlertHistoryPage;
