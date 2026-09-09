package com.algamza.visionguard.ai;

public interface AiClient {
    PredictionResult predict(byte[] image, String frameId, double fps);
}
