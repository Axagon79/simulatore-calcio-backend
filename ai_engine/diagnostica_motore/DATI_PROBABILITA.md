# Come nasce `probabilita_stimata` — Mappa A / S / C

Mappatura fattuale (via lettura codice) del percorso "dati grezzi → sub-motori →
confidence → `probabilita_stimata`" nei 3 sistemi.

Complementare a `FORMULA_STAKE_ATTUALE.md`: lì è documentata la formula di
stake, qui l'input che la alimenta.

---

## Verifica dell'ipotesi iniziale

**Ipotesi utente:** *"La probabilità viene dalla confidenza, che è una media
normalizzata dei pesi dei sub-motori: BVS, fattore campo, testa a testa, stato
di forma, attacco vs difesa, ecc."*

**Esito:** ✅ **confermato per A e S**, ❌ **smentito per C**.

- **A / S**: la `confidence` è effettivamente media **pesata** (non semplice)
  dei sub-motori, e `probabilita_stimata` è derivata dai sub-score via una
  trasformazione non-lineare con bonus/penalità. Corrisponde al ricordo.
- **C**: non c'è una media di sub-motori. La `confidence` è la **percentuale
  diretta** dalla distribuzione di 100 simulazioni Monte Carlo, e
  `probabilita_stimata = confidence` (senza altra trasformazione).

Dunque il "motore a sub-punteggi" è l'architettura di A/S. C è un'architettura
di simulazione che produce direttamente una probabilità frequentista.

---

## Sistema A (run_daily_predictions.py)

### 1. Input grezzi

Dati caricati da MongoDB durante la pipeline (file:
`functions_python/ai_engine/calculators/run_daily_predictions.py`):

| Collection | Cosa fornisce | Uso |
| --- | --- | --- |
| `h2h_by_round` | Match pre-calcolati con `h2h_data` embedded: BVS, lucifero, trust, DNA, `fattore_campo`, `h2h_score` | **Fonte principale** dei sub-score |
| `teams` | `ranking`, `scores` (attack/defense), `stats.motivation` | `motivazioni`, fallback `att_vs_def` |
| `team_seasonal_stats` | `xg_avg`, `total_volume_avg` | Sub-motore `xg` (GOL) |
| `league_stats` | `avg_goals` per lega | Sub-motore `media_lega` (GOL) |
| `raw_h2h_data_v2` | Pattern storici BTTS%, Over 2.5%, gol medi | Sub-motore `h2h_gol` |
| `odds` (dentro il doc) | Quote SNAI 1/X/2/Over/Under/Goal/NoGoal | Sub-motore `quote`, blend finale |
| `matches_champions_league` / `matches_europa_league` | Risultati e calendari coppe | Coppe |

**Forma squadre**: proxy `lucifero_home/away` dal precalcolo `h2h_data`
(range 0-25). Non c'è un reperimento diretto delle "ultime N partite" — la
forma è già compressa nel valore Lucifero.

**H2H**: il calcolo è già precomputato in `h2h_by_round`; il numero esatto di
match storici coperti dipende da come l'ha popolato lo scraper.

### 2. Sub-motori (SEGNO)

Funzione `analyze_segno()` (~linea 1920). Ogni sub-motore calcola uno score
normalizzato in [0, 100].

| Sub-motore | Campo dettaglio | Formula base | Peso A (PESI_SEGNO) |
| --- | --- | --- | ---: |
| BVS | `bvs` | classificazione (PURO/SEMI/NON) + `bvs_match_index` (-6..+7) + bonus `is_linear` | **20.60%** |
| Quote | `quote` | picco 100 a quota ≈1.639, penalizzata fuori fascia | 1.99% |
| Lucifero | `lucifero` | `abs(luc_home − luc_away)` trasformato con bonus se max ≥20 | 3.81% |
| Affidabilità | `affidabilita` | trust letter A-D + affidabilità casa/trasferta | **35.08%** |
| DNA | `dna` | differenza `home_dna` vs `away_dna` (att/def/tec/val compositi) | 6.11% |
| Motivazioni | `motivazioni` | `stats.motivation` (salvezza/europa/ecc.) con bonus/malus per ruolo favorita/sfavorita | 6.78% |
| H2H | `h2h` | `home_score`/`away_score` di h2h (% vittorie negli scontri diretti) | 3.95% |
| Fattore campo | `campo` | `fattore_campo` (home/away da h2h_data) con bonus se field_home ≥55-70 | **19.68%** |
| Strisce | `strisce` | % vittorie ultimi 5 + moltiplicatore streak | 2.02% |

Totale pesi = 100% (dichiarato: "ridistribuiti ×0.9 + strisce 0.10" nel commento).

I sub-score vengono **anche salvati** nel documento (`segno_dettaglio.{campo,
bvs, affidabilita, lucifero}`) e quei valori sono quelli che ho usato come
feature nella pipeline di pattern discovery e nelle diagnostiche.

### 3. Sub-motori (GOL)

Funzione `analyze_gol()` (~linea 2357).

| Sub-motore | Campo dettaglio | Descrizione | Peso A (PESI_GOL) |
| --- | --- | --- | ---: |
| Media gol | `media_gol` | `(gol_fatti_casa + gol_subiti_trasferta)/2` e viceversa | 11.14% |
| Att vs Def | `att_vs_def` | attacco squadra debole vs difesa squadra forte | 3.78% |
| xG | `xg` | xg_avg combined dalle team_seasonal_stats | **19.74%** |
| H2H gol | `h2h_gol` | pattern storici Over/BTTS da raw_h2h_data_v2 | 15.79% |
| Media lega | `media_lega` | scostamento vs media goals della lega | **19.13%** |
| DNA off/def | `dna_off_def` | compositi DNA attacco/difesa | **18.22%** |
| Strisce | `strisce` | % Over ultimi 5 match | 12.18% |

Totale pesi = 100%.

**GG/NG è separato**: 8 segnali pesati (BTTS h2h 18%, BTTS xG 15%, BTTS att 10%,
ecc.) → `btts_total` / `nogoal_total` [0-100], decisione su soglie:
`BTTS_SOGLIA_GOAL_MIN ≈ 60-64`, `NOGOAL_SOGLIA ≈ 56`.

### 4. Aggregazione → `confidence`

```python
# SEGNO
confidence_segno = sum(score_k * PESI_SEGNO[k] for k in SUBMOTORI_SEGNO)
# poi moltiplicatore strisce (±5%)

# GOL
confidence_gol = sum(score_k * PESI_GOL[k] for k in SUBMOTORI_GOL)
# + moltiplicatore strisce
# Decisione Over vs Under: in base a `over_count` vs `under_count` fra i sub-motori
```

`confidence_segno` e `confidence_gol` sono salvati a livello documento
(`confidence_segno`, `confidence_gol`), mentre nei singoli pronostici
`confidence` è il valore rilevante per quel mercato.

**Soglie decisionali:**
- `THRESHOLD_INCLUDE = 56.5` (linea 74): sotto questo si scarta.
- `THRESHOLD_HIGH = 70`: confidence alta.
- `CUP_CONF_CAP = 65`: in coppa, la confidence viene cap-ata.

### 5. `confidence` → `probabilita_stimata`

Funzione `calcola_probabilita_stimata(quota, dettaglio, tipo, directions)`
(linea 2678).

```python
# A) Prob mercato (solo informativa, NO blend)
p_market = min(0.92, (1.0 / quota) * 0.96)

# B) Statistiche sui sub-score
avg       = mean(dettaglio.values())
consensus = frazione di score > 55
strong    = frazione di score > 70
std       = stdev(dettaglio.values())

# C) Base differenziata per tipo (!)
if tipo == 'SEGNO':
    p_model = 0.44 + (avg - 50) * 0.015
elif tipo == 'DOPPIA_CHANCE':
    p_model = 0.52 + (avg - 50) * 0.018
else:  # GOL
    p_model = 0.42 + (avg - 50) * 0.013

# D) Bonus consensus a gradini
if consensus >= 0.80: p_model += 0.03
elif consensus >= 0.70: p_model += 0.02
elif consensus >= 0.60: p_model += 0.01

# E) Bonus strong signals
if strong >= 0.50: p_model += 0.03
elif strong >= 0.35: p_model += 0.02

# F) Direction bonus (GOL) + penalità std
p_model += direction_bonus
if std > 12:
    p_model -= (std - 12) * 0.003
p_model = clamp(p_model, 0.25, 0.88)

# G) NESSUN BLEND con p_market. Modello puro.
p_final = p_model

# H) Cap per tipo mercato
if tipo == 'SEGNO':         p_final = clamp(0.30, 0.78)
elif tipo == 'DOPPIA_CHANCE': p_final = clamp(0.45, 0.88)
else:                        p_final = clamp(0.35, 0.80)

return {
    'probabilita_stimata': round(p_final * 100, 1),
    'prob_mercato':        round(p_market * 100, 1),  # informativo
    'prob_modello':        round(p_model * 100, 1),
}
```

**Punti importanti:**
- `probabilita_stimata` **NON** è `confidence`. Arriva da una funzione a parte
  che parte da `avg(sub-score)` e ci applica bonus/penalità.
- **Nessun blend** con la quota di mercato ("modello puro", commento nel codice).
- I cap per tipo sono espliciti: SEGNO non può mai essere > 78%, DC > 88%, GOL > 80%.

### 6. Salvataggio nel documento pronostico

Il pronostico salvato in `daily_predictions.pronostici[]` contiene in sintesi:
- `confidence` (0-100, la media pesata sub-motori)
- `probabilita_stimata` (0-100, la trasformazione sopra)
- `prob_mercato` (0-100, informativo)
- `prob_modello` (0-100, prima dei cap)
- `stars` (scala 0-5 derivata da confidence)

---

## Sistema S (run_daily_predictions_sandbox.py)

### Differenze rispetto ad A

**Formula identica**. S è un fork "sandbox" di A per A/B testing / ottimizzazione
Optuna. Differiscono:

1. **Pesi caricati da MongoDB** (`prediction_tuning_settings`) se presenti,
   altrimenti fallback a default hardcoded **diversi da A**:

   | Peso chiave | A | S (default) |
   | --- | ---: | ---: |
   | `PESI_SEGNO['campo']` | 19.68% | **31.86%** |
   | `PESI_SEGNO['affidabilita']` | 35.08% | diverso (rivedere per esattezza) |
   | `PESI_GOL['xg']` | 19.74% | 19.80% |
   | `PESI_GOL['media_gol']` | 11.14% | ~10.24% |
   | `THRESHOLD_INCLUDE` | 56.5 | **48.9** (più permissivo) |

2. **Output collection diverse**: `daily_predictions_sandbox`,
   `daily_bombs_sandbox`. Non tocca produzione.

3. **Tutto il resto è identico**: stessi sub-motori, stessa funzione
   `calcola_probabilita_stimata` (copia), stessa pipeline dati, stesse
   trasformazioni. La differenza è parametrica, non strutturale.

### Implicazione

Per i fini del calcolo probabilità, **A e S sono lo stesso motore con parametri
diversi**. Il fatto che possano divergere sulle decisioni è conseguenza dei
pesi e della soglia diversa, non di logica diversa.

---

## Sistema C (run_daily_predictions_engine_c.py)

### 1. Architettura: Monte Carlo, non sub-motori

C è **strutturalmente diverso** da A/S. Non ha la stessa idea "media pesata di
sub-motori". Usa `engine_core.predict_match()` (algoritmo Master, `ALGO_MODE=6`)
come black-box di simulazione.

```python
# linea 20-21
SIMULATION_CYCLES = 100
ALGO_MODE = 6

# linea 152
def run_monte_carlo(preloaded_data, home, away, cycles=100):
    results = []
    for i in range(cycles):
        s_h, s_a, r_h, r_a = engine_core.predict_match(
            home, away, mode=ALGO_MODE, preloaded=preloaded_data
        )
        gh, ga = calculate_goals_from_engine(s_h, s_a, r_h, r_a)
        results.append((gh, ga))

    # Statistiche sulla distribuzione delle 100 simulazioni:
    home_win_pct = sum(1 for gh, ga in results if gh > ga) / cycles * 100
    draw_pct     = sum(1 for gh, ga in results if gh == ga) / cycles * 100
    away_win_pct = sum(1 for gh, ga in results if gh < ga) / cycles * 100
    over_15_pct  = sum(1 for gh, ga in results if gh+ga > 1.5) / cycles * 100
    over_25_pct  = ...
    gg_pct       = sum(1 for gh, ga in results if gh > 0 and ga > 0) / cycles * 100
    ng_pct       = 100 - gg_pct
    # + avg goals casa/trasferta, top_scores (risultati più frequenti)
    return distribution
```

**Cosa guida ogni singolo ciclo** (`engine_core.predict_match`):
cassaforte interna al modulo `engine_core`. Usa dentro di sé una combinazione
di algoritmi (`mode=6 = "Master"`: ensemble Statistico + Dinamico + Tattico
+ Caos + Monte Carlo). Include:
- ranking squadre (attack/defense)
- forma (valutata internamente)
- fattore campo
- componente stocastica (mode=Caos)

Il dettaglio di `engine_core` è definito al di fuori del calculator — lo
tratto come black-box.

### 2. Dai conteggi MC al pronostico

Funzione `decidi_segno_dc(dist, odds, re_dir)` (linea 317).
18 regole hardcoded che mappano `home_win_pct`, `draw_pct`, `away_win_pct`,
`re_dir` (dai top_scores) + quote → decisione (`1`, `X`, `2`, `1X`, `X2`, `12`)
o SKIP.

Esempi (non esaustivo):
- Regola "Favorita ≥70%" → SEGNO puro
- Regola "Favorita 62-70%" → SEGNO o DC in base a quota
- Regola "Pareggio favorito" → DC
- Regola "Piatta" (max<40%, diff<8%) → SKIP o DC se RE forte
- Soglia quota minima `SOGLIA_QUOTA_MIN = 1.30`.

Per GOL c'è logica simile ma più estesa (Over/Under + MG) usando i conteggi
`over_XX_pct` e `avg_goals`.

### 3. `confidence` → `probabilita_stimata` (C)

```python
# linea 853 (run_daily_predictions_engine_c.py):
p['probabilita_stimata'] = round(p['confidence'], 1)
```

In C `probabilita_stimata` è **letteralmente la confidence arrotondata**, cioè
la percentuale dalla distribuzione MC (es. `home_win_pct`, `over_25_pct`, ...).

Non c'è la trasformazione `0.44 + (avg - 50) * 0.015` di A/S. Non ci sono cap
per tipo. **È una probabilità frequentista**.

C'è un altro punto (linea 970) dove `probabilita_stimata = round(prob * 100, 1)`
in un caso di ricalcolo (conversione), ma la logica resta "prob = frequenza
MC".

### 4. DC in C?

C **non emette pronostici DC** direttamente (verificato anche nella diagnostica
al Punto 6: C × DC aveva 0 righe). DC è appannaggio di A/S nel routing del MoE.

---

## MoE Unified (orchestrate_experts.py)

### Routing per mercato

Schema approssimato dal codice `ROUTING`:

| Mercato | Sistemi scelti | Regola |
| --- | --- | --- |
| 1X2 (SEGNO) | C | single (prende da C) |
| DC | A, S | consensus_both |
| Over 1.5 | A, S | consensus_both |
| Over 2.5 | A, S | consensus_both |
| Over 3.5 | C | single |
| Under 2.5 | A | single |
| Under 3.5 | A, S | union |
| Goal | S, C | priority_chain (prima S, fallback C) |
| NoGoal | A, C, S | combo_under_segno |

### Cosa succede al `probabilita_stimata`

- Quando il MoE sceglie un pronostico da A/S: **riusa** il `probabilita_stimata`
  calcolato dai motori (la funzione `calcola_probabilita_stimata` con cap per tipo).
- Quando sceglie da C: **riusa** `probabilita_stimata = confidence` di C.
- Nelle **conversioni** (es. DC→Under 2.5, Goal→Under 2.5): ricalcola usando
  `prob_mod` cablata costante (es. Under 2.5 → 0.70) invece di derivarla dai
  dati del match — vedi `FORMULA_STAKE_ATTUALE.md`.

**Conseguenza**: nel dataset unified convivono `probabilita_stimata` prodotte
da 3 logiche diverse:
1. Trasformazione sub-score → prob (A/S)
2. Frequenza MC (C)
3. Costante hardcoded (conversioni MoE)

Questo spiega l'eterogeneità della calibrazione per source al Punto 1
(delta pesato: A +8.66, C -7.64, C-derivati -4.17): **non misurano la stessa cosa**.

---

## Differenze strutturali A vs S vs C (quadro sinottico)

| Aspetto | A | S | C |
| --- | --- | --- | --- |
| Dataset input | h2h_by_round + teams + seasonal | identico a A | engine_core (ingloba suoi dati) |
| Approccio | sub-motori pesati | sub-motori pesati (pesi diversi) | Monte Carlo 100 cicli |
| `confidence` | media pesata di 9 sub-motori (SEGNO) / 7 (GOL) | identico, pesi diversi | % diretta dalla distribuzione MC |
| `probabilita_stimata` | trasformazione `0.44+(avg-50)*0.015` + bonus + cap | stessa funzione | `= confidence` |
| Cap per tipo | SEGNO 30-78, DC 45-88, GOL 35-80 | idem | nessuno |
| Blend con mercato | NO (modello puro) | NO | NO (frequentista) |
| Mercati emessi | SEGNO, DC, GOL (incluso Over/Under/GG/NG) | idem | SEGNO/DC/GOL ma **no DC diretto**, Over 3.5 specialista |
| THRESHOLD_INCLUDE | 56.5 | 48.9 | 0 (emette tutto che passa regole) |
| Configurabilità | hardcoded | pesi da `prediction_tuning_settings` | interno engine_core |

---

## Cosa significa "probabilita_stimata ≠ confidence"

È importante perché cambia quello che si misura nella diagnostica:

- `confidence` in A/S è la media pesata dei sub-score (cioè quanto il motore
  "si fida" del suo giudizio). È un **indice di convinzione**.
- `probabilita_stimata` in A/S è una **probabilità stimata del risultato**,
  derivata dai sub-score con trasformazione ad hoc.

La differenza è evidente nel fatto che:
- `confidence = 65` → `probabilita_stimata` può essere ovunque tra 50 e 70 a
  seconda di consensus, strong, direction bonus, std dei sub-score.
- In C, `confidence = probabilita_stimata` per costruzione (la frequenza MC
  è "il suo livello di convinzione" e allo stesso tempo la sua stima di p).

Per i calcoli Kelly (stake) si usa `probabilita_stimata`, quindi è il campo
giusto da calibrare. Ma se in futuro si volesse tenere `confidence` per il
rating a stelle e separatamente `probabilita_stimata` per lo stake, questa
distinzione va preservata.

---

## Dati presenti nel DB ma NON USATI dai motori

Esplorando le collection (via `config.db.list_collection_names()` e campionamenti),
i seguenti campi/dataset sono potenzialmente sfruttabili ma oggi non entrano
nel calcolo probabilità:

| Fonte | Campo / Info | Uso attuale | Nota |
| --- | --- | --- | --- |
| `teams` | `lineup_probable`, `injuries`, `suspensions` | Non usati | Formazioni probabili non sono nel flusso |
| `teams` | `yellow_cards`, `red_cards_history` | Non usati | |
| `teams` | `coach_change_date` / equivalenti | Non usati | Cambio allenatore recente |
| `matches_*` / `h2h_by_round` | `sportradar_comments` | Non usati | Commenti testuali, potenziali per AI |
| `matches_*` | `referee`, `stadium` | Non usati | |
| `matches_*` | `weather` (se presente) | Non usati | |
| Documenti match in `daily_predictions_unified` | `streak_home_context` / `streak_away_context` | Usati parzialmente per strisce | Contesto (qualità avversari ultimi 5) — non parametrizzato |
| `classifiche` | `position_change`, `points_to_safe`, `points_to_europa` | Non usati direttamente | Motivazione desumibile |
| `team_seasonal_stats` | `h2h_streak_vs_opponent`, vari campi avanzati | Usati solo xg_avg / total_volume_avg | xG aggiuntivo, vantaggio casa stagionale |
| (non esiste nel DB) | Orario anticipata/posticipata, importanza giornata | Non presente | |

**Caveat**: non ho verificato **ogni** campo in ogni collection — ho fatto
campionamento. Se si vuole una lista esaustiva di campi disponibili serve
un'esplorazione dedicata (eventualmente uno script che per ogni collection
calcoli la union di chiavi usate su N documenti).

---

## Implicazioni per Kelly calibrato

La diagnostica (Punto 1, Punto 3) mostra che `probabilita_stimata` è
**sistematicamente disallineata** dalla HR reale, con pattern diversi per
gruppo source — cioè per ognuna delle 3 logiche sopra. Una ricalibrazione seria
deve tenere conto di:

1. **A/S e C producono scale concettualmente diverse**. Una ricalibrazione
   per bin `(gruppo, mercato, bin prob)` — come fatto al Punto 3 — tiene conto
   della diversità. Va mantenuta quella segmentazione.

2. **I cap per tipo in A/S** (30-78 SEGNO, 45-88 DC, 35-80 GOL) comprimono
   artificialmente la distribuzione. Forse sono troppo stretti (e spiegano
   perché il motore va underconfident sui bin bassi).

3. **C non ha cap ma usa 100 cicli MC**, il che implica una risoluzione ≈1%.
   Questo limita quanto precise possono essere le sue probabilità sulla coda
   (es. 92% significa 92 vittorie su 100, niente valore intermedio). È una
   causa strutturale di overconfidence vicino al 100%.

4. **Per alimentare Kelly calibrato** si può scegliere:
   a. **Ricalibrare ogni source separatamente** (quello che ho fatto al Punto 3),
   lasciando intoccate le formule a monte.
   b. **Unificare le scale**: far sì che A/S e C producano una probabilità
   sulla stessa scala (non compressa dai cap tipo-specifici), poi calibrare
   una volta sola.
   c. **Usare la probabilità ricalibrata come input a Kelly**, bypassando
   `probabilita_stimata` originale. Questa è la via più pulita: Kelly vede
   una prob calibrata vera, non un proxy.

---

## File sorgenti citati (riferimento rapido)

| Cosa | Path | Linea |
| --- | --- | ---: |
| `THRESHOLD_INCLUDE` / `PESI_SEGNO` / `PESI_GOL` (A) | [functions_python/ai_engine/calculators/run_daily_predictions.py](../../functions_python/ai_engine/calculators/run_daily_predictions.py#L74) | 74-99 |
| `analyze_segno()` (A) | [functions_python/ai_engine/calculators/run_daily_predictions.py](../../functions_python/ai_engine/calculators/run_daily_predictions.py#L1920) | ~1920 |
| `analyze_gol()` (A) | [functions_python/ai_engine/calculators/run_daily_predictions.py](../../functions_python/ai_engine/calculators/run_daily_predictions.py#L2357) | ~2357 |
| `calcola_probabilita_stimata()` (A) | [functions_python/ai_engine/calculators/run_daily_predictions.py](../../functions_python/ai_engine/calculators/run_daily_predictions.py#L2678) | 2678 |
| Pesi e soglia S | [functions_python/ai_engine/calculators/run_daily_predictions_sandbox.py](../../functions_python/ai_engine/calculators/run_daily_predictions_sandbox.py#L75) | 75-92 |
| `SIMULATION_CYCLES`, `ALGO_MODE` (C) | [functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py](../../functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py#L20) | 20-21 |
| `run_monte_carlo()` (C) | [functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py](../../functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py#L152) | ~152 |
| `decidi_segno_dc()` (C) | [functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py](../../functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py#L317) | ~317 |
| `probabilita_stimata = confidence` (C) | [functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py](../../functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py#L853) | 853 |
| `_apply_fattore_quota` (MoE) | [functions_python/ai_engine/calculators/orchestrate_experts.py](../../functions_python/ai_engine/calculators/orchestrate_experts.py#L60) | 60 |

---

## Note di onestà

- Alcuni valori esatti di pesi del **Sistema S** vanno riletti direttamente dal
  file (solo `campo` e qualche altro peso sono stati verificati con precisione).
  Per una calibrazione seria apriremo il file e leggeremo riga per riga.
- **Non ho ispezionato `engine_core`** (il black-box usato da C). So cosa
  produce (ranking, attack/defense, cicli MC) ma non i dettagli interni.
  Se serve lo esploriamo come step dedicato.
- **La lista di campi "non usati"** è indicativa. Per avere certezza va fatto
  un dump delle chiavi presenti in ogni collection e un cross-check contro il
  codice dei 3 motori.
