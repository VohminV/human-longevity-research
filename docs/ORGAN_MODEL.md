# ORGAN_MODEL.md — Минимальная модель абстрактного органа (Stage 4A)

> Это НЕ модель организма и НЕ модель конкретного человеческого органа.
> Локальная устойчивость тканевых политик НЕ равна устойчивости органа
> (см. `docs/LONGEVITY.md`). Бессмертие остаётся предельной
> исследовательской гипотезой (`docs/IMMORTALITY.md`), а не выводом этапа.

## 1. Что такое OrganModel

`src/longevity/model/organ.py`, класс `OrganModel` — композиция тканевых
модулей, каждый из которых шагается существующим `TissueModel` Stage 3A
(динамика НЕ дублируется), плюс два общих ограниченных ресурса:

| Сущность | Смысл |
|---|---|
| `tissues` | 1–8 модулей `TissueModuleConfig` (`tissue_id / role / weight / is_vital / required_function / initial_state / tissue_parameters / policy / demand_coefficients`) |
| `shared_vascular_capacity` | общий перфузионный ресурс (абстрактные единицы/шаг) |
| `shared_immune_capacity` | общий ресурс иммунного надзора (те же единицы) |
| `organ_function` | агрегат нормализованных тканевых функций |
| `bottleneck_tissue` | худшая ткань (`argmin`, ties — по `sorted tissue_id`) |
| `organ_cancer_risk / organ_fibrosis_index` | максимумы по тканям (bottleneck-чувствительно, операционально) |

Роли: `parenchyma` (функциональная, вес 2), `stroma` (поддержка/ECM, вес 1,
медленный turnover, высокая чувствительность фиброза),
`vascular_interface` (опциональная третья). Веса, размеры пулов и скорости —
модельные допущения O-1…O-7 ниже, не измерения.

Один шаг органа: чистые планы замены каждой ткани → спрос на ресурсы →
коэффициенты распределения → контексты шага → `TissueModel.step(policy,
context)` → снепшот (функция, bottleneck, риски, спрос, viability).

## 2. TissueStepContext (единственное изменение TissueModel)

`TissueStepContext(effective_vascular_support, effective_immune_support,
systemic_damage_modifier)` — опциональный параметр `step/run`.
`context=None` воспроизводит Stage 3A численно идентично (регрессионный
тест). Эффекты: vascular масштабирует niche-gated регенерацию,
immune — эффективность клиренса сенесцентных, modifier — поток damage.
Checkpoint-формат ткани не менялся (контекст транзиентен).

## 3. Допущения Stage 4A (O-1…O-7)

| # | Допущение |
|---|---|
| O-1 | Спрос ткани линеен по пулам: vascular — functional/damaged/senescent + активность замены; immune — damaged/senescent/cancer/fibrosis + замена |
| O-2 | Распределение пропорциональное: `ratio = min(1, capacity / total_demand)`; ноль спроса не делит на ноль |
| O-3 | Shortfall бьёт по регенерации (vascular), клиренсу (immune) и добавляет системный damage `(1 − min_ratio) × systemic_damage_gain` |
| O-4 | Координация `resource_aware_scaling` — тот же ratio как общий множитель интенсивности замены; политики при этом не мутируют (чистая функция) |
| O-5 | Функция ткани = `functional / initial_functional`; агрегат по умолчанию `weighted_sum` (есть `min_normalized`, `weighted_geometric`) |
| O-6 | Органные рак/фиброз = максимумы по тканям |
| O-7 | Все скорости/ёмкости/пороги — порядковые заглушки; шаг абстрактный |

## 4. Эксперименты

Раннер `src/longevity/experiment/organ_runner.py`
(`load_organ_config`, `run_organ_experiment`, CLI `--config/--out`);
результат — JSON `organ_id / model_scope=abstract_organ_composition /
config / trajectory / metrics / summary / runtime / rng_summary`
(RNG на ткань — `seed + index`, глобальный random не трогается).
Мини-свип `src/longevity/experiment/organ_sweep.py` крутит
`global_replacement_scale × vascular × immune × coordination` по сидам.

Конфиги (`experiments/configs/`): `organ_baseline`,
`organ_independent_replacement` (тканевые политики из sustainable-области
Stage 3C: parenchyma q5/f0.1, stroma q10/f0.05, strong controls),
`organ_resource_aware_replacement` (те же + координация),
`organ_heterogeneous_strong_parenchyma_weak_stroma`,
`organ_heterogeneous_weak_parenchyma_strong_stroma`,
`organ_mini_sweep` (3×2×2×2×2 сида = 48 прогонов).

## 5. Viability и причинность

Орган viable, если: `organ_function ≥ 0.75`; каждая vital-ткань `≥ 0.6`;
allocation ratios `≥ 0.6`; органные рак `≤ 0.15`, фиброз `≤ 0.3`.
Пороги операциональные, не биологические. Метрики:
`time_to_organ_viability_failure`, `organ_healthspan_proxy` (суммарное
viable-время), `primary_organ_failure_cause` (`none / parenchyma_failure /
stroma_failure / vascular_interface_failure / organ_function_failure /
vascular_capacity_failure / immune_capacity_failure / organ_cancer_risk /
organ_fibrosis / multiple_simultaneous`), `organ_failure_cause_sequence`
(порядок первых нарушений, детерминирован). Сравнения:
`organ_rejuvenation_delta_vs_baseline`, `coordination_benefit_*`,
`resource_contention_index = 1 − mean(min(ratios))`.

## 6. Результаты v0 (внутри модели, seed 42, 200 шагов)

| Прогон | final function | ttf | healthspan | причина | bottleneck |
|---|---|---|---|---|---|
| baseline | 1.011 | 78 | 77 | immune_capacity_failure | parenchyma |
| independent | 1.090 | 101 | 112 | immune_capacity_failure | parenchyma |
| resource-aware | 1.070 | 86 | 95 | immune_capacity_failure | parenchyma |
| hetero strongP/weakS | 1.086 | 101 | 110 | immune_capacity_failure | parenchyma |
| hetero weakP/strongS | 1.081 | 91 | 98 | immune_capacity_failure | parenchyma |

Чтение строго внутримодельное:

1. **Орган деградирует иначе, чем ткани.** Функция органа ~1.0 во всех
   руках (пулы целы), а viability теряется по общему иммунному ресурсу:
   спрос растёт 3 → 13 за счёт сенесцентной нагрузки обеих тканей,
   allocation падает 1.0 → 0.38. Ткани «выглядят здоровыми», орган —
   нет: bottleneck ресурсный, не функциональный.
2. **Независимая замена помогает.** ttf 78 → 101, healthspan 77 → 112:
   sustainable-политики Stage 3C давят сенесценцию и тем самым иммунный
   спрос — локальная замена разгружает общий ресурс.
3. **Наивная координация вредит.** `coordination_benefit` отрицателен
   (healthspan −17, ttf −15): пропорциональное урезание замены экономит
   replacement-спрос, но оставляет больше сенесцентных — а спрос
   определяется именно ими. В модели координация «меньше заменять при
   дефиците» — неверная эвристика, когда дефицит создаёт проблема, а не
   лечение. Это наблюдение о конкретной эвристике, не о координации
   вообще.
4. **Слабость распространяется неравномерно.** Weak stroma ≈ all-strong
   (ttf 101, локальная цена ECM 0.894 → 0.866); weak parenchyma тянет
   орган вниз (ttf 91, собственный ECM 0.834 → 0.571, рак 0.098 → 0.148).
   Высоковесная, высокооборотная ткань со слабым контролем — самая
   хрупкая комбинация органа.
5. **Мини-свип: иммунная ёмкость доминирует.** При immune=3 ttf ~15 при
   любых vascular/интенсивности; при immune=5 ttf 79–119 и растёт с
   интенсивностью замены; vascular 8 vs 12 почти не влияет; bottleneck —
   всегда parenchyma; причина — всегда `immune_capacity_failure`;
   coordination benefit ≤ 0 везде. Орган в этой сетке — «иммунно-лимитированная
   система с parenchyma-bottleneck».

## 7. Что это НЕ доказывает (ограничения)

- Ничего про человеческие органы: нет анатомии, калибровки, валидации.
- Порядковые скорости; абстрактный шаг; операциональные пороги.
- 1–2 сида в свипе — описательно, не значимость.
- `unstable`-аналог на органном уровне не строился; `vital_tissue_priority`
  как отдельный режим не реализован (расширение, а не пропуск анализа).
- HYP-0 не затрагивается: горизонт конечен, t→∞ не исследуется.

## 8. Stage 4B — Demand-aware координация и immune sensitivity

> Проверка тезиса: координация полезна не когда «меньше замены вообще»,
> а когда приоритет отдаётся заменам, снижающим будущий системный спрос.
> Score — операциональная модельная эвристика, не биологическая польза
> и не доказательство rejuvenation.

### 8.1. Почему 4A мотивирует 4B

Отрицательный benefit наивного `resource_aware_scaling` — наблюдение об
одной эвристике (слепое пропорциональное урезание режет и «разгружающие»
действия), а не опровержение координации как таковой.

### 8.2. Режимы (`longevity.model.organ_policy`)

Старые сохранены побайтово (`independent_tissue_policies`,
`resource_aware_scaling`; алиасы `independent` / `proportional_scale`
нормализуются к каноническим именам). Новые (чистые, политики не мутируют):

- `demand_relief_priority` — greedy water-filling по score: планы в порядке
  убывания score исполняются, пока хватает predicted capacity; первый
  непоместившийся — частично (масштабированная доля — архитектура это
  поддерживает), остальные отклоняются; relief floor — top-1 план, если не
  поместилось ничего;
- `senescent_burden_priority` — тот же water-filling, но score только по
  очищенным клеткам (relief-only);
- `immune_reserve_guard` — пока predicted immune allocation ≥ порога
  (default 0.6), исполняется всё; ниже — только планы со score ≥ cutoff
  (default 0.0), иначе top-1;
- `hybrid_demand_guard` — cutoff-фильтр, затем water-filling survivors.

Допущения O-8…O-9: score =
`(α·senescence_relief + β·damage_relief − γ·cancer − δ·fibrosis − ε·arch) /
(plan_immune_cost + w_vascular·plan_vascular_cost + eps)`;
relief капится пулом; ties — по tissue_id; веса конфигурируемы
(`coordination_params`, дефолты не меняют старые режимы).

### 8.3. Результаты (внутри модели)

Compare-свип (3 intensity × imm {3,5,8} × 6 modes × 2 seeds): ни один режим
не превзошёл independent ни в одной точке (лучшие gains — 0.0).
Упорядочение: `independent == guard ≥ demand == senescent == hybrid >
proportional`. При scale=1/imm=5: proportional −14.5, demand −5.5,
guard 0.0 (healthspan gains). Селективное урезание вдвое снижает вред
слепого, но не бьёт «ничего не резать»: в этом органе замена и есть
механизм разгрузки будущего спроса. Guard вырождается в independent,
потому что relief-положительных планов почти всегда большинство.

Immune sensitivity (imm {3…12} × intensity {0.5,1.0} × 4 modes × 3 seeds):
imm ≤ 5 — 100% `immune_capacity_failure`; imm = 6 — переход (выживают все,
кроме proportional/scale=0.5 — урезание бьёт ровно на границе);
imm ≥ 8 — полная устойчивость (`none`) по всей сетке. Тканевых причин
отказа нет нигде: `no_tissue_cause_in_current_grid` для всех режимов.
Орган в сетке — иммунно-лимитированная система с жёстким порогом
устойчивости между immune capacity 6 и 8.

Hetero + demand_relief: weakP/strongS ttf 91 → 81 (умная координация
вредит хрупкой комбинации сильнее, чем independent); strongP/weakS
101 → 96. Вывод: координация-урезание опаснее всего там, где замена
нужнее всего.

Механистическое пояснение отрицательного результата: score близорук
(один шаг) — будущий relief не моделируется, поэтому любое урезание
режет и разгрузку будущего спроса. Это ограничение эвристики,
зафиксированное честно, а не провал метода измерения.

### 8.4. Интерпретационные правила

- Положительный benefit = улучшение внутри модели; отрицательный = данная
  политика хуже альтернативы; отсутствие benefit ≠ невозможность
  координации вообще.
- Все метрики (execution_fraction, relief/executed, shortfall AUC,
  burden AUC) — локальные прокси абстрактного органа.
- Ограничения: те же, что §7, плюс близорукий score и n ≤ 3.

## 9. Stage 4C — Delayed relief и non-destructive координация

> Проверка тезиса: координация полезна не когда «меньше замены вообще»,
> а когда она планирует замену во времени при немедленной цене и
> отложенной пользе. Временная модель — операциональная абстракция,
> не биологическая калибровка.

### 9.1. Временная модель (O-10…O-12)

`temporal_relief_model = none` (default) — побайтово поведение Stage 4B.
`delayed_relief` добавляет, не трогая динамику тканей:

- immediate spike: исполненная замена добавляет
  `accepted × mult × per_replacement` к спросу текущего шага;
- delayed relief: то же исполнение создаёт событие demand-кредита
  (`relief_magnitude_scale`, сплит composite 50/50), активное на окне
  `[created + delay, created + delay + duration)`;
- relief_target v0: только `immune_demand / vascular_demand / composite`
  (`senescence/damage` отклоняются — им нужна pool-динамика).

### 9.2. Non-destructive режимы (O-13…O-15)

- `lookahead_priority` — water-filling по lookahead-score
  (`discounted_future_relief − риски) / (immediate + eps)`;
- `deferral_scheduler` — rank по demand-score; исполняемое — пока predicted
  immune allocation ≥ порога, остальное откладывается на `defer_steps`
  (re-дефер при пустом пуле, expiry по `deferred_plan_max_age`);
- `hybrid_lookahead_deferral` — lookahead-rank + deferral остатка.
Отложенные планы мержатся со свежими, ревалидируются по пулу
(`min(сумма, pool)`), исполняются через точную fractional-политику;
физические caps Stage 3A соблюдаются исполнением. Checkpoint покрывает
события и очередь (старые checkpoint'ы ресторятся с пустым состоянием).

### 9.3. Результаты (внутри модели)

Temporal-механика работает: spike/relief-события с точным delay,
realization ratio ~0.96, очередь отсрочки исполняется (42 ячейки сетки с
`executed_after_deferral > 0`, mean defer ровно 5.0).

Но benefit нет нигде: в sensitivity-сетке (delays 0–20 × costs 0–2 ×
imm 4–8 × intensity × 3 modes × 3 seeds, 1728 прогонов) lookahead/deferral
ни разу не превзошли independent (max gain ровно 0.0; pooled hs 143.4 vs
140.9 vs 139.3). Transition по delay отсутствует — лучший режим везде
independent, тканевых причин нет нигде.

Иерархия при этом есть: scheduling бьёт слепое урезание там, где оно
бьёт больнее всего (imm=5/scale=1: lookahead +23.5 hs и deferral +13.5 hs
vs proportional; independent +15.0 vs demand). Independent сам
чувствителен к temporal-параметрам (hs 148–161 при росте cost/delay) —
временна́я асимметрия в модели реальна, но планировщик её не конвертирует
в выигрыш: отложенная замена оставляет сенесценцию, которая и есть
источник спроса.

Hetero + deferral (честный temporal-baseline): weakP 116 → 111,
strongP 131 → 126 (−5 обеим). Урезание/отсрочка вредят и хрупкой
комбинации тоже.

### 9.4. Вывод: non-interference

```text
For locally sustainable replacement policies with immediate net demand
relief, optimal organ-level coordination is non-interference.
```

Любое подавление/отсрочка замены в этой архитектуре режет и разгрузку
будущего спроса. Это валидный отрицательный результат: он сужает
пространство гипотез до архитектур, где разгрузка НЕ следует немедленно
из самого акта замены (например, отдельный recovery-процесс ниши).

Ограничения: те же, что §§7–8, плюс некалиброванные temporal-параметры
и relief только demand-слоя (не pool-слоя).

## 10. Stage 4D — Decoupled niche recovery и supply-demand координация

> Проверка гипотезы: если разгрузка спроса отделена от восстановления
> ресурсной ёмкости (два класса вмешательств с разными временны́ми
> профилями), становится ли координация нетривиально полезной?
> Recovery — операциональная абстракция (цена + задержка + эффект),
> не биологическая калибровка и не «магическое rejuvenation».

### 10.1. Модель (O-16…O-22)

`recovery_model = none` (default) — побайтово поведение Stage 4C.
`decoupled_niche_recovery` добавляет:

- `RecoveryPolicy` на ткань (`target`: `vascular_capacity` /
  `immune_capacity` / `ecm_quality`; частота, магнитуда, delay,
  immediate-мультипликаторы) и чистый `RecoveryPlan`;
- динамические capacities: деградация от спроса и сенесцентной нагрузки,
  восстановление через delayed capacity-события (merge дубликатов,
  ceiling 2× initial, floor 0), ECM-реставрация в ткань обладателя;
- joint score: replacement ценится за relief, recovery — за
  `supply_beta × magnitude`, делённые на немедленную цену;
- deferral-очередь обоих типов (replacement — по пулу, recovery — по
  headroom; stale не исполняется слепо; expiry по возрасту).

Новые режимы (чистые, политики не мутируют): `independent_all`
(исполнять всё), `supply_demand_greedy` (water-fill + floor, остаток —
reject), `lookahead_supply_demand` (discounted future rank + water-fill),
`deferral_supply_demand` (rank + defer остатка). Старые 9 режимов
сохранены; legacy-режимы координируют только replacement, recovery при
них исполняется независимо.

Новые причины отказа: `capacity_exhaustion` (просадка dynamic supply),
`ecm_collapse`, `recovery_debt`, `chronic_inflammatory_overload` —
пороги по умолчанию не срабатывают на legacy-прогонах (проверено
побайтовым воспроизведением всех хранимых выводов 4A–4C).

### 10.2. Результаты (внутри модели)

Recovery-only baseline (замена выключена, recovery включён): орган
устойчив (ttf 200, `none`) — supply restoration само по себе держит
систему в этой параметризации, хотя сенесценция не удаляется.

Compare (mag 1.0, imm 5/8): все режимы ttf 200 — насыщение, дифференциации
нет. Sensitivity (2 intensity × imm 4–8 × rec-delay {0,10} × cost {0,1} ×
mag {0.5,1.0} × 4 modes × 3 seeds, 768 прогонов):

- gains vs `independent_all` по healthspan: max ровно 0.0 (192 строки) —
  координация снова не бьёт non-interference;
- pooled: independent hs 194.3 ≈ greedy 193.2 ≈ deferral 173? нет:
  independent 194.3, greedy 193.2, lookahead 191.9, deferral 193.2 —
  все в пределах ~1%;
- новая причина отказа: `vascular_capacity_failure` (4 прогона,
  greedy/deferral при imm=4/scale=1/rdelay=10/mag=0.5/cost=1.0) —
  урезание/отсрочка vascular recovery создаёт дефицит, которого у
  independent нет. `ecm_collapse`, `recovery_debt`, `chronic_overload` —
  `no_tissue_cause`-аналог: не посещены в сетке;
- capacity transition: imm=4 — 56 immune + 4 vascular failures при 132
  sustained; imm ≥ 5 — 100% sustained. Recovery сдвигает порог
  устойчивости вниз по сравнению с 4B (там imm=5 падало);
- hetero + recovery: обе комбинации ttf 200 — decoupled recovery
  стирает weak-parenchyma хрупкость Stage 4A (там было 91 vs 101).

Отдельная калибровочная находка: при recovery magnitude 2.0 +
mult 1.0 independent падает на ttf 10 (синхронные spike), а
координированные режимы выживают (ttf 200) — единственный найденный
регион, где фазирование спасает. Но это region «перегруженных
интервенций», а не устойчивых политик: вывод — координация страхует от
синхронных всплесков цены, но не улучшает устойчивые режимы.

### 10.3. Вывод

```text
Even with decoupled supply recovery, top-down scheduling does not beat
non-interference in the current abstract organ architecture; recovery
itself (executed independently) is what sustains the organ, and pruning
or deferring it can create the capacity failures it prevents.
```

Ограничения: те же, что §§7–9, плюс некалиброванные recovery-параметры,
single recovery policy на ткань, ECM-реставрация без pool-динамики,
n ≤ 3.

## 11. Связь со Stage 6A

Идеи и уроки Stage 4A–4D (shared capacities, demand/allocation,
recovery как отдельный pipeline, вред naive pruning) использованы как
inspiration для reduced organ proxies Stage 6A — см.
`docs/ORGAN_BACKED_ORGANISM_MODEL.md`. Это параметризация идеями, а не
перенос кода: прокси — упрощённые состояния, а не экземпляры
`OrganModel`. Закон ветки подтверждён уровнем выше: organism-level
coordination не бьёт independent execution (scaling −0.25).
