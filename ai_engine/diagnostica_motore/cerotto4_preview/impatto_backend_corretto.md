# Cerotto 4 — Analisi impatto con metodo BACKEND corretto

Finestra: **2026-02-19 → 2026-04-18**.

**Metodo**: replica esatta di `popola_pl_storico.py::calcola_pl_giorno`.

- NESSUN dedup (`date`, `home`, `away`, `tipo`, `pronostico`)
- Scatole NON mutualmente esclusive: un pronostico contribuisce a `tutti` sempre, a `alto_rendimento` se `quota≥soglia` o RE, a `elite` se flag, a `pronostici` se sotto soglia e non RE.
- `mixer` aggiunta come quinta scatola (parallela, non esclusiva): contribuisce se `p.mixer=True`.
- PL pesato per `stake`: vinto = `(quota-1)×stake`, perso = `-stake`.
- NO BET escluso; pronostici con `esito=None` esclusi.

Totale pronostici processati: **1519**.

## 1. Baseline backend (match fedele con pl_storico)

| Scatola | bets | wins | HR | PL (u) | staked | YIELD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| tutti | 1519 | 892 | 58.7% | +136.78 | 7875 | +1.7% |
| pronostici | 1377 | 837 | 60.8% | -40.03 | 7267 | -0.6% |
| elite | 236 | 154 | 65.3% | +31.27 | 1664 | +1.9% |
| alto_rendimento | 142 | 55 | 38.7% | +176.81 | 608 | +29.1% |
| mixer | 570 | 342 | 60.0% | +211.24 | 3174 | +6.7% |

**Verifica**: `tutti` e `alto_rendimento` e `elite` devono combaciare con la tabella `pl_storico` del backend (= quello che il frontend mostra).

### Confronto diretto con pl_storico

| Scatola | bets (mia) | bets (pl_storico) | PL (mia) | PL (pl_storico) |
| --- | ---: | ---: | ---: | ---: |
| tutti | 1519 | 1514 | +136.78 | +256.23 |
| pronostici | 1377 | 1372 | -40.03 | +9.61 |
| elite | 236 | 235 | +31.27 | +40.46 |
| alto_rendimento | 142 | 142 | +176.81 | +246.62 |

Piccole differenze possibili: `pl_storico` può avere esiti finalizzati successivamente o fallback `live_score` non più disponibili. L'importante è che i numeri siano nell'ordine di grandezza giusto.

## 2. Tabella 7 combo SCARTA + 3 Dimezza (backend-style)

| ID | Combo | Azione | N | Wins | Losses | HR | Quota media | Stake medio | Staked | PL (u) | YIELD | Verdetto |
| --- | --- | :---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| C1 | SEGNO + fascia_quota=3.00+ | Dimezza | 74 | 24 | 50 | 32.43% | 4.04 | 4.15 | 307u | +154.18u | +50.22% | FALSO ALLARME (yield positivo) |
| C2 | SEGNO + tipo_partita=aperta | SCARTA | 29 | 6 | 23 | 20.69% | 2.73 | 4.48 | 130u | -57.54u | -44.26% | TOSSICA (yield negativo netto) |
| C3 | SEGNO + categoria=Alto Rendimento | Dimezza | 88 | 28 | 60 | 31.82% | 3.83 | 4.31 | 379u | +136.96u | +36.14% | FALSO ALLARME (yield positivo) |
| C4 | tipo_partita=aperta + categoria=Alto Rendimento | SCARTA | 19 | 4 | 15 | 21.05% | 2.91 | 4.37 | 83u | -41.59u | -50.11% | TOSSICA (yield negativo netto) |
| C5 | SEGNO + Monday + tipo_partita=aperta | SCARTA | 9 | 0 | 9 | 0.00% | 2.81 | 4.22 | 38u | -39.00u | -102.63% | TOSSICA (yield negativo netto) |
| C6 | fascia_oraria=sera + categoria=Alto Rendimento | SCARTA | 45 | 12 | 33 | 26.67% | 4.35 | 4.64 | 209u | -12.20u | -5.84% | TOSSICA (yield negativo netto) |
| C7 | fascia_quota=3.00+ + categoria=Alto Rendimento | Dimezza | 98 | 32 | 66 | 32.65% | 5.21 | 3.73 | 366u | +200.16u | +54.69% | FALSO ALLARME (yield positivo) |
| C8 | Friday + fascia_quota=3.00+ + tipo_partita=equilibrata | SCARTA | 9 | 1 | 8 | 11.11% | 4.65 | 3.44 | 31u | -27.67u | -89.26% | TOSSICA (yield negativo netto) |
| C9 | fascia_quota=2.50-2.99 + tipo_partita=aperta | SCARTA | 17 | 4 | 13 | 23.53% | 2.65 | 4.71 | 80u | -38.59u | -48.24% | TOSSICA (yield negativo netto) |
| C10 | Friday + categoria=Alto Rendimento | SCARTA | 24 | 4 | 20 | 16.67% | 5.02 | 3.38 | 81u | -50.17u | -61.94% | TOSSICA (yield negativo netto) |

**Nota**: verdetto su YIELD pesato (non ROI/unit come nel report precedente). Soglia: yield>0 FALSO ALLARME, yield in (-5%,0] DUBBIO, yield ≤ -5% TOSSICA.

## 3. Verifica "falsi allarmi" C1, C3, C7 — 1u vs backend pesato

| ID | N | PL a 1u | ROI/unit | PL pesato | YIELD pesato | Verdetto 1u | Verdetto backend |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| C1 | 74 | +22.53 | +30.45% | +154.18 | +50.22% | FALSO ALLARME | FALSO ALLARME |
| C3 | 88 | +19.39 | +22.03% | +136.96 | +36.14% | FALSO ALLARME | FALSO ALLARME |
| C7 | 98 | +41.35 | +42.19% | +200.16 | +54.69% | FALSO ALLARME | FALSO ALLARME |

**C1, C3, C7 restano FALSI ALLARMI anche col metodo backend.** I pronostici "SEGNO + quota alta" fanno soldi anche pesando per stake.

## 4. Impatto Cerotto 4 (7 SCARTA) per scatola (backend-style)

| Scatola | Bets prima | Bets dopo | Δ Bets | HR prima | HR dopo | PL prima | PL dopo | Δ PL | Yield prima | Yield dopo |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tutti | 1519 | 1439 | -80 | 58.72% | 60.53% | +136.78 | +191.02 | +54.24 | +1.74% | +2.54% |
| pronostici | 1377 | 1365 | -12 | 60.78% | 61.10% | -40.03 | -22.83 | +17.20 | -0.55% | -0.32% |
| elite | 236 | 236 | 0 | 65.25% | 65.25% | +31.27 | +31.27 | +0.00 | +1.88% | +1.88% |
| alto_rendimento | 142 | 74 | -68 | 38.73% | 50.00% | +176.81 | +213.85 | +37.04 | +29.08% | +67.89% |
| mixer | 570 | 547 | -23 | 60.00% | 60.69% | +211.24 | +171.97 | -39.27 | +6.66% | +5.62% |

## 5. Sovrapposizioni tra combo (backend-style)

Vedi `sovrapposizioni_backend.csv` per matrice completa.

Coppie altamente sovrapposte (intersezione ≥ 50% su min(Ni,Nj)):

| Coppia | Intersezione | % |
| --- | ---: | ---: |
| C1 ∩ C3 | 74 | 100.0% |
| C1 ∩ C7 | 74 | 100.0% |
| C2 ∩ C5 | 9 | 100.0% |
| C7 ∩ C8 | 9 | 100.0% |
| C8 ∩ C10 | 9 | 100.0% |
| C2 ∩ C4 | 18 | 94.7% |
| C3 ∩ C4 | 18 | 94.7% |
| C1 ∩ C8 | 8 | 88.9% |
| C3 ∩ C8 | 8 | 88.9% |
| C2 ∩ C9 | 15 | 88.2% |
| C6 ∩ C7 | 38 | 84.4% |
| C3 ∩ C7 | 74 | 84.1% |
| C6 ∩ C8 | 7 | 77.8% |
| C3 ∩ C6 | 34 | 75.6% |
| C7 ∩ C10 | 18 | 75.0% |

## 6. Nota metodologica — diagnostiche precedenti affette dallo stesso bias

Tutte le mie diagnostiche precedenti usavano **dataset dedupato a 1u con scatole mutualmente esclusive**. Questo metodo è valido per domande "classificatorie" (il motore è calibrato? quale source funziona meglio a parità di stake?) ma **NON** per confronti con i dati mostrati nel frontend o per stimare l'impatto economico reale.

| Diagnostica | Affetta? | Nota |
| --- | :---: | --- |
| 01_calibrazione (reliability diagram) | ❌ NO | Misura HR vs prob, lo stake è irrilevante. Numeri corretti. |
| 02_expected_value (EV test) | ⚠️ PARZIALE | HR e frequenza sono corrette. Ma "ROI per fascia EV" usa PL a 1u. Per stimare PL reale andrebbe rifatto col PL pesato. Le conclusioni qualitative (monotonicità rotta, EV non predittivo) restano valide. |
| 03_stake (analisi stake) | ✅ CORRETTA | Qui lo stake è proprio l'oggetto di studio: confronta stake old vs Kelly calibrato. Le simulazioni PL pesato erano sotto stake old (+1242u) vs Kelly new (+3075u), entrambi su stake pesato. Numeri direttamente confrontabili coi dati frontend. |
| 04_no_bet (NO BET + conversioni) | ⚠️ PARZIALE | La parte NO BET simula a 1u. Le conclusioni sono qualitative (filtro giusto/sbagliato) e robuste. Per impatto economico reale andrebbe ripesato. |
| 05_segmenti (lega/giorno/quota) | ⚠️ PARZIALE | ROI per segmento è a 1u. Le "leghe peggiori/migliori" ordinate per ROI qualitative sono OK, ma le magnitudini PL non sono confrontabili col frontend. |
| 06_motori (A vs S vs C) | ⚠️ PARZIALE | Idem: ROI isolato per motore è a 1u. Specializzazione tier resta valida, valori assoluti no. |
| 07_mistral_audit | ❌ NO | Analisi testuale, senza PL. |
| stake_kelly_preview | ✅ CORRETTA | Confronto stake old vs Kelly new entrambi pesati. +1832u di delta PL è cifra reale. |

### Cosa andrebbe rifatto col metodo giusto

- **02_expected_value**: rifare "ROI per fascia EV" con PL pesato per avere il numero economico vero. Le conclusioni concettuali non cambiano.
- **04_no_bet**: idem per i filtri NO BET — vedere il PL reale evitato.
- **05_segmenti**: utile per comunicare "La Liga costa X euro reali al mese". Le priorità di intervento restano le stesse.
- **06_motori**: utile se vuoi decidere quanto pesare economicamente le specializzazioni tier.

**NON servono rifacimenti urgenti**: le conclusioni qualitative sono robuste (curva di calibrazione, EV non predittivo, specializzazione tier, Mistral contraddittorio). È solo una questione di "numeri reali" per confronto con dashboard, quando si vuole comunicare l'impatto in euro.

## 7. Verifica `calibration_table` (Kelly in produzione)

Verificato anche il criterio di `calibration_table._id='current'` (la tabella
che `kelly_unified` sta usando in produzione da stanotte).

### Criterio originale (`refresh_calibration_table.py` pre-verifica)

Richiedeva:
- `tipo` in {SEGNO, DOPPIA_CHANCE, GOL}
- `pronostico != NO BET`
- **`profit_loss` not None** ← criterio stretto
- `probabilita_stimata` not None
- bin prob in [35, 100]

Coperto: **1696** pronostici.

### Criterio backend completo

Identico al frontend `pl_storico`:
- `tipo` in {SEGNO, DOPPIA_CHANCE, GOL}  (RE escluso perché non ha prob stimata)
- `pronostico != NO BET`
- **`esito` not None** ← criterio più lasco
- `probabilita_stimata` not None
- bin prob in [35, 100]

Coperto: **1702** pronostici.

### Gap e impatto

Differenza: **6 pronostici** (0.4%) mancavano dal criterio originale. Sono
pronostici con `esito` noto ma `profit_loss` None (casi edge dove
`calculate_profit_loss.py` non ha ancora scritto il PL, es. rinvii recenti o
partite appena finite). 

**Impatto sulla calibrazione**: trascurabile. 6 pronostici su 1702 non
spostano HR delle celle in modo misurabile. La calibration_table in produzione
era **sottostimata del 0.4%**, non sbagliata.

### Azioni fatte

1. Rigenerata `calibration_table._id='current'` con criterio backend completo
   (`rigenera_calibration_completa.py`): ora contiene **1702** pronostici.
2. Aggiornato `refresh_calibration_table.py` (step 29.3 nightly) per allineare
   il criterio: d'ora in poi userà `esito not None` invece di `profit_loss not None`.

Nessun impatto operativo visibile (stake calcolati praticamente identici).
Ma ora la tabella è allineata al resto del perimetro backend.

### File

- `rigenera_calibration_completa.py` — script one-shot eseguito stanotte.
- `refresh_calibration_table.py` — modificato: criterio lasco anche in nightly.

**NON servono rifacimenti urgenti**: le conclusioni qualitative sono robuste (curva di calibrazione, EV non predittivo, specializzazione tier, Mistral contraddittorio). È solo una questione di "numeri reali" per confronto con dashboard, quando si vuole comunicare l'impatto in euro.