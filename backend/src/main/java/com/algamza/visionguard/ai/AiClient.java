package com.algamza.visionguard.ai;

public interface AiClient {

    default void reset() {
    }

    default void reset(String cameraId, String streamId) {
        reset();
    }

    /*
     * 기존 Mock/Test는 false.
     * 실제 HTTP AI만 true로 override한다.
     */
    default boolean supportsScopedStreams() {
        return false;
    }

    /*
     * 기존 단일-stream API.
     * Mock 및 기존 테스트 호환용.
     */
    PredictionResult predict(
            byte[] image,
            String frameId,
            double fps
    );

    /*
     * 실제 다중-camera AI용 API.
     *
     * 기본 구현은 기존 API로 위임해서
     * MockAiClient와 기존 테스트를 깨뜨리지 않는다.
     */
    default PredictionResult predict(
            byte[] image,
            String cameraId,
            String streamId,
            String frameId,
            double fps
    ) {
        return predict(image, frameId, fps);
    }
}