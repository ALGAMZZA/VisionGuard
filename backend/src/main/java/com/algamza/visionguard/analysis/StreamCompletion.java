package com.algamza.visionguard.analysis;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "stream_completions")
public class StreamCompletion {
    @Id @Column(length = 64) private String scopeKey;
    @Column(nullable = false) private Instant endedAt;
    @Lob @Column(nullable = false, columnDefinition = "LONGTEXT") private String responseJson;
    protected StreamCompletion() {}
    public StreamCompletion(String scopeKey, Instant endedAt, String responseJson) {
        this.scopeKey = scopeKey; this.endedAt = endedAt; this.responseJson = responseJson;
    }
    public Instant getEndedAt() { return endedAt; }
    public String getResponseJson() { return responseJson; }
}
