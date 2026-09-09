"""Selectively extract training inputs from an NVIDIA artifacts TAR shard."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tarfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

DEFAULT_SUFFIXES = (
    ".rgb.mp4",
    ".object_detection.jsonl",
    ".meta.json",
)


@dataclass(frozen=True)
class ExtractionSummary:
    archive: str
    output_dir: str
    selected_files: int
    extracted_files: int
    skipped_files: int
    selected_bytes: int


def _validate_member(member: tarfile.TarInfo) -> None:
    path = PurePosixPath(member.name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe TAR member path: {member.name}")
    if not member.isfile():
        raise ValueError(f"selected TAR member is not a regular file: {member.name}")


def extract_artifacts(
    archive_path: str | Path,
    output_dir: str | Path,
    *,
    suffixes: Sequence[str] = DEFAULT_SUFFIXES,
    overwrite: bool = False,
) -> ExtractionSummary:
    """Extract only files ending in ``suffixes`` while blocking path traversal."""

    archive = Path(archive_path).expanduser().resolve()
    destination_root = Path(output_dir).expanduser().resolve()
    normalized_suffixes = tuple(suffixes)

    if not archive.is_file():
        raise FileNotFoundError(f"archive not found: {archive}")
    if not normalized_suffixes or any(not suffix for suffix in normalized_suffixes):
        raise ValueError("at least one non-empty suffix is required")

    destination_root.mkdir(parents=True, exist_ok=True)

    extracted = 0
    skipped = 0
    selected_bytes = 0

    with tarfile.open(archive, mode="r:*") as tar:
        members = [
            member
            for member in tar.getmembers()
            if member.name.endswith(normalized_suffixes)
        ]
        for member in members:
            _validate_member(member)

        for member in members:
            selected_bytes += member.size
            target = destination_root.joinpath(*PurePosixPath(member.name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)

            if target.exists() and not overwrite:
                if target.is_file() and target.stat().st_size == member.size:
                    skipped += 1
                    continue
                raise FileExistsError(
                    f"target already exists with a different size: {target}"
                )

            source = tar.extractfile(member)
            if source is None:
                raise OSError(f"could not read TAR member: {member.name}")

            temporary = target.with_name(f"{target.name}.part")
            try:
                with source, temporary.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                os.replace(temporary, target)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            extracted += 1

    return ExtractionSummary(
        archive=str(archive),
        output_dir=str(destination_root),
        selected_files=len(members),
        extracted_files=extracted,
        skipped_files=skipped,
        selected_bytes=selected_bytes,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract RGB videos and 2D annotations from an artifacts TAR shard."
    )
    parser.add_argument("--archive", required=True, help="Path to the artifacts TAR file")
    parser.add_argument("--output", required=True, help="Directory for selected files")
    parser.add_argument(
        "--include",
        action="append",
        dest="suffixes",
        help="File suffix to include; may be supplied multiple times",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace selected files that already exist",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    summary = extract_artifacts(
        args.archive,
        args.output,
        suffixes=args.suffixes or DEFAULT_SUFFIXES,
        overwrite=args.overwrite,
    )
    print(json.dumps(asdict(summary), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
