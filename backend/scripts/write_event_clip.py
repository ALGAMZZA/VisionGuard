"""Encode ordered JPEG frames as an MP4 event clip."""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frames", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--fps", required=True, type=float)
    args = parser.parse_args()

    frame_paths = sorted(Path(args.frames).glob("*.jpg"))
    if not frame_paths or args.fps <= 0:
        raise SystemExit("frames and a positive fps are required")
    first = cv2.imread(str(frame_paths[0]))
    if first is None:
        raise SystemExit("first frame is not a readable JPEG")
    height, width = first.shape[:2]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(
        str(output), cv2.VideoWriter_fourcc(*"VP80"), args.fps, (width, height)
    )
    if not writer.isOpened():
        raise SystemExit("could not open MP4 writer")
    try:
        for frame_path in frame_paths:
            frame = cv2.imread(str(frame_path))
            if frame is None or frame.shape[:2] != (height, width):
                raise SystemExit(f"invalid or inconsistent frame: {frame_path}")
            writer.write(frame)
    finally:
        writer.release()
    if not output.is_file() or output.stat().st_size == 0:
        raise SystemExit("MP4 output was not created")


if __name__ == "__main__":
    main()
