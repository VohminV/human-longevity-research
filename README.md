# HUMAN LONGEVITY RESEARCH

![stages](https://img.shields.io/badge/stages-1%E2%80%936A_done-brightgreen)
![tests](https://img.shields.io/badge/tests-364_passing-brightgreen)
![HYP-0](https://img.shields.io/badge/HYP--0-hypothesis_not_proven-orange)
![python](https://img.shields.io/badge/python-%3E%3D3.10-blue)

**Вычислительная исследовательская платформа для изучения человеческого развития,
старения, регенерации, продолжительности жизни и потенциальных механизмов радикального
продления здоровой жизни.**

> Презентация прогресса: **[PRESENTATION.md](PRESENTATION.md)** — визуальный обзор
> всех этапов, ключевых результатов и статуса гипотезы HYP-0.

> **Ключевая долгосрочная гипотеза проекта:**
> Можно ли построить достаточно подробную вычислительную модель человека, чтобы
> экспериментально исследовать механизмы старения и определить, какие изменения способны
> замедлять, останавливать или обращать отдельные процессы деградации организма?
>
> «Бессмертие» НЕ является заранее доказанным результатом. Это предельная
> исследовательская гипотеза, а не утверждение.

---

## Принцип

**СНАЧАЛА ПРАВИЛЬНАЯ НАУЧНАЯ МОДЕЛЬ.**

**ПОТОМ СИМУЛЯТОР.**

**ПОТОМ ЭКСПЕРИМЕНТЫ.**

**ПОТОМ ПРОВЕРКА ГИПОТЕЗ.**

Модель не подгоняется под идею бессмертия. Пусть результаты симуляции сами показывают,
какие механизмы ограничивают жизнеспособность системы.

## Уровни модели

```
SCIENTIFIC DATA
        ↓
BIOLOGICAL MODEL
        ↓
CELL MODEL
        ↓
TISSUE MODEL
        ↓
ORGAN MODEL
        ↓
ORGANISM MODEL
        ↓
AGING MODEL
        ↓
INTERVENTION MODEL
        ↓
COMPUTATIONAL EXPERIMENTS
        ↓
LONGEVITY ANALYSIS
```

Симулятор — инструмент исследования, а не игровая симуляция человека.

## Прогресс

```text
Этапы 1–6A:  ███████████████ 15/15 завершены
HYP-0:       hypothesis_not_proven (честный статус во всех артефактах)
Тесты:       364 passing (детерминизм, инварианты, checkpoint/restore)
```

| Блок | Этапы | Статус | Главный вывод |
|---|---|---|---|
| Клетка и развитие | 1, 2, 3, 3.5 | ✅ | Калибровка против данных → **MODEL MISMATCH**, частичное закрытие (модель C) |
| Ткань | 3A–3C | ✅ | Устойчивые политики замены существуют; агрессивная замена истощает stem pool |
| Орган | 4A–4D | ✅ | `non-interference is optimal` — координация не бьёт independent execution |
| Организм | 5A | ✅ | Adaptive control: lifespan 117.8; bounded degradation — нигде |
| Robust | 5B | ✅ | Binding constraint везде одно: `biological_age_slope` (70/70) |
| Mechanistic | 5C | ✅ | Драйверы разложены; доминируют `cellular_senescence` / `epigenetic_drift`; v2 — нигде |
| Organ-backed | 6A | ✅ | Прокси + ресурсы + координация; лучший 104.8; v3 — нигде, binding везде `biological_age` |
| Дальше | 5D / 6B | ⏳ | Более глубокая обратимость или следующий cross-scale шаг |

Детали — в [PRESENTATION.md](PRESENTATION.md) и `docs/ROADMAP.md`.

## Понятия

- **LIFESPAN** — сколько времени организм существует.
- **HEALTHSPAN** — сколько времени организм сохраняет нормальную функцию.
- **REJUVENATION** — возвращение отдельных систем в более молодое функциональное состояние.
- **IMMORTALITY** — способность организма сохранять необходимую функциональность неопределённо долго.

Эти понятия не смешиваются. Разделение и определения — в `docs/LONGEVITY.md`.

## Документация (`docs/`)

| Документ | Содержание |
|---|---|
| `RESEARCH.md` | Научный контекст, граница между наблюдением и гипотезой |
| `BIOLOGY.md` | Биологическая основа: клеточный цикл, деление, смерть, дифференцировка |
| `CELL_COUNT.md` | **Критический документ**: сколько клеток на разных стадиях развития человека |
| `CELLULAR_AGING.md` | Потенциальные механизмы старения и их абстракции для модели |
| `LONGEVITY.md` | Lifespan / healthspan / rejuvenation / immortality |
| `IMMORTALITY.md` | Предельная гипотеза: что она означает и как её формулировать строго |
| `TISSUE_MODEL.md` | Модель абстрактной ткани, replacement policy, свипы устойчивости (Stage 3A–3C) |
| `ORGAN_MODEL.md` | Модель абстрактного органа, координация, temporal relief, recovery (Stage 4A–4D) |
| `ORGANISM_MODEL.md` | Модель организменного жизненного цикла и поиска политик (Stage 5A) |
| `AGING_MODEL.md` | Механистический слой старения и reversibility search (Stage 5C) |
| `ORGAN_BACKED_ORGANISM_MODEL.md` | Organ-backed организм: прокси, ресурсы, координация (Stage 6A) |
| `CALIBRATION.md` | Калибровка ранней динамики против данных (MODEL MISMATCH) |
| `DEVELOPMENTAL_DYNAMICS.md` | Стадия-зависимый клеточный цикл (Этап 3.5) |
| `ASSUMPTIONS.md` | Все принятые допущения |
| `LIMITATIONS.md` | Ограничения модели и данных |
| `ARCHITECTURE.md` | Разделение слоёв: DATA / MODEL / ENGINE / EXPERIMENT / ANALYSIS |
| `EXPERIMENTS.md` | Формат контролируемых вычислительных экспериментов |
| `ROADMAP.md` | Этапы развития проекта |
| `DATA_SOURCES.md` | Каталог научных источников (source / DOI / PMID / метод) |

## Структура репозитория

```
docs/          — документация (наука, архитектура, допущения, ограничения)
research/
  literature/  — научные статьи, ключевые цитаты, заметки
  datasets/    — описания и ссылки на данные (без гигантских файлов в git)
  hypotheses/  — сформулированные гипотезы для проверки
  evidence/    — собранные наблюдения с указанием источников
experiments/   — конфигурации и результаты вычислительных экспериментов
src/           — код (reference implementation)
tests/         — тесты ключевых инвариантов
```

## Статус проекта

**Этап 1 — научная и архитектурная основа** — завершён `07651e6`.

**Этап 2 — минимальная модель клетки (reference)** — реализован:

- [x] `Cell`, статусы (normal / senescent / apoptotic / dead), lineage, деление, смерть
- [x] детерминизм по seed; уникальные id; parent/generation/lineage (инварианты + тесты)
- [x] теломерная динамика и DNA damage — отдельные опции (выключены по умолчанию),
      mortality — отдельная опция
- [x] checkpoint/restore (RNG сериализуется, restore идентичен непрерывному запуску)
- [x] `ExperimentConfig` и запись результатов в JSON (`experiments/output/`)

**Этап 3 — раннее развитие: калибровка и стадия-зависимый цикл** — реализован:

- [x] асинхронные циклы, milestones, калибровка против S-6/S-7 → **MODEL MISMATCH** (`docs/CALIBRATION.md`)
- [x] опциональная группа `cell_cycle.phases`, частичное закрытие mismatch (модель C)

**Этапы 3A–3C — абстрактная ткань и карта устойчивости замены** — реализованы:

- [x] компартментная `TissueState` + `ReplacementPolicy` (чистое планирование) + детерминизм + checkpoint
- [x] свип `max_replacement_fraction × frequency`: устойчивое множество политик существует;
      агрессивная замена истощает stem pool при «молодой» сенесцентной нагрузке
- [x] boundary closure + `strong/weak controls` + failure causality
      (strong рвётся по stem, weak — по ECM)

**Этапы 4A–4D — абстрактный орган и координация** — реализованы:

- [x] `OrganModel` из тканевых модулей + shared vascular/immune capacity;
      орган падает по shared-ресурсу при целых тканях
- [x] координация как урезание/приоритизация/отсрочка **не превосходит**
      independent execution (`non-interference is optimal` — честный отрицательный результат)
- [x] temporal relief (immediate cost + delayed relief) и decoupled niche
      recovery с динамическими ёмкостями; recovery сам по себе стабилизирует,
      pruning recovery создаёт дефицит

**Этап 5A — организменный жизненный цикл и поиск политик** — реализован:

- [x] `OrganismModel`: embryo → старость, 8 витальных систем, biological_age,
      смерть отказом (не таймером); baseline: lifespan 68.0, причина — systemic cascade
- [x] 8 классов вмешательств (repair/replacement/maintenance/modulation/boost/
      neural/surveillance/recovery — у каждого польза И цена) + 10 политик
- [x] лучший результат: adaptive threshold control — lifespan 117.8 / healthspan 100.2;
      deterministic policy search (best: repair q3 + senolytic q3 — 96.2/84.8);
      `bounded_degradation_indicator` нигде — candidate immortality policy **не найдена**
- [x] во всех артефактах: `immortality_status = hypothesis_not_proven`

**Этап 5B — robust long-horizon search и стресс-тестирование** — реализован:

- [x] multi-seed оценка, параметрический шум, детерминированные шоки, long horizon (250 лет)
- [x] `robust_bounded_degradation_indicator` — false во всех ячейках; binding всегда `biological_age_slope`
- [x] adaptive constrained: cancer −24% без потери lifespan; toxicity — самый опасный стресс

**Этап 5C — механистические драйверы старения и reversibility search** — реализован:

- [x] 8 драйверов старения, `biological_age` как взвешенная агрегация с полом `adult_age_setpoint`
- [x] 12 driver-targeted вмешательств с ценами, рисками и diminishing returns
- [x] лучший результат: combined maintenance — lifespan 70.8, bio slope 0.417 (всё ещё >> eps);
      robust search mini — лучший 72.2/65.2, `robust_bounded_degradation_v2` — нигде
- [x] доминирующие связывающие драйверы: `cellular_senescence` / `epigenetic_drift`

**Этап 6A — organ-backed emergent aging и cross-scale поиск** — реализован:

- [x] 8 reduced organ proxies + 4 системных ресурса + 5 coordination modes (opt-in, `none` = Stage 5C бит-в-бит)
- [x] лучший результат: combined organ-backed — lifespan 101.5 / healthspan 87.2; search best — 104.8
- [x] coordination не бьёт independent (scaling −0.25); repair — критичнейший ресурс; `robust_bounded_degradation_v3` — нигде

Полный план и детали — в `docs/ROADMAP.md`, `docs/TISSUE_MODEL.md`,
`docs/ORGAN_MODEL.md`, `docs/ORGANISM_MODEL.md`, `docs/AGING_MODEL.md`,
`docs/ORGAN_BACKED_ORGANISM_MODEL.md`.

## Как начать

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

Быстрый запуск минимального эксперимента:

```bash
python -c "import sys; sys.path.insert(0, 'src');
from longevity.experiment.config import ExperimentConfig;
from longevity.experiment.runner import run_experiment;
run_experiment(ExperimentConfig(experiment_id='demo', seed=42, population=1,
duration=168.0, model_version='0.1.0', data_version='0.0.1'),
out_path='experiments/output/demo.json')"
```

Жизненный цикл организма (Stage 5A):

```bash
$env:PYTHONPATH='src'; python -m longevity.experiment.organism_runner --config experiments/configs/organism_life_course_baseline.json --out experiments/output/organism_baseline.json
$env:PYTHONPATH='src'; python -m longevity.experiment.organism_policy_search --config experiments/configs/organism_policy_search_mini.json --out-prefix experiments/output/organism_policy_search_mini
```

Механистическое старение (Stage 5C):

```bash
$env:PYTHONPATH='src'; python -m longevity.experiment.organism_runner --config experiments/configs/organism_aging_combined_mechanistic.json --out experiments/output/organism_aging_combined_mechanistic.json
$env:PYTHONPATH='src'; python -m longevity.experiment.organism_policy_search --config experiments/configs/organism_aging_robust_search_mini.json --out-prefix experiments/output/organism_aging_robust_search_mini
```

Organ-backed организм (Stage 6A):

```bash
$env:PYTHONPATH='src'; python -m longevity.experiment.organism_runner --config experiments/configs/organism_organ_backed_combined.json --out experiments/output/organism_organ_backed_combined.json
$env:PYTHONPATH='src'; python -m longevity.experiment.organism_organ_backed --config experiments/configs/organism_organ_backed_coordination_compare.json --out-prefix experiments/output/organism_organ_backed_coordination_compare
```

<!--
Секции ниже появятся на следующих этапах.
- Installation & environment
- Usage example
- Contributor guide
-->

## Лицензия и статус

Проект находится на ранней исследовательской стадии. Перед использованием какого-либо
материала проконсультируйтесь с владельцем репозитория.