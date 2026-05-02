# Confronto ordine selezione cella — PROFONDITA' vs AMPIEZZA vs MISTA

**Soglia minima partite per accettare cella**: 5

**Test set**: 25 Serie A + 25 altre leghe, stagione 2024-25, seed=42


## Strategie testate

- **PROFONDITA**: T-first (T1 23/23 -> T1 20-22 -> ... -> T5 8-11) — dà priorità alla strettezza tolleranza
- **AMPIEZZA**: banda-first (23/23 T1 -> 23/23 T2 -> ... -> 8-11 T5) — dà priorità al numero di feature compatibili
- **MISTA**: score combinato (peso T x peso banda) — bilanciamento


### Pesi MISTA

- T1=1.0, T2=0.8, T3=0.6, T4=0.4, T5=0.2
- 23/23=1.0, 20-22=0.85, 16-19=0.7, 12-15=0.55, 8-11=0.4
- Top score: T1 23/23 (1.0) > T1 20-22 (0.85) > T2 23/23 (0.8) > ...

---


## Hit rate per mercato — confronto strategie


### GLOBALE

| Mercato | PROFONDITA | AMPIEZZA | MISTA |
|---|---|---|---|
| 1X2 | 27/50 = **54.0%** | 29/50 = **58.0%** | 27/50 = **54.0%** |
| DC | 43/50 = **86.0%** | 43/50 = **86.0%** | 43/50 = **86.0%** |
| O/U 2.5 | 21/50 = **42.0%** | 25/50 = **50.0%** | 31/50 = **62.0%** |
| GG/NG | 25/50 = **50.0%** | 27/50 = **54.0%** | 26/50 = **52.0%** |
| MG | 31/50 = **62.0%** | 31/50 = **62.0%** | 27/50 = **54.0%** |

### INTRA-LEGA

| Mercato | PROFONDITA | AMPIEZZA | MISTA |
|---|---|---|---|
| 1X2 | 26/50 = **52.0%** | 28/50 = **56.0%** | 27/50 = **54.0%** |
| DC | 37/50 = **74.0%** | 42/50 = **84.0%** | 38/50 = **76.0%** |
| O/U 2.5 | 35/50 = **70.0%** | 31/50 = **62.0%** | 37/50 = **74.0%** |
| GG/NG | 27/50 = **54.0%** | 25/50 = **50.0%** | 28/50 = **56.0%** |
| MG | 32/50 = **64.0%** | 30/50 = **60.0%** | 31/50 = **62.0%** |

## Distribuzione celle sorgente

Quale cella ha 'vinto' come prima qualificata (>= 5 partite) per ogni strategia.


### Vista GLOBAL

| Cella | PROFONDITA | AMPIEZZA | MISTA |
|---|---|---|---|
| T1 12-15 | 3 | 0 | 0 |
| T1 8-11 | 16 | 0 | 0 |
| T2 16-19 | 0 | 0 | 11 |
| T2 12-15 | 27 | 0 | 26 |
| T2 8-11 | 4 | 0 | 0 |
| T3 20-22 | 0 | 0 | 9 |
| T3 16-19 | 0 | 0 | 3 |
| T3 12-15 | 0 | 0 | 1 |
| T4 23/23 | 0 | 34 | 0 |
| T5 23/23 | 0 | 15 | 0 |
| T5 20-22 | 0 | 1 | 0 |

### Vista INTRA

| Cella | PROFONDITA | AMPIEZZA | MISTA |
|---|---|---|---|
| T1 12-15 | 1 | 0 | 0 |
| T1 8-11 | 8 | 0 | 0 |
| T2 16-19 | 1 | 0 | 8 |
| T2 12-15 | 29 | 0 | 27 |
| T2 8-11 | 11 | 0 | 0 |
| T3 20-22 | 0 | 0 | 4 |
| T3 16-19 | 0 | 0 | 9 |
| T3 12-15 | 0 | 0 | 1 |
| T4 23/23 | 0 | 17 | 0 |
| T4 20-22 | 0 | 0 | 1 |
| T5 23/23 | 0 | 32 | 0 |
| T5 20-22 | 0 | 1 | 0 |