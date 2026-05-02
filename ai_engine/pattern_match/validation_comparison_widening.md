# Confronto allargamento maglie — BASE vs WIDE_A vs WIDE_B

**Test set**: 25 Serie A + 25 altre leghe, stagione 2024-25, seed=42

**Soglia minima per gerarchico**: 10 partite


## Definizione varianti

- **BASE**: tolleranze attuali (T1=0 esatto, T2/T3 standard).
- **WIDE_A**: T1 invariato (T1=0), T2 e T3 allargate ~+15-20%.
- **WIDE_B**: T1 leggermente allargato (T1>0), T2 e T3 allargate ~+30-40%.

---


## Hit rate — confronto 3 varianti


### Metodo CELLA-PER-CELLA (prima cella non vuota)

| Mercato | Vista | BASE | WIDE_A | WIDE_B |
|---|---|---|---|---|
| 1X2 | global | 25/50 = **50.0%** | 25/50 = **50.0%** | 21/50 = **42.0%** |
| 1X2 | intra | 25/50 = **50.0%** | 20/50 = **40.0%** | 25/50 = **50.0%** |
| DC | global | 43/50 = **86.0%** | 43/50 = **86.0%** | 41/50 = **82.0%** |
| DC | intra | 43/50 = **86.0%** | 39/50 = **78.0%** | 39/50 = **78.0%** |
| O/U 2.5 | global | 24/50 = **48.0%** | 23/50 = **46.0%** | 28/50 = **56.0%** |
| O/U 2.5 | intra | 32/50 = **64.0%** | 33/50 = **66.0%** | 32/50 = **64.0%** |
| GG/NG | global | 26/50 = **52.0%** | 25/50 = **50.0%** | 23/50 = **46.0%** |
| GG/NG | intra | 24/50 = **48.0%** | 24/50 = **48.0%** | 26/50 = **52.0%** |
| MG | global | 30/50 = **60.0%** | 28/50 = **56.0%** | 29/50 = **58.0%** |
| MG | intra | 28/50 = **56.0%** | 28/50 = **56.0%** | 28/50 = **56.0%** |

### Metodo GERARCHICO (prima cella >= 10 partite)

| Mercato | Vista | BASE | WIDE_A | WIDE_B |
|---|---|---|---|---|
| 1X2 | global | 26/50 = **52.0%** | 29/50 = **58.0%** | 24/50 = **48.0%** |
| 1X2 | intra | 26/50 = **52.0%** | 26/50 = **52.0%** | 28/50 = **56.0%** |
| DC | global | 41/50 = **82.0%** | 43/50 = **86.0%** | 43/50 = **86.0%** |
| DC | intra | 39/50 = **78.0%** | 41/50 = **82.0%** | 41/50 = **82.0%** |
| O/U 2.5 | global | 21/50 = **42.0%** | 28/50 = **56.0%** | 28/50 = **56.0%** |
| O/U 2.5 | intra | 36/50 = **72.0%** | 33/50 = **66.0%** | 37/50 = **74.0%** |
| GG/NG | global | 26/50 = **52.0%** | 24/50 = **48.0%** | 27/50 = **54.0%** |
| GG/NG | intra | 27/50 = **54.0%** | 28/50 = **56.0%** | 30/50 = **60.0%** |
| MG | global | 30/50 = **60.0%** | 32/50 = **64.0%** | 32/50 = **64.0%** |
| MG | intra | 30/50 = **60.0%** | 28/50 = **56.0%** | 31/50 = **62.0%** |

### Risultato Esatto (top 5 gerarchico)

| Vista | BASE | WIDE_A | WIDE_B |
|---|---|---|---|
| global | 24/50 = **48.0%** | 18/50 = **36.0%** | 20/50 = **40.0%** |
| intra | 20/50 = **40.0%** | 24/50 = **48.0%** | 24/50 = **48.0%** |

## Distribuzione celle sorgente — metodo cella-per-cella (1X2)

Quale cella e' stata 'la prima non vuota' (cioe' la cella usata per il verdetto)?


### Vista GLOBAL

| Cella | BASE | WIDE_A | WIDE_B |
|---|---|---|---|
| T1 16-19 | 0 | 0 | 11 |
| T1 12-15 | 7 | 7 | 36 |
| T1 8-11 | 37 | 37 | 3 |
| T2 20-22 | 0 | 2 | 0 |
| T2 16-19 | 0 | 3 | 0 |
| T2 12-15 | 6 | 1 | 0 |

### Vista INTRA

| Cella | BASE | WIDE_A | WIDE_B |
|---|---|---|---|
| T1 16-19 | 0 | 0 | 9 |
| T1 12-15 | 4 | 4 | 35 |
| T1 8-11 | 29 | 29 | 6 |
| T2 20-22 | 0 | 3 | 0 |
| T2 16-19 | 2 | 12 | 0 |
| T2 12-15 | 13 | 2 | 0 |
| T2 8-11 | 2 | 0 | 0 |

## Distribuzione celle sorgente — metodo gerarchico (>=10 partite)


### Vista GLOBAL

| Cella | BASE | WIDE_A | WIDE_B |
|---|---|---|---|
| T1 16-19 | 0 | 0 | 3 |
| T1 12-15 | 3 | 3 | 24 |
| T1 8-11 | 9 | 9 | 23 |
| T2 16-19 | 0 | 21 | 0 |
| T2 12-15 | 32 | 17 | 0 |
| T2 8-11 | 6 | 0 | 0 |

### Vista INTRA

| Cella | BASE | WIDE_A | WIDE_B |
|---|---|---|---|
| T1 12-15 | 0 | 0 | 15 |
| T1 8-11 | 7 | 7 | 34 |
| T2 16-19 | 1 | 13 | 0 |
| T2 12-15 | 24 | 28 | 0 |
| T2 8-11 | 18 | 2 | 1 |