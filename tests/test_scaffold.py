"""Минимальный тестовый каркас (этап 1).

Проверяет скелет пакета. Инварианты модели (детерминизм seed, уникальность id,
parent-child, generation, lineage, деление, смерть, сенесценция, теломеры,
ДНК-повреждения, checkpoint/restore) появятся с моделью на этапе 2.
"""

import pytest

import longevity
from longevity.version import DATA_VERSION, MODEL_VERSION


def test_package_importable() -> None:
    assert hasattr(longevity, "__version__")


def test_versions_are_semver() -> None:
    for v in (longevity.__version__, MODEL_VERSION, DATA_VERSION):
        major, minor, patch = v.split(".")
        assert major.isdigit()
        assert minor.isdigit()
        assert patch.isdigit()


def test_version_info_contains_versions() -> None:
    info = longevity.version.version_info()
    assert MODEL_VERSION in info
    assert DATA_VERSION in info


def test_core_capabilities_importable():
    from longevity.experiment.config import ExperimentConfig
    from longevity.experiment.runner import run_experiment
    from longevity.sim.engine import PopulationEngine
    from longevity.sim.rng import Rng

    assert ExperimentConfig is not None
    assert run_experiment is not None
    assert PopulationEngine is not None
    assert Rng is not None