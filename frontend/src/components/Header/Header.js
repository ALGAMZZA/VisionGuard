import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiAlertTriangle, FiBell, FiChevronRight } from 'react-icons/fi';
import { getRiskEvents } from '../../api/visionGuardApi';
import { getApiErrorMessage } from '../../api/client';
import { formatDateTime, riskLevelLabels } from '../../utils/riskEvent';
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
  const [riskEvents, setRiskEvents] = useState([]);
  const [lastReadId, setLastReadId] = useState(() => Number(window.localStorage.getItem('visionguard.lastReadEventId') || 0));
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    async function refreshNotifications() {
      if (!riskEvents.length) setLoading(true);
      try {
        const data = await getRiskEvents({ size: 20 });
        if (active) {
          const content = data.content || [];
          setRiskEvents(content);
          setError('');
          if (window.localStorage.getItem('visionguard.lastReadEventId') === null && content.length) {
            const newestId = Math.max(...content.map((event) => Number(event.id) || 0));
            window.localStorage.setItem('visionguard.lastReadEventId', String(newestId));
            setLastReadId(newestId);
          }
        }
      } catch (err) {
        if (active) setError(getApiErrorMessage(err));
      } finally {
        if (active) setLoading(false);
      }
    }
    refreshNotifications();
    const timer = window.setInterval(refreshNotifications, 5000);
    return () => { active = false; window.clearInterval(timer); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const unreadCount = riskEvents.filter((event) => Number(event.id) > lastReadId).length;

  function toggleNotifications() {
    const opening = !isNotificationOpen;
    setIsNotificationOpen(opening);
    if (opening && riskEvents.length) {
      const newestId = Math.max(...riskEvents.map((event) => Number(event.id) || 0));
      window.localStorage.setItem('visionguard.lastReadEventId', String(newestId));
      setLastReadId(newestId);
    }
  }

  return (
    <header className={`header${isSidebarExpanded ? ' header--sidebar-expanded' : ''}`}>
      <VisionGuardLogo />

      <div className="header__notification-area">
        <button className="header__notification" type="button" aria-label={`알림 확인${unreadCount ? `, 읽지 않은 알림 ${unreadCount}개` : ''}`} aria-expanded={isNotificationOpen} onClick={toggleNotifications}>
          <FiBell aria-hidden="true" />
          {unreadCount > 0 && <span className="header__notification-count">{unreadCount > 99 ? '99+' : unreadCount}</span>}
        </button>

        {isNotificationOpen && (
          <section className="notification-popover" aria-label="최근 알림">
            <div className="notification-popover__header"><div><strong>최근 알림</strong><span>최근 위험 이벤트</span></div><button type="button" onClick={() => setIsNotificationOpen(false)}>닫기</button></div>
            <div className="notification-popover__list">
              {loading && <p role="status">불러오는 중입니다.</p>}
              {error && <p role="alert">{error}</p>}
              {!loading && !error && !riskEvents.length && <p>위험 이벤트가 없습니다.</p>}
              {riskEvents.map((event) => (
                <Link className={`notification-item notification-item--${event.level}${Number(event.id) > lastReadId ? ' is-unread' : ''}`} to={`/alerts?eventId=${event.id}`} key={event.id} onClick={() => setIsNotificationOpen(false)}>
                  <span className="notification-item__icon"><FiAlertTriangle /></span>
                  <div><strong>{riskLevelLabels[event.level] || event.level}</strong><p>{event.cameraId}</p><time>{formatDateTime(event.capturedAt)}</time></div>
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
