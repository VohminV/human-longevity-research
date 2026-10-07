# CANDIDATE_GENE_AND_CIRCUIT_REGISTRY.md — Реестр кандидатов и контуров (Stage 8.5)

> Статус документа: `candidate_only`. Реестр — не список «рабочих
> мишеней», а перечень кандидатов к проверке по 10 критериям
> (`docs/MASTER_SWITCH_DISCOVERY_PROGRAM.md` §3).
> HYP-0 остаётся `hypothesis_not_proven`.
> Все внешние биологические утверждения ниже — `needs_verification`:
> в репозитории нет ни одного проверенного источника по механизмам
> старения (см. `docs/EXTERNAL_EVIDENCE_ANCHORS.md`).
> DOI, PMID и авторы не выдумываются и потому здесь отсутствуют.

Поля каждой записи: `name`, `type`, `biological_role`,
`aging_evidence`, `longevity_evidence`, `rejuvenation_potential`,
`cancer_risk`, `human_relevance`, `measurable_proxy`,
`model_abstraction_candidate`, `priority`, `status`,
`falsification_criterion`.

---

## §1. Реестр кандидатов

### 1. mTOR / TOR

- **name:** `mTOR_TOR`
- **type:** pathway (nutrient-growth signaling)
- **biological_role:** мторм-зависимое подавление анаболизма и аутофагии, рост, метаболическая сенсорная ось (`needs_verification`).
- **aging_evidence:** подавление TOR-сигналинга ассоциируется с модуляцией скорости старения в модельных организмах (`needs_verification`).
- **longevity_evidence:** связь ингибирования TOR-пути с продолжительностью жизни — `needs_verification`.
- **rejuvenation_potential:** косвенный: через аутофагию и протеостаз, не прямое омоложение (`needs_verification`).
- **cancer_risk:** двусторонний: и подавление роста, и нарушение иммунного/клеточного гомеостаза при хроническом ингибировании (`needs_verification`).
- **human_relevance:** высокая заявляемая релевантность (консервированная ось) — `needs_verification`.
- **measurable_proxy:** proxy активности пути + динамика `proteostasis_loss`/`cellular_senescence` в модели.
- **model_abstraction_candidate:** `proteostasis_loss`, `energy_coupled_repair_autophagy` (Stage 8 P3), `repair_ceiling`.
- **priority:** P0.
- **status:** `candidate_only`.
- **falsification_criterion:** варьирование подавления пути в широком диапазоне не даёт устойчивого сдвига `biological_age_slope`/attribution за пределы Stage 7 noise и не различимо от `repair_ceiling`.

### 2. FOXO3

- **name:** `FOXO3`
- **type:** transcription factor
- **biological_role:** транскрипционный ответ на стресс, метаболизм, антиоксидантные и репаративные программы (`needs_verification`).
- **aging_evidence:** ассоциации вариантов гена со старением/выживаемостью — `needs_verification`.
- **longevity_evidence:** заявляемые ассоциации с долголетием человека — `needs_verification` (в репозитории GWAS-источников нет).
- **rejuvenation_potential:** не заявлен напрямую; возможный системный модулятор (`needs_verification`).
- **cancer_risk:** контекст-зависимый (апоптоз vs выживание клеток) (`needs_verification`).
- **human_relevance:** заявляется как один из немногих генов долголетия человека — `needs_verification`.
- **measurable_proxy:** транскрипционный/функциональный proxy; в модели — attribution по `dna_damage`/`chronic_inflammation`.
- **model_abstraction_candidate:** `dna_damage`, `chronic_inflammation`, контур D `systemic_renewal_circuit`.
- **priority:** P1.
- **status:** `candidate_only`.
- **falsification_criterion:** активация канала не сдвигает ни один driver/атрибуцию в модели и не даёт различимого ответа на стресс-тесты Stage 5B-класса.

### 3. SIRT1 / SIRT6 / SIRT7

- **name:** `SIRT1_SIRT6_SIRT7`
- **type:** sirtuin family (NAD+-dependent deacetylases)
- **biological_role:** метаболическая регуляция, репарация ДНК, хроматин, воспаление (`needs_verification`).
- **aging_evidence:** сиртуины связывают NAD+-статус, метаболизм и признаки старения (`needs_verification`).
- **longevity_evidence:** прямых подтверждений у человека — `needs_verification`.
- **rejuvenation_potential:** возможный косвенный (через метаболизм и хроматин) — `needs_verification`.
- **cancer_risk:** двусторонний: супрессия опухоли и выживание клеток в разных контекстах (`needs_verification`).
- **human_relevance:** `needs_verification`.
- **measurable_proxy:** NAD+-связанные метаболические proxy; в модели — `mitochondrial_dysfunction`, `epigenetic_drift`.
- **model_abstraction_candidate:** `mitochondrial_dysfunction`, `epigenetic_drift`, контур C `metabolic_support_circuit`.
- **priority:** P1.
- **status:** `candidate_only`.
- **falsification_criterion:** варьирование оси не влияет на `mitochondrial_dysfunction`/`epigenetic_drift` в модели и неотличимо от независимого сдвига энергетического budget.

### 4. TERT

- **name:** `TERT`
- **type:** gene (telomerase reverse transcriptase)
- **biological_role:** удлинение теломер, поддержание делительного потенциала стволовых/клеточных пулов (`needs_verification`).
- **aging_evidence:** теломерная динамика заявлена в модели через `telomere_attrition` (reserved, проксируется через `stem_exhaustion`); биологическая связь — `needs_verification`.
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** потенциал через клеточный ресурс, не через клиренс повреждений (`needs_verification`).
- **cancer_risk:** **высокий**: активация теломеразы — классический онко-канал (`needs_verification`).
- **human_relevance:** `needs_verification`.
- **measurable_proxy:** длина теломер/делительный потенциал; в модели — `stem_exhaustion`.
- **model_abstraction_candidate:** `stem_exhaustion` (reserved `telomere_attrition` не реализован).
- **priority:** P2.
- **status:** `candidate_only` (активация — только с safety-моделью Stage 11).
- **falsification_criterion:** эффект на lifespan в модели достигается ростом `cancer_prone` сопоставимой величины (net-эффект ≈ 0 или отрицателен).

### 5. CDKN2A / p16INK4A

- **name:** `CDKN2A_p16INK4A`
- **type:** gene / tumor-suppressor locus
- **biological_role:** ингибитор циклин-зависимых киназ, барьер деления, маркер клеточного старения (`needs_verification`).
- **aging_evidence:** локус ассоциируется с признаками клеточного старения и возрастными заболеваниями (`needs_verification`).
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** отрицательный как прямой target омоложения; точка контроля безопасности (`needs_verification`).
- **cancer_risk:** подавление — риск; экспрессия — противораковый барьер (`needs_verification`).
- **human_relevance:** `needs_verification`.
- **measurable_proxy:** экспрессия маркера сенесценции; в модели — `cellular_senescence`.
- **model_abstraction_candidate:** `cellular_senescence`, `cancer_prone` (защитная ось safety-модели).
- **priority:** P1 (в роли безопасности, не омоложения).
- **status:** `candidate_only`.
- **falsification_criterion:** подавление оси, якобы дающее омоложение, неотличимо от роста `cancer_prone` в модели (проверка `safe` критерия).

### 6. CDKN1A / p21

- **name:** `CDKN1A_p21`
- **type:** gene / tumor-suppressor
- **biological_role:** ответ на повреждение ДНК, остановка цикла, апоптоз/сенесценция (`needs_verification`).
- **aging_evidence:** роль в старении и регенерации — `needs_verification`.
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** косвенный, через баланс «ремонт vs деление» (`needs_verification`).
- **cancer_risk:** подавление — риск; активация — задержка регенерации (`needs_verification`).
- **human_relevance:** `needs_verification`.
- **measurable_proxy:** fraction остановленных клеток; в модели — `dna_damage`, `cancer_prone`.
- **model_abstraction_candidate:** `dna_damage`, `cancer_prone`.
- **priority:** P2.
- **status:** `candidate_only`.
- **falsification_criterion:** любой «выигрыш» от модуляции исчезает при учёте `cancer_prone` (net-эффект неотличим от нуля).

### 7. TP53

- **name:** `TP53`
- **type:** gene / tumor suppressor
- **biological_role:** контроль повреждения ДНК, апоптоз, сенесценция, геномная стабильность (`needs_verification`).
- **aging_evidence:** доза/активность p53 связана с балансом защиты и старения (`needs_verification`).
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** прямого нет; это ось безопасности, а не омоложения.
- **cancer_risk:** низкий при сохранении функции (потеря — риск); хроническая гиперактивация — цена регенерации (`needs_verification`).
- **human_relevance:** высокая для safety-модели — `needs_verification` по частотам.
- **measurable_proxy:** частота апоптоза/остановок; в модели — `cancer_prone`, `dna_damage`.
- **model_abstraction_candidate:** `cancer_prone` (центр safety-слоя Stage 11), `dna_damage`.
- **priority:** P0 (обязательная ось безопасности любого контура).
- **status:** `candidate_only`.
- **falsification_criterion:** кандидатный контур не может пройти `safe`, если его эффект требует подавления p53-ответа в модели (см. kill criterion 1).

### 8. OSK / OCT4 / SOX2 / KLF4

- **name:** `OSK_OCT4_SOX2_KLF4`
- **type:** transcription factor set (partial reprogramming class)
- **biological_role:** факторы плюрипотентности; кратковременное/циклическое экспрессирование заявлена как частичное восстановление эпигенетической информации без полной де-дифференцировки (`needs_verification`).
- **aging_evidence:** частичное репрограммирование в доклинике заявлено как обратимое омоложение нескольких тканей (`needs_verification`).
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** самый прямой заявленный канал омоложения в реестре — `needs_verification` (доклиника, не человек).
- **cancer_risk:** **высокий**: тератомы, де-дифференцировка, онкогенная репрограммация (`needs_verification`).
- **human_relevance:** доклинические модели; человек — `needs_verification`.
- **measurable_proxy:** эпигенетический возраст/планы экспрессии; в модели — `epigenetic_drift` + новый plasticity-канал.
- **model_abstraction_candidate:** `epigenetic_drift`, `epigenetic_plasticity_restoration` (Stage 8 P0 gap), контуры A и E.
- **priority:** P0.
- **status:** `candidate_only`.
- **falsification_criterion:** в модели сброс пластичности без онко-цены даёт тривиальный сдвиг метрик (ложный выигрыш) — тогда кандидат отбрасывается как небезопасный; либо сдвиг не выходит за Stage 7 noise.

### 9. MYC (осторожно)

- **name:** `MYC`
- **type:** oncogene / transcription factor
- **biological_role:** пролиферация, метаболизм, транскрипционный амплификатор; компонент наборов репрограммирования (`needs_verification`).
- **aging_evidence:** противоречивое: роль в старении и клеточном обновлении — `needs_verification`.
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** только как компонент коктейля, никогда как самостоятельный target (`needs_verification`).
- **cancer_risk:** **критический**: классический онкоген (`needs_verification`).
- **human_relevance:** `needs_verification`.
- **measurable_proxy:** пролиферативный индекс; в модели — `cancer_prone` (жёсткий лимит).
- **model_abstraction_candidate:** `cancer_prone` (только как ограничитель), `stem_exhaustion`.
- **priority:** P3.
- **status:** `candidate_only`, прямая активация — `rejected_for_now` до safety-модели Stage 11.
- **falsification_criterion:** любая конфигурация с MYC-активацией в модели выходит за допустимый `cancer_prone` бюджет — кандидат убивается немедленно (kill criterion 1/2).

### 10. AMPK

- **name:** `AMPK`
- **type:** kinase / energy sensor
- **biological_role:** энергетический сенсор, катаболизм, активация аутофагии, метаболический гомеостаз (`needs_verification`).
- **aging_evidence:** активация AMPK связывают с модуляцией метаболического старения (`needs_verification`).
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** косвенный, через аутофагию/протеостаз (`needs_verification`).
- **cancer_risk:** контекст-зависимый (метаболический контроль vs выживание) (`needs_verification`).
- **human_relevance:** `needs_verification`.
- **measurable_proxy:** энергетический статус клетки; в модели — `mitochondrial_dysfunction`, `proteostasis_loss`.
- **model_abstraction_candidate:** `proteostasis_loss`, `mitochondrial_dysfunction`, `energy_coupled_repair_autophagy`, контур C.
- **priority:** P1.
- **status:** `candidate_only`.
- **falsification_criterion:** энергетический budget не различим от текущего `repair_ceiling` (тот же провал, что и у Stage 8 P3) — тогда кандидат снимается.

### 11. NAD+ / NAMPT

- **name:** `NAD_NAMPT`
- **type:** metabolite / rate-limiting enzyme axis
- **biological_role:** кофактор окислительно-восстановительных и NAD+-зависимых реакций; ось NAD+ → сиртуины/PARP (`needs_verification`).
- **aging_evidence:** возрастное снижение NAD+ и его восстановление — `needs_verification`.
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** заявляется косвенный, системный (`needs_verification`).
- **cancer_risk:** двусторонний: репарация vs метаболизм опухоли (`needs_verification`).
- **human_relevance:** добавки/прекурсоры изучаются на людях — `needs_verification` (результаты в репозитории отсутствуют).
- **measurable_proxy:** уровень/восстановление NAD+; в модели — `mitochondrial_dysfunction`, `dna_damage` (PARP-конкуренция).
- **model_abstraction_candidate:** `mitochondrial_dysfunction`, `dna_damage`, контур C.
- **priority:** P1.
- **status:** `candidate_only`.
- **falsification_criterion:** восстановление оси не сдвигает репаративные метрики в модели при фиксированном `repair_ceiling` (неотличимо от плацебо-эффекта параметра).

### 12. NF-kB

- **name:** `NF_kb`
- **type:** transcription factor complex (inflammation)
- **biological_role:** регуляция воспалительного ответа, иммунная сигнализация (`needs_verification`).
- **aging_evidence:** хроническое воспаление как драйвер старения (inflammaging) — `needs_verification`.
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** подавление заявлена как снижение воспалительной нагрузки, не как омоложение (`needs_verification`).
- **cancer_risk:** подавление — риск потери иммунного надзора (`needs_verification`).
- **human_relevance:** `needs_verification`.
- **measurable_proxy:** провоспалительные маркеры; в модели — `chronic_inflammation`.
- **model_abstraction_candidate:** `chronic_inflammation`, контур B/D.
- **priority:** P2.
- **status:** `candidate_only`.
- **falsification_criterion:** подавление канала снижает `chronic_inflammation` в модели, но `biological_age_slope`/binding не меняются (Stage 6F-паттерн) — кандидат не является переключателем.

### 13. IL-6 / inflammaging

- **name:** `IL6_inflammaging`
- **type:** cytokine axis (chronic inflammation)
- **biological_role:** интерлейкин-6 и хроническое низкоуровневое воспаление старения (`needs_verification`).
- **aging_evidence:** inflammaging как системный маркер старения — `needs_verification`.
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** снижение нагрузки, не омоложение (`needs_verification`).
- **cancer_risk:** двусторонний (надзор vs регенерация) (`needs_verification`).
- **human_relevance:** плазменные маркеры измеримы у человека — `needs_verification`.
- **measurable_proxy:** концентрация цитокина; в модели — `chronic_inflammation`.
- **model_abstraction_candidate:** `chronic_inflammation`, `systemic_circulation_pool` (Stage 8 P1).
- **priority:** P2.
- **status:** `candidate_only`.
- **falsification_criterion:** маркер сдвигается, но никакой driver/attribution в модели не следует за ним — маркер не является управляемой точкой.

### 14. ATG5 / BECN1 / MAP1LC3

- **name:** `ATG5_BECN1_MAP1LC3`
- **type:** autophagy machinery genes
- **biological_role:** ключевые компоненты аутофагического клиренса (`needs_verification`).
- **aging_evidence:** аутофагия как механизм поддержания клеточного гомеостаза при старении — `needs_verification`.
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** косвенный через клиренс повреждённых компонентов (`needs_verification`).
- **cancer_risk:** двусторонний: подавление аутофагии — риск накопления повреждений и опухолевого роста (`needs_verification`).
- **human_relevance:** `needs_verification`.
- **measurable_proxy:** flux аутофагии; в модели — `proteostasis_loss` (классы агрегатов Stage 8 P6).
- **model_abstraction_candidate:** `proteostasis_loss`, `aggregate_class_partition`, контур B `damage_clearance_circuit`.
- **priority:** P0.
- **status:** `candidate_only`.
- **falsification_criterion:** усиление клиренса в модели не различимо от существующих senolytic/clearance вмешательств Stage 5C–6C (нового канала нет — тогда не master switch).

### 15. BRCA1 / ATM / ATR / PARP1

- **name:** `BRCA1_ATM_ATR_PARP1`
- **type:** DNA damage response / repair genes
- **biological_role:** сенсоры и репарация повреждений ДНК, контрольных точек цикла (`needs_verification`).
- **aging_evidence:** дефицит репарации ускоряет признаки старения — `needs_verification`.
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** прямого нет; рост ёмкости ремонта (`needs_verification`).
- **cancer_risk:** гиперактивация/ингибиторы (PARPi) — контекстно-зависимый, существенный (`needs_verification`).
- **human_relevance:** хорошо измеримая клиническая генетика — `needs_verification`.
- **measurable_proxy:** частота/тип повреждений ДНК; в модели — `dna_damage`, `repair_ceiling`.
- **model_abstraction_candidate:** `dna_damage`, `repair_ceiling`, `conversion` (irreversible flux Stage 6C).
- **priority:** P2.
- **status:** `candidate_only`.
- **falsification_criterion:** рост репаративной ёмкости упирается в `repair_ceiling`/энергетический бюджет и не сдвигает binding (`biological_age_slope`) — потолок, а не переключатель.

### 16. PGC-1alpha

- **name:** `PGC1A`
- **type:** transcriptional coactivator (mitochondrial biogenesis)
- **biological_role:** митохондриальный биогенез, окислительный метаболизм, глюконеогенез (`needs_verification`).
- **aging_evidence:** митохондриальная дисфункция как драйвер старения — `needs_verification`.
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** косвенный (`needs_verification`).
- **cancer_risk:** контекст-зависимый (метаболизм опухоли) (`needs_verification`).
- **human_relevance:** `needs_verification`.
- **measurable_proxy:** митохондриальная функция/биомаркеры; в модели — `mitochondrial_dysfunction`.
- **model_abstraction_candidate:** `mitochondrial_dysfunction`, контур C.
- **priority:** P2.
- **status:** `candidate_only`.
- **falsification_criterion:** митохондриальный сдвиг в модели не выходит за Stage 7 noise по `biological_age_slope` и не меняет binding.

### 17. Stem niche factors

- **name:** `stem_niche_factors`
- **type:** factor set (stem cell niche signaling)
- **biological_role:** сигналы ниши: покой, дифференцировочная координация, регенеративный ответ стволовых пулов (`needs_verification`).
- **aging_evidence:** дисфункция ниши как механизм старения — `needs_verification` (Stage 8 mismatch `stem_count_without_niche`).
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** возможный системный через регенерацию (`needs_verification`).
- **cancer_risk:** высокий: стволовые сигналы + рост = риск (`needs_verification`).
- **human_relevance:** `needs_verification`.
- **measurable_proxy:** регенеративный ответ; в модели — `stem_exhaustion`.
- **model_abstraction_candidate:** `stem_exhaustion`, `stem_cell_niche_quality` (Stage 8 P2), контур D `systemic_renewal_circuit`.
- **priority:** P1.
- **status:** `candidate_only`.
- **falsification_criterion:** в модели пара `pool × niche_quality` не даёт регенеративного ответа при фиксированном pool (Stage 8 P2 провалена) — канал лишний.

### 18. Epigenetic maintainers: DNMT3A / TET2 / EZH2 / HUSH / lamins / histones

- **name:** `epigenetic_maintainers_DNMT3A_TET2_EZH2_HUSH_lamins_histones`
- **type:** gene set / chromatin machinery
- **biological_role:** метилирование, хроматиновая упаковка, ядерная ламина, наследование эпигенетических состояний (`needs_verification`).
- **aging_evidence:** эпигенетический дрейф как драйвер старения (в модели — доминирующий канал `epigenetic_drift`) — `needs_verification` по биологическим источникам; в модели dominant частично подтверждён (Stage 6E attribution).
- **longevity_evidence:** `needs_verification`.
- **rejuvenation_potential:** прямой заявленный через сброс эпигенетической информации (`needs_verification`).
- **cancer_risk:** высокий: EZH2/TET2/DNMT3A — частые онко-мишени (`needs_verification`).
- **human_relevance:** `needs_verification`.
- **measurable_proxy:** эпигенетические планы/метилирование; в модели — `epigenetic_drift`, `information_debt`.
- **model_abstraction_candidate:** `epigenetic_drift`, `information_debt`, `epigenetic_plasticity_restoration`, контур A `epigenetic_restoration_circuit`.
- **priority:** P1.
- **status:** `candidate_only`.
- **falsification_criterion:** сброс эпигенетического состояния в модели даёт выигрыш только через `information_debt`-переименование без изменения механики (тот же провал, что и reset без цены) — кандидат отбрасывается.

### 19. DNA repair axis (см. также §15)

- **name:** `repair_axis_extended`
- **type:** note (сводная запись, не отдельный ген)
- **biological_role:** — (см. `BRCA1_ATM_ATR_PARP1` и `CDKN1A_p21`).
- **aging_evidence:** —
- **longevity_evidence:** —
- **rejuvenation_potential:** —
- **cancer_risk:** —
- **human_relevance:** —
- **measurable_proxy:** aggregate `dna_damage`.
- **model_abstraction_candidate:** `dna_damage`, `repair_ceiling`.
- **priority:** P2.
- **status:** `candidate_only`.
- **falsification_criterion:** — (см. §15).

---

## §2. Кандидатные контуры (minimal circuits)

| id | Контур | Цель | Главный риск | Наблюдаемый proxy | Модельный proxy | Минимальный эксперимент | Приоритет |
|---|---|---|---|---|---|---|---|
| A | `epigenetic_restoration_circuit` | восстановление регуляторной пластичности | онкориск сброса, ложный выигрыш без цены | эпигенетический возраст/планы | `epigenetic_drift`, `information_debt`, plasticity-канал | vарьирование reset-скорости с онко-ценой: сдвиг binding/attribution vs Stage 7 noise | P0 |
| B | `damage_clearance_circuit` | клиренс повреждённых компонентов | истощение, чрезмерный клиренс | flux клиренса, доля повреждённых компонентов | `proteostasis_loss`, `cellular_senescence`, `aggregate_class_partition` | два типа клиренса × классы нагрузки: различимость от Stage 5C–6C clearance | P0 |
| C | `metabolic_support_circuit` | энергетическая поддержка ремонта | неотличимость от `repair_ceiling`, метаболическая перегрузка | энергетический статус/бюджет | `mitochondrial_dysfunction`, `proteostasis_loss`, `energy_coupled_repair_autophagy` | различимость budget от текущего ceiling в пределах Stage 7 сетки | P1 |
| D | `systemic_renewal_circuit` | системное обновление (ниша + циркулирующие факторы) | системная перегрузка, клон доминирование | регенеративный ответ органов | `stem_exhaustion`, `stem_cell_niche_quality`, `systemic_circulation_pool` | pool × niche_quality при фиксированном pool; системная vs локальная компонента | P1 |
| E | `tumor_suppressed_rejuvenation_circuit` | омоложение под жёстким онко-контролем | потеря контроля = тератома/опухоль | онко-бюджет + эффект омоложения | `cancer_prone` (лимит), `cellular_senescence`, `epigenetic_drift` | тот же сброс, что и в A, но с обязательным safety-гейтом: эффект при допустимом `cancer_prone` бюджете | P0 |

Все контуры — `candidate_only`. Ни один не симулирован. Ни один не
является заявлением об эффективности в человеке.

## §3. Как читать статусы

- `candidate_only` — зарегистрирован, не проверен, не симулирован.
- `needs_verification` — присвоен каждому внешнему биологическому
  утверждению: источника в репозитории нет.
- `rejected_for_now` — отклонён до выполнения условия (у MYC:
  прямая активация до safety-модели Stage 11).
- `verified_in_repo` — в этом реестре не присвоен ни одной записи
  по внешним основаниям; единственные `verified_in_repo`-факты —
  модельные результаты Stage 5–8 (`docs/EXTERNAL_EVIDENCE_ANCHORS.md`).
