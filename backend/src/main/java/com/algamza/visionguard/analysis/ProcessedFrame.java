package com.algamza.visionguard.analysis;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "processed_frames", indexes = @Index(name = "idx_frame_scope_time", columnList = "scopeKey,capturedAt"))
public class ProcessedFrame {
    // SHA-256 of cameraId/streamId/frameId gives a case-sensitive, bounded primary key.
    @Id @Column(length = 64) private String id;
    @Column(nullable = false, length = 64) private String scopeKey;
    @Column(nullable = false, length = 64) private String fingerprint;
    @Column(nullable = false) private Instant capturedAt;
    @Lob @Column(nullable = false, columnDefinition = "LONGTEXT") private String responseJson;
    protected ProcessedFrame() {}
    public ProcessedFrame(String id, String scopeKey, String fingerprint, Instant capturedAt, String responseJson) {
        this.id = id; this.scopeKey = scopeKey; this.fingerprint = fingerprint;
        this.capturedAt = capturedAt; this.responseJson = responseJson;
    }
    public String getFingerprint() { return fingerprint; }
    public Instant getCapturedAt() { return capturedAt; }
    public String getResponseJson() { return responseJson; }
}
