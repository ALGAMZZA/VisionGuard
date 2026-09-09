from pathlib import Path
from types import SimpleNamespace

import pytest

from AI.training.train import TrainingConfig, load_training_config, run_training


class FakeModel:
    def __init__(self, model_path: str, save_dir: Path) -> None:
        self.model_path = model_path
        self.save_dir = save_dir
        self.options: dict[str, object] = {}

    def train(self, **options: object) -> SimpleNamespace:
        self.options = options
        weights = self.save_dir / "weights"
        weights.mkdir(parents=True)
        (weights / "best.pt").touch()
        (weights / "last.pt").touch()
        return SimpleNamespace(save_dir=self.save_dir)


def test_load_training_config_applies_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "training.yaml"
    config_path.write_text(
        "data: dataset.yaml\nmodel: yolo11n.pt\nepochs: 10\n",
        encoding="utf-8",
    )

    config = load_training_config(config_path, overrides={"epochs": 2, "device": "cpu"})

    assert config.epochs == 2
    assert config.device == "cpu"
    assert config.model == "yolo11n.pt"


def test_training_config_rejects_invalid_fraction() -> None:
    with pytest.raises(ValueError, match="fraction"):
        TrainingConfig(data="dataset.yaml", fraction=0)


def test_run_training_returns_verified_checkpoints(tmp_path: Path) -> None:
    data = tmp_path / "dataset.yaml"
    data.touch()
    fake = FakeModel("yolo11n.pt", tmp_path / "run")
    config = TrainingConfig(data=str(data), epochs=1)

    result = run_training(
        config,
        validate_data=False,
        model_factory=lambda model_path: fake,
    )

    assert fake.options["epochs"] == 1
    assert fake.options["data"] == str(data.resolve())
    assert fake.options["project"] == str(Path("AI/models/checkpoints").resolve())
    assert Path(result.best_checkpoint).is_file()
    assert Path(result.last_checkpoint).is_file()
