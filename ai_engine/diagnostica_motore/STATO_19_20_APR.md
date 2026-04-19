# Stato lavoro 19-20 aprile 2026

Documento di ripartenza: se riapriamo fra qualche giorno senza il contesto chat,
qui trovi tutto quello che serve a non ripartire da zero.

**Nota**: questo file è scritto dopo una sessione lunga in cui abbiamo fatto
diagnostica completa del motore + 3 cerotti in produzione + fix frontend.
Prima di modifiche future, leggere **prima** questo file, poi i report
puntuali nelle sottocartelle.

---

## 1. Diagnostica completata (punti 1-6 + audit Mistral)

Cartelle in `ai_engine/diagnostica_motore/`:

| Cartella | Contenuto | Validità dati |
| --- | --- | --- |
| `01_calibrazione/` | Reliability diagram (HR reale vs probabilita_stimata) per gruppo × mercato × bin | ✅ Numeri corretti (HR non dipende da stake) |
| `02_expected_value/` | EV = prob × quota - 1 vs ROI reale. Monotonicità rotta su tutti i mercati. | ⚠️ ROI a 1u. Conclusioni qualitative robuste. Per PL reale andrebbe rifatto con stake pesato. |
| `03_stake/` | Performance per stake 1-10 + simulazione Kelly 0.10/0.25 dichiarato/calibrato | ✅ Stake pesato (qui era l'oggetto di studio). +2938u vs +1243u Kelly calibrato vs stake old. |
| `04_no_bet/` | NO BET simulati (74/213 risolvibili) + audit 160 conversioni MoE | ⚠️ A 1u. Ma verdetti "conversione peggiorativa" robusti. |
| `05_segmenti/` | Performance per lega/tier/quota/giorno/mercato/gruppo | ⚠️ ROI a 1u. Ordinamenti OK, magnitudini no. |
| `06_motori/` | A vs S vs C isolati, matrice concordanza, tier lega TOP/Seconde/Altro | ⚠️ Idem. Specializzazione tier valida, valori no. |
| `07_mistral_audit/` | Audit 618 documenti `prediction_errors`: Mistral contraddittorio, loop non chiudibile in auto | ✅ Analisi testuale, senza PL. |
| `cerotto4_preview/` | Verifica 10 combo del report_globale → 3 falsi allarmi + 7 tossiche; impatto per scatola backend-style | ✅ Numeri backend-style corretti (allineati con `pl_storico`) |

Documentazione trasversale:

- `FORMULA_STAKE_ATTUALE.md` — mappa esatta del calcolo stake prima del Cerotto 1 (A/S/C/MoE/backfill) — **archivio storico**, ora superato dal Kelly unificato.
- `DATI_PROBABILITA.md` — come nasce `probabilita_stimata` nei 3 sistemi (A/S sub-motori pesati, C Monte Carlo diretto). Valida, non è cambiato nulla.
- `AUTOMIGLIORAMENTO_ATTUALE.md` — feedback loop Mistral: **gira** (step 29.5) ma è passivo, non aggiorna pesi. I `suggested_adjustment` restano su DB inutilizzati.

---

## 2. Cerotti in produzione

### Cerotto 1 — Kelly unificato calibrato (attivo dal 19/04 notte)

**Cosa fa**: sostituisce il calcolo stake nei 3 sistemi (A, S, C) e nel
backfill con una funzione condivisa `kelly_unified(db, prob, quota, source,
mercato, kelly_fraction=0.25)` che:

1. Legge `calibration_table._id='current'` da MongoDB
2. Mappa (source, mercato, bin probabilità) → HR reale storica (con shrinkage bin se N<30 cella)
3. Applica Kelly puro 0.25 senza fattore quota a fasce, senza cap tipo-specifici
4. Se `edge ≤ 0` → stake=1 con `low_value=True` (no NO BET automatico)

**File chiave**:
- `functions_python/ai_engine/stake_kelly.py` — modulo principale
- `functions_python/ai_engine/source_classify.py` — classificazione gruppo A/S/C/A+S/C-derivati/Altro
- `ai_engine/refresh_calibration_table.py` — rigenerazione calibration_table (step 29.3 nightly)

**Call sites sostituiti**:
- `functions_python/ai_engine/calculators/run_daily_predictions.py` (Sistema A)
- `functions_python/ai_engine/calculators/run_daily_predictions_sandbox.py` (Sistema S)
- `functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py` (Sistema C)
- `backfill_stakes_legacy.py` (rinominato da `backfill_stakes.py`, **NON** modificato — non chiamato da pipeline)

**Nuovi campi nel pronostico** salvato su `daily_predictions_unified.pronostici[]`:
- `prob_calibrata` (0-100): la prob letta dalla calibration_table
- `low_value` (bool): true se edge≤0
- `source_group` (str): 'A'|'S'|'C'|'A+S'|'C-derivati'|'Altro'

**Backup file vecchi** in `ai_engine/_archive/` con timestamp `2026-04-19`.

**Simulazione storica** (stake pesato su 1456 pronostici 19/02→18/04):
- PL old stake: +1242.52u
- PL nuovo Kelly calibrato 0.25: **+3075.02u** (Δ +1832.50u)
- 50% dei pronostici flaggati `low_value`
- Drawdown: -987 → -326

**Frontend**: badge giallo ambra "⚠ Bassa Value" su pronostici con `low_value=True` visibile accanto allo stake in `UnifiedPredictions.tsx`, `MixerPredictions.tsx`, `DailyPredictions.tsx`.

### Cerotto 3 — 4 regole conversione tossiche disattivate (attivo dal 19/04 notte)

In `functions_python/ai_engine/calculators/orchestrate_experts.py` commentate 4 regole MoE:

- `as_o25_to_dc` (righe ~1995-2006)
- `as_o25_to_under25` (righe ~2008-2040)
- `as_o25_to_segno1` (era già commentata 18/04, aggiunto solo commento Cerotto 3)
- `gg_conf_dc_downgrade` (chiamata riga ~3028 commentata, funzione intatta)

**Effetto**: un Over 2.5 A+S debole viene scartato senza tentativo di conversione tossica (PRIORITÀ 4 fallback rimane attiva).

### Cerotto 4 — 7 combo tossiche scartate, solo non-mixer (attivo dal 20/04 notte)

In `orchestrate_experts.py` nuova funzione `_apply_toxic_combo_filter(unified, base_doc)` (~riga 2716), chiamata dopo `route_predictions` e prima di `_apply_multigol` (~riga 3160).

**Combo disattivate** (tutte con yield pesato negativo sul dataset storico):

| ID | Combo | Yield storico |
| --- | --- | ---: |
| C2 | SEGNO + tipo_partita=aperta | -44% |
| C4 | tipo_partita=aperta + categoria=Alto Rendimento | -50% |
| C5 | SEGNO + Monday + aperta | -103% |
| C6 | fascia_oraria=sera + Alto Rendimento | -6% |
| C8 | Friday + fascia_quota=3.00+ + equilibrata | -89% |
| C9 | fascia_quota=2.50-2.99 + aperta | -48% |
| C10 | Friday + categoria=Alto Rendimento | -62% |

**C1, C3, C7** (SEGNO+3.00+, SEGNO+AR, 3.00+ AR) sono **"falsi allarmi"**: HR bassa ma yield ~+40-54%. **NON** disattivati. Il report globale proponeva "Dimezza" ma l'analisi backend mostra che dimezzare costa -107u.

**Ambito**: solo pronostici con `mixer != True`. Se mixer=True il filtro salta (scatola Mixer resta intatta, +211u su 2 mesi).

**Definizioni** (dal notebook `c:/Progetti/analisi_professionale.ipynb`):
- `tipo_partita` da `qmin=min(quota_1,quota_X,quota_2)`: <1.40 dominante, 1.40-1.79 favorita, 1.80-2.29 equilibrata, ≥2.30 aperta
- `fascia_oraria` da hour(match_time): <15 mattina, 15-17 pomeriggio, 18-20 sera, ≥21 notte
- `fascia_quota` sul pronostico: 3.00+ | 2.50-2.99 | ecc.
- `categoria`: quota>2.50 → Alto Rendimento, altrimenti Pronostici
- `giorno_settimana`: nome inglese (Monday, Friday)

**Azione**: pronostico colpito → NO BET con `toxic_combo=True`, `toxic_combo_ids=[...]`, `stake=0`, preservando `original_pronostico`/`original_quota`.

**Impatto atteso backend-style su storico 19/02-18/04**:
- tutti: +136.78u → +191.02u (+54u)
- alto_rendimento: +176.81u → +213.85u (+37u, yield 29% → 68%)
- mixer: +211.24u invariato

**Dinamicità**: chiamato sia da pipeline notturna sia da `pre_match_update.py` ogni 15 min. Il flag `toxic_combo` viene ricalcolato da zero ad ogni run su odds/match_time aggiornate — un pronostico può diventare tossico o tornare valido tra una run e l'altra.

---

## 3. Infrastruttura di supporto aggiunta

### Pipeline notturna

Aggiunto step 29.3 `refresh_calibration_table.py` in `update_manager.py` tra step 29 (calculate_profit_loss) e 29.5 (feedback_loop_analyzer). Rigenera ogni notte la `calibration_table` leggendo tutti i pronostici storici con `esito` noto (criterio allineato al backend `pl_storico`).

### MongoDB collection nuova

- `calibration_table._id='current'`
  - Struttura: `cells[gruppo|mercato|bin]={n, hr}`, `fallback_mercato_bin[mercato|bin]={n, hr}`, `bins`, `bin_labels`, `updated_at`, `n_totale`, `finestra`
  - Al 19/04 contiene ~1702 pronostici (criterio allineato backend). Aggiornata quotidianamente dallo step 29.3.

### tuning_settings.json

Aggiunto blocco `KELLY_UNIFIED` con `kelly_fraction: 0.25` e `kelly_enabled: true` in **entrambe** le copie (`ai_engine/engine/` e `functions_python/ai_engine/engine/`). Il codice attuale **non legge** ancora `kelly_enabled` — è placeholder per futuro rollback.

### Frontend (commit separato)

- 4 file type `Prediction` con nuovi campi opzionali `prob_calibrata`, `low_value`, `source_group`
- Badge "⚠ Bassa Value" giallo ambra (#F59E0B) accanto allo stake, tema dark/light
- Fix contatori tab: "Pronostici"/"Alto Rendimento" ora escludono NO BET correttamente (era bug con `hasRealTip` a livello match)
- Indicatore "Aggiornato alle HH:MM" (contenitore opaco, non trasparente)
- Accordion leghe e card partita: una sola aperta alla volta
- Reset espansi al cambio data/tab

---

## 4. Discrepanza metodologica risolta (19/04)

**Problema scoperto**: mie diagnostiche usavano dataset **dedupato + stake 1u + scatole mutuamente esclusive**, mentre il backend (`popola_pl_storico.py`) usa **no dedup + stake pesato + scatole sovrapposte + include RE**.

Risultato: "AR def B = +4u" (mio calcolo) vs "AR frontend = +246u" (backend). Differenza 98%.

**Nessuna delle due è sbagliata** — misurano cose diverse:
- Metodo mio: **qualità predittiva** del classificatore (a parità di stake)
- Metodo backend: **performance economica** come l'utente la vede

**Per confronti con dashboard frontend, usare SEMPRE metodo backend**. Per valutare il motore di classificazione in isolamento, il mio metodo va bene.

**Report completo**: `cerotto4_preview/discrepanza_dati.md` + `impatto_backend_corretto.md`.

### Fix calibration_table (stessa occasione)

Il criterio originale di `refresh_calibration_table.py` richiedeva `profit_loss not None`. Allineato a `esito not None` (come backend). Differenza sul dataset reale: 6 pronostici su 1702 (0.4%). Script one-shot `rigenera_calibration_completa.py` eseguito. Nightly già allineato.

---

## 5. Cose da monitorare nei prossimi giorni

### Kelly unificato (Cerotto 1)

- Stake medio atteso scendere da ~5.2 a ~2.9
- Circa 50% pronostici flaggati `low_value`
- Sulla scatola **Mixer** non dovrebbero esserci cambiamenti (il flag `low_value` viene comunque calcolato, ma lo stake se era alto via Fattore Quota sarà più basso — attenzione alla sensazione "mixer è più piatto")
- Monitorare yield dashboard: se scende, il Kelly calibrato sta sbagliando segmento, da investigare

### Cerotto 4

- Log `🚫 TOXIC COMBO: ...` dovrebbero comparire sia nel log notturno sia nei pre_match_update intraday
- Conteggio pronostici giornalieri potrebbe scendere leggermente (escluse 7 combo su pronostici non-mixer)
- Impatto atteso modesto (+27u/mese)

### Calibration table

- Lo step 29.3 deve girare ogni notte. Verificare `calibration_table.updated_at` ogni tanto.
- Se il motore cambia (es. Kelly calibrato imbocca una deriva), la tabella si auto-adatta (HR si muove con i nuovi stake), ma è un feedback loop che va tenuto d'occhio.

### Feedback loop Mistral

Non chiuso. Continua a riempire `prediction_errors` ogni notte. I `suggested_adjustment` restano non applicati per scelta (audit 07 ha mostrato che Mistral è contraddittorio settimanalmente, richiede livello umano intermedio per applicazione pesi).

---

## 6. Lavori NON fatti / in sospeso

### Da considerare in futuro

- **Rifare 02/04/05/06 con stake pesato** per avere PL reali comunicabili. **Non urgente** — conclusioni qualitative sono robuste. Utile se vuoi citare "La Liga costa X euro/mese" in comunicazione.
- **Chiudere il loop Mistral**: impossibile senza livello umano. Possibile roadmap: aggregare `suggested_adjustment` settimanalmente → review utente → apply manuale via UI.
- **Backtest Kelly calibrato su dati out-of-sample** (settimane post-19/04): il +1832u storico è post-hoc sullo stesso dataset che ha tarato la calibration. Bisogna verificare che regge anche forward.
- **Cerotto 2** (non esiste): la numerazione "1, 3, 4" era volontaria (Cerotto 2 era un piano diverso mai formalizzato, non c'è gap).

### Decisioni prese su cui non tornare indietro senza motivo

- Kelly 0.25 come default (da Punto 3: +78% ROI per unità rischiata, migliore drawdown)
- NO BET automatico NO — mantieni stake 1 con `low_value=True` per lasciare al frontend la scelta di come mostrarlo
- `stake_min`/`stake_max` rimossi dal Sistema C (non usati altrove)
- Fattore Quota a Fasce non chiamato più dai 3 motori (funzione rimasta in orchestrate_experts per compat conversioni, non la usa nessuno)
- Le 7 combo Cerotto 4 NON toccano mixer (preservazione scatola Mixer +211u)

---

## 7. Commit chiave della sessione

Ordine cronologico (backend):

1. `f8417bb3` — Backup pre Kelly unificato
2. `6648561f` — Modulo Kelly unificato + source_classify
3. `6748dcfb` — Script refresh_calibration_table + prima popolazione
4. `0a1243ce` — Pipeline notturna: step 29.3
5. `50d5f978` — Sistemi A/S/C: sostituito calcolo stake con kelly_unified
6. `f008cc17` — Test preview Kelly unificato
7. `de04f22e` — tuning_settings: blocco KELLY_UNIFIED
8. `a3baa224` — Cerotto 3: 4 regole conversione tossiche disattivate
9. `5bebad60` — Cerotto 4: filtro 7 combo tossiche (solo non-MIXER)

Frontend:

1. `feb6bf4` — Fix contatori Best Picks + accordion leghe/card + indicatore aggiornato
2. `73365e8` — gitignore ODT/DOCX
3. `67418e5` — Badge "Bassa Value" per pronostici low_value

Tutti già pushati su `origin/main`. Nessun commit locale pendente al momento della scrittura.

---

## 8. Come ripartire dopo compattazione

Se riapriamo chat e non ho più il filo:

1. Leggi **questo file** per primo
2. Vai in `ai_engine/diagnostica_motore/` per i report tecnici
3. Guarda `git log --oneline -15` in entrambi i repo per vedere dove siamo
4. Se un numero specifico serve, i report markdown lo hanno
5. Se vuoi capire il "perché" di una decisione, guarda il messaggio di commit del relativo file

Tutto il contesto operativo è nei file. Quello che si perde è "il sapore della discussione" — ordine delle scoperte, alternative scartate, sfumature. Se serve ricostruirle, chiedimi e rifaccio l'analisi.
