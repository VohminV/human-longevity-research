# -*- coding: utf-8 -*-
"""Stage 8: biological alignment manifest validation and classification.

Docs + research maps + pure validator only. No simulation, no model
dynamics change, no new biology in the model.
"""

import copy
import json

import pytest

from longevity.research.biological_alignment import (
    ALIGNMENT_LABELS,
    classify_alignment,
    find_overclaims,
    load_and_validate_manifest,
    validate_manifest,
)

MANIFEST_PATH = "experiments/configs/stage8_biological_alignment_manifest.json"

REQUIRED_CANDIDATE_IDS = {
    "epigenetic_plasticity_restoration",
    "damage_adaptation_split",
    "systemic_circulation_pool",
    "stem_cell_niche_quality",
    "energy_coupled_repair_autophagy",
    "hierarchical_hallmark_feedback",
    "nonlinear_age_waves",
    "aggregate_class_partition",
}

OVERCLAIM_STRINGS = (
    "бессмертие доказано",
    "омоложение доказано",
    "v5 достигнута",
    "старение обратимо у человека",
    "механизм бессмертия найден",
)


@pytest.fixture(scope="module")
def manifest():
    with open(MANIFEST_PATH, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def validated():
    return load_and_validate_manifest(MANIFEST_PATH)


def test_manifest_loads_and_parses(manifest):
    assert isinstance(manifest, dict)
    assert manifest["stage"] == "8"


def test_hypothesis_status_not_proven(manifest):
    assert manifest["hypothesis_status"] == "hypothesis_not_proven"
    assert manifest["hypothesis_status_ru"] == "гипотеза не доказана"


def test_prior_result_is_robust_diffuse_wall(manifest):
    prior = manifest["prior_result"]
    assert prior["stage_7_classification"] == "robust_diffuse_wall"
    assert prior["v5_operational_success"] is False


def test_anchors_have_required_fields(manifest):
    required = {"name", "model_construct", "biological_meaning",
                "anchor_type", "source_status", "calibration_possible",
                "confidence", "notes_ru"}
    assert manifest["anchors"]
    for anchor in manifest["anchors"]:
        assert required <= set(anchor), anchor.get("name")


def test_mismatches_have_required_fields(manifest):
    required = {"name", "model_assumption", "biological_evidence_summary",
                "severity", "affects", "recommended_action", "notes_ru"}
    assert manifest["mismatches"]
    for mismatch in manifest["mismatches"]:
        assert required <= set(mismatch), mismatch.get("name")
        assert mismatch["affects"]


def test_candidates_have_required_fields(manifest):
    required = {"id", "name", "name_ru", "biological_basis",
                "targeted_model_gap", "proposed_abstract_representation",
                "observable_proxy", "expected_effect_on_wall", "risk",
                "priority", "status", "not_claim", "notes_ru"}
    assert REQUIRED_CANDIDATE_IDS <= {c["id"] for c in manifest["candidate_mechanisms"]}
    for candidate in manifest["candidate_mechanisms"]:
        assert required <= set(candidate), candidate.get("id")
        assert candidate["observable_proxy"].strip()
        assert candidate["risk"].strip()


def test_verified_requires_source_ref(manifest):
    for anchor in manifest["anchors"]:
        if anchor["source_status"] == "verified_in_repo":
            assert anchor.get("source_ref", "").strip(), anchor["name"]


def test_needs_verification_never_data_backed(manifest):
    for anchor in manifest["anchors"]:
        if anchor["source_status"] != "verified_in_repo":
            assert anchor["confidence"] != "data-backed", anchor["name"]


def test_no_candidate_status_proven(manifest):
    for candidate in manifest["candidate_mechanisms"]:
        assert candidate["status"] == "candidate_only"
        assert candidate["not_claim"]["not_proven_in_humans"] is True
        assert candidate["not_claim"]["not_simulated_yet"] is True
        assert candidate["not_claim"]["not_v5_success"] is True


def test_no_overclaims_in_manifest(manifest):
    assert validate_manifest(manifest)["valid"]
    assert find_overclaims(manifest) == []
    for banned in OVERCLAIM_STRINGS:
        assert banned not in json.dumps(manifest, ensure_ascii=False).lower()


def test_overclaim_detector_catches_affirmative():
    bad = {"stage": "8", "note": "Эпигенетическое репрограммирование решает старение"}
    assert find_overclaims(bad)
    good = {"stage": "8",
            "note": "Это не доказательство бессмертия; HYP-0 остаётся гипотеза не доказана"}
    assert find_overclaims(good) == []


def test_classifier_returns_allowed_label(validated):
    assert validated["valid"], validated["errors"]
    label = validated["classification"]["classification"]
    assert label in ALIGNMENT_LABELS
    assert validated["classification"]["classification_ru"]
    assert validated["classification"]["confidence"] in ("low", "medium", "high")


def test_all_six_labels_reachable_on_synthetics():
    base = {"stage": "8", "hypothesis_status": "hypothesis_not_proven",
            "prior_result": {"stage_7_classification": "robust_diffuse_wall",
                             "v5_operational_success": False},
            "stage9_priorities": [{"priority": "P0", "mechanism_id": "m",
                                   "rationale_ru": "r", "first_prototype_ru": "p"}]}

    def _anchor(status="verified_in_repo", atype="qualitative",
                calib=False, conf="expert-plausible"):
        return {"name": "a", "model_construct": "c", "biological_meaning": "m",
                "anchor_type": atype, "source_status": status,
                "source_ref": "docs/X.md" if status == "verified_in_repo" else "",
                "calibration_possible": calib, "confidence": conf, "notes_ru": "n"}
    def _mismatch(severity="medium", action="recalibrate"):
        return {"name": "mm", "model_assumption": "a",
                "biological_evidence_summary": "e", "severity": severity,
                "affects": ["attribution"], "recommended_action": action,
                "notes_ru": "n"}

    def _candidate(cid="m"):
        return {"id": cid, "name": cid, "name_ru": "н", "biological_basis": "b",
                "targeted_model_gap": "g",
                "proposed_abstract_representation": "r",
                "observable_proxy": "o", "expected_effect_on_wall": "e",
                "risk": "r", "priority": "P0", "status": "candidate_only",
                "not_claim": {"not_proven_in_humans": True,
                              "not_simulated_yet": True, "not_v5_success": True},
                "notes_ru": "n"}

    assert classify_alignment({**base, "anchors": [], "mismatches": [],
                               "candidate_mechanisms": []})["classification"] \
        == "inconclusive_alignment"
    assert classify_alignment({**base, "anchors": [_anchor()], "mismatches":
                               [_mismatch(severity="critical",
                                          action="recalibrate")],
                               "candidate_mechanisms": [_candidate()]})["classification"] \
        == "model_mismatch_critical"
    assert classify_alignment({**base, "anchors": [_anchor()], "mismatches":
                               [_mismatch(severity="high",
                                          action="add_mechanism_stage9")],
                               "candidate_mechanisms": [_candidate()]})["classification"] \
        == "mechanistic_extension_required"
    assert classify_alignment({**base, "anchors": [_anchor()], "mismatches":
                               [_mismatch(severity="low", action="collect_data")],
                               "candidate_mechanisms": [_candidate()]})["classification"] \
        == "calibration_data_insufficient"
    assert classify_alignment({**base, "anchors": [_anchor()], "mismatches":
                               [_mismatch(severity="medium",
                                          action="recalibrate")],
                               "candidate_mechanisms": [_candidate()]})["classification"] \
        == "partially_aligned_major_gaps"
    aligned = classify_alignment(
        {**base, "anchors": [_anchor(conf="data-backed")], "mismatches": [],
         "candidate_mechanisms": [_candidate()]})
    assert aligned["classification"] == "aligned_with_current_evidence"
    assert aligned["confidence"] == "high"


def test_critical_without_action_rejected():
    manifest = {"stage": "8", "hypothesis_status": "hypothesis_not_proven",
                "prior_result": {"stage_7_classification": "robust_diffuse_wall",
                                 "v5_operational_success": False},
                "anchors": [], "candidate_mechanisms": [],
                "stage9_priorities": [{"priority": "P0", "mechanism_id": "m",
                                       "rationale_ru": "r",
                                       "first_prototype_ru": "p"}],
                "mismatches": [{"name": "mm", "model_assumption": "a",
                                "biological_evidence_summary": "e",
                                "severity": "critical", "affects": ["repair"],
                                "recommended_action": "",
                                "notes_ru": "n"}]}
    check = validate_manifest(manifest)
    assert not check["valid"]
    assert classify_alignment(manifest)["classification"] == "inconclusive_alignment"


def test_missing_proxy_or_risk_rejected(manifest):
    bad = copy.deepcopy(manifest)
    bad["candidate_mechanisms"][0]["observable_proxy"] = "  "
    assert not validate_manifest(bad)["valid"]
    bad = copy.deepcopy(manifest)
    bad["candidate_mechanisms"][0]["risk"] = ""
    assert not validate_manifest(bad)["valid"]


def test_model_dynamics_change_rejected(manifest):
    bad = copy.deepcopy(manifest)
    bad["boundary_params"] = {"conversion_scale": 0.5}
    check = validate_manifest(bad)
    assert not check["valid"]
    assert any("dynamics" in err for err in check["errors"])


def test_ru_statuses_present(validated):
    classification = validated["classification"]
    assert classification["classification_ru"]
    assert classification["confidence_ru"]
    manifest = validated["manifest"]
    assert manifest["hypothesis_status_ru"] == "гипотеза не доказана"
    assert manifest["prior_result"]["stage_7_classification_ru"] == \
        "устойчивая диффузная стена"
    assert manifest["limitations_ru"]


def test_no_model_dynamics_change_by_validator():
    import longevity.model.boundary as boundary
    import longevity.model.organism as organism

    assert hasattr(boundary, "validate_boundary_params")
    assert hasattr(organism, "OrganismModel")
