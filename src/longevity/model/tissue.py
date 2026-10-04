"""TISSUE MODEL LAYER: compartment state of one abstract tissue (Stage 3A).

This module is part of the BIOLOGICAL MODEL LAYER (see docs/ARCHITECTURE.md):
pure domain state and dynamics, no I/O and no GUI. The replacement *policy*
lives in :mod:`longevity.model.policy`; this module owns state mutation.

Scope (see docs/TISSUE_MODEL.md):
- ONE abstract tissue, modelled as compartment pools (floats), NOT as
  individual cells and NOT as an organism. Local tissue rejuvenation is not
  organism rejuvenation.
- Dynamics are deliberately minimal and deterministic given an injected RNG.
"""

from __future__ import annotations

import copy
import math

from dataclasses import dataclass, field
from typing import Any

from longevity.sim.rng import Rng, state_from_json, state_to_json

TISSUE_MODEL_VERSION = "0.3.0"

# ---------------------------------------------------------------------------
# Parameter defaults.
#
# These are MODEL assumptions (order-of-magnitude placeholders that make the
# dynamics qualitatively plausible), not measurements. Every default is
# documented here so a reader can trace each number to its scientific meaning
# (see docs/TISSUE_MODEL.md). tune only via TissueParams, never by editing
# call sites.
# ---------------------------------------------------------------------------
DEFAULT_DT = 1.0  # abstract tissue time-step; NOT hours, NOT days.

DEFAULT_TISSUE_PARAMETERS: dict[str, Any] = {
    # Per-step fractional fluxes between cell pools.
    "damage_rate": 0.01,  # functional -> damaged per functional cell per step.
    "sasp_damage_amplification": 1.5,  # senescent (SASP) amplify damage_rate.
    "senescence_rate": 0.02,  # damaged -> senescent per damaged cell per step.
    "damaged_recovery_rate": 0.05,  # damaged -> functional (repair) per step.
    "damaged_death_rate": 0.005,  # damaged -> dead per step.
    "clearance_rate": 0.05,  # senescent -> dead (natural immune clearance).
    "immune_clearance_impairment": 0.5,  # high immune_pressure impairs clearance.
    # Regeneration: stem -> functional, gated by niche quality.
    "differentiation_rate": 0.10,  # stem -> functional per stem cell per step.
    "stem_half_saturation": 200.0,  # stem level at half-maximal regeneration.
    "immune_regeneration_suppression": 0.5,  # inflamed niche suppresses regen.
    "stem_renewal_rate": 0.12,  # logistic self-renewal of the stem pool.
    "stem_capacity": 1000.0,  # carrying capacity of the stem niche.
    # Niche (ECM / vasculature / immune / fibrosis) dynamics.
    "ecm_decay_rate": 0.002,  # ECM erosion per step, worse when senescent.
    "ecm_repair_rate": 0.01,  # functional-driven ECM repair toward 1.
    "vascular_decay_rate": 0.001,  # vascular erosion per step (senescent-driven).
    "vascular_repair_rate": 0.002,  # functional-driven vascular repair toward 1.
    "immune_baseline": 0.1,  # resting immune pressure (healthy niche).
    "immune_activation_rate": 0.05,  # senescent-driven immune activation.
    "immune_decay_rate": 0.02,  # relaxation of immune pressure toward baseline.
    "fibrosis_rate": 0.01,  # senescent-driven fibrosis accumulation.
    "fibrosis_repair_rate": 0.002,  # slow fibrosis resolution.
    # Oncological cost of proliferation (differentiation + replacement).
    "cancer_proliferation_rate": 0.00001,  # risk per newly produced cell.
    "cancer_senescent_rate": 0.002,  # chronic SASP-driven risk per step.
    "cancer_repair_rate": 0.01,  # immune/DNA-repair control of risk.
    # Replacement side-effect costs, per replaced cell (see policy.py).
    "architecture_cost_per_cell": 0.0005,  # ECM damage per replaced cell.
    "immune_cost_per_cell": 0.0005,  # immune pressure per replaced cell.
    "cancer_cost_per_cell": 0.0001,  # cancer-risk increment per replaced cell.
    "fibrosis_cost_per_cell": 0.0001,  # fibrosis increment per replaced cell.
    "external_bank_immune_multiplier": 2.0,  # allogeneic source inflames more.
    # Stochasticity (0 = fully deterministic ODE-like dynamics).
    "stochastic_jitter": 0.0,  # relative gauss noise on fluxes; needs RNG.
}

TISSUE_PARAM_KEYS = tuple(DEFAULT_TISSUE_PARAMETERS) + ("dt",)
# Params that must lie in [0, 1] when used as fractions/rates.
_FRACTION_KEYS = (
    "damage_rate",
    "senescence_rate",
    "damaged_recovery_rate",
    "damaged_death_rate",
    "clearance_rate",
    "immune_clearance_impairment",
    "differentiation_rate",
    "immune_regeneration_suppression",
    "stem_renewal_rate",
    "ecm_decay_rate",
    "ecm_repair_rate",
    "vascular_decay_rate",
    "vascular_repair_rate",
    "immune_baseline",
    "immune_activation_rate",
    "immune_decay_rate",
    "fibrosis_rate",
    "fibrosis_repair_rate",
    "cancer_repair_rate",
    "stochastic_jitter",
)
# Params that must simply be >= 0 (scales, capacities, per-cell costs).
_NONNEGATIVE_KEYS = (
    "sasp_damage_amplification",
    "stem_half_saturation",
    "stem_capacity",
    "cancer_proliferation_rate",
    "cancer_senescent_rate",
    "architecture_cost_per_cell",
    "immune_cost_per_cell",
    "cancer_cost_per_cell",
    "fibrosis_cost_per_cell",
    "external_bank_immune_multiplier",
)

# Normalized quality fields of TissueState: always clamped to [0, 1].
QUALITY_FIELDS = ("ecm_quality", "vascular_quality", "immune_pressure")
# Risk indices: bounded to [0, 1] so they stay comparable across runs.
RISK_FIELDS = ("cancer_risk", "fibrosis_index")
# Cell pools: compartment counts, always >= 0.
POOL_FIELDS = (
    "stem_cells",
    "functional_cells",
    "damaged_cells",
    "senescent_cells",
    "dead_cells",
)


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


def validate_tissue_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Validate a tissue parameter dict, filling documented defaults."""
    params = dict(DEFAULT_TISSUE_PARAMETERS)
    params.update(parameters)

    unknown = set(params) - set(TISSUE_PARAM_KEYS)
    if unknown:
        raise ValueError(f"unknown tissue parameters: {sorted(unknown)}")

    for key in _FRACTION_KEYS:
        _require_number(params[key], f"tissue.{key}", lo=0.0, hi=1.0)
    for key in _NONNEGATIVE_KEYS:
        _require_number(params[key], f"tissue.{key}", lo=0.0)
    _require_number(params.get("dt", DEFAULT_DT), "tissue.dt", lo=1e-9)
    params["dt"] = float(params.get("dt", DEFAULT_DT))
    return params


@dataclass
class TissueState:
    """Compartment state of one abstract tissue (float pools, not cells).

    Pools are floats because this is a population-compartment model: values
    represent expected cell counts in each compartment, not tracked individuals.
    """

    time: float = 0.0
    stem_cells: float = 500.0
    functional_cells: float = 8000.0
    damaged_cells: float = 200.0
    senescent_cells: float = 100.0
    dead_cells: float = 0.0
    ecm_quality: float = 0.9
    vascular_quality: float = 0.9
    immune_pressure: float = 0.1
    cancer_risk: float = 0.0
    fibrosis_index: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "stem_cells": self.stem_cells,
            "functional_cells": self.functional_cells,
            "damaged_cells": self.damaged_cells,
            "senescent_cells": self.senescent_cells,
            "dead_cells": self.dead_cells,
            "ecm_quality": self.ecm_quality,
            "vascular_quality": self.vascular_quality,
            "immune_pressure": self.immune_pressure,
            "cancer_risk": self.cancer_risk,
            "fibrosis_index": self.fibrosis_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TissueState":
        return cls(
            time=float(data.get("time", 0.0)),
            stem_cells=float(data.get("stem_cells", 0.0)),
            functional_cells=float(data.get("functional_cells", 0.0)),
            damaged_cells=float(data.get("damaged_cells", 0.0)),
            senescent_cells=float(data.get("senescent_cells", 0.0)),
            dead_cells=float(data.get("dead_cells", 0.0)),
            ecm_quality=float(data.get("ecm_quality", 1.0)),
            vascular_quality=float(data.get("vascular_quality", 1.0)),
            immune_pressure=float(data.get("immune_pressure", 0.0)),
            cancer_risk=float(data.get("cancer_risk", 0.0)),
            fibrosis_index=float(data.get("fibrosis_index", 0.0)),
        )


def tissue_invariant_violation(state: TissueState) -> str | None:
    """First violated tissue invariant, or None when the state is physical."""
    for name in POOL_FIELDS:
        value = getattr(state, name)
        if not math.isfinite(value):
            return f"{name} is not finite: {value!r}"
        if value < 0.0:
            return f"{name} is negative: {value!r}"
    for name in QUALITY_FIELDS + RISK_FIELDS:
        value = getattr(state, name)
        if not math.isfinite(value):
            return f"{name} is not finite: {value!r}"
        if not 0.0 <= value <= 1.0:
            return f"{name} out of [0, 1]: {value!r}"
    if not math.isfinite(state.time) or state.time < 0.0:
        return f"time is invalid: {state.time!r}"
    return None


def assert_tissue_invariants(state: TissueState) -> None:
    violation = tissue_invariant_violation(state)
    if violation is not None:
        raise AssertionError(f"tissue invariant violated: {violation}")


@dataclass(frozen=True)
class TissueStepContext:
    """Per-step organ environment for one tissue (Stage 4A, operational).

    Carried from the organ layer into :meth:`TissueModel.step`; ``None``
    (the default everywhere) reproduces the exact Stage 3A dynamics. All
    effects are multiplicative/additive gates documented as model
    assumptions (see ``docs/ORGAN_MODEL.md``), not biological measurements:

    - ``effective_vascular_support`` in [0, 1] scales niche-gated
      regeneration (1 = full perfusion, 0 = no regeneration);
    - ``effective_immune_support`` in [0, 1] scales senescent clearance
      efficiency (1 = full surveillance, 0 = no clearance);
    - ``systemic_damage_modifier`` >= 0 amplifies the damage flux
      (0 = no systemic load).
    """

    effective_vascular_support: float = 1.0
    effective_immune_support: float = 1.0
    systemic_damage_modifier: float = 0.0

    def __post_init__(self) -> None:
        for name in ("effective_vascular_support", "effective_immune_support"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"context.{name} must be a number, got {value!r}")
            numeric = float(value)
            if not math.isfinite(numeric) or not 0.0 <= numeric <= 1.0:
                raise ValueError(f"context.{name} must be in [0, 1], got {value!r}")
        modifier = self.systemic_damage_modifier
        if isinstance(modifier, bool) or not isinstance(modifier, (int, float)):
            raise ValueError(f"context.systemic_damage_modifier must be a number, got {modifier!r}")
        if not math.isfinite(float(modifier)) or float(modifier) < 0.0:
            raise ValueError("context.systemic_damage_modifier must be finite and >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "effective_vascular_support": float(self.effective_vascular_support),
            "effective_immune_support": float(self.effective_immune_support),
            "systemic_damage_modifier": float(self.systemic_damage_modifier),
        }


def regeneration_capacity(state: TissueState, params: dict[str, Any]) -> float:
    """Niche-gated regeneration capacity in [0, 1].

    Biological reading: stem cells can only rebuild functional tissue when the
    niche supports them -- enough stem cells (saturating), perfused vasculature,
    intact ECM, and low inflammatory pressure. Multiplicative form: every factor
    is necessary, none is sufficient alone (documented assumption T-4).
    """
    stem_factor = state.stem_cells / (state.stem_cells + float(params["stem_half_saturation"]))
    niche = state.vascular_quality * state.ecm_quality
    calm = 1.0 - float(params["immune_regeneration_suppression"]) * state.immune_pressure
    return max(0.0, min(1.0, stem_factor * niche * max(0.0, calm)))


class TissueModel:
    """Executable compartment dynamics of one abstract tissue.

    Owns: current :class:`TissueState`, validated params, step counter,
    replacement counters, and the injected RNG. Never touches global random:
    the only stochasticity source is ``self.rng`` (used only when
    ``stochastic_jitter > 0``).

    One :meth:`step` = natural dynamics (damage/senescence/clearance/renewal)
    followed by at most one policy-driven replacement event executed from a
    :class:`ReplacementPlan`. Planning itself is the policy's job (pure, in
    :mod:`longevity.model.policy`); this class only executes.
    """

    def __init__(
        self,
        state: TissueState | None = None,
        parameters: dict[str, Any] | None = None,
        rng: Rng | None = None,
        seed: int = 0,
    ):
        self.state = state or TissueState()
        assert_tissue_invariants(self.state)
        self.parameters = validate_tissue_parameters(parameters or {})
        self.rng = rng if rng is not None else Rng(seed)
        self.step_count = 0
        self.replacement_events = 0
        self.total_replaced_cells = 0.0

    # -- internal helpers -------------------------------------------------
    def _jitter(self, flux: float) -> float:
        """Apply relative Gaussian noise to a flux (no-op when jitter == 0).

        When enabled, consumes exactly one RNG draw per call, so trajectories
        stay reproducible for a fixed seed and checkpoint/restore stays exact.
        """
        jitter = float(self.parameters["stochastic_jitter"])
        if jitter <= 0.0:
            return flux
        return max(0.0, flux * (1.0 + jitter * self.rng.gauss(0.0, 1.0)))

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    # -- natural dynamics -------------------------------------------------
    def _natural_dynamics(self, context: TissueStepContext | None = None) -> dict[str, float]:
        """Advance pools by one natural step; returns produced-cell counts.

        ``context=None`` reproduces the exact Stage 3A dynamics. A Stage 4A
        :class:`TissueStepContext` gates regeneration (vascular), clearance
        (immune) and damage (systemic load) as documented on the context.
        """
        p = self.parameters
        dt = float(p["dt"])
        s = self.state
        vascular_support = 1.0 if context is None else float(context.effective_vascular_support)
        immune_support = 1.0 if context is None else float(context.effective_immune_support)
        damage_modifier = 0.0 if context is None else float(context.systemic_damage_modifier)

        living = s.functional_cells + s.damaged_cells + s.senescent_cells
        senescent_fraction = s.senescent_cells / living if living > 0.0 else 0.0
        functional_fraction = s.functional_cells / living if living > 0.0 else 0.0

        # 1. Damage: functional -> damaged, amplified by senescent (SASP).
        # Stage 4A: systemic load from the organ layer amplifies damage.
        damage_flux = self._jitter(
            s.functional_cells
            * float(p["damage_rate"])
            * (1.0 + float(p["sasp_damage_amplification"]) * senescent_fraction)
            * (1.0 + damage_modifier)
            * dt
        )
        damage_flux = min(damage_flux, s.functional_cells)

        # 2. Damaged fates: senescence, repair back to functional, or death.
        senescence_flux = self._jitter(s.damaged_cells * float(p["senescence_rate"]) * dt)
        recovery_flux = self._jitter(s.damaged_cells * float(p["damaged_recovery_rate"]) * dt)
        damaged_death_flux = self._jitter(s.damaged_cells * float(p["damaged_death_rate"]) * dt)
        total_damaged_out = senescence_flux + recovery_flux + damaged_death_flux
        if total_damaged_out > s.damaged_cells and total_damaged_out > 0.0:
            scale = s.damaged_cells / total_damaged_out
            senescence_flux *= scale
            recovery_flux *= scale
            damaged_death_flux *= scale

        # 3. Natural clearance: senescent -> dead (impaired when inflamed).
        # Stage 4A: shared immune shortfall scales surveillance down.
        clearance_efficiency = 1.0 - float(p["immune_clearance_impairment"]) * s.immune_pressure
        clearance_flux = self._jitter(
            s.senescent_cells * float(p["clearance_rate"]) * max(0.0, clearance_efficiency) * immune_support * dt
        )
        clearance_flux = min(clearance_flux, s.senescent_cells)

        # 4. Regeneration: stem -> functional, gated by niche capacity.
        # Stage 4A: shared vascular shortfall throttles regeneration.
        capacity = regeneration_capacity(s, p) * vascular_support
        differentiation_flux = self._jitter(
            s.stem_cells * float(p["differentiation_rate"]) * capacity * dt
        )
        differentiation_flux = min(differentiation_flux, s.stem_cells)

        # 5. Stem self-renewal (logistic toward stem_capacity).
        renewal_flux = (
            float(p["stem_renewal_rate"]) * s.stem_cells * (1.0 - s.stem_cells / float(p["stem_capacity"])) * dt
        )

        s.functional_cells += recovery_flux + differentiation_flux - damage_flux
        s.damaged_cells += damage_flux - senescence_flux - recovery_flux - damaged_death_flux
        s.senescent_cells += senescence_flux - clearance_flux
        s.stem_cells += renewal_flux - differentiation_flux
        s.dead_cells += damaged_death_flux + clearance_flux

        produced = differentiation_flux + recovery_flux

        # 6. Niche: ECM / vasculature erode under senescent burden, repaired
        #    by functional tissue; immune pressure tracks senescent burden and
        #    relaxes toward baseline; fibrosis accumulates slowly.
        s.ecm_quality = self._clamp01(
            s.ecm_quality
            + float(p["ecm_repair_rate"]) * functional_fraction * (1.0 - s.ecm_quality) * dt
            - float(p["ecm_decay_rate"]) * (0.5 + senescent_fraction) * s.ecm_quality * dt
        )
        s.vascular_quality = self._clamp01(
            s.vascular_quality
            + float(p["vascular_repair_rate"]) * functional_fraction * (1.0 - s.vascular_quality) * dt
            - float(p["vascular_decay_rate"]) * (0.5 + senescent_fraction) * s.vascular_quality * dt
        )
        baseline = float(p["immune_baseline"])
        s.immune_pressure = self._clamp01(
            s.immune_pressure
            + float(p["immune_activation_rate"]) * senescent_fraction * dt
            - float(p["immune_decay_rate"]) * (s.immune_pressure - baseline) * dt
        )
        s.fibrosis_index = self._clamp01(
            s.fibrosis_index
            + float(p["fibrosis_rate"]) * senescent_fraction * dt
            - float(p["fibrosis_repair_rate"]) * s.fibrosis_index * dt
        )
        # 7. Cancer-risk index: rises with proliferation and chronic SASP
        #    exposure, controlled by repair/immune surveillance.
        s.cancer_risk = self._clamp01(
            s.cancer_risk
            + float(p["cancer_proliferation_rate"]) * produced
            + float(p["cancer_senescent_rate"]) * senescent_fraction * dt
            - float(p["cancer_repair_rate"]) * s.cancer_risk * dt
        )

        # Guard against float drift below zero before the invariant check.
        for name in POOL_FIELDS:
            if getattr(s, name) < 0.0:
                setattr(s, name, 0.0)

        s.time += dt
        self.step_count += 1
        return {"produced_cells": produced}

    # -- replacement execution --------------------------------------------
    def apply_replacement_plan(self, plan: Any) -> float:
        """Execute a :class:`ReplacementPlan`; returns cells actually replaced.

        Caps the plan by physically available cells (target pool, stem pool for
        ``stem_pool`` source). Removed target cells move to ``dead_cells``
        (elimination record); ``source_count`` new functional cells arrive from
        the source. Side-effect costs (ECM / immune / cancer / fibrosis) follow
        the per-cell coefficients in params, mitigated by the plan's control
        estimates carried on the plan itself.
        """
        from longevity.model.policy import ReplacementPlan  # deferred: avoid import cycle

        if not isinstance(plan, ReplacementPlan):
            raise ValueError(f"expected ReplacementPlan, got {type(plan)}")
        if plan.target_count <= 0.0:
            return 0.0

        p = self.parameters
        s = self.state
        pool_name = {"damaged": "damaged_cells", "senescent": "senescent_cells"}.get(plan.target)
        if pool_name is None:
            return 0.0
        available = getattr(s, pool_name)
        # The plan must never remove more cells than exist (invariant R-3).
        target_count = min(plan.target_count, available)
        if target_count <= 0.0:
            return 0.0

        # One-to-one replacement: the event is capped by BOTH the target pool
        # and the source. A stale/oversized plan therefore shrinks instead of
        # removing cells it cannot replace.
        if plan.source == "stem_pool":
            feasible = min(target_count, plan.source_count, s.stem_cells)
            s.stem_cells -= feasible
        elif plan.source == "external_bank":
            feasible = min(target_count, plan.source_count)
        else:
            return 0.0
        if feasible <= 0.0:
            return 0.0
        source_count = feasible

        setattr(s, pool_name, available - feasible)
        s.functional_cells += source_count
        s.dead_cells += feasible

        # Side-effect costs: the plan carries absolute expected deltas computed
        # for its full target_count; a capped execution scales them linearly.
        scale = feasible / plan.target_count if plan.target_count > 0.0 else 0.0
        s.ecm_quality = self._clamp01(s.ecm_quality - plan.expected_architecture_cost * scale)
        immune_multiplier = (
            float(p["external_bank_immune_multiplier"]) if plan.source == "external_bank" else 1.0
        )
        s.immune_pressure = self._clamp01(
            s.immune_pressure + plan.expected_immune_cost * immune_multiplier * scale
        )
        s.cancer_risk = self._clamp01(s.cancer_risk + plan.expected_cancer_risk_delta * scale)
        s.fibrosis_index = self._clamp01(s.fibrosis_index + plan.expected_fibrosis_delta * scale)
        # Replacement-driven proliferation also feeds the cancer index.
        s.cancer_risk = self._clamp01(
            s.cancer_risk + float(p["cancer_proliferation_rate"]) * source_count
        )

        self.replacement_events += 1
        self.total_replaced_cells += feasible
        assert_tissue_invariants(s)
        return feasible

    def step(self, policy: Any | None = None, context: TissueStepContext | None = None) -> Any:
        """Advance one step: natural dynamics, then one policy replacement.

        ``context`` is the optional Stage 4A organ environment; ``None``
        reproduces Stage 3A behavior exactly.
        """
        from longevity.model.policy import ReplacementPlan  # deferred: avoid import cycle

        self._natural_dynamics(context)
        if policy is None:
            return ReplacementPlan.empty()
        plan = policy.plan(self.state, self.parameters, self.step_count)
        self.apply_replacement_plan(plan)
        assert_tissue_invariants(self.state)
        return plan

    def run(
        self,
        steps: int,
        policy: Any | None = None,
        context: TissueStepContext | None = None,
    ) -> list[dict[str, Any]]:
        """Run ``steps`` steps; returns the per-step state trajectory (t0 first).

        A single ``context`` applies to every step; per-step contexts are
        passed via repeated :meth:`step` calls (as the organ layer does).
        """
        if steps < 0:
            raise ValueError("steps must be >= 0")
        trajectory = [self.state.to_dict()]
        for _ in range(steps):
            self.step(policy, context)
            trajectory.append(self.state.to_dict())
        return trajectory

    # -- checkpoint / restore (mirrors sim.engine conventions) -------------
    def to_checkpoint_dict(self) -> dict[str, Any]:
        _, generator_state = self.rng.getstate()
        return {
            "model_version": TISSUE_MODEL_VERSION,
            "time": self.state.time,
            "step_count": self.step_count,
            "rng": {"seed": self.rng.seed, "generator_state": state_to_json(generator_state)},
            "parameters": copy.deepcopy(self.parameters),
            "state": self.state.to_dict(),
            "counters": {
                "replacement_events": self.replacement_events,
                "total_replaced_cells": self.total_replaced_cells,
            },
        }

    @classmethod
    def from_checkpoint(cls, data: dict[str, Any], rng: Rng | None = None) -> "TissueModel":
        model = cls.__new__(cls)
        model.state = TissueState.from_dict(data["state"])
        assert_tissue_invariants(model.state)
        model.parameters = validate_tissue_parameters(dict(data["parameters"]))
        model.rng = rng or Rng(data["rng"]["seed"])
        model.rng.setstate((data["rng"]["seed"], state_from_json(data["rng"]["generator_state"])))
        model.step_count = int(data.get("step_count", 0))
        counters = data.get("counters", {})
        model.replacement_events = int(counters.get("replacement_events", 0))
        model.total_replaced_cells = float(counters.get("total_replaced_cells", 0.0))
        return model
