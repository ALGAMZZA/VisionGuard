package com.algamza.visionguard.event;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface RiskEventRepository extends JpaRepository<RiskEvent, Long>, JpaSpecificationExecutor<RiskEvent> {
    java.util.List<RiskEvent> findByEndedAtIsNullAndScopeKeyIsNotNull();
    java.util.List<RiskEvent> findByScopeKeyAndEndedAtIsNull(String scopeKey);
}
