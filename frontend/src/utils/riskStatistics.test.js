import { loadStatisticsEvents, statisticsRange, summarizeEvents } from './riskStatistics';
import { getRiskEvents } from '../api/visionGuardApi';
jest.mock('../api/visionGuardApi', () => ({ getRiskEvents: jest.fn() }));

test('loads all pages and deduplicates events before aggregation', async () => {
  getRiskEvents.mockResolvedValueOnce({ content: [{ id: 1 }], totalPages: 2 }).mockResolvedValueOnce({ content: [{ id: 1 }, { id: 2 }], totalPages: 2 });
  const range = { from: '2026-09-01T00:00:00Z', to: '2026-09-14T00:00:00Z' };
  expect(await loadStatisticsEvents(range)).toEqual([{ id: 1 }, { id: 2 }]);
  expect(getRiskEvents).toHaveBeenLastCalledWith({ ...range, page: 1, size: 100 }, { signal: undefined });
});

test('uses local calendar dates and applies risk filter to both chart and camera counts', () => {
  const now = new Date(2026, 8, 14, 12);
  const range = statisticsRange('week', now);
  expect(new Date(range.from).getDate()).toBe(8);
  expect(new Date(range.from).getHours()).toBe(0);
  const events = [
    { cameraId: 'camera-2', level: 'DANGER', capturedAt: new Date(2026, 8, 14, 10).toISOString() },
    { cameraId: 'camera-1', level: 'WARNING', capturedAt: new Date(2026, 8, 8, 0).toISOString() },
    { cameraId: 'camera-1', level: 'DANGER', capturedAt: new Date(2026, 8, 7, 23).toISOString() },
  ];
  const result = summarizeEvents(events, 'week', range, 'DANGER');
  expect(result.total).toBe(1);
  expect(result.cameras).toEqual([['camera-2', 1]]);
  expect(result.buckets[6]).toMatchObject({ label: '9/14', count: 1 });
  expect(result.buckets.reduce((sum, bucket) => sum + bucket.count, 0)).toBe(1);
});
