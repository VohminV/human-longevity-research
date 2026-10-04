"""EXPERIMENT ENGINE LAYER: minimal organ sweep (Stage 4A, mini).

Explores ``global_replacement_scale x shared_vascular_capacity x
shared_immune_capacity x coordination`` over a few seeds by reusing
:func:`run_organ_experiment` (no organ dynamics duplicated here). Finds
the first vascular/immune bottleneck zones; it is reconnaissance, not a
full stability map.

CLI::

    PYTHONPATH=src python -m longevity.experiment.organ_sweep \\
        --config experiments/configs/organ_mini_sweep.json \\
        --out-prefix experiments/output/organ_mini_sweep
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import os
import platform
import time

from dataclasses import dataclass, field
from typing import Any

from longevity.experiment.organ_runner import run_organ_experiment
from longevity.model.organ import ORGAN_MODEL_VERSION, OrganConfig
from longevity.model.organ_policy import COORDINATION_MODES, validate_coordination

ORGAN_SWEEP_FORMAT_VERSION = "1.1"
MIN_ORGAN_SWEEP_SEEDS = 2


def _require_seed_list(seeds: Any) -> tuple[int, ...]:
    if not isinstance(seeds, (list, tuple)) or len(seeds) == 0:
        raise ValueError("organ sweep seeds must be a non-empty list")
    cleaned: list[int] = []
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"organ sweep seed must be an int, got {seed!r}")
        cleaned.append(seed)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"organ sweep seeds must be unique, got {cleaned!r}")
    if len(cleaned) < MIN_ORGAN_SWEEP_SEEDS:
        raise ValueError(f"organ sweep needs at least {MIN_ORGAN_SWEEP_SEEDS} seeds, got {len(cleaned)}")
    return tuple(cleaned)


def _require_scale_grid(values: Any) -> tuple[float, ...]:
    if not isinstance(values, (list, tuple)) or len(values) == 0:
        raise ValueError("grid.global_replacement_scale must be a non-empty list")
    cleaned: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"grid.global_replacement_scale must hold numbers, got {value!r}")
        result = float(value)
        if not math.isfinite(result) or not 0.0 <= result <= 1.0:
            raise ValueError(f"grid.global_replacement_scale must be in [0, 1], got {value!r}")
        cleaned.append(result)
    return tuple(cleaned)


def _require_capacity_grid(values: Any, name: str) -> tuple[float, ...]:
    if not isinstance(values, (list, tuple)) or len(values) == 0:
        raise ValueError(f"grid.{name} must be a non-empty list")
    cleaned: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"grid.{name} must hold numbers, got {value!r}")
        result = float(value)
        if not math.isfinite(result) or result <= 0.0:
            raise ValueError(f"grid.{name} must be positive, got {value!r}")
        cleaned.append(result)
    return tuple(cleaned)


def _require_coordination_list(values: Any) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or len(values) == 0:
        raise ValueError("coordination_modes must be a non-empty list")
    cleaned: list[str] = []
    for value in values:
        try:
            canonical = validate_coordination(value)
        except ValueError:
            raise ValueError(f"unknown coordination mode {value!r}; known: {list(COORDINATION_MODES)}")
        cleaned.append(canonical)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError(f"coordination_modes must be unique, got {cleaned!r}")
    return tuple(cleaned)


def _require_delay_grid(values: Any) -> tuple[int, ...] | None:
    if values is None:
        return None
    if not isinstance(values, (list, tuple)) or len(values) == 0:
        raise ValueError("grid.relief_delay_steps must be a non-empty list")
    cleaned: list[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"grid.relief_delay_steps must hold ints >= 0, got {value!r}")
        cleaned.append(value)
    return tuple(cleaned)


def _require_recovery_delay_grid(values: Any) -> tuple[int, ...] | None:
    if values is None:
        return None
    if not isinstance(values, (list, tuple)) or len(values) == 0:
        raise ValueError("grid.recovery_delay_steps must be a non-empty list")
    cleaned: list[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"grid.recovery_delay_steps must hold ints >= 0, got {value!r}")
        cleaned.append(value)
    return tuple(cleaned)


def _require_recovery_magnitude_grid(values: Any) -> tuple[float, ...] | None:
    if values is None:
        return None
    if not isinstance(values, (list, tuple)) or len(values) == 0:
        raise ValueError("grid.recovery_magnitude must be a non-empty list")
    cleaned: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"grid.recovery_magnitude must hold numbers, got {value!r}")
        result = float(value)
        if not math.isfinite(result) or result < 0.0:
            raise ValueError(f"grid.recovery_magnitude must be finite and >= 0, got {value!r}")
        cleaned.append(result)
    return tuple(cleaned)


def _require_imm_cost_grid(values: Any) -> tuple[float, ...] | None:
    if values is None:
        return None
    if not isinstance(values, (list, tuple)) or len(values) == 0:
        raise ValueError("grid.immediate_immune_cost must be a non-empty list")
    cleaned: list[float] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"grid.immediate_immune_cost must hold numbers, got {value!r}")
        result = float(value)
        if not math.isfinite(result) or result < 0.0:
            raise ValueError(f"grid.immediate_immune_cost must be finite and >= 0, got {value!r}")
        cleaned.append(result)
    return tuple(cleaned)


@dataclass(frozen=True)
class OrganMiniSweepConfig:
    """Complete, self-describing organ mini-sweep configuration."""

    experiment_id: str
    seeds: tuple[int, ...] = ()
    grid_scales: tuple[float, ...] = ()
    grid_vascular: tuple[float, ...] = ()
    grid_immune: tuple[float, ...] = ()
    coordination_modes: tuple[str, ...] = ()
    base_organ_config: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""
    # Stage 4C (optional; None = base config values, single combination).
    temporal_relief_model: str | None = None
    grid_delays: tuple[int, ...] | None = None
    grid_imm_costs: tuple[float, ...] | None = None
    # Stage 4D (optional; None = base config values, single combination).
    recovery_model: str | None = None
    grid_recovery_delays: tuple[int, ...] | None = None
    grid_recovery_magnitudes: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seed_list(list(self.seeds))
        _require_scale_grid(list(self.grid_scales))
        _require_capacity_grid(list(self.grid_vascular), "shared_vascular_capacity")
        _require_capacity_grid(list(self.grid_immune), "shared_immune_capacity")
        _require_coordination_list(list(self.coordination_modes))
        if not isinstance(self.base_organ_config, dict) or not self.base_organ_config:
            raise ValueError("base_organ_config must be a non-empty dict")
        OrganConfig.from_config_dict(copy.deepcopy(self.base_organ_config))
        if self.temporal_relief_model is not None:
            from longevity.model.organ import validate_temporal_model  # deferred: avoid import cycle

            object.__setattr__(
                self, "temporal_relief_model", validate_temporal_model(self.temporal_relief_model)
            )
        object.__setattr__(self, "grid_delays", _require_delay_grid(
            list(self.grid_delays) if self.grid_delays is not None else None))
        object.__setattr__(self, "grid_imm_costs", _require_imm_cost_grid(
            list(self.grid_imm_costs) if self.grid_imm_costs is not None else None))
        if self.recovery_model is not None:
            from longevity.model.organ import validate_recovery_model  # deferred: avoid import cycle

            object.__setattr__(
                self, "recovery_model", validate_recovery_model(self.recovery_model)
            )
        object.__setattr__(self, "grid_recovery_delays", _require_recovery_delay_grid(
            list(self.grid_recovery_delays) if self.grid_recovery_delays is not None else None))
        object.__setattr__(self, "grid_recovery_magnitudes", _require_recovery_magnitude_grid(
            list(self.grid_recovery_magnitudes) if self.grid_recovery_magnitudes is not None else None))

    def to_config_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            "grid": {
                "global_replacement_scale": list(self.grid_scales),
                "shared_vascular_capacity": list(self.grid_vascular),
                "shared_immune_capacity": list(self.grid_immune),
            },
            "coordination_modes": list(self.coordination_modes),
            "base_organ_config": copy.deepcopy(self.base_organ_config),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }
        if self.temporal_relief_model is not None:
            payload["temporal_relief_model"] = self.temporal_relief_model
        if self.grid_delays is not None:
            payload["grid"]["relief_delay_steps"] = list(self.grid_delays)
        if self.grid_imm_costs is not None:
            payload["grid"]["immediate_immune_cost"] = list(self.grid_imm_costs)
        if self.recovery_model is not None:
            payload["recovery_model"] = self.recovery_model
        if self.grid_recovery_delays is not None:
            payload["grid"]["recovery_delay_steps"] = list(self.grid_recovery_delays)
        if self.grid_recovery_magnitudes is not None:
            payload["grid"]["recovery_magnitude"] = list(self.grid_recovery_magnitudes)
        return payload

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "OrganMiniSweepConfig":
        grid = data.get("grid", {})
        return cls(
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            grid_scales=tuple(grid.get("global_replacement_scale", ())),
            grid_vascular=tuple(grid.get("shared_vascular_capacity", ())),
            grid_immune=tuple(grid.get("shared_immune_capacity", ())),
            coordination_modes=tuple(data.get("coordination_modes", ("independent_tissue_policies",))),
            base_organ_config=copy.deepcopy(data.get("base_organ_config", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
            temporal_relief_model=data.get("temporal_relief_model", None),
            grid_delays=tuple(grid.get("relief_delay_steps", ())) if grid.get("relief_delay_steps") is not None else None,
            grid_imm_costs=tuple(grid.get("immediate_immune_cost", ())) if grid.get("immediate_immune_cost") is not None else None,
            recovery_model=data.get("recovery_model", None),
            grid_recovery_delays=tuple(grid.get("recovery_delay_steps", ())) if grid.get("recovery_delay_steps") is not None else None,
            grid_recovery_magnitudes=tuple(grid.get("recovery_magnitude", ())) if grid.get("recovery_magnitude") is not None else None,
        )


def organ_sweep_config_hash(config: OrganMiniSweepConfig) -> str:
    canonical = json.dumps(config.to_config_dict(), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _scaled_base_config(
    base: dict[str, Any],
    scale: float,
    vascular: float,
    immune: float,
    coordination: str,
    seed: int,
    temporal_model: str | None = None,
    delay: int | None = None,
    imm_cost: float | None = None,
    recovery_model: str | None = None,
    recovery_delay: int | None = None,
    recovery_magnitude: float | None = None,
) -> OrganConfig:
    data = copy.deepcopy(base)
    data["seed"] = seed
    data["shared_vascular_capacity"] = float(vascular)
    data["shared_immune_capacity"] = float(immune)
    data["coordination"] = coordination
    if temporal_model is not None:
        data["temporal_relief_model"] = temporal_model
    params = dict(data.get("temporal_params", {}))
    if delay is not None:
        params["relief_delay_steps"] = int(delay)
    if imm_cost is not None:
        params["immediate_immune_cost_multiplier"] = float(imm_cost)
    data["temporal_params"] = params
    if recovery_model is not None:
        data["recovery_model"] = recovery_model
    for tissue in data.get("tissues", []):
        policy = tissue.get("policy", {})
        if "max_replacement_fraction" in policy:
            policy["max_replacement_fraction"] = max(0.0, min(1.0, float(policy["max_replacement_fraction"]) * float(scale)))
        recovery = tissue.get("recovery", {})
        # The sweep-level immediate-cost grid scales both replacement spikes
        # and recovery prices (single documented multiplier).
        if imm_cost is not None and recovery.get("enabled"):
            recovery["immediate_immune_multiplier"] = float(imm_cost)
            recovery["immediate_vascular_multiplier"] = float(imm_cost)
        if recovery_delay is not None and recovery.get("enabled"):
            recovery["delay_steps"] = int(recovery_delay)
        if recovery_magnitude is not None and recovery.get("enabled"):
            recovery["magnitude"] = float(recovery_magnitude)
    return OrganConfig.from_config_dict(data)


def _mean(values: list[float]) -> float:
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        raise ValueError("cannot average empty/non-finite data")
    return sum(finite) / len(finite)


def _aggregate_point(
    config: OrganMiniSweepConfig,
    coordination: str,
    vascular: float,
    immune: float,
    scale: float,
    delay: int | None,
    imm_cost: float | None,
    rec_delay: int | None,
    rec_mag: float | None,
    seed_summaries: dict[str, Any],
) -> dict[str, Any]:
    functions = [s["final_organ_function"] for s in seed_summaries.values()]
    healthspans = [s["organ_healthspan_proxy"] for s in seed_summaries.values()]
    ttfs = [s["time_to_organ_viability_failure"] for s in seed_summaries.values()]
    causes: dict[str, int] = {}
    bottlenecks: dict[str, int] = {}
    min_vasc = [s["min_vascular_allocation_ratio"] for s in seed_summaries.values()]
    min_imm = [s["min_immune_allocation_ratio"] for s in seed_summaries.values()]
    exec_frac = [s["coordination"]["execution_fraction"] for s in seed_summaries.values()]
    relief = [s["coordination"]["demand_relief_per_executed_replacement"] for s in seed_summaries.values()]
    sen_auc = [s["coordination"]["senescent_burden_auc"] for s in seed_summaries.values()]
    deferred = [s["temporal"]["deferred_plan_count"] for s in seed_summaries.values()]
    rec_exec = [s["recovery"]["total_recovery_executed"] for s in seed_summaries.values()]
    rec_deferred = [s["recovery"]["total_recovery_deferred"] for s in seed_summaries.values()]
    cap_v = [s["capacity"]["final_vascular_capacity"] for s in seed_summaries.values()]
    cap_i = [s["capacity"]["final_immune_capacity"] for s in seed_summaries.values()]
    for summary in seed_summaries.values():
        causes[summary["primary_organ_failure_cause"]] = causes.get(summary["primary_organ_failure_cause"], 0) + 1
        bottlenecks[summary["bottleneck_tissue_final"]] = bottlenecks.get(summary["bottleneck_tissue_final"], 0) + 1
    point: dict[str, Any] = {
        "global_replacement_scale": float(scale),
        "shared_vascular_capacity": float(vascular),
        "shared_immune_capacity": float(immune),
        "coordination": coordination,
        "n_seeds": len(config.seeds),
        "mean_final_organ_function": _mean(functions),
        "mean_organ_healthspan_proxy": _mean(healthspans),
        "mean_time_to_organ_viability_failure": _mean(ttfs),
        "mean_min_vascular_allocation_ratio": _mean(min_vasc),
        "mean_min_immune_allocation_ratio": _mean(min_imm),
        "mean_execution_fraction": _mean(exec_frac),
        "mean_demand_relief_per_executed": _mean(relief),
        "mean_senescent_burden_auc": _mean(sen_auc),
        "mean_deferred_plan_count": _mean([float(v) for v in deferred]),
        "mean_recovery_executed": _mean([float(v) for v in rec_exec]),
        "mean_recovery_deferred": _mean([float(v) for v in rec_deferred]),
        "mean_final_vascular_capacity": _mean(cap_v),
        "mean_final_immune_capacity": _mean(cap_i),
        "healthspan_stats": _describe(healthspans),
        "ttf_stats": _describe(ttfs),
        "function_stats": _describe(functions),
        "primary_cause_counts": causes,
        "bottleneck_counts": bottlenecks,
        "seeds": seed_summaries,
    }
    if delay is not None:
        point["relief_delay_steps"] = int(delay)
    if imm_cost is not None:
        point["immediate_immune_cost"] = float(imm_cost)
    if rec_delay is not None:
        point["recovery_delay_steps"] = int(rec_delay)
    if rec_mag is not None:
        point["recovery_magnitude"] = float(rec_mag)
    return point


def _describe(values: list[float]) -> dict[str, Any]:
    """Descriptive stats over a tiny seed sample (population std, no inference)."""
    finite = [float(v) for v in values]
    for value in finite:
        if not math.isfinite(value):
            raise ValueError(f"cannot describe non-finite value {value!r}")
    if not finite:
        raise ValueError("cannot describe empty data")
    ordered = sorted(finite)
    n = len(ordered)
    mean = sum(ordered) / n
    variance = sum((v - mean) ** 2 for v in ordered) / n

    def _pct(fraction: float) -> float:
        if n == 1:
            return ordered[0]
        rank = fraction * (n - 1)
        low, high = math.floor(rank), math.ceil(rank)
        if low == high:
            return ordered[low]
        weight = rank - low
        return ordered[low] * (1.0 - weight) + ordered[high] * weight

    return {
        "mean": mean,
        "std": math.sqrt(variance),
        "min": ordered[0],
        "max": ordered[-1],
        "median": _pct(0.5),
        "p25": _pct(0.25),
        "p75": _pct(0.75),
        "count": n,
    }


def _gain(point: dict[str, Any], reference: dict[str, Any]) -> dict[str, float]:
    return {
        "healthspan_gain": point["mean_organ_healthspan_proxy"] - reference["mean_organ_healthspan_proxy"],
        "ttf_gain": point["mean_time_to_organ_viability_failure"] - reference["mean_time_to_organ_viability_failure"],
        "function_gain": point["mean_final_organ_function"] - reference["mean_final_organ_function"],
    }


def _point_key(point: dict[str, Any]) -> tuple:
    return (
        point["global_replacement_scale"],
        point["shared_vascular_capacity"],
        point["shared_immune_capacity"],
        point.get("relief_delay_steps"),
        point.get("immediate_immune_cost"),
        point.get("recovery_delay_steps"),
        point.get("recovery_magnitude"),
        point["coordination"],
    )


def run_organ_sweep(config: OrganMiniSweepConfig) -> dict[str, Any]:
    """Run the mini grid over all seeds; returns a JSON-serializable result."""
    wall_start = time.perf_counter()
    delays = sorted(config.grid_delays) if config.grid_delays is not None else [None]
    imm_costs = sorted(config.grid_imm_costs) if config.grid_imm_costs is not None else [None]
    rec_delays = sorted(config.grid_recovery_delays) if config.grid_recovery_delays is not None else [None]
    rec_mags = sorted(config.grid_recovery_magnitudes) if config.grid_recovery_magnitudes is not None else [None]
    points: list[dict[str, Any]] = []
    for coordination in config.coordination_modes:
        for vascular in sorted(config.grid_vascular):
            for immune in sorted(config.grid_immune):
                for scale in sorted(config.grid_scales):
                    for delay in delays:
                        for imm_cost in imm_costs:
                            for rec_delay in rec_delays:
                                for rec_mag in rec_mags:
                                    seed_summaries: dict[str, Any] = {}
                                    for seed in config.seeds:
                                        organ_config = _scaled_base_config(
                                            config.base_organ_config, scale, vascular, immune, coordination, seed,
                                            config.temporal_relief_model, delay, imm_cost,
                                            config.recovery_model, rec_delay, rec_mag,
                                        )
                                        result = run_organ_experiment(organ_config, out_path=None)
                                        seed_summaries[str(seed)] = result["metrics"]["final"]
                                    point = _aggregate_point(
                                        config, coordination, vascular, immune, scale, delay, imm_cost,
                                        rec_delay, rec_mag, seed_summaries,
                                    )
                                    points.append(point)
    # Coordination benefit per grid cell present in both modes (legacy pair).
    benefit: list[dict[str, Any]] = []
    by_key = {_point_key(p): p for p in points}
    modes = list(config.coordination_modes)
    if len(modes) >= 2:
        for scale in sorted(config.grid_scales):
            for vascular in sorted(config.grid_vascular):
                for immune in sorted(config.grid_immune):
                    for delay in delays:
                        for imm_cost in imm_costs:
                            for rec_delay in rec_delays:
                                for rec_mag in rec_mags:
                                    rows = {
                                        mode: by_key.get(
                                            (float(scale), float(vascular), float(immune), delay, imm_cost,
                                             rec_delay, rec_mag, mode)
                                        )
                                        for mode in modes
                                    }
                                    if all(rows.values()):
                                        first, second = modes[0], modes[1]
                                        row = {
                                            "global_replacement_scale": float(scale),
                                            "shared_vascular_capacity": float(vascular),
                                            "shared_immune_capacity": float(immune),
                                            "baseline_mode": first,
                                            "comparison_mode": second,
                                            "healthspan_gain": rows[second]["mean_organ_healthspan_proxy"] - rows[first]["mean_organ_healthspan_proxy"],
                                            "ttf_gain": rows[second]["mean_time_to_organ_viability_failure"] - rows[first]["mean_time_to_organ_viability_failure"],
                                            "function_gain": rows[second]["mean_final_organ_function"] - rows[first]["mean_final_organ_function"],
                                        }
                                        if delay is not None:
                                            row["relief_delay_steps"] = int(delay)
                                        if imm_cost is not None:
                                            row["immediate_immune_cost"] = float(imm_cost)
                                        if rec_delay is not None:
                                            row["recovery_delay_steps"] = int(rec_delay)
                                        if rec_mag is not None:
                                            row["recovery_magnitude"] = float(rec_mag)
                                        benefit.append(row)
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    result: dict[str, Any] = {
        "experiment_id": config.experiment_id,
        "format": ORGAN_SWEEP_FORMAT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": organ_sweep_config_hash(config),
        "model_version": ORGAN_MODEL_VERSION,
        "seeds": list(config.seeds),
        "points": points,
        "coordination_benefit": benefit,
        "coordination_comparison": _coordination_comparison(points, list(config.coordination_modes)),
        "supply_demand_comparison": _supply_demand_comparison(points, list(config.coordination_modes)),
        "immune_sensitivity": _immune_sensitivity(points, sorted(config.grid_immune)),
        "immune_transition": _immune_transition(points, list(config.coordination_modes)),
        "failure_cause_distribution": _failure_cause_distribution(points, list(config.coordination_modes)),
        "temporal_sensitivity": _temporal_sensitivity(points),
        "temporal_transition": _temporal_transition(points, list(config.coordination_modes)),
        "capacity_transition": _capacity_transition(points),
        "runtime": {
            "engine": "organ-sweep/v1",
            "python": platform.python_version(),
            "platform": platform.platform(),
            "wall_seconds": wall_seconds,
        },
    }
    return result


def _coordination_comparison(points: list[dict[str, Any]], modes: list[str]) -> dict[str, Any]:
    """Pooled per-mode stats plus gains vs independent/proportional (pure)."""
    by_mode: dict[str, Any] = {}
    for mode in modes:
        owned = [p for p in points if p["coordination"] == mode]
        if not owned:
            continue
        causes: dict[str, int] = {}
        for point in owned:
            for cause, count in point["primary_cause_counts"].items():
                causes[cause] = causes.get(cause, 0) + count
        by_mode[mode] = {
            "n_points": len(owned),
            "mean_healthspan": _mean([p["mean_organ_healthspan_proxy"] for p in owned]),
            "mean_ttf": _mean([p["mean_time_to_organ_viability_failure"] for p in owned]),
            "mean_function": _mean([p["mean_final_organ_function"] for p in owned]),
            "mean_execution_fraction": _mean([p["mean_execution_fraction"] for p in owned]),
            "pooled_cause_counts": causes,
        }
    gains: dict[str, list[dict[str, Any]]] = {"vs_independent": [], "vs_proportional": [], "vs_demand_relief": []}
    index = {_point_key(p): p for p in points}
    references = {
        "vs_independent": "independent_tissue_policies",
        "vs_proportional": "resource_aware_scaling",
        "vs_demand_relief": "demand_relief_priority",
    }
    for key, reference_mode in references.items():
        for point in points:
            reference = index.get(
                (point["global_replacement_scale"], point["shared_vascular_capacity"],
                 point["shared_immune_capacity"], point.get("relief_delay_steps"),
                 point.get("immediate_immune_cost"), reference_mode)
            )
            if reference is None or point["coordination"] == reference_mode:
                continue
            row = {
                "global_replacement_scale": point["global_replacement_scale"],
                "shared_vascular_capacity": point["shared_vascular_capacity"],
                "shared_immune_capacity": point["shared_immune_capacity"],
                "coordination": point["coordination"],
                "reference": reference_mode,
                **_gain(point, reference),
            }
            if point.get("relief_delay_steps") is not None:
                row["relief_delay_steps"] = point["relief_delay_steps"]
            if point.get("immediate_immune_cost") is not None:
                row["immediate_immune_cost"] = point["immediate_immune_cost"]
            if point.get("recovery_delay_steps") is not None:
                row["recovery_delay_steps"] = point["recovery_delay_steps"]
            if point.get("recovery_magnitude") is not None:
                row["recovery_magnitude"] = point["recovery_magnitude"]
            gains[key].append(row)
    # Non-destructive benefit: temporal/scheduling modes vs pruning modes.
    pruning_modes = {
        "resource_aware_scaling", "demand_relief_priority",
        "senescent_burden_priority", "hybrid_demand_guard",
    }
    scheduling_modes = {"lookahead_priority", "deferral_scheduler", "hybrid_lookahead_deferral"}
    non_destructive: list[dict[str, Any]] = []
    for point in points:
        if point["coordination"] not in scheduling_modes:
            continue
        for reference_mode in sorted(pruning_modes):
            reference = index.get(
                (point["global_replacement_scale"], point["shared_vascular_capacity"],
                 point["shared_immune_capacity"], point.get("relief_delay_steps"),
                 point.get("immediate_immune_cost"), reference_mode)
            )
            if reference is None:
                continue
            row = {
                "global_replacement_scale": point["global_replacement_scale"],
                "shared_vascular_capacity": point["shared_vascular_capacity"],
                "shared_immune_capacity": point["shared_immune_capacity"],
                "coordination": point["coordination"],
                "reference": reference_mode,
                **_gain(point, reference),
            }
            if point.get("relief_delay_steps") is not None:
                row["relief_delay_steps"] = point["relief_delay_steps"]
            if point.get("immediate_immune_cost") is not None:
                row["immediate_immune_cost"] = point["immediate_immune_cost"]
            non_destructive.append(row)
    gains["non_destructive_benefit"] = non_destructive
    return {"by_mode": by_mode, "gains": gains}


def _temporal_sensitivity(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Per (delay, imm cost, immune cap): cause mix + per-mode means (pure)."""
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for point in points:
        key = (point.get("relief_delay_steps"), point.get("immediate_immune_cost"), point["shared_immune_capacity"])
        groups.setdefault(key, []).append(point)
    rows: list[dict[str, Any]] = []
    for (delay, imm_cost, immune) in sorted(groups, key=lambda k: (k[0] is None, k[0], k[1] is None, k[1], k[2])):
        owned = groups[(delay, imm_cost, immune)]
        causes: dict[str, int] = {}
        for point in owned:
            for cause, count in point["primary_cause_counts"].items():
                causes[cause] = causes.get(cause, 0) + count
        per_mode = {
            mode: {
                "mean_healthspan": _mean([p["mean_organ_healthspan_proxy"] for p in owned if p["coordination"] == mode]),
                "mean_ttf": _mean([p["mean_time_to_organ_viability_failure"] for p in owned if p["coordination"] == mode]),
            }
            for mode in sorted({p["coordination"] for p in owned})
        }
        row: dict[str, Any] = {
            "shared_immune_capacity": immune,
            "n_points": len(owned),
            "primary_cause_counts": causes,
            "immune_only": len(causes) == 1 and "immune_capacity_failure" in causes,
            "per_mode": per_mode,
        }
        if delay is not None:
            row["relief_delay_steps"] = delay
        if imm_cost is not None:
            row["immediate_immune_cost"] = imm_cost
        rows.append(row)
    return {"by_temporal_cell": rows}


def _temporal_transition(points: list[dict[str, Any]], modes: list[str]) -> dict[str, Any]:
    """Best mode and cause mix per delay value (pure).

    Reports, for each relief delay present in the grid, which coordination
    wins on mean healthspan and whether any tissue failure cause appears.
    """
    tissue_causes = {
        "parenchyma_failure", "stroma_failure", "vascular_interface_failure",
        "organ_function_failure", "organ_cancer_risk", "organ_fibrosis",
    }
    delays = sorted({p.get("relief_delay_steps") for p in points}, key=lambda v: (v is None, v))
    rows: list[dict[str, Any]] = []
    for delay in delays:
        owned = [p for p in points if p.get("relief_delay_steps") == delay]
        by_mode_hs = {
            mode: _mean([p["mean_organ_healthspan_proxy"] for p in owned if p["coordination"] == mode])
            for mode in sorted({p["coordination"] for p in owned})
        }
        causes: dict[str, int] = {}
        for point in owned:
            for cause, count in point["primary_cause_counts"].items():
                causes[cause] = causes.get(cause, 0) + count
        row: dict[str, Any] = {
            "n_points": len(owned),
            "best_mode_by_healthspan": max(by_mode_hs, key=lambda m: (by_mode_hs[m], m)) if by_mode_hs else None,
            "per_mode_healthspan": by_mode_hs,
            "tissue_cause_present": any(cause in tissue_causes for cause in causes),
            "tissue_cause_marker": None if any(cause in tissue_causes for cause in causes) else "no_tissue_cause_at_this_delay",
        }
        if delay is not None:
            row["relief_delay_steps"] = delay
        rows.append(row)
    return {"by_delay": rows}


def _immune_sensitivity(points: list[dict[str, Any]], immune_grid: list[float]) -> dict[str, Any]:
    """Per immune capacity: cause mix and per-mode viability means (pure)."""
    rows: list[dict[str, Any]] = []
    for immune in sorted(float(v) for v in immune_grid):
        owned = [p for p in points if float(p["shared_immune_capacity"]) == immune]
        causes: dict[str, int] = {}
        for point in owned:
            for cause, count in point["primary_cause_counts"].items():
                causes[cause] = causes.get(cause, 0) + count
        per_mode = {
            mode: {
                "mean_healthspan": _mean([p["mean_organ_healthspan_proxy"] for p in owned if p["coordination"] == mode]),
                "mean_ttf": _mean([p["mean_time_to_organ_viability_failure"] for p in owned if p["coordination"] == mode]),
            }
            for mode in sorted({p["coordination"] for p in owned})
        }
        rows.append(
            {
                "shared_immune_capacity": immune,
                "n_points": len(owned),
                "primary_cause_counts": causes,
                "immune_only": len(causes) == 1 and "immune_capacity_failure" in causes,
                "per_mode": per_mode,
            }
        )
    return {"by_immune_capacity": rows}


def _immune_transition(points: list[dict[str, Any]], modes: list[str]) -> dict[str, Any]:
    """Immune-dominated range vs tissue-cause emergence per mode (pure).

    ``immune_collapse_max_capacity``: largest immune capacity where every
    seed still fails with ``immune_capacity_failure``. ``tissue_emergence``
    tracks genuine tissue/organ-risk failure causes only (``"none"`` —
    sustained viability — never counts as emergence). Absence of tissue
    causes is reported explicitly, not as a boundary.
    """
    tissue_causes = {
        "parenchyma_failure", "stroma_failure", "vascular_interface_failure",
        "organ_function_failure", "organ_cancer_risk", "organ_fibrosis",
    }
    by_mode: dict[str, Any] = {}
    for mode in modes:
        owned = sorted(
            (p for p in points if p["coordination"] == mode),
            key=lambda p: float(p["shared_immune_capacity"]),
        )
        immune_only_caps = [
            float(p["shared_immune_capacity"])
            for p in owned
            if set(p["primary_cause_counts"]) == {"immune_capacity_failure"}
        ]
        tissue_caps = [
            float(p["shared_immune_capacity"])
            for p in owned
            if any(cause in tissue_causes for cause in p["primary_cause_counts"])
        ]
        by_mode[mode] = {
            "immune_collapse_max_capacity": max(immune_only_caps) if immune_only_caps else None,
            "tissue_emergence_min_capacity": min(tissue_caps) if tissue_caps else None,
            "tissue_cause_marker": None if tissue_caps else "no_tissue_cause_in_current_grid",
        }
    return {"by_mode": by_mode}


def _supply_demand_comparison(points: list[dict[str, Any]], modes: list[str]) -> dict[str, Any]:
    """Pooled per-mode supply-demand stats plus gains vs independent_all (pure)."""
    by_mode: dict[str, Any] = {}
    for mode in modes:
        owned = [p for p in points if p["coordination"] == mode]
        if not owned:
            continue
        causes: dict[str, int] = {}
        for point in owned:
            for cause, count in point["primary_cause_counts"].items():
                causes[cause] = causes.get(cause, 0) + count
        by_mode[mode] = {
            "n_points": len(owned),
            "mean_healthspan": _mean([p["mean_organ_healthspan_proxy"] for p in owned]),
            "mean_ttf": _mean([p["mean_time_to_organ_viability_failure"] for p in owned]),
            "mean_function": _mean([p["mean_final_organ_function"] for p in owned]),
            "mean_execution_fraction": _mean([p["mean_execution_fraction"] for p in owned]),
            "mean_recovery_executed": _mean([p["mean_recovery_executed"] for p in owned]),
            "mean_final_vascular_capacity": _mean([p["mean_final_vascular_capacity"] for p in owned]),
            "mean_final_immune_capacity": _mean([p["mean_final_immune_capacity"] for p in owned]),
            "pooled_cause_counts": causes,
        }
    gains: list[dict[str, Any]] = []
    index = {_point_key(p): p for p in points}
    for point in points:
        reference = index.get(
            (point["global_replacement_scale"], point["shared_vascular_capacity"],
             point["shared_immune_capacity"], point.get("relief_delay_steps"),
             point.get("immediate_immune_cost"), point.get("recovery_delay_steps"),
             point.get("recovery_magnitude"), "independent_all")
        )
        if reference is None or point["coordination"] == "independent_all":
            continue
        row = {
            "global_replacement_scale": point["global_replacement_scale"],
            "shared_vascular_capacity": point["shared_vascular_capacity"],
            "shared_immune_capacity": point["shared_immune_capacity"],
            "coordination": point["coordination"],
            "reference": "independent_all",
            **_gain(point, reference),
        }
        for key in ("relief_delay_steps", "immediate_immune_cost", "recovery_delay_steps", "recovery_magnitude"):
            if point.get(key) is not None:
                row[key] = point[key]
        gains.append(row)
    return {"by_mode": by_mode, "gains_vs_independent_all": gains}


def _capacity_transition(points: list[dict[str, Any]]) -> dict[str, Any]:
    """Per initial-capacity cause mix and capacity means (pure, Stage 4D)."""
    groups: dict[tuple, list[dict[str, Any]]] = {}
    for point in points:
        key = (point["shared_vascular_capacity"], point["shared_immune_capacity"])
        groups.setdefault(key, []).append(point)
    rows: list[dict[str, Any]] = []
    for (vascular, immune) in sorted(groups):
        owned = groups[(vascular, immune)]
        causes: dict[str, int] = {}
        for point in owned:
            for cause, count in point["primary_cause_counts"].items():
                causes[cause] = causes.get(cause, 0) + count
        rows.append(
            {
                "shared_vascular_capacity": vascular,
                "shared_immune_capacity": immune,
                "n_points": len(owned),
                "primary_cause_counts": causes,
                "mean_final_vascular_capacity": _mean([p["mean_final_vascular_capacity"] for p in owned]),
                "mean_final_immune_capacity": _mean([p["mean_final_immune_capacity"] for p in owned]),
                "per_mode": {
                    mode: {
                        "mean_healthspan": _mean([p["mean_organ_healthspan_proxy"] for p in owned if p["coordination"] == mode]),
                        "mean_ttf": _mean([p["mean_time_to_organ_viability_failure"] for p in owned if p["coordination"] == mode]),
                    }
                    for mode in sorted({p["coordination"] for p in owned})
                },
            }
        )
    return {"by_initial_capacity": rows}


def _failure_cause_distribution(points: list[dict[str, Any]], modes: list[str]) -> dict[str, Any]:
    """Pooled primary-cause counts per mode and overall (pure)."""
    overall: dict[str, int] = {}
    by_mode: dict[str, Any] = {}
    for mode in modes:
        counts: dict[str, int] = {}
        for point in points:
            if point["coordination"] != mode:
                continue
            for cause, count in point["primary_cause_counts"].items():
                counts[cause] = counts.get(cause, 0) + count
                overall[cause] = overall.get(cause, 0) + count
        by_mode[mode] = counts
    return {"by_mode": by_mode, "overall": overall}


def _round6(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [_round6(v) for v in value]
    if isinstance(value, dict):
        return {k: _round6(v) for k, v in value.items()}
    return value


def write_organ_sweep_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    """Write mini-sweep summary JSON + CSV artifacts (Stage 4A shape)."""
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    summary_path = f"{out_prefix}_summary.json"
    csv_path = f"{out_prefix}_summary.csv"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(_round6(result), fh, ensure_ascii=False, indent=2, allow_nan=False)
    fieldnames = [
        "global_replacement_scale", "shared_vascular_capacity", "shared_immune_capacity",
        "coordination", "n_seeds", "mean_final_organ_function", "mean_organ_healthspan_proxy",
        "mean_time_to_organ_viability_failure", "mean_min_vascular_allocation_ratio",
        "mean_min_immune_allocation_ratio", "primary_cause_counts", "bottleneck_counts",
    ]
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for point in result["points"]:
            writer.writerow(
                {
                    **{k: _round6(point[k]) for k in fieldnames if k not in ("primary_cause_counts", "bottleneck_counts")},
                    "primary_cause_counts": json.dumps(point["primary_cause_counts"], sort_keys=True),
                    "bottleneck_counts": json.dumps(point["bottleneck_counts"], sort_keys=True),
                }
            )
    return {"summary_json": summary_path, "summary_csv": csv_path}


LONG_COLUMNS = (
    "seed",
    "coordination",
    "global_replacement_scale",
    "shared_vascular_capacity",
    "shared_immune_capacity",
    "final_organ_function",
    "organ_healthspan_proxy",
    "time_to_organ_viability_failure",
    "primary_organ_failure_cause",
    "bottleneck_tissue_final",
    "min_vascular_allocation_ratio",
    "min_immune_allocation_ratio",
    "execution_fraction",
    "demand_relief_per_executed_replacement",
    "senescent_burden_auc",
)


def write_organ_coordination_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    """Write Stage 4B coordination/sensitivity artifacts (long + summaries).

    Long CSV holds one row per seed + point; summary CSV one row per point;
    JSON blocks carry the coordination comparison, failure-cause
    distribution and the immune-transition boundary.
    """
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    long_path = f"{out_prefix}_long.csv"
    summary_path = f"{out_prefix}_summary.csv"
    summary_json_path = f"{out_prefix}_summary.json"
    comparison_path = f"{out_prefix}_comparison.json"
    failure_path = f"{out_prefix}_failure_causes.json"
    boundary_path = f"{out_prefix}_boundary.json"

    long_columns = list(LONG_COLUMNS)
    has_temporal = any(
        "relief_delay_steps" in p or "immediate_immune_cost" in p
        or "recovery_delay_steps" in p or "recovery_magnitude" in p
        for p in result["points"]
    )
    if has_temporal:
        long_columns += ["relief_delay_steps", "immediate_immune_cost", "recovery_delay_steps", "recovery_magnitude"]
    long_rows: list[dict[str, Any]] = []
    for point in result["points"]:
        for seed in result["seeds"]:
            row = point["seeds"][str(seed)]
            coordination = row.get("coordination", {})
            long_row = {
                "seed": seed,
                "coordination": point["coordination"],
                "global_replacement_scale": _round6(point["global_replacement_scale"]),
                "shared_vascular_capacity": _round6(point["shared_vascular_capacity"]),
                "shared_immune_capacity": _round6(point["shared_immune_capacity"]),
                "final_organ_function": _round6(row["final_organ_function"]),
                "organ_healthspan_proxy": _round6(row["organ_healthspan_proxy"]),
                "time_to_organ_viability_failure": _round6(row["time_to_organ_viability_failure"]),
                "primary_organ_failure_cause": row["primary_organ_failure_cause"],
                "bottleneck_tissue_final": row["bottleneck_tissue_final"],
                "min_vascular_allocation_ratio": _round6(row["min_vascular_allocation_ratio"]),
                "min_immune_allocation_ratio": _round6(row["min_immune_allocation_ratio"]),
                "execution_fraction": _round6(coordination.get("execution_fraction", 1.0)),
                "demand_relief_per_executed_replacement": _round6(
                    coordination.get("demand_relief_per_executed_replacement", 0.0)
                ),
                "senescent_burden_auc": _round6(coordination.get("senescent_burden_auc", 0.0)),
            }
            if has_temporal:
                long_row["relief_delay_steps"] = point.get("relief_delay_steps", "")
                long_row["immediate_immune_cost"] = point.get("immediate_immune_cost", "")
                long_row["recovery_delay_steps"] = point.get("recovery_delay_steps", "")
                long_row["recovery_magnitude"] = point.get("recovery_magnitude", "")
            long_rows.append(long_row)
    with open(long_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=long_columns)
        writer.writeheader()
        writer.writerows(long_rows)

    summary_fieldnames = [
        "global_replacement_scale", "shared_vascular_capacity", "shared_immune_capacity",
        "coordination", "n_seeds", "mean_final_organ_function", "mean_organ_healthspan_proxy",
        "mean_time_to_organ_viability_failure", "mean_min_vascular_allocation_ratio",
        "mean_min_immune_allocation_ratio", "mean_execution_fraction",
        "mean_demand_relief_per_executed", "mean_senescent_burden_auc",
        "primary_cause_counts", "bottleneck_counts",
    ]
    if has_temporal:
        summary_fieldnames += ["relief_delay_steps", "immediate_immune_cost",
                               "recovery_delay_steps", "recovery_magnitude"]
    with open(summary_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=summary_fieldnames)
        writer.writeheader()
        for point in result["points"]:
            row = {
                "global_replacement_scale": _round6(point["global_replacement_scale"]),
                "shared_vascular_capacity": _round6(point["shared_vascular_capacity"]),
                "shared_immune_capacity": _round6(point["shared_immune_capacity"]),
                "coordination": point["coordination"],
                "n_seeds": point["n_seeds"],
                "mean_final_organ_function": _round6(point["mean_final_organ_function"]),
                "mean_organ_healthspan_proxy": _round6(point["mean_organ_healthspan_proxy"]),
                "mean_time_to_organ_viability_failure": _round6(point["mean_time_to_organ_viability_failure"]),
                "mean_min_vascular_allocation_ratio": _round6(point["mean_min_vascular_allocation_ratio"]),
                "mean_min_immune_allocation_ratio": _round6(point["mean_min_immune_allocation_ratio"]),
                "mean_execution_fraction": _round6(point["mean_execution_fraction"]),
                "mean_demand_relief_per_executed": _round6(point["mean_demand_relief_per_executed"]),
                "mean_senescent_burden_auc": _round6(point["mean_senescent_burden_auc"]),
                "primary_cause_counts": json.dumps(point["primary_cause_counts"], sort_keys=True),
                "bottleneck_counts": json.dumps(point["bottleneck_counts"], sort_keys=True),
            }
            if has_temporal:
                row["relief_delay_steps"] = point.get("relief_delay_steps", "")
                row["immediate_immune_cost"] = point.get("immediate_immune_cost", "")
                row["recovery_delay_steps"] = point.get("recovery_delay_steps", "")
                row["recovery_magnitude"] = point.get("recovery_magnitude", "")
            writer.writerow(row)

    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(_round6(result), fh, ensure_ascii=False, indent=2, allow_nan=False)
    comparison_payload = {
        "experiment_id": result["experiment_id"],
        "config_hash": result["config_hash"],
        "coordination_comparison": _round6(result.get("coordination_comparison", {})),
        "coordination_benefit": _round6(result.get("coordination_benefit", [])),
    }
    with open(comparison_path, "w", encoding="utf-8") as fh:
        json.dump(comparison_payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    failure_payload = {
        "experiment_id": result["experiment_id"],
        "config_hash": result["config_hash"],
        "failure_cause_distribution": _round6(result.get("failure_cause_distribution", {})),
        "immune_sensitivity": _round6(result.get("immune_sensitivity", {})),
    }
    with open(failure_path, "w", encoding="utf-8") as fh:
        json.dump(failure_payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    boundary_payload = {
        "experiment_id": result["experiment_id"],
        "config_hash": result["config_hash"],
        "immune_transition": _round6(result.get("immune_transition", {})),
        "temporal_transition": _round6(result.get("temporal_transition", {})),
    }
    with open(boundary_path, "w", encoding="utf-8") as fh:
        json.dump(boundary_payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    return {
        "long_csv": long_path,
        "summary_csv": summary_path,
        "summary_json": summary_json_path,
        "comparison_json": comparison_path,
        "failure_causes_json": failure_path,
        "boundary_json": boundary_path,
    }


RECOVERY_STATS_COLUMNS = (
    "global_replacement_scale",
    "shared_vascular_capacity",
    "shared_immune_capacity",
    "relief_delay_steps",
    "immediate_immune_cost",
    "recovery_delay_steps",
    "recovery_magnitude",
    "coordination",
    "n_seeds",
    "mean_recovery_planned",
    "mean_recovery_executed",
    "mean_recovery_deferred",
    "mean_recovery_expired",
    "mean_recovery_rejected",
    "mean_recovery_merged",
    "mean_capacity_increase_created",
    "mean_capacity_increase_realized",
    "mean_capacity_realization_ratio",
    "mean_final_vascular_capacity",
    "mean_final_immune_capacity",
)


def write_organ_recovery_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    """Write Stage 4D recovery artifacts (temporal set + recovery stats).

    Reuses :func:`write_organ_temporal_outputs` for the long/summary/
    comparison/failure/boundary/deferral family and adds a per-point
    recovery-stats CSV plus the supply-demand comparison JSON.
    """
    paths = write_organ_temporal_outputs(result, out_prefix)
    stats_path = f"{out_prefix}_recovery_stats.csv"
    with open(stats_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(RECOVERY_STATS_COLUMNS))
        writer.writeheader()
        for point in result["points"]:
            per_seed = [point["seeds"][str(seed)]["recovery"] for seed in result["seeds"]]
            writer.writerow(
                {
                    "global_replacement_scale": _round6(point["global_replacement_scale"]),
                    "shared_vascular_capacity": _round6(point["shared_vascular_capacity"]),
                    "shared_immune_capacity": _round6(point["shared_immune_capacity"]),
                    "relief_delay_steps": point.get("relief_delay_steps", ""),
                    "immediate_immune_cost": point.get("immediate_immune_cost", ""),
                    "recovery_delay_steps": point.get("recovery_delay_steps", ""),
                    "recovery_magnitude": point.get("recovery_magnitude", ""),
                    "coordination": point["coordination"],
                    "n_seeds": point["n_seeds"],
                    "mean_recovery_planned": _round6(_mean([float(s["total_recovery_planned"]) for s in per_seed])),
                    "mean_recovery_executed": _round6(_mean([float(s["total_recovery_executed"]) for s in per_seed])),
                    "mean_recovery_deferred": _round6(_mean([float(s["total_recovery_deferred"]) for s in per_seed])),
                    "mean_recovery_expired": _round6(_mean([float(s["total_recovery_expired"]) for s in per_seed])),
                    "mean_recovery_rejected": _round6(_mean([float(s["total_recovery_rejected"]) for s in per_seed])),
                    "mean_recovery_merged": _round6(_mean([float(s["total_recovery_merged"]) for s in per_seed])),
                    "mean_capacity_increase_created": _round6(
                        _mean([float(s["total_capacity_increase_created"]) for s in per_seed])),
                    "mean_capacity_increase_realized": _round6(
                        _mean([float(s["total_capacity_increase_realized"]) for s in per_seed])),
                    "mean_capacity_realization_ratio": _round6(
                        _mean([float(s["capacity_increase_realization_ratio"]) for s in per_seed])),
                    "mean_final_vascular_capacity": _round6(point["mean_final_vascular_capacity"]),
                    "mean_final_immune_capacity": _round6(point["mean_final_immune_capacity"]),
                }
            )
    paths["recovery_stats_csv"] = stats_path
    supply_path = f"{out_prefix}_supply_demand_comparison.json"
    with open(supply_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "experiment_id": result["experiment_id"],
                "config_hash": result["config_hash"],
                "supply_demand_comparison": _round6(result.get("supply_demand_comparison", {})),
                "capacity_transition": _round6(result.get("capacity_transition", {})),
            },
            fh, ensure_ascii=False, indent=2, allow_nan=False,
        )
    paths["supply_demand_comparison_json"] = supply_path
    return paths


DEFERRAL_STATS_COLUMNS = (
    "global_replacement_scale",
    "shared_vascular_capacity",
    "shared_immune_capacity",
    "relief_delay_steps",
    "immediate_immune_cost",
    "coordination",
    "n_seeds",
    "mean_deferred_plan_count",
    "mean_executed_after_deferral_count",
    "mean_expired_deferred_plan_count",
    "mean_defer_steps",
    "mean_max_defer_queue_length",
    "mean_delayed_relief_realized",
    "mean_relief_realization_ratio",
    "mean_immediate_immune_cost",
)


def write_organ_temporal_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    """Write Stage 4C temporal artifacts (coordination set + deferral stats).

    Reuses :func:`write_organ_coordination_outputs` for the long/summary/
    comparison/failure/boundary family (temporal point keys flow through
    the generic blocks) and adds a per-point deferral-stats CSV plus the
    temporal comparison/sensitivity blocks.
    """
    paths = write_organ_coordination_outputs(result, out_prefix)
    stats_path = f"{out_prefix}_deferral_stats.csv"
    with open(stats_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(DEFERRAL_STATS_COLUMNS))
        writer.writeheader()
        for point in result["points"]:
            per_seed = [point["seeds"][str(seed)]["temporal"] for seed in result["seeds"]]
            writer.writerow(
                {
                    "global_replacement_scale": _round6(point["global_replacement_scale"]),
                    "shared_vascular_capacity": _round6(point["shared_vascular_capacity"]),
                    "shared_immune_capacity": _round6(point["shared_immune_capacity"]),
                    "relief_delay_steps": point.get("relief_delay_steps", ""),
                    "immediate_immune_cost": point.get("immediate_immune_cost", ""),
                    "coordination": point["coordination"],
                    "n_seeds": point["n_seeds"],
                    "mean_deferred_plan_count": _round6(_mean([float(s["deferred_plan_count"]) for s in per_seed])),
                    "mean_executed_after_deferral_count": _round6(
                        _mean([float(s["executed_after_deferral_count"]) for s in per_seed])
                    ),
                    "mean_expired_deferred_plan_count": _round6(
                        _mean([float(s["expired_deferred_plan_count"]) for s in per_seed])
                    ),
                    "mean_defer_steps": _round6(
                        _mean([s["mean_defer_steps"] for s in per_seed if s["mean_defer_steps"] is not None])
                    ) if any(s["mean_defer_steps"] is not None for s in per_seed) else "",
                    "mean_max_defer_queue_length": _round6(
                        _mean([float(s["max_defer_queue_length"]) for s in per_seed])
                    ),
                    "mean_delayed_relief_realized": _round6(
                        _mean([float(s["total_delayed_relief_realized"]) for s in per_seed])
                    ),
                    "mean_relief_realization_ratio": _round6(
                        _mean([float(s["relief_realization_ratio"]) for s in per_seed])
                    ),
                    "mean_immediate_immune_cost": _round6(
                        _mean([float(s["total_immediate_immune_cost"]) for s in per_seed])
                    ),
                }
            )
    paths["deferral_stats_csv"] = stats_path
    temporal_path = f"{out_prefix}_temporal_comparison.json"
    with open(temporal_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "experiment_id": result["experiment_id"],
                "config_hash": result["config_hash"],
                "coordination_comparison": _round6(result.get("coordination_comparison", {})),
                "temporal_sensitivity": _round6(result.get("temporal_sensitivity", {})),
                "temporal_transition": _round6(result.get("temporal_transition", {})),
            },
            fh, ensure_ascii=False, indent=2, allow_nan=False,
        )
    paths["temporal_comparison_json"] = temporal_path
    return paths


def load_organ_sweep_config(path: str) -> OrganMiniSweepConfig:
    """Read an organ mini-sweep JSON file into a validated config."""
    with open(path, encoding="utf-8") as fh:
        return OrganMiniSweepConfig.from_config_dict(json.load(fh))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Stage 4A/4B organ sweep.")
    parser.add_argument("--config", required=True, help="Organ sweep config JSON (e.g. experiments/configs/organ_mini_sweep.json)")
    parser.add_argument("--out-prefix", default="", help="Output prefix (default: config output_prefix)")
    parser.add_argument(
        "--artifacts",
        default="mini",
        choices=("mini", "coordination", "temporal", "recovery"),
        help="Artifact set: 'mini' writes summary JSON+CSV (Stage 4A shape); 'coordination' adds long CSV, comparison, failure-cause and boundary JSON (Stage 4B); 'temporal' adds deferral-stats CSV and temporal comparison JSON (Stage 4C); 'recovery' adds recovery-stats CSV and supply-demand comparison JSON (Stage 4D)",
    )
    args = parser.parse_args()

    config = load_organ_sweep_config(args.config)
    out_prefix = args.out_prefix or config.output_prefix
    if not out_prefix:
        raise ValueError("no out-prefix: pass --out-prefix or set output_prefix in the config")
    result = run_organ_sweep(config)
    if args.artifacts == "recovery":
        paths = write_organ_recovery_outputs(result, out_prefix)
    elif args.artifacts == "temporal":
        paths = write_organ_temporal_outputs(result, out_prefix)
    elif args.artifacts == "coordination":
        paths = write_organ_coordination_outputs(result, out_prefix)
    else:
        paths = write_organ_sweep_outputs(result, out_prefix)
    print(f"[organ sweep {config.experiment_id}] {len(result['points'])} points x {len(config.seeds)} seeds")
    for row in result["coordination_benefit"]:
        print(f"[benefit scale={row['global_replacement_scale']} vasc={row['shared_vascular_capacity']} imm={row['shared_immune_capacity']}] "
              f"healthspan_gain={row['healthspan_gain']:.1f} ttf_gain={row['ttf_gain']:.1f}")
    for key, path in paths.items():
        print(f"[{key}] {path}")


if __name__ == "__main__":
    main()
