# Validazione COMPLETA su 200 partite

**Test set**: 199 pronostici (100 Serie A + 100 altre leghe, stagioni 2023-24 + 2024-25, seed=42)


## Hit rate per mercato — baseline vs filtrato

| Mercato | Baseline Hit | Baseline % | Filtrato Hit | Filtrato % |
|---|---|---|---|---|
| 1X2 (DC>=71%) | 96/199 | 48.2% | 50/81 | **61.7%** |
| O/U 1.5 (>=65.5%) | 156/199 | 78.4% | 124/160 | **77.5%** |
| O/U 2.5 (>=65.5%) | 120/199 | 60.3% | 19/33 | **57.6%** |
| O/U 3.5 (>=70.5%) | 143/199 | 71.9% | 64/85 | **75.3%** |
| MG (>=65.5%) | 126/199 | 63.3% | 65/100 | **65.0%** |
| DC (no filtro) | 151/199 | **75.9%** | — | — |
| GG/NG (no filtro) | 106/199 | **53.3%** | — | — |
| RE top 5 | 76/199 | **38.2%** | — | — |

## Pattern GOAL (X<30% AND Over 2.5>65%)

**Partite attive**: 20/199 (10.1%)

| Mercato | Hit | Hit rate |
|---|---|---|
| **Goal** | 12/20 | **60.0%** |
| Over 2.5 | 13/20 | **65.0%** |
| 1 OR 2 | 17/20 | **85.0%** |
| RE top 5 | 8/20 | **40.0%** |

## Pattern NOGOAL (media_tot<2.5 AND min_squadra<0.9)

**Partite attive**: 21/199 (10.6%)

| Mercato | Hit | Hit rate |
|---|---|---|
| **NoGoal** | 7/21 | **33.3%** |
| Under 2.5 | 10/21 | **47.6%** |
| RE top 5 | 10/21 | **47.6%** |