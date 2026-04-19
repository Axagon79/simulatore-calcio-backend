# Punto 5 — Analisi per segmento

Dataset rigenerato da MongoDB (stesso dedup della pipeline originale):
**1501** pronostici, 2026-02-19 → 2026-04-18.

Baseline globale: N=1501, HR=59.09%, ROI=9.04%, PL=135.73.

**Nota Mistral**: il campo `post_match_stats.ai_analysis` esiste a schema ma
è valorizzato in 0 documenti nella finestra → segmentazione "Mistral vs no"
non eseguibile con i dati attuali.

## 1. Lega (min N=20)

### Segmentazione per lega

Baseline globale ROI = +9.04%. Δ = ROI − baseline.

| league | N | HR | PL | ROI | Δ vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| Primera División | 144 | 59.72% | -43.27 | -30.05% | -39.09 |
| Championship | 87 | 55.17% | -3.87 | -4.45% | -13.49 |
| Major League Soccer | 80 | 60.00% | +42.41 | +53.01% | +43.97 |
| Serie C - Girone A | 75 | 57.33% | -29.04 | -38.72% | -47.76 |
| Serie B | 70 | 61.43% | -14.21 | -20.30% | -29.34 |
| Eredivisie | 64 | 67.19% | +2.17 | +3.39% | -5.65 |
| Serie C - Girone B | 62 | 61.29% | +50.02 | +80.68% | +71.64 |
| LaLiga 2 | 61 | 72.13% | +54.82 | +89.87% | +80.83 |
| Serie C - Girone C | 59 | 59.32% | +28.25 | +47.88% | +38.84 |
| Ligue 2 | 58 | 60.34% | -5.56 | -9.59% | -18.63 |
| 2. Bundesliga | 54 | 61.11% | +5.86 | +10.85% | +1.81 |
| Serie A | 53 | 56.60% | -17.86 | -33.70% | -42.74 |
| Bundesliga | 52 | 63.46% | -0.95 | -1.83% | -10.87 |
| Premier League | 47 | 53.19% | -9.73 | -20.70% | -29.74 |
| Eerste Divisie | 43 | 62.79% | -10.01 | -23.28% | -32.32 |
| League Two | 42 | 59.52% | +31.98 | +76.14% | +67.10 |
| Ligue 1 | 42 | 54.76% | -4.86 | -11.57% | -20.61 |
| Liga Portugal | 40 | 50.00% | -44.46 | -111.15% | -120.19 |
| Süper Lig | 38 | 52.63% | -9.03 | -23.76% | -32.80 |
| La Liga | 38 | 50.00% | -30.02 | -79.00% | -88.04 |
| League One | 37 | 43.24% | -15.74 | -42.54% | -51.58 |
| Brasileirão Serie A | 33 | 60.61% | -1.79 | -5.42% | -14.46 |
| League of Ireland Premier Division | 26 | 57.69% | -6.33 | -24.35% | -33.39 |
| 3. Liga | 26 | 46.15% | -30.84 | -118.62% | -127.66 |
| Jupiler Pro League | 24 | 62.50% | +3.56 | +14.83% | +5.79 |
| Scottish Premiership | 24 | 62.50% | +102.24 | +426.00% | +416.96 |

## 2. Coppa vs Campionato

### 

Baseline globale ROI = +9.04%. Δ = ROI − baseline.

| cup_vs_league | N | HR | PL | ROI | Δ vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| Campionato | 1476 | 59.08% | +125.57 | +8.51% | -0.53 |
| Coppa | 25 | 60.00% | +10.16 | +40.64% | +31.60 |

## 3. Fascia quota

### 

Baseline globale ROI = +9.04%. Δ = ROI − baseline.

| quota_bin | N | HR | PL | ROI | Δ vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1.30-1.50 | 384 | 71.09% | +18.08 | +4.71% | -4.33 |
| 1.50-1.80 | 645 | 60.16% | -40.95 | -6.35% | -15.39 |
| 1.80-2.00 | 215 | 50.70% | -28.27 | -13.15% | -22.19 |
| 2.00-2.50 | 147 | 54.42% | +20.83 | +14.17% | +5.13 |
| 2.50-3.50 | 65 | 33.85% | +27.13 | +41.74% | +32.70 |
| 3.50+ | 45 | 33.33% | +138.91 | +308.69% | +299.65 |

## 4. Fascia probabilità stimata

### 

Baseline globale ROI = +9.04%. Δ = ROI − baseline.

| prob_bin | N | HR | PL | ROI | Δ vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| 35-50 | 216 | 50.00% | -41.50 | -19.21% | -28.25 |
| 50-60 | 399 | 63.91% | +110.95 | +27.81% | +18.77 |
| 60-70 | 375 | 60.00% | +33.64 | +8.97% | -0.07 |
| 70-80 | 379 | 56.46% | -7.62 | -2.01% | -11.05 |
| 80+ | 87 | 65.52% | +37.03 | +42.56% | +33.52 |
| (null) | 45 | 62.22% | +3.23 | +7.18% | -1.86 |

## 5. Giorno della settimana

### 

Baseline globale ROI = +9.04%. Δ = ROI − baseline.

| giorno | N | HR | PL | ROI | Δ vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lunedì | 133 | 45.86% | -99.47 | -74.79% | -83.83 |
| Martedì | 81 | 50.62% | -16.87 | -20.83% | -29.87 |
| Mercoledì | 72 | 65.28% | +32.53 | +45.18% | +36.14 |
| Giovedì | 56 | 64.29% | +35.11 | +62.70% | +53.66 |
| Venerdì | 216 | 56.02% | -82.59 | -38.24% | -47.28 |
| Sabato | 528 | 60.04% | +51.72 | +9.80% | +0.76 |
| Domenica | 415 | 63.61% | +215.30 | +51.88% | +42.84 |

## 6. Tipo mercato

### 

Baseline globale ROI = +9.04%. Δ = ROI − baseline.

| tipo | N | HR | PL | ROI | Δ vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| GOL | 786 | 62.98% | +34.71 | +4.42% | -4.62 |
| SEGNO | 405 | 50.12% | +58.23 | +14.38% | +5.34 |
| DOPPIA_CHANCE | 310 | 60.97% | +42.79 | +13.80% | +4.76 |

## 7. Gruppo source

### 

Baseline globale ROI = +9.04%. Δ = ROI − baseline.

| gruppo | N | HR | PL | ROI | Δ vs baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| C-derivati | 570 | 57.89% | -75.33 | -13.22% | -22.26 |
| C | 519 | 55.68% | +202.97 | +39.11% | +30.07 |
| A+S | 263 | 64.64% | -15.88 | -6.04% | -15.08 |
| A | 116 | 68.10% | +16.17 | +13.94% | +4.90 |
| Altro | 25 | 56.00% | +2.33 | +9.32% | +0.28 |
| S | 8 | 62.50% | +5.47 | +68.38% | +59.34 |

## 8. Matrice gruppo × mercato

| Gruppo \ Mercato | SEGNO | DOPPIA_CHANCE | GOL |
| --- | :---: | :---: | :---: |
| A | — | — | N=116, ROI=+13.94% |
| S | — | — | N=8, ROI=+68.38% |
| C | N=331, ROI=+48.10% | — | N=188, ROI=+23.28% |
| A+S | — | N=54, ROI=+70.94% | N=209, ROI=-25.93% |
| C-derivati | N=71, ROI=-138.83% | N=256, ROI=+1.75% | N=243, ROI=+7.72% |
| Altro | N=3, ROI=-80.00% | — | N=22, ROI=+21.50% |

## 9. Osservazioni oggettive

### Leghe peggiori (N≥30, ordinate per ROI crescente)

| League | N | HR | ROI | Δ vs baseline |
| --- | ---: | ---: | ---: | ---: |
| Liga Portugal | 40 | 50.00% | -111.15% | -120.19 |
| La Liga | 38 | 50.00% | -79.00% | -88.04 |
| League One | 37 | 43.24% | -42.54% | -51.58 |
| Serie C - Girone A | 75 | 57.33% | -38.72% | -47.76 |
| Serie A | 53 | 56.60% | -33.70% | -42.74 |

### Leghe migliori (N≥30, ordinate per ROI decrescente)

| League | N | HR | ROI | Δ vs baseline |
| --- | ---: | ---: | ---: | ---: |
| LaLiga 2 | 61 | 72.13% | +89.87% | +80.83 |
| Serie C - Girone B | 62 | 61.29% | +80.68% | +71.64 |
| League Two | 42 | 59.52% | +76.14% | +67.10 |
| Major League Soccer | 80 | 60.00% | +53.01% | +43.97 |
| Serie C - Girone C | 59 | 59.32% | +47.88% | +38.84 |

### Celle gruppo × mercato peggiori (N≥30, ROI < -10%)

| Gruppo | Mercato | N | HR | ROI |
| --- | --- | ---: | ---: | ---: |
| C-derivati | SEGNO | 71 | 33.80% | -138.83% |
| A+S | GOL | 209 | 62.20% | -25.93% |

### Celle gruppo × mercato migliori (N≥30, ROI > +10%)

| Gruppo | Mercato | N | HR | ROI |
| --- | --- | ---: | ---: | ---: |
| A+S | DOPPIA_CHANCE | 54 | 74.07% | +70.94% |
| C | SEGNO | 331 | 53.78% | +48.10% |
| C | GOL | 188 | 59.04% | +23.28% |
| A | GOL | 116 | 68.10% | +13.94% |

## 10. File generati

- `segmento_league.csv`
- `segmento_cup_vs_campionato.csv`
- `segmento_quota.csv`
- `segmento_prob.csv`
- `segmento_giorno.csv`
- `segmento_mercato.csv`
- `segmento_gruppo.csv`
- `segmento_gruppo_x_mercato.csv`
- `plot_league.png`, `plot_quota.png`, `plot_prob.png`, `plot_giorno.png`