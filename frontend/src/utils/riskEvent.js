export const riskLevelLabels = { SAFE: '안전', WARNING: '경고', DANGER: '위험' };
export const eventStatusLabels = { OPEN: '진행 중', CLOSED: '종료', LEGACY: '이전 데이터' };
export function formatDateTime(value) {
  return value ? new Date(value).toLocaleString('ko-KR') : '—';
}

// 날짜 입력은 브라우저의 로컬 날짜로 해석하고 UTC로 전송합니다.
export function getDateRange(date) {
  if (!date) return {};
  return {
    from: new Date(`${date}T00:00:00.000`).toISOString(),
    to: new Date(`${date}T23:59:59.999`).toISOString(),
  };
}
