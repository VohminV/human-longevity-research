"""Comparison of modelled values against the calibration reference.

Pure functions: given a modelled value (or per-seed distribution: mean/SD) and
a :class:`ReferencePoint`, produce absolute/relative error and a pass/fail-on-
range verdict. No simulation runs here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from longevity.calibration.reference import ALL_REFERENCE_POINTS, ReferencePoint


@dataclass(frozen=True)
class ModelValue:
    mean: float
    sd: float | None = None
    n_seeds: int = 1
    values: tuple[float, ...] = ()


@dataclass(frozen=True)
class ComparisonResult:
    key: str
    label: str
    observed_mean: float
    observed_sd: float | None
    observed_range: tuple[float, float] | None
    modelled_mean: float
    modelled_sd: float | None
    absolute_error: float
    relative_error: float | None
    within_observed: bool
    n_seeds: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compare_metric(key: str, modelled: ModelValue) -> ComparisonResult:
    """Compare `modelled` to the reference point identified by `key`.

    `relative_error` is None when the observed mean is 0. `within_observed`
    is True when the modelled mean falls inside the observed range if given,
    else inside observed_mean +/- observed_sd (when sd given).
    """
    reference = ALL_REFERENCE_POINTS[key]
    abs_err = modelled.mean - reference.observed_mean
    rel_err = abs_err / reference.observed_mean if reference.observed_mean else None

    inside = False
    if reference.observed_range is not None:
        lo, hi = reference.observed_range
        inside = lo <= modelled.mean <= hi
    elif reference.observed_sd is not None and reference.observed_sd > 0:
        inside = (
            reference.observed_mean - reference.observed_sd
            <= modelled.mean
            <= reference.observed_mean + reference.observed_sd
        )
    inside = bool(inside)

    return ComparisonResult(
        key=key,
        label=reference.label,
        observed_mean=reference.observed_mean,
        observed_sd=reference.observed_sd,
        observed_range=reference.observed_range,
        modelled_mean=round(modelled.mean, 4),
        modelled_sd=round(modelled.sd, 4) if modelled.sd is not None else None,
        absolute_error=round(abs_err, 4),
        relative_error=round(rel_err, 4) if rel_err is not None else None,
        within_observed=inside,
        n_seeds=modelled.n_seeds,
    )


def compare_reference_targets(modelled_by_key: dict[str, ModelValue]) -> list[dict[str, Any]]:
    """Compare a set of modelled metrics (keyed like the reference) and return
    a list of serializable comparison rows in reference order."""
    comparisons: list[ComparisonResult] = []
    for key in ALL_REFERENCE_POINTS:
        if key in modelled_by_key:
            comparisons.append(compare_metric(key, modelled_by_key[key]))
    return [c.to_dict() for c in comparisons]


def distribute(values: tuple[float, ...]) -> ModelValue:
    """Aggregate per-seed values into a ModelValue (mean / SD of the sample)."""
    n = len(values)
    if n == 0:
        raise ValueError("distribute() needs at least one value")
    mean = sum(values) / n
    sd = (sum((v - mean) ** 2 for v in values) / n) ** 0.5 if n > 1 else 0.0
    return ModelValue(mean=mean, sd=sd, n_seeds=n, values=tuple(round(v, 4) for v in values))