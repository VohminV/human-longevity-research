# Publication Readiness — Stages 9 / 9b / 10 / 10.5

> Статус модели для текущей публикационной версии: **заморожена как вычислительный артефакт**
> (`implementation discrepancy = false`, результаты воспроизводимы).
> `HYP-0: hypothesis_not_proven` во всех артефактах.
> Названия файлов, параметров и статусов из кода даны `моноширинным шрифтом`.
> Остальной текст — на русском.

## Publication handoff (по §24 Promt)

```text
model_state: unchanged
stage9_status: done_prototype_no_miracle
stage9b_status: done_aggregation_or_unresolved_residual_low_confidence
stage10_status: done_aggregation_or_coupling_medium_confidence
stage10_5_status: done_partial_accounting_medium_confidence

main_computational_finding:
    residual slope 1.1666 after successful rollback is carried in slope
    terms by directly_accounted drivers (sum 1.3339, bio/sum 0.8746,
    top3 share 0.808), discounted by reconstructed couplings
    (nonlinear gap -0.1672, 14.34% of bio); level books do NOT close
    (max_abs 1.07 vs tol ~0.32)

main_unresolved_issue:
    per-channel split of the -0.167 slope gap and the 1.07 level gap
    across caps / blending lag / shadowing / diminishing gate is not
    separable from stored damages/entropy alone; reversibility/network
    ledgers and resource/feedback states are not_identifiable for
    s.biological_age in the investigated path

publication_safe_claims:
    - rollback suppresses H_epi (5.35e-05) but bio slope stays 1.1666
    - no single driver explains residual (best DNA 2.79% < 30%)
    - top slope carriers are proteostasis/mito/stem, none dominant
    - accounting is computational attribution, not causal proof

claims_requiring_caution:
    - any statement of the form coupling explains residual quantitatively
      in full (only partial_accounting is shown; gap 14.34% remains)

claims_not_supported:
    - candidate immortality policy exists
    - v1/v2/v3/v4/v5/v6 passed anywhere
    - hidden aging mechanism found
    - 100% accounting achieved
```

Для каждого основного вывода (по §24):

### Вывод 1. Rollback работает по энтропии, но не по биовозрасту

```text
finding: epigenetic rollback подавляет H_epi до 5.35e-05, slope биовозраста остаётся 1.1666
evidence: experiments/output/organism_rollback_attribution.json (baseline bio 1.1666192491, h_epi 5.3535e-05, seeds 42/7/99 идентичны);
          experiments/output/organism_backup_rollback_search_long.csv (54 точки, lifespan 67.5–68.75, bounded_any False везде)
confidence: high
scope: Stage 9 прототип reference_restore (threshold 0.03 / intensity 1.0 / interval 1.0 / apoptosis q10), 150 лет, dt 0.25
limitation: абстрактный организм, порядковые параметры, n=3 сида (описательный разброс, не значимость)
```

### Вывод 2. Ни один драйвер не объясняет остаток

```text
finding: лучший single-driver ablation (dna_damage x0.1) даёт 2.79%, остальные <=0.22%, порог 30% не взят нигде
evidence: experiments/output/organism_rollback_attribution.json (dna 1.134044 vs 1.166619; mito 0.224%; proteostasis 0.202%;
          stem 0.148%; senescence 0.123%; inflammation 0.102%; cancer 0.095%; drift -0.553%)
confidence: high (операционный порог) / low (причинная интерпретация — запрещена)
scope: Stage 9b LODO x0.1, seeds 42/7/99, production model untouched
limitation: driver state != driver contribution != driver slope; ablation-mute ожидается из-за капов и repair-gate
```

### Вывод 3. Наклон несут белки/мито/стволовые, но без доминанта

```text
finding: rollback-компоненты: proteostasis_loss 0.4561 (33.73%), mitochondrial_dysfunction 0.3649 (26.99%),
         stem_exhaustion 0.2720 (20.11%), senescence 0.1132, inflammation 0.0861, dna 0.0358, cancer 0.0237,
         epigenetic_drift -0.0184, backup 0.00043, setpoint 0.0; топ-3 дают 80.83%, ни один не берёт 50% + margin 2x
evidence: experiments/output/organism_biological_age_decomposition.json (bio 1.1666192491, sum 1.3338990247,
          classification aggregation_or_coupling, confidence medium)
confidence: medium
scope: Stage 10 три условия x 3 сида (без отката / с откатом / с откатом + DNA x0.1), формула aggregate_biological_age + entropy_bio_contribution
limitation: линейная slope-арифметика поверх нелинейной агрегации (капы, floor, blending lag); сумма намеренно overshoot'ит bio
```

### Вывод 4. Stage 10.5: partial accounting, discrepancy нет

```text
finding: decision_case partial_accounting (medium): напрямую учтено 87.46% slope (bio/sum),
         нелинейный зазор -0.16728 (14.34%), level-зазор max_abs 1.07206 vs tol ~0.31838,
         residual_slope -0.01423 (1.22%); implementation_discrepancy = false
evidence: experiments/output/organism_channel_accounting.json (decision partial_accounting, confidence medium,
          accounted_slope_fraction 0.8745933744, gap_share 0.1433884926, accounting_closed false,
          deterministic rerun identical, seeds [42, 7, 99])
confidence: medium
scope: анализ поверх хранимых артефактов Stage 10 + 9b; production semantics не менялась; production model files не менялись
limitation: The remaining uncertainty is a limitation of the current computational attribution,
            not evidence for an unknown biological mechanism. Поканальный сплит -0.167
            принципиально неразделим из существующих полей траектории.
```

---

## 1. Final model version

```text
model_version: 0.5.0 (src/longevity/model/organism.py::ORGANISM_MODEL_VERSION)
data_version: 0.1.0
model_scope: abstract_epigenetic_backup_organism_life_course
organism_stack: mechanistic_drivers + reduced_organ_proxies + reduced_network_feedback
                + split_reversible_irreversible + reference_restore
coordination_mode (Stage 9 path): independent_reversibility
adult_age_setpoint: 25.0
hypothesis_status: hypothesis_not_proven (все артефакты)
```

Production semantics не изменены. Production model files не изменены.
Добавлены только: анализ (`src/longevity/analysis/channel_accounting.py`),
конфиг (`experiments/configs/organism_channel_accounting.json`),
артефакт (`experiments/output/organism_channel_accounting.json`),
тесты (`tests/test_channel_accounting.py`, 11 шт.), документация.

## 2. Exact configuration hashes / identifiers

```text
organism_backup_rollback_baseline.json (config): sha256 2d1d466d0c657113
organism_rollback_attribution.json (config):    sha256 1112316d67139d9a
organism_biological_age_decomposition.json:     sha256 9da04fe326ac6d50
organism_channel_accounting.json (config):      sha256 ab1a4df2967c3a6b

organism_biological_age_decomposition.json (output): sha256 326f6c59452b55c1
organism_rollback_attribution.json (output):         sha256 15dc93a02b3ae48a
organism_channel_accounting.json (output):           sha256 a76166f3ae42187f

organism_backup_rollback_search_best.json: config_hash aa5173ec3c0ae25903b203bd817033c85d2629218159c0f1bb7d437301d594d4
seeds everywhere: [42, 7, 99]
dt: 0.25, duration_years: 150.0
rollback path: policy_index 6 threshold 0.03 / intensity 1.0 / interval 1.0 + apoptosis policy_index 7 interval 10.0
ablation: dna_damage base_aging_rate x0.1 (Stage 9b best, Stage 10 condition C)
```

## 3. Stage 9 results

- Прототип `reference_restore`: захват референса в 25 лет, entropy-gated rollback + периодический синтетический апоптоз.
- Поиск `54x3`: `v6` не пройден нигде (`bounded_any False` во всех 54 строках
  `organism_backup_rollback_search_long.csv`), жизнь `67.5–68.75` (лучшее `68.75/60.0`,
  смерть `brain_failure`), энтропийный наклон в норме, стенка та же распределённая.
- Бейзлайн `organism_backup_rollback_baseline.json` (seed 42): жизнь `68.75`,
  `H_epi` подавлена, `biological_age` финал `111.53`, `rejuvenation_events 22`,
  `rollback_events 5`, `apoptosis_events 5`.
- Вывод Stage 9: механизм работает, чуда нет; `HYP-0` не доказана.

## 4. Stage 9b attribution

- База: лучший Stage 9 rollback-конфиг (`0.03/1.0/1.0`, апоптоз `q10`), `bio 1.1666192491`,
  `H_epi 5.3535052733e-05`, все три сида бит-идентичны.
- Аблации `8 x 3` (`base_aging_rate x0.1` по одному драйверу):

```text
dna_damage                 1.134044  (-2.7923%)
mitochondrial_dysfunction  1.164006  (-0.2240%)
proteostasis_loss          1.164267  (-0.2016%)
stem_exhaustion            1.164895  (-0.1478%)
cellular_senescence        1.165187  (-0.1227%)
chronic_inflammation       1.165426  (-0.1023%)
cancer_prone               1.165512  (-0.0949%)
epigenetic_drift           1.173067  (+0.5527%, ухудшение)
```

- Операционный порог `30%` не взят нигде. Классификация Stage 9b:
  `aggregation_or_unresolved_residual`, уверенность низкая.
- Сейчас нельзя утверждать, что residual вызван конкретным драйвером.

## 5. Stage 10 decomposition

- Формула фактическая (не предполагаемая):

```text
biological_age = max(floor, adult_setpoint + sum_i(contribution_i * damage_i / adult_reference_i))
                 + entropy_bio_weight * epigenetic_entropy
files: src/longevity/model/aging.py::aggregate_biological_age
       src/longevity/model/organism.py::OrganismModel._driver_step
       src/longevity/model/epigenetic_backup.py::entropy_bio_contribution
method: reconstructed from stored damages/entropy without changing the formula
```

- Три условия (`baseline` без отката / `rollback` / `rollback + dna x0.1`), сиды `42, 7, 99`.
- Откат срезал эпигенетику (`+0.539 -> -0.018`) и энтропию (`0.03004 -> 0.00043`),
  но общий наклон упал лишь `1.67117 -> 1.16662 -> 1.13404`.
- Реконструкция не замкнулась: `mean -0.19308`, `median -0.08953`, `max_abs 1.07206`
  (tolerance `~0.31838`), `residual_slope -0.01423`, `accounting_closed false`.
- Сумма компонент `1.33390` vs `bio 1.16662`, `nonlinear_coupling_residual -0.16728`.
- Один виноватый не найден: топ-3 `~80.83%`, ни один не тянет половину с margin `2x`.
- Капы и связки глушат точечные гашения (`base_rate` ручка != наклон один к одному).
- Классификация: `aggregation_or_coupling`, уверенность средняя. `HYP-0` не доказана.

## 6. Stage 10.5 channel accounting

### 6.1 Фактический execution path (документирован по коду, §22 scientific выполнено)

```text
1 OrganismModel.step — оркестрация, прямого bio-члена нет
2 _development_step — рост/резерв, прямого bio-члена нет
3 _aging_step provisional bio_rate (0.85 + 1.6*global_damage + 0.8*senescence) — ПЕРЕЗАПИСАН ниже
4 _driver_step + aggregate_biological_age + entropy_bio_contribution — ПОСЛЕДНЯЯ
  mechanistic-запись s.biological_age в пути без интервенций
5 _organ_backed_step emergent blending ((1-w)*damage + w*level) — ПОСЛЕ вычисления bio,
  one-step stale-bio coupling; веса dna 0.0 / drift 0.0 / proteostasis 0.2 / mito 0.2 /
  senescence 0.5 / stem 0.3 / inflammation 0.5 / cancer 0.3
6 _organ_network_step — пишет ТОЛЬКО biological_age_network, s.biological_age НЕ трогает
7 _reversibility_step — пишет ТОЛЬКО biological_age_reversibility + floor_dynamic,
  s.biological_age напрямую НЕ трогает
8 _epigenetic_backup_step (entropy_step) — обновляет entropy; влияет на СЛЕДУЮЩИЙ шаг
  через entropy-член и drift_noise_coupling 0.15 в накопление epigenetic_drift
9 apply_effect — delta_biological_age применён, ЗАТЕМ перезаписан ре-агрегацией (shadowing);
  entropy пропущена при driver-only пересчёте; reversibility-чистка stale'ит bio;
  rollback ре-агрегирует + entropy
```

### 6.2 Каналы и измеримость (§22 scientific выполнено)

```text
directly_accounted (10):
  dna_damage 0.03580283 (share 0.02648)
  epigenetic_drift -0.01839888 (share -0.01361)
  proteostasis_loss 0.45611549 (share 0.33729)
  mitochondrial_dysfunction 0.36494337 (share 0.26987)
  cellular_senescence 0.11320367 (share 0.08371)
  stem_exhaustion 0.27196404 (share 0.20111)
  chronic_inflammation 0.08614993 (share 0.06371)
  cancer_prone 0.02369030 (share 0.01752)
  epigenetic_backup_entropy 0.00042828 (share 0.00032)
  adult_setpoint 25.0 offset, slope 0.0

reconstructed (6, направление известно, поканальный сплит неразделим):
  damage_cap_saturation_[0,1] — кламп damage в _driver_step + blending
  floor_max_setpoint — max(floor, setpoint+sum); в adult rollback-пути не биндится (bio >> floor)
  emergent_blending_lag — blending ПОСЛЕ bio, виден только на следующем шаге
  drift_noise_coupling — entropy * 0.15 в накопление drift; откатом подавлено к ~0
  intervention_shadowing — delta_bio перезаписан; entropy omission; stale после clearance
  repair_diminishing_gate — effective_reversal 1-damage/saturation + repair_capacity*reserve;
    объясняет ablation-mute

not_identifiable (6, отдельного bio-члена в исследованном пути нет):
  reversibility_age_ledger (reversibility age + floor_dynamic + reversible/irreversible +
    information_debt / mutation_fixation / niche_disorder / entropy_production)
  network_age_ledger (network age + deficit/shortfall/gain/mutation/continuity/fibrosis/cancer/cascade)
  provisional_bio_rate (перезаписан _driver_step в mechanistic-режиме)
  organ_proxy_resources (proxy damage/senescence/fibrosis/cancer/ECM/vascular + 4 ресурса;
    только косвенно через blending и global_damage)
  network_edges_feedback_limits (12 рёбер + 7 петель + hard limits; только косвенно)
  global_debts (информация/мутации/ниша/энтропия AUC; каpped-леджеры без прямого bio-члена)
```

### 6.3 Residual количественно (§22 scientific выполнено)

```text
bio_age_slope_rollback_mean:        1.1666192491
sum_component_slopes_mean:          1.3338990247
nonlinear_coupling_residual_mean:   -0.1672797756
gap_share (|nonlin|/|bio|):          0.1433884926 (14.34%)
accounted_slope_fraction (bio/sum):  0.8745933744 (87.46%)
reconstruction mean:                -0.1930786357
reconstruction median:              -0.0895308075
reconstruction max_abs:              1.0720622903 (tol ~0.3183772830)
reconstruction std:                  0.2980113564
reconstruction residual_slope:       -0.0142335504 (share 0.0122006819, 1.22%)
accounting_closed:                   false
dna_ablation_relative_improvement:   0.0279228196 (2.79%, порог 30% не взят)
top3_share:                          0.8082707927
substantial (>0.30):                 [proteostasis_loss] (только один)
```

100% accounting НЕ требуется и НЕ достигнут. Это допустимый научный результат:
часть residual принципиально неразделима из существующей реализации.

### 6.4 Accounting не выдаётся за causal proof

- `driver state != driver contribution != driver slope` (смешивать запрещено).
- То, что ablation драйверов глушится, НЕ доказывает автоматически, что виновата агрегация.
  Направление зазора (сумма overshoot'ит bio) согласуется с известными couplings
  (капы, blending lag, shadowing, diminishing gate), но это attribution,
  а не доказательство причинности и не скрытый механизм старения.
- Все необъяснённые компоненты явно перечислены (§6.5).

### 6.5 Все необъяснённые компоненты явно перечислены

```text
- nonlinear slope gap -0.1672797756 (14.34% bio): поканальный сплит across
  damage_cap_saturation / emergent_blending_lag / intervention_shadowing /
  repair_diminishing_gate НЕИЗМЕРИМ из хранимых damages/entropy
  (нужны per-step blend deltas, cap-hit counts, recompute-event flags)
- level gap max_abs 1.0720622903 vs tol ~0.318: форма timing/lag, не только наклон
- residual_slope -0.0142335504 (1.22%): остаточная slope-форма level-невязки
- reversibility/network леджеры и resource/feedback состояния: not_identifiable
  для s.biological_age в исследованном пути (нет прямого члена)
```

### 6.6 Decision Gate (§23)

Решение заранее не устанавливалось как `frozen` или `revised`. По результату:

```text
decision_case: partial_accounting (confidence medium)
implementation_discrepancy: false
```

- НЕ `channel_identified` (нет одного канала с majority + margin при закрытых книгах).
- НЕ `distributed_channels` (книги не закрыты; `accounting_closed false`).
- ДА `partial_accounting`: существенная часть объяснена напрямую учитываемыми
  драйверами (`0.8746 bio/sum`, `top3 0.8083`), но часть остаётся
  (`gap 14.34%` + `level 1.07`); искусственно закрывать assumptions запрещено;
  дальнейшая работа только при отдельном научном обосновании.
- НЕТ `accounting_discrepancy`: заявленная формула совпала с фактической
  production-реализацией; баг не обнаружен; чинить нечего; affected result
  биологически не интерпретируется (таких нет).
- НЕТ `unresolved` в чистом виде: мажорная доля показана, ограничение зафиксировано
  как неразделимость сплита, а не как полное отсутствие данных.

Следствие: модель computationally consistent относительно исследованного
execution path на уровне partial accounting; новых диагностических экспериментов
для объяснения этого residual НЕ требуется; новых механизмов НЕ добавлять.

## 7. Reproducibility status

```text
full test suite: 623 passed (612 исходных + 11 новых test_channel_accounting.py), EXIT 0
targeted tests: test_biological_age_decomposition.py (12) + test_attribution_analysis.py (14)
                + test_epigenetic_backup.py (21) = 47 passed;
                test_channel_accounting.py (11) passed
deterministic rerun: Stage 10 rerun bio 1.1666192491132565 == artifact (identical);
                     Stage 10.5 rerun identical (два прогона в tmp совпали побайтово кроме runtime)
seeds matched: [42, 7, 99] в Stage 9 поиске, Stage 9b attribution, Stage 10 decomposition,
               Stage 10.5 accounting (конфиг валидирует точное равенство)
JSON valid: allow_nan=False дамп проходит для decomposition, attribution, channel_accounting;
            NaN/Infinity в файлах отсутствуют
production semantics: не изменены
production model files: не изменены (только новые analysis/config/artifact/tests/docs)
```

Воспроизведение (PowerShell; в Linux заменить `$env:PYTHONPATH='src';` на `PYTHONPATH=src`):

```powershell
$env:PYTHONPATH='src'; python -m pytest -q
$env:PYTHONPATH='src'; python -m pytest tests/test_biological_age_decomposition.py tests/test_attribution_analysis.py tests/test_epigenetic_backup.py tests/test_channel_accounting.py -v
$env:PYTHONPATH='src'; python -c "import sys; sys.path.insert(0, 'src'); from longevity.analysis.biological_age_decomposition import run_biological_age_decomposition; run_biological_age_decomposition('experiments/configs/organism_biological_age_decomposition.json')"
$env:PYTHONPATH='src'; python -c "import sys; sys.path.insert(0, 'src'); from longevity.analysis.channel_accounting import run_channel_accounting; run_channel_accounting('experiments/configs/organism_channel_accounting.json')"
```

## 8. Known limitations

- Абстрактный организм, порядковые параметры, операционные пороги — не калиброванная биология.
- `n=3` сида — описательный разброс, не значимость.
- `reduced_organ_proxies` (8), 12 рёбер, 7 петель, hard limits — reduced абстракция, не анатомия.
- Slope-арифметика линейна поверх нелинейной агрегации (капы, floor, blending lag).
- Траектории хранят damages/entropy, но не per-step blend deltas, cap-hit counts,
  recompute-event flags — поэтому сплит `-0.167` неразделим текущей инструментацией.
- Reversibility/network леджеры диагностические; прямого bio-члена нет.
- Горизонт `150 лет`, `dt 0.25`; чувствительность к `eps/dt/seed` для Stage 10.5
  отдельно не свипилась (это было сделано в Stage 6E/7 для стенки; здесь анализ
  поверх хранимых артефактов, новых симуляций не добавлялось по дизайну).
- The remaining uncertainty is a limitation of the current computational
  attribution, not evidence for an unknown biological mechanism.

## 9. Scientific claims supported by the model

`PRIMARY_RESULTS` и `SECONDARY_RESULTS` — только то, что показано кодом и артефактами.
Категории не смешиваются (см. §11).

`PRIMARY_RESULTS`:

```text
1. Rollback подавляет H_epi (5.35e-05), bio slope остаётся 1.1666 (high; Stage 9/9b/10).
2. Ни один из 8 драйверов при x0.1 не даёт >=30% улучшения bio slope; лучший DNA 2.79% (high operationally).
3. Slope-носители после отката: proteostasis 0.456 + mito 0.365 + stem 0.272 при epi drift -0.018 и backup 0.00043;
   доминанта нет (medium; Stage 10).
4. Partial accounting: 87.46% slope напрямую за драйверами, зазор 14.34% + level 1.07 — реконструированные
   couplings (капы/blending/shadowing/gate), discrepancy нет (medium; Stage 10.5).
```

`SECONDARY_RESULTS`:

```text
1. Setpoint статичен (slope 0.0); setpoint-динамика не при чём.
2. Entropy-член после успешного rollback почти нулевой slope (0.00043); стена не в H_epi.
3. DNA-аблация убирает свой вклад почти в ноль, общий наклон двигает лишь на 2.79% — ручка base_rate != наклон
   (капы + diminishing gate + смешивание между прокси).
4. Emergent blending идёт ПОСЛЕ вычисления bio (one-step stale) — задокументированная связь реализации.
5. Provisional bio_rate, reversibility age и network age не пишут s.biological_age в исследованном пути
   (not_identifiable для этого вопроса).
```

## 10. Claims explicitly NOT supported by the model

`NEGATIVE_RESULTS` (честные отрицательные; это тоже результаты):

```text
1. v1/v2/v3/v4/v5/v6 не пройдены нигде (Stage 5A/5C/6A/6B/6C/9: 0 везде, включая 54x3 поиск и 70 стресс-проверок).
2. Candidate immortality policy НЕ найдена (HYP-0 hypothesis_not_proven везде).
3. Single removable driver НЕ найден (лучшее -2.79%, порог заметности 20% и операционный 30% не взяты).
4. Knife-edge/резкая граница НЕ найдена (Stage 6E 8x3 + 36 ячеек чувствительности).
5. 100% accounting НЕ достигнут (accounting_closed false; max_abs 1.07 > tol 0.32).
6. Скрытый механизм старения НЕ найден (Stage 10.5 не ищет его по дизайну; см. §29).
7. Coupling НЕ доказан как причина (accounting != causal proof; см. §29).
```

## 11. Категории без смешивания (§26)

`PRIMARY_RESULTS`: см. §9 (4 пункта).

`SECONDARY_RESULTS`: см. §9 (5 пунктов).

`NEGATIVE_RESULTS`: см. §10 (7 пунктов).

`LIMITATIONS`:

```text
1. Абстрактная модель, порядковые параметры, операционные пороги.
2. n=3, reduced proxies/edges/loops/limits, dt 0.25, горизонт 150.
3. Линейная slope-архитектура поверх нелинейного кода; сплит -0.167 неразделим хранимыми полями.
4. not_identifiable леджеры не дают bio-slope доли в этом пути.
5. Остаточная неопределённость — ограничение attribution, не доказательство новой биологии.
```

`FUTURE_WORK` (НЕ запускается автоматически; только при отдельном научном вопросе
с falsifiable prediction и заранее определённым stop criterion, §27):

```text
1. Per-step инструментация blending deltas / cap-hit counts / recompute-event flags —
   только если будет отдельный вопрос про разделимость -0.167 со stop criterion
   вида accounting_closed true/false на фиксированных допусках.
2. Отдельные биологические гипотезы (P0–P6 из Stage 8) — вне freeze, отдельной версией
   модели и отдельным обоснованием.
3. Manuscript preparation: figures, tables, supplementary artifacts, reproducibility checks.
```

## 12. Publication Freeze Rule (§25)

```text
implementation discrepancy = false
основные результаты воспроизводимы (623 passed, deterministic rerun, seeds matched, JSON ok)
=> модель МОЖЕТ быть заморожена для текущей публикационной версии.
```

Freeze означает (запрещено):

```text
- менять scientific semantics
- подгонять модель под желаемый результат
- добавлять новые aging mechanisms
- менять aggregation
- менять parameters ради улучшения результата
- проводить новые эксперименты только потому, что текущий результат неудобен
```

Разрешены:

```text
- bug fixes (только реальные баги, с локализацией и повтором затронутых экспериментов)
- documentation
- figures
- tables
- supplementary artifacts
- reproducibility checks
- manuscript preparation
```

Любое изменение production semantics после freeze требует отдельной версии модели
и отдельного научного обоснования.

## 13. No automatic next-stage escalation (§27) + Stop condition (§28)

- Запрещён автоматический переход к `Stage 11/12/13...` и добавление
  новых aging/repair mechanisms, multi-driver interventions, RL, genetic algorithms,
  optimization, новых causal assumptions.
- Следующий эксперимент допустим только при отдельном научном вопросе
  (следует из Stage 10.5; falsifiable prediction; не ради красивого результата;
  заранее определённый stop criterion). Stage 10.5 сам следующий эксперимент НЕ реализует.
- Показан `residual partially accounted with no implementation discrepancy` —
  экспериментальную цепочку автоматически НЕ продолжать.
- Зафиксировано: The remaining uncertainty is a limitation of the current
  computational attribution, not evidence for an unknown biological mechanism.
- Приоритетом была бы проверка реализации при `implementation discrepancy`
  (не обнаружен), а не добавление новой биологии.

## 14. Final scientific principle (§29)

Главный результат Stage 10.5 — НЕ доказать coupling и НЕ найти скрытый механизм старения.

Главный результат:

> определить, насколько residual biological-age slope объясняется непосредственно
> существующим execution path модели и насколько остаётся необъяснённым.

Итог по допустимым финальным выводам (§29):

```text
Moderate result: major fraction accounted; remaining fraction unresolved
(87.46% slope напрямую, зазор 14.34% + level 1.07 неразделимы текущей инструментацией,
 discrepancy нет, decision partial_accounting, confidence medium)
```

Результат не выбирался заранее: decision вычислен порогами из данных
(`accounting_closed`, `gap_rel`, `residual_rel`, `accounted_slope_fraction`, `top3_share`),
а не захардкожен. Любой из четырёх исходов (strong/moderate/diagnostic/negative)
был бы валидным; получен moderate/partial — и это честно зафиксировано без
искусственного закрытия residual дополнительными assumptions.
