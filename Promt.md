# ROLE

Ты — Senior Computational Biologist + Senior Python Engineer проекта `human-longevity-research`.

Работай строго научно:

**данные → декомпозиция → проверка → классификация → интерпретация.**

Не меняй модель для получения желаемого результата.

---

# CONTEXT

Stage 9:

- epigenetic rollback успешно подавляет H_epi;
- H_epi slope ≈ `5.4e-05`;
- rollback events происходят;
- biological_age slope остаётся ≈ `1.1666`.

Stage 9b:

- проведена LODO-ablation всех 8 aging drivers;
- каждый driver подавлялся на 90%;
- лучший эффект дал `dna_damage`: только `2.79%`;
- остальные drivers дали ≤ `0.22%`;
- ни один driver не достиг операционного порога `30%`;
- baseline воспроизводим на seeds `42, 7, 99`;
- production model не изменялась;
- classification:

```text
aggregation_or_unresolved_residual
```

Следовательно, сейчас нельзя утверждать, что residual slope вызван конкретным aging driver.

---

# GOAL

Провести **Stage 10 — Biological Age Decomposition**.

Главный вопрос:

> **Из какого математического компонента существующей модели возникает residual biological-age slope ≈ 1.1666 после успешного epigenetic rollback?**

Это диагностический эксперимент.

На этом этапе НЕ пытайся уменьшить slope.

Нужно только установить его происхождение.

---

# 1. ABSOLUTE RESTRICTION

НЕ менять production semantics.

Запрещено:

- менять biological-age formula;
- менять weights;
- менять biological-age setpoint;
- менять aging rates;
- менять rollback;
- менять intervention policy;
- добавлять новый aging mechanism;
- добавлять новый repair mechanism;
- добавлять nonlinear aggregation;
- добавлять RL;
- оптимизировать параметры ради уменьшения slope.

Разрешены только:

- instrumentation;
- analysis;
- experiment configuration;
- artifact;
- tests;
- documentation of observed results.

---

# 2. FIND THE ACTUAL BIOLOGICAL AGE FORMULA

Сначала изучи существующий код.

Не реконструируй формулу по предположению.

Найди фактическую реализацию:

- biological_age;
- biological_age_setpoint;
- aging-driver contributions;
- aggregation;
- thresholds;
- any nonlinear/coupled terms.

В отчёте укажи точные файлы/функции, которые реально формируют biological_age.

Если формула отличается от предполагаемой — использовать именно фактическую реализацию.

---

# 3. INSTRUMENTATION

Добавь diagnostic instrumentation без изменения результата расчёта.

Для каждого timestep, где возможно, сохрани:

### Biological age

- biological_age;
- biological_age_setpoint.

### Aging drivers

- DNA damage;
- epigenetic drift;
- proteostasis;
- mitochondrial dysfunction;
- cellular senescence;
- stem exhaustion;
- chronic inflammation;
- cancer propensity.

### Contributions

Для каждого driver получить его фактический contribution в biological_age.

Если contribution в текущем коде отсутствует как отдельное значение:

- вычислить его через существующую формулу;
- не изменяя саму формулу;
- документировать метод реконструкции.

### Other terms

Отдельно сохранить все существующие:

- backup contribution;
- noise;
- scaling;
- offsets;
- thresholds;
- nonlinear terms;
- coupling terms;
- resource-related terms;

если они реально участвуют в biological_age.

Не придумывать отсутствующие компоненты.

---

# 4. RECONSTRUCTION CHECK

Для каждого timestep построить:

```text
reconstructed_biological_age
```

из фактических компонентов существующей формулы.

Затем:

```text
reconstruction_residual =
    biological_age
    - reconstructed_biological_age
```

Посчитать:

- mean residual;
- median residual;
- max absolute residual;
- residual standard deviation;
- residual slope.

---

# 5. ACCOUNTING TEST

Проверить:

```text
biological_age
≈
sum(actual_components)
```

с учётом существующих offsets/setpoint/noise/etc.

Если residual близок к машинной/численной погрешности:

```text
accounting_closed = true
```

Если residual существенный:

```text
accounting_closed = false
```

НЕ исправлять residual автоматически.

Если accounting не замыкается — найти причину.

Это может быть:

- omitted term;
- nonlinear transformation;
- hidden state;
- implementation detail;
- instrumentation error.

---

# 6. SLOPE DECOMPOSITION

Для каждого компонента рассчитать slope на том же временном диапазоне, который использовался в Stage 9b.

Получить:

```text
component_slope
```

Например:

```text
dna_damage_slope
epigenetic_drift_slope
proteostasis_slope
...
setpoint_slope
backup_slope
other_term_slope
```

Проверить:

```text
sum(component_slopes)
≈
biological_age_slope
```

Если присутствует нелинейность, не притворяться, что простая сумма slope является точной декомпозицией.

В этом случае явно показать:

- raw component slopes;
- actual biological_age slope;
- nonlinear/coupling residual.

---

# 7. THREE CONDITIONS

Провести одну и ту же декомпозицию для трёх условий:

### A. Baseline

Без epigenetic rollback.

### B. Stage 9 rollback

С успешным epigenetic rollback.

### C. Stage 9 rollback + DNA ablation

Использовать лучший Stage 9b single-driver ablation:

```text
dna_damage × 0.1
```

Почему DNA:

он дал максимальный эффект в Stage 9b — `2.79%`.

Все остальные параметры оставить идентичными.

---

# 8. COMPARE THE THREE CONDITIONS

Для каждого компонента показать:

```text
baseline
rollback
rollback + DNA ablation
```

и:

```text
slope
delta from baseline
delta from rollback
```

Особенно важно определить:

### Что изменилось после rollback?

Например:

```text
epigenetic contribution ↓
H_epi ↓
но biological_age slope ≈ unchanged
```

### Что осталось?

Определить компоненты, которые продолжают формировать slope.

---

# 9. SETPOINT ANALYSIS

Отдельно исследовать biological-age setpoint.

Определить:

```text
setpoint slope
```

Если setpoint статичен:

```text
setpoint_slope = 0
```

и это должно быть явно указано.

Если setpoint динамический:

показать его вклад в residual slope.

Не менять setpoint.

---

# 10. NONLINEAR / COUPLING ANALYSIS

Проверить существующий код на наличие:

- nonlinear transformations;
- multiplicative terms;
- thresholds;
- clipping;
- interactions;
- resource coupling;
- biological-age feedback;
- state-dependent weights.

Если таких механизмов нет:

```text
nonlinear_coupling = none_detected
```

Если есть:

показать, какой именно term способен создавать slope.

Не создавать новый nonlinear mechanism.

---

# 11. CLASSIFICATION

После анализа выбрать РОВНО одну классификацию:

```text
driver_contribution
```

если один существующий contribution объясняет основную часть residual slope.

```text
distributed_contribution
```

если slope формируется несколькими contributions и ни один не доминирует.

```text
setpoint_dynamics
```

если значительная часть slope возникает из динамического setpoint.

```text
aggregation_or_coupling
```

если существующая aggregation/coupling структура объясняет residual dynamics.

```text
accounting_discrepancy
```

если decomposition не замыкается и есть существенный unexplained residual.

```text
unresolved
```

если имеющихся данных недостаточно для различения этих вариантов.

Не выбирать classification заранее.

---

# 12. IMPORTANT SCIENTIFIC RULE

Не делать вывод:

> "если driver ablation не сработал, значит aggregation является причиной."

Это НЕ следует автоматически.

Также:

> driver state ≠ driver contribution ≠ driver slope.

Не смешивать эти три понятия.

---

# 13. ANALYSIS MODULE

Создай в существующем стиле проекта analysis function:

```python
def analyze_biological_age_decomposition(results: dict) -> dict:
    ...
```

Предпочтительная структура:

```python
{
    "bio_age_slope": float,

    "conditions": {
        "baseline": {...},
        "rollback": {...},
        "rollback_dna_ablation": {...}
    },

    "component_slopes": {
        "<component>": float
    },

    "setpoint": {
        "slope": float,
        "contribution": float
    },

    "reconstruction": {
        "mean_residual": float,
        "max_abs_residual": float,
        "residual_std": float,
        "residual_slope": float,
        "accounting_closed": bool
    },

    "nonlinear_coupling": {
        "detected": bool,
        "terms": [...]
    },

    "classification": "...",

    "confidence": "high | medium | low"
}
```

Classification должен быть результатом анализа, а не ручным вводом.

---

# 14. EXPERIMENT ARTIFACT

Создай:

```text
experiments/configs/organism_biological_age_decomposition.json
```

и:

```text
experiments/output/organism_biological_age_decomposition.json
```

Используй существующую архитектуру experiment artifacts.

Не создавать новую параллельную систему результатов.

---

# 15. TESTS

Добавь тесты для:

- reconstruction;
- slope decomposition;
- residual calculation;
- multi-condition comparison;
- deterministic output;
- classification;
- artifact schema.

Не тестировать ожидаемый научный результат.

То есть тест должен проверять:

> "если входные данные такие-то, classification считается правильно"

а не:

> "classification обязательно должна быть aggregation_or_coupling".

---

# 16. VERIFICATION

После реализации:

1. Запусти полный test suite.
2. Проверь количество тестов.
3. Проверь deterministic reproducibility.
4. Проверь legacy compatibility.
5. Проверь, что production model semantics не изменились.
6. Проверь artifact JSON.
7. Покажи git diff summary.
8. Укажи все изменённые файлы.

---

# 17. FINAL REPORT

Отчёт строго в таком формате:

## 1. Implementation

Файлы и изменения.

## 2. Actual biological-age formula

Точная существующая реализация:

- файлы;
- функции;
- формула/алгоритм.

## 3. Experiment

Conditions, seeds, horizon, configuration.

## 4. Component slopes

Таблица:

| Component | Baseline | Rollback | Rollback + DNA ablation |
|---|---:|---:|---:|

## 5. Reconstruction

- mean residual;
- max residual;
- residual std;
- residual slope;
- accounting_closed.

## 6. Setpoint

Численный вклад setpoint.

## 7. Nonlinear / coupling terms

Что реально обнаружено в существующей модели.

## 8. Classification

Ровно одна:

```text
driver_contribution
distributed_contribution
setpoint_dynamics
aggregation_or_coupling
accounting_discrepancy
unresolved
```

## 9. Scientific interpretation

Только выводы, непосредственно поддержанные данными.

Использовать:

> "within this computational model"

> "the decomposition indicates"

> "the current implementation produces"

Не использовать:

> "proves"

> "fundamental biological law"

> "universal limit"

> "aging is mathematically proven"

## 10. What remains unresolved

Все ограничения.

## 11. Exactly ONE next experiment

Предложить только один следующий эксперимент.

НЕ реализовывать его.

## 12. Verification

- tests;
- deterministic reproducibility;
- artifact;
- legacy compatibility;
- git diff.

---

# FINAL RULE

**Этот этап не должен пытаться сделать biological_age slope меньше.**

Его единственная задача:

> **понять, откуда в существующей модели появляется slope ≈ 1.1666 после успешного epigenetic rollback.**

Если источник не удаётся локализовать — честный результат:

```text
unresolved
```

# Stage 10 — Biological Age Decomposition

Stage 9b завершён.

Результат:
- rollback успешно подавляет H_epi;
- baseline biological_age slope = 1.1666;
- 90%-ное подавление каждого из 8 aging drivers отдельно почти не меняет slope;
- максимальный эффект DNA damage = 2.79%;
- остальные эффекты ≤ 0.22%;
- classification = aggregation_or_unresolved_residual;
- production model не изменялась;
- 600 тестов проходят.

НЕ переходить пока к multi-driver rollback.

## Цель
Определить, из какого математического компонента текущей модели возникает residual biological-age slope, не изменяя саму модель.
Это диагностический эксперимент.

---

# 1. НЕ МЕНЯТЬ PRODUCTION MODEL
Запрещено:
- менять aggregation formula;
- менять weights;
- менять biological-age setpoint;
- добавлять nonlinear aggregation;
- добавлять новый aging mechanism;
- добавлять новый repair mechanism;
- менять rollback;
- оптимизировать модель ради уменьшения slope.

Только instrumentation + analysis + experiment artifact + tests.

---

# 2. Разложить biological_age
Для каждого timestep, где это возможно, получить:
- biological_age;
- biological_age_setpoint;
- DNA damage contribution;
- epigenetic drift contribution;
- proteostasis contribution;
- mitochondrial contribution;
- cellular senescence contribution;
- stem exhaustion contribution;
- inflammation contribution;
- cancer propensity contribution;
- epigenetic backup contribution;
- noise contribution;
- любые дополнительные существующие компоненты aggregation.

Используй существующую реализацию модели.
НЕ реконструируй формулу вручную, если её можно получить из фактического model state.

---

# 3. Проверка баланса
Для каждого timestep вычислить:
`reconstructed_biological_age` из существующих компонентов.

Проверить:
`reconstructed_biological_age - biological_age`

Отдельно вывести:
- mean residual;
- max absolute residual;
- residual slope.

Если residual практически нулевой — зафиксировать, что aggregation accounting замыкается.
Если residual существенный — НЕ исправлять его автоматически.
Классифицировать как diagnostic discrepancy и найти источник.

---

# 4. SLOPE DECOMPOSITION
Для каждого компонента рассчитать slope за тот же временной интервал, что использовался для Stage 9/9b.

Получить:
`component_slope`

и проверить:
`sum(component_slopes) ≈ biological_age_slope`
с учётом setpoint/noise/других реально существующих компонентов.

Не считать величину состояния драйвера доказательством его влияния на slope.

---

# 5. SETPOINT ANALYSIS
Отдельно рассчитать:
- setpoint slope;
- total driver contribution slope;
- backup contribution slope;
- residual slope.

Ответить численно:
> Какая часть 1.1666 slope возникает из динамики setpoint, а какая — из driver contributions?

Если setpoint не является динамическим компонентом — явно указать это.

---

# 6. NONLINEARITY / COUPLING DIAGNOSTIC
Если aggregation нелинейная или содержит coupling:
не менять её.

Только определить:
- какие terms являются nonlinear;
- какие terms зависят от других state variables;
- какие terms могут создавать slope при почти неизменных driver states.

Если существующая aggregation линейна — так и написать.
Не вводить новую nonlinear formula.

---

# 7. THREE CONDITIONS
Сравнить одинаковую decomposition для:
A. baseline без rollback
B. Stage 9 rollback
C. Stage 9 rollback + лучший Stage 9b single-driver ablation (DNA damage)

Цель:
посмотреть, какой компонент изменился после rollback, а какой продолжил формировать slope.

---

# 8. PRIMARY QUESTION
Ответить строго численно:
> Если все отдельные driver ablations из Stage 9b почти не меняют biological-age slope, откуда математически берётся residual slope 1.1666?

Возможные результаты:

### A. Driver contribution
Residual slope в основном объясняется одним существующим contribution.

### B. Distributed contribution
Несколько contribution совместно формируют slope.

### C. Setpoint dynamics
Значительная часть slope возникает из setpoint dynamics.

### D. Aggregation/coupling
Существующая aggregation/coupling создаёт residual dynamics.

### E. Accounting discrepancy
Компоненты не замыкаются и есть unexplained residual.

Не выбирать вариант заранее.

---

# 9. ARTIFACT
Создать:
`experiments/configs/organism_biological_age_decomposition.json`
и:
`experiments/output/organism_biological_age_decomposition.json`

Использовать существующую архитектуру experiment artifacts.

---

# 10. ANALYSIS
Создать analysis function в существующем стиле проекта.
Например:
```python
def analyze_biological_age_decomposition(results: dict) -> dict:
    ...
```

Результат должен содержать:
```python
{
    "bio_age_slope": float,
    "component_slopes": {...},
    "setpoint_slope": float,
    "reconstruction": {
        "mean_residual": float,
        "max_abs_residual": float,
        "residual_slope": float
    },
    "conditions": {
        "baseline": {...},
        "rollback": {...},
        "rollback_dna_ablation": {...}
    },
    "classification": "driver_contribution" | "distributed_contribution" | "setpoint_dynamics" | "aggregation_or_coupling" | "accounting_discrepancy"
}
```
Classification должна быть основана только на измеренных данных.

---

# 11. TESTS
Добавить тесты:
- reconstruction;
- slope decomposition;
- component accounting;
- deterministic output;
- schema;
- classification.

Не тестировать заранее ожидаемый научный результат.
Полный test suite обязателен.

---

# 12. SCIENTIFIC RESTRICTIONS
Не использовать формулировки:
- "aging is mathematically proven";
- "fundamental biological wall";
- "thermodynamic entropy of aging";
- "rejuvenation is impossible";
- "immortality is impossible".

Корректные формулировки:
- "within this computational model";
- "the decomposition indicates";
- "the current aggregation produces";
- "the experiment does not establish whether this reflects real biology".

HYP-0 оставить:
`hypothesis_not_proven`

---

# 13. FINAL REPORT
Отчёт:

## 1. Implementation
## 2. Experiment
## 3. Component slopes
## 4. Reconstruction error
## 5. Setpoint contribution
## 6. Aggregation/coupling
## 7. Comparison: baseline vs rollback vs DNA ablation
## 8. Classification
## 9. Scientific interpretation
## 10. Remaining uncertainty
## 11. Exactly ONE next experiment
## 12. Verification

Не реализовывать следующий эксперимент.

Главное правило:
Stage 10 должен объяснить происхождение наблюдаемого slope, а не пытаться его уменьшить.

Если объяснение не найдено — вернуть `unresolved` и не подгонять модель.
