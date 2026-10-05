# ORGAN_BACKED_ORGANISM_MODEL.md — Organ-обусловленное старение (Stage 6A)

> Это НЕ модель человека. Порядковые скорости, абстрактные годы, reduced
> proxies вместо органов, нет анатомии и калибровки.
> `robust_bounded_degradation_v3 = true` — модельный флаг, а не
> доказательство бессмертия. Бессмертие — `hypothesis_not_proven`.

## 1. Зачем Stage 6A

Stage 5C разложил `biological_age` на драйверы, но robust bounded
degradation v2 не нашёл: доминируют `cellular_senescence` и
`epigenetic_drift`. При этом витальные системы организма оставались
плоскими абстракциями, а Stage 3/4 показали, что на тканевом и органном
уровнях важны регенеративный резерв, ECM, vascular/immune support,
fibrosis, cancer risk, конкуренция за ресурсы и recovery как отдельный
класс поддержания. Stage 6A проверяет cross-scale гипотезу:

```text
Меняется ли природа bounded degradation, если витальные системы частично
выводятся из органно-обусловленных состояний, а не являются плоскими абстракциями?
```

## 2. Reduced organ proxies (не полная симуляция)

Никакой клеточной симуляции внутри организма нет. Вместо этого — 8
компактных прокси (`src/longevity/model/organ_backed.py`), по одному на
витальную систему: `brain_cns_proxy`, `cardiovascular_proxy`,
`respiratory_proxy`, `hepatic_proxy`, `renal_proxy`, `immune_proxy`,
`metabolic_proxy`, `musculoskeletal_proxy`. Архитектура допускает меньшее
число через `mapped_vital_systems`, но v0 использует полный набор.

Каждый прокси: function/reserve/damage/senescence/fibrosis/cancer_risk/
ECM/vascular/immune_pressure/capacities/repair/recovery_pending/
turnover/replacement_tolerance/пороги/critical. У brain — обязательно
`informational_continuity` в [0, 1]: омоложение мозга ценой личности
моделью запрещено фиксировать как успех.

Включение: `organ_backed_model = reduced_organ_proxies` (дефолт `none`
численно идентичен Stage 5C; регрессия: 66.8/60.8 cascade бит-в-бит).

## 3. Маппинг на витальные системы

После каждого шага функция витальной системы смешивается с функцией
прокси 50/50; continuity мозга — аналогично. Это операциональная связь,
не биология: органы буферизуют системы, но их деградация тянет системы
вниз. Пример: `cardiovascular.function` следует за функцией прокси,
глобальным перфузионным allocation, damage и fibrosis.

## 4. Эмерджентные драйверы

Часть Stage 5C драйверов становится частично эмерджентной (веса
`emergent_weights`, дефолты в скобках):

- `cellular_senescence` (0.5) — средний senescence прокси;
- `chronic_inflammation` (0.5) — средний immune pressure;
- `cancer_prone` (0.3) — средний cancer risk;
- `stem_exhaustion` (0.3) — damage + истощение резервов;
- `mitochondrial_dysfunction` (0.2) — damage metabolic-группы;
- `proteostasis_loss` (0.2) — damage при низком repair;
- `dna_damage` (0.0), `epigenetic_drift` (0.0) — остаются
  феноменологическими, потому что у прокси нет явного представления
  генома/эпигенома; вводить его ради галочки было бы фикцией.

Смешивание: `damage = (1-w)*phenomenological + w*emergent`, границы и
floor соблюдаются.

## 5. Systemic resource layer

Четыре ресурса: `perfusion`, `immune`, `metabolic`, `repair` (бюджеты
дефолт 8.0). Каждый прокси генерирует demand (base + function + damage +
senescence + activity). Allocation = min(1, budget/demand); shortfall =
max(0, demand - budget). При allocation < 1: растёт damage, падает repair
и recovery, вмешивается coordination. Бюджеты тратятся органными ценами
вмешательств и бьются `resource_shock` (отдельный тип, вне Stage 5B
потока, чтобы legacy-сиды были бит-идентичны).

## 6. Organ-level interventions

Существующие типы получили органную маршрутизацию (аддитивные ключи
`target_organ_ids`, `organ_delta_*`, `organ_resource_cost`; без них
эффекты работают как раньше):

- `tissue_organ_maintenance`: +ECM/vascular, −fibrosis (цена repair);
- `recovery_support`: +recovery_pending (цены repair/metabolic);
- `cancer_surveillance`: −organ cancer_risk (цена immune);
- `senolytic_clearance`: −organ senescence (цена immune);
- `neural_protective_maintenance`: +continuity brain-прокси.

Политики несут `target_organ_ids`; биомаркеры расширены:
`organ:<proxy>:<field>`, `resource:<name>:allocation`,
`min_organ_function`, `min_resource_allocation`.

## 7. Coordination на уровне организма

Пять режимов (`independent_organ_policies`, `global_resource_aware_scaling`,
`vital_organ_priority`, `lookahead_organ_resource`,
`deferral_organ_resource`): масштабирование планов при дефиците, приоритет
критичным, ранжирование по relief-per-cost, откладывание вместо отмены
(FIFO-очередь с лимитом retries, персистентна в checkpoint). Вывод не
форсируется: если independent снова лучший — это валидный результат.

## 8. Причины отказа и метрики

Новые причины: `organ_failure`, `multi_organ_cascade`,
`perfusion_failure`, `immune_surveillance_failure`,
`metabolic_support_failure`, `repair_budget_exhaustion`,
`global_resource_exhaustion`. Метрики (`organ_backed_metrics.py`):
функции/склоны/отказы по органам, allocation/shortfall/exhaustion по
ресурсам, coordination-статистика, `dominant_binding_level/organ/driver/
resource`, `candidate_robust_bounded_degradation_v3_found` (только флаг).

## 9. Robust bounded degradation v3

Строже v2: условия v2 плюс функция критичных прокси выше порога с
запасом, allocation выше `min_allocation`, нет истощения резервов и
ресурсов, нет terminal_decline, ни один орган/ресурс без runaway trend.
Политика проходит при success rate ≥ 0.8 и worst-case дисциплине.
Операциональный критерий, не доказательство бессмертия.

## 10. Результаты v0 (в рамках модели)

| Политика | lifespan | healthspan | binding |
|---|---|---|---|
| legacy none (= Stage 5C) | 66.8 | 60.8 | bio slope |
| organ-backed baseline | 82.8 | 71.8 | bio slope |
| organ maintenance | 88.0 | 76.0 | bio slope |
| combined organ-backed | 101.5 | 87.2 | bio slope |
| adaptive cross-scale | 97.5 | 82.2 | bio slope |
| neural preserving | 87.0 | 75.8 | bio slope (continuity 0.84) |
| search best (12×3) | 104.8 | — | v3 false везде |

- Coordination (4 modes × 3 seeds): independent = deferral = lookahead
  (101.5), scaling −0.25. Урок 4D подтверждён уровнем выше:
  non-interference остаётся оптимальным; масштабирование вредит.
- Resource sweep (27×3): repair — критичнейший ресурс (бюджет 4 →
  ~76–79 независимо от остальных; ≥8 → 101–110). Transition budgets
  найдены для всех трёх осей.
- Stress (3×7×3): ranking стабилен (combined 96.1 > adaptive 94.3 >
  baseline 80.6); v3 false везде, включая `global_resource_shock`.
- HYP-0: `hypothesis_not_proven`;
  `candidate_robust_bounded_degradation_v3_found = false`.

## 11. Ограничения

Абстрактный организм; reduced proxies, а не органы; порядковые
параметры; операциональные пороги; n ≤ 3 (описательно); нет
биологической валидации. Отсутствие v3 — валидный, более сильный
внутримодельный результат: даже эмерджентные органные ограничения не
открыли bounded degradation. HYP-0 остаётся `hypothesis_not_proven`.

## 12. Stage 6B — Cross-organ network (кратко)

Ответ на вопрос Stage 6A — см. `docs/ORGAN_NETWORK_MODEL.md`. Рёбра,
feedback, hard limits и network age утяжеляют baseline (82.8 → 67.0),
но binding остаётся `biological_age_slope`; координация 6×3 не бьёт
independent; v4 — нигде. HYP-0 остаётся `hypothesis_not_proven`.
