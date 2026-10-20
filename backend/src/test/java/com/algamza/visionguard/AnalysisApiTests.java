package com.algamza.visionguard;

import com.algamza.visionguard.event.RiskEventRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import tools.jackson.databind.ObjectMapper;
import javax.imageio.ImageIO;
import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class AnalysisApiTests {
    @LocalServerPort int port;
    @Autowired RiskEventRepository events;
    @Autowired com.algamza.visionguard.analysis.StreamCompletionRepository completions;
    @Autowired com.algamza.visionguard.analysis.ProcessedFrameRepository frames;
    @Autowired ObjectMapper mapper;
    final HttpClient client = HttpClient.newHttpClient();

    @BeforeEach void clear() { completions.deleteAll(); frames.deleteAll(); events.deleteAll(); }

    @Test void analyzeThenFilterAndReadDetail() throws Exception {
        var response = analyze("camera-1", "30", png());
        assertThat(response.statusCode()).isEqualTo(200);
        var json = mapper.readTree(response.body());
        assertThat(json.get("aiMode").asText()).isEqualTo("mock");
        assertThat(json.get("prediction").get("overall_risk").asText()).isEqualTo("WARNING");
        assertThat(json.get("prediction").get("image_width").asInt()).isEqualTo(100);
        long id = json.get("eventId").asLong();
        var detail = get("/api/risk-events/" + id);
        assertThat(detail.statusCode()).isEqualTo(200);
        assertThat(mapper.readTree(detail.body()).get("prediction").get("risks").size()).isEqualTo(1);
        var list = get("/api/risk-events?cameraId=camera-1&from=2026-09-01T00:00:00Z&to=2026-09-30T00:00:00Z");
        assertThat(mapper.readTree(list.body()).get("totalElements").asInt()).isEqualTo(1);
        assertThat(mapper.readTree(get("/api/risk-events?cameraId=other").body()).get("totalElements").asInt()).isZero();
        assertThat(mapper.readTree(get("/api/risk-events?from=2027-01-01T00:00:00Z").body()).get("totalElements").asInt()).isZero();
    }

    @Test void rejectsOtherCameraAndInvalidFpsWithoutSaving() throws Exception {
        assertThat(analyze("camera-2", "30", png()).statusCode()).isEqualTo(400);
        assertThat(analyze("camera-1", "NaN", png()).statusCode()).isEqualTo(400);
        assertThat(analyze("camera-1", "0", png()).statusCode()).isEqualTo(400);
        assertThat(events.count()).isZero();
    }

    @Test void rejectsInvalidImage() throws Exception {
        assertThat(analyze("camera-1", "30", new byte[]{1, 2, 3}).statusCode()).isEqualTo(400);
        assertThat(events.count()).isZero();
    }

    @Test void validatesQueriesAndMissingEvents() throws Exception {
        assertThat(get("/api/risk-events?size=101").statusCode()).isEqualTo(400);
        assertThat(get("/api/risk-events?from=2027-01-01T00:00:00Z&to=2026-01-01T00:00:00Z").statusCode()).isEqualTo(400);
        assertThat(get("/api/risk-events/999999").statusCode()).isEqualTo(404);
    }

    @Test void streamEndHttpContractAndValidation() throws Exception {
        assertThat(end("{}").statusCode()).isEqualTo(400);
        var result = mapper.readTree(analyze("camera-1", "30", png()).body());
        String body = """
                {"cameraId":"camera-1","streamId":"default","endedAt":"2026-09-07T00:00:00Z"}
                """;
        var response = end(body);
        assertThat(response.statusCode()).isEqualTo(200);
        assertThat(mapper.readTree(response.body()).get("closedEventIds").get(0).asLong())
                .isEqualTo(result.get("eventId").asLong());
        assertThat(end(body).body()).isEqualTo(response.body());
        assertThat(mapper.readTree(get("/api/risk-events/" + result.get("eventId").asLong()).body())
                .get("event").get("endReason").asText()).isEqualTo("STREAM_ENDED");
    }

    HttpResponse<String> end(String body) throws Exception {
        return client.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/api/streams/end"))
                .header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString(body)).build(),
                HttpResponse.BodyHandlers.ofString());
    }

    @Test void swaggerExposesAllEndpointsAndUploadSchema() throws Exception {
        var response = get("/v3/api-docs");
        assertThat(response.statusCode()).isEqualTo(200);
        var doc = mapper.readTree(response.body());
        var paths = doc.get("paths");
        assertThat(paths.has("/api/analyses")).isTrue();
        assertThat(paths.has("/api/risk-events")).isTrue();
        assertThat(paths.has("/api/risk-events/{id}")).isTrue();
        assertThat(paths.has("/api/streams/end")).isTrue();
        assertThat(paths.get("/api/analyses").get("post").get("requestBody")
                .get("content").has("multipart/form-data")).isTrue();
        assertThat(doc.get("components").get("schemas").get("PredictionResult")
                .get("properties").has("overall_risk")).isTrue();
        assertThat(get("/swagger-ui/index.html").statusCode()).isEqualTo(200);
    }

    @Test void corsAllowsConfiguredOriginsAndRejectsOthers() throws Exception {
        for (String origin : java.util.List.of("http://localhost:3000", "http://localhost:5173")) {
            var response = preflight(origin, "POST");
            assertThat(response.statusCode()).isEqualTo(200);
            assertThat(response.headers().firstValue("Access-Control-Allow-Origin")).contains(origin);
            assertThat(response.headers().firstValue("Access-Control-Allow-Credentials")).isEmpty();
        }
        assertThat(preflight("https://untrusted.example", "POST").statusCode()).isEqualTo(403);
        assertThat(preflight("http://localhost:3000", "DELETE").statusCode()).isEqualTo(403);
    }

    @Test void actualCorsResponseIncludesOriginForSuccessAndValidationError() throws Exception {
        var success = client.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/api/risk-events"))
                .header("Origin", "http://localhost:3000").GET().build(), HttpResponse.BodyHandlers.ofString());
        assertThat(success.statusCode()).isEqualTo(200);
        assertThat(success.headers().firstValue("Access-Control-Allow-Origin")).contains("http://localhost:3000");
        var error = client.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/api/streams/end"))
                .header("Origin", "http://localhost:3000").header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{}")).build(), HttpResponse.BodyHandlers.ofString());
        assertThat(error.statusCode()).isEqualTo(400);
        assertThat(error.headers().firstValue("Access-Control-Allow-Origin")).contains("http://localhost:3000");
    }

    HttpResponse<String> preflight(String origin, String method) throws Exception {
        return client.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + "/api/streams/end"))
                .header("Origin", origin).header("Access-Control-Request-Method", method)
                .header("Access-Control-Request-Headers", "content-type")
                .method("OPTIONS", HttpRequest.BodyPublishers.noBody()).build(), HttpResponse.BodyHandlers.ofString());
    }

    HttpResponse<String> get(String path) throws Exception {
        return client.send(HttpRequest.newBuilder(URI.create("http://localhost:" + port + path)).GET().build(), HttpResponse.BodyHandlers.ofString());
    }

    HttpResponse<String> analyze(String camera, String fps, byte[] image) throws Exception {
        var out = new ByteArrayOutputStream();
        out.write(("--testboundary\r\nContent-Disposition: form-data; name=\"file\"; filename=\"frame.png\"\r\nContent-Type: image/png\r\n\r\n").getBytes(StandardCharsets.UTF_8));
        out.write(image);
        out.write("\r\n--testboundary--\r\n".getBytes(StandardCharsets.UTF_8));
        var uri = URI.create("http://localhost:" + port + "/api/analyses?cameraId=" + camera + "&frameId=1&capturedAt=2026-09-07T00:00:00Z&fps=" + fps);
        return client.send(HttpRequest.newBuilder(uri).header("Content-Type", "multipart/form-data; boundary=testboundary")
                .POST(HttpRequest.BodyPublishers.ofByteArray(out.toByteArray())).build(), HttpResponse.BodyHandlers.ofString());
    }

    byte[] png() throws Exception {
        var out = new ByteArrayOutputStream();
        ImageIO.write(new BufferedImage(100, 80, BufferedImage.TYPE_INT_RGB), "png", out);
        return out.toByteArray();
    }
}
