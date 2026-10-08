# HYP-0: candidate immortality policy — статус проверки

> Статус: **hypothesis_not_proven**.
> Формулировка критерия: `docs/IMMORTALITY.md` §§6–16 (robust v1 → mechanistic v2 →
> organ-backed v3 → network v4 → reversibility v5 + правила интерпретации 6D–8.5).
> Модель: абстрактный организм Stage 5A → 8 (organism → organ-backed →
> organ-network → reversibility + boundary/audit/alignment зонды).

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

## Stage 6E result

Compound wall attribution и knife-edge probe добавлены, candidate robust
bounded degradation v5 **не найден** ни в nominal, ни в аблациях, ни в
sensitivity:

- knife-edge sweep 8×3 (0.0 … 1.0 при independent=0): v5=false во всех
  8 точках, включая 1e-6 — knife-edge нет, порога нет; binding везде
  `biological_age_slope`; source `conversion` (≥0.01) →
  `information_debt` (≤0.001);
- bio-age attribution стабильна по аблациям: total slope ≈ 1.33,
  dominant `proteostasis_loss` → `proteostasis_metabolic` (0.69), далее
  `stem_exhaustion` (0.23), `inflammatory_senescent` (0.18); residual
  −0.014 (linear proxy объясняет ~99%); значимых источников — 3;
- sensitivity (eps 0.002/0.004/0.008 × dt 0.5/0.25/0.1 × 4 аблации × 5
  seeds, 60 прогонов, v5 переоценён без реранов): eps/dt/seed stable все
  true; v5=false во всех 36 ячейках, включая самый мягкий eps;
- compound wall в sensitivity и compound-attribution независимо:
  `compound_residual_wall` — irreversible slope подавлен, v5 false,
  binding `biological_age_slope`, ≥2 остаточных источников;
- `candidate_robust_bounded_degradation_v5_found = false` везде;
- dominant wall: `compound_residual_wall` (уточнение 6D-метки
  `parametric_irreversibility_wall` для v5 как целого).

Статус остаётся `hypothesis_not_proven`. Attribution shares — linear
diagnostic proxy, не conservation law; unlimited ceiling exploratory.
Ограничения: абстрактная boundary-probe модель, порядковые параметры,
операциональные пороги, dt ∈ {0.5, 0.25, 0.1}, n ≤ 5, нет биологической
валидации.

## Stage 6F result

Heterogeneous residual driver probe добавлен поверх Stage 6E,
candidate robust bounded degradation v5 **не найден** ни в одном
гетерогенном режиме:

- probe (15 режимов × 3 seeds: control + `proteostasis_metabolic` /
  `stem_exhaustion` по 1.0/0.5/0.25/0.0 + combos): v5=false везде;
  binding везде `biological_age_slope`; dominant bio-age источник
  везде `proteostasis_metabolic`; source flip нет; снижение bio slope
  ≤0.6% (ослабление частично нивелируется repair/coupling динамикой
  текущей абстракции — операционный диагностический эффект, не
  биологическое утверждение);
- sweep (14 режимов × 3 seeds: все 6 source-групп по 1.0/0.0 + joint
  ablation): v5=false везде; joint suppression всех групп снижает bio
  slope лишь на 17% (1.33 → 1.10) — ниже substantial-порога 20%;
  поодиночке ≤8.5%; binding и dominant источник не меняются;
- residual wall в probe и sweep независимо: `diffuse_residual_wall`
  (диффузная остаточная стена), уверенность средняя — в текущей
  абстрактной модели остаточная стена сохраняется при целевом
  гетерогенном подавлении;
- `candidate_robust_bounded_degradation_v5_found = false` везде;
- driver не является единственно съёмным ограничением при текущем
  операционном v5; это диагностический вывод внутри модели, а не
  биологическая смена причины.

Статус остаётся `hypothesis_not_proven`. Это не биологическая
валидация, не доказательство бессмертия и не доказательство
необратимости старения. Ограничения: stability покрывает seeds
(eps/dt/horizon — сеткой 6E); attribution shares — диагностические
прокси; вывод действует только внутри abstract organ-network
reversibility boundary-probe модели.

## Stage 7 result

Criterion and Parameter Robustness Audit добавлен поверх Stage 6F,
candidate robust bounded degradation v5 **не найден** ни в одном
параметрическом режиме и ни в одном criterion variant:

- parameter probe (23 режима × 3 seeds: веса top drivers 0.5/1.0/2.0,
  ledger scales 0.75/1.0/1.25/1.5, explicit combos): v5=false везде;
  binding везде `biological_age_slope`; dominant bio-age источник
  везде `proteostasis_metabolic`; flip нет;
- criterion probe (всё задекларировано до прогона): horizons
  100/150/200, thresholds ±10/±20%, aggregations
  global/network/reversibility, estimators
  least_squares/endpoint/trailing_window — вердикт v5, binding и
  dominant source не меняются ни в одном variant при той же динамике;
- identifiability: оба драйвера responsive (proteostasis +51%, stem
  +17% наблюдаемого отклика при ×2) — каналы различимы,
  `identifiable`;
- audit classification: `robust_diffuse_wall` (устойчивая диффузная
  стена), уверенность высокая — в текущей абстрактной модели
  проверена устойчивость диагностического вывода;
- `candidate_robust_bounded_degradation_v5_found = false`;
  audit-режим: возможный v5=true классифицировался бы как sensitivity
  (criterion/parameter), а не как кандидат.

Статус остаётся `hypothesis_not_proven`. Это проверка качества самой
диагностики, а не поиск успеха. Ограничения: сетка (веса 0.5–2.0,
ledger 0.75–1.5, горизонты 100–200, пороги ±20%); attribution
shares — диагностические прокси; unlimited ceiling остаётся
exploratory; вывод действует только внутри abstract organ-network
reversibility boundary-probe модели.

## Stage 8 result

Biological Alignment and Mechanistic Extension Feasibility Gate
добавлен поверх Stage 7. Это не новая биология в симуляции и не
попытка получить v5: биологические направления 2022–2026 переведены
в модельно-ориентированные артефакты.

- Манифест `experiments/configs/stage8_biological_alignment_manifest.json`:
  13 anchors, 9 mismatches, 8 candidate mechanisms (P0–P6),
  stage9_priorities, limitations. Все внешние направления помечены
  `needs_verification`: проверяемых источников в репозитории нет
  (каталог S-1…S-20 покрывает счёт клеток и раннее развитие, а не
  механизмы старения).
- Pure validator `src/longevity/research/biological_alignment.py`:
  schema, запрет overclaims, source_status, candidate schema,
  классификатор из 6 меток. Симуляцию не запускает, модель не меняет.
- Главные пробелы: эпигенетическая пластичность, системная
  межорганная коммуникация, качество ниши стволовых клеток,
  энергетическая координация ремонта, разделение damage/adaptation,
  нелинейная возрастная динамика, классы агрегатов.
- Классификация: `mechanistic_extension_required` (требуется
  механистическое расширение), уверенность средняя.
- Приоритеты Stage 9: P0 — epigenetic_plasticity_restoration +
  damage_adaptation_split; P1 — systemic_circulation_pool; далее
  ниша (P2), энергия (P3), иерархия (P4), волны (P5), классы
  агрегатов (P6). Кандидаты не симулированы; реализация Stage 9 не
  начата и требует отдельного решения.

Статус остаётся `hypothesis_not_proven`. Это не биологическая
валидация, не доказательство бессмертия и не доказательство
омоложения человека. Ограничения: все 2022–2026 направления без
источника помечены `needs_verification`; количественной калибровки
скоростей нет; выводы действуют только внутри текущей абстракции.

## Strategic Pivot (2026-10-07)

Решением 2026-10-07 вместо немедленного прототипа (прежний план
Stage 9 из `docs/MECHANISTIC_EXTENSION_ROADMAP.md` — **отложен**,
не отменён) открыт docs-only гейт
`Immortality Master Switch Discovery Gate` (Stage 8.5). Pivot
заменяет нумерацию этапов после Stage 8; код модели, конфиги
экспериментов и симуляция не менялись.

- Уровни цели: `docs/IMMORTALITY_TARGET_DEFINITION.md`
  (7 уровней; проект проверял только уровни 1–3 и отрицательно — 5).
- Программа, 10 критериев master switch, kill criteria, карта
  Stage 8.5 → 16: `docs/MASTER_SWITCH_DISCOVERY_PROGRAM.md`.
- Реестр кандидатов и контуров A–E: в
  `docs/CANDIDATE_GENE_AND_CIRCUIT_REGISTRY.md` — все
  `candidate_only`, внешние основания `needs_verification`.
- Внешние anchors: `docs/EXTERNAL_EVIDENCE_ANCHORS.md`
  (5 `verified_in_repo` — только модельные; 7 `needs_verification`;
  1 `unavailable`).
- Модель безопасности/онкориска (проект, fail-closed): в
  `docs/SAFETY_AND_CANCER_RISK_MODEL.md`; реализация — Stage 11.
- Гипотезы HYP-2.1…HYP-2.5: в
  `research/hypotheses/HYP-2_master_switch_candidates.md`.

**Статус HYP-0 не меняется: `hypothesis_not_proven`.** Ни один
мастер-свитч не найден, не доказан, не заявлен возможным или
близким. Решение на гейте — `review` (не `proceed`).

## Stage 9 result

Epigenetic Backup Prototype (information-preservation model,
`epigenetic_backup_model=reference_restore`) добавлен поверх полного
стека 6C; candidate robust bounded degradation v6 **не найден**:

- механизм работает как задумано: наклон энтропии 0.0003–0.0009
  (в допуске eps 0.004), Backup Drive читаем во всех прогонах,
  reference заморожен на 25.0, откаты и синтетические апоптозы
  срабатывают (5+ событий за прогон), санитированный геном снижает
  bio slope 1.38 → 1.35;
- поиск 54×3 (откат: cooldown × интенсивность × порог энтропии;
  апоптоз: каденс): v6=false в 54/54, lifespan плоский 67.5–68.8,
  binding везде `biological_age_slope` остальных драйверов;
- `candidate_robust_bounded_degradation_v6_found = false`;
- стена: точечный откат одного драйвера третью стену не снимает
  (диффузный паттерн Stage 6F/7 повторяется на новом слое).

Статус остаётся `hypothesis_not_proven`. Это граница текущей
абстракции с новым каналом, а не опровержение гипотезы в реальности.
Ограничения: порядковые параметры, n = 3, некалиброванная биология;
вывод действует только внутри abstract organ-network reversibility
backup модели.

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
- Stage 6E: hypothesis_not_proven, knife-edge sweep (v5 false в 8/8,
  knife-edge нет) + bio-age attribution (dominant proteostasis_metabolic)
  + sensitivity (eps/dt/seed stable, v5 false в 36/36);
  wall = compound_residual_wall.
- Stage 6F: hypothesis_not_proven, heterogeneous probe (v5 false в
  15/15) + sweep всех групп (v5 false в 14/14, joint ablation −17%);
  residual wall = diffuse_residual_wall.
- Stage 7: hypothesis_not_proven, parameter probe (v5 false в 23/23)
  + criterion variants (flip нет) + identifiability (оба драйвера
  responsive); audit = robust_diffuse_wall.
- Stage 8: hypothesis_not_proven, alignment manifest (13 anchors,
  9 mismatches, 8 кандидатов P0–P6) + validator; внешние направления
  needs_verification; classification = mechanistic_extension_required.
- Stage 8.5 (2026-10-07): hypothesis_not_proven, docs-only Discovery
  Gate (6 документов, без кода/симуляции); pivot заменяет нумерацию
  после Stage 8; решение = review, не proceed.
- Stage 9 (2026-10-08): hypothesis_not_proven, epigenetic backup
  prototype (reference_restore + rollback/apoptosis, 54×3 поиск +
  санитированная проба); механизм работает, v6=false везде;
  стена точечного отката повторяет диффузный паттерн 6F/7.
