package com.algamza.visionguard.analysis;

import com.algamza.visionguard.ai.AiClient;
import com.algamza.visionguard.ai.AiUnavailableException;
import com.algamza.visionguard.ai.PredictionResult;
import com.algamza.visionguard.event.RiskEvent;
import com.algamza.visionguard.event.RiskEventRepository;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.server.ResponseStatusException;

import tools.jackson.databind.ObjectMapper;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import static com.algamza.visionguard.ai.PredictionResult.RiskLevel.SAFE;

@Service
public class AnalysisService {

    private final AiClient ai;

    /*
     * Mock/legacy 단일 스트림 테스트용.
     * 실제 HTTP AI에서는 camera/stream별 Predictor를
     * AI 서버가 별도로 관리한다.
     */
    private String activeAiScope;

    private final RiskEventRepository events;
    private final ProcessedFrameRepository frames;
    private final StreamCompletionRepository completions;
    private final ObjectMapper mapper;

    /*
     * 기존 Mock/Test 호환용 카메라 ID.
     * HTTP 모드에서는 이 값으로 카메라를 제한하지 않는다.
     */
    private final String cameraId;

    private final String mode;
    private final TransactionTemplate transaction;
    private final long maxGapMs;

    /*
     * 실시간 관제 화면용.
     *
     * DB에 매번 최신 상태 조회용 row를 추가하는 대신,
     * Backend가 실행되는 동안 카메라별 가장 최근
     * AnalysisResponse 하나만 메모리에 보관한다.
     */
    private final Map<String, AnalysisResponse> latestByCamera =
            new ConcurrentHashMap<>();


    public AnalysisService(
            AiClient ai,
            RiskEventRepository events,
            ProcessedFrameRepository frames,
            StreamCompletionRepository completions,
            ObjectMapper mapper,
            PlatformTransactionManager transactionManager,
            @Value("${visionguard.camera-id:camera-1}")
            String cameraId,
            @Value("${visionguard.ai.mode}")
            String mode,
            @Value("${visionguard.events.max-gap-ms:2000}")
            long maxGapMs
    ) {

        if (maxGapMs <= 0) {
            throw new IllegalArgumentException(
                    "max-gap-ms must be positive"
            );
        }

        this.ai = ai;
        this.events = events;
        this.frames = frames;
        this.completions = completions;
        this.mapper = mapper;
        this.cameraId = cameraId;
        this.mode = mode;
        this.maxGapMs = maxGapMs;

        this.transaction =
                new TransactionTemplate(
                        transactionManager
                );
    }


    /*
     * 프레임 한 장 분석
     */
    public synchronized AnalysisResponse analyze(
            byte[] image,
            String cameraId,
            String streamId,
            String frameId,
            Instant capturedAt,
            double fps
    ) {

        /*
         * Mock 모드에서는 기존 단일 카메라 계약 유지.
         *
         * HTTP 모드에서는 camera-1, camera-2,
         * 향후 camera-3, camera-4까지 모두 허용한다.
         */
        if (
                !"http".equalsIgnoreCase(mode)
                        && !this.cameraId.equals(cameraId)
        ) {

            throw new IllegalArgumentException(
                    "현재 서버는 카메라 "
                            + this.cameraId
                            + "만 지원합니다."
            );
        }


        var at =
                capturedAt.truncatedTo(
                        ChronoUnit.MICROS
                );

        var scope =
                hash(
                        cameraId,
                        streamId
                );

        var key =
                hash(
                        cameraId,
                        streamId,
                        frameId
                );

        var fingerprint =
                hash(
                        hexDigest(image),
                        at.toString(),
                        Double.toString(fps)
                );


        return transaction.execute(status -> {

            /*
             * 이미 처리한 동일 프레임이면
             * 저장된 응답 재사용.
             */
            var previous =
                    frames.findById(key);

            if (previous.isPresent()) {

                if (
                        !previous.get()
                                .getFingerprint()
                                .equals(fingerprint)
                ) {

                    throw conflict(
                            "같은 프레임 ID에 다른 이미지·촬영 시각·fps를 사용할 수 없습니다."
                    );
                }

                var replay =
                        mapper.readValue(
                                previous.get()
                                        .getResponseJson(),
                                AnalysisResponse.class
                        );

                latestByCamera.put(
                        cameraId,
                        replay
                );

                return replay;
            }


            /*
             * 이미 종료된 stream에는 새 프레임 금지.
             */
            if (
                    completions.existsById(scope)
            ) {

                throw conflict(
                        "종료된 스트림에는 새 프레임을 추가할 수 없습니다. 새로운 streamId를 사용하세요."
                );
            }


            /*
             * 같은 stream에서는 capturedAt이
             * 계속 증가해야 한다.
             */
            frames
                    .findFirstByScopeKeyOrderByCapturedAtDesc(
                            scope
                    )
                    .ifPresent(last -> {

                        if (
                                !at.isAfter(
                                        last.getCapturedAt()
                                )
                        ) {

                            throw conflict(
                                    "새 프레임의 촬영 시각은 이전 프레임보다 늦어야 합니다."
                            );
                        }
                    });


            final PredictionResult prediction;


            /*
             * 실제 HTTP AI.
             *
             * cameraId와 streamId를 AI Server까지 전달하여
             * DeepSORT / Collision state를 카메라별로 분리.
             */
            if (
                    "http".equalsIgnoreCase(mode)
            ) {

                prediction =
                        ai.predict(
                                image,
                                cameraId,
                                streamId,
                                frameId,
                                fps
                        );

            } else {

                /*
                 * 기존 Mock/Test 동작 보존.
                 */
                if (
                        !scope.equals(
                                activeAiScope
                        )
                ) {

                    ai.reset();
                    activeAiScope = scope;
                }

                prediction =
                        ai.predict(
                                image,
                                frameId,
                                fps
                        );
            }


            var current =
                    collectRisks(
                            prediction
                    );

            var active =
                    new HashMap<Pair, RiskEvent>();


            /*
             * 현재 camera에 해당하는 열린 Event 갱신.
             */
            for (
                    var event :
                    events.findByEndedAtIsNullAndScopeKeyIsNotNull()
            ) {

                /*
                 * 다른 CCTV 이벤트는 절대 건드리지 않는다.
                 */
                if (
                        !cameraId.equals(
                                event.getCameraId()
                        )
                ) {
                    continue;
                }


                /*
                 * 같은 카메라지만 다른 stream이면
                 * 이전 stream 이벤트 종료.
                 */
                if (
                        !scope.equals(
                                event.getScopeKey()
                        )
                ) {

                    event.end(
                            event.getLastSeenAt(),
                            "STREAM_CHANGED"
                    );

                } else if (
                        at.isAfter(
                                event.getLastSeenAt()
                                        .plusMillis(
                                                maxGapMs
                                        )
                        )
                ) {

                    event.end(
                            event.getLastSeenAt()
                                    .plusMillis(
                                            maxGapMs
                                    ),
                            "FRAME_GAP"
                    );

                } else {

                    var pair =
                            new Pair(
                                    event.getPersonTrackId(),
                                    event.getForkliftTrackId()
                            );

                    if (
                            !current.containsKey(pair)
                    ) {

                        event.end(
                                at,
                                "NOT_OBSERVED"
                        );

                    } else {

                        active.put(
                                pair,
                                event
                        );
                    }
                }
            }


            var ids =
                    new ArrayList<Long>();


            /*
             * 현재 프레임의 WARNING / DANGER 처리.
             */
            for (
                    var entry :
                    current.entrySet()
            ) {

                var risk =
                        entry.getValue();

                var snapshot =
                        new PredictionResult(
                                prediction.frame_id(),
                                prediction.image_width(),
                                prediction.image_height(),
                                prediction.detections(),
                                List.of(risk),
                                risk.level(),
                                prediction.processing_time_ms()
                        );

                var json =
                        mapper.writeValueAsString(
                                snapshot
                        );

                var event =
                        active.get(
                                entry.getKey()
                        );


                if (
                        event == null
                ) {

                    event =
                            RiskEvent.start(
                                    cameraId,
                                    streamId,
                                    scope,
                                    frameId,
                                    at,
                                    risk.person_track_id(),
                                    risk.forklift_track_id(),
                                    risk.level(),
                                    json
                            );


                    /*
                     * 실제 Track ID가 없는 위험은
                     * 단일 프레임 Event로 처리.
                     */
                    if (
                            risk.person_track_id()
                                    == null
                                    || risk.forklift_track_id()
                                    == null
                    ) {

                        event.end(
                                at,
                                "UNTRACKED"
                        );
                    }


                    events.save(event);

                } else {

                    event.observe(
                            at,
                            risk.level(),
                            json
                    );
                }


                ids.add(
                        event.getId()
                );
            }


            var result =
                    new AnalysisResponse(
                            ids.isEmpty()
                                    ? null
                                    : ids.get(0),

                            List.copyOf(ids),

                            cameraId,
                            streamId,
                            at,
                            mode,
                            prediction
                    );


            /*
             * 프레임 처리 기록 저장.
             */
            frames.save(
                    new ProcessedFrame(
                            key,
                            scope,
                            fingerprint,
                            at,
                            mapper.writeValueAsString(
                                    result
                            )
                    )
            );


            /*
             * Frontend 실시간 조회용 최신 상태 저장.
             */
            latestByCamera.put(
                    cameraId,
                    result
            );


            return result;
        });
    }


    /*
     * Frontend 실시간 관제용 최신 분석 결과 조회.
     */
    public AnalysisResponse getLatest(
            String cameraId
    ) {

        if (
                cameraId == null
                        || cameraId.isBlank()
                        || cameraId.length() > 100
        ) {

            throw new IllegalArgumentException(
                    "cameraId는 1~100자여야 합니다."
            );
        }


        var result =
                latestByCamera.get(
                        cameraId
                );


        if (
                result == null
        ) {

            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND,
                    "아직 처리된 프레임이 없는 카메라입니다."
            );
        }


        return result;
    }


    /*
     * Stream 종료
     */
    public synchronized StreamEndResponse endStream(
            String cameraId,
            String streamId,
            Instant endedAt
    ) {

        /*
         * Mock/legacy 모드에서만 기존 단일-camera 제한.
         */
        if (
                !"http".equalsIgnoreCase(mode)
                        && !this.cameraId.equals(cameraId)
        ) {

            throw new IllegalArgumentException(
                    "현재 서버는 카메라 "
                            + this.cameraId
                            + "만 지원합니다."
            );
        }


        var scope =
                hash(
                        cameraId,
                        streamId
                );

        var at =
                endedAt.truncatedTo(
                        ChronoUnit.MICROS
                );


        var result =
                transaction.execute(status -> {

                    var previous =
                            completions.findById(
                                    scope
                            );


                    if (
                            previous.isPresent()
                    ) {

                        if (
                                !previous.get()
                                        .getEndedAt()
                                        .equals(at)
                        ) {

                            throw conflict(
                                    "이미 종료된 스트림의 종료 시각을 변경할 수 없습니다."
                            );
                        }


                        return mapper.readValue(
                                previous.get()
                                        .getResponseJson(),
                                StreamEndResponse.class
                        );
                    }


                    var last =
                            frames
                                    .findFirstByScopeKeyOrderByCapturedAtDesc(
                                            scope
                                    )
                                    .orElseThrow(
                                            () ->
                                                    new ResponseStatusException(
                                                            HttpStatus.NOT_FOUND,
                                                            "처리된 프레임이 없는 스트림입니다."
                                                    )
                                    );


                    if (
                            at.isBefore(
                                    last.getCapturedAt()
                            )
                    ) {

                        throw conflict(
                                "종료 시각은 마지막 프레임 촬영 시각보다 빠를 수 없습니다."
                        );
                    }


                    var ids =
                            new ArrayList<Long>();


                    for (
                            var event :
                            events.findByScopeKeyAndEndedAtIsNull(
                                    scope
                            )
                    ) {

                        event.end(
                                at,
                                "STREAM_ENDED"
                        );

                        ids.add(
                                event.getId()
                        );
                    }


                    ids.sort(
                            Long::compareTo
                    );


                    var response =
                            new StreamEndResponse(
                                    cameraId,
                                    streamId,
                                    at,
                                    List.copyOf(ids)
                            );


                    completions.save(
                            new StreamCompletion(
                                    scope,
                                    at,
                                    mapper.writeValueAsString(
                                            response
                                    )
                            )
                    );


                    return response;
                });


        /*
         * HTTP AI에서는 해당 camera/stream Predictor 제거.
         *
         * Bridge를 여러 번 재시작해도
         * AI Server에 오래된 Predictor가 계속 쌓이는 것을 방지.
         */
        if (
                "http".equalsIgnoreCase(mode)
        ) {

            ai.reset(
                    cameraId,
                    streamId
            );
        }


        return result;
    }


    public record StreamEndResponse(
            String cameraId,
            String streamId,
            Instant endedAt,
            List<Long> closedEventIds
    ) {
    }


    /*
     * SAFE를 제외하고 Event 저장 대상 위험만 수집.
     */
    private Map<Pair, PredictionResult.Risk> collectRisks(
            PredictionResult prediction
    ) {

        if (
                prediction == null
                        || prediction.overall_risk()
                        == null
                        || prediction.risks()
                        == null
                        || prediction.detections()
                        == null
        ) {

            throw new AiUnavailableException();
        }


        var result =
                new LinkedHashMap<
                        Pair,
                        PredictionResult.Risk
                        >();


        for (
                var risk :
                prediction.risks()
        ) {

            if (
                    risk == null
                            || risk.level()
                            == null
            ) {

                throw new AiUnavailableException();
            }


            if (
                    risk.level()
                            == SAFE
            ) {

                continue;
            }


            /*
             * Track ID가 없으면 현재 frame에서만
             * 사용할 synthetic negative key 생성.
             */
            var pair =
                    new Pair(

                            risk.person_track_id()
                                    == null
                                    ? -risk.person_index() - 1
                                    : risk.person_track_id(),

                            risk.forklift_track_id()
                                    == null
                                    ? -risk.forklift_index() - 1
                                    : risk.forklift_track_id()
                    );


            /*
             * 동일 pair가 중복되면 더 높은 위험 유지.
             */
            result.merge(
                    pair,
                    risk,
                    (a, b) ->
                            a.level()
                                            .ordinal()
                                    >= b.level()
                                            .ordinal()
                                    ? a
                                    : b
            );
        }


        var highest =
                result.values()
                        .stream()
                        .map(
                                PredictionResult.Risk::level
                        )
                        .max(
                                Comparator.naturalOrder()
                        )
                        .orElse(
                                SAFE
                        );


        if (
                highest
                        != prediction.overall_risk()
        ) {

            throw new AiUnavailableException();
        }


        return result;
    }


    private static ResponseStatusException conflict(
            String message
    ) {

        return new ResponseStatusException(
                HttpStatus.CONFLICT,
                message
        );
    }


    private static String hash(
            String... values
    ) {

        var digest =
                digest();


        for (
                var value :
                values
        ) {

            var bytes =
                    value.getBytes(
                            StandardCharsets.UTF_8
                    );


            digest.update(
                    ByteBuffer.allocate(4)
                            .putInt(
                                    bytes.length
                            )
                            .array()
            );


            digest.update(
                    bytes
            );
        }


        return HexFormat
                .of()
                .formatHex(
                        digest.digest()
                );
    }


    private static String hexDigest(
            byte[] value
    ) {

        return HexFormat
                .of()
                .formatHex(
                        digest()
                                .digest(
                                        value
                                )
                );
    }


    private static MessageDigest digest() {

        try {

            return MessageDigest.getInstance(
                    "SHA-256"
            );

        } catch (
                NoSuchAlgorithmException e
        ) {

            throw new IllegalStateException(
                    e
            );
        }
    }


    private record Pair(
            Integer person,
            Integer forklift
    ) {
    }


    public record AnalysisResponse(
            Long eventId,
            List<Long> eventIds,
            String cameraId,
            String streamId,
            Instant capturedAt,
            String aiMode,
            PredictionResult prediction
    ) {
    }
}