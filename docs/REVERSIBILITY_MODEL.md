# REVERSIBILITY_MODEL.md — Reversibility ceiling, irreversible accumulation,
# boundary probe и compound wall attribution (Stage 6C–6E)

> Это НЕ модель человека. Порядковые скорости, абстрактные годы, reduced
> proxies/рёбра, нет анатомии и калибровки.
> `robust_bounded_degradation_v5 = true` — модельный флаг, а не
> доказательство бессмертия. Бессмертие — `hypothesis_not_proven`.

## 1. Зачем Stage 6C

Stage 6B показал: сеть, feedback и hard limits сделали ограничения
честнее, но `biological_age_slope` остался binding, а v4 не найден.
Открытым остался главный вопрос:

```text
Растёт ли biological_age из-за обратимого мусора, который можно вычищать,
или из-за необратимого долга, который устанавливает пол?
```

Stage 6C (содержательно — идея Stage 5D внутри organ-network
архитектуры) разделяет повреждения на reversible и irreversible,
вводит conversion, repair ceiling, information debt, mutation fixation,
niche disorder и entropy production, и проверяет, существует ли политика
robust bounded degradation v5.

## 2. Reversible / irreversible split

Реализация: `src/longevity/model/reversibility.py`. Opt-in
`reversibility_model = split_reversible_irreversible` (дефолт `none`
численно идентичен Stage 6B).

Ведётся раздельный ledger:

- per-driver (8 mechanistic драйверов): reversible / irreversible /
  conversion_rate / repair_used;
- per-organ-proxy (8 прокси): то же;
- глобальные пулы: reversible_burden, irreversible_burden,
  information_debt, mutation_fixation, niche_disorder, entropy_production,
  biological_age_reversibility + dynamic floor.

Инвариант: `damage = reversible + irreversible` для каждого компонента.
Conversion переклассифицирует массу, не меняя total damage; clearance
снижает reversible и underlying damage; irreversible repair снижает
irreversible и damage в пределах ceiling/floor.

## 3. Conversion reversible → irreversible

```text
convert_i = base_conversion_rate * reversible_i * modifier * stage_mult * dt
modifier = 1 + infl*c + energy*c + repair*c + network*c + niche*c + toxicity*c
```

Плюс независимое irreversible accrual (`independent_irreversible_rate`)
для mutation fixation / information loss / niche entropy, не проходящих
через reversible стадию. Conversion ограничен доступным reversible
(отрицательных значений нет), детерминирован, реагирует на
вмешательства через prevention/suppression. Runaway = максимальная
поколоночная conversion rate выше порога.

## 4. Repair ceiling

`repair_ceiling` (дефолт 0.30) — максимум суммарного irreversible repair
за жизнь. Ремонт в пределах остатка, с diminishing returns (чем больше
использовано, тем меньше реализовано), ценой (воспаление/рак/мутация/
токсичность) и риском (information/mutation debt от агрессивного
ремонта). `ceiling=0` запрещает irreversible repair полностью.
Восстановление ниже driver floor невозможно.

## 5. Information debt, mutation fixation, niche disorder, entropy

- information_debt [0,1]: растёт с brain irreversible + epigenetic drift;
  information_preservation чинит лишь частично (×0.5); агрессивный
  irreversible repair добавляет долг;
- mutation_fixation [0,1]: медленный accrual + cancer irreversible;
  mutation_fixation_control чинит частично; surveillance снижает load,
  но не fixation бесплатно;
- niche_disorder [0,1]: растёт с воспалением/energy shortfall; niche
  support чинит ×0.6; повышает conversion modifier (coupling);
- entropy_production ≥ 0: мера стоимости поддержания порядка;
  entropy_management снижает частично.

## 6. Biological age с irreversible floor

```text
bio_rev = setpoint + w_rev*reversible + w_irr*irreversible
        + w_info*info + w_mut*mutation + w_niche*niche
floor   = setpoint + w_irr*irreversible + w_info*info + w_mut*mutation + w_niche*niche
```

Reversible вмешательства снижают только reversible вклад; irreversible
вклад формирует пол. По умолчанию пол соблюдается
(`allow_sub_adult_reversibility_age=false`); `true` — exploratory mode.

## 7. Interventions

9 новых типов (аддитивно, `rev_*` ключи инертны при `none`):
reversible_clearance, conversion_suppression, damage_prevention,
irreversible_repair_pulse (дорогой, рисковый, в пределах ceiling),
information_preservation, mutation_fixation_control,
niche_integrity_support, entropy_management,
combined_reversibility_maintenance. У каждого — цена, риск, diminishing
returns, cooldown. Старые типы работают как раньше.

## 8. Coordination

7 режимов (аддитивно): independent_reversibility, preventive_priority,
repair_ceiling_guard, information_guard, mutation_guard,
entropy_budget_scheduler, lookahead_reversibility. Вывод не форсируется.

## 9. Причины отказа и v5

Новые причины (аддитивно): irreversible_accumulation_failure,
repair_ceiling_exhaustion, conversion_runaway, information_debt_failure,
mutation_fixation_failure, niche_disorder_failure,
entropy_production_failure, biological_age_floor_erosion,
unknown_reversibility_collapse.

`robust_bounded_degradation_v5` = условия v4 плюс: bio_rev slope,
reversible/irreversible/info/mutation/niche slopes, conversion rate,
repair remaining, отсутствие runaway, v4 true. Success rate ≥ 0.8 +
worst-case дисциплина. Operational criterion, не доказательство.

## 10. Результаты v0 (в рамках модели)

| Политика | lifespan | healthspan | wall |
|---|---|---|---|
| legacy none (= Stage 6B) | 67.0 | 58.2 | bio slope |
| reversibility baseline | 67.0 | 58.2 | irreversible_accumulation |
| preventive only | 68.2 | 59.2 | bio slope |
| clearance only | 69.0 | 60.5 | bio slope |
| irreversible repair only | 67.0 | 58.2 | bio slope (ceiling не тронут) |
| combined preventive+clearance | 69.5 | 60.5 | irreversible_accumulation |
| aggressive reversal | 69.0 | 60.5 | bio slope + долги |
| neural preserving | 69.8 | 61.0 | bio slope (continuity 0.95+) |
| search best (6×3) | 68.8 | 60.2 | v5 false везде |

- Reversible vs irreversible: в baseline reversible slope 0.0021 < eps,
  irreversible slope 0.0027–0.0054 (на грани/выше eps 0.004);
  dominant wall — `irreversible_accumulation`; conversion rate 0.06–0.07
  выше порога 0.05.
- Prevention замедляет, но не останавливает irreversible accrual;
  clearance снижает reversible burden, но conversion продолжает кормить
  irreversible; repair alone упирается в неиспользуемый потолок —
  политика без rev-нагрузки потолок вообще не трогает.
- Aggressive reversal не бесплатен: +information/mutation долги,
  toxicity, цена repair; lifespan не выше combined.
- Repair ceiling sweep (0.1/0.3/0.6): плоский 69.5 — потолок не binding,
  потому что политика его не исчерпывает; v5 false везде.
- Conversion sweep (0.005/0.02/0.05): 69.5/69.5/60.5 — elevated
  conversion роняет lifespan на ~9 лет: conversion — главный механизм
  irreversible accumulation.
- Info/mutation sweep 9×3: плоский 69.0 — лимиты не binding при текущих
  политиках; v5 false везде.
- Coordination 4×3: все 69.5, gain 0.0 — non-interference подтверждён и
  при scarce ceiling.
- Stress 3×5×3: ranking стабилен (combined 65.7 > aggressive 64.4 >
  baseline 64.1); robust false везде.
- HYP-0: `hypothesis_not_proven`;
  `candidate_robust_bounded_degradation_v5_found = false`.

## 11. Ограничения

Абстрактный organ-network организм; reduced proxies/рёбра; порядковые
параметры; операциональные пороги; n ≤ 3 (описательно); нет
биологической валидации. Отсутствие v5 — валидный внутримодельный
результат: irreversible accumulation / conversion выглядит
фундаментальным wall текущей архитектуры. HYP-0 остаётся
`hypothesis_not_proven`.

## 12. Stage 6D — Irreversibility boundary probe (кратко)

Диагностический, не биологический этап: поверх 6C добавлен opt-in
`boundary_probe_model = none | irreversibility_ablation`
(`none` и нейтральные scales 1.0/flags false — численно идентичны
Stage 6C). Аблации: `conversion_scale`,
`independent_accrual_scale`, `repair_ceiling_scale`, component
overrides, флаги disable/unlimited (unlimited — non-physiological
exploratory, помечается в metadata). Метрики: contribution
decomposition (`conversion_flux + independent_accrual − repair_offset =
net slope` по компонентам), dominant source attribution, wall
classification (parametric vs structural — только внутримодельная).

Главный результат (в рамках модели):

- conversion_scale=0: irreversible slope 0.00536 → 0.00082 (в допуске),
  но v5 всё равно false — binding смещается на `biological_age_slope`;
- independent sweep почти не двигает slope (0.00501–0.00570) —
  conversion доминирует;
- ceiling sweep (0.0–3.0) плоский — потолок не binding;
- attribution: default → source `conversion`, component
  `driver:stem_exhaustion`; conversion_zero → source
  `independent_irreversible_accrual`, component `driver:dna_damage`;
  both_suppressed → source `information_debt`;
- все 9+9+7 точек ultra-свипов, attribution (6 аблаций × 3 seeds),
  search и stress: v5 false везде;
- wall classification: `parametric_irreversibility_wall` —
  irreversible-компонент параметрически подавим, но v5 как целое
  остаётся недостижимой: подавление irreversible-источников открывает
  другую binding wall (`biological_age_slope`).

Вывод — исход 2: `Suppressing irreversible generation reveals another
binding wall`. HYP-0 остаётся `hypothesis_not_proven`;
`candidate_robust_bounded_degradation_v5_found = false` в default,
аблациях и стрессе.

## 13. Stage 6E — Compound wall attribution and knife-edge probe (кратко)

Диагностический extension поверх Stage 6D: отвечает, является ли
барьер после 6D узким параметрическим knife-edge, множественной
остаточной стеной или нестабильным выводом. Новая биология не
добавляется.

Что добавлено (всё additive, `boundary_probe_model=none` по-прежнему
эквивалентен 6C):

- Knife-edge probe: single-конфиг (`conversion_scale=1e-4`,
  `independent_accrual_scale=0.0`) и sweep
  `0.0, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.1, 1.0` при independent=0 —
  переиспользует generic `conversion_ultra_sweep` раннера.
- `decompose_biological_age_slope` (`boundary_metrics.py`): раскладка
  mechanistic `biological_age_slope` по 8 драйверам весами
  `contribution_i / adult_reference_i` и по 6 семейств-источников
  (genomic, epigenetic, proteostasis_metabolic, inflammatory_senescent,
  stem, oncogenic) + residual (floor/clamp/прямые delta bio-age).
  Linear diagnostic proxy, не conservation law; вход не мутируется.
- `classify_compound_wall` (pure): 7 labels — `no_wall`,
  `single_channel_parametric_wall`, `knife_edge_parametric_wall`,
  `compound_residual_wall`,
  `structural_under_current_abstraction_wall`, `ceiling_mediated_wall`,
  `inconclusive_sensitivity_failure`. Неполные данные или нестабильность
  по seed/eps/dt → всегда `inconclusive_sensitivity_failure`, угадывания нет.
- Sensitivity-kind в `organism_boundary.py`: траектории прогоняются один
  раз на (dt × аблация × seed), вердикт v5 переоценивается на каждый eps
  без реранов. Вердикты, stability-флаги и compound-классификация пишутся
  в `*_sensitivity.json`.
- Фитнес поиска не менялся: поиск идёт по nominal (non-exploratory)
  базам; v5 в аблациях оценивается отдельно и маркируется.

Главный результат (в рамках модели, seeds 42/7/99):

- Knife-edge sweep 8×3: v5=false во всех 8 точках, включая 1e-6 —
  knife-edge нет, порога нет. Binding везде `biological_age_slope`;
  source смещается `conversion` (≥0.01) → `information_debt` (≤0.001).
- Bio-age attribution стабильна по аблациям: total slope ≈ 1.33,
  dominant `proteostasis_loss` → `proteostasis_metabolic` (0.69),
  далее `stem_exhaustion` (0.23), `inflammatory_senescent` (0.18);
  residual −0.014 (прокси объясняет ~99%); значимых источников (доля
  ≥ 0.1) — 3.
- Sensitivity (eps 0.002/0.004/0.008 × dt 0.5/0.25/0.1 × 4 аблации × 5
  seeds, 60 прогонов + переоценка): eps_stable, dt_stable, seed_stable —
  все true; v5=false в all 36 ячейках, включая самый мягкий eps.
- Compound wall в sensitivity и compound-attribution: обе независимо дают
  `compound_residual_wall` — irreversible slope подавлен, v5 false,
  binding `biological_age_slope`, ≥2 остаточных источников.
- HYP-0 остаётся `hypothesis_not_proven`. Это diagnostic classification
  внутри abstract organ-network reversibility boundary-probe модели, а не
  биологический закон и не доказательство (не)возможности бессмертия.

## 14. Stage 6F — Heterogeneous residual driver probe (кратко)

Диагностический extension поверх Stage 6E: проверяет структуру
составной остаточной стены — является ли она диффузной,
локализованной, смешанной или неоднозначной в текущей абстрактной
модели. Новая биология не добавляется, базовая динамика 6C/6D/6E не
меняется, `boundary_probe_model=none` по-прежнему эквивалентен 6C.

Инвентаризация показала: существующие per-component overrides
покрывают только reversibility-ledger (conversion/independent
на драйвер/орган); `weight_override` и `repair_ceiling_override`
валидируются, но не заведены в модель; per-source overrides
отсутствуют. Поэтому точечное ослабление bio-age драйверов
реализовано без изменения модели — через существующий конфиг-слой
`aging_drivers` (`base_aging_rate` × driver_scale) плюс matching
driver-type `component_overrides`. `driver_scale=1.0` не добавляет
записей и воспроизводит baseline бит-в-бит (покрыто тестом).

Что добавлено (всё additive):

- `heterogeneous_probe`-kind в `organism_boundary.py`:
  `HeterogeneousProbeConfig` (drivers с именами и шкалами, combos,
  `combination_scales`, seeds; имена валидируются против 8 драйверов +
  6 source-групп + алиасы, неизвестные и пересекающиеся targets
  отклоняются), детерминированная таблица режимов (control → singles
  1.0/0.5/0.25/0.0 → combos), `_run_hetero_one`, writer
  (`*_summary.json`, `*_regimes.csv`,
  `*_residual_classification.json`).
- `classify_residual_wall` (pure): 4 labels —
  `diffuse_residual_wall`, `localized_residual_wall`,
  `mixed_residual_wall`, `inconclusive_residual_probe`. Неполные данные
  или нестабильность по seed → всегда `inconclusive`, угадывания нет.
  Robust v5 в не-exploratory режиме даёт `localized` с пометкой
  «требуется Stage 6G audit», HYP-0 при этом остаётся
  `hypothesis_not_proven`.
- Русские человекочитаемые статусы (`*_ru`): английские enum,
  JSON-ключи и имена файлов не переименованы; переводы —
  `wall_classification_ru`, `binding_constraint_ru`,
  `bio_age_source_ru`, `confidence_ru`, `hypothesis_ru`,
  `v5_operational_success_ru`, `exploratory_ru`,
  `sensitivity_stable_ru`.
- Порог substantial-эффекта: снижение bio slope ≥ 20% против control
  или смена binding (диагностический порог, не биологическая
  константа).

Главный результат (в рамках модели, seeds 42/7/99):

- Probe (15 режимов): v5=false везде; binding везде
  `biological_age_slope` (наклон биологического возраста); dominant
  источник везде `proteostasis_metabolic`; source flip нет;
  максимальное снижение bio slope ≤0.6%.
- Sweep (все 6 групп + joint ablation, 14 режимов): v5=false везде;
  joint suppression всех групп снижает bio slope лишь на 17%
  (1.33 → 1.10) — ниже порога 20%; поодиночке ≤8.5%.
- Residual wall в обоих независимо: `diffuse_residual_wall`
  (диффузная остаточная стена), уверенность средняя. В текущей
  абстрактной модели остаточная стена сохраняется при целевом
  гетерогенном подавлении: ослабление частично нивелируется
  repair/coupling динамикой текущей абстракции — операционный
  диагностический эффект, не биологическое утверждение; стена
  распределена по нескольким каналам.
- Binding constraint, source attribution, wall classification и Stage 6F
  residual classification разделены: per-regime wall —
  `parametric_irreversibility_wall` (6D-классификатор поверх вердикта
  режима), итог зонда — `diffuse_residual_wall`.
- Явные вердикты зонда: локализованный removable driver не найден
  (`stem_exhaustion` значим, но не единственно съёмен для v5);
  смешанный residual transition не найден (flip binding/source
  отсутствует); эффект ножевого края отсутствует (результат 6E,
  область 6F его подтверждает: порогового поведения нет и при
  гетерогенном подавлении).
- HYP-0 остаётся `hypothesis_not_proven`. Это computational
  exploration внутри abstract organ-network reversibility
  boundary-probe модели, не биологическая валидация.

Ограничения: stability покрывает seeds (eps/dt/horizon — сеткой 6E);
attribution shares — диагностические прокси, не законы сохранения;
unlimited ceiling остаётся exploratory; вывод действует только внутри
текущей абстракции и проверенной сетки чувствительности.
