# IMMORTALITY.md — Предельная исследовательская гипотеза

> «Бессмертие» НЕ является заранее доказанным результатом.
> Это предельная исследовательская гипотеза.

Этот документ формулирует, что под «immortality» понимается в рамках проекта, чтобы
термин был **проверяемым**, а не лозунгом.

## 1. Формулировка гипотезы

**HYP-0 (предельная).** Существует конфигурация параметров клеточной модели человека,
при которой система (в рамках модели) сохраняет жизнеспособность и нормальную функцию
неограниченно долго, то есть:

```
lim_{t→∞} P( организим функционален в момент t ) > 0
```

и при этом:

- не происходит терминального отказа (lifespan не ограничен),
- метрики healthspan остаются выше порогов,
- результат устойчив к стохастическому шуму (повторные запуски с различными seed).

## 2. Что НЕ входит в HYP-0

- Биологическое бессмертие реального человека (не входит в вычислительный проект
  как подтверждённый факт).
- Возможность «воскрешения» после терминального отказа системы.
- Отсутствие всех видов деградации (иммунная старость, рак и т.д. — остаются
  возможными ограничителями модели).

## 3. Как HYP-0 проверяется в вычислительной среде

1. Вводится **базовая конфигурация** (baseline) — эмерджентное старение из каталога
   механизмов (`docs/CELLULAR_AGING.md`).
2. Вводится **интервенционный слой** — параметрические изменения (усиление репарации,
   клиренс сенесцентных клеток, улучшение поддержания стволовых клеток и т.д.).
3. Запускаются контролируемые эксперименты (`docs/EXPERIMENTS.md`).
4. **Иммортальность** считается **наблюдаемой только если**:
   - симуляция стабилизируется (метрики не деградируют) на горизонте, где baseline
     гарантированно деградирует;
   - проверено ≥ 2–3 независимых seed;
   - стабильность длится «неограниченно» в практическом смысле (много порядков дольше
     baseline lifespan).
5. Если это не наблюдается — **это результат тоже важен**: он указывает, какие
   механизмы неустранимы в модели.

## 4. Известные ограничители, которые модель не должна прятать

- Раковые риски: любая конфигурация, стимулирующая неограниченную пролиферацию без
  контроля, должна вести к раковой деградации (иначе модель некорректна).
- Ошибки репликации ДНК и теломерная динамика: даже при совершенной репарации
  остаются постоянные стохастические события.
- Стохастическая природа событий: immortality в модели означает *устойчивое* состояние,
  а не «смертности никогда не бывает».

## 5. Стандарты исключения из выводов

- Результат «система жила дольше baseline» НЕ равен «бессмертие». Разделять:
  1. «продление lifespan» (конечный, но больший горизонт);
  2. «стабилизация на конечном горизонте»;
  3. «ненаблюдаемая деградация в пределах бюджета симуляции»;
  4. «доказательное неподдержание деградации» — единственный кандидат на HYP-0.
- Каждый отчёт об эксперименте обязан назвать пороги и горизонт, на котором сделан
  вывод (см. `docs/EXPERIMENTS.md`).

## 6. Robust model criterion для candidate immortality policy (Stage 5B)

В конечной симуляции candidate immortality policy может рассматриваться
только как политика, при которой bounded degradation наблюдается на
длинном горизонте, устойчиво к множеству seed, параметрическому шуму и
стрессовым сценариям, при соблюдении ограничений по онкориску,
воспалению, фиброзу, резерву и нейронной непрерывности. Это не
доказательство бессмертия, а операциональный критерий для computational
exploration.

Конкретно (`docs/ORGANISM_MODEL.md` §8): `robust_bounded_degradation_indicator`
истинен, если success rate bounded ≥ `min_success_rate` (0.8) по сидам,
worst-case slopes в допусках, окна rolling-чистые, cancer/inflammation/
fibrosis/continuity/reserve в hard limits. Текущий статус по итогам
Stage 5B — `hypothesis_not_proven`: ни одна проверенная политика не
прошла критерий; связывающее ограничение — `biological_age_slope`.
Детали статуса — в `research/hypotheses/HYP-0_immortality_policy.md`.

## 7. Mechanistic candidate immortality criterion (Stage 5C)

В конечной симуляции candidate immortality policy может рассматриваться
только как политика, при которой:

1. biological_age slope после зрелости ограничен;
2. ни один ключевой драйвер старения не имеет runaway trend;
3. витальные системы сохраняют запас прочности;
4. онкориск, воспаление, фиброз, резерв и нейронная непрерывность
   остаются в допустимых пределах;
5. результат устойчив к seed, шуму и стрессовым сценариям.

Это операциональный критерий computational exploration, а не
доказательство бессмертия.

Конкретно (`docs/AGING_MODEL.md` §7): `robust_bounded_degradation_v2`
истинен, если success rate ≥ `min_success_rate` (0.8), worst-case bio и
driver slopes в допусках, hard limits соблюдены, нет terminal decline
и ни один драйвер не имеет runaway trend. Текущий статус по итогам
Stage 5C — `hypothesis_not_proven`: ни одна проверенная mechanistic
политика не прошла критерий; доминирующие связывающие драйверы —
`cellular_senescence` / `epigenetic_drift`.

## 8. Organ-backed candidate immortality criterion (Stage 6A)

В конечной симуляции candidate immortality policy может рассматриваться
только как политика, при которой:

1. biological_age slope после зрелости ограничен;
2. ни один ключевой драйвер старения не имеет runaway trend;
3. критические органы сохраняют функцию выше безопасного порога;
4. системные ресурсы не истощаются монотонно;
5. онкориск, воспаление, фиброз, резерв и нейронная непрерывность
   остаются ограниченными;
6. результат устойчив к seed, шуму и стрессовым сценариям.

Это операциональный критерий computational exploration, а не
доказательство бессмертия.

Конкретно (`docs/ORGAN_BACKED_ORGANISM_MODEL.md` §9):
`robust_bounded_degradation_v3` добавляет к v2 требования по органам
(функция + склоны), ресурсам (allocation + склоны) и отсутствию
terminal decline. Текущий статус по итогам Stage 6A —
`hypothesis_not_proven`: ни одна проверенная organ-backed политика не
прошла критерий; связывающее ограничение — `biological_age_slope` во
всех ячейках.

## 9. Organ-network candidate immortality criterion (Stage 6B)

В конечной симуляции candidate immortality policy может рассматриваться
только как политика, при которой:

1. biological_age slope после зрелости ограничен;
2. ни один ключевой драйвер старения не имеет runaway trend;
3. критические органы сохраняют функцию выше безопасного порога;
4. системные ресурсы не истощаются монотонно;
5. обратные связи не входят в runaway режим;
6. каскадный риск ограничен;
7. онкориск и мутационная нагрузка остаются в допустимых пределах;
8. нейронная непрерывность и информационная целостность сохраняются;
9. энергетический и токсический бюджеты вмешательств не истощаются;
10. результат устойчив к seed, шуму и стрессовым сценариям.

Это операциональный критерий computational exploration, а не
доказательство бессмертия.

Конкретно (`docs/ORGAN_NETWORK_MODEL.md` §8):
`robust_bounded_degradation_v4` добавляет к v3 требования по network age
slope, cascade, mutation, feedback, energy, toxicity и отсутствию failed
edges/hard-limit violations. Текущий статус по итогам Stage 6B —
`hypothesis_not_proven`: ни одна проверенная organ-network политика не
прошла критерий; доминирующее связывающее ограничение —
`biological_age_slope`.

## 10. Reversibility-aware candidate immortality criterion (Stage 6C)

В конечной симуляции candidate immortality policy может рассматриваться
только как политика, при которой:

1. biological_age slope после зрелости ограничен;
2. reversible burden не растёт неограниченно;
3. irreversible accumulation slope не положителен или достаточно мал;
4. conversion в необратимое состояние не имеет runaway trend;
5. repair ceiling не истощается монотонно;
6. information debt, mutation fixation, niche disorder и entropy
   production остаются ограниченными;
7. критические органы и системные ресурсы сохраняют запас прочности;
8. онкориск, воспаление, фиброз, энергия, токсичность и нейронная
   непрерывность соблюдаются;
9. результат устойчив к seed, шуму и стрессовым сценариям.

Это операциональный критерий computational exploration, а не
доказательство бессмертия.

Конкретно (`docs/REVERSIBILITY_MODEL.md` §9):
`robust_bounded_degradation_v5` добавляет к v4 требования по bio_rev
slope, reversible/irreversible/info/mutation/niche slopes, conversion
rate, repair remaining и отсутствию runaway. Текущий статус по итогам
Stage 6C — `hypothesis_not_proven`: ни одна проверенная reversibility
политика не прошла критерий; доминирующий wall —
`irreversible_accumulation` / conversion.

## 11. Boundary-probe interpretation rule (Stage 6D)

Если candidate bounded degradation появляется только при диагностическом
подавлении irreversible flux, это означает не доказательство бессмертия,
а то, что текущая абстрактная модель допускает bounded degradation лишь
вблизи нулевого необратимого накопления. Такой результат должен
формулироваться как parametric или structural model constraint, а не как
биологический вывод.

Конкретно (Stage 6D): conversion_scale=0 снижает irreversible slope в
допуск, но v5 остаётся false — binding смещается на
`biological_age_slope` (исход 2: подавление открывает другую стену).
Wall classification: `parametric_irreversibility_wall`. Unlimited-ceiling
аблации помечены non-physiological exploratory. Статус —
`hypothesis_not_proven`.

## 12. Compound-wall interpretation rule (Stage 6E)

В конечной симуляции candidate immortality policy может рассматриваться
только как политика, при которой v5 достигается robustly в
не-exploratory режимах со стабильным вердиктом по seed/eps/dt. Появление
v5 только в узком ultra-low окне conversion при false по обе стороны —
это `knife_edge_parametric_wall`, а не успех; появление только с
unlimited ceiling — `ceiling_mediated_wall`; смена вердикта при
eps/dt/seed — `inconclusive_sensitivity_failure`.

Конкретно (Stage 6E): knife-edge sweep 8×3 — v5=false везде, knife-edge
нет; bio-age attribution — dominant `proteostasis_metabolic` при total
slope ≈ 1.33; sensitivity eps×dt×seed — стабильно false; compound wall —
`compound_residual_wall`. Статус — `hypothesis_not_proven`.

## 13. Heterogeneous-probe interpretation rule (Stage 6F)

Точечное подавление top-драйверов `biological_age_slope` существующими
механизмами (`aging_drivers` + `component_overrides`, без новой
биологии) проверяет структуру составной остаточной стены: диффузная,
локализованная, смешанная или неоднозначная.

Конкретно (Stage 6F): probe 15×3 + sweep всех групп 14×3 — v5=false
в 29/29 режимах, flip binding/source нет, dominant везде
`proteostasis_metabolic`, joint ablation всех групп −17% (ниже
substantial-порога 20%). Residual wall — `diffuse_residual_wall`
(уверенность средняя): стена распределена по нескольким каналам
текущей абстракции, а не держится на одном removable драйвере.
Attribution shares — операционные диагностические прокси, не законы
сохранения. Статус — `hypothesis_not_proven`.

## 14. Robustness-audit interpretation rule (Stage 7)

Audit проверяет качество самой диагностики: устойчива ли диффузная
стена к вариациям операционного критерия v5 и параметров модели.
Появившийся в аудите v5=true классифицируется как sensitivity
(criterion/parameter), а не как кандидат; это не поиск успеха.

Конкретно (Stage 7): parameter probe 23×3 (веса 0.5–2.0, ledger
0.75–1.5) + pre-declared criterion variants (horizons 100/150/200,
thresholds ±20%, aggregations global/network/reversibility, estimators
least_squares/endpoint/trailing_window) — v5=false везде, flip нет,
оба драйвера identifiable (proteostasis +51%, stem +17%). Audit —
`robust_diffuse_wall` (уверенность высокая). Статус —
`hypothesis_not_proven`.

## 15. Alignment gate and target levels (Stage 8 → 8.5)

Stage 8 не добавляет биологию в симуляцию и не пытается достичь v5:
это выравнивающий гейт (манифест 13 anchors / 9 mismatches /
8 кандидатов P0–P6 + pure validator; классификация
`mechanistic_extension_required`, уверенность средняя; все внешние
направления 2022–2026 — `needs_verification`). Детали —
`docs/BIOLOGICAL_ALIGNMENT.md`,
`docs/MECHANISTIC_EXTENSION_ROADMAP.md`,
`research/hypotheses/HYP-0_immortality_policy.md` (раздел Stage 8 result).

Stage 8.5 — docs-only `Master Switch Discovery Gate` (код и симуляция
не менялись; прежний Stage 9 prototype отложен, не отменён):
7 уровней цели — `docs/IMMORTALITY_TARGET_DEFINITION.md` (проект
проверял только уровни 1–3 и отрицательно — 5; HYP-0 соответствует
уровню 6); программа с 10 критериями и kill criteria —
`docs/MASTER_SWITCH_DISCOVERY_PROGRAM.md` (решение: `review`);
реестр кандидатов и контуров —
`docs/CANDIDATE_GENE_AND_CIRCUIT_REGISTRY.md`; карта anchors —
`docs/EXTERNAL_EVIDENCE_ANCHORS.md`; проект safety-модели —
`docs/SAFETY_AND_CANCER_RISK_MODEL.md`; гипотезы HYP-2 —
`research/hypotheses/HYP-2_master_switch_candidates.md`.
Ничего не найдено и не доказано; статус — `hypothesis_not_proven`.