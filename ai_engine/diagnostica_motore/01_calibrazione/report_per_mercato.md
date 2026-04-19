# Punto 1 (esteso) — Calibrazione per Gruppo × Mercato

Dataset: **1456** pronostici con `probabilita_stimata`.

## 1. Calibrazione per mercato (ignorando gruppo source)

| Mercato | N tot | Prob. media pesata | HR pesata | Delta |
| --- | ---: | ---: | ---: | ---: |
| SEGNO | 405 | 62.52% | 50.12% | -12.40 |
| DOPPIA_CHANCE | 265 | 56.92% | 60.75% | +3.84 |
| GOL | 786 | 63.69% | 62.98% | -0.72 |

### Mercato SEGNO

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 86 | 44.58% | 41.86% | -2.72 |
| 50-60 | 93 | 53.61% | 56.99% | +3.38 |
| 60-70 | 64 | 64.34% | 56.25% | -8.09 |
| 70-80 | 117 | 73.44% | 41.88% | -31.56 |
| 80+ | 45 | 84.24% | 64.44% | -19.80 |

### Mercato DOPPIA_CHANCE

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 84 | 44.52% | 54.76% | +10.25 |
| 50-60 | 80 | 54.75% | 73.75% | +19.00 |
| 60-70 | 45 | 63.03% | 60.00% | -3.03 |
| 70-80 | 48 | 71.57% | 50.00% | -21.57 |
| 80+ | 8 | 86.48% | 62.50% | -23.97 |

### Mercato GOL

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 46 | 43.93% | 56.52% | +12.60 |
| 50-60 | 226 | 55.72% | 63.27% | +7.55 |
| 60-70 | 266 | 64.30% | 60.90% | -3.40 |
| 70-80 | 214 | 72.38% | 65.89% | -6.50 |
| 80+ | 34 | 84.00% | 67.65% | -16.35 |

## 2. Matrice completa: gruppo × mercato × bin

### Riepilogo pesato (delta medio per cella gruppo × mercato)

| Gruppo \ Mercato | SEGNO | DOPPIA_CHANCE | GOL |
| --- | :---: | :---: | :---: |
| A | — | — | N=116, Δ=+8.66 |
| S | — | — | N=8, Δ=-0.52 |
| C | N=331, Δ=-6.46 | — | N=188, Δ=-9.72 |
| A+S | — | N=54, Δ=+10.67 | N=209, Δ=+0.10 |
| C-derivati | N=71, Δ=-39.07 | N=211, Δ=+2.09 | N=243, Δ=+0.59 |
| Altro | N=3, Δ=-36.67 | — | N=22, Δ=+4.46 |

### Tabelle dettagliate (ogni cella)

### A × GOL

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 8 | 35.91% | 62.50% | +26.59 |
| 50-60 | 53 | 55.57% | 67.92% | +12.35 |
| 60-70 | 39 | 64.22% | 61.54% | -2.68 |
| 70-80 | 16 | 72.38% | 87.50% | +15.12 |
| 80+ | 0 | — | — | — |

### S × GOL

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 0 | — | — | — |
| 50-60 | 3 | 55.77% | 66.67% | +10.90 |
| 60-70 | 3 | 60.63% | 66.67% | +6.03 |
| 70-80 | 1 | 75.00% | 100.00% | +25.00 |
| 80+ | 1 | 80.00% | 0.00% | -80.00 |

### C × SEGNO

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 86 | 44.58% | 41.86% | -2.72 |
| 50-60 | 93 | 53.61% | 56.99% | +3.38 |
| 60-70 | 59 | 64.29% | 59.32% | -4.97 |
| 70-80 | 48 | 73.62% | 52.08% | -21.54 |
| 80+ | 45 | 84.24% | 64.44% | -19.80 |

### C × GOL

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 0 | — | — | — |
| 50-60 | 14 | 58.36% | 28.57% | -29.79 |
| 60-70 | 92 | 65.28% | 55.43% | -9.85 |
| 70-80 | 72 | 73.08% | 69.44% | -3.64 |
| 80+ | 10 | 84.20% | 60.00% | -24.20 |

### A+S × DOPPIA_CHANCE

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 2 | 49.65% | 50.00% | +0.35 |
| 50-60 | 24 | 56.37% | 87.50% | +31.13 |
| 60-70 | 17 | 63.38% | 58.82% | -4.55 |
| 70-80 | 6 | 75.73% | 66.67% | -9.07 |
| 80+ | 5 | 87.96% | 80.00% | -7.96 |

### A+S × GOL

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 0 | — | — | — |
| 50-60 | 86 | 56.25% | 58.14% | +1.88 |
| 60-70 | 81 | 63.54% | 62.96% | -0.58 |
| 70-80 | 42 | 71.29% | 69.05% | -2.24 |
| 80+ | 0 | — | — | — |

### C-derivati × SEGNO

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 0 | — | — | — |
| 50-60 | 0 | — | — | — |
| 60-70 | 5 | 65.00% | 20.00% | -45.00 |
| 70-80 | 66 | 73.47% | 34.85% | -38.62 |
| 80+ | 0 | — | — | — |

### C-derivati × DOPPIA_CHANCE

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 82 | 44.39% | 54.88% | +10.49 |
| 50-60 | 56 | 54.05% | 67.86% | +13.80 |
| 60-70 | 28 | 62.82% | 60.71% | -2.11 |
| 70-80 | 42 | 70.98% | 47.62% | -23.36 |
| 80+ | 3 | 84.00% | 33.33% | -50.67 |

### C-derivati × GOL

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 25 | 44.92% | 64.00% | +19.08 |
| 50-60 | 69 | 54.65% | 72.46% | +17.81 |
| 60-70 | 48 | 64.17% | 64.58% | +0.41 |
| 70-80 | 78 | 72.42% | 55.13% | -17.29 |
| 80+ | 23 | 84.09% | 73.91% | -10.17 |

### Altro × SEGNO

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 0 | — | — | — |
| 50-60 | 0 | — | — | — |
| 60-70 | 0 | — | — | — |
| 70-80 | 3 | 70.00% | 33.33% | -36.67 |
| 80+ | 0 | — | — | — |

### Altro × GOL

| Bin | N | Prob. media | HR reale | Delta |
| --- | ---: | ---: | ---: | ---: |
| 35-50 | 13 | 46.95% | 38.46% | -8.48 |
| 50-60 | 1 | 54.90% | 100.00% | +45.10 |
| 60-70 | 3 | 61.53% | 100.00% | +38.47 |
| 70-80 | 5 | 70.40% | 80.00% | +9.60 |
| 80+ | 0 | — | — | — |

## Osservazioni oggettive

### Bin con delta significativo (|delta| ≥ 5 e N ≥ 30)

| Gruppo | Mercato | Bin | N | Prob. | HR | Delta | Tipo |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| A | GOL | 50-60 | 53 | 55.57% | 67.92% | +12.35 | underconfident |
| C | SEGNO | 70-80 | 48 | 73.62% | 52.08% | -21.54 | overconfident |
| C | SEGNO | 80+ | 45 | 84.24% | 64.44% | -19.80 | overconfident |
| C | GOL | 60-70 | 92 | 65.28% | 55.43% | -9.85 | overconfident |
| C-derivati | SEGNO | 70-80 | 66 | 73.47% | 34.85% | -38.62 | overconfident |
| C-derivati | DOPPIA_CHANCE | 35-50 | 82 | 44.39% | 54.88% | +10.49 | underconfident |
| C-derivati | DOPPIA_CHANCE | 50-60 | 56 | 54.05% | 67.86% | +13.80 | underconfident |
| C-derivati | DOPPIA_CHANCE | 70-80 | 42 | 70.98% | 47.62% | -23.36 | overconfident |
| C-derivati | GOL | 50-60 | 69 | 54.65% | 72.46% | +17.81 | underconfident |
| C-derivati | GOL | 70-80 | 78 | 72.42% | 55.13% | -17.29 | overconfident |

### Delta pesato per mercato (ordinamento per grandezza assoluta)

| Mercato | N | Prob. | HR | Delta | Natura |
| --- | ---: | ---: | ---: | ---: | --- |
| SEGNO | 405 | 62.52% | 50.12% | -12.40 | overconfident |
| DOPPIA_CHANCE | 265 | 56.92% | 60.75% | +3.84 | underconfident |
| GOL | 786 | 63.69% | 62.98% | -0.72 | overconfident |

## File generati

- `calibrazione_per_mercato.csv`
- `calibrazione_matrice_completa.csv`
- `reliability_per_mercato.png`
- `reliability_matrice.png`