# Audit qualità Feedback Loop Mistral

Obiettivo: decidere se le analisi prodotte da `feedback_loop_analyzer.py`
(step 29.5 della pipeline notturna) sono abbastanza affidabili per **chiudere
il loop** in automatico (aggiornare i pesi dei motori sulla base dei
suggerimenti), o se serve un livello umano intermedio.

Dataset analizzato: **618 documenti** di `prediction_errors`.
Finestra reale: **2026-03-09 → 2026-04-19** (il Feedback Loop è attivo da 41
giorni, non da fine febbraio come ipotizzato).

---

## Verdetto rapido

**NO, non si può chiudere il loop in automatico oggi.**

Le analisi sono ben strutturate e, sul singolo caso, sensate. Ma 3 elementi
impediscono l'apply automatico:

1. **Mistral non conosce i valori dei pesi attuali.** Il prompt gli dice *i
   nomi* dei sub-motori ma non i *valori* (es. PESI_SEGNO['strisce']=0.0202).
   Quindi i suggerimenti sono a livello "ridurre peso strisce" — serve un
   umano per tradurre in "ridurre da 0.0202 a 0.015".
2. **Contraddizioni settimanali massicce.** Nella stessa settimana lo stesso
   sub-motore viene raccomandato *sia "aumentare" sia "ridurre"*. Nel W11:
   **`strisce` ha 30 suggerimenti "aumenta" + 115 "riduci"**. Applicare
   direttamente genererebbe un rumore di aggiustamenti incoerenti.
3. **Campione ristretto su "solo errori"**, non su successi. Mistral vede solo
   casi in cui il modello ha sbagliato → bias cognitivo: tende sempre a
   "ridurre il peso di quello che ha sbagliato", ma non vede i casi in cui lo
   stesso peso ha funzionato. Un sistema di auto-aggiornamento deve bilanciare
   i due lati.

Il loop chiuso è fattibile **con un livello di aggregazione** (non applicare
singoli suggerimenti ma statistiche settimanali) e **con conferma umana**
(step semi-automatico: propone, l'umano approva in un click).

---

## Analisi 1 — Campione 30 documenti stratificato

File: [campione_30.csv](campione_30.csv)

Divisione (per data `created_at`):
- **10 più vecchi** (9-10 marzo 2026, W11)
- **10 mediani** (attorno al 24-26 marzo, W13)
- **10 più recenti** (18-19 aprile, W16)

Nota: il Feedback Loop non ha documenti prima del 9/3 → non c'è una fascia
"fine febbraio" come ipotizzato inizialmente.

### Esempio 1 — 2026-03-09 Genoa vs Roma (SEGNO "2")

- Pronostico: SEGNO 2, quota 1.91, prob 70%, stake 4 → Persa (Roma-Genoa 1-2 ribaltato)
- **Severity**: high
- **Root cause**: "Roma imbattuta in 4 partite ma Genoa senza vittorie nascondeva reazione"
- **AI analysis**: "Il modello ha dato 70% per il 2 basandosi su 4 imbattibilità della Roma, ignorando che il Genoa nelle ultime 3 partite ha sempre segnato. La quota 4.20 per il 1 segnalava un'anomalia che il modello non ha intercettato. La simulazione Monte Carlo dava 70% per la vittoria della Roma, ma il Genoa ha vinto 2-1."
- **Suggested**: "Ridurre il peso di 'strisce' quando la squadra sfavorita ha quote > 4.00 — il mercato prezza un upset possibile."
- **Variables impact**: streaks 0.6, market_odds 0.4, resto 0

Giudizio: **buona qualità**. Analisi coerente, cita numeri specifici, suggerimento è una regola contestuale (non un semplice "aumenta/diminuisci X").

### Esempio 2 — 2026-03-18 Reggiana vs Monza (SEGNO "2")

- Pronostico: SEGNO 2, quota 1.62, prob 70%, stake 2 → Persa (pareggio 0-0)
- **Severity**: high
- **AI analysis**: "Il modello ha sovrastimato il Monza (70% confidence) basandosi su quote 1.62 e bvs 71.8, ma Monte Carlo segnalava solo 10% home_win_pct. Le strisce della Reggiana (3 sconfitte consecutive) erano un segnale fuorviante, mentre il Monza in trasferta aveva 3 over25 nelle ultime 3 partite. Il mercato (59.3% prob) era più vicino alla realtà di quanto il modello non abbia pesato."
- **Suggested**: "Ridurre il peso di 'bvs' e 'quote' quando Monte Carlo home_win_pct < 15% — il segnale è troppo debole per un pronostico SEGNO."
- **Variables impact**: form 0.45, market_odds 0.35, streaks 0.1

Giudizio: **ottima qualità**. Identifica la discrepanza segno modello vs Monte Carlo (il pronostico è in diretto disaccordo con MC) — un pattern che se venisse sistematizzato come regola di sanity-check produrrebbe valore.

### Esempio 3 — 2026-04-19 Torreense vs Marítimo (Goal)

- Pronostico: Goal, quota 1.70, prob 65%, stake 1 → Persa (1:0 Under 2.5 + NG)
- **Severity**: high
- **Suggested**: "Aumentare il peso di **strisce** (soprattutto clean_sheet ≥ 3) e ridurre l'influenza di **att_vs_def** quando **xg** e **media_gol** sono neutrali, con penalizzazione se **under25** ospite ≥ 70% nelle ultime 3 partite."
- **Variables impact**: streaks 0.45, market_odds 0.45

Giudizio: **molto buona**. Prescrive una regola condizionale multifattore (strisce clean_sheet ≥ 3 AND xg/media_gol neutrali) — è il tipo di suggerimento difficile da applicare automaticamente ma potenzialmente utile per un umano che rifinisce la scrematura.

### Giudizio complessivo del campione

Su 30 analisi lette:
- **Testo ben strutturato** (segue il formato chiesto dal prompt, niente frasi
  vuote — il prompt stesso vieta "frasi vaghe tipo 'suggerendo valutazione
  equilibrata'").
- **Cita numeri**: quasi tutte le `root_cause` e `ai_analysis` citano % Monte
  Carlo, quote, strisce specifiche (come il prompt chiede).
- **Pattern tags coerenti** con il caso.
- **Variables impact bilanciate**: in media 2-3 fattori dominanti per caso,
  come richiesto dal prompt ("assegna 0.0 alle variabili irrilevanti").

---

## Analisi 2 — Evoluzione temporale

### 2a) Pattern tags per settimana

File: [pattern_tags_per_settimana.csv](pattern_tags_per_settimana.csv)

Tags dominanti settimana per settimana (top 3):

| Settimana | #1 | #2 | #3 |
| --- | --- | --- | --- |
| W11 | quota_troppo_bassa (177) | modello_overconfident (159) | striscia_interrotta (128) |
| W12 | quota_troppo_alta (48) | striscia_interrotta (47) | modello_overconfident (45) |
| W13 | quota_troppo_alta (46) | striscia_interrotta (43) | modello_overconfident (33) |
| W14 | modello_overconfident (47) | quota_troppo_bassa (46) | striscia_interrotta (41) |
| W15 | modello_overconfident (100) | quota_troppo_bassa (91) | striscia_interrotta (82) |
| W16 | modello_overconfident (62) | striscia_interrotta (59) | quota_troppo_bassa (59) |

**Pattern ricorrenti in TUTTE le settimane**: `modello_overconfident`,
`striscia_interrotta`, `quota_troppo_bassa`. Mistral identifica consistentemente
tre famiglie di errore stabili nel tempo → segnale sano.

Nuovi pattern emergono a metà periodo: `difesa_atipica` compare in W14 (20) e
esplode in W15 (45) e W16 (33). Questo **coincide con un periodo di errori su
Over/Goal dove la difesa performa meglio del previsto** — Mistral lo nota.

### 2b) Severity per settimana

File: [severity_per_settimana.csv](severity_per_settimana.csv)

| Settimana | Totale | low | medium | high | % high |
| --- | ---: | ---: | ---: | ---: | ---: |
| W11 | 274 | 100 | 47 | 127 | 46.4% |
| W12 | 71 | 13 | 9 | 49 | 69.0% |
| W13 | 54 | 4 | 6 | 44 | 81.5% |
| W14 | 54 | 1 | 8 | 45 | 83.3% |
| W15 | 100 | 1 | 19 | 80 | 80.0% |
| W16 | 65 | 0 | 11 | 54 | 83.1% |

**Drift severity da W11 a W16**: la percentuale `high` passa da 46% a 83%.
Interpretazione: Mistral sta diventando sempre più severo nel giudicare gli
errori. Due ipotesi:
- Il modello del motore sta effettivamente peggiorando → più errori gravi.
- Mistral "impara" a essere più duro nel tempo senza che il motore cambi (ma
  non ha memoria tra chiamate, quindi è improbabile).

Più probabile: la composizione del dataset cambia. A W11 c'erano più pronostici
a bassa confidence (low severity dominante), mentre nelle settimane successive
il motore si è concentrato su pronostici a confidence alta che falliscono
clamorosamente (high severity dominante). Questo coincide con l'ipotesi del
**Punto 1**: il motore overconfident nel bin 70-80% sbaglia con frequenza alta.

### 2c) Sub-motori più suggeriti (direzione)

File: [submotori_suggeriti.csv](submotori_suggeriti.csv)

| Sub-motore | Totale citato | Aumenta | Riduci | Misto |
| --- | ---: | ---: | ---: | ---: |
| **strisce** | 377 | 94 | **166** | 104 |
| **quote** | 271 | 61 | **152** | 47 |
| media_gol | 152 | 38 | 46 | 60 |
| att_vs_def | 109 | 31 | 26 | 47 |
| xg | 69 | 19 | 17 | 32 |
| edge | 66 | 21 | 7 | 29 |
| h2h_gol | 59 | 16 | 19 | 20 |
| bvs | 51 | 11 | 18 | 16 |
| confidence | 49 | 11 | 10 | 17 |
| affidabilita | 46 | 13 | 2 | 26 |
| h2h | 39 | 8 | 14 | 16 |
| motivazioni | 38 | 13 | 2 | 23 |

**Osservazione chiave**:
- **`strisce`** è il sub-motore più spesso citato (377 volte) e con direzione
  dominante **"ridurre"** (166 vs 94). Coerente col pattern
  `striscia_interrotta` / `forma_fuorviante` che ricorre in tutte le settimane.
- **`quote`** è il secondo più citato (271), anche qui con direzione
  dominante **"ridurre"** (152 vs 61). Coerente con pattern
  `quota_troppo_bassa` / `quota_troppo_alta`.
- `affidabilita` (46) è citato 13 volte "aumenta" e 2 "riduci". Anche se poco
  frequente, ha direzione molto univoca.
- `motivazioni` (38) è 13 "aumenta" vs 2 "riduci". Mistral vede le motivazioni
  come sottoutilizzate.

**Lettura operativa**: se esistesse un modo grossolano di applicare queste
indicazioni, i due segnali più forti sarebbero "ridurre peso strisce" e
"ridurre peso quote". Attualmente in PESI_SEGNO[A] `strisce` pesa 2.02% e
`quote` 1.99% — sono già fra i più bassi. Invece in PESI_GOL[A] `strisce`
pesa **12.18%** — questo potrebbe effettivamente essere troppo alto.

### 2d) Contraddizioni settimanali

File: [contraddizioni_settimanali.csv](contraddizioni_settimanali.csv)

**Ogni sub-motore nella maggior parte delle settimane è raccomandato in
direzioni opposte**. Esempi (settimana W11):

| Sub-motore | Aumenta | Riduci | Totale |
| --- | ---: | ---: | ---: |
| quote | 41 | 119 | 168 |
| strisce | 30 | 115 | 150 |
| media_gol | 6 | 23 | 35 |
| att_vs_def | 6 | 16 | 26 |
| dna | 6 | 12 | 20 |

**Diagnosi**: Mistral analizza ogni caso in isolamento. Un singolo pronostico
perso dove strisce hanno ingannato → "ridurre strisce". Un altro pronostico
perso dove strisce non sono state usate → "aumentare strisce". Entrambi nello
stesso giorno. Lo è coerente per il *singolo caso* ma contraddittorio in
aggregato.

**Implicazione critica per il loop chiuso**: se applichiamo
meccanicamente ogni suggerimento, otteniamo un walk random dei pesi. Serve
aggregare (es. "questa settimana strisce è stato citato 115 volte riduci vs
30 aumenta → bilancio netto ridurre") prima di applicare.

### 2e) Root cause — varietà o ripetizione?

File: [root_cause_per_settimana.csv](root_cause_per_settimana.csv)

Prendendo le prime 4 parole di ogni `root_cause` e contando ripetizioni per
settimana: **le top 5 frasi per settimana compaiono al massimo 1-2 volte
ciascuna**. Mistral **non ripete frasi identiche** settimana dopo settimana →
buon segnale di varietà analitica.

Ma la struttura sintattica è identica ("X [numero] ma Y [numero]
nascondeva/segnalava Z"). È il prompt che lo forza (`root_cause` max 20
parole, deve citare almeno un numero). Quindi: forma costante, sostanza
variabile — il comportamento desiderato.

---

## Analisi 3 — Mistral conosce i pesi?

### Cosa dice il prompt

Dal file [ai_engine/feedback_loop_analyzer.py:45-140](../../ai_engine/feedback_loop_analyzer.py#L45):

```
suggested_adjustment (1 frase):
- DEVE nominare il segnale specifico del modello da modificare (usa i nomi
  dei campi: bvs, lucifero, affidabilita, dna, motivazioni, h2h, campo,
  strisce, media_gol, att_vs_def, xg, ecc.)
```

→ Mistral **riceve i nomi** dei sub-motori (bvs, lucifero, affidabilita, dna,
motivazioni, h2h, campo, strisce, media_gol, att_vs_def, xg).

### Cosa NON riceve

Dal contesto che `build_context_for_mistral()` costruisce (linea 196-254):

- ✅ `segno_dettaglio` (score 0-100 di ogni sub-motore **per quel match**)
- ✅ `gol_dettaglio` (idem per GOL)
- ✅ Quote, strisce, Monte Carlo
- ❌ **I pesi attuali** (PESI_SEGNO / PESI_GOL con i valori 0.206, 0.0202, ...)
- ❌ I thresholds (THRESHOLD_INCLUDE, ecc.)
- ❌ Che la formula usa Kelly 1/4 (A/S) o 3/4 (C)

**Risposta alla domanda**: Mistral **conosce i nomi ma non conosce i valori**
dei pesi. Quindi può dire "ridurre peso strisce" ma non "ridurre
PESI_SEGNO['strisce'] da 0.0202 a 0.015".

### Top 5 suggerimenti più specifici

File: [top5_suggerimenti_specifici.csv](top5_suggerimenti_specifici.csv)

Uno su tutti (2026-04-12, Bodrum vs Bandirma):

> "Aggiungere un **filtro di contraddizione** tra `media_gol` (73.4 over) e
> `strisce` (under25=6 consecutivi): se la discrepanza supera il 30%, ridurre
> il peso di `bvs` e `lucifero` del 50% e aumentare quello di `h2h_gol` e
> `att_vs_def`."

Questo è il **massimo di specificità** che Mistral raggiunge. Nota:
- Cita percentuali ("30%", "50%") — ma **inventate**, non basate sui pesi
  reali del sistema (lucifero pesa 3.81% in PESI_SEGNO).
- Prescrive una logica a filtro ("se discrepanza > 30% allora...")
- Mischia sub-motori SEGNO e GOL (`bvs` è SEGNO, `h2h_gol` è GOL) — fattibile
  solo se c'è un orchestratore che legge entrambi.

### Lettura

Gli `suggested_adjustment` sono **pseudocodice di policy**, non istruzioni
applicabili:
- Forniscono intent ("ridurre l'influenza di strisce in presenza di X")
- Non forniscono il numero preciso
- A volte confondono tipi di mercato

Un umano può trasformarli in modifiche concrete ai file Python (PESI_SEGNO,
PESI_GOL, regole di scrematura). Un processo automatico **non può** senza un
meccanismo di traduzione "intent → numero".

---

## Stats globali

File: [stats_globali.json](stats_globali.json)

| Metrica | Valore |
| --- | ---: |
| Totale documenti | 618 |
| Finestra date | 2026-03-09 → 2026-04-19 |
| Con `variables_impact` | **618 / 618** (100%) |
| Con `root_cause` | **618 / 618** (100%) |
| Con `ai_analysis` | **618 / 618** (100%) |
| Con `suggested_adjustment` | **618 / 618** (100%) |
| Con `pattern_tags` | 607 / 618 (98.2%) |
| Severity high | 399 (64.6%) |
| Severity medium | 100 (16.2%) |
| Severity low | 119 (19.3%) |
| Severity null | 0 |

**Completezza quasi perfetta**. Il Feedback Loop ha zero fallimenti su
`ai_analysis`/`root_cause`/`suggested_adjustment`, solo 11 casi senza
pattern_tags. Significa che il prompt è ben tarato e Mistral risponde sempre
nel formato richiesto.

### Medie di `variables_impact`

| Fattore | Media |
| --- | ---: |
| **market_odds** | **0.405** |
| **streaks** | **0.266** |
| tactical_dna | 0.124 |
| form | 0.058 |
| home_advantage | 0.042 |
| motivation | 0.034 |
| h2h | 0.024 |
| fatigue | 0.000 |

**Quattro osservazioni forti**:
1. `market_odds` domina: Mistral dice "il mercato aveva ragione" nel 40% dei
   casi medi. È coerente con la diagnosi del Punto 1 (motore
   **overconfident**): il mercato, che incorpora la saggezza della folla,
   spesso vede meglio.
2. `streaks` è il secondo fattore: 27% del peso medio. Coerente con
   `striscia_interrotta` nei pattern_tags.
3. `fatigue` è **a 0.000 stabile**. Mistral non attribuisce mai errori alla
   stanchezza. Ha senso perché il contesto non fornisce calendari: fatigue è
   un fattore che Mistral non può giudicare senza i dati.
4. `h2h` è bassissimo (0.024). Mistral ritiene che l'h2h non sia
   responsabile di molti errori — eppure il peso `h2h` in PESI_SEGNO è
   3.95% e `h2h_gol` in PESI_GOL è 15.79%. Possibile sovrarappresentazione nel
   motore?

---

## Risposta sintetica alle 3 domande

### 1. Mistral è concretamente utilizzabile per auto-aggiornare i pesi?

**No, non direttamente.** Per tre ragioni:
- Non conosce i valori attuali dei pesi → suggerimenti qualitativi.
- 40-70% di contraddizioni settimanali sullo stesso sub-motore.
- Campione solo su errori, non su successi → bias di attribuzione.

### 2. Serve un livello umano intermedio?

**Sì, oggi è necessario.** Possibili workflow:

- **Livello minimo (report settimanale)**: ogni settimana Mistral aggrega →
  un umano decide cosa cambiare manualmente. È lo stato "da completare" che il
  sistema aveva già progettato (vedi `analyze_prediction_errors.py` non
  schedulato).
- **Livello medio (proposta automatica + approvazione)**: uno script
  aggrega i suggerimenti settimanali per sub-motore, calcola il bilancio
  netto (aumenta/riduci), produce una proposta di modifica dei pesi di entità
  piccola (es. ±2-5% del valore attuale). L'umano approva con un click.
  Questo richiede infrastruttura nuova.
- **Livello avanzato (ottimizzazione dati-driven)**: bypassare Mistral e usare
  una procedura Optuna / bayesian optimization con segnale diretto su ROI
  storico. Mistral rimane come "spiegatore", non come decisore.

### 3. Cosa funziona in Mistral, cosa no?

**Funziona:**
- Diagnosi del singolo caso (ai_analysis + root_cause sono ben fatte)
- Identificazione consistente di 3 pattern di errore macro
  (`modello_overconfident`, `striscia_interrotta`, `quota_troppo_bassa/alta`)
- `variables_impact` aggregati danno un segnale forte e coerente
  (market_odds 0.405, streaks 0.266)
- Coerenza formale (100% dei campi compilati)

**Non funziona:**
- Apply automatico dei singoli `suggested_adjustment`
- Traduzione "nome sub-motore" → "valore numerico peso"
- Coerenza cross-case nella stessa finestra temporale
- Giudizio di mercati dove Mistral non ha dati (fatigue = 0 sempre)

---

## Implicazioni per il Kelly calibrato

La calibrazione bin-based che ho usato al Punto 3 **non richiede Mistral**:
bastano gli esiti reali vs probabilita_stimata. È un loop chiuso pulito, senza
LLM di mezzo. Il cerotto Kelly calibrato può partire oggi senza dipendere
dalle analisi Mistral.

Mistral può servire **dopo**, come layer esplicativo:
- "La calibrazione ha spostato lo stake del 20% — perché?"
- "Mistral ha identificato che `strisce` era sovraponderato. La nuova mappa
  di calibrazione conferma un bias overconfident del 15% nel bin 70-80% per
  pronostici dominati dalle strisce."

Mistral diventa utile come **traduttore di pattern statistici in lingua
operativa**, non come ottimizzatore di pesi.

---

## File generati

- `campione_30.csv` — 30 documenti stratificati (leggibile a mano)
- `root_cause_per_settimana.csv` — top 5 prefissi root_cause per settimana
- `pattern_tags_per_settimana.csv` — distribuzione tag per settimana
- `severity_per_settimana.csv` — distribuzione severity per settimana
- `submotori_suggeriti.csv` — sub-motori citati in `suggested_adjustment` con direzioni
- `contraddizioni_settimanali.csv` — sub-motori con direzioni opposte nella stessa settimana
- `top5_suggerimenti_specifici.csv` — i 5 suggerimenti più specifici trovati
- `stats_globali.json` — metriche aggregate (completezza, severity, variables_impact medi)
