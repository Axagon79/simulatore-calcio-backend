# Formula Stake Attuale — Mappa Completa

Mappatura del calcolo stake nei 3 sistemi (A, S, C) + MoE unified, finalizzata
a fornire la base per una ri-implementazione con Kelly calibrato (Punto 3 della
diagnostica).

Finestra analisi: 2026-02-19 → 2026-04-18 (stessa dei punti 1-6).

---

## Panoramica rapida

| Sistema | File principale | Funzione | Kelly | Prob. input |
| --- | --- | --- | :---: | --- |
| A | `functions_python/ai_engine/calculators/run_daily_predictions.py:2761` | `calcola_stake_kelly` | **1/4** (quarter) | `probabilita_stimata` (modello puro) |
| S | `functions_python/ai_engine/calculators/run_daily_predictions_sandbox.py:2746` | `calcola_stake_kelly` | **1/4** (quarter) | `probabilita_stimata` (modello puro) |
| C | `functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py:826` | `apply_kelly` | **3/4** (three-quarter) | `confidence` MC diretta |
| MoE | `functions_python/ai_engine/calculators/orchestrate_experts.py` | conserva stake motori + ricalcola in conversioni | **3/4** (three-quarter) nelle conversioni | `prob_mod` (storico per mercato) |

Copia della formula A/S esiste anche in `backfill_stakes.py:119` (usata per
ripristino retroattivo, non in produzione notturna).

---

## Sistema A (daily_predictions)

**File:** `functions_python/ai_engine/calculators/run_daily_predictions.py`
**Funzione:** `calcola_stake_kelly(quota, probabilita_stimata, tipo='GOL')` (linea 2761)

### Input
- `quota`: quota bookmaker (float)
- `probabilita_stimata`: output di `calcola_probabilita_stimata()`, scala 0-100
- `tipo`: `'SEGNO'` | `'DOPPIA_CHANCE'` | `'GOL'`

### Formula

```python
p = probabilita_stimata / 100
edge_pct = (p * quota - 1) * 100

if p * quota <= 1:
    stake = 1                          # edge negativo → stake minimo
else:
    full_kelly = (p * quota - 1) / (quota - 1)
    quarter_kelly = full_kelly / 4
    stake = round(quarter_kelly * 100) # scala a 1-10
    stake = max(1, min(10, stake))

# --- PROTEZIONI TIPO-SPECIFICHE ---
if tipo == 'SEGNO':
    if quota < 1.30:
        stake = min(stake, 2)          # favorita super: cap stake 2
    elif quota < 1.50:
        stake = min(stake, 4)          # favorita media: cap stake 4

if quota < 1.20:
    stake = min(stake, 2)              # quote bassissime generiche
if probabilita_stimata > 85:
    stake = min(stake, 3)              # overconfidence protection
if quota > 5.00:
    stake = min(stake, 2)              # value trap protection

# --- FATTORE QUOTA A FASCE (post-protezioni) ---
# Vedi sezione dedicata in fondo al documento.
stake = _apply_fattore_quota(stake, quota)

return stake, edge_pct
```

### Come nasce `probabilita_stimata` (Sistema A)

Calcolata in `calcola_probabilita_stimata()` (linea 2678 stesso file). Modello
**puro**, **nessun blend con la quota del mercato**. Differenziata per `tipo`:

```python
# Base (dipende dal tipo):
if tipo == 'SEGNO':
    p_model = 0.44 + (avg_score - 50) * 0.015
elif tipo == 'DOPPIA_CHANCE':
    p_model = 0.52 + (avg_score - 50) * 0.018
elif tipo == 'GOL':
    p_model = 0.42 + (avg_score - 50) * 0.013

# Bonus consensus (a gradini): ≥80% → +3%, ≥70% → +2%, ≥60% → +1%
# Bonus strong signals:        ≥50% → +3%, ≥35% → +2%
# Penalità varianza se std > 12 (valore assoluto esatto nel codice)
# Cap finali per tipo:
#   SEGNO:         30% - 78%
#   DOPPIA_CHANCE: 45% - 88%
#   GOL:           35% - 80%
```

### Output

- `stake`: intero in [1, 10]
- `edge_pct`: float (solo a scopo informativo, non influenza lo stake)

### Post-processing (Sistema A, in isolamento)

Nessuno oltre al Fattore Quota a Fasce, che è **già chiamato dentro**
`calcola_stake_kelly`.

---

## Sistema S (daily_predictions_sandbox)

**File:** `functions_python/ai_engine/calculators/run_daily_predictions_sandbox.py`
**Funzione:** `calcola_stake_kelly(quota, probabilita_stimata, tipo='GOL')` (linea 2746)

**Formula: identica a Sistema A.** Sandbox è un fork di produzione con lo stesso
calcolatore di stake. Differiscono nei parametri di ingresso (pesi, soglie di
scoring) ma non nel calcolo stake.

Stessi input, stessa formula, stessi output, stesso fattore quota.

---

## Sistema C (daily_predictions_engine_c)

**File:** `functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py`
**Funzione:** `apply_kelly(pronostici, dist, odds=None)` (linea 826)

### Input
- `pronostici`: lista di dict pronostico. Usa `p['confidence']` (0-100) come probabilità.
- `dist`: distribuzione Monte Carlo (serve per RE directions modificatore 2)
- `odds`: quote mercato

### Formula

```python
prob = confidence / 100            # prob direttamente dal MC (niente modello secondario)
quota = pronostico['quota']
edge_pct = (prob * quota - 1) * 100

# --- BASE KELLY 3/4 ---
if prob * quota <= 1:
    stake_base = 1.0
else:
    full_kelly = (prob * quota - 1) / (quota - 1)
    tq_kelly = full_kelly * 3 / 4         # 3/4 Kelly, NON 1/4 come A/S
    stake_base = tq_kelly * 10            # scala 1-10

# --- 5 MODIFICATORI (ciascuno ±20%, sommati con cap ±50% totale) ---
mod_pct = 0.0
# 1. Confidence: ≥65 → +20%,  <50 → -20%
# 2. RE confermano la direzione del pronostico: +20%
# 3. Edge value: > 10% → +20%,  < 3% → -20%
# 4. Book contradice il modello: -20%
# 5. Conflitti cross-mercato (Over+NoGoal o Under+Goal): -20%

mod_pct = max(-0.50, min(0.50, mod_pct))
raw_stake = stake_base + stake_base * mod_pct
raw_stake = max(1.0, min(10.0, raw_stake))

# --- STAKE MIN/MAX (range decimale, usato solo da C) ---
floor = int(raw_stake)
decimal_part = raw_stake - floor
if decimal_part > 0.25:
    stake_min, stake_max = floor, floor + 1
else:
    stake_min, stake_max = floor - 1, floor
stake_min = max(1, stake_min)
stake_max = min(10, stake_max)

# --- FATTORE QUOTA A FASCE (applicato a stake, stake_min, stake_max) ---
stake = _apply_fattore_quota(round(raw_stake), quota)
stake_min = _apply_fattore_quota(stake_min, quota)
stake_max = _apply_fattore_quota(stake_max, quota)

return stake, stake_min, stake_max, edge_pct
```

### Differenze chiave rispetto ad A/S

| Aspetto | A / S | C |
| --- | --- | --- |
| Kelly frazionario | 1/4 | **3/4** (3× più aggressivo) |
| Input probabilità | `probabilita_stimata` (modello puro) | `confidence` MC diretta |
| Modificatori ±20% | NO | SÌ (5 fattori, cap ±50%) |
| `stake_min` / `stake_max` | Non presenti | **Presenti** (range decimale) |
| Protezioni quota tossica | SÌ (SEGNO <1.50, prob>85%, quota>5) | NO (non ha protezioni tipo-specifiche) |

### Output

- `stake`: intero in [1, 10]
- `stake_min`, `stake_max`: interi in [1, 10] — range di stake proposto, usato dall'orchestratore
- `edge_pct`: float informativo

---

## MoE Unified (daily_predictions_unified)

**File:** `functions_python/ai_engine/calculators/orchestrate_experts.py`
**Funzione principale di orchestrazione:** `route_predictions()` (linea 2716)

### Comportamento generale

1. **Riuso stake**: Quando il MoE sceglie un pronostico da un motore (A, S o C),
   fa un `deepcopy()` del pronostico originale. **Lo stake è quello calcolato
   dal motore di origine**: NON viene ricalcolato.
2. **Copia anche `stake_min` / `stake_max`** quando il pronostico proviene da C.
3. **Ricalcola da zero SOLO quando**:
   - Converte il pronostico a un mercato diverso (es. SEGNO → Over 2.5, DC → NoGoal, O2.5 → Goal, ...)
   - Combina pronostici in un nuovo mercato (Multi-Gol Poisson, combo #96)
   - Downgrade/upgrade (es. SEGNO stake 7 → stake 5 con cap)
4. **Filtra** (setta `pronostico = 'NO BET'` e `stake = 0`) quando applica regole di scrematura.

### Formula di ricalcolo (usata nelle conversioni)

Usata in decine di funzioni `_apply_*` (vedi lista sotto). Sempre Kelly 3/4.

```python
prob_mod = X              # valore storico "conservativo" per il nuovo mercato,
                          # cablato come costante dentro la funzione di conversione
                          # (es. Under 2.5 storico 92% → prob_mod = 0.70)
prob_mkt = 1.0 / new_quota
edge = prob_mod - prob_mkt

if edge > 0:
    # Formula Kelly esplicita nell'orchestratore:
    kelly = 0.75 * (edge * new_quota - (1 - edge)) / (new_quota - 1)
    stake = max(1, min(10, round(kelly * 10)))
    stake = _apply_fattore_quota(stake, new_quota)
    edge_result = round(edge * 100, 1)
else:
    stake = 1
    edge_result = 0

return stake, edge_result
```

### `prob_mod` cablati per conversione (estratto)

| Conversione | `prob_mod` | Note |
| --- | ---: | --- |
| → Under 2.5 | 0.70 | storico 92% |
| → Over 1.5 | 0.78 | storico 80% |
| → NoGoal | 0.80 | storico 92% |
| → Goal da O2.5 | 0.70 | storico 74% |
| Multi-Gol Poisson | variabile | calcolata da λ (zones) |

### Post-processing MoE (in ordine di esecuzione)

Non-esaustivo ma copre i più impattanti sul stake:

1. `_apply_gol_low_stake_to_nogoal` — Goal bassa confidence → NoGoal (ricalcola stake con prob_mod=0.80)
2. `_apply_gol_stake3_filter` — Over 2.5 stake 3 → NO BET (stake=0)
3. `_apply_gol_stake4_quota_filter` — Over 2.5 stake 4 fascia 1.80-1.89 → NO BET
4. `_apply_gol_stake5_q160_to_nogoal` — GOL stake 5 quota 1.60-1.69 → NoGoal (ricalcola)
5. `_apply_gol_stake7_filter` — GOL stake 7 quote <1.40, MG 2-3, quota 1.90-1.99 → NO BET
6. `_apply_dc_stake1_to_under25` — DC stake 1 → Under 2.5 (ricalcola)
7. `_apply_segno_low_stake_filter` — SEGNO puro stake 1 quota <1.60 → NO BET
8. `_apply_dc_stake4_to_nogoal` — DC stake 4 → NoGoal (ricalcola)
9. `_apply_multigol` — Sostituisce Over/Under/Goal/NoGoal con Multi-Gol Poisson (ricalcola da λ)
10. `_apply_segno_stake7_cap` — SEGNO/DC stake 7 fasce deboli: stake 7 → 5
11. ...altre regole elencate nel Punto 4 parte C della diagnostica

Gli effetti netti di queste regole sono stati misurati al **Punto 4 parte C**:

- Globale: PL conv -7.02u vs PL orig simulato -4.95u → **Δ -2.07u** (conversioni mediamente peggiorative).
- Pattern: **conversioni verso GOL aiutano**, conversioni verso DC o SEGNO peggiorano.

### Fattore Quota a Fasce (shared)

Definito in `orchestrate_experts.py:60` come `_apply_fattore_quota(stake, quota)`:

```python
def _apply_fattore_quota(stake, quota):
    if not quota or quota <= 0:
        return stake
    if quota < 1.50:
        fattore = 2.00 / quota
    elif quota < 2.00:
        return stake                 # nessun aggiustamento
    elif quota < 2.50:
        fattore = 2.20 / quota
    elif quota < 3.50:
        fattore = 2.00 / quota
    elif quota < 5.00:
        fattore = 3.50 / quota
    else:
        return stake                 # nessun aggiustamento
    return max(1, min(10, round(stake * fattore)))
```

**Effetto pratico per fascia quota (stake pre-fattore = 5):**

| Quota | Fattore | Stake post |
| --- | --- | ---: |
| 1.40 | 2.00/1.40 = 1.43 | 7 |
| 1.75 | — (nessuno) | 5 |
| 2.20 | 2.20/2.20 = 1.00 | 5 |
| 3.00 | 2.00/3.00 = 0.67 | 3 |
| 4.00 | 3.50/4.00 = 0.875 | 4 |
| 6.00 | — (nessuno) | 5 |

Il fattore **spinge in alto** su quote <1.50 (boost aggressivo) e **comprime** su
quote 2.50-3.50 (-33%).

**Nota diagnostica:** al Punto 3 abbiamo misurato che lo stake attuale è in
media **+3.43 posizioni sopra Kelly calibrato 0.25 nel bin prob 60-70%** (il
più problematico). Il fattore quota a fasce è uno dei responsabili principali
di questa over-stake.

---

## Risposte alle domande esplicite

### 1. I 3 motori hanno la stessa formula?

No.

- **A e S**: formula **identica**, Kelly 1/4 con protezioni tipo-specifiche + fattore quota.
- **C**: formula **diversa**, Kelly 3/4 con 5 modificatori proporzionali + fattore quota. Niente protezioni tipo-specifiche.

L'aggressività strutturale è molto diversa: **Kelly 3/4 su C vs Kelly 1/4 su A/S → C punta 3× in più a parità di edge**.

### 2. L'unified riusa o ricalcola?

**Riusa** nella maggior parte dei casi (deepcopy del pronostico dal motore di
provenienza). **Ricalcola da zero** solo per:

- Conversioni di mercato (cambia `tipo` o `pronostico`)
- Combo nuove (Multi-Gol, combo #96)
- Filtri (→ NO BET, stake = 0)

I cap (es. `_apply_segno_stake7_cap`) invece **modificano** lo stake esistente senza ricalcolo.

### 3. Ci sono differenze tra mercati?

Sì:

- **A/S**: protezioni tipo-specifiche solo su SEGNO (cap a stake 2/4 a seconda della quota). Cap generali (overconfidence, quota>5) applicati a tutti.
- **C**: nessuna protezione tipo-specifica a livello di stake, ma il modificatore "conflitti cross-mercato" penalizza Over+NoGoal o Under+Goal.
- **MoE**: tutte le regole di conversione/filtro sono specifiche per mercato — il comportamento sul stake post-unified è fortemente dipendente dal mercato.

### 4. `stake_min` / `stake_max`?

- **A / S**: non producono questi campi.
- **C**: li produce, come range decimale intorno a `raw_stake`, clampato in [1, 10] e passato nel fattore quota.
- **MoE**: eredita `stake_min` / `stake_max` da C in deepcopy. Nelle conversioni non li ricalcola (potenziale buco).

Nel dataset di produzione `stake_min` / `stake_max` appaiono solo sui
pronostici di origine C o C-derivati. Per A/S non sono valorizzati.

### 5. Kelly frazionario

- **A / S**: Kelly 1/4 → `quarter_kelly = full_kelly / 4`
- **C**: Kelly 3/4 → `tq_kelly = full_kelly * 3 / 4`
- **MoE conversioni**: Kelly 3/4 esplicito → `kelly = 0.75 * (edge * quota - (1 - edge)) / (quota - 1)`

**Nessun sistema usa full Kelly.** Tutti sono teoricamente conservativi, ma
il fattore quota a fasce può moltiplicare lo stake fino a **×2.33** (per
quota 1.50 → 2.00/1.50) o **×1.43** (quota 1.40 → 2.00/1.40). In pratica sulle
quote <1.50 un quarter Kelly viene convertito in quasi-Kelly pieno.

---

## Incoerenze e punti di attenzione rilevati

1. **Frammentazione della formula**: la stessa formula A/S è duplicata in 3
   file (`run_daily_predictions.py`, `run_daily_predictions_sandbox.py`,
   `backfill_stakes.py`). Modifiche future devono toccare tutti e 3.

2. **Probabilità di input incoerenti**:
   - A/S: modello puro (`calcola_probabilita_stimata`) con cap per tipo
   - C: `confidence` MC senza ri-modellazione
   - MoE: `prob_mod` cablati per conversione (costanti ad hoc)
   Non esiste un "canale" comune di probabilità calibrata — la Diagnosi ha
   misurato che le probabilità dichiarate sono sistematicamente disallineate
   dalla HR reale (Punto 1).

3. **Kelly aggressivo in C + fattore quota moltiplicativo**: C è 3× più
   aggressivo di A/S e poi passa anche dal fattore quota. Su fascia quota
   1.30-1.50 il risultato è uno stake vicino al cap 10. Questo spiega lo
   stake medio più alto osservato nel Punto 3 (6.85 nel bin prob 80+).

4. **`stake_min`/`stake_max` asimmetrici**: esistono solo per C e non sono
   aggiornati dall'orchestratore nelle conversioni → i valori in DB per
   pronostici convertiti possono essere residui del motore originale.

5. **Cap/floor non uniformi**:
   - A/S hanno cap tipo-specifici (SEGNO <1.50, prob>85%, ecc.)
   - C non ha cap tipo-specifici
   - MoE applica cap post-routing (`_apply_segno_stake7_cap`, filtri scrematura)
   Un pronostico SEGNO quota 1.40 passa da protezione A/S (stake max 4), ma
   lo stesso pronostico **da C puro** non ha questo cap.

---

## Implicazioni per la ri-implementazione Kelly calibrato

Dal **Punto 3** è emerso che Kelly calibrato 0.25 (usando la HR reale del
Punto 1 come probabilità) genera **+2938u vs +1243u dello stake attuale** con
metà del drawdown. Se si procede con ri-implementazione:

1. **Centralizzare il calcolo stake**: una sola funzione in un modulo
   condiviso (es. `ai_engine/stake_kelly.py`), chiamata da A/S/C/MoE/backfill.

2. **Unificare il canale probabilità**: invece di 4 input diversi, definire
   una funzione `get_calibrated_probability(source, tipo, prob_raw, quota,
   league?)` che applichi la ricalibrazione da bin (shrinkage come nel Punto 3).

3. **Rimuovere / ridisegnare Fattore Quota a Fasce**: la diagnostica mostra
   che è il principale driver dell'overbet sul bin prob 60-70%. Va valutato
   se tenerlo (con coefficienti rivisti) o rimuoverlo lasciando fare a Kelly
   calibrato.

4. **Mantenere Kelly 0.25 come default**: al Punto 3 dà il miglior profilo
   di ROI/unità (+78%) e il miglior drawdown gestibile.

5. **`stake_min` / `stake_max`**: se si mantiene la logica range, applicarla
   coerentemente a tutti i sistemi o rimuoverla del tutto.

---

## File sorgenti citati (riferimento rapido)

| Cosa | Path | Linea |
| --- | --- | ---: |
| `calcola_stake_kelly` (A) | [functions_python/ai_engine/calculators/run_daily_predictions.py](../../functions_python/ai_engine/calculators/run_daily_predictions.py#L2761) | 2761 |
| `calcola_stake_kelly` (S) | [functions_python/ai_engine/calculators/run_daily_predictions_sandbox.py](../../functions_python/ai_engine/calculators/run_daily_predictions_sandbox.py#L2746) | 2746 |
| `apply_kelly` (C) | [functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py](../../functions_python/ai_engine/calculators/run_daily_predictions_engine_c.py#L826) | 826 |
| `_apply_fattore_quota` (MoE) | [functions_python/ai_engine/calculators/orchestrate_experts.py](../../functions_python/ai_engine/calculators/orchestrate_experts.py#L60) | 60 |
| `route_predictions` (MoE) | [functions_python/ai_engine/calculators/orchestrate_experts.py](../../functions_python/ai_engine/calculators/orchestrate_experts.py#L2716) | 2716 |
| `calcola_stake_kelly` (backfill) | [backfill_stakes.py](../../backfill_stakes.py#L119) | 119 |
| `calcola_probabilita_stimata` (A) | [functions_python/ai_engine/calculators/run_daily_predictions.py](../../functions_python/ai_engine/calculators/run_daily_predictions.py#L2678) | 2678 |
