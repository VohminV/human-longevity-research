# ROADMAP.md — Этапы развития проекта

Цели и порядок работ. Этапы следуют принципу
**наука → модель → симулятор → эксперименты → проверка гипотез**.

## Этап 1 — Научная и архитектурная основа (готов ✅)

Выход: зафиксированные научные точки, допущения, архитектура и каталог источников.
Коммит: `07651e6 docs: establish research foundation (stage 1)`.

## Этап 2 — Минимальная модель клетки (reference) (готов ✅)

- [x] модели: `Cell`, клеточный цикл, деление, смерть, lineage
- [x] детерминированность по seed; уникальные id; parent/generation/lineage
- [x] инварианты и тесты (детерминизм, уникальность id, parent-child, поколение,
      lineage, деление, смерть, сенесценция)
- [x] теломерная динамика (базовая) и DNA damage (базовое) как отдельные опции
      >=0 параметров (по умолчанию выключены); mortality — отдельная опция
- [x] checkpoint/restore (RNG сериализуется, restore после JSON-roundtrip
      идентичен непрерывному запуску)
- [x] `Experiment`-конфигурация и запись результатов (JSON)

Модули: `longevity.biology` (cell, params), `longevity.sim` (rng, engine),
`longevity.experiment` (config, runner), `longevity.analysis` (metrics).

## Этап 3 — Динамика раннего развития (калибровка, готов ✅)

- [x] асинхронные циклы деления (~10–12 ч/цикл), гибель, milestones для точных
      времён достижения стадий
- [x] калибровка против S-6/S-7 (Istanbul/Hardy): времена стадий + число клеток
      бластоцисты д.5–7; результат — **MODEL MISMATCH** (см. `docs/CALIBRATION.md`)
- [ ] TE/ICM-распределение (Hardy 1989) — отложено: в модели нет клеточных судеб
      и пространства (Этап 6)
- [ ] сравнение с наблюдённым profile распределения числа клеток на д.3 —
      отложено: вне текущего набора референсных данных (Этап 6)

Новое в кодовой базе: `longevity.calibration` (reference, stages, compare,
multirun, sensitivity), milestones в engine, драйвер `experiments/run_calibration.py`.

## Этап 3.5 — Клеточный цикл и динамика раннего развития (готов ✅)

- [x] опциональная группа `cell_cycle.phases` (стадия-зависимые mean/sd и
      death_per_division; пороги по числу живых клеток; opt-in, обратно совместима)
- [x] верификация Этапа 3: модель A = поведение v0.1.0 (v1 воспроизводима)
- [x] проверка H1/H2: частичное закрытие MODEL MISMATCH — времена 2/4 клеток
      воспроизведены, 8-клеточная с остатком −9%; численности д.5–7 требуют
      дополнительного позднего тормоза (модель C: д.7 в окне)
- [x] референс-реестр `cell_cycle.phases.*` (obs/inf/assumption), источники S-19/S-20
- [x] свипы по 5 ручкам фаз; отчёт-этап `docs/DEVELOPMENTAL_DYNAMICS.md`
- [ ] [Этап 6] фаза «мижду 2 и 8» (mean ≈ 24 ч) как отдельная фаза; вторичное
      удлинение 45–47 ч/деление после морулы; судьбы TE/ICM и кавитация

Новое: `cell_cycle` в `params.py`/engine/`config.py`, quantile-отчёты
(median/p05/p95) в `calibration`, драйвер `experiments/run_stage4.py`,
конфиги `experiments/configs/stage4_*.json`, тесты
`tests/test_developmental_dynamics.py`. Версия модели → 0.2.0.

## Этап 3A — Модель ткани с политикой замены (готов ✅)

- [x] компартментная модель одной абстрактной ткани (`TissueState`: stem /
      functional / damaged / senescent / dead + ecm / vascular / immune /
      cancer_risk / fibrosis) — `longevity.model.tissue`, версия модели `0.3.0`
- [x] `ReplacementPolicy` (планирование, чистое) + `ReplacementPlan` отдельно
      от исполнения (`TissueModel`) — `longevity.model.policy`
- [x] детерминизм по seed (инжектируемый `Rng`, без глобального random);
      checkpoint/restore с сериализацией RNG, restore после JSON-roundtrip
      идентичен непрерывному запуску
- [x] инварианты (пулы >= 0, качества/риски в [0, 1], кап замены, нет NaN/inf,
      JSON-roundtrip) + тесты (`tests/test_tissue_model.py`,
      `tests/test_replacement_policy.py`)
- [x] три конфига (`tissue_baseline / tissue_senescent_replacement /
      tissue_aggressive_replacement`), раннер `longevity.experiment.tissue_runner`,
      метрики (`longevity.analysis.tissue_metrics`), doc `docs/TISSUE_MODEL.md`
- [x] наблюдение (в рамках модели): умеренная замена устойчива; агрессивная
      истощает стволовой пул и платит раком/фиброзом/иммунитетом/ECM

Новое: `longevity.model` (tissue, policy), `longevity.analysis.tissue_metrics`,
`longevity.experiment.tissue_runner`, конфиги `experiments/configs/tissue_*.json`.
`Cell` и `PopulationEngine` не тронуты. Локальное омоложение ткани ≠
rejuvenation организма; HYP-0 не затрагивается.

## Этап 3B — Карта устойчивости замены, sweep fraction × frequency (готов ✅)

- [x] `TissueSweepConfig` (валидация grid/seeds/thresholds/policy-template,
      ≥3 seed на точку, канонический `config_hash`) —
      `longevity.experiment.tissue_sweep` (+ CLI `python -m ...`)
- [x] прогон сетки 7 × 5 через существующий `run_tissue_experiment` (динамика
      Stage 3A не дублировалась и не менялась); baseline-рукав на каждый seed
      для `*_vs_baseline`-дельт при том же seed
- [x] operational viability-констрейнты, `time_to_first_viability_failure`,
      `healthspan_tissue`, `survival_time` — `longevity.analysis.tissue_sweep`
- [x] детерминированная классификация 6 режимов (baseline_like / sustainable /
      risky_but_functional / stem_depleting / collapsing /
      unstable_high_replacement), чистая функция, состояние не мутирует
- [x] агрегация по сидам (mean/std/min/max/median/p25/p75/count, rates, счётчики
      режимов), граница устойчивости по частоте, pareto-фронт польза/цены
- [x] артефакты: `tissue_sweep_v0_{long,summary}.csv`,
      `tissue_sweep_v0_{summary,boundary}.json` (guard от NaN/inf)
- [x] наблюдение v0 (в рамках модели): широкое плато sustainable + угол
      коллапса q=1/f≥0.1, который рвётся первым по `stem_depleted` при почти
      нулевой сенесцентной нагрузке; граница `{1: 0.05, 5/10/25/50: 0.2*}` —
      при q≥5 край открыт (нужны доли >0.2); risky/unstable в v0 не посещены
- [x] тесты (`tests/test_tissue_sweep.py`, 37 шт.): детерминизм summary+boundary,
      валидация, агрегация на синтетике, все 6 лейблов, boundary-края, схема и
      round-trip артефактов, нетронутость глобального random, fraction-0.0 ==
      baseline того же seed

Новое: `longevity.analysis.tissue_sweep`, `longevity.experiment.tissue_sweep`,
конфиг `experiments/configs/tissue_sweep_v0.json`, doc § Stage 3B в
`docs/TISSUE_MODEL.md`. n=3 — описательный разброс, не значимость; HYP-0 не
затрагивается.

## Этап 3C — Закрытие границы и контрольно-чувствительный свип (готов ✅)

- [x] расширенная сетка долей `[0.0 … 0.5]` (12 × 5 = 60 точек на профиль,
      края v0 `0.2` закрыты изнутри теми же seeds `[42, 7, 99]`, 200 шагов) —
      конфиги `experiments/configs/tissue_sweep_v1_boundary_closure.json`
      (strong + weak) и `tissue_sweep_v1_weak_controls.json` (weak standalone)
- [x] `control_profiles` в `TissueSweepConfig` (пресеты strong 0.9 / weak 0.4,
      валидация, обратно совместимо: v0-конфиг без блока ведёт себя как раньше)
- [x] причинность отказа из траектории (чистая функция, без изменения динамики):
      `first_*_time` × 8, `primary_failure_cause`, `failure_cause_sequence`
      (детерминированный порядок, `multiple_simultaneous`/`none`)
- [x] граница по парам частота×профиль (`max/first_unsustainable_fraction`,
      `boundary_open`), покрытие режимов, сводка причин, сравнение
      strong-vs-weak — артефакты `tissue_sweep_v1_{boundary_closure,
      regime_coverage,failure_causes,control_comparison}.{json,csv}`
- [x] наблюдение v1 (в рамках модели): граница strong `{1: 0.05, 5: 0.3,
      10/25/50: 0.5*}` vs weak `{1: 0.02, 5: 0.1, 10: 0.1, 25: 0.35, 50: 0.5*}`;
      weak посещает `risky_but_functional` (27 прогонов), strong — терминальный
      `stem_depleting` (q=5/f=0.35); первичный отказ сдвигается со
      `stem_depletion` (strong) на `ecm_failure` (weak); `unstable` не посещён;
      коллапс при низкой сенесценции и нулевом/добитом stem подтверждён
- [x] тесты (`tests/test_tissue_sweep_v1.py`, 26 шт.): совместимость v0,
      валидация профилей, поведение strong==legacy, closure-края, coverage,
      causality (порядок/simultaneous/none/немутация), comparison, схемы и
      сериализация артефактов, детерминизм без глобального random, малая
      end-to-end сетка

Новое: `control_profiles` + Stage 3C-анализ в `tissue_sweep` (анализ и
эксперимент), конфиги `tissue_sweep_v1_*.json`, doc § Stage 3C в
`docs/TISSUE_MODEL.md`. Локальный тканевый результат, не rejuvenation
организма; HYP-0 не затрагивается.

## Этап 4A — Минимальная композиция органа (готов ✅)

- [x] `OrganModel` из 2 тканевых модулей (parenchyma + stroma) поверх
      существующего `TissueModel` без дублирования динамики; единственный
      аддитивный хук — опциональный `TissueStepContext` (`None` численно
      идентичен Stage 3A, регрессионный тест)
- [x] общие `shared_vascular_capacity / shared_immune_capacity`, линейный
      demand, пропорциональный allocation, поддержка → контексты шага,
      агрегация функции (`weighted_sum/min_normalized/weighted_geometric`),
      bottleneck, органная viability и failure causality — `longevity.model`
      (organ, organ_policy), версия модели `0.4.0`
- [x] координация `independent_tissue_policies` vs `resource_aware_scaling`
      (чистая, политики не мутируют) + опциональный `global_replacement_cap`
- [x] конфиги `organ_baseline / organ_independent_replacement /
      organ_resource_aware_replacement /
      organ_heterogeneous_{strong_parenchyma_weak_stroma,
      weak_parenchyma_strong_stroma} / organ_mini_sweep`,
      раннер + CLI (`organ_runner --config/--out`), мини-свип
      (scale × vascular × immune × coordination, `organ_sweep --config/--out-prefix`)
- [x] наблюдение v0 (в рамках модели): орган fails по `immune_capacity_failure`
      при целой функции (~1.0) — bottleneck ресурсный; независимая замена
      продлевает ttf 78 → 101; наивное resource-aware урезание вредит
      (ttf 86, benefit −15) — дефицит создаёт сенесценция, а не замена;
      weak stroma ≈ all-strong (ttf 101), weak parenchyma тянет вниз
      (ttf 91, ECM 0.57, рак 0.148); мини-свип — иммунно-лимитированная
      система с parenchyma-bottleneck, vascular почти не влияет
- [x] тесты (`test_organ_model` 20 шт., `test_organ_runner` 7 шт.,
      `test_organ_metrics` 7 шт.): совместимость 3A/3B/3C, детерминизм,
      checkpoint/restore, валидация, allocation, агрегация, viability,
      causality, independent-vs-aware, hetero, mini-sweep, model_scope

Новое: `longevity.model` (organ, organ_policy), `longevity.analysis`
(organ_metrics), `longevity.experiment` (organ_runner, organ_sweep),
конфиги `experiments/configs/organ_*.json`, doc `docs/ORGAN_MODEL.md`.
Абстрактная органная композиция, не организм; HYP-0 не затрагивается.

## Этап 4B — Demand-aware координация и immune sensitivity (готов ✅)

- [x] score ценности плана (relief/cost, детерминирован, веса
      конфигурируемы) + 4 режима: `demand_relief_priority` (water-filling с
      relief floor), `senescent_burden_priority` (relief-only),
      `immune_reserve_guard` (cutoff + top-1), `hybrid_demand_guard`;
      старые режимы и алиасы (`independent`/`proportional_scale`)
      побайтово сохранены
- [x] `coordination_params` в `OrganConfig`, селективное исполнение в
      `OrganModel` (политики не мутируют), per-step `coordination_detail` +
      executed-demand в снепшотах; координационный блок метрик
      (execution/rejected fractions, scores, relief/executed, burden AUC)
- [x] свип расширен аддитивно: descriptive stats, `coordination_comparison`
      (gains vs independent/proportional), `immune_sensitivity`,
      `immune_transition`, `failure_cause_distribution`; новый writer
      (long/summary/comparison/failure/boundary), старый writer и CLI
      без изменений (+ флаг `--artifacts`)
- [x] конфиги `organ_coordination_compare` (6 modes),
      `organ_demand_relief_priority`, `organ_immune_reserve_guard`,
      `organ_immune_sensitivity_sweep` (imm 3…12 × 3 seeds),
      `organ_heterogeneous_demand_relief` (+ mirror)
- [x] наблюдение (в рамках модели): ни один режим не бьёт independent
      (guard == independent, demand −5.5 лучше proportional −14.5, но хуже
      independent); imm ≤ 5 — 100% immune failure, imm = 6 — переход,
      imm ≥ 8 — устойчивость; тканевых причин нет нигде
      (`no_tissue_cause_in_current_grid`); demand-урезание вредит хрупкой
      weakP-комбинации сильнее (ttf 91 → 81); score близорук (один шаг)
- [x] тесты (`tests/test_organ_coordination.py`, 18 шт.): совместимость,
      валидация, детерминизм/tie-break, score (чистота/ноль/монотонность),
      приоритет исполнения, guard (no-op/cutoff/top-1), метрики, sweep
      end-to-end, hetero-чистота, model_scope без bio-claims

Новое: режимы и score в `organ_policy`, селекция в `organ.py`,
координационные метрики, sensitivity-блоки свипа, конфиги `organ_*4B*.json`
и `organ_immune_sensitivity_sweep.json`, doc § Stage 4B в
`docs/ORGAN_MODEL.md`. Отрицательный результат зафиксирован честно;
HYP-0 не затрагивается.

## Этап 4C — Delayed relief и non-destructive координация (готов ✅)

- [x] opt-in `temporal_relief_model` (`none` побайтово = Stage 4B;
      `delayed_relief`: immediate spike + delayed demand-relief events с
      точным delay/duration, demand-слой only, checkpoint покрывает события
      и deferral-очередь)
- [x] режимы `lookahead_priority` (water-filling по discounted future
      relief), `deferral_scheduler` (rank + defer остатка, merge/due,
      revalidation по пулу, expiry), `hybrid_lookahead_deferral`;
      stale/due-баг (молчаливая потеря очереди) найден тестами и исправлен
      с регрессионным тестом
- [x] temporal-метрики (spike totals/peaks/min-allocation, relief
      created/realized/expired + realization ratio, deferral counts/delays,
      queue max) + sweep-блоки (temporal_sensitivity/transition,
      gains vs independent/proportional/demand, non_destructive_benefit) +
      writer (long/summary/comparison/failure/boundary + deferral_stats CSV)
- [x] конфиги `organ_delayed_relief_{independent,lookahead,deferral}`,
      `organ_delayed_relief_compare` (6 modes),
      `organ_temporal_sensitivity_sweep` (delays 0–20 × costs 0–2 × imm
      4–8 × intensity × 3 modes × 3 seeds = 1728 прогонов),
      `organ_heterogeneous_delayed_relief` (+ mirror + 2 temporal-baseline)
- [x] наблюдение (в рамках модели): механика работает (realization ~0.96,
      42 ячейки с executed-after-deferral), но benefit нет нигде
      (max gain ровно 0.0; pooled hs 143.4 vs 140.9 vs 139.3);
      scheduling бьёт слепое урезание (lookahead +23.5 vs proportional),
      но не independent; hetero-deferral −5 обеим комбинациям;
      вывод — `non-interference_is_optimal_in_current_model`
- [x] тесты (`tests/test_organ_temporal_coordination.py`, 21 шт.): 12 групп
      по брифу (совместимость, валидация, детерминизм, spike, relief-timing,
      deferral, lookahead, benefit-измеримость, sweep, hetero, checkpoint,
      scope)

Новое: temporal-блок `organ.py`/`organ_policy`, temporal-метрики, sweep-
расширение, конфиги `organ_delayed_relief_*.json` и
`organ_temporal_sensitivity_sweep.json`, doc § Stage 4C в
`docs/ORGAN_MODEL.md`. HYP-0 не затрагивается.

## Этап 4D — Decoupled niche recovery и supply-demand координация (готов ✅)

- [x] opt-in `recovery_model` (`none` побайтово = Stage 4C):
      `RecoveryPolicy`/`RecoveryPlan` (чистое планирование), delayed
      capacity/ECM-события с merge, динамические capacities (деградация от
      спроса/сенесценции, ceiling 2×, floor 0), ECM-реставрация в ткань
- [x] supply-demand режимы (`independent_all`, `supply_demand_greedy`,
      `lookahead_supply_demand`, `deferral_supply_demand`, joint score с
      `supply_beta`); deferral-очередь обоих типов (recovery — по headroom);
      9 старых режимов и алиасы сохранены; legacy-режимы + recovery =
      независимое исполнение recovery
- [x] новые причины отказа (`capacity_exhaustion`, `ecm_collapse`,
      `recovery_debt`, `chronic_inflammatory_overload`) с порогами,
      не срабатывающими на legacy-прогонах (все хранимые выводы 4A–4C
      воспроизводятся бит-в-бит)
- [x] recovery/capacity/supply метрики + sweep-расширение (recovery-сетки,
      `supply_demand_comparison`, `capacity_transition`,
      writer `recovery` + `recovery_stats.csv`)
- [x] конфиги `organ_decoupled_recovery_{independent,greedy,lookahead,
      deferral}`, `organ_recovery_only_baseline`,
      `organ_decoupled_recovery_compare`,
      `organ_supply_demand_sensitivity_sweep` (768 прогонов),
      `organ_heterogeneous_decoupled_recovery` (+ mirror)
- [x] наблюдение (в рамках модели): recovery-only устойчив; gains vs
      independent_all max ровно 0.0; новая причина `vascular_capacity_failure`
      (4 прогона — pruning recovery создаёт дефицит); `ecm_collapse` и др.
      не посещены; hetero-хрупкость стёрта recovery (обе ttf 200);
      калибровка: при токсичной магнитуде (2.0) фазирование спасает (200 vs
      10), но это страховка от перегрузки, не улучшение устойчивых режимов
- [x] тесты (`tests/test_organ_decoupled_recovery.py`, 23 шт.): 14 групп
      по брифу (совместимость, валидация, детерминизм, purity, spike,
      delay/expiry/merge, capacities, deferral обоих типов, lookahead,
      benefit-измеримость, sweep, hetero, checkpoint, scope)

Новое: recovery-блок `organ_policy`/`organ.py`, supply-demand режимы,
recovery/capacity-метрики, sweep-расширение, конфиги
`organ_decoupled_recovery_*.json` и
`organ_supply_demand_sensitivity_sweep.json`, doc § Stage 4D в
`docs/ORGAN_MODEL.md`. Вывод усилен: non-interference оптимален даже при
отделённом recovery; HYP-0 не затрагивается.

## Этап 4 — Базовое эмерджентное старение

- [ ] минимальный набор механизмов (теломеры + ДНК-повреждения + сенесценция)
- [ ] метрики: living/dead/senescent, lineage depth, telomere state, ...
- [ ] длинные прогоны; наблюдение эмерджентной деградации (или её отсутствия)

## Этап 5 — Интервенции и эксперименты

- [ ] параметрические интервенции (improved DNA repair / senescent-cell clearance /
      improved stem-cell maintenance / improved mitochondrial maintenance /
      combined)
- [ ] baseline vs intervention при одном seed; перепроверка на ≥2 seed
- [ ] анализ: продление / стабилизация / отсутствие деградации
- [ ] первые отчёты в `experiments/`

## Этап 6 — Расширения и открытый анализ

- [ ] NumPy/SoA-оптимизация при необходимости
- [ ] выбракованные: 3D-ткань, метаболизм, иммунитет — исследовательские,
      по требованиям гипотез
- [ ] валидация против литературы по клеточным системам

## Критерии готовности каждого этапа

1. Документация обновлена (любое крупное архитектурное изменение).
2. Тесты зелёные (`pytest`).
3. Код проходит заявленные инварианты (детерминизм, уникальность, lineage).
4. Не выполнено «молча»: результаты фиксируют версии модели и данных.