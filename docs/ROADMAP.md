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

## Этап 5A — Minimal organism life-course and longevity policy search (готов ✅)

- [x] `OrganismModel`: стадии embryo→late_aging (+ вычисляемый
      terminal_decline), 8 витальных систем (function/reserve/damage +
      sensitivities; у brain — `informational_continuity`), 9 глобальных
      драйверов старения, bio_age ≠ chrono_age, смерть отказом витальных
      систем (12 причин + `unknown`-fallback по max_age), checkpoint/restore,
      инжектируемый RNG
- [x] `intervention.py`: 8 классов (repair/replacement/maintenance/
      modulation/boost/neural/surveillance/recovery — у каждого польза И
      цена), `LongevityPolicy` (periodic/threshold + refractory-cooldown +
      constraints), `PolicySet` (детерминирован); 10 политик (natural,
      senolytic, repair, regenerative/antiinfl/surveillance-блоки, neural,
      combined, adaptive, organ-inspired)
- [x] метрики: lifespan/healthspan (hs ≤ ls), AUC бремён, slopes после
      зрелости, `bounded_degradation_indicator(ε)`, fitness multi-objective,
      Pareto, агрегаты по сидам; `immortality_status = hypothesis_not_proven`
- [x] раннер + CLI (`organism_runner --config/--out`), deterministic
      policy search (grid/random/hill-climbing-lite, top-K, pareto, long CSV)
- [x] 8 конфигов (`organism_life_course_{baseline,senolytic,molecular_repair,
      combined_maintenance,adaptive_threshold,neural_preserving,
      organ_inspired}` + `organism_policy_search_mini`)
- [x] наблюдение (seed 42, в рамках модели): baseline 68.0/61.8 cascade;
      repair (74.5) > replacement (70.0); combined 80.5; adaptive 117.8/100.2
      (лучший, цена — cancer ×3.3); neural самый чистый по раку (0.89);
      organ-inspired 79.0 ≈ combined при меньшем раке; search (27×2):
      лучший repair q3 + senolytic q3 (96.2/84.8), bounded 0/27, pareto 14 —
      candidate immortality policy НЕ найдена
- [x] тесты (4 файла, 26 шт.): 12 групп по брифу (совместимость,
      детерминизм, валидация, life-course, bio-age, 8 классов, trade-offs,
      hs≤ls, neural identity, search, organ-inspired, scope без bio-claims)

Новое: `longevity.model` (organism, intervention), `longevity.analysis`
(organism_metrics), `longevity.experiment` (organism_runner,
organism_policy_search), конфиги `experiments/configs/organism_*.json`,
doc `docs/ORGANISM_MODEL.md`. HYP-0 формализована как candidate policy,
не доказана.

## Этап 5B — Robust long-horizon longevity policy search and stress testing (готов ✅)

- [x] opt-in `perturbation_model = parametric_noise` (`none` побайтово = 5A):
      шум aging/repair/efficacy на выделенных RNG-потоках + 7 типов
      детерминированных шоков; по пути пойман баг общего perturb_seed=0
      (все noise-прогоны были идентичны) + отсутствие seed в вызове модели
      из раннера — исправлено с регрессионным тестом
- [x] multi-seed агрегаты, rolling windows, `robust_bounded_degradation_indicator`
      (rate ≥ 0.8 + worst-case slopes + чистые окна), binding constraints
      (первое нарушение в каноническом порядке), robust fitness
      (mean − λ·std − λ·worst, дефолтные λ = 0)
- [x] stress suite из 9 сценариев + модуль `organism_robust` (CLI
      `organism_stress`): runs × seeds × scenarios, comparison/binding/
      stress-артефакты
- [x] 8 конфигов (`organism_robust_{baseline,key_policies,adaptive_constrained,
      repair_plus_senolytic,neural_preserving_extended}`,
      `organism_long_horizon_search` (250y), `organism_stress_suite` (135 прогонов),
      `organism_robust_policy_search_mini`)
- [x] наблюдение (в рамках модели): ranking стабилен везде (adaptive 118.7 >
      search_best 95.5 > combined 80.7 > inspired 79.1); robust_bounded —
      false везде (0/45 stress-ячеек, 0/27 поисков); binding всегда
      `biological_age_slope` (70/70); adaptive constrained: cancer −24% без
      потери benefit; toxicity — самый опасный стресс; neural_stress не
      влияет; long horizon (250y) без новых поздних причин
- [x] тесты (3 файла, 23 шт.): 15 групп по брифу (совместимость,
      детерминизм, агрегация, пертурбации, шоки, горизонт/окна, robust
      индикатор, binding, stress, robust-поиск, adaptive constraints,
      hybrid, neural-extended, checkpoint+cooldown, scope)

Новое: perturbation/shock-слой `organism.py`, состояние cooldown
`intervention.py`, robust/window/binding-метрики, `organism_robust`
(мультисид + стрессы), robust-фитнес в поиске, конфиги
`experiments/configs/organism_robust_*.json`,
`organism_long_horizon_search.json`, `organism_stress_suite.json`,
doc § Stage 5B в `docs/ORGANISM_MODEL.md`, критерий в `docs/IMMORTALITY.md`,
статус в `research/hypotheses/HYP-0_immortality_policy.md`.
HYP-0: `hypothesis_not_proven`, связывающее ограничение —
`biological_age_slope`.

## Этап 5C — Mechanistic aging drivers and biological age reversibility search (готов ✅)

- [x] opt-in `aging_mechanism_model = none | mechanistic_drivers`
      (`none` численно идентичен Stage 5B); 8 драйверов с накоплением,
      репарацией, обратимостью, diminishing returns; `biological_age` —
      взвешенная агрегация с полом `adult_age_setpoint`
      (rejuvenation = возврат к взрослому setpoint)
- [x] 12 mechanistic вмешательств с ценами/рисками (reprogramming —
      cancer/neural; telomere/stem — cancer; teratogenic proxy до
      зрелости); `driver:*` биомаркеры; 12+ mechanistic политик
      (одиночные, combined, adaptive, neural preserving, organ-inspired)
- [x] `dominant_binding_driver`, `robust_bounded_degradation_v2`,
      driver-aware fitness, binding-driver sweep, mechanistic stress
      suite; 16 конфигов `organism_aging_*.json`
- [x] наблюдение (в рамках модели): legacy 68.0 = Stage 5B бит-в-бит;
      combined лучший (70.8, bio slope 0.417 >> eps); одиночные слабее;
      search mini лучший 72.2/65.2, v2 false везде; sweep 18/27 —
      `epigenetic_drift`, 9/27 — `cellular_senescence`; stress ranking
      стабилен; bounded v2 — нигде
- [x] тесты (4 файла): совместимость, детерминизм, границы, floor,
      trade-offs, binding, v2, поиск, стресс, checkpoint, scope

Новое: `longevity.model` (aging), mechanistic-слой `organism.py` /
`intervention.py`, `longevity.analysis` (aging_metrics),
`longevity.experiment` (organism_aging), конфиги
`experiments/configs/organism_aging_*.json`, doc `docs/AGING_MODEL.md`,
§ Stage 5C в `docs/ORGANISM_MODEL.md`, критерий в `docs/IMMORTALITY.md`,
статус в `research/hypotheses/HYP-0_immortality_policy.md`.
HYP-0: `hypothesis_not_proven`; доминирующие связывающие драйверы —
`cellular_senescence` / `epigenetic_drift`.
Ограничение: абстрактный организм, порядковые параметры,
операциональные пороги, малое число seeds, HYP-0 формализована, но не
доказана.

## Этап 6A — Organ-backed emergent aging and cross-scale policy search (готов ✅)

- [x] opt-in `organ_backed_model = none | reduced_organ_proxies`
      (`none` численно идентичен Stage 5C); 8 reduced organ proxies
      (идеи Stage 4, не экземпляры `OrganModel`), маппинг на витальные
      системы, частично эмерджентные драйверы (`emergent_weights`)
- [x] systemic resources (perfusion/immune/metabolic/repair) с
      demand/allocation/shortfall; органные цены вмешательств;
      отдельный `resource_shock` вне Stage 5B потока
- [x] 5 organism coordination modes (independent/scaling/priority/
      lookahead/deferral) + FIFO-очередь в checkpoint; органные
      биомаркеры (`organ:*`, `resource:*`, минимумы)
- [x] `dominant_binding_level/organ/driver/resource`,
      `robust_bounded_degradation_v3`, cross-scale fitness
      (`w_organ_slope`, `w_resource_shortfall`, `w_bounded_v3_bonus`),
      coordination compare + resource sensitivity модули
- [x] 10 конфигов `organism_organ_backed_*.json`
- [x] наблюдение (в рамках модели): baseline 82.8/71.8; maintenance
      88.0; combined 101.5/87.2; adaptive 97.5; search best 104.8;
      coordination: independent = deferral = lookahead, scaling −0.25;
      repair — критичнейший ресурс (бюджет 4 → ~76–79); stress ranking
      стабилен; v3 — нигде, binding level везде `biological_age`
- [x] тесты (5 файлов, 31 шт.): совместимость, детерминизм, маппинг,
      эмерджентность, ресурсы, координация, binding, v3, свипы, поиск,
      стресс, checkpoint, scope

Новое: `longevity.model` (organ_backed), organ-слой `organism.py` /
`intervention.py`, `longevity.analysis` (organ_backed_metrics),
`longevity.experiment` (organism_organ_backed), конфиги
`experiments/configs/organism_organ_backed_*.json`, doc
`docs/ORGAN_BACKED_ORGANISM_MODEL.md`, § Stage 6A в
`docs/ORGANISM_MODEL.md`, ссылка в `docs/ORGAN_MODEL.md`, секция в
`docs/AGING_MODEL.md`, критерий в `docs/IMMORTALITY.md`, статус в
`research/hypotheses/HYP-0_immortality_policy.md`.
HYP-0: `hypothesis_not_proven`; связывающий уровень —
`biological_age` во всех ячейках.
Ограничение: абстрактный organ-backed организм, reduced proxies,
порядковые параметры, операциональные пороги, малое число seeds,
HYP-0 формализована, но не доказана.

## Этап 6B — Cross-organ network, systemic feedback, and hard physical limits (готов ✅)

- [x] opt-in `organ_network_model = none | reduced_network_feedback`
      (`none` численно идентичен Stage 6A); 12 рёбер по умолчанию,
      7 feedback loops, hard limits (energy/information/mutation/
      irreversible/niche/toxicity)
- [x] network-derived `biological_age_network` с floor adult setpoint;
      7 network coordination modes; 9 новых причин отказа (аддитивно)
- [x] `robust_bounded_degradation_v4` + network binding analysis
      (level/organ/driver/resource/edge/loop/hard limit)
- [x] 11 конфигов `organism_organ_network_*.json` (baseline, maintenance,
      combined, adaptive, neural, coordination compare, resource sweep,
      hard-limit sweep, robust search mini, stress)
- [x] наблюдение (в рамках модели): baseline 67.0/58.2; combined
      76.5/68.8; adaptive 76.8/70.2; coordination 6×3 все 76.5
      (non-interference на сетевом уровне); repair снова критичен
      (4 → ~55; ≥8 → ~77.8); v4 — нигде, binding везде `biological_age_slope`
- [x] тесты (6 файлов, 39 шт.): совместимость, детерминизм, feedback,
      limits, coordination, binding, v4, свипы, поиск, стресс, checkpoint, scope

Новое: `longevity.model` (organ_network), сетевой слой `organism.py` /
`intervention`-pricing, `longevity.analysis` (organ_network_metrics),
`longevity.experiment` (organism_organ_network), конфиги
`experiments/configs/organism_organ_network_*.json`, doc
`docs/ORGAN_NETWORK_MODEL.md`, § Stage 6B в `docs/ORGANISM_MODEL.md`,
`docs/AGING_MODEL.md`, `docs/ORGAN_BACKED_ORGANISM_MODEL.md`, критерий в
`docs/IMMORTALITY.md`, статус в `research/hypotheses/HYP-0_immortality_policy.md`.
HYP-0: `hypothesis_not_proven`; связывающее ограничение —
`biological_age_slope` во всех ячейках.
Ограничение: абстрактный organ-network организм, reduced proxies/edges,
порядковые параметры, операциональные пороги, малое число seeds,
HYP-0 формализована, но не доказана.

## Этап 6C — Reversibility ceiling and irreversible accumulation search (готов ✅)

- [x] opt-in `reversibility_model = none | split_reversible_irreversible`
      (`none` численно идентичен Stage 6B); per-driver/per-organ
      reversible/irreversible ledger, conversion с модификаторами,
      repair ceiling с cost/risk/diminishing, information debt, mutation
      fixation, niche disorder, entropy production
- [x] reversibility-derived `biological_age_reversibility` с динамическим
      irreversible floor; 9 новых intervention-типов (`rev_*` ключи);
      7 coordination modes; 9 новых причин отказа (аддитивно)
- [x] `robust_bounded_degradation_v5` + reversibility binding analysis
      (wall/level/organ/driver/resource/edge/loop/hard limit)
- [x] 14 конфигов `organism_reversibility_*.json` (baseline, preventive,
      clearance, irreversible repair, combined, aggressive, neural,
      coordination compare, ceiling sweep, conversion sweep,
      info/mutation sweep, robust search mini, stress)
- [x] наблюдение (в рамках модели): baseline 67.0/58.2, wall
      `irreversible_accumulation`; combined 69.5/60.5; aggressive 69.0
      (долги растут); conversion 0.05 роняет lifespan 69.5 → 60.5;
      coordination 4×3 все 69.5 (non-interference); ceiling sweep плоский;
      v5 — нигде, binding везде `biological_age_slope`
- [x] тесты (6 файлов, 39 шт.): совместимость, детерминизм, split,
      conversion, ceiling, floor, interventions, trade-offs, coordination,
      binding, v5, свипы, поиск, стресс, checkpoint, scope

Новое: `longevity.model` (reversibility), reversibility-слой
`organism.py` / `intervention.py`, `longevity.analysis`
(reversibility_metrics), `longevity.experiment`
(organism_reversibility), конфиги
`experiments/configs/organism_reversibility_*.json`, doc
`docs/REVERSIBILITY_MODEL.md`, § Stage 6C в `docs/ORGAN_NETWORK_MODEL.md`,
`docs/AGING_MODEL.md`, `docs/ORGANISM_MODEL.md`, критерий в
`docs/IMMORTALITY.md`, статус в `research/hypotheses/HYP-0_immortality_policy.md`.
HYP-0: `hypothesis_not_proven`; доминирующий wall —
`irreversible_accumulation` / conversion.
Ограничение: абстрактный organ-network reversibility организм, reduced
proxies/edges, порядковые параметры, операциональные пороги, малое число
seeds, HYP-0 формализована, но не доказана.

## Этап 6D — Irreversibility boundary probe and structural wall attribution (готов ✅)

- [x] opt-in `boundary_probe_model = none | irreversibility_ablation`
      (`none` и нейтральные scales численно идентичны Stage 6C);
      `conversion_scale` / `independent_accrual_scale` /
      `repair_ceiling_scale`, component overrides, ablation flags
      (unlimited ceiling — non-physiological exploratory, помечается)
- [x] contribution decomposition
      (`conversion_flux + independent_accrual − repair_offset = net slope`),
      dominant source attribution, parametric-vs-structural wall
      classification (только внутримодельная)
- [x] 13 конфигов `organism_reversibility_boundary_*.json` (legacy, default,
      conversion/independent/both suppressed, high/unlimited ceiling,
      3 ultra-свипа 9+9+7 точек, component attribution, robust search, stress)
- [x] наблюдение (в рамках модели): conversion_scale=0 снижает
      irreversible slope 0.00536 → 0.00082 (в допуске), но v5 false —
      binding смещается на `biological_age_slope`;
      independent sweep почти не двигает slope (conversion доминирует);
      ceiling sweep плоский; attribution default → conversion /
      `driver:stem_exhaustion`, conversion_zero → independent /
      `driver:dna_damage`, both_suppressed → `information_debt`;
      v5 false везде (default, аблации, свипы, search, stress)
- [x] wall classification: `parametric_irreversibility_wall` —
      irreversible-компонент подавим параметрически, но v5 как целое
      недостижима (исход 2: подавление открывает другую стену)
- [x] тесты (5 файлов, 30 шт.): совместимость, нейтральность scales,
      детерминизм, валидация, аблации, overrides, decomposition,
      attribution, classification, свипы, поиск, стресс, checkpoint, scope

Новое: `longevity.model` (boundary), ablation-слой `organism.py`,
`longevity.analysis` (boundary_metrics), `longevity.experiment`
(organism_boundary), конфиги
`experiments/configs/organism_reversibility_boundary_*.json`, § Stage 6D
в `docs/REVERSIBILITY_MODEL.md`, критерий в `docs/IMMORTALITY.md`,
статус в `research/hypotheses/HYP-0_immortality_policy.md`.
HYP-0: `hypothesis_not_proven`; dominant source — `conversion`,
компонент — `driver:stem_exhaustion`.
Ограничение: диагностические аблации, не биологические допущения;
абстрактная модель; порядковые параметры; n ≤ 3.

## Этап 6E — Compound wall attribution and knife-edge probe (готов ✅)

- [x] knife-edge probe: single-конфиг (`conversion_scale=1e-4`,
      `independent_accrual_scale=0.0`) и sweep
      `0.0, 1e-6, 1e-5, 1e-4, 1e-3, 1e-2, 0.1, 1.0` при independent=0 —
      переиспользует generic `conversion_ultra_sweep` раннера, без новой динамики
- [x] `decompose_biological_age_slope` (`boundary_metrics.py`): раскладка
      mechanistic slope по 8 драйверам весами модели + 6 семейств +
      residual; linear diagnostic proxy, вход не мутируется
- [x] `classify_compound_wall` (pure): 7 labels — `no_wall`,
      `single_channel_parametric_wall`, `knife_edge_parametric_wall`,
      `compound_residual_wall`,
      `structural_under_current_abstraction_wall`, `ceiling_mediated_wall`,
      `inconclusive_sensitivity_failure`; неполные данные и нестабильность
      seed/eps/dt → всегда `inconclusive`, угадывания нет
- [x] sensitivity-kind в `organism_boundary.py`: траектории один раз на
      (dt × аблация × seed), вердикт v5 переоценивается на каждый eps без
      реранов; per-seed v5, stability-флаги и compound-классификация в артефактах
- [x] 4 конфига `organism_reversibility_boundary_{knife_edge_conversion_1e-4,
      knife_edge_sweep,compound_attribution,sensitivity}.json`
- [x] наблюдение (в рамках модели, seeds 42/7/99): knife sweep 8×3 —
      v5=false везде, включая 1e-6 (knife-edge нет, порога нет); binding
      везде `biological_age_slope`; source `conversion` (≥0.01) →
      `information_debt` (≤0.001)
- [x] bio-age attribution стабильна: total slope ≈ 1.33, dominant
      `proteostasis_loss` → `proteostasis_metabolic` (0.69), далее
      `stem_exhaustion` (0.23), `inflammatory_senescent` (0.18);
      residual −0.014 (прокси объясняет ~99%); значимых источников — 3
- [x] sensitivity (eps × dt × аблации × 5 seeds, 60 прогонов): eps/dt/seed
      stable все true; v5=false во всех 36 ячейках, включая самый мягкий eps
- [x] compound wall в sensitivity и compound-attribution независимо:
      `compound_residual_wall` — irreversible slope подавлен, v5 false,
      binding `biological_age_slope`, ≥2 остаточных источников
- [x] тесты (4 новых файла + 1 в 6D-файле, 20 шт.): knife-edge,
      attribution (shares, ties, немутация, legacy), classifier (все 7
      labels, insufficient data, нестабильность), sensitivity
      (переиспользование траекторий, mini end-to-end, загрузка конфигов)

Новое: `decompose_biological_age_slope`, `classify_compound_wall`,
`compute_eps_sensitivity`, `select_suppressed_evidence`
(`boundary_metrics`); `SensitivityConfig`, `run_sensitivity`
(`organism_boundary`); bio-age attribution в seed-строках и
compound_wall в attribution-артефактах; § Stage 6E в
`docs/REVERSIBILITY_MODEL.md`, критерий в `docs/IMMORTALITY.md`, статус
в `research/hypotheses/HYP-0_immortality_policy.md`.
HYP-0: `hypothesis_not_proven`; wall — `compound_residual_wall`.
Ограничение: diagnostic proxies, не conservation laws; shares линейны;
unlimited ceiling exploratory; n ≤ 5; dt ∈ {0.5, 0.25, 0.1}.

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