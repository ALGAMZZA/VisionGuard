import { useState } from 'react';
import { BrowserRouter, Route, Routes } from 'react-router-dom';
import Header from './components/Header/Header';
import Sidebar from './components/Sidebar/Sidebar';
import AlertHistoryPage from './pages/AlertHistoryPage';
import DashboardPage from './pages/DashboardPage';
import LiveMapPage from './pages/LiveMapPage';
import RiskHeatmapPage from './pages/RiskHeatmapPage';
import './App.css';

function App() {
  const [isSidebarExpanded, setIsSidebarExpanded] = useState(false);

  return (
    <BrowserRouter>
      <div className={`app-shell${isSidebarExpanded ? ' app-shell--sidebar-expanded' : ''}`}>
        <Sidebar
          isExpanded={isSidebarExpanded}
          onToggle={() => setIsSidebarExpanded((current) => !current)}
        />
        <Header isSidebarExpanded={isSidebarExpanded} />
        <main className="app-content">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/alerts" element={<AlertHistoryPage />} />
            <Route path="/risk-heatmap" element={<RiskHeatmapPage />} />
            <Route path="/live-map" element={<LiveMapPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
