import apiClient from './client';
import { analyzeFrame, endStream, getLatestAnalysis, getRiskEvent, getRiskEvents } from './visionGuardApi';

jest.mock('./client', () => ({ __esModule: true, default: { post: jest.fn(), get: jest.fn() } }));
beforeEach(() => jest.clearAllMocks());

test('analysis sends one image and exact metadata without forcing Content-Type', async () => {
  const response = { eventIds: [1, 2], prediction: { overall_risk: 'WARNING' } };
  apiClient.post.mockResolvedValue({ data: response });
  const file = new File(['image'], 'frame.jpg', { type: 'image/jpeg' });
  const frame = { file, cameraId: 'camera-1', frameId: '0', capturedAt: '2026-09-08T09:00:00+09:00', streamId: 'stream-a', fps: 10 };
  expect(await analyzeFrame(frame)).toBe(response);
  const [url, body, config] = apiClient.post.mock.calls[0];
  expect(url).toBe('/analyses');
  expect(body.get('file')).toBe(file);
  for (const key of ['cameraId', 'frameId', 'capturedAt', 'streamId', 'fps']) expect(body.get(key)).toBe(String(frame[key]));
  expect(config.headers).toBeUndefined();
});

test('optional analysis fields remain omitted', async () => {
  apiClient.post.mockResolvedValue({ data: {} });
  await analyzeFrame({ file: new Blob(['image']), cameraId: 'camera-1', frameId: '1', capturedAt: '2026-09-08T00:00:00Z' });
  const body = apiClient.post.mock.calls[0][1];
  expect(body.has('fps')).toBe(false);
  expect(body.has('streamId')).toBe(false);
});

test('latest analysis requests the selected camera', async () => {
  const data = { cameraId: 'camera-1', prediction: { overall_risk: 'SAFE' } };
  apiClient.get.mockResolvedValue({ data });
  expect(await getLatestAnalysis('camera-1')).toBe(data);
  expect(apiClient.get).toHaveBeenCalledWith('/analyses/latest', {
    params: { cameraId: 'camera-1' }, signal: undefined,
  });
});

test('list preserves pagination and only sends supported query parameters', async () => {
  const data = { content: [], page: 0, totalPages: 0, totalElements: 0, size: 20 };
  apiClient.get.mockResolvedValue({ data });
  const from = '2026-09-08T09:00:00+09:00';
  expect(await getRiskEvents({ from, level: 'DANGER' })).toBe(data);
  expect(apiClient.get).toHaveBeenCalledWith('/risk-events', { params: { cameraId: undefined, from, to: undefined, page: 0, size: 20 }, signal: undefined });
});

test('detail and stream end preserve server response and end timestamp', async () => {
  const detail = { event: { id: 2 }, prediction: { risks: [] } };
  apiClient.get.mockResolvedValue({ data: detail });
  expect(await getRiskEvent(2)).toBe(detail);
  expect(apiClient.get).toHaveBeenCalledWith('/risk-events/2', { signal: undefined });
  const payload = { cameraId: 'camera-1', streamId: 'stream-a', endedAt: '2026-09-08T00:00:00Z' };
  apiClient.post.mockResolvedValue({ data: { closedEventIds: [2] } });
  expect(await endStream(payload)).toEqual({ closedEventIds: [2] });
  expect(apiClient.post).toHaveBeenCalledWith('/streams/end', payload, { signal: undefined });
});

test('server errors are not swallowed', async () => {
  const error = { response: { status: 409, data: { detail: 'Conflict' } } };
  apiClient.post.mockRejectedValue(error);
  await expect(endStream({})).rejects.toBe(error);
});
