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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!isNotificationOpen) return undefined;
    const controller = new AbortController();
    setLoading(true);
    setError('');
    setRiskEvents([]);
    getRiskEvents({ size: 4 }, { signal: controller.signal })
      .then((data) => { if (!controller.signal.aborted) setRiskEvents(data.content); })
      .catch((err) => { if (!controller.signal.aborted) setError(getApiErrorMessage(err)); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [isNotificationOpen]);

  return (
    <header className={`header${isSidebarExpanded ? ' header--sidebar-expanded' : ''}`}>
      <VisionGuardLogo />

      <div className="header__notification-area">
        <button className="header__notification" type="button" aria-label="알림 확인" aria-expanded={isNotificationOpen} onClick={() => setIsNotificationOpen((current) => !current)}>
          <FiBell aria-hidden="true" />
        </button>

        {isNotificationOpen && (
          <section className="notification-popover" aria-label="최근 알림">
            <div className="notification-popover__header"><div><strong>최근 알림</strong><span>최근 위험 이벤트</span></div><button type="button" onClick={() => setIsNotificationOpen(false)}>닫기</button></div>
            <div className="notification-popover__list">
              {loading && <p role="status">불러오는 중입니다.</p>}
              {error && <p role="alert">{error}</p>}
              {!loading && !error && !riskEvents.length && <p>위험 이벤트가 없습니다.</p>}
              {riskEvents.map((event) => (
                <Link className={`notification-item notification-item--${event.level}`} to={`/alerts?eventId=${event.id}`} key={event.id} onClick={() => setIsNotificationOpen(false)}>
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
