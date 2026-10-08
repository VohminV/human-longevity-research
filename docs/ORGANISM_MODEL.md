# ORGANISM_MODEL.md — Минимальная организменная жизненная траектория (Stage 5A)

> Это НЕ модель человека. Порядковые скорости, абстрактные годы, нет
> анатомии и калибровки. `bounded_degradation_indicator = true` — это
> модельный флаг, а не доказательство бессмертия. Бессмертие —
> `hypothesis_not_proven` в каждом результате.

## 1. Что такое OrganismModel

`src/longevity/model/organism.py`: организм проходит стадии embryo →
fetal → infancy → childhood → adolescence → adult_homeostasis →
early_aging → late_aging (плюс вычисляемый `terminal_decline`) по
конфигурируемым границам возраста. Восемь витальных систем
(`brain_cns`, `cardiovascular`, `respiratory`, `hepatic`, `renal`,
`immune`, `metabolic`, `musculoskeletal`) с полями function/reserve/
damage/aging_rate/repair/warning/failure-пороги/чувствительности; у
`brain_cns` — `informational_continuity` (не путать замену тела с
сохранением личности, см. `docs/IMMORTALITY.md`).

До зрелости — программа развития (рост функции/резерва/размера тела,
damage ≈ 0); после — coupled-старение девяти драйверов (damage,
senescence, inflammation, fibrosis, cancer, epigenetic drift,
proteostasis/mito decline, regenerative exhaustion) с ремонтом из
резерва. `biological_age` идёт медленнее в детстве, быстрее при
повреждениях и падает от вмешательств (считается rejuvenation event).

## 2. Смерть — отказ, а не таймер

`check_viability`: critical system < failure → `<system>_failure`;
`vitality_index` (взвешенное среднее, мозг ×3) < 0.30 или ≥3 систем ниже
warning → `systemic_cascade`; `cancer_burden` > 0.80 → `cancer_death`;
иммунный коллапс + воспаление → `immune_failure`; continuity < 0.50 →
`neural_identity_loss` (опционально летально). Плюс `unknown`-fallback
по `max_age = 150`. Фиксируются `death_time`, `primary_cause_of_death`,
`failure_cause_sequence` (первая причина; ties — канонический порядок).

## 3. Вмешательства (`longevity.model.intervention`)

8 классов (операциональные шаблоны, не измерения): `molecular_repair`,
`cellular_replacement`, `tissue_organ_maintenance`, `systemic_modulation`,
`regenerative_boost` (+cancer-риск), `neural_protection`,
`cancer_surveillance`, `recovery_support`. У каждого — польза И цена
(резерв, рак, воспаление): бесплатных нет. `LongevityPolicy`:
periodic (фаза по interval) / threshold_based (биомаркер + порог +
refractory-cooldown через `interval`, иначе доза несравнима с
периодическими — урок калибровки); constraints (`max_cancer_allowed`,
`min_reserve_required`) пропускают срабатывание. `PolicySet` детерминирован
(порядок + история срабатываний, без random).

Предустановленные политики: natural, senolytic_periodic,
molecular_repair_periodic, regenerative_support (блок), anti_inflammatory
(блок), cancer_surveillance (блок), neural_preserving, combined_maintenance,
adaptive_threshold, organ_inspired_maintenance (не pruning без системной
причины + отдельный recovery + cancer-constraint — уроки Stage 4D).

## 4. Метрики (`longevity.analysis.organism_metrics`)

lifespan/healthspan (healthspan ≤ lifespan всегда), AUC бремён,
`final/min/time_to_failure` по системам, `neural_identity_preservation`,
rejuvenation-счётчики, `biological_age_slope` / `damage_slope` после
зрелости (наименьшие квадраты), `bounded_degradation_indicator`
(жив + slopes ≤ ε + витальные системы выше порогов + рак/воспаление/фиброз
ограничены). Фитнес — взвешенная multi-objective сумма (lifespan,
healthspan, reserve − damage − cancer − inflammation − neural loss +
bounded-бонус); Pareto по (lifespan, healthspan, −cancer).

## 5. Результаты v0 (seed 42, dt 0.25)

| Политика | lifespan | healthspan | bio | причина | rejuv | cancer_auc |
|---|---|---|---|---|---|---|
| baseline | 68.0 | 61.8 | 68.2 | systemic_cascade | 0 | 1.14 |
| senolytic | 70.0 | 63.5 | 65.8 | systemic_cascade | 9 | 1.47 |
| molecular_repair | 74.5 | 68.0 | 71.1 | systemic_cascade | 10 | 1.58 |
| combined | 80.5 | 73.0 | 67.7 | systemic_cascade | 42 | 1.18 |
| adaptive | 117.8 | 100.2 | 87.1 | systemic_cascade | 132 | 3.78 |
| neural_preserving | 75.8 | 69.8 | 68.0 | systemic_cascade | 34 | 0.89 |
| organ_inspired | 79.0 | 71.8 | 68.8 | systemic_cascade | 34 | 0.97 |

Чтение строго внутримодельное:

1. **Baseline умирает каскадом, а не одной системой** (min functions
   0.34–0.62, ни одна ниже failure): смерть — системное событие при
   целых-т0 порогах. Витальность 61 AUC, bio≈chrono.
2. **Repair > replacement** (74.5 vs 70.0): чинить damage выгоднее, чем
   чистить сенесценцию, в этой параметризации.
3. **Reactive control доминирует** (117.8/100.2): вмешиваться по порогам
   лучше фиксированного расписания; цена — cancer_auc ×3.3 (агрессивная
   замена без достаточного surveillance). Cooldown через `interval`
   обязателен, иначе доза threshold-политик несравнима (без него был
   артефакт 150/150).
4. **Neural-preserving самый чистый по раку** (0.89 < baseline): surveillance
   + умеренность окупаются; continuity сохранена.
5. **Organ-inspired ≈ combined** (79.0 vs 80.5) при меньшем раке (0.97):
   не-прининг + recovery + cancer-constraint — уроки 4D переносятся.
6. **Bounded degradation нигде**: даже adaptive (bio slope > ε). Mini
   policy search (27 комбинаций × 2 сида): лучший — агрессивный repair q3
   + senolytic q3 (lifespan 96.2, healthspan 84.8); bounded = 0/27;
   Pareto = 14. Candidate immortality policy НЕ найдена — честный
   отрицательный результат поиска в этой сетке.

## 6. Гипотеза бессмертия (формализация)

```text
Существует политика P, при которой после зрелости: все critical-системы
выше failure_threshold; biological_age и global_damage без устойчивого
положительного тренда; rejuvenation возвращает функции; рак/воспаление/
фиброз/потеря continuity ограничены; отказ витальных систем не растёт
неограниченно на длинном горизонте.
```

Статус во всех артефактах: `immortality_status = hypothesis_not_proven`.
`bounded_degradation_indicator` — проверяемый прокси, не доказательство.

## 7. Ограничения (Stage 5A)

Абстрактный организм: порядковые параметры, нет калибровки на людях,
dt 0.25 года мостит быстрые/медленные процессы грубо,
mini-поиск покрывает малую сетку, HYP-0 — только формализация.
Уроки Stage 3/4 перенесены явно: replacement недостаточен, recovery важен,
слепой pruning вреден, non-interference был оптимален в органе,
биомаркер ≠ жизнеспособность.

## 8. Stage 5B — Robust long-horizon search и stress testing

> Проверка: держится ли хоть какая-то политика, если смотреть не на один
> seed, а на распределение по сидам, шуму, стрессам и длинному горизонту.
> Все критерии — операциональные, внутримодельные; HYP-0 остаётся
> `hypothesis_not_proven`.

### 8.1. Что добавлено

- Opt-in `perturbation_model = parametric_noise` (`none` побайтово = 5A):
  шум aging/repair/efficacy на выделенных RNG-потоках (динамика-RNG не
  трогается) + 7 типов детерминированных шоков с настраиваемыми
  вероятностью/магнитудой/длительностью/подмножеством типов.
- Multi-seed агрегаты (mean/std/min/max/median, success rates,
  распределения причин) — описательно, не statistical proof.
- Rolling windows для slopes и границ — ловят late divergence.
- `robust_bounded_degradation_indicator`: bounded по всем сидам с rate ≥
  `min_success_rate` (0.8) + worst-case slopes в допусках + чистые окна.
- Binding constraints: первое нарушенное ограничение в каноническом
  порядке (`biological_age_slope`, `damage_slope`, `critical_function_margin`,
  `cancer_burden`, `inflammation`, `fibrosis`, `neural_continuity`) —
  честный ответ «почему не bounded».
- Robust fitness: mean − λ·std − λ·worst (дефолтные λ = 0, поведение 5A
  сохранено); stress suite из 9 сценариев;Cooldown-история политик
  персистентна в checkpoint (legacy restore работает; ограничение 5A снято).

### 8.2. Результаты (внутри модели)

- Baseline robust (5 сидов): 68.0 ± 0.0, всегда `systemic_cascade`,
  binding всегда `biological_age_slope`.
- Key policies × nominal/noise: ranking 5A сохраняется (adaptive 118.7 >
  search_best 95.5 > combined 80.7 > inspired 79.1 > repair ≈ neural 76 >
  senolytic 70.3); robust_bounded — false везде.
- Adaptive constrained: cancer_auc 3.78 → 2.88 (−24%) при сохранённом
  lifespan (117.5 vs 117.8) — constraint работает как задумано.
- Stress suite (5 runs × 9 scenarios × 3 seeds): ranking стабилен;
  toxicity бьёт сильнее всего (adaptive 117.8 → 92.8, search_best 95 → 78.8);
  low_reserve переключает search_best на `immune_failure`;
  neural_stress не влияет нигде (continuity защищена/шоки слабы — факт о
  модели); bounded — 0/45 ячеек.
- Robust search и long-horizon search (250y): тот же оптимум (repair q3 +
  senolytic q3), bounded 0/27 в обоих; pareto 14.
- По пути пойманы и исправлены два бага: общий perturb_seed=0 для всех
  сидов (все noise-прогоны были идентичны) и отсутствие seed в вызове
  модели из раннера; добавлен регрессионный тест.

### 8.3. HYP-0 статус

```text
hypothesis_not_proven.
No candidate robust immortality policy in the current abstract organism
model: bounded degradation fails everywhere, and the binding constraint
is biological_age_slope in 70/70 evaluated key-policy cells.
```

Единственное ограничение, которое систематически связывает результат, —
неустранимый положительный наклон biological age после зрелости. Ни рак,
ни резерв, ни continuity не являются первыми нарушителями ни в одной
ячейке. Это и есть честный ответ Stage 5B: в текущей модели старение как
тренд биологического возраста не останавливается ни одной проверенной
политикой.

### 8.4. Ограничения Stage 5B

Те же, что §§5–7, плюс: n ≤ 5 описательно; perturbation/shock-параметры
некалиброваны; mini-сетки поиска узкие; HYP-0 — только формализация.

## 9. Stage 5C — Mechanistic aging drivers и reversibility search

> Ответ на вопрос Stage 5B: из чего состоит biological_age и какой
> именно драйвер не даёт тренду остановиться. Все критерии —
> операциональные, внутримодельные; HYP-0 остаётся
> `hypothesis_not_proven`.

### 9.1. Что добавлено

- Opt-in `aging_mechanism_model = none | mechanistic_drivers` (`none`
  численно идентичен Stage 5B; регрессия: 68.0/61.8 cascade бит-в-бит).
- 8 драйверов (`dna_damage`, `epigenetic_drift`, `proteostasis_loss`,
  `mitochondrial_dysfunction`, `cellular_senescence`, `stem_exhaustion`,
  `chronic_inflammation`, `cancer_prone`) с накоплением, репарацией из
  резерва, обратимостью и diminishing returns; `biological_age` —
  взвешенная агрегация с полом `adult_age_setpoint` (rejuvenation =
  возврат к взрослому setpoint, не эмбриональное сбрасывание).
- 12 mechanistic вмешательств с ценами и рисками (reprogramming —
  cancer/neural; telomere/stem — cancer; см. `docs/AGING_MODEL.md`).
- `dominant_binding_driver` (взвешенный slope, tie-break по имени),
  `robust_bounded_degradation_v2` (bio slope + max driver slope +
  hard limits + worst case), driver-aware fitness
  (`w_driver_slope`, `w_bounded_v2_bonus`), binding-driver sweep,
  mechanistic stress suite.
- 16 конфигов `organism_aging_*.json`; тесты (4 файла): совместимость,
  детерминизм, границы, floor, trade-offs, binding, v2, поиск, стресс,
  checkpoint, scope.

### 9.2. Результаты (внутри модели)

- Mechanistic baseline: 66.8/60.8, dominant `cellular_senescence`.
- Одиночные: лучший slope — senolytic (0.620); epigenetic — cancer
  1.45 + neural min 0.745; stem/telomere — cancer 1.39.
- Combined — лучший фиксированный (70.8, bio 47.3, cancer 0.68), но
  slope 0.417 >> eps; binding смещается на `epigenetic_drift`.
- Robust search mini (12 × 3): лучший 72.2/65.2, v2 false везде.
- Binding sweep (27 × 3): 18 — `epigenetic_drift`, 9 —
  `cellular_senescence`.
- Stress (3 × 6 × 3): ranking стабилен; toxicity бьёт сильнее;
  v2 false везде.

### 9.3. HYP-0 статус

```text
hypothesis_not_proven.
No candidate robust bounded degradation v2 in the current abstract
organism model: no policy holds biological_age slope and all driver
slopes within bounds robustly; dominant binding drivers are
cellular_senescence / epigenetic_drift depending on policy.
```

### 9.4. Ограничения Stage 5C

Те же, что §§5–8, плюс: параметры драйверов некалиброваны;
telomere/altered-communication/fibrosis — расширения; n ≤ 3
описательно; HYP-0 — только формализация.

## 10. Stage 6A — Organ-backed emergent aging (кратко)

> Ответ на вопрос Stage 5C: меняется ли картина, когда витальные системы
> частично опираются на reduced organ proxies и systemic resources.
> Полная версия — `docs/ORGAN_BACKED_ORGANISM_MODEL.md`.

- Opt-in `organ_backed_model = reduced_organ_proxies` (`none` = Stage 5C
  бит-в-бит: 66.8/60.8 cascade); 8 прокси, 4 системных ресурса,
  5 coordination modes, частично эмерджентные драйверы,
  `robust_bounded_degradation_v3`, cross-scale binding.
- Baseline 82.8/71.8, maintenance 88.0/76.0, combined 101.5/87.2,
  adaptive 97.5/82.2, search best 104.8; coordination: independent =
  deferral = lookahead, scaling −0.25 (non-interference подтверждён
  уровнем выше); repair — критичнейший ресурс; stress ranking стабилен.
- HYP-0: `hypothesis_not_proven`;
  `candidate_robust_bounded_degradation_v3_found = false`; binding —
  `biological_age_slope` во всех ячейках.

## 11. Stage 6B — Cross-organ network и hard limits (кратко)

> Ответ на вопрос Stage 6A: меняется ли картина, когда старение —
> эмерджентное свойство сети органов, feedback, энергии, информации,
> мутаций и необратимости. Полная версия — `docs/ORGAN_NETWORK_MODEL.md`.

- Opt-in `organ_network_model = reduced_network_feedback` (`none` =
  Stage 6A бит-в-бит); 12 рёбер, 7 feedback loops, hard limits, network
  age с floor, 7 новых coordination modes, 9 новых причин отказа,
  `robust_bounded_degradation_v4`, network binding v3.
- Baseline 67.0/58.2, maintenance 73.0/65.0, combined 76.5/68.8,
  adaptive 76.8/70.2, search best 75.2; coordination 6x3 все 76.5
  (non-interference на сетевом уровне); repair снова критичен
  (4 → ~55; ≥8 → ~77.8); stress ranking стабилен.
- HYP-0: `hypothesis_not_proven`;
  `candidate_robust_bounded_degradation_v4_found = false`; binding —
  `biological_age` (и network slope) во всех ячейках.

## 12. Stage 6C — Reversibility ceiling и irreversible accumulation (кратко)

> Ответ на вопрос Stage 6B: reversible мусор или irreversible долг?
> Полная версия — `docs/REVERSIBILITY_MODEL.md`.

- Opt-in `reversibility_model = split_reversible_irreversible` (`none` =
  Stage 6B бит-в-бит); per-driver/per-organ rev/irr ledger, conversion с
  модификаторами, repair ceiling с cost/risk/diminishing, information
  debt, mutation fixation, niche disorder, entropy, bio_rev с
  динамическим irreversible floor, 9 новых intervention-типов, 7
  coordination modes, 9 новых причин отказа, `robust_bounded_degradation_v5`.
- Baseline 67.0/58.2 (wall `irreversible_accumulation`), combined
  preventive+clearance 69.5/60.5, aggressive 69.0 (долги растут), neural
  69.8/61.0, search best 68.8; conversion 0.05 → 60.5 (−9 лет);
  coordination 4×3 все 69.5 (non-interference); ceiling sweep плоский.
- HYP-0: `hypothesis_not_proven`;
  `candidate_robust_bounded_degradation_v5_found = false`; первое
  нарушение — `biological_age`, dominant wall — `irreversible_accumulation`.

## 13. Stage 6D — Irreversibility boundary probe (кратко)

> Диагностический этап: аблации, а не новая биология. Полная версия —
> `docs/REVERSIBILITY_MODEL.md` §12.

- Opt-in `boundary_probe_model = irreversibility_ablation` (`none` и
  нейтральные scales = Stage 6C бит-в-бит); scales conversion /
  independent / ceiling, component overrides, disable/unlimited флаги;
  contribution decomposition, source attribution, wall classification.
- conversion_scale=0: irreversible slope 0.00536 → 0.00082 (в допуске),
  но v5 false — binding смещается на `biological_age_slope`;
  independent sweep почти не двигает slope; ceiling sweep плоский;
  attribution default → `conversion` / `driver:stem_exhaustion`;
  ultra-свипы 9+9+7, search, stress — v5 false везде.
- HYP-0: `hypothesis_not_proven`;
  wall — `parametric_irreversibility_wall` (исход 2).

## 14. Stage 6E — Compound wall attribution and knife-edge probe (кратко)

> Диагностический extension поверх 6D: knife-edge, bio-age attribution,
> compound-классификатор, sensitivity. Полная версия —
> `docs/REVERSIBILITY_MODEL.md` §13.

- Knife-edge sweep 8×3 (0.0 … 1.0 при independent=0): v5=false везде,
  knife-edge нет; bio-age attribution стабильна (total slope ≈ 1.33,
  dominant `proteostasis_metabolic`, residual −0.014, 3 источника).
- Sensitivity eps×dt×seed (60 прогонов): стабильно false везде;
  compound wall — `compound_residual_wall`.
- HYP-0: `hypothesis_not_proven`.

## 15. Stage 6F — Heterogeneous residual driver probe (кратко)

> Диагностический зонд структуры составной стены: точечное подавление
> top-драйверов существующими механизмами, без новой биологии.
> Полная версия — `docs/REVERSIBILITY_MODEL.md` §14.

- Probe 15×3 + sweep всех групп 14×3: v5=false в 29/29 режимах;
  binding везде `biological_age_slope`; dominant везде
  `proteostasis_metabolic`; flip нет; joint ablation всех групп −17%
  (ниже substantial-порога 20%); поодиночке ≤8.5%.
- Residual wall — `diffuse_residual_wall` (уверенность средняя).
- HYP-0: `hypothesis_not_proven`.

## 16. Stage 7 — Criterion and Parameter Robustness Audit (кратко)

> Проверка качества самой диагностики, не поиск v5.
> Полная версия — `docs/REVERSIBILITY_MODEL.md` §15.

- Parameter probe 23×3 + pre-declared criterion variants
  (horizons 100/150/200, thresholds ±20%, aggregations, estimators):
  v5=false везде, flip нет, оба драйвера identifiable.
- Audit — `robust_diffuse_wall` (уверенность высокая).
- HYP-0: `hypothesis_not_proven`.

## 17. Stage 8 → 8.5 — Alignment gate и master-switch gate (кратко)

> Stage 8: выравнивание с биологией без смены модели.
> Stage 8.5: docs-only гейт, код и симуляция не менялись.
> Полные версии — `docs/REVERSIBILITY_MODEL.md` §§16–17,
> `docs/BIOLOGICAL_ALIGNMENT.md`,
> `docs/MASTER_SWITCH_DISCOVERY_PROGRAM.md`.

- Stage 8: манифест (13 anchors, 9 mismatches, 8 кандидатов P0–P6)
  + pure validator; классификация `mechanistic_extension_required`
  (уверенность средняя); все внешние направления — `needs_verification`.
- Stage 8.5: 7 уровней цели, программа с 10 критериями и kill criteria,
  реестр ~19 кандидатов + 5 контуров A–E, карта anchors
  (5 verified_in_repo — только модельные / 7 needs_verification /
  1 unavailable), проект safety-модели, гипотезы HYP-2.
  Прежний Stage 9 prototype отложен, не отменён.
  Решение на гейте: `review`.
- HYP-0: `hypothesis_not_proven`.
