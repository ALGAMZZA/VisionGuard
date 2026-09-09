import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DEFAULT_CAMERA_ID, getRiskEvent, getRiskEvents } from '../api/visionGuardApi';
import { getApiErrorMessage } from '../api/client';
import { eventStatusLabels, formatDateTime, getDateRange, riskLevelLabels } from '../utils/riskEvent';
import './AlertHistoryPage.css';

function EventDetail({ detail: { event, prediction } }) {
  const fields = [
    ['최고 위험 단계', riskLevelLabels[event.level] || event.level],
    ['최근 판정', riskLevelLabels[prediction.overall_risk] || prediction.overall_risk],
    ['발생 시간', formatDateTime(event.capturedAt)],
    ['마지막 감지', formatDateTime(event.lastSeenAt)],
    ['종료 시간', formatDateTime(event.endedAt)],
    ['상태', eventStatusLabels[event.status] || event.status],
    ['작업자 Tracking ID', event.personTrackId],
    ['지게차 Tracking ID', event.forkliftTrackId],
    ['카메라 ID', event.cameraId], ['스트림 ID', event.streamId],
    ['시작 프레임 ID', event.frameId], ['감지 프레임 수', event.frameCount],
    ['종료 이유', event.endReason],
  ];
  return <section className="alert-analysis">
    <h2>위험 이벤트 #{event.id}</h2>
    <p>현재 서버는 원본 이미지와 영상을 저장하지 않습니다.</p>
    <dl>{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value ?? '—'}</dd></div>)}</dl>
    {prediction.risks.map((risk, index) => <section key={index}>
      <h3>위험 쌍 {index + 1} · {riskLevelLabels[risk.level] || risk.level}</h3>
      <dl>
        <div><dt>위험 점수</dt><dd>{risk.score} / 100</dd></div>
        <div><dt>현재 거리</dt><dd>{risk.distance_px} px</dd></div>
        <div><dt>예측 거리</dt><dd>{risk.future_distance_px} px</dd></div>
        <div><dt>최근접 예상 시간</dt><dd>{risk.time_to_closest_approach_s == null ? '—' : risk.time_to_closest_approach_s + '초'}</dd></div>
      </dl><p>{risk.reason}</p>
    </section>)}
    {!prediction.risks.length && <p>저장된 위험 쌍 정보가 없습니다.</p>}
  </section>;
}

function AlertHistoryPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  // 기존 알림 링크도 지원합니다.
  const rawId = searchParams.get('eventId') ?? searchParams.get('alert');
  const selectedId = rawId && /^[0-9]+$/.test(rawId) ? Number(rawId) : null;
  const [date, setDate] = useState('');
  const [cameraId, setCameraId] = useState('');
  const [page, setPage] = useState(0);
  const [result, setResult] = useState(null);
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState('');
  const [detailError, setDetailError] = useState('');
  const [refresh, setRefresh] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setResult(null);
    getRiskEvents({ cameraId: cameraId || undefined, ...getDateRange(date), page, size: 20 }, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setResult(data); })
      .catch((err) => { if (!controller.signal.aborted) setError(getApiErrorMessage(err)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [cameraId, date, page, refresh]);

  const activeId = selectedId ?? result?.content[0]?.id ?? null;
  useEffect(() => {
    const controller = new AbortController();
    setDetail(null);
    setDetailError('');
    setDetailLoading(activeId !== null);
    if (activeId !== null) {
      getRiskEvent(activeId, { signal: controller.signal })
        .then((data) => { if (!controller.signal.aborted) setDetail(data); })
        .catch((err) => { if (!controller.signal.aborted) setDetailError(getApiErrorMessage(err)); })
        .finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    }
    return () => controller.abort();
  }, [activeId, refresh]);

  function resetSelection() { setSearchParams({}); setPage(0); }

  return <div className="alert-history">
    <div className="alert-history__heading"><div><h1>위험 이력</h1><p>위험 이벤트 기록 및 분석 결과</p></div><button type="button" onClick={() => setRefresh((value) => value + 1)}>새로고침</button></div>
    <section className="alert-history__filters">
      <label>발생 날짜<input aria-label="발생 날짜" type="date" value={date} onChange={(e) => { setDate(e.target.value); resetSelection(); }} /></label>
      <label>카메라<select aria-label="카메라" value={cameraId} onChange={(e) => { setCameraId(e.target.value); resetSelection(); }}><option value="">전체 카메라</option><option value={DEFAULT_CAMERA_ID}>{DEFAULT_CAMERA_ID}</option></select></label>
    </section>
    {error && <p role="alert">{error}</p>}
    <div className="alert-history__workspace">
      <aside className="alert-list">
        <div className="alert-list__header"><strong>이벤트 목록</strong><span>전체 {result?.totalElements ?? '—'}건</span></div>
        {loading && <p role="status">목록을 불러오는 중입니다.</p>}
        {result?.content.length === 0 && <p>조회된 위험 이벤트가 없습니다.</p>}
        {result?.content.map((event) => <button className={'alert-list__item alert-list__item--' + event.level + (activeId === event.id ? ' is-active' : '')} type="button" key={event.id} onClick={() => setSearchParams({ eventId: String(event.id) })}>
          <div className="alert-list__thumbnail">#{event.id}</div>
          <div className="alert-list__content"><div><b>{riskLevelLabels[event.level] || event.level}</b></div><strong>{event.cameraId}</strong><span>{formatDateTime(event.capturedAt)}</span></div>
          <em>{eventStatusLabels[event.status] || event.status}</em>
        </button>)}
        <div className="alert-list__pagination">
          <button type="button" disabled={loading || page === 0} onClick={() => { setPage(page - 1); setSearchParams({}); }}>이전</button>
          <span>{result && result.totalPages > 0 ? result.page + 1 : 0} / {result?.totalPages ?? 0}</span>
          <button type="button" disabled={loading || !result || page + 1 >= result.totalPages} onClick={() => { setPage(page + 1); setSearchParams({}); }}>다음</button>
        </div>
      </aside>
      <main className="alert-detail">
        {detailLoading && <p role="status">상세 정보를 불러오는 중입니다.</p>}
        {detailError && <p role="alert">{detailError}</p>}
        {detail && <EventDetail detail={detail} />}
        {!detailLoading && !detailError && !detail && <p>위험 이벤트를 선택해 주세요.</p>}
      </main>
    </div>
  </div>;
}

export default AlertHistoryPage;
