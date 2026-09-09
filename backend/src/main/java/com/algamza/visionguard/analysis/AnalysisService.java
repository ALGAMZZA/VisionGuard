package com.algamza.visionguard.analysis;

import com.algamza.visionguard.ai.AiClient;
import com.algamza.visionguard.ai.AiUnavailableException;
import com.algamza.visionguard.ai.PredictionResult;
import com.algamza.visionguard.event.RiskEvent;
import com.algamza.visionguard.event.RiskEventRepository;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.nio.charset.StandardCharsets;
import java.nio.ByteBuffer;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;
import static com.algamza.visionguard.ai.PredictionResult.RiskLevel.SAFE;

@Service
public class AnalysisService {
    private final AiClient ai;
    private final RiskEventRepository events;
    private final ProcessedFrameRepository frames;
    private final StreamCompletionRepository completions;
    private final ObjectMapper mapper;
    private final String cameraId;
    private final String mode;
    private final TransactionTemplate transaction;
    private final long maxGapMs;

    public AnalysisService(AiClient ai, RiskEventRepository events, ProcessedFrameRepository frames,
                           StreamCompletionRepository completions, ObjectMapper mapper, PlatformTransactionManager transactionManager,
                           @Value("${visionguard.camera-id}") String cameraId,
                           @Value("${visionguard.ai.mode}") String mode,
                           @Value("${visionguard.events.max-gap-ms:2000}") long maxGapMs) {
        if (maxGapMs <= 0) throw new IllegalArgumentException("max-gap-ms must be positive");
        this.ai = ai; this.events = events; this.frames = frames; this.mapper = mapper;
        this.completions = completions;
        this.cameraId = cameraId; this.mode = mode; this.maxGapMs = maxGapMs;
        this.transaction = new TransactionTemplate(transactionManager);
    }

    // Single backend instance: keep the monitor until the transaction has COMMITTED.
    // A retry therefore sees the stored response before it can advance the AI tracker.
    public synchronized AnalysisResponse analyze(byte[] image, String cameraId, String streamId,
                                                 String frameId, Instant capturedAt, double fps) {
        if (!this.cameraId.equals(cameraId))
            throw new IllegalArgumentException("현재 서버는 카메라 " + this.cameraId + "만 지원합니다.");
        var at = capturedAt.truncatedTo(ChronoUnit.MICROS);
        var scope = hash(cameraId, streamId);
        var key = hash(cameraId, streamId, frameId);
        var fingerprint = hash(hexDigest(image), at.toString(), Double.toString(fps));
        return transaction.execute(status -> {
            var previous = frames.findById(key);
            if (previous.isPresent()) {
                if (!previous.get().getFingerprint().equals(fingerprint))
                    throw conflict("같은 프레임 ID에 다른 이미지·촬영 시각·fps를 사용할 수 없습니다.");
                return mapper.readValue(previous.get().getResponseJson(), AnalysisResponse.class);
            }
            if (completions.existsById(scope))
                throw conflict("종료된 스트림에는 새 프레임을 추가할 수 없습니다. 새로운 streamId를 사용하세요.");
            frames.findFirstByScopeKeyOrderByCapturedAtDesc(scope).ifPresent(last -> {
                if (!at.isAfter(last.getCapturedAt()))
                    throw conflict("새 프레임의 촬영 시각은 이전 프레임보다 늦어야 합니다.");
            });
            var prediction = ai.predict(image, frameId, fps);
            var current = collectRisks(prediction);
            var active = new HashMap<Pair, RiskEvent>();
            for (var event : events.findByEndedAtIsNullAndScopeKeyIsNotNull()) {
                if (!cameraId.equals(event.getCameraId())) continue;
                if (!scope.equals(event.getScopeKey())) {
                    event.end(event.getLastSeenAt(), "STREAM_CHANGED");
                } else if (at.isAfter(event.getLastSeenAt().plusMillis(maxGapMs))) {
                    event.end(event.getLastSeenAt().plusMillis(maxGapMs), "FRAME_GAP");
                } else {
                    var pair = new Pair(event.getPersonTrackId(), event.getForkliftTrackId());
                    if (!current.containsKey(pair)) event.end(at, "NOT_OBSERVED");
                    else active.put(pair, event);
                }
            }
            var ids = new ArrayList<Long>();
            for (var entry : current.entrySet()) {
                var risk = entry.getValue();
                // Store only this pair's risk; retain detections to preserve the risk indices.
                var snapshot = new PredictionResult(prediction.frame_id(), prediction.image_width(),
                        prediction.image_height(), prediction.detections(), List.of(risk),
                        risk.level(), prediction.processing_time_ms());
                var json = mapper.writeValueAsString(snapshot);
                var event = active.get(entry.getKey());
                if (event == null) {
                    event = RiskEvent.start(cameraId, streamId, scope, frameId, at,
                            risk.person_track_id(), risk.forklift_track_id(), risk.level(), json);
                    if (risk.person_track_id() == null || risk.forklift_track_id() == null)
                        event.end(at, "UNTRACKED");
                    events.save(event);
                } else event.observe(at, risk.level(), json);
                ids.add(event.getId());
            }
            var result = new AnalysisResponse(ids.isEmpty() ? null : ids.get(0), List.copyOf(ids),
                    cameraId, streamId, at, mode, prediction);
            frames.save(new ProcessedFrame(key, scope, fingerprint, at, mapper.writeValueAsString(result)));
            return result;
        });
    }

    // Shares analyze's monitor, so completion cannot race a pending frame commit.
    public synchronized StreamEndResponse endStream(String cameraId, String streamId, Instant endedAt) {
        if (!this.cameraId.equals(cameraId))
            throw new IllegalArgumentException("현재 서버는 카메라 " + this.cameraId + "만 지원합니다.");
        var scope = hash(cameraId, streamId);
        var at = endedAt.truncatedTo(ChronoUnit.MICROS);
        return transaction.execute(status -> {
            var previous = completions.findById(scope);
            if (previous.isPresent()) {
                if (!previous.get().getEndedAt().equals(at))
                    throw conflict("이미 종료된 스트림의 종료 시각을 변경할 수 없습니다.");
                return mapper.readValue(previous.get().getResponseJson(), StreamEndResponse.class);
            }
            var last = frames.findFirstByScopeKeyOrderByCapturedAtDesc(scope).orElseThrow(() ->
                    new ResponseStatusException(HttpStatus.NOT_FOUND, "처리된 프레임이 없는 스트림입니다."));
            if (at.isBefore(last.getCapturedAt()))
                throw conflict("종료 시각은 마지막 프레임 촬영 시각보다 빠를 수 없습니다.");
            var ids = new ArrayList<Long>();
            for (var event : events.findByScopeKeyAndEndedAtIsNull(scope)) {
                event.end(at, "STREAM_ENDED");
                ids.add(event.getId());
            }
            ids.sort(Long::compareTo);
            var result = new StreamEndResponse(cameraId, streamId, at, List.copyOf(ids));
            completions.save(new StreamCompletion(scope, at, mapper.writeValueAsString(result)));
            return result;
        });
    }
    public record StreamEndResponse(String cameraId, String streamId, Instant endedAt, List<Long> closedEventIds) {}

    private Map<Pair, PredictionResult.Risk> collectRisks(PredictionResult prediction) {
        if (prediction == null || prediction.overall_risk() == null || prediction.risks() == null
                || prediction.detections() == null) throw new AiUnavailableException();
        var result = new LinkedHashMap<Pair, PredictionResult.Risk>();
        for (var risk : prediction.risks()) {
            if (risk == null || risk.level() == null) throw new AiUnavailableException();
            if (risk.level() == SAFE) continue;
            // Negative synthetic keys only group duplicates within this frame, never across frames.
            var pair = new Pair(risk.person_track_id() == null ? -risk.person_index() - 1 : risk.person_track_id(),
                    risk.forklift_track_id() == null ? -risk.forklift_index() - 1 : risk.forklift_track_id());
            result.merge(pair, risk, (a, b) -> a.level().ordinal() >= b.level().ordinal() ? a : b);
        }
        var highest = result.values().stream().map(PredictionResult.Risk::level)
                .max(Comparator.naturalOrder()).orElse(SAFE);
        if (highest != prediction.overall_risk()) throw new AiUnavailableException();
        return result;
    }
    private static ResponseStatusException conflict(String message) {
        return new ResponseStatusException(HttpStatus.CONFLICT, message);
    }
    private static String hash(String... values) {
        var digest = digest();
        for (var value : values) {
            var bytes = value.getBytes(StandardCharsets.UTF_8);
            digest.update(ByteBuffer.allocate(4).putInt(bytes.length).array());
            digest.update(bytes);
        }
        return HexFormat.of().formatHex(digest.digest());
    }
    private static String hexDigest(byte[] value) { return HexFormat.of().formatHex(digest().digest(value)); }
    private static MessageDigest digest() {
        try { return MessageDigest.getInstance("SHA-256"); }
        catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
    private record Pair(Integer person, Integer forklift) {}
    public record AnalysisResponse(Long eventId, List<Long> eventIds, String cameraId, String streamId,
                                   Instant capturedAt, String aiMode, PredictionResult prediction) {}
}
