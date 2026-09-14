import { getRiskEvents } from '../api/visionGuardApi';
import { eventStatusLabels, getDateRange, riskLevelLabels } from './riskEvent';

export async function collectRiskEvents({ date, cameraId }, { signal } = {}) {
  const events = new Map();
  let totalPages = 1;
  for (let page = 0; page < totalPages; page += 1) {
    const result = await getRiskEvents({ cameraId: cameraId || undefined, ...getDateRange(date), page, size: 100 }, { signal });
    totalPages = result.totalPages;
    result.content.forEach((event) => events.set(event.id, event));
  }
  return [...events.values()];
}

// Excel has no timezone: store UTC clock values and label the columns explicitly.
function excelDate(value) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export async function createRiskEventsWorkbook(events, origin) {
  const { default: ExcelJS } = await import('exceljs');
  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet('위험 이력', { views: [{ state: 'frozen', ySplit: 1 }] });
  sheet.columns = [
    ['이력 ID', 'id', 14], ['발생 일시 (UTC)', 'capturedAt', 23],
    ['위치', 'location', 22], ['카메라 ID', 'cameraId', 22],
    ['위험 유형', 'riskType', 20], ['위험도 (누적 최고)', 'level', 21],
    ['처리 상태', 'handlingStatus', 20], ['이벤트 상태', 'status', 18],
    ['영상 링크', 'video', 28], ['이력 상세 링크', 'detail', 45],
    ['마지막 감지 (UTC)', 'lastSeenAt', 23], ['종료 일시 (UTC)', 'endedAt', 23],
    ['저장 일시 (UTC)', 'createdAt', 23], ['작업자 Tracking ID', 'personTrackId', 23],
    ['지게차 Tracking ID', 'forkliftTrackId', 23], ['스트림 ID', 'streamId', 25],
    ['시작 프레임 ID', 'frameId', 25], ['감지 프레임 수', 'frameCount', 18],
    ['종료 이유', 'endReason', 25],
  ].map(([header, key, width]) => ({ header, key, width }));
  events.forEach((event) => {
    const row = sheet.addRow({
      ...event,
      id: String(event.id),
      capturedAt: excelDate(event.capturedAt), lastSeenAt: excelDate(event.lastSeenAt),
      endedAt: excelDate(event.endedAt), createdAt: excelDate(event.createdAt),
      location: '미제공 (카메라 ID 참고)', riskType: '미제공', handlingStatus: '미제공',
      level: riskLevelLabels[event.level] || event.level,
      status: eventStatusLabels[event.status] || event.status,
      video: '미제공 (서버 영상 미저장)',
      detail: { text: '이력 상세 보기', hyperlink: new URL(`/alerts?eventId=${encodeURIComponent(event.id)}`, origin).href },
    });
    row.getCell('detail').font = { color: { argb: 'FF0563C1' }, underline: true };
  });
  ['capturedAt', 'lastSeenAt', 'endedAt', 'createdAt'].forEach((key) => {
    sheet.getColumn(key).numFmt = 'yyyy-mm-dd hh:mm:ss';
  });
  sheet.autoFilter = { from: 'A1', to: 'S1' };
  sheet.getRow(1).height = 30;
  sheet.getRow(1).eachCell((cell) => {
    cell.font = { bold: true, color: { argb: 'FFFFFFFF' } };
    cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF334155' } };
  });
  return workbook;
}

export async function downloadRiskEvents(filters, options = {}) {
  const events = await collectRiskEvents(filters, options);
  if (!events.length) throw new Error('내려받을 위험 이력이 없습니다.');
  const workbook = await createRiskEventsWorkbook(events, window.location.origin);
  const buffer = await workbook.xlsx.writeBuffer();
  if (options.signal?.aborted) return;
  const url = URL.createObjectURL(new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `위험이력_${filters.date || '전체기간'}_${new Date().toISOString().replace(/[:.]/g, '-')}.xlsx`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return events.length;
}
