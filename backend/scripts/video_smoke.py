#!/usr/bin/env python3
"""Send a constant-frame-rate local video through VisionGuard and close its stream.

Requires OpenCV (already installed in AI/.venv); HTTP uses the Python standard library.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import math
from pathlib import Path
import socket
import sys
import time
from urllib import error, request
import uuid


def iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError("UTC 오프셋이 필요합니다")
        return result.astimezone(timezone.utc)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("시각은 UTC 오프셋이 있는 ISO 8601 형식이어야 합니다") from exc


class Api:
    def __init__(self, base_url: str, timeout: float, retries: int):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def call(self, method: str, path: str, data: bytes | None = None,
             content_type: str = "application/json") -> dict:
        req = request.Request(self.base_url + path, data=data, method=method,
                              headers={"Content-Type": content_type})
        for attempt in range(self.retries + 1):
            try:
                with request.urlopen(req, timeout=self.timeout) as response:
                    return json.load(response)
            except error.HTTPError as exc:
                # Do not blindly retry application errors or AI failures.
                detail = exc.read(4096).decode("utf-8", errors="replace")
                raise RuntimeError(f"{method} {path}: HTTP {exc.code}: {detail}") from exc
            except (error.URLError, TimeoutError, socket.timeout) as exc:
                if attempt == self.retries:
                    raise RuntimeError(f"{method} {path}: 연결 실패: {exc}") from exc
                print(f"응답 연결 실패, 동일 요청 재시도 {attempt + 1}/{self.retries}", file=sys.stderr)
                time.sleep(min(2 ** attempt, 4))
        raise AssertionError("unreachable")

    def post_json(self, path: str, payload: dict) -> dict:
        return self.call("POST", path, json.dumps(payload).encode("utf-8"))

    def analyze(self, jpeg: bytes, fields: dict) -> dict:
        boundary = "visionguard-" + uuid.uuid4().hex
        body = bytearray()
        for key, value in fields.items():
            body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
        body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="frame.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode())
        body.extend(jpeg)
        body.extend(f"\r\n--{boundary}--\r\n".encode())
        return self.call("POST", "/api/analyses", bytes(body), f"multipart/form-data; boundary={boundary}")


def run(args, cv2, report: dict, api: Api | None = None) -> int:
    api = api or Api(args.base_url, args.timeout, args.retries)
    capture = cv2.VideoCapture(str(args.source))
    last_attempt = None
    event_ids: set[int] = set()
    failure = None
    report.update(status="RUNNING", framesSent=0, decodedFrames=0, riskCounts={}, eventIds=[])
    try:
        if not capture.isOpened():
            raise RuntimeError("영상 파일을 열 수 없습니다")
        source_fps = args.source_fps or capture.get(cv2.CAP_PROP_FPS)
        if not math.isfinite(source_fps) or source_fps <= 0:
            raise RuntimeError("영상 FPS를 읽을 수 없습니다. --source-fps로 지정하세요")
        effective_fps = source_fps / args.stride
        if not 0 < effective_fps <= 240:
            raise RuntimeError("처리 FPS는 0 초과 240 이하여야 합니다. --stride를 조정하세요")
        raw_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
        expected_count = int(raw_count) if math.isfinite(raw_count) and raw_count > 0 else 0
        report.update(sourceFps=source_fps, effectiveFps=effective_fps,
                      expectedSourceFrames=expected_count, stride=args.stride)
        if args.reset_ai_url:
            # Reset is opt-in and never retried: a delayed reset could erase an active tracker.
            report["aiReset"] = Api(args.reset_ai_url, args.timeout, 0).call("POST", "/reset")
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                if index == 0:
                    raise RuntimeError("영상에 읽을 수 있는 프레임이 없습니다")
                if expected_count and index < expected_count - 1:
                    raise RuntimeError(f"영상이 예상보다 일찍 끝났습니다: {index}/{expected_count} 프레임")
                report["stopReason"] = "EOF"
                break
            report["decodedFrames"] += 1
            frame_index = index
            index += 1
            if frame_index % args.stride:
                continue
            ok, encoded = cv2.imencode(".jpg", frame)
            if not ok:
                raise RuntimeError(f"프레임 {frame_index} JPEG 변환 실패")
            captured_at = iso(args.start_time + timedelta(seconds=frame_index / source_fps))
            last_attempt = captured_at
            result = api.analyze(encoded.tobytes(), {
                "cameraId": args.camera_id, "streamId": args.stream_id,
                "frameId": str(frame_index), "capturedAt": captured_at, "fps": effective_fps,
            })
            if result.get("streamId") != args.stream_id or result.get("cameraId") != args.camera_id:
                raise RuntimeError("분석 응답의 카메라/스트림이 요청과 다릅니다")
            risk = result["prediction"]["overall_risk"]
            report["riskCounts"][risk] = report["riskCounts"].get(risk, 0) + 1
            report["framesSent"] += 1
            report["aiMode"] = result["aiMode"]
            event_ids.update(result["eventIds"])
            print(f'frame={frame_index} risk={risk} events={result["eventIds"]}', flush=True)
            if args.max_frames and report["framesSent"] >= args.max_frames:
                report["stopReason"] = "MAX_FRAMES"
                break
    except KeyboardInterrupt:
        failure = "사용자가 중단했습니다"
        report["status"] = "INTERRUPTED"
    except Exception as exc:
        failure = str(exc)
        report["status"] = "FAILED"
    finally:
        capture.release()
        report["eventIds"] = sorted(event_ids)
        if failure:
            report["error"] = failure
        if last_attempt is not None:
            try:
                # Includes the last attempted frame in case its response was lost after commit.
                report["completionRequest"] = {
                    "cameraId": args.camera_id, "streamId": args.stream_id, "endedAt": last_attempt,
                }
                report["completion"] = api.post_json("/api/streams/end", report["completionRequest"])
                event_ids.update(report["completion"]["closedEventIds"])
                report["eventIds"] = sorted(event_ids)
                details = []
                for event_id in sorted(event_ids):
                    event = api.call("GET", f"/api/risk-events/{event_id}")["event"]
                    if event["status"] != "CLOSED" or event["streamId"] != args.stream_id:
                        raise RuntimeError(f"이벤트 {event_id} 종료 검증 실패")
                    details.append(event)
                report["events"] = details
                report["verifiedClosed"] = True
            except Exception as exc:
                report["completionError"] = str(exc)
                report["verifiedClosed"] = False
                if report["status"] != "INTERRUPTED":
                    report["status"] = "FAILED"
        if report["status"] == "RUNNING":
            report["status"] = "PASSED"
    return 0 if report["status"] == "PASSED" else 130 if report["status"] == "INTERRUPTED" else 1


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path, help="로컬 MP4 등 일정 FPS 영상")
    p.add_argument("--base-url", default="http://localhost:8080")
    p.add_argument("--camera-id", default="camera-1")
    p.add_argument("--stream-id", default=None, help="기본값: 실행마다 새 UUID")
    p.add_argument("--start-time", type=timestamp, default=None)
    p.add_argument("--stride", type=int, default=1, help="N프레임마다 전송 (기본 1)")
    p.add_argument("--source-fps", type=float, help="원본 영상 FPS 덮어쓰기")
    p.add_argument("--max-frames", type=int, default=0, help="최대 전송 프레임 수 (0: 전체)")
    p.add_argument("--timeout", type=float, default=45)
    p.add_argument("--retries", type=int, default=2, help="응답 연결 실패 시 동일 요청 재시도 수")
    p.add_argument("--reset-ai-url", help="실제 AI 서버 /reset 호출 주소 (예: http://localhost:8000)")
    p.add_argument("--report", type=Path, help="결과 JSON 경로 (기존 파일 덮어쓰기 금지)")
    return p


def main(argv=None) -> int:
    p = parser()
    args = p.parse_args(argv)
    if not args.source.is_file():
        p.error("source는 존재하는 로컬 영상 파일이어야 합니다")
    if args.stride < 1 or args.max_frames < 0 or args.retries < 0:
        p.error("stride >= 1, max-frames >= 0, retries >= 0이어야 합니다")
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        p.error("timeout은 양수여야 합니다")
    if args.source_fps is not None and (not math.isfinite(args.source_fps) or args.source_fps <= 0):
        p.error("source-fps는 양수여야 합니다")
    args.stream_id = args.stream_id or "video-" + uuid.uuid4().hex
    if any(not value.strip() or len(value) > 100 or "\r" in value or "\n" in value
           for value in [args.camera_id, args.stream_id]):
        p.error("camera-id와 stream-id는 줄바꿈 없는 1~100자여야 합니다")
    args.start_time = args.start_time or datetime.now(timezone.utc)
    try:
        import cv2
    except ImportError:
        print("OpenCV가 필요합니다. ../AI/.venv/bin/python scripts/video_smoke.py ... 로 실행하세요", file=sys.stderr)
        return 1
    output = args.report or Path("reports") / ("video-smoke-" + uuid.uuid4().hex + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"source": str(args.source.resolve()), "cameraId": args.camera_id,
              "streamId": args.stream_id, "startTime": iso(args.start_time), "baseUrl": args.base_url}
    try:
        with output.open("x", encoding="utf-8") as handle:
            code = run(args, cv2, report)
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    except FileExistsError:
        p.error(f"결과 파일이 이미 있습니다: {output}")
    print(f'{report["status"]}: {report["framesSent"]} frames, {len(report["eventIds"])} events; report={output}')
    return code


if __name__ == "__main__":
    raise SystemExit(main())
