# Auto-miglioramento automatico — Stato attuale (2026-04-19)

Verifica del sistema di feedback/tuning in AI Simulator. Obiettivo: capire se
i pesi dei motori (A, S, C, MoE mixer, scrematura) vengono aggiornati
automaticamente sulla base degli esiti, o se tutto è manuale.

---

## Verdetto rapido

**NO. Non esiste auto-miglioramento automatico che aggiorni i pesi.**

Esiste un **sistema di feedback passivo** che:
1. ✅ Gira davvero ogni notte (step 29.5 della pipeline)
2. ✅ Analizza gli errori con Mistral AI
3. ✅ Salva gli output strutturati in MongoDB (`prediction_errors`)
4. ❌ **Non aggiorna alcun peso**. I pesi cambiano solo quando l'utente li modifica manualmente via UI/API.

Lo step di analisi aggregata (`analyze_prediction_errors.py`) che produrrebbe
raccomandazioni di modifica pesi **non è chiamato dalla pipeline notturna** e
**nessuno script applica le sue raccomandazioni** a MongoDB.

---

## Sezione 1 — Componenti identificati

### 1.1 Feedback Loop Analyzer — **Step 29.5 pipeline notturna, ATTIVO**

- **File**: [ai_engine/feedback_loop_analyzer.py](../../ai_engine/feedback_loop_analyzer.py)
- **Pipeline**: dichiarato come step 29.5 in
  [ai_engine/update_manager.py:155](../../ai_engine/update_manager.py#L155),
  dentro `SCRAPER_SEQUENCE` (linea 66). Il while loop alla linea 273 itera
  `SCRAPER_SEQUENCE`, quindi **viene eseguito**.
- **Logica**:
  1. Legge i pronostici **non ancora analizzati** da `daily_predictions_unified` (con profit_loss calcolato).
  2. Estrae contesto (segnali, quote, strisce, MC, ecc.).
  3. Per ogni errore chiama **Mistral** (`mistral-medium-2508`) con un prompt strutturato.
  4. Mistral restituisce JSON con: `variables_impact` (8 fattori: form, motivation, home_advantage, market_odds, h2h, fatigue, streaks, tactical_dna), `severity`, `pattern_tags`, `root_cause`, `ai_analysis`, `suggested_adjustment`.
  5. **Salva ciascun errore analizzato come documento in `prediction_errors`**.
- **Cosa NON fa**: nessun update su `tuning_settings` o altra collection pesi. Il campo `suggested_adjustment` di Mistral viene scritto in DB ma non applicato.
- **Stato verificato (19/04/2026)**:

  | Metrica | Valore |
  | --- | --- |
  | Documenti totali `prediction_errors` | **618** |
  | Ultimo `created_at` | **2026-04-19 06:22** (stamattina) |
  | Conteggio per giorno (ultimi 10) | 2026-04-19: 23, 04-18: 10, 04-17: 1, 04-15: 3, 04-14: 12, 04-13: 16, 04-12: 27, 04-11: 13, 04-10: 1 |

  → **Gira regolarmente** nella pipeline notturna. L'analisi degli errori è quindi operativa.

### 1.2 Aggregate Prediction Errors — **ESISTE MA NON SCHEDULATO**

- **File**: [ai_engine/aggregate_prediction_errors.py](../../ai_engine/aggregate_prediction_errors.py)
- **Logica**:
  - Legge tutti i doc da `prediction_errors`
  - Aggrega `variables_impact` per sistema (A/S/C) e per mercato (SEGNO/GOL/DC)
  - Produce file JSON `ai_engine/log/prediction_errors_aggregated.json`
- **Scheduling**: **non** in pipeline notturna. Solo chiamabile manualmente.
- **Stato**: file di output probabilmente non aggiornato di recente. Da verificare se esiste nel filesystem — non l'ho trovato attivamente.

### 1.3 Analyze Prediction Errors — **ESISTE MA NON SCHEDULATO**

- **File**: [ai_engine/analyze_prediction_errors.py](../../ai_engine/analyze_prediction_errors.py)
- **Logica**:
  - Legge `prediction_errors_aggregated.json`
  - Legge i pesi attuali da MongoDB (`tuning_settings._id="algo_c_config"`)
  - Identifica sub-motori/segnali con più errori
  - Genera **raccomandazioni** di aumento/diminuzione pesi (es. PESO_STREAK, PESO_BVS_QUOTE)
  - Scrive 2 output:
    - TXT umano: `ai_engine/log/prediction_errors_recommendations.txt`
    - JSON: `ai_engine/log/prediction_errors_recommendations.json`
- **Scheduling**: **non in pipeline notturna**.
- **Output finale**: **nessuno script legge il JSON per applicarlo al DB**. Le raccomandazioni restano su file e richiedono intervento umano.

### 1.4 MC Tuning Tester — strumento manuale per sviluppatore

- **File**: `functions_python/ai_engine/tools/mc_tuning_tester.py`
- **Logica**: dry-run di parametri Monte Carlo (Sistema C) su storico per confrontare HR/PL con parametri attuali vs modificati. Se l'operatore è soddisfatto, può salvare i nuovi parametri su MongoDB.
- **Scheduling**: manuale (CLI). Il memoria utente cita l'uso di questo tool nei processi di "sfida pesi MC" (es. lorenzo_ultimo_v2 +210.1).
- **Stato**: strumento manuale, completamente umano-dipendente.

### 1.5 Tuning Server / Tuning Console — manuale

- **File**:
  - `ai_engine/engine/tuning_server.py` (+ `tuning_server_ultimo.py`, duplicato)
  - `ai_engine/engine/tuning_console.py`
  - `functions_python/upload_tuning_to_mongo.py`
- **Logica**: UI web / CLI per modificare `tuning_settings`. Workflow: modifichi manopole → salvi in `tuning_settings.json` locale → `upload_tuning_to_mongo.py` pusha su MongoDB.
- **Stato**: manuale. Nessun automatismo.

### 1.6 Endpoint Firebase `save_prediction_tuning` — manuale via API

- **File**: `functions_python/main.py` (endpoint HTTP POST)
- **Logica**: accetta JSON dal frontend/API e salva su `prediction_tuning_settings`.
- **Scheduling**: invocato solo da chiamata esplicita.

---

## Sezione 2 — Collezioni MongoDB dei pesi

### 2.1 `tuning_settings` (2 documenti)

- `_id = "main_config"` — pesi GLOBAL + ALGO_1..5 (usati da engine_core / Sistema C)
- `_id = "algo_c_config"` — pesi specifici ALGO_C

**Timestamp di update**: **non presente** in nessuno dei due documenti. Non c'è
campo `updated_at`, `modified_at`, `last_update`, `created_at`. Questo
significa che:
- O i documenti non vengono mai aggiornati (la storia dei pesi non è tracciata)
- O gli script che li scrivono (`upload_tuning_to_mongo.py`) non aggiungono il timestamp

**Chi la aggiorna**: solo `upload_tuning_to_mongo.py` (manuale) e l'endpoint
`save_prediction_tuning` (API manuale).

### 2.2 `prediction_tuning_settings`

- Usata da Sistema A (`run_daily_predictions.py`) e Sistema S (`run_daily_predictions_sandbox.py`) per caricare pesi PESI_SEGNO / PESI_GOL / soglie.
- `_id = "main_config"`, 2 chiavi totali (struttura minimale)
- Stesso discorso di `tuning_settings`: **niente timestamp in documento**.

### 2.3 `prediction_errors`

- Documenti totali: **618**
- Ultima scrittura: **2026-04-19** (oggi)
- Scritta solo da `feedback_loop_analyzer.py` (step 29.5).
- **Append-only**. Nessuna modifica ai pesi, solo log di errori analizzati.

### 2.4 Collezioni pesi NON trovate

Nessuna collection dedicata al mixer MoE, scrematura dinamica, pesi bollette,
pesi hybrid_pattern — questi valori sono **hardcoded nei file Python**
(`orchestrate_experts.py`, `generate_bollette_2.py`, ecc.). Quindi
l'aggiornamento richiederebbe `git commit`, non un update DB.

---

## Sezione 3 — Grep mirati per confermare assenza di update automatici

Ho cercato nel codice qualsiasi update/insert/replace su `tuning_settings` o
`prediction_tuning_settings`:

```
Grep: update_one/update_many/insert/replace su tuning_settings
Risultato: ZERO occorrenze.
```

Gli unici scrittori sono:
- `upload_tuning_to_mongo.py` (usa probabilmente `replace_one` via pattern
  diverso, o `insert_one` con overwrite) — **manuale**
- `save_prediction_tuning` endpoint — **manuale via API**

Nessun cron/task/pipeline chiama script che scrivono su quelle collection.

---

## Sezione 4 — Pipeline notturna passo per passo (filtrata per "auto-miglioramento")

Dal file `update_manager.py`, la `SCRAPER_SEQUENCE` contiene ~39 step. Quelli
legati al **feedback/tuning** (non data ingestion né scoring):

| Step | File | Effetto sui pesi |
| ---: | --- | --- |
| **29** | `calculate_profit_loss.py` | calcola P/L dei pronostici, scrive `profit_loss` e `hit` nei pronostici. NO update pesi. |
| **29.5** | `feedback_loop_analyzer.py` | analizza errori con Mistral, scrive in `prediction_errors`. NO update pesi. |
| 32 | `tag_elite.py` | tag pattern elite (P1-P18). NO update pesi (anche i pattern stessi sono hardcoded). |
| 33 | `tag_mixer.py` | tag pattern mixer (V01-V12 + hybrid). NO update pesi. |
| 34 | snapshot nightly | backup. NO update pesi. |
| 36 | `analisi_match.py` | analisi post-partita per dashboard. NO update pesi. |

**Conclusione**: nella pipeline notturna non c'è alcun passaggio che aggiorni
pesi basandosi sui risultati. L'unico feedback è **passivo** (step 29.5: log
strutturato di errori).

---

## Sezione 5 — Cosa NON esiste (gap vs ricordo utente)

Il ricordo di un "sistema di auto-miglioramento che aggiorna pesi
automaticamente" non trova riscontro nel codice. Specificamente:

| Meccanismo sospettato | Trovato? | Note |
| --- | :---: | --- |
| Job che aggiorna PESI_SEGNO / PESI_GOL su `prediction_tuning_settings` | ❌ | Solo manuale via API |
| Job che aggiorna `tuning_settings` (GLOBAL + ALGO_C) | ❌ | Solo manuale via `upload_tuning_to_mongo.py` |
| Optuna / Bayesian tuning schedulato | ❌ | Non trovato |
| Ricalibrazione probabilità automatica | ❌ | Non esiste; le probabilità restano come uscite dal motore |
| Aggiornamento pesi mixer MoE basato su concordanza A/S/C | ❌ | Pesi mixer sono hardcoded in codice |
| Aggiornamento soglie scrematura dinamiche | ❌ | Tutte hardcoded (`_apply_segno_scrematura` e friends) |
| Applicazione automatica delle raccomandazioni di `analyze_prediction_errors` | ❌ | Il file JSON viene prodotto (se chiamato manualmente) ma non letto da nessuno |
| Tracking dello storico dei pesi (audit log) | ❌ | Nessun timestamp nei documenti di `tuning_settings` |

---

## Sezione 6 — Stato attuale riassunto (tabella)

| Componente | Esiste? | Schedulato? | Attivo? | Ultimo uso | Aggiorna pesi? |
| --- | :---: | :---: | :---: | --- | :---: |
| Feedback Loop (Mistral) | ✅ | ✅ (step 29.5) | ✅ sì | 2026-04-19 06:22 | ❌ |
| `prediction_errors` collection | ✅ | — | ✅ 618 doc | 2026-04-19 | — |
| Aggregate prediction errors | ✅ | ❌ | Solo se lanciato a mano | Non tracciato | ❌ |
| Analyze prediction errors (recommendations) | ✅ | ❌ | Solo manuale | Non tracciato | ❌ |
| `tuning_settings` (pesi Sistema C) | ✅ | — | Usato in lettura | Nessun timestamp nei doc | — |
| `prediction_tuning_settings` (pesi A/S) | ✅ | — | Usato in lettura | Nessun timestamp nei doc | — |
| MC Tuning Tester | ✅ | ❌ | Solo manuale CLI | Memoria: usato recentemente ("sfida pesi MC") | Solo se operatore clicca |
| Tuning Server (Web UI) | ✅ | ❌ | Solo manuale | — | Solo se operatore clicca |
| Auto-tuning su concordanza A/S/C | ❌ | — | — | — | — |
| Ricalibrazione automatica probabilità | ❌ | — | — | — | — |

---

## Sezione 7 — Architettura "as-is" del feedback (disegno logico)

```
          ┌──────────────────────────────────────┐
          │   PIPELINE NOTTURNA (update_manager) │
          └──────────────────────────────────────┘
                          │
    ... step 25-28 (pronostici + P/L calcolati) ...
                          ▼
         ┌──────────────────────────────────────┐
         │  Step 29.5 — feedback_loop_analyzer  │
         │  (Mistral AI analizza errori)        │
         └──────────────────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────┐
        │ MongoDB: prediction_errors      │
        │ (618 doc, append-only)          │
        └─────────────────────────────────┘
                          │
                          │    ❌ nessun trigger automatico
                          │
                          ▼
        ┌─────────────────────────────────┐
        │ aggregate_prediction_errors.py  │   ← manuale
        │ analyze_prediction_errors.py    │   ← manuale
        └─────────────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────┐
        │ log/prediction_errors_recomm... │
        │ (TXT + JSON con raccomandazioni)│
        └─────────────────────────────────┘
                          │
                          │    ❌ nessuno script lo applica
                          │
                          ▼
                   (umano legge)
                          │
                          ▼
        ┌─────────────────────────────────┐
        │ Tuning Server UI / API          │   ← manuale
        │ upload_tuning_to_mongo.py       │   ← manuale
        └─────────────────────────────────┘
                          │
                          ▼
        ┌─────────────────────────────────┐
        │ tuning_settings                 │
        │ prediction_tuning_settings      │
        │ (pesi aggiornati SOLO da umano) │
        └─────────────────────────────────┘
```

---

## Sezione 8 — Onestà e limiti della verifica

- Non ho ispezionato `engine_core` interno (Sistema C black-box) — se al suo
  interno ci fosse qualche auto-calibrazione runtime (improbabile dato il
  design) non l'ho scoperta.
- Le collection pesi (`tuning_settings`, `prediction_tuning_settings`) non
  hanno timestamp di update, quindi **non posso dirti l'esatta data di ultimo
  aggiornamento dei pesi**. Il subagent che ha esplorato ha citato "18 feb
  2026" leggendo un file locale, ma non è una data certificata da MongoDB.
- Non ho contato i file `.json` di recommendations nel filesystem per
  verificare se `analyze_prediction_errors.py` sia mai stato eseguito.

---

## Sezione 9 — Implicazioni pratiche

1. **Le raccomandazioni di Mistral vengono archiviate ma non applicate.** Il
   campo `suggested_adjustment` in `prediction_errors` è un tesoro inutilizzato.
2. **I pesi dei motori sono effettivamente statici** rispetto al periodo
   analizzato (19/02 → 18/04/2026). La calibrazione che hai misurato al
   Punto 1 è quella prodotta da pesi fermi.
3. **Decisione di design da prendere**: prima di un cerotto "Kelly calibrato",
   bisogna decidere se investire anche su un **apply automatico** delle
   raccomandazioni di Mistral, o se rimanere sullo schema manuale. Oggi il
   feedback c'è ma è un loop aperto (Mistral → DB → ... → stop).
4. Per il **Kelly calibrato**: la mappa di calibrazione (HR reale per bin
   gruppo × mercato × prob) può essere aggiornata automaticamente ogni notte
   usando lo stesso meccanismo del feedback loop — un nuovo step 29.6 che
   ricalcola `calibration_map` e la salva in una collection dedicata. Sarebbe
   il primo anello di retroazione reale.

---

## Sezione 10 — File sorgenti citati

| Cosa | Path | Riga |
| --- | --- | ---: |
| Pipeline notturna (step order) | [ai_engine/update_manager.py](../../ai_engine/update_manager.py#L66) | 66 (SCRAPER_SEQUENCE) |
| Dichiarazione step 29.5 | [ai_engine/update_manager.py](../../ai_engine/update_manager.py#L155) | 155 |
| Loop di esecuzione step | [ai_engine/update_manager.py](../../ai_engine/update_manager.py#L273) | 273 |
| Feedback Loop Analyzer | [ai_engine/feedback_loop_analyzer.py](../../ai_engine/feedback_loop_analyzer.py) | 1 |
| Aggregate errors | [ai_engine/aggregate_prediction_errors.py](../../ai_engine/aggregate_prediction_errors.py) | — |
| Analyze errors / recommendations | [ai_engine/analyze_prediction_errors.py](../../ai_engine/analyze_prediction_errors.py) | — |
| Tuning server UI | [ai_engine/engine/tuning_server.py](../../ai_engine/engine/tuning_server.py) | — |
| Upload tuning → Mongo | [functions_python/upload_tuning_to_mongo.py](../../functions_python/upload_tuning_to_mongo.py) | — |
| API salvataggio pesi | [functions_python/main.py](../../functions_python/main.py) | (search `save_prediction_tuning`) |
