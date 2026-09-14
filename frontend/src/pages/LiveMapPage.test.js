import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import LiveMapPage from './LiveMapPage';
import useLatestAnalyses from '../hooks/useLatestAnalyses';
jest.mock('../hooks/useLatestAnalyses');

test('renders server pixel coordinates and filters detected classes', () => {
  useLatestAnalyses.mockReturnValue([{ id: 'camera-2', analysis: { capturedAt: '2026-09-14T00:00:00Z', aiMode: 'http', prediction: {
    image_width: 640, image_height: 480, overall_risk: 'WARNING', detections: [
      { class_name: 'person', track_id: 5, bbox: { x1: 10, y1: 20, x2: 40, y2: 80 } },
      { class_name: 'forklift', track_id: 9, bbox: { x1: 100, y1: 120, x2: 200, y2: 240 } },
    ],
  } } }]);
  render(<MemoryRouter><LiveMapPage /></MemoryRouter>);
  const svg = screen.getByLabelText('camera-2 탐지 객체 위치');
  expect(svg).toHaveAttribute('viewBox', '0 0 640 480');
  expect(svg.querySelector('rect')).toHaveAttribute('width', '30');
  fireEvent.click(screen.getByRole('button', { name: '지게차' }));
  expect(svg.querySelectorAll('rect')).toHaveLength(1);
  expect(svg.querySelector('rect')).toHaveAttribute('x', '100');
  expect(screen.getByRole('link', { name: 'camera-2' })).toHaveAttribute('href', '/?cameraId=camera-2');
});
