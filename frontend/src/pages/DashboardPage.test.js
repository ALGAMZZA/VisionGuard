import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import DashboardPage from './DashboardPage';
import { getLatestAnalysis, getRiskEvents } from '../api/visionGuardApi';

jest.mock('../api/visionGuardApi', () => ({ CAMERA_IDS: ['camera-1', 'camera-2'], getLatestAnalysis: jest.fn(), getRiskEvents: jest.fn() }));
beforeEach(() => {
  jest.clearAllMocks();
  getRiskEvents.mockResolvedValue({ content: [{ id: 7, cameraId: 'camera-2', level: 'DANGER', capturedAt: new Date().toISOString() }] });
});

test('uses latest analysis, distinguishes missing data, and filters recent history by camera', async () => {
  getLatestAnalysis.mockImplementation((id) => id === 'camera-1' ? Promise.reject({ response: { status: 404 } }) : Promise.resolve({
    cameraId: id, streamId: 'stream-2', aiMode: 'mock', capturedAt: '2020-01-01T00:00:00Z',
    prediction: { overall_risk: 'DANGER', detections: [], risks: [{ level: 'DANGER', score: 87, distance_px: 42, person_track_id: 0, forklift_track_id: 3, time_to_closest_approach_s: null }] },
  }));
  const { unmount } = render(<MemoryRouter><DashboardPage /></MemoryRouter>);
  expect(await screen.findByText('87 / 100')).toBeInTheDocument();
  expect(screen.getByText('42 px')).toBeInTheDocument();
  expect(screen.getByText('분석 데이터 대기 중')).toBeInTheDocument();
  expect(screen.getByText('갱신 지연 · 마지막 분석 결과입니다.')).toBeInTheDocument();
  expect(screen.getByText('0 / 3')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'camera-2' }));
  await waitFor(() => expect(getRiskEvents).toHaveBeenLastCalledWith({ cameraId: 'camera-2', size: 4 }, expect.anything()));
  expect(await screen.findByRole('link', { name: /DANGER|위험/ })).toHaveAttribute('href', '/alerts?eventId=7');
  const signal = getLatestAnalysis.mock.calls[0][1].signal;
  unmount();
  expect(signal.aborted).toBe(true);
});

test('connection failures are not displayed as safe', async () => {
  getLatestAnalysis.mockRejectedValue(new Error('offline'));
  render(<MemoryRouter><DashboardPage /></MemoryRouter>);
  expect(await screen.findAllByText('서버에 연결할 수 없습니다.')).toHaveLength(2);
  expect(screen.queryByText('안전')).not.toBeInTheDocument();
});
