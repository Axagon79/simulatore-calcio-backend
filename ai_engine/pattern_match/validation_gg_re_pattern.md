# Test pattern: coerenza GG/NG vs Top 15 RE

**Test set**: 49 partite (seed=42)

**N RE controllati per partita**: 15


## Logica

Per ogni partita: confronto la predizione GG/NG con i top 15 RE.
Conto quanti RE sono *coerenti*:
- Se predizione = **Goal** → RE coerente se entrambe le squadre hanno ≥1 gol (es. 1-1, 2-1)
- Se predizione = **NoGoal** → RE coerente se almeno una squadra a 0 (es. 0-0, 1-0, 0-1)

Più coerenza = più segnale forte. Verifico se hit rate aumenta con coerenza.


## Hit rate GG/NG per livello di coerenza

| Coerenza (RE coerenti / 15) | N partite | Hit | Hit rate |
|---|---|---|---|
| 10/15 | 1 | 0 | **0.0%** |
| 9/15 | 2 | 1 | **50.0%** |
| 8/15 | 8 | 6 | **75.0%** |
| 7/15 | 11 | 5 | **45.5%** |
| 6/15 | 16 | 10 | **62.5%** |
| 5/15 | 10 | 8 | **80.0%** |
| 4/15 | 1 | 0 | **0.0%** |

## Cumulativo: Hit rate quando coerenza >= soglia

| Soglia minima coerenza | N partite (>=) | Hit | Hit rate |
|---|---|---|---|
| ≥ 10/15 | 1/49 | 0 | **0.0%** |
| ≥ 9/15 | 3/49 | 1 | **33.3%** |
| ≥ 8/15 | 11/49 | 7 | **63.6%** |
| ≥ 7/15 | 22/49 | 12 | **54.5%** |
| ≥ 6/15 | 38/49 | 22 | **57.9%** |
| ≥ 5/15 | 48/49 | 30 | **62.5%** |
| ≥ 4/15 | 49/49 | 30 | **61.2%** |

## Dettaglio per partita (ordinate per coerenza decrescente)

| Coerenza | Partita | Reale | Predetto | GG % | Hit |
|---|---|---|---|---|---|
| 10/14 | Roma vs Fiorentina (1-0) | nogoal | goal (65%) | ❌ |
| 9/14 | Roma vs Monza (4-0) | nogoal | goal (65%) | ❌ |
| 9/14 | Go Ahead Eagles vs Feyenoord (1-5) | goal | goal (60%) | ✅ |
| 8/14 | Udinese vs Lazio (2-1) | goal | goal (70%) | ✅ |
| 8/14 | Roma vs Lecce (4-1) | goal | goal (55%) | ✅ |
| 8/11 | Lazio vs Udinese (1-1) | goal | goal (70%) | ✅ |
| 8/12 | Brighton vs Ipswich (0-0) | nogoal | goal (65%) | ❌ |
| 8/15 | Mainz vs Hoffenheim (2-0) | nogoal | goal (65%) | ❌ |
| 8/13 | Augsburg vs Dortmund (2-1) | goal | goal (70%) | ✅ |
| 8/12 | NAC Breda vs Twente (2-1) | goal | goal (55%) | ✅ |
| 8/14 | Betis vs Valladolid (5-1) | goal | goal (50%) | ✅ |
| 7/12 | Venezia vs Juventus (2-3) | goal | nogoal (65%) | ❌ |
| 7/12 | Lazio vs Lecce (0-1) | nogoal | goal (55%) | ❌ |
| 7/11 | Genoa vs Juventus (0-3) | nogoal | goal (55%) | ❌ |
| 7/11 | Napoli vs Bologna (3-0) | nogoal | nogoal (55%) | ✅ |
| 7/12 | Monza vs Milan (0-1) | nogoal | goal (60%) | ❌ |
| 7/10 | Guimaraes vs Estrela (2-0) | nogoal | goal (70%) | ❌ |
| 7/12 | Villarreal vs Real Madrid (1-2) | goal | goal (60%) | ✅ |
| 7/14 | Strasbourg vs Auxerre (3-1) | goal | goal (50%) | ✅ |
| 7/11 | Willem II vs Twente (0-1) | nogoal | goal (70%) | ❌ |
| 7/12 | Nijmegen vs Waalwijk (2-1) | goal | goal (50%) | ✅ |
| 7/13 | Westerlo vs Genk (1-2) | goal | goal (60%) | ✅ |
| 6/11 | Napoli vs Roma (1-0) | nogoal | goal (50%) | ❌ |
| 6/12 | Parma vs Inter (2-2) | goal | nogoal (55%) | ❌ |
| 6/13 | Torino vs Atalanta (2-1) | goal | goal (50%) | ✅ |
| 6/9 | Monza vs Bologna (1-2) | goal | nogoal (80%) | ❌ |
| 6/10 | Venezia vs Parma (1-2) | goal | goal (70%) | ✅ |
| 6/10 | Verona vs Inter (0-5) | nogoal | nogoal (60%) | ✅ |
| 6/11 | Empoli vs Cagliari (0-0) | nogoal | goal (50%) | ❌ |
| 6/12 | Parma vs Milan (2-1) | goal | goal (55%) | ✅ |
| 6/11 | Roma vs Cagliari (1-0) | nogoal | nogoal (65%) | ✅ |
| 6/12 | Sp Braga vs Estoril (2-2) | goal | nogoal (55%) | ❌ |
| 6/11 | St Truiden vs Dender (3-3) | goal | goal (55%) | ✅ |
| 6/12 | Marseille vs Le Havre (5-1) | goal | nogoal (70%) | ❌ |
| 6/11 | Wolves vs Chelsea (2-6) | goal | goal (65%) | ✅ |
| 6/11 | Brighton vs Bournemouth (2-1) | goal | goal (55%) | ✅ |
| 6/10 | Werder Bremen vs Holstein Kiel (2-1) | goal | goal (70%) | ✅ |
| 6/13 | Twente vs Ajax (2-2) | goal | goal (50%) | ✅ |
| 5/9 | Genoa vs Lazio (0-2) | nogoal | nogoal (55%) | ✅ |
| 5/13 | Empoli vs Fiorentina (0-0) | nogoal | nogoal (55%) | ✅ |
| 5/13 | Inter vs Napoli (1-1) | goal | goal (50%) | ✅ |
| 5/11 | Milan vs Udinese (1-0) | nogoal | nogoal (65%) | ✅ |
| 5/10 | Lecce vs Parma (2-2) | goal | goal (60%) | ✅ |
| 5/10 | Venezia vs Verona (1-1) | goal | nogoal (55%) | ❌ |
| 5/8 | Sevilla vs Betis (1-0) | nogoal | nogoal (65%) | ✅ |
| 5/13 | Everton vs West Ham (1-1) | goal | nogoal (55%) | ❌ |
| 5/10 | Estoril vs Casa Pia (0-2) | nogoal | nogoal (60%) | ✅ |
| 5/10 | Paris SG vs Lens (1-0) | nogoal | nogoal (55%) | ✅ |
| 4/10 | Rizespor vs Konyaspor (1-1) | goal | nogoal (55%) | ❌ |