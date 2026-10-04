# TISSUE_MODEL.md — Модель одной абстрактной ткани с политикой замены (Stage 3A)

> Это НЕ модель организма. Локальное омоложение ткани НЕ равно rejuvenation
> организма (см. `docs/LONGEVITY.md`). Бессмертие остаётся предельной
> исследовательской гипотезой (`docs/IMMORTALITY.md`), а не выводом этого этапа.

## 1. Что такое TissueState

`src/longevity/model/tissue.py`, класс `TissueState` — компартментное состояние
**одной абстрактной ткани**. Пулы — `float` (ожидаемые численности, не
индивидуальные клетки):

| Поле | Смысл | Диапазон |
|---|---|---|
| `time` | модельное время (абстрактные шаги, НЕ часы) | `>= 0` |
| `stem_cells` | стволовой пул (источник регенерации, истощаем) | `>= 0` |
| `functional_cells` | функциональные клетки ткани | `>= 0` |
| `damaged_cells` | повреждённые (ремонтопригодные или кандидаты в сенесценцию) | `>= 0` |
| `senescent_cells` | сенесцентные (не делятся, SASP-нагрузка) | `>= 0` |
| `dead_cells` | кумулятивный пул выбывших (апоптоз/клиренс/элиминация при замене) | `>= 0` |
| `ecm_quality` | качество внеклеточного матрикса / архитектуры | `[0, 1]` |
| `vascular_quality` | качество васкуляризации ниши | `[0, 1]` |
| `immune_pressure` | воспалительная/иммунная нагрузка ниши | `[0, 1]` |
| `cancer_risk` | индекс онкологического риска (не вероятность) | `[0, 1]` |
| `fibrosis_index` | индекс фиброза | `[0, 1]` |

Один шаг модели (`TissueModel.step`): сначала естественная динамика
(damage → senescence/recovery/death, клиренс сенесцентных, дифференцировка
`stem → functional` через `regeneration_capacity`, динамика ниши/ECM/сосудов/
иммунитета/фиброза/риска), затем не более одного события замены по плану
политики. Инварианты проверяются после каждого шага
(`assert_tissue_invariants`).

## 2. Политика замены (планирование ≠ исполнение)

`src/longevity/model/policy.py`:

- `ReplacementPolicy`: `name / enabled / target (none|damaged|senescent) /
  source (none|stem_pool|external_bank) / frequency / max_replacement_fraction /
  preserve_architecture / immune_compatibility / cancer_control`.
- `ReplacementPlan`: `target_count / source_count` + четыре абсолютные
  ожидаемые цены (`expected_architecture_cost / expected_immune_cost /
  expected_cancer_risk_delta / expected_fibrosis_delta`).
- `policy.plan(state, params, step)` — **чистая функция**: не мутирует
  состояние (покрыто тестом). Исполнение с капами
  («не больше, чем есть»; замена строго один-к-одному; урезанное событие
  линейно масштабирует цену) — `TissueModel.apply_replacement_plan`.

Детерминизм — как в остальном проекте: никакого глобального `random`, только
инжектируемый `Rng` (`longevity.sim.rng`); `stochastic_jitter = 0` по умолчанию
(полностью детерминированная динамика); checkpoint (`to_checkpoint_dict` /
`from_checkpoint`) сериализует RNG через `state_to_json`/`state_from_json`,
restore после JSON-roundtrip идентичен непрерывному запуску (тест).

## 3. Допущения Stage 3A (T-1…T-7)

| # | Допущение |
|---|---|
| T-1 | Ткань — хорошо перемешанные компартменты; пространства, градиентов и типов клеток нет |
| T-2 | Сенесцентные клетки усиливают повреждение функциональных (SASP) мультипликативно |
| T-3 | Регенерация — произведение факторов ниши (стволовые с насыщением × сосуды × ECM × (1 − воспаление)): каждый фактор необходим, ни один не достаточен |
| T-4 | Воспаление одновременно подавляет регенерацию и ухудшает клиренс сенесцентных |
| T-5 | Любая пролиферация (дифференцировка + замена) растит `cancer_risk`; контроль (`cancer_control`, `cancer_repair_rate`) его гасит |
| T-6 | Внешний банк (`external_bank`) безлимитен, но несёт удвоенную иммунную цену (аллогенность) |
| T-7 | Все скорости — порядковые заглушки модели (см. комментарии в `tissue.py`), а не измерения; шаг времени абстрактный |

## 4. Эксперименты

`src/longevity/experiment/tissue_runner.py` (`run_tissue_experiment`,
`load_tissue_config`, `TissueExperimentConfig`) — конфиг → начальный
`TissueState` → прогон → траектория + метрики → JSON в `experiments/output/`.
Три конфига (один seed = 42, одни параметры — различается только политика):

- `experiments/configs/tissue_baseline.json` — замена выключена.
- `experiments/configs/tissue_senescent_replacement.json` — умеренная очистка
  сенесцентных (20% каждые 5 шагов, высокие контроли).
- `experiments/configs/tissue_aggressive_replacement.json` — агрессивная очистка
  (80% каждый шаг, слабые контроли).

Метрики (`src/longevity/analysis/tissue_metrics.py`): финальные пулы,
`area_under_senescent_curve` / `area_under_damage_curve` (интегралы бремени),
`max_cancer_risk`, финальные `fibrosis/ecm/vascular/immune`,
`rejuvenation_delta = final_functional − initial_functional` (**локальный прокси
этой ткани**), `replacement_events` / `total_replaced_cells`. Сравнение
«вмешательство минус baseline при том же seed» — `compare_against_baseline`
(`functional_gain`, `senescent_reduction`).

Референсные результаты (seed 42, 200 шагов):

| Метрика | baseline | moderate | aggressive |
|---|---|---|---|
| final_functional | 7762 | 7942 | 5016 |
| final_senescent | 500 | 219 | 372 |
| max_cancer_risk | 0.080 | 0.085 | 0.097 |
| final_fibrosis | 0.076 | 0.056 | 0.115 |
| final_ecm | 0.886 | 0.845 | 0.798 |
| final_immune | 0.227 | 0.191 | 0.246 |
| total_replaced | 0 | 1969 | 1356 |

Чтение (в рамках модели, не биологический факт): умеренная замена устойчива —
сенесцентное бремя halved при сохранной функции и малой цене архитектуры;
агрессия истощает стволовой пул в ноль (~100 шагов), замена останавливается,
сенесцентные отрастают обратно, а цена (рак/фиброз/иммунитет/ECM/функция)
проявляется везде. Это наблюдение о пределах replacement-based maintenance,
а не рецепт.

## 5. Что это НЕ доказывает (ограничения)

- Ничего про организм: нет органов, системных связей, иммунитета как системы,
  мозга/идентичности (см. `docs/LIMITATIONS.md`).
- `rejuvenation_delta > 0` — это «ткань кончается с большим числом
  функциональных клеток, чем начала», а не омоложение организма.
- Параметры не калиброваны против данных; выводы валидны только относительно
  самой модели.
- HYP-0 (`docs/IMMORTALITY.md`) не затрагивается: горизонт конечный (200 шагов),
  стабилизация не показана, мульти-seed проверка не проводилась.

## 6. Stage 3B — карта устойчивости замены (sweep fraction × frequency)

> Exploratory analysis внутри абстрактной тканевой модели. Не доказательство
> бессмертия, не модель организма, не биологический вывод.

### 6.1. Цель и сетка

Конфиг `experiments/configs/tissue_sweep_v0.json`: сетка
`max_replacement_fraction × frequency` (7 × 5 = 35 точек),
seeds `[42, 7, 99]` (3 на точку), горизонт 200 шагов, шаблон политики
`senescent / stem_pool` с контролями 0.9 (изолируется именно интенсивность),
`stochastic_jitter = 0.05` (сиды зондируют чувствительность; один и тот же сид
во всех рукавах изолирует политику по EXPERIMENTS.md §6), отдельный рукав
baseline (политика выключена) для `*_vs_baseline`-дельт при том же сиде.

Отклонение от примерной сетки в постановке: `frequency` — целый период в
шагах (`int >= 1`, семантика Stage 3A: событие на шагах, кратных периоду).
Частота `0.0` невалидна (нулевой период непланируем); «выключено»
представлено долей `0.0` (пустые планы) плюс отдельным disabled-baseline.
Сетка v0: доли `[0.0, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2]`,
периоды `[1, 5, 10, 25, 50]`.

Код: чистый анализ — `src/longevity/analysis/tissue_sweep.py` (слой ANALYSIS);
конфиг/прогон через существующий `run_tissue_experiment`/запись артефактов/CLI —
`src/longevity/experiment/tissue_sweep.py` (слой EXPERIMENT). Динамика
`TissueModel` не дублируется и не менялась. Запуск:

```bash
$env:PYTHONPATH='src'; python -m longevity.experiment.tissue_sweep \
  --config experiments/configs/tissue_sweep_v0.json \
  --out-prefix experiments/output/tissue_sweep_v0
```

Артефакты: `tissue_sweep_v0_long.csv` (строка на seed + точку, baseline-рукав
включён первым), `tissue_sweep_v0_summary.csv` (строка на точку),
`tissue_sweep_v0_summary.json` (метаданные, `config_hash` sha256 канонического
конфига, сетка, пороги, агрегаты, счётчики режимов, граница, pareto),
`tissue_sweep_v0_boundary.json`.

### 6.2. Viability и время

Ткань viable в момент t, если выполнены все operational-констрейнты
(пороги v0 — аналитический выбор, не биология):
functional ≥ 75% начального; senescent/living ≤ 10%; stem ≥ 50% начального;
cancer ≤ 0.15; fibrosis ≤ 0.3; ECM ≥ 0.7; vascular ≥ 0.7; immune ≤ 0.4.

- `time_to_first_viability_failure` — первый момент нарушения, иначе горизонт.
- `healthspan_tissue` — суммарное viable-время (отличается от предыдущего,
  только если viability теряется и восстанавливается).
- `survival_time` — lifespan-прокси свипа, равен моменту первого отказа.

### 6.3. Режимы (детерминированная классификация, приоритет сверху вниз)

1. `baseline_like` — замена фактически выключена (рукав-референс).
2. `collapsing` — ранняя потеря viability (ttf < 50% горизонта), или
   терминальная потеря functional, или терминальный сенесцентный бремен
   вне контроля.
3. `stem_depleting` — терминальный stem ниже порога (ресурс невосстановим).
4. `unstable_high_replacement` — ≥2 риск/нишевых нарушений
   (пик cancer, fibrosis, immune, ECM, vascular).
5. `risky_but_functional` — ровно 1 риск/нишевое нарушение, либо транзиентная
   потеря viability с чистым терминальным состоянием.
6. `sustainable` — viable весь горизонт (ttf ≥ 90%), чистое терминальное
   состояние.

### 6.4. Агрегация, граница, pareto

По точке: mean/std/min/max/median/p25/p75/count на метрику; `std` —
популяционное (делит на n), это описательный разброс при n=3, **не**
статистическая значимость. `sustainable_rate` (доля sustainable),
`failure_rate` (доля collapsing), счётчики всех шести режимов (сумма = числу
сидов), средний/медианный ttf. Граница устойчивости на частоту: максимальная
доля с `sustainable_rate ≥ 2/3` и средним ttf ≥ 80% горизонта, иначе `null`.
Pareto: недоминируемые точки (польза — снижение сенесцентных vs baseline;
цены — пик cancer, фиброз, истощение stem vs baseline).

### 6.5. Результаты v0 (внутри модели)

Карта режимов, доминирующий лейбл (счёт/3):

| freq \ frac | 0.0 | 0.005 | 0.01 | 0.02 | 0.05 | 0.1 | 0.2 |
|---|---|---|---|---|---|---|---|
| 1 | B | S | S | S | S | C | C |
| 5 | B | S | S | S | S | S | S |
| 10 | B | S | S | S | S | S | S |
| 25 | B | S | S | S | S | S | S |
| 50 | B | S | S | S | S | S | S |

B = baseline_like (доля 0.0), S = sustainable 3/3, C = collapsing 3/3.
Итого по сетке: 84 sustainable, 6 collapsing, 15 baseline_like;
`risky_but_functional`, `unstable_high_replacement`, терминальный
`stem_depleting` в сетке v0 **не наблюдаются** (переход резкий; машинерия
лейблов покрыта синтетическими тестами).

Граница: `{1: 0.05, 5: 0.2*, 10: 0.2*, 25: 0.2*, 50: 0.2*}`
(`*` — край сетки, граница открыта: при периодах ≥5 даже 0.2/событие
поглощается). Немонотонности нет: чем чаще замена, тем меньше допустимая
доля — монотонное сужение к периоду 1.

Baseline (среднее 3 сидов): functional 7765, senescent 495, stem 586
(рост!), cancer-max 0.08, fibrosis 0.08, ECM 0.89, immune 0.23, ttf 200.

Trade-off (средние; `senred` = снижение сенесцентных vs baseline,
`stemdepl` = истощение stem vs baseline):

| точка | режим | ttf | func | sen | stem | cancermax | fibr | ECM | senred | stemdepl |
|---|---|---|---|---|---|---|---|---|---|---|
| q=1, f=0.05 | S | 200 | 7881 | 221 | 390 | 0.084 | 0.054 | 0.843 | +274 | +196 |
| q=1, f=0.1 | C | ~85 | 6199 | 397 | 0 | 0.070 | 0.052 | 0.858 | +98 | +586 |
| q=1, f=0.2 | C | ~50 | 5173 | 371 | 0 | 0.055 | 0.064 | 0.872 | +124 | +586 |
| q=5, f=0.2 | S | 200 | 7940 | 218 | 388 | 0.085 | 0.056 | 0.845 | +278 | +198 |
| q=50, f=0.2 | S | 200 | 7897 | 386 | 488 | 0.083 | 0.073 | 0.877 | +109 | +98 |

Ключевое наблюдение: угол коллапса (q=1, f≥0.1) рвётся **первым по
`stem_depleted`** (t≈47–52 при f=0.2; t≈83–88 при f=0.1) — при почти нулевой
сенесцентной нагрузке (sen≈70, доля <1%) и целой functional. Ткань «выглядит
молодой» по сенесценции, но сжигает регенеративный резерв; functional падает
позже. Пик cancer в углу коллапса даже **ниже** baseline (0.055 vs 0.08):
пролиферация останавливается вместе с тканью. Цена агрессии здесь — не рак,
а истощение stem и функциональный коллапс.

Pareto-фронт совпал почти со всей сеткой (польза и цены растут вместе
постепенно, резкого «колена» нет); точка «ничего не делать» на фронте по
построению (нулевая цена). Это отсутствие результата, а не граница.

### 6.6. Interpretation rules

- Улучшение senescence reduction без падения stem и без роста рисков —
  candidate sustainable regime (плато q≥5 в v0).
- Быстрое снижение senescence с истощением stem — depleting/collapsing regime
  (угол q=1, f≥0.1 в v0).
- Снижение senescence с ростом cancer/fibrosis/immune — risky/unstable regime
  (в v0 не наблюдался при контролях 0.9 — факт о модели, не пропуск анализа).
- Ранняя потеря viability — collapsing regime независимо от «молодого» вида
  отдельных метрик.
- Отсутствие чистой границы (открытый край 0.2 при q≥5) — не ошибка модели,
  а указание расширить сетку, а не вывод об устойчивости.

### 6.7. Ограничения v0

Порядковые скорости; абстрактный шаг времени; одна ткань; нет системных
связей; пороги viability — модельные; 3 сида — описательно, не значимость;
`jitter = 0.05` мал — межсидовый разброс почти нулевой (baseline ttf 200/200/200);
граница при q≥5 открыта (нужны доли >0.2); промежуточные режимы risky/unstable
не посещены (нужны слабые контроли или мельче сетка). `rejuvenation_delta` и
все `*_vs_baseline` — локальные тканевые прокси, не rejuvenation организма;
HYP-0 (`docs/IMMORTALITY.md`) не затрагивается: горизонт конечен, t→∞ не
исследуется.

## 7. Stage 3C — закрытие границы и контрольно-чувствительный свип

> Exploratory analysis внутри той же абстрактной тканевой модели. Не
> доказательство бессмертия, не модель организма, не биологический вывод.

### 7.1. Цель и сетка

Конфиг `experiments/configs/tissue_sweep_v1_boundary_closure.json`: сетка v0
расширена за открытый край — доли
`[0.0, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5]`
(12 × 5 = 60 точек на профиль), те же seeds `[42, 7, 99]`, горизонт 200 шагов,
`stochastic_jitter = 0.05` — v1 сопоставима с v0 точка-в-точку до доли 0.2.
Та же сетка прогоняется под двумя профилями контроля
(`control_profiles` в конфиге, `longevity.experiment.tissue_sweep`):

- `strong_controls` — `preserve_architecture / immune_compatibility /
  cancer_control = 0.9` (дефолты Stage 3A/3B);
- `weak_controls` — `0.4 / 0.4 / 0.4` (уровень агрессивного конфига Stage 3A).

Это модельные operational settings замены, не биологические константы.
Отдельный конфиг `experiments/configs/tissue_sweep_v1_weak_controls.json` —
та же сетка только под слабым профилем (standalone-проверка чувствительности).
Запуск:

```bash
$env:PYTHONPATH='src'; python -m longevity.experiment.tissue_sweep \
  --config experiments/configs/tissue_sweep_v1_boundary_closure.json \
  --out-prefix experiments/output/tissue_sweep_v1
```

Артефакты (префикс `experiments/output/tissue_sweep_v1`): legacy-четвёрка
(`_long.csv` с колонками `control_profile / primary_failure_cause /
failure_cause_sequence / first_*_time`, `_summary.csv` с колонкой
`control_profile`, `_summary.json`, `_boundary.json`) плюс
`_boundary_closure.json` (граница по каждой паре частота×профиль),
`_regime_coverage.{json,csv}`, `_failure_causes.{json,csv}`,
`_control_comparison.json`. Динамика `TissueModel` не менялась; причинность
выводится из записанной траектории чистыми функциями
(`longevity.analysis.tissue_sweep.failure_causality` и др.).

### 7.2. Как считается закрытие границы

Для каждой пары (частота, профиль) доли сортируются по возрастанию;
`sustainable` точки — то же правило Stage 3B (`sustainable_rate ≥ 2/3` и
средний ttf ≥ 80% горизонта):

- `max_sustainable_fraction` — максимальная устойчивая доля (`null`, если
  устойчивых нет);
- `first_unsustainable_fraction` — минимальная неустойчивая доля строго выше
  неё (`null`, если выше всё устойчиво);
- `boundary_open = true` — максимальная доля сетки всё ещё устойчива
  (переход за краем сетки). Это указание расширить сетку, а не доказательство
  неограниченной устойчивости.

### 7.3. Причины отказа

Для каждой траектории фиксируется первое нарушение каждого
viability-констрейнта; нарушение отображается на причину
(`stem_depleted → stem_depletion`, `functional_below_threshold/tissue_empty →
functional_collapse`, `senescent_fraction_exceeded → senescence_blowout`,
`cancer_risk_exceeded → cancer_risk`, `fibrosis_exceeded → fibrosis`,
`ecm_degraded → ecm_failure`, `vascular_degraded → vascular_failure`,
`immune_pressure_exceeded → immune_failure`). `primary_failure_cause` —
самая ранняя причина (`multiple_simultaneous`, если в earliest-момент их ≥2;
`none`, если нарушений не было); `failure_cause_sequence` — все причины в
порядке (время, канонический порядок). Порядок детерминирован и покрыт
тестами.

### 7.4. Результаты v1 (внутри модели)

Граница по профилям (`max_sustainable`, `*` = край сетки, открыта):

| freq | strong | weak |
|---|---|---|
| 1 | 0.05 (след. 0.1) | 0.02 (след. 0.05) |
| 5 | 0.30 (след. 0.35) | 0.10 (след. 0.2) |
| 10 | 0.50* | 0.10 (след. 0.2) |
| 25 | 0.50* | 0.35 (след. 0.4) |
| 50 | 0.50* | 0.50* |

Закрыты: strong при q=1/5, weak при q=1/5/10/25. Открыты: strong при q≥10
и weak при q=50 на доле 0.5 — даже половинная замена редкими событиями
поглощается моделью. Ослабление контроля сдвигает границу вниз на каждом
периоде (q=1: 0.05→0.02; q=5: 0.3→0.1; q=10: открыта→0.1).

Покрытие режимов (360 прогонов: 180 strong + 180 weak): sustainable 234,
collapsing 66, baseline_like 30, risky_but_functional 27 (все — weak),
stem_depleting 3 (strong, q=5/f=0.35 — промежуточная точка между sustainable
0.3 и collapsing 0.4: терминальный stem ~170 при целой functional ~7430 и
низкой сенесценции ~126), unstable_high_replacement —
`regime_not_visited_in_current_grid` (двойных риск/нишевых нарушений нет даже
под слабым контролем — факт о модели, не пропуск анализа).

Причинность: strong рвётся первым по `stem_depletion` (30 первичных; типичная
цепочка `stem_depletion;functional_collapse`); weak — первым по `ecm_failure`
(63 первичных; цепочки `ecm_failure`, `ecm_failure;stem_depletion;
functional_collapse`). `functional_collapse` встречается только вторичным
(37 раз), первичным — никогда: функция падает следом за резервом или нишей.
`senescence_blowout` как первичное — 0: замена давит сенесценцию даже в
рушащихся руках. Паттерн Stage 3B подтверждён и уточнён: рушащиеся strong-руки
(q=1, f≥0.1) имеют сенесцентную долю ~5% при `stem = 0` — ткань «выглядит
молодой» по сенесценции, но регенеративный резерв сожжён; под weak-контролем
аналогичная «молодая» картина бывает при целых stem (~530), но с разрушенной
ECM (~0.5).

Компромиссы (средние по 60 точкам профиля, n=3 описательно): weak даёт чуть
большее снижение сенесцентных (+138 vs +131), но ценой роста пикового рака
(0.106 vs 0.079) и фиброза (0.108 vs 0.068) и меньшего healthspan (162 vs 177).
Формулировка строго внутримодельная: ослабление контрольных параметров
сдвигает границу устойчивости вниз и меняет профиль отказа со stem-первого
на ECM-первый.

### 7.5. Ограничения v1

Одна абстрактная ткань; порядковые скорости; абстрактный шаг; операциональные
пороги; n=3 — описательный разброс, не значимость; `unstable` не посещён;
три края сетки открыты (нужны доли >0.5 или другая ось); `rejuvenation_delta`
и `*_vs_baseline` — локальные тканевые прокси; HYP-0 не затрагивается.
