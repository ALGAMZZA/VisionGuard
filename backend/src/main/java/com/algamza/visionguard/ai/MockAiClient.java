package com.algamza.visionguard.ai;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import javax.imageio.ImageIO;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.util.List;
import static com.algamza.visionguard.ai.PredictionResult.*;

@Component
@ConditionalOnProperty(name = "visionguard.ai.mode", havingValue = "mock")
public class MockAiClient implements AiClient {
    @Override
    public PredictionResult predict(byte[] image, String frameId, double fps) {
        try {
            var decoded = ImageIO.read(new ByteArrayInputStream(image));
            if (decoded == null) throw new IllegalArgumentException("JPEG 또는 PNG 이미지가 필요합니다.");
            int w = decoded.getWidth(), h = decoded.getHeight();
            return new PredictionResult(frameId, w, h,
                    List.of(new Detection(0, "person", 0.95,
                                    new BoundingBox(0, 0, w * 0.4, h), 1),
                            new Detection(1, "forklift", 0.95,
                                    new BoundingBox(w * 0.5, 0, w, h), 2)),
                    List.of(new Risk(RiskLevel.WARNING, 0, 1, 1, 2,
                            w * 0.1, w * 0.05, 1.0, 60, "MOCK: 개발용 고정 위험 응답")),
                    RiskLevel.WARNING, 0);
        } catch (IOException e) {
            throw new IllegalArgumentException("이미지를 읽을 수 없습니다.");
        }
    }
}
