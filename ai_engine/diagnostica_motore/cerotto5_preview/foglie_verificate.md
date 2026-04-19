# Cerotto 5 — Verifica foglie Decision Tree

**Finestra**: 2026-02-19 → 2026-04-18
**Metodo**: backend-aligned (no dedup, stake pesato, esito not None, esclusi NO BET)

## Baseline globale

- N pronostici validi: **1567**
- HR globale: **57.43%**
- ROI globale (su 1u stake): **+8.73%**
- PL totale (stake pesato): **+136.78u**

## Riepilogo foglie

| Foglia | Condizione | N | HR | Quota media | ROI (1u) | PL (stake pesato, u) | Volume |
|---|---|---:|---:|---:|---:|---:|:---:|
| A | `quota<=1.51 AND mc_avg_goals_away>2.21 AND sig_strisce<=49.75` | 24 | 33.33% | 1.44 | -310.38% | -74.49 | ⚠️ <50 (overfitting?) |
| B | `1.51<quota<=2.20 AND mc_home_win_pct<=49.50` | 573 | 53.05% | 1.75 | -21.76% | -124.66 | ✅ |
| C | `quota>2.20 AND quota_over25<=1.81 AND sig_affidabilita>44.78` | 21 | 28.57% | 4.68 | -23.95% | -5.03 | ⚠️ <50 (overfitting?) |
| D | `quota>2.20 AND quota_over25>1.81` | 85 | 23.53% | 4.26 | -51.56% | -43.83 | ✅ |

## Dettaglio per foglia

### Foglia A

**Condizione**: `quota<=1.51 AND mc_avg_goals_away>2.21 AND sig_strisce<=49.75`

- N = 24
- HR = 33.33% (vs globale 57.43%, Δ = -24.10pp)
- Quota media = 1.44
- ROI (1u) = -310.38%
- PL (stake pesato) = -74.49u

**Distribuzione per scatola**

| Scatola | N | HR | PL (stake pesato) |
|---|---:|---:|---:|
| MIXER | 13 | 23.08% | -53.55u |
| ELITE | 3 | 33.33% | -18.55u |
| AR | 0 | — | 0.00 |
| PRONOSTICI | 8 | 50.00% | -2.39u |

**Sovrapposizione con combo Cerotto 4**

- Pronostici già coperti da almeno una combo C4: **0/24** (0.0%)
- Pronostici NON coperti da C4 (net nuovo filtro): **24/24** (100.0%)

Breakdown per combo C4:

**Sovrapposizione con altre foglie DT**

- Nessuna sovrapposizione con altre foglie

### Foglia B

**Condizione**: `1.51<quota<=2.20 AND mc_home_win_pct<=49.50`

- N = 573
- HR = 53.05% (vs globale 57.43%, Δ = -4.38pp)
- Quota media = 1.75
- ROI (1u) = -21.76%
- PL (stake pesato) = -124.66u

**Distribuzione per scatola**

| Scatola | N | HR | PL (stake pesato) |
|---|---:|---:|---:|
| MIXER | 187 | 51.34% | -67.71u |
| ELITE | 4 | 75.00% | +12.05u |
| AR | 0 | — | 0.00 |
| PRONOSTICI | 382 | 53.66% | -69.00u |

**Sovrapposizione con combo Cerotto 4**

- Pronostici già coperti da almeno una combo C4: **0/573** (0.0%)
- Pronostici NON coperti da C4 (net nuovo filtro): **573/573** (100.0%)

Breakdown per combo C4:

**Sovrapposizione con altre foglie DT**

- Nessuna sovrapposizione con altre foglie

### Foglia C

**Condizione**: `quota>2.20 AND quota_over25<=1.81 AND sig_affidabilita>44.78`

- N = 21
- HR = 28.57% (vs globale 57.43%, Δ = -28.86pp)
- Quota media = 4.68
- ROI (1u) = -23.95%
- PL (stake pesato) = -5.03u

**Distribuzione per scatola**

| Scatola | N | HR | PL (stake pesato) |
|---|---:|---:|---:|
| MIXER | 3 | 0.00% | -10.00u |
| ELITE | 0 | — | 0.00 |
| AR | 15 | 33.33% | +11.53u |
| PRONOSTICI | 3 | 33.33% | -6.56u |

**Sovrapposizione con combo Cerotto 4**

- Pronostici già coperti da almeno una combo C4: **17/21** (81.0%)
- Pronostici NON coperti da C4 (net nuovo filtro): **4/21** (19.0%)

Breakdown per combo C4:
  - C4_1: 8
  - C4_2: 1
  - C4_3: 9
  - C4_4: 1
  - C4_5: 10
  - C4_6: 15
  - C4_7: 1

**Sovrapposizione con altre foglie DT**

- Nessuna sovrapposizione con altre foglie

### Foglia D

**Condizione**: `quota>2.20 AND quota_over25>1.81`

- N = 85
- HR = 23.53% (vs globale 57.43%, Δ = -33.91pp)
- Quota media = 4.26
- ROI (1u) = -51.56%
- PL (stake pesato) = -43.83u

**Distribuzione per scatola**

| Scatola | N | HR | PL (stake pesato) |
|---|---:|---:|---:|
| MIXER | 25 | 36.00% | +31.11u |
| ELITE | 0 | — | 0.00 |
| AR | 46 | 19.57% | -44.14u |
| PRONOSTICI | 14 | 14.29% | -30.80u |

**Sovrapposizione con combo Cerotto 4**

- Pronostici già coperti da almeno una combo C4: **69/85** (81.2%)
- Pronostici NON coperti da C4 (net nuovo filtro): **16/85** (18.8%)

Breakdown per combo C4:
  - C4_1: 48
  - C4_2: 4
  - C4_3: 58
  - C4_4: 4
  - C4_5: 36
  - C4_6: 57
  - C4_7: 4

**Sovrapposizione con altre foglie DT**

- Nessuna sovrapposizione con altre foglie

## Note metodologiche

- Foglie estratte da `DecisionTreeClassifier(max_depth=4, min_samples_leaf=20, class_weight=balanced)` addestrato nel notebook `analisi_professionale.ipynb` (cella 54)
- Campi `mc_*` da `daily_predictions_engine_c.simulation_data`
- Campi `sig_strisce`, `sig_affidabilita` da `daily_predictions.segno_dettaglio`
- Campo `quota_over25` da `daily_predictions_unified.odds.over_25`
- Metodo conforme a Cerotto 4: stake pesato, no dedup, pronostici con `esito not None` e diversi da NO BET
- Scatole non mutuamente esclusive: un pronostico MIXER può avere anche `elite=True`; la priorità qui è MIXER > ELITE > AR > PRONOSTICI

## Soglie di valutazione (per decidere implementazione)

Una foglia va implementata come filtro tossico se SIMULTANEAMENTE:
1. Volume N ≥ 50 (altrimenti overfitting DT, non generalizza)
2. ROI (1u) significativamente negativo (< -5%)
3. HR sotto globale con Δ ≥ -5pp
4. Sovrapposizione con C4 < 80% (altrimenti ridondante)

Se una foglia è dominata da MIXER, ricorda che Cerotto 4 esclude MIXER — stessa logica qui.
