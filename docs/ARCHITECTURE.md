# ARCHITECTURE.md — Архитектура вычислительной платформы

Цель: разделить научную теорию, данные, движок, эксперименты и анализ так, чтобы
**не связывать научную модель с GUI** и **не смешивать данные публикаций с кодом
симулятора**.

## 1. Слои

```
┌───────────────────────────────────────────────┐
│  DATA LAYER          научные данные, версии    │
│    research/datasets  research/literature      │
│    research/evidence  research/hypotheses      │
└───────────────┬───────────────────────────────┘
                │ импорт (полу-структурированный)
┌───────────────▼───────────────────────────────┐
│  BIOLOGICAL MODEL LAYER   доменные сущности    │
│    Cell, Lineage, CellCycle, Telomere, ...     │
│    (чистые модели, без I/O и UI)               │
└───────────────┬───────────────────────────────┘
                │ используется
┌───────────────▼───────────────────────────────┐
│  SIMULATION ENGINE LAYER  runtime              │
│    движок времени, RNG, планировщик событий,   │
│    checkpoint/restore                          │
└───────────────┬───────────────────────────────┘
                │ запускает
┌───────────────▼───────────────────────────────┐
│  EXPERIMENT ENGINE LAYER  контроль             │
│    эксперименты, intervention, конфигурация,   │
│    протоколы и результаты                      │
└───────────────┬───────────────────────────────┘
                │ анализирует
┌───────────────▼───────────────────────────────┐
│  ANALYSIS LAYER   метрики, сравнение, выводы   │
└───────────────┬───────────────────────────────┘
                │
┌───────────────▼───────────────────────────────┐
│  VISUALIZATION LAYER   (позже, не в v0)       │
└───────────────────────────────────────────────┘
```

Правила связи:

- DATA не импортируется симулятором напрямую. Данные превращаются в **параметры и
  диапазоны** (см. `docs/RESEARCH.md`) на этапе конфигурации эксперимента.
- BIOLOGICAL MODEL не знает о симуляторе и RNG; он содержит чистые функции/состояния.
- SIMULATION ENGINE не знает о научных источниках.
- EXPERIMENT ENGINE связывает модель с конфигурацией и записывает результат.
- GUI/визуализация опциональна и не влияет на науку.

## 2. Пакетная структура (фактическая, Stage 8.5)

```
src/longevity/
  __init__.py
  version.py
  biology/        # cell.py (Cell, статусы, lineage), params.py (параметры, интервенции)
  sim/            # rng.py (инъекцируемый RNG), engine.py (PopulationEngine, checkpoint)
  model/          # tissue.py, policy.py, organ.py, organism.py, intervention.py,
                  # aging.py, organ_backed.py, organ_network.py, reversibility.py,
                  # boundary.py (Stage 3A → 6D)
  calibration/    # reference, stages, compare, multirun, sensitivity (Stage 3)
  experiment/     # config.py, runner.py, tissue_runner/sweep, organ_runner/sweep,
                  # organism_runner/policy_search/robust/aging/organ_backed/
                  # organ_network/reversibility/boundary (Stage 3A → 7)
  analysis/       # metrics.py, tissue_metrics/sweep, organ_metrics, organism_metrics,
                  # aging_metrics, organ_backed/network/reversibility/boundary_metrics
  research/       # biological_alignment.py — pure validator манифеста Stage 8 (без симуляции)
tests/            # 565 тестов: детерминизм, инварианты, checkpoint/restore, свипы, поиски,
                  # boundary probe 6D, compound wall 6E, heterogeneous probe 6F,
                  # robustness audit 7, alignment validator 8
```

Состав на этапе 2 зафиксирован (см. `docs/ROADMAP.md`); расширения
Stage 3 → 8 добавляли только новые модули (`model/`, `calibration/`,
`research/`) и новые раннеры/метрики, не меняя контрактов слоёв §1.

## 3. Модель клетки (концептуальная спецификация)

Минимально достаточный набор полей (вводить поэтапно):

```
id
parent_id
generation
lineage_id
cell_type
differentiation_state
position
age
cell_cycle_state        (G0/G1/S/G2/M)
telomere_state
dna_damage
dna_repair_capacity
mutation_state
metabolic_state
senescence_state
apoptosis_state
environmental_state
```

Статусы клетки: `normal` / `senescent` / `apoptotic` / `dead`.

## 4. Воспроизводимость и RNG

- Единый источник случайности (один `random.Random` или `numpy` Generator), передаваемый
  в движок; никакие глобальные random не используются.
- `seed` — часть конфигурации эксперимента.
- **требование:** одинаковый seed ⇒ одинаковый результат;
- **требование:** restore из checkpoint продолжает симуляцию идентично непрерывному
  запуску при том же seed и том же состоянии RNG (RNG сериализуется в checkpoint).

## 5. Checkpoint / restore

Формат реализован в `longevity.sim.engine.PopulationEngine.to_checkpoint_dict`
(+ `from_checkpoint`). Первый уровень зафиксирован:

```
checkpoint = {
  "model_version": "0.1.0",
  "sim_time": ...,
  "next_id": ...,
  "rng_state": [...],         # сериализованное состояние RNG (state_to_json)
  "population": {...},        # id -> клетка (cell.to_dict); lineage -> list
  "counters": {...},
  "parameters": {...},
}
```

Формат JSON-safe: `to_checkpoint_dict` + `json.dumps` + `json.loads` +
`from_checkpoint` даёт симуляцию, идентичную непрерывному запуску (тест
`test_restore_after_json_roundtrip`).

## 6. Производительность

Сначала reference-реализация. Приоритет:

```
correctness → reproducibility → testability → clarity
```

Позже возможен переход: Python objects → NumPy → SoA → Numba → GPU/CuPy/PyTorch.
Не оптимизировать преждевременно.

## 7. Версии модели и данных

- Каждый эксперимент фиксирует `model_version` и источник данных (пакет/версию).
- Изменение научных данных или параметров не молча влияет на результаты: оно видно
  в конфигурации эксперимента.

## 8. Принятые решения (ADR — архитектурные решения)

| Решение | Статус |
|---|---|
| Научная модель отделена от I/O и GUI | принято |
| Данные публикаций не входят в код симулятора | принято |
| RNG инъекцируется, а не глобальный | принято |
| Reference-реализация, оптимизация позже | принято |
| Эксперименты хранят полный контекст (seed, версии, параметры) | принято |
| GUI/визуализация — вне ядра | принято |
| Единицы времени симуляции — часы (hours) | принято |
| Теломерная динамика и DNA damage — отдельные опции, выключены по умолчанию (пустой dict = включить с defaults) | принято |
| Сенесценция в этапе 2 — детерминированная (порог по теломерам / DNA damage) | принято |
| `cell_cycle` — опциональная группа стадия-зависимого цикла (пороги по числу клеток), opt-in, обратно совместима с v0.1.0 | принято |
| `population` обязан быть `1` при активированной `cell_cycle` (один эмбрион) | принято |

## 9. Эксперимент (концепт)

```
Experiment(
    population=N,
    seed=42,
    duration=...,
    model_version=...,
    parameters=...,
    intervention=...,
)
```

Результат сохраняет: seed, configuration, model version, source dataset version,
parameters, interventions, metrics, simulation duration, result summary.
Подробнее — `docs/EXPERIMENTS.md`.

## 10. Параметрическая группа `cell_cycle` (v0.2.0)

Опциональная группа верхнего уровня в `parameters` (валидация —
`longevity.biology.params`):

```
cell_cycle:
  phases: [ { threshold, mean, sd?, death_per_division? }, ... ]
```

- Фаза активна при `threshold <= число живых клеток` (пороги строго
  возрастающие, первый = 0). Цикл деления в активной фазе — `max(0, gauss(mean, sd))`.
- `sd` по умолчанию = `doubling_time_sd`; `death_per_division` по умолчанию = 0.0
  и комбинируется с глобальным `mortality.rate` как независимый риск.
- Без группы движок ведёт себя как v0.1.0 (долевое `doubling_time_mean/sd`).
- `apply_interventions` адресует фазы через индексы списка
  (`cell_cycle.phases.2.mean`); список фаз нельзя создать «с нуля» интервенцией.
- Семантика запуска: `cell_cycle` ⇒ единичный эмбрион ⇒ `population == 1`
  (ошибка в движке и в `ExperimentConfig`).

Детали и валидационные правила — `docs/DEVELOPMENTAL_DYNAMICS.md` §2.