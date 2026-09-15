import { getRiskEvents } from '../api/visionGuardApi';

export function statisticsRange(period, now = new Date()) {
  const from = new Date(now);
  from.setHours(0, 0, 0, 0);
  from.setDate(from.getDate() - ({ today: 1, week: 7, month: 30 }[period] - 1));
  return { from: from.toISOString(), to: now.toISOString() };
}

export async function loadStatisticsEvents(range, { signal } = {}) {
  const events = new Map();
  let totalPages = 1;
  for (let page = 0; page < totalPages; page += 1) {
    const data = await getRiskEvents({ ...range, page, size: 100 }, { signal });
    data.content.forEach((event) => events.set(event.id, event));
    totalPages = data.totalPages;
  }
  return [...events.values()];
}

export function summarizeEvents(events, period, range, level) {
  const from = new Date(range.from);
  const buckets = Array.from({ length: period === 'today' ? 12 : period === 'week' ? 7 : 30 }, (_, index) => {
    const date = new Date(from);
    if (period === 'today') date.setHours(index * 2);
    else date.setDate(date.getDate() + index);
    return { start: date.getTime(), label: period === 'today' ? `${index * 2}:00` : `${date.getMonth() + 1}/${date.getDate()}`, count: 0 };
  });
  const cameras = new Map();
  let total = 0;
  events.forEach((event) => {
    const at = Date.parse(event.capturedAt);
    if (at < Date.parse(range.from) || at > Date.parse(range.to) || !Number.isFinite(at)) return;
    if (level !== 'all' && event.level !== level) return;
    total += 1;
    cameras.set(event.cameraId, (cameras.get(event.cameraId) || 0) + 1);
    const bucket = [...buckets].reverse().find((item) => at >= item.start);
    if (bucket) bucket.count += 1;
  });
  return { total, buckets, cameras: [...cameras].sort((a, b) => b[1] - a[1]) };
}
