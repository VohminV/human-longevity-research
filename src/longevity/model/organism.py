"""ORGANISM MODEL LAYER: minimal abstract life-course (Stage 5A).

An organism develops embryo -> ... -> adult_homeostasis, then ages under
coupled global drivers (damage / senescence / inflammation / fibrosis /
cancer / epigenetic drift / proteostasis / mitochondrial decline) acting on
eight vital systems. Death is a vital failure, never a timer: any critical
system below its failure threshold, vitality collapse, cascade, cancer
overburden, or (optionally) neural identity loss ends the run.

Scope (see docs/ORGANISM_MODEL.md): abstract years, ordinal rates, no
human anatomy and no calibrated biology. All numbers are OPERATIONAL model
choices. Determinism comes from an injected RNG; global random is never
touched.
"""

from __future__ import annotations

import copy
import math

from dataclasses import dataclass, field
from typing import Any

from longevity.sim.rng import Rng, state_from_json, state_to_json

ORGANISM_MODEL_VERSION = "0.5.0"
MODEL_SCOPE = "abstract_organism_life_course"

STAGES = (
    "embryo",
    "fetal",
    "infancy",
    "childhood",
    "adolescence",
    "adult_homeostasis",
    "early_aging",
    "late_aging",
    "terminal_decline",
)

DEFAULT_STAGE_BOUNDS: dict[str, float] = {
    "age_embryo_end": 0.75,
    "age_fetal_end": 1.0,
    "age_infancy_end": 3.0,
    "age_childhood_end": 12.0,
    "age_adolescence_end": 20.0,
    "age_adult_end": 45.0,
    "age_early_aging_end": 70.0,
}
_STAGE_BOUND_ORDER = (
    ("embryo", "age_embryo_end"),
    ("fetal", "age_fetal_end"),
    ("infancy", "age_infancy_end"),
    ("childhood", "age_childhood_end"),
    ("adolescence", "age_adolescence_end"),
    ("adult_homeostasis", "age_adult_end"),
    ("early_aging", "age_early_aging_end"),
)

# Per-system aging speed multipliers once adult_homeostasis is reached.
_STAGE_AGING_MULT = {
    "embryo": 0.0,
    "fetal": 0.0,
    "infancy": 0.05,
    "childhood": 0.1,
    "adolescence": 0.25,
    "adult_homeostasis": 1.0,
    "early_aging": 1.6,
    "late_aging": 2.2,
    "terminal_decline": 2.6,
}

VITAL_SYSTEMS = (
    "brain_cns",
    "cardiovascular",
    "respiratory",
    "hepatic",
    "renal",
    "immune",
    "metabolic",
    "musculoskeletal",
)

# Operational per-system profiles (O-5A-1…; not measurements). aging_rate is
# function loss per abstract year at multiplier 1.0; repair_capacity is
# function restored per reserve unit per year under full support.
DEFAULT_SYSTEM_PROFILES: dict[str, dict[str, float]] = {
    "brain_cns": {"aging_rate": 0.010, "repair_capacity": 0.010, "reserve_cap": 1.2,
                  "failure_threshold": 0.25, "warning_threshold": 0.40, "critical": 1.0,
                  "inflammation_sensitivity": 0.6, "cancer_sensitivity": 0.4,
                  "neural_identity_relevance": 1.0, "vitality_weight": 3.0, "growth_rate": 0.35},
    "cardiovascular": {"aging_rate": 0.014, "repair_capacity": 0.012, "reserve_cap": 1.0,
                       "failure_threshold": 0.25, "warning_threshold": 0.40, "critical": 1.0,
                       "inflammation_sensitivity": 0.8, "cancer_sensitivity": 0.3,
                       "neural_identity_relevance": 0.0, "vitality_weight": 2.0, "growth_rate": 0.45},
    "respiratory": {"aging_rate": 0.012, "repair_capacity": 0.012, "reserve_cap": 1.0,
                    "failure_threshold": 0.25, "warning_threshold": 0.40, "critical": 1.0,
                    "inflammation_sensitivity": 0.7, "cancer_sensitivity": 0.5,
                    "neural_identity_relevance": 0.0, "vitality_weight": 2.0, "growth_rate": 0.45},
    "hepatic": {"aging_rate": 0.011, "repair_capacity": 0.020, "reserve_cap": 1.4,
                "failure_threshold": 0.25, "warning_threshold": 0.40, "critical": 1.0,
                "inflammation_sensitivity": 0.5, "cancer_sensitivity": 0.7,
                "neural_identity_relevance": 0.0, "vitality_weight": 1.0, "growth_rate": 0.45},
    "renal": {"aging_rate": 0.013, "repair_capacity": 0.010, "reserve_cap": 1.0,
              "failure_threshold": 0.25, "warning_threshold": 0.40, "critical": 1.0,
              "inflammation_sensitivity": 0.6, "cancer_sensitivity": 0.4,
              "neural_identity_relevance": 0.0, "vitality_weight": 1.5, "growth_rate": 0.45},
    "immune": {"aging_rate": 0.015, "repair_capacity": 0.018, "reserve_cap": 1.2,
               "failure_threshold": 0.25, "warning_threshold": 0.40, "critical": 1.0,
               "inflammation_sensitivity": 0.9, "cancer_sensitivity": 0.6,
               "neural_identity_relevance": 0.0, "vitality_weight": 1.5, "growth_rate": 0.40},
    "metabolic": {"aging_rate": 0.012, "repair_capacity": 0.016, "reserve_cap": 1.2,
                  "failure_threshold": 0.25, "warning_threshold": 0.40, "critical": 1.0,
                  "inflammation_sensitivity": 0.7, "cancer_sensitivity": 0.5,
                  "neural_identity_relevance": 0.0, "vitality_weight": 1.0, "growth_rate": 0.45},
    "musculoskeletal": {"aging_rate": 0.016, "repair_capacity": 0.014, "reserve_cap": 1.0,
                        "failure_threshold": 0.20, "warning_threshold": 0.35, "critical": 0.0,
                        "inflammation_sensitivity": 0.5, "cancer_sensitivity": 0.3,
                        "neural_identity_relevance": 0.0, "vitality_weight": 0.5, "growth_rate": 0.50},
}

DEATH_CAUSES = (
    "none",
    "brain_failure",
    "cardiovascular_failure",
    "respiratory_failure",
    "hepatic_failure",
    "renal_failure",
    "immune_failure",
    "metabolic_failure",
    "musculoskeletal_failure",
    "cancer_death",
    "systemic_cascade",
    "neural_identity_loss",
    # Stage 6A organ-backed causes (appended after legacy causes so the
    # canonical order of Stage 5A/5B/5C violations is preserved).
    "organ_failure",
    "multi_organ_cascade",
    "perfusion_failure",
    "immune_surveillance_failure",
    "metabolic_support_failure",
    "repair_budget_exhaustion",
    "global_resource_exhaustion",
    # Stage 6B organ-network causes (appended after 6A; canonical order
    # of all earlier violations is preserved).
    "network_cascade_failure",
    "energy_exhaustion",
    "information_loss",
    "mutation_load_failure",
    "feedback_runaway",
    "bottleneck_edge_failure",
    "critical_organ_cascade",
    "hard_limit_violation",
    "unknown_network_collapse",
    # Stage 6C reversibility causes (appended after 6B; canonical order
    # of all earlier violations is preserved).
    "irreversible_accumulation_failure",
    "repair_ceiling_exhaustion",
    "conversion_runaway",
    "information_debt_failure",
    "mutation_fixation_failure",
    "niche_disorder_failure",
    "entropy_production_failure",
    "biological_age_floor_erosion",
    "unknown_reversibility_collapse",
    "unknown",
)

# Stage 5B shock types (operational stress events, O-5B-1).
SHOCK_TYPES = (
    "inflammation_spike",
    "immune_challenge",
    "cancer_burst",
    "metabolic_stress",
    "neural_stress",
    "intervention_toxicity",
    "reserve_shock",
)

DEFAULT_PERTURBATION: dict[str, Any] = {
    "model": "none",
    "aging_noise_scale": 0.0,
    "intervention_efficacy_noise_scale": 0.0,
    "repair_capacity_noise_scale": 0.0,
    "shock_probability_per_step": 0.0,
    "shock_magnitude_scale": 0.0,
    "shock_duration_steps": 1,
    "efficacy_scale": 1.0,
    "perturb_seed": None,
    "shock_types": None,
}
PERTURBATION_MODELS = ("none", "parametric_noise")

_SYSTEM_TO_CAUSE = {
    "brain_cns": "brain_failure",
    "cardiovascular": "cardiovascular_failure",
    "respiratory": "respiratory_failure",
    "hepatic": "hepatic_failure",
    "renal": "renal_failure",
    "immune": "immune_failure",
    "metabolic": "metabolic_failure",
    "musculoskeletal": "musculoskeletal_failure",
}

DEFAULT_ORGANISM_THRESHOLDS: dict[str, Any] = {
    "min_vitality": 0.30,
    "cascade_warning_count": 3,
    "max_cancer_burden": 0.80,
    "max_inflammation_with_immune_collapse": 0.60,
    "min_neural_identity_threshold": 0.50,
    "neural_identity_loss_lethal": True,
    "min_health_function": 0.60,
}
_THRESHOLD_KEYS = tuple(DEFAULT_ORGANISM_THRESHOLDS)


def _require_number(value: Any, path: str, lo: float | None = None, hi: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{path} must be finite, got {value!r}")
    if lo is not None and result < lo:
        raise ValueError(f"{path} must be >= {lo}")
    if hi is not None and result > hi:
        raise ValueError(f"{path} must be <= {hi}")
    return result


def stage_for_age(age: float, bounds: dict[str, float]) -> str:
    """Developmental stage for a chronological age (pure, monotone)."""
    for stage, key in _STAGE_BOUND_ORDER:
        if age < bounds[key]:
            return stage
    return "late_aging"


def validate_stage_bounds(bounds: dict[str, Any]) -> dict[str, float]:
    """Validate strictly increasing stage boundaries."""
    if not isinstance(bounds, dict):
        raise ValueError("stage bounds must be a dict")
    missing = set(DEFAULT_STAGE_BOUNDS) - set(bounds)
    if missing:
        raise ValueError(f"stage bounds missing keys: {sorted(missing)}")
    unknown = set(bounds) - set(DEFAULT_STAGE_BOUNDS)
    if unknown:
        raise ValueError(f"stage bounds unknown keys: {sorted(unknown)}")
    validated = {k: _require_number(bounds[k], f"stages.{k}", lo=0.0) for k in DEFAULT_STAGE_BOUNDS}
    ordered = [validated[k] for _, k in _STAGE_BOUND_ORDER]
    if any(b <= a for a, b in zip(ordered, ordered[1:])):
        raise ValueError(f"stage bounds must be strictly increasing, got {ordered}")
    return validated


def validate_organism_thresholds(thresholds: dict[str, Any]) -> dict[str, Any]:
    """Validate organism viability thresholds."""
    if not isinstance(thresholds, dict):
        raise ValueError("organism thresholds must be a dict")
    missing = set(_THRESHOLD_KEYS) - set(thresholds)
    if missing:
        raise ValueError(f"organism thresholds missing keys: {sorted(missing)}")
    unknown = set(thresholds) - set(_THRESHOLD_KEYS)
    if unknown:
        raise ValueError(f"organism thresholds unknown keys: {sorted(unknown)}")
    validated: dict[str, Any] = {}
    for key in _THRESHOLD_KEYS:
        if key == "cascade_warning_count":
            value = thresholds[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"organism thresholds.{key} must be an int >= 1, got {value!r}")
            validated[key] = value
        elif key == "neural_identity_loss_lethal":
            if not isinstance(thresholds[key], bool):
                raise ValueError(f"organism thresholds.{key} must be a bool, got {thresholds[key]!r}")
            validated[key] = bool(thresholds[key])
        else:
            validated[key] = _require_number(thresholds[key], f"organism thresholds.{key}", lo=0.0, hi=1.0)
    return validated


@dataclass
class VitalSystemState:
    """One vital system: function/reserve/damage plus sensitivities."""

    name: str = "cardiovascular"
    function: float = 0.6
    reserve: float = 0.2
    damage: float = 0.0
    aging_rate: float = 0.012
    repair_capacity: float = 0.012
    reserve_cap: float = 1.0
    failure_threshold: float = 0.25
    warning_threshold: float = 0.40
    critical: bool = True
    inflammation_sensitivity: float = 0.5
    cancer_sensitivity: float = 0.5
    neural_identity_relevance: float = 0.0
    vitality_weight: float = 1.0
    growth_rate: float = 0.45
    informational_continuity: float = 1.0

    def __post_init__(self) -> None:
        if self.name not in VITAL_SYSTEMS:
            raise ValueError(f"system name must be one of {VITAL_SYSTEMS}, got {self.name!r}")
        for field_name in ("function", "failure_threshold", "warning_threshold",
                           "inflammation_sensitivity", "cancer_sensitivity",
                           "neural_identity_relevance", "informational_continuity"):
            _require_number(getattr(self, field_name), f"system.{self.name}.{field_name}", lo=0.0, hi=1.0)
        for field_name in ("damage", "reserve", "aging_rate", "repair_capacity", "reserve_cap",
                           "vitality_weight", "growth_rate"):
            _require_number(getattr(self, field_name), f"system.{self.name}.{field_name}", lo=0.0)
        if not isinstance(self.critical, bool):
            raise ValueError("system.critical must be a bool")
        if not self.failure_threshold < self.warning_threshold:
            raise ValueError("system failure_threshold must be < warning_threshold")

    def to_dict(self) -> dict[str, Any]:
        return {key: getattr(self, key) for key in (
            "name", "function", "reserve", "damage", "aging_rate", "repair_capacity",
            "reserve_cap", "failure_threshold", "warning_threshold", "critical",
            "inflammation_sensitivity", "cancer_sensitivity", "neural_identity_relevance",
            "vitality_weight", "growth_rate", "informational_continuity")}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "VitalSystemState":
        profile = dict(DEFAULT_SYSTEM_PROFILES.get(data.get("name", ""), {}))
        merged = dict(profile)
        merged.update(data)
        if "critical" in merged:
            merged["critical"] = bool(merged["critical"])
        return cls(**{k: merged[k] for k in (
            "name", "function", "reserve", "damage", "aging_rate", "repair_capacity",
            "reserve_cap", "failure_threshold", "warning_threshold", "critical",
            "inflammation_sensitivity", "cancer_sensitivity", "neural_identity_relevance",
            "vitality_weight", "growth_rate", "informational_continuity") if k in merged})


@dataclass
class OrganismState:
    """Full organism state (JSON-serializable, all finite)."""

    time: float = 0.0
    chronological_age: float = 0.0
    biological_age: float = 0.0
    developmental_stage: str = "embryo"
    alive: bool = True
    body_size: float = 0.05
    functional_reserve: float = 0.1
    vitality_index: float = 0.15
    systems: dict[str, Any] = field(default_factory=dict)
    global_damage: float = 0.0
    senescence_burden: float = 0.0
    inflammation: float = 0.02
    fibrosis: float = 0.0
    cancer_burden: float = 0.0
    epigenetic_drift: float = 0.0
    proteostasis_capacity: float = 1.0
    mitochondrial_function: float = 1.0
    intervention_history: list = field(default_factory=list)
    rejuvenation_events: int = 0
    failure_cause: str = "none"
    death_time: float | None = None
    active_shocks: list = field(default_factory=list)
    shock_history: list = field(default_factory=list)
    aging: dict[str, Any] | None = None
    organ_backed: dict[str, Any] | None = None
    organ_network: dict[str, Any] | None = None
    reversibility: dict[str, Any] | None = None
    boundary: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {key: getattr(self, key) for key in (
            "time", "chronological_age", "biological_age", "developmental_stage", "alive",
            "body_size", "functional_reserve", "vitality_index", "global_damage",
            "senescence_burden", "inflammation", "fibrosis", "cancer_burden",
            "epigenetic_drift", "proteostasis_capacity", "mitochondrial_function",
            "intervention_history", "rejuvenation_events", "failure_cause", "death_time",
            "active_shocks", "shock_history", "aging", "organ_backed", "organ_network",
            "reversibility", "boundary")}
        data["systems"] = {name: VitalSystemState.from_dict(info).to_dict()
                           for name, info in self.systems.items()}
        return copy.deepcopy(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OrganismState":
        systems = {name: VitalSystemState.from_dict(info).to_dict()
                   for name, info in dict(data.get("systems", {})).items()}
        kwargs = {k: data.get(k, getattr(cls, k, None)) for k in (
            "time", "chronological_age", "biological_age", "developmental_stage", "alive",
            "body_size", "functional_reserve", "vitality_index", "global_damage",
            "senescence_burden", "inflammation", "fibrosis", "cancer_burden",
            "epigenetic_drift", "proteostasis_capacity", "mitochondrial_function",
            "intervention_history", "rejuvenation_events", "failure_cause", "death_time",
            "active_shocks", "shock_history", "aging", "organ_backed", "organ_network",
            "reversibility", "boundary")}
        kwargs["systems"] = systems
        # Legacy (Stage 5A) states carry no shock lists.
        kwargs["active_shocks"] = list(kwargs.get("active_shocks") or [])
        kwargs["shock_history"] = list(kwargs.get("shock_history") or [])
        return cls(**kwargs)


def organism_invariant_violation(state: OrganismState) -> str | None:
    """First violated organism invariant, or None when physical."""
    for name in ("time", "chronological_age", "biological_age", "body_size",
                 "functional_reserve", "vitality_index", "global_damage",
                 "senescence_burden", "inflammation", "fibrosis", "cancer_burden",
                 "epigenetic_drift", "proteostasis_capacity", "mitochondrial_function"):
        value = getattr(state, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return f"{name} is not finite: {value!r}"
        if float(value) < 0.0:
            return f"{name} is negative: {value!r}"
    for name in ("proteostasis_capacity", "mitochondrial_function"):
        if not 0.0 <= float(getattr(state, name)) <= 1.0:
            return f"{name} out of [0, 1]"
    if state.developmental_stage not in STAGES:
        return f"unknown stage {state.developmental_stage!r}"
    for field_name in ("intervention_history", "active_shocks", "shock_history"):
        if not isinstance(getattr(state, field_name), list):
            return f"{field_name} must be a list"
    if state.aging is not None:
        if not isinstance(state.aging, dict):
            return "aging must be a dict or None"
        drivers = state.aging.get("drivers", {})
        for name, info in drivers.items():
            damage = info.get("damage", 0.0)
            if isinstance(damage, bool) or not isinstance(damage, (int, float)) \
                    or not math.isfinite(float(damage)) or not 0.0 <= float(damage) <= 1.0:
                return f"aging.drivers.{name}.damage out of [0, 1]: {damage!r}"
    if state.organ_backed is not None:
        from longevity.model.organ_backed import validate_organ_backed_state  # deferred

        try:
            validate_organ_backed_state(state.organ_backed)
        except ValueError as exc:
            return f"organ_backed invalid: {exc}"
    if state.organ_network is not None:
        from longevity.model.organ_network import validate_organ_network_state  # deferred

        try:
            validate_organ_network_state(state.organ_network)
        except ValueError as exc:
            return f"organ_network invalid: {exc}"
    if state.reversibility is not None:
        from longevity.model.reversibility import validate_reversibility_state  # deferred

        try:
            validate_reversibility_state(state.reversibility)
        except ValueError as exc:
            return f"reversibility invalid: {exc}"
    if state.boundary is not None:
        from longevity.model.boundary import validate_boundary_state  # deferred

        try:
            validate_boundary_state(state.boundary)
        except ValueError as exc:
            return f"boundary invalid: {exc}"
    if state.failure_cause not in DEATH_CAUSES:
        return f"unknown failure cause {state.failure_cause!r}"
    if set(state.systems) != set(VITAL_SYSTEMS):
        return f"systems must be exactly {VITAL_SYSTEMS}"
    for name, info in state.systems.items():
        for field_name in ("function", "reserve", "damage"):
            value = info.get(field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(float(value)) or float(value) < 0.0:
                return f"systems.{name}.{field_name} invalid: {value!r}"
        if not 0.0 <= float(info.get("function", 0.0)) <= 1.0:
            return f"systems.{name}.function out of [0, 1]"
        continuity = info.get("informational_continuity", 1.0)
        if not 0.0 <= float(continuity) <= 1.0:
            return f"systems.{name}.informational_continuity out of [0, 1]"
    return None


def assert_organism_invariants(state: OrganismState) -> None:
    violation = organism_invariant_violation(state)
    if violation is not None:
        raise AssertionError(f"organism invariant violated: {violation}")


class OrganismModel:
    """Executable abstract life-course: development, aging, death.

    Owns the :class:`OrganismState`, validated dynamics parameters, and the
    injected RNG (used only when ``stochastic_jitter > 0``). Interventions
    arrive as plain effect dicts (see :mod:`longevity.model.intervention`);
    this class applies them without knowing policy logic.
    """

    def __init__(
        self,
        state: OrganismState | None = None,
        parameters: dict[str, Any] | None = None,
        rng: Rng | None = None,
        seed: int = 0,
        perturbation: dict[str, Any] | None = None,
        perturb_seed: int | None = None,
        aging_model: str = "none",
        aging_drivers: dict[str, Any] | None = None,
        adult_age_setpoint: float = 25.0,
        allow_sub_adult_biological_age: bool = False,
        organ_backed_model: str = "none",
        organ_proxies: dict[str, Any] | None = None,
        systemic_resources: dict[str, Any] | None = None,
        coordination_mode: str = "independent_organ_policies",
        emergent_weights: dict[str, Any] | None = None,
        organ_network_model: str = "none",
        organ_network_edges: list[dict[str, Any]] | None = None,
        organ_network_feedback: dict[str, Any] | None = None,
        organ_network_hard_limits: dict[str, Any] | None = None,
        irreversible_thresholds: dict[str, Any] | None = None,
        allow_sub_adult_network_age: bool = False,
        reversibility_model: str = "none",
        reversibility_params: dict[str, Any] | None = None,
        allow_sub_adult_reversibility_age: bool = False,
        boundary_probe_model: str = "none",
        boundary_params: dict[str, Any] | None = None,
        component_overrides: list[dict[str, Any]] | None = None,
    ):
        from longevity.model.aging import (  # deferred: avoid import cycle
            default_driver_state,
            validate_aging_drivers,
            validate_aging_model,
        )
        from longevity.model.organ_backed import (  # deferred: avoid import cycle
            default_organ_backed_state,
            validate_coordination_mode,
            validate_emergent_weights,
            validate_organ_backed_model,
            validate_proxy_params,
            validate_resource_budgets,
        )
        from longevity.model.organ_network import (  # deferred: avoid import cycle
            default_organ_network_state,
            validate_feedback_config,
            validate_hard_limits,
            validate_irreversible_thresholds,
            validate_network_edges,
            validate_organ_network_model,
        )
        from longevity.model.reversibility import (  # deferred: avoid import cycle
            default_reversibility_state,
            validate_reversibility_model,
            validate_reversibility_params,
        )
        from longevity.model.boundary import (  # deferred: avoid import cycle
            _ablation_hash,
            default_boundary_state,
            effective_repair_ceiling,
            validate_boundary_params,
            validate_boundary_probe_model,
            validate_component_overrides,
        )

        self.state = state or self.default_state()
        assert_organism_invariants(self.state)
        self.parameters = validate_organism_parameters(parameters or {})
        self.perturbation = validate_perturbation(perturbation or {})
        self.rng = rng if rng is not None else Rng(seed)
        self.perturb_seed = seed if perturb_seed is None else perturb_seed
        if self.perturbation["perturb_seed"] is not None:
            self.perturb_seed = int(self.perturbation["perturb_seed"])
        # Dedicated streams keep perturbation draws out of the dynamics RNG.
        self.perturb_rng = Rng(self.perturb_seed)
        self.shock_rng = Rng(self.perturb_seed + 1)
        self.step_count = 0
        self.aging_model = validate_aging_model(aging_model)
        self.aging_drivers = validate_aging_drivers(aging_drivers)
        if isinstance(adult_age_setpoint, bool) or not isinstance(adult_age_setpoint, (int, float)) \
                or not math.isfinite(float(adult_age_setpoint)) or float(adult_age_setpoint) < 0.0:
            raise ValueError(f"adult_age_setpoint must be finite and >= 0, got {adult_age_setpoint!r}")
        self.adult_age_setpoint = float(adult_age_setpoint)
        if not isinstance(allow_sub_adult_biological_age, bool):
            raise ValueError("allow_sub_adult_biological_age must be a bool")
        self.allow_sub_adult_biological_age = allow_sub_adult_biological_age
        self.organ_backed_model = validate_organ_backed_model(organ_backed_model)
        self.organ_proxy_params = validate_proxy_params(organ_proxies)
        self.resource_budgets = validate_resource_budgets(systemic_resources)
        self.coordination_mode = validate_coordination_mode(coordination_mode)
        self.emergent_weights = validate_emergent_weights(emergent_weights)
        self.organ_network_model = validate_organ_network_model(organ_network_model)
        self.network_edges = validate_network_edges(organ_network_edges)
        self.network_feedback_config = validate_feedback_config(organ_network_feedback)
        self.network_hard_limits = validate_hard_limits(organ_network_hard_limits)
        self.irreversible_thresholds = validate_irreversible_thresholds(irreversible_thresholds)
        if not isinstance(allow_sub_adult_network_age, bool):
            raise ValueError("allow_sub_adult_network_age must be a bool")
        self.allow_sub_adult_network_age = allow_sub_adult_network_age
        self.reversibility_model = validate_reversibility_model(reversibility_model)
        self.reversibility_params = validate_reversibility_params(reversibility_params)
        if not isinstance(allow_sub_adult_reversibility_age, bool):
            raise ValueError("allow_sub_adult_reversibility_age must be a bool")
        self.allow_sub_adult_reversibility_age = allow_sub_adult_reversibility_age
        self.boundary_probe_model = validate_boundary_probe_model(boundary_probe_model)
        self.boundary_params = validate_boundary_params(boundary_params)
        self.component_overrides = validate_component_overrides(component_overrides)
        self._apply_static_perturbation()
        if self.aging_model == "mechanistic_drivers" and self.state.aging is None:
            self.state.aging = default_driver_state()
        if self.organ_backed_model == "reduced_organ_proxies" and self.state.organ_backed is None:
            self.state.organ_backed = default_organ_backed_state()
            self.state.organ_backed["resources"]["budgets"] = dict(self.resource_budgets)
        if self.organ_network_model == "reduced_network_feedback" and self.state.organ_network is None:
            self.state.organ_network = default_organ_network_state()
            self.state.organ_network["edges"] = [
                {**dict(e), "utilization": 0.0, "failure_risk": 0.0, "failed": False}
                for e in self.network_edges
            ]
            self.state.organ_network["hard_limits"] = dict(self.network_hard_limits)
            self.state.organ_network["irreversible_thresholds"] = dict(self.irreversible_thresholds)
            for loop, cfg in self.network_feedback_config.items():
                self.state.organ_network["feedback"][loop]["enabled"] = cfg["enabled"]
                self.state.organ_network["feedback"][loop]["configured_gain"] = cfg["gain"]
            self.state.organ_network["biological_age_network"] = float(self.adult_age_setpoint)
        if self.reversibility_model == "split_reversible_irreversible" \
                and self.state.reversibility is None:
            self.state.reversibility = default_reversibility_state()
            self.state.reversibility["repair_ceiling"] = float(
                self.reversibility_params["repair_ceiling"])
            self.state.reversibility["repair_remaining"] = float(
                self.reversibility_params["repair_ceiling"])
            self.state.reversibility["biological_age_reversibility"] = float(
                self.adult_age_setpoint)
            self.state.reversibility["biological_age_floor_dynamic"] = float(
                self.adult_age_setpoint)
        if self.boundary_probe_model == "irreversibility_ablation" and self.state.boundary is None:
            exploratory = bool(self.boundary_params.get("force_repair_ceiling_unlimited", False)
                               or self.boundary_params.get("disable_repair_ceiling", False))
            self.state.boundary = {
                "params": dict(self.boundary_params),
                "overrides": [dict(o) for o in self.component_overrides],
                "exploratory": exploratory,
                "ablation_flags_hash": _ablation_hash(self.boundary_params,
                                                     self.component_overrides),
            }
        if self.reversibility_model == "split_reversible_irreversible" \
                and self.state.reversibility is not None \
                and self.boundary_probe_model == "irreversibility_ablation":
            # Effective ceiling under ablation (unlimited modes use a large
            # finite sentinel and are marked exploratory in metadata).
            ceiling, _ = effective_repair_ceiling(
                float(self.reversibility_params["repair_ceiling"]), self.boundary_params)
            self.state.reversibility["repair_ceiling"] = float(ceiling)
            self.state.reversibility["repair_remaining"] = float(ceiling)

    def _apply_static_perturbation(self) -> None:
        """One-time init perturbation of rates (seeded, order-fixed)."""
        if self.perturbation["model"] == "none":
            return
        aging_scale = float(self.perturbation["aging_noise_scale"])
        repair_scale = float(self.perturbation["repair_capacity_noise_scale"])
        if aging_scale > 0.0:
            for name in VITAL_SYSTEMS:
                factor = max(0.0, 1.0 + aging_scale * self.perturb_rng.gauss(0.0, 1.0))
                self.state.systems[name]["aging_rate"] = max(0.0, float(self.state.systems[name]["aging_rate"]) * factor)
        if repair_scale > 0.0:
            for name in VITAL_SYSTEMS:
                factor = max(0.0, 1.0 + repair_scale * self.perturb_rng.gauss(0.0, 1.0))
                self.state.systems[name]["repair_capacity"] = max(
                    0.0, float(self.state.systems[name]["repair_capacity"]) * factor)
        if self.organ_backed_model == "reduced_organ_proxies" and self.state.organ_backed is not None:
            from longevity.model.organ_backed import ORGAN_PROXIES  # deferred

            if repair_scale > 0.0:
                for pid in ORGAN_PROXIES:
                    factor = max(0.0, 1.0 + repair_scale * self.perturb_rng.gauss(0.0, 1.0))
                    proxy = self.state.organ_backed["proxies"][pid]
                    proxy["repair_capacity"] = max(0.0, float(proxy["repair_capacity"]) * factor)

    def _maybe_shock(self, dt: float) -> list[dict[str, Any]]:
        """Draw deterministic shock events for this step (Stage 5B)."""
        if self.perturbation["model"] == "none":
            return []
        probability = float(self.perturbation["shock_probability_per_step"])
        if probability <= 0.0 or self.shock_rng.random() >= probability:
            return []
        magnitude = max(0.0, float(self.perturbation["shock_magnitude_scale"])
                        * (0.5 + self.shock_rng.random()))
        allowed = self.perturbation.get("shock_types") or list(SHOCK_TYPES)
        shock_type = allowed[int(self.shock_rng.random() * len(allowed)) % len(allowed)]
        duration = int(self.perturbation["shock_duration_steps"])
        event = {"age": self.state.chronological_age, "type": shock_type,
                 "magnitude": magnitude, "remaining": duration, "duration": duration}
        self.state.active_shocks.append(dict(event))
        self.state.shock_history.append({"age": event["age"], "type": shock_type,
                                         "magnitude": magnitude, "duration": duration})
        if self.organ_backed_model == "reduced_organ_proxies":
            self._maybe_organ_shock(dt)
        if self.organ_network_model == "reduced_network_feedback":
            self._maybe_network_shock(dt)
        if self.reversibility_model == "split_reversible_irreversible":
            self._maybe_reversibility_shock(dt)
        return [event]

    def _maybe_organ_shock(self, dt: float) -> None:
        """Separate organ-backed shock draw (Stage 6A only).

        Uses its own gate on the shock stream so Stage 5B shock sequences
        stay untouched; legacy modes never create resource shocks.
        """
        from longevity.model.organ_backed import ORGAN_BACKED_SHOCK_TYPES  # deferred

        probability = float(self.perturbation["shock_probability_per_step"]) * 0.5
        if probability <= 0.0 or self.shock_rng.random() >= probability:
            return
        _ = dt
        magnitude = max(0.0, float(self.perturbation["shock_magnitude_scale"])
                        * (0.5 + self.shock_rng.random()))
        duration = int(self.perturbation["shock_duration_steps"])
        event = {"age": self.state.chronological_age, "type": ORGAN_BACKED_SHOCK_TYPES[0],
                 "magnitude": magnitude, "remaining": duration, "duration": duration}
        self.state.active_shocks.append(dict(event))
        self.state.shock_history.append({"age": event["age"], "type": event["type"],
                                         "magnitude": magnitude, "duration": duration})

    def _maybe_network_shock(self, dt: float) -> None:
        """Separate organ-network shock draw (Stage 6B only).

        Uses its own gate on the shock stream so Stage 5B/6A shock
        sequences stay untouched; legacy modes never create network shocks.
        """
        from longevity.model.organ_network import ORGAN_NETWORK_SHOCK_TYPES  # deferred

        probability = float(self.perturbation["shock_probability_per_step"]) * 0.4
        if probability <= 0.0 or self.shock_rng.random() >= probability:
            return
        _ = dt
        magnitude = max(0.0, float(self.perturbation["shock_magnitude_scale"])
                        * (0.5 + self.shock_rng.random()))
        duration = int(self.perturbation["shock_duration_steps"])
        shock_type = ORGAN_NETWORK_SHOCK_TYPES[
            int(self.shock_rng.random() * len(ORGAN_NETWORK_SHOCK_TYPES)) % len(ORGAN_NETWORK_SHOCK_TYPES)]
        event = {"age": self.state.chronological_age, "type": shock_type,
                 "magnitude": magnitude, "remaining": duration, "duration": duration}
        self.state.active_shocks.append(dict(event))
        self.state.shock_history.append({"age": event["age"], "type": event["type"],
                                         "magnitude": magnitude, "duration": duration})

    def _apply_active_shocks(self, dt: float) -> None:
        """Apply one step of active shocks; decrement and retire finished ones."""
        s = self.state
        remaining = []
        for shock in s.active_shocks:
            magnitude = float(shock["magnitude"])
            shock_type = shock["type"]
            if shock_type == "inflammation_spike":
                s.inflammation = min(1.0, s.inflammation + 0.05 * magnitude)
                s.global_damage = max(0.0, s.global_damage + 0.005 * magnitude * dt)
            elif shock_type == "immune_challenge":
                info = s.systems["immune"]
                info["damage"] = max(0.0, info["damage"] + 0.02 * magnitude * dt)
                info["reserve"] = max(0.0, info["reserve"] - 0.01 * magnitude * dt)
            elif shock_type == "cancer_burst":
                s.cancer_burden = min(1.0, s.cancer_burden + 0.02 * magnitude * dt)
            elif shock_type == "metabolic_stress":
                info = s.systems["metabolic"]
                info["damage"] = max(0.0, info["damage"] + 0.02 * magnitude * dt)
                s.global_damage = max(0.0, s.global_damage + 0.005 * magnitude * dt)
            elif shock_type == "neural_stress":
                brain = s.systems["brain_cns"]
                brain["informational_continuity"] = max(
                    0.0, float(brain.get("informational_continuity", 1.0)) - 0.01 * magnitude * dt)
            elif shock_type == "intervention_toxicity":
                s.functional_reserve = max(0.0, s.functional_reserve - 0.02 * magnitude * dt)
                s.inflammation = min(1.0, s.inflammation + 0.01 * magnitude * dt)
            elif shock_type == "reserve_shock":
                s.functional_reserve = max(0.0, s.functional_reserve - 0.05 * magnitude * dt)
                for name in VITAL_SYSTEMS:
                    info = s.systems[name]
                    info["reserve"] = max(0.0, info["reserve"] - 0.02 * magnitude * dt)
            elif shock_type == "resource_shock":
                # Organ-backed only: systemic budgets take a transient hit.
                if s.organ_backed is not None:
                    from longevity.model.organ_backed import SYSTEMIC_RESOURCES  # deferred

                    budgets = s.organ_backed["resources"]["budgets"]
                    for resource in SYSTEMIC_RESOURCES:
                        budgets[resource] = max(0.0, float(budgets[resource])
                                                - 0.05 * magnitude * dt)
            elif shock_type == "edge_failure":
                if s.organ_network is not None and s.organ_network.get("edges"):
                    import hashlib as _hashlib

                    idx = int(_hashlib.sha256(
                        f"{s.chronological_age:.4f}".encode()).hexdigest(), 16) \
                        % len(s.organ_network["edges"])
                    edge = s.organ_network["edges"][idx]
                    edge["failure_risk"] = min(1.0, float(edge.get("failure_risk", 0.0))
                                               + 0.2 * magnitude)
                    if edge["failure_risk"] > float(edge.get("failure_threshold", 0.6)):
                        edge["failed"] = True
            elif shock_type == "feedback_amplification":
                if s.organ_network is not None:
                    for loop in s.organ_network.get("feedback", {}):
                        info = s.organ_network["feedback"][loop]
                        info["gain_value"] = max(0.0, min(2.0, float(info.get("gain_value", 0.0))
                                                          + 0.05 * magnitude * dt))
                    s.inflammation = min(1.0, s.inflammation + 0.01 * magnitude * dt)
            elif shock_type == "energy_shortage":
                if s.organ_network is not None:
                    s.organ_network["energy_budget"] = max(
                        0.0, float(s.organ_network.get("energy_budget", 0.0))
                        - 0.5 * magnitude * dt)
            elif shock_type == "conversion_spike":
                if s.reversibility is not None:
                    from longevity.model.aging import AGING_DRIVERS  # deferred

                    bump = 0.01 * magnitude * dt
                    for name in AGING_DRIVERS:
                        comp = s.reversibility["drivers"][name]
                        move = min(float(comp.get("reversible", 0.0)), bump)
                        comp["reversible"] = max(0.0, float(comp["reversible"]) - move)
                        comp["irreversible"] = max(0.0, min(1.0, float(comp["irreversible"]) + move))
                    s.reversibility["total_conversion_flux"] = max(
                        0.0, float(s.reversibility.get("total_conversion_flux", 0.0)) + bump)
            elif shock_type == "repair_ceiling_shock":
                if s.reversibility is not None:
                    s.reversibility["repair_remaining"] = max(
                        0.0, float(s.reversibility.get("repair_remaining", 0.0))
                        - 0.02 * magnitude * dt)
            shock["remaining"] = int(shock["remaining"]) - 1
            if int(shock["remaining"]) > 0:
                remaining.append(shock)
        s.active_shocks = remaining

    @staticmethod
    def default_state() -> OrganismState:
        systems = {name: VitalSystemState.from_dict({"name": name}).to_dict() for name in VITAL_SYSTEMS}
        return OrganismState(systems=systems)

    # -- internal helpers -------------------------------------------------
    def _jitter(self, value: float) -> float:
        jitter = float(self.parameters["stochastic_jitter"])
        if jitter <= 0.0:
            return value
        return max(0.0, value * (1.0 + jitter * self.rng.gauss(0.0, 1.0)))

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    # -- dynamics ----------------------------------------------------------
    def _development_step(self, dt: float, bounds: dict[str, float]) -> None:
        """Growth program before aging dominates: function/reserve/size rise."""
        s = self.state
        p = self.parameters
        adult = s.developmental_stage in ("embryo", "fetal", "infancy", "childhood", "adolescence")
        for name in VITAL_SYSTEMS:
            info = s.systems[name]
            if adult:
                info["function"] = self._clamp01(
                    info["function"] + float(p["development_growth"]) * float(info.get("growth_rate", 0.45))
                    * (1.0 - info["function"]) * dt)
                info["reserve"] = min(float(info.get("reserve_cap", 1.0)),
                                      info["reserve"] + float(p["reserve_accrual"]) * dt)
            else:
                info["reserve"] = max(0.0, info["reserve"] - float(p["reserve_decay"]) * info["reserve"] * dt * 0.1)
        s.body_size = min(1.0, s.body_size + float(p["body_growth"]) * (1.0 - s.body_size) * dt) if adult else s.body_size
        _ = bounds

    def _aging_step(self, dt: float, stage: str) -> None:
        """Damage/senescence/inflammation/cancer/epigenetic/mitochondrial drift."""
        s = self.state
        p = self.parameters
        mult = _STAGE_AGING_MULT[stage]
        if mult <= 0.0:
            # Background drift only; damage stays ~0 during development.
            s.epigenetic_drift += float(p["epigenetic_rate"]) * 0.1 * dt
            return
        support = float(s.proteostasis_capacity) * float(s.mitochondrial_function)
        # Global drivers.
        s.global_damage += self._jitter(float(p["damage_rate"]) * mult * (1.0 + s.global_damage)) * dt
        s.senescence_burden = self._clamp01(
            s.senescence_burden + self._jitter(float(p["senescence_rate"]) * mult
                                              * (1.0 + s.global_damage + s.epigenetic_drift)) * dt)
        s.inflammation = self._clamp01(
            s.inflammation + self._jitter(float(p["inflammation_rate"]) * mult
                                         * (0.3 + s.senescence_burden)) * dt
            - float(p["inflammation_decay"]) * max(0.0, s.inflammation - 0.02) * dt)
        s.fibrosis = self._clamp01(
            s.fibrosis + self._jitter(float(p["fibrosis_rate"]) * mult
                                      * (0.2 + s.senescence_burden + s.inflammation)) * dt)
        cancer_growth = self._jitter(float(p["cancer_rate"]) * mult * (1.0 + s.global_damage)
                                     * (1.0 + s.epigenetic_drift)) * dt
        s.cancer_burden = self._clamp01(s.cancer_burden + cancer_growth
                                        - float(p["cancer_immune_control"]) * s.cancer_burden
                                        * float(s.systems["immune"]["function"]) * dt)
        s.epigenetic_drift += self._jitter(float(p["epigenetic_rate"]) * mult) * dt
        s.proteostasis_capacity = self._clamp01(
            s.proteostasis_capacity - float(p["proteostasis_decline"]) * mult * dt)
        s.mitochondrial_function = self._clamp01(
            s.mitochondrial_function - float(p["mito_decline"]) * mult * dt)
        # Per-system damage, function loss, and reserve-funded repair.
        driver_burden = 0.0
        if self.aging_model == "mechanistic_drivers" and s.aging is not None:
            # Mechanistic coupling: unresolved driver damage leaks into
            # system damage (O-5C-1). Zero in none-mode by construction.
            driver_burden = sum(float(cell["damage"]) for cell in s.aging["drivers"].values()) / 8.0
        for name in VITAL_SYSTEMS:
            info = s.systems[name]
            damage_in = self._jitter(
                (float(info["aging_rate"]) + float(p["damage_coupling"]) * s.global_damage
                 + float(info["inflammation_sensitivity"]) * s.inflammation * 0.01
                 + float(info["cancer_sensitivity"]) * s.cancer_burden * 0.01
                 + driver_burden * 0.03) * mult) * dt
            info["damage"] = max(0.0, info["damage"] + damage_in)
            info["function"] = self._clamp01(info["function"] - info["damage"] * 0.020 * dt * mult
                                             - float(info["aging_rate"]) * mult * dt * 0.12)
            repair = min(info["reserve"], float(info["repair_capacity"]) * max(0.0, support) * dt)
            info["function"] = self._clamp01(info["function"] + repair * 0.8)
            info["reserve"] = max(0.0, info["reserve"] - repair * float(p["repair_reserve_cost"]))
        # Brain continuity erodes with neural damage + drift.
        brain = s.systems["brain_cns"]
        brain["informational_continuity"] = self._clamp01(
            brain.get("informational_continuity", 1.0)
            - (brain["damage"] * 0.006 + s.epigenetic_drift * 0.001) * mult * dt)
        # Biological age runs slower early, faster when damaged.
        bio_rate = 0.85 + 1.6 * min(1.0, s.global_damage) + 0.8 * s.senescence_burden
        if stage in ("embryo", "fetal", "infancy"):
            bio_rate = min(bio_rate, 0.9)
        s.biological_age = max(0.0, s.biological_age + bio_rate * dt)
        if self.aging_model == "mechanistic_drivers":
            self._driver_step(dt, stage)

    def _driver_step(self, dt: float, stage: str) -> None:
        """Mechanistic driver accumulation/repair; bio_age from drivers (5C)."""
        from longevity.model.aging import aggregate_biological_age  # deferred: avoid import cycle

        s = self.state
        assert s.aging is not None
        mult = _STAGE_AGING_MULT[stage]
        reserve_factor = max(0.0, min(1.0, float(s.functional_reserve)))
        for name, params in self.aging_drivers.items():
            cell = s.aging["drivers"][name]
            damage = float(cell["damage"])
            accumulation = self._jitter(float(params["base_aging_rate"]) * mult
                                        * (1.0 + s.global_damage)) * dt
            repair = min(damage, float(params["repair_capacity"]) * reserve_factor * dt)
            cell["damage"] = max(float(params["floor"]),
                                 min(1.0, damage + accumulation - repair))
        bio, _ = aggregate_biological_age(
            {name: float(cell["damage"]) for name, cell in s.aging["drivers"].items()},
            self.aging_drivers, self.adult_age_setpoint, self.allow_sub_adult_biological_age)
        s.biological_age = bio

    def _organ_backed_step(self, dt: float, stage: str) -> None:
        """Reduced organ proxy dynamics + resource contention (Stage 6A)."""
        from longevity.model.organ_backed import (  # deferred: avoid import cycle
            ORGAN_PROXIES,
            SYSTEMIC_RESOURCES,
            compute_allocation,
            compute_demands,
            emergent_driver_levels,
            proxy_function_from_components,
        )

        s = self.state
        ob = s.organ_backed
        assert ob is not None
        proxies = ob["proxies"]
        mult = _STAGE_AGING_MULT[stage]
        # Demand/allocation from the current proxy state (stored for metrics).
        demands = compute_demands(proxies)
        allocation = compute_allocation(ob["resources"]["budgets"], demands)
        ob["resources"]["demand"] = demands
        ob["resources"]["allocation"] = allocation
        ob["resources"]["shortfall"] = {
            r: max(0.0, demands[r] - ob["resources"]["budgets"][r]) for r in SYSTEMIC_RESOURCES}
        if mult <= 0.0:
            # Development: proxies grow toward healthy function like systems.
            for pid in ORGAN_PROXIES:
                proxy = proxies[pid]
                growth = float(self.organ_proxy_params[pid]["growth_rate"])
                proxy["function"] = self._clamp01(
                    proxy["function"] + 0.35 * growth * (1.0 - proxy["function"]) * dt)
                proxy["ecm_quality"] = self._clamp01(
                    proxy["ecm_quality"] + 0.5 * (1.0 - proxy["ecm_quality"]) * dt)
                proxy["vascular_quality"] = self._clamp01(
                    proxy["vascular_quality"] + 0.5 * (1.0 - proxy["vascular_quality"]) * dt)
                proxy["reserve"] = max(0.0, proxy["reserve"]
                                       + float(self.parameters["reserve_accrual"]) * dt)
            self._map_proxies_to_systems()
            return
        reserve_factor = max(0.0, min(1.0, float(s.functional_reserve)))
        for pid in ORGAN_PROXIES:
            proxy = proxies[pid]
            params = self.organ_proxy_params[pid]
            support_repair = allocation["repair"]
            support_immune = allocation["immune"]
            support_perfusion = allocation["perfusion"]
            shortfall = 1.0 - min(support_perfusion, support_repair, support_immune)
            damage = max(0.0, float(proxy["damage"]))
            sen = max(0.0, min(1.0, float(proxy["senescence_burden"])))
            # Accumulation: base drift + systemic coupling + contention penalty.
            damage_in = self._jitter(
                (float(params["base_damage_rate"]) * (1.0 + s.global_damage)
                 + 0.02 * shortfall
                 + float(self.parameters["damage_coupling"]) * s.global_damage * 0.5) * mult) * dt
            damage = max(0.0, damage + damage_in)
            sen_in = self._jitter(float(params["base_senescence_rate"]) * mult * (1.0 + damage)) * dt
            turnover_out = float(params["turnover_rate"]) * support_repair * sen * dt
            sen = max(0.0, min(1.0, sen + sen_in - turnover_out))
            fib_in = self._jitter(float(params["base_fibrosis_rate"]) * mult
                                  * (0.2 + sen + s.inflammation)) * dt
            fibrosis = max(0.0, min(1.0, float(proxy["fibrosis"]) + fib_in))
            cancer_in = self._jitter(float(params["base_cancer_rate"]) * mult * (1.0 + damage)) * dt
            cancer_out = 0.05 * cancer_in * 0 + 0.05 * float(proxy["cancer_risk"]) \
                * float(s.systems["immune"]["function"]) * support_immune * dt
            cancer_risk = max(0.0, min(1.0, float(proxy["cancer_risk"]) + cancer_in - cancer_out))
            ecm = max(0.0, min(1.0, float(proxy["ecm_quality"])
                                      - float(params["ecm_decay"]) * mult * (1.0 + fibrosis) * dt))
            vascular_quality = max(0.0, min(1.0, float(proxy["vascular_quality"])
                                            - 0.002 * mult * (0.5 + damage) * dt
                                            + 0.1 * min(float(proxy["recovery_pending"]),
                                                        float(params["recovery_efficiency"])
                                                        * support_repair * dt)))
            immune_pressure = max(0.0, min(1.0, float(proxy["immune_pressure"])
                                           + 0.01 * mult * (sen + damage) * dt
                                           - 0.05 * max(0.0, float(proxy["immune_pressure"]) - 0.02) * dt))
            # Reserve-funded repair (mirrors the vital-system repair loop).
            repair = min(float(proxy["reserve"]),
                         float(proxy["repair_capacity"]) * support_repair * reserve_factor * dt)
            damage = max(0.0, damage - repair)
            proxy["reserve"] = max(0.0, float(proxy["reserve"])
                                   - repair * float(self.parameters["repair_reserve_cost"]))
            # Recovery pipeline (Stage 4D inspiration): pending work restores
            # capacities instead of vanishing.
            pending = max(0.0, float(proxy["recovery_pending"]))
            flow = min(pending, float(params["recovery_efficiency"]) * support_repair * dt)
            proxy["recovery_pending"] = max(0.0, pending - flow)
            proxy["vascular_capacity"] = max(0.0, min(2.0, float(proxy["vascular_capacity"])
                                                      - 0.01 * mult * (damage + sen) * dt
                                                      + flow * 0.5))
            proxy["immune_capacity"] = max(0.0, min(2.0, float(proxy["immune_capacity"])
                                                    - 0.01 * mult * sen * dt + flow * 0.3))
            proxy["damage"] = damage
            proxy["senescence_burden"] = sen
            proxy["fibrosis"] = fibrosis
            proxy["cancer_risk"] = cancer_risk
            proxy["ecm_quality"] = ecm
            proxy["vascular_quality"] = vascular_quality
            proxy["immune_pressure"] = immune_pressure
            proxy["recent_activity"] = max(0.0, float(proxy["recent_activity"]) * max(0.0, 1.0 - dt))
            proxy["function"] = proxy_function_from_components(proxy)
            if pid == "brain_cns_proxy":
                proxy["informational_continuity"] = self._clamp01(
                    float(proxy["informational_continuity"])
                    - (damage * 0.006 + s.epigenetic_drift * 0.001) * mult * dt)
        # Emergent driver blend (only over the mechanistic track, if present).
        if self.aging_model == "mechanistic_drivers" and s.aging is not None:
            levels = emergent_driver_levels(proxies)
            for name, weight in self.emergent_weights.items():
                if weight <= 0.0 or name not in s.aging["drivers"]:
                    continue
                cell = s.aging["drivers"][name]
                floor = float(self.aging_drivers[name]["floor"])
                blended = (1.0 - weight) * float(cell["damage"]) + weight * levels[name]
                cell["damage"] = max(floor, min(1.0, blended))
        self._map_proxies_to_systems()

    def _map_proxies_to_systems(self) -> None:
        """Blend vital-system function/continuity toward proxy states (6A)."""
        from longevity.model.organ_backed import PROXY_TO_SYSTEMS, proxy_function_from_components  # deferred

        s = self.state
        ob = s.organ_backed
        assert ob is not None
        for pid, systems in PROXY_TO_SYSTEMS.items():
            proxy = ob["proxies"][pid]
            proxy_function = proxy_function_from_components(proxy)
            for name in systems:
                if name not in s.systems:
                    continue
                info = s.systems[name]
                info["function"] = self._clamp01(
                    0.5 * float(info["function"]) + 0.5 * proxy_function)
                if name == "brain_cns" and proxy.get("informational_continuity") is not None:
                    info["informational_continuity"] = self._clamp01(
                        0.5 * float(info.get("informational_continuity", 1.0))
                        + 0.5 * float(proxy["informational_continuity"]))

    def _coordinate_effects(self, effects: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Run organism-level coordination over organ-targeted effects (6A/6B/6C)."""
        from longevity.model.organ_backed import coordinate_organ_effects  # deferred
        from longevity.model.organ_network import NETWORK_COORDINATION_MODES  # deferred
        from longevity.model.reversibility import REVERSIBILITY_COORDINATION_MODES  # deferred

        s = self.state
        assert s.organ_backed is not None
        if self.coordination_mode in REVERSIBILITY_COORDINATION_MODES:
            from longevity.model.reversibility import coordinate_reversibility_effects  # deferred

            if s.reversibility is None:
                return list(effects), {"mode": self.coordination_mode, "n_pending": len(effects),
                                       "n_executed": len(effects), "n_deferred": 0, "n_rejected": 0}
            queue = list(s.reversibility.get("coordination_queue", []))
            result = coordinate_reversibility_effects(
                effects, s.reversibility, self.coordination_mode, queue)
            s.reversibility["coordination_queue"] = result["queue"]
            stats = s.organ_backed["coordination_stats"]
            stats["executed"] += len(result["executed"])
            stats["deferred"] += len(result["deferred"])
            stats["rejected"] += len(result["rejected"])
            if result["detail"]["mode"] != "independent_reversibility":
                stats["scaled"] += len(result["executed"])
            net_stats = s.reversibility["coordination_stats"]
            if result["detail"]["mode"] == "preventive_priority":
                net_stats["preventive_priority_executions"] += len(result["executed"])
            if result["detail"]["mode"] == "repair_ceiling_guard":
                net_stats["repair_ceiling_guard_rejections"] += len(result["rejected"])
            if result["detail"]["mode"] == "information_guard":
                net_stats["information_guard_rejections"] += len(result["rejected"])
            if result["detail"]["mode"] == "mutation_guard":
                net_stats["mutation_guard_rejections"] += len(result["rejected"])
            return result["executed"], result["detail"]
        if self.coordination_mode in NETWORK_COORDINATION_MODES:
            from longevity.model.organ_network import coordinate_network_effects  # deferred

            network_ctx = s.organ_network if s.organ_network is not None else {}
            result = coordinate_network_effects(
                effects, s.organ_backed["proxies"],
                s.organ_backed["resources"]["allocation"],
                self.coordination_mode, s.organ_backed["coordination_queue"], network_ctx)
            s.organ_backed["coordination_queue"] = result["queue"]
            stats = s.organ_backed["coordination_stats"]
            stats["executed"] += len(result["executed"])
            stats["deferred"] += len(result["deferred"])
            stats["rejected"] += len(result["rejected"])
            if result["detail"]["mode"] != "independent_network":
                stats["scaled"] += len(result["executed"])
            if s.organ_network is not None:
                net_stats = s.organ_network["coordination_stats"]
                detail = result["detail"]
                if result["detail"]["mode"] == "cascade_guard":
                    net_stats["cascade_guard_rejections"] += len(result["rejected"])
                if result["detail"]["mode"] == "network_bottleneck_priority":
                    net_stats["bottleneck_priority_executions"] += len(result["executed"])
                if result["detail"]["mode"] == "mutation_load_guard":
                    net_stats["mutation_guard_rejections"] += len(result["rejected"])
                if result["detail"]["mode"] == "information_preservation_priority":
                    net_stats["information_priority_executions"] += len(result["executed"])
            return result["executed"], result["detail"]
        result = coordinate_organ_effects(
            effects, s.organ_backed["proxies"],
            s.organ_backed["resources"]["allocation"],
            self.coordination_mode, s.organ_backed["coordination_queue"])
        s.organ_backed["coordination_queue"] = result["queue"]
        stats = s.organ_backed["coordination_stats"]
        stats["executed"] += len(result["executed"])
        stats["deferred"] += len(result["deferred"])
        stats["rejected"] += len(result["rejected"])
        if result["detail"]["mode"] != "independent_organ_policies":
            stats["scaled"] += len(result["executed"])
        return result["executed"], result["detail"]

    def apply_effect(self, effect: dict[str, Any], source: str) -> dict[str, Any]:
        """Apply one intervention effect dict; returns the applied record.

        Pure arithmetic on state with clamps; records history + counts a
        rejuvenation event when biological age drops.
        """
        from longevity.model.intervention import validate_effect  # deferred: avoid import cycle

        effect = {k: v for k, v in dict(effect).items() if not k.startswith("_coord_")}
        effect = validate_effect(effect)
        s = self.state
        bio_before = s.biological_age
        targets = effect.get("target_systems") or list(VITAL_SYSTEMS)
        for name in targets:
            if name not in s.systems:
                continue
            info = s.systems[name]
            info["damage"] = max(0.0, info["damage"] + float(effect.get("delta_damage", 0.0)))
            info["function"] = self._clamp01(info["function"] + float(effect.get("delta_function", 0.0)))
            info["reserve"] = max(0.0, min(float(info.get("reserve_cap", 1.0)),
                                           info["reserve"] + float(effect.get("delta_reserve", 0.0))))
            if name == "brain_cns":
                info["informational_continuity"] = self._clamp01(
                    info.get("informational_continuity", 1.0) + float(effect.get("delta_neural_continuity", 0.0)))
        s.global_damage = max(0.0, s.global_damage + float(effect.get("delta_damage_global", 0.0)))
        s.senescence_burden = self._clamp01(s.senescence_burden + float(effect.get("delta_senescence", 0.0)))
        s.inflammation = self._clamp01(s.inflammation + float(effect.get("delta_inflammation", 0.0)))
        s.fibrosis = self._clamp01(s.fibrosis + float(effect.get("delta_fibrosis", 0.0)))
        s.cancer_burden = self._clamp01(s.cancer_burden + float(effect.get("delta_cancer", 0.0)))
        s.epigenetic_drift = max(0.0, s.epigenetic_drift + float(effect.get("delta_epigenetic_drift", 0.0)))
        if effect.get("pre_adult_firing", False):
            # Teratogenic proxy: rejuvenation-class firing during development
            # perturbs epigenetic state (documented in AGING_MODEL.md).
            s.epigenetic_drift = max(0.0, s.epigenetic_drift + 0.002 * float(effect.get("intensity", 1.0)))
        s.proteostasis_capacity = self._clamp01(
            s.proteostasis_capacity + float(effect.get("delta_proteostasis", 0.0)))
        s.mitochondrial_function = self._clamp01(
            s.mitochondrial_function + float(effect.get("delta_mitochondrial", 0.0)))
        s.biological_age = max(0.0, s.biological_age + float(effect.get("delta_biological_age", 0.0)))
        if self.aging_model == "mechanistic_drivers":
            self._apply_driver_effect(effect, source)
            # Mechanistic bio follows drivers; re-aggregate so the snapshot
            # reflects driver repair immediately (floor still enforced).
            from longevity.model.aging import aggregate_biological_age  # deferred: avoid import cycle

            assert s.aging is not None
            bio, _ = aggregate_biological_age(
                {name: float(cell["damage"]) for name, cell in s.aging["drivers"].items()},
                self.aging_drivers, self.adult_age_setpoint, self.allow_sub_adult_biological_age)
            # Direct bio deltas persist only insofar as drivers allow: a driver
            # repair that would push bio below the floor is clamped by it.
            s.biological_age = bio
        if self.organ_backed_model == "reduced_organ_proxies":
            self._apply_organ_effect(effect, source)
        if self.organ_network_model == "reduced_network_feedback" and s.organ_network is not None:
            self._apply_network_effect_costs(effect)
        if self.reversibility_model == "split_reversible_irreversible" and s.reversibility is not None:
            self._apply_reversibility_effect(effect)
        if s.biological_age < bio_before - 1e-9:
            s.rejuvenation_events += 1
        s.functional_reserve = max(0.0, s.functional_reserve + float(effect.get("delta_reserve_global", 0.0)))
        record = {"age": s.chronological_age, "source": source, "effect": effect.get("intervention_type", "?"),
                  "bio_delta": s.biological_age - bio_before,
                  "target_drivers": list(effect.get("target_drivers", []))}
        s.intervention_history.append(record)
        assert_organism_invariants(s)
        return record

    def _apply_driver_effect(self, effect: dict[str, Any], source: str) -> None:
        """Driver-level repair/reversal with diminishing returns + floor (5C)."""
        from longevity.model.aging import AGING_DRIVERS, effective_reversal  # deferred: avoid import cycle

        s = self.state
        assert s.aging is not None
        repairs = effect.get("driver_repairs") or {}
        reversals = effect.get("driver_reversals") or {}
        if not isinstance(repairs, dict) or not isinstance(reversals, dict):
            raise ValueError("driver_repairs/driver_reversals must be dicts")
        for name in AGING_DRIVERS:
            params = self.aging_drivers[name]
            cell = s.aging["drivers"][name]
            damage = float(cell["damage"])
            repair = max(0.0, float(repairs.get(name, 0.0)))
            if repair > 0.0:
                applied = min(damage - float(params["floor"]), repair)
                cell["damage"] = max(float(params["floor"]), damage - max(0.0, applied))
            requested = max(0.0, float(reversals.get(name, 0.0)))
            if requested > 0.0:
                realized = effective_reversal(requested, float(cell["damage"]),
                                              float(params["reversibility"]),
                                              float(params["reversal_saturation"]))
                cell["damage"] = max(float(params["floor"]), float(cell["damage"]) - realized)
                cell["reversal_applied_total"] = float(cell["reversal_applied_total"]) + realized
                if realized > 1e-12:
                    s.aging["age_reversal_events"].append(
                        {"age": s.chronological_age, "driver": name, "source": source,
                         "delta": -realized})

    def _apply_organ_effect(self, effect: dict[str, Any], source: str) -> None:
        """Organ-proxy deltas + systemic resource costs (Stage 6A)."""
        from longevity.model.organ_backed import (  # deferred: avoid import cycle
            ORGAN_PROXIES,
            SYSTEMIC_RESOURCES,
            proxy_function_from_components,
        )

        s = self.state
        ob = s.organ_backed
        assert ob is not None
        targets = effect.get("target_organ_ids") or list(ORGAN_PROXIES)
        for pid in targets:
            if pid not in ob["proxies"]:
                continue
            proxy = ob["proxies"][pid]
            proxy["damage"] = max(0.0, float(proxy["damage"])
                                  + float(effect.get("organ_delta_damage", 0.0)))
            proxy["senescence_burden"] = self._clamp01(
                float(proxy["senescence_burden"]) + float(effect.get("organ_delta_senescence", 0.0)))
            proxy["fibrosis"] = self._clamp01(
                float(proxy["fibrosis"]) + float(effect.get("organ_delta_fibrosis", 0.0)))
            proxy["cancer_risk"] = self._clamp01(
                float(proxy["cancer_risk"]) + float(effect.get("organ_delta_cancer_risk", 0.0)))
            proxy["ecm_quality"] = self._clamp01(
                float(proxy["ecm_quality"]) + float(effect.get("organ_delta_ecm", 0.0)))
            proxy["vascular_quality"] = self._clamp01(
                float(proxy["vascular_quality"]) + float(effect.get("organ_delta_vascular", 0.0)))
            proxy["immune_pressure"] = self._clamp01(
                float(proxy["immune_pressure"]) + float(effect.get("organ_delta_immune", 0.0)))
            proxy["reserve"] = max(0.0, float(proxy["reserve"])
                                   + float(effect.get("organ_delta_reserve", 0.0)))
            proxy["repair_capacity"] = max(
                0.0, float(proxy["repair_capacity"])
                + float(effect.get("organ_delta_repair_capacity", 0.0)))
            proxy["recovery_pending"] = max(
                0.0, float(proxy["recovery_pending"]) + float(effect.get("organ_delta_recovery", 0.0)))
            if pid == "brain_cns_proxy":
                proxy["informational_continuity"] = self._clamp01(
                    float(proxy["informational_continuity"])
                    + float(effect.get("organ_delta_continuity", 0.0)))
            proxy["function"] = self._clamp01(
                proxy_function_from_components(proxy) + float(effect.get("organ_delta_function", 0.0)))
            proxy["recent_activity"] = max(
                0.0, float(proxy["recent_activity"]) + 0.25 * float(effect.get("intensity", 1.0)))
        resource_cost = effect.get("organ_resource_cost") or {}
        if isinstance(resource_cost, dict):
            for resource in SYSTEMIC_RESOURCES:
                cost = max(0.0, float(resource_cost.get(resource, 0.0)))
                ob["resources"]["budgets"][resource] = max(
                    0.0, float(ob["resources"]["budgets"][resource]) - cost)

    def _vitality(self) -> float:
        total = sum(float(self.state.systems[name]["function"])
                    * float(self.state.systems[name].get("vitality_weight", 1.0)) for name in VITAL_SYSTEMS)
        weights = sum(float(self.state.systems[name].get("vitality_weight", 1.0)) for name in VITAL_SYSTEMS)
        return total / weights if weights > 0 else 0.0

    def check_viability(self, thresholds: dict[str, Any]) -> tuple[bool, list[str]]:
        """Death check (pure read): returns (alive, violations-as-causes)."""
        s = self.state
        violations: list[str] = []
        for name in VITAL_SYSTEMS:
            info = s.systems[name]
            if bool(info["critical"]) and float(info["function"]) < float(info["failure_threshold"]):
                violations.append(_SYSTEM_TO_CAUSE[name])
        vitality = self._vitality()
        if vitality < thresholds["min_vitality"]:
            violations.append("systemic_cascade")
        warnings = sum(1 for name in VITAL_SYSTEMS
                       if float(s.systems[name]["function"]) < float(s.systems[name]["warning_threshold"]))
        if warnings >= thresholds["cascade_warning_count"]:
            violations.append("systemic_cascade")
        if s.cancer_burden > thresholds["max_cancer_burden"]:
            violations.append("cancer_death")
        immune_collapsed = (float(s.systems["immune"]["function"])
                            < float(s.systems["immune"]["failure_threshold"]))
        if immune_collapsed and s.inflammation > thresholds["max_inflammation_with_immune_collapse"]:
            violations.append("immune_failure")
        brain = s.systems["brain_cns"]
        if (thresholds["neural_identity_loss_lethal"]
                and float(brain.get("informational_continuity", 1.0)) < thresholds["min_neural_identity_threshold"]):
            violations.append("neural_identity_loss")
        if s.organ_backed is not None:
            violations.extend(self._organ_backed_violations())
        if s.organ_network is not None:
            violations.extend(self._organ_network_violations())
        if s.reversibility is not None:
            violations.extend(self._reversibility_violations())
        ordered = [c for c in DEATH_CAUSES if c in violations]
        return (len(ordered) == 0, ordered)

    def _organ_backed_violations(self) -> list[str]:
        """Organ/resource death checks (Stage 6A; pure read)."""
        from longevity.model.organ_backed import ORGAN_PROXIES, SYSTEMIC_RESOURCES  # deferred

        s = self.state
        ob = s.organ_backed
        assert ob is not None
        violations: list[str] = []
        warnings = 0
        for pid in ORGAN_PROXIES:
            proxy = ob["proxies"][pid]
            params = self.organ_proxy_params[pid]
            if float(params["critical"]) > 0.5 \
                    and float(proxy["function"]) < float(params["failure_threshold"]):
                violations.append("organ_failure")
            if float(proxy["function"]) < float(params["warning_threshold"]):
                warnings += 1
        if warnings >= 3:
            violations.append("multi_organ_cascade")
        allocation = ob["resources"]["allocation"]
        exhausted = [r for r in SYSTEMIC_RESOURCES if float(allocation.get(r, 1.0)) < 0.2]
        if "perfusion" in exhausted:
            violations.append("perfusion_failure")
        if "immune" in exhausted:
            violations.append("immune_surveillance_failure")
        if "metabolic" in exhausted:
            violations.append("metabolic_support_failure")
        if "repair" in exhausted:
            violations.append("repair_budget_exhaustion")
        if len(exhausted) >= 2:
            violations.append("global_resource_exhaustion")
        return violations

    def _organ_network_violations(self) -> list[str]:
        """Network/hard-limit death checks (Stage 6B; pure read)."""
        s = self.state
        net = s.organ_network
        assert net is not None
        violations: list[str] = []
        limits = net.get("hard_limits", {})
        if float(net.get("cascade_risk", 0.0)) > float(limits.get("max_cascade_risk", 0.6)):
            violations.append("network_cascade_failure")
        if float(net.get("energy_budget", 1.0)) <= 1e-9:
            violations.append("energy_exhaustion")
        brain_cont = 1.0
        if s.organ_backed is not None and "brain_cns_proxy" in s.organ_backed["proxies"]:
            brain_cont = float(s.organ_backed["proxies"]["brain_cns_proxy"]
                               .get("informational_continuity", 1.0))
        else:
            brain_cont = float(s.systems["brain_cns"].get("informational_continuity", 1.0))
        if brain_cont < float(limits.get("min_informational_continuity", 0.5)) * 0.6:
            violations.append("information_loss")
        if float(net.get("mutation_load", 0.0)) > float(limits.get("max_mutation_load", 1.0)):
            violations.append("mutation_load_failure")
        max_gain = 0.0
        runaway_loops = []
        for loop, info in (net.get("feedback", {}) or {}).items():
            gain = max(0.0, float(info.get("gain_value", 0.0)))
            max_gain = max(max_gain, gain)
            if gain > float(limits.get("max_feedback_gain", 0.8)):
                runaway_loops.append(loop)
        if runaway_loops:
            violations.append("feedback_runaway")
        failed_edges = [e for e in net.get("edges", []) if e.get("failed")]
        if failed_edges:
            violations.append("bottleneck_edge_failure")
        if s.organ_backed is not None:
            from longevity.model.organ_backed import ORGAN_PROXIES  # deferred

            critical_failed = 0
            for pid in ORGAN_PROXIES:
                proxy = s.organ_backed["proxies"][pid]
                params = self.organ_proxy_params.get(pid, {})
                if float(params.get("critical", 1.0)) > 0.5 \
                        and float(proxy.get("function", 1.0)) < float(params.get("failure_threshold", 0.25)):
                    critical_failed += 1
            if critical_failed >= 2:
                violations.append("critical_organ_cascade")
        if net.get("failed_hard_limit_ids"):
            violations.append("hard_limit_violation")
        return violations

    def _reversibility_violations(self) -> list[str]:
        """Reversibility wall death checks (Stage 6C; pure read)."""
        s = self.state
        rev = s.reversibility
        assert rev is not None
        params = self.reversibility_params
        violations: list[str] = []
        if float(rev.get("irreversible_burden", 0.0)) > 0.55:
            violations.append("irreversible_accumulation_failure")
        if float(rev.get("repair_remaining", 1.0)) <= 1e-9 \
                and float(rev.get("repair_used_global", 0.0)) > 0.0:
            violations.append("repair_ceiling_exhaustion")
        if bool(rev.get("conversion_runaway", False)):
            violations.append("conversion_runaway")
        if float(rev.get("information_debt", 0.0)) > float(params["max_information_debt"]):
            violations.append("information_debt_failure")
        if float(rev.get("mutation_fixation", 0.0)) > float(params["max_mutation_fixation"]):
            violations.append("mutation_fixation_failure")
        if float(rev.get("niche_disorder", 0.0)) > float(params["max_niche_disorder"]):
            violations.append("niche_disorder_failure")
        adult_years = max(0.0, float(s.chronological_age) - 20.0)
        if adult_years > 1.0 and float(rev.get("entropy_auc", 0.0)) / adult_years \
                > float(params["max_entropy_rate"]) * 4.0:
            violations.append("entropy_production_failure")
        floor = float(rev.get("biological_age_floor_dynamic", self.adult_age_setpoint))
        if floor > float(self.adult_age_setpoint) + 30.0:
            violations.append("biological_age_floor_erosion")
        if rev.get("failed_ids"):
            violations.append("unknown_reversibility_collapse")
        return violations

    def _reversibility_step(self, dt: float, stage: str) -> None:
        """Reversible / irreversible accumulation + conversion + ceiling (6C).

        Stage 6D boundary scales multiply the base conversion / independent
        rates (neutral 1.0 reproduces 6C exactly); per-component overrides
        multiply individual ledger entries.
        """
        from longevity.model.aging import AGING_DRIVERS  # deferred
        from longevity.model.organ_backed import ORGAN_PROXIES  # deferred
        from longevity.model.reversibility import (  # deferred
            compute_reversibility_age,
            conversion_modifiers,
        )
        from longevity.model.boundary import (  # deferred
            effective_conversion_scale,
            effective_independent_scale,
            override_for,
        )

        s = self.state
        rev = s.reversibility
        assert rev is not None
        params = self.reversibility_params
        boundary_active = self.boundary_probe_model == "irreversibility_ablation"
        bparams = self.boundary_params if boundary_active else None
        overrides = self.component_overrides if boundary_active else []
        base_conv = float(params["base_conversion_rate"])
        base_indep = float(params["independent_irreversible_rate"])
        if bparams is not None:
            if bparams.get("disable_conversion", False):
                base_conv = 0.0
            else:
                base_conv *= max(0.0, float(bparams.get("conversion_scale", 1.0)))
            if bparams.get("disable_independent_accrual", False):
                base_indep = 0.0
            else:
                base_indep *= max(0.0, float(bparams.get("independent_accrual_scale", 1.0)))
        mult = {"embryo": 0.0, "fetal": 0.0, "infancy": 0.05, "childhood": 0.1,
                "adolescence": 0.25, "adult_homeostasis": 1.0, "early_aging": 1.6,
                "late_aging": 2.2, "terminal_decline": 2.6}[stage]
        if mult <= 0.0:
            self._update_reversibility_age()
            return
        # Prevention buffer decays and blunts new accumulation.
        prevention = max(0.0, float(rev.get("prevention_pending", 0.0)))
        prevention = max(0.0, prevention - prevention * 0.5 * dt - 0.002 * dt)
        rev["prevention_pending"] = prevention
        energy_shortfall = 0.0
        repair_shortfall = 0.0
        cascade = 0.0
        if s.organ_backed is not None:
            alloc = s.organ_backed["resources"]["allocation"]
            energy_shortfall = 0.0
            if s.organ_network is not None:
                initial = max(1e-9, float(s.organ_network.get("hard_limits", {})
                                          .get("energy_budget_initial", 30.0)))
                energy_shortfall = max(0.0, 1.0 - float(s.organ_network.get("energy_budget", initial))
                                       / initial)
            repair_shortfall = max(0.0, 1.0 - max(0.0, min(1.0, float(alloc.get("repair", 1.0)))))
        if s.organ_network is not None:
            cascade = max(0.0, min(1.0, float(s.organ_network.get("cascade_risk", 0.0))))
        toxicity = 0.0
        if s.organ_network is not None:
            toxicity = max(0.0, min(1.0, float(s.organ_network.get("intervention_toxicity", 0.0)) / 3.0))
        modifier = conversion_modifiers(
            max(0.0, min(1.0, float(s.inflammation))), energy_shortfall,
            repair_shortfall, cascade, max(0.0, min(1.0, float(rev.get("niche_disorder", 0.0)))),
            toxicity, params)
        flux = 0.0
        # Driver ledger: conversion reclassifies; independent accrual adds irr.
        if s.aging is not None:
            for name in AGING_DRIVERS:
                cell = s.aging["drivers"][name]
                comp = rev["drivers"][name]
                ov = override_for(overrides, "driver", name) if overrides else None
                conv_rate = base_conv
                indep_rate = base_indep
                if ov is not None:
                    if ov.get("conversion_rate_override") is not None:
                        conv_rate = base_conv * max(0.0, float(ov["conversion_rate_override"]))
                    if ov.get("independent_accrual_override") is not None:
                        indep_rate = base_indep * max(0.0, float(ov["independent_accrual_override"]))
                damage = max(0.0, min(1.0, float(cell.get("damage", 0.0))))
                irr = max(0.0, min(1.0, float(comp.get("irreversible", 0.0))))
                irr = min(irr, damage)
                reversible = max(0.0, damage - irr)
                convert = min(reversible, conv_rate * reversible * modifier * mult * dt)
                indep = indep_rate * mult * dt
                reversible -= convert
                irr_new = min(1.0, irr + convert + indep)
                flux += convert
                comp["reversible"] = max(0.0, min(1.0, reversible))
                comp["irreversible"] = max(0.0, min(1.0, irr_new))
                comp["conversion_rate"] = convert / max(dt, 1e-9)
                comp["conversion_cumul"] = max(0.0, float(comp.get("conversion_cumul", 0.0)) + convert)
                comp["independent_cumul"] = max(0.0, float(comp.get("independent_cumul", 0.0)) + indep)
        # Organ ledger mirrors proxy damage the same way.
        if s.organ_backed is not None:
            for pid in ORGAN_PROXIES:
                proxy = s.organ_backed["proxies"][pid]
                comp = rev["organs"][pid]
                ov = override_for(overrides, "organ", pid) if overrides else None
                conv_rate = base_conv
                indep_rate = 0.5 * base_indep
                if ov is not None:
                    if ov.get("conversion_rate_override") is not None:
                        conv_rate = base_conv * max(0.0, float(ov["conversion_rate_override"]))
                    if ov.get("independent_accrual_override") is not None:
                        indep_rate = base_indep * max(0.0, float(ov["independent_accrual_override"]))
                damage = max(0.0, float(proxy.get("damage", 0.0)))
                damage_n = max(0.0, min(1.0, damage))
                irr = max(0.0, min(1.0, float(comp.get("irreversible", 0.0))))
                irr = min(irr, damage_n)
                reversible = max(0.0, damage_n - irr)
                convert = min(reversible, conv_rate * reversible * modifier * mult * dt)
                indep = indep_rate * mult * dt
                reversible -= convert
                irr_new = min(1.0, irr + convert + indep)
                flux += 0.5 * convert
                comp["reversible"] = max(0.0, min(1.0, reversible))
                comp["irreversible"] = max(0.0, min(1.0, irr_new))
                comp["conversion_rate"] = convert / max(dt, 1e-9)
                comp["conversion_cumul"] = max(0.0, float(comp.get("conversion_cumul", 0.0)) + convert)
                comp["independent_cumul"] = max(0.0, float(comp.get("independent_cumul", 0.0)) + indep)
        rev["total_conversion_flux"] = max(0.0, float(rev.get("total_conversion_flux", 0.0)) + flux)
        threshold = float(params["conversion_runaway_threshold"])
        per_step = flux / max(dt, 1e-9)
        if per_step > threshold and rev.get("time_to_first_conversion_threshold") is None:
            rev["time_to_first_conversion_threshold"] = float(s.chronological_age)
        max_comp_rate = 0.0
        for comp in list(rev["drivers"].values()) + list(rev["organs"].values()):
            max_comp_rate = max(max_comp_rate, float(comp.get("conversion_rate", 0.0)))
        rev["conversion_runaway"] = bool(max_comp_rate > threshold)
        # Global burdens: means over ledgers (deterministic order).
        if s.aging is not None:
            rev["reversible_burden"] = sum(float(rev["drivers"][n]["reversible"])
                                          for n in AGING_DRIVERS) / max(1, len(AGING_DRIVERS))
            irr_drivers = sum(float(rev["drivers"][n]["irreversible"])
                              for n in AGING_DRIVERS) / max(1, len(AGING_DRIVERS))
        else:
            rev["reversible_burden"] = max(0.0, min(1.0, float(s.global_damage)))
            irr_drivers = 0.0
        irr_organs = sum(float(rev["organs"][p]["irreversible"]) for p in rev["organs"]) \
            / max(1, len(rev["organs"]))
        rev["irreversible_burden"] = max(0.0, min(1.0, 0.6 * irr_drivers + 0.4 * irr_organs))
        # Information / mutation / niche / entropy drift (all capped, no NaN).
        brain_irr = 0.0
        if "brain_cns_proxy" in rev["organs"]:
            brain_irr = float(rev["organs"]["brain_cns_proxy"]["irreversible"])
        info_step = (0.004 * brain_irr + 0.002 * float(s.epigenetic_drift)) * mult * dt
        rev["information_debt"] = max(0.0, min(1.0, float(rev["information_debt"]) + info_step))
        cancer_irr = 0.0
        if s.aging is not None and "cancer_prone" in rev["drivers"]:
            cancer_irr = float(rev["drivers"]["cancer_prone"]["irreversible"])
        mut_step = (0.5 * float(params["independent_irreversible_rate"])
                    * (0.5 + cancer_irr) * mult * dt)
        rev["mutation_fixation"] = max(0.0, min(1.0, float(rev["mutation_fixation"]) + mut_step))
        niche_in = max(0.0, min(1.0, float(s.inflammation) * 0.5 + energy_shortfall * 0.5))
        rev["niche_disorder"] = max(0.0, min(1.0, float(rev["niche_disorder"])
                                             + 0.004 * niche_in * mult * dt))
        entropy_step = (flux * 0.5 + max(0.0, 1.0 - (1.0 - energy_shortfall)) * 0.002) * mult
        rev["entropy_production"] = max(0.0, entropy_step / max(dt, 1e-9) * dt)
        rev["entropy_auc"] = max(0.0, float(rev.get("entropy_auc", 0.0)) + entropy_step * dt)
        # Niche disorder feeds back by slowing future clearance implicitly
        # via the conversion modifier (documented coupling).
        self._update_reversibility_age()

    def _update_reversibility_age(self) -> None:
        """Refresh reversibility bio age + floor from current ledgers."""
        from longevity.model.reversibility import compute_reversibility_age  # deferred

        s = self.state
        rev = s.reversibility
        assert rev is not None
        total, floor, rev_c, irr_c = compute_reversibility_age(
            self.adult_age_setpoint, float(rev.get("reversible_burden", 0.0)),
            float(rev.get("irreversible_burden", 0.0)),
            float(rev.get("information_debt", 0.0)),
            float(rev.get("mutation_fixation", 0.0)),
            float(rev.get("niche_disorder", 0.0)),
            self.reversibility_params, self.allow_sub_adult_reversibility_age)
        rev["biological_age_reversibility"] = float(total)
        rev["biological_age_floor_dynamic"] = float(floor)
        rev["reversible_age_contribution"] = float(rev_c)
        rev["irreversible_age_contribution"] = float(irr_c)

    def _apply_reversibility_effect(self, effect: dict[str, Any]) -> None:
        """Apply rev_* keys to the reversibility ledger (Stage 6C)."""
        from longevity.model.aging import AGING_DRIVERS  # deferred
        from longevity.model.organ_backed import ORGAN_PROXIES  # deferred

        s = self.state
        rev = s.reversibility
        assert rev is not None
        params = self.reversibility_params
        intensity = max(0.0, float(effect.get("intensity", 1.0)))
        # Prevention buffer (blunts future accumulation implicitly via step).
        prevention = max(0.0, float(effect.get("rev_prevention", 0.0)))
        if prevention > 0.0:
            rev["prevention_pending"] = max(0.0, float(rev.get("prevention_pending", 0.0))
                                            + prevention * float(params["prevention_relief"]))
        # Reversible clearance: reduce rev pools and underlying damage.
        clearance = max(0.0, float(effect.get("rev_clearance", 0.0)))
        if clearance > 0.0:
            if s.aging is not None:
                for name in AGING_DRIVERS:
                    comp = rev["drivers"][name]
                    take = min(float(comp["reversible"]), clearance / 8.0)
                    comp["reversible"] = max(0.0, float(comp["reversible"]) - take)
                    cell = s.aging["drivers"][name]
                    cell["damage"] = max(float(self.aging_drivers[name]["floor"]),
                                         max(0.0, min(1.0, float(cell.get("damage", 0.0)) - take)))
            if s.organ_backed is not None:
                for pid in ORGAN_PROXIES:
                    comp = rev["organs"][pid]
                    take = min(float(comp["reversible"]), clearance / 16.0)
                    comp["reversible"] = max(0.0, float(comp["reversible"]) - take)
                    proxy = s.organ_backed["proxies"][pid]
                    proxy["damage"] = max(0.0, float(proxy.get("damage", 0.0)) - take)
            rev["reversible_burden"] = max(0.0, float(rev.get("reversible_burden", 0.0)) - clearance * 0.2)
        # Conversion suppression is realized as a smaller next-step modifier
        # via a transient prevention bump (documented approximation).
        suppression = max(0.0, min(1.0, float(effect.get("rev_conversion_suppression", 0.0))))
        if suppression > 0.0:
            rev["prevention_pending"] = max(0.0, float(rev.get("prevention_pending", 0.0))
                                            + suppression * 0.02 * intensity)
        # Irreversible repair subject to ceiling / floor / diminishing.
        requested = max(0.0, float(effect.get("rev_irreversible_repair", 0.0)))
        if requested > 0.0 and not (self.boundary_probe_model == "irreversibility_ablation"
                                    and self.boundary_params.get("disable_irreversible_repair", False)):
            remaining = max(0.0, float(rev.get("repair_remaining", 0.0)))
            allowed = min(requested, remaining)
            # Diminishing: the fuller the ceiling usage, the less realized.
            used_frac = 1.0 - remaining / max(1e-9, float(rev.get("repair_ceiling", 0.3)))
            realized = allowed * max(0.0, 1.0 - float(params["repair_diminishing"]) * used_frac)
            per_driver = realized / 16.0
            if s.aging is not None:
                for name in AGING_DRIVERS:
                    comp = rev["drivers"][name]
                    take = min(float(comp["irreversible"]), per_driver)
                    floor = float(self.aging_drivers[name]["floor"])
                    comp["irreversible"] = max(0.0, float(comp["irreversible"]) - take)
                    comp["repair_used"] = max(0.0, float(comp["repair_used"]) + take)
                    comp["repair_cumul"] = max(0.0, float(comp.get("repair_cumul", 0.0)) + take)
                    cell = s.aging["drivers"][name]
                    cell["damage"] = max(floor, max(0.0, min(1.0, float(cell.get("damage", 0.0)) - take)))
            if s.organ_backed is not None:
                for pid in ORGAN_PROXIES:
                    comp = rev["organs"][pid]
                    take = min(float(comp["irreversible"]), per_driver * 0.5)
                    comp["irreversible"] = max(0.0, float(comp["irreversible"]) - take)
                    comp["repair_used"] = max(0.0, float(comp["repair_used"]) + take)
                    comp["repair_cumul"] = max(0.0, float(comp.get("repair_cumul", 0.0)) + take)
                    proxy = s.organ_backed["proxies"][pid]
                    proxy["damage"] = max(0.0, float(proxy.get("damage", 0.0)) - take)
            rev["repair_used_global"] = max(0.0, float(rev.get("repair_used_global", 0.0)) + realized)
            rev["repair_remaining"] = max(0.0, remaining - realized)
            cost = realized * float(params["repair_cost_per_unit"])
            risk = realized * float(params["repair_risk_per_unit"])
            rev["repair_cost_auc"] = max(0.0, float(rev.get("repair_cost_auc", 0.0)) + cost)
            rev["repair_risk_auc"] = max(0.0, float(rev.get("repair_risk_auc", 0.0)) + risk)
            s.inflammation = max(0.0, min(1.0, float(s.inflammation) + risk * 0.3))
            s.cancer_burden = max(0.0, min(1.0, float(s.cancer_burden) + risk * 0.2))
            if s.organ_network is not None:
                s.organ_network["mutation_load"] = max(
                    0.0, float(s.organ_network.get("mutation_load", 0.0)) + risk * 0.1)
                s.organ_network["intervention_toxicity"] = max(
                    0.0, float(s.organ_network.get("intervention_toxicity", 0.0)) + cost * 0.2)
            if rev.get("repair_ceiling_exhaustion_time") is None and rev["repair_remaining"] <= 1e-9 \
                    and realized > 0.0:
                rev["repair_ceiling_exhaustion_time"] = float(s.chronological_age)
        # Information / mutation / niche / entropy repairs (capped, costly).
        info_rep = max(0.0, float(effect.get("rev_information_repair", 0.0)))
        if info_rep > 0.0:
            # Already-lost identity is sticky: only a fraction is recoverable.
            rev["information_debt"] = max(0.0, float(rev.get("information_debt", 0.0)) - info_rep * 0.5)
        mut_rep = max(0.0, float(effect.get("rev_mutation_repair", 0.0)))
        if mut_rep > 0.0:
            rev["mutation_fixation"] = max(0.0, float(rev.get("mutation_fixation", 0.0)) - mut_rep * 0.5)
            if s.organ_network is not None:
                s.organ_network["mutation_load"] = max(
                    0.0, float(s.organ_network.get("mutation_load", 0.0)) - mut_rep * 0.2)
        niche_rep = max(0.0, float(effect.get("rev_niche_repair", 0.0)))
        if niche_rep > 0.0:
            rev["niche_disorder"] = max(0.0, float(rev.get("niche_disorder", 0.0)) - niche_rep * 0.6)
        entropy_red = max(0.0, float(effect.get("rev_entropy_reduction", 0.0)))
        if entropy_red > 0.0:
            rev["entropy_production"] = max(0.0, float(rev.get("entropy_production", 0.0))
                                            - entropy_red * 0.3)
        # Aggressive repair without guards raises debt (no free lunch).
        if str(effect.get("intervention_type", "")) == "irreversible_repair_pulse":
            rev["information_debt"] = max(0.0, min(1.0, float(rev.get("information_debt", 0.0))
                                                  + 0.004 * intensity))
            rev["mutation_fixation"] = max(0.0, min(1.0, float(rev.get("mutation_fixation", 0.0))
                                                   + 0.004 * intensity))
        self._update_reversibility_age()

    def _maybe_reversibility_shock(self, dt: float) -> None:
        """Separate reversibility shock draw (Stage 6C only)."""
        from longevity.model.reversibility import REVERSIBILITY_SHOCK_TYPES  # deferred

        probability = float(self.perturbation["shock_probability_per_step"]) * 0.3
        if probability <= 0.0 or self.shock_rng.random() >= probability:
            return
        _ = dt
        magnitude = max(0.0, float(self.perturbation["shock_magnitude_scale"])
                        * (0.5 + self.shock_rng.random()))
        duration = int(self.perturbation["shock_duration_steps"])
        shock_type = REVERSIBILITY_SHOCK_TYPES[
            int(self.shock_rng.random() * len(REVERSIBILITY_SHOCK_TYPES)) % len(REVERSIBILITY_SHOCK_TYPES)]
        event = {"age": self.state.chronological_age, "type": shock_type,
                 "magnitude": magnitude, "remaining": duration, "duration": duration}
        self.state.active_shocks.append(dict(event))
        self.state.shock_history.append({"age": event["age"], "type": event["type"],
                                         "magnitude": magnitude, "duration": duration})

    def _organ_network_step(self, dt: float, stage: str) -> None:
        """Cross-organ edges + feedback + hard limits (Stage 6B, opt-in)."""
        from longevity.model.organ_backed import ORGAN_PROXIES, SYSTEMIC_RESOURCES  # deferred
        from longevity.model.organ_network import (  # deferred
            compute_cascade_risk,
            compute_feedback_gains,
            compute_network_age,
        )

        s = self.state
        net = s.organ_network
        assert net is not None
        assert s.organ_backed is not None
        proxies = s.organ_backed["proxies"]
        allocation = s.organ_backed["resources"]["allocation"]
        mult = {"embryo": 0.0, "fetal": 0.0, "infancy": 0.05, "childhood": 0.1,
                "adolescence": 0.25, "adult_homeostasis": 1.0, "early_aging": 1.6,
                "late_aging": 2.2, "terminal_decline": 2.6}[stage]
        # Deliver due delayed edge effects (FIFO, deterministic order).
        due_now: dict[str, float] = {}
        still_pending: list[dict[str, Any]] = []
        for item in net.get("pending_delays", []):
            remaining = int(item.get("remaining", 0)) - 1
            if remaining <= 0:
                due_now[item["target"]] = due_now.get(item["target"], 0.0) + float(item.get("amount", 0.0))
            else:
                still_pending.append({"edge_id": item["edge_id"], "target": item["target"],
                                      "amount": float(item.get("amount", 0.0)), "remaining": remaining})
        net["pending_delays"] = still_pending
        for target, amount in due_now.items():
            if target in proxies:
                proxies[target]["damage"] = max(0.0, float(proxies[target]["damage"]) + amount)
        # Edge coupling: source burden -> target damage / demand.
        for edge in net.get("edges", []):
            source = proxies.get(edge["source"])
            target = proxies.get(edge["target"])
            if source is None or target is None:
                edge["utilization"] = 0.0
                edge["failure_risk"] = 0.0
                edge["failed"] = False
                continue
            weight = float(edge.get("weight", 0.0))
            if weight <= 0.0:
                edge["utilization"] = 0.0
                edge["failure_risk"] = 0.0
                edge["failed"] = False
                continue
            etype = str(edge.get("edge_type", ""))
            gain = float(edge.get("gain", 1.0))
            if etype in ("vascular_dependency", "immune_dependency",
                         "metabolic_dependency", "repair_resource_flow"):
                burden = max(0.0, float(source.get("damage", 0.0))) \
                    + max(0.0, min(1.0, float(source.get("senescence_burden", 0.0)))) * 0.5
                effect = weight * gain * burden * mult * dt
            elif etype in ("inflammatory_spread", "fibrosis_spread", "cancer_seeding_risk"):
                key = {"inflammatory_spread": "immune_pressure",
                       "fibrosis_spread": "fibrosis",
                       "cancer_seeding_risk": "cancer_risk"}[etype]
                burden = max(0.0, min(1.0, float(source.get(key, 0.0))))
                effect = weight * gain * burden * mult * dt
            else:  # signals: weak coupling via dysfunction
                burden = max(0.0, 1.0 - float(source.get("function", 1.0)))
                effect = weight * gain * burden * mult * dt * 0.5
            delay = int(edge.get("delay_steps", 0))
            if delay > 0 and effect > 1e-12:
                still_pending.append({"edge_id": edge["edge_id"], "target": edge["target"],
                                      "amount": effect, "remaining": delay})
            elif effect > 1e-12:
                target["damage"] = max(0.0, float(target.get("damage", 0.0)) + effect)
            utilization = max(0.0, min(1.0, weight * 4.0 * (0.3 + min(1.0, burden))))
            protection = float(edge.get("protection_sensitivity", 0.5))
            immune_alloc = max(0.0, min(1.0, float(allocation.get("immune", 1.0))))
            failure_risk = max(0.0, min(1.0, utilization * gain * (1.0 - protection * immune_alloc * 0.3)))
            edge["utilization"] = utilization
            edge["failure_risk"] = failure_risk
            was_failed = bool(edge.get("failed", False))
            edge["failed"] = bool(failure_risk > float(edge.get("failure_threshold", 0.6)))
            if edge["failed"] and not was_failed:
                net["failed_edge_ids"] = sorted(set(net.get("failed_edge_ids", [])) | {edge["edge_id"]})
                net["network_failure_sequence"] = list(net.get("network_failure_sequence", [])) + [edge["edge_id"]]
        net["pending_delays"] = still_pending
        # Feedback gains (pure) then operational application.
        gains = compute_feedback_gains(proxies, allocation, self.network_feedback_config)
        for loop, value in gains.items():
            net["feedback"][loop]["gain_value"] = float(value)
            net["feedback"][loop]["burden"] = float(value)
        infl = gains.get("inflammation_damage_loop", 0.0)
        immune_ex = gains.get("immune_exhaustion_loop", 0.0)
        metab = gains.get("metabolic_repair_loop", 0.0)
        vasc = gains.get("vascular_support_loop", 0.0)
        neural = gains.get("neural_identity_loop", 0.0)
        cancer_loop = gains.get("cancer_surveillance_loop", 0.0)
        fibro = gains.get("fibrosis_stiffness_loop", 0.0)
        if mult > 0.0:
            s.inflammation = max(0.0, min(1.0, s.inflammation + 0.01 * infl * mult * dt))
            for pid in ORGAN_PROXIES:
                proxy = proxies[pid]
                proxy["damage"] = max(0.0, float(proxy["damage"])
                                      + (0.004 * infl + 0.003 * metab + 0.003 * vasc
                                         + 0.002 * fibro) * mult * dt)
                proxy["senescence_burden"] = max(0.0, min(1.0, float(proxy["senescence_burden"])
                                                          + 0.002 * infl * mult * dt))
                proxy["fibrosis"] = max(0.0, min(1.0, float(proxy["fibrosis"])
                                                 + 0.002 * fibro * mult * dt))
                proxy["immune_pressure"] = max(0.0, min(1.0, float(proxy["immune_pressure"])
                                                        + 0.004 * infl * mult * dt))
                node = net["nodes"][pid]
                node["feedback_inflammation"] = max(0.0, min(2.0, 0.5 * infl))
                node["feedback_damage"] = max(0.0, min(2.0, 0.4 * (infl + metab + vasc)))
                node["feedback_repair"] = max(0.0, min(2.0, 0.3 * metab))
            s.cancer_burden = max(0.0, min(1.0, s.cancer_burden + 0.004 * cancer_loop * mult * dt))
            s.global_damage = max(0.0, s.global_damage + 0.002 * (infl + metab) * mult * dt)
            _ = immune_ex
        # Energy budget: drain + intervention-agnostic metabolic cost.
        limits = net.get("hard_limits", {})
        demands = s.organ_backed["resources"]["demand"]
        total_demand = sum(max(0.0, float(v)) for v in demands.values())
        drain = float(limits.get("energy_drain_per_year", 0.05)) * mult * dt \
            + 0.002 * total_demand * dt
        metabolic_func = float(proxies.get("metabolic_proxy", {}).get("function", 0.5))
        net["energy_budget"] = max(0.0, float(net.get("energy_budget", 0.0)) - drain
                                   + 0.005 * metabolic_func * dt)
        # Toxicity decay; niche disorder persists (no free washout).
        net["intervention_toxicity"] = max(
            0.0, float(net.get("intervention_toxicity", 0.0))
            - float(limits.get("toxicity_decay_per_year", 0.02)) * dt)
        # Irreversible damage: below-threshold function ratchets a floor.
        for pid in ORGAN_PROXIES:
            proxy = proxies[pid]
            node = net["nodes"][pid]
            threshold = float(net.get("irreversible_thresholds", {}).get(pid, 0.2))
            if float(proxy.get("function", 1.0)) < threshold:
                node["irreversible_damage"] = max(
                    float(node.get("irreversible_damage", 0.0)),
                    min(0.5, float(proxy.get("damage", 0.0)) * 0.3))
            floor = float(node.get("irreversible_damage", 0.0))
            if float(proxy.get("damage", 0.0)) < floor:
                proxy["damage"] = floor
        # Cascade + network age.
        cascade = compute_cascade_risk(proxies, allocation, gains, self.organ_proxy_params)
        net["cascade_risk"] = cascade
        net["max_cascade_risk_seen"] = max(float(net.get("max_cascade_risk_seen", 0.0)), cascade)
        brain_proxy = proxies.get("brain_cns_proxy", {})
        continuity = max(0.0, min(1.0, float(brain_proxy.get("informational_continuity", 1.0))))
        net["information_loss_risk"] = max(0.0, min(1.0, 1.0 - continuity))
        driver_damages: dict[str, float] = {}
        if s.aging is not None:
            driver_damages = {name: float(cell.get("damage", 0.0))
                              for name, cell in s.aging["drivers"].items()}
        else:
            driver_damages = {}
        organ_deficit = sum(max(0.0, 1.0 - float(p.get("function", 1.0))) for p in proxies.values()) \
            / max(1, len(proxies))
        shortfall_frac = 0.0
        if allocation:
            shortfall_frac = 1.0 - min(max(0.0, min(1.0, float(v))) for v in allocation.values())
            shortfall_frac = max(0.0, min(1.0, shortfall_frac))
        mean_gain = sum(gains.values()) / max(1, len(gains))
        fibrosis_mean = sum(max(0.0, min(1.0, float(p.get("fibrosis", 0.0))))
                            for p in proxies.values()) / max(1, len(proxies))
        cancer_mean = max(0.0, min(1.0, float(s.cancer_burden)))
        bio_net, contrib = compute_network_age(
            self.adult_age_setpoint, driver_damages, self.aging_drivers,
            organ_deficit, shortfall_frac, mean_gain,
            max(0.0, float(net.get("mutation_load", 0.0))),
            max(0.0, min(1.0, 1.0 - continuity)),
            fibrosis_mean, cancer_mean, cascade,
            None, self.allow_sub_adult_network_age)
        net["network_age_contribution"] = float(contrib)
        net["biological_age_network"] = float(bio_net)
        # Hard-limit violation ledger (operational, deterministic order).
        violated: list[str] = []
        if float(net.get("mutation_load", 0.0)) > float(limits.get("max_mutation_load", 1.0)):
            violated.append("mutation_load_ceiling")
        if continuity < float(limits.get("min_informational_continuity", 0.5)):
            violated.append("information_preservation_constraint")
        if cascade > float(limits.get("max_cascade_risk", 0.6)):
            violated.append("cascade_risk_limit")
        if float(net.get("energy_budget", 1.0)) <= 1e-9:
            violated.append("energy_budget")
        if float(net.get("intervention_toxicity", 0.0)) > float(limits.get("max_intervention_toxicity", 3.0)):
            violated.append("intervention_toxicity_budget")
        if float(net.get("niche_disorder", 0.0)) > float(limits.get("niche_integrity_limit", 1.0)):
            violated.append("niche_integrity_limit")
        for loop, info in net.get("feedback", {}).items():
            if float(info.get("gain_value", 0.0)) > float(limits.get("max_feedback_gain", 0.8)) \
                    and loop not in net.get("failed_feedback_loop_ids", []):
                net["failed_feedback_loop_ids"] = sorted(
                    set(net.get("failed_feedback_loop_ids", [])) | {loop})
                net["network_failure_sequence"] = list(net.get("network_failure_sequence", [])) + [loop]
        net["failed_hard_limit_ids"] = sorted(set(violated))
        # Energy shortage throttles repair capacities (no free repair).
        if float(net.get("energy_budget", 1.0)) < 0.2 * float(limits.get("energy_budget_initial", 30.0)):
            for pid in ORGAN_PROXIES:
                proxies[pid]["repair_capacity"] = max(
                    0.0, float(proxies[pid].get("repair_capacity", 0.0)) * (1.0 - 0.05 * dt))

    def _apply_network_effect_costs(self, effect: dict[str, Any]) -> None:
        """Energy/mutation/toxicity/niche pricing for one effect (Stage 6B)."""
        from longevity.model.organ_network import PROLIFERATIVE_TYPES  # deferred

        s = self.state
        net = s.organ_network
        assert net is not None
        limits = net.get("hard_limits", {})
        intensity = max(0.0, float(effect.get("intensity", 1.0)))
        net["energy_budget"] = max(
            0.0, float(net.get("energy_budget", 0.0))
            - float(limits.get("energy_per_intervention", 0.10)) * intensity)
        toxicity = float(limits.get("toxicity_per_intensity", 0.05)) * intensity
        if str(effect.get("intervention_type", "")) in PROLIFERATIVE_TYPES:
            toxicity *= 2.0
        net["intervention_toxicity"] = max(0.0, float(net.get("intervention_toxicity", 0.0)) + toxicity)
        itype = str(effect.get("intervention_type", ""))
        mutation_delta = {
            "telomere_maintenance": 0.020,
            "stem_niche_restoration": 0.020,
            "epigenetic_reprogramming_pulse": 0.030,
            "regenerative_boost": 0.020,
            "cellular_replacement": 0.005,
        }.get(itype, 0.0) * intensity
        # Cancer surveillance cannot erase load; it only slows growth
        # (operational: partial mitigation, never full compensation).
        if itype in ("cancer_surveillance", "cancer_surveillance_boost"):
            net["mutation_load"] = max(0.0, float(net.get("mutation_load", 0.0)) - 0.002 * intensity)
        net["mutation_load"] = max(0.0, float(net.get("mutation_load", 0.0)) + mutation_delta)
        if itype in ("stem_niche_restoration", "regenerative_boost",
                     "epigenetic_reprogramming_pulse"):
            net["niche_disorder"] = max(
                0.0, float(net.get("niche_disorder", 0.0))
                + float(limits.get("niche_disorder_per_stem", 0.03)) * intensity)
        # Information preservation: aggressive reprogramming harms continuity;
        # continuity cannot be freely restored (capped trickle only).
        if itype == "epigenetic_reprogramming_pulse" and s.organ_backed is not None:
            brain = s.organ_backed["proxies"].get("brain_cns_proxy")
            if brain is not None:
                brain["informational_continuity"] = max(
                    0.0, min(1.0, float(brain.get("informational_continuity", 1.0))
                             - 0.005 * intensity))

    def _scale_effect(self, effect: dict[str, Any]) -> dict[str, Any]:
        """Apply efficacy scale + noise to an effect (Stage 5B, deterministic)."""
        if self.perturbation["model"] == "none":
            return effect
        scaled = dict(effect)
        factor = float(self.perturbation["efficacy_scale"])
        noise = float(self.perturbation["intervention_efficacy_noise_scale"])
        if noise > 0.0:
            factor *= max(0.0, 1.0 + noise * self.perturb_rng.gauss(0.0, 1.0))
        for key, value in scaled.items():
            if key.startswith("delta_") and isinstance(value, (int, float)) and not isinstance(value, bool):
                scaled[key] = float(value) * factor
        for key, value in scaled.items():
            if key.startswith("organ_delta_") and isinstance(value, (int, float)) \
                    and not isinstance(value, bool):
                scaled[key] = float(value) * factor
        for key, value in scaled.items():
            if key.startswith("rev_") and isinstance(value, (int, float)) \
                    and not isinstance(value, bool):
                scaled[key] = float(value) * factor
        return scaled

    def step(self, dt: float, bounds: dict[str, float], thresholds: dict[str, Any],
             effects: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        """Advance one time step: develop, age, shock, intervene, check death."""
        s = self.state
        if not s.alive:
            return {"died": False, "already_dead": True, "causes": []}
        s.time += dt
        s.chronological_age += dt
        s.developmental_stage = stage_for_age(s.chronological_age, bounds)
        if s.developmental_stage == "late_aging" and s.chronological_age >= bounds["age_early_aging_end"] + 25.0:
            s.developmental_stage = "terminal_decline"
        self._development_step(dt, bounds)
        self._aging_step(dt, s.developmental_stage)
        if self.organ_backed_model == "reduced_organ_proxies":
            assert s.organ_backed is not None
            self._organ_backed_step(dt, s.developmental_stage)
        if self.organ_network_model == "reduced_network_feedback":
            assert s.organ_network is not None
            assert s.organ_backed is not None
            self._organ_network_step(dt, s.developmental_stage)
        if self.reversibility_model == "split_reversible_irreversible":
            assert s.reversibility is not None
            self._reversibility_step(dt, s.developmental_stage)
        new_shocks = self._maybe_shock(dt)
        self._apply_active_shocks(dt)
        applied = []
        coordination_detail: dict[str, Any] = {}
        if self.organ_backed_model == "reduced_organ_proxies":
            effects, coordination_detail = self._coordinate_effects(list(effects or []))
        else:
            effects = effects or []
        for effect in effects:
            applied.append(self.apply_effect(self._scale_effect(effect), effect.get("source", "policy")))
        if self.organ_backed_model == "reduced_organ_proxies":
            # Organ-targeted repairs must be visible to systems immediately.
            self._map_proxies_to_systems()
        if self.organ_network_model == "reduced_network_feedback" and s.organ_network is not None \
                and s.organ_backed is not None:
            # Network coupling must be visible to systems immediately.
            self._map_proxies_to_systems()
        s.vitality_index = self._vitality()
        s.functional_reserve = self._clamp01(sum(
            float(s.systems[name]["function"]) for name in VITAL_SYSTEMS) / len(VITAL_SYSTEMS))
        alive, violations = self.check_viability(thresholds)
        result: dict[str, Any] = {"died": False, "already_dead": False, "causes": violations,
                                   "applied": applied, "stage": s.developmental_stage,
                                   "shocks": [dict(sh) for sh in new_shocks],
                                   "coordination": coordination_detail}
        if not alive:
            s.alive = False
            s.death_time = s.chronological_age
            s.failure_cause = violations[0] if violations else "unknown"
            result["died"] = True
        self.step_count += 1
        assert_organism_invariants(s)
        return result

    def run(self, duration_years: float, dt: float, bounds: dict[str, float],
            thresholds: dict[str, Any], policy=None) -> list[dict[str, Any]]:
        """Run the life-course; stops at death. Returns snapshots (t0 first)."""
        if duration_years < 0:
            raise ValueError("duration_years must be >= 0")
        trajectory = [self.state.to_dict()]
        elapsed = 0.0
        while elapsed < duration_years - 1e-12 and self.state.alive:
            effects = policy.effects_for_age(self.state.chronological_age, self.state.to_dict()) if policy else []
            self.step(dt, bounds, thresholds, effects)
            trajectory.append(self.state.to_dict())
            elapsed += dt
        return trajectory

    # -- checkpoint / restore ----------------------------------------------
    def to_checkpoint_dict(self, policy_state: dict[str, Any] | None = None) -> dict[str, Any]:
        _, generator_state = self.rng.getstate()
        _, perturb_state = self.perturb_rng.getstate()
        _, shock_state = self.shock_rng.getstate()
        return {
            "model_version": ORGANISM_MODEL_VERSION,
            "model_scope": MODEL_SCOPE,
            "time": self.state.time,
            "step_count": self.step_count,
            "rng": {"seed": self.rng.seed, "generator_state": state_to_json(generator_state)},
            "perturb_rng": {"seed": self.perturb_rng.seed, "generator_state": state_to_json(perturb_state)},
            "shock_rng": {"seed": self.shock_rng.seed, "generator_state": state_to_json(shock_state)},
            "perturb_seed": self.perturb_seed,
            "parameters": copy.deepcopy(self.parameters),
            "perturbation": copy.deepcopy(self.perturbation),
            "aging_model": self.aging_model,
            "aging_drivers": copy.deepcopy(self.aging_drivers),
            "adult_age_setpoint": self.adult_age_setpoint,
            "allow_sub_adult_biological_age": self.allow_sub_adult_biological_age,
            "organ_backed_model": self.organ_backed_model,
            "organ_proxies": copy.deepcopy(self.organ_proxy_params),
            "systemic_resources": copy.deepcopy(self.resource_budgets),
            "coordination_mode": self.coordination_mode,
            "emergent_weights": copy.deepcopy(self.emergent_weights),
            "organ_network_model": self.organ_network_model,
            "organ_network_edges": copy.deepcopy(self.network_edges),
            "organ_network_feedback": copy.deepcopy(self.network_feedback_config),
            "organ_network_hard_limits": copy.deepcopy(self.network_hard_limits),
            "irreversible_thresholds": copy.deepcopy(self.irreversible_thresholds),
            "allow_sub_adult_network_age": self.allow_sub_adult_network_age,
            "reversibility_model": self.reversibility_model,
            "reversibility_params": copy.deepcopy(self.reversibility_params),
            "allow_sub_adult_reversibility_age": self.allow_sub_adult_reversibility_age,
            "boundary_probe_model": self.boundary_probe_model,
            "boundary_params": copy.deepcopy(self.boundary_params),
            "component_overrides": copy.deepcopy(self.component_overrides),
            "policy_cooldown": copy.deepcopy(policy_state) if policy_state is not None else {},
            "state": self.state.to_dict(),
        }

    @classmethod
    def from_checkpoint(cls, data: dict[str, Any], rng: Rng | None = None) -> "OrganismModel":
        from longevity.model.aging import validate_aging_drivers, validate_aging_model  # deferred
        from longevity.model.organ_backed import (  # deferred
            default_organ_backed_state,
            validate_coordination_mode,
            validate_emergent_weights,
            validate_organ_backed_model,
            validate_proxy_params,
            validate_resource_budgets,
        )
        from longevity.model.organ_network import (  # deferred
            default_organ_network_state,
            validate_feedback_config,
            validate_hard_limits,
            validate_irreversible_thresholds,
            validate_network_edges,
            validate_organ_network_model,
        )
        from longevity.model.reversibility import (  # deferred
            default_reversibility_state,
            validate_reversibility_model,
            validate_reversibility_params,
        )
        from longevity.model.boundary import (  # deferred
            _ablation_hash,
            default_boundary_state,
            effective_repair_ceiling,
            validate_boundary_params,
            validate_boundary_probe_model,
            validate_component_overrides,
        )

        model = cls.__new__(cls)
        model.state = OrganismState.from_dict(data["state"])
        assert_organism_invariants(model.state)
        model.parameters = validate_organism_parameters(dict(data["parameters"]))
        model.perturbation = validate_perturbation(dict(data.get("perturbation", {})))
        model.perturb_seed = int(data.get("perturb_seed", data["rng"]["seed"]))
        model.rng = rng or Rng(data["rng"]["seed"])
        model.rng.setstate((data["rng"]["seed"], state_from_json(data["rng"]["generator_state"])))
        if "perturb_rng" in data:
            model.perturb_rng = Rng(data["perturb_rng"]["seed"])
            model.perturb_rng.setstate((data["perturb_rng"]["seed"],
                                        state_from_json(data["perturb_rng"]["generator_state"])))
        else:  # legacy Stage 5A checkpoints predate perturbation streams
            model.perturb_rng = Rng(model.perturb_seed)
        if "shock_rng" in data:
            model.shock_rng = Rng(data["shock_rng"]["seed"])
            model.shock_rng.setstate((data["shock_rng"]["seed"],
                                      state_from_json(data["shock_rng"]["generator_state"])))
        else:
            model.shock_rng = Rng(model.perturb_seed + 1)
        model.step_count = int(data.get("step_count", 0))
        model.aging_model = validate_aging_model(data.get("aging_model", "none"))
        model.aging_drivers = validate_aging_drivers(data.get("aging_drivers", None))
        model.adult_age_setpoint = float(data.get("adult_age_setpoint", 25.0))
        model.allow_sub_adult_biological_age = bool(data.get("allow_sub_adult_biological_age", False))
        model.organ_backed_model = validate_organ_backed_model(data.get("organ_backed_model", "none"))
        model.organ_proxy_params = validate_proxy_params(data.get("organ_proxies", None))
        model.resource_budgets = validate_resource_budgets(data.get("systemic_resources", None))
        model.coordination_mode = validate_coordination_mode(
            data.get("coordination_mode", "independent_organ_policies"))
        model.emergent_weights = validate_emergent_weights(data.get("emergent_weights", None))
        model.organ_network_model = validate_organ_network_model(data.get("organ_network_model", "none"))
        model.network_edges = validate_network_edges(data.get("organ_network_edges", None))
        model.network_feedback_config = validate_feedback_config(data.get("organ_network_feedback", None))
        model.network_hard_limits = validate_hard_limits(data.get("organ_network_hard_limits", None))
        model.irreversible_thresholds = validate_irreversible_thresholds(data.get("irreversible_thresholds", None))
        model.allow_sub_adult_network_age = bool(data.get("allow_sub_adult_network_age", False))
        model.reversibility_model = validate_reversibility_model(data.get("reversibility_model", "none"))
        model.reversibility_params = validate_reversibility_params(data.get("reversibility_params", None))
        model.allow_sub_adult_reversibility_age = bool(
            data.get("allow_sub_adult_reversibility_age", False))
        model.boundary_probe_model = validate_boundary_probe_model(data.get("boundary_probe_model", "none"))
        model.boundary_params = validate_boundary_params(data.get("boundary_params", None))
        model.component_overrides = validate_component_overrides(data.get("component_overrides", None))
        if model.aging_model == "mechanistic_drivers" and model.state.aging is None:
            from longevity.model.aging import default_driver_state  # deferred

            model.state.aging = default_driver_state()
        if model.organ_backed_model == "reduced_organ_proxies" and model.state.organ_backed is None:
            model.state.organ_backed = default_organ_backed_state()
            model.state.organ_backed["resources"]["budgets"] = dict(model.resource_budgets)
        if model.organ_network_model == "reduced_network_feedback" and model.state.organ_network is None:
            model.state.organ_network = default_organ_network_state()
            model.state.organ_network["edges"] = [
                {**dict(e), "utilization": 0.0, "failure_risk": 0.0, "failed": False}
                for e in model.network_edges
            ]
            model.state.organ_network["hard_limits"] = dict(model.network_hard_limits)
            model.state.organ_network["irreversible_thresholds"] = dict(model.irreversible_thresholds)
        if model.reversibility_model == "split_reversible_irreversible" \
                and model.state.reversibility is None:
            model.state.reversibility = default_reversibility_state()
            model.state.reversibility["repair_ceiling"] = float(
                model.reversibility_params["repair_ceiling"])
            model.state.reversibility["repair_remaining"] = float(
                model.reversibility_params["repair_ceiling"])
        if model.boundary_probe_model == "irreversibility_ablation" \
                and model.state.boundary is None:
            from longevity.model.boundary import _ablation_hash as _bh  # deferred

            exploratory = bool(model.boundary_params.get("force_repair_ceiling_unlimited", False)
                               or model.boundary_params.get("disable_repair_ceiling", False))
            model.state.boundary = {
                "params": dict(model.boundary_params),
                "overrides": [dict(o) for o in model.component_overrides],
                "exploratory": exploratory,
                "ablation_flags_hash": _bh(model.boundary_params, model.component_overrides),
            }
        return model


DEFAULT_ORGANISM_PARAMETERS: dict[str, Any] = {
    "damage_rate": 0.0025,
    "senescence_rate": 0.0035,
    "inflammation_rate": 0.004,
    "inflammation_decay": 0.05,
    "fibrosis_rate": 0.002,
    "cancer_rate": 0.0012,
    "cancer_immune_control": 0.05,
    "epigenetic_rate": 0.004,
    "proteostasis_decline": 0.002,
    "mito_decline": 0.002,
    "damage_coupling": 0.10,
    "development_growth": 0.35,
    "reserve_accrual": 0.06,
    "reserve_decay": 0.02,
    "body_growth": 0.5,
    "repair_reserve_cost": 0.4,
    "stochastic_jitter": 0.0,
}

_ORGANISM_PARAM_KEYS = tuple(DEFAULT_ORGANISM_PARAMETERS)


def validate_organism_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Validate organism dynamics parameters, filling documented defaults."""
    params = dict(DEFAULT_ORGANISM_PARAMETERS)
    params.update(parameters)
    unknown = set(params) - set(_ORGANISM_PARAM_KEYS)
    if unknown:
        raise ValueError(f"unknown organism parameters: {sorted(unknown)}")
    return {k: _require_number(params[k], f"organism.{k}", lo=0.0) for k in _ORGANISM_PARAM_KEYS}


def validate_perturbation(perturbation: dict[str, Any] | None) -> dict[str, Any]:
    """Validate the Stage 5B opt-in perturbation block (all neutral by default)."""
    if perturbation is None:
        perturbation = {}
    if not isinstance(perturbation, dict):
        raise ValueError(f"perturbation must be a dict, got {perturbation!r}")
    merged = dict(DEFAULT_PERTURBATION)
    merged.update(perturbation)
    unknown = set(merged) - set(DEFAULT_PERTURBATION)
    if unknown:
        raise ValueError(f"unknown perturbation keys: {sorted(unknown)}")
    if merged["model"] not in PERTURBATION_MODELS:
        raise ValueError(f"perturbation.model must be one of {PERTURBATION_MODELS}, got {merged['model']!r}")
    validated: dict[str, Any] = {"model": merged["model"]}
    for key in ("aging_noise_scale", "intervention_efficacy_noise_scale", "repair_capacity_noise_scale",
                "shock_probability_per_step", "shock_magnitude_scale", "efficacy_scale"):
        validated[key] = _require_number(merged[key], f"perturbation.{key}", lo=0.0)
    if not 0.0 <= validated["shock_probability_per_step"] <= 1.0:
        raise ValueError("perturbation.shock_probability_per_step must be in [0, 1]")
    duration = merged["shock_duration_steps"]
    if isinstance(duration, bool) or not isinstance(duration, int) or duration < 1:
        raise ValueError(f"perturbation.shock_duration_steps must be an int >= 1, got {duration!r}")
    validated["shock_duration_steps"] = duration
    seed = merged["perturb_seed"]
    if seed is not None and (isinstance(seed, bool) or not isinstance(seed, int)):
        raise ValueError(f"perturbation.perturb_seed must be an int or null, got {seed!r}")
    validated["perturb_seed"] = seed
    shock_types = merged.get("shock_types", None)
    if shock_types is not None:
        if not isinstance(shock_types, list) or not shock_types \
                or any(t not in SHOCK_TYPES for t in shock_types):
            raise ValueError(f"perturbation.shock_types must be a non-empty subset of {SHOCK_TYPES}")
        validated["shock_types"] = list(shock_types)
    else:
        validated["shock_types"] = None
    return validated
