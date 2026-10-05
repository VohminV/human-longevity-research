# HYP-0: candidate immortality policy — статус проверки

> Статус: **hypothesis_not_proven**.
> Формулировка критерия: `docs/IMMORTALITY.md` §6.
> Модель: абстрактный организм Stage 5A/5B (`docs/ORGANISM_MODEL.md`).

## Гипотеза

Существует политика вмешательств P, при которой после зрелости все
critical-системы остаются выше порогов отказа, biological age и global
damage не имеют устойчивого положительного тренда, а рак/воспаление/
фиброз/потеря нейронной непрерывности остаются ограниченными —
устойчиво к множеству seed, параметрическому шуму, стрессовым сценариям
и длинному горизонту.

## Текущий результат (Stage 5B)

Кандидат **не найден**:

- лучший fixed-schedule результат: adaptive threshold, lifespan 117.8 /
  healthspan 100.2 (ценой cancer ×3.3);
- лучший поисковой результат: repair q3 + senolytic q3, 96.2 / 84.8;
- `bounded_degradation_indicator`: 0/27 (mini search), 0/27 (long horizon);
- `robust_bounded_degradation_indicator`: false во всех 70+ ячейках
  multi-seed/stress-оценки;
- связывающее ограничение везде одно: `biological_age_slope` —
  положительный наклон биологического возраста после зрелости не
  останавливается ни одной проверенной политикой.

## Что это означает

Не опровержение гипотезы в реальности. Это граница текущей абстрактной
модели: при заданных механизмах деградации и классах вмешательств
bounded degradation недостижима. Следующие направления проверки:
стохастическая устойчивость найденных кандидатов, более сильные
recovery-механизмы, подключение тканево-органных модулей Stage 3/4 как
подсистем вместо placeholders.

## Stage 5C result (2026-10-04)

Механистический слой добавлен, candidate robust bounded degradation v2
**не найден**:

- legacy `none` = Stage 5B бит-в-бит (68.0/61.8 cascade);
- mechanistic baseline 66.8/60.8, dominant `cellular_senescence`;
- лучший фиксированный — combined 70.8/64.0, bio slope 0.417 >> eps,
  dominant `epigenetic_drift`, cancer 0.68;
- лучший поисковой — dna intensity 1.5, 72.2/65.2, v2 false везде;
- binding sweep 27×3: 18 — `epigenetic_drift`, 9 — `cellular_senescence`;
- stress 3×6×3: ranking стабилен, toxicity бьёт сильнее, v2 false везде;
- `candidate_robust_bounded_degradation_v2_found = false`;
- dominant binding drivers: `cellular_senescence` / `epigenetic_drift`.

Статус остаётся `hypothesis_not_proven`. Ограничения: абстрактный
организм, порядковые скорости, операциональные пороги, n ≤ 3,
некалиброванные параметры драйверов, нет биологической валидации.

## Stage 6A result

Organ-backed слой добавлен, candidate robust bounded degradation v3
**не найден**:

- legacy `none` = Stage 5C бит-в-бит (66.8/60.8 cascade);
- organ-backed baseline 82.8/71.8 — прокси буферизуют системы, но slope
  остаётся положительным;
- лучший фиксированный — combined 101.5/87.2; adaptive 97.5/82.2;
  neural preserving держит continuity 0.84;
- лучший поисковой — 104.8, v3 false везде, pareto 8;
- coordination 4×3: independent = deferral = lookahead, scaling −0.25;
- resource sweep 27×3: repair — критичнейший ресурс;
- stress 3×7×3: ranking стабилен, v3 false везде;
- `candidate_robust_bounded_degradation_v3_found = false`;
- dominant binding level: `biological_age` во всех ячейках.

Статус остаётся `hypothesis_not_proven`. Ограничения: абстрактный
organ-backed организм, reduced proxies, порядковые параметры,
операциональные пороги, n ≤ 3, нет биологической валидации.

## Stage 6B result

Organ-network слой добавлен, candidate robust bounded degradation v4
**не найден**:

- legacy `none` = Stage 6A бит-в-бит (82.8/71.8 при organ-backed baseline;
  66.8/60.8 при полном legacy);
- network baseline 67.0/58.2 — рёбра и feedback утяжеляют систему,
  dominant edge `cardio_vascular_to_brain`, dominant loop
  `inflammation_damage_loop`;
- лучший фиксированный — adaptive 76.8/70.2; combined 76.5/68.8;
  maintenance 73.0/65.0;
- лучший поисковой — 75.2/67.5, v4 false везде, pareto из 12 комбо;
- coordination 6×3: все режимы 76.5, gain 0.0 — non-interference
  подтверждён на сетевом уровне;
- resource sweep 27×3: repair снова критичен (4 → ~55; ≥8 → ~77.8);
  energy сам по себе исхода не меняет;
- hard-limit sweep 27×3: lifespan плоский 76.5, v4 false везде;
- stress 3×5×3: ranking стабилен, v4 false везде;
- `candidate_robust_bounded_degradation_v4_found = false`;
- dominant binding level: `biological_age` во всех ячейках
  (network slope тоже положителен: ~0.38 в baseline).

Статус остаётся `hypothesis_not_proven`. Ограничения: абстрактный
organ-network организм, reduced proxies/edges, порядковые параметры,
операциональные пороги, n ≤ 3, нет биологической валидации.

## Stage 6C result

Reversibility слой добавлен, candidate robust bounded degradation v5
**не найден**:

- legacy `none` = Stage 6B бит-в-бит (67.0/58.2 baseline);
- reversibility baseline 67.0/58.2 — ledger отслеживается без
  мгновенной смерти, dominant wall `irreversible_accumulation`
  (irreversible slope 0.0027–0.0054 против eps 0.004; conversion rate
  0.06–0.07 против порога 0.05);
- preventive only 68.2/59.2, clearance only 69.0/60.5, irreversible
  repair only 67.0/58.2 (потолок не тронут без rev-нагрузки);
- combined preventive+clearance 69.5/60.5 — лучший неагрессивный;
- aggressive reversal 69.0/60.5 — ремонт не бесплатен
  (information/mutation долги, toxicity, цена ceiling);
- neural preserving 69.8/61.0 — continuity держится (min 0.95+);
- лучший поисковой — 68.8/60.2, v5 false везде;
- coordination 4×3: все режимы 69.5, gain 0.0 — non-interference
  подтверждён и при scarce ceiling;
- repair ceiling sweep (0.1/0.3/0.6): плоский 69.5 — потолок не binding,
  политика его не исчерпывает;
- conversion sweep (0.005/0.02/0.05): 69.5/69.5/60.5 — elevated
  conversion роняет lifespan на ~9 лет: conversion — главный механизм;
- info/mutation sweep 9×3: плоский 69.0, v5 false везде;
- stress 3×5×3: ranking стабилен, v5 false везде;
- `candidate_robust_bounded_degradation_v5_found = false`;
- dominant binding level: `biological_age` (первое нарушение),
  dominant reversibility wall: `irreversible_accumulation`.

Статус остаётся `hypothesis_not_proven`. Ограничения: абстрактный
organ-network reversibility организм, reduced proxies/edges, порядковые
параметры, операциональные пороги, n ≤ 3, нет биологической валидации.

## Stage 6D result

Boundary probe добавлен, candidate robust bounded degradation v5
**не найден** ни в default, ни в аблациях, ни в свипах, ни в поиске,
ни в стрессе:

- legacy `none` и нейтральные scales = Stage 6C бит-в-бит;
- default (combined + neutral ablation) 69.5/60.5, wall
  `irreversible_accumulation`, source `conversion`, компонент
  `driver:stem_exhaustion`;
- conversion_zero 69.5/60.5: irreversible slope 0.00536 → 0.00082
  (в допуске eps 0.004), но v5 false — binding смещается на
  `biological_age_slope`; source flips to
  `independent_irreversible_accrual` (`driver:dna_damage`);
- independent_zero 69.5/60.8: slope почти не меняется (0.00501+) —
  conversion доминирует;
- both_suppressed 69.5/60.8: v5 false, source flips to
  `information_debt`;
- high (×3.0) и unlimited ceiling: 69.5/60.5, v5 false — потолок не binding;
- conversion ultra sweep (9 точек): slope монотонно 0.00082 → 0.00454
  (2.0× роняет lifespan до 60.5), v5 false везде, threshold отсутствует;
- independent ultra sweep (9 точек): slope 0.00501–0.00570, v5 false везде;
- ceiling ultra sweep (7 точек): плоский 69.5, v5 false везде;
- robust search: best 68.8/60.2, v5 false; stress: ranking стабилен,
  v5 false везде;
- wall classification: `parametric_irreversibility_wall` —
  irreversible-компонент параметрически подавим (slope в допуске при
  conversion 0), но v5 как целое недостижима: подавление
  irreversible-источников открывает другую binding wall
  (`biological_age_slope`);
- `candidate_robust_bounded_degradation_v5_found = false` везде;
- dominant irreversibility source: `conversion`;
  dominant component: `driver:stem_exhaustion`.

Статус остаётся `hypothesis_not_proven`. Аблации — диагностические,
не биологические допущения; unlimited ceiling помечен exploratory.
Ограничения: абстрактная boundary-probe модель, порядковые параметры,
операциональные пороги, n ≤ 3, нет биологической валидации.

## История статусов

- Stage 5A (2026-10-04): hypothesis_not_proven, single-seed search, bounded 0/27.
- Stage 5B (2026-10-04): hypothesis_not_proven, multi-seed + noise + shocks +
  long horizon, robust bounded false везде, binding = biological_age_slope.
- Stage 5C: hypothesis_not_proven, mechanistic drivers, v2 false везде,
  binding = cellular_senescence / epigenetic_drift.
- Stage 6A: hypothesis_not_proven, organ-backed proxies + resources +
  coordination, v3 false везде, binding level = biological_age.
- Stage 6B: hypothesis_not_proven, organ-network edges + feedback +
  hard limits + network age, v4 false везде, binding level = biological_age.
- Stage 6C: hypothesis_not_proven, reversible/irreversible split +
  conversion + repair ceiling + info/mutation/niche/entropy, v5 false
  везде, wall = irreversible_accumulation / conversion.
- Stage 6D: hypothesis_not_proven, boundary ablation probe —
  conversion подавляем (slope в допуске), но v5 false везде;
  wall = parametric_irreversibility_wall, source = conversion,
  компонент = driver:stem_exhaustion.
