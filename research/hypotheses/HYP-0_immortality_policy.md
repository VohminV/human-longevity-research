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

## История статусов

- Stage 5A (2026-10-04): hypothesis_not_proven, single-seed search, bounded 0/27.
- Stage 5B (2026-10-04): hypothesis_not_proven, multi-seed + noise + shocks +
  long horizon, robust bounded false везде, binding = biological_age_slope.
- Stage 5C: hypothesis_not_proven, mechanistic drivers, v2 false везде,
  binding = cellular_senescence / epigenetic_drift.
- Stage 6A: hypothesis_not_proven, organ-backed proxies + resources +
  coordination, v3 false везде, binding level = biological_age.
