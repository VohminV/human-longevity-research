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


def test_scaffold_only_placeholder() -> None:
    # Этап 1 не реализует модель; пакет существует для организации будущего кода.
    assert not hasattr(longevity, "Cell")