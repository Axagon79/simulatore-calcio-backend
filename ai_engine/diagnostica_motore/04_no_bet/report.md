# Punto 4 — Analisi NO BET ed esclusioni

Finestra: 2026-02-19 → 2026-04-18.
NO BET estratti: **213**. Risolti con esito reale: **74** (34.7%).
Non risolti (mancava real_score): 139.

Simulazione: ogni NO BET viene "giocato" a 1 unità con `original_pronostico` e `original_quota`.
Classificazione scrematura = routing_rule contiene `screm`, `filter`, `low_q` o `toxic`.

## 1. Riepilogo globale

| Scope | N | HR | PL | ROI |
| --- | ---: | ---: | ---: | ---: |
| GLOBALE — tutti NO BET | 74 | 43.24% | -5.49 | -7.42% |
| NO BET da scrematura/filtro | 68 | 41.18% | -7.64 | -11.24% |
| NO BET puri (non scrematura) | 6 | 66.67% | +2.15 | +35.83% |

## 2. NO BET per mercato

| Mercato | Scope | N | HR | PL | ROI |
| --- | --- | ---: | ---: | ---: | ---: |
| SEGNO | tutti | 44 | 34.09% | -5.77 | -13.11% |
| SEGNO | scrematura | 44 | 34.09% | -5.77 | -13.11% |
| SEGNO | puri | 0 | — | — | — |
| DOPPIA_CHANCE | tutti | 6 | 50.00% | -0.88 | -14.67% |
| DOPPIA_CHANCE | scrematura | 6 | 50.00% | -0.88 | -14.67% |
| DOPPIA_CHANCE | puri | 0 | — | — | — |
| GOL | tutti | 24 | 58.33% | +1.16 | +4.83% |
| GOL | scrematura | 18 | 55.56% | -0.99 | -5.50% |
| GOL | puri | 6 | 66.67% | +2.15 | +35.83% |

## 3. NO BET per gruppo source

| Gruppo | Scope | N | HR | PL | ROI |
| --- | --- | ---: | ---: | ---: | ---: |
| A | tutti | 4 | 50.00% | -0.75 | -18.75% |
| A | scrematura | 1 | 0.00% | -1.00 | -100.00% |
| A | puri | 3 | 66.67% | +0.25 | +8.33% |
| S | tutti | 0 | — | — | — |
| S | scrematura | 0 | — | — | — |
| S | puri | 0 | — | — | — |
| C | tutti | 20 | 40.00% | -2.42 | -12.10% |
| C | scrematura | 20 | 40.00% | -2.42 | -12.10% |
| C | puri | 0 | — | — | — |
| A+S | tutti | 1 | 0.00% | -1.00 | -100.00% |
| A+S | scrematura | 1 | 0.00% | -1.00 | -100.00% |
| A+S | puri | 0 | — | — | — |
| C-derivati | tutti | 44 | 40.91% | -3.33 | -7.57% |
| C-derivati | scrematura | 41 | 39.02% | -5.23 | -12.76% |
| C-derivati | puri | 3 | 66.67% | +1.90 | +63.33% |
| Altro | tutti | 5 | 80.00% | +2.01 | +40.20% |
| Altro | scrematura | 5 | 80.00% | +2.01 | +40.20% |
| Altro | puri | 0 | — | — | — |

## 4. Matrice gruppo × mercato

| Gruppo \ Mercato | SEGNO | DOPPIA_CHANCE | GOL |
| --- | :---: | :---: | :---: |
| A | — | — | N=4, ROI=-18.75% |
| S | — | — | — |
| C | N=16, ROI=-1.81% | — | N=4, ROI=-53.25% |
| A+S | — | — | N=1, ROI=-100.00% |
| C-derivati | N=28, ROI=-19.57% | N=6, ROI=-14.67% | N=10, ROI=+30.30% |
| Altro | — | — | N=5, ROI=+40.20% |

## 5. Top routing_rule (per volume)

| Routing rule | N | HR | PL | ROI |
| --- | ---: | ---: | ---: | ---: |
| `segno_s2_toxic_q_filter` | 37 | 27.03% | -8.01 | -21.65% |
| `gol_s4_q180_filter` | 7 | 57.14% | +0.54 | +7.71% |
| `x2_s2_filter` | 6 | 50.00% | -0.88 | -14.67% |
| `u25_s7_nobet` | 6 | 66.67% | +2.15 | +35.83% |
| `se2_s8_q190_filter` | 6 | 66.67% | +1.72 | +28.67% |
| `gol_s3_filter` | 5 | 40.00% | -1.26 | -25.20% |
| `gol_s7_filter` | 4 | 50.00% | -1.27 | -31.75% |
| `gol_s4_filter` | 2 | 100.00% | +1.00 | +50.00% |
| `segno_s1_low_q_filter` | 1 | 100.00% | +0.52 | +52.00% |

## 6. Osservazioni oggettive

### Interpretazione

- ROI < 0 su NO BET = **filtro giusto** (avrebbero perso soldi se giocati).
- ROI > 0 su NO BET = **filtro troppo aggressivo** (erano profittevoli).
- ROI ~ 0 = filtro neutro.

### Filtri potenzialmente da rivedere (ROI > +5% e N ≥ 30)

| Scope | N | HR | ROI |
| --- | ---: | ---: | ---: |
| — | — | — | — |

### Filtri che funzionano (ROI ≤ -5% e N ≥ 30)

| Scope | N | HR | ROI |
| --- | ---: | ---: | ---: |
| rule=`segno_s2_toxic_q_filter` | 37 | 27.03% | -21.65% |

## 7. File generati

- `no_bet_raw.csv` — tutti i NO BET con esito+PL simulato
- `no_bet_unresolved.csv` — NO BET senza real_score disponibile
- `no_bet_per_mercato.csv`
- `no_bet_per_gruppo.csv`
- `no_bet_matrice.csv` (gruppo × mercato)
- `no_bet_per_routing_rule.csv` — breakdown per regola
- `no_bet_roi_per_mercato.png`