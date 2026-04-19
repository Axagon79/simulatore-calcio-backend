# Impatto Cerotto 4 (7 combo SCARTA) sulla scatola Alto Rendimento

Dataset: **1501** pronostici dedupati, finestra 19/02/2026 → 18/04/2026.

Le 7 combo del Cerotto 4 ridotto (solo SCARTA, senza le 3 "falsi allarme"): 
C2, C4, C5, C6, C8, C9, C10 (vedi `combo_verificate.md`).

## Due definizioni di Alto Rendimento a confronto

| Definizione | Regola | N |
| --- | --- | ---: |
| **A** (notebook / report globale) | `quota > 2.50` | **103** |
| **B** (scatola frontend) | `elite=False AND mixer=False AND quota >= 2.51 (2.00 DC)` | **73** |

Baseline globale: N=1501, HR=59.09%, ROI=+9.04%, PL=+135.73u

## Baseline AR per definizione

| Metrica | Globale | AR def A | AR def B |
| --- | ---: | ---: | ---: |
| N | 1501 | 103 | 73 |
| HR | 59.09% | 33.98% | 36.99% |
| Quota media | 1.79 | 3.71 | 3.23 |
| ROI | +9.04% | +164.12% | +5.48% |
| PL (u) | +135.73 | +169.04 | +4.00 |

## Task 1 — Impatto 7 combo su AR def A (quota > 2.50)

| ID | Combo | N in AR | Wins | Losses | HR | Quota media | ROI | PL (u) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| C2 | SEGNO + tipo_partita=aperta | 18 | 3 | 15 | 16.67% | 2.92 | -240.78% | -43.34 |
| C4 | tipo_partita=aperta + categoria=Alto Rendimento | 19 | 4 | 15 | 21.05% | 2.91 | -218.89% | -41.59 |
| C5 | SEGNO + Monday + tipo_partita=aperta | 6 | 0 | 6 | 0.00% | 3.01 | -433.33% | -26.00 |
| C6 | fascia_oraria=sera + categoria=Alto Rendimento | 41 | 11 | 30 | 26.83% | 3.70 | -29.76% | -12.20 |
| C8 | Friday + fascia_quota=3.00+ + tipo_partita=equilibrata | 8 | 1 | 7 | 12.50% | 4.01 | -345.88% | -27.67 |
| C9 | fascia_quota=2.50-2.99 + tipo_partita=aperta | 12 | 3 | 9 | 25.00% | 2.71 | -254.92% | -30.59 |
| C10 | Friday + categoria=Alto Rendimento | 19 | 3 | 16 | 15.79% | 3.72 | -264.05% | -50.17 |

**Pronostici AR def A univoci colpiti da almeno 1 combo**: 61 (di cui 16 vinti, 45 persi)

## Task 2 — Impatto 7 combo su AR def B (scatola frontend)

| ID | Combo | N in AR | Wins | Losses | HR | Quota media | ROI | PL (u) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| C2 | SEGNO + tipo_partita=aperta | 15 | 2 | 13 | 13.33% | 2.96 | -318.27% | -47.74 |
| C4 | tipo_partita=aperta + categoria=Alto Rendimento | 16 | 3 | 13 | 18.75% | 2.95 | -287.44% | -45.99 |
| C5 | SEGNO + Monday + tipo_partita=aperta | 6 | 0 | 6 | 0.00% | 3.01 | -433.33% | -26.00 |
| C6 | fascia_oraria=sera + categoria=Alto Rendimento | 26 | 4 | 22 | 15.38% | 3.70 | -178.73% | -46.47 |
| C8 | Friday + fascia_quota=3.00+ + tipo_partita=equilibrata | 4 | 0 | 4 | 0.00% | 3.58 | -525.00% | -21.00 |
| C9 | fascia_quota=2.50-2.99 + tipo_partita=aperta | 10 | 2 | 8 | 20.00% | 2.74 | -359.90% | -35.99 |
| C10 | Friday + categoria=Alto Rendimento | 11 | 1 | 10 | 9.09% | 3.23 | -368.18% | -40.50 |

**Pronostici AR def B univoci colpiti da almeno 1 combo**: 40 (di cui 7 vinti, 33 persi)

## Confronto AR prima/dopo Cerotto 4

| Metrica | AR def A prima | AR def A dopo | Δ | AR def B prima | AR def B dopo | Δ |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| N | 103 | 42 | -61 | 73 | 33 | -40 |
| HR | 33.98% | 45.24% | +11.26pp | 36.99% | 60.61% | +23.62pp |
| ROI | +164.12% | +490.67% | +326.55pp | +5.48% | +229.42% | +223.94pp |
| PL (u) | +169.04 | +206.08 | +37.04 | +4.00 | +75.71 | +71.71 |

## Task 3 — Dove finiscono i pronostici tossici (frontend scatola)

### Distribuzione per scatola frontend dei pronostici "AR def A colpiti da 7 combo"

Questi sono i pronostici che def A classifica come AR (quota>2.50) e che sono toccati dal Cerotto 4. Dove vanno a finire nel frontend dopo dedup MIXER>ELITE>AR>PRONOSTICI?

| Scatola frontend | N | % del totale AR def A colpiti |
| --- | ---: | ---: |
| MIXER | 21 | 34.4% |
| ELITE | 0 | 0.0% |
| ALTO_RENDIMENTO | 40 | 65.6% |
| PRONOSTICI | 0 | 0.0% |

### Distribuzione per scatola di TUTTI i pronostici colpiti dalle 7 combo

(indipendentemente da quota>2.50: incluso quelli con quota bassa)

| Scatola frontend | N | % |
| --- | ---: | ---: |
| MIXER | 23 | 31.5% |
| ELITE | 0 | 0.0% |
| ALTO_RENDIMENTO | 40 | 54.8% |
| PRONOSTICI | 10 | 13.7% |

## Lettura e criterio di decisione

- Se usiamo **def A** (il filtro scatta quando `quota > 2.50`): colpiamo tutti i pronostici ad alta quota tossici, anche quelli che nel frontend finiscono in MIXER/ELITE/PRONOSTICI. Coerente col report globale.
- Se usiamo **def B** (il filtro scatta solo sulla scatola AR del frontend): colpiamo solo i pronostici che l'utente vede sotto "Alto Rendimento". Lascia fuori eventuali MIXER/ELITE tossici che comunque verranno mostrati.

Valuta: se AR def A post-cerotto scende sotto il +150u, fermati e discutiamo.

## Warning metodologico

L'analisi è post-hoc sullo stesso dataset che ha generato le 10 combo. Il PL recuperato è per costruzione favorevole; un test out-of-sample potrebbe dare risultati diversi.