"""Reference (observed) data for the preimplantation calibration.

Every numeric target here is traced to a primary or explicitly graded source
(docs/DATA_SOURCES.md). Scope is STRICTLY the preimplantation period: zygote
through blastocyst (day 5-7, IVF/in vitro culture). Nothing beyond that belongs
here.

Two families of targets:
- STAGE_REACH_TIMES -- time when a stage is REACHED (hours post-insemination),
  Istanbul consensus time-lapse grading (S-7), nominal + range.
- BLASTOCYST_COUNTS -- direct nuclear counts of whole blastocysts at fixed
  culture days (S-6, Hardy 1989), mean + SD. NOT hard rules: these are
  observations with scatter, to be compared as mean/uncertainty/range.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

CALIBRATION_DATASET_VERSION = "preimplantation/v1"


class ParameterStatus(str, Enum):
    """Taxonomy for every model parameter (required for CALIBRATION.md).

    - OBSERVED: taken from a direct measurement of this quantity.
    - INFERRED: backed by a published estimate, but not a direct measurement.
    - ASSUMPTION: a modelling choice with no direct data.
    - CALIBRATED: set by fitting the model to the reference dataset.
    - UNKNOWN: no reliable estimate; deliberately undefined.
    """

    OBSERVED = "obs"
    INFERRED = "inf"
    ASSUMPTION = "assumption"
    CALIBRATED = "calibrated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReferencePoint:
    """One observed measurement to calibrate against."""

    key: str
    label: str
    observed_mean: float
    observed_sd: float | None
    units: str
    source: str
    method: str
    scope: str
    notes: str = ""
    observed_range: tuple[float, float] | None = None


@dataclass(frozen=True)
class ParameterStatusEntry:
    path: str
    status: ParameterStatus
    value: float
    rationale: str
    source: str = ""


STAGE_REACH_TIMES: tuple[ReferencePoint, ...] = (
    ReferencePoint(
        key="time_to_2_cell",
        label="2-cell stage reached",
        observed_mean=27.0,
        observed_sd=None,
        observed_range=(26.0, 28.0),
        units="hours",
        source="S-7",
        method="IVF time-lapse consensus grading",
        scope="in vitro",
        notes="Istanbul consensus (Alpha Scientists / ESHRE SIG Embryology).",
    ),
    ReferencePoint(
        key="time_to_4_cell",
        label="4-cell stage reached",
        observed_mean=44.0,
        observed_sd=None,
        observed_range=(43.0, 45.0),
        units="hours",
        source="S-7",
        method="IVF time-lapse consensus grading",
        scope="in vitro",
    ),
    ReferencePoint(
        key="time_to_8_cell",
        label="8-cell stage reached",
        observed_mean=68.0,
        observed_sd=None,
        observed_range=(67.0, 69.0),
        units="hours",
        source="S-7",
        method="IVF time-lapse consensus grading",
        scope="in vitro",
    ),
    ReferencePoint(
        key="time_to_morula",
        label="morula stage reached",
        observed_mean=92.0,
        observed_sd=None,
        observed_range=(90.0, 94.0),
        units="hours",
        source="S-7",
        method="IVF time-lapse consensus grading",
        scope="in vitro",
    ),
    ReferencePoint(
        key="time_to_blastocyst",
        label="blastocyst stage reached",
        observed_mean=116.0,
        observed_sd=None,
        observed_range=(114.0, 118.0),
        units="hours",
        source="S-7",
        method="IVF time-lapse consensus grading",
        scope="in vitro",
    ),
)

BLASTOCYST_COUNTS: tuple[ReferencePoint, ...] = (
    ReferencePoint(
        key="cell_count_at_120h",
        label="blastocyst cell count, day 5",
        observed_mean=58.3,
        observed_sd=8.1,
        units="cells",
        source="S-6",
        method="differential nuclear labelling, whole blastocyst",
        scope="in vitro",
        notes="Hardy, Handyside & Winston 1989; n=181 embryos. TE 37.9±6.0, ICM 20.4±4.0.",
    ),
    ReferencePoint(
        key="cell_count_at_144h",
        label="blastocyst cell count, day 6",
        observed_mean=84.4,
        observed_sd=5.7,
        units="cells",
        source="S-6",
        method="differential nuclear labelling, whole blastocyst",
        scope="in vitro",
        notes="Hardy, Handyside & Winston 1989. TE 40.3±5.0, ICM 41.9±5.0.",
    ),
    ReferencePoint(
        key="cell_count_at_168h",
        label="blastocyst cell count, day 7",
        observed_mean=125.5,
        observed_sd=19.0,
        units="cells",
        source="S-6",
        method="differential nuclear labelling, whole blastocyst",
        scope="in vitro",
        notes="Hardy, Handyside & Winston 1989. TE 80.6±15.2, ICM 45.6±10.2.",
    ),
)

STAGE_REACH_BY_KEY: dict[str, ReferencePoint] = {p.key: p for p in STAGE_REACH_TIMES}
BLASTOCYST_COUNT_BY_KEY: dict[str, ReferencePoint] = {p.key: p for p in BLASTOCYST_COUNTS}
ALL_REFERENCE_POINTS: dict[str, ReferencePoint] = {**STAGE_REACH_BY_KEY, **BLASTOCYST_COUNT_BY_KEY}

MORULA_CELL_COUNT_APPROX = (16.0, 32.0)
"""Morula is roughly 16-32 cells at ~96 h (S-9, secondary). Used only for
stage inference heuristics, never as a hard calibration rule."""


PARAMETER_STATUS: tuple[ParameterStatusEntry, ...] = (
    ParameterStatusEntry(
        path="doubling_time_mean",
        status=ParameterStatus.INFERRED,
        value=10.8,
        rationale=(
            "Per-division doubling time 10-12 h cited for cleavage-stage human "
            "embryos (S-8). Default 10.8 h. This describes the per-division "
            "draw, NOT the net population doubling of the whole preimplantation "
            "window; the two differ because cleavage is asynchronous and, in "
            "the real embryo, the cell cycle lengthens late (blastocyst)."
        ),
        source="S-8",
    ),
    ParameterStatusEntry(
        path="doubling_time_sd",
        status=ParameterStatus.ASSUMPTION,
        value=1.2,
        rationale="Scatter of per-division cycle length is not directly measured; 1.2 h is a modelling choice.",
    ),
    ParameterStatusEntry(
        path="mortality.rate",
        status=ParameterStatus.ASSUMPTION,
        value=0.0,
        rationale=(
            "Cell death at blastocyst stages is real (Hardy 1989 reports a few "
            "% per embryo) but is not constrained by a measured rate; default "
            "0.0 keeps the baseline honest."
        ),
        source="S-6",
    ),
    ParameterStatusEntry(
        path="telomere.length_start",
        status=ParameterStatus.UNKNOWN,
        value=100.0,
        rationale="Telomere mechanics are irrelevant within the 0-168 h calibration window (no divisions shorten a zygote to senescence).",
    ),
    ParameterStatusEntry(
        path="telomere.loss_per_division",
        status=ParameterStatus.UNKNOWN,
        value=5.0,
        rationale="Same as telomere.length_start: out of calibration scope.",
    ),
    ParameterStatusEntry(
        path="dna_damage.accrual_per_division",
        status=ParameterStatus.UNKNOWN,
        value=0.2,
        rationale="DNA-damage burden is out of calibration scope for the 0-168 h window.",
    ),
    ParameterStatusEntry(
        path="dna_damage.threshold",
        status=ParameterStatus.UNKNOWN,
        value=5.0,
        rationale="Out of calibration scope.",
    ),
    ParameterStatusEntry(
        path="dna_damage.repair_per_division",
        status=ParameterStatus.UNKNOWN,
        value=0.0,
        rationale="Out of calibration scope.",
    ),
    ParameterStatusEntry(
        path="cell_cycle.phases.0.threshold",
        status=ParameterStatus.ASSUMPTION,
        value=0.0,
        rationale=(
            "Structural phase boundary: phase 0 governs the first division(s) of "
            "the zygote (living count >= 1). A phase threshold is the living cell "
            "count selecting the phase, a modelling convention over an observable "
            "quantity."
        ),
    ),
    ParameterStatusEntry(
        path="cell_cycle.phases.0.mean",
        status=ParameterStatus.OBSERVED,
        value=26.0,
        rationale=(
            "Duration of the first division (zygote -> 2-cell): Istanbul "
            "consensus places 2-cell at 26-28 h post-insemination (S-7), so the "
            "first cycle is ~24-28 h. Mean 26 h sits inside the consensus range."
        ),
        source="S-7",
    ),
    ParameterStatusEntry(
        path="cell_cycle.phases.0.sd",
        status=ParameterStatus.ASSUMPTION,
        value=2.0,
        rationale="Cycle-length scatter of the first division not directly measured; 2.0 h keeps 26 +/- a plausible spread inside the 24-28 h window.",
    ),
    ParameterStatusEntry(
        path="cell_cycle.phases.0.death_per_division",
        status=ParameterStatus.ASSUMPTION,
        value=0.0,
        rationale="Default 0; Model C raises the post-8-cell phase death (documented blastocyst phenomenon, rate unconstrained, S-6).",
        source="S-6",
    ),
    ParameterStatusEntry(
        path="cell_cycle.phases.1.threshold",
        status=ParameterStatus.ASSUMPTION,
        value=2.0,
        rationale=(
            "Cleavage phase starts once the embryo has 2 cells (count >= 2). "
            "Boundary choice; compatible with EGA timing literature (bulk "
            "transcription only after the reductive cleavage series, S-19)."
        ),
        source="S-19",
    ),
    ParameterStatusEntry(
        path="cell_cycle.phases.1.mean",
        status=ParameterStatus.INFERRED,
        value=17.0,
        rationale=(
            "Cleavage-stage cycle length inferred from the Istanbul timing "
            "segment: 2-cell at ~27 h, 4-cell at ~44 h (S-7) gives ~17 h per "
            "cleavage division. By contrast the S-8 time-lapse per-division "
            "figure of 10-12 h, measured over short windows, cannot reproduce "
            "the observed stage-reach times and is documented as a discrepancy "
            "rather than used."
        ),
        source="S-7",
    ),
    ParameterStatusEntry(
        path="cell_cycle.phases.1.sd",
        status=ParameterStatus.ASSUMPTION,
        value=1.5,
        rationale="Scatter of cleavage-cycle length not directly measured; 1.5 h is a modelling choice.",
    ),
    ParameterStatusEntry(
        path="cell_cycle.phases.1.death_per_division",
        status=ParameterStatus.ASSUMPTION,
        value=0.0,
        rationale="Cleavage-stage cell death is minimal in the reference window; kept 0.",
    ),
    ParameterStatusEntry(
        path="cell_cycle.phases.2.threshold",
        status=ParameterStatus.INFERRED,
        value=8.0,
        rationale=(
            "Post-EGA phase begins at the 8-cell count: major human ZGA is "
            "completed by the 8-cell stage (S-19, S-20), after which cleavage "
            "lengthens. Boundary taken as count >= 8."
        ),
        source="S-19",
    ),
    ParameterStatusEntry(
        path="cell_cycle.phases.2.mean",
        status=ParameterStatus.INFERRED,
        value=24.0,
        rationale=(
            "Post-EGA cycle length inferred as intermediate (~24 h): the "
            "S-7 blastocyst reach (~116 h) and Hardy growth from day 5 to day 7 "
            "(58 -> 84 -> 126 cells; S-6) imply effective per-division times of "
            "~18-24 h deep into blastulation. 45-47 h would be needed to match "
            "the day 5-7 net growth alone, which overshoots the early counts; "
            "the U-shaped deceleration that no single lengthened phase can fit "
            "is a Stage 4 finding (see CALIBRATION.md), not a hidden parameter."
        ),
        source="S-7",
    ),
    ParameterStatusEntry(
        path="cell_cycle.phases.2.sd",
        status=ParameterStatus.ASSUMPTION,
        value=3.0,
        rationale="Scatter of post-EGA cycle length not directly measured; 3.0 h is a modelling choice.",
    ),
    ParameterStatusEntry(
        path="cell_cycle.phases.2.death_per_division",
        status=ParameterStatus.ASSUMPTION,
        value=0.0,
        rationale=(
            "Per-division death rate at blastulation is a documented phenomenon "
            "(Hardy 1989), but its value is not constrained by a measurement -- "
            "default 0. Model C sets it to 0.05 as a stated assumption to test "
            "whether death alone (without cycle tuning) reconciles the late "
            "counts; the sweep sweeps 0.0-0.20."
        ),
        source="S-6",
    ),
)


def parameter_status_table() -> list[dict[str, str | float]]:
    """Flat, serializable version of PARAMETER_STATUS for experiment reports."""
    return [
        {
            "parameter": entry.path,
            "status": entry.status.value,
            "value": entry.value,
            "rationale": entry.rationale,
            "source": entry.source,
        }
        for entry in PARAMETER_STATUS
    ]