# Punto 6 — A vs S vs C: performance, concordanza, specializzazione

Finestra: 2026-02-19 → 2026-04-18.

## ⚠️ Caveat metodologico

Le performance isolate dei motori sono calcolate sulle rispettive
collection complete (`daily_predictions`, `daily_predictions_sandbox`,
`daily_predictions_engine_c`), NON sul sottoinsieme che finisce nello
unified. I volumi dei tre motori sono quindi diversi fra loro e diversi
dallo unified (1501 righe):

- A: 1325 righe (risolte: 1314)
- S: 1360 righe (risolte: 1347)
- C: 3924 righe (risolte: 3890)
- Unified (riferimento): 1501 righe

Questo caveat va tenuto presente nel confronto: un motore con volume
maggiore probabilmente emette anche pronostici che il MoE poi scarta.

## 1. Performance motore isolata (globale)

| Motore | N | HR | PL | ROI |
| --- | ---: | ---: | ---: | ---: |
| A (daily_predictions) | 1314 | 56.70% | -57.54 | -4.38% |
| S (daily_predictions_sandbox) | 1347 | 57.02% | -50.54 | -3.75% |
| C (daily_predictions_engine_c) | 3890 | 52.26% | -130.68 | -3.36% |

### Per mercato

| Motore | Mercato | N | HR | PL | ROI |
| --- | --- | ---: | ---: | ---: | ---: |
| A | SEGNO | 511 | 49.71% | -19.61 | -3.84% |
| A | DOPPIA_CHANCE | 114 | 70.18% | -4.99 | -4.38% |
| A | GOL | 689 | 59.65% | -32.94 | -4.78% |
| S | SEGNO | 518 | 50.00% | -15.44 | -2.98% |
| S | DOPPIA_CHANCE | 117 | 70.94% | -3.82 | -3.27% |
| S | GOL | 712 | 59.83% | -31.28 | -4.39% |
| C | SEGNO | 1317 | 49.20% | +18.74 | +1.42% |
| C | DOPPIA_CHANCE | 0 | — | — | — |
| C | GOL | 2573 | 53.83% | -149.42 | -5.81% |

## 2. Matrice di concordanza

Chiave: (date, home, away, mercato). Per ogni chiave recupero il
pronostico proposto da A, S, C (uno per motore, dopo dedup).

Categorie:

- `tutti_3`: A=S=C (unanimità)
- `conc_XY`: solo 2 motori presenti e concordi
- `XY_vs_Z`: 3 motori, 2 concordano e uno dissente
- `disc_XY`: solo 2 motori presenti e discordi
- `tutti_diversi`: 3 motori, 3 pronostici diversi
- `solo_X`: solo un motore propone pronostico

Quando c'è un consenso, il PL "consensus" è quello del pronostico concorde.
Quando c'è discordanza, riporto ROI per motore sul sottoinsieme.

| Categoria | N | HR conc | ROI conc | N_A | HR_A | ROI_A | N_S | HR_S | ROI_S | N_C | HR_C | ROI_C |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| tutti_3 | 453 | 54.22% | -6.49% | 450 | 54.22% | -6.49% | 450 | 54.22% | -6.49% | 450 | 54.22% | -6.60% |
| conc_AS | 454 | 56.98% | -3.23% | 451 | 56.98% | -3.23% | 451 | 56.98% | -3.23% | — | — | — |
| conc_AC | 5 | 60.00% | +8.60% | 5 | 60.00% | +8.60% | — | — | — | 5 | 60.00% | +8.60% |
| conc_SC | 2 | 50.00% | -31.00% | — | — | — | 2 | 50.00% | -31.00% | 2 | 50.00% | -35.00% |
| AS_vs_C | 397 | 58.67% | -3.82% | 392 | 58.67% | -3.82% | 392 | 58.67% | -3.82% | 392 | 52.04% | -7.97% |
| AC_vs_S | 0 | — | — | — | — | — | — | — | — | — | — | — |
| SC_vs_A | 0 | — | — | — | — | — | — | — | — | — | — | — |
| disc_AS | 0 | — | — | — | — | — | — | — | — | — | — | — |
| disc_AC | 4 | — | — | 4 | 75.00% | +15.25% | — | — | — | 4 | 25.00% | -53.75% |
| disc_SC | 3 | — | — | — | — | — | 3 | 66.67% | +7.33% | 3 | 0.00% | -100.00% |
| tutti_diversi | 0 | — | — | — | — | — | — | — | — | — | — | — |
| solo_A | 1 | — | — | 1 | 100.00% | +32.00% | — | — | — | — | — | — |
| solo_S | 40 | — | — | — | — | — | 38 | 71.05% | +23.04% | — | — | — |
| solo_C | 2093 | — | — | — | — | — | — | — | — | 2076 | 54.05% | -0.38% |

## 3. Performance motore per tier di lega

**Tier TOP** (5 leghe): Bundesliga, La Liga, Ligue 1, Premier League, Serie A

**Tier Seconde** (10 leghe): 2. Bundesliga, Championship, LaLiga 2, League One, League Two, Ligue 2, Serie B, Serie C - Girone A, Serie C - Girone B, Serie C - Girone C

**Tier Altro**: tutto il resto (MLS, sudamericane, nordiche, Portogallo, Scozia, ecc.)

| Motore | Tier | N | HR | PL | ROI |
| --- | --- | ---: | ---: | ---: | ---: |
| A | TOP | 244 | 56.15% | -15.42 | -6.32% |
| A | Seconde | 423 | 58.16% | +0.20 | +0.05% |
| A | Altro | 647 | 55.95% | -42.32 | -6.54% |
| S | TOP | 253 | 56.92% | -11.80 | -4.66% |
| S | Seconde | 430 | 58.14% | -0.78 | -0.18% |
| S | Altro | 664 | 56.33% | -37.96 | -5.72% |
| C | TOP | 691 | 52.53% | -33.95 | -4.91% |
| C | Seconde | 1603 | 51.84% | -78.96 | -4.93% |
| C | Altro | 1596 | 52.57% | -17.77 | -1.11% |

### Motore × tier × mercato

| Motore | Tier | Mercato | N | HR | ROI |
| --- | --- | --- | ---: | ---: | ---: |
| A | TOP | SEGNO | 91 | 47.25% | -11.24% |
| A | TOP | DOPPIA_CHANCE | 20 | 70.00% | -5.45% |
| A | TOP | GOL | 133 | 60.15% | -3.08% |
| A | Seconde | SEGNO | 208 | 52.88% | +2.17% |
| A | Seconde | DOPPIA_CHANCE | 42 | 78.57% | +7.14% |
| A | Seconde | GOL | 173 | 59.54% | -4.23% |
| A | Altro | SEGNO | 212 | 47.64% | -6.56% |
| A | Altro | DOPPIA_CHANCE | 52 | 63.46% | -13.27% |
| A | Altro | GOL | 383 | 59.53% | -5.62% |
| S | TOP | SEGNO | 94 | 46.81% | -11.63% |
| S | TOP | DOPPIA_CHANCE | 21 | 71.43% | -3.76% |
| S | TOP | GOL | 138 | 61.59% | -0.06% |
| S | Seconde | SEGNO | 208 | 52.88% | +2.32% |
| S | Seconde | DOPPIA_CHANCE | 43 | 79.07% | +7.95% |
| S | Seconde | GOL | 179 | 59.22% | -5.04% |
| S | Altro | SEGNO | 216 | 48.61% | -4.32% |
| S | Altro | DOPPIA_CHANCE | 53 | 64.15% | -12.18% |
| S | Altro | GOL | 395 | 59.49% | -5.62% |
| C | TOP | SEGNO | 226 | 49.56% | -6.02% |
| C | TOP | GOL | 465 | 53.98% | -4.38% |
| C | Seconde | SEGNO | 559 | 48.48% | +2.65% |
| C | Seconde | GOL | 1044 | 53.64% | -8.98% |
| C | Altro | SEGNO | 532 | 49.81% | +3.30% |
| C | Altro | GOL | 1064 | 53.95% | -3.32% |

## 4. Motore superiore per segmento (mercato × tier × quota)

Solo celle con N ≥ 30 in almeno un motore. Evidenzio il motore con ROI più alto.

| Mercato | Tier | Quota | A (n/ROI) | S (n/ROI) | C (n/ROI) | Vincitore |
| --- | --- | --- | ---: | ---: | ---: | --- |
| SEGNO | TOP | 1.30-1.50 | 7/+2.0% | 7/+2.0% | 40/+3.7% | C |
| SEGNO | TOP | 1.50-1.80 | 23/-28.2% | 23/-28.2% | 56/-10.0% | C |
| SEGNO | TOP | 1.80-2.00 | 23/-11.1% | 23/-19.1% | 33/-21.2% | C |
| SEGNO | TOP | 2.00-2.50 | 38/-3.5% | 41/-0.4% | 51/-9.9% | S |
| SEGNO | TOP | 2.50-3.50 | — | — | 31/+18.1% | C |
| SEGNO | Seconde | 1.30-1.50 | 4/+6.5% | 4/+6.5% | 49/-5.7% | C |
| SEGNO | Seconde | 1.50-1.80 | 36/+0.1% | 35/-2.0% | 115/-4.9% | A |
| SEGNO | Seconde | 1.80-2.00 | 76/-5.8% | 76/-5.8% | 75/+0.0% | C |
| SEGNO | Seconde | 2.00-2.50 | 89/+10.3% | 90/+11.3% | 153/+2.1% | S |
| SEGNO | Seconde | 2.50-3.50 | 3/-16.7% | 3/-16.7% | 123/+12.6% | C |
| SEGNO | Seconde | 3.50+ | — | — | 44/+10.3% | C |
| SEGNO | Altro | 1.30-1.50 | 18/-36.3% | 18/-36.3% | 78/-12.4% | C |
| SEGNO | Altro | 1.50-1.80 | 54/-1.3% | 55/-0.2% | 121/+5.1% | C |
| SEGNO | Altro | 1.80-2.00 | 58/-3.8% | 59/-2.3% | 68/+4.1% | C |
| SEGNO | Altro | 2.00-2.50 | 70/-24.3% | 71/-22.4% | 119/-10.6% | C |
| SEGNO | Altro | 2.50-3.50 | 2/+62.5% | 3/+111.7% | 107/-6.0% | C |
| SEGNO | Altro | 3.50+ | 10/+112.5% | 10/+112.5% | 39/+95.7% | C |
| DOPPIA_CHANCE | Seconde | 1.30-1.50 | 42/+7.1% | 43/+8.0% | — | S |
| DOPPIA_CHANCE | Altro | 1.30-1.50 | 52/-13.3% | 53/-12.2% | — | S |
| GOL | TOP | 1.30-1.50 | 37/+1.5% | 37/+1.5% | 82/-5.3% | A |
| GOL | TOP | 1.50-1.80 | 62/-6.6% | 64/-4.5% | 110/+1.3% | C |
| GOL | TOP | 1.80-2.00 | 22/-16.4% | 24/-8.0% | 121/+2.0% | C |
| GOL | TOP | 2.00-2.50 | 12/+25.4% | 13/+32.3% | 130/-0.4% | C |
| GOL | Seconde | 1.30-1.50 | 40/+12.8% | 42/+13.9% | 271/-10.4% | S |
| GOL | Seconde | 1.50-1.80 | 100/-12.6% | 102/-12.8% | 275/-5.4% | C |
| GOL | Seconde | 1.80-2.00 | 21/+5.9% | 23/-3.4% | 272/-15.3% | C |
| GOL | Seconde | 2.00-2.50 | 12/-8.8% | 12/-8.8% | 201/-4.8% | C |
| GOL | Altro | 1.30-1.50 | 130/-6.2% | 132/-7.6% | 197/-1.2% | C |
| GOL | Altro | 1.50-1.80 | 169/-6.6% | 178/-5.0% | 300/-8.3% | S |
| GOL | Altro | 1.80-2.00 | 53/-12.7% | 54/-14.3% | 202/+2.4% | C |
| GOL | Altro | 2.00-2.50 | 28/+12.1% | 28/+12.1% | 284/-9.2% | C |
| GOL | Altro | 2.50-3.50 | 1/+175.0% | 1/+175.0% | 75/+20.5% | C |

## 5. Sovrapposizione "buchi neri" (bonus)

Verifico la concentrazione di C-derivati nei segmenti peggiori del Punto 5.

| Scope | N | HR | PL | ROI |
| --- | ---: | ---: | ---: | ---: |
| C-derivati_totale | 567 | 57.67% | -18.38 | -3.24% |
| C-derivati_in_TOP | 75 | 57.33% | -2.46 | -3.28% |
| C-derivati_in_quota_150_200 | 299 | 57.19% | -16.12 | -5.39% |
| C-derivati_in_TOP_AND_quota_150_200 | 44 | 59.09% | -0.89 | -2.02% |

### Distribuzione C-derivati per tier

| Tier | Quota del totale C-derivati |
| --- | ---: |
| TOP | 13.16% |
| Seconde | 45.26% |
| Altro | 41.58% |

### Distribuzione C-derivati per fascia quota

| Quota | Quota del totale C-derivati |
| --- | ---: |
| <1.30 | 0.00% |
| 1.30-1.50 | 29.47% |
| 1.50-1.80 | 40.70% |
| 1.80-2.00 | 11.75% |
| 2.00-2.50 | 11.05% |
| 2.50-3.50 | 5.79% |
| 3.50+ | 1.23% |

## 6. Osservazioni oggettive

### Δ ROI tra tier per ciascun motore

| Motore | ROI TOP | ROI Seconde | ROI Altro | Δ (Altro - TOP) |
| --- | ---: | ---: | ---: | ---: |
| A | -6.32% | +0.05% | -6.54% | -0.22% |
| S | -4.66% | -0.18% | -5.72% | -1.06% |
| C | -4.91% | -4.93% | -1.11% | +3.80% |

## 7. File generati

- `performance_isolata.csv`, `performance_isolata_per_mercato.csv`
- `concordanza_raw.csv`, `concordanza_summary.csv`
- `motore_per_tier_lega.csv`, `motore_per_tier_mercato.csv`
- `motore_superiore_per_segmento.csv`
- `buchi_neri.csv`