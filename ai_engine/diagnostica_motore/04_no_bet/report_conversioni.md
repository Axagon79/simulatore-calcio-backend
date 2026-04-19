# Punto 4 (parte C) — Analisi conversioni di scrematura

Finestra: 2026-02-19 → 2026-04-18.
Pronostici convertiti (routing_rule/source contiene `_conv` o `_rec`,
con `original_pronostico` e `original_quota` valorizzati): **160**.
Risolti (entrambi i PL disponibili): **160**.

Confronto per unità (1u stake):
- `pl_conv_1u`: PL reale del pronostico convertito, diviso lo stake.
- `pl_orig_1u`: PL simulato del pronostico originale (prima della conversione) a 1u.
- `delta`: pl_conv − pl_orig. Positivo = la conversione ha migliorato.

## 1. Riepilogo globale

| N | PL conv (1u) | PL orig (1u) | Δ | ROI conv | ROI orig | HR conv | HR orig | Salvate | Peggiorate |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 160 | -7.02 | -4.95 | -2.07 | -4.39% | -3.09% | 54.37% | 55.00% | 47 | 48 |

## 2. Per tipo di conversione (mercato orig → mercato conv)

| Conversione | N | PL conv (1u) | PL orig (1u) | Δ | ROI conv | ROI orig | Salvate | Peggiorate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| GOL → GOL | 78 | -5.01 | -6.58 | +1.57 | -6.43% | -8.44% | 27 | 27 |
| SEGNO → GOL | 26 | +2.65 | +0.25 | +2.40 | +10.20% | +0.96% | 11 | 4 |
| DOPPIA_CHANCE → GOL | 24 | +3.32 | -0.42 | +3.74 | +13.83% | -1.75% | 4 | 5 |
| GOL → DOPPIA_CHANCE | 21 | -1.91 | +1.92 | -3.83 | -9.07% | +9.14% | 4 | 9 |
| SEGNO → DOPPIA_CHANCE | 6 | -3.00 | +1.63 | -4.64 | -50.08% | +27.17% | 1 | 2 |
| GOL → SEGNO | 5 | -3.07 | -1.75 | -1.32 | -61.33% | -35.00% | 0 | 1 |

## 3. Per routing_rule (top 20 per volume)

| Routing rule | N | PL conv | PL orig | Δ | ROI conv | ROI orig | Salv | Peggior |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `o25_s6_to_goal` | 28 | +2.14 | +0.74 | +1.40 | +7.64% | +2.64% | 4 | 4 |
| `as_o25_to_dc` | 21 | -1.91 | +1.92 | -3.83 | -9.07% | +9.14% | 4 | 9 |
| `gol_s2_to_ng` | 19 | -2.31 | -0.68 | -1.63 | -12.16% | -3.58% | 9 | 10 |
| `goal_to_u25` | 13 | -2.93 | -7.18 | +4.25 | -22.54% | -55.23% | 6 | 3 |
| `mc_filter_convert` | 13 | -0.22 | +1.01 | -1.23 | -1.68% | +7.77% | 6 | 2 |
| `dc_s4_to_ng` | 10 | +2.44 | -0.77 | +3.21 | +24.40% | -7.70% | 3 | 3 |
| `segno_s6_to_o25` | 10 | +4.22 | +0.74 | +3.48 | +42.20% | +7.40% | 4 | 1 |
| `dc_s6_to_goal` | 8 | +2.88 | +1.98 | +0.90 | +36.00% | +24.75% | 0 | 0 |
| `gol_s5_q160_to_ng` | 8 | -0.70 | -0.11 | -0.59 | -8.75% | -1.37% | 3 | 5 |
| `as_o25_to_under25` | 6 | -2.48 | +2.90 | -5.38 | -41.39% | +48.33% | 2 | 4 |
| `dc_s1_to_u25` | 6 | -2.00 | -1.63 | -0.37 | -33.33% | -27.17% | 1 | 2 |
| `gg_conf_dc_downgrade` | 6 | -3.00 | +1.63 | -4.64 | -50.08% | +27.17% | 1 | 2 |
| `as_o25_to_segno1` | 5 | -3.07 | -1.75 | -1.32 | -61.33% | -35.00% | 0 | 1 |
| `gol_s1_to_ng` | 4 | +1.27 | -2.25 | +3.52 | +31.75% | -56.25% | 3 | 1 |
| `segno_s9_f150_to_goal` | 3 | -1.35 | -1.50 | +0.15 | -45.00% | -50.00% | 1 | 1 |

## 4. Per mercato convertito (quello realmente giocato)

| Mercato conv | N | PL conv (1u) | PL orig (1u) | Δ | ROI conv | ROI orig |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SEGNO | 5 | -3.07 | -1.75 | -1.32 | -61.33% | -35.00% |
| DOPPIA_CHANCE | 27 | -4.91 | +3.55 | -8.46 | -18.19% | +13.15% |
| GOL | 128 | +0.96 | -6.75 | +7.71 | +0.75% | -5.27% |

## 5. Per mercato originale (quello previsto prima della conversione)

| Mercato orig | N | PL conv (1u) | PL orig (1u) | Δ | ROI conv | ROI orig |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SEGNO | 32 | -0.35 | +1.88 | -2.23 | -1.10% | +5.88% |
| DOPPIA_CHANCE | 24 | +3.32 | -0.42 | +3.74 | +13.83% | -1.75% |
| GOL | 104 | -9.99 | -6.41 | -3.58 | -9.60% | -6.16% |

## 6. Per gruppo source

| Gruppo | N | PL conv (1u) | PL orig (1u) | Δ | ROI conv | ROI orig |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 0 | — | — | — | — | — |
| S | 0 | — | — | — | — | — |
| C | 0 | — | — | — | — | — |
| A+S | 36 | +0.65 | +1.27 | -0.62 | +1.81% | +3.53% |
| C-derivati | 123 | -8.55 | -6.89 | -1.66 | -6.95% | -5.60% |
| Altro | 1 | +0.88 | +0.67 | +0.21 | +88.00% | +67.00% |

## 7. File generati

- `conversioni_raw.csv`
- `conversioni_per_tipo.csv`
- `conversioni_per_routing_rule.csv`