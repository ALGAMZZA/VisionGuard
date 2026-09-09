import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib import error

spec = importlib.util.spec_from_file_location("video_smoke", Path(__file__).parents[1] / "video_smoke.py")
video = importlib.util.module_from_spec(spec)
spec.loader.exec_module(video)


class Encoded:
    def tobytes(self):
        return b"jpeg"


class Capture:
    def __init__(self, frames=7):
        self.frames = frames
        self.index = 0
        self.released = False

    def isOpened(self):
        return True

    def get(self, prop):
        return 30 if prop == 1 else self.frames

    def read(self):
        if self.index == self.frames:
            return False, None
        self.index += 1
        return True, "frame"

    def release(self):
        self.released = True


class Cv2:
    CAP_PROP_FPS = 1
    CAP_PROP_FRAME_COUNT = 2

    def __init__(self, frames=7):
        self.capture = Capture(frames)

    def VideoCapture(self, path):
        return self.capture

    def imencode(self, ext, frame):
        return True, Encoded()


class Api:
    def __init__(self, failure=None, end_failure=False):
        self.fields = []
        self.ended = None
        self.failure = failure
        self.end_failure = end_failure

    def analyze(self, jpeg, fields):
        self.fields.append(fields)
        if len(self.fields) == 2 and self.failure:
            raise self.failure
        return {"cameraId": "camera-1", "streamId": "test", "eventIds": [1],
                "aiMode": "mock", "prediction": {"overall_risk": "WARNING"}}

    def post_json(self, path, payload):
        self.ended = payload
        if self.end_failure:
            raise RuntimeError("end unavailable")
        return {"closedEventIds": [1]}

    def call(self, method, path):
        return {"event": {"id": 1, "status": "CLOSED", "streamId": "test"}}


def args(**overrides):
    values = dict(source=Path("test.mp4"), base_url="http://localhost:8080", timeout=1,
                  retries=0, source_fps=None, stride=3, reset_ai_url=None, camera_id="camera-1",
                  stream_id="test", start_time=datetime(2026, 9, 7, tzinfo=timezone.utc), max_frames=0)
    values.update(overrides)
    return argparse.Namespace(**values)


class VideoTests(unittest.TestCase):
    def test_stride_uses_video_time_and_adjusted_fps_then_closes(self):
        api, cv2, report = Api(), Cv2(), {}
        self.assertEqual(video.run(args(), cv2, report, api), 0)
        self.assertEqual([f["frameId"] for f in api.fields], ["0", "3", "6"])
        self.assertEqual([f["fps"] for f in api.fields], [10, 10, 10])
        self.assertEqual(api.fields[1]["capturedAt"], "2026-09-07T00:00:00.100000Z")
        self.assertEqual(api.ended["endedAt"], "2026-09-07T00:00:00.200000Z")
        self.assertTrue(report["verifiedClosed"])
        self.assertTrue(cv2.capture.released)

    def test_max_frames_still_closes(self):
        api, report = Api(), {}
        self.assertEqual(video.run(args(max_frames=1), Cv2(), report, api), 0)
        self.assertEqual(report["stopReason"], "MAX_FRAMES")
        self.assertEqual(len(api.fields), 1)
        self.assertIsNotNone(api.ended)

    def test_failure_closes_at_last_attempt_but_remains_failed(self):
        api, report = Api(failure=RuntimeError("connection lost")), {}
        self.assertEqual(video.run(args(), Cv2(), report, api), 1)
        self.assertEqual(report["status"], "FAILED")
        self.assertEqual(report["framesSent"], 1)
        self.assertEqual(api.ended["endedAt"], api.fields[1]["capturedAt"])

    def test_interrupt_attempts_completion(self):
        api, report = Api(failure=KeyboardInterrupt()), {}
        self.assertEqual(video.run(args(), Cv2(), report, api), 130)
        self.assertEqual(report["status"], "INTERRUPTED")
        self.assertIsNotNone(api.ended)

    def test_completion_failure_is_not_reported_as_pass(self):
        api, report = Api(end_failure=True), {}
        self.assertEqual(video.run(args(), Cv2(), report, api), 1)
        self.assertFalse(report["verifiedClosed"])
        self.assertIn("end unavailable", report["completionError"])

    def test_empty_video_does_not_close_unknown_stream(self):
        api, report = Api(), {}
        self.assertEqual(video.run(args(), Cv2(frames=0), report, api), 1)
        self.assertIsNone(api.ended)

    def test_network_retry_keeps_identical_request_bytes(self):
        attempts = []
        def fail(req, timeout):
            attempts.append(req.data)
            raise error.URLError("lost")
        with patch.object(video.request, "urlopen", side_effect=fail), patch.object(video.time, "sleep"):
            with self.assertRaises(RuntimeError):
                video.Api("http://test", 1, 1).analyze(b"jpeg", {"frameId": "1"})
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0], attempts[1])

    def test_naive_start_time_is_rejected(self):
        with self.assertRaises(argparse.ArgumentTypeError):
            video.timestamp("2026-09-07T00:00:00")


if __name__ == "__main__":
    unittest.main()
