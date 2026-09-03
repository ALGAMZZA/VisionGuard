# ============================================================
# YOLO + DeepSORT 기반 사전 충돌 예측 시스템 
#
# 핵심 처리 흐름
# 1. YOLO가 영상에서 사람과 차량을 탐지
# 2. DeepSORT가 프레임 사이에서 동일 객체에 같은 Track ID를 유지
# 3. 객체 중심점의 변화량으로 이동 속도(velocity)를 계산
# 4. 현재 속도가 유지된다고 가정하여 미래 trajectory를 선형 예측
# 5. 사람과 위험 객체의 미래 경로 거리, TTC, 접근 여부를 이용해
#    collision score를 계산
# 6. 위험 점수가 임계값을 넘으면 화면에 충돌 경보를 표시
#
# ============================================================

import argparse
# time은 FPS 계산을 위해 사용
import time
# OpenCV는 영상 입출력 및 시각화를 위해 사용
import cv2
# numpy는 벡터 및 거리 계산에 사용
import numpy as np
# deque는 trajectory history 저장에 사용
from collections import deque
# YOLO 객체 탐지 모델을 사용하기 위해 import
from ultralytics import YOLO
# DeepSORT tracker를 사용하기 위해 import
from deep_sort_realtime.deepsort_tracker import DeepSort


# ------------------------------------------------------------
# 탐지 대상 클래스 설정
# ------------------------------------------------------------
#
# 주요 기능:
# - YOLO가 탐지할 수 있는 여러 클래스 중 이 시스템에서 실제로 사용할 대상을 지정한다.
# - 사람은 충돌 보호 대상, 차량·동물은 사람과 충돌 가능성을 검사할 위험 객체로 구분한다.

# 사람 class id
PERSON_CLASS_IDS = [0]

# 차량 class id
VEHICLE_CLASS_IDS = [2, 3, 5, 7]

# 동물 class id
ANIMAL_CLASS_IDS = [15, 16, 17, 18, 19]

# 최종 탐지 허용 class
ALLOWED_CLASSES = (
    PERSON_CLASS_IDS
    + VEHICLE_CLASS_IDS
    #+ ANIMAL_CLASS_IDS
)


# ------------------------------------------------------------
# 사전 충돌 파라미터
# ------------------------------------------------------------
#
# 주요 기능:
# - 미래 경로 거리, TTC, 충돌 점수 등 사전 충돌 판단에 사용하는 핵심 기준값을 설정한다.
# - 이 값들을 조정하면 경보의 민감도와 미래 예측 범위를 변경할 수 있다.

# 미래 trajectory 최소거리 threshold
FUTURE_DISTANCE_THRESHOLD = 80.0

# TTC threshold
TTC_THRESHOLD = 4.0

# collision score threshold
COLLISION_SCORE_THRESHOLD = 50.0

# alarm 유지 프레임 수
ALARM_HOLD_FRAMES = 15

# 미래 trajectory step
FUTURE_STEPS = 20

# trajectory history 길이
HISTORY_LENGTH = 5

# 현재 방향 화살표 길이
TRACK_ARROW_SCALE = 7.0

# 미래 방향 화살표 길이
FUTURE_ARROW_SCALE = 3.0


# ------------------------------------------------------------
# FPS 최적화 파라미터
# ------------------------------------------------------------
#
# 주요 기능:
# - 모든 프레임에서 무거운 YOLO 추론을 수행하지 않도록 탐지 간격과 입력 크기를 조절한다.
# - 정확도와 처리 속도(FPS) 사이의 균형을 맞추기 위한 성능 최적화 설정이다.

# frame skip
# 3이면 3프레임 중 1프레임만 detection 수행
FRAME_SKIP = 3

# YOLO inference size
# 작을수록 FPS 증가
YOLO_IMAGE_SIZE = 416

# trajectory 표시 간격
DRAW_FUTURE_POINT_INTERVAL = 10


# ------------------------------------------------------------
# 중심점 계산
# ------------------------------------------------------------
#
# 주요 기능:
# - 객체의 bounding box 좌표에서 중앙점 (cx, cy)를 계산한다.
# - 이 중심점은 이동 이력, 속도 계산, 미래 trajectory 예측의 기준 위치로 사용된다.

def get_center(box):
    '''
    OpenCV 영상 좌표는 **왼쪽 위가 (0, 0) 즉 (x1,y1)**입니다.

    x1: 박스의 왼쪽(Left) x좌표
    y1: 박스의 위쪽(Top) y좌표
    x2: 박스의 오른쪽(Right) x좌표
    y2: 박스의 아래쪽(Bottom) y좌표
    '''
    # xyxy 좌표 분리
    x1, y1, x2, y2 = box

    # 중심 x 계산
    cx = (x1 + x2) / 2.0

    # 중심 y 계산
    cy = (y1 + y2) / 2.0

    # numpy 배열 반환
    return np.array(
        [cx, cy],
        dtype=np.float32
    )


# ------------------------------------------------------------
# Track 상태 클래스
# ------------------------------------------------------------
#
# 주요 기능:
# - DeepSORT로 추적되는 객체별 현재 위치, 클래스, 신뢰도, 이동 이력과 속도를 관리한다.
# - 이전 위치와 현재 위치의 차이로 velocity를 계산하고 이를 이용해 미래 이동 위치를 예측한다.

class TrackState:

    # 객체 상태 초기화
    def __init__(
        self,
        track_id,
        box,
        class_id,
        confidence,
        frame_index
    ):

        # track id 저장
        self.track_id = track_id

        # 현재 bounding box 저장
        self.box = np.array(
            box,
            dtype=np.float32
        )

        # class id 저장
        self.class_id = class_id

        # confidence 저장
        self.confidence = confidence

        # trajectory history 저장
        self.history = deque(
            maxlen=HISTORY_LENGTH
        )

        # 현재 중심 추가
        self.history.append(
            get_center(self.box)
        )

        # velocity 초기화
        self.velocity = np.array(
            [0.0, 0.0],
            dtype=np.float32
        )

        # 마지막 frame 저장
        self.last_frame_index = frame_index

    # 상태 업데이트
    def update(
        self,
        box,
        class_id,
        confidence,
        frame_index
    ):

        # 이전 중심 계산
        prev_center = get_center(
            self.box
        )

        # 새 bounding box 저장
        self.box = np.array(
            box,
            dtype=np.float32
        )

        # class 저장
        self.class_id = class_id

        # confidence 저장
        self.confidence = confidence

        current_center = get_center(
            self.box
        )

        # frame 간격 계산
        dt = max(
            1,
            frame_index
            - self.last_frame_index
        )

        # velocity 계산
        measured_velocity = (
            current_center
            - prev_center
        ) / float(dt)

        # velocity smoothing
        # 객체 탐지는 프레임마다 좌표가 흔들릴 수 있기 때문에
        # 바로 velocity를 사용하면 trajectory가 튀는 문제가 발생
        # 따라서 이전 velocity 80% + 현재 측정 velocity 20%를 섞어서
        # trajectory를 안정화
        self.velocity = (
            0.8 * self.velocity
            + 0.2 * measured_velocity
        )

        # trajectory history 저장
        self.history.append(
            current_center
        )

        # 마지막 frame 저장
        self.last_frame_index = frame_index

    def predict_future_points(self):

        current_center = get_center(
            self.box
        )

        # 미래 trajectory 리스트
        future_points = []

        for step in range(
            1,
            FUTURE_STEPS + 1
        ):

            # 미래 위치 계산
            # 현재 속도로 계속 이동한다고 가정하고
            # 미래 위치를 선형 예측한다.
            # FUTURE_ARROW_SCALE을 크게 하면
            # 더 먼 미래 trajectory를 예측하게 된다.
            future_point = (
                current_center
                + self.velocity
                * float(step)
                * FUTURE_ARROW_SCALE
            )

            # 미래 위치 저장
            future_points.append(
                future_point
            )

        # trajectory 반환
        return future_points


# ------------------------------------------------------------
# YOLO detection
# ------------------------------------------------------------
#
# 주요 기능:
# - 현재 영상 프레임을 YOLO에 입력하여 사람·차량 등 객체의 위치와 클래스를 탐지한다.
# - 허용 클래스만 남긴 뒤 탐지 결과를 DeepSORT가 요구하는 [left, top, width, height] 형식으로 변환한다.

def detect_objects(
    model,
    frame,
    conf_threshold
):

    # YOLO inference
    '''results = model.predict(
        source=frame,
        conf=conf_threshold,
        imgsz=YOLO_IMAGE_SIZE,
        verbose=False,
        half=True,
        device=0
    )'''
    results = model.predict(
        source=frame,
        conf=conf_threshold,
        imgsz=YOLO_IMAGE_SIZE,
        verbose=False
    )

    # 첫 번째 결과
    result = results[0]

    # detection 리스트
    detections = []

    # detection 없으면 반환
    if result.boxes is None:
        return detections

    # detection 순회
    for box in result.boxes:

        confidence = float(
            box.conf[0]
        )

        class_id = int(
            box.cls[0]
        )

        # 허용 class 아니면 제거
        if (
            class_id
            not in ALLOWED_CLASSES
        ):
            continue

        xyxy = (
            box.xyxy[0]
            .cpu()
            .numpy()
            .astype(np.float32)
        )

        # 좌표 분리
        x1, y1, x2, y2 = xyxy

        width = float(x2 - x1)

        height = float(y2 - y1)

        # 너무 작은 detection 제거
        if width <= 2 or height <= 2:
            continue

        # DeepSORT 입력 형식
        ltwh = [
            float(x1),
            float(y1),
            width,
            height
        ]

        # detection 저장
        detections.append(
            (
                ltwh,
                confidence,
                class_id
            )
        )

    # detection 반환
    return detections


# ------------------------------------------------------------
# 사전 collision 계산
# ------------------------------------------------------------
#
# 주요 기능:
# - 사람과 위험 객체의 미래 trajectory를 비교하여 충돌 가능성을 0~100점으로 계산한다.
# - 미래 최소 거리, TTC(Time To Collision), 실제 접근 여부를 결합하여 위험도를 평가한다.

def calculate_collision_score(
    track_a,
    track_b
):

    future_a = (
        track_a.predict_future_points()
    )

    future_b = (
        track_b.predict_future_points()
    )

    # 최소 미래 거리 초기화
    min_future_distance = 99999.0

    # trajectory 전체 비교
    # 작업자와 차량의 미래 trajectory 전체를 비교
    # 현재 위치가 아니라
    # 앞으로 trajectory가 가까워질 가능성을 계산하기 위한 로직

    for pa in future_a:

        for pb in future_b:

            # 미래 trajectory 거리 계산
            dist = np.linalg.norm(
                pa - pb
            )

            # 최소 거리 저장
            min_future_distance = min(
                min_future_distance,
                dist
            )

    center_a = get_center(
        track_a.box
    )

    center_b = get_center(
        track_b.box
    )

    # 상대 위치 계산
    relative_position = (
        center_a - center_b
    )

    # 상대 속도 계산
    relative_velocity = (
        track_a.velocity
        - track_b.velocity
    )

    # 접근 여부 판단
    # relative_position과 relative_velocity의 내적을 사용하여
    # 서로 가까워지는 방향인지 판단
    #
    # 내적 < 0:
    # 접근 중
    #
    # 내적 > 0:
    # 멀어지는 중
    approaching = (
        np.dot(
            relative_position,
            relative_velocity
        ) < 0
    )

    # 상대 속도 크기
    relative_speed = np.linalg.norm(
        relative_velocity
    )

    # TTC 계산
    if relative_speed < 0.5:

        # 속도 너무 작으면 TTC 무한대
        ttc = 999.0

    else:

        # 현재 거리 계산
        current_distance = np.linalg.norm(
            relative_position
        )

        # TTC 계산
        # TTC(Time To Collision)는
        # 현재 거리와 상대속도를 기반으로
        # 몇 초 뒤 충돌할 가능성이 있는지를 의미
        # 값이 작을수록 위험하다.
        ttc = (
            current_distance
            / relative_speed
        )

    # future score 계산
    future_score = (
        1.0
        - min(
            min_future_distance
            / FUTURE_DISTANCE_THRESHOLD,
            1.0
        )
    )

    # TTC score 계산
    ttc_score = (
        1.0
        - min(
            ttc / TTC_THRESHOLD,
            1.0
        )
    )

    # approaching score
    approaching_score = (
        1.0 if approaching else 0.0
    )

    # 최종 collision score 계산
    #
    # future_score:
    # 미래 trajectory가 얼마나 가까워지는가
    #
    # ttc_score:
    # 몇 초 뒤 충돌 가능한가
    #
    # approaching_score:
    # 실제로 서로 접근 중인가
    #
    # 현재 거리보다
    # 미래 trajectory 교차 가능성을 훨씬 더 중요하게 반영
    score = (
        75 * future_score
        + 15 * ttc_score
        + 10 * approaching_score
    )

    # score clipping
    score = np.clip(
        score,
        0.0,
        100.0
    )

    # 결과 반환
    return {
        "score": float(score),
        "ttc": float(ttc),
        "future_distance": float(
            min_future_distance
        )
    }


# ------------------------------------------------------------
# alarm 표시
# ------------------------------------------------------------
#
# 주요 기능:
# - 충돌 위험 점수가 임계값을 넘었을 때 영상 상단에 눈에 띄는 경고 메시지를 표시한다.
# - 영상 크기와 문자 크기를 이용해 경보 문구가 화면 중앙에 배치되도록 계산한다.

def draw_alarm_header(
    frame,
    text
):

    # frame 크기
    h, w = frame.shape[:2]

    # text 크기 계산
    (tw, th), _ = cv2.getTextSize(
        text,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        2
    )

    # 중앙 위치 계산
    x = int((w - tw) / 2)

    y = 55

    # background rectangle
    cv2.rectangle(
        frame,
        (x - 15, y - th - 10),
        (x + tw + 15, y + 10),
        (0, 0, 255),
        -1
    )

    cv2.putText(
        frame,
        text,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (255, 255, 255),
        2
    )


# ------------------------------------------------------------
# 객체 시각화
# ------------------------------------------------------------
#
# 주요 기능:
# - 추적 객체의 bounding box, Track ID, 이동 이력, 현재 이동 방향과 미래 trajectory를 영상에 표시한다.
# - 탐지·추적 결과와 충돌 예측 과정을 사용자가 화면에서 직관적으로 확인할 수 있게 한다.

def draw_track_visuals(
    frame,
    state,
    label,
    color
):

    # box 좌표
    x1, y1, x2, y2 = (
        state.box.astype(int)
    )

    # bounding box
    cv2.rectangle(
        frame,
        (x1, y1),
        (x2, y2),
        color,
        2
    )

    # label 출력
    cv2.putText(
        frame,
        label,
        (x1, max(20, y1 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        color,
        2
    )

    # trajectory history
    pts = list(state.history)

    # trajectory line
    for i in range(1, len(pts)):

        # 이전 점
        p1 = tuple(
            pts[i - 1].astype(int)
        )

        # 현재 점
        p2 = tuple(
            pts[i].astype(int)
        )

        # trajectory line
        cv2.line(
            frame,
            p1,
            p2,
            color,
            1
        )

    # 현재 중심
    center = get_center(
        state.box
    ).astype(int)

    # 현재 방향 화살표 끝점
    arrow_end = (
        center
        + (
            state.velocity
            * TRACK_ARROW_SCALE
        ).astype(int)
    )

    # 현재 방향 화살표
    cv2.arrowedLine(
        frame,
        tuple(center),
        tuple(arrow_end),
        color,
        2
    )

    # 미래 trajectory
    future_points = (
        state.predict_future_points()
    )

    # 미래 trajectory 일부만 표시
    for idx, point in enumerate(
        future_points
    ):

        # 일부 trajectory만 표시
        if (
            idx
            % DRAW_FUTURE_POINT_INTERVAL
            == 0
        ):

            cv2.circle(
                frame,
                tuple(point.astype(int)),
                2,
                color,
                -1
            )


# ------------------------------------------------------------
# main
# ------------------------------------------------------------
#
# 주요 기능:
# - 프로그램의 전체 실행 흐름을 담당하며 YOLO와 DeepSORT를 초기화하고 영상을 프레임 단위로 처리한다.
# - 객체 탐지·추적 → 상태 갱신 → 충돌 위험 계산 → 경보 및 시각화 → 영상 출력/저장을 순서대로 수행한다.

def main():

    # argparse 생성
    parser = argparse.ArgumentParser()

    # source 입력
    parser.add_argument(
        "--source",
        type=str,
        required=True
    )

    # model 입력
    parser.add_argument(
        "--model",
        type=str,
        default="yolov8n.pt"
    )

    # confidence 입력
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25
    )

    # 저장 경로
    parser.add_argument(
        "--save",
        type=str,
        default=None
    )

    # argument parse
    args = parser.parse_args()

    # YOLO 모델 로드
    model = YOLO(args.model)

    # model fuse
    model.fuse()

    # class names
    class_names = model.names

    
    # DeepSORT 객체 추적기 생성
    tracker = DeepSort(
        max_age=15,                 # 객체를 놓쳐도 추적을 유지할 최대 프레임 수
        n_init=1,                   # 객체를 Track으로 확정하기 위한 최소 검출 횟수
        max_cosine_distance=0.4,    # 동일 객체 판단을 위한 외형 특징 거리 기준
        nn_budget=30,               # 객체별로 저장할 외형 특징의 최대 개수
        embedder="mobilenet",       # 외형 특징 추출 모델
        bgr=True,                   # OpenCV의 BGR 이미지 사용
        embedder_gpu=False          # 임베딩 모델을 CPU에서 실행
    )
    
    # 영상 열기
    cap = cv2.VideoCapture(
        args.source
    )

    # 영상 열기 실패
    if not cap.isOpened():

        print("영상 열기 실패")
        return

    # FPS
    video_fps = cap.get(
        cv2.CAP_PROP_FPS
    )

    # FPS 보정
    video_fps = (
        video_fps
        if video_fps > 0
        else 30
    )

    frame_w = int(
        cap.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    frame_h = int(
        cap.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    # writer 초기화
    writer = None

    # 저장 옵션
    if args.save is not None:

        # codec
        fourcc = cv2.VideoWriter_fourcc(
            *"mp4v"
        )

        # writer 생성
        writer = cv2.VideoWriter(
            args.save,
            fourcc,
            video_fps,
            (frame_w, frame_h)
        )

    # track state 저장
    track_states = {}

    # alarm hold
    alarm_hold = 0

    # pause 상태
    paused = False

    frame_index = 0

    # 마지막 frame 저장
    last_display_frame = None

    # FPS 계산용 이전 시간
    prev_time = time.time()

    frame_counter = 0

    # 이전 tracking 결과
    previous_tracks = []

    # 메인 루프
    while True:

        # pause 상태
        if paused:

            # pause frame 생성
            pause_frame = (
                last_display_frame.copy()
                if last_display_frame
                is not None
                else np.zeros(
                    (
                        frame_h,
                        frame_w,
                        3
                    ),
                    dtype=np.uint8
                )
            )

            # pause text
            cv2.putText(
                pause_frame,
                "PAUSED - SPACE Resume / ESC Exit",
                (30, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2
            )

            cv2.imshow(
                "Pre-Collision Alarm",
                pause_frame
            )

            key = (
                cv2.waitKey(0)
                & 0xFF
            )

            # ESC 종료
            if key == 27:
                break

            # SPACE resume
            if key == 32:
                paused = False

            continue

        ret, frame = cap.read()

        if not ret:
            break

        # frame counter 증가
        frame_counter += 1

        # frame index 증가
        frame_index += 1

        # detection skip. 모든 프레임에서 detection하지 않고
        # 일부 프레임은 이전 tracking 결과를 재사용하여
        # FPS를 향상시킨다.
        if (
            frame_counter
            % FRAME_SKIP
            != 0
        ):

            # 이전 tracking 사용
            tracks = previous_tracks

        else:

            # detection 수행
            detections = detect_objects(
                model,
                frame,
                args.conf
            )

            # tracking 수행
            # YOLO는 프레임마다 객체를 새로 탐지하기 때문에
            # 같은 객체를 유지할 수 없음
            # DeepSORT는 appearance feature와 motion 정보를 사용하여
            # 동일 객체에 같은 ID를 유지
            tracks = tracker.update_tracks(
                detections,
                frame=frame
            )

            previous_tracks = tracks

        # 사람 track
        person_tracks = []

        # 위험 객체 track
        risk_tracks = []

        # tracking 순회
        for track in tracks:

            # confirm 안된 track 제거
            if not track.is_confirmed():
                continue

            # track id
            track_id = track.track_id

            # bounding box
            box = np.array(
                track.to_ltrb(),
                dtype=np.float32
            )

            class_id = (
                int(track.get_det_class())
                if track.get_det_class()
                is not None
                else -1
            )

            confidence = (
                float(track.get_det_conf())
                if track.get_det_conf()
                is not None
                else 0.0
            )

            # 새 track
            if track_id not in track_states:

                track_states[
                    track_id
                ] = TrackState(
                    track_id,
                    box,
                    class_id,
                    confidence,
                    frame_index
                )

            # 기존 track
            else:

                track_states[
                    track_id
                ].update(
                    box,
                    class_id,
                    confidence,
                    frame_index
                )

            state = track_states[
                track_id
            ]

            # 사람
            if class_id in PERSON_CLASS_IDS:

                color = (
                    255,
                    128,
                    0
                )

                person_tracks.append(
                    state
                )

                group_name = "person"

            # 차량/동물
            else:

                if (
                    class_id
                    in VEHICLE_CLASS_IDS
                ):

                    color = (
                        255,
                        0,
                        255
                    )

                    group_name = "vehicle"

                else:

                    color = (
                        0,
                        180,
                        255
                    )

                    group_name = "animal"

                risk_tracks.append(
                    state
                )

            # class 이름
            class_name = class_names.get(
                class_id,
                str(class_id)
            )

            # label 생성
            label = (
                f"ID:{track_id} "
                f"{group_name}/"
                f"{class_name}"
            )

            # visualization
            draw_track_visuals(
                frame,
                state,
                label,
                color
            )

        # 최고 collision score
        top_score = 0.0

        # 최고 collision 정보
        top_info = None

        # 사람 vs 위험객체
        for person in person_tracks:

            for risk_obj in risk_tracks:

                # collision 계산
                info = (
                    calculate_collision_score(
                        person,
                        risk_obj
                    )
                )

                # 최고 score 갱신
                if (
                    info["score"]
                    > top_score
                ):

                    top_score = (
                        info["score"]
                    )

                    top_info = info

        # threshold 넘으면 alarm
        if (
            top_score
            >= COLLISION_SCORE_THRESHOLD
        ):

            alarm_hold = (
                ALARM_HOLD_FRAMES
            )

        # alarm 출력
        if alarm_hold > 0:

            alarm_hold -= 1

            # alarm text
            alarm_text = (
                f"** COLLISION "
                f"ALARM "
                f"{top_score:.0f} **"
            )

            # alarm draw
            draw_alarm_header(
                frame,
                alarm_text
            )

        # FPS 계산
        current_time = time.time()

        fps = (
            1.0
            / (
                current_time
                - prev_time
            )
        )

        prev_time = current_time

        # FPS 표시
        cv2.putText(
            frame,
            f"FPS: {fps:.1f}",
            (20, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

        # 설명 표시
        '''cv2.putText(
            frame,
            "person / vehicle / animal",
            (20, frame_h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (220, 220, 220),
            1
        )'''

        if writer is not None:

            writer.write(frame)

        # 마지막 frame 저장
        last_display_frame = (
            frame.copy()
        )

        cv2.imshow(
            "Pre-Collision Alarm",
            frame
        )

        key = (
            cv2.waitKey(1)
            & 0xFF
        )

        # ESC 종료
        if key == 27:
            break

        # SPACE pause
        if key == 32:
            paused = True

    # cap release
    cap.release()

    # writer release
    if writer is not None:
        writer.release()

    # window close
    cv2.destroyAllWindows()


# ------------------------------------------------------------
# 시작점
# ------------------------------------------------------------
#
# 주요 기능:
# - 현재 Python 파일이 직접 실행된 경우 main() 함수를 호출하는 프로그램 시작 지점이다.
# - 다른 파일에서 모듈로 import할 때는 main()이 자동 실행되지 않도록 한다.

if __name__ == "__main__":

    main()
