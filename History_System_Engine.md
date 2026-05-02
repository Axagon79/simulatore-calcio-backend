# History_Systrem_Engine — Design Document

**Progetto**: AI Simulator
**Modulo**: Sistema di analisi storica per pattern matching strutturale
**Data**: Maggio 2026
**Stato**: Design completo, pronto per implementazione
**Owner**: Lorenzo
**Implementazione**: Claudio (Claude Code)
 
---

## 1. Obiettivo del sistema

Costruire un **motore autonomo e indipendente** dai 6 algoritmi attuali (Statistico, Dinamico, Tattico, Caos, Master, MonteCarlo) e dall'Algo C, che lavori per **analogia storica**: dato il contesto strutturale di una partita di oggi, cerca configurazioni simili nel passato e produce un verdetto basato sulla distribuzione frequentista degli esiti reali di quelle partite.

### Principio guida

Il sistema lavora su **stati statici** ("fotografie del presente"), non su traiettorie. Confronta configurazioni strutturali della partita di oggi con configurazioni storiche, ignorando completamente i dati di forma in-game (xG, possesso, tiri, ecc. — quelli sono già coperti dai 6 algoritmi attuali).

### Differenza concettuale rispetto al resto di AI Simulator

| | 6 algoritmi attuali | Pattern Match Engine |
|---|---|---|
| Cosa guardano | Come stanno giocando ora | A chi assomiglia questa configurazione storicamente |
| Tipo di dato | Statistiche grezze stagionali | Solo metadati di contesto |
| Approccio | Modelli che catturano pattern di gioco | Case-based reasoning frequentista |
| Aggregazione | Combinati da orchestratore MoE | **Sistema indipendente, non si fonde con gli altri** |

---

## 2. Filosofia e vincoli di design

Tutte le decisioni del sistema discendono da questi principi, in ordine di priorità:

### 2.1 Solo stati statici, mai traiettorie
Il sistema non considera **come si è arrivati** allo stato attuale (trend Elo, line movement quote, momentum classifica). Considera solo **dov'è ora**. Aggiungere traiettorie sarebbe Sistema 2 futuro, non parte di questo design.

### 2.2 Coerenza interna assoluta
Tutte le feature parlano la stessa lingua: "stato del momento presente". Niente derivate, niente medie mobili, niente indicatori dinamici.

### 2.3 Non riscrivere il passato
I dati storici si prendono come sono, senza normalizzazioni che li rendano artificialmente comparabili al presente. L'aggio del bookmaker dell'epoca resta com'era. Le quote pre-closing storiche si confrontano con pre-closing attuali.

### 2.4 Pattern matching "a cerchi concentrici"
Il principio del raggio progressivo si applica **a tutto**: tolleranze, numero di feature compatibili, lega. Niente filtri rigidi, solo gradiente di similarità.

### 2.5 Sistema autonomo, non orchestrato
Non entra nel MoE come settimo expert. Vive in parallelo, con propria UI, propria logica, propria collection MongoDB.

### 2.6 Shadow mode iniziale
Al lancio, le predizioni sono visibili solo all'admin (Lorenzo). Eventuale apertura al pubblico è decisione separata e successiva.

### 2.7 Soglie empiriche, non a priori
Le soglie del filtro "partite mostrabili" si definiscono dopo aver fatto analisi statistica una tantum sul dataset storico, non si inventano al tavolino.

---

## 3. Vettore feature: 23 dimensioni

### 3.1 Tabella completa

| # | Feature | Tipo | Note |
|---|---|---|---|
| 1 | `lega` | Categorica | Identifica la competizione |
| 2 | `giornata` | Numerica | Turno di campionato |
| 3 | `posizione_classifica_casa` | Numerica | Generale |
| 4 | `posizione_classifica_ospite` | Numerica | Generale |
| 5 | `punti_casa` | Numerica | Totali stagione |
| 6 | `punti_ospite` | Numerica | Totali stagione |
| 7 | `differenza_punti` | Numerica | `punti_casa - punti_ospite` |
| 8 | `partite_giocate_casa` | Numerica | Per normalizzazione |
| 9 | `partite_giocate_ospite` | Numerica | Per normalizzazione |
| 10 | `gol_fatti_casa` | Numerica | Totali stagione |
| 11 | `gol_subiti_casa` | Numerica | Totali stagione |
| 12 | `gol_fatti_ospite` | Numerica | Totali stagione |
| 13 | `gol_subiti_ospite` | Numerica | Totali stagione |
| 14 | `posizione_classifica_casa_solo_casalinga` | Numerica | Split |
| 15 | `punti_casa_solo_casalinga` | Numerica | Split |
| 16 | `posizione_classifica_ospite_solo_trasferta` | Numerica | Split |
| 17 | `punti_ospite_solo_trasferta` | Numerica | Split |
| 18 | `prob_implicita_1` | Numerica | Da quota Bet365 pre-closing |
| 19 | `prob_implicita_X` | Numerica | Da quota Bet365 pre-closing |
| 20 | `prob_implicita_2` | Numerica | Da quota Bet365 pre-closing |
| 21 | `elo_casa` | Numerica | Alla data della partita |
| 22 | `elo_ospite` | Numerica | Alla data della partita |
| 23 | `elo_diff` | Numerica | `elo_casa - elo_ospite` |

### 3.2 Note critiche sulle quote

- **Bookmaker unico**: Bet365.
- **Tipo**: pre-closing odds (colonne `B365H`, `B365D`, `B365A` di Football-Data.co.uk).
- **Trasformazione**: `prob_implicita = 1/quota`. **Non normalizzare** per togliere l'aggio.
- **Per partita di oggi**: rilevare la quota Bet365 il prima possibile dopo apertura mercato (24-48h dopo pubblicazione), proxy operativo dell'opening.
- **Motivazione**: tesi del mean reversion (Lorenzo) — le opening odds di Bet365 sono empiricamente più predittive delle closing per pattern strutturali, perché le closing incorporano rumore di flusso.

### 3.3 Note critiche sull'Elo

- **Fonte**: clubelo.com (API gratuita: `api.clubelo.com/{NOMECLUB}`).
- **CRITICAL — DATA LEAKAGE**: per ogni partita storica, salvare l'Elo **alla data esatta della partita**, NON l'Elo attuale. La API ClubElo fornisce lo storico day-by-day per ogni squadra: estrarre il valore valido nel periodo che include la data partita.
- Errore tipico da evitare: usare il valore Elo corrente di una squadra per pesare partite di 8 anni fa. Sarebbe data leakage.

### 3.4 Feature ESCLUSE deliberatamente (e perché)

| Feature | Motivo esclusione |
|---|---|
| Mese | Ambigua cross-lega (gennaio in Serie A ≠ gennaio in MLS) |
| Stagione climatica | Approssimativa, non aggiunge segnale netto |
| Giorno settimana | Cambiato significato negli anni (contemporaneità diversa anni '90 vs oggi) |
| Fascia oraria | Valore predittivo marginale |
| Stagione (anno) | Solo filtro temporale del dataset, non feature di matching |
| xG, possesso, tiri | Sono dati di forma in-game, già coperti dai 6 algoritmi |
| Forma WWDLW | Idem |
| Allenatore, infortuni, formazioni | Esplodono spazio feature, dati storici incompleti |
| `is_derby`, `is_salvezza`, `is_scontro_diretto` | Soggettivi e/o derivabili dalla classifica |
| Trend Elo, line movement quote | Sono traiettorie, non stati. Sistema 2 futuro |

---

## 4. Scope dati

### 4.1 Leghe coperte (10)

| # | Lega | Codice F-D | Codice ClubElo |
|---|---|---|---|
| 1 | Premier League 🏴󠁧󠁢󠁥󠁮󠁧󠁿 | E0 | ENG |
| 2 | La Liga 🇪🇸 | SP1 | ESP |
| 3 | Serie A 🇮🇹 | I1 | ITA |
| 4 | Bundesliga 🇩🇪 | D1 | GER |
| 5 | Ligue 1 🇫🇷 | F1 | FRA |
| 6 | Eredivisie 🇳🇱 | N1 | NED |
| 7 | Primeira Liga 🇵🇹 | P1 | POR |
| 8 | Scottish Premiership 🏴󠁧󠁢󠁳󠁣󠁴󠁿 | SC0 | SCO |
| 9 | Pro League Belgio 🇧🇪 | B1 | BEL |
| 10 | Süper Lig Turchia 🇹🇷 | T1 | TUR |

### 4.2 Profondità temporale

- **10 stagioni**: 2015/16 → 2024/25 + stagione corrente in continuo aggiornamento
- **Motivazione del cap a 10 anni**: il calcio si è uniformato globalmente, andare oltre introduce rumore (calcio strutturalmente diverso) senza guadagno informativo.

### 4.3 Volume atteso

~33.000 partite storiche complete (3.300 partite/stagione × 10 stagioni).

### 4.4 Esclusioni

- ❌ Coppe (Champions, Europa, Conference, coppe nazionali)
- ❌ Extra leagues di Football-Data (dataset incompleto, manca B365 garantito)
- ❌ Dati pre-2015
- ❌ Statistiche di partita (xG, possesso, ecc.)

---

## 5. Algoritmo di matching: matrice 5×5

### 5.1 Concetto

Per ogni partita di oggi, il sistema produce una **matrice di evidenze 5×5** (25 celle), incrociando due dimensioni di similarità:

- **Asse X — livello di tolleranza** (quanto stretto è il match per ogni feature)
- **Asse Y — numero feature compatibili** (quanti attributi corrispondono effettivamente)

### 5.2 Tabella tolleranze multi-livello

Ogni feature numerica ha 5 soglie di tolleranza, una per ogni livello (T1=strettissima, T5=larghissima):

| Feature | T1 | T2 | T3 | T4 | T5 |
|---|---|---|---|---|---|
| Giornata | ±0 | ±1 | ±2 | ±4 | ±6 |
| Posizione classifica (qualsiasi) | ±0 | ±1 | ±2 | ±4 | ±6 |
| Punti (casa/ospite) | ±0 | ±2 | ±4 | ±7 | ±12 |
| Differenza punti | ±0 | ±2 | ±5 | ±10 | ±15 |
| Partite giocate | ±0 | ±1 | ±2 | ±4 | ±6 |
| Gol (fatti/subiti) | ±0 | ±3 | ±6 | ±10 | ±15 |
| Posizione split | ±0 | ±1 | ±2 | ±4 | ±6 |
| Punti split | ±0 | ±1 | ±3 | ±6 | ±10 |
| `prob_implicita_1` | ±0 pp | ±1.5 pp | ±4 pp | ±8 pp | ±15 pp |
| `prob_implicita_X` | ±0 pp | ±1.5 pp | ±4 pp | ±8 pp | ±15 pp |
| `prob_implicita_2` | ±0 pp | ±1.5 pp | ±4 pp | ±8 pp | ±15 pp |
| Elo casa/ospite | ±0 | ±15 | ±35 | ±75 | ±150 |
| Elo diff | ±0 | ±20 | ±50 | ±100 | ±200 |

(`pp` = punti percentuali assoluti su probabilità implicita)

### 5.3 Tolleranza per la lega (categorica)

| Livello | Comportamento |
|---|---|
| T1 | Stessa lega esatta |
| T2 | Stessa lega esatta |
| T3 | Stessa lega esatta |
| T4 | Lega della stessa famiglia/tier |
| T5 | Qualsiasi lega delle 10 |

**Tier proposti** (da raffinare):
- Tier alto: Premier, La Liga, Bundesliga, Serie A
- Tier medio: Ligue 1, Eredivisie, Primeira
- Tier base: Belgio, Turchia, Scozia

### 5.4 Definizione di "compatibile"

Una feature è **compatibile a livello Tn** se:
- È numerica → la differenza assoluta tra valore di oggi e valore storico è ≤ tolleranza Tn
- È categorica (lega) → segue la regola del tier per Tn

### 5.5 Costruzione della matrice

Per ogni partita storica e per ogni livello di tolleranza T1..T5:
- Conta quante delle 23 feature sono compatibili a quel livello
- Classifica la partita in una delle 5 fasce di compatibilità: `23/23`, `20-22/23`, `16-19/23`, `12-15/23`, `8-11/23`

Risultato: ogni partita storica è classificata in una cella della matrice 5×5 per ogni livello di tolleranza.

**Nota implementativa**: una partita storica può comparire in più celle (es. compatibile 23/23 a T5 ma 18/23 a T3). Si conta in tutte le celle dove rientra.

### 5.6 Output per ogni cella

Per ogni cella della matrice 5×5:
- Numero di partite trovate
- Distribuzione esiti: % di 1, X, 2
- Lista top-K partite (es. K=5) per riferimento qualitativo (per Mistral)

### 5.7 Vista intra-lega (secondo livello di analisi)

Oltre alla matrice globale (su tutte le 10 leghe), il sistema produce una **seconda matrice 5×5 ristretta alla sola lega** della partita di oggi.

Mistral confronta i due output (globale vs intra-lega) per identificare specificità di lega.

---

## 6. Output del sistema

### 6.1 Struttura dati per ogni partita predetta

```json
{
  "match_id": "...",
  "lega": "I1",
  "data_partita": "2026-05-10T20:45:00Z",
  "home_team": "Inter",
  "away_team": "Milan",
  "feature_vector_today": { ... 23 features ... },
  "matrix_global": {
    "cells": [
      {
        "tolerance_level": "T1",
        "compatibility_band": "23/23",
        "n_matches": 0,
        "outcome_distribution": null,
        "top_matches": []
      },
      {
        "tolerance_level": "T3",
        "compatibility_band": "16-19/23",
        "n_matches": 87,
        "outcome_distribution": { "1": 0.54, "X": 0.23, "2": 0.23 },
        "top_matches": [ ... 5 match references ... ]
      }
      // ... 25 celle totali
    ]
  },
  "matrix_intra_league": { ... stessa struttura ... },
  "narrative_mistral": "Le evidenze più strette in Serie A...",
  "predictability_score": 0.78,
  "is_high_quality": true,
  "computed_at": "2026-05-10T04:00:00Z"
}
```

### 6.2 Narrativa Mistral

**Modello**: `mistral-medium-2508` (già in uso nel progetto).

**Compito di Mistral**: ricevere le due matrici (globale + intra-lega) e produrre 2-4 paragrafi che evidenziano:
- Convergenze tra cerchi (esito coerente a tutti i livelli → segnale forte)
- Divergenze (esito che cambia tra cerchi → segnale debole o configurazione anomala)
- Confronto globale vs intra-lega
- Eventuali pattern interessanti nelle top match

**Vincoli per Mistral**:
- Restare ancorato ai numeri della matrice
- Non inventare interpretazioni qualitative non supportate dai dati
- Non parlare di squadre specifiche in modo soggettivo, solo come riferimenti analoghi
- Tono asciutto, descrittivo, no marketing

### 6.3 Predictability score

Calcolato a posteriori (dopo analisi statistica una tantum del dataset storico) come funzione di:
- Numerosità match nei cerchi stretti
- Convergenza esito tra cerchi
- Confidenza esito dominante

Score normalizzato 0-1. Soglia per `is_high_quality` da definire dopo analisi del dataset.

---

## 7. Architettura MongoDB

### 7.1 Cluster e database

Stesso cluster di AI Simulator. Stesso database principale. **Niente nuovo cluster**.

### 7.2 Collection nuove (3)

Tutte con prefisso `historical__` per raggruppamento visivo nell'interfaccia Compass/Atlas.

#### `historical__matches_pattern`
Dataset storico delle ~33.000 partite, ognuna con il vettore feature completo + esito reale.

```json
{
  "_id": ObjectId,
  "match_uid": "I1_2018_2018-09-15_INTER_MILAN",
  "lega": "I1",
  "stagione": "2018-19",
  "data_partita": ISODate,
  "home_team": "Inter",
  "away_team": "Milan",
  "feature_vector": {
    "lega": "I1",
    "giornata": 4,
    "posizione_classifica_casa": 5,
    // ... tutte le 23 feature
  },
  "outcome": {
    "result_1x2": "1",
    "goals_home": 1,
    "goals_away": 0,
    "ft_score": "1-0"
  },
  "raw_data_sources": {
    "footballdata_row": { ... },
    "clubelo_home_at_date": 1834,
    "clubelo_away_at_date": 1798
  },
  "ingested_at": ISODate,
  "schema_version": 1
}
```

**Indici**:
- `{lega: 1, stagione: 1, data_partita: 1}` — query temporali
- `{match_uid: 1}` unique — deduplica
- Compound su feature più filtrate in fase di matching (da raffinare in tuning)

#### `historical__pattern_predictions`
Predizioni shadow del sistema per le partite del giorno.

Struttura come sezione 6.1.

**Indici**:
- `{data_partita: 1}` — query del giorno
- `{is_high_quality: 1, predictability_score: -1}` — ordinamento dashboard

#### `historical__pattern_validation`
Confronto tra predizione del sistema e esito reale, per monitoraggio accuracy.

```json
{
  "_id": ObjectId,
  "match_id": "...",
  "predicted_distribution": { "1": 0.54, "X": 0.23, "2": 0.23 },
  "predicted_dominant": "1",
  "actual_outcome": "X",
  "hit": false,
  "brier_score": 0.42,
  "log_loss": 1.47,
  "validated_at": ISODate
}
```

**Indici**:
- `{validated_at: -1}` — report temporali
- `{hit: 1}` — accuracy aggregata

---

## 8. Pipeline di ingestion

### 8.1 Script una tantum: `ingest_historical_dataset.py`

Da eseguire una sola volta al setup, poi solo aggiornamenti incrementali.

**Step**:

1. **Download CSV Football-Data.co.uk** per le 10 leghe × 10 stagioni
   - URL pattern: `https://www.football-data.co.uk/mmz4281/{stagione}/{codice_lega}.csv`
   - Esempio: `https://www.football-data.co.uk/mmz4281/2324/I1.csv`
   - Cache locale, retry con backoff su errori
   - Libreria consigliata: `soccerdata` (wrapper Python già pronto)

2. **Parse CSV → struct intermedie**
   - Estrai: data, home_team, away_team, FTHG, FTAG, FTR, B365H, B365D, B365A
   - Normalizza nomi squadre (mapping per gestire varianti tipografiche)

3. **Calcolo classifiche progressive**
   - Per ogni partita, ricostruisci la classifica della lega **al momento della partita** (escludendo la partita stessa)
   - Calcola: posizione, punti, gol fatti/subiti, partite giocate per casa e ospite
   - Idem per classifiche split (solo casalinga / solo trasferta)

4. **Download Elo storico ClubElo**
   - Per ogni squadra unica, una chiamata API `api.clubelo.com/{nome_squadra}`
   - Restituisce CSV con storico day-by-day: `From, To, Elo`
   - Cache locale (i dati storici non cambiano)

5. **Match Elo per ogni partita**
   - Per ogni partita: trova il record ClubElo dove `From <= data_partita <= To`
   - Estrai Elo casa e Elo ospite a quella data
   - **CRITICAL**: usare l'Elo del giorno della partita, MAI quello attuale

6. **Calcolo prob_implicite**
   - `prob_1 = 1 / B365H`, `prob_X = 1 / B365D`, `prob_2 = 1 / B365A`
   - Niente normalizzazione

7. **Costruzione vettore feature 23-dim per ogni partita**

8. **Insert in MongoDB** (`historical__matches_pattern`)
   - Bulk insert, batch da 1000
   - Skip se `match_uid` già esiste

### 8.2 Script ricorrente: `update_historical_dataset.py`

Da inserire nel pipeline notturno `update_manager.py` (step nuovo, eventualmente come step 39.5 dopo il 39 attuale).

**Compito**: scaricare le partite delle ultime 24-48h delle 10 leghe e aggiungerle al dataset storico. Aggiornare anche gli Elo recenti.

### 8.3 Script di matching: `pattern_match_engine.py`

Eseguito ogni notte alle 04:00 nel pipeline. Per ogni partita delle 10 leghe in programma nelle prossime 24-48h:

1. Carica vettore feature della partita di oggi (dalle predizioni esistenti, integrato con quote Bet365 fresche)
2. Carica dataset storico in memoria (~10MB di numpy array)
3. Calcola matrice 5×5 globale e intra-lega
4. Calcola predictability score
5. Genera narrativa Mistral
6. Salva in `historical__pattern_predictions`

**Performance attesa**: <5 secondi per partita su CPU normale (brute force su 33k×23 floats).

### 8.4 Script di validazione: `validate_pattern_predictions.py`

Dopo che le partite finiscono, confronta predizione vs esito reale e popola `historical__pattern_validation`.

---

## 9. Frontend / Dashboard

### 9.1 Posizionamento

**Tab nuovo** dentro la pagina pronostici esistente di AI Simulator (frontend Vercel `aisimulator.vercel.app`).

**Nome tab**: da decidere (proposte: "Storico", "Analogie", "Pattern").

### 9.2 Visibilità

- **Inizio**: solo admin (Lorenzo). Flag su account.
- **Dopo validazione**: decisione separata su apertura al pubblico.

### 9.3 Contenuto del tab

Lista delle partite del giorno con `is_high_quality = true`, ordinate per `predictability_score` decrescente.

Per ogni partita, una **card** con:
- Header: home vs away, lega, ora
- Vettore feature riassunto (3-4 dati salienti)
- Visualizzazione matrice 5×5 (cella colorate per esito dominante, numerosità in tooltip)
- Narrativa Mistral
- Esito reale (se partita finita) + verdetto: ✅ ci ha azzeccato / ❌ no
- Badge predictability_score

### 9.4 Vista admin di calibrazione

Una **seconda vista** (toggle in alto) che mostra **tutte** le partite, anche quelle borderline o senza segnale, per analisi. Utile per Lorenzo per vedere il sistema "nudo".

---

## 10. Definizione soglie filtro (a posteriori)

### 10.1 Procedura una tantum

**Prima del deploy** in produzione, eseguire script di analisi statistica del dataset storico:

```python
# Pseudo-script
for ogni_partita in dataset_storico:
    matrice_5x5 = simula_matching(partita, dataset_storico_escluso_se_stessa)
    statistiche.append({
        "n_matches_per_cella": ...,
        "convergenza_tra_cerchi": ...,
        "confidenza_esito_dominante": ...
    })

distribuzioni = analizza(statistiche)
soglie = scegli_percentili(distribuzioni)  # es: 70° percentile
```

### 10.2 Output dello script

Tabella con percentili delle metriche su tutto il dataset. Esempio fittizio:

| Metrica | 50° pct | 70° pct | 90° pct |
|---|---|---|---|
| N matches al cerchio T3 16-19/23 | 45 | 87 | 150 |
| Convergenza tra cerchi | 2/5 | 3/5 | 4/5 |
| Confidenza esito dominante | 0.42 | 0.51 | 0.62 |

Da queste tabelle Lorenzo decide manualmente le soglie di `is_high_quality`.

### 10.3 Quando rifarlo

Le soglie vanno riviste:
- Quando il dataset cresce significativamente (es. ogni anno)
- Quando si osservano comportamenti anomali in produzione

---

## 11. Roadmap implementativa proposta

### Fase 0 — Preparazione (~1 giorno)
- Setup cartella `ai_engine/pattern_match/`
- Scaffolding moduli vuoti
- Test connessione ClubElo + Football-Data
- Mapping nomi squadre Football-Data ↔ ClubElo

### Fase 1 — Ingestion (~2-3 giorni)
- `ingest_historical_dataset.py` completo
- Verifica integrità dei ~33.000 documenti
- Spot check manuali su partite famose (Inter-Juve 2019, Liverpool-City 2022, ecc.)

### Fase 2 — Matching engine (~2-3 giorni)
- `pattern_match_engine.py` con algoritmo 5×5
- Test su partite storiche (verifica che il sistema dia risultati sensati)
- Tuning soglie tolleranza se necessario

### Fase 3 — Mistral narrativa (~1-2 giorni)
- Prompt design + test su partite reali
- Iterazione sul tono e struttura

### Fase 4 — Frontend tab (~3-4 giorni)
- UI del tab in pagina pronostici
- Visualizzazione matrice 5×5
- Card delle partite

### Fase 5 — Validation pipeline (~1 giorno)
- `validate_pattern_predictions.py`
- Dashboard accuracy aggregata

### Fase 6 — Calibrazione soglie (~1 giorno)
- Script di analisi statistica
- Definizione soglie `is_high_quality`

### Fase 7 — Integrazione pipeline notturno (~0.5 giorno)
- Aggiunta step in `update_manager.py`
- Test end-to-end

**Totale stimato**: 11-15 giorni di lavoro Claudio + review Lorenzo.

---

## 12. Cose da NON fare (anti-pattern)

Per evitare derive nell'implementazione, qui i divieti espliciti:

- ❌ **NON** integrare nel MoE come settimo expert
- ❌ **NON** mescolare con i dati grezzi di forma stagionale (xG, possesso, ecc.)
- ❌ **NON** usare Elo attuale per partite storiche (data leakage)
- ❌ **NON** normalizzare l'aggio del bookmaker
- ❌ **NON** inventare soglie di filtro a priori — sempre da analisi empirica
- ❌ **NON** usare le closing odds — solo pre-closing
- ❌ **NON** aggiungere feature di traiettoria (trend Elo, line movement) — Sistema 2 futuro
- ❌ **NON** estendere a coppe o leghe extra — fuori scope per ora
- ❌ **NON** usare MSA, vector DB esotici, GPU, training di modelli — non servono
- ❌ **NON** creare nuovi cluster/database MongoDB — vive in quello esistente con prefisso

---

## 13. Cose specifiche da segnalare a Claudio

### 13.1 Comportamento richiesto durante implementazione

- **Verificare prima di codificare**: prima di scrivere ogni modulo, mostrare a Lorenzo lo schema/firma e chiedere conferma.
- **Non inventare dati**: se manca un'informazione (es. nome squadra in ClubElo non mappa a Football-Data), chiedere a Lorenzo, NON inventare.
- **Distinguere osservato vs inferito**: ogni risultato presentato deve specificare se è da query diretta o da derivazione.
- **"Non lo so" è una risposta valida**: se qualcosa non è chiaro, fermarsi e chiedere.

### 13.2 Punti di attenzione tecnica

- **Mapping nomi squadre**: i CSV di Football-Data e l'API di ClubElo usano grafie diverse (es. "Man United" vs "Manchester United"). Costruire un dict di mapping una tantum, gestire le varianti.
- **Date format**: Football-Data usa `dd/mm/yyyy`. ClubElo usa ISO. Standardizzare tutto a ISO 8601.
- **Promosse/retrocesse**: una squadra può non esistere in Premier nel 2017 (era in Championship). Gestire il caso "squadra non in lega in quella stagione" con grazia.
- **Stagioni con date irregolari**: la stagione 2019/20 (COVID) è anomala. Considerare se includerla o flaggarla.
- **Quote mancanti**: alcune partite vecchie possono avere `B365H = 0` o NaN. Gestire con fallback (es. usare Pinnacle PSH/PSD/PSA come backup, oppure escludere la partita).

### 13.3 Test minimi prima di considerare "fatto"

- Almeno 1 partita per ogni lega × ogni stagione caricata correttamente
- Spot check manuale: 10 partite famose con valori verificabili a occhio
- Performance: matching engine <5 secondi per partita
- Idempotenza: ri-eseguire l'ingestion non duplica documenti

---

## 14. Glossario

| Termine | Definizione |
|---|---|
| **Pattern Match Engine** | Nome del sistema oggetto di questo documento |
| **Vettore feature** | I 23 numeri/categorie che descrivono una partita |
| **Matrice 5×5** | Output del sistema: 5 livelli tolleranza × 5 livelli compatibilità |
| **Cerchio concentrico** | Sinonimo informale di livello di tolleranza |
| **Compatibilità** | Numero di feature delle 23 che combaciano (entro tolleranza) |
| **Pre-closing odds** | Quote rilevate prima della chiusura del mercato (campo B365H/D/A) |
| **Closing odds** | Quote finali, poco prima del fischio d'inizio (campo B365CH/CD/CA) |
| **Probabilità implicita** | 1/quota, senza normalizzazione aggio |
| **Aggio** | Margine del bookmaker, somma prob. implicite > 100% |
| **ClubElo** | Servizio gratuito di rating Elo storico per club di calcio |
| **Football-Data.co.uk** | Fonte gratuita di risultati storici + quote bookmaker |
| **Predictability score** | Punteggio 0-1 che misura quanto il sistema è "sicuro" della predizione |
| **Shadow mode** | Sistema attivo ma visibile solo all'admin |
| **Data leakage** | Errore in cui si usano informazioni dal futuro per predire il passato |
| **Mean reversion** | Tendenza delle quote a tornare verso l'opening dopo oscillazioni |

---

## 15. Stato finale

Design **completo, coerente, chiuso**. Pronto per essere consegnato a Claudio (Claude Code) per implementazione.

Ogni decisione in questo documento è frutto di discussione iterativa con Lorenzo. Tutte le motivazioni sono tracciate. Tutti i compromessi sono espliciti.

**Modifiche al design da qui in avanti vanno trattate come deviazioni dall'autorità** e richiedono approvazione esplicita.

---

*Documento di design generato a maggio 2026 in collaborazione tra Lorenzo (product owner & architect) e Claude (analytical layer).*
