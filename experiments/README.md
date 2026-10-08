# experiments/

Здесь хранятся конфигурации и результаты вычислительных экспериментов
(формат — `docs/EXPERIMENTS.md`, план — `docs/ROADMAP.md`).

- `configs/` — ~130 JSON-конфигураций Stage 3–8: калибровка (`blastocyst_calibration`,
  `stage4_*`), ткань (`tissue_*`), орган (`organ_*`), организм 5A/5B
  (`organism_life_course_*`, `organism_robust_*`, `organism_stress_suite`,
  `organism_policy_search_mini`, `organism_long_horizon_search`), mechanistic 5C
  (`organism_aging_*`), organ-backed 6A (`organism_organ_backed_*`), network 6B
  (`organism_organ_network_*`), reversibility 6C (`organism_reversibility_*`),
  boundary 6D / knife-edge и compound 6E / heterogeneous 6F / audit 7
  (`organism_reversibility_boundary_*`), манифест выравнивания 8
  (`stage8_biological_alignment_manifest.json`).
- `output/` — сгенерированные результаты (в .gitignore, не коммитятся).
- `reports/` — закоммиченные сводки ранних этапов: `v1/` (калибровка Этапа 3),
  `v2/` (модели A–C и свип Этапа 3.5). Сводки поздних этапов живут в
  `experiments/output/` (gitignored) и в тексте `docs/`.
- `run_calibration.py`, `run_stage4.py` — legacy-драйверы Этапов 3/3.5
  (актуальные раннеры — `python -m longevity.experiment.*`, см. README.md).
- Каждая конфигурация фиксирует: experiment_id, seed, population, duration,
  model_version, data_version, parameters, interventions, metrics_config.
- Stage 8.5 — docs-only гейт: новых конфигов и симуляций нет.