# Punto 1 — Reliability Diagram (Calibrazione)

Dataset: **1456** pronostici con `probabilita_stimata` valorizzata
(su 1501 totali), finestra 2026-02-19 → 2026-04-18.

Bin usati: 35-50, 50-60, 60-70, 70-80, 80+.

Delta = HR reale − probabilità media stimata nel bin.
Delta negativo = overconfident. Delta positivo = underconfident.

## Distribuzione gruppi

| Gruppo | N |
| --- | ---: |
| A | 116 |
| S | 8 |
| C | 519 |
| A+S | 263 |
| C-derivati | 525 |
| Altro | 25 |

## Tabelle per gruppo

### Gruppo A

| Bin | N | Prob. media | HR reale | Delta (HR - prob) |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 8 | 35.91% | 62.50% | +26.59 |
| 50-60 | 53 | 55.57% | 67.92% | +12.35 |
| 60-70 | 39 | 64.22% | 61.54% | -2.68 |
| 70-80 | 16 | 72.38% | 87.50% | +15.12 |
| 80+ | 0 | — | — | — |

### Gruppo S

| Bin | N | Prob. media | HR reale | Delta (HR - prob) |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 0 | — | — | — |
| 50-60 | 3 | 55.77% | 66.67% | +10.90 |
| 60-70 | 3 | 60.63% | 66.67% | +6.03 |
| 70-80 | 1 | 75.00% | 100.00% | +25.00 |
| 80+ | 1 | 80.00% | 0.00% | -80.00 |

### Gruppo C

| Bin | N | Prob. media | HR reale | Delta (HR - prob) |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 86 | 44.58% | 41.86% | -2.72 |
| 50-60 | 107 | 54.23% | 53.27% | -0.96 |
| 60-70 | 151 | 64.89% | 56.95% | -7.94 |
| 70-80 | 120 | 73.30% | 62.50% | -10.80 |
| 80+ | 55 | 84.24% | 63.64% | -20.60 |

### Gruppo A+S

| Bin | N | Prob. media | HR reale | Delta (HR - prob) |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 2 | 49.65% | 50.00% | +0.35 |
| 50-60 | 110 | 56.28% | 64.55% | +8.27 |
| 60-70 | 98 | 63.51% | 62.24% | -1.27 |
| 70-80 | 48 | 71.84% | 68.75% | -3.09 |
| 80+ | 5 | 87.96% | 80.00% | -7.96 |

### Gruppo C-derivati

| Bin | N | Prob. media | HR reale | Delta (HR - prob) |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 107 | 44.51% | 57.01% | +12.50 |
| 50-60 | 125 | 54.38% | 70.40% | +16.02 |
| 60-70 | 81 | 63.76% | 60.49% | -3.26 |
| 70-80 | 186 | 72.47% | 46.24% | -26.23 |
| 80+ | 26 | 84.08% | 69.23% | -14.85 |

### Gruppo Altro

| Bin | N | Prob. media | HR reale | Delta (HR - prob) |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 13 | 46.95% | 38.46% | -8.48 |
| 50-60 | 1 | 54.90% | 100.00% | +45.10 |
| 60-70 | 3 | 61.53% | 100.00% | +38.47 |
| 70-80 | 8 | 70.25% | 62.50% | -7.75 |
| 80+ | 0 | — | — | — |

## Osservazioni oggettive

### Delta medio pesato per gruppo (HR reale - probabilità stimata)

| Gruppo | N totale | Prob. media pesata | HR media | Delta |
| --- | ---: | ---: | ---: | ---: |
| A | 116 | 59.44% | 68.10% | +8.66 |
| S | 8 | 63.03% | 62.50% | -0.52 |
| C | 519 | 63.32% | 55.68% | -7.64 |
| A+S | 263 | 62.37% | 64.64% | +2.27 |
| C-derivati | 525 | 61.70% | 57.52% | -4.17 |
| Altro | 25 | 56.47% | 56.00% | -0.47 |

### Bin con delta significativo (|delta| >= 5 e N >= 30)

| Gruppo | Bin | N | Prob. media | HR | Delta | Tipo |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| A | 50-60 | 53 | 55.57% | 67.92% | +12.35 | underconfident |
| C | 60-70 | 151 | 64.89% | 56.95% | -7.94 | overconfident |
| C | 70-80 | 120 | 73.30% | 62.50% | -10.80 | overconfident |
| C | 80+ | 55 | 84.24% | 63.64% | -20.60 | overconfident |
| A+S | 50-60 | 110 | 56.28% | 64.55% | +8.27 | underconfident |
| C-derivati | 35-50 | 107 | 44.51% | 57.01% | +12.50 | underconfident |
| C-derivati | 50-60 | 125 | 54.38% | 70.40% | +16.02 | underconfident |
| C-derivati | 70-80 | 186 | 72.47% | 46.24% | -26.23 | overconfident |

## File generati

- `calibrazione_per_gruppo.csv` — dati raw
- `reliability_diagram_6gruppi.png` — 6 pannelli
- `reliability_diagram_combined.png` — tutti i gruppi sovrapposti