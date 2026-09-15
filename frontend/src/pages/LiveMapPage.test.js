import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import LiveMapPage from './LiveMapPage';
import useLatestAnalyses from '../hooks/useLatestAnalyses';
jest.mock('../hooks/useLatestAnalyses');

test('preserves the floor plan and telemetry layout while filtering API objects', () => {
  useLatestAnalyses.mockReturnValue([{ id: 'camera-2', analysis: { capturedAt: '2026-09-14T00:00:00Z', aiMode: 'http', prediction: {
    image_width: 640, image_height: 480, overall_risk: 'WARNING', detections: [
      { class_name: 'person', track_id: 5, bbox: { x1: 10, y1: 20, x2: 40, y2: 80 } },
      { class_name: 'forklift', track_id: 9, bbox: { x1: 100, y1: 120, x2: 200, y2: 240 } },
    ],
  } } }]);
  const { container } = render(<MemoryRouter><LiveMapPage /></MemoryRouter>);
  expect(screen.getByLabelText('실시간 공장 도면')).toBeInTheDocument();
  expect(container.querySelector('.live-control__layout > .live-map-panel')).toBeInTheDocument();
  expect(container.querySelector('.live-control__layout > .telemetry')).toBeInTheDocument();
  expect(container.querySelectorAll('.telemetry-object')).toHaveLength(2);
  expect(screen.getByText('camera-2 · 영상 좌표 (25, 80)')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '지게차' }));
  expect(container.querySelectorAll('.telemetry-object')).toHaveLength(1);
  expect(screen.getByText('camera-2 · 영상 좌표 (150, 240)')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'CAM-02' })).toHaveAttribute('href', '/?cctv=2');
});
