# Pattern Discovery

Pipeline ML per cercare pattern robusti nei pronostici storici di `daily_predictions_unified`, con feature selection rigorosa e validazione out-of-sample.

## Approccio

1. **Split cronologico**: training prime 1000 partite, buffer 30, test ultime 471 (totale 1501 dedupati). Il test non viene mai guardato durante il training.
2. **Random Forest feature importance** su `profit_loss` come target continuo: identifica le variabili che spostano il valore economico (non solo l'esito binario). `min_samples_leaf=25` per evitare regole su pochissime partite.
3. **Lasso con StandardScaler** sulle feature sopravvissute alla RF: penalizza i coefficienti e azzera quelli legati a vincite casuali/overfitting. `alpha` scelto via `LassoCV` (5-fold). Le feature con coefficiente non-zero sono le "immortali".
4. **Greedy con soglie umane**: forward selection. A ogni step prende la variabile (tra quelle sopravvissute) e la soglia (da una lista pre-definita di valori arrotondati) che massimizza il ROI sul training. Vincolo volume ≥ 150 per step. Si ferma quando nessuna aggiunta migliora il ROI.
5. **Forward test**: applica il pattern finale al test set. Riporta ROI train vs ROI test, HR train vs HR test, max drawdown, p-value (`ttest_1samp` su `profit_loss` vs 0). Se il ROI test crolla rispetto al training → overfitting.

## Struttura cartella

```
pattern_discovery/
├── README.md              — questo file
├── config.py              — parametri modificabili
├── pipeline.py            — script eseguibile (load → split → RF → Lasso → greedy → forward test)
├── dataset_cache.parquet  — dataset dedupato cached (1501 righe)
├── run_history.md         — log cronologico dei run
└── results/
    └── run_YYYY-MM-DD_HHMM/
        ├── feature_importance.csv
        ├── lasso_survivors.csv
        ├── greedy_steps.csv
        ├── final_pattern.json
        ├── metrics.md
        └── report.md
```

## Come rilanciare

```
cd c:/Progetti/simulatore-calcio-backend
python ai_engine/pattern_discovery/pipeline.py
```

Il primo run crea la cache parquet da MongoDB. I run successivi leggono dalla cache (veloci). Per rigenerare la cache: eliminare `dataset_cache.parquet`.

## Parametri modificabili

Tutti in `config.py`:

- **Finestra date**: `DATE_FROM`, `DATE_TO`
- **Split**: `TRAIN_SIZE`, `BUFFER_SIZE`, `TEST_SIZE`
- **Random Forest**: `RF_N_ESTIMATORS`, `RF_MIN_SAMPLES_LEAF`, `RF_IMPORTANCE_THRESHOLD`
- **Lasso**: `LASSO_CV_FOLDS`, `LASSO_MAX_ITER`
- **Greedy**: `GREEDY_MIN_VOL`, `GREEDY_MAX_STEPS`
- **Soglie umane**: `HUMAN_THRESHOLDS` dict per-variabile
- **Aggregazione valori rari categorici**: `RARE_CATEGORY_THRESHOLD`
- **Obiettivi per giudicare il run**: `TARGET_ROI_TEST`, `TARGET_MIN_VOL_TRAIN`, `TARGET_MIN_VOL_TEST`, `TARGET_MAX_PVALUE`

## Variabili in uso

**Numeriche** (grezze, non binate — RF/Lasso trovano da soli le non-linearità):
`stars`, `confidence`, `quota`, `stake`, `sd_campo`, `sd_bvs`, `sd_affidabilita`, `sd_lucifero`, `gd_att_vs_def`, `prob_modello`, `probabilita_stimata`

**Categoriche** (one-hot con aggregazione valori rari → 'OTHER'):
`source`, `routing_rule`, `tipo`, `pronostico`

**Condizionata**: `dir_dna` (inclusa solo se non è tutta `None` nella finestra).

## Variabili escluse

Escluse per scelta metodologica o disponibilità:

- `gol_dettaglio.*` tranne `att_vs_def` (tenuto perché sub-motore chiave del motore gol)
- `gol_directions.*` tranne `dir_dna` (conditional)
- `segno_dettaglio.*` tranne quelle elencate (bvs, campo, affidabilita, lucifero)
- `expected_total_goals` (già usata internamente dal motore gol — non ortogonale)
- `streak_*` (segnale debole nell'analisi univariata)
- `match_time`, `giornata`, `is_cup`, `anticipata`, `analysis_score`, `league` (esclusi per direttiva operativa)
- `edge` (derivato da prob_modello e quota — collineare)
- `NO BET` e `RISULTATO_ESATTO` esclusi a monte

## Dedup

Ogni pronostico unico = `(date, home, away, tipo, pronostico)`. Se compare in più scatole (es. Mixer + Pronostici) viene assegnato a quella prioritaria (`MIXER > ELITE > ALTO_RENDIMENTO > PRONOSTICI`). Ogni riga del dataset conta una volta sola.

## Output di giudizio

Un run si considera riuscito se:

- ROI test ≥ 10%
- Volume test ≥ 50
- p-value ≤ 0.05
- Volume training ≥ 150

Altrimenti è probabilmente overfitting e serve intervenire su alpha Lasso / soglie / variabili.
