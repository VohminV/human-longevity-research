"""RESEARCH LAYER: biological alignment manifest validator (Stage 8).

Pure stdlib module. Loads the Stage 8 biological alignment manifest,
validates its schema, enforces the no-overclaims rule and source-status
discipline, and returns the alignment classification. It never runs a
simulation, never touches the model, the organism runner, or v5.
"""

from __future__ import annotations

import json

from typing import Any

ALIGNMENT_LABELS = (
    "aligned_with_current_evidence",
    "partially_aligned_major_gaps",
    "mechanistic_extension_required",
    "calibration_data_insufficient",
    "model_mismatch_critical",
    "inconclusive_alignment",
)

ALIGNMENT_LABELS_RU: dict[str, str] = {
    "aligned_with_current_evidence": "согласовано с текущими доказательствами",
    "partially_aligned_major_gaps": "частично согласовано, есть критические пробелы",
    "mechanistic_extension_required": "требуется механистическое расширение",
    "calibration_data_insufficient": "недостаточно данных для калибровки",
    "model_mismatch_critical": "критическое расхождение модели и биологии",
    "inconclusive_alignment": "неоднозначное выравнивание",
}

CONFIDENCE_RU: dict[str, str] = {
    "low": "низкая",
    "medium": "средняя",
    "high": "высокая",
}

ANCHOR_TYPES = ("quantitative", "ordinal", "qualitative", "unavailable")
SOURCE_STATUSES = ("verified_in_repo", "needs_verification", "unavailable")
CONFIDENCES = ("data-backed", "literature-backed", "expert-plausible", "unavailable")
SEVERITIES = ("low", "medium", "high", "critical")
AFFECTS = ("v5_criterion", "attribution", "organ_network", "repair",
           "stem_cells", "epigenetics", "metabolism",
           "systemic_communication", "nonlinearity")
RECOMMENDED_ACTIONS = ("recalibrate", "redefine_metric", "add_mechanism_stage9",
                       "collect_data", "external_review")
PRIORITIES = ("P0", "P1", "P2", "P3", "P4", "P5", "P6")

ALLOWED_TOP_LEVEL_KEYS = {"stage", "type", "type_ru", "model_scope",
                          "hypothesis_status", "hypothesis_status_ru",
                          "prior_result", "anchors", "mismatches",
                          "candidate_mechanisms", "stage9_priorities",
                          "classification", "limitations", "limitations_ru"}

# Dynamics/model knobs must never appear in an alignment manifest.
FORBIDDEN_MODEL_KEYS = {"aging_drivers", "boundary_params",
                        "reversibility_params", "component_overrides",
                        "model_dynamics", "simulation", "policies"}

# Positive biological-success claims. Negations ("не доказательство ...")
# do not match these entries; keep the list to affirmative claims only.
OVERCLAIM_PATTERNS = (
    "бессмертие доказано",
    "омоложение доказано",
    "v5 достигнута",
    "старение обратимо у человека",
    "старение обратимо",
    "механизм бессмертия найден",
    "бессмертие возможно",
    "омоложение достигнуто",
    "стена старения доказана биологически",
    "найден механизм, снимающий v5",
    "v5 почти достигнута",
    "параметры позволяют достичь v5",
    "критерий был неправильный",
    "молодая кровь омолаживает человека",
    "экзосомы продлевают жизнь",
    "стволовые клетки можно просто вернуть",
    "модель теперь биологически валидна",
    "HYP-0 подтверждена",
    "найден путь к бессмертию",
    "эпигенетическое репрограммирование решает старение",
    "реальная биологическая причина",
    "информационный долг — реальная биологическая причина",
    "протеостаз — реальная биологическая причина",
)


def _is_nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _collect_strings(node: Any) -> list[str]:
    """All string leaves of a JSON-like structure (for overclaim scan)."""
    found: list[str] = []
    if isinstance(node, str):
        found.append(node)
    elif isinstance(node, dict):
        for value in node.values():
            found.extend(_collect_strings(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_collect_strings(item))
    return found


def find_overclaims(manifest: dict[str, Any]) -> list[str]:
    """Affirmative overclaim patterns present anywhere in the manifest."""
    hits: list[str] = []
    for text in _collect_strings(manifest):
        lowered = text.lower()
        for pattern in OVERCLAIM_PATTERNS:
            if pattern in lowered and pattern not in hits:
                hits.append(pattern)
    return hits


def _require_fields(entry: Any, fields: tuple[str, ...], path: str,
                    errors: list[str]) -> bool:
    if not isinstance(entry, dict):
        errors.append(f"{path} must be a dict")
        return False
    ok = True
    for field in fields:
        if field not in entry:
            errors.append(f"{path} missing required field {field!r}")
            ok = False
    return ok


def validate_manifest(manifest: Any) -> dict[str, Any]:
    """Validate a Stage 8 manifest; return {valid, errors} (pure)."""
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return {"valid": False, "errors": ["manifest must be a dict"]}
    unknown = set(manifest) - ALLOWED_TOP_LEVEL_KEYS
    if unknown:
        errors.append(f"unknown top-level keys: {sorted(unknown)}")
    intruding = set(manifest) & FORBIDDEN_MODEL_KEYS
    if intruding:
        errors.append(
            "manifest must not change model dynamics; "
            f"forbidden keys present: {sorted(intruding)}")
    if manifest.get("stage") != "8":
        errors.append(f"stage must be '8', got {manifest.get('stage')!r}")
    if manifest.get("hypothesis_status") != "hypothesis_not_proven":
        errors.append("hypothesis_status must stay 'hypothesis_not_proven'")
    prior = manifest.get("prior_result", {})
    if not isinstance(prior, dict):
        errors.append("prior_result must be a dict")
    else:
        if prior.get("stage_7_classification") != "robust_diffuse_wall":
            errors.append("prior_result.stage_7_classification must be 'robust_diffuse_wall'")
        if prior.get("v5_operational_success") is not False:
            errors.append("prior_result.v5_operational_success must be false")
    anchors = manifest.get("anchors", None)
    if not isinstance(anchors, list):
        errors.append("anchors must be a list")
    else:
        for i, anchor in enumerate(anchors):
            path = f"anchors[{i}]"
            if not _require_fields(anchor, ("name", "model_construct",
                                            "biological_meaning", "anchor_type",
                                            "source_status", "calibration_possible",
                                            "confidence", "notes_ru"), path, errors):
                continue
            if anchor["anchor_type"] not in ANCHOR_TYPES:
                errors.append(f"{path}.anchor_type must be one of {list(ANCHOR_TYPES)}")
            if anchor["source_status"] not in SOURCE_STATUSES:
                errors.append(f"{path}.source_status must be one of {list(SOURCE_STATUSES)}")
            if anchor["confidence"] not in CONFIDENCES:
                errors.append(f"{path}.confidence must be one of {list(CONFIDENCES)}")
            if not isinstance(anchor["calibration_possible"], bool):
                errors.append(f"{path}.calibration_possible must be a bool")
            if anchor["source_status"] == "verified_in_repo" \
                    and not _is_nonempty_str(anchor.get("source_ref", "")):
                errors.append(f"{path}: verified_in_repo requires a non-empty source_ref")
            if anchor["confidence"] == "data-backed" and (
                    anchor["source_status"] != "verified_in_repo"
                    or not _is_nonempty_str(anchor.get("source_ref", ""))):
                errors.append(
                    f"{path}: data-backed confidence requires verified_in_repo "
                    "with a non-empty source_ref; needs_verification must not "
                    "be presented as data-backed")
    mismatches = manifest.get("mismatches", None)
    if not isinstance(mismatches, list):
        errors.append("mismatches must be a list")
    else:
        for i, mismatch in enumerate(mismatches):
            path = f"mismatches[{i}]"
            if not _require_fields(mismatch, ("name", "model_assumption",
                                              "biological_evidence_summary",
                                              "severity", "affects",
                                              "recommended_action", "notes_ru"),
                                   path, errors):
                continue
            if mismatch["severity"] not in SEVERITIES:
                errors.append(f"{path}.severity must be one of {list(SEVERITIES)}")
            affects = mismatch["affects"]
            if not isinstance(affects, list) or not affects \
                    or any(a not in AFFECTS for a in affects):
                errors.append(f"{path}.affects must be a non-empty list of "
                              f"{list(AFFECTS)}")
            if mismatch["recommended_action"] not in RECOMMENDED_ACTIONS:
                errors.append(f"{path}.recommended_action must be one of "
                              f"{list(RECOMMENDED_ACTIONS)}")
    candidates = manifest.get("candidate_mechanisms", None)
    if not isinstance(candidates, list):
        errors.append("candidate_mechanisms must be a list")
    else:
        for i, candidate in enumerate(candidates):
            path = f"candidate_mechanisms[{i}]"
            if not _require_fields(candidate, ("id", "name", "name_ru",
                                               "biological_basis",
                                               "targeted_model_gap",
                                               "proposed_abstract_representation",
                                               "observable_proxy",
                                               "expected_effect_on_wall",
                                               "risk", "priority", "status",
                                               "not_claim", "notes_ru"),
                                   path, errors):
                continue
            if candidate["priority"] not in PRIORITIES:
                errors.append(f"{path}.priority must be one of {list(PRIORITIES)}")
            if candidate["status"] != "candidate_only":
                errors.append(f"{path}.status must be 'candidate_only', never proven")
            if not _is_nonempty_str(candidate["observable_proxy"]):
                errors.append(f"{path} requires an observable_proxy")
            if not _is_nonempty_str(candidate["risk"]):
                errors.append(f"{path} requires a risk")
            not_claim = candidate["not_claim"]
            if not isinstance(not_claim, dict):
                errors.append(f"{path}.not_claim must be a dict")
            else:
                for flag in ("not_proven_in_humans", "not_simulated_yet",
                             "not_v5_success"):
                    if not_claim.get(flag) is not True:
                        errors.append(f"{path}.not_claim.{flag} must be true")
    priorities = manifest.get("stage9_priorities", None)
    if not isinstance(priorities, list) or not priorities:
        errors.append("stage9_priorities must be a non-empty list")
    else:
        known_ids = {c.get("id") for c in candidates
                     if isinstance(c, dict)} if isinstance(candidates, list) else set()
        for i, item in enumerate(priorities):
            path = f"stage9_priorities[{i}]"
            if not _require_fields(item, ("priority", "mechanism_id",
                                          "rationale_ru", "first_prototype_ru"),
                                   path, errors):
                continue
            if item["priority"] not in PRIORITIES:
                errors.append(f"{path}.priority must be one of {list(PRIORITIES)}")
            if item["mechanism_id"] not in known_ids:
                errors.append(f"{path}.mechanism_id {item['mechanism_id']!r} "
                              "matches no candidate mechanism")
    for pattern in find_overclaims(manifest):
        errors.append(f"overclaim pattern forbidden: {pattern!r}")
    return {"valid": not errors, "errors": errors}


def classify_alignment(manifest: dict[str, Any]) -> dict[str, Any]:
    """Stage 8 alignment classification over a manifest (pure).

    Never declares biological immortality possible; it only classifies
    the alignment state between the model and biology. Invalid
    manifests yield inconclusive_alignment instead of a guess.
    """
    check = validate_manifest(manifest)
    if not check["valid"]:
        return {"classification": "inconclusive_alignment",
                "classification_ru": ALIGNMENT_LABELS_RU["inconclusive_alignment"],
                "confidence": "low",
                "confidence_ru": CONFIDENCE_RU["low"],
                "reasons": [f"invalid manifest: {check['errors'][0]}"],
                "notes_ru": "Манифест невалиден; сильный вывод невозможен."}
    anchors = manifest.get("anchors", [])
    mismatches = manifest.get("mismatches", [])
    candidates = manifest.get("candidate_mechanisms", [])
    if not anchors and not mismatches and not candidates:
        return {"classification": "inconclusive_alignment",
                "classification_ru": ALIGNMENT_LABELS_RU["inconclusive_alignment"],
                "confidence": "low",
                "confidence_ru": CONFIDENCE_RU["low"],
                "reasons": ["manifest carries no anchors, mismatches or candidates"],
                "notes_ru": "Пустой манифест; выравнивание неоднозначно."}

    def _done(label: str, confidence: str, reasons: list[str],
              notes_ru: str) -> dict[str, Any]:
        return {"classification": label,
                "classification_ru": ALIGNMENT_LABELS_RU[label],
                "confidence": confidence,
                "confidence_ru": CONFIDENCE_RU[confidence],
                "reasons": reasons,
                "notes_ru": notes_ru}

    critical = [m["name"] for m in mismatches if m.get("severity") == "critical"]
    if critical:
        return _done(
            "model_mismatch_critical", "medium",
            [f"critical mismatches: {critical}"],
            "Заявлено критическое расхождение модели и биологии. Требуется пересмотр базовых допущений; HYP-0 остаётся гипотеза не доказана.")
    mechanistic = [m["name"] for m in mismatches
                   if m.get("recommended_action") == "add_mechanism_stage9"
                   and m.get("severity") in ("high", "critical")]
    if mechanistic:
        return _done(
            "mechanistic_extension_required", "medium",
            [f"mechanisms required by: {mechanistic}"],
            "Текущая абстракция не покрывает ключевые механизмы; robust_diffuse_wall может быть артефактом отсутствия пластичности, системной коммуникации, ниши, энергии и иерархии. Нужен Stage 9 prototype; HYP-0 остаётся гипотеза не доказана.")
    quantitative = [a["name"] for a in anchors
                    if a.get("anchor_type") == "quantitative"
                    and a.get("calibration_possible") is True
                    and a.get("source_status") == "verified_in_repo"]
    remaining = [m["name"] for m in mismatches if m.get("severity") in ("high", "medium")]
    if remaining:
        return _done(
            "partially_aligned_major_gaps", "medium",
            [f"major gaps remain: {remaining}"],
            "Часть конструктов согласована; есть значимые, но не фатальные расхождения. Возможна калибровка без смены архитектуры.")
    if not quantitative:
        if anchors and all(a.get("source_status") == "verified_in_repo"
                           and a.get("confidence") == "data-backed" for a in anchors):
            return _done(
                "aligned_with_current_evidence", "high",
                ["all anchors verified in repo with data-backed confidence, "
                 "no major mismatches"],
                "Конструкты согласованы с текущими доказательствами в пределах проверенного.")
        return _done(
            "calibration_data_insufficient", "medium",
            ["no quantitative verified calibration anchors"],
            "Есть гипотезы, но недостаточно внешних данных для количественной привязки. HYP-0 остаётся гипотеза не доказана.")
    if anchors and all(a.get("source_status") == "verified_in_repo" for a in anchors) \
            and not [m for m in mismatches if m.get("severity") in ("high", "medium", "critical")]:
        return _done(
            "aligned_with_current_evidence", "high",
            ["all anchors verified in repo, no major mismatches"],
            "Конструкты согласованы с текущими доказательствами в пределах проверенного.")
    return _done(
        "inconclusive_alignment", "low",
        ["anchors contradictory or unverified without actionable mismatches"],
        "Источники не проверены или противоречивы; сильный вывод невозможен.")


def load_manifest(path: str) -> dict[str, Any]:
    """Read an alignment manifest JSON file (pure)."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("alignment manifest must be a JSON object")
    return data


def load_and_validate_manifest(path: str) -> dict[str, Any]:
    """Load, validate and classify a manifest file (pure).

    Returns {manifest, valid, errors, classification}. Never raises on
    content problems (only on unreadable files); an invalid manifest
    classifies as inconclusive_alignment.
    """
    manifest = load_manifest(path)
    check = validate_manifest(manifest)
    classification = classify_alignment(manifest)
    summary = {
        "stage": manifest.get("stage"),
        "hypothesis_status": manifest.get("hypothesis_status"),
        "n_anchors": len(manifest.get("anchors", [])),
        "n_mismatches": len(manifest.get("mismatches", [])),
        "n_candidates": len(manifest.get("candidate_mechanisms", [])),
    }
    return {"manifest": manifest, "valid": bool(check["valid"]),
            "errors": check["errors"], "classification": classification,
            "manifest_summary": summary}
