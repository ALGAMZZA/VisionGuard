"""Evaluate a trained YOLO model and decide whether it meets release criteria."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

import yaml

from AI.training.dataset import validate_dataset


@dataclass(frozen=True, slots=True)
class AcceptanceCriteria:
    """Minimum aggregate metrics required for model promotion."""

    min_precision: float = 0.7
    min_recall: float = 0.7
    min_map50: float = 0.75
    min_map50_95: float = 0.5
    min_class_map50: float = 0.65
    max_inference_ms: float | None = None

    def __post_init__(self) -> None:
        metric_values = (
            self.min_precision,
            self.min_recall,
            self.min_map50,
            self.min_map50_95,
            self.min_class_map50,
        )
        if not all(0.0 <= value <= 1.0 for value in metric_values):
            raise ValueError("metric acceptance thresholds must be within 0..1")
        if self.max_inference_ms is not None and self.max_inference_ms <= 0:
            raise ValueError("max_inference_ms must be positive when configured")


@dataclass(frozen=True, slots=True)
class EvaluationConfig:
    """Ultralytics validation options and report destination."""

    model: str
    data: str
    split: str = "val"
    imgsz: int = 640
    batch: int = 16
    device: str | int | None = None
    workers: int = 4
    project: str = "AI/reports/evaluation"
    name: str = "visionguard"
    plots: bool = True
    save_json: bool = False

    def __post_init__(self) -> None:
        if not self.model.strip() or not self.data.strip():
            raise ValueError("model and data paths are required")
        if self.split not in {"val", "test"}:
            raise ValueError("split must be val or test")
        if self.imgsz < 32 or self.batch == 0 or self.workers < 0:
            raise ValueError("invalid imgsz, batch, or workers value")


@dataclass(frozen=True, slots=True)
class MetricValues:
    precision: float
    recall: float
    map50: float
    map50_95: float


@dataclass(frozen=True, slots=True)
class ClassMetrics:
    class_id: int
    class_name: str
    metrics: MetricValues


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    model: str
    data: str
    split: str
    overall: MetricValues
    per_class: list[ClassMetrics]
    speed_ms_per_image: dict[str, float]
    passed: bool
    failures: list[str]
    output_dir: str
    report_path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_evaluation_settings(
    config_path: str | Path,
    *,
    overrides: Mapping[str, Any] | None = None,
) -> tuple[EvaluationConfig, AcceptanceCriteria]:
    """Load evaluation and acceptance settings from a YAML mapping."""

    path = Path(config_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"evaluation config not found: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise TypeError("evaluation config must contain a YAML mapping")

    raw_criteria = raw.pop("acceptance", {})
    if not isinstance(raw_criteria, dict):
        raise TypeError("acceptance settings must contain a YAML mapping")
    supported = {item.name for item in fields(EvaluationConfig)}
    unknown = set(raw) - supported
    if unknown:
        raise ValueError(f"unknown evaluation options: {', '.join(sorted(unknown))}")
    values = dict(raw)
    values.update(
        {key: value for key, value in (overrides or {}).items() if value is not None}
    )
    return EvaluationConfig(**values), AcceptanceCriteria(**raw_criteria)


def _metric_values(values: Sequence[float]) -> MetricValues:
    if len(values) != 4:
        raise RuntimeError("YOLO returned an unexpected metric tuple")
    return MetricValues(*(float(value) for value in values))


def _class_name(names: Any, class_id: int) -> str:
    if isinstance(names, dict):
        return str(names.get(class_id, class_id))
    if isinstance(names, Sequence) and not isinstance(names, str):
        return str(names[class_id]) if class_id < len(names) else str(class_id)
    return str(class_id)


def _extract_class_metrics(metrics: Any, names: Any) -> list[ClassMetrics]:
    box = metrics.box
    raw_indices = getattr(box, "ap_class_index", ())
    return [
        ClassMetrics(
            class_id=int(class_id),
            class_name=_class_name(names, int(class_id)),
            metrics=_metric_values(box.class_result(result_index)),
        )
        for result_index, class_id in enumerate(raw_indices)
    ]


def evaluate_acceptance(
    overall: MetricValues,
    per_class: Sequence[ClassMetrics],
    speed: Mapping[str, float],
    criteria: AcceptanceCriteria,
    *,
    expected_class_ids: Sequence[int],
) -> list[str]:
    """Return human-readable release failures; an empty list means pass."""

    failures: list[str] = []
    aggregate_checks = (
        ("precision", overall.precision, criteria.min_precision),
        ("recall", overall.recall, criteria.min_recall),
        ("mAP50", overall.map50, criteria.min_map50),
        ("mAP50-95", overall.map50_95, criteria.min_map50_95),
    )
    for label, actual, required in aggregate_checks:
        if actual < required:
            failures.append(f"{label} {actual:.4f} is below required {required:.4f}")

    metrics_by_class = {item.class_id: item for item in per_class}
    for class_id in expected_class_ids:
        item = metrics_by_class.get(class_id)
        if item is None:
            failures.append(f"class {class_id} has no evaluation metrics")
        elif item.metrics.map50 < criteria.min_class_map50:
            failures.append(
                f"class {class_id} ({item.class_name}) mAP50 "
                f"{item.metrics.map50:.4f} is below required "
                f"{criteria.min_class_map50:.4f}"
            )

    inference_ms = speed.get("inference")
    if (
        criteria.max_inference_ms is not None
        and inference_ms is not None
        and inference_ms > criteria.max_inference_ms
    ):
        failures.append(
            f"inference {inference_ms:.2f}ms exceeds {criteria.max_inference_ms:.2f}ms"
        )
    return failures


def run_evaluation(
    config: EvaluationConfig,
    criteria: AcceptanceCriteria | None = None,
    *,
    validate_data: bool = True,
    model_factory: Callable[[str], Any] | None = None,
) -> EvaluationReport:
    """Run YOLO validation, write a JSON report, and return its contents."""

    model_path = Path(config.model).expanduser().resolve()
    data_path = Path(config.data).expanduser().resolve()
    if not model_path.is_file():
        raise FileNotFoundError(f"model checkpoint not found: {model_path}")
    if validate_data:
        dataset_report = validate_dataset(data_path)
        if not dataset_report.valid:
            preview = "\n".join(dataset_report.errors[:10])
            raise ValueError(f"dataset validation failed:\n{preview}")
    else:
        dataset_report = None

    if model_factory is None:
        from ultralytics import YOLO

        model_factory = YOLO
    model = model_factory(str(model_path))
    output_project = Path(config.project).expanduser().resolve()
    metrics = model.val(
        data=str(data_path),
        split=config.split,
        imgsz=config.imgsz,
        batch=config.batch,
        device=config.device,
        workers=config.workers,
        project=str(output_project),
        name=config.name,
        plots=config.plots,
        save_json=config.save_json,
    )

    overall = _metric_values(metrics.box.mean_results())
    names = getattr(model, "names", {})
    per_class = _extract_class_metrics(metrics, names)
    speed = {
        str(key): float(value) for key, value in getattr(metrics, "speed", {}).items()
    }
    if dataset_report is not None:
        expected_ids = sorted(dataset_report.classes)
    else:
        expected_ids = (
            sorted(int(key) for key in names)
            if isinstance(names, dict)
            else list(range(len(names)))
        )
    failures = evaluate_acceptance(
        overall,
        per_class,
        speed,
        criteria or AcceptanceCriteria(),
        expected_class_ids=expected_ids,
    )

    raw_save_dir = getattr(metrics, "save_dir", None)
    if raw_save_dir is None:
        validator = getattr(model, "validator", None)
        raw_save_dir = getattr(validator, "save_dir", None)
    if raw_save_dir is None:
        raise RuntimeError("YOLO evaluation did not report an output directory")
    output_dir = Path(raw_save_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "evaluation_report.json"
    report = EvaluationReport(
        model=str(model_path),
        data=str(data_path),
        split=config.split,
        overall=overall,
        per_class=per_class,
        speed_ms_per_image=speed,
        passed=not failures,
        failures=failures,
        output_dir=str(output_dir),
        report_path=str(report_path),
    )
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate a trained YOLO model")
    parser.add_argument(
        "--config",
        default="AI/configs/evaluation.yaml.example",
        help="Evaluation YAML",
    )
    parser.add_argument("--model")
    parser.add_argument("--data")
    parser.add_argument("--split", choices=("val", "test"))
    parser.add_argument("--imgsz", type=int)
    parser.add_argument("--batch", type=int)
    parser.add_argument("--device")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--project")
    parser.add_argument("--name")
    parser.add_argument("--skip-dataset-validation", action="store_true")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    override_names = (
        "model",
        "data",
        "split",
        "imgsz",
        "batch",
        "device",
        "workers",
        "project",
        "name",
    )
    config, criteria = load_evaluation_settings(
        args.config,
        overrides={name: getattr(args, name) for name in override_names},
    )
    report = run_evaluation(
        config,
        criteria,
        validate_data=not args.skip_dataset_validation,
    )
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
