package com.algamza.visionguard.analysis;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;

import org.springframework.web.bind.annotation.*;
import java.time.Instant;

@Tag(name = "영상 종료")
@RestController
@RequestMapping("/api/streams")
public class StreamController {
    private final AnalysisService service;
    public StreamController(AnalysisService service) { this.service = service; }

    @Operation(summary = "영상 스트림 종료", description = "열린 위험 이벤트를 STREAM_ENDED로 종료합니다. "
            + "동일 종료 요청은 원래 응답을 반환하며 종료 시각 변경은 409, 처리한 프레임이 없는 스트림은 404입니다. AI reset은 수행하지 않습니다.")
    @PostMapping("/end")
    public AnalysisService.StreamEndResponse end(@RequestBody StreamEndRequest request) {
        if (request.cameraId() == null || request.cameraId().isBlank() || request.cameraId().length() > 100
                || request.streamId() == null || request.streamId().isBlank() || request.streamId().length() > 100
                || request.endedAt() == null) {
            throw new IllegalArgumentException("cameraId와 streamId는 1~100자이고 endedAt은 필수입니다.");
        }
        return service.endStream(request.cameraId(), request.streamId(), request.endedAt());
    }
    public record StreamEndRequest(
            @Schema(description = "카메라 ID", example = "camera-1", requiredMode = Schema.RequiredMode.REQUIRED, minLength = 1, maxLength = 100) String cameraId,
            @Schema(description = "종료할 영상 ID", example = "video-demo-1", requiredMode = Schema.RequiredMode.REQUIRED, minLength = 1, maxLength = 100) String streamId,
            @Schema(description = "마지막 프레임 촬영 시각 이상", example = "2026-09-09T00:00:01Z", requiredMode = Schema.RequiredMode.REQUIRED) Instant endedAt) {}
}
