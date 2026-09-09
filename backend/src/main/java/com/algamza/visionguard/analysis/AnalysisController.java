package com.algamza.visionguard.analysis;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Schema;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import java.io.IOException;
import java.time.Instant;

@Tag(name = "프레임 분석")
@RestController
@RequestMapping("/api/analyses")
public class AnalysisController {
    private final AnalysisService service;
    public AnalysisController(AnalysisService service) { this.service = service; }

    @Operation(summary = "이미지 프레임 분석", description = "이미지 한 장(최대 25 MiB)을 분석합니다. "
            + "같은 프레임 ID·내용의 재요청은 기존 응답을 반환합니다. 새 프레임은 촬영 시각 순서로 전송하세요. "
            + "종료된 스트림의 새 프레임과 ID 충돌은 409입니다.")
    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public AnalysisService.AnalysisResponse analyze(
            @Parameter(description = "이미지 파일, 최대 25 MiB", required = true) @RequestParam MultipartFile file,
            @Parameter(description = "카메라 ID", example = "camera-1", schema = @Schema(minLength = 1, maxLength = 100)) @RequestParam String cameraId,
            @Parameter(description = "스트림 내 고유 프레임 ID", example = "1") @RequestParam String frameId,
            @Parameter(description = "UTC 오프셋 포함 촬영 시각", example = "2026-09-09T00:00:00Z") @RequestParam Instant capturedAt,
            @Parameter(description = "새 영상마다 새 ID 사용", example = "video-demo-1") @RequestParam(defaultValue = "default") String streamId,
            @Parameter(description = "실제 처리 FPS: 0 초과 240 이하", schema = @Schema(minimum = "0", exclusiveMinimum = true, maximum = "240")) @RequestParam(defaultValue = "30") double fps) throws IOException {
        if (cameraId.isBlank() || cameraId.length() > 100
                || frameId.isBlank() || frameId.length() > 100
                || streamId.isBlank() || streamId.length() > 100) {
            throw new IllegalArgumentException("cameraId, streamId, frameId는 1~100자여야 합니다.");
        }
        if (!Double.isFinite(fps) || fps <= 0 || fps > 240) {
            throw new IllegalArgumentException("fps는 0보다 크고 240 이하여야 합니다.");
        }
        if (file.isEmpty()) throw new IllegalArgumentException("이미지 파일이 비어 있습니다.");
        return service.analyze(file.getBytes(), cameraId, streamId, frameId, capturedAt, fps);
    }
}
