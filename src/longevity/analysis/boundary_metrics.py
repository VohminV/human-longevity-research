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

# Stage 6F residual-wall labels (diagnostic only; see classify_residual_wall).
RESIDUAL_WALL_LABELS = (
    "diffuse_residual_wall",
    "localized_residual_wall",
    "mixed_residual_wall",
    "inconclusive_residual_probe",
)

# Stage 6F: heterogeneous driver names accepted by the probe. Canonical
# names are the 8 mechanistic drivers plus the 6 bio-age source groups;
# short aliases map to their canonical group (rejected when ambiguous
# only by being unknown — see canonical_heterogeneous_driver).
HETEROGENEOUS_DRIVER_ALIASES: dict[str, str] = {
    "stem": "stem_exhaustion",
    "proteostasis": "proteostasis_metabolic",
    "metabolic": "proteostasis_metabolic",
    "inflammatory": "inflammatory_senescent",
    "senescence": "inflammatory_senescent",
    "genomic": "genomic_integrity",
}

# Single-driver bio-age slope reduction that counts as a "substantial"
# targeted effect (diagnostic threshold, not a biological constant).
SUBSTANTIAL_BIO_SLOPE_REDUCTION = 0.20

# Human-readable Russian statuses (Stage 6F contract): English identifiers
# stay untouched; *_ru fields carry the human-readable translation.
WALL_CLASSIFICATION_RU: dict[str, str] = {
    "no_wall": "стена не обнаружена",
    "single_channel_parametric_wall": "параметрическая стена одного канала",
    "knife_edge_parametric_wall": "параметрическая стена эффекта ножевого края",
    "compound_residual_wall": "составная остаточная стена",
    "structural_under_current_abstraction_wall": "структурная стена текущей абстракции",
    "ceiling_mediated_wall": "стена, опосредованная потолком ремонта",
    "inconclusive_sensitivity_failure": "неоднозначно из-за чувствительности",
    "insufficient_data": "недостаточно данных",
    "diffuse_residual_wall": "диффузная остаточная стена",
    "localized_residual_wall": "локализованная остаточная стена",
    "mixed_residual_wall": "смешанная остаточная стена",
    "inconclusive_residual_probe": "неоднозначный зонд остаточной стены",
    "parametric_irreversibility_wall": "параметрическая стена необратимости",
    "structural_conversion_wall": "структурная стена конверсии",
    "structural_independent_accrual_wall": "структурная стена независимого накопления",
    "structural_repair_ceiling_wall": "структурная стена потолка ремонта",
    "structural_information_wall": "структурная информационная стена",
    "structural_mutation_wall": "структурная мутационная стена",
    "structural_niche_wall": "структурная нишевая стена",
    "structural_entropy_wall": "структурная энтропийная стена",
    "structural_other_wall": "структурная стена другого канала",
    "mixed_wall": "смешанная стена",
    "inconclusive": "неоднозначно",
    "robust_diffuse_wall": "устойчивая диффузная стена",
    "criterion_sensitive_wall": "стена, чувствительная к критерию",
    "parameter_sensitive_wall": "стена, чувствительная к параметрам",
    "non_identifiable_abstraction": "неидентифицируемая абстракция",
    "inconclusive_insufficient_calibration": "неоднозначно: недостаточно калибровки",
}

BINDING_CONSTRAINT_RU: dict[str, str] = {
    "none": "нет (ограничение не выявлено)",
    "irreversible_net_slope": "чистый наклон необратимости",
    "biological_age_slope": "наклон биологического возраста",
    "biological_age_network_slope": "наклон сетевого биологического возраста",
    "biological_age_reversibility_slope": "наклон обратимостного биологического возраста",
    "driver_slope": "наклон драйверов",
    "reversible_burden": "обратимая нагрузка",
    "irreversible_accumulation": "необратимое накопление",
    "conversion_runaway": "неконтролируемая конверсия",
    "conversion_flux": "конверсионный поток",
    "independent_accrual": "независимое накопление",
    "independent_irreversible_accrual": "независимое необратимое накопление",
    "repair_ceiling": "потолок ремонта",
    "repair_ceiling_exhaustion": "исчерпание потолка ремонта",
    "repair_ceiling_limitation": "ограничение потолка ремонта",
    "insufficient_repair_offset": "недостаточная компенсация ремонтом",
    "information_debt": "информационный долг",
    "mutation_fixation": "фиксация мутаций",
    "niche_disorder": "разупорядочивание ниши",
    "entropy_production": "производство энтропии",
    "conversion": "конверсия",
    "mixed": "смешанный источник",
    "other_binding_wall": "другая связывающая стена",
}

BIO_AGE_SOURCE_RU: dict[str, str] = {
    "none": "нет",
    "genomic_integrity": "целостность генома (genomic_integrity)",
    "epigenetic": "эпигенетика (epigenetic)",
    "proteostasis_metabolic": "протеостаз/метаболизм (proteostasis_metabolic)",
    "inflammatory_senescent": "воспаление/сенесцентность (inflammatory_senescent)",
    "stem_exhaustion": "истощение стволовых пулов (stem_exhaustion)",
    "oncogenic": "онкогенный риск (oncogenic)",
}

CONFIDENCE_RU: dict[str, str] = {
    "low": "низкая",
    "medium": "средняя",
    "high": "высокая",
}

HYPOTHESIS_RU: dict[str, str] = {
    "hypothesis_not_proven": "гипотеза не доказана",
    "candidate_found": "кандидат найден",
    "candidate_not_found": "кандидат не найден",
}


def wall_classification_ru(label: str) -> str:
    """Russian human-readable wall label (pure, 6F).

    English identifiers are never renamed; unknown labels raise instead
    of guessing a translation.
    """
    if label not in WALL_CLASSIFICATION_RU:
        raise ValueError(f"unknown wall classification {label!r}")
    return WALL_CLASSIFICATION_RU[label]


def binding_constraint_ru(name: str) -> str:
    """Russian human-readable binding-constraint name (pure, 6F).

    Unknown codes fall back to the English code itself (forward
    compatible with future model constraints).
    """
    return BINDING_CONSTRAINT_RU.get(name, name)


def bio_age_source_ru(name: str) -> str:
    """Russian human-readable bio-age source-group name (pure, 6F)."""
    return BIO_AGE_SOURCE_RU.get(name, name)


def confidence_ru(level: str) -> str:
    """Russian human-readable confidence level (pure, 6F)."""
    if level not in CONFIDENCE_RU:
        raise ValueError(f"unknown confidence {level!r}")
    return CONFIDENCE_RU[level]


def hypothesis_ru(status: str) -> str:
    """Russian human-readable hypothesis status (pure, 6F)."""
    if status not in HYPOTHESIS_RU:
        raise ValueError(f"unknown hypothesis status {status!r}")
    return HYPOTHESIS_RU[status]


def v5_operational_success_ru(v5: bool) -> str:
    """Russian human-readable v5 verdict (pure, 6F)."""
    if not isinstance(v5, bool):
        raise ValueError(f"v5 verdict must be a bool, got {v5!r}")
    return ("операционный критерий v5 выполнен"
            if v5 else "операционный критерий v5 не выполнен")


def exploratory_ru(exploratory: bool) -> str:
    """Russian human-readable exploratory flag (pure, 6F)."""
    if not isinstance(exploratory, bool):
        raise ValueError(f"exploratory flag must be a bool, got {exploratory!r}")
    return ("exploratory-режим, не калиброван как биологическая модель"
            if exploratory else "номинальный (не exploratory) режим")


def sensitivity_stable_ru(all_stable: bool, any_stable: bool) -> str:
    """Russian human-readable sensitivity stability (pure, 6F)."""
    if not isinstance(all_stable, bool) or not isinstance(any_stable, bool):
        raise ValueError("stability flags must be bools")
    if all_stable:
        return "устойчиво"
    if any_stable:
        return "частично"
    return "неустойчиво"


def canonical_heterogeneous_driver(name: Any) -> str:
    """Canonical heterogeneous driver/group name (pure, 6F).

    Accepts the 8 mechanistic drivers, the 6 bio-age source groups and
    the documented short aliases. Unknown names raise (never guessed).
    """
    if not isinstance(name, str) or not name:
        raise ValueError(f"heterogeneous driver name must be a non-empty string, got {name!r}")
    canonical = HETEROGENEOUS_DRIVER_ALIASES.get(name, name)
    known = set(AGING_DRIVERS) | set(BIO_AGE_SOURCE_GROUPS)
    if canonical not in known:
        raise ValueError(
            f"unknown heterogeneous driver {name!r}; known drivers: {sorted(AGING_DRIVERS)}, "
            f"known source groups: {sorted(BIO_AGE_SOURCE_GROUPS)}, "
            f"known aliases: {sorted(HETEROGENEOUS_DRIVER_ALIASES)}")
    return canonical


def expand_heterogeneous_driver(name: Any) -> tuple[str, ...]:
    """Mechanistic drivers covered by one heterogeneous target (pure, 6F)."""
    canonical = canonical_heterogeneous_driver(name)
    if canonical in BIO_AGE_SOURCE_GROUPS:
        return tuple(BIO_AGE_SOURCE_GROUPS[canonical])
    return (canonical,)


def validate_heterogeneous_driver_scale(value: Any, path: str) -> float:
    """Validate one driver attenuation scale (pure, 6F)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{path} must be finite, got {value!r}")
    if result < 0.0:
        raise ValueError(f"{path} must be >= 0")
    return result


def classify_residual_wall(*,
                           v5_robust_non_exploratory: bool = False,
                           v5_narrow_only: bool = False,
                           substantial_single_driver_effect: bool = False,
                           binding_or_source_flip: bool = False,
                           n_drivers_tested: int = 0,
                           stability: dict[str, Any] | None = None) -> dict[str, Any]:
    """Heterogeneous residual-wall classification over 6F evidence (pure, 6F).

    Pure diagnostic homunculus over already-computed regime evidence;
    never touches the simulation. Precedence: insufficient data ->
    instability -> robust non-exploratory v5 (localized, audit required)
    -> narrow-only v5 (inconclusive) -> channel flip (mixed) ->
    substantial single-driver effect (localized) -> diffuse. Missing
    evidence is never guessed: incomplete data yields
    ``inconclusive_residual_probe``.
    """
    for flag_name, flag in (
            ("v5_robust_non_exploratory", v5_robust_non_exploratory),
            ("v5_narrow_only", v5_narrow_only),
            ("substantial_single_driver_effect", substantial_single_driver_effect),
            ("binding_or_source_flip", binding_or_source_flip)):
        if not isinstance(flag, bool):
            raise ValueError(f"{flag_name} must be a bool, got {flag!r}")
    if isinstance(n_drivers_tested, bool) or not isinstance(n_drivers_tested, int) \
            or n_drivers_tested < 0:
        raise ValueError(f"n_drivers_tested must be an int >= 0, got {n_drivers_tested!r}")
    stability = dict(stability or {})
    data_complete = bool(stability.get("data_complete", False))
    if not data_complete or n_drivers_tested == 0:
        return {"stage_6f_residual_classification": "inconclusive_residual_probe",
                "stage_6f_residual_classification_reason":
                    "insufficient data: refusing to guess a residual-wall label",
                "confidence": "low"}
    unstable = sorted(k for k, v in stability.items()
                      if k != "data_complete" and not v)
    if unstable:
        return {"stage_6f_residual_classification": "inconclusive_residual_probe",
                "stage_6f_residual_classification_reason":
                    f"verdict unstable across {', '.join(unstable)}; no strong residual claim",
                "confidence": "low"}
    if v5_robust_non_exploratory:
        return {"stage_6f_residual_classification": "localized_residual_wall",
                "stage_6f_residual_classification_reason":
                    "targeted suppression reaches robust v5 in a non-exploratory regime; "
                    "requires a Stage 6G robustness audit before any claim; "
                    "HYP-0 stays hypothesis_not_proven",
                "confidence": "medium"}
    if v5_narrow_only:
        return {"stage_6f_residual_classification": "inconclusive_residual_probe",
                "stage_6f_residual_classification_reason":
                    "v5 true only in narrow/exploratory regimes; not a robust localized wall",
                "confidence": "low"}
    if binding_or_source_flip:
        return {"stage_6f_residual_classification": "mixed_residual_wall",
                "stage_6f_residual_classification_reason":
                    "targeted suppression shifts the binding constraint or the dominant "
                    "residual source to another channel while v5 stays false; "
                    "diagnostic transition, not a biological change of cause",
                "confidence": "medium"}
    if substantial_single_driver_effect:
        return {"stage_6f_residual_classification": "localized_residual_wall",
                "stage_6f_residual_classification_reason":
                    "targeted suppression of one driver substantially lowers "
                    "biological_age_slope or moves the binding constraint, "
                    "yet v5 stays false: significant diagnostic constraint, "
                    "not solely removable for v5",
                "confidence": "medium"}
    return {"stage_6f_residual_classification": "diffuse_residual_wall",
            "stage_6f_residual_classification_reason":
                "targeted suppression of top drivers leaves the binding constraint "
                "and v5 substantially unchanged; residual wall spread across channels "
                "in the current abstraction",
            "confidence": "medium"}

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


# Stage 7 audit labels (diagnostic only; see classify_stage7_audit).
STAGE7_AUDIT_LABELS = (
    "robust_diffuse_wall",
    "criterion_sensitive_wall",
    "parameter_sensitive_wall",
    "non_identifiable_abstraction",
    "inconclusive_insufficient_calibration",
)

# Stage 7: identifiability flags for driver channels (diagnostic only).
IDENTIFIABILITY_FLAGS = (
    "identifiable",
    "weakly_identifiable",
    "non_identifiable",
    "insufficient_data",
)

# Stage 7: slope estimator names for the criterion probe (pure analysis,
# no simulation change; see estimate_bio_slope).
SLOPE_ESTIMATORS = (
    "least_squares",
    "endpoint",
    "trailing_window",
)

# Trailing window width for the trailing_window estimator (years).
TRAILING_WINDOW_YEARS = 30.0

# Aggregation channels for the criterion probe (existing summary slopes).
AGGREGATION_CHANNELS = (
    "global",
    "network",
    "reversibility",
)

# Slope-eps criterion keys scaled by threshold relativity (same nine as
# the Stage 6E eps-sensitivity probe; worst-case gates stay fixed).
SLOPE_EPS_KEYS_7 = ("eps_bio", "eps_bio_network", "eps_bio_rev", "eps_driver",
                    "eps_reversible", "eps_irreversible", "eps_information",
                    "eps_mutation", "eps_niche")

# Multipliers inside these closed ranges are nominal audit perturbations;
# wider ones are auto-marked exploratory (see is_nominal_audit_multiplier).
NOMINAL_DRIVER_MULT_RANGE = (0.5, 2.0)
NOMINAL_LEDGER_SCALE_RANGE = (0.75, 1.5)

IDENTIFIABILITY_RU: dict[str, str] = {
    "identifiable": "идентифицируем",
    "weakly_identifiable": "слабо идентифицируем",
    "non_identifiable": "неидентифицируем",
    "insufficient_data": "недостаточно данных",
}


def identifiability_ru(flag: str) -> str:
    """Russian human-readable identifiability flag (pure, 7)."""
    if flag not in IDENTIFIABILITY_RU:
        raise ValueError(f"unknown identifiability flag {flag!r}")
    return IDENTIFIABILITY_RU[flag]


def criterion_variant_ru(kind: str, value: Any) -> str:
    """Russian human-readable criterion variant name (pure, 7).

    Technical variant ids stay English; this helper only builds the
    human-readable companion string (e.g. threshold_-0.2).
    """
    if kind == "threshold":
        return f"порог {float(value):+.0%} (threshold_{value})"
    if kind == "horizon":
        return f"горизонт {float(value):g} лет (horizon_{value})"
    if kind == "aggregation":
        return f"агрегация {value} (aggregation_{value})"
    if kind == "estimator":
        return f"оценка наклона {value} (estimator_{value})"
    raise ValueError(f"unknown criterion variant kind {kind!r}")


def validate_audit_multiplier(value: Any, path: str) -> float:
    """Validate one audit perturbation multiplier (pure, 7)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{path} must be finite, got {value!r}")
    if result < 0.0:
        raise ValueError(f"{path} must be >= 0")
    return result


def is_nominal_audit_multiplier(value: float, family: str) -> bool:
    """True when a multiplier is inside the nominal audit range (pure, 7).

    ``family`` is ``"driver"`` (weight multipliers) or ``"ledger"``
    (boundary scales). Wider perturbations are legitimate audit points
    but auto-marked exploratory by the runner.
    """
    if family == "driver":
        lo, hi = NOMINAL_DRIVER_MULT_RANGE
    elif family == "ledger":
        lo, hi = NOMINAL_LEDGER_SCALE_RANGE
    else:
        raise ValueError(f"unknown audit family {family!r}")
    return bool(lo <= float(value) <= hi)


def relativize_slope_criteria(criteria: dict[str, Any], relativity: float) -> dict[str, float]:
    """Scale the nine slope-eps thresholds by (1 + relativity) (pure, 7).

    Worst-case gates stay fixed, like in the Stage 6E eps-sensitivity
    probe. ``relativity`` must keep every eps >= 0.
    """
    if isinstance(relativity, bool) or not isinstance(relativity, (int, float)) \
            or not math.isfinite(float(relativity)) or float(relativity) < -1.0:
        raise ValueError(f"threshold relativity must be finite and >= -1, got {relativity!r}")
    scaled = dict(criteria)
    for key in SLOPE_EPS_KEYS_7:
        scaled[key] = float(criteria[key]) * (1.0 + float(relativity))
    return scaled


def estimate_bio_slope(trajectory: list[dict[str, Any]], estimator: str) -> float:
    """Adult biological-age slope under one estimator (pure, 7).

    ``least_squares`` is the baseline estimator used by every summary;
    ``endpoint`` and ``trailing_window`` are trivial diagnostic
    alternatives (no new dynamics, no refits). Never mutates the
    trajectory.
    """
    if estimator not in SLOPE_ESTIMATORS:
        raise ValueError(f"unknown slope estimator {estimator!r}; "
                         f"known: {list(SLOPE_ESTIMATORS)}")
    if not trajectory or len(trajectory) < 2:
        raise ValueError("estimate_bio_slope of empty trajectory")
    adult = _adult_rows(trajectory)
    if not adult:
        raise ValueError("estimate_bio_slope with no adult rows")
    times = [float(row["chronological_age"]) for row in adult]
    values = [float(row["biological_age"]) for row in adult]
    if estimator == "least_squares":
        return float(_slope(times, values))
    if estimator == "endpoint":
        span = times[-1] - times[0]
        if span <= 0.0:
            return 0.0
        return float((values[-1] - values[0]) / span)
    window = [(t, v) for t, v in zip(times, values)
              if t >= times[-1] - TRAILING_WINDOW_YEARS]
    if len(window) < 2:
        window = list(zip(times, values))
    wtimes = [t for t, _ in window]
    wvalues = [v for _, v in window]
    return float(_slope(wtimes, wvalues))


def truncate_trajectory(trajectory: list[dict[str, Any]],
                        horizon_years: float) -> list[dict[str, Any]]:
    """Truncate a trajectory to a horizon without rerunning (pure, 7).

    Keeps the initial row plus every row with
    ``chronological_age <= horizon``. Never mutates the input.
    Horizons with fewer than 2 adult rows are degenerate for slope
    metrics; the runner marks such variants instead of failing.
    """
    if isinstance(horizon_years, bool) or not isinstance(horizon_years, (int, float)) \
            or not math.isfinite(float(horizon_years)) or float(horizon_years) <= 0.0:
        raise ValueError(f"horizon_years must be finite and > 0, got {horizon_years!r}")
    if not trajectory or len(trajectory) < 2:
        raise ValueError("truncate_trajectory of empty trajectory")
    horizon = float(horizon_years)
    kept = [trajectory[0]] + [row for row in trajectory[1:]
                              if float(row["chronological_age"]) <= horizon + 1e-9]
    if len(kept) < 2:
        raise ValueError(f"horizon {horizon} keeps fewer than 2 rows")
    return [dict(row) for row in kept]


def assess_identifiability(*,
                           control_observable: float,
                           driver_responses: dict[str, dict[str, Any]] | None = None,
                           min_relative_change: float = 0.05,
                           seed_stable: bool = True,
                           data_complete: bool = True) -> dict[str, Any]:
    """Driver-channel identifiability over audit evidence (pure, 7).

    ``driver_responses`` maps a tested driver group to
    ``relative_observable_change`` (fraction vs control),
    ``binding_changed`` and ``source_changed`` bools. A channel is
    responsive when the observable moves by at least
    ``min_relative_change`` or the binding/source flips: the dial is
    connected to something the metrics can see. Pure diagnostic over
    already-computed numbers; never touches the simulation.
    """
    driver_responses = dict(driver_responses or {})
    if isinstance(min_relative_change, bool) or not isinstance(min_relative_change, (int, float)) \
            or not math.isfinite(float(min_relative_change)) \
            or float(min_relative_change) < 0.0:
        raise ValueError(f"min_relative_change must be finite and >= 0, "
                         f"got {min_relative_change!r}")
    for flag_name, flag in (("seed_stable", seed_stable),
                            ("data_complete", data_complete)):
        if not isinstance(flag, bool):
            raise ValueError(f"{flag_name} must be a bool, got {flag!r}")
    if not data_complete or not driver_responses:
        return {"identifiability": "insufficient_data",
                "identifiability_reason":
                    "insufficient data: refusing to judge identifiability",
                "per_driver": {}}
    if not seed_stable:
        return {"identifiability": "insufficient_data",
                "identifiability_reason":
                    "seed-unstable responses cannot support identifiability",
                "per_driver": {}}
    per_driver: dict[str, Any] = {}
    for name in sorted(driver_responses):
        info = driver_responses[name]
        change = info.get("relative_observable_change", 0.0)
        if isinstance(change, bool) or not isinstance(change, (int, float)) \
                or not math.isfinite(float(change)):
            raise ValueError(f"driver response {name!r} change must be finite, "
                             f"got {change!r}")
        for key in ("binding_changed", "source_changed"):
            if not isinstance(info.get(key), bool):
                raise ValueError(f"driver response {name!r}.{key} must be a bool")
        responsive = bool(float(change) >= float(min_relative_change)
                          or info["binding_changed"] or info["source_changed"])
        per_driver[name] = {
            "relative_observable_change": float(change),
            "binding_changed": bool(info["binding_changed"]),
            "source_changed": bool(info["source_changed"]),
            "channel": "identifiable" if responsive else "weakly_identifiable",
        }
    responsive = sum(1 for v in per_driver.values() if v["channel"] == "identifiable")
    if responsive == len(per_driver):
        flag, reason = ("identifiable",
                        "every tested driver moves the observable or flips "
                        "binding/source; channels distinguishable")
    elif responsive == 0:
        flag, reason = ("non_identifiable",
                        "no tested driver moves the observable or flips "
                        "binding/source; perturbations indistinguishable "
                        "in the current abstraction")
    else:
        weak = sorted(n for n, v in per_driver.items() if v["channel"] != "identifiable")
        flag, reason = ("weakly_identifiable",
                        f"channels {weak} do not respond to perturbation; "
                        f"remaining channels distinguishable")
    return {"identifiability": flag, "identifiability_reason": reason,
            "per_driver": per_driver}


def classify_stage7_audit(*,
                          v5_any_non_exploratory: bool = False,
                          criterion_flip: bool = False,
                          parameter_v5_flip: bool = False,
                          parameter_attribution_flip: bool = False,
                          identifiability: str = "insufficient_data",
                          n_regimes_tested: int = 0,
                          stability: dict[str, Any] | None = None) -> dict[str, Any]:
    """Criterion/parameter robustness audit classification (pure, 7).

    Pure diagnostic homunculus over already-computed audit evidence;
    never touches the simulation. A ``v5=true`` inside the audit is
    never success: with unchanged dynamics it means the criterion is
    unstable (``criterion_sensitive_wall``), with perturbed parameters
    it means calibration is missing (``parameter_sensitive_wall``).
    HYP-0 stays ``hypothesis_not_proven`` in every branch. Missing
    evidence is never guessed.
    """
    for flag_name, flag in (
            ("v5_any_non_exploratory", v5_any_non_exploratory),
            ("criterion_flip", criterion_flip),
            ("parameter_v5_flip", parameter_v5_flip),
            ("parameter_attribution_flip", parameter_attribution_flip)):
        if not isinstance(flag, bool):
            raise ValueError(f"{flag_name} must be a bool, got {flag!r}")
    if identifiability not in IDENTIFIABILITY_FLAGS:
        raise ValueError(f"unknown identifiability flag {identifiability!r}")
    if isinstance(n_regimes_tested, bool) or not isinstance(n_regimes_tested, int) \
            or n_regimes_tested < 0:
        raise ValueError(f"n_regimes_tested must be an int >= 0, got {n_regimes_tested!r}")
    stability = dict(stability or {})
    data_complete = bool(stability.get("data_complete", False))
    if not data_complete or n_regimes_tested == 0:
        return {"stage_7_audit_classification": "inconclusive_insufficient_calibration",
                "stage_7_audit_classification_reason":
                    "insufficient data: refusing to judge robustness",
                "confidence": "low"}
    unstable = sorted(k for k, v in stability.items()
                      if k != "data_complete" and not v)
    if unstable:
        return {"stage_7_audit_classification": "inconclusive_insufficient_calibration",
                "stage_7_audit_classification_reason":
                    f"verdict unstable across {', '.join(unstable)}; no strong audit claim",
                "confidence": "low"}
    if criterion_flip:
        return {"stage_7_audit_classification": "criterion_sensitive_wall",
                "stage_7_audit_classification_reason":
                    "same dynamics, different v5 verdict/binding/source under a "
                    "pre-declared criterion variant; the operationalization is "
                    "unstable, not the biology; HYP-0 stays hypothesis_not_proven",
                "confidence": "medium"}
    if parameter_v5_flip or parameter_attribution_flip:
        return {"stage_7_audit_classification": "parameter_sensitive_wall",
                "stage_7_audit_classification_reason":
                    "reasonable parameter perturbation changes the v5 verdict or "
                    "the dominant attribution while dynamics stay nominal; "
                    "calibration is missing before any strong claim, not "
                    "removability of the wall; HYP-0 stays hypothesis_not_proven",
                "confidence": "medium"}
    if identifiability == "non_identifiable":
        return {"stage_7_audit_classification": "non_identifiable_abstraction",
                "stage_7_audit_classification_reason":
                    "perturbations are indistinguishable in the metrics; no "
                    "reliable channel holds the wall in the current abstraction",
                "confidence": "medium"}
    if identifiability == "insufficient_data":
        return {"stage_7_audit_classification": "inconclusive_insufficient_calibration",
                "stage_7_audit_classification_reason":
                    "identifiability could not be judged; withholding a robustness claim",
                "confidence": "low"}
    return {"stage_7_audit_classification": "robust_diffuse_wall",
            "stage_7_audit_classification_reason":
                "v5 false in every non-exploratory regime, no criterion or "
                "parameter flip, binding stays biological_age_slope; diffuse "
                "residual wall stable inside the audited ranges",
            "confidence": "high" if identifiability == "identifiable" else "medium"}


def information_wall_proximity(trajectory: list[dict[str, Any]]) -> dict[str, Any]:
    """Backup-Drive readability at the end of a trajectory (pure, Stage 9).

    Delegates to :func:`longevity.model.epigenetic_backup.information_wall_proximity`
    on the final row's ``epigenetic_backup`` block (nominal params: the
    trajectory carries state, not config). ``proximity`` in [0, 1] is how
    close the organism is to losing the ability to read the Backup Drive;
    ``readable`` False means the wall is reached. Never mutates input.
    """
    from longevity.model.epigenetic_backup import (  # deferred: avoid import cycle
        information_wall_proximity as _model_proximity,
    )

    if not trajectory:
        raise ValueError("information_wall_proximity of empty trajectory")
    final = trajectory[-1].get("epigenetic_backup")
    result = _model_proximity(dict(final) if final is not None else None, None)
    result["final_age"] = float(trajectory[-1].get("chronological_age", 0.0))
    return result


def information_wall_proximity_ru(proximity: float, readable: bool) -> str:
    """Russian human-readable wall proximity label (pure, Stage 9)."""
    from longevity.model.epigenetic_backup import (  # deferred: avoid import cycle
        information_wall_proximity_ru as _ru,
    )

    return _ru(proximity, readable)
