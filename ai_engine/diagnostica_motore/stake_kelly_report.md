# Preview Kelly unificato — Confronto stake vecchio vs nuovo

Dataset: 1456 pronostici storici (19/02 → 18/04/2026).
Letta `calibration_table._id=current` da MongoDB.

## 1. Statistiche globali

| Scope | N | HR | Stake medio old | Stake medio new | PL old tot | PL new tot | Δ PL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| totale | 1456 | 59.00% | 5.21 | 2.87 | +1242.52 | +3075.02 | +1832.50 |
| low_value (edge <= 0) | 727 | 60.11% | 5.1 | 1.0 | -1369.33 | -200.19 | +1169.14 |
| positive_edge | 729 | 57.89% | 5.32 | 4.73 | +2611.85 | +3275.21 | +663.36 |

**Pronostici flaggati low_value**: 727 su 1456 (49.9%)

## 2. Distribuzione delta stake (new - old)

| Δ | N |
| ---: | ---: |
| -9 | 66 |
| -8 | 75 |
| -7 | 64 |
| -6 | 124 |
| -5 | 110 |
| -4 | 137 |
| -3 | 153 |
| -2 | 154 |
| -1 | 118 |
| +0 | 166 |
| +1 | 68 |
| +2 | 62 |
| +3 | 56 |
| +4 | 40 |
| +5 | 10 |
| +6 | 21 |
| +7 | 9 |
| +8 | 11 |
| +9 | 12 |

## 3. Per gruppo source

| Gruppo | N | HR | Stake old | Stake new | PL old | PL new | Δ PL |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 116 | 68.10% | 5.4 | 2.84 | +14.56 | +278.54 | +263.98 |
| S | 8 | 62.50% | 5.25 | 3.0 | +39.75 | +67.74 | +27.99 |
| C | 519 | 55.68% | 5.59 | 3.26 | +1737.15 | +1841.29 | +104.14 |
| A+S | 263 | 64.64% | 5.51 | 2.53 | -51.31 | +251.91 | +303.22 |
| C-derivati | 525 | 57.52% | 4.66 | 2.69 | -532.85 | +661.19 | +1194.04 |
| Altro | 25 | 56.00% | 5.04 | 2.2 | +35.22 | -25.65 | -60.87 |

## 4. Low value — HR e PL dei pronostici flaggati

Un "low_value" è un pronostico per cui Kelly unificato ha calcolato edge <= 0 dopo calibrazione. Stake impostato a 1 (niente NO BET automatico).

- Volume low_value: **727** (49.9% del dataset)
- HR storico low_value: **60.11%**
- ROI/unit (PL medio a stake 1): **-27.54%**
- Con stake vecchio avrebbero contribuito: **PL -1369.33u**
- Con stake nuovo (=1 forzato): **PL -200.19u**
- Delta: **+1169.14u**

## 5. File

- `stake_kelly_preview.csv` — 10 righe campione stratificato per bin prob
- `stake_kelly_simulazione.csv` — dataset intero