package com.algamza.visionguard.analysis;

import org.springframework.data.jpa.repository.JpaRepository;
import java.util.Optional;

public interface ProcessedFrameRepository extends JpaRepository<ProcessedFrame, String> {
    Optional<ProcessedFrame> findFirstByScopeKeyOrderByCapturedAtDesc(String scopeKey);
}
