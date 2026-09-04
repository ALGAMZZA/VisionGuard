import { useState } from 'react';
import { Link } from 'react-router-dom';
import { FiAlertTriangle, FiBell, FiChevronRight } from 'react-icons/fi';
import { alerts } from '../../data/alerts';
import visionGuardLogo from '../../assets/images/vision-guard-logo.png';
import './Header.css';

function VisionGuardLogo() {
  return (
    <img
      className="header__logo"
      src={visionGuardLogo}
      alt="Vision Guard"
    />
  );
}

function Header({ isSidebarExpanded }) {
  const [isNotificationOpen, setIsNotificationOpen] = useState(false);
  const unreadCount = alerts.filter((alert) => !alert.isRead).length;

  return (
    <header className={`header${isSidebarExpanded ? ' header--sidebar-expanded' : ''}`}>
      <VisionGuardLogo />

      <div className="header__notification-area">
        <button className="header__notification" type="button" aria-label="알림 확인" aria-expanded={isNotificationOpen} onClick={() => setIsNotificationOpen((current) => !current)}>
          <FiBell aria-hidden="true" />
          {unreadCount > 0 && <span className="header__notification-count">{unreadCount}</span>}
        </button>

        {isNotificationOpen && (
          <section className="notification-popover" aria-label="최근 알림">
            <div className="notification-popover__header"><div><strong>최근 알림</strong><span>미확인 {unreadCount}건</span></div><button type="button" onClick={() => setIsNotificationOpen(false)}>닫기</button></div>
            <div className="notification-popover__list">
              {alerts.slice(0, 4).map((alert) => (
                <Link className={`notification-item notification-item--${alert.levelKey}${!alert.isRead ? ' is-unread' : ''}`} to={`/alerts?alert=${alert.id}`} key={alert.id} onClick={() => setIsNotificationOpen(false)}>
                  <span className="notification-item__icon"><FiAlertTriangle /></span>
                  <div><strong>{alert.level}</strong><p>{alert.cctv} · {alert.location}</p><time>{alert.date} {alert.time}</time></div>
                  <FiChevronRight className="notification-item__arrow" />
                </Link>
              ))}
            </div>
            <Link className="notification-popover__footer" to="/alerts" onClick={() => setIsNotificationOpen(false)}>알림 이력 전체보기 <FiChevronRight /></Link>
          </section>
        )}
      </div>
    </header>
  );
}

export default Header;
