"""ORGAN-NETWORK MODEL LAYER: cross-organ graph + feedback + hard limits (Stage 6B).

Abstract, operational, non-calibrated. Adds an opt-in network over the
Stage 6A reduced organ proxies:

- directed edges (vascular/immune/metabolic/endocrine/neural/
  inflammatory/fibrosis/cancer-seeding/repair-flow) with weight/delay/gain
  and failure thresholds;
- seven systemic feedback loops with deterministic gains and runaway
  detection;
- hard physical/informational limits (energy, information preservation,
  mutation ceiling, irreversible damage, niche integrity, toxicity);
- network-derived biological age with adult-setpoint floor.

``none`` mode is behaviorally inert by construction: no state, no dynamics,
no coordination change. All helpers are pure; state lives in
``OrganismState.organ_network``.
"""

from __future__ import annotations

import math

from typing import Any

ORGAN_NETWORK_MODELS = ("none", "reduced_network_feedback")
ORGAN_NETWORK_SCOPE = "abstract_organ_network_organism_life_course"

EDGE_TYPES = (
    "vascular_dependency",
    "immune_dependency",
    "metabolic_dependency",
    "endocrine_signal",
    "neural_signal",
    "inflammatory_spread",
    "fibrosis_spread",
    "cancer_seeding_risk",
    "repair_resource_flow",
)

FEEDBACK_LOOPS = (
    "inflammation_damage_loop",
    "immune_exhaustion_loop",
    "metabolic_repair_loop",
    "vascular_support_loop",
    "neural_identity_loop",
    "cancer_surveillance_loop",
    "fibrosis_stiffness_loop",
)

NETWORK_DEATH_CAUSES = (
    "network_cascade_failure",
    "energy_exhaustion",
    "information_loss",
    "mutation_load_failure",
    "feedback_runaway",
    "bottleneck_edge_failure",
    "critical_organ_cascade",
    "hard_limit_violation",
    "unknown_network_collapse",
)

NETWORK_COORDINATION_MODES = (
    "independent_network",
    "network_bottleneck_priority",
    "cascade_guard",
    "information_preservation_priority",
    "mutation_load_guard",
    "lookahead_network",
    "deferral_network",
)

# global_resource_aware_scaling already exists in Stage 6A and is reused.

ORGAN_NETWORK_SHOCK_TYPES = (
    "edge_failure",
    "feedback_amplification",
    "energy_shortage",
)

PROLIFERATIVE_TYPES = (
    "regenerative_boost",
    "stem_niche_restoration",
    "telomere_maintenance",
    "epigenetic_reprogramming_pulse",
    "cellular_replacement",
)

DEFAULT_EDGES: list[dict[str, Any]] = [
    {"edge_id": "cardio_vascular_to_respiratory", "source": "cardiovascular_proxy",
     "target": "respiratory_proxy", "edge_type": "vascular_dependency",
     "weight": 0.03, "delay_steps": 1, "gain": 1.0,
     "failure_threshold": 0.6, "protection_sensitivity": 0.5},
    {"edge_id": "cardio_vascular_to_renal", "source": "cardiovascular_proxy",
     "target": "renal_proxy", "edge_type": "vascular_dependency",
     "weight": 0.03, "delay_steps": 1, "gain": 1.0,
     "failure_threshold": 0.6, "protection_sensitivity": 0.5},
    {"edge_id": "cardio_vascular_to_brain", "source": "cardiovascular_proxy",
     "target": "brain_cns_proxy", "edge_type": "vascular_dependency",
     "weight": 0.04, "delay_steps": 1, "gain": 1.0,
     "failure_threshold": 0.6, "protection_sensitivity": 0.6},
    {"edge_id": "immune_to_all_surveillance", "source": "immune_proxy",
     "target": "hepatic_proxy", "edge_type": "immune_dependency",
     "weight": 0.03, "delay_steps": 1, "gain": 1.0,
     "failure_threshold": 0.6, "protection_sensitivity": 0.5},
    {"edge_id": "immune_to_metabolic", "source": "immune_proxy",
     "target": "metabolic_proxy", "edge_type": "immune_dependency",
     "weight": 0.02, "delay_steps": 2, "gain": 1.0,
     "failure_threshold": 0.6, "protection_sensitivity": 0.4},
    {"edge_id": "metabolic_to_brain", "source": "metabolic_proxy",
     "target": "brain_cns_proxy", "edge_type": "metabolic_dependency",
     "weight": 0.03, "delay_steps": 1, "gain": 1.0,
     "failure_threshold": 0.6, "protection_sensitivity": 0.5},
    {"edge_id": "hepatic_to_immune_endocrine", "source": "hepatic_proxy",
     "target": "immune_proxy", "edge_type": "endocrine_signal",
     "weight": 0.02, "delay_steps": 2, "gain": 0.8,
     "failure_threshold": 0.7, "protection_sensitivity": 0.4},
    {"edge_id": "brain_neural_to_cardio", "source": "brain_cns_proxy",
     "target": "cardiovascular_proxy", "edge_type": "neural_signal",
     "weight": 0.02, "delay_steps": 1, "gain": 0.8,
     "failure_threshold": 0.7, "protection_sensitivity": 0.5},
    {"edge_id": "inflammation_immune_to_cardio", "source": "immune_proxy",
     "target": "cardiovascular_proxy", "edge_type": "inflammatory_spread",
     "weight": 0.03, "delay_steps": 1, "gain": 1.0,
     "failure_threshold": 0.6, "protection_sensitivity": 0.5},
    {"edge_id": "fibrosis_hepatic_to_renal", "source": "hepatic_proxy",
     "target": "renal_proxy", "edge_type": "fibrosis_spread",
     "weight": 0.02, "delay_steps": 2, "gain": 0.8,
     "failure_threshold": 0.7, "protection_sensitivity": 0.4},
    {"edge_id": "cancer_hepatic_seeding", "source": "hepatic_proxy",
     "target": "respiratory_proxy", "edge_type": "cancer_seeding_risk",
     "weight": 0.01, "delay_steps": 2, "gain": 0.6,
     "failure_threshold": 0.8, "protection_sensitivity": 0.6},
    {"edge_id": "repair_metabolic_to_muscle", "source": "metabolic_proxy",
     "target": "musculoskeletal_proxy", "edge_type": "repair_resource_flow",
     "weight": 0.02, "delay_steps": 1, "gain": 0.8,
     "failure_threshold": 0.7, "protection_sensitivity": 0.4},
]

DEFAULT_FEEDBACK_CONFIG: dict[str, dict[str, float]] = {
    loop: {"enabled": 1.0, "gain": 1.0} for loop in FEEDBACK_LOOPS
}

DEFAULT_HARD_LIMITS: dict[str, float] = {
    "max_mutation_load": 1.0,
    "min_informational_continuity": 0.5,
    "max_cascade_risk": 0.6,
    "energy_budget_initial": 30.0,
    "energy_drain_per_year": 0.05,
    "energy_per_intervention": 0.10,
    "max_intervention_toxicity": 3.0,
    "toxicity_per_intensity": 0.05,
    "toxicity_decay_per_year": 0.02,
    "niche_integrity_limit": 1.0,
    "niche_disorder_per_stem": 0.03,
    "max_feedback_gain": 0.8,
    "cascade_guard_threshold": 0.5,
    "mutation_guard_threshold": 0.7,
}

DEFAULT_IRREVERSIBLE_THRESHOLDS: dict[str, float] = {
    "brain_cns_proxy": 0.30,
    "cardiovascular_proxy": 0.20,
    "respiratory_proxy": 0.20,
    "hepatic_proxy": 0.25,
    "renal_proxy": 0.20,
    "immune_proxy": 0.25,
    "metabolic_proxy": 0.25,
    "musculoskeletal_proxy": 0.15,
}

DEFAULT_NETWORK_AGE_WEIGHTS: dict[str, float] = {
    "driver": 1.0,
    "organ_deficit": 12.0,
    "resource_shortfall": 3.0,
    "feedback_gain": 4.0,
    "mutation": 8.0,
    "information_loss": 12.0,
    "fibrosis": 6.0,
    "cancer": 8.0,
    "cascade": 8.0,
}

_EDGE_REQUIRED = ("edge_id", "source", "target", "edge_type", "weight",
                  "delay_steps", "gain", "failure_threshold",
                  "protection_sensitivity")


def _require_number(value: Any, path: str, lo: float | None = None,
                    hi: float | None = None) -> float:
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


def validate_organ_network_model(model: Any) -> str:
    if not isinstance(model, str) or model not in ORGAN_NETWORK_MODELS:
        raise ValueError(
            f"organ_network_model must be one of {ORGAN_NETWORK_MODELS}, got {model!r}")
    return model


def scope_for_network_model(mode: str) -> str:
    from longevity.model.organism import MODEL_SCOPE  # deferred

    return ORGAN_NETWORK_SCOPE if validate_organ_network_model(mode) != "none" else MODEL_SCOPE


def validate_network_edges(edges: Any) -> list[dict[str, Any]]:
    from longevity.model.organ_backed import ORGAN_PROXIES  # deferred

    if edges is None:
        edges = []
    if not isinstance(edges, list):
        raise ValueError(f"organ_network_edges must be a list, got {edges!r}")
    if not edges:
        return [dict(e) for e in DEFAULT_EDGES]
    seen: set[str] = set()
    validated: list[dict[str, Any]] = []
    for i, edge in enumerate(edges):
        if not isinstance(edge, dict):
            raise ValueError(f"organ_network_edges[{i}] must be a dict")
        missing = set(_EDGE_REQUIRED) - set(edge)
        if missing:
            raise ValueError(f"organ_network_edges[{i}] missing keys: {sorted(missing)}")
        unknown = set(edge) - set(_EDGE_REQUIRED)
        if unknown:
            raise ValueError(f"organ_network_edges[{i}] unknown keys: {sorted(unknown)}")
        edge_id = edge["edge_id"]
        if not isinstance(edge_id, str) or not edge_id:
            raise ValueError(f"organ_network_edges[{i}].edge_id must be non-empty string")
        if edge_id in seen:
            raise ValueError(f"duplicate edge_id {edge_id!r}")
        seen.add(edge_id)
        if edge["source"] not in ORGAN_PROXIES:
            raise ValueError(f"organ_network_edges[{i}].source unknown proxy {edge['source']!r}")
        if edge["target"] not in ORGAN_PROXIES:
            raise ValueError(f"organ_network_edges[{i}].target unknown proxy {edge['target']!r}")
        if edge["edge_type"] not in EDGE_TYPES:
            raise ValueError(f"organ_network_edges[{i}].edge_type must be one of {EDGE_TYPES}")
        validated.append({
            "edge_id": edge_id,
            "source": edge["source"],
            "target": edge["target"],
            "edge_type": str(edge["edge_type"]),
            "weight": _require_number(edge["weight"], f"edges[{i}].weight", lo=0.0, hi=1.0),
            "delay_steps": _require_delay(edge["delay_steps"], f"edges[{i}].delay_steps"),
            "gain": _require_number(edge["gain"], f"edges[{i}].gain", lo=0.0, hi=5.0),
            "failure_threshold": _require_number(edge["failure_threshold"],
                                                 f"edges[{i}].failure_threshold", lo=0.0, hi=1.0),
            "protection_sensitivity": _require_number(edge["protection_sensitivity"],
                                                      f"edges[{i}].protection_sensitivity",
                                                      lo=0.0, hi=1.0),
        })
    return validated


def _require_delay(value: Any, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0 or value > 20:
        raise ValueError(f"{path} must be an int in [0, 20], got {value!r}")
    return int(value)


def validate_feedback_config(feedback: Any) -> dict[str, dict[str, float]]:
    if feedback is None:
        feedback = {}
    if not isinstance(feedback, dict):
        raise ValueError(f"organ_network_feedback must be a dict, got {feedback!r}")
    unknown = set(feedback) - set(FEEDBACK_LOOPS)
    if unknown:
        raise ValueError(f"unknown feedback loops: {sorted(unknown)}")
    validated: dict[str, dict[str, float]] = {}
    for loop in FEEDBACK_LOOPS:
        block = dict(DEFAULT_FEEDBACK_CONFIG[loop])
        block.update(feedback.get(loop, {}))
        extra = set(block) - {"enabled", "gain"}
        if extra:
            raise ValueError(f"feedback {loop!r} unknown keys: {sorted(extra)}")
        enabled = block["enabled"]
        if isinstance(enabled, bool):
            enabled_f = 1.0 if enabled else 0.0
        else:
            enabled_f = _require_number(enabled, f"feedback.{loop}.enabled", lo=0.0, hi=1.0)
            enabled_f = 1.0 if enabled_f >= 0.5 else 0.0
        validated[loop] = {
            "enabled": enabled_f,
            "gain": _require_number(block["gain"], f"feedback.{loop}.gain", lo=0.0, hi=5.0),
        }
    return validated


def validate_hard_limits(limits: Any) -> dict[str, float]:
    if limits is None:
        limits = {}
    if not isinstance(limits, dict):
        raise ValueError(f"organ_network_hard_limits must be a dict, got {limits!r}")
    unknown = set(limits) - set(DEFAULT_HARD_LIMITS)
    if unknown:
        raise ValueError(f"unknown hard limit keys: {sorted(unknown)}")
    merged = dict(DEFAULT_HARD_LIMITS)
    merged.update(limits)
    validated: dict[str, float] = {}
    for key, value in merged.items():
        lo = 0.0
        hi = None
        if key in ("min_informational_continuity", "max_cascade_risk",
                   "cascade_guard_threshold", "mutation_guard_threshold"):
            hi = 1.0
        validated[key] = _require_number(value, f"hard_limits.{key}", lo=lo, hi=hi)
    return validated


def validate_irreversible_thresholds(thresholds: Any) -> dict[str, float]:
    from longevity.model.organ_backed import ORGAN_PROXIES  # deferred

    if thresholds is None:
        thresholds = {}
    if not isinstance(thresholds, dict):
        raise ValueError("irreversible_thresholds must be a dict")
    unknown = set(thresholds) - set(ORGAN_PROXIES)
    if unknown:
        raise ValueError(f"unknown irreversible threshold proxies: {sorted(unknown)}")
    merged = dict(DEFAULT_IRREVERSIBLE_THRESHOLDS)
    merged.update(thresholds)
    return {pid: _require_number(merged[pid], f"irreversible.{pid}", lo=0.0, hi=1.0)
            for pid in ORGAN_PROXIES}


def default_organ_network_state() -> dict[str, Any]:
    from longevity.model.organ_backed import ORGAN_PROXIES  # deferred

    limits = validate_hard_limits(None)
    return {
        "edges": [
            {**dict(e), "utilization": 0.0, "failure_risk": 0.0, "failed": False}
            for e in validate_network_edges(None)
        ],
        "nodes": {
            pid: {
                "incoming_demand": 0.0,
                "outgoing_support": 1.0,
                "feedback_inflammation": 0.0,
                "feedback_damage": 0.0,
                "feedback_repair": 0.0,
                "neural_dependency": 1.0 if pid == "brain_cns_proxy" else 0.3,
                "vascular_dependency": 0.6,
                "immune_dependency": 0.5,
                "metabolic_dependency": 0.5,
                "criticality": 1.0 if pid != "musculoskeletal_proxy" else 0.0,
                "irreversible_damage": 0.0,
                "information_relevance": 1.0 if pid == "brain_cns_proxy" else 0.0,
                "mutation_sensitivity": 0.6 if pid in ("hepatic_proxy", "immune_proxy",
                                                       "metabolic_proxy") else 0.4,
            }
            for pid in ORGAN_PROXIES
        },
        "feedback": {
            loop: {"enabled": cfg["enabled"], "configured_gain": cfg["gain"],
                   "gain_value": 0.0, "burden": 0.0}
            for loop, cfg in validate_feedback_config(None).items()
        },
        "pending_delays": [],
        "hard_limits": dict(limits),
        "irreversible_thresholds": dict(validate_irreversible_thresholds(None)),
        "energy_budget": float(limits["energy_budget_initial"]),
        "mutation_load": 0.0,
        "intervention_toxicity": 0.0,
        "niche_disorder": 0.0,
        "cascade_risk": 0.0,
        "max_cascade_risk_seen": 0.0,
        "information_loss_risk": 0.0,
        "network_age_contribution": 0.0,
        "biological_age_network": 25.0,
        "network_failure_sequence": [],
        "failed_edge_ids": [],
        "failed_feedback_loop_ids": [],
        "failed_hard_limit_ids": [],
        "coordination_stats": {"cascade_guard_rejections": 0,
                              "bottleneck_priority_executions": 0,
                              "mutation_guard_rejections": 0,
                              "information_priority_executions": 0},
    }


def validate_organ_network_state(state: Any) -> dict[str, Any] | None:
    if state is None:
        return None
    if not isinstance(state, dict):
        raise ValueError(f"organ_network state must be a dict or None, got {state!r}")
    edges = state.get("edges", [])
    if not isinstance(edges, list):
        raise ValueError("organ_network.edges must be a list")
    for i, edge in enumerate(edges):
        for key in ("utilization", "failure_risk"):
            _require_number(edge.get(key), f"organ_network.edges[{i}].{key}", lo=0.0, hi=5.0)
        if not isinstance(edge.get("failed"), bool):
            raise ValueError(f"organ_network.edges[{i}].failed must be a bool")
    for key in ("energy_budget", "mutation_load", "intervention_toxicity",
                "niche_disorder", "cascade_risk", "max_cascade_risk_seen",
                "information_loss_risk", "network_age_contribution",
                "biological_age_network"):
        _require_number(state.get(key), f"organ_network.{key}", lo=0.0)
    if not 0.0 <= float(state.get("cascade_risk", 0.0)) <= 1.0:
        raise ValueError("organ_network.cascade_risk out of [0, 1]")
    if not 0.0 <= float(state.get("information_loss_risk", 0.0)) <= 1.0:
        raise ValueError("organ_network.information_loss_risk out of [0, 1]")
    feedback = state.get("feedback", {})
    for loop in FEEDBACK_LOOPS:
        if loop not in feedback:
            raise ValueError(f"organ_network.feedback missing {loop!r}")
        _require_number(feedback[loop].get("gain_value"), f"organ_network.feedback.{loop}.gain_value",
                        lo=0.0)
    nodes = state.get("nodes", {})
    for pid, node in nodes.items():
        for key in ("incoming_demand", "outgoing_support", "feedback_inflammation",
                    "feedback_damage", "feedback_repair", "irreversible_damage"):
            _require_number(node.get(key), f"organ_network.nodes.{pid}.{key}", lo=0.0)
    pending = state.get("pending_delays", [])
    if not isinstance(pending, list):
        raise ValueError("organ_network.pending_delays must be a list")
    for key in ("network_failure_sequence", "failed_edge_ids",
                "failed_feedback_loop_ids", "failed_hard_limit_ids"):
        if not isinstance(state.get(key), list):
            raise ValueError(f"organ_network.{key} must be a list")
    stats = state.get("coordination_stats", {})
    for key in ("cascade_guard_rejections", "bottleneck_priority_executions",
                "mutation_guard_rejections", "information_priority_executions"):
        value = stats.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"organ_network.coordination_stats.{key} must be int >= 0")
    return state


def compute_feedback_gains(proxies: dict[str, Any], allocation: dict[str, float],
                           config: dict[str, dict[str, float]]) -> dict[str, float]:
    """Deterministic per-loop gain in [0, ~1] from current state (pure)."""
    def _mean(key: str) -> float:
        vals = [max(0.0, min(1.0, float(p.get(key, 0.0)))) for p in proxies.values()]
        return sum(vals) / max(1, len(vals))

    sen = _mean("senescence_burden")
    cancer = _mean("cancer_risk")
    damage = sum(max(0.0, float(p.get("damage", 0.0))) for p in proxies.values()) / max(1, len(proxies))
    immune_alloc = max(0.0, min(1.0, float(allocation.get("immune", 1.0))))
    repair_alloc = max(0.0, min(1.0, float(allocation.get("repair", 1.0))))
    perfusion_alloc = max(0.0, min(1.0, float(allocation.get("perfusion", 1.0))))
    brain = proxies.get("brain_cns_proxy", {})
    continuity = max(0.0, min(1.0, float(brain.get("informational_continuity", 1.0))))
    fibrosis = _mean("fibrosis")
    raw = {
        "inflammation_damage_loop": sen * 0.7 + damage * 0.3,
        "immune_exhaustion_loop": (sen + cancer) * 0.5 * (1.0 - immune_alloc),
        "metabolic_repair_loop": (1.0 - repair_alloc) * (0.4 + 0.6 * min(1.0, damage)),
        "vascular_support_loop": (1.0 - perfusion_alloc) * (0.4 + 0.6 * min(1.0, damage)),
        "neural_identity_loop": (1.0 - continuity) * 0.8 + (1.0 - perfusion_alloc) * 0.2,
        "cancer_surveillance_loop": cancer * (1.0 - immune_alloc * 0.7),
        "fibrosis_stiffness_loop": fibrosis * (0.5 + 0.5 * (1.0 - perfusion_alloc)),
    }
    gains = {}
    for loop in FEEDBACK_LOOPS:
        enabled = float(config.get(loop, {}).get("enabled", 1.0)) >= 0.5
        cfg_gain = float(config.get(loop, {}).get("gain", 1.0))
        gains[loop] = max(0.0, min(2.0, raw[loop] * cfg_gain)) if enabled else 0.0
    return gains


def compute_cascade_risk(proxies: dict[str, Any], allocation: dict[str, float],
                         feedback_gains: dict[str, float],
                         proxy_params: dict[str, dict[str, float]]) -> float:
    """Operational cascade risk in [0, 1] (pure)."""
    n = max(1, len(proxies))
    warnings = 0
    for pid, proxy in proxies.items():
        threshold = float(proxy_params.get(pid, {}).get("warning_threshold", 0.4))
        if float(proxy.get("function", 1.0)) < threshold:
            warnings += 1
    warning_frac = warnings / n
    shortfall = 1.0 - min(max(0.0, min(1.0, float(v))) for v in allocation.values()) \
        if allocation else 0.0
    shortfall = 1.0 - min(max(0.0, min(1.0, float(v))) for v in allocation.values()) \
        if allocation else 0.0
    max_gain = max(feedback_gains.values()) if feedback_gains else 0.0
    risk = 0.45 * warning_frac + 0.30 * max(0.0, min(1.0, shortfall)) \
        + 0.25 * max(0.0, min(1.0, max_gain))
    return max(0.0, min(1.0, risk))


def compute_network_age(adult_setpoint: float, driver_damages: dict[str, float],
                        driver_params: dict[str, dict[str, float]],
                        organ_deficit: float, resource_shortfall: float,
                        feedback_gain: float, mutation_load: float,
                        information_loss: float, fibrosis: float,
                        cancer: float, cascade: float,
                        weights: dict[str, float] | None = None,
                        allow_sub_adult: bool = False) -> tuple[float, float]:
    """Network-derived biological age (pure).

    Returns (biological_age_network, contribution). Floored at the adult
    setpoint unless sub-adult exploration is explicitly allowed.
    """
    weights = weights or dict(DEFAULT_NETWORK_AGE_WEIGHTS)
    driver_term = 0.0
    for name, damage in driver_damages.items():
        params = driver_params.get(name, {})
        reference = max(1e-9, float(params.get("adult_reference", 1.0)))
        contrib = float(params.get("contribution", 0.0))
        driver_term += contrib * max(0.0, float(damage)) / reference
    driver_term *= float(weights.get("driver", 1.0)) / max(1e-9, 8.0)
    # driver_term is mean contribution scaled to years-like units.
    contribution = (
        driver_term
        + float(weights.get("organ_deficit", 0.0)) * max(0.0, organ_deficit)
        + float(weights.get("resource_shortfall", 0.0)) * max(0.0, resource_shortfall)
        + float(weights.get("feedback_gain", 0.0)) * max(0.0, feedback_gain)
        + float(weights.get("mutation", 0.0)) * max(0.0, mutation_load)
        + float(weights.get("information_loss", 0.0)) * max(0.0, information_loss)
        + float(weights.get("fibrosis", 0.0)) * max(0.0, fibrosis)
        + float(weights.get("cancer", 0.0)) * max(0.0, cancer)
        + float(weights.get("cascade", 0.0)) * max(0.0, cascade)
    )
    total = float(adult_setpoint) + max(0.0, contribution)
    floor = 0.0 if allow_sub_adult else float(adult_setpoint)
    return (max(floor, total), max(0.0, contribution))


def coordinate_network_effects(effects: list[dict[str, Any]],
                               proxies: dict[str, Any],
                               allocation: dict[str, float],
                               mode: str,
                               queue: list[dict[str, Any]] | None = None,
                               network: dict[str, Any] | None = None) -> dict[str, Any]:
    """Network-aware coordination over organ-targeted effects (pure).

    Never mutates inputs. Deterministic tie-breaking (sorted proxy id,
    stable effect order). Unknown network context degrades gracefully to
    resource-only logic so legacy trajectories stay reproducible.
    """
    from longevity.model.organ_backed import _plan_relief_score  # deferred

    queue = [dict(entry) for entry in (queue or [])]
    network = dict(network or {})
    cascade = max(0.0, min(1.0, float(network.get("cascade_risk", 0.0))))
    mutation = max(0.0, float(network.get("mutation_load", 0.0)))
    max_mut = max(1e-9, float(network.get("hard_limits", {}).get("max_mutation_load", 1.0)))
    brain_cont = 1.0
    proxies_net = network.get("nodes", {})
    _ = proxies_net
    # Brain continuity read from proxies (authoritative) when present.
    if "brain_cns_proxy" in proxies:
        brain_cont = max(0.0, min(1.0, float(
            proxies["brain_cns_proxy"].get("informational_continuity", 1.0))))
    guard_threshold = float(network.get("hard_limits", {}).get("cascade_guard_threshold", 0.5))
    mut_threshold = float(network.get("hard_limits", {}).get("mutation_guard_threshold", 0.7))
    min_alloc = min(float(allocation.get(r, 1.0)) for r in allocation) if allocation else 1.0
    # Bottleneck = lowest-function proxy, tie-break by sorted id.
    bottleneck = None
    if proxies:
        bottleneck = sorted(proxies, key=lambda p: (float(proxies[p].get("function", 1.0)), p))[0]
    executed: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    pending = queue + [{"effect": dict(effect), "retries": 0} for effect in effects]
    detail: dict[str, Any] = {"mode": mode, "n_pending": len(pending),
                              "cascade_risk": cascade, "bottleneck": bottleneck}
    for entry in pending:
        effect = dict(entry["effect"])
        targets = effect.get("target_organ_ids") or sorted(proxies)
        itype = str(effect.get("intervention_type", ""))
        proliferative = itype in PROLIFERATIVE_TYPES
        harms_continuity = float(effect.get("delta_neural_continuity", 0.0)) < 0.0
        raises_damage = float(effect.get("organ_delta_damage", 0.0)) > 0.0 \
            or float(effect.get("organ_delta_cancer_risk", 0.0)) > 0.0
        if mode == "independent_network":
            executed.append(effect)
            continue
        if mode == "network_bottleneck_priority":
            hits_bottleneck = bottleneck is not None and bottleneck in targets
            if hits_bottleneck or min_alloc >= 0.5:
                executed.append(effect)
            elif int(entry.get("retries", 0)) >= 4:
                rejected.append(effect)
            else:
                deferred.append(entry)
            continue
        if mode == "cascade_guard":
            if cascade >= guard_threshold and (raises_damage or proliferative):
                if int(entry.get("retries", 0)) >= 4:
                    rejected.append(effect)
                else:
                    deferred.append(entry)
            elif min_alloc >= 0.4:
                executed.append(effect)
            elif int(entry.get("retries", 0)) >= 4:
                rejected.append(effect)
            else:
                deferred.append(entry)
            continue
        if mode == "information_preservation_priority":
            if harms_continuity and brain_cont < 0.7:
                if int(entry.get("retries", 0)) >= 4:
                    rejected.append(effect)
                else:
                    deferred.append(entry)
            else:
                executed.append(effect)
            continue
        if mode == "mutation_load_guard":
            if proliferative and (mutation / max_mut) >= mut_threshold and min_alloc < 0.8:
                if int(entry.get("retries", 0)) >= 4:
                    rejected.append(effect)
                else:
                    deferred.append(entry)
            else:
                executed.append(effect)
            continue
        if mode == "lookahead_network":
            score = _plan_relief_score(effect) - 2.0 * cascade * (1.0 if proliferative else 0.3) \
                - (1.0 - brain_cont) * (1.0 if harms_continuity else 0.0) \
                - (mutation / max_mut) * (1.0 if proliferative else 0.0)
            entry["relief_score"] = score
            if min_alloc >= 0.7 or score >= 0.005:
                executed.append(effect)
            elif int(entry.get("retries", 0)) >= 4:
                rejected.append(effect)
            else:
                deferred.append(entry)
            continue
        if mode == "deferral_network":
            if min_alloc >= 0.5 and cascade < 0.8:
                executed.append(effect)
            elif int(entry.get("retries", 0)) >= 4:
                rejected.append(effect)
            else:
                deferred.append(entry)
            continue
        raise ValueError(f"unknown network coordination mode {mode!r}")
    new_queue = []
    for entry in deferred:
        record: dict[str, Any] = {"effect": entry["effect"],
                                  "age": entry.get("age", 0.0),
                                  "retries": int(entry.get("retries", 0)) + 1}
        if "relief_score" in entry:
            record["relief_score"] = entry["relief_score"]
        new_queue.append(record)
    detail.update({"n_executed": len(executed), "n_deferred": len(new_queue),
                   "n_rejected": len(rejected), "min_allocation": min_alloc})
    return {"executed": executed, "deferred": [d["effect"] for d in deferred],
            "rejected": rejected, "queue": new_queue, "detail": detail}
