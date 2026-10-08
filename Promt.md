# ROLE

Ты — Senior Computational Biologist + Senior Python Engineer проекта `human-longevity-research`.

Работай строго научно: сначала данные → затем анализ → затем классификация → только после этого интерпретация.

Не подгоняй эксперимент под гипотезу и не вводи громкие термины до подтверждения механизмом.

---

# TASK

Реализуй **Stage 9b — Causal Attribution / Constraint Attribution**.

Stage 9 уже показал:

- epigenetic rollback работает;
- H_epi / epigenetic entropy существенно подавляется;
- rollback events происходят;
- legacy mode не изменён;
- biological-age slope при этом остаётся положительным (~1.33);
- `robust_bounded_degradation_v6 = false`.

Теперь необходимо определить:

> **Что именно удерживает biological-age slope после успешного epigenetic rollback?**

Проверяем три возможности:

1. один оставшийся aging driver становится доминирующим;
2. остаточный slope распределён между несколькими drivers;
3. ни один driver отдельно не объясняет slope, и причина находится в aggregation/setpoint/interactions/resources либо пока не идентифицирована.

**Не предполагай заранее ни один из этих вариантов.**

---

# 1. CONFIGURATION

Создай:

`experiments/configs/organism_rollback_attribution.json`

Используй **лучшую существующую Stage 9 rollback configuration**, которая дала минимальный воспроизводимый H_epi slope.

Не создавай новую оптимизацию rollback policy.

Используй минимум 3 deterministic seeds:

```text
42
7
99
```

Во всех экспериментах должны быть одинаковыми:

- initial state;
- simulation horizon;
- rollback policy;
- intervention schedule;
- resources;
- thresholds;
- model parameters;
- model version.

Меняется только явно указанный ablation.

---

# 2. BASELINE ROLLBACK

Для каждого seed запусти:

**rollback без driver ablation**

Сохрани:

- biological_age slope;
- H_epi slope;
- final biological_age;
- lifespan;
- healthspan;
- значения всех 8 aging drivers;
- вклад каждого driver в biological_age, если такой diagnostic уже существует;
- epigenetic_backup state;
- resource states;
- system failure information.

Если возможно без изменения production semantics, сохраняй time-series.

Не ограничивайся только final state.

---

# 3. DRIVER ABLATION

Для каждого существующего aging driver проведи:

`rollback + driver_scale = 0.1`

Drivers:

1. DNA damage
2. epigenetic drift
3. proteostasis
4. mitochondrial dysfunction
5. cellular senescence
6. stem pools
7. inflammation
8. cancer propensity

Каждое условие повторить для всех трёх seeds.

Важно:

Это **ablation/sensitivity attribution**, а не автоматическое доказательство причинности.

Не называй результат causal proof, если эксперимент фактически проверяет только sensitivity к `driver_scale`.

Не меняй production semantics.

---

# 4. CALCULATE EFFECT

Для каждого driver:

```text
delta_slope =
    baseline_rollback_slope
    - ablated_slope
```

и:

```text
relative_improvement =
    delta_slope / baseline_rollback_slope
```

Рассчитай:

- значение для каждого seed;
- mean;
- standard deviation;
- lifespan delta;
- healthspan delta.

Сделай ranking drivers по reproducible slope reduction.

---

# 5. SINGLE DRIVER

Используй заранее заданный operational criterion.

Driver может считаться **candidate dominant residual constraint**, если:

1. его ablation уменьшает biological-age slope воспроизводимо;
2. среднее relative improvement > 30%;
3. эффект не объясняется очевидным resource/system-failure confounder.

Для классификации `single_driver_migration` дополнительно:

- этот driver должен иметь наибольший эффект;
- его эффект должен быть минимум примерно в 2 раза больше следующего driver.

Важно:

`30%` и `2×` — это **операционные пороги данного эксперимента**, а не биологические законы.

---

# 6. DISTRIBUTED RESIDUAL

Используй:

`distributed_residual`

если:

- несколько drivers имеют воспроизводимый существенный эффект;
- ни один не удовлетворяет single-driver criterion;
- удаление любого одного driver недостаточно для устранения большей части residual slope.

Не определяй distributed residual только по величине самих driver states.

Главный критерий — изменение biological-age slope при ablation.

---

# 7. UNRESOLVED CASE

Если ни один driver отдельно не объясняет residual slope:

используй:

`aggregation_or_unresolved_residual`

НЕ называй это автоматически `aggregation_artifact`.

Потому что возможны:

- aggregation;
- biological-age setpoint;
- nonlinear interactions;
- resource limitation;
- system-level dynamics;
- coupling между drivers;
- другой существующий механизм модели.

Выполни диагностическую декомпозицию:

- driver contributions;
- biological-age setpoint;
- aggregation;
- resources;
- system-level failure.

Но **не изменяй aggregation formula**.

---

# 8. OPTIONAL INTERACTION TEST

Если результаты показывают несколько потенциально важных drivers, проведи дополнительный тест top-2:

A. rollback  
B. rollback + driver A ablation  
C. rollback + driver B ablation  
D. rollback + A+B ablation

Сравни:

```text
effect(A)
effect(B)
effect(A+B)
```

Проверь, является ли эффект примерно аддитивным или присутствует interaction.

Если:

```text
effect(A+B) != effect(A) + effect(B)
```

зафиксируй это как **model interaction**, а не как доказательство биологической синергии.

---

# 9. ANALYSIS MODULE

Создай:

`src/longevity/analysis/attribution_analysis.py`

Реализуй детерминированную функцию:

```python
def analyze_constraint_migration(results: dict) -> dict:
    ...
```

Результат должен иметь структуру:

```python
{
    "classification":
        "single_driver_migration"
        | "distributed_residual"
        | "aggregation_or_unresolved_residual",

    "baseline": {
        "bio_slope_mean": float,
        "bio_slope_by_seed": dict,
        "h_epi_slope_mean": float,
        "driver_slopes": dict
    },

    "ablation_results": {
        "<driver>": {
            "bio_slope_mean": float,
            "bio_slope_by_seed": dict,
            "slope_improvement_mean": float,
            "relative_improvement_mean": float,
            "slope_improvement_std": float,
            "lifespan_delta": float,
            "healthspan_delta": float
        }
    },

    "ranking": [...],

    "candidate_binding_driver": str | None,

    "interaction_analysis": {...},

    "confidence":
        "high"
        | "medium"
        | "low"
}
```

Не позволяй analysis function самостоятельно делать биологические выводы за пределами заданных классификационных правил.

---

# 10. CONFIDENCE

### HIGH

Если:

- эффект воспроизводится на всех seeds;
- один driver явно отделён от остальных;
- нет серьёзного confounder.

### MEDIUM

Если:

- эффект воспроизводим;
- но несколько drivers имеют близкие эффекты;
- либо остаётся частичный confounder.

### LOW

Если:

- большая межseed variance;
- эффект слабый;
- system/resource failure мешает attribution;
- результаты не позволяют различить механизмы.

---

# 11. ARTIFACT

Создай machine-readable artifact:

`experiments/output/organism_rollback_attribution.json`

Используй существующий формат experiment artifacts проекта.

Не создавай параллельную систему результатов.

Artifact должен содержать:

- model version;
- experiment version;
- configuration;
- seeds;
- baseline;
- all ablations;
- slope statistics;
- driver ranking;
- classification;
- confidence;
- interaction results;
- unresolved questions.

---

# 12. TESTS

Добавь тесты только для корректности:

- slope calculation;
- multi-seed aggregation;
- ranking;
- classification thresholds;
- deterministic analysis;
- missing/invalid data;
- interaction calculation;
- artifact schema.

Не пиши тесты, предполагающие, что конкретный driver обязан победить.

После этого запусти полный test suite.

---

# 13. STRICT SCIENTIFIC RESTRICTIONS

НЕ:

- менять HYP-0;
- утверждать доказательство immortality limit;
- утверждать thermodynamic entropy theory;
- утверждать universal information wall;
- утверждать, что реальные методы rejuvenation falsified;
- добавлять новый aging mechanism;
- добавлять multi-driver restoration;
- менять biological-age aggregation;
- добавлять RL;
- оптимизировать модель ради уменьшения biological-age slope;
- подгонять classification под ожидаемый результат.

Stage 9b — **только attribution**.

---

# 14. FINAL REPORT

После выполнения верни отчёт строго в формате:

## 1. Implementation

Какие файлы созданы/изменены.

## 2. Experiment

- configuration;
- seeds;
- horizon;
- baseline;
- ablation methodology.

## 3. Results

Таблица:

| Driver | Baseline slope | Ablated slope | Δ slope | Relative improvement | Lifespan Δ | Healthspan Δ |
|---|---:|---:|---:|---:|---:|---:|

## 4. Ranking

Отсортируй drivers по slope reduction.

## 5. Attribution

Какой driver или drivers реально объясняют residual slope.

## 6. Classification

Ровно один:

```text
single_driver_migration
distributed_residual
aggregation_or_unresolved_residual
```

## 7. Confidence

`high / medium / low`

с численным обоснованием.

## 8. Scientific interpretation

Только то, что непосредственно следует из эксперимента.

Используй формулировки:

- "the model shows..."
- "the ablation indicates..."
- "within this computational model..."

Не используй:

- "proves universally"
- "fundamental biological law"
- "real-world rejuvenation is impossible"

## 9. What remains unresolved

Чётко перечисли ограничения.

## 10. Next experiment

Предложи **ровно один** следующий эксперимент.

Но НЕ реализуй его.

## 11. Verification

Укажи:

- full test count;
- new tests;
- artifact path;
- git diff summary;
- legacy compatibility;
- deterministic reproducibility.

---

# FINAL RULE

Главное правило этого этапа:

> **Если данные не позволяют определить binding constraint — результатом является unresolved attribution.**

Не заставляй эксперимент выбрать driver.

Отрицательный или неопределённый результат является полноценным результатом Stage 9b.




# ROLE: Expert Computational Biologist and Systems Architect

You are working on the `human-longevity-research` project. Your task is to design and implement a rigorous **causal attribution experiment** (Stage 9b) to determine why the epigenetic rollback mechanism (implemented in Stage 9) fails to reduce the biological age slope despite successfully suppressing epigenetic entropy.

## CONTEXT: Current State

Stage 9 results show:
- Epigenetic rollback works: H_epi slope → ~0.0003–0.0009 (near zero)
- Rollback/apoptosis events fire correctly (5+ per run)
- BUT biological_age slope remains ~1.33
- robust_bounded_degradation_v6 = false in all 54/54 configurations
- Lifespan flat: 67.5–68.8 years

We need to understand **what is causing the residual biological_age slope** after successful epigenetic rollback.

## OBJECTIVE

Design a comprehensive causal attribution framework that distinguishes between three possible explanations:

1. **Single-driver residual**: One specific aging driver dominates the residual slope
2. **Distributed residual**: Multiple drivers contribute simultaneously  
3. **Aggregation artifact**: The biological_age calculation itself creates the residual slope

## TASK 1: Baseline Attribution Instrumentation

Create a diagnostic layer that tracks per-step contributions without modifying production semantics:

```python
# Add to src/longevity/analysis/attribution_instrumentation.py
class AttributionTracker:
    """Diagnostic-only tracker for biological age components."""
    
    def __init__(self, enabled=True):
        self.enabled = enabled
        self.step_data = []
    
    def record_step(self, step, drivers_state, h_epi, bio_age, setpoint):
        """Record contributions at each time step."""
        if not self.enabled:
            return
        
        entry = {
            "step": step,
            "biological_age": bio_age,
            "setpoint": setpoint,
            "h_epi": h_epi,
            "driver_contributions": {}
        }
        
        for driver_name, state in drivers_state.items():
            entry["driver_contributions"][driver_name] = {
                "damage": state.get("damage", 0),
                "contribution_weight": state.get("contribution", 0),
                "weighted_contribution": state.get("damage", 0) * state.get("contribution", 0)
            }
        
        self.step_data.append(entry)
    
    def get_slope_contributions(self):
        """Calculate slope contribution for each driver."""
        # Implement linear regression on time series
        pass
```

**Requirements:**
- Must not affect legacy behavior when disabled
- Must serialize to checkpoint (for reproducibility)
- Must track all 8 drivers + H_epi + setpoint separately

## TASK 2: Leave-One-Driver-Out (LODO) Ablation Study

Design experiments where each driver is individually suppressed after rollback:

```python
# Create experiments/configs/stage9b_lodo_attribution.json
{
    "experiment_type": "stage9b_causal_attribution",
    "description": "Leave-one-driver-out attribution for residual biological age slope",
    "seeds": [42, 7, 99],
    "base_policy": "best_rollback_from_stage9",
    
    "conditions": [
        {
            "name": "baseline_no_backup",
            "epigenetic_backup_model": "none",
            "driver_suppressions": {}
        },
        {
            "name": "rollback_only", 
            "epigenetic_backup_model": "epigenetic_hard_drive",
            "driver_suppressions": {}
        },
        {
            "name": "rollback_plus_dna_suppressed",
            "epigenetic_backup_model": "epigenetic_hard_drive",
            "driver_suppressions": {
                "dna_damage": {"base_aging_rate_scale": 0.1}
            }
        },
        {
            "name": "rollback_plus_epigenetic_suppressed",
            "epigenetic_backup_model": "epigenetic_hard_drive",
            "driver_suppressions": {
                "epigenetic_drift": {"base_aging_rate_scale": 0.1}
            }
        },
        # ... repeat for all 8 drivers:
        # proteostasis_loss, mitochondrial_dysfunction, 
        # cellular_senescence, stem_exhaustion,
        # chronic_inflammation, cancer_prone
    ],
    
    "metrics": [
        "biological_age_slope",
        "h_epi_slope", 
        "lifespan",
        "healthspan",
        "dominant_binding_driver",
        "driver_slope_contributions"
    ]
}
```

## TASK 3: Constraint Migration Analysis

```python
# Add to src/longevity/analysis/constraint_migration.py
def detect_constraint_migration(baseline_results, rollback_results):
    """
    Determine if the binding constraint shifts after rollback.
    
    Returns:
    {
        "migration_detected": bool,
        "baseline_binding": str,
        "rollback_binding": str,
        "confidence": "high|medium|low",
        "evidence": {...}
    }
    """
    pass

def classify_residual_constraint(lodo_results):
    """
    Classify the residual slope pattern.
    
    Returns one of:
    - "single_driver_constraint": One driver explains >50% of residual slope
    - "distributed_residual": Multiple drivers each explain 15-40%
    - "aggregation_artifact": No driver explains significant portion
    - "inconclusive": Insufficient data
    """
    pass
```

## TASK 4: Aggregation Structure Analysis

If LODO shows no single driver explains the slope, analyze the aggregation formula:

```python
def analyze_aggregation_structure(state_trajectory):
    """
    Decompose biological_age = setpoint + sum(w_i * damage_i)
    
    Track:
    - setpoint_contribution_over_time
    - sum_driver_contributions_over_time  
    - residual_unexplained_over_time
    - correlation between H_epi reduction and bio_age slope
    """
    pass
```

## TASK 5: Quantitative Attribution Metrics

For each condition, calculate:

```python
attribution_metrics = {
    "condition_name": str,
    "bio_age_slope": float,
    "h_epi_slope": float,
    "delta_slope_vs_rollback": float,  # How much slope changes
    "relative_contribution": float,     # % of total slope explained
    "binding_driver": str,
    "driver_slopes": {
        "dna_damage": float,
        "epigenetic_drift": float,
        # ... all 8 drivers
    },
    "statistical_confidence": float  # Based on seed variance
}
```

## TASK 6: Generate Machine-Readable Artifact

Save results to `experiments/results/stage9b_causal_attribution.json`:

```json
{
  "metadata": {
    "model_version": "...",
    "experiment_version": "stage9b",
    "timestamp": "...",
    "seeds": [42, 7, 99],
    "total_conditions": 10,
    "tests_passed": true
  },
  
  "baseline_attribution": {
    "bio_age_slope": 1.33,
    "h_epi_slope": 0.0005,
    "binding_driver": "...",
    "driver_contributions": {...}
  },
  
  "rollback_attribution": {
    "bio_age_slope": 1.31,
    "h_epi_slope": 0.0003,
    "binding_driver": "...",
    "driver_contributions": {...}
  },
  
  "lodo_results": {
    "dna_damage_suppressed": {
      "bio_age_slope": ...,
      "delta_slope": ...,
      "new_binding_driver": ...
    },
    // ... for each driver
  },
  
  "constraint_analysis": {
    "migration_detected": bool,
    "baseline_binding": "...",
    "rollback_binding": "...",
    "classification": "single_driver|distributed|aggregation_artifact|inconclusive"
  },
  
  "aggregation_diagnostic": {
    "setpoint_contribution_pct": float,
    "driver_sum_contribution_pct": float,
    "unexplained_residual_pct": float
  },
  
  "interpretation": {
    "summary": "...",
    "confidence_level": "...",
    "next_experiment_needed": "..."
  }
}
```

## TASK 7: Add Tests

Create `tests/test_stage9b_attribution.py`:

1. Test attribution tracker records correctly
2. Test LODO configuration parsing
3. Test constraint migration detection logic
4. Test classification logic for all 4 categories
5. Test aggregation decomposition
6. Test legacy compatibility (all existing tests must pass)
7. Test determinism (same seed → same attribution results)

## TASK 8: Update Documentation

Update `docs/ROADMAP.md`:
```markdown
### Stage 9b: Causal Attribution Analysis
**Status**: In Progress  
**Objective**: Determine cause of residual biological_age slope after successful epigenetic rollback  
**Method**: Leave-one-driver-out ablation + constraint migration analysis  
**Deliverable**: `experiments/results/stage9b_causal_attribution.json`
```

Update `research/hypotheses/HYP-0_immortality_policy.md`:
```markdown
## Stage 9b: Attribution Analysis Pending
- Stage 9 shows rollback works but bio_age slope persists
- Causal attribution experiment in progress
- No interpretation of results until attribution completes
- Status: hypothesis_not_proven
```

## CONSTRAINTS & RULES

1. **DO NOT** modify existing model behavior - only add diagnostic layer
2. **DO NOT** implement Stage 10 features (multi-driver restore, RL, etc.)
3. **DO NOT** change aggregation function to "fix" the problem
4. **DO NOT** introduce dramatic terminology until data confirms it
5. **DO NOT** modify HYP-0 status from `hypothesis_not_proven`
6. **MUST** maintain bit-for-bit legacy compatibility
7. **MUST** run full test suite after changes
8. **MUST** report exact test count and new tests added

## DELIVERABLES

Provide:
1. `src/longevity/analysis/attribution_instrumentation.py`
2. `src/longevity/analysis/constraint_migration.py`  
3. `experiments/configs/stage9b_lodo_attribution.json`
4. `src/longevity/experiment/stage9b_runner.py`
5. `tests/test_stage9b_attribution.py`
6. Updated documentation files
7. Summary of changes and test results

## FINAL OUTPUT FORMAT

After implementation, provide a structured report:

```
=== STAGE 9b CAUSAL ATTRIBUTION REPORT ===

SECTION 1: What Was Measured
- [List all metrics tracked]

SECTION 2: Numerical Results  
- Baseline slope: X.XX
- Rollback slope: X.XX  
- H_epi slope: X.XXXX
- Per-driver slopes: [table]

SECTION 3: Binding Constraint
- Baseline binding driver: [name]
- Rollback binding driver: [name]

SECTION 4: Constraint Migration
- Migration detected: YES/NO
- Evidence: [data]

SECTION 5: Residual Classification
- Pattern: single_driver | distributed | aggregation_artifact | inconclusive
- Confidence: high | medium | low

SECTION 6: Aggregation Analysis
- Setpoint contribution: X%
- Driver sum contribution: X%  
- Unexplained residual: X%

SECTION 7: What This Proves (Model-Internal Only)
- [Strict interpretation based on data]

SECTION 8: What Remains Unproven
- [List limitations and unknowns]

SECTION 9: Next Required Experiment
- [Specific next step based on findings]
```

**CRITICAL**: If data cannot explain the residual slope, honestly report `causal_attribution_inconclusive`. This is a valid scientific result.
