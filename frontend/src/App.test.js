import { render, screen } from '@testing-library/react';
import App from './App';
import { getLatestAnalysis, getRiskEvents } from './api/visionGuardApi';

jest.mock('./api/visionGuardApi', () => ({
  CAMERA_IDS: ['camera-1', 'camera-2'],
  getLatestAnalysis: jest.fn(() => new Promise(() => {})),
  getRiskEvents: jest.fn(() => new Promise(() => {})),
}));

test('renders the dashboard', () => {
  getLatestAnalysis.mockImplementation(() => new Promise(() => {}));
  getRiskEvents.mockImplementation(() => new Promise(() => {}));
  render(<App />);
  const linkElement = screen.getByRole('heading', { name: '통합 관제 대시보드' });
  expect(linkElement).toBeInTheDocument();
});
