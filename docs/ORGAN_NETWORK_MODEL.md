# ORGAN_NETWORK_MODEL.md — Cross-organ network, feedback и hard limits (Stage 6B)

> Это НЕ модель человека. Порядковые скорости, абстрактные годы, reduced
> network поверх reduced proxies, нет анатомии и калибровки.
> `robust_bounded_degradation_v4 = true` — модельный флаг, а не
> доказательство бессмертия. Бессмертие — `hypothesis_not_proven`.

## 1. Зачем Stage 6B

Stage 6A показал: organ proxies буферизуют системы (82.8/71.8 против
66.8/60.8), repair budget критичен, но `biological_age_slope` остался
binding во всех ячейках, а координация не превзошла independent
execution. Проблема — `biological_age` оставался агрегированным трендом.
Stage 6B проверяет:

```text
Меняется ли природа bounded degradation, если старение — эмерджентное
свойство сети органов, обратных связей, энергии, информации, мутаций
и необратимых повреждений?
```

## 2. Reduced organ network (не биология)

Граф из 12 рёбер по умолчанию (`src/longevity/model/organ_network.py`),
типы: vascular/immune/metabolic зависимости, endocrine/neural сигналы,
inflammatory/fibrosis spread, cancer seeding, repair flow. Каждое ребро:
source/target/type/weight/delay/gain/failure_threshold/
protection_sensitivity. Веса малые (0.01–0.04), задержки 1–2 шага.
Нулевые веса не дают эффектов. Это операциональная абстракция.

Включение: `organ_network_model = reduced_network_feedback` (дефолт
`none` численно идентичен Stage 6A; регрессии: legacy none = Stage 5C
бит-в-бит, organ-backed + network none = Stage 6A бит-в-бит).

## 3. Feedback loops

Семь контуров, все детерминированные, конфигурируемые, отключаемые:
inflammation_damage, immune_exhaustion, metabolic_repair,
vascular_support, neural_identity, cancer_surveillance,
fibrosis_stiffness. Gain считается из текущего состояния, применяется
как дополнительный damage/inflammation/fibrosis/cancer дрейф.
Runaway = gain > `max_feedback_gain` (дефолт 0.8). Это модельные loops,
не калиброванная биология.

## 4. Hard limits

- energy_budget (дефолт 30.0): дрейф + цена каждого вмешательства;
  при <20% repair capacities душат;
- information_preservation: continuity нельзя бесплатно восстановить;
  reprogramming дополнительно −0.005;
- mutation_load_ceiling (дефолт 1.0): telomere/stem/reprogramming/
  regenerative наращивают load; surveillance лишь −0.002 (не компенсация);
- irreversible_damage: ниже порога функции damage получает floor;
- niche_integrity_limit: stem/regenerative наращивают disorder;
- intervention_toxicity_budget: кумулятивная токсичность с медленным decay.
Все opt-in, конфигурируемы через `organ_network_hard_limits`.

## 5. Biological age network

`biological_age_network = adult_setpoint + contribution(drivers,
organ deficit, resource shortfall, feedback, mutation, information loss,
fibrosis, cancer, cascade)`, floor на adult setpoint по умолчанию.
`allow_sub_adult_network_age=true` — exploratory non-physiological mode,
помечается в конфиге. Legacy `biological_age` сохранён.

## 6. Coordination

Старые 5 режимов сохранены. Новые 7: `independent_network`,
`network_bottleneck_priority`, `cascade_guard`,
`information_preservation_priority`, `mutation_load_guard`,
`lookahead_network`, `deferral_network`. Вывод не форсируется.

## 7. Причины отказа и метрики

Новые причины: `network_cascade_failure`, `energy_exhaustion`,
`information_loss`, `mutation_load_failure`, `feedback_runaway`,
`bottleneck_edge_failure`, `critical_organ_cascade`,
`hard_limit_violation`, `unknown_network_collapse` (аддитивно, порядок
старых сохранён). Метрики (`organ_network_metrics.py`): edge
utilization/failure risk, dominant edge/loop, cascade, feedback gains,
energy/mutation/toxicity/niche, network age slope, v4, binding v3
(level/organ/driver/resource/edge/loop/hard limit).

## 8. Robust bounded degradation v4

Условия v3 плюс: network age slope, cascade, mutation, feedback,
energy, toxicity, нет runaway/failed edges/hard-limit violations.
Политика проходит при success rate ≥ 0.8 и worst-case дисциплине.
Операциональный критерий, не доказательство бессмертия.

## 9. Результаты v0 (в рамках модели)

| Политика | lifespan | healthspan | binding |
|---|---|---|---|
| legacy none (= Stage 5C) | 66.8 | 60.8 | bio slope |
| network baseline | 67.0 | 58.2 | bio slope |
| network maintenance | 73.0 | 65.0 | bio slope |
| network combined | 76.5 | 68.8 | bio slope |
| network adaptive | 76.8 | 70.2 | bio slope |
| neural preserving | 76.5 | 68.8 | bio slope |
| search best (12×3) | 75.2 | 67.5 | v4 false везде |

- Сеть утяжеляет baseline 6A (82.8 → 67.0): рёбра и feedback — реальная
  нагрузка, dominant edge `cardio_vascular_to_brain`, dominant loop
  `inflammation_damage_loop`/`metabolic_repair_loop`.
- Coordination 6×3: все режимы 76.5 — non-interference подтверждён и на
  сетевом уровне.
- Resource sweep 27×3: repair снова критичен (4 → ~55; ≥8 → ~77.8);
  energy 15 vs 45 не меняет исхода при тех же repair (transition только
  по repair/perfusion).
- Hard-limit sweep 27×3: lifespan плоский 76.5, v4 false везде — лимиты
  пока не binding жёстко, binding остаётся bio slope.
- Stress 3×5×3: ranking стабилен, robust bounded false везде.
- HYP-0: `hypothesis_not_proven`;
  `candidate_robust_bounded_degradation_v4_found = false`.

## 10. Ограничения

Абстрактный organ-network организм; reduced proxies и рёбра;
порядковые параметры; операциональные пороги; n ≤ 3; нет биологической
валидации. Отсутствие v4 — валидный внутримодельный результат.
HYP-0 остаётся `hypothesis_not_proven`.

## 11. Stage 6C — Reversibility ceiling (кратко)

Ответ на вопрос Stage 6B — см. `docs/REVERSIBILITY_MODEL.md`. Split
reversible/irreversible, conversion, repair ceiling, information debt,
mutation fixation, niche disorder и entropy показывают: reversible
slope удержим, irreversible accumulation — нет; conversion — главный
механизм; v5 — нигде. HYP-0 остаётся `hypothesis_not_proven`.
