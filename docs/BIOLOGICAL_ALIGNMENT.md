# BIOLOGICAL_ALIGNMENT.md — Биологическое выравнивание модели (Stage 8)

> Это НЕ биологическая валидация модели.
> Это alignment-артефакт: сопоставление конструктов текущей абстрактной
> модели с биологическими направлениями 2022–2026.
> Все направления без источника в репозитории помечены
> `needs_verification`.
> HYP-0 остаётся `hypothesis_not_proven` (гипотеза не доказана).
> Candidate mechanisms не симулированы на этом этапе.

Машинно-читаемая версия: `experiments/configs/stage8_biological_alignment_manifest.json`.
Валидатор: `src/longevity/research/biological_alignment.py`.
Классификация Stage 8: `mechanistic_extension_required`
(требуется механистическое расширение), уверенность средняя.

## 1. Модельные конструкты

| Конструкт | Что означает в модели | Биологический аналог | Степень согласованности |
|---|---|---|---|
| `conversion_flux` | Переклассификация reversible → irreversible | Накопление необратимых повреждений | Частично: канала пластичности нет |
| `independent_accrual` | Необратимое накопление мимо reversible | Мутации, потеря информации, энтропия ниши | Частично: классы повреждений слиты |
| `repair_ceiling` | Суммарный лимит irreversible repair | Репарация, аутофагия, протеостаз | Частично: нет энергетического coupling |
| `biological_age_slope` | Наклон биовозраста после зрелости | Темп старения организма | Частично: линейный slope, damage/adaptation слиты |
| `information_debt` | Глобальный пул [0,1] | Потеря эпигенетической информации | Частично: без механизма восстановления |
| `proteostasis_metabolic` | Группа драйверов bio-age attribution | Протеостаз + метаболизм + энергия | Частично: классы агрегатов слиты |
| `stem_exhaustion` | Драйвер и ledger irreversible | Истощение стволовых и ниши | Частично: ниши нет, только пул |
| abstract tissue | Компартменты + replacement policy | Тканевый гомеостаз | Абстракция без внешней привязки |
| abstract organ | Два тканевых модуля + shared capacity | Орган как система | Абстракция без внешней привязки |
| organ network | Рёбра, feedback, hard limits | Межорганные связи | Частично: системного пула нет |
| reversibility boundary probe | Диагностические аблации 6D–6F | Нет прямого аналога (инструмент) | Инструмент, не биология |
| `robust_diffuse_wall` | Итог Stage 7 | Нет прямого аналога (вывод) | Вывод внутри модели |

Степени согласованности: ни один конструкт не имеет количественных
внешних точек привязки (`quantitative_rate_anchors` — `unavailable`).
Качественные соответствия подтверждены структурой кода и документов
(`verified_in_repo`), биологические направления — `needs_verification`.

## 2. Сопоставление с биологией 2022–2026

Используются восемь направлений из постановки Stage 8
(иерархическая сеть hallmarks; эпигенетическая пластичность;
системная коммуникация; ниша стволовых; протеостаз–энергия;
damage/adaptation сплит; нелинейные волны; классы агрегатов).
Каждое направление в манифесте — отдельный anchor со статусом
`needs_verification`, потому что в каталоге репозитория
(`docs/DATA_SOURCES.md`, `research/literature/`,
`research/evidence/`) проверяемых источников по ним нет.
Исключение — сам факт наличия конструктов в коде (`verified_in_repo`).

Это честная фиксация: направления используются как ориентир для
выравнивания, а не как доказанные факты внутри проекта.

## 3. Mismatches

Девять расхождений в манифесте (раздел `mismatches`), главные:

- `linear_slope_vs_age_waves` (high): линейный slope против волн/порогов → `add_mechanism_stage9`;
- `missing_epigenetic_plasticity` (high): нет канала пластичности → `add_mechanism_stage9`;
- `autonomous_organs_no_systemic_pool` (high): нет системного пула → `add_mechanism_stage9`;
- `no_quantitative_calibration_anchors` (high): нет количественной привязки → `collect_data`;
- `stem_count_without_niche`, `repair_decoupled_from_energy`, `flat_driver_hierarchy` (medium) → `add_mechanism_stage9`;
- `blended_bio_age_damage_adaptation` (medium) → `redefine_metric`;
- `lumped_aggregate_classes` (medium) → `collect_data`.

Критических (`critical`) расхождений не заявлено: прямых
противоречий установленной биологии проект не утверждает, все
внешние направления помечены `needs_verification`.

## 4. Anchors и их status

- 5 якорей `verified_in_repo` (конструкты и вычислительные итоги 6/7;
  confidence `expert-plausible` — это суждение о соответствии, а не
  данные).
- 7 якорей `needs_verification` (биологические направления;
  confidence `literature-backed` — литература существует в мире, в
  репозитории не проверена).
- 1 якорь `unavailable` (количественные точки привязки скоростей).

Правило: `needs_verification` никогда не выдаётся как `data-backed`;
`data-backed` требует `verified_in_repo` с непустым `source_ref`.
Проверяется валидатором и тестами.

## 5. Что это не утверждает

- Это не биологическая валидация модели.
- HYP-0 остаётся `hypothesis_not_proven` (гипотеза не доказана).
- Candidate mechanisms не симулированы на этом этапе.
- Ничего из этого не является доказательством бессмертия,
  омоложения человека или достижимости v5.
- robust_diffuse_wall остаётся выводом внутри текущей абстракции и
  проверенной диагностической сетки.
