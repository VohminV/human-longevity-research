"""EXPERIMENT ENGINE LAYER: tissue replacement parameter sweep (Stage 3B).

Drives :class:`TissueModel` runs through the existing Stage 3A
:func:`longevity.experiment.tissue_runner.run_tissue_experiment` (no dynamics
duplicated here), classifies every seed with the pure analysis layer
(:mod:`longevity.analysis.tissue_sweep`), and writes long/summary CSV plus
summary/boundary JSON artifacts.

CLI::

    PYTHONPATH=src python -m longevity.experiment.tissue_sweep \\
        --config experiments/configs/tissue_sweep_v0.json \\
        --out-prefix experiments/output/tissue_sweep_v0
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
import time

from dataclasses import dataclass, field
from typing import Any

from longevity.analysis.tissue_sweep import (
    FIRST_TIME_FIELDS,
    FAILURE_CAUSE_ORDER,
    PRIMARY_FAILURE_CAUSES,
    aggregate_point,
    build_regime_coverage,
    classify_regime,
    compare_control_profiles,
    compute_boundary,
    compute_boundary_closure,
    compute_seed_metrics,
    pareto_frontier,
    summarize_failure_causes,
    validate_thresholds,
)
from longevity.experiment.tissue_runner import TissueExperimentConfig, run_tissue_experiment
from longevity.model.policy import ReplacementPolicy
from longevity.model.tissue import (
    TISSUE_MODEL_VERSION,
    TissueState,
    assert_tissue_invariants,
    validate_tissue_parameters,
)
from longevity.version import DATA_VERSION

TISSUE_SWEEP_FORMAT_VERSION = "1.0"
# Minimum seeds per grid point: below this the per-point spread is not even a
# descriptive uncertainty estimate (see docs/TISSUE_MODEL.md, Stage 3B).
MIN_SWEEP_SEEDS = 3

BASELINE_POLICY_DICT: dict[str, Any] = {
    "name": "sweep-baseline-disabled",
    "enabled": False,
    "target": "none",
    "source": "none",
    "frequency": 5,
    "max_replacement_fraction": 0.0,
    "preserve_architecture": 1.0,
    "immune_compatibility": 1.0,
    "cancer_control": 1.0,
}

# Long-CSV column order: coordinates first, then per-seed metrics, then regime.
PER_SEED_COLUMNS = (
    "seed",
    "max_replacement_fraction",
    "frequency",
    "policy_enabled",
    "survival_time",
    "healthspan_tissue",
    "time_to_first_viability_failure",
    "final_functional_cells",
    "final_senescent_cells",
    "final_damaged_cells",
    "final_dead_cells",
    "final_stem_cells",
    "final_cancer_risk",
    "final_senescent_fraction",
    "min_stem_cells",
    "min_stem_fraction",
    "area_under_senescent_curve",
    "area_under_damage_curve",
    "area_under_functional_curve",
    "max_cancer_risk",
    "final_fibrosis_index",
    "final_ecm_quality",
    "final_vascular_quality",
    "final_immune_pressure",
    "rejuvenation_delta",
    "rejuvenation_delta_vs_baseline",
    "senescence_reduction_vs_baseline",
    "stem_depletion_delta_vs_baseline",
    "replacement_events",
    "total_replaced_cells",
    "regime_label",
    "regime_reasons",
)

# Stage 3C extended long-CSV columns (v1 multi-profile outputs only; legacy
# Stage 3B outputs keep exactly PER_SEED_COLUMNS so old schemas never shift).
FIRST_TIME_COLUMNS = (
    "first_stem_depletion_time",
    "first_functional_collapse_time",
    "first_senescence_blowout_time",
    "first_cancer_threshold_time",
    "first_fibrosis_threshold_time",
    "first_ecm_collapse_time",
    "first_vascular_collapse_time",
    "first_immune_overload_time",
)
PER_SEED_COLUMNS_V1 = (
    ("seed", "control_profile", "max_replacement_fraction", "frequency", "policy_enabled")
    + tuple(c for c in PER_SEED_COLUMNS if c not in ("seed", "max_replacement_fraction", "frequency", "policy_enabled"))
    + ("primary_failure_cause", "failure_cause_sequence")
    + FIRST_TIME_COLUMNS
)

# Stage 3C control profiles: model-operational settings for replacement
# maintenance, NOT biological constants. Strong matches the Stage 3A/3B
# defaults (0.9 controls); weak follows the aggressive Stage 3A config (0.4).
CONTROL_PRESET_STRONG = "strong_controls"
CONTROL_PRESET_WEAK = "weak_controls"
CONTROL_PROFILE_PRESETS: dict[str, dict[str, float]] = {
    CONTROL_PRESET_STRONG: {
        "preserve_architecture": 0.9,
        "immune_compatibility": 0.9,
        "cancer_control": 0.9,
    },
    CONTROL_PRESET_WEAK: {
        "preserve_architecture": 0.4,
        "immune_compatibility": 0.4,
        "cancer_control": 0.4,
    },
}
_CONTROL_OVERRIDE_KEYS = ("preserve_architecture", "immune_compatibility", "cancer_control")


def _require_control_profiles(value: Any) -> dict[str, dict[str, float]] | None:
    """Normalize the optional ``control_profiles`` sweep block (Stage 3C).

    Accepts None/absent (legacy single-profile mode), a list of preset names,
    or a dict name -> override dict. Returns None for legacy mode, otherwise
    a normalized {name: {control_key: float}} mapping. Rejects unknown preset
    names, unknown override keys, out-of-range values, and explicitly empty
    collections.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        if len(value) == 0:
            raise ValueError("control_profiles must be non-empty when present")
        normalized: dict[str, dict[str, float]] = {}
        for name in value:
            if not isinstance(name, str) or not name:
                raise ValueError(f"control profile name must be a non-empty string, got {name!r}")
            if name not in CONTROL_PROFILE_PRESETS:
                raise ValueError(f"unknown control profile {name!r}; known presets: {sorted(CONTROL_PROFILE_PRESETS)}")
            if name in normalized:
                raise ValueError(f"duplicate control profile {name!r}")
            normalized[name] = dict(CONTROL_PROFILE_PRESETS[name])
        return normalized
    if isinstance(value, dict):
        if len(value) == 0:
            raise ValueError("control_profiles must be non-empty when present")
        normalized = {}
        for name, overrides in value.items():
            if not isinstance(name, str) or not name:
                raise ValueError(f"control profile name must be a non-empty string, got {name!r}")
            if overrides is None:
                if name not in CONTROL_PROFILE_PRESETS:
                    raise ValueError(f"unknown control profile {name!r} with null overrides")
                normalized[name] = dict(CONTROL_PROFILE_PRESETS[name])
                continue
            if not isinstance(overrides, dict):
                raise ValueError(f"control_profiles[{name!r}] must be a dict of control overrides")
            unknown = set(overrides) - set(_CONTROL_OVERRIDE_KEYS)
            if unknown:
                raise ValueError(f"control_profiles[{name!r}] unknown keys: {sorted(unknown)}")
            cleaned: dict[str, float] = {}
            for key in _CONTROL_OVERRIDE_KEYS:
                if key in overrides:
                    raw = overrides[key]
                    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                        raise ValueError(f"control_profiles[{name!r}].{key} must be a number, got {raw!r}")
                    numeric = float(raw)
                    if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
                        raise ValueError(f"control_profiles[{name!r}].{key} must be in [0, 1], got {raw!r}")
                    cleaned[key] = numeric
            if name in normalized:
                raise ValueError(f"duplicate control profile {name!r}")
            # Missing keys fall back to the policy template at run time; store
            # only explicit overrides plus preset fill for known names.
            if name in CONTROL_PROFILE_PRESETS:
                filled = dict(CONTROL_PROFILE_PRESETS[name])
                filled.update(cleaned)
                normalized[name] = filled
            else:
                normalized[name] = cleaned
        return normalized
    raise ValueError("control_profiles must be a list of preset names or a dict name -> overrides")


def _require_seed_list(seeds: Any) -> tuple[int, ...]:
    if not isinstance(seeds, (list, tuple)) or len(seeds) == 0:
        raise ValueError("sweep seeds must be a non-empty list")
    cleaned: list[int] = []
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"sweep seed must be an int, got {seed!r}")
        cleaned.append(seed)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"sweep seeds must be unique, got {cleaned!r}")
    if len(cleaned) < MIN_SWEEP_SEEDS:
        raise ValueError(
            f"sweep needs at least {MIN_SWEEP_SEEDS} seeds per point, got {len(cleaned)}"
        )
    return tuple(cleaned)


def _require_fraction_grid(values: Any, name: str) -> tuple[float, ...]:
    if not isinstance(values, (list, tuple)) or len(values) == 0:
        raise ValueError(f"sweep grid {name} must be a non-empty list")
    cleaned: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"sweep grid {name} must hold numbers, got {value!r}")
        result = float(value)
        if not math.isfinite(result):
            raise ValueError(f"sweep grid {name} must be finite, got {value!r}")
        if not 0.0 <= result <= 1.0:
            raise ValueError(f"sweep grid {name} must be in [0, 1], got {value!r}")
        cleaned.append(result)
    return tuple(cleaned)


def _require_frequency_grid(values: Any) -> tuple[int, ...]:
    """Step-period grid: positive ints (Stage 3A policy semantics).

    ``0`` is rejected: a zero period is not schedulable (``step % 0``). The
    "replacement off" arm is ``max_replacement_fraction = 0.0`` (empty plans)
    plus the separate disabled-policy baseline, not a zero frequency.
    """
    if not isinstance(values, (list, tuple)) or len(values) == 0:
        raise ValueError("sweep grid frequency must be a non-empty list")
    cleaned: list[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"sweep grid frequency must hold ints >= 1, got {value!r}")
        if value < 1:
            raise ValueError(f"sweep grid frequency must hold ints >= 1, got {value!r}")
        cleaned.append(value)
    return tuple(cleaned)


@dataclass(frozen=True)
class TissueSweepConfig:
    """Complete, self-describing tissue-sweep configuration (Stage 3B/3C)."""

    experiment_id: str
    seeds: tuple[int, ...] = ()
    grid_fractions: tuple[float, ...] = ()
    grid_frequencies: tuple[int, ...] = ()
    steps: int = 200
    dt: float = 1.0
    model_version: str = TISSUE_MODEL_VERSION
    data_version: str = DATA_VERSION
    initial_state: dict[str, Any] = field(default_factory=dict)
    tissue_parameters: dict[str, Any] = field(default_factory=dict)
    policy_template: dict[str, Any] = field(default_factory=dict)
    thresholds: dict[str, float] = field(default_factory=dict)
    metrics: list[str] = field(default_factory=list)
    include_baseline: bool = True
    output_prefix: str = ""
    notes: str = ""
    # Stage 3C: optional control profiles. None = legacy Stage 3B mode
    # (policy_template used as-is). Otherwise {name: overrides} with keys in
    # {"preserve_architecture", "immune_compatibility", "cancer_control"};
    # missing keys fall back to the template value at run time.
    control_profiles: Any = None

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seed_list(list(self.seeds))
        _require_fraction_grid(list(self.grid_fractions), "max_replacement_fraction")
        _require_frequency_grid(list(self.grid_frequencies))
        if isinstance(self.steps, bool) or not isinstance(self.steps, int) or self.steps < 1:
            raise ValueError("steps must be a positive int")
        if isinstance(self.dt, bool) or not isinstance(self.dt, (int, float)) or not math.isfinite(float(self.dt)) or float(self.dt) <= 0.0:
            raise ValueError("dt must be a positive finite number")
        if not self.model_version:
            raise ValueError("model_version must be non-empty")
        if not self.data_version:
            raise ValueError("data_version must be non-empty")
        if not isinstance(self.initial_state, dict):
            raise ValueError("initial_state must be a dict")
        if not isinstance(self.tissue_parameters, dict):
            raise ValueError("tissue_parameters must be a dict")
        if not isinstance(self.policy_template, dict):
            raise ValueError("policy_template must be a dict")
        # Effective tissue params: explicit dt wins, then validation fills the rest.
        effective = dict(self.tissue_parameters)
        effective["dt"] = float(self.dt)
        validate_tissue_parameters(effective)
        assert_tissue_invariants(TissueState.from_dict(self.initial_state))
        template = ReplacementPolicy.from_dict(dict(self.policy_template))
        if not template.enabled:
            raise ValueError("policy_template must be enabled (the baseline arm is separate)")
        validate_thresholds(dict(self.thresholds))
        if not isinstance(self.metrics, list) or not self.metrics or not all(isinstance(m, str) for m in self.metrics):
            raise ValueError("metrics must be a non-empty list of metric names")
        if not isinstance(self.include_baseline, bool):
            raise ValueError("include_baseline must be a bool")
        normalized = _require_control_profiles(self.control_profiles)
        object.__setattr__(self, "control_profiles", normalized)

    def effective_tissue_parameters(self) -> dict[str, Any]:
        effective = dict(self.tissue_parameters)
        effective["dt"] = float(self.dt)
        return validate_tissue_parameters(effective)

    def duration_time(self) -> float:
        return float(self.steps) * float(self.dt)

    def to_config_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "experiment_id": self.experiment_id,
            "model_version": self.model_version,
            "data_version": self.data_version,
            "steps": self.steps,
            "dt": float(self.dt),
            "seeds": list(self.seeds),
            "grid": {
                "max_replacement_fraction": list(self.grid_fractions),
                "frequency": list(self.grid_frequencies),
            },
            "initial_state": TissueState.from_dict(self.initial_state).to_dict(),
            "tissue_parameters": self.effective_tissue_parameters(),
            "policy_template": ReplacementPolicy.from_dict(dict(self.policy_template)).to_dict(),
            "thresholds": validate_thresholds(dict(self.thresholds)),
            "metrics": list(self.metrics),
            "include_baseline": self.include_baseline,
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }
        # Stage 3C: only present when profiles are configured, so legacy v0
        # configs keep a byte-stable canonical form (and config_hash).
        if self.control_profiles is not None:
            payload["control_profiles"] = {
                name: dict(overrides) for name, overrides in self.control_profiles.items()
            }
        return payload

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "TissueSweepConfig":
        grid = data.get("grid", {})
        return cls(
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            grid_fractions=tuple(grid.get("max_replacement_fraction", ())),
            grid_frequencies=tuple(grid.get("frequency", ())),
            steps=data.get("steps", 200),
            dt=float(data.get("dt", 1.0)),
            model_version=data.get("model_version", TISSUE_MODEL_VERSION),
            data_version=data.get("data_version", DATA_VERSION),
            initial_state=data.get("initial_state", {}),
            tissue_parameters=data.get("tissue_parameters", {}),
            policy_template=data.get("policy_template", {}),
            thresholds=data.get("thresholds", {}),
            metrics=data.get("metrics", []),
            include_baseline=bool(data.get("include_baseline", True)),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
            control_profiles=data.get("control_profiles", None),
        )


def config_hash(config: TissueSweepConfig) -> str:
    """Canonical sha256 of the validated config (reproducibility anchor)."""
    canonical = json.dumps(config.to_config_dict(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _policy_for_point(
    template: dict[str, Any],
    fraction: float,
    frequency: int,
    profile_name: str | None = None,
    profile_overrides: dict[str, float] | None = None,
) -> dict[str, Any]:
    point = dict(template)
    point["max_replacement_fraction"] = float(fraction)
    point["frequency"] = int(frequency)
    if profile_overrides:
        for key, value in profile_overrides.items():
            point[key] = float(value)
    base = str(template.get("name", "sweep"))
    if profile_name:
        point["name"] = f"{base}-{profile_name}-f{float(fraction):g}-q{int(frequency)}"
    else:
        point["name"] = f"{base}-f{float(fraction):g}-q{int(frequency)}"
    return point


def run_tissue_sweep(config: TissueSweepConfig, control_profile: str | None = None) -> dict[str, Any]:
    """Run the full fraction x frequency grid over all seeds (Stage 3B/3C).

    Each (point, seed) reuses :func:`run_tissue_experiment` (Stage 3A runner);
    the same seed across arms isolates the policy (EXPERIMENTS.md §6). Baseline
    (disabled policy) runs per seed provide the same-seed reference for
    ``*_vs_baseline`` deltas. Returns a JSON-serializable structured result.

    Stage 3C: when the config carries ``control_profiles``, the same grid is
    run once per profile (policy template overridden per profile) and the
    result carries per-profile points plus boundary-closure, regime-coverage,
    failure-cause, and control-comparison summaries. ``control_profile``
    optionally restricts the run to a single configured profile.
    Legacy configs (no ``control_profiles``) keep the exact Stage 3B result
    shape: points carry no ``control_profile`` key.
    """
    wall_start = time.perf_counter()
    thresholds = validate_thresholds(dict(config.thresholds))
    duration_time = config.duration_time()
    tissue_params = config.effective_tissue_parameters()

    profiles: dict[str, dict[str, float]] | None = config.control_profiles
    if control_profile is not None:
        if profiles is None:
            if control_profile != "default":
                raise ValueError(f"unknown control profile {control_profile!r}: config has no control_profiles")
            profiles = None
        else:
            if control_profile not in profiles:
                raise ValueError(f"unknown control profile {control_profile!r}; configured: {sorted(profiles)}")
            profiles = {control_profile: profiles[control_profile]}
    is_v1 = profiles is not None
    profile_names: list[str] | None = sorted(profiles) if profiles is not None else None

    def _run_arm(policy_dict: dict[str, Any], seed: int, tag: str) -> dict[str, Any]:
        experiment = TissueExperimentConfig(
            experiment_id=f"{config.experiment_id}__{tag}__s{seed}",
            seed=seed,
            steps=config.steps,
            model_version=config.model_version,
            data_version=config.data_version,
            initial_state=dict(config.initial_state),
            tissue_parameters=dict(tissue_params),
            policy=dict(policy_dict),
        )
        result = run_tissue_experiment(experiment, out_path=None)
        row = compute_seed_metrics(
            result["trajectory"],
            float(tissue_params["dt"]),
            result["metrics"]["final"]["replacement_events"],
            result["metrics"]["final"]["total_replaced_cells"],
            thresholds,
            duration_time,
        )
        return row

    baselines: dict[str, dict[str, Any]] = {}
    if config.include_baseline:
        for seed in config.seeds:
            row = _run_arm(BASELINE_POLICY_DICT, seed, "baseline")
            verdict = classify_regime(row, thresholds, duration_time, policy_off=True)
            row["regime_label"] = verdict["label"]
            row["regime_reasons"] = list(verdict["reasons"])
            row["seed"] = seed
            row["max_replacement_fraction"] = 0.0
            row["frequency"] = 0
            row["policy_enabled"] = False
            row["rejuvenation_delta_vs_baseline"] = 0.0
            row["senescence_reduction_vs_baseline"] = 0.0
            row["stem_depletion_delta_vs_baseline"] = 0.0
            if is_v1:
                row["control_profile"] = "baseline"
            baselines[str(seed)] = row

    def _run_grid_point(policy_dict: dict[str, Any], fraction: float, frequency: int, tag_suffix: str, profile_name: str | None) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        policy_off = (not ReplacementPolicy.from_dict(policy_dict).enabled) or fraction <= 0.0
        for seed in config.seeds:
            row = _run_arm(policy_dict, seed, tag_suffix)
            baseline = baselines.get(str(seed))
            row["rejuvenation_delta_vs_baseline"] = (
                row["rejuvenation_delta"] - baseline["rejuvenation_delta"] if baseline else 0.0
            )
            row["senescence_reduction_vs_baseline"] = (
                (baseline["final_senescent_cells"] - row["final_senescent_cells"]) if baseline else 0.0
            )
            row["stem_depletion_delta_vs_baseline"] = (
                (baseline["final_stem_cells"] - row["final_stem_cells"]) if baseline else 0.0
            )
            verdict = classify_regime(row, thresholds, duration_time, policy_off=policy_off)
            row["regime_label"] = verdict["label"]
            row["regime_reasons"] = list(verdict["reasons"])
            row["seed"] = seed
            row["max_replacement_fraction"] = float(fraction)
            row["frequency"] = int(frequency)
            row["policy_enabled"] = bool(ReplacementPolicy.from_dict(policy_dict).enabled)
            if profile_name is not None:
                row["control_profile"] = profile_name
            rows.append(row)
        point: dict[str, Any] = {
            "max_replacement_fraction": float(fraction),
            "frequency": int(frequency),
            "aggregate": aggregate_point(rows),
            "seeds": {str(seed): rows[i] for i, seed in enumerate(config.seeds)},
        }
        if profile_name is not None:
            point["control_profile"] = profile_name
        return point

    points: list[dict[str, Any]] = []
    if not is_v1:
        for frequency in sorted(config.grid_frequencies):
            for fraction in sorted(config.grid_fractions):
                policy_dict = _policy_for_point(dict(config.policy_template), fraction, frequency)
                points.append(_run_grid_point(policy_dict, fraction, frequency, f"f{fraction:g}-q{frequency}", None))
    else:
        assert profile_names is not None and profiles is not None
        for profile_name in profile_names:
            overrides = dict(profiles[profile_name])
            for frequency in sorted(config.grid_frequencies):
                for fraction in sorted(config.grid_fractions):
                    policy_dict = _policy_for_point(
                        dict(config.policy_template), fraction, frequency, profile_name, overrides
                    )
                    tag = f"{profile_name}-f{fraction:g}-q{frequency}"
                    points.append(_run_grid_point(policy_dict, fraction, frequency, tag, profile_name))

    boundary_inputs = [
        {
            "frequency": p["frequency"],
            "max_replacement_fraction": p["max_replacement_fraction"],
            "sustainable_rate": p["aggregate"]["sustainable_rate"],
            "mean_time_to_first_viability_failure": p["aggregate"]["mean_time_to_first_viability_failure"],
        }
        for p in points
    ]
    boundary = compute_boundary(
        boundary_inputs,
        duration_time,
        thresholds["boundary_sustainable_rate_min"],
        thresholds["boundary_ttf_fraction_min"],
    )
    pareto = pareto_frontier(
        [
            {
                "frequency": p["frequency"],
                "max_replacement_fraction": p["max_replacement_fraction"],
                "benefit": p["aggregate"]["metrics"]["senescence_reduction_vs_baseline"]["mean"],
                "costs": [
                    p["aggregate"]["metrics"]["max_cancer_risk"]["mean"],
                    p["aggregate"]["metrics"]["final_fibrosis_index"]["mean"],
                    p["aggregate"]["metrics"]["stem_depletion_delta_vs_baseline"]["mean"],
                ],
            }
            for p in points
        ]
    )

    # Stage 3C summaries (pure analysis over recorded rows; no re-simulation).
    closure_inputs = [
        {
            "frequency": p["frequency"],
            "max_replacement_fraction": p["max_replacement_fraction"],
            "control_profile": p.get("control_profile", "default"),
            "sustainable_rate": p["aggregate"]["sustainable_rate"],
            "mean_time_to_first_viability_failure": p["aggregate"]["mean_time_to_first_viability_failure"],
            "regime_counts": dict(p["aggregate"]["regime_counts"]),
        }
        for p in points
    ]
    boundary_closure = compute_boundary_closure(
        closure_inputs,
        duration_time,
        thresholds["boundary_sustainable_rate_min"],
        thresholds["boundary_ttf_fraction_min"],
    )
    regime_coverage = build_regime_coverage(points)
    all_seed_rows: list[dict[str, Any]] = []
    for point in points:
        for row in point["seeds"].values():
            all_seed_rows.append(row)
    failure_summary = summarize_failure_causes(all_seed_rows)
    control_comparison: dict[str, Any] | None = None
    pareto_by_profile: dict[str, Any] | None = None
    if is_v1:
        control_comparison = compare_control_profiles(points, all_seed_rows)
        pareto_by_profile = {}
        assert profile_names is not None
        for profile_name in profile_names:
            owned = [p for p in points if p.get("control_profile") == profile_name]
            pareto_by_profile[profile_name] = pareto_frontier(
                [
                    {
                        "frequency": p["frequency"],
                        "max_replacement_fraction": p["max_replacement_fraction"],
                        "benefit": p["aggregate"]["metrics"]["senescence_reduction_vs_baseline"]["mean"],
                        "costs": [
                            p["aggregate"]["metrics"]["max_cancer_risk"]["mean"],
                            p["aggregate"]["metrics"]["final_fibrosis_index"]["mean"],
                            p["aggregate"]["metrics"]["stem_depletion_delta_vs_baseline"]["mean"],
                        ],
                    }
                    for p in owned
                ]
            )

    wall_seconds = round(time.perf_counter() - wall_start, 4)
    result: dict[str, Any] = {
        "experiment_id": config.experiment_id,
        "format": TISSUE_SWEEP_FORMAT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": config_hash(config),
        "model_version": config.model_version,
        "data_version": config.data_version,
        "duration_steps": config.steps,
        "duration_time": duration_time,
        "seeds": list(config.seeds),
        "grid": {
            "max_replacement_fraction": sorted(float(f) for f in config.grid_fractions),
            "frequency": sorted(int(q) for q in config.grid_frequencies),
        },
        "thresholds": thresholds,
        "baselines": baselines,
        "points": points,
        "boundary": boundary,
        "pareto": pareto,
        "boundary_closure": boundary_closure,
        "regime_coverage": regime_coverage,
        "failure_causes": failure_summary,
        "runtime": {
            "engine": "tissue-sweep/v1" if is_v1 else "tissue-sweep/v0",
            "python": platform.python_version(),
            "platform": platform.platform(),
            "wall_seconds": wall_seconds,
        },
    }
    if is_v1:
        assert profile_names is not None and profiles is not None
        result["control_profiles"] = list(profile_names)
        result["control_profile_params"] = {name: dict(profiles[name]) for name in profile_names}
        result["control_comparison"] = control_comparison
        result["pareto_by_profile"] = pareto_by_profile
    return result


def _round6(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [_round6(v) for v in value]
    if isinstance(value, dict):
        return {k: _round6(v) for k, v in value.items()}
    return value


def _assert_finite_jsonable(node: Any, path: str = "$") -> None:
    if isinstance(node, float):
        if not math.isfinite(node):
            raise ValueError(f"non-finite float at {path}: {node!r}")
    elif isinstance(node, dict):
        for key, value in node.items():
            _assert_finite_jsonable(value, f"{path}.{key}")
    elif isinstance(node, (list, tuple)):
        for index, value in enumerate(node):
            _assert_finite_jsonable(value, f"{path}[{index}]")


def _is_v1_result(result: dict[str, Any]) -> bool:
    return "control_profiles" in result and result["control_profiles"] not in (None, [], ["default"])


def _csv_cell(row: dict[str, Any], key: str) -> Any:
    if key in ("regime_reasons", "failure_cause_sequence"):
        values = row.get(key, [])
        return ";".join(values) if isinstance(values, list) else values
    return _round6(row.get(key))


def write_tissue_sweep_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    """Write long CSV, summary CSV, summary JSON, boundary JSON artifacts.

    Stage 3B legacy configs produce exactly these four files with the exact
    Stage 3B schemas. Stage 3C multi-profile results additionally write
    boundary-closure, regime-coverage (JSON+CSV), failure-causes (JSON+CSV),
    and control-comparison JSON artifacts.

    Floats are rounded to 6 decimals for readability; JSON is guarded with
    ``allow_nan=False`` after an explicit finiteness walk so NaN/inf can
    never silently land in an artifact.
    """
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    long_path = f"{out_prefix}_long.csv"
    summary_path = f"{out_prefix}_summary.csv"
    summary_json_path = f"{out_prefix}_summary.json"
    boundary_json_path = f"{out_prefix}_boundary.json"

    v1 = _is_v1_result(result)
    long_columns = list(PER_SEED_COLUMNS_V1) if v1 else list(PER_SEED_COLUMNS)

    long_rows: list[dict[str, Any]] = []
    for seed in result["seeds"]:
        baseline = result["baselines"].get(str(seed))
        if baseline is not None:
            long_rows.append({key: _csv_cell(baseline, key) for key in long_columns})
    for point in result["points"]:
        for seed in result["seeds"]:
            row = dict(point["seeds"][str(seed)])
            long_rows.append({key: _csv_cell(row, key) for key in long_columns})

    with open(long_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=long_columns)
        writer.writeheader()
        writer.writerows(long_rows)

    summary_fieldnames = ["frequency", "max_replacement_fraction", "n_seeds"]
    if v1:
        summary_fieldnames = ["control_profile"] + summary_fieldnames
    metric_means = [f"mean_{name}" for name in _SUMMARY_METRIC_NAMES]
    metric_medians = [f"median_{name}" for name in _SUMMARY_METRIC_NAMES]
    summary_fieldnames += metric_means + metric_medians
    summary_fieldnames += [
        "sustainable_rate",
        "failure_rate",
        "mean_time_to_first_viability_failure",
        "median_time_to_first_viability_failure",
        "sustainable_count",
        "risky_count",
        "depleting_count",
        "collapsing_count",
        "unstable_count",
        "baseline_like_count",
    ]
    summary_rows: list[dict[str, Any]] = []
    for point in result["points"]:
        aggregate = point["aggregate"]
        row: dict[str, Any] = {
            "frequency": point["frequency"],
            "max_replacement_fraction": _round6(point["max_replacement_fraction"]),
            "n_seeds": aggregate["n_seeds"],
        }
        if v1:
            row["control_profile"] = point.get("control_profile", "default")
            # Keep control_profile first for readability.
            row = {"control_profile": row.pop("control_profile"), **row}
        for name in _SUMMARY_METRIC_NAMES:
            row[f"mean_{name}"] = _round6(aggregate["metrics"][name]["mean"])
            row[f"median_{name}"] = _round6(aggregate["metrics"][name]["median"])
        row["sustainable_rate"] = _round6(aggregate["sustainable_rate"])
        row["failure_rate"] = _round6(aggregate["failure_rate"])
        row["mean_time_to_first_viability_failure"] = _round6(aggregate["mean_time_to_first_viability_failure"])
        row["median_time_to_first_viability_failure"] = _round6(aggregate["median_time_to_first_viability_failure"])
        for key, value in aggregate["regime_counts"].items():
            row[key] = value
        summary_rows.append(row)
    # Deterministic order: profile, then frequency, then fraction.
    if v1:
        summary_rows.sort(key=lambda r: (str(r.get("control_profile")), int(r["frequency"]), float(r["max_replacement_fraction"])))

    with open(summary_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=summary_fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    summary_payload: dict[str, Any] = {
        "experiment_id": result["experiment_id"],
        "format": result["format"],
        "config_hash": result["config_hash"],
        "model_version": result["model_version"],
        "data_version": result["data_version"],
        "duration_steps": result["duration_steps"],
        "duration_time": result["duration_time"],
        "seeds": result["seeds"],
        "grid": result["grid"],
        "thresholds": {k: _round6(v) for k, v in result["thresholds"].items()},
        "baselines": {seed: _rounded_row(row) for seed, row in result["baselines"].items()},
        "points": [
            {
                **({"control_profile": p.get("control_profile")} if v1 else {}),
                "max_replacement_fraction": _round6(p["max_replacement_fraction"]),
                "frequency": p["frequency"],
                "aggregate": _rounded_aggregate(p["aggregate"]),
                "seeds": {seed: _rounded_row(row) for seed, row in p["seeds"].items()},
            }
            for p in result["points"]
        ],
        "boundary": {k: (_round6(v) if v is not None else None) for k, v in result["boundary"].items()},
        "pareto": result["pareto"],
        "boundary_closure": _round6(result.get("boundary_closure", {})),
        "regime_coverage": _round6(result.get("regime_coverage", {})),
        "failure_causes": _round6(result.get("failure_causes", {})),
        "runtime": result["runtime"],
    }
    if v1:
        summary_payload["control_profiles"] = list(result["control_profiles"])
        summary_payload["control_profile_params"] = {k: dict(v) for k, v in result["control_profile_params"].items()}
        summary_payload["control_comparison"] = _round6(result.get("control_comparison", {}))
        summary_payload["pareto_by_profile"] = result.get("pareto_by_profile", {})
    _assert_finite_jsonable(summary_payload)
    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(summary_payload, fh, ensure_ascii=False, indent=2, allow_nan=False)

    boundary_payload = {
        "experiment_id": result["experiment_id"],
        "config_hash": result["config_hash"],
        "rule": {
            "sustainable_rate_min": result["thresholds"]["boundary_sustainable_rate_min"],
            "mean_ttf_min": result["thresholds"]["boundary_ttf_fraction_min"] * result["duration_time"],
        },
        "boundary_max_sustainable_fraction_by_frequency": {
            k: (_round6(v) if v is not None else None) for k, v in result["boundary"].items()
        },
    }
    with open(boundary_json_path, "w", encoding="utf-8") as fh:
        json.dump(boundary_payload, fh, ensure_ascii=False, indent=2, allow_nan=False)

    paths = {
        "long_csv": long_path,
        "summary_csv": summary_path,
        "summary_json": summary_json_path,
        "boundary_json": boundary_json_path,
    }
    if not v1:
        return paths

    # -- Stage 3C extra artifacts (v1 only) ---------------------------------
    closure = result.get("boundary_closure", {})
    closure_payload = {
        "metadata": {
            "experiment_id": result["experiment_id"],
            "model_version": result["model_version"],
            "data_version": result["data_version"],
            "config_hash": result["config_hash"],
            "seeds": result["seeds"],
            "duration": result["duration_time"],
            "duration_steps": result["duration_steps"],
            "control_profiles": list(result["control_profiles"]),
        },
        "boundary_by_frequency": _round6(closure.get("boundary_by_frequency", {})),
        "open_boundaries": closure.get("open_boundaries", []),
        "closed_boundaries": closure.get("closed_boundaries", []),
    }
    closure_path = f"{out_prefix}_boundary_closure.json"
    _assert_finite_jsonable(closure_payload)
    with open(closure_path, "w", encoding="utf-8") as fh:
        json.dump(closure_payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    paths["boundary_closure_json"] = closure_path

    coverage = result.get("regime_coverage", {})
    coverage_path = f"{out_prefix}_regime_coverage.json"
    _assert_finite_jsonable(coverage)
    with open(coverage_path, "w", encoding="utf-8") as fh:
        json.dump(_round6(coverage), fh, ensure_ascii=False, indent=2, allow_nan=False)
    paths["regime_coverage_json"] = coverage_path
    coverage_csv_path = f"{out_prefix}_regime_coverage.csv"
    with open(coverage_csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["regime_label", "run_count", "n_points", "visited", "example_control_profile", "example_frequency", "example_fraction"],
        )
        writer.writeheader()
        for label, entry in coverage.get("labels", {}).items():
            example = (entry.get("examples") or [{}])[0]
            writer.writerow(
                {
                    "regime_label": label,
                    "run_count": entry.get("run_count", 0),
                    "n_points": entry.get("n_points", 0),
                    "visited": str(bool(entry.get("run_count", 0))).lower(),
                    "example_control_profile": example.get("control_profile", ""),
                    "example_frequency": example.get("frequency", ""),
                    "example_fraction": example.get("max_replacement_fraction", ""),
                }
            )
    paths["regime_coverage_csv"] = coverage_csv_path

    failure = result.get("failure_causes", {})
    failure_path = f"{out_prefix}_failure_causes.json"
    _assert_finite_jsonable(failure)
    with open(failure_path, "w", encoding="utf-8") as fh:
        json.dump(_round6(failure), fh, ensure_ascii=False, indent=2, allow_nan=False)
    paths["failure_causes_json"] = failure_path
    failure_csv_path = f"{out_prefix}_failure_causes.csv"
    with open(failure_csv_path, "w", encoding="utf-8", newline="") as fh:
        fieldnames = ["seed", "control_profile", "frequency", "max_replacement_fraction", "primary_failure_cause", "failure_cause_sequence"] + list(FIRST_TIME_COLUMNS)
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for point in result["points"]:
            for seed in result["seeds"]:
                row = point["seeds"][str(seed)]
                writer.writerow(
                    {
                        "seed": row.get("seed"),
                        "control_profile": row.get("control_profile", ""),
                        "frequency": row.get("frequency"),
                        "max_replacement_fraction": _round6(row.get("max_replacement_fraction")),
                        "primary_failure_cause": row.get("primary_failure_cause", ""),
                        "failure_cause_sequence": ";".join(row.get("failure_cause_sequence", [])),
                        **{col: _round6(row.get(col)) if row.get(col) is not None else "" for col in FIRST_TIME_COLUMNS},
                    }
                )
    paths["failure_causes_csv"] = failure_csv_path

    comparison = result.get("control_comparison", {})
    comparison_path = f"{out_prefix}_control_comparison.json"
    _assert_finite_jsonable(comparison)
    with open(comparison_path, "w", encoding="utf-8") as fh:
        json.dump(_round6(comparison), fh, ensure_ascii=False, indent=2, allow_nan=False)
    paths["control_comparison_json"] = comparison_path

    return paths


_SUMMARY_METRIC_NAMES = (
    "healthspan_tissue",
    "survival_time",
    "final_functional_cells",
    "final_senescent_cells",
    "final_stem_cells",
    "final_cancer_risk",
    "max_cancer_risk",
    "final_fibrosis_index",
    "final_ecm_quality",
    "final_vascular_quality",
    "final_immune_pressure",
    "area_under_senescent_curve",
    "area_under_functional_curve",
    "rejuvenation_delta_vs_baseline",
    "senescence_reduction_vs_baseline",
    "stem_depletion_delta_vs_baseline",
    "total_replaced_cells",
)


def _rounded_aggregate(aggregate: dict[str, Any]) -> dict[str, Any]:
    rounded = dict(aggregate)
    rounded["metrics"] = {
        name: {stat: _round6(value) for stat, value in stats.items()}
        for name, stats in aggregate["metrics"].items()
    }
    rounded["sustainable_rate"] = _round6(aggregate["sustainable_rate"])
    rounded["failure_rate"] = _round6(aggregate["failure_rate"])
    rounded["mean_time_to_first_viability_failure"] = _round6(aggregate["mean_time_to_first_viability_failure"])
    rounded["median_time_to_first_viability_failure"] = _round6(aggregate["median_time_to_first_viability_failure"])
    return rounded


def _rounded_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _round6(value) for key, value in row.items()}


def load_tissue_sweep_config(path: str) -> TissueSweepConfig:
    """Read a sweep JSON file into a validated config."""
    with open(path, encoding="utf-8") as fh:
        return TissueSweepConfig.from_config_dict(json.load(fh))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Stage 3B/3C tissue replacement sweep.")
    parser.add_argument("--config", required=True, help="Sweep config JSON (e.g. experiments/configs/tissue_sweep_v0.json)")
    parser.add_argument(
        "--out-prefix",
        default="",
        help="Output prefix (default: config output_prefix; files: _long.csv, _summary.csv, _summary.json, _boundary.json plus Stage 3C extras when control_profiles are configured)",
    )
    parser.add_argument(
        "--control-profile",
        default=None,
        help="Run only this control profile from the config (default: all profiles)",
    )
    args = parser.parse_args()

    config = load_tissue_sweep_config(args.config)
    out_prefix = args.out_prefix or config.output_prefix
    if not out_prefix:
        raise ValueError("no out-prefix: pass --out-prefix or set output_prefix in the config")
    result = run_tissue_sweep(config, control_profile=args.control_profile)
    paths = write_tissue_sweep_outputs(result, out_prefix)
    n_points = len(result["points"])
    print(f"[sweep {config.experiment_id}] {n_points} points x {len(config.seeds)} seeds")
    print(f"[boundary] {result['boundary']}")
    if "control_profiles" in result:
        print(f"[profiles] {result['control_profiles']}")
        print(f"[boundary_closure] {result['boundary_closure']['boundary_by_frequency']}")
    for key, path in paths.items():
        print(f"[{key}] {path}")


if __name__ == "__main__":
    main()
