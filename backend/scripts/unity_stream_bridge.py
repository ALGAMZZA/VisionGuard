from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone

import requests


# ============================================================
# 설정
# ============================================================

TARGET_FPS = 2.0

CAMERAS = [
    {
        "camera_id": "camera-1",
        "snapshot_url": "http://127.0.0.1:8080/snapshot.jpg",
        "stream_prefix": "unity-zone-01",
    },
    {
        "camera_id": "camera-2",
        "snapshot_url": "http://127.0.0.1:8081/snapshot.jpg",
        "stream_prefix": "unity-zone-02",
    },
]

REQUEST_TIMEOUT = 15


def get_wsl_ip() -> str:
    result = subprocess.run(
        ["wsl", "hostname", "-I"],
        capture_output=True,
        text=True,
        check=True,
    )

    addresses = result.stdout.strip().split()

    if not addresses:
        raise RuntimeError("WSL IP를 찾을 수 없습니다.")

    return addresses[0]


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def create_streams() -> None:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")

    for camera in CAMERAS:
        camera["stream_id"] = (
            f"{camera['stream_prefix']}-{run_id}"
        )
        camera["frame_id"] = 0


def capture_snapshot(
    session: requests.Session,
    camera: dict,
) -> bytes:

    response = session.get(
        camera["snapshot_url"],
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    return response.content


def send_frame(
    session: requests.Session,
    backend_url: str,
    camera: dict,
    image: bytes,
) -> dict:

    camera["frame_id"] += 1

    frame_id = str(camera["frame_id"])

    files = {
        "file": (
            "frame.jpg",
            image,
            "image/jpeg",
        )
    }

    data = {
        "cameraId": camera["camera_id"],
        "streamId": camera["stream_id"],
        "frameId": frame_id,
        "capturedAt": utc_now(),

        # 실제 Bridge가 전송하는 속도
        "fps": str(TARGET_FPS),
    }

    response = session.post(
        f"{backend_url}/api/analyses",
        files=files,
        data=data,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()

    return response.json()


def print_result(
    camera: dict,
    result: dict,
) -> None:

    prediction = result.get("prediction") or {}

    risk = prediction.get(
        "overall_risk",
        "UNKNOWN",
    )

    processing_ms = prediction.get(
        "processing_time_ms",
        0,
    )

    detections = prediction.get(
        "detections",
        [],
    )

    objects = []

    for detection in detections:
        class_name = detection.get(
            "class_name",
            "object",
        )

        track_id = detection.get(
            "track_id",
            "?",
        )

        confidence = detection.get(
            "confidence",
            0,
        )

        objects.append(
            f"{class_name}#{track_id}"
            f"({confidence:.2f})"
        )

    object_text = (
        ", ".join(objects)
        if objects
        else "-"
    )

    print(
        f"[{camera['camera_id']}] "
        f"frame={camera['frame_id']} | "
        f"risk={risk} | "
        f"objects={object_text} | "
        f"AI={processing_ms:.1f}ms"
    )


def end_stream(
    session: requests.Session,
    backend_url: str,
    camera: dict,
) -> None:

    try:
        response = session.post(
            f"{backend_url}/api/streams/end",
            json={
                "cameraId": camera["camera_id"],
                "streamId": camera["stream_id"],
                "endedAt": utc_now(),
            },
            timeout=5,
        )

        if response.ok:
            print(
                f"[{camera['camera_id']}] "
                "stream 종료 처리 완료"
            )
        else:
            print(
                f"[{camera['camera_id']}] "
                f"stream 종료 실패: "
                f"{response.status_code}"
            )

    except Exception as exc:
        print(
            f"[{camera['camera_id']}] "
            f"stream 종료 요청 실패: {exc}"
        )


def main() -> None:

    print("VisionGuard Unity 2-Camera Bridge")
    print("--------------------------------")

    wsl_ip = get_wsl_ip()

    backend_url = (
        f"http://{wsl_ip}:8082"
    )

    create_streams()

    print(f"WSL IP  : {wsl_ip}")
    print(f"Backend : {backend_url}")
    print(f"FPS     : {TARGET_FPS}")
    print()

    for camera in CAMERAS:
        print(
            f"{camera['camera_id']} "
            f"→ {camera['snapshot_url']}"
        )

        print(
            f"streamId: "
            f"{camera['stream_id']}"
        )

    print()
    print(
        "Ctrl+C로 종료할 수 있습니다."
    )
    print()

    session = requests.Session()

    frame_interval = (
        1.0 / TARGET_FPS
    )

    try:

        while True:

            cycle_started = time.perf_counter()

            for camera in CAMERAS:

                try:

                    image = capture_snapshot(
                        session,
                        camera,
                    )

                    result = send_frame(
                        session,
                        backend_url,
                        camera,
                        image,
                    )

                    print_result(
                        camera,
                        result,
                    )

                except requests.RequestException as exc:

                    print(
                        f"[{camera['camera_id']}] "
                        f"요청 실패: {exc}"
                    )

                except Exception as exc:

                    print(
                        f"[{camera['camera_id']}] "
                        f"오류: {exc}"
                    )

            elapsed = (
                time.perf_counter()
                - cycle_started
            )

            sleep_time = (
                frame_interval
                - elapsed
            )

            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:

        print()
        print("Bridge 종료 중...")

        for camera in CAMERAS:
            end_stream(
                session,
                backend_url,
                camera,
            )

        print("Bridge 종료 완료.")


if __name__ == "__main__":
    main()