package com.algamza.visionguard.event;

import jakarta.annotation.PreDestroy;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

@Service
public class EventClipService {
    private static final long CLIP_SIDE_SECONDS = 5;
    private static final DateTimeFormatter FILE_TIME =
            DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss").withZone(ZoneOffset.UTC);

    private final RiskEventRepository events;
    private final Path storageDirectory;
    private final Path encoderScript;
    private final String pythonExecutable;
    private final Map<String, ArrayDeque<Frame>> buffers = new HashMap<>();
    private final Map<Long, Recording> recordings = new HashMap<>();
    private final ExecutorService encoder = Executors.newSingleThreadExecutor();

    public EventClipService(
            RiskEventRepository events,
            @Value("${visionguard.events.video-storage:storage/events}") String storageDirectory,
            @Value("${visionguard.events.video-python:../AI/.venv/bin/python}") String pythonExecutable,
            @Value("${visionguard.events.video-encoder-script:scripts/write_event_clip.py}") String encoderScript
    ) {
        this.events = events;
        this.storageDirectory = Path.of(storageDirectory).toAbsolutePath().normalize();
        this.pythonExecutable = pythonExecutable;
        this.encoderScript = Path.of(encoderScript).toAbsolutePath().normalize();
    }

    public synchronized void acceptFrame(
            String cameraId, Instant capturedAt, double fps, byte[] jpeg
    ) {
        var frame = new Frame(capturedAt, jpeg.clone());
        var buffer = buffers.computeIfAbsent(cameraId, ignored -> new ArrayDeque<>());
        buffer.addLast(frame);
        var cutoff = capturedAt.minusSeconds(CLIP_SIDE_SECONDS);
        while (!buffer.isEmpty() && buffer.peekFirst().capturedAt().isBefore(cutoff)) {
            buffer.removeFirst();
        }

        var completed = new ArrayList<Recording>();
        for (var recording : recordings.values()) {
            if (!recording.cameraId().equals(cameraId)) continue;
            recording.frames().add(frame);
            if (!capturedAt.isBefore(recording.endsAt())) completed.add(recording);
        }
        for (var recording : completed) {
            recordings.remove(recording.eventId());
            encoder.submit(() -> encode(recording));
        }
    }

    public synchronized void trigger(
            long eventId, String cameraId, Instant eventAt, double fps
    ) {
        if (recordings.containsKey(eventId)) return;
        var buffered = buffers.getOrDefault(cameraId, new ArrayDeque<>());
        var startsAt = eventAt.minusSeconds(CLIP_SIDE_SECONDS);
        var frames = buffered.stream()
                .filter(frame -> !frame.capturedAt().isBefore(startsAt))
                .collect(java.util.stream.Collectors.toCollection(ArrayList::new));
        recordings.put(eventId, new Recording(
                eventId, cameraId, eventAt, eventAt.plusSeconds(CLIP_SIDE_SECONDS), fps, frames
        ));
    }

    private void encode(Recording recording) {
        var safeCamera = recording.cameraId().replaceAll("[^A-Za-z0-9_-]", "_");
        var baseName = "event_%d_%s_%s".formatted(
                recording.eventId(), safeCamera, FILE_TIME.format(recording.eventAt())
        );
        var workDirectory = storageDirectory.resolve("." + baseName + "_frames");
        var output = storageDirectory.resolve(baseName + ".webm");
        try {
            Files.createDirectories(workDirectory);
            for (int index = 0; index < recording.frames().size(); index++) {
                Files.write(
                        workDirectory.resolve("frame_%08d.jpg".formatted(index)),
                        recording.frames().get(index).jpeg()
                );
            }
            var process = new ProcessBuilder(
                    pythonExecutable,
                    encoderScript.toString(),
                    "--frames", workDirectory.toString(),
                    "--output", output.toString(),
                    "--fps", Double.toString(recording.fps())
            ).redirectErrorStream(true).start();
            var processOutput = new String(process.getInputStream().readAllBytes());
            if (process.waitFor() != 0 || !Files.isRegularFile(output) || Files.size(output) == 0) {
                throw new IOException("event clip encoder failed: " + processOutput);
            }
            events.findById(recording.eventId()).ifPresent(event -> {
                event.attachVideoPath(output.toString());
                events.save(event);
            });
        } catch (Exception exception) {
            System.err.println("Event clip creation failed for event "
                    + recording.eventId() + ": " + exception.getMessage());
        } finally {
            deleteWorkDirectory(workDirectory);
        }
    }

    private void deleteWorkDirectory(Path directory) {
        if (!directory.startsWith(storageDirectory) || !Files.exists(directory)) return;
        try (var paths = Files.walk(directory)) {
            paths.sorted(java.util.Comparator.reverseOrder()).forEach(path -> {
                try { Files.deleteIfExists(path); } catch (IOException ignored) { }
            });
        } catch (IOException ignored) { }
    }

    @PreDestroy
    void shutdown() {
        encoder.shutdown();
    }

    private record Frame(Instant capturedAt, byte[] jpeg) { }
    private record Recording(
            long eventId, String cameraId, Instant eventAt, Instant endsAt,
            double fps, List<Frame> frames
    ) { }
}
