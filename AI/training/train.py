"""Train a VisionGuard object detector with Ultralytics YOLO."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

import yaml

from AI.training.dataset import validate_dataset


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    """Supported YOLO training options."""

    data: str
    model: str = "yolo11n.pt"
    epochs: int = 100
    imgsz: int = 640
    batch: int = 16
    device: str | int | None = None
    workers: int = 4
    project: str = "AI/models/checkpoints"
    name: str = "visionguard"
    patience: int = 25
    seed: int = 42
    cache: bool | str = False
    fraction: float = 1.0
    resume: bool = False

    def __post_init__(self) -> None:
        if not self.data.strip():
            raise ValueError("data must point to a dataset YAML file")
        if not self.model.strip():
            raise ValueError("model cannot be empty")
        if self.epochs < 1 or self.imgsz < 32 or self.batch == 0:
            raise ValueError(
                "epochs and batch must be non-zero; imgsz must be at least 32"
            )
        if self.workers < 0 or self.patience < 0:
            raise ValueError("workers and patience cannot be negative")
        if not 0.0 < self.fraction <= 1.0:
            raise ValueError("fraction must be greater than 0 and at most 1")


@dataclass(frozen=True, slots=True)
class TrainingResult:
    """Paths produced by one completed training run."""

    save_dir: str
    best_checkpoint: str
    last_checkpoint: str


def load_training_config(
    config_path: str | Path,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> TrainingConfig:
    """Load supported options from YAML and apply non-None CLI overrides."""

    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"training config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("training config must contain a YAML mapping")

    supported = {item.name for item in fields(TrainingConfig)}
    unknown = set(raw) - supported
    if unknown:
        raise ValueError(f"unknown training options: {', '.join(sorted(unknown))}")
    values = dict(raw)
    values.update(
        {key: value for key, value in (overrides or {}).items() if value is not None}
    )
    return TrainingConfig(**values)


def run_training(
    config: TrainingConfig,
    *,
    validate_data: bool = True,
    model_factory: Callable[[str], Any] | None = None,
) -> TrainingResult:
    """Validate the dataset, run training, and verify checkpoint creation."""

    data_path = Path(config.data).expanduser().resolve()
    if validate_data:
        report = validate_dataset(data_path)
        if not report.valid:
            preview = "\n".join(report.errors[:10])
            raise ValueError(f"dataset validation failed:\n{preview}")

    if model_factory is None:
        from ultralytics import YOLO

        model_factory = YOLO
    model = model_factory(config.model)
    options = asdict(config)
    options["data"] = str(data_path)
    options["project"] = str(Path(config.project).expanduser().resolve())
    options.pop("model")
    training_output = model.train(**options)

    raw_save_dir = getattr(training_output, "save_dir", None)
    if raw_save_dir is None:
        trainer = getattr(model, "trainer", None)
        raw_save_dir = getattr(trainer, "save_dir", None)
    if raw_save_dir is None:
        raise RuntimeError("YOLO training did not report an output directory")

    save_dir = Path(raw_save_dir).resolve()
    best = save_dir / "weights" / "best.pt"
    last = save_dir / "weights" / "last.pt"
    if not best.is_file() or not last.is_file():
        raise RuntimeError(
            f"training completed without expected checkpoints: {save_dir}"
        )
    return TrainingResult(str(save_dir), str(best), str(last))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train the VisionGuard YOLO model")
    parser.add_argument(
        "--config", default="AI/configs/training.yaml.example", help="Training YAML"
    )
    parser.add_argument("--data", help="Override dataset YAML path")
    parser.add_argument("--model", help="Override base model or checkpoint")
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--imgsz", type=int)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--device")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--project")
    parser.add_argument("--name")
    parser.add_argument("--fraction", type=float)
    parser.add_argument("--skip-dataset-validation", action="store_true")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    override_names = (
        "data",
        "model",
        "epochs",
        "imgsz",
        "batch",
        "device",
        "workers",
        "project",
        "name",
        "fraction",
    )
    overrides = {name: getattr(args, name) for name in override_names}
    config = load_training_config(args.config, overrides=overrides)
    print(json.dumps(asdict(config), indent=2, ensure_ascii=False))
    result = run_training(
        config,
        validate_data=not args.skip_dataset_validation,
    )
    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
