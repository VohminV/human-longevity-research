"""ANALYSIS LAYER: irreversibility boundary probe metrics (Stage 6D).

Pure functions over organism trajectories carrying ``reversibility`` and
optionally ``boundary`` blocks: per-component contribution decomposition
(conversion flux + independent accrual − repair offset = net slope),
dominant-source attribution, and parametric-vs-structural wall
classification. All descriptive and model-internal; diagnostic ablation
results are never biological claims.
"""

from __future__ import annotations

import math

from typing import Any

from longevity.model.aging import AGING_DRIVERS
from longevity.model.organ_backed import ORGAN_PROXIES

SOURCES = (
    "none",
    "conversion",
    "independent_irreversible_accrual",
    "insufficient_repair_offset",
    "repair_ceiling_limitation",
    "information_debt",
    "mutation_fixation",
    "niche_disorder",
    "entropy_production",
    "mixed",
    "other_binding_wall",
)

WALL_CLASSES = (
    "no_wall",
    "parametric_irreversibility_wall",
    "structural_conversion_wall",
    "structural_independent_accrual_wall",
    "structural_repair_ceiling_wall",
    "structural_information_wall",
    "structural_mutation_wall",
    "structural_niche_wall",
    "structural_entropy_wall",
    "structural_other_wall",
    "mixed_wall",
    "inconclusive",
)


def _slope(times: list[float], values: list[float]) -> float:
    n = len(times)
    if n < 2:
        return 0.0
    mean_t = sum(times) / n
    mean_v = sum(values) / n
    denom = sum((t - mean_t) ** 2 for t in times)
    if denom <= 0.0:
        return 0.0
    return sum((t - mean_t) * (v - mean_v) for t, v in zip(times, values)) / denom


def _adult_rows(trajectory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in trajectory[1:]
            if row["developmental_stage"] not in ("embryo", "fetal", "infancy", "childhood", "adolescence")]


def _has_reversibility(trajectory: list[dict[str, Any]]) -> bool:
    return any(row.get("reversibility") is not None for row in trajectory[1:])


def _component_ids() -> list[str]:
    return [f"driver:{n}" for n in AGING_DRIVERS] + [f"organ:{p}" for p in ORGAN_PROXIES]


def _comp_of(row: dict[str, Any], cid: str) -> dict[str, Any]:
    rev = row.get("reversibility") or {}
    kind, name = cid.split(":", 1)
    section = rev.get("drivers", {}) if kind == "driver" else rev.get("organs", {})
    return section.get(name, {})


def summarize_contributions(trajectory: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-component irreversible contribution decomposition (pure, 6D)."""
    if not trajectory:
        raise ValueError("summarize_contributions of empty trajectory")
    if not _has_reversibility(trajectory):
        return {"has_contributions": False, "dominant_irreversibility_component": "none",
                "dominant_irreversibility_source": "none",
                "top_k_irreversibility_components": [],
                "component_binding_ranking": []}
    adult = _adult_rows(trajectory)
    times = [float(row["chronological_age"]) for row in adult]
    span = max(1e-9, times[-1] - times[0]) if len(times) >= 2 else 1.0
    conv_flux: dict[str, float] = {}
    indep_acc: dict[str, float] = {}
    repair_off: dict[str, float] = {}
    net_slope: dict[str, float] = {}
    for cid in _component_ids():
        series = [max(0.0, min(1.0, float(_comp_of(row, cid).get("irreversible", 0.0))))
                  for row in adult]
        net_slope[cid] = float(_slope(times, series)) if series else 0.0
        final = _comp_of(trajectory[-1], cid)
        conv_flux[cid] = max(0.0, float(final.get("conversion_cumul", 0.0))) / span
        indep_acc[cid] = max(0.0, float(final.get("independent_cumul", 0.0))) / span
        repair_off[cid] = max(0.0, float(final.get("repair_cumul", 0.0))) / span
    positive = {cid: max(0.0, net_slope[cid]) for cid in net_slope}
    total = sum(positive.values())
    shares = {cid: (positive[cid] / total if total > 0.0 else 0.0) for cid in positive}
    ranking = sorted(positive, key=lambda c: (-positive[c], c))
    dominant = ranking[0] if total > 0.0 else "none"
    # Bio-age contribution proxy: net slope share (documented approximation;
    # exact age weights live in reversibility params).
    return {
        "has_contributions": True,
        "irreversible_slope_by_component": {k: float(v) for k, v in net_slope.items()},
        "conversion_flux_by_component": {k: float(v) for k, v in conv_flux.items()},
        "independent_accrual_by_component": {k: float(v) for k, v in indep_acc.items()},
        "repair_offset_by_component": {k: float(v) for k, v in repair_off.items()},
        "net_irreversible_slope_by_component": {k: float(v) for k, v in net_slope.items()},
        "contribution_share_to_irreversible_slope_by_component": {k: float(v) for k, v in shares.items()},
        "contribution_share_to_biological_age_reversibility_by_component": {
            k: float(v) for k, v in shares.items()},
        "dominant_irreversibility_component": dominant,
        "top_k_irreversibility_components": ranking[:5],
        "component_binding_ranking": ranking,
    }


def attribute_source(contributions: dict[str, Any],
                     reversibility_summary: dict[str, Any] | None = None,
                     ablation_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dominant irreversible source attribution (pure, deterministic).

    Compares aggregate conversion flux vs independent accrual vs repair
    offset vs information / mutation / niche / entropy slopes with a
    documented winner-takes-all rule; near-ties resolve to ``mixed``.
    """
    reversibility_summary = reversibility_summary or {}
    ablation_meta = ablation_meta or {}
    if not contributions.get("has_contributions"):
        return {"dominant_irreversibility_source": "none",
                "source_attribution_reason": "no reversibility ledger in trajectory"}
    conv = sum(contributions.get("conversion_flux_by_component", {}).values())
    indep = sum(contributions.get("independent_accrual_by_component", {}).values())
    repair = sum(contributions.get("repair_offset_by_component", {}).values())
    info = max(0.0, float(reversibility_summary.get("information_debt_slope", 0.0)))
    mut = max(0.0, float(reversibility_summary.get("mutation_fixation_slope", 0.0)))
    niche = max(0.0, float(reversibility_summary.get("niche_disorder_slope", 0.0)))
    entropy = max(0.0, float(reversibility_summary.get("entropy_production_slope", 0.0)))
    ceiling = max(0.0, float(reversibility_summary.get("repair_ceiling", 0.0)))
    remaining = float(reversibility_summary.get("repair_remaining_min", ceiling))
    candidates = {
        "conversion": conv,
        "independent_irreversible_accrual": indep,
        "information_debt": info * 2.0,
        "mutation_fixation": mut * 2.0,
        "niche_disorder": niche * 2.0,
        "entropy_production": entropy * 2.0,
    }
    ordered = sorted(candidates, key=lambda k: (-candidates[k], k))
    top, second = ordered[0], ordered[1]
    reason = (f"flux conversion={conv:.6f} independent={indep:.6f} repair_offset={repair:.6f} "
              f"info_slope={info:.6f} mut_slope={mut:.6f} niche_slope={niche:.6f}")
    if candidates[top] <= 0.0:
        return {"dominant_irreversibility_source": "other_binding_wall",
                "source_attribution_reason": reason + "; all fluxes non-positive"}
    # Near-tie between the top two flux sources -> mixed.
    if candidates[second] > 0.0 and (candidates[top] - candidates[second]) / candidates[top] < 0.15 \
            and top in ("conversion", "independent_irreversible_accrual") \
            and second in ("conversion", "independent_irreversible_accrual"):
        return {"dominant_irreversibility_source": "mixed",
                "source_attribution_reason": reason + "; top-two fluxes within 15%"}
    if top == "conversion":
        if remaining <= 1e-9 and ceiling > 0.0:
            return {"dominant_irreversibility_source": "repair_ceiling_limitation",
                    "source_attribution_reason": reason + "; ceiling exhausted"}
        if repair < 0.3 * conv:
            return {"dominant_irreversibility_source": "conversion",
                    "source_attribution_reason": reason + "; conversion dominates, repair offsets <30%"}
        return {"dominant_irreversibility_source": "insufficient_repair_offset",
                "source_attribution_reason": reason + "; repair offsets >=30% yet net slope positive"}
    if top == "independent_irreversible_accrual":
        return {"dominant_irreversibility_source": "independent_irreversible_accrual",
                "source_attribution_reason": reason}
    return {"dominant_irreversibility_source": top,
            "source_attribution_reason": reason}


def classify_wall(v5_default: bool,
                  ablation_verdicts: dict[str, bool],
                  dominant_source: str = "none",
                  thresholds_note: str = "") -> dict[str, Any]:
    """Parametric-vs-structural wall classification (pure, deterministic).

    ``ablation_verdicts`` maps probe names (``conversion_zero``,
    ``independent_zero``, ``both_suppressed``, ``high_ceiling``,
    ``unlimited_ceiling``) to v5 booleans.
    """
    get = ablation_verdicts.get
    if v5_default:
        return {"wall_classification": "no_wall",
                "wall_classification_reason": "v5 true in default Stage 6C; no wall" + thresholds_note}
    conv = bool(get("conversion_zero", False))
    indep = bool(get("independent_zero", False))
    both = bool(get("both_suppressed", False))
    high = bool(get("high_ceiling", False))
    unlimited = bool(get("unlimited_ceiling", False))
    if both:
        return {"wall_classification": "parametric_irreversibility_wall",
                "wall_classification_reason": "v5 true only when both irreversible sources suppressed; "
                "wall is parametric under present conversion/accrual settings" + thresholds_note}
    if conv and not indep:
        return {"wall_classification": "structural_conversion_wall",
                "wall_classification_reason": "v5 true when conversion suppressed alone" + thresholds_note}
    if indep and not conv:
        return {"wall_classification": "structural_independent_accrual_wall",
                "wall_classification_reason": "v5 true when independent accrual suppressed alone" + thresholds_note}
    if unlimited and not (conv or indep or both or high):
        return {"wall_classification": "structural_repair_ceiling_wall",
                "wall_classification_reason": "v5 true only with unlimited ceiling ablation "
                "(non-physiological)" + thresholds_note}
    if high and not (conv or indep or both):
        return {"wall_classification": "parametric_irreversibility_wall",
                "wall_classification_reason": "v5 true with high (finite) ceiling" + thresholds_note}
    if dominant_source in ("information_debt", "mutation_fixation", "niche_disorder",
                           "entropy_production"):
        mapping = {"information_debt": "structural_information_wall",
                   "mutation_fixation": "structural_mutation_wall",
                   "niche_disorder": "structural_niche_wall",
                   "entropy_production": "structural_entropy_wall"}
        return {"wall_classification": mapping[dominant_source],
                "wall_classification_reason": f"v5 false under all irreversible-source ablations; "
                f"dominant source is {dominant_source}" + thresholds_note}
    if dominant_source in ("conversion", "independent_irreversible_accrual",
                           "insufficient_repair_offset", "repair_ceiling_limitation", "mixed"):
        return {"wall_classification": "parametric_irreversibility_wall",
                "wall_classification_reason": f"v5 false even suppressed; dominant source "
                f"{dominant_source} persists -> parametric wall at tested thresholds"
                + thresholds_note}
    return {"wall_classification": "structural_other_wall",
            "wall_classification_reason": f"v5 false with irreversible sources suppressed; "
            f"another binding wall dominates (source={dominant_source})" + thresholds_note}


def summarize_boundary_run(trajectory: list[dict[str, Any]], dt: float = 0.25) -> dict[str, Any]:
    """Full boundary per-run summary for runner merge (pure)."""
    from longevity.analysis.reversibility_metrics import summarize_reversibility

    contributions = summarize_contributions(trajectory)
    rev_summary: dict[str, Any] = {}
    if trajectory and any(row.get("reversibility") is not None for row in trajectory[1:]):
        rev_summary = summarize_reversibility(trajectory, dt)
    attribution = attribute_source(contributions, rev_summary)
    boundary = (trajectory[-1].get("boundary") if trajectory else None) or {}
    params = boundary.get("params", {})
    return {
        "boundary": {
            "boundary_probe_model": "irreversibility_ablation" if boundary else "none",
            "conversion_scale": float(params.get("conversion_scale", 1.0)),
            "independent_accrual_scale": float(params.get("independent_irreversible_accrual_scale", 1.0)),
            "repair_ceiling_scale": float(params.get("repair_ceiling_scale", 1.0)),
            "disable_conversion": bool(params.get("disable_conversion", False)),
            "disable_independent_accrual": bool(params.get("disable_independent_accrual", False)),
            "disable_irreversible_repair": bool(params.get("disable_irreversible_repair", False)),
            "disable_repair_ceiling": bool(params.get("disable_repair_ceiling", False)),
            "force_repair_ceiling_unlimited": bool(params.get("force_repair_ceiling_unlimited", False)),
            "exploratory": bool(boundary.get("exploratory", False)),
            "ablation_flags_hash": str(boundary.get("ablation_flags_hash", "none")),
        },
        "contributions": contributions,
        "attribution": attribution,
        "reversibility": rev_summary,
    }
