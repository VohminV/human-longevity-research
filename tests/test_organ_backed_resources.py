"""Stage 6A: systemic resources -- demand/allocation/shortfall/exhaustion."""

import json
import math

import pytest

from longevity.model.organ_backed import (
    SYSTEMIC_RESOURCES,
    compute_allocation,
    compute_demands,
    default_organ_backed_state,
    validate_organ_backed_state,
    validate_resource_budgets,
)
from longevity.model.organism import (
    DEFAULT_ORGANISM_THRESHOLDS,
    DEFAULT_STAGE_BOUNDS,
    OrganismModel,
    validate_organism_thresholds,
    validate_stage_bounds,
)


def test_allocation_math_edge_cases():
    budgets = {"perfusion": 8.0, "immune": 8.0, "metabolic": 8.0, "repair": 8.0}
    zero = {"perfusion": 0.0, "immune": 0.0, "metabolic": 0.0, "repair": 0.0}
    assert compute_allocation(budgets, zero) == {r: 1.0 for r in SYSTEMIC_RESOURCES}
    assert compute_allocation(zero, budgets) == {r: 0.0 for r in SYSTEMIC_RESOURCES}
    double = {r: 16.0 for r in SYSTEMIC_RESOURCES}
    assert compute_allocation(budgets, double) == {r: pytest.approx(0.5) for r in SYSTEMIC_RESOURCES}
    demands = compute_demands(default_organ_backed_state()["proxies"])
    assert set(demands) == set(SYSTEMIC_RESOURCES)
    assert all(math.isfinite(v) and v > 0.0 for v in demands.values())
    allocation = compute_allocation(budgets, demands)
    assert all(0.0 <= v <= 1.0 for v in allocation.values())


def test_demands_grow_with_proxy_damage():
    healthy = default_organ_backed_state()["proxies"]
    damaged = {pid: dict(p, damage=0.8, senescence_burden=0.5) for pid, p in healthy.items()}
    calm = compute_demands(healthy)
    stressed = compute_demands(damaged)
    for resource in SYSTEMIC_RESOURCES:
        assert stressed[resource] > calm[resource]


def test_resource_shock_drains_budgets():
    model = OrganismModel(seed=3, organ_backed_model="reduced_organ_proxies")
    before = dict(model.state.organ_backed["resources"]["budgets"])
    model.state.active_shocks.append({"age": 30.0, "type": "resource_shock",
                                      "magnitude": 2.0, "remaining": 2, "duration": 2})
    model._apply_active_shocks(0.5)
    after = model.state.organ_backed["resources"]["budgets"]
    for resource in SYSTEMIC_RESOURCES:
        assert after[resource] < before[resource]
        assert after[resource] >= 0.0


def test_starved_budgets_exhaust_and_kill():
    model = OrganismModel(seed=3, organ_backed_model="reduced_organ_proxies",
                          systemic_resources={r: 0.5 for r in SYSTEMIC_RESOURCES})
    trajectory = model.run(60.0, 0.5, validate_stage_bounds(dict(DEFAULT_STAGE_BOUNDS)),
                           validate_organism_thresholds(dict(DEFAULT_ORGANISM_THRESHOLDS)), None)
    allocations = [min(row["organ_backed"]["resources"]["allocation"].values())
                   for row in trajectory[1:]]
    assert min(allocations) < 0.2
    assert model.state.organ_backed is not None
    validate_organ_backed_state(model.state.organ_backed)
    # State stays JSON-safe and finite throughout.
    json.dumps(trajectory[-1]["organ_backed"])
    for row in trajectory[1:]:
        for value in row["organ_backed"]["resources"]["allocation"].values():
            assert 0.0 <= value <= 1.0 and math.isfinite(value)


def test_budgets_validation_and_defaults():
    assert validate_resource_budgets(None) == validate_resource_budgets({})
    assert validate_resource_budgets({"perfusion": 4.0})["perfusion"] == pytest.approx(4.0)
    assert validate_resource_budgets({"perfusion": 4.0})["immune"] == pytest.approx(8.0)
