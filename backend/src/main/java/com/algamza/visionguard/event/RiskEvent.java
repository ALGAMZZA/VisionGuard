package com.algamza.visionguard.event;

import com.algamza.visionguard.ai.PredictionResult.RiskLevel;
import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "risk_events", indexes = {
        @Index(name = "idx_risk_camera_captured", columnList = "cameraId,capturedAt"),
        @Index(name = "idx_risk_captured", columnList = "capturedAt"),
        @Index(name = "idx_risk_active", columnList = "scopeKey,endedAt")})
public class RiskEvent {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;
    @Column(nullable = false, length = 100)
    private String cameraId;
    @Column(nullable = false, length = 100)
    private String frameId;
    @Column(nullable = false)
    private Instant capturedAt;
    @Column(nullable = false)
    private Instant createdAt;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 16)
    private RiskLevel level;
    @Lob @Column(nullable = false, columnDefinition = "LONGTEXT")
    private String predictionJson;

    // Nullable additions preserve events created before lifecycle tracking existed.
    @Column(length = 100) private String streamId;
    @Column(length = 64) private String scopeKey;
    private Integer personTrackId;
    private Integer forkliftTrackId;
    private Instant lastSeenAt;
    private Instant endedAt;
    private Long frameCount;
    @Column(length = 32) private String endReason;

    protected RiskEvent() {}
    public static RiskEvent start(String cameraId, String streamId, String scopeKey,
                                  String frameId, Instant at, Integer personId, Integer forkliftId,
                                  RiskLevel level, String json) {
        var event = new RiskEvent(cameraId, frameId, at, level, json);
        event.streamId = streamId;
        event.scopeKey = scopeKey;
        event.personTrackId = personId;
        event.forkliftTrackId = forkliftId;
        event.lastSeenAt = at;
        event.frameCount = 1L;
        return event;
    }
    public void observe(Instant at, RiskLevel observedLevel, String json) {
        lastSeenAt = at;
        frameCount++;
        if (observedLevel.ordinal() > level.ordinal()) level = observedLevel;
        predictionJson = json;
    }
    public void end(Instant at, String reason) { endedAt = at; endReason = reason; }
    public String getStreamId() { return streamId; }
    public String getScopeKey() { return scopeKey; }
    public Integer getPersonTrackId() { return personTrackId; }
    public Integer getForkliftTrackId() { return forkliftTrackId; }
    public Instant getLastSeenAt() { return lastSeenAt; }
    public Instant getEndedAt() { return endedAt; }
    public Long getFrameCount() { return frameCount; }
    public String getEndReason() { return endReason; }
    public String getStatus() { return scopeKey == null ? "LEGACY" : endedAt == null ? "OPEN" : "CLOSED"; }

    public RiskEvent(String cameraId, String frameId, Instant capturedAt,
                     RiskLevel level, String predictionJson) {
        this.cameraId = cameraId;
        this.frameId = frameId;
        this.capturedAt = capturedAt;
        this.createdAt = Instant.now();
        this.level = level;
        this.predictionJson = predictionJson;
    }
    public Long getId() { return id; }
    public String getCameraId() { return cameraId; }
    public String getFrameId() { return frameId; }
    public Instant getCapturedAt() { return capturedAt; }
    public Instant getCreatedAt() { return createdAt; }
    public RiskLevel getLevel() { return level; }
    public String getPredictionJson() { return predictionJson; }
}
