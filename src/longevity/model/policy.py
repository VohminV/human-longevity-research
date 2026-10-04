"""Replacement policy: PLANNING only (Stage 3A).

A :class:`ReplacementPolicy` decides *what* to replace, *from where*, *when*
and *how much* -- as a pure function of observable tissue state. It never
mutates state: execution (pool arithmetic, caps, side effects) belongs to
:class:`TissueModel.apply_replacement_plan`. This separation exists so the
choice logic can be unit-tested without running dynamics.
"""

from __future__ import annotations

import math

from dataclasses import dataclass
from typing import Any

VALID_TARGETS = ("none", "damaged", "senescent")
VALID_SOURCES = ("none", "stem_pool", "external_bank")

_TARGET_POOL = {"damaged": "damaged_cells", "senescent": "senescent_cells"}


def _require_fraction(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{path} must be finite, got {value!r}")
    if result < 0.0:
        raise ValueError(f"{path} must be >= 0 (got {result})")
    if result > 1.0:
        raise ValueError(f"{path} must be <= 1 (got {result})")
    return result


@dataclass
class ReplacementPlan:
    """One scheduled replacement event (output of planning, input to execution).

    ``expected_*`` fields are the planner's own ABSOLUTE cost estimates for this
    event, computed from per-cell tissue coefficients mitigated by the policy's
    compatibility controls; the model applies them (plus the
    proliferation-driven cancer term and, for ``external_bank``, the immune
    multiplier) on execution. Counts are floats to match
    the compartment (non-integer pool) representation.
    """

    target: str = "none"
    source: str = "none"
    target_count: float = 0.0
    source_count: float = 0.0
    expected_architecture_cost: float = 0.0
    expected_immune_cost: float = 0.0
    expected_cancer_risk_delta: float = 0.0
    expected_fibrosis_delta: float = 0.0

    def __post_init__(self) -> None:
        if self.target not in VALID_TARGETS:
            raise ValueError(f"plan.target must be one of {VALID_TARGETS}, got {self.target!r}")
        if self.source not in VALID_SOURCES:
            raise ValueError(f"plan.source must be one of {VALID_SOURCES}, got {self.source!r}")
        for name in (
            "target_count",
            "source_count",
            "expected_architecture_cost",
            "expected_immune_cost",
            "expected_cancer_risk_delta",
            "expected_fibrosis_delta",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"plan.{name} must be a number, got {value!r}")
            if not math.isfinite(float(value)):
                raise ValueError(f"plan.{name} must be finite, got {value!r}")
            if float(value) < 0.0:
                raise ValueError(f"plan.{name} must be >= 0 (got {value})")

    @classmethod
    def empty(cls) -> "ReplacementPlan":
        """The no-op plan: policy disabled, off-schedule, or nothing to do."""
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "source": self.source,
            "target_count": self.target_count,
            "source_count": self.source_count,
            "expected_architecture_cost": self.expected_architecture_cost,
            "expected_immune_cost": self.expected_immune_cost,
            "expected_cancer_risk_delta": self.expected_cancer_risk_delta,
            "expected_fibrosis_delta": self.expected_fibrosis_delta,
        }


@dataclass
class ReplacementPolicy:
    """When and how aggressively to replace target cells.

    Fields:
    - ``target``: which compartment to clear (``none`` = never).
    - ``source``: where new functional cells come from. ``stem_pool`` consumes
      the tissue's own stem compartment (depletable); ``external_bank`` is
      unlimited but carries extra immune cost (allogeneic assumption T-6).
    - ``frequency``: intervene every N-th model step (1 = every step).
    - ``max_replacement_fraction``: per-event cap as a fraction of the target
      pool -- the aggressiveness knob.
    - ``preserve_architecture`` / ``immune_compatibility`` / ``cancer_control``:
      mitigation controls in [0, 1]; 1 = perfect (no side effect), 0 = none.
    """

    name: str = "default"
    enabled: bool = False
    target: str = "none"
    source: str = "none"
    frequency: int = 5
    max_replacement_fraction: float = 0.2
    preserve_architecture: float = 0.9
    immune_compatibility: float = 0.9
    cancer_control: float = 0.9

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("policy.name must be non-empty")
        if self.target not in VALID_TARGETS:
            raise ValueError(f"policy.target must be one of {VALID_TARGETS}, got {self.target!r}")
        if self.source not in VALID_SOURCES:
            raise ValueError(f"policy.source must be one of {VALID_SOURCES}, got {self.source!r}")
        if isinstance(self.frequency, bool) or not isinstance(self.frequency, int):
            raise ValueError(f"policy.frequency must be an int, got {self.frequency!r}")
        if self.frequency < 1:
            raise ValueError("policy.frequency must be >= 1")
        self.max_replacement_fraction = _require_fraction(
            self.max_replacement_fraction, "policy.max_replacement_fraction"
        )
        self.preserve_architecture = _require_fraction(
            self.preserve_architecture, "policy.preserve_architecture"
        )
        self.immune_compatibility = _require_fraction(
            self.immune_compatibility, "policy.immune_compatibility"
        )
        self.cancer_control = _require_fraction(self.cancer_control, "policy.cancer_control")
        if self.enabled:
            if self.target == "none":
                raise ValueError("enabled policy must have target != 'none'")
            if self.source == "none":
                raise ValueError("enabled policy must have source != 'none'")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "target": self.target,
            "source": self.source,
            "frequency": self.frequency,
            "max_replacement_fraction": self.max_replacement_fraction,
            "preserve_architecture": self.preserve_architecture,
            "immune_compatibility": self.immune_compatibility,
            "cancer_control": self.cancer_control,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReplacementPolicy":
        return cls(
            name=data.get("name", "default"),
            enabled=bool(data.get("enabled", False)),
            target=data.get("target", "none"),
            source=data.get("source", "none"),
            frequency=int(data.get("frequency", 5)),
            max_replacement_fraction=float(data.get("max_replacement_fraction", 0.0)),
            preserve_architecture=float(data.get("preserve_architecture", 1.0)),
            immune_compatibility=float(data.get("immune_compatibility", 1.0)),
            cancer_control=float(data.get("cancer_control", 1.0)),
        )

    # -- pure planning ----------------------------------------------------
    def is_due(self, step_count: int) -> bool:
        """True when a replacement event is scheduled at this step counter."""
        if not self.enabled:
            return False
        return step_count % self.frequency == 0

    def plan(
        self,
        state: Any,
        parameters: dict[str, Any],
        step_count: int,
    ) -> ReplacementPlan:
        """Compute the replacement event for this step WITHOUT mutating state.

        Reads the target pool size and the stem pool (for ``stem_pool`` source
        capping) and returns cost estimates; the caller executes the plan.
        Returns :meth:`ReplacementPlan.empty` when disabled, off-schedule, or
        when there is nothing to replace.
        """
        if not self.enabled or not self.is_due(step_count):
            return ReplacementPlan.empty()
        pool_name = _TARGET_POOL.get(self.target)
        if pool_name is None:
            return ReplacementPlan.empty()
        available = float(getattr(state, pool_name, 0.0))
        target_count = available * self.max_replacement_fraction
        if target_count <= 0.0:
            return ReplacementPlan.empty()

        if self.source == "stem_pool":
            source_count = min(target_count, float(getattr(state, "stem_cells", 0.0)))
        elif self.source == "external_bank":
            source_count = target_count
        else:
            return ReplacementPlan.empty()
        if source_count <= 0.0:
            return ReplacementPlan.empty()

        # Cost estimates mirror TissueModel.apply_replacement_plan (per-cell
        # coefficients from tissue params, mitigated by policy controls).
        # All four are ABSOLUTE expected deltas for this event. NOTE: the
        # external-bank immune multiplier is applied at execution; the
        # estimate reports the pre-multiplier cost (documented in T-6).
        architecture_leak = 1.0 - self.preserve_architecture
        immune_leak = 1.0 - self.immune_compatibility
        return ReplacementPlan(
            target=self.target,
            source=self.source,
            target_count=target_count,
            source_count=source_count,
            expected_architecture_cost=(
                target_count
                * float(parameters.get("architecture_cost_per_cell", 0.0))
                * architecture_leak
            ),
            expected_immune_cost=(
                target_count
                * float(parameters.get("immune_cost_per_cell", 0.0))
                * immune_leak
            ),
            expected_cancer_risk_delta=(
                target_count
                * float(parameters.get("cancer_cost_per_cell", 0.0))
                * (1.0 - self.cancer_control)
            ),
            expected_fibrosis_delta=(
                target_count
                * float(parameters.get("fibrosis_cost_per_cell", 0.0))
                * architecture_leak
            ),
        )
