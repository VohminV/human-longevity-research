# EXPERIMENTS.md — Вычислительный эксперимент: формат и протокол

> Это не клинические испытания и не медицинские рекомендации.
> Это **framework для контролируемых вычислительных экспериментов**
> над параметризованной клеточной моделью.

## 1. Концепт эксперимента

```
Experiment(
    population=N,
    seed=42,
    duration=...,
    model_version=...,
    parameters=...,
    intervention=...
)
```

## 2. Конфигурация (обязательные поля)

| Поле | Описание | Обязательно |
|---|---|---|
| `experiment_id` | уникальный идентификатор | да |
| `seed` | seed RNG | да |
| `population` | стартовое число клеток | да |
| `duration` | горизонт симуляции | да |
| `model_version` | версия модели | да |
| `data_version` | версия набора данных/параметров | да |
| `parameters` | словарь параметров модели | да |
| `interventions` | список модификаций параметров | да (пустой = baseline) |
| `metrics_config` | какие метрики записывать | да |
| `notes` | свободные заметки | нет |

## 3. Метрики

Каждый запуск сохраняет серию метрик:

```
cell count, living cells, dead cells, senescent cells,
cell division rate, lineage depth, DNA damage, mutation burden,
telomere state, stem-cell reserve, regenerative capacity,
inflammation, organ function, biological age,
healthspan, lifespan
```

Ни один параметр не считается достаточным сам по себе.

## 4. Результат (файл результата)

Формат реализован в `longevity.experiment.runner.run_experiment`
(`RESULT_FORMAT_VERSION = "1.0"`, `ENGINE_VERSION = "population-engine/v0"`):

```
{
  "experiment_id": ...,
  "config": {experiment_id, seed, population, duration, model_version,
             data_version, parameters, effective_parameters, interventions,
             metrics_config, notes},
  "metrics": {series: [{sim_time, population, normal, senescent, dead, depth, ...}],
              final: {...}},
  "summary": {final_population, final_normal, final_senescent, total_deaths,
              total_divisions, max_lineage_depth, population_senescent_fraction},
  "runtime": {engine, run_duration_s, platform, timestamp_utc, model_version},
  "rng_summary": {rng_seed_confirmed, ...},
}
```

Запись в JSON — через `out_path` (родительский каталог создаётся автоматически).

`run_experiment(..., record_milestones=True)` дополнительно кладёт под
`metrics.milestones` журнал событий деления
`[{sim_time, live_count, born_count, dead_count}, ...]` — из него выводятся
точные времена достижения стадий (2/4/8 клеток). На основе milestones построен
калибровочный отчётный слой (`longevity.calibration`), см. `docs/CALIBRATION.md`.

## 5. Сравнение (baseline vs intervention)

Минимальная схема:

1. Запуск **baseline** (interventions=[]), seed=42.
2. Запуск **intervention** (например, изменён `dna_repair_capacity`), seed=42.
3. Запуск **intervention + другой seed** (например, seed=43) — для проверки
   устойчивости вывода.
4. Сравнение метрик; вывод о **продлении** (конечном), **стабилизации** или
   **доказательстве отсутствия деградации** (см. `docs/IMMORTALITY.md`).

## 6. Протокол валидности вывода

- Любое сравнение между конфигурациями выполняется при **одинаковом seed**, если цель —
  изолировать вмешательство.
- Для «стабилизации»/«immortality» вывод делается только при ≥2–3 seed и горизонте,
  значительно превышающем baseline lifespan.
- В отчёте указываются: пороги метрик, горизонты, seed, версии.

## 7. Хранение

- Конфигурация и результаты — в `experiments/` (JSON или совместимый формат).
- Крупные сгенерированные трейсы НЕ коммитятся в git без необходимости.
- Каждому выпуску цифр сопоставляются ревизии `model_version` и `data_version`.

## 8. Открытые вопросы перед реализацией

1. **Единицы времени — РЕШЕНО: часы (hours).** `duration` и все параметры времени
   (например, `doubling_time_mean`) — в часах. Поколения выводятся из lineage.
2. Что считать порогом «деградации» для healthspan (задание по умолчанию).
3. Стандартный минимальный набор интервенций (клонирование параметров).
4. Достаточно ли одной метрики-индикатора для ранней фазы (недостаточно — см. §3).