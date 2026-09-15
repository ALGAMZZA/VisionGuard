import { fireEvent, render, screen, within } from '@testing-library/react';
import RiskHeatmapPage from './RiskHeatmapPage';
import { loadStatisticsEvents } from '../utils/riskStatistics';
jest.mock('../utils/riskStatistics', () => ({ ...jest.requireActual('../utils/riskStatistics'), loadStatisticsEvents: jest.fn() }));

test('keeps the map/chart/ranking layout and displays API totals in the existing ranking', async () => {
  loadStatisticsEvents.mockResolvedValue([
    { id: 1, cameraId: 'camera-2', level: 'DANGER', capturedAt: new Date().toISOString() },
    { id: 2, cameraId: 'camera-2', level: 'WARNING', capturedAt: new Date().toISOString() },
  ]);
  const { container } = render(<RiskHeatmapPage />);
  expect(screen.getByLabelText('공장 도면')).toBeInTheDocument();
  expect(container.querySelector('.risk-heatmap__main > .heatmap-panel')).toBeInTheDocument();
  expect(container.querySelector('.risk-heatmap__main > .heatmap-chart')).toBeInTheDocument();
  const ranking = within(container.querySelector('.hotspot-ranking'));
  expect(await ranking.findByText('camera-2')).toBeInTheDocument();
  expect(ranking.getByText('2건')).toBeInTheDocument();
  fireEvent.change(screen.getByRole('combobox'), { target: { value: 'danger' } });
  expect(ranking.getByText('1건')).toBeInTheDocument();
  expect(container.querySelectorAll('.hotspot-rank__progress')).toHaveLength(1);
});
