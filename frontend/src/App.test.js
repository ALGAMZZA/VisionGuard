import { render, screen } from '@testing-library/react';
import App from './App';

test('renders the dashboard', () => {
  render(<App />);
  const linkElement = screen.getByRole('heading', { name: '통합 관제 대시보드' });
  expect(linkElement).toBeInTheDocument();
});
