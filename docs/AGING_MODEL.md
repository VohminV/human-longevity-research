# AGING_MODEL.md — Механистический слой старения (Stage 5C)

> Это НЕ модель биологического старения человека. Порядковые скорости,
> абстрактные годы, некалиброванные параметры, нет анатомии и нет
> биологической валидации. `robust_bounded_degradation_v2 = true` — это
> модельный флаг, а не доказательство бессмертия. Бессмертие —
> `hypothesis_not_proven` в каждом результате.

## 1. Зачем Stage 5C

Stage 5B показал честный отрицательный результат: robust bounded
degradation не достигается ни в одной проверенной политике, и
единственное связывающее ограничение во всех 70 ячейках —
`biological_age_slope`. Рак, воспаление, фиброз, резерв, нейронная
непрерывность, стоимость вмешательств и стрессы нигде не являются
первым нарушителем.

Но в Stage 5B `biological_age` был феноменологической переменной: один
агрегированный тренд, который политика может лишь замедлять. На вопрос
«какой именно процесс старения не даёт тренду остановиться и можно ли
его обратить» такая модель ответить не может. Stage 5C разлагает
биологический возраст на драйверы с собственной динамикой накопления,
репарации и обратимости и проверяет, существует ли robust политика,
способная удержать драйверы в bounded или negative режиме без
недопустимого роста рака, потери нейронной непрерывности, истощения
резерва или системного коллапса.

Научная рамка — каталог механизмов из `docs/CELLULAR_AGING.md`.

## 2. Драйверы старения

Реализация: `src/longevity/model/aging.py`. В v0 включены 8 драйверов:

- `dna_damage` — накопление повреждений ДНК;
- `epigenetic_drift` — эпигенетический дрейф;
- `proteostasis_loss` — потеря протеостаза;
- `mitochondrial_dysfunction` — митохондриальная дисфункция;
- `cellular_senescence` — клеточная сенесценция;
- `stem_exhaustion` — истощение стволового пула;
- `chronic_inflammation` — хроническое воспаление;
- `cancer_prone` — онкологическая предрасположенность.

Зарезервированы как расширения (валидация явно отвергает):
`telomere_attrition` (проксируется через `stem_exhaustion`),
`altered_intercellular_communication`, `fibrosis_prone`.

Каждый драйвер (`AgingDriverState`, операционально — словарь параметров +
`damage` в состоянии):

- `damage` в [0, 1] — нормализованное накопленное повреждение;
- `repair_capacity >= 0` — скорость фоновой репарации;
- `reversibility` в [0, 1] — доля запрошенного обращения, реализуемая
  вмешательством;
- `contribution_to_biological_age >= 0` (`contribution`) — вес в агрегации;
- `base_aging_rate >= 0` — базовая скорость накопления;
- `stage_multiplier` — через `_STAGE_AGING_MULT` модели организма:
  до зрелости накопление минимально или нулевое (embryo/fetal — 0),
  после `adult_homeostasis` — положительно по умолчанию;
- `reversal_saturation` — шкала diminishing returns;
- `floor` в [0, 1] — физиологический минимум драйвера;
- `adult_reference` — нормализация вклада.

Состояние: `OrganismState.aging = {"drivers": {name: {"damage",
"reversal_applied_total"}}, "age_reversal_events": [...]}`.
При `aging_mechanism_model = "none"` поле `None` и поведение численно
идентично Stage 5B.

## 3. Biological age из драйверов

При `aging_mechanism_model = "mechanistic_drivers"`:

```text
biological_age = adult_age_setpoint + sum(contribution_i * damage_i / adult_reference_i)
```

`adult_age_setpoint` — абстрактный взрослый биологический возраст
(дефолт 25 условных лет). По умолчанию действует пол:

```text
biological_age_floor = adult_age_setpoint
```

Rejuvenation означает возврат систем к взрослому функциональному
setpoint, а не эмбриональное сбрасывание. Опция
`allow_sub_adult_biological_age = true` технически разрешает уход ниже
setpoint, но помечается как non-physiological exploratory mode.
По умолчанию `false`.

Драйверы также связаны с остальной динамикой: неразрешённое повреждение
драйверов протекает в повреждение витальных систем
(`driver_burden * 0.03` в `_aging_step`), а прямое снижение
`biological_age` вмешательством в mechanistic-режиме пересчитывается из
драйверов — «бесплатный» сброс bio без ремонта драйверов невозможен.

## 4. Динамика драйверов

```text
damage_i[t+1] = damage_i[t] + accumulation_i - repair_i - reversal_i
accumulation_i = base_aging_rate_i * stage_mult * (1 + global_damage) * dt
repair_i      = min(damage_i, repair_capacity_i * reserve_factor * dt)
reversal_i    = effective_reversal(requested, damage, reversibility, saturation)
```

- `reserve_factor` — текущий `functional_reserve` в [0, 1]: без резерва
  фоновая репарация останавливается;
- `effective_reversal = requested * reversibility * max(0, 1 - damage / saturation)` —
  diminishing returns: тот же импульс даёт всё меньше по мере снижения
  damage; свести драйвер к floor бесплатно нельзя;
- floor соблюдается всегда: `damage >= floor`.

## 5. Вмешательства против драйверов

Реализация: `src/longevity/model/intervention.py` (12 новых типов поверх
8 базовых Stage 5A). У каждого — польза И цена, diminishing returns,
cooldown через `interval`/`refractory`, constraints. Кратко:

| Вмешательство | Чинит | Цена / риск |
|---|---|---|
| `dna_repair_enhancement` | `dna_damage` | малый cancer delta, расход резерва |
| `epigenetic_reprogramming_pulse` | `epigenetic_drift` (+частично proteostasis/senescence) | высокий cancer risk, neural continuity loss, teratogenic proxy до зрелости |
| `proteostasis_enhancement` | `proteostasis_loss` | расход metabolic/immune ресурсов, снижает senescence/inflammation |
| `mitochondrial_turnover` | `mitochondrial_dysfunction` | transient cancer risk, расход резерва |
| `telomere_maintenance` | `stem_exhaustion` | сильный рост `cancer_prone`, только с surveillance |
| `senolytic_clearance` | `cellular_senescence` | расход immune/reserve, снижает inflammation |
| `senomorphic_modulation` | senescence/inflammation без удаления клеток | остаточный cancer risk |
| `stem_niche_restoration` | `stem_exhaustion` + reserve | рост `cancer_prone`, требует support |
| `anti_inflammatory_resolution` | `chronic_inflammation` (+fibrosis) | чрезмерность → immune/infection/cancer риск |
| `fibrosis_reversal_support` | fibrosis через inflammation | дорого, расход резерва |
| `cancer_surveillance_boost` | `cancer_prone`/burden | расход immune ресурсов, не бесплатно |
| `neural_protective_maintenance` | continuity (не драйвер) | расход резерва, защищает при reprogramming |

Rejuvenation-политики по умолчанию disabled до `adult_homeostasis`
(`allow_pre_adult = false`); срабатывание до зрелости с
`allow_pre_adult = true` несёт teratogenic drift proxy
(+0.002 к epigenetic drift на единицу intensity).

Предустановленные mechanistic-наборы политик (конфиги
`experiments/configs/organism_aging_*.json`): natural baseline, 6
одиночных (dna/epigenetic/proteostasis/mitochondrial/senolytic/stem),
combined, adaptive threshold по `driver:*` биомаркерам, neural
preserving, organ-inspired (уроки Stage 4D: не pruning без системной
причины + отдельный recovery + constraints).

## 6. Binding driver analysis

Реализация: `src/longevity/analysis/aging_metrics.py::summarize_drivers`.
Для каждого драйвера — slope после зрелости (наименьшие квадраты) и
финальное damage. `dominant_binding_driver` — драйвер с максимальным
contribution-взвешенным положительным slope; ties — детерминированно по
sorted имени. `binding_driver_sequence` — упорядоченный список.
Без driver-состояния — нейтральный `has_drivers: False`, не ошибка
(backward compatibility).

## 7. Robust bounded degradation v2

Строгий критерий поверх индикатора Stage 5B (который сохранён без
изменений). `robust_bounded_degradation_v2 = true` для политики, если:

1. `success_rate_bounded_v2 >= 0.8` по сидам;
2. `worst_case_driver_slope <= eps_driver_worst`;
3. `worst_case_biological_age_slope <= eps_bio_worst`;
4. hard limits (cancer/inflammation/fibrosis/continuity/reserve/vital)
   в худшем случае;
5. нет `terminal_decline`;
6. ни один драйвер не имеет runaway trend, даже если агрегированный
   bio slope формально мал.

Это operational model criterion, не доказательство бессмертия.

## 8. Результаты v0 (seed 42, в рамках модели)

| Политика | lifespan | bio slope | final bio | dominant | cancer_auc |
|---|---|---|---|---|---|
| legacy none (= Stage 5B) | 68.0 | 1.069 | 68.2 | — | 1.14 |
| mechanistic baseline | 66.8 | 0.736 | 61.1 | cellular_senescence | 1.08 |
| dna only | 69.2 | 0.633 | 57.7 | cellular_senescence | 1.28 |
| epigenetic only | 67.0 | 0.645 | 56.9 | cellular_senescence | 1.45 |
| proteostasis only | 67.0 | 0.691 | 58.9 | cellular_senescence | 1.09 |
| mitochondrial only | 68.0 | 0.682 | 59.1 | cellular_senescence | 1.35 |
| senolytic only | 67.0 | 0.620 | 55.8 | epigenetic_drift | 1.09 |
| stem niche only | 67.0 | 0.685 | 58.8 | cellular_senescence | 1.39 |
| anti-inflammatory only | 67.0 | 0.647 | 56.9 | cellular_senescence | 1.31 |
| combined | 70.8 | 0.417 | 47.3 | epigenetic_drift | 0.68 |
| adaptive threshold | 67.0 | 0.622 | 52.8 | chronic_inflammation | 1.12 |
| neural preserving | 70.0 | 0.592 | 56.3 | cellular_senescence | 0.57 |
| organ-inspired | 69.8 | 0.517 | 52.5 | epigenetic_drift | 0.57 |

Чтение строго внутримодельное:

1. **Legacy compatibility**: `aging_mechanism_model = none` воспроизводит
   Stage 5B бит-в-бит (68.0/61.8 cascade).
2. **Baseline**: без вмешательств доминирует `cellular_senescence`;
   bio slope 0.736 >> eps.
3. **Одиночные**: лучший slope — senolytic (0.620); epigenetic
   reprogramming даёт высокий cancer (1.45) и низший neural min (0.745);
   telomere/stem — cancer 1.39. Diminishing returns не дают свести
   драйвер к floor.
4. **Combined** — лучший фиксированный (70.8, bio 47.3, cancer 0.68),
   но slope 0.417 >> eps; доминирование смещается на
   `epigenetic_drift` — необработанный драйвер становится binding.
5. **Robust search mini** (12 комбо × 3 сида): лучший — dna intensity
   1.5 + частые schedules (72.2/65.2); v2 — false везде; pareto 4.
6. **Binding sweep** (27 точек × 3 сида): 18 — `epigenetic_drift`,
   9 — `cellular_senescence`; worst driver slope до 0.0104.
7. **Stress** (3 runs × 6 scenarios × 3 seeds): ranking стабилен
   (combined ~70.8 везде); toxicity бьёт сильнее (69.0); bounded v2 —
   false везде.
8. **HYP-0**: `hypothesis_not_proven`. Candidate robust bounded
   degradation v2 не найден; доминирующее ограничение —
   `cellular_senescence` / `epigenetic_drift` в зависимости от политики.

## 9. Эмерджентные драйверы (Stage 6A)

Stage 6A делает часть драйверов частично эмерджентной из reduced organ
proxies (`emergent_weights`): `cellular_senescence` (0.5),
`chronic_inflammation` (0.5), `cancer_prone` (0.3), `stem_exhaustion`
(0.3), `mitochondrial_dysfunction` (0.2), `proteostasis_loss` (0.2);
`dna_damage` и `epigenetic_drift` остаются феноменологическими (у прокси
нет представления генома/эпигенома). Смешивание —
`(1-w)*phenomenological + w*emergent`, границы и floor соблюдаются.
Детали — `docs/ORGAN_BACKED_ORGANISM_MODEL.md` §4.

## 10. Network-derived biological age и hard limits (Stage 6B)

Stage 6B добавляет `biological_age_network = adult_setpoint +
contribution(drivers, organ deficit, resource shortfall, feedback,
mutation, information loss, fibrosis, cancer, cascade)` с floor на
adult setpoint (`allow_sub_adult_network_age=true` — exploratory mode).
Legacy `biological_age` сохранён. Hard limits (energy, information,
mutation ceiling, irreversible damage, niche, toxicity) делают
«омолодить всё бесплатно» невозможным. Детали —
`docs/ORGAN_NETWORK_MODEL.md` §§4–5.

## 11. Reversible / irreversible split и repair ceiling (Stage 6C)

Stage 6C разделяет каждый драйвер и органный прокси на reversible и
irreversible компоненты (`damage = reversible + irreversible`):
conversion переклассифицирует массу под действием воспаления, energy /
repair shortfall, cascade, niche и toxicity; irreversible repair возможен
только в пределах `repair_ceiling` с ценой, риском и diminishing
returns и никогда ниже floor. `biological_age_reversibility` получает
динамический irreversible floor. Детали — `docs/REVERSIBILITY_MODEL.md`.

## 12. Ограничения
Абстрактный организм; порядковые скорости; операциональные пороги;
малые сетки и n ≤ 3 (описательно, не значимость); некалиброванные
параметры драйверов; нет биологической валидации; HYP-0 — только
формализация. Отсутствие bounded degradation — валидный результат:
граница текущей модели, а не опровержение гипотезы в реальности. Даже
наличие candidate policy не доказывало бы бессмертие — только
операциональный флаг внутри абстрактной модели.

## 13. Information Preservation Model: epigenetic backup (Stage 9 prototype)

Сдвиг рамки от «Repair Model» (чинить урон после того, как он лёг) к
«Information Preservation Model»: организм несёт замороженный
`reference_epigenome` (слепок при `adult_age_setpoint`) и канал
чтения/восстановления, который откатывает шенноновскую энтропию
эпигенома к референсу, не трогая идентичность клеток.

Уравнения (операциональные, `src/longevity/model/epigenetic_backup.py`):

```text
dH_epi/dt = Noise_Generation - Repair_Capacity - Backup_Restore_Rate
Noise_Generation = base * (1 + te_coupling * (0.5*D_epi + 0.5*Infl)
                              + metabolic_coupling * D_mito)
```

- `D_epi` — повреждение драйвера `epigenetic_drift` (прокси дерепрессии
  LINE-1/Alu), `Infl` — воспаление, `D_mito` — повреждение драйвера
  `mitochondrial_dysfunction` (метаболические побочные продукты).
- `Repair_Capacity` — эндогенное поддержание (потолок: чинить нечего
  нельзя ниже нуля). `Backup_Restore_Rate` — событийный (только пульсы
  отката, в шаге равен нулю).
- Мета-драйвер: 8-драйверный леджер не тронут; энтропия входит в
  биовозраст аддитивно: `bio = aggregate_8(drivers) + w_entropy * H_epi`,
  плюс шумовое эхо `dD_epi += H_epi * drift_noise_coupling`.
- Стекло чтения: `proximity = H_epi / wall_read_threshold`;
  `readable = H_epi < wall_read_threshold`; fidelity падает к
  `min_read_fidelity` по мере приближения к стенке
  (`Information_Wall_Proximity` — `longevity.analysis.boundary_metrics`).
- Санитированный геном (`genome_sanitized=true`, прокси удаления
  ретротранспозонов): накопление `dna_damage` и фиксация мутаций × 0.1
  (−90% эндогенного мутагенеза).

Гейт безопасности (fail-closed, порядок детерминирован):

```text
burden = 0.6*mutation_fixation + 0.4*D_dna
if burden > apoptosis_threshold:  synthetic_apoptosis ВМЕСТО отката
elif D_cancer_prone >= rollback_cancer_gate:  пульс ЗАБЛОКИРОВАН
else:  H_epi -> к референсному минимуму (точно, без RNG),
       ремонт D_epi (diminishing), частичный клиренс information_debt,
       БЕЗ потери identity (delta_neural_continuity = 0)
```

Критерий `robust_bounded_degradation_v6` (строже v5):
v5-условия ПЛЮС наклон энтропии ≤ eps, драйв читаем в конце,
худший наклон в допуске; отсутствие backup-блока = провал, не пас.

Честный итог прототипа (2026-10-08): механизм работает (наклон энтропии
~0.0003–0.0009 ≤ eps, стенка читаема везде, 5+ откатов и апоптозов за
прогон), но поиск 54×3 и санитированная проба v6 не дали: bio slope
~1.33–1.38 держится остальными 7 драйверами, lifespan плоский
67.5–68.8. Точечный откат одного драйвера третью стену не снимает —
тот же диффузный паттерн Stage 6F/7. HYP-0: `hypothesis_not_proven`.
