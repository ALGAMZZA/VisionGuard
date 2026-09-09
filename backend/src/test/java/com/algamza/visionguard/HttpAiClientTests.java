package com.algamza.visionguard;

import com.algamza.visionguard.ai.HttpAiClient;
import com.algamza.visionguard.ai.AiUnavailableException;
import com.algamza.visionguard.ai.PredictionResult.RiskLevel;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.Test;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;
import static org.assertj.core.api.Assertions.*;

class HttpAiClientTests {
    @Test void sendsMultipartAndDecodesPythonResponse() throws Exception {
        var requestBody = new AtomicReference<String>();
        var query = new AtomicReference<String>();
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/predict", exchange -> {
            requestBody.set(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            query.set(exchange.getRequestURI().getQuery());
            var response = """
                    {"frame_id":"frame-1","image_width":100,"image_height":80,
                     "detections":[{"class_id":0,"class_name":"person","confidence":0.9,
                       "bbox":{"x1":0,"y1":0,"x2":10,"y2":20},"track_id":null}],
                     "risks":[],"overall_risk":"SAFE","processing_time_ms":12.5}
                    """.getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, response.length);
            exchange.getResponseBody().write(response);
            exchange.close();
        });
        server.start();
        try {
            var client = new HttpAiClient("http://127.0.0.1:" + server.getAddress().getPort(), 1000);
            var result = client.predict(new byte[]{1,2,3}, "frame-1", 15);
            assertThat(result.overall_risk()).isEqualTo(RiskLevel.SAFE);
            assertThat(result.detections().get(0).track_id()).isNull();
            assertThat(query.get()).contains("frame_id=frame-1", "fps=15.0");
            assertThat(requestBody.get()).contains("name=\"file\"", "filename=\"frame.jpg\"");
        } finally { server.stop(0); }
    }

    @Test void translatesUpstreamFailures() throws Exception {
        var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/predict", exchange -> {
            exchange.getRequestBody().readAllBytes();
            exchange.sendResponseHeaders(500, -1);
            exchange.close();
        });
        server.start();
        try {
            var client = new HttpAiClient("http://127.0.0.1:" + server.getAddress().getPort(), 1000);
            assertThatThrownBy(() -> client.predict(new byte[]{1}, "1", 30))
                    .isInstanceOf(AiUnavailableException.class);
        } finally { server.stop(0); }
    }
}
