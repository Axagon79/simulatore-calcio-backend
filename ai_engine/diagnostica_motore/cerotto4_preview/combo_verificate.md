# Cerotto 4 — Verifica 10 combo tossiche (preview)

Dataset: **1501** pronostici dedupati (MIXER>ELITE>AR>PRONOSTICI), finestra 19/02/2026 → 18/04/2026.

**Definizioni** (dal notebook `c:/Progetti/analisi_professionale.ipynb`, verificate):

- `quota_min_1x2 = min(quota_1, quota_X, quota_2)` dalla partita
- `tipo_partita`: <1.40 dominante, 1.40-1.79 favorita, 1.80-2.29 equilibrata, ≥2.30 aperta
- `fascia_oraria`: hour<15 mattina, 15-17 pomeriggio, 18-20 sera, ≥21 notte
- `categoria`: quota>2.50 Alto Rendimento, altrimenti Pronostici
- `fascia_quota`: 3.00+ = quota≥3.00, 2.50-2.99 = 2.50≤quota<3.00

Nota: il report originale sovrappone `categoria=Alto Rendimento` (quota>2.50) e `fascia_quota=3.00+` (quota≥3.00) — sono filtri quasi identici, molte combo risultano strettamente sovrapposte (vedi task 2).

## Baseline globale

- N = 1501
- HR = 59.09%
- ROI = +9.04%
- PL totale = +135.73u

## 1. Tabella combo (5 colonne richieste + verdetto)

| ID | Combo | Azione | N | HR | Quota media | ROI | PL (u) | Verdetto |
| --- | --- | :---: | ---: | ---: | ---: | ---: | ---: | --- |
| C1 | SEGNO + fascia_quota=3.00+ | Dimezza | 74 | 32.43% | 4.04 | +208.35% | +154.18 | FALSO ALLARME (ROI positivo nonostante HR bassa) |
| C2 | SEGNO + tipo_partita=aperta | SCARTA | 29 | 20.69% | 2.73 | -198.41% | -57.54 | TOSSICA (ROI negativo netto) |
| C3 | SEGNO + categoria=Alto Rendimento | Dimezza | 88 | 31.82% | 3.83 | +155.64% | +136.96 | FALSO ALLARME (ROI positivo nonostante HR bassa) |
| C4 | tipo_partita=aperta + categoria=Alto Rendimento | SCARTA | 19 | 21.05% | 2.91 | -218.89% | -41.59 | TOSSICA (ROI negativo netto) |
| C5 | SEGNO + Monday + tipo_partita=aperta | SCARTA | 9 | 0.00% | 2.81 | -433.33% | -39.00 | TOSSICA (ROI negativo netto) |
| C6 | fascia_oraria=sera + categoria=Alto Rendimento | SCARTA | 41 | 26.83% | 3.70 | -29.76% | -12.20 | TOSSICA (ROI negativo netto) |
| C7 | fascia_quota=3.00+ + categoria=Alto Rendimento | Dimezza | 81 | 34.57% | 3.98 | +247.11% | +200.16 | FALSO ALLARME (ROI positivo nonostante HR bassa) |
| C8 | Friday + fascia_quota=3.00+ + tipo_partita=equilibrata | SCARTA | 8 | 12.50% | 4.01 | -345.88% | -27.67 | TOSSICA (ROI negativo netto) |
| C9 | fascia_quota=2.50-2.99 + tipo_partita=aperta | SCARTA | 17 | 23.53% | 2.65 | -227.00% | -38.59 | TOSSICA (ROI negativo netto) |
| C10 | Friday + categoria=Alto Rendimento | SCARTA | 19 | 15.79% | 3.72 | -264.05% | -50.17 | TOSSICA (ROI negativo netto) |

**Soglia verdetto**: ROI > 0 → FALSO ALLARME. ROI in (-5%, 0] → DUBBIO. ROI ≤ -5% → TOSSICA.

## 2. Sovrapposizione tra combo

- Pronostici univoci colpiti da almeno 1 combo: **112** (7.5% del dataset)
- Distribuzione del numero di combo hit per pronostico:
  - colpiti da 1 combo: 13 pronostici
  - colpiti da 2 combo: 11 pronostici
  - colpiti da 3 combo: 37 pronostici
  - colpiti da 4 combo: 29 pronostici
  - colpiti da 5 combo: 10 pronostici
  - colpiti da 6 combo: 11 pronostici
  - colpiti da 7 combo: 1 pronostici

Matrice diagonale = N singolo (diagonale == task 1). Off-diagonale (i,j) = pronostici colpiti da entrambe Ci e Cj. Vedi file [`sovrapposizioni.csv`](sovrapposizioni.csv).

### Coppie più sovrapposte

| Coppia | Intersezione | % su min(N_i,N_j) |
| --- | ---: | ---: |
| C1 ∩ C3 | 74 | 100.0% |
| C1 ∩ C7 | 74 | 100.0% |
| C1 ∩ C8 | 8 | 100.0% |
| C2 ∩ C5 | 9 | 100.0% |
| C3 ∩ C8 | 8 | 100.0% |
| C7 ∩ C8 | 8 | 100.0% |
| C8 ∩ C10 | 8 | 100.0% |
| C2 ∩ C4 | 18 | 94.7% |
| C3 ∩ C4 | 18 | 94.7% |
| C3 ∩ C7 | 74 | 91.4% |
