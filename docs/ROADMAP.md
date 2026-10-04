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