# Archivio — snapshot prima di modifiche invasive

File copiati qui come backup letterale prima di interventi sulla logica di stake.

## 2026-04-19 — pre Kelly unificato

Copia dei 4 file che implementavano la logica di stake pre-diagnostica.
Riferimento: `ai_engine/diagnostica_motore/FORMULA_STAKE_ATTUALE.md`.

- `run_daily_predictions__pre_kelly_unified_2026-04-19.py`
  - Sistema A. Funzione `calcola_stake_kelly` (Kelly 1/4 + protezioni tipo-specifiche + Fattore Quota a Fasce).
- `run_daily_predictions_sandbox__pre_kelly_unified_2026-04-19.py`
  - Sistema S. Formula identica ad A, pesi da MongoDB `prediction_tuning_settings`.
- `run_daily_predictions_engine_c__pre_kelly_unified_2026-04-19.py`
  - Sistema C. Funzione `apply_kelly` (Kelly 3/4 + 5 modificatori ±20% + stake_min/stake_max + Fattore Quota a Fasce).
- `backfill_stakes__pre_kelly_unified_2026-04-19.py`
  - Script backfill retroattivo. Identico ad A/S. Dopo l'intervento rinominato in produzione in `backfill_stakes_legacy.py`.

Per ripristinare: confrontare diff contro `git log` e copiare le funzioni volute.
