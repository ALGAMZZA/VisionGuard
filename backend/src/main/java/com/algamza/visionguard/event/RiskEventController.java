package com.algamza.visionguard.event;

import com.algamza.visionguard.ai.PredictionResult;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;

import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.List;

@Tag(name = "위험 이력")
@RestController
@RequestMapping("/api/risk-events")
public class RiskEventController {
    private final RiskEventRepository events;
    private final ObjectMapper mapper;
    public RiskEventController(RiskEventRepository events, ObjectMapper mapper) {
        this.events = events; this.mapper = mapper;
    }

    @Operation(summary = "위험 이력 목록", description = "위험 시작 시각으로 기간 필터링하며 양 끝 시각을 포함합니다. "
            + "촬영 시각과 ID 내림차순. page는 0부터, size는 1~100입니다.")
    @GetMapping
    public EventPage list(@RequestParam(required = false) String cameraId,
                          @RequestParam(required = false) Instant from,
                          @RequestParam(required = false) Instant to,
                          @RequestParam(defaultValue = "0") int page,
                          @RequestParam(defaultValue = "20") int size) {
        if (page < 0 || size < 1 || size > 100 || (from != null && to != null && from.isAfter(to))) {
            throw new IllegalArgumentException("페이지 또는 조회 기간이 올바르지 않습니다.");
        }
        Specification<RiskEvent> spec = (root, query, cb) -> {
            var predicates = new java.util.ArrayList<jakarta.persistence.criteria.Predicate>();
            if (cameraId != null) predicates.add(cb.equal(root.get("cameraId"), cameraId));
            if (from != null) predicates.add(cb.greaterThanOrEqualTo(root.get("capturedAt"), from));
            if (to != null) predicates.add(cb.lessThanOrEqualTo(root.get("capturedAt"), to));
            return cb.and(predicates.toArray(jakarta.persistence.criteria.Predicate[]::new));
        };
        var result = events.findAll(spec, PageRequest.of(page, size,
                Sort.by(Sort.Direction.DESC, "capturedAt", "id")));
        return new EventPage(result.stream().map(EventSummary::of).toList(),
                page, size, result.getTotalElements(), result.getTotalPages());
    }

    @Operation(summary = "위험 이력 상세", description = "event.level은 누적 최고 위험도, prediction은 최근 위험 프레임 판정입니다. 없는 ID는 404입니다.")
    @GetMapping("/{id}")
    public EventDetail detail(@PathVariable long id) {
        var event = events.findById(id).orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND, "위험 이벤트를 찾을 수 없습니다."));
        return new EventDetail(EventSummary.of(event),
                mapper.readValue(event.getPredictionJson(), PredictionResult.class));
    }

    @GetMapping("/{id}/video")
    public ResponseEntity<Resource> video(@PathVariable long id) {
        var event = events.findById(id).orElseThrow(() ->
                new ResponseStatusException(HttpStatus.NOT_FOUND, "위험 이벤트를 찾을 수 없습니다."));
        if (event.getVideoPath() == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "아직 생성된 이벤트 영상이 없습니다.");
        }
        var resource = new FileSystemResource(event.getVideoPath());
        if (!resource.exists() || !resource.isReadable()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "이벤트 영상 파일을 찾을 수 없습니다.");
        }
        var mediaType = event.getVideoPath().toLowerCase().endsWith(".webm")
                ? "video/webm" : "video/mp4";
        return ResponseEntity.ok()
                .contentType(MediaType.parseMediaType(mediaType))
                .body(resource);
    }

    public record EventSummary(Long id, String cameraId, String frameId, Instant capturedAt,
                               Instant createdAt, PredictionResult.RiskLevel level, String streamId,
                               Integer personTrackId, Integer forkliftTrackId, Instant lastSeenAt,
                               Instant endedAt, Long frameCount, String status, String endReason,
                               String videoUrl) {
        static EventSummary of(RiskEvent e) {
            return new EventSummary(e.getId(), e.getCameraId(), e.getFrameId(),
                    e.getCapturedAt(), e.getCreatedAt(), e.getLevel(), e.getStreamId(),
                    e.getPersonTrackId(), e.getForkliftTrackId(), e.getLastSeenAt(),
                    e.getEndedAt(), e.getFrameCount(), e.getStatus(), e.getEndReason(),
                    e.getVideoPath() == null ? null : "/api/risk-events/" + e.getId() + "/video");
        }
    }
    public record EventPage(List<EventSummary> content, int page, int size, long totalElements, int totalPages) {}
    public record EventDetail(EventSummary event, PredictionResult prediction) {}
}
