import { NavLink } from 'react-router-dom';
import {
  FiGrid,
  FiMenu,
  FiMapPin,
  FiRadio,
  FiTrendingUp,
} from 'react-icons/fi';
import './Sidebar.css';

const menuItems = [
  { path: '/', label: '대시보드', icon: FiGrid, end: true },
  { path: '/alerts', label: '알림 이력', icon: FiRadio },
  { path: '/risk-heatmap', label: '위험구역 히트맵', icon: FiTrendingUp },
  { path: '/live-map', label: '실시간 도면 관제', icon: FiMapPin },
];

function Sidebar({ isExpanded, onToggle }) {
  return (
    <aside className={`sidebar${isExpanded ? ' sidebar--expanded' : ''}`}>
      <div className="sidebar__top">
        <button
          className="sidebar__toggle"
          type="button"
          onClick={onToggle}
          aria-label={isExpanded ? '사이드바 축소' : '사이드바 펼치기'}
          aria-expanded={isExpanded}
        >
          <FiMenu aria-hidden="true" />
        </button>
      </div>

      <nav className="sidebar__nav" aria-label="주요 메뉴">
        {menuItems.map(({ path, label, icon: Icon, end }) => (
          <NavLink
            key={path}
            to={path}
            end={end}
            className={({ isActive }) =>
              `sidebar__menu-item${isActive ? ' sidebar__menu-item--active' : ''}`
            }
          >
            <Icon className="sidebar__menu-icon" aria-hidden="true" />
            <span className="sidebar__menu-label">{label}</span>
            {!isExpanded && (
              <span className="sidebar__tooltip" role="tooltip">
                {label}
              </span>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

export default Sidebar;
