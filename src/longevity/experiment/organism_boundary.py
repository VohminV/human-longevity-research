"""EXPERIMENT ENGINE LAYER: irreversibility boundary probe studies (Stage 6D).

Five config kinds (dispatched on the ``kind`` field), all sweeping
``boundary_params`` over a reversibility base config:

- ``conversion_ultra_sweep``: grid over ``conversion_scale``.
- ``independent_ultra_sweep``: grid over ``independent_accrual_scale``.
- ``ceiling_ultra_sweep``: grid over ``repair_ceiling_scale`` (+ optional
  unlimited-ceiling ablation point).
- ``component_attribution``: single-point detailed decomposition runs
  (default + key ablations) with contribution reports.
- ``heterogeneous_probe`` (Stage 6F): targeted attenuation of top
  bio-age drivers via the existing ``aging_drivers`` config layer
  (``base_aging_rate`` x driver_scale) plus matching per-driver
  ``component_overrides`` (conversion/independent x driver_scale).
  No model change, no new biology: ``driver_scale=1.0`` adds no
  override entries and reproduces the baseline trajectory exactly.

CLI::

    PYTHONPATH=src python -m longevity.experiment.organism_boundary \\
        --config experiments/configs/organism_reversibility_boundary_conversion_ultra_sweep.json \\
        --out-prefix experiments/output/organism_reversibility_boundary_conversion_ultra_sweep
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import itertools
import json
import math
import os
import platform
import time

from dataclasses import dataclass, field
from typing import Any

from longevity.analysis.boundary_metrics import (
    SUBSTANTIAL_BIO_SLOPE_REDUCTION,
    bio_age_source_ru,
    binding_constraint_ru,
    canonical_heterogeneous_driver,
    classify_residual_wall,
    classify_wall,
    confidence_ru,
    decompose_biological_age_slope,
    expand_heterogeneous_driver,
    exploratory_ru,
    hypothesis_ru,
    sensitivity_stable_ru,
    v5_operational_success_ru,
    validate_heterogeneous_driver_scale,
    wall_classification_ru,
    summarize_boundary_run,
)
from longevity.analysis.reversibility_metrics import (
    reversibility_binding,
    robust_bounded_degradation_v5,
    validate_v5_criteria,
)
from longevity.experiment.organism_runner import OrganismExperimentConfig, run_organism_experiment
from longevity.model.boundary import (
    BOUNDARY_SCOPE,
    validate_boundary_params,
)

BOUNDARY_EXPERIMENT_VERSION = "1.0"
MIN_BOUNDARY_SEEDS = 2

KIND_TO_PARAM = {
    "conversion_ultra_sweep": ("conversion_scale",),
    "independent_ultra_sweep": ("independent_accrual_scale",),
    "ceiling_ultra_sweep": ("repair_ceiling_scale",),
}


def _require_seeds(seeds: Any) -> tuple[int, ...]:
    if not isinstance(seeds, (list, tuple)) or len(seeds) == 0:
        raise ValueError("boundary seeds must be a non-empty list")
    cleaned = []
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError(f"boundary seed must be an int, got {seed!r}")
        cleaned.append(seed)
    if len(set(cleaned)) != len(cleaned):
        raise ValueError("boundary seeds must be unique")
    if len(cleaned) < MIN_BOUNDARY_SEEDS:
        raise ValueError(
            f"boundary studies need at least {MIN_BOUNDARY_SEEDS} seeds, got {len(cleaned)}")
    return tuple(cleaned)


def _require_boundary_base(base: dict[str, Any]) -> None:
    if not isinstance(base, dict) or not base:
        raise ValueError("base_organism_config must be a non-empty dict")
    if base.get("reversibility_model", "none") != "split_reversible_irreversible":
        raise ValueError("boundary studies require base_organism_config with "
                         "reversibility_model=split_reversible_irreversible")
    OrganismExperimentConfig.from_config_dict(copy.deepcopy(base))


def _mean(values: list[float]) -> float:
    finite = [v for v in values if math.isfinite(v)]
    if not finite:
        raise ValueError("cannot average empty/non-finite data")
    return sum(finite) / len(finite)


def _run_one(base: dict[str, Any], seed: int, overrides: dict[str, Any],
             criteria: dict[str, float]) -> dict[str, Any]:
    data = copy.deepcopy(base)
    data["seed"] = seed
    data.update(copy.deepcopy(overrides))
    # Boundary sweeps force the ablation layer on (neutral unless params differ).
    if data.get("boundary_probe_model", "none") == "none":
        data["boundary_probe_model"] = "irreversibility_ablation"
    experiment = OrganismExperimentConfig.from_config_dict(data)
    result = run_organism_experiment(experiment, out_path=None)
    summary = result["metrics"]["final"]
    binding = reversibility_binding(result["trajectory"], dict(criteria))
    boundary = summarize_boundary_run(result["trajectory"])
    from longevity.model.aging import validate_aging_drivers  # local: model-layer reuse

    driver_params = validate_aging_drivers(dict(data.get("aging_drivers", {}) or {}))
    bio_age_attribution = decompose_biological_age_slope(result["trajectory"], driver_params)
    return {"summary": summary, "binding": binding, "boundary": boundary,
            "bio_age_attribution": bio_age_attribution}


@dataclass(frozen=True)
class BoundarySweepConfig:
    kind: str = "conversion_ultra_sweep"
    experiment_id: str = ""
    seeds: tuple[int, ...] = ()
    param_axes: dict[str, list] = field(default_factory=dict)
    extra_boundary_params: dict[str, Any] = field(default_factory=dict)
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    v5_criteria: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.kind not in KIND_TO_PARAM:
            raise ValueError(f"boundary sweep kind must be one of {sorted(KIND_TO_PARAM)}, "
                             f"got {self.kind!r}")
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        allowed = set(KIND_TO_PARAM[self.kind])
        if not isinstance(self.param_axes, dict) or not self.param_axes:
            raise ValueError("param_axes must be a non-empty dict of param -> values")
        for param, values in self.param_axes.items():
            if param not in allowed:
                raise ValueError(f"param axis must be one of {sorted(allowed)}, got {param!r}")
            if not isinstance(values, list) or not values:
                raise ValueError(f"param_axes[{param!r}] must be a non-empty list")
            validate_boundary_params({param: v for v in values} if values else {})
        validate_boundary_params(dict(self.extra_boundary_params or {}))
        _require_boundary_base(copy.deepcopy(self.base_organism_config))
        validate_v5_criteria(dict(self.v5_criteria))

    def to_config_dict(self) -> dict[str, Any]:
        key = {"conversion_ultra_sweep": "conversion_axes",
               "independent_ultra_sweep": "independent_axes",
               "ceiling_ultra_sweep": "ceiling_axes"}[self.kind]
        return {
            "kind": self.kind,
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            key: copy.deepcopy(self.param_axes),
            "extra_boundary_params": copy.deepcopy(dict(self.extra_boundary_params)),
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "v5_criteria": copy.deepcopy(dict(self.v5_criteria)),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "BoundarySweepConfig":
        kind = data.get("kind", "")
        if kind not in KIND_TO_PARAM:
            raise ValueError(f"boundary sweep kind must be one of {sorted(KIND_TO_PARAM)}, "
                             f"got {kind!r}")
        key = {"conversion_ultra_sweep": "conversion_axes",
               "independent_ultra_sweep": "independent_axes",
               "ceiling_ultra_sweep": "ceiling_axes"}[kind]
        return cls(
            kind=kind,
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            param_axes=copy.deepcopy(data.get(key, {})),
            extra_boundary_params=copy.deepcopy(data.get("extra_boundary_params", {})),
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            v5_criteria=copy.deepcopy(data.get("v5_criteria", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class ComponentAttributionConfig:
    experiment_id: str = ""
    seeds: tuple[int, ...] = ()
    ablations: dict[str, Any] = field(default_factory=dict)
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    v5_criteria: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        if not isinstance(self.ablations, dict) or not self.ablations:
            raise ValueError("ablations must be a non-empty dict of name -> boundary_params")
        for name, params in self.ablations.items():
            validate_boundary_params(dict(params))
        _require_boundary_base(copy.deepcopy(self.base_organism_config))
        validate_v5_criteria(dict(self.v5_criteria))

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "kind": "component_attribution",
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            "ablations": copy.deepcopy(self.ablations),
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "v5_criteria": copy.deepcopy(dict(self.v5_criteria)),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "ComponentAttributionConfig":
        if data.get("kind", "") != "component_attribution":
            raise ValueError(f"component attribution kind mismatch, got {data.get('kind')!r}")
        return cls(
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            ablations=copy.deepcopy(data.get("ablations", {})),
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            v5_criteria=copy.deepcopy(data.get("v5_criteria", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


def _config_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


SLOPE_EPS_KEYS = ("eps_bio", "eps_bio_network", "eps_bio_rev", "eps_driver",
                  "eps_reversible", "eps_irreversible", "eps_information",
                  "eps_mutation", "eps_niche")


@dataclass(frozen=True)
class SensitivityConfig:
    experiment_id: str = ""
    seeds: tuple[int, ...] = ()
    eps_values: tuple[float, ...] = ()
    dts: tuple[float, ...] = ()
    ablations: dict[str, Any] = field(default_factory=dict)
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    v5_criteria: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        if not self.eps_values:
            raise ValueError("eps_values must be non-empty")
        for eps in self.eps_values:
            if isinstance(eps, bool) or not isinstance(eps, (int, float)) \
                    or not math.isfinite(float(eps)) or float(eps) < 0.0:
                raise ValueError(f"eps value must be finite and >= 0, got {eps!r}")
        if not self.dts:
            raise ValueError("dts must be non-empty")
        for dt in self.dts:
            if isinstance(dt, bool) or not isinstance(dt, (int, float)) \
                    or not math.isfinite(float(dt)) or float(dt) <= 0.0:
                raise ValueError(f"dt value must be finite and > 0, got {dt!r}")
        if not isinstance(self.ablations, dict) or not self.ablations:
            raise ValueError("ablations must be a non-empty dict of name -> boundary_params")
        for name, params in self.ablations.items():
            validate_boundary_params(dict(params))
        _require_boundary_base(copy.deepcopy(self.base_organism_config))
        validate_v5_criteria(dict(self.v5_criteria))

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "kind": "sensitivity",
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            "eps_values": list(self.eps_values),
            "dts": list(self.dts),
            "ablations": copy.deepcopy(self.ablations),
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "v5_criteria": copy.deepcopy(dict(self.v5_criteria)),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "SensitivityConfig":
        if data.get("kind", "") != "sensitivity":
            raise ValueError(f"sensitivity kind mismatch, got {data.get('kind')!r}")
        return cls(
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            eps_values=tuple(data.get("eps_values", ())),
            dts=tuple(data.get("dts", ())),
            ablations=copy.deepcopy(data.get("ablations", {})),
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            v5_criteria=copy.deepcopy(data.get("v5_criteria", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


def run_sensitivity(config: SensitivityConfig) -> dict[str, Any]:
    """Run dt x ablation x seed trajectories once; evaluate v5 per eps (pure re-eval)."""
    from longevity.analysis.boundary_metrics import (  # local: analysis reuse
        classify_compound_wall,
        compute_eps_sensitivity,
    )
    from longevity.analysis.reversibility_metrics import robust_bounded_degradation_v5

    wall_start = time.perf_counter()
    base_criteria = validate_v5_criteria(dict(config.v5_criteria))
    # Trajectories: one run per (dt, ablation, seed); eps needs no reruns.
    runs: dict[str, Any] = {}
    for dt in config.dts:
        for name in sorted(config.ablations):
            params = dict(config.ablations[name])
            for seed in config.seeds:
                key = f"{dt}|{name}|{seed}"
                runs[key] = _run_one(copy.deepcopy(config.base_organism_config), seed,
                                     {"boundary_params": params, "dt": float(dt)},
                                     dict(base_criteria))
                runs[key]["dt"] = float(dt)
                runs[key]["ablation"] = name
    cells: dict[str, Any] = {}
    for dt in config.dts:
        for eps in config.eps_values:
            criteria = dict(base_criteria)
            for skey in SLOPE_EPS_KEYS:
                criteria[skey] = float(eps)
            for name in sorted(config.ablations):
                summaries = [runs[f"{dt}|{name}|{seed}"]["summary"] for seed in config.seeds]
                v5 = robust_bounded_degradation_v5(summaries, criteria)
                seed_v5 = {str(seed): bool(robust_bounded_degradation_v5(
                    [runs[f"{dt}|{name}|{seed}"]["summary"]], criteria)
                    ["robust_bounded_degradation_v5"]) for seed in config.seeds}
                cells[f"{dt}|{eps}|{name}"] = {
                    "dt": float(dt), "eps": float(eps), "ablation": name,
                    "robust_v5": bool(v5["robust_bounded_degradation_v5"]),
                    "success_rate_v5": float(v5["success_rate_bounded_v5"]),
                    "seed_v5": seed_v5,
                    "seed_stable": len(set(seed_v5.values())) == 1,
                }
    # Stability: verdict identical across eps (per dt+ablation), across dts
    # (per eps+ablation), and across seeds (per cell).
    eps_stable = all(
        len({cells[f"{dt}|{eps}|{name}"]["robust_v5"] for eps in config.eps_values}) == 1
        for dt in config.dts for name in config.ablations)
    dt_stable = all(
        len({cells[f"{dt}|{eps}|{name}"]["robust_v5"] for dt in config.dts}) == 1
        for eps in config.eps_values for name in config.ablations)
    seed_stable = all(cell["seed_stable"] for cell in cells.values())
    # Reference cell for wall classification: dt=0.25 if present else first dt,
    # eps closest to the base criteria eps_bio.
    ref_dt = 0.25 if 0.25 in config.dts else config.dts[0]
    ref_eps = min(config.eps_values, key=lambda e: abs(float(e) - float(base_criteria["eps_bio"])))
    verdicts = {name: cells[f"{ref_dt}|{ref_eps}|{name}"]["robust_v5"]
                for name in sorted(config.ablations)}
    # Residual evidence: prefer a suppressed-yet-failing ablation (6E
    # Variant B); fall back to the reference default ablation.
    from longevity.analysis.boundary_metrics import select_suppressed_evidence  # local

    per_ablation: dict[str, dict[str, Any]] = {}
    for name in sorted(config.ablations):
        irr_slopes = [runs[f"{ref_dt}|{name}|{seed}"]["summary"]
                      .get("reversibility", {}).get("worst_irreversible_slope", 9e9)
                      for seed in config.seeds]
        firsts: dict[str, int] = {}
        n_src = 0
        for seed in config.seeds:
            row = runs[f"{ref_dt}|{name}|{seed}"]
            key = row["binding"]["first_reversibility_constraint_violated"]
            firsts[key] = firsts.get(key, 0) + 1
            n_src = max(n_src, int(row["bio_age_attribution"].get("n_significant_sources", 0)))
        per_ablation[name] = {
            "max_irr_slope": max(float(v) for v in irr_slopes),
            "v5": bool(cells[f"{ref_dt}|{ref_eps}|{name}"]["robust_v5"]),
            "binding": sorted(firsts, key=lambda k: (-firsts[k], k))[0],
            "n_sources": n_src,
        }
    suppressed_evidence = select_suppressed_evidence(
        per_ablation, float(base_criteria["eps_irreversible"]))
    irr_suppressed = bool(suppressed_evidence["irr_suppressed"])
    residual_binding = str(suppressed_evidence["residual_binding"])
    n_residual_sources = int(suppressed_evidence["n_residual_sources"])
    if not irr_suppressed:
        ref_names = sorted(config.ablations)
        ref_default = "default" if "default" in ref_names else ref_names[0]
        first_counts: dict[str, int] = {}
        for seed in config.seeds:
            row = runs[f"{ref_dt}|{ref_default}|{seed}"]
            key = row["binding"]["first_reversibility_constraint_violated"]
            first_counts[key] = first_counts.get(key, 0) + 1
        residual_binding = sorted(first_counts, key=lambda k: (-first_counts[k], k))[0]
        n_residual_sources = 0
        for seed in config.seeds:
            bio = runs[f"{ref_dt}|{ref_default}|{seed}"]["bio_age_attribution"]
            n_residual_sources = max(n_residual_sources, int(bio.get("n_significant_sources", 0)))
    knife_band = {}
    if "knife_edge_1e-4" in verdicts:
        knife_band = {0.0001: bool(verdicts["knife_edge_1e-4"])}
    compound_wall = classify_compound_wall(
        bool(verdicts.get("default", False)), verdicts, knife_band,
        irr_suppressed=irr_suppressed, residual_binding=residual_binding,
        n_residual_sources=n_residual_sources,
        stability={"data_complete": True, "seed_stable": bool(seed_stable),
                   "eps_stable": bool(eps_stable), "dt_stable": bool(dt_stable)},
        exploratory_only=False)
    # Per-ablation eps-sensitivity detail (reuses pure helper on cached summaries).
    eps_detail = {}
    for dt in config.dts:
        for name in sorted(config.ablations):
            summaries = [runs[f"{dt}|{name}|{seed}"]["summary"] for seed in config.seeds]
            eps_detail[f"{dt}|{name}"] = compute_eps_sensitivity(
                summaries, [float(e) for e in config.eps_values], dict(base_criteria))
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "kind": "sensitivity",
        "experiment_id": config.experiment_id,
        "format": BOUNDARY_EXPERIMENT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": _config_hash(config.to_config_dict()),
        "model_scope": BOUNDARY_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "candidate_robust_bounded_degradation_v5_found": any(
            cell["robust_v5"] for cell in cells.values()),
        "reference_dt": float(ref_dt),
        "reference_eps": float(ref_eps),
        "eps_stable": bool(eps_stable),
        "dt_stable": bool(dt_stable),
        "seed_stable": bool(seed_stable),
        "verdicts_at_reference": verdicts,
        "compound_wall": compound_wall,
        "cells": cells,
        "eps_detail": eps_detail,
        "seeds": list(config.seeds),
        "runtime": {"engine": "organism-boundary/v0", "python": platform.python_version(),
                    "platform": platform.platform(), "wall_seconds": wall_seconds},
    }


def run_boundary_sweep(config: BoundarySweepConfig) -> dict[str, Any]:
    wall_start = time.perf_counter()
    criteria = validate_v5_criteria(dict(config.v5_criteria))
    axes = sorted(config.param_axes)
    points: list[dict[str, Any]] = []
    for values in itertools.product(*[config.param_axes[axis] for axis in axes]):
        combo = dict(zip(axes, values))
        seed_rows: dict[str, Any] = {}
        for seed in config.seeds:
            params = dict(config.extra_boundary_params)
            params.update(combo)
            seed_rows[str(seed)] = _run_one(copy.deepcopy(config.base_organism_config), seed,
                                            {"boundary_params": params}, criteria)
        summaries = [row["summary"] for row in seed_rows.values()]
        from longevity.analysis.reversibility_metrics import robust_bounded_degradation_v5

        v5 = robust_bounded_degradation_v5(summaries, dict(criteria))
        binding_votes: dict[str, int] = {}
        source_votes: dict[str, int] = {}
        for row in seed_rows.values():
            binding = row["binding"]["first_reversibility_constraint_violated"]
            binding_votes[binding] = binding_votes.get(binding, 0) + 1
            source = row["boundary"]["attribution"]["dominant_irreversibility_source"]
            source_votes[source] = source_votes.get(source, 0) + 1
        points.append({
            "combo": combo,
            "n_seeds": len(config.seeds),
            "mean_lifespan": _mean([r["summary"]["lifespan"] for r in seed_rows.values()]),
            "mean_healthspan": _mean([r["summary"]["healthspan"] for r in seed_rows.values()]),
            "mean_irreversible_slope": _mean([
                r["summary"].get("reversibility", {}).get("worst_irreversible_slope", 0.0)
                for r in seed_rows.values()]),
            "robust_v5": v5["robust_bounded_degradation_v5"],
            "success_rate_v5": v5["success_rate_bounded_v5"],
            "binding_votes": binding_votes,
            "source_votes": source_votes,
            "seeds": seed_rows,
        })
    # Threshold: first combo (ascending by first axis) where v5 turns true.
    first_axis = axes[0]
    ordered = sorted(points, key=lambda p: p["combo"][first_axis])
    threshold = next((p["combo"][first_axis] for p in ordered if p["robust_v5"]), None)
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "kind": config.kind,
        "experiment_id": config.experiment_id,
        "format": BOUNDARY_EXPERIMENT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": _config_hash(config.to_config_dict()),
        "model_scope": BOUNDARY_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "candidate_robust_bounded_degradation_v5_found": any(p["robust_v5"] for p in points),
        "v5_threshold": threshold,
        "seeds": list(config.seeds),
        "points": points,
        "runtime": {"engine": "organism-boundary/v0", "python": platform.python_version(),
                    "platform": platform.platform(), "wall_seconds": wall_seconds},
    }


def run_component_attribution(config: ComponentAttributionConfig) -> dict[str, Any]:
    wall_start = time.perf_counter()
    criteria = validate_v5_criteria(dict(config.v5_criteria))
    entries: dict[str, Any] = {}
    for name in sorted(config.ablations):
        params = dict(config.ablations[name])
        seed_rows: dict[str, Any] = {}
        for seed in config.seeds:
            seed_rows[str(seed)] = _run_one(copy.deepcopy(config.base_organism_config), seed,
                                            {"boundary_params": params}, criteria)
        summaries = [row["summary"] for row in seed_rows.values()]
        from longevity.analysis.reversibility_metrics import robust_bounded_degradation_v5

        v5 = robust_bounded_degradation_v5(summaries, dict(criteria))
        seed_v5 = {str(seed): bool(robust_bounded_degradation_v5(
            [row["summary"]], dict(criteria))["robust_bounded_degradation_v5"])
            for seed, row in seed_rows.items()}
        entries[name] = {
            "n_seeds": len(config.seeds),
            "mean_lifespan": _mean([r["summary"]["lifespan"] for r in seed_rows.values()]),
            "mean_irreversible_slope": _mean([
                r["summary"].get("reversibility", {}).get("worst_irreversible_slope", 0.0)
                for r in seed_rows.values()]),
            "robust_v5": v5["robust_bounded_degradation_v5"],
            "seed_v5": seed_v5,
            "seed_stable": len(set(seed_v5.values())) == 1,
            "bio_age_attribution": {
                str(seed): row["bio_age_attribution"] for seed, row in seed_rows.items()},
            "dominant_components": {
                str(seed): row["boundary"]["contributions"].get(
                    "dominant_irreversibility_component", "none")
                for seed, row in seed_rows.items()},
            "dominant_sources": {
                str(seed): row["boundary"]["attribution"].get(
                    "dominant_irreversibility_source", "none")
                for seed, row in seed_rows.items()},
            "seeds": seed_rows,
        }
    # Wall classification across ablations.
    verdicts = {
        "conversion_zero": entries.get("conversion_zero", {}).get("robust_v5", False),
        "independent_zero": entries.get("independent_zero", {}).get("robust_v5", False),
        "both_suppressed": entries.get("both_suppressed", {}).get("robust_v5", False),
        "high_ceiling": entries.get("high_ceiling", {}).get("robust_v5", False),
        "unlimited_ceiling": entries.get("unlimited_ceiling", {}).get("robust_v5", False),
    }
    default_entry = entries.get("default", {})
    default_sources: dict[str, int] = {}
    for seed_row in default_entry.get("seeds", {}).values():
        src = seed_row["boundary"]["attribution"]["dominant_irreversibility_source"]
        default_sources[src] = default_sources.get(src, 0) + 1
    dominant_source = sorted(default_sources,
                             key=lambda k: (-default_sources[k], k))[0] if default_sources else "none"
    classification = classify_wall(
        any(entries[n].get("robust_v5", False) for n in ("default",) if n in entries),
        verdicts, dominant_source)
    from longevity.analysis.boundary_metrics import (  # local: analysis reuse
        classify_compound_wall,
        select_suppressed_evidence,
    )

    default_bio_sources: dict[str, int] = {}
    per_ablation: dict[str, dict[str, Any]] = {}
    for aname, entry in entries.items():
        firsts: dict[str, int] = {}
        n_src = 0
        irr_slopes = []
        for seed_row in entry.get("seeds", {}).values():
            key = seed_row["binding"]["first_reversibility_constraint_violated"]
            firsts[key] = firsts.get(key, 0) + 1
            bio = seed_row["bio_age_attribution"]
            if aname == "default":
                bsrc = bio.get("dominant_source", "none")
                default_bio_sources[bsrc] = default_bio_sources.get(bsrc, 0) + 1
            n_src = max(n_src, int(bio.get("n_significant_sources", 0)))
            irr_slopes.append(float(seed_row["summary"].get("reversibility", {})
                                    .get("worst_irreversible_slope", 9e9)))
        per_ablation[aname] = {
            "max_irr_slope": max(irr_slopes) if irr_slopes else 9e9,
            "v5": bool(entry.get("robust_v5", False)),
            "binding": sorted(firsts, key=lambda k: (-firsts[k], k))[0] if firsts else "none",
            "n_sources": n_src,
        }
    suppressed_evidence = select_suppressed_evidence(
        per_ablation, float(criteria["eps_irreversible"]))
    irr_suppressed = bool(suppressed_evidence["irr_suppressed"])
    residual_binding = str(suppressed_evidence["residual_binding"])
    n_bio_sources = int(suppressed_evidence["n_residual_sources"])
    if not irr_suppressed:
        residual_binding = next(
            (seed_row["binding"]["first_reversibility_constraint_violated"]
             for seed_row in default_entry.get("seeds", {}).values()),
            "none")
        n_bio_sources = 0
        for seed_row in default_entry.get("seeds", {}).values():
            n_bio_sources = max(n_bio_sources, int(
                seed_row["bio_age_attribution"].get("n_significant_sources", 0)))
    compound_wall = classify_compound_wall(
        bool(default_entry.get("robust_v5", False)), verdicts,
        {0.0001: bool(entries["knife_edge_1e-4"]["robust_v5"])}
        if "knife_edge_1e-4" in entries else {},
        irr_suppressed=irr_suppressed,
        residual_binding=residual_binding,
        n_residual_sources=n_bio_sources,
        stability={"data_complete": True,
                   "seed_stable": all(e.get("seed_stable", False) for e in entries.values()),
                   "eps_stable": True, "dt_stable": True},
        exploratory_only=False)
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    return {
        "kind": "component_attribution",
        "experiment_id": config.experiment_id,
        "format": BOUNDARY_EXPERIMENT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": _config_hash(config.to_config_dict()),
        "model_scope": BOUNDARY_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "candidate_robust_bounded_degradation_v5_found": any(
            e["robust_v5"] for e in entries.values()),
        "verdicts": verdicts,
        "wall_classification": classification,
        "compound_wall": compound_wall,
        "seeds": list(config.seeds),
        "entries": entries,
        "runtime": {"engine": "organism-boundary/v0", "python": platform.python_version(),
                    "platform": platform.platform(), "wall_seconds": wall_seconds},
    }


def _require_heterogeneous_drivers(drivers: Any) -> tuple[dict[str, Any], ...]:
    """Validate the heterogeneous driver table (pure, 6F).

    Returns canonical ``({"name": canonical, "scales": [...]}, ...)`` in
    config order. Rejects unknown names, empty/duplicate tables,
    non-numeric or negative scales, and overlapping member coverage.
    """
    if not isinstance(drivers, (list, tuple)) or not drivers:
        raise ValueError("heterogeneous drivers must be a non-empty list")
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, entry in enumerate(drivers):
        if not isinstance(entry, dict):
            raise ValueError(f"drivers[{i}] must be a dict, got {entry!r}")
        canonical = canonical_heterogeneous_driver(entry.get("name", ""))
        if canonical in seen:
            raise ValueError(f"duplicate heterogeneous driver {canonical!r}")
        seen.add(canonical)
        scales = entry.get("scales", None)
        if not isinstance(scales, (list, tuple)) or not scales:
            raise ValueError(f"drivers[{i}].scales must be a non-empty list")
        validated_scales = [validate_heterogeneous_driver_scale(
            s, f"drivers[{i}].scales") for s in scales]
        if len(set(validated_scales)) != len(validated_scales):
            raise ValueError(f"drivers[{i}].scales must be unique")
        cleaned.append({"name": canonical, "scales": validated_scales})
    covered: set[str] = set()
    for entry in cleaned:
        for member in expand_heterogeneous_driver(entry["name"]):
            if member in covered:
                raise ValueError(
                    f"heterogeneous driver {entry['name']!r} overlaps another driver "
                    f"on member {member!r}; targets must be disjoint")
            covered.add(member)
    return tuple(cleaned)


def _require_heterogeneous_combinations(combinations: Any) -> tuple[Any, ...]:
    """Validate combo targets (pure, 6F).

    Each entry is ``"all_significant"`` or a non-empty list of known
    driver names (canonicalized, order preserved, no duplicates).
    An empty list is allowed (singles-only probe).
    """
    if combinations is None:
        return ()
    if not isinstance(combinations, (list, tuple)):
        raise ValueError(f"combinations must be a list, got {combinations!r}")
    cleaned: list[Any] = []
    for i, entry in enumerate(combinations):
        if entry == "all_significant":
            cleaned.append("all_significant")
            continue
        if not isinstance(entry, (list, tuple)) or not entry:
            raise ValueError(f"combinations[{i}] must be a non-empty driver list "
                             f"or 'all_significant', got {entry!r}")
        names = [canonical_heterogeneous_driver(n) for n in entry]
        if len(set(names)) != len(names):
            raise ValueError(f"combinations[{i}] has duplicate drivers")
        cleaned.append(tuple(names))
    return tuple(cleaned)


def _require_combination_scales(scales: Any) -> tuple[float, ...]:
    if scales is None:
        return (0.0,)
    if not isinstance(scales, (list, tuple)) or not scales:
        raise ValueError("combination_scales must be a non-empty list")
    validated = [validate_heterogeneous_driver_scale(s, "combination_scales")
                 for s in scales]
    if len(set(validated)) != len(validated):
        raise ValueError("combination_scales must be unique")
    return tuple(validated)


def heterogeneous_regimes(drivers: tuple[dict[str, Any], ...],
                          combinations: tuple[Any, ...],
                          combination_scales: tuple[float, ...]) -> list[dict[str, Any]]:
    """Deterministic regime table for a heterogeneous probe (pure, 6F).

    ``control`` first (no scaling), then per-driver singles in config
    order, then combos in config order. ``driver_scales`` maps each
    mechanistic member driver to its attenuation scale.
    """
    regimes: list[dict[str, Any]] = [{"name": "control", "kind": "control",
                                     "targets": (), "driver_scales": {}}]
    seen_names = {"control"}
    all_canonical = [entry["name"] for entry in drivers]

    def _add(name: str, kind: str, targets: tuple[str, ...],
             member_scales: dict[str, float]) -> None:
        if name in seen_names:
            raise ValueError(f"duplicate heterogeneous regime {name!r}")
        seen_names.add(name)
        regimes.append({"name": name, "kind": kind, "targets": targets,
                        "driver_scales": dict(member_scales)})

    for entry in drivers:
        for scale in entry["scales"]:
            members = expand_heterogeneous_driver(entry["name"])
            _add(f"driver:{entry['name']}@{scale:g}", "single", (entry["name"],),
                 {m: scale for m in members})
    for combo in combinations:
        if combo == "all_significant":
            members: dict[str, None] = {}
            for canonical in all_canonical:
                for member in expand_heterogeneous_driver(canonical):
                    members[member] = None
            combo_name, targets = "all_significant", tuple(all_canonical)
            member_list = list(members)
        else:
            member_list = []
            for canonical in combo:
                for member in expand_heterogeneous_driver(canonical):
                    if member not in member_list:
                        member_list.append(member)
            combo_name, targets = "+".join(combo), tuple(combo)
        for scale in combination_scales:
            _add(f"combo:{combo_name}@{scale:g}", "combo", targets,
                 {m: scale for m in member_list})
    return regimes


def _majority(votes: dict[str, int]) -> str:
    if not votes:
        return "none"
    return sorted(votes, key=lambda k: (-votes[k], k))[0]


@dataclass(frozen=True)
class HeterogeneousProbeConfig:
    kind: str = "heterogeneous_probe"
    experiment_id: str = ""
    seeds: tuple[int, ...] = ()
    drivers: tuple[dict[str, Any], ...] = ()
    combination_scales: tuple[float, ...] = (0.0,)
    combinations: tuple[Any, ...] = ()
    base_organism_config: dict[str, Any] = field(default_factory=dict)
    v5_criteria: dict[str, Any] = field(default_factory=dict)
    output_prefix: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        if self.kind != "heterogeneous_probe":
            raise ValueError(f"heterogeneous probe kind mismatch, got {self.kind!r}")
        if not self.experiment_id:
            raise ValueError("experiment_id must be non-empty")
        _require_seeds(list(self.seeds))
        _require_heterogeneous_drivers(list(self.drivers))
        _require_heterogeneous_combinations(
            list(self.combinations) if self.combinations else [])
        _require_combination_scales(list(self.combination_scales))
        _require_boundary_base(copy.deepcopy(self.base_organism_config))
        validate_v5_criteria(dict(self.v5_criteria))

    def to_config_dict(self) -> dict[str, Any]:
        return {
            "kind": "heterogeneous_probe",
            "experiment_id": self.experiment_id,
            "seeds": list(self.seeds),
            "drivers": [{"name": e["name"], "scales": list(e["scales"])}
                        for e in self.drivers],
            "combination_scales": list(self.combination_scales),
            "combinations": [list(c) if isinstance(c, tuple) else c
                             for c in self.combinations],
            "base_organism_config": copy.deepcopy(self.base_organism_config),
            "v5_criteria": copy.deepcopy(dict(self.v5_criteria)),
            "output_prefix": self.output_prefix,
            "notes": self.notes,
        }

    @classmethod
    def from_config_dict(cls, data: dict[str, Any]) -> "HeterogeneousProbeConfig":
        if data.get("kind", "") != "heterogeneous_probe":
            raise ValueError(f"heterogeneous probe kind mismatch, got {data.get('kind')!r}")
        drivers = _require_heterogeneous_drivers(data.get("drivers", []))
        return cls(
            kind="heterogeneous_probe",
            experiment_id=data["experiment_id"],
            seeds=tuple(data.get("seeds", ())),
            drivers=drivers,
            combination_scales=_require_combination_scales(
                data.get("combination_scales", [0.0])),
            combinations=_require_heterogeneous_combinations(
                data.get("combinations", [])),
            base_organism_config=copy.deepcopy(data.get("base_organism_config", {})),
            v5_criteria=copy.deepcopy(data.get("v5_criteria", {})),
            output_prefix=data.get("output_prefix", ""),
            notes=data.get("notes", ""),
        )


def _run_hetero_one(base: dict[str, Any], seed: int,
                    driver_scales: dict[str, float],
                    criteria: dict[str, float]) -> dict[str, Any]:
    """One heterogeneous regime x seed run (Stage 6F, no model change).

    Attenuation reuses two existing layers: per-member
    ``base_aging_rate`` scaling in the ``aging_drivers`` config plus
    matching driver-type ``component_overrides``
    (conversion/independent x scale). ``scale == 1.0`` members add no
    entries, so the control trajectory is bit-identical to the
    unmodified base. Never mutates ``base`` or ``driver_scales``.
    """
    from longevity.model.aging import validate_aging_drivers  # local: model-layer reuse

    data = copy.deepcopy(base)
    data["seed"] = seed
    if data.get("boundary_probe_model", "none") == "none":
        data["boundary_probe_model"] = "irreversibility_ablation"
    if driver_scales:
        validated_rates = validate_aging_drivers(
            copy.deepcopy(data.get("aging_drivers", {}) or {}))
        aging = copy.deepcopy(data.get("aging_drivers", {}) or {})
        for member in sorted(driver_scales):
            scale = driver_scales[member]
            if member not in validated_rates:
                raise ValueError(f"heterogeneous member {member!r} is not a known driver")
            if scale == 1.0:
                continue
            entry = dict(aging.get(member, {}))
            entry["base_aging_rate"] = float(validated_rates[member]["base_aging_rate"]) \
                * float(scale)
            aging[member] = entry
        data["aging_drivers"] = aging
        existing = list(data.get("component_overrides", []) or [])
        for item in existing:
            if item.get("component_type") == "driver" \
                    and item.get("component_id") in driver_scales \
                    and item.get("enabled", True):
                raise ValueError(
                    f"base config already overrides driver {item.get('component_id')!r}; "
                    "heterogeneous probe refuses to guess a merge")
        overrides = [dict(item) for item in existing]
        for member in sorted(driver_scales):
            scale = float(driver_scales[member])
            if scale == 1.0:
                continue
            overrides.append({"component_id": member, "component_type": "driver",
                              "conversion_rate_override": scale,
                              "independent_accrual_override": scale})
        data["component_overrides"] = overrides
    experiment = OrganismExperimentConfig.from_config_dict(data)
    result = run_organism_experiment(experiment, out_path=None)
    summary = result["metrics"]["final"]
    binding = reversibility_binding(result["trajectory"], dict(criteria))
    boundary = summarize_boundary_run(result["trajectory"])
    driver_params = validate_aging_drivers(dict(data.get("aging_drivers", {}) or {}))
    bio_age_attribution = decompose_biological_age_slope(result["trajectory"], driver_params)
    return {"summary": summary, "binding": binding, "boundary": boundary,
            "bio_age_attribution": bio_age_attribution}


def run_heterogeneous_probe(config: HeterogeneousProbeConfig) -> dict[str, Any]:
    """Run control + targeted driver attenuations + combos (Stage 6F)."""
    from longevity.analysis.reversibility_metrics import robust_bounded_degradation_v5

    wall_start = time.perf_counter()
    criteria = validate_v5_criteria(dict(config.v5_criteria))
    regimes = heterogeneous_regimes(tuple(config.drivers), tuple(config.combinations),
                                    tuple(config.combination_scales))
    entries: dict[str, Any] = {}
    for regime in regimes:
        seed_rows: dict[str, Any] = {}
        for seed in config.seeds:
            seed_rows[str(seed)] = _run_hetero_one(
                copy.deepcopy(config.base_organism_config), seed,
                dict(regime["driver_scales"]), dict(criteria))
        summaries = [row["summary"] for row in seed_rows.values()]
        v5 = robust_bounded_degradation_v5(summaries, dict(criteria))
        seed_v5 = {str(seed): bool(robust_bounded_degradation_v5(
            [row["summary"]], dict(criteria))["robust_bounded_degradation_v5"])
            for seed, row in seed_rows.items()}
        binding_votes: dict[str, int] = {}
        source_votes: dict[str, int] = {}
        bio_comp_votes: dict[str, int] = {}
        bio_source_votes: dict[str, int] = {}
        bio_totals: list[float] = []
        bio_slopes: list[float] = []
        irr_slopes: list[float] = []
        exploratory = False
        for row in seed_rows.values():
            binding = row["binding"]["first_reversibility_constraint_violated"]
            binding_votes[binding] = binding_votes.get(binding, 0) + 1
            source = row["boundary"]["attribution"]["dominant_irreversibility_source"]
            source_votes[source] = source_votes.get(source, 0) + 1
            bio = row["bio_age_attribution"]
            bio_comp_votes[bio.get("dominant_component", "none")] = \
                bio_comp_votes.get(bio.get("dominant_component", "none"), 0) + 1
            bio_source_votes[bio.get("dominant_source", "none")] = \
                bio_source_votes.get(bio.get("dominant_source", "none"), 0) + 1
            bio_totals.append(float(bio.get("total_slope", 0.0)))
            bio_slopes.append(float(row["summary"].get(
                "biological_age_slope_after_adulthood", 0.0)))
            irr_slopes.append(float(row["summary"].get("reversibility", {})
                                    .get("worst_irreversible_slope", 0.0)))
            exploratory = exploratory or bool(
                row["boundary"]["boundary"].get("exploratory", False))
        for values in (bio_totals, bio_slopes, irr_slopes):
            if not all(math.isfinite(v) for v in values):
                raise ValueError("non-finite heterogeneous probe output")
        binding_majority = _majority(binding_votes)
        bio_source_majority = _majority(bio_source_votes)
        wall = classify_wall(bool(v5["robust_bounded_degradation_v5"]), {},
                             dominant_source=_majority(source_votes))
        entries[regime["name"]] = {
            "kind": regime["kind"],
            "targets": list(regime["targets"]),
            "driver_scales": dict(regime["driver_scales"]),
            "n_seeds": len(config.seeds),
            "robust_v5": bool(v5["robust_bounded_degradation_v5"]),
            "v5_operational_success_ru": v5_operational_success_ru(
                bool(v5["robust_bounded_degradation_v5"])),
            "seed_v5": seed_v5,
            "seed_stable": len(set(seed_v5.values())) == 1,
            "seed_stable_ru": sensitivity_stable_ru(len(set(seed_v5.values())) == 1,
                                                   len(set(seed_v5.values())) == 1),
            "mean_bio_age_slope": _mean(bio_slopes),
            "mean_bio_attribution_total_slope": _mean(bio_totals),
            "mean_irreversible_slope": _mean(irr_slopes),
            "binding_majority": binding_majority,
            "binding_majority_ru": binding_constraint_ru(binding_majority),
            "binding_votes": binding_votes,
            "dominant_bio_component_majority": _majority(bio_comp_votes),
            "dominant_bio_source_majority": bio_source_majority,
            "dominant_bio_source_majority_ru": bio_age_source_ru(bio_source_majority),
            "bio_source_votes": bio_source_votes,
            "dominant_attribution_source_majority": _majority(source_votes),
            "attribution_source_votes": source_votes,
            "wall_classification": wall["wall_classification"],
            "wall_classification_ru": wall_classification_ru(
                wall["wall_classification"]),
            "exploratory": bool(exploratory),
            "exploratory_ru": exploratory_ru(bool(exploratory)),
            "bio_age_attribution": {str(seed): row["bio_age_attribution"]
                                    for seed, row in seed_rows.items()},
            "seeds": seed_rows,
        }
    control = entries["control"]
    control_bio = float(control["mean_bio_attribution_total_slope"])
    suppressed_names = [name for name, entry in entries.items()
                        if name != "control"
                        and any(s != 1.0 for s in entry["driver_scales"].values())]
    for name in suppressed_names:
        entry = entries[name]
        regime_bio = float(entry["mean_bio_attribution_total_slope"])
        reduction = ((control_bio - regime_bio) / abs(control_bio)
                     if abs(control_bio) > 1e-12 else 0.0)
        entry["bio_reduction_vs_control"] = float(reduction)
        binding_changed = entry["binding_majority"] != control["binding_majority"]
        source_flip = entry["dominant_bio_source_majority"] != \
            control["dominant_bio_source_majority"]
        entry["binding_changed_vs_control"] = bool(binding_changed)
        entry["source_flip_vs_control"] = bool(source_flip)
        if binding_changed or source_flip:
            entry["diagnostic_transition_note"] = (
                f"после подавления {name} связывающим становится "
                f"{entry['binding_majority']} (было {control['binding_majority']}), "
                f"доминирующим bio-age источником становится "
                f"{entry['dominant_bio_source_majority']} (был "
                f"{control['dominant_bio_source_majority']}); "
                "это диагностический переход источника остаточной деградации, "
                "а не биологическая смена причины")
        else:
            entry["diagnostic_transition_note"] = ""
    for name, entry in entries.items():
        if name == "control":
            entry["bio_reduction_vs_control"] = 0.0
            entry["binding_changed_vs_control"] = False
            entry["source_flip_vs_control"] = False
            entry["diagnostic_transition_note"] = "контроль (без подавления)"
            continue
        if name in suppressed_names:
            continue
        entry["bio_reduction_vs_control"] = 0.0
        entry["binding_changed_vs_control"] = False
        entry["source_flip_vs_control"] = False
        entry["diagnostic_transition_note"] = "эквивалентный контроль (масштаб 1.0)"
    singles = [entries[n] for n in suppressed_names if entries[n]["kind"] == "single"]
    substantial_single = any(
        e["bio_reduction_vs_control"] >= SUBSTANTIAL_BIO_SLOPE_REDUCTION
        or e["binding_changed_vs_control"] for e in singles)
    flip = any(entries[n]["binding_changed_vs_control"]
               or entries[n]["source_flip_vs_control"] for n in suppressed_names)
    v5_any = any(e["robust_v5"] for e in entries.values())
    v5_non_exploratory = any(e["robust_v5"] and not e["exploratory"]
                             for e in entries.values())
    seed_stable_all = all(e["seed_stable"] for e in entries.values())
    residual = classify_residual_wall(
        v5_robust_non_exploratory=bool(v5_non_exploratory),
        v5_narrow_only=bool(v5_any and not v5_non_exploratory),
        substantial_single_driver_effect=bool(substantial_single),
        binding_or_source_flip=bool(flip),
        n_drivers_tested=len(config.drivers),
        stability={"data_complete": True, "seed_stable": bool(seed_stable_all)})
    stage_6f = {
        **residual,
        "stage_6f_residual_classification_ru": wall_classification_ru(
            residual["stage_6f_residual_classification"]),
        "confidence_ru": confidence_ru(residual["confidence"]),
        "substantial_bio_slope_reduction_threshold":
            float(SUBSTANTIAL_BIO_SLOPE_REDUCTION),
        "evidence": {
            "n_drivers_tested": len(config.drivers),
            "n_regimes": len(entries),
            "v5_any_regime": bool(v5_any),
            "v5_robust_non_exploratory": bool(v5_non_exploratory),
            "substantial_single_driver_effect": bool(substantial_single),
            "binding_or_source_flip": bool(flip),
            "seed_stable_all_regimes": bool(seed_stable_all),
            "control_binding": control["binding_majority"],
            "control_binding_ru": control["binding_majority_ru"],
            "control_dominant_bio_source": control["dominant_bio_source_majority"],
            "control_dominant_bio_source_ru":
                control["dominant_bio_source_majority_ru"],
        },
        "seed_stable_ru": sensitivity_stable_ru(bool(seed_stable_all),
                                               bool(seed_stable_all)),
        "attribution_proxy_note": ("Attribution shares являются операционными "
                                   "диагностическими прокси, не законами сохранения."),
    }
    wall_seconds = round(time.perf_counter() - wall_start, 4)
    candidate_found = bool(v5_non_exploratory)
    return {
        "kind": "heterogeneous_probe",
        "experiment_id": config.experiment_id,
        "format": BOUNDARY_EXPERIMENT_VERSION,
        "config": config.to_config_dict(),
        "config_hash": _config_hash(config.to_config_dict()),
        "model_scope": BOUNDARY_SCOPE,
        "immortality_status": "hypothesis_not_proven",
        "immortality_status_ru": hypothesis_ru("hypothesis_not_proven"),
        "candidate_robust_bounded_degradation_v5_found": candidate_found,
        "candidate_ru": hypothesis_ru(
            "candidate_found" if candidate_found else "candidate_not_found"),
        "control": control["binding_majority"],
        "seed_stable_all_regimes": bool(seed_stable_all),
        "stage_6f": stage_6f,
        "seeds": list(config.seeds),
        "entries": entries,
        "runtime": {"engine": "organism-boundary/v0", "python": platform.python_version(),
                    "platform": platform.platform(), "wall_seconds": wall_seconds},
    }


def _round6(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, list):
        return [_round6(v) for v in value]
    if isinstance(value, dict):
        return {k: _round6(v) for k, v in value.items()}
    return value


def write_sweep_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    long_path = f"{out_prefix}_long.csv"
    summary_path = f"{out_prefix}_summary.csv"
    summary_json_path = f"{out_prefix}_summary.json"
    report_path = f"{out_prefix}_report.json"
    with open(long_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["combo", "seed", "lifespan", "healthspan",
                                                "primary_cause_of_death",
                                                "first_reversibility_constraint",
                                                "dominant_source",
                                                "worst_irreversible_slope"])
        writer.writeheader()
        for point in result["points"]:
            for seed in result["seeds"]:
                row = point["seeds"][str(seed)]
                writer.writerow({
                    "combo": json.dumps(point["combo"], sort_keys=True), "seed": seed,
                    "lifespan": _round6(row["summary"]["lifespan"]),
                    "healthspan": _round6(row["summary"]["healthspan"]),
                    "primary_cause_of_death": row["summary"]["primary_cause_of_death"],
                    "first_reversibility_constraint":
                        row["binding"]["first_reversibility_constraint_violated"],
                    "dominant_source":
                        row["boundary"]["attribution"]["dominant_irreversibility_source"],
                    "worst_irreversible_slope": _round6(row["summary"].get("reversibility", {})
                                                        .get("worst_irreversible_slope", 0.0)),
                })
    with open(summary_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["combo", "n_seeds", "mean_lifespan", "mean_healthspan",
                                                "mean_irreversible_slope", "robust_v5",
                                                "binding_votes", "source_votes"])
        writer.writeheader()
        for point in result["points"]:
            writer.writerow({
                "combo": json.dumps(point["combo"], sort_keys=True), "n_seeds": point["n_seeds"],
                "mean_lifespan": _round6(point["mean_lifespan"]),
                "mean_healthspan": _round6(point["mean_healthspan"]),
                "mean_irreversible_slope": _round6(point["mean_irreversible_slope"]),
                "robust_v5": point["robust_v5"],
                "binding_votes": json.dumps(point["binding_votes"], sort_keys=True),
                "source_votes": json.dumps(point["source_votes"], sort_keys=True),
            })
    payload = _round6(result)
    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "model_scope": result["model_scope"],
                   "immortality_status": result["immortality_status"],
                   "candidate_robust_bounded_degradation_v5_found":
                       result["candidate_robust_bounded_degradation_v5_found"],
                   "v5_threshold": result.get("v5_threshold")}, fh, ensure_ascii=False,
                  indent=2, allow_nan=False)
    for value in [p["mean_lifespan"] for p in result["points"]]:
        if not math.isfinite(float(value)):
            raise ValueError("non-finite boundary output")
    return {"long_csv": long_path, "summary_csv": summary_path, "summary_json": summary_json_path,
            "report_json": report_path}


def write_attribution_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    summary_json_path = f"{out_prefix}_summary.json"
    attribution_path = f"{out_prefix}_component_attribution.json"
    wall_path = f"{out_prefix}_wall_classification.json"
    payload = _round6(result)
    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(attribution_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "entries": {name: {
                       "mean_lifespan": _round6(e["mean_lifespan"]),
                       "mean_irreversible_slope": _round6(e["mean_irreversible_slope"]),
                       "robust_v5": e["robust_v5"],
                       "dominant_components": e["dominant_components"],
                       "dominant_sources": e["dominant_sources"]}
                       for name, e in result["entries"].items()}},
                  fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(wall_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "model_scope": result["model_scope"],
                   "immortality_status": result["immortality_status"],
                   "verdicts": result["verdicts"],
                   "wall_classification": result["wall_classification"],
                   "compound_wall": result.get("compound_wall", {})},
                  fh, ensure_ascii=False, indent=2, allow_nan=False)
    return {"summary_json": summary_json_path, "component_attribution_json": attribution_path,
            "wall_classification_json": wall_path}


def write_sensitivity_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    long_path = f"{out_prefix}_long.csv"
    summary_path = f"{out_prefix}_summary.csv"
    summary_json_path = f"{out_prefix}_summary.json"
    sensitivity_path = f"{out_prefix}_sensitivity.json"
    with open(long_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["dt", "eps", "ablation", "robust_v5",
                                                "success_rate_v5", "seed_v5"])
        writer.writeheader()
        for key in sorted(result["cells"]):
            cell = result["cells"][key]
            writer.writerow({
                "dt": cell["dt"], "eps": cell["eps"], "ablation": cell["ablation"],
                "robust_v5": cell["robust_v5"],
                "success_rate_v5": _round6(cell["success_rate_v5"]),
                "seed_v5": json.dumps(cell["seed_v5"], sort_keys=True),
            })
    with open(summary_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["dt", "eps", "ablation", "robust_v5",
                                                "eps_stable", "dt_stable", "seed_stable"])
        writer.writeheader()
        for key in sorted(result["cells"]):
            cell = result["cells"][key]
            writer.writerow({
                "dt": cell["dt"], "eps": cell["eps"], "ablation": cell["ablation"],
                "robust_v5": cell["robust_v5"],
                "eps_stable": result["eps_stable"], "dt_stable": result["dt_stable"],
                "seed_stable": result["seed_stable"],
            })
    payload = _round6(result)
    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(sensitivity_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"], "config_hash": result["config_hash"],
                   "model_scope": result["model_scope"],
                   "immortality_status": result["immortality_status"],
                   "reference_dt": result["reference_dt"],
                   "reference_eps": result["reference_eps"],
                   "eps_stable": result["eps_stable"], "dt_stable": result["dt_stable"],
                   "seed_stable": result["seed_stable"],
                   "verdicts_at_reference": result["verdicts_at_reference"],
                   "compound_wall": result["compound_wall"],
                   "eps_detail": _round6(result["eps_detail"])}, fh, ensure_ascii=False,
                  indent=2, allow_nan=False)
    for cell in result["cells"].values():
        if not math.isfinite(float(cell["success_rate_v5"])):
            raise ValueError("non-finite sensitivity output")
    return {"long_csv": long_path, "summary_csv": summary_path, "summary_json": summary_json_path,
            "sensitivity_json": sensitivity_path}


def write_heterogeneous_outputs(result: dict[str, Any], out_prefix: str) -> dict[str, str]:
    parent = os.path.dirname(os.path.abspath(out_prefix))
    os.makedirs(parent, exist_ok=True)
    summary_json_path = f"{out_prefix}_summary.json"
    regimes_path = f"{out_prefix}_regimes.csv"
    residual_path = f"{out_prefix}_residual_classification.json"
    with open(regimes_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=[
            "regime", "kind", "driver_scales", "n_seeds", "robust_v5", "v5_ru",
            "mean_bio_age_slope", "mean_bio_attribution_total_slope",
            "bio_reduction_vs_control", "mean_irreversible_slope",
            "binding_majority", "binding_ru", "dominant_bio_source",
            "dominant_bio_source_ru", "source_flip", "binding_changed",
            "wall_classification", "wall_ru", "seed_stable"])
        writer.writeheader()
        for name in result["entries"]:
            entry = result["entries"][name]
            writer.writerow({
                "regime": name, "kind": entry["kind"],
                "driver_scales": json.dumps(entry["driver_scales"], sort_keys=True),
                "n_seeds": entry["n_seeds"], "robust_v5": entry["robust_v5"],
                "v5_ru": entry["v5_operational_success_ru"],
                "mean_bio_age_slope": _round6(entry["mean_bio_age_slope"]),
                "mean_bio_attribution_total_slope": _round6(
                    entry["mean_bio_attribution_total_slope"]),
                "bio_reduction_vs_control": _round6(
                    entry.get("bio_reduction_vs_control", 0.0)),
                "mean_irreversible_slope": _round6(entry["mean_irreversible_slope"]),
                "binding_majority": entry["binding_majority"],
                "binding_ru": entry["binding_majority_ru"],
                "dominant_bio_source": entry["dominant_bio_source_majority"],
                "dominant_bio_source_ru": entry["dominant_bio_source_majority_ru"],
                "source_flip": entry.get("source_flip_vs_control", False),
                "binding_changed": entry.get("binding_changed_vs_control", False),
                "wall_classification": entry["wall_classification"],
                "wall_ru": entry["wall_classification_ru"],
                "seed_stable": entry["seed_stable"],
            })
    payload = _round6(result)
    with open(summary_json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, allow_nan=False)
    with open(residual_path, "w", encoding="utf-8") as fh:
        json.dump({"experiment_id": result["experiment_id"],
                   "config_hash": result["config_hash"],
                   "model_scope": result["model_scope"],
                   "immortality_status": result["immortality_status"],
                   "immortality_status_ru": result["immortality_status_ru"],
                   "candidate_robust_bounded_degradation_v5_found":
                       result["candidate_robust_bounded_degradation_v5_found"],
                   "candidate_ru": result["candidate_ru"],
                   "seed_stable_all_regimes": result["seed_stable_all_regimes"],
                   "stage_6f": _round6(result["stage_6f"])},
                  fh, ensure_ascii=False, indent=2, allow_nan=False)
    for entry in result["entries"].values():
        for value in (entry["mean_bio_age_slope"],
                      entry["mean_bio_attribution_total_slope"],
                      entry["mean_irreversible_slope"]):
            if not math.isfinite(float(value)):
                raise ValueError("non-finite heterogeneous output")
    return {"summary_json": summary_json_path, "regimes_csv": regimes_path,
            "residual_classification_json": residual_path}


def load_boundary_config(path: str) -> BoundarySweepConfig | ComponentAttributionConfig | SensitivityConfig | HeterogeneousProbeConfig:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    kind = data.get("kind", "")
    if kind in KIND_TO_PARAM:
        return BoundarySweepConfig.from_config_dict(data)
    if kind == "component_attribution":
        return ComponentAttributionConfig.from_config_dict(data)
    if kind == "sensitivity":
        return SensitivityConfig.from_config_dict(data)
    if kind == "heterogeneous_probe":
        return HeterogeneousProbeConfig.from_config_dict(data)
    raise ValueError(f"boundary config kind must be one of {sorted(KIND_TO_PARAM) + ['component_attribution', 'sensitivity', 'heterogeneous_probe']}, "
                     f"got {kind!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a Stage 6D boundary probe study.")
    parser.add_argument("--config", required=True, help="Boundary study config JSON")
    parser.add_argument("--out-prefix", default="", help="Output prefix (default: config output_prefix)")
    args = parser.parse_args()
    config = load_boundary_config(args.config)
    out_prefix = args.out_prefix or config.output_prefix
    if not out_prefix:
        raise ValueError("no out-prefix: pass --out-prefix or set output_prefix in the config")
    if isinstance(config, BoundarySweepConfig):
        result = run_boundary_sweep(config)
        paths = write_sweep_outputs(result, out_prefix)
        print(f"[{config.kind} {config.experiment_id}] {len(result['points'])} points x {len(config.seeds)} seeds")
    elif isinstance(config, SensitivityConfig):
        result = run_sensitivity(config)
        paths = write_sensitivity_outputs(result, out_prefix)
        print(f"[sensitivity {config.experiment_id}] {len(result['cells'])} cells x {len(config.seeds)} seeds")
    elif isinstance(config, HeterogeneousProbeConfig):
        result = run_heterogeneous_probe(config)
        paths = write_heterogeneous_outputs(result, out_prefix)
        print(f"[heterogeneous_probe {config.experiment_id}] "
              f"{len(result['entries'])} regimes x {len(config.seeds)} seeds")
    else:
        result = run_component_attribution(config)
        paths = write_attribution_outputs(result, out_prefix)
        print(f"[attribution {config.experiment_id}] {len(result['entries'])} ablations x {len(config.seeds)} seeds")
    for key, path in paths.items():
        print(f"[{key}] {path}")


if __name__ == "__main__":
    main()
