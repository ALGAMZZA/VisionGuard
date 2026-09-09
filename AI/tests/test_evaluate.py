from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar

import pytest

from AI.training.evaluate import (
    AcceptanceCriteria,
    ClassMetrics,
    EvaluationConfig,
    MetricValues,
    evaluate_acceptance,
    load_evaluation_settings,
    run_evaluation,
)


class FakeBoxMetrics:
    ap_class_index: ClassVar[list[int]] = [0, 1]

    @staticmethod
    def mean_results() -> list[float]:
        return [0.91, 0.88, 0.86, 0.67]

    @staticmethod
    def class_result(index: int) -> tuple[float, float, float, float]:
        return [(0.9, 0.85, 0.82, 0.61), (0.92, 0.91, 0.90, 0.73)][index]


class FakeModel:
    names: ClassVar[dict[int, str]] = {0: "person", 1: "forklift"}

    def __init__(self, save_dir: Path) -> None:
        self.save_dir = save_dir
        self.options: dict[str, object] = {}

    def val(self, **options: object) -> SimpleNamespace:
        self.options = options
        return SimpleNamespace(
            box=FakeBoxMetrics(),
            speed={"preprocess": 1.0, "inference": 12.5, "postprocess": 2.0},
            save_dir=self.save_dir,
        )


def test_load_evaluation_settings(tmp_path: Path) -> None:
    config_path = tmp_path / "evaluation.yaml"
    config_path.write_text(
        "model: best.pt\ndata: dataset.yaml\nacceptance:\n  min_map50: 0.8\n",
        encoding="utf-8",
    )

    config, criteria = load_evaluation_settings(config_path, overrides={"batch": 4})

    assert config.batch == 4
    assert criteria.min_map50 == 0.8


def test_acceptance_reports_aggregate_and_class_failures() -> None:
    failures = evaluate_acceptance(
        MetricValues(0.9, 0.6, 0.8, 0.55),
        [ClassMetrics(0, "person", MetricValues(0.9, 0.9, 0.5, 0.4))],
        {"inference": 30.0},
        AcceptanceCriteria(max_inference_ms=20.0),
        expected_class_ids=[0, 1],
    )

    assert any("recall" in failure for failure in failures)
    assert any("person" in failure for failure in failures)
    assert any("class 1" in failure for failure in failures)
    assert any("inference" in failure for failure in failures)


def test_run_evaluation_writes_report(tmp_path: Path) -> None:
    model_path = tmp_path / "best.pt"
    data_path = tmp_path / "dataset.yaml"
    model_path.touch()
    data_path.touch()
    fake = FakeModel(tmp_path / "evaluation")

    report = run_evaluation(
        EvaluationConfig(model=str(model_path), data=str(data_path)),
        AcceptanceCriteria(),
        validate_data=False,
        model_factory=lambda _: fake,
    )

    assert report.passed
    assert report.overall.map50 == pytest.approx(0.86)
    assert report.per_class[1].class_name == "forklift"
    assert Path(report.report_path).is_file()
    assert fake.options["project"] == str(Path("AI/reports/evaluation").resolve())
