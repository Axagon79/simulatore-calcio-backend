# Validazione Pattern Match Engine — METODO GERARCHICO

**Soglia minima partite per cella sorgente**: 10

**Test set**: 25 Serie A + 25 altre leghe, stagione 2024-25, seed=42

**Algoritmo**: per ogni mercato, scendo dalle celle piu strette (T1 23/23) alle piu larghe (T5 8-11). Mi fermo alla prima con >= 10 partite.

---


## Match 1/50: Genoa vs Lazio

- **uid**: `I1_2024-25_2025-04-23_Genoa_Lazio` | **I1 2024-25** | **2025-04-23**
- **Esito reale**: 0-2 (1X2=A, gol_tot=2, GG/NG=nogoal)
- **Quote**: 1=3.30 X=3.20 2=2.30

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | D (43%) [T2 12-15, n=14] | H (43%) [T2 8-11, n=90] | A | ❌ | ❌ |
| DC | X2 | 12 | X2,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | under | ❌ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | nogoal | ❌ | ❌ |
| MG | 1_3 | 1_3 | 1_2,1_3,2_3,2_4 | ✅ | ✅ |
| RE (top5) | 1-2,0-0,1-1,2-1,0-1 | 1-2,0-1,2-1,1-0,1-1 | 0-2 | ❌ | ❌ |

---


## Match 2/50: Empoli vs Fiorentina

- **uid**: `I1_2024-25_2024-09-29_Empoli_Fiorentina` | **I1 2024-25** | **2024-09-29**
- **Esito reale**: 0-0 (1X2=D, gol_tot=0, GG/NG=nogoal)
- **Quote**: 1=3.40 X=3.30 2=2.20

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (50%) [T1 8-11, n=10] | H (47%) [T2 12-15, n=59] | D | ❌ | ❌ |
| DC | 12 | 12 | X2,1X | ❌ | ❌ |
| O/U 1.5 | over | over | under | ❌ | ❌ |
| O/U 2.5 | over | under | under | ❌ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | nogoal | nogoal | ❌ | ✅ |
| MG | 1_3 | 1_3 |  | ❌ | ❌ |
| RE (top5) | 0-1,2-1,2-2,5-3,1-0 | 2-1,2-2,0-0,2-0,0-1 | 0-0 | ❌ | ✅ |

---


## Match 3/50: Udinese vs Lazio

- **uid**: `I1_2024-25_2024-08-24_Udinese_Lazio` | **I1 2024-25** | **2024-08-24**
- **Esito reale**: 2-1 (1X2=H, gol_tot=3, GG/NG=goal)
- **Quote**: 1=3.30 X=3.10 2=2.35

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (44%) [T1 12-15, n=18] | A (38%) [T1 8-11, n=56] | H | ❌ | ❌ |
| DC | 12 | 12 | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 1_3 | 2_4 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 2-2,0-1,1-0,1-1,1-2 | 0-0,2-1,2-2,0-1,1-2 | 2-1 | ❌ | ✅ |

---


## Match 4/50: Venezia vs Juventus

- **uid**: `I1_2024-25_2025-05-25_Venezia_Juventus` | **I1 2024-25** | **2025-05-25**
- **Esito reale**: 2-3 (1X2=A, gol_tot=5, GG/NG=goal)
- **Quote**: 1=5.75 X=4.33 2=1.53

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (52%) [T2 8-11, n=137] | A (45%) [T2 8-11, n=69] | A | ✅ | ✅ |
| DC | 12 | 12 | X2,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | over | ❌ | ❌ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 1_3 | 1_3 | 3_5,4_6 | ❌ | ❌ |
| RE (top5) | 0-1,2-3,0-2,1-1,2-0 | 0-1,2-3,0-2,2-1,2-0 | 2-3 | ✅ | ✅ |

---


## Match 5/50: Roma vs Lecce

- **uid**: `I1_2024-25_2024-12-07_Roma_Lecce` | **I1 2024-25** | **2024-12-07**
- **Esito reale**: 4-1 (1X2=H, gol_tot=5, GG/NG=goal)
- **Quote**: 1=1.57 X=4.00 2=6.25

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (56%) [T2 12-15, n=50] | H (77%) [T2 12-15, n=13] | H | ✅ | ✅ |
| DC | 1X | 1X | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | over | ❌ | ❌ |
| GG/NG | nogoal | nogoal | goal | ❌ | ❌ |
| MG | 1_3 | 1_3 | 3_5,4_6 | ❌ | ❌ |
| RE (top5) | 5-0,1-1,0-1,2-1,1-0 | 1-1,1-0,3-0,2-1,4-1 | 4-1 | ❌ | ✅ |

---


## Match 6/50: Napoli vs Roma

- **uid**: `I1_2024-25_2024-11-24_Napoli_Roma` | **I1 2024-25** | **2024-11-24**
- **Esito reale**: 1-0 (1X2=H, gol_tot=1, GG/NG=nogoal)
- **Quote**: 1=1.73 X=3.60 2=5.00

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (72%) [T2 12-15, n=57] | H (75%) [T2 12-15, n=12] | H | ✅ | ✅ |
| DC | 1X | 1X | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | under | ❌ | ❌ |
| O/U 2.5 | over | over | under | ❌ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | nogoal | goal | nogoal | ✅ | ❌ |
| MG | 2_4 | 2_4 | 1_2,1_3 | ❌ | ❌ |
| RE (top5) | 2-0,3-0,4-1,2-1,1-0 | 2-0,3-0,1-0,2-2,1-1 | 1-0 | ✅ | ✅ |

---


## Match 7/50: Inter vs Napoli

- **uid**: `I1_2024-25_2024-11-10_Inter_Napoli` | **I1 2024-25** | **2024-11-10**
- **Esito reale**: 1-1 (1X2=D, gol_tot=2, GG/NG=goal)
- **Quote**: 1=1.85 X=3.70 2=4.10

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (47%) [T2 12-15, n=30] | H (45%) [T2 8-11, n=109] | D | ❌ | ❌ |
| DC | 1X | 1X | X2,1X | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | under | under | ❌ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 2_4 | 1_3 | 1_2,1_3,2_3,2_4 | ✅ | ✅ |
| RE (top5) | 2-0,1-1,2-1,3-0,1-2 | 2-0,1-0,3-0,1-1,1-2 | 1-1 | ✅ | ✅ |

---


## Match 8/50: Milan vs Udinese

- **uid**: `I1_2024-25_2024-10-19_Milan_Udinese` | **I1 2024-25** | **2024-10-19**
- **Esito reale**: 1-0 (1X2=H, gol_tot=1, GG/NG=nogoal)
- **Quote**: 1=1.38 X=4.75 2=8.50

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (46%) [T2 12-15, n=163] | H (47%) [T2 12-15, n=36] | H | ✅ | ✅ |
| DC | 1X | 1X | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | under | ❌ | ❌ |
| O/U 2.5 | over | under | under | ❌ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | nogoal | ❌ | ❌ |
| MG | 2_4 | 1_3 | 1_2,1_3 | ❌ | ✅ |
| RE (top5) | 3-1,1-0,3-3,1-3,0-0 | 3-1,3-3,1-3,1-1,0-0 | 1-0 | ✅ | ❌ |

---


## Match 9/50: Lazio vs Lecce

- **uid**: `I1_2024-25_2025-05-25_Lazio_Lecce` | **I1 2024-25** | **2025-05-25**
- **Esito reale**: 0-1 (1X2=A, gol_tot=1, GG/NG=nogoal)
- **Quote**: 1=1.53 X=3.70 2=7.50

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (56%) [T2 8-11, n=116] | H (48%) [T2 8-11, n=44] | A | ❌ | ❌ |
| DC | 1X | 1X | X2,12 | ❌ | ❌ |
| O/U 1.5 | over | over | under | ❌ | ❌ |
| O/U 2.5 | over | over | under | ❌ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | nogoal | ❌ | ❌ |
| MG | 1_3 | 2_4 | 1_2,1_3 | ✅ | ❌ |
| RE (top5) | 2-1,5-2,3-1,1-1,2-0 | 2-1,5-2,3-1,1-1,0-0 | 0-1 | ❌ | ❌ |

---


## Match 10/50: Genoa vs Juventus

- **uid**: `I1_2024-25_2024-09-28_Genoa_Juventus` | **I1 2024-25** | **2024-09-28**
- **Esito reale**: 0-3 (1X2=A, gol_tot=3, GG/NG=nogoal)
- **Quote**: 1=5.50 X=3.50 2=1.70

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (55%) [T1 8-11, n=11] | A (38%) [T2 12-15, n=55] | A | ✅ | ✅ |
| DC | X2 | 12 | X2,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | over | ❌ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | nogoal | goal | nogoal | ✅ | ❌ |
| MG | 1_3 | 2_4 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 1-2,0-0,0-1,0-3,5-2 | 1-2,0-0,2-3,2-1,1-1 | 0-3 | ✅ | ❌ |

---


## Match 11/50: Roma vs Fiorentina

- **uid**: `I1_2024-25_2025-05-04_Roma_Fiorentina` | **I1 2024-25** | **2025-05-04**
- **Esito reale**: 1-0 (1X2=H, gol_tot=1, GG/NG=nogoal)
- **Quote**: 1=1.65 X=3.70 2=5.50

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (49%) [T2 8-11, n=229] | H (48%) [T2 8-11, n=82] | H | ✅ | ✅ |
| DC | 1X | 1X | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | under | ❌ | ❌ |
| O/U 2.5 | over | over | under | ❌ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | nogoal | ❌ | ❌ |
| MG | 2_4 | 2_4 | 1_2,1_3 | ❌ | ❌ |
| RE (top5) | 2-1,1-1,3-1,1-0,2-0 | 2-1,1-1,3-1,2-0,2-2 | 1-0 | ✅ | ❌ |

---


## Match 12/50: Lazio vs Udinese

- **uid**: `I1_2024-25_2025-03-10_Lazio_Udinese` | **I1 2024-25** | **2025-03-10**
- **Esito reale**: 1-1 (1X2=D, gol_tot=2, GG/NG=goal)
- **Quote**: 1=1.73 X=3.50 2=5.25

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (43%) [T2 12-15, n=14] | H (56%) [T2 8-11, n=106] | D | ❌ | ❌ |
| DC | 1X | 12 | X2,1X | ✅ | ❌ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | under | ✅ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 1_3 | 1_3 | 1_2,1_3,2_3,2_4 | ✅ | ✅ |
| RE (top5) | 0-0,1-1,0-1,2-1,0-2 | 0-2,1-1,0-1,0-0,1-0 | 1-1 | ✅ | ✅ |

---


## Match 13/50: Lecce vs Parma

- **uid**: `I1_2024-25_2024-09-21_Lecce_Parma` | **I1 2024-25** | **2024-09-21**
- **Esito reale**: 2-2 (1X2=D, gol_tot=4, GG/NG=goal)
- **Quote**: 1=2.20 X=3.50 2=3.25

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | D (39%) [T1 8-11, n=28] | H (40%) [T2 16-19, n=10] | D | ✅ | ❌ |
| DC | 1X | 1X | X2,1X | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | over | ❌ | ✅ |
| O/U 3.5 | under | under | over | ❌ | ❌ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 2_4 | 1_3 | 2_4,3_5,4_6 | ✅ | ❌ |
| RE (top5) | 0-0,0-1,2-2,2-0,2-1 | 0-1,2-2,2-1,0-0,4-1 | 2-2 | ✅ | ✅ |

---


## Match 14/50: Parma vs Inter

- **uid**: `I1_2024-25_2025-04-05_Parma_Inter` | **I1 2024-25** | **2025-04-05**
- **Esito reale**: 2-2 (1X2=D, gol_tot=4, GG/NG=goal)
- **Quote**: 1=6.50 X=4.50 2=1.48

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (64%) [T2 12-15, n=14] | A (53%) [T2 8-11, n=59] | D | ❌ | ❌ |
| DC | X2 | X2 | X2,1X | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | over | ❌ | ❌ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 1_3 | 1_3 | 2_4,3_5,4_6 | ❌ | ❌ |
| RE (top5) | 1-1,1-2,0-2,1-4,2-4 | 1-1,3-1,1-2,2-1,0-1 | 2-2 | ❌ | ❌ |

---


## Match 15/50: Venezia vs Verona

- **uid**: `I1_2024-25_2025-01-27_Venezia_Verona` | **I1 2024-25** | **2025-01-27**
- **Esito reale**: 1-1 (1X2=D, gol_tot=2, GG/NG=goal)
- **Quote**: 1=2.15 X=3.50 2=3.25

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (47%) [T2 12-15, n=30] | H (38%) [T2 12-15, n=13] | D | ❌ | ❌ |
| DC | 1X | 1X | X2,1X | ✅ | ✅ |
| O/U 1.5 | over | under | over | ✅ | ❌ |
| O/U 2.5 | under | under | under | ✅ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | nogoal | nogoal | goal | ❌ | ❌ |
| MG | 1_3 | 1_2 | 1_2,1_3,2_3,2_4 | ✅ | ✅ |
| RE (top5) | 1-2,1-0,0-1,1-1,0-0 | 0-0,0-1,1-0,1-1,2-0 | 1-1 | ✅ | ✅ |

---


## Match 16/50: Napoli vs Bologna

- **uid**: `I1_2024-25_2024-08-25_Napoli_Bologna` | **I1 2024-25** | **2024-08-25**
- **Esito reale**: 3-0 (1X2=H, gol_tot=3, GG/NG=nogoal)
- **Quote**: 1=1.90 X=3.50 2=4.10

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (45%) [T1 12-15, n=11] | A (37%) [T1 8-11, n=52] | H | ❌ | ❌ |
| DC | 12 | 12 | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | nogoal | ❌ | ❌ |
| MG | 1_3 | 1_3 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 1-2,3-3,2-0,1-0,0-3 | 2-0,0-1,2-1,0-0,2-2 | 3-0 | ❌ | ❌ |

---


## Match 17/50: Torino vs Atalanta

- **uid**: `I1_2024-25_2024-08-25_Torino_Atalanta` | **I1 2024-25** | **2024-08-25**
- **Esito reale**: 2-1 (1X2=H, gol_tot=3, GG/NG=goal)
- **Quote**: 1=3.20 X=3.10 2=2.38

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (41%) [T1 8-11, n=123] | A (40%) [T1 8-11, n=30] | H | ❌ | ❌ |
| DC | 12 | 12 | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | over | ❌ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | nogoal | goal | goal | ❌ | ✅ |
| MG | 1_3 | 1_3 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 4-2,0-1,0-0,1-1,1-2 | 4-2,0-1,2-2,1-2,1-0 | 2-1 | ❌ | ❌ |

---


## Match 18/50: Monza vs Bologna

- **uid**: `I1_2024-25_2024-09-22_Monza_Bologna` | **I1 2024-25** | **2024-09-22**
- **Esito reale**: 1-2 (1X2=A, gol_tot=3, GG/NG=goal)
- **Quote**: 1=3.30 X=3.10 2=2.40

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (50%) [T1 8-11, n=14] | H (40%) [T2 12-15, n=90] | A | ✅ | ❌ |
| DC | 12 | 1X | X2,12 | ✅ | ❌ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | under | over | ✅ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 1_3 | 2_4 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 1-2,2-1,1-1,2-3,0-1 | 2-1,0-2,0-0,2-3,1-3 | 1-2 | ✅ | ❌ |

---


## Match 19/50: Venezia vs Parma

- **uid**: `I1_2024-25_2024-11-09_Venezia_Parma` | **I1 2024-25** | **2024-11-09**
- **Esito reale**: 1-2 (1X2=A, gol_tot=3, GG/NG=goal)
- **Quote**: 1=2.55 X=3.40 2=2.70

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (44%) [T2 12-15, n=181] | H (42%) [T2 12-15, n=38] | A | ❌ | ❌ |
| DC | 1X | 1X | X2,12 | ❌ | ❌ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 1_3 | 2_4 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 0-0,1-2,1-3,1-1,2-1 | 0-0,1-2,2-1,2-2,1-1 | 1-2 | ✅ | ✅ |

---


## Match 20/50: Verona vs Inter

- **uid**: `I1_2024-25_2024-11-23_Verona_Inter` | **I1 2024-25** | **2024-11-23**
- **Esito reale**: 0-5 (1X2=A, gol_tot=5, GG/NG=nogoal)
- **Quote**: 1=7.00 X=5.25 2=1.38

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (50%) [T2 12-15, n=42] | D (36%) [T2 12-15, n=11] | A | ✅ | ❌ |
| DC | X2 | X2 | X2,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | over | over | ❌ | ✅ |
| GG/NG | goal | goal | nogoal | ❌ | ❌ |
| MG | 2_4 | 2_4 | 3_5,4_6 | ❌ | ❌ |
| RE (top5) | 1-3,4-3,3-1,1-2,1-1 | 1-3,4-3,1-2,2-2,1-4 | 0-5 | ❌ | ❌ |

---


## Match 21/50: Roma vs Monza

- **uid**: `I1_2024-25_2025-02-24_Roma_Monza` | **I1 2024-25** | **2025-02-24**
- **Esito reale**: 4-0 (1X2=H, gol_tot=4, GG/NG=nogoal)
- **Quote**: 1=1.33 X=4.75 2=11.00

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (71%) [T2 12-15, n=17] | H (64%) [T2 8-11, n=124] | H | ✅ | ✅ |
| DC | 1X | 1X | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | over | ❌ | ✅ |
| O/U 3.5 | under | under | over | ❌ | ❌ |
| GG/NG | nogoal | goal | nogoal | ✅ | ❌ |
| MG | 1_3 | 1_3 | 2_4,3_5,4_6 | ❌ | ❌ |
| RE (top5) | 4-2,1-0,5-2,1-1,3-0 | 4-2,1-0,5-2,3-0,2-2 | 4-0 | ❌ | ❌ |

---


## Match 22/50: Empoli vs Cagliari

- **uid**: `I1_2024-25_2025-04-06_Empoli_Cagliari` | **I1 2024-25** | **2025-04-06**
- **Esito reale**: 0-0 (1X2=D, gol_tot=0, GG/NG=nogoal)
- **Quote**: 1=2.45 X=3.00 2=3.10

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (47%) [T2 12-15, n=30] | D (39%) [T2 8-11, n=149] | D | ❌ | ✅ |
| DC | 1X | 1X | X2,1X | ✅ | ✅ |
| O/U 1.5 | over | over | under | ❌ | ❌ |
| O/U 2.5 | under | under | under | ✅ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | nogoal | goal | nogoal | ✅ | ❌ |
| MG | 1_3 | 1_3 |  | ❌ | ❌ |
| RE (top5) | 1-3,2-1,1-0,1-1,0-0 | 1-3,2-1,1-0,1-1,2-0 | 0-0 | ✅ | ❌ |

---


## Match 23/50: Parma vs Milan

- **uid**: `I1_2024-25_2024-08-24_Parma_Milan` | **I1 2024-25** | **2024-08-24**
- **Esito reale**: 2-1 (1X2=H, gol_tot=3, GG/NG=goal)
- **Quote**: 1=4.75 X=3.90 2=1.70

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (45%) [T1 8-11, n=152] | H (53%) [T1 8-11, n=32] | H | ✅ | ✅ |
| DC | 12 | 1X | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | over | ❌ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | nogoal | nogoal | goal | ❌ | ❌ |
| MG | 1_3 | 1_3 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 0-1,2-1,1-4,1-0,1-1 | 2-1,0-0,1-0,2-2,0-1 | 2-1 | ✅ | ✅ |

---


## Match 24/50: Roma vs Cagliari

- **uid**: `I1_2024-25_2025-03-16_Roma_Cagliari` | **I1 2024-25** | **2025-03-16**
- **Esito reale**: 1-0 (1X2=H, gol_tot=1, GG/NG=nogoal)
- **Quote**: 1=1.55 X=4.20 2=5.75

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (65%) [T2 12-15, n=43] | H (77%) [T2 12-15, n=13] | H | ✅ | ✅ |
| DC | 1X | 1X | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | under | ❌ | ❌ |
| O/U 2.5 | over | over | under | ❌ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | nogoal | ❌ | ❌ |
| MG | 1_3 | 1_3 | 1_2,1_3 | ✅ | ✅ |
| RE (top5) | 1-0,2-1,1-1,3-1,2-0 | 2-1,1-0,1-1,3-2,0-2 | 1-0 | ✅ | ✅ |

---


## Match 25/50: Monza vs Milan

- **uid**: `I1_2024-25_2024-11-02_Monza_Milan` | **I1 2024-25** | **2024-11-02**
- **Esito reale**: 0-1 (1X2=A, gol_tot=1, GG/NG=nogoal)
- **Quote**: 1=5.00 X=3.60 2=1.70

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (37%) [T2 12-15, n=130] | A (54%) [T2 12-15, n=28] | A | ✅ | ✅ |
| DC | 12 | 12 | X2,12 | ✅ | ✅ |
| O/U 1.5 | over | over | under | ❌ | ❌ |
| O/U 2.5 | over | under | under | ❌ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | nogoal | nogoal | ❌ | ✅ |
| MG | 1_3 | 1_3 | 1_2,1_3 | ✅ | ✅ |
| RE (top5) | 0-1,2-1,0-3,1-2,2-0 | 0-1,0-3,1-2,1-1,1-0 | 0-1 | ✅ | ✅ |

---


## Match 26/50: Rizespor vs Konyaspor

- **uid**: `T1_2024-25_2024-12-14_Rizespor_Konyaspor` | **T1 2024-25** | **2024-12-14**
- **Esito reale**: 1-1 (1X2=D, gol_tot=2, GG/NG=goal)
- **Quote**: 1=2.10 X=3.40 2=3.40

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (44%) [T2 12-15, n=119] | H (49%) [T2 12-15, n=35] | D | ❌ | ❌ |
| DC | 12 | 1X | X2,1X | ❌ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | under | ❌ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 1_3 | 1_3 | 1_2,1_3,2_3,2_4 | ✅ | ✅ |
| RE (top5) | 2-0,0-0,0-1,2-3,0-3 | 2-0,0-0,1-0,1-1,2-1 | 1-1 | ❌ | ✅ |

---


## Match 27/50: Sevilla vs Betis

- **uid**: `SP1_2024-25_2024-10-06_Sevilla_Betis` | **SP1 2024-25** | **2024-10-06**
- **Esito reale**: 1-0 (1X2=H, gol_tot=1, GG/NG=nogoal)
- **Quote**: 1=2.45 X=3.20 2=3.00

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (55%) [T1 8-11, n=11] | H (44%) [T2 12-15, n=63] | H | ❌ | ✅ |
| DC | X2 | 1X | 1X,12 | ❌ | ✅ |
| O/U 1.5 | over | over | under | ❌ | ❌ |
| O/U 2.5 | under | over | under | ✅ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | nogoal | goal | nogoal | ✅ | ❌ |
| MG | 1_3 | 2_4 | 1_2,1_3 | ✅ | ❌ |
| RE (top5) | 0-1,2-2,1-1,1-3,0-0 | 2-2,4-0,0-1,0-3,5-0 | 1-0 | ❌ | ❌ |

---


## Match 28/50: Sp Braga vs Estoril

- **uid**: `P1_2024-25_2024-12-06_SpBraga_Estoril` | **P1 2024-25** | **2024-12-06**
- **Esito reale**: 2-2 (1X2=D, gol_tot=4, GG/NG=goal)
- **Quote**: 1=1.22 X=7.00 2=10.00

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (73%) [T2 12-15, n=52] | H (75%) [T2 12-15, n=16] | D | ❌ | ❌ |
| DC | 1X | 12 | X2,1X | ✅ | ❌ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | over | over | ❌ | ✅ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 2_4 | 2_4 | 2_4,3_5,4_6 | ✅ | ✅ |
| RE (top5) | 3-1,5-0,3-0,1-2,2-1 | 3-1,3-0,4-1,4-0,2-1 | 2-2 | ❌ | ❌ |

---


## Match 29/50: Everton vs West Ham

- **uid**: `E0_2024-25_2025-03-15_Everton_WestHam` | **E0 2024-25** | **2025-03-15**
- **Esito reale**: 1-1 (1X2=D, gol_tot=2, GG/NG=goal)
- **Quote**: 1=2.05 X=3.20 2=3.90

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (47%) [T2 12-15, n=32] | H (50%) [T2 12-15, n=10] | D | ❌ | ❌ |
| DC | 12 | 12 | X2,1X | ❌ | ❌ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | under | ✅ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | nogoal | goal | goal | ❌ | ✅ |
| MG | 1_3 | 1_3 | 1_2,1_3,2_3,2_4 | ✅ | ✅ |
| RE (top5) | 0-2,3-2,0-1,0-0,1-1 | 3-2,1-0,2-0,3-1,0-1 | 1-1 | ✅ | ❌ |

---


## Match 30/50: Guimaraes vs Estrela

- **uid**: `P1_2024-25_2025-03-16_Guimaraes_Estrela` | **P1 2024-25** | **2025-03-16**
- **Esito reale**: 2-0 (1X2=H, gol_tot=2, GG/NG=nogoal)
- **Quote**: 1=1.45 X=4.10 2=7.50

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (58%) [T2 12-15, n=33] | H (53%) [T2 8-11, n=112] | H | ✅ | ✅ |
| DC | 1X | 1X | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | under | under | ❌ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | nogoal | nogoal | ❌ | ✅ |
| MG | 2_4 | 1_3 | 1_2,1_3,2_3,2_4 | ✅ | ✅ |
| RE (top5) | 2-1,3-1,1-0,2-0,0-0 | 2-1,3-1,1-0,0-0,2-3 | 2-0 | ✅ | ❌ |

---


## Match 31/50: Villarreal vs Real Madrid

- **uid**: `SP1_2024-25_2025-03-15_Villarreal_RealMadrid` | **SP1 2024-25** | **2025-03-15**
- **Esito reale**: 1-2 (1X2=A, gol_tot=3, GG/NG=goal)
- **Quote**: 1=3.10 X=3.75 2=2.15

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (45%) [T2 8-11, n=298] | A (49%) [T2 8-11, n=68] | A | ✅ | ✅ |
| DC | 12 | 12 | X2,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 1_3 | 2_4 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 0-3,1-6,1-2,5-2,0-0 | 1-6,1-2,2-1,2-0,1-1 | 1-2 | ✅ | ✅ |

---


## Match 32/50: Strasbourg vs Auxerre

- **uid**: `F1_2024-25_2025-01-05_Strasbourg_Auxerre` | **F1 2024-25** | **2025-01-05**
- **Esito reale**: 3-1 (1X2=H, gol_tot=4, GG/NG=goal)
- **Quote**: 1=1.85 X=3.60 2=4.20

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (36%) [T2 12-15, n=53] | H (50%) [T2 12-15, n=12] | H | ✅ | ✅ |
| DC | 1X | 12 | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | over | ❌ | ✅ |
| O/U 3.5 | under | under | over | ❌ | ❌ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 1_3 | 2_4 | 2_4,3_5,4_6 | ❌ | ✅ |
| RE (top5) | 1-1,3-2,2-2,2-4,0-1 | 2-2,2-4,1-2,3-0,4-0 | 3-1 | ❌ | ❌ |

---


## Match 33/50: St Truiden vs Dender

- **uid**: `B1_2024-25_2024-08-17_StTruiden_Dender` | **B1 2024-25** | **2024-08-17**
- **Esito reale**: 3-3 (1X2=D, gol_tot=6, GG/NG=goal)
- **Quote**: 1=2.55 X=3.40 2=2.70

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (37%) [T1 8-11, n=60] | H (38%) [T1 8-11, n=16] | D | ❌ | ❌ |
| DC | X2 | 12 | X2,1X | ✅ | ❌ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | over | ❌ | ✅ |
| O/U 3.5 | under | under | over | ❌ | ❌ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 1_3 | 2_4 | 4_6 | ❌ | ❌ |
| RE (top5) | 1-1,1-0,0-1,2-2,2-1 | 1-3,2-2,0-1,2-1,1-1 | 3-3 | ❌ | ❌ |

---


## Match 34/50: Brighton vs Ipswich

- **uid**: `E0_2024-25_2024-09-14_Brighton_Ipswich` | **E0 2024-25** | **2024-09-14**
- **Esito reale**: 0-0 (1X2=D, gol_tot=0, GG/NG=nogoal)
- **Quote**: 1=1.38 X=5.00 2=7.50

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (64%) [T1 8-11, n=47] | H (70%) [T1 8-11, n=10] | D | ❌ | ❌ |
| DC | 1X | 1X | X2,1X | ✅ | ✅ |
| O/U 1.5 | over | over | under | ❌ | ❌ |
| O/U 2.5 | over | over | under | ❌ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | nogoal | ❌ | ❌ |
| MG | 2_4 | 2_4 |  | ❌ | ❌ |
| RE (top5) | 2-1,1-1,3-0,3-1,0-0 | 2-1,1-1,3-0,3-1,4-1 | 0-0 | ✅ | ❌ |

---


## Match 35/50: Galatasaray vs Buyuksehyr

- **uid**: `T1_2024-25_2025-05-30_Galatasaray_Buyuksehyr` | **T1 2024-25** | **2025-05-30**
- **Esito reale**: 2-0 (1X2=H, gol_tot=2, GG/NG=nogoal)
- **Quote**: 1=1.70 X=4.75 2=3.90

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (61%) [T2 8-11, n=71] | H (60%) [T2 8-11, n=15] | H | ✅ | ✅ |
| DC | 12 | 12 | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | under | ❌ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | nogoal | ❌ | ❌ |
| MG | 2_4 | 1_3 | 1_2,1_3,2_3,2_4 | ✅ | ✅ |
| RE (top5) | 0-1,5-1,2-2,2-0,2-1 | 2-1,0-1,0-0,7-0,6-1 | 2-0 | ✅ | ❌ |

---


## Match 36/50: Estoril vs Casa Pia

- **uid**: `P1_2024-25_2024-12-15_Estoril_CasaPia` | **P1 2024-25** | **2024-12-15**
- **Esito reale**: 0-2 (1X2=A, gol_tot=2, GG/NG=nogoal)
- **Quote**: 1=2.63 X=3.10 2=2.75

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (43%) [T2 12-15, n=109] | A (39%) [T2 12-15, n=38] | A | ❌ | ✅ |
| DC | 12 | 12 | X2,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | under | under | ❌ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | nogoal | ❌ | ❌ |
| MG | 1_3 | 1_3 | 1_2,1_3,2_3,2_4 | ✅ | ✅ |
| RE (top5) | 0-1,1-3,1-0,1-4,3-0 | 0-1,1-0,1-4,1-2,2-1 | 0-2 | ❌ | ❌ |

---


## Match 37/50: Willem II vs Twente

- **uid**: `N1_2024-25_2024-11-02_WillemII_Twente` | **N1 2024-25** | **2024-11-02**
- **Esito reale**: 0-1 (1X2=A, gol_tot=1, GG/NG=nogoal)
- **Quote**: 1=5.75 X=3.60 2=1.65

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (47%) [T2 12-15, n=89] | A (42%) [T2 12-15, n=12] | A | ✅ | ✅ |
| DC | 12 | 12 | X2,12 | ✅ | ✅ |
| O/U 1.5 | over | over | under | ❌ | ❌ |
| O/U 2.5 | over | over | under | ❌ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | nogoal | ❌ | ❌ |
| MG | 2_4 | 2_4 | 1_2,1_3 | ❌ | ❌ |
| RE (top5) | 1-2,0-3,3-2,0-1,1-1 | 0-3,1-2,2-0,2-2,2-3 | 0-1 | ✅ | ❌ |

---


## Match 38/50: Marseille vs Le Havre

- **uid**: `F1_2024-25_2025-01-05_Marseille_LeHavre` | **F1 2024-25** | **2025-01-05**
- **Esito reale**: 5-1 (1X2=H, gol_tot=6, GG/NG=goal)
- **Quote**: 1=1.30 X=6.00 2=8.00

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (85%) [T2 12-15, n=20] | H (56%) [T2 8-11, n=94] | H | ✅ | ✅ |
| DC | 1X | 12 | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | over | ❌ | ✅ |
| O/U 3.5 | under | under | over | ❌ | ❌ |
| GG/NG | nogoal | nogoal | goal | ❌ | ❌ |
| MG | 2_4 | 2_4 | 4_6 | ❌ | ❌ |
| RE (top5) | 5-0,1-1,2-0,1-0,4-0 | 1-0,4-0,3-2,0-1,2-0 | 5-1 | ❌ | ❌ |

---


## Match 39/50: Wolves vs Chelsea

- **uid**: `E0_2024-25_2024-08-25_Wolves_Chelsea` | **E0 2024-25** | **2024-08-25**
- **Esito reale**: 2-6 (1X2=A, gol_tot=8, GG/NG=goal)
- **Quote**: 1=4.33 X=4.00 2=1.75

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (50%) [T1 12-15, n=32] | H (44%) [T1 8-11, n=172] | A | ❌ | ❌ |
| DC | 12 | 12 | X2,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | over | ❌ | ✅ |
| O/U 3.5 | under | under | over | ❌ | ❌ |
| GG/NG | goal | nogoal | goal | ✅ | ❌ |
| MG | 1_3 | 1_3 |  | ❌ | ❌ |
| RE (top5) | 1-0,2-1,2-0,1-1,1-2 | 1-0,0-0,2-1,2-2,4-0 | 2-6 | ❌ | ❌ |

---


## Match 40/50: Brighton vs Bournemouth

- **uid**: `E0_2024-25_2025-02-25_Brighton_Bournemouth` | **E0 2024-25** | **2025-02-25**
- **Esito reale**: 2-1 (1X2=H, gol_tot=3, GG/NG=goal)
- **Quote**: 1=2.00 X=3.80 2=3.30

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (58%) [T2 12-15, n=19] | H (47%) [T2 8-11, n=116] | H | ✅ | ✅ |
| DC | 1X | 12 | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 3_5 | 2_4 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 3-1,2-1,1-2,0-0,2-2 | 3-1,2-1,0-2,2-2,1-0 | 2-1 | ✅ | ✅ |

---


## Match 41/50: Go Ahead Eagles vs Feyenoord

- **uid**: `N1_2024-25_2024-10-19_GoAheadEagles_Feyenoord` | **N1 2024-25** | **2024-10-19**
- **Esito reale**: 1-5 (1X2=A, gol_tot=6, GG/NG=goal)
- **Quote**: 1=4.50 X=4.50 2=1.65

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (39%) [T2 12-15, n=132] | D (43%) [T2 12-15, n=23] | A | ✅ | ❌ |
| DC | 12 | 1X | X2,12 | ✅ | ❌ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | over | ❌ | ❌ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 2_4 | 2_4 | 4_6 | ❌ | ❌ |
| RE (top5) | 1-1,1-0,2-1,2-2,0-1 | 1-1,2-1,0-3,0-4,2-2 | 1-5 | ❌ | ❌ |

---


## Match 42/50: Mainz vs Hoffenheim

- **uid**: `D1_2024-25_2024-12-01_Mainz_Hoffenheim` | **D1 2024-25** | **2024-12-01**
- **Esito reale**: 2-0 (1X2=H, gol_tot=2, GG/NG=nogoal)
- **Quote**: 1=2.10 X=3.40 2=3.50

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (50%) [T2 12-15, n=113] | H (54%) [T2 12-15, n=26] | H | ✅ | ✅ |
| DC | 1X | 1X | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | under | ❌ | ❌ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | nogoal | nogoal | ❌ | ✅ |
| MG | 2_4 | 1_3 | 1_2,1_3,2_3,2_4 | ✅ | ✅ |
| RE (top5) | 2-1,0-1,0-3,1-1,3-1 | 1-1,3-1,1-0,0-0,2-0 | 2-0 | ❌ | ✅ |

---


## Match 43/50: Augsburg vs Dortmund

- **uid**: `D1_2024-25_2024-10-26_Augsburg_Dortmund` | **D1 2024-25** | **2024-10-26**
- **Esito reale**: 2-1 (1X2=H, gol_tot=3, GG/NG=goal)
- **Quote**: 1=3.60 X=4.00 2=1.90

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (48%) [T2 12-15, n=33] | D (42%) [T2 12-15, n=12] | H | ❌ | ❌ |
| DC | X2 | X2 | 1X,12 | ❌ | ❌ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 2_4 | 2_4 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 1-1,1-3,3-3,1-0,3-1 | 1-1,1-3,3-1,2-2,2-0 | 2-1 | ❌ | ❌ |

---


## Match 44/50: Nijmegen vs Waalwijk

- **uid**: `N1_2024-25_2025-04-11_Nijmegen_Waalwijk` | **N1 2024-25** | **2025-04-11**
- **Esito reale**: 2-1 (1X2=H, gol_tot=3, GG/NG=goal)
- **Quote**: 1=1.67 X=4.00 2=4.75

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (58%) [T2 12-15, n=24] | H (50%) [T2 12-15, n=10] | H | ✅ | ✅ |
| DC | 12 | 12 | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | over | ❌ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 1_3 | 1_3 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 1-0,2-0,2-1,1-1,1-3 | 1-0,1-1,2-3,3-1,1-2 | 2-1 | ✅ | ❌ |

---


## Match 45/50: Werder Bremen vs Holstein Kiel

- **uid**: `D1_2024-25_2024-11-09_WerderBremen_HolsteinKiel` | **D1 2024-25** | **2024-11-09**
- **Esito reale**: 2-1 (1X2=H, gol_tot=3, GG/NG=goal)
- **Quote**: 1=1.62 X=4.33 2=4.75

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (57%) [T2 12-15, n=56] | H (64%) [T2 12-15, n=14] | H | ✅ | ✅ |
| DC | 1X | 1X | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | nogoal | nogoal | goal | ❌ | ❌ |
| MG | 2_4 | 2_4 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 1-0,2-2,2-0,0-0,2-1 | 2-1,0-0,4-0,2-0,2-2 | 2-1 | ✅ | ✅ |

---


## Match 46/50: NAC Breda vs Twente

- **uid**: `N1_2024-25_2025-01-19_NACBreda_Twente` | **N1 2024-25** | **2025-01-19**
- **Esito reale**: 2-1 (1X2=H, gol_tot=3, GG/NG=goal)
- **Quote**: 1=4.75 X=4.10 2=1.65

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (45%) [T2 12-15, n=44] | D (46%) [T2 12-15, n=13] | H | ❌ | ❌ |
| DC | X2 | 1X | 1X,12 | ❌ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | nogoal | goal | ✅ | ❌ |
| MG | 2_4 | 2_4 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 1-6,1-2,1-1,0-2,0-0 | 0-0,2-2,1-1,3-5,0-3 | 2-1 | ❌ | ❌ |

---


## Match 47/50: Twente vs Ajax

- **uid**: `N1_2024-25_2024-11-10_Twente_Ajax` | **N1 2024-25** | **2024-11-10**
- **Esito reale**: 2-2 (1X2=D, gol_tot=4, GG/NG=goal)
- **Quote**: 1=2.55 X=3.40 2=2.70

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | A (46%) [T2 12-15, n=46] | H (41%) [T2 8-11, n=106] | D | ❌ | ❌ |
| DC | 12 | 12 | X2,1X | ❌ | ❌ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | over | ❌ | ✅ |
| O/U 3.5 | under | under | over | ❌ | ❌ |
| GG/NG | nogoal | goal | goal | ❌ | ✅ |
| MG | 1_3 | 1_3 | 2_4,3_5,4_6 | ❌ | ❌ |
| RE (top5) | 1-3,1-0,1-1,1-2,0-1 | 1-3,2-1,2-2,1-2,1-0 | 2-2 | ❌ | ✅ |

---


## Match 48/50: Betis vs Valladolid

- **uid**: `SP1_2024-25_2025-04-24_Betis_Valladolid` | **SP1 2024-25** | **2025-04-24**
- **Esito reale**: 5-1 (1X2=H, gol_tot=6, GG/NG=goal)
- **Quote**: 1=1.20 X=7.00 2=13.00

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (72%) [T2 8-11, n=167] | H (78%) [T2 8-11, n=40] | H | ✅ | ✅ |
| DC | 1X | 1X | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | over | over | over | ✅ | ✅ |
| O/U 3.5 | under | under | over | ❌ | ❌ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 2_4 | 1_3 | 4_6 | ❌ | ❌ |
| RE (top5) | 2-0,1-1,0-1,1-2,1-0 | 2-1,1-0,0-1,2-0,1-1 | 5-1 | ❌ | ❌ |

---


## Match 49/50: Paris SG vs Lens

- **uid**: `F1_2024-25_2024-11-02_ParisSG_Lens` | **F1 2024-25** | **2024-11-02**
- **Esito reale**: 1-0 (1X2=H, gol_tot=1, GG/NG=nogoal)
- **Quote**: 1=1.42 X=5.00 2=6.25

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (80%) [T2 12-15, n=25] | H (56%) [T2 8-11, n=95] | H | ✅ | ✅ |
| DC | 1X | 12 | 1X,12 | ✅ | ✅ |
| O/U 1.5 | over | over | under | ❌ | ❌ |
| O/U 2.5 | over | under | under | ❌ | ✅ |
| O/U 3.5 | over | under | under | ❌ | ✅ |
| GG/NG | goal | nogoal | nogoal | ❌ | ✅ |
| MG | 2_4 | 1_3 | 1_2,1_3 | ❌ | ✅ |
| RE (top5) | 6-1,2-0,3-0,2-1,2-2 | 5-0,2-1,4-0,5-2,1-0 | 1-0 | ❌ | ✅ |

---


## Match 50/50: Westerlo vs Genk

- **uid**: `B1_2024-25_2025-01-25_Westerlo_Genk` | **B1 2024-25** | **2025-01-25**
- **Esito reale**: 1-2 (1X2=A, gol_tot=3, GG/NG=goal)
- **Quote**: 1=3.30 X=3.75 2=2.05

| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |
|---|---|---|---|---|---|
| 1X2 | H (40%) [T2 12-15, n=15] | A (46%) [T2 8-11, n=98] | A | ❌ | ✅ |
| DC | 12 | X2 | X2,12 | ✅ | ✅ |
| O/U 1.5 | over | over | over | ✅ | ✅ |
| O/U 2.5 | under | over | over | ❌ | ✅ |
| O/U 3.5 | under | under | under | ✅ | ✅ |
| GG/NG | goal | goal | goal | ✅ | ✅ |
| MG | 2_4 | 1_3 | 1_3,2_3,2_4,3_5 | ✅ | ✅ |
| RE (top5) | 0-1,3-2,0-2,1-1,3-1 | 0-1,3-2,1-3,3-1,1-1 | 1-2 | ❌ | ❌ |

---


# Riepilogo aggregato — METODO GERARCHICO

Hit rate per ogni mercato, calcolato sul verdetto della prima cella con >= 10 partite (in ordine T1 23/23 -> T5 8-11).


| Mercato | GLOBALE | INTRA-LEGA |
|---|---|---|
| 1X2 | 26/50 = **52.0%** | 26/50 = **52.0%** |
| DC | 41/50 = **82.0%** | 39/50 = **78.0%** |
| O/U 1.5 | 38/50 = **76.0%** | 37/50 = **74.0%** |
| O/U 2.5 | 21/50 = **42.0%** | 36/50 = **72.0%** |
| O/U 3.5 | 35/50 = **70.0%** | 38/50 = **76.0%** |
| GG/NG | 26/50 = **52.0%** | 27/50 = **54.0%** |
| MG | 30/50 = **60.0%** | 30/50 = **60.0%** |
| RE top5 | 24/50 = **48.0%** | 20/50 = **40.0%** |

## Distribuzione celle sorgente (per 1X2)

Da quale cella e' venuto il verdetto piu spesso? Indica quanto i cerchi stretti sono utilizzabili.


### GLOBALE

| Cella | N partite |
|---|---|
| T2 12-15 | 32 |
| T1 8-11 | 9 |
| T2 8-11 | 6 |
| T1 12-15 | 3 |

### INTRA-LEGA

| Cella | N partite |
|---|---|
| T2 12-15 | 24 |
| T2 8-11 | 18 |
| T1 8-11 | 7 |
| T2 16-19 | 1 |

## Baseline (su 32k partite)

| Esito | Baseline |
|---|---|
| 1 | 44.4% |
| X | 24.6% |
| 2 | 31.0% |
| Over 1.5 | 76.9% |
| Over 2.5 | 53.2% |
| Over 3.5 | 30.9% |
| Goal | 53.4% |