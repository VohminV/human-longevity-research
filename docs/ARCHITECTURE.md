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

## 2. Пакетная структура (предварительная)

```
src/longevity/
  __init__.py
  version.py
  data/           # отдельный слой данных (позже)
  biology/        # cell.py (Cell, статусы, lineage), params.py (параметры, интервенции)
  sim/            # rng.py (инъекцируемый RNG), engine.py (PopulationEngine, checkpoint)
  experiment/     # config.py (ExperimentConfig), runner.py (run_experiment -> JSON)
  analysis/       # metrics.py (population_metrics, experiment_summary)
tests/
  ...
```

Состав на этапе 2 зафиксирован (см. `docs/ROADMAP.md`).

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