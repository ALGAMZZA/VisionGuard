package com.algamza.visionguard.ai;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

@Component
@ConditionalOnProperty(
        name = "visionguard.ai.mode",
        havingValue = "http"
)
public class HttpAiClient implements AiClient {

    private final RestClient client;

    public HttpAiClient(
            @Value("${visionguard.ai.base-url}") String baseUrl,
            @Value("${visionguard.ai.timeout-ms}") int timeoutMs
    ) {
        var factory =
                new SimpleClientHttpRequestFactory();

        factory.setConnectTimeout(timeoutMs);
        factory.setReadTimeout(timeoutMs);

        this.client =
                RestClient.builder()
                        .baseUrl(baseUrl)
                        .requestFactory(factory)
                        .build();
    }

    /*
     * 실제 HTTP AI는 camera/stream별 상태 분리를 지원한다.
     */
    @Override
    public boolean supportsScopedStreams() {
        return true;
    }

    /*
     * 전체 AI tracker reset.
     * 기존 테스트 및 호환용.
     */
    @Override
    public void reset() {
        try {
            client.post()
                    .uri("/reset")
                    .retrieve()
                    .toBodilessEntity();

        } catch (RestClientException e) {
            throw new AiUnavailableException();
        }
    }

    /*
     * 특정 camera/stream만 reset.
     */
    @Override
    public void reset(
            String cameraId,
            String streamId
    ) {
        try {
            client.post()
                    .uri(builder ->
                            builder
                                    .path("/reset")
                                    .queryParam(
                                            "camera_id",
                                            cameraId
                                    )
                                    .queryParam(
                                            "stream_id",
                                            streamId
                                    )
                                    .build()
                    )
                    .retrieve()
                    .toBodilessEntity();

        } catch (RestClientException e) {
            throw new AiUnavailableException();
        }
    }

    /*
     * 기존 API 호환.
     */
    @Override
    public PredictionResult predict(
            byte[] image,
            String frameId,
            double fps
    ) {
        return predict(
                image,
                "legacy-camera",
                "legacy-stream",
                frameId,
                fps
        );
    }

    /*
     * 실제 다중-camera 분석.
     */
    @Override
    public PredictionResult predict(
            byte[] image,
            String cameraId,
            String streamId,
            String frameId,
            double fps
    ) {

        var body =
                new LinkedMultiValueMap<String, Object>();

        body.add(
                "file",
                new ByteArrayResource(image) {
                    @Override
                    public String getFilename() {
                        return "frame.jpg";
                    }
                }
        );

        try {

            var result =
                    client.post()
                            .uri(builder ->
                                    builder
                                            .path("/predict")
                                            .queryParam(
                                                    "camera_id",
                                                    cameraId
                                            )
                                            .queryParam(
                                                    "stream_id",
                                                    streamId
                                            )
                                            .queryParam(
                                                    "frame_id",
                                                    frameId
                                            )
                                            .queryParam(
                                                    "fps",
                                                    fps
                                            )
                                            .build()
                            )
                            .contentType(
                                    MediaType.MULTIPART_FORM_DATA
                            )
                            .body(body)
                            .retrieve()
                            .body(
                                    PredictionResult.class
                            );

            if (
                    result == null
                            || result.overall_risk() == null
                            || result.detections() == null
                            || result.risks() == null
                            || result.image_width() <= 0
                            || result.image_height() <= 0
            ) {
                throw new AiUnavailableException();
            }

            return result;

        } catch (RestClientResponseException e) {

            int status =
                    e.getStatusCode().value();

            if (
                    status == 400
                            || status == 413
                            || status == 422
            ) {
                throw new IllegalArgumentException(
                        "AI 서버가 이미지 또는 스트림 입력을 거부했습니다."
                );
            }

            throw new AiUnavailableException();

        } catch (RestClientException e) {

            throw new AiUnavailableException();
        }
    }
}