import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AlertHistoryPage from './AlertHistoryPage';
import { getRiskEvent, getRiskEvents } from '../api/visionGuardApi';
import { downloadRiskEvents } from '../utils/exportRiskEvents';

jest.mock('../utils/exportRiskEvents', () => ({ downloadRiskEvents: jest.fn() }));

jest.mock('../api/visionGuardApi', () => ({ CAMERA_IDS: ['camera-1', 'camera-2'], getRiskEvent: jest.fn(), getRiskEvents: jest.fn() }));
beforeEach(() => jest.clearAllMocks());

test('renders server detail with nullable tracking IDs, pixel units, and pagination', async () => {
  const event = { id: 7, cameraId: 'camera-1', capturedAt: '2026-09-08T00:00:00Z', level: 'DANGER', status: 'LEGACY', personTrackId: null };
  getRiskEvents.mockResolvedValue({ content: [event], page: 0, totalPages: 2, totalElements: 21 });
  getRiskEvent.mockResolvedValue({ event, prediction: { overall_risk: 'WARNING', risks: [{ level: 'WARNING', score: 64, distance_px: 120, future_distance_px: 80, time_to_closest_approach_s: null, reason: '접근 중' }] } });
  render(<MemoryRouter><AlertHistoryPage /></MemoryRouter>);
  expect(await screen.findByText('120 px')).toBeInTheDocument();
  expect(screen.getByText('64 / 100')).toBeInTheDocument();
  expect(screen.getByText('전체 21건')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '다음' }));
  await waitFor(() => expect(getRiskEvents).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1 }), expect.anything()));
});

test('empty list does not request an undefined event', async () => {
  getRiskEvents.mockResolvedValue({ content: [], page: 0, totalPages: 0, totalElements: 0 });
  render(<MemoryRouter><AlertHistoryPage /></MemoryRouter>);
  expect(await screen.findByText('조회된 위험 이벤트가 없습니다.')).toBeInTheDocument();
  expect(getRiskEvent).not.toHaveBeenCalled();
  expect(screen.getByRole('button', { name: '엑셀 다운로드' })).toBeDisabled();
});

test('exports selected filters and allows retry after a failure', async () => {
  getRiskEvents.mockResolvedValue({ content: [], page: 0, totalPages: 1, totalElements: 1 });
  downloadRiskEvents.mockRejectedValueOnce(new Error('다운로드 오류')).mockResolvedValueOnce(1);
  render(<MemoryRouter><AlertHistoryPage /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText('발생 날짜'), { target: { value: '2026-09-13' } });
  fireEvent.change(screen.getByLabelText('카메라'), { target: { value: 'camera-1' } });
  const button = screen.getByRole('button', { name: '엑셀 다운로드' });
  await waitFor(() => expect(button).toBeEnabled());
  fireEvent.click(button);
  expect(await screen.findByRole('alert')).toHaveTextContent('엑셀 다운로드 실패');
  expect(downloadRiskEvents).toHaveBeenCalledWith({ date: '2026-09-13', cameraId: 'camera-1' }, { signal: expect.any(AbortSignal) });
  fireEvent.click(screen.getByRole('button', { name: '엑셀 다운로드' }));
  expect(await screen.findByText('1건의 엑셀 다운로드를 시작했습니다.')).toBeInTheDocument();
});

test('deep links request detail even outside the current page and show Problem Detail', async () => {
  getRiskEvents.mockResolvedValue({ content: [], page: 0, totalPages: 0, totalElements: 0 });
  getRiskEvent.mockRejectedValue({ response: { status: 404, data: { detail: '이벤트가 없습니다.' } } });
  render(<MemoryRouter initialEntries={['/alerts?eventId=99']}><AlertHistoryPage /></MemoryRouter>);
  expect(await screen.findByRole('alert')).toHaveTextContent('이벤트가 없습니다.');
  expect(getRiskEvent).toHaveBeenCalledWith(99, expect.anything());
});
