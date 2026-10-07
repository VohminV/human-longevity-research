# EXTERNAL_EVIDENCE_ANCHORS.md — Карта внешних anchors (Stage 8.5)

> Статус документа: `candidate_only` / карта статусов.
> Правило: внешний биологический источник без проверки в репозитории
> получает `needs_verification`; направление без даже заявленного
> источника — `unavailable`; `verified_in_repo` присваивается только
> тому, что реально подтверждено данными/манифестами в репозитории.
> DOI, PMID, авторы и URL здесь не выдумываются. Заполнение столбцов
> «Источник» — задача Stage 12 (`External Anchor Calibration`).

## 1. Три статуса

- `verified_in_repo` — подтверждено артефактами репозитория
  (манифесты Stage 4–8, результаты, тесты).
- `needs_verification` — направление заявлено, но источника,
  проверенного в репозитории, нет; проверяемо в Stage 12.
- `unavailable` — источника нет даже в заявленном виде; калибровка
  невозможна без нового внешнего материала.

## 2. Модельные anchors (Stage 8 manifest) — что есть в репо

Источник: `experiments/configs/stage8_biological_alignment_manifest.json`,
ключ `anchors`. Это **не внешние** биологические источники, а
вычислительно подтверждённые конструкты; статус `verified_in_repo`
относится к их наличию/прогону в модели.

| name | model_construct | anchor_type | source_status | confidence |
|---|---|---|---|---|
| `eight_mechanistic_drivers_present` | mechanistic_drivers | qualitative | `verified_in_repo` | high |
| `weighted_bio_age_aggregation` | biological_age_slope | quantitative-in-model | `verified_in_repo` | high |
| `stage7_robust_diffuse_wall` | robust_diffuse_wall | qualitative | `verified_in_repo` | high |
| `proteostasis_dominant_attribution` | proteostasis_metabolic | qualitative | `verified_in_repo` | medium |
| `stem_exhaustion_significant_channel` | stem_exhaustion | qualitative | `verified_in_repo` | medium |
| `hierarchical_hallmarks_literature` | mechanistic_drivers | qualitative | **`needs_verification`** | low |
| `epigenetic_plasticity_literature` | epigenetic_drift | qualitative | **`needs_verification`** | low |
| `systemic_circulation_literature` | organ_network | qualitative | **`needs_verification`** | low |
| `stem_niche_quality_literature` | stem_exhaustion | qualitative | **`needs_verification`** | low |
| `proteostasis_energy_coupling_literature` | proteostasis_metabolic | qualitative | **`needs_verification`** | low |
| `damage_adaptation_split_literature` | biological_age_slope | qualitative | **`needs_verification`** | low |
| `nonlinear_age_waves_literature` | biological_age_slope | qualitative | **`needs_verification`** | low |
| `quantitative_rate_anchors` | conversion_flux | quantitative | **`unavailable`** | none |

Итог: **5** `verified_in_repo` (все — модельные), **7**
`needs_verification`, **1** `unavailable`.

## 3. Внешние направления для master-switch программы

Каждая строка — направление, нужное для критериев
`human-relevant` и `reversible`/`durable`. Пустой столбец «Источник»
означает: репозиторий не содержит проверенного источника; заполняется
только в Stage 12 реальным citation (без выдумывания).

| # | Направление (enum) | Что нужно подтвердить | Модельная величина / прокси | Статус | Риск при отсутствии |
|---|---|---|---|---|---|
| 1 | `partial_reprogramming_literature` | обратимость и границы частичного репрограммирования | plasticity reset-cost, `epigenetic_drift` slope | `needs_verification` | контур A/E неотличим от ложного сброса |
| 2 | `senolytics_interventions` | объём и границы клиренса сенесцентных клеток | senolytic эффект size (сравнить с Stage 6F: +32.9y) | `needs_verification` | контур B = повтор Stage 5C без нового знания |
| 3 | `nutrient_sensing_interventions` (mTOR/AMPK/rapamycin-class) | масштаб и границы метаболических вмешательств | `proteostasis_loss`, `repair_ceiling` | `needs_verification` | контур C неотличим от ceiling |
| 4 | `nad_metabolism` | динамика NAD+ с возрастом и ответ на прекурсоры | `mitochondrial_dysfunction` | `needs_verification` | контур C провал критерия `measurable` |
| 5 | `telomere_biology` | теломерная динамика и онкориск теломеразы | `stem_exhaustion` (reserved `telomere_attrition`) | `needs_verification` | TERT опасен и неинтерпретируем |
| 6 | `inflammaging_biomarkers` | системные воспалительные маркеры у человека | `chronic_inflammation`, `systemic_circulation_pool` | `needs_verification` | контур D без измеримого proxy |
| 7 | `stem_cell_niche` | вклад ниши vs пула в регенерацию | `stem_exhaustion` × niche | `needs_verification` | mismatch `stem_count_without_niche` остаётся |
| 8 | `systemic_circulation_factors` | циркулирующие факторы молодости/старения | `systemic_circulation_pool` | `needs_verification` | автономные органы без системной компоненты |
| 9 | `dna_damage_rate_human` | скорости повреждения/репарации ДНК у человека | `dna_damage`, `conversion` | `needs_verification` | нет временно́й шкалы для `falsifiable`-критериев |
| 10 | `epigenetic_clocks` | калибровка эпигенетических часов человека | `epigenetic_drift`, `information_debt` | `needs_verification` | эпигенетический proxy немеряем вне модели |
| 11 | `tumor_suppressor_tradeoffs` | баланс TP53/p16 и регенеративного ответа | `cancer_prone` бюджет | `needs_verification` | safety-модель не калибруема (kill criterion 2) |
| 12 | `caloric_restriction_human` | длительные эффекты КР у человека | aggregate slope | `needs_verification` | нет human-relevant базовой линии эффектов |
| 13 | `quantitative_aging_rates` | численные скорости старения процессов | `conversion_flux` | **`unavailable`** | без чисел Stage 12–13 невозможны; kill criterion 3 |

## 4. Что считать успехом Stage 12

- Минимум для перехода Stage 8.5 → Stage 9:
  ≥ 3 строки §3 переведены в `verified_in_repo` с реально
  записанным source (не выдуманным), из них обязательно
  `partial_reprogramming_literature` и `tumor_suppressor_tradeoffs`
  (критерии `human-relevant` и `safe`).
- Для Stage 13 (portfolio screening): строка
  `quantitative_aging_rates` переведена с `unavailable` хотя бы в
  `needs_verification` с числовой модельной величиной.

## 5. Чего документ не делает

- Не ссылается на конкретные работы: перечисление DOI/PMID/авторов
  без возможности проверки в репо запрещено правилом невыдумывания.
- Не заявляет существование результатов, которых нет в репозитории.
- Не повышает статус HYP-0: `hypothesis_not_proven`.
