package com.algamza.visionguard;

import com.algamza.visionguard.ai.*;
import com.algamza.visionguard.analysis.*;
import com.algamza.visionguard.event.*;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.ObjectMapper;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.*;
import static com.algamza.visionguard.ai.PredictionResult.RiskLevel.*;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

@SpringBootTest
class AnalysisServiceTests {
    @MockitoBean AiClient ai;
    @Autowired AnalysisService service;
    @Autowired RiskEventRepository events;
    @Autowired com.algamza.visionguard.analysis.StreamCompletionRepository completions;
    @MockitoSpyBean ProcessedFrameRepository frames;
    @Autowired ObjectMapper mapper;
    @Autowired PlatformTransactionManager transactionManager;
    final Instant start = Instant.parse("2026-09-07T00:00:00Z");

    @BeforeEach void clear() { completions.deleteAll(); frames.deleteAll(); events.deleteAll(); }

    PredictionResult.Risk risk(PredictionResult.RiskLevel level, Integer person, Integer forklift) {
        return new PredictionResult.Risk(level, 0, 1, person, forklift, 10, 5, 1.0, 60, "test");
    }
    PredictionResult prediction(PredictionResult.Risk... risks) {
        var level = java.util.Arrays.stream(risks).map(PredictionResult.Risk::level)
                .max(java.util.Comparator.naturalOrder()).orElse(SAFE);
        return new PredictionResult("frame", 100, 80, List.of(), List.of(risks), level, 1);
    }
    AnalysisService.AnalysisResponse send(String frame, long millis) {
        return service.analyze(new byte[]{1}, "camera-1", "stream-1", frame, start.plusMillis(millis), 30);
    }
    void respond(PredictionResult... predictions) {
        doReturn(predictions[0], (Object[]) java.util.Arrays.copyOfRange(predictions, 1, predictions.length))
                .when(ai).predict(any(), anyString(), anyDouble());
    }

    @Test void resetsOnlyBeforeNewStreamInferenceAndNeverForReplayOrEnd() {
        respond(prediction());
        var instance = new AnalysisService(ai, events, frames, completions, mapper, transactionManager, "camera-1", "mock", 2000);
        instance.analyze(new byte[]{1}, "camera-1", "reset-a", "1", start, 2);
        instance.analyze(new byte[]{1}, "camera-1", "reset-a", "2", start.plusMillis(500), 2);
        instance.analyze(new byte[]{1}, "camera-1", "reset-b", "1", start.plusSeconds(1), 2);
        instance.analyze(new byte[]{1}, "camera-1", "reset-a", "1", start, 2);
        instance.endStream("camera-1", "reset-a", start.plusMillis(500));
        var order = inOrder(ai);
        order.verify(ai).reset();
        order.verify(ai).predict(any(), eq("1"), eq(2.0));
        order.verify(ai).predict(any(), eq("2"), eq(2.0));
        order.verify(ai).reset();
        order.verify(ai).predict(any(), eq("1"), eq(2.0));
        order.verifyNoMoreInteractions();
    }

    @Test void mergesPairPreservesPeakAndEndsWhenSafe() {
        respond(prediction(risk(WARNING, 1, 2)), prediction(risk(DANGER, 1, 2)),
                prediction(risk(WARNING, 1, 2)), prediction());
        long id = send("1", 0).eventId();
        assertThat(send("2", 100).eventIds()).containsExactly(id);
        assertThat(send("3", 200).eventId()).isEqualTo(id);
        assertThat(send("4", 300).eventId()).isNull();
        var event = events.findById(id).orElseThrow();
        assertThat(events.count()).isEqualTo(1);
        assertThat(event.getCapturedAt()).isEqualTo(start);
        assertThat(event.getLastSeenAt()).isEqualTo(start.plusMillis(200));
        assertThat(event.getEndedAt()).isEqualTo(start.plusMillis(300));
        assertThat(event.getFrameCount()).isEqualTo(3);
        assertThat(event.getLevel()).isEqualTo(DANGER);
        assertThat(event.getStatus()).isEqualTo("CLOSED");
        assertThat(mapper.readValue(event.getPredictionJson(), PredictionResult.class).overall_risk()).isEqualTo(WARNING);
    }

    @Test void handlesMultiplePairsIndependently() {
        respond(prediction(risk(WARNING, 1, 2), risk(DANGER, 3, 2)), prediction(risk(WARNING, 1, 2)));
        var first = send("1", 0);
        assertThat(first.eventIds()).hasSize(2);
        assertThat(send("2", 100).eventIds()).containsExactly(first.eventIds().get(0));
        assertThat(events.findById(first.eventIds().get(1)).orElseThrow().getStatus()).isEqualTo("CLOSED");
        assertThat(mapper.readValue(events.findById(first.eventId()).orElseThrow().getPredictionJson(),
                PredictionResult.class).risks()).hasSize(1);
    }

    @Test void safeFrameIsDeduplicatedWithoutRiskEvent() {
        respond(prediction());
        assertThat(send("1", 0).eventId()).isNull();
        assertThat(send("1", 0).eventId()).isNull();
        assertThat(events.count()).isZero();
        assertThat(frames.count()).isEqualTo(1);
        verify(ai, times(1)).predict(any(), anyString(), anyDouble());
    }

    @Test void replaysOriginalResponseAfterLaterFramesAndServiceRecreation() {
        respond(prediction(risk(WARNING, 1, 2)), prediction(risk(DANGER, 1, 2)));
        var original = send("1", 0);
        send("2", 100);
        var recreated = new AnalysisService(ai, events, frames, completions, mapper, transactionManager, "camera-1", "mock", 2000);
        assertThat(recreated.analyze(new byte[]{1}, "camera-1", "stream-1", "1", start, 30)).isEqualTo(original);
        assertThat(events.findById(original.eventId()).orElseThrow().getFrameCount()).isEqualTo(2);
        verify(ai, times(2)).predict(any(), anyString(), anyDouble());
    }

    @Test void conflictingRetryAndOutOfOrderFrameAreRejectedBeforeInference() {
        respond(prediction(risk(WARNING, 1, 2)));
        send("1", 100);
        assertThatThrownBy(() -> service.analyze(new byte[]{2}, "camera-1", "stream-1", "1", start.plusMillis(100), 30))
                .isInstanceOfSatisfying(ResponseStatusException.class, e -> assertThat(e.getStatusCode().value()).isEqualTo(409));
        assertThatThrownBy(() -> send("2", 0)).isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> send("2", 100)).isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> service.analyze(new byte[]{1}, "camera-1", "stream-1", "1", start.plusMillis(100), 15))
                .isInstanceOf(ResponseStatusException.class);
        verify(ai, times(1)).predict(any(), anyString(), anyDouble());
    }

    @Test void concurrentIdenticalRequestsOnlyInferAndStoreOnce() throws Exception {
        respond(prediction(risk(WARNING, 1, 2)));
        var pool = Executors.newFixedThreadPool(2);
        try {
            var gate = new CountDownLatch(1);
            Callable<AnalysisService.AnalysisResponse> task = () -> { gate.await(); return send("1", 0); };
            var a = pool.submit(task); var b = pool.submit(task); gate.countDown();
            assertThat(a.get(10, TimeUnit.SECONDS)).isEqualTo(b.get(10, TimeUnit.SECONDS));
            assertThat(events.count()).isEqualTo(1);
            verify(ai, times(1)).predict(any(), anyString(), anyDouble());
        } finally { pool.shutdownNow(); }
    }

    @Test void anotherCameraCanAnalyzeAndEndWhileFirstCameraIsInferring() throws Exception {
        var instance = new AnalysisService(ai, events, frames, completions, mapper,
                transactionManager, "camera-1", "http", 2000);
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        when(ai.predict(any(), anyString(), anyString(), anyString(), anyDouble())).thenAnswer(call -> {
            if ("camera-1".equals(call.getArgument(1))) {
                entered.countDown();
                if (!release.await(10, TimeUnit.SECONDS)) throw new AssertionError("test timed out");
            }
            return prediction(risk(WARNING, 1, 2));
        });
        var pool = Executors.newFixedThreadPool(2);
        try {
            var first = pool.submit(() -> instance.analyze(new byte[]{1}, "camera-1", "stream-1", "1", start, 30));
            assertThat(entered.await(5, TimeUnit.SECONDS)).isTrue();
            var second = pool.submit(() -> {
                var response = instance.analyze(new byte[]{1}, "camera-2", "stream-1", "1", start, 30);
                assertThat(instance.endStream("camera-2", "stream-1", start).closedEventIds())
                        .containsExactly(response.eventId());
                return response;
            });
            assertThat(second.get(5, TimeUnit.SECONDS).cameraId()).isEqualTo("camera-2");
            assertThat(first.isDone()).isFalse();
            release.countDown();
            assertThat(first.get(5, TimeUnit.SECONDS).cameraId()).isEqualTo("camera-1");
            assertThat(events.count()).isEqualTo(2);
        } finally { release.countDown(); pool.shutdownNow(); }
    }

    @Test void gapAndReappearanceStartNewEvents() {
        respond(prediction(risk(WARNING, 1, 2)), prediction(risk(WARNING, 1, 2)),
                prediction(), prediction(risk(WARNING, 1, 2)));
        var first = send("1", 0);
        var second = send("2", 3000);
        assertThat(second.eventId()).isNotEqualTo(first.eventId());
        var closed = events.findById(first.eventId()).orElseThrow();
        assertThat(closed.getEndedAt()).isEqualTo(start.plusSeconds(2));
        assertThat(closed.getEndReason()).isEqualTo("FRAME_GAP");
        send("3", 3100);
        assertThat(send("4", 3200).eventId()).isNotEqualTo(second.eventId());
    }

    @Test void unknownTrackIdsNeverMerge() {
        respond(prediction(risk(WARNING, null, 2)));
        var first = send("1", 0);
        assertThat(send("2", 100).eventId()).isNotEqualTo(first.eventId());
        assertThat(events.findById(first.eventId()).orElseThrow().getEndReason()).isEqualTo("UNTRACKED");
    }

    @Test void newStreamAllowsReusedFrameIdsAndClosesOldEvents() {
        respond(prediction(risk(WARNING, 1, 2)));
        var first = send("1", 0);
        var second = service.analyze(new byte[]{1}, "camera-1", "stream-2", "1", start, 30);
        assertThat(second.eventId()).isNotEqualTo(first.eventId());
        assertThat(events.findById(first.eventId()).orElseThrow().getEndReason()).isEqualTo("STREAM_CHANGED");
    }

    @Test void inferenceFailureLeavesLifecycleUntouchedAndCanRetry() {
        respond(prediction(risk(WARNING, 1, 2)));
        long id = send("1", 0).eventId();
        when(ai.predict(any(), anyString(), anyDouble())).thenThrow(new AiUnavailableException());
        assertThatThrownBy(() -> send("2", 100)).isInstanceOf(AiUnavailableException.class);
        assertThat(frames.count()).isEqualTo(1);
        assertThat(events.findById(id).orElseThrow().getStatus()).isEqualTo("OPEN");
        respond(prediction());
        send("2", 100);
        assertThat(events.findById(id).orElseThrow().getStatus()).isEqualTo("CLOSED");
    }

    @Test void receiptWriteFailureRollsBackEventMutation() {
        respond(prediction(risk(WARNING, 1, 2)));
        long id = send("1", 0).eventId();
        doThrow(new IllegalStateException("simulated DB failure")).when(frames).save(any(ProcessedFrame.class));
        assertThatThrownBy(() -> send("2", 100)).isInstanceOf(IllegalStateException.class);
        assertThat(events.findById(id).orElseThrow().getFrameCount()).isEqualTo(1);
        assertThat(frames.count()).isEqualTo(1);
    }

    @Test void legacyRowsRemainReadableAndAreNotMerged() {
        var old = events.save(new RiskEvent("camera-1", "old", start, WARNING, mapper.writeValueAsString(prediction())));
        respond(prediction(risk(WARNING, 1, 2)));
        assertThat(send("1", 0).eventId()).isNotEqualTo(old.getId());
        assertThat(events.findById(old.getId()).orElseThrow().getStatus()).isEqualTo("LEGACY");
    }
    @Test void streamEndClosesPairsAndReplaysAfterServiceRecreation() {
        respond(prediction(risk(WARNING, 1, 2), risk(DANGER, 3, 4)));
        var first = send("1", 0);
        var end = service.endStream("camera-1", "stream-1", start.plusMillis(100));
        assertThat(end.closedEventIds()).containsExactlyElementsOf(first.eventIds());
        for (long id : first.eventIds()) {
            var event = events.findById(id).orElseThrow();
            assertThat(event.getEndReason()).isEqualTo("STREAM_ENDED");
            assertThat(event.getEndedAt()).isEqualTo(start.plusMillis(100));
        }
        var recreated = new AnalysisService(ai, events, frames, completions, mapper,
                transactionManager, "camera-1", "mock", 2000);
        assertThat(recreated.endStream("camera-1", "stream-1", start.plusMillis(100))).isEqualTo(end);
        assertThat(send("1", 0)).isEqualTo(first);
        assertThatThrownBy(() -> send("2", 200)).isInstanceOf(ResponseStatusException.class);
        verify(ai, times(1)).predict(any(), anyString(), anyDouble());
    }

    @Test void streamEndValidatesTimestampAndUnknownStreams() {
        respond(prediction(risk(WARNING, 1, 2)));
        send("1", 100);
        assertThatThrownBy(() -> service.endStream("camera-1", "stream-1", start))
                .isInstanceOfSatisfying(ResponseStatusException.class, e -> assertThat(e.getStatusCode().value()).isEqualTo(409));
        assertThatThrownBy(() -> service.endStream("camera-1", "unknown", start))
                .isInstanceOfSatisfying(ResponseStatusException.class, e -> assertThat(e.getStatusCode().value()).isEqualTo(404));
        assertThatThrownBy(() -> service.endStream("camera-2", "stream-1", start))
                .isInstanceOf(IllegalArgumentException.class);
        service.endStream("camera-1", "stream-1", start.plusMillis(100));
        assertThatThrownBy(() -> service.endStream("camera-1", "stream-1", start.plusMillis(200)))
                .isInstanceOf(ResponseStatusException.class);
    }

    @Test void safeOnlyStreamCanBeClosedAndCannotAcceptNewFrames() {
        respond(prediction());
        send("1", 0);
        assertThat(service.endStream("camera-1", "stream-1", start).closedEventIds()).isEmpty();
        assertThatThrownBy(() -> send("2", 100)).isInstanceOf(ResponseStatusException.class);
        assertThat(events.count()).isZero();
    }

    @Test void closingAnOldStreamDoesNotCloseTheCurrentStream() {
        respond(prediction(risk(WARNING, 1, 2)));
        send("1", 0);
        var current = service.analyze(new byte[]{1}, "camera-1", "stream-2", "1", start, 30);
        assertThat(service.endStream("camera-1", "stream-1", start).closedEventIds()).isEmpty();
        assertThat(events.findById(current.eventId()).orElseThrow().getStatus()).isEqualTo("OPEN");
    }

    @Test void endWaitsForInFlightFrameCommit() throws Exception {
        var entered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        when(ai.predict(any(), anyString(), anyDouble())).thenAnswer(call -> {
            entered.countDown();
            if (!release.await(5, TimeUnit.SECONDS)) throw new AssertionError("test timed out");
            return prediction(risk(WARNING, 1, 2));
        });
        var pool = Executors.newFixedThreadPool(2);
        try {
            var frame = pool.submit(() -> send("1", 0));
            assertThat(entered.await(5, TimeUnit.SECONDS)).isTrue();
            var end = pool.submit(() -> service.endStream("camera-1", "stream-1", start));
            release.countDown();
            assertThat(end.get(10, TimeUnit.SECONDS).closedEventIds()).containsExactly(frame.get().eventId());
        } finally { release.countDown(); pool.shutdownNow(); }
    }

}
