# DATA_SOURCES.md — Каталог научных источников

Каталог важных источников проекта. Правила: peer-reviewed приоритет; для каждого
важного параметра — source, DOI, PMID, год, метод, выборка, неопределённость, заметки.
Расхождения фиксируются, а не замалчиваются.

> Указанные в этом файле DOI/PMIDs собраны из первичных страниц публикаций.
> Перед использованием в печати проверяйте актуальность ссылок.

## 1. Клеточный счёт взрослого человека

| # | Ссылка | PMID | DOI | Метод | Значение |
|---|---|---|---|---|---|
| S-1 | Bianconi E. et al. «An estimation of the number of cells in the human body». Ann Hum Biol 40(6):463–471, 2013 | 23829164 | 10.3109/03014460.2013.807878 | компиляция 56 категорий клеток + расчёт | 3.72×10¹³ (SD 0.8×10¹³) |
| S-2 | Sender R., Fuchs S., Milo R. «Revised estimates for the number of human and bacteria cells in the body». PLoS Biol 14(8):e1002533, 2016 | 27541692 | 10.1371/journal.pbio.1002533 | ревизия, вклад гемопоэза | ≈3.0×10¹³ (CV 14%) |
| S-3 | Hatton I.A. et al. «The human cell count and size distribution». PNAS 120(28):e2303077120, 2023 | 37722043 | 10.1073/pnas.2303077120 | компиляция ~1200 групп клеток, 60 тканей | м 36×10¹²; ж 28×10¹²; ребёнок 17×10¹² (32 кг) |

Расхождение: 2.8–3.7×10¹³ (≈±25%). Основные причины: учёт эритроцитов, лимфоцитов,
масса репрезентативной модели. Для модели берётся диапазон (см. CELL_COUNT.md).

- Данные Hatton доступны: https://humancelltreemap.mis.mpg.de/

## 2. Новорождённый

| # | Ссылка | PMID | Значение | Метод |
|---|---|---|---|---|
| S-4 | Osgood E.E. «Development and growth of hematopoietic tissues...». Pediatrics 15(6):733–751, 1955 | 14384372 | ≈1.25×10¹² диплоидных клеток у доношенного | косвенный: масса 150-дн плода / ожидаемая масса при рождении |
| S-5 | Hirsch H.R. «The dynamics of repetitive asymmetric cell division». Mech Ageing Dev 6(5):319–332, 1977 | 895205 | цитирование Osgood; BNID 106413 | анализ |

## 3. Раннее развитие: прямые подсчёты бластоцисты

| # | Ссылка | PMID | Key данные | Метод |
|---|---|---|---|---|
| S-6 | Hardy K., Handyside A.H., Winston R.M. «The human blastocyst: cell number, death and allocation during late preimplantation development in vitro». Development 107(3):597–604, 1989 | 2612378 | д.5: 58.3±8.1 (TE 37.9±6.0, ICM 20.4±4.0); д.6: 84.4±5.7 (40.3±5.0, 41.9±5.0); д.7: 125.5±19 (80.6±15.2, 45.6±10.2) | дифференциальная метка ядер, in vitro, 181 эмбрион |

## 4. Хронология дробления (IVF-консенсус)

| # | Ссылка | DOI | Key данные |
|---|---|---|---|
| S-7 | Alpha Scientists…; ESHRE SIG Embryology. «The Istanbul consensus workshop on embryo assessment...». Hum Reprod 26(6):1270–1283, 2011 | 10.1093/humrep/der037 | 2-кл ~26–28 ч; 4-кл 44±1 ч; 8-кл 68±1 ч; морула 92±2 ч; бластоциста 116±2 ч |
| S-8 | 相关 time-lapse обзоры (например, *Hum Reprod* 2012–2015; см. PMC4831697 ниже) | — | циклы ~10–12 ч; д.3 7–8 клеток = хороший прогноз |

Доп. ссылка: «The Relationship between Cell Number, Division Behavior and
Developmental Potential of Cleavage Stage Human Embryos: A Time-Lapse Study».
PLoS One (PMC4831697), n=799 эмбрионов.

## 5. Раннее развитие: морула/бластоциста (учебные и обзорные источники)

| # | Ссылка | Данные |
|---|---|---|
| S-9 | embryology.ch (учебный ресурс Ун-та Берна), «The cleavage divisions up to the morula stage» | зигота ~16–20 ч; 2-кл ~24 ч; 4-кл ~45 ч; 8-кл ~72 ч; морула ~30 клеток ~96 ч; асинхронность делений |
| S-10 | Обзор «Early human development and stem cell-based human embryo models» (Cell Stem Cell, 2021; PMC7617107) | компактизация/морула при ~10 клетках; ранняя бластоциста ~20 клеток; поздняя бластоциста ~200 клеток к хетчингу (день 7) |
| S-11 | Carnegie staging (UNSW Embryology, Carnegie collection) | стадии 1–23 с днями и морфологией |

### 5a. Активация эмбрионального генома (ZGA/EGA) и удлинение клеточного цикла

| # | Ссылка | Key данные |
|---|---|---|
| S-19 | Perry A.C.F. et al. «The initiation of mammalian embryonic transcription: to begin at the beginning». *Trends Cell Biol* 33(5):365–373, 2023 | ZGA у человека — не «внезапно на 8-клеточной стадии», а инициируется уже в 1-клеточном эмбрионе; полный геномный переход завершается к 8-клеточной стадии. «Bulk transcription» стартует после серии редуктивных делений, когда длительность клеточного цикла растёт — феноменологическая основа фазы «пост-8-клеточного удлинения цикла» (Model B/C, `cell_cycle.phases.2`) |
| S-20 | Taubenschmid-Stowers J. et al. «8C-like cells capture the human zygotic genome activation program in vitro». *Cell Stem Cell* 29(4):602–615, 2022. PMID 35216671 | Подтверждение: мажорная ZGA человека на стадии 8 клеток; 8CLCs-программа транскриптомно повторяет 8-клеточный эмбрион (научное основание границы фаз `threshold: 2` и `threshold: 8` в `cell_cycle.phases`) |

## 6. Single-cell-RNA-seq ресурсы (vfov: захваченные клетки, не тотальные счёты)

| # | Ссылка | PMID/DOI | Клеток (после QC) |
|---|---|---|---|
| S-12 | Yan L. et al. Nat Struct Mol Biol 20:1131–1139, 2013 | 23934149 / 10.1038/nsmb.2660 | 124 |
| S-13 | Blakeley P. et al. Development 142:1121–1133, 2015 | 10.1242/dev.117945 | 30 |
| S-14 | Petropoulos S. et al. Cell 165:1012–1026, 2016 | 10.1016/j.cell.2016.04.037 | 1529 (88 эмбрионов, E3–E7) |
| S-15 | Сводный анализ (PMC5818005) | — | ~1683 суммарно (Yan+Blakeley+Petropoulos) |

## 7. Прочее

| # | Ссылка | Примечание |
|---|---|---|
| S-16 | BioNumbers (HMS/Harvard) | BNID 106413 (новорождённый), BNID 110895 (методы оценки), BNID 109716 (обзор) |
| S-17 | Sender R., Fuchs S., Milo R. «Are we really vastly outnumbered?...». Cell 164:337–340, 2016 | препринт для S-2 |
| S-18 | Zhu J. et al. Доп. обзоры по развитию | кандидатуры на добавление |

## 8. Процедура пополнения

1. Источник добавляется с S-номером и полными метаданными.
2. Для каждого параметра, взятого из источника в модель, в коде/конфигурации делается
   ссылка на S-номер (парамметры живут в DATA LAYER, не в коде).
3. Если число взято из «вторички» (учебник/обзор), это отмечается — первичный источник
   указывается при наличии.
4. Не peer-reviewed источники (веб-курсы, базы) помечаются как secondary/tertiary.