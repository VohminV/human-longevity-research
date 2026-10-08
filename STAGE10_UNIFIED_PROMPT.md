# STAGE 10 — UNIFIED PROMPT (ChatGPT + Qwen merged)

> Собрано из двух исходников в `Promt.md` (верхняя детальная версия + нижняя компактная).
> Противоречий нет, только разная детализация. Ниже — объединение без потерь:
> взята структура детальной версии, добавлены явные числа/пороги/формулировки из компактной.
> Этот файл — канон для выполнения. После выполнения — только диагностика, без изменения модели.

## ROLE

Ты — Senior Computational Biologist + Senior Python Engineer проекта `human-longevity-research`.
Работай строго научно: **данные → декомпозиция → проверка → классификация → интерпретация.**
Не меняй модель для получения желаемого результата.

## CONTEXT (факты Stage 9 / 9b, не предположения)

- Stage 9: `epigenetic rollback` успешно подавляет `H_epi`; `H_epi slope ≈ 5.4e-05`; `rollback events` происходят; `biological_age slope ≈ 1.1666`.
- Stage 9b: проведена LODO-абляция всех 8 `aging drivers` (подавление `base_aging_rate` на 90%, scale `×0.1`); лучший эффект `dna_damage ≈ 2.79%`; остальные `≤ 0.22%`; ни один не достиг операционного порога `30%`; baseline воспроизводим на seeds `42, 7, 99`; production model не изменялась; classification `aggregation_or_unresolved_residual`.
- Следовательно, сейчас нельзя утверждать, что residual slope вызван конкретным драйвером.
- 600 тестов проходят. НЕ переходить к multi-driver rollback до декомпозиции.

## GOAL — Stage 10 Biological Age Decomposition

Главный вопрос:

> **Из какого математического компонента существующей модели возникает residual `biological_age slope ≈ 1.1666` после успешного epigenetic rollback?**

Это диагностический эксперимент. НЕ пытаться уменьшить slope. Только установить происхождение.

## 1. ABSOLUTE RESTRICTION — не менять production semantics

Запрещено: менять `biological-age formula`, `weights`, `setpoint`, `aging rates`, `rollback`, `intervention policy`, добавлять новый `aging/repair` механизм, `nonlinear aggregation`, `RL`, оптимизировать параметры ради уменьшения slope, менять `aggregation formula`.
Разрешены только: `instrumentation`, `analysis`, `experiment configuration`, `artifact`, `tests`, `documentation of observed results`.

## 2. FIND THE ACTUAL FORMULA

Изучить код, не реконструировать по предположению. Найти фактическую реализацию: `biological_age`, `biological_age_setpoint`, `aging-driver contributions`, `aggregation`, `thresholds`, любые `nonlinear/coupled terms`. В отчёте — точные файлы/функции. Если формула отличается от предполагаемой — использовать фактическую.

Ожидаемая (подлежит проверке): `src/longevity/model/aging.py::aggregate_biological_age` + `src/longevity/model/organism.py::OrganismModel._driver_step` (+ `_apply_driver_effect`, `_apply_reversibility_effect`, `_organ_backed_step` blending, `_apply_epigenetic_backup_effect`) + `src/longevity/model/epigenetic_backup.py::entropy_bio_contribution`. Плюс проверить: `floor/max()`, капы `damage ∈ [0,1]`, `effective_reversal`, `emergent_weights`, пропуск `entropy` на шагах интервенций, stale `bio` после reversibility-чисток.

## 3. INSTRUMENTATION (без изменения результата)

Для каждого timestep (где возможно) сохранить: `biological_age`, `biological_age_setpoint`, 8 драйверов (`DNA damage`, `epigenetic drift`, `proteostasis`, `mitochondrial`, `senescence`, `stem exhaustion`, `inflammation`, `cancer propensity`), их фактические `contribution` в `biological_age` (если нет отдельного значения — вычислить через существующую формулу без её изменения, метод задокументировать), отдельно `backup/entropy contribution`, `noise`, `scaling`, `offsets`, `thresholds`, `nonlinear/coupling/resource` термы — только если реально участвуют. Не придумывать отсутствующие компоненты.

## 4. RECONSTRUCTION CHECK

Построить `reconstructed_biological_age` из фактических компонентов. `reconstruction_residual = biological_age − reconstructed_biological_age`. Посчитать: `mean`, `median`, `max absolute`, `std`, `slope` остатка.

## 5. ACCOUNTING TEST

Проверить `biological_age ≈ sum(actual_components)` с учётом `offsets/setpoint/noise`. Если residual на уровне машинной/численной погрешности → `accounting_closed = true`, иначе `false`. НЕ исправлять автоматически. Если не замыкается — найти причину (`omitted term`, `nonlinear`, `hidden state`, `implementation detail`, `instrumentation error`).

## 6. SLOPE DECOMPOSITION

Для каждого компонента — `component_slope` за тот же интервал, что в Stage 9/9b (adult rows). Проверить `sum(component_slopes) ≈ biological_age_slope`. При нелинейности не притворяться, что сумма точна: показать `raw slopes`, `actual slope`, `nonlinear/coupling residual`. Не считать величину состояния драйвера доказательством влияния на slope. Отдельно: `setpoint slope`, `total driver slope`, `backup slope`, `residual slope`. Ответить численно, какая часть `1.1666` из setpoint, а какая из contributions (если setpoint статичен — явно `setpoint_slope = 0`, не менять его).

## 7. THREE CONDITIONS (одинаковая декомпозиция)

- A. Baseline без rollback (та же база, rollback выключен).
- B. Stage 9 rollback (threshold `0.03` / intensity `1.0` / interval `1.0`, apoptosis `q10` — лучший из 54×3).
- C. B + лучший Stage 9b single ablation (`dna_damage × 0.1`). Остальные параметры идентичны. Seeds `42, 7, 99`, horizon `150.0`, `dt 0.25`.

## 8. COMPARE

Для каждого компонента: `baseline / rollback / rollback+DNA`, `slope`, `delta from baseline`, `delta from rollback`. Что изменилось после rollback (например, `epigenetic contribution ↓`, `H_epi ↓`, но `bio slope ≈ unchanged`)? Что осталось и продолжает формировать slope?

## 9. SETPOINT + NONLINEAR / COUPLING

Setpoint — отдельно (статичен или динамичен + вклад). Проверить код на `nonlinear/multiplicative/thresholds/clipping/interactions/resource coupling/bio feedback/state-dependent weights`. Если нет → `nonlinear_coupling = none_detected`. Если есть — какой term способен создавать slope. Новый механизм не создавать. Важное правило: `driver state ≠ driver contribution ≠ driver slope`; из «абляция не сработала» не следует автоматически «виновата агрегация».

## 10. CLASSIFICATION — ровно одна, по данным, не заранее

- `driver_contribution` — один contribution объясняет основную часть (доля `≥50%`, отрыв `≥2×`, воспроизводимо).
- `distributed_contribution` — несколько делят slope, доминанта нет.
- `setpoint_dynamics` — значительная часть из динамики setpoint.
- `aggregation_or_coupling` — существующая aggregation/coupling объясняет динамику.
- `accounting_discrepancy` — декомпозиция не замыкается, существенный необъяснённый остаток.
- `unresolved` — данных недостаточно (честный выход, если не локализуется).

Пороги `30% / 2× / 50%` — операционные, не законы биологии.

## 11. ANALYSIS MODULE

`def analyze_biological_age_decomposition(results: dict) -> dict` в стиле проекта. Ключи: `bio_age_slope`, `conditions {baseline, rollback, rollback_dna_ablation}`, `component_slopes {<component>: float}`, `setpoint {slope, contribution}`, `reconstruction {mean_residual, median_residual, max_abs_residual, residual_std, residual_slope, accounting_closed}`, `nonlinear_coupling {detected, terms}`, `classification`, `confidence (high|medium|low)`. Classification — результат анализа, не ручной ввод.

## 12. ARTIFACT + TESTS + VERIFICATION

- `experiments/configs/organism_biological_age_decomposition.json` + `experiments/output/organism_biological_age_decomposition.json`, на существующей архитектуре артефактов.
- Тесты: `reconstruction`, `slope decomposition`, `residual`, `multi-condition`, `deterministic`, `classification`, `schema`. Тестировать правило подсчёта, а не ожидаемый научный вывод.
- После: полный test suite + число тестов, детерминизм, legacy-совместимость, неизменность production semantics, валидный JSON, `git diff summary`, список изменённых файлов.

## 13. FINAL REPORT (строго)

1. Implementation (файлы/изменения). 2. Actual formula (файлы/функции/алгоритм). 3. Experiment (conditions/seeds/horizon/config). 4. Component slopes (таблица Baseline/Rollback/Rollback+DNA). 5. Reconstruction (mean/max/std/slope/accounting_closed). 6. Setpoint (численный вклад). 7. Nonlinear/coupling (что реально найдено). 8. Classification (ровно одна). 9. Scientific interpretation (только `within this computational model`, `the decomposition indicates`, `the current implementation produces`; запрет `proves`, `fundamental biological law`, `universal limit`, `aging is mathematically proven`, `thermodynamic entropy of aging`, `rejuvenation/immortality is (im)possible`). 10. What remains unresolved. 11. Exactly ONE next experiment (не реализовывать). 12. Verification (tests/determinism/artifact/legacy/git diff).

## FINAL RULE

Не уменьшать slope. Понять, откуда `≈1.1666` после rollback. Если не локализуется — честно `unresolved`. HYP-0 оставить `hypothesis_not_proven`.
