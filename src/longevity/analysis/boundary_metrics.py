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

# Stage 6E compound wall labels (diagnostic only; see classify_compound_wall).
COMPOUND_WALL_LABELS = (
    "no_wall",
    "single_channel_parametric_wall",
    "knife_edge_parametric_wall",
    "compound_residual_wall",
    "structural_under_current_abstraction_wall",
    "ceiling_mediated_wall",
    "inconclusive_sensitivity_failure",
)

# Stage 6E: driver-family grouping for biological_age_slope attribution.
# Grounded in the mechanistic aggregation
# (bio = setpoint + sum(contribution_i * damage_i / reference_i));
# shares are a linear diagnostic proxy, not a conservation law.
BIO_AGE_SOURCE_GROUPS: dict[str, tuple[str, ...]] = {
    "genomic_integrity": ("dna_damage",),
    "epigenetic": ("epigenetic_drift",),
    "proteostasis_metabolic": ("proteostasis_loss", "mitochondrial_dysfunction"),
    "inflammatory_senescent": ("cellular_senescence", "chronic_inflammation"),
    "stem_exhaustion": ("stem_exhaustion",),
    "oncogenic": ("cancer_prone",),
}


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


def decompose_biological_age_slope(trajectory: list[dict[str, Any]],
                                   driver_params: dict[str, dict[str, float]] | None = None,
                                   ) -> dict[str, Any]:
    """Diagnostic attribution of the mechanistic biological_age slope (pure, 6E).

    Uses the model's own aggregation weights
    (``contribution_i / adult_reference_i`` × post-adulthood damage slope).
    The sum matches the measured bio-age slope up to flooring, clamping and
    intervention deltas, so shares are an operational diagnostic proxy, not
    a conservation law. Never mutates the trajectory.
    """
    from longevity.model.aging import DEFAULT_DRIVER_PARAMS, validate_aging_drivers

    if not trajectory or len(trajectory) < 2:
        raise ValueError("decompose_biological_age_slope of empty trajectory")
    params = validate_aging_drivers(dict(driver_params or {})) if driver_params is not None \
        else {name: dict(DEFAULT_DRIVER_PARAMS[name]) for name in AGING_DRIVERS}
    adult = _adult_rows(trajectory)
    has_drivers = any((row.get("aging") or {}).get("drivers") for row in trajectory[1:])
    if not has_drivers or not adult:
        return {"has_bio_age_attribution": False, "total_slope": 0.0,
                "by_component": {}, "by_source": {}, "residual": 0.0,
                "dominant_component": "none", "dominant_source": "none",
                "top_components": [], "top_sources": [], "share_sum": 0.0,
                "deterministic": True,
                "notes": ("no mechanistic driver ledger in trajectory; "
                          "attribution unavailable")}
    times = [float(row["chronological_age"]) for row in adult]
    total_slope = float(_slope(
        times, [float(row["biological_age"]) for row in adult]))
    by_component: dict[str, float] = {}
    for name in AGING_DRIVERS:
        series = [max(0.0, float((row.get("aging") or {}).get("drivers", {})
                                 .get(name, {}).get("damage", 0.0))) for row in adult]
        weight = float(params[name]["contribution"]) \
            / max(1e-9, float(params[name]["adult_reference"]))
        by_component[name] = weight * float(_slope(times, series))
    by_source = {source: sum(by_component[d] for d in members)
                 for source, members in BIO_AGE_SOURCE_GROUPS.items()}
    explained = sum(by_component.values())
    residual = total_slope - explained
    positive = {k: max(0.0, v) for k, v in by_component.items()}
    total_pos = sum(positive.values())
    shares = {k: (positive[k] / total_pos if total_pos > 0.0 else 0.0) for k in positive}
    comp_ranking = sorted(positive, key=lambda k: (-positive[k], k))
    dominant_component = comp_ranking[0] if total_pos > 0.0 else "none"
    spositive = {k: max(0.0, v) for k, v in by_source.items()}
    stotal = sum(spositive.values())
    sranking = sorted(spositive, key=lambda k: (-spositive[k], k))
    dominant_source = sranking[0] if stotal > 0.0 else "none"
    n_significant = sum(1 for v in spositive.values()
                        if stotal > 0.0 and v / stotal >= 0.1)
    return {
        "has_bio_age_attribution": True,
        "total_slope": float(total_slope),
        "by_component": {k: float(v) for k, v in by_component.items()},
        "by_source": {k: float(v) for k, v in by_source.items()},
        "residual": float(residual),
        "dominant_component": dominant_component,
        "dominant_source": dominant_source,
        "top_components": comp_ranking[:3],
        "top_sources": sranking[:3],
        "share_sum": float(sum(shares.values())),
        "n_significant_sources": int(n_significant),
        "deterministic": True,
        "notes": ("linear diagnostic proxy from the model's aggregation weights; "
                  "residual covers flooring, clamping and direct bio-age intervention deltas"),
    }


def classify_compound_wall(v5_default: bool,
                           ablation_verdicts: dict[str, bool] | None = None,
                           knife_band_verdicts: dict[float, bool] | None = None,
                           irr_suppressed: bool = False,
                           residual_binding: str = "none",
                           n_residual_sources: int = 0,
                           stability: dict[str, bool] | None = None,
                           exploratory_only: bool = False) -> dict[str, Any]:
    """Compound wall classification over 6D/6E probe evidence (pure, 6E).

    Pure diagnostic homunculus over already-computed verdicts; never touches
    the simulation. ``ablation_verdicts`` maps probe names
    (``conversion_zero``, ``independent_zero``, ``both_suppressed``,
    ``high_ceiling``, ``unlimited_ceiling``) to v5 booleans;
    ``knife_band_verdicts`` maps ultra-low conversion scales to v5 booleans.
    ``stability`` carries ``data_complete``, ``seed_stable``,
    ``eps_stable``, ``dt_stable``. Missing evidence is never guessed:
    incomplete data yields ``inconclusive_sensitivity_failure``.
    """
    ablation_verdicts = dict(ablation_verdicts or {})
    knife_band_verdicts = dict(knife_band_verdicts or {})
    stability = dict(stability or {})
    for name, value in ablation_verdicts.items():
        if not isinstance(value, bool):
            raise ValueError(f"ablation verdict {name!r} must be a bool, got {value!r}")
    for scale, value in knife_band_verdicts.items():
        if not isinstance(value, bool):
            raise ValueError(f"knife-band verdict {scale!r} must be a bool, got {value!r}")
    if not stability.get("data_complete", False):
        return {"wall_classification": "inconclusive_sensitivity_failure",
                "wall_classification_reason": "insufficient data: refusing to guess a wall label",
                "confidence": "low"}
    if not (stability.get("seed_stable", False) and stability.get("eps_stable", False)
            and stability.get("dt_stable", False)):
        failed = sorted(k for k in ("seed_stable", "eps_stable", "dt_stable")
                        if not stability.get(k, False))
        return {"wall_classification": "inconclusive_sensitivity_failure",
                "wall_classification_reason":
                    f"verdict unstable across {', '.join(failed)}; no strong wall claim",
                "confidence": "low"}
    if v5_default and not exploratory_only:
        return {"wall_classification": "no_wall",
                "wall_classification_reason": "v5 true in default non-exploratory setting",
                "confidence": "high"}
    band = {float(s): bool(v) for s, v in knife_band_verdicts.items()}
    band_true = sorted(s for s, v in band.items() if v)
    band_ultra_low = [s for s in band_true if s <= 1e-4]
    # Knife-edge: v5 true only inside the ultra-low nonzero band, false at
    # zero and at/above 1e-3 (unstable parametric window, not a robust wall).
    if band_ultra_low and not ablation_verdicts.get("conversion_zero", False) \
            and not any(band.get(s, False) for s in band if s >= 1e-3):
        return {"wall_classification": "knife_edge_parametric_wall",
                "wall_classification_reason":
                    f"v5 true only at ultra-low scales {band_ultra_low}; "
                    "formally removable but not robust",
                "confidence": "medium"}
    if exploratory_only and not any(ablation_verdicts.get(k, False)
                                    for k in ("conversion_zero", "independent_zero",
                                              "both_suppressed", "high_ceiling")):
        return {"wall_classification": "ceiling_mediated_wall",
                "wall_classification_reason": "v5 true only with unlimited/exploratory ceiling",
                "confidence": "medium"}
    single = [k for k in ("conversion_zero", "independent_zero", "high_ceiling")
              if ablation_verdicts.get(k, False)]
    if len(single) == 1 and not ablation_verdicts.get("both_suppressed", False):
        return {"wall_classification": "single_channel_parametric_wall",
                "wall_classification_reason":
                    f"v5 true with one moderate ablation ({single[0]}), stable; "
                    "no unlimited ceiling, no knife-edge",
                "confidence": "medium"}
    if irr_suppressed and residual_binding in ("biological_age_slope", "information_debt") \
            and n_residual_sources >= 2:
        return {"wall_classification": "compound_residual_wall",
                "wall_classification_reason":
                    f"irreversible slope suppressed yet v5 false; binding shifted to "
                    f"{residual_binding} across {n_residual_sources} residual sources; "
                    "no single removable channel",
                "confidence": "medium"}
    if not any(ablation_verdicts.values()) and not band_true:
        return {"wall_classification": "structural_under_current_abstraction_wall",
                "wall_classification_reason":
                    "v5 false under ultra-low conversion, zero independent and "
                    "high/unlimited ceiling with stable residual attribution; "
                    "structural only inside the current abstraction",
                "confidence": "medium"}
    return {"wall_classification": "inconclusive_sensitivity_failure",
            "wall_classification_reason": "evidence pattern matches no wall archetype; "
            "withholding a strong claim",
            "confidence": "low"}


def select_suppressed_evidence(per_ablation: dict[str, dict[str, Any]],
                               eps_irreversible: float) -> dict[str, Any]:
    """Pick the suppressed-yet-failing ablation for wall classification (pure, 6E).

    ``per_ablation`` maps ablation name to ``max_irr_slope``,
    ``v5`` (bool), ``binding`` (majority first constraint) and
    ``n_sources`` (significant bio-age sources). Returns the suppressed
    (slope in eps) but still-failing ablation with the smallest slope, or
    ``{"name": None, ...}`` when no ablation suppresses the slope.
    """
    suppressed = {name: info for name, info in per_ablation.items()
                  if float(info.get("max_irr_slope", 9e9)) <= float(eps_irreversible)
                  and not bool(info.get("v5", True))}
    if not suppressed:
        return {"name": None, "irr_suppressed": False,
                "residual_binding": "none", "n_residual_sources": 0}
    name = sorted(suppressed,
                  key=lambda k: (suppressed[k].get("max_irr_slope", 9e9), k))[0]
    info = suppressed[name]
    return {"name": name, "irr_suppressed": True,
            "residual_binding": str(info.get("binding", "none")),
            "n_residual_sources": int(info.get("n_sources", 0))}


def compute_eps_sensitivity(summaries: list[dict[str, Any]],
                            eps_values: list[float],
                            base_criteria: dict[str, Any] | None = None) -> dict[str, Any]:
    """v5 verdicts across uniform slope-eps values (pure, 6E).

    Varies the nine per-run slope thresholds uniformly; worst-case gates
    are held fixed. Never reruns the simulation.
    """
    from longevity.analysis.reversibility_metrics import (
        robust_bounded_degradation_v5,
        validate_v5_criteria,
    )

    if not summaries:
        raise ValueError("compute_eps_sensitivity of empty summaries")
    if not eps_values:
        raise ValueError("eps_values must be non-empty")
    for eps in eps_values:
        if isinstance(eps, bool) or not isinstance(eps, (int, float)) \
                or not math.isfinite(float(eps)) or float(eps) < 0.0:
            raise ValueError(f"eps value must be finite and >= 0, got {eps!r}")
    base = validate_v5_criteria(base_criteria)
    slope_keys = ("eps_bio", "eps_bio_network", "eps_bio_rev", "eps_driver",
                  "eps_reversible", "eps_irreversible", "eps_information",
                  "eps_mutation", "eps_niche")
    verdict_by_eps: dict[str, bool] = {}
    for eps in eps_values:
        criteria = dict(base)
        for key in slope_keys:
            criteria[key] = float(eps)
        verdict_by_eps[str(eps)] = bool(
            robust_bounded_degradation_v5(summaries, criteria)["robust_bounded_degradation_v5"])
    values = list(verdict_by_eps.values())
    return {
        "eps_values": [float(e) for e in eps_values],
        "verdict_by_eps": verdict_by_eps,
        "eps_stable": all(v == values[0] for v in values),
        "reason": ("verdict identical across eps" if all(v == values[0] for v in values)
                   else "verdict changes across eps"),
    }
