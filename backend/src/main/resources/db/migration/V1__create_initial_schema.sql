-- Schema corresponding to the existing Hibernate-managed VisionGuard database.
-- Existing databases matching this schema must be explicitly baselined at version 1.
CREATE TABLE risk_events (
    id BIGINT NOT NULL AUTO_INCREMENT,
    camera_id VARCHAR(100) NOT NULL,
    frame_id VARCHAR(100) NOT NULL,
    captured_at ${instantType} NOT NULL,
    created_at ${instantType} NOT NULL,
    level ENUM('DANGER', 'SAFE', 'WARNING') NOT NULL,
    prediction_json ${jsonTextType} NOT NULL,
    stream_id VARCHAR(100),
    scope_key VARCHAR(64),
    person_track_id INT,
    forklift_track_id INT,
    last_seen_at ${instantType},
    ended_at ${instantType},
    frame_count BIGINT,
    end_reason VARCHAR(32),
    PRIMARY KEY (id)
);
CREATE INDEX idx_risk_camera_captured ON risk_events (camera_id, captured_at);
CREATE INDEX idx_risk_captured ON risk_events (captured_at);
CREATE INDEX idx_risk_active ON risk_events (scope_key, ended_at);

CREATE TABLE processed_frames (
    id VARCHAR(64) NOT NULL,
    scope_key VARCHAR(64) NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    captured_at ${instantType} NOT NULL,
    response_json ${jsonTextType} NOT NULL,
    PRIMARY KEY (id)
);
CREATE INDEX idx_frame_scope_time ON processed_frames (scope_key, captured_at);

CREATE TABLE stream_completions (
    scope_key VARCHAR(64) NOT NULL,
    ended_at ${instantType} NOT NULL,
    response_json ${jsonTextType} NOT NULL,
    PRIMARY KEY (scope_key)
);
