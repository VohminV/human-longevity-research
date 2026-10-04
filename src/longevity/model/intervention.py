"""INTERVENTION LAYER: longevity intervention classes + policies (Stage 5A).

Interventions are broader than cell replacement: molecular repair, senescent
clearance, maintenance, systemic modulation, regenerative boost, neural
protection, cancer surveillance, recovery support. Each is a deterministic,
configurable effect dict applied by :class:`OrganismModel`; policies decide
*when* they fire. Pure planning, no global state.
"""

from __future__ import annotations

import math

from dataclasses import dataclass, field
from typing import Any

INTERVENTION_TYPES = (
    "molecular_repair",
    "cellular_replacement",
    "tissue_organ_maintenance",
    "systemic_modulation",
    "regenerative_boost",
    "neural_protection",
    "cancer_surveillance",
    "recovery_support",
    # Stage 5C mechanistic, driver-targeted interventions.
    "dna_repair_enhancement",
    "epigenetic_reprogramming_pulse",
    "proteostasis_enhancement",
    "mitochondrial_turnover",
    "telomere_maintenance",
    "senolytic_clearance",
    "senomorphic_modulation",
    "stem_niche_restoration",
    "anti_inflammatory_resolution",
    "fibrosis_reversal_support",
    "cancer_surveillance_boost",
    "neural_protective_maintenance",
)

TRIGGER_TYPES = ("periodic", "threshold_based")

# Per-type operational effect templates at intensity 1.0 (model
# assumptions, not measurements). Positive deltas heal/restore, negative
# deltas harm; risks ride along deliberately (no free lunch).
INTERVENTION_EFFECTS: dict[str, dict[str, float]] = {
    "molecular_repair": {
        "delta_damage": -0.02, "delta_damage_global": -0.010,
        "delta_epigenetic_drift": -0.004, "delta_proteostasis": 0.01,
        "delta_mitochondrial": 0.008, "delta_cancer": 0.0015,
        "delta_biological_age": -0.15,
    },
    "cellular_replacement": {
        "delta_damage": -0.008, "delta_senescence": -0.030, "delta_function": 0.010,
        "delta_reserve": -0.010, "delta_cancer": 0.002,
        "delta_biological_age": -0.10,
    },
    "tissue_organ_maintenance": {
        "delta_fibrosis": -0.012, "delta_damage_global": -0.006,
        "delta_inflammation": -0.006, "delta_reserve": -0.008,
        "delta_biological_age": -0.06,
        "organ_delta_ecm": 0.020, "organ_delta_vascular": 0.015,
        "organ_delta_fibrosis": -0.010,
        "organ_resource_cost": {"repair": 0.02},
    },
    "systemic_modulation": {
        "delta_inflammation": -0.020, "delta_damage_global": -0.004,
        "delta_mitochondrial": 0.004, "delta_reserve": -0.004,
        "delta_biological_age": -0.05,
    },
    "regenerative_boost": {
        "delta_reserve": 0.030, "delta_reserve_global": 0.010,
        "delta_function": 0.006, "delta_cancer": 0.004,
        "delta_biological_age": -0.04,
    },
    "neural_protection": {
        "delta_neural_continuity": 0.010, "delta_damage": -0.004,
        "delta_reserve": -0.006, "delta_biological_age": -0.02,
    },
    "cancer_surveillance": {
        "delta_cancer": -0.012, "delta_reserve": -0.006,
        "delta_inflammation": 0.002, "delta_biological_age": -0.02,
        "organ_delta_cancer_risk": -0.010,
        "organ_resource_cost": {"immune": 0.02},
    },
    "recovery_support": {
        "delta_reserve": 0.020, "delta_reserve_global": 0.015,
        "delta_damage_global": -0.005, "delta_inflammation": -0.005,
        "delta_proteostasis": 0.006, "delta_mitochondrial": 0.006,
        "delta_biological_age": -0.05,
        "organ_delta_recovery": 0.05,
        "organ_resource_cost": {"repair": 0.03, "metabolic": 0.02},
    },
    # --- Stage 5C mechanistic interventions (driver-targeted) ---
    "dna_repair_enhancement": {
        "delta_damage_global": -0.008, "delta_cancer": 0.001,
        "delta_biological_age": -0.08,
        "target_drivers": ["dna_damage"],
        "driver_repairs": {"dna_damage": 0.020},
        "driver_reversals": {"dna_damage": 0.010},
    },
    "epigenetic_reprogramming_pulse": {
        "delta_cancer": 0.006, "delta_reserve": -0.010,
        "delta_biological_age": -0.20,
        "target_drivers": ["epigenetic_drift", "proteostasis_loss", "cellular_senescence"],
        "driver_repairs": {"epigenetic_drift": 0.010},
        "driver_reversals": {"epigenetic_drift": 0.030, "proteostasis_loss": 0.005,
                             "cellular_senescence": 0.005},
        "delta_neural_continuity": -0.008,
    },
    "proteostasis_enhancement": {
        "delta_senescence": -0.004, "delta_inflammation": -0.004,
        "delta_reserve": -0.006, "delta_biological_age": -0.06,
        "target_drivers": ["proteostasis_loss"],
        "driver_repairs": {"proteostasis_loss": 0.020},
        "driver_reversals": {"proteostasis_loss": 0.008},
    },
    "mitochondrial_turnover": {
        "delta_damage_global": -0.004, "delta_inflammation": -0.003,
        "delta_cancer": 0.002, "delta_reserve": -0.006,
        "delta_biological_age": -0.05,
        "target_drivers": ["mitochondrial_dysfunction"],
        "driver_repairs": {"mitochondrial_dysfunction": 0.020},
        "driver_reversals": {"mitochondrial_dysfunction": 0.008},
    },
    "telomere_maintenance": {
        "delta_cancer": 0.008, "delta_biological_age": -0.05,
        "target_drivers": ["stem_exhaustion"],
        "driver_repairs": {"stem_exhaustion": 0.015},
        "driver_reversals": {"stem_exhaustion": 0.008},
    },
    "senolytic_clearance": {
        "delta_senescence": -0.030, "delta_inflammation": -0.006,
        "delta_reserve": -0.008, "delta_biological_age": -0.10,
        "target_drivers": ["cellular_senescence"],
        "driver_repairs": {},
        "driver_reversals": {"cellular_senescence": 0.030},
        "organ_delta_senescence": -0.020,
        "organ_resource_cost": {"immune": 0.02},
    },
    "senomorphic_modulation": {
        "delta_inflammation": -0.012, "delta_cancer": 0.003,
        "delta_biological_age": -0.04,
        "target_drivers": ["cellular_senescence", "chronic_inflammation"],
        "driver_repairs": {"cellular_senescence": 0.010, "chronic_inflammation": 0.010},
        "driver_reversals": {},
    },
    "stem_niche_restoration": {
        "delta_reserve_global": 0.008, "delta_cancer": 0.005,
        "delta_biological_age": -0.06,
        "target_drivers": ["stem_exhaustion"],
        "driver_repairs": {"stem_exhaustion": 0.020},
        "driver_reversals": {"stem_exhaustion": 0.008},
    },
    "anti_inflammatory_resolution": {
        "delta_inflammation": -0.020, "delta_fibrosis": -0.004,
        "delta_cancer": 0.002, "delta_biological_age": -0.05,
        "target_drivers": ["chronic_inflammation"],
        "driver_repairs": {"chronic_inflammation": 0.025},
        "driver_reversals": {"chronic_inflammation": 0.008},
    },
    "fibrosis_reversal_support": {
        "delta_fibrosis": -0.012, "delta_reserve": -0.010,
        "delta_biological_age": -0.05,
        "target_drivers": ["chronic_inflammation"],
        "driver_repairs": {"chronic_inflammation": 0.005},
        "driver_reversals": {},
    },
    "cancer_surveillance_boost": {
        "delta_cancer": -0.012, "delta_reserve": -0.006,
        "delta_biological_age": -0.02,
        "target_drivers": ["cancer_prone"],
        "driver_repairs": {},
        "driver_reversals": {"cancer_prone": 0.020},
    },
    "neural_protective_maintenance": {
        "delta_damage": -0.004, "delta_reserve": -0.006,
        "delta_biological_age": -0.02,
        "target_drivers": [],
        "driver_repairs": {},
        "driver_reversals": {},
        "delta_neural_continuity": 0.010,
        "organ_delta_continuity": 0.010,
    },
}

_EFFECT_KEYS = (
    "delta_damage", "delta_function", "delta_reserve", "delta_neural_continuity",
    "delta_damage_global", "delta_senescence", "delta_inflammation", "delta_fibrosis",
    "delta_cancer", "delta_epigenetic_drift", "delta_proteostasis", "delta_mitochondrial",
    "delta_biological_age", "delta_reserve_global",
)

# Stage 6A organ-proxy delta keys (operational, applied only when the
# organ-backed model is enabled; inert otherwise).
_ORGAN_EFFECT_KEYS = (
    "organ_delta_function", "organ_delta_damage", "organ_delta_senescence",
    "organ_delta_fibrosis", "organ_delta_cancer_risk", "organ_delta_ecm",
    "organ_delta_vascular", "organ_delta_immune", "organ_delta_reserve",
    "organ_delta_repair_capacity", "organ_delta_recovery", "organ_delta_continuity",
)


def validate_effect(effect: dict[str, Any]) -> dict[str, Any]:
    """Validate an intervention effect dict (finite numbers, known type)."""
    if not isinstance(effect, dict):
        raise ValueError(f"effect must be a dict, got {effect!r}")
    intervention_type = effect.get("intervention_type", "")
    if intervention_type not in INTERVENTION_TYPES:
        raise ValueError(f"unknown intervention_type {intervention_type!r}")
    target_systems = effect.get("target_systems", [])
    if not isinstance(target_systems, list) or not all(isinstance(t, str) for t in target_systems):
        raise ValueError("effect.target_systems must be a list of strings")
    unknown = set(effect) - set(_EFFECT_KEYS) - set(_ORGAN_EFFECT_KEYS) - {
        "intervention_type", "target_systems", "source", "intensity",
        "target_drivers", "driver_repairs", "driver_reversals",
        "pre_adult_firing", "target_organ_ids", "organ_resource_cost"}
    if unknown:
        raise ValueError(f"unknown effect keys: {sorted(unknown)}")
    cleaned: dict[str, Any] = {
        "intervention_type": intervention_type,
        "target_systems": list(target_systems),
        "source": str(effect.get("source", "")),
        "intensity": float(effect.get("intensity", 1.0)),
    }
    for key in _EFFECT_KEYS:
        value = effect.get(key, 0.0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"effect.{key} must be a number, got {value!r}")
        if not math.isfinite(float(value)):
            raise ValueError(f"effect.{key} must be finite, got {value!r}")
        cleaned[key] = float(value)
    for key in _ORGAN_EFFECT_KEYS:
        value = effect.get(key, 0.0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"effect.{key} must be a number, got {value!r}")
        if not math.isfinite(float(value)):
            raise ValueError(f"effect.{key} must be finite, got {value!r}")
        cleaned[key] = float(value)
    from longevity.model.aging import AGING_DRIVERS  # deferred: avoid import cycle
    from longevity.model.organ_backed import (  # deferred: avoid import cycle
        ORGAN_PROXIES,
        SYSTEMIC_RESOURCES,
    )

    target_drivers = effect.get("target_drivers", [])
    if not isinstance(target_drivers, list) or not all(isinstance(t, str) for t in target_drivers):
        raise ValueError("effect.target_drivers must be a list of strings")
    for driver in target_drivers:
        if driver not in AGING_DRIVERS:
            raise ValueError(f"unknown target driver {driver!r}")
    cleaned["target_drivers"] = list(target_drivers)
    for key in ("driver_repairs", "driver_reversals"):
        mapping = effect.get(key, {})
        if not isinstance(mapping, dict):
            raise ValueError(f"effect.{key} must be a dict")
        cleaned_mapping = {}
        for driver, amount in mapping.items():
            if driver not in AGING_DRIVERS:
                raise ValueError(f"unknown driver {driver!r} in effect.{key}")
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) \
                    or not math.isfinite(float(amount)) or float(amount) < 0.0:
                raise ValueError(f"effect.{key}[{driver}] must be finite and >= 0, got {amount!r}")
            cleaned_mapping[driver] = float(amount)
        cleaned[key] = cleaned_mapping
    pre_adult = effect.get("pre_adult_firing", False)
    if not isinstance(pre_adult, bool):
        raise ValueError("effect.pre_adult_firing must be a bool")
    cleaned["pre_adult_firing"] = pre_adult
    target_organs = effect.get("target_organ_ids", [])
    if not isinstance(target_organs, list) or not all(isinstance(t, str) for t in target_organs):
        raise ValueError("effect.target_organ_ids must be a list of strings")
    for pid in target_organs:
        if pid not in ORGAN_PROXIES:
            raise ValueError(f"unknown target organ {pid!r}")
    cleaned["target_organ_ids"] = list(target_organs)
    resource_cost = effect.get("organ_resource_cost", {})
    if not isinstance(resource_cost, dict):
        raise ValueError("effect.organ_resource_cost must be a dict")
    cleaned_cost = {}
    for resource, amount in resource_cost.items():
        if resource not in SYSTEMIC_RESOURCES:
            raise ValueError(f"unknown systemic resource {resource!r} in effect.organ_resource_cost")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) \
                or not math.isfinite(float(amount)) or float(amount) < 0.0:
            raise ValueError(f"effect.organ_resource_cost[{resource}] must be finite and >= 0, got {amount!r}")
        cleaned_cost[resource] = float(amount)
    cleaned["organ_resource_cost"] = cleaned_cost
    return cleaned


def build_effect(intervention_type: str, intensity: float = 1.0,
                 target_systems: list[str] | None = None, source: str = "",
                 target_organs: list[str] | None = None) -> dict[str, Any]:
    """Instantiate a configured effect dict from a type template (pure)."""
    if intervention_type not in INTERVENTION_TYPES:
        raise ValueError(f"unknown intervention_type {intervention_type!r}")
    if isinstance(intensity, bool) or not isinstance(intensity, (int, float)):
        raise ValueError(f"intensity must be a number, got {intensity!r}")
    if not math.isfinite(float(intensity)) or float(intensity) < 0.0:
        raise ValueError(f"intensity must be finite and >= 0, got {intensity!r}")
    template = INTERVENTION_EFFECTS[intervention_type]
    effect: dict[str, Any] = {
        "intervention_type": intervention_type,
        "target_systems": list(target_systems) if target_systems else [],
        "target_organ_ids": list(target_organs) if target_organs else [],
        "source": source,
        "intensity": float(intensity),
    }
    for key, value in template.items():
        if key == "target_drivers":
            effect[key] = list(value)
        elif key in ("driver_repairs", "driver_reversals", "organ_resource_cost"):
            effect[key] = {name: float(amount) * float(intensity) for name, amount in dict(value).items()}
        else:
            effect[key] = float(value) * float(intensity)
    return validate_effect(effect)


@dataclass(frozen=True)
class LongevityPolicy:
    """One longevity policy: when a given intervention fires (Stage 5A)."""

    policy_id: str = "natural"
    enabled: bool = True
    start_age: float = 20.0
    stop_age: float = 150.0
    trigger_type: str = "periodic"
    interval: float = 5.0
    intensity: float = 1.0
    intervention_type: str = "molecular_repair"
    target_systems: tuple = ()
    target_organs: tuple = ()
    biomarker: str = ""
    biomarker_threshold: float = 0.0
    max_cancer_allowed: float = 1.0
    min_reserve_required: float = 0.0
    allow_pre_adult: bool = False

    def __post_init__(self) -> None:
        if not self.policy_id or not isinstance(self.policy_id, str):
            raise ValueError("policy_id must be a non-empty string")
        if not isinstance(self.enabled, bool):
            raise ValueError("policy enabled must be a bool")
        for field_name in ("start_age", "stop_age", "interval", "intensity"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"policy.{field_name} must be a number, got {value!r}")
            if not math.isfinite(float(value)) or float(value) < 0.0:
                raise ValueError(f"policy.{field_name} must be finite and >= 0, got {value!r}")
        if float(self.stop_age) < float(self.start_age):
            raise ValueError("policy stop_age must be >= start_age")
        if self.trigger_type not in TRIGGER_TYPES:
            raise ValueError(f"policy trigger_type must be one of {TRIGGER_TYPES}, got {self.trigger_type!r}")
        if self.intervention_type not in INTERVENTION_TYPES:
            raise ValueError(f"unknown intervention_type {self.intervention_type!r}")
        if not isinstance(self.target_systems, (list, tuple)):
            raise ValueError("policy.target_systems must be a list")
        object.__setattr__(self, "target_systems", tuple(self.target_systems))
        if not isinstance(self.target_organs, (list, tuple)):
            raise ValueError("policy.target_organs must be a list")
        object.__setattr__(self, "target_organs", tuple(self.target_organs))
        from longevity.model.organ_backed import ORGAN_PROXIES  # deferred: avoid import cycle

        for pid in self.target_organs:
            if pid not in ORGAN_PROXIES:
                raise ValueError(f"unknown target organ {pid!r}")
        for field_name in ("biomarker_threshold", "max_cancer_allowed", "min_reserve_required"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise ValueError(f"policy.{field_name} must be finite, got {value!r}")
        if self.trigger_type == "threshold_based" and not self.biomarker:
            raise ValueError("threshold_based trigger requires a non-empty biomarker")
        if not isinstance(self.allow_pre_adult, bool):
            raise ValueError("policy.allow_pre_adult must be a bool")

    def is_due(self, age: float, state: dict[str, Any]) -> bool:
        """True when this policy fires at the given age/state (pure)."""
        if not self.enabled:
            return False
        if not (float(self.start_age) <= age <= float(self.stop_age)):
            return False
        if self.trigger_type == "periodic":
            if float(self.interval) <= 0.0:
                return False
            phase = (age - float(self.start_age)) / float(self.interval)
            return abs(phase - round(phase)) < 1e-9
        # threshold_based: fire while the biomarker exceeds its threshold.
        value = _biomarker_value(self.biomarker, state)
        return value > float(self.biomarker_threshold)

    def build_effect(self) -> dict[str, Any]:
        """Effect dict for one firing (pure)."""
        return build_effect(self.intervention_type, float(self.intensity),
                            list(self.target_systems), source=self.policy_id,
                            target_organs=list(self.target_organs))

    def allows(self, state: dict[str, Any]) -> bool:
        """Constraint gate: skip firing when safety bounds would break (pure)."""
        if float(state.get("cancer_burden", 0.0)) >= float(self.max_cancer_allowed):
            return False
        reserves = [float(info.get("reserve", 0.0)) for info in state.get("systems", {}).values()]
        if reserves and min(reserves) < float(self.min_reserve_required):
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id, "enabled": self.enabled,
            "start_age": float(self.start_age), "stop_age": float(self.stop_age),
            "trigger_type": self.trigger_type, "interval": float(self.interval),
            "intensity": float(self.intensity), "intervention_type": self.intervention_type,
            "target_systems": list(self.target_systems), "biomarker": self.biomarker,
            "target_organ_ids": list(self.target_organs),
            "biomarker_threshold": float(self.biomarker_threshold),
            "max_cancer_allowed": float(self.max_cancer_allowed),
            "min_reserve_required": float(self.min_reserve_required),
            "allow_pre_adult": bool(self.allow_pre_adult),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LongevityPolicy":
        return cls(
            policy_id=data.get("policy_id", "policy"),
            enabled=bool(data.get("enabled", True)),
            start_age=float(data.get("start_age", 20.0)),
            stop_age=float(data.get("stop_age", 150.0)),
            trigger_type=data.get("trigger_type", "periodic"),
            interval=float(data.get("interval", 5.0)),
            intensity=float(data.get("intensity", 1.0)),
            intervention_type=data.get("intervention_type", "molecular_repair"),
            target_systems=tuple(data.get("target_systems", ())),
            target_organs=tuple(data.get("target_organ_ids", data.get("target_organs", ()))),
            biomarker=data.get("biomarker", ""),
            biomarker_threshold=float(data.get("biomarker_threshold", 0.0)),
            max_cancer_allowed=float(data.get("max_cancer_allowed", 1.0)),
            min_reserve_required=float(data.get("min_reserve_required", 0.0)),
            allow_pre_adult=bool(data.get("allow_pre_adult", False)),
        )


PRE_ADULT_STAGES = ("embryo", "fetal", "infancy", "childhood", "adolescence")


def _biomarker_value(name: str, state: dict[str, Any]) -> float:
    """Read a named biomarker from a state snapshot (pure)."""
    if name in ("senescence_burden", "inflammation", "fibrosis", "cancer_burden",
                "global_damage", "epigenetic_drift", "biological_age", "vitality_index"):
        return float(state.get(name, 0.0))
    if name == "min_system_function":
        functions = [float(info.get("function", 1.0)) for info in state.get("systems", {}).values()]
        return min(functions) if functions else 1.0
    if name == "max_system_damage":
        damages = [float(info.get("damage", 0.0)) for info in state.get("systems", {}).values()]
        return max(damages) if damages else 0.0
    if name == "min_organ_function":
        proxies = (state.get("organ_backed") or {}).get("proxies", {})
        if not proxies:
            raise ValueError(f"biomarker {name!r} requires organ-backed state")
        return min(float(p.get("function", 1.0)) for p in proxies.values())
    if name == "min_resource_allocation":
        allocation = (state.get("organ_backed") or {}).get("resources", {}).get("allocation", {})
        if not allocation:
            raise ValueError(f"biomarker {name!r} requires organ-backed state")
        return min(float(v) for v in allocation.values())
    if name.startswith("organ:"):
        parts = name.split(":")
        if len(parts) != 3:
            raise ValueError(f"unknown biomarker {name!r}")
        _, pid, field = parts
        from longevity.model.organ_backed import ORGAN_PROXIES  # deferred

        if pid not in ORGAN_PROXIES:
            raise ValueError(f"unknown driver biomarker {name!r}")
        proxies = (state.get("organ_backed") or {}).get("proxies", {})
        if pid not in proxies:
            raise ValueError(f"biomarker {name!r} requires organ-backed state")
        if field not in ("function", "damage", "senescence_burden", "fibrosis",
                         "cancer_risk", "reserve", "ecm_quality", "vascular_quality",
                         "immune_pressure", "recovery_pending"):
            raise ValueError(f"unknown biomarker {name!r}")
        return float(proxies[pid].get(field, 0.0))
    if name.startswith("resource:"):
        parts = name.split(":")
        if len(parts) != 3 or parts[2] != "allocation":
            raise ValueError(f"unknown biomarker {name!r}")
        from longevity.model.organ_backed import SYSTEMIC_RESOURCES  # deferred

        if parts[1] not in SYSTEMIC_RESOURCES:
            raise ValueError(f"unknown biomarker {name!r}")
        allocation = (state.get("organ_backed") or {}).get("resources", {}).get("allocation", {})
        if parts[1] not in allocation:
            raise ValueError(f"biomarker {name!r} requires organ-backed state")
        return float(allocation[parts[1]])
    if name.startswith("driver:"):
        driver = name.split(":", 1)[1]
        drivers = (state.get("aging") or {}).get("drivers", {})
        if driver not in drivers:
            raise ValueError(f"unknown driver biomarker {name!r}")
        return float(drivers[driver].get("damage", 0.0))
    raise ValueError(f"unknown biomarker {name!r}")


class PolicySet:
    """An ordered set of longevity policies evaluated each step (Stage 5A).

    Threshold-triggered policies observe ``interval`` as a refractory
    cooldown between firings (otherwise they would fire every integration
    step while above threshold, an incomparable dose vs periodic schedules).
    Firing history makes this object stateful but still fully deterministic:
    fixed policy order, no randomness.
    """

    def __init__(self, policies: list[dict[str, Any] | LongevityPolicy] | None = None):
        self.policies = [
            p if isinstance(p, LongevityPolicy) else LongevityPolicy.from_dict(dict(p))
            for p in (policies or [])
        ]
        self._last_fired: dict[str, float] = {}

    def effects_for_age(self, age: float, state: dict[str, Any]) -> list[dict[str, Any]]:
        """Due + allowed effects at this age/state (updates firing history).

        Rejuvenation-class policies stay out of development unless explicitly
        allowed: firing pre-adult without ``allow_pre_adult`` is skipped, and
        firing with it carries a teratogenic drift proxy flag handled by the
        model layer.
        """
        effects = []
        pre_adult = state.get("developmental_stage", "") in PRE_ADULT_STAGES
        for policy in self.policies:
            if pre_adult and not policy.allow_pre_adult:
                continue
            if policy.trigger_type == "threshold_based":
                last = self._last_fired.get(policy.policy_id, float("-inf"))
                if age - last < float(policy.interval):
                    continue
                if policy.is_due(age, state) and policy.allows(state):
                    effects.append(policy.build_effect())
                    self._last_fired[policy.policy_id] = age
                    if pre_adult:
                        effects[-1] = dict(effects[-1], pre_adult_firing=True)
            else:
                if policy.is_due(age, state) and policy.allows(state):
                    effects.append(policy.build_effect())
                    if pre_adult:
                        effects[-1] = dict(effects[-1], pre_adult_firing=True)
        return effects

    def to_state_dict(self) -> dict[str, Any]:
        """Serializable refractory/cooldown state (Stage 5B checkpoint support)."""
        return {"last_fired": {pid: float(age) for pid, age in self._last_fired.items()}}

    def load_state_dict(self, data: dict[str, Any]) -> None:
        """Restore refractory state (legacy/empty dicts start clean)."""
        self._last_fired = {str(pid): float(age) for pid, age in dict(data.get("last_fired", {})).items()}
