"""
GENERATE BOLLETTE — Step 35 Pipeline Notturna
==============================================
Genera bollette (biglietti scommessa pre-composti) tramite Mistral AI.
Legge pronostici unified per 3 giorni, recupera selezioni valide da
bollette saltate, e produce max 10 bollette al giorno.
"""

import os, sys, re, json, time, glob, logging, threading
from datetime import datetime, timedelta, timezone

# --- LOGGING ---
logger = logging.getLogger("bollette")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    logger.addHandler(_handler)

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

# ==================== PATTERN MATCHING BOLLETTE ====================
# Usa gli stessi 85 pattern del Mixer (tag_mixer.py)
# Un pronostico entra nel pool non-elite se matcha almeno uno di questi

from tag_mixer import _check, PATTERNS

def matches_bollette_pattern(sel):
    """Controlla se una selezione matcha almeno uno degli 85 pattern Mixer.
    Usato per filtrare il pool prima di passarlo a Mistral nelle sezioni non-elite."""
    if sel.get("pronostico") == "NO BET":
        return False
    # Mappa campo 'mercato' -> 'tipo' per compatibilità (bollette usa 'mercato', mixer usa 'tipo')
    p = dict(sel)
    if 'mercato' in p and 'tipo' not in p:
        p['tipo'] = p['mercato']
    flags = _check(p)
    return any(all(flags.get(c, False) for c in conds) for conds in PATTERNS.values())


try:
    import requests
except ImportError:
    logger.error("Modulo 'requests' non trovato. Installa con: pip install requests")
    sys.exit(1)

from bollette_config import (
    OPENROUTER_URL, OPENROUTER_MODEL, MISTRAL_URL, MISTRAL_MODEL,
    MAX_BOLLETTE, FASCE, CATEGORY_CONSTRAINTS, SECTION_ORDER, SECTION_TARGETS,
    QUOTA_TOTALE_TOLERANCE_UP, QUOTA_TOTALE_TOLERANCE_DOWN,
    QUOTA_SINGOLA_TOLERANCE, MAX_RETRY_FEEDBACK,
    MIN_SCORE_PER_CATEGORY, MIN_SCORE_RECOMPOSE,
    SCRIPT_TIMEOUT_MINUTES,
)

DEBUG_MODE = False  # Attivato con --debug, salva prompt LLM su file

# --- CONFIGURAZIONE LLM (DeepSeek R1 via OpenRouter + fallback Mistral) ---
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")

# Carica da .env se non in ambiente
if not OPENROUTER_API_KEY or not MISTRAL_API_KEY:
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(current_path, '.env'))
        OPENROUTER_API_KEY = OPENROUTER_API_KEY or os.environ.get("OPENROUTER_API_KEY")
        MISTRAL_API_KEY = MISTRAL_API_KEY or os.environ.get("MISTRAL_API_KEY")
        if not OPENROUTER_API_KEY or not MISTRAL_API_KEY:
            root_env = os.path.join(current_path, '..', '..', '.env')
            load_dotenv(os.path.abspath(root_env))
            OPENROUTER_API_KEY = OPENROUTER_API_KEY or os.environ.get("OPENROUTER_API_KEY")
            MISTRAL_API_KEY = MISTRAL_API_KEY or os.environ.get("MISTRAL_API_KEY")
    except ImportError:
        pass

# Almeno un provider deve essere disponibile
if not OPENROUTER_API_KEY and not MISTRAL_API_KEY:
    logger.error("Nessuna API key trovata (OPENROUTER_API_KEY o MISTRAL_API_KEY)!")
    sys.exit(1)

# Provider attivo
if OPENROUTER_API_KEY:
    LLM_URL = OPENROUTER_URL
    LLM_MODEL = OPENROUTER_MODEL
    LLM_API_KEY = OPENROUTER_API_KEY
    LLM_PROVIDER = "DeepSeek R1 (OpenRouter)"
else:
    LLM_URL = MISTRAL_URL
    LLM_MODEL = MISTRAL_MODEL
    LLM_API_KEY = MISTRAL_API_KEY
    LLM_PROVIDER = "Mistral (fallback)"
logger.info(f"LLM: {LLM_PROVIDER}")

# --- PROMPT MISTRAL ---
SYSTEM_PROMPT = """Sei un analista dati sportivo specializzato nella composizione di bollette scommesse. NON sei tu a fare i pronostici — quelli li ha già fatti un sistema AI. Il tuo compito è ANALIZZARE i dati statistici di ogni selezione e decidere QUALI COMBINARE insieme nei biglietti.

Ricevi un pool di selezioni (pronostici già decisi dall'AI) con: partita, mercato, pronostico, quota, confidence, stelle. Per ogni partita hai anche dati statistici: classifica, forma, trend, motivazione, strisce, affidabilità, DNA tecnico.

Il tuo lavoro è:
- LEGGERE i dati statistici di ogni selezione
- ESCLUDERE selezioni con segnali negativi (squadra in crisi, trend in calo, affidabilità bassa, motivazione assente)
- PREFERIRE selezioni con segnali positivi (buona forma, trend in salita, alta affidabilità, motivazione forte)
- COMBINARE selezioni in bollette equilibrate, diversificando mercati e campionati
- NON mettere nello stesso biglietto troppe selezioni rischiose

Rispetta TUTTE queste regole:

═══════════════════════════════════════
REGOLE COMPOSIZIONE
═══════════════════════════════════════

1. Ogni partita può apparire UNA SOLA VOLTA per bolletta, con UN SOLO mercato
2. REGOLA CRITICA: la stessa selezione (stessa partita + stesso pronostico) può apparire MASSIMO 1 VOLTA per categoria. Se generi 3 bollette "oggi", una selezione può stare in UNA sola di quelle 3. Stesso per elite, selettiva, bilanciata, ambiziosa. Se ripeti la stessa selezione in 2 bollette della stessa categoria e quella perde, perdi entrambe. DIVERSIFICA
3. Hai a disposizione partite di oggi, domani e dopodomani. Sei libero di scegliere come combinarle: puoi fare bollette miste o concentrate su un giorno solo. Consiglio: cerca di non mettere TUTTE le partite dello stesso giorno in tutte le bollette, ma segui il tuo istinto da professionista
4. Obiettivo: fino a {max_bollette} bollette totali, divise in 5 categorie. Genera fino a 3 bollette per categoria, ma se la qualità del pool non è sufficiente puoi generarne meno (anche 0):

   📌 OGGI — Campo "tipo": "oggi"
   - SOLO ed ESCLUSIVAMENTE partite di oggi ({today_date}). OGNI selezione deve avere data {today_date}
   - Se una selezione ha data diversa da {today_date}, NON può stare in una bolletta "oggi"
   - Quote libere, qualsiasi fascia
   - Minimo 2, massimo 4 selezioni per bolletta. Diversifica: una da 2, una da 3, una da 4
   - Fino a 3 bollette oggi

   📌 SELETTIVA — Campo "tipo": "selettiva"
   - Fino a 3 bollette selettive
   - Quota totale MASSIMO 4.50
   - Minimo 2, massimo 5 selezioni per bolletta
   - Quota max per SINGOLA selezione (varia in base al numero di selezioni):
     • 2 selezioni → ogni quota max 2.20
     • 3 selezioni → ogni quota max 1.70
     • 4 selezioni → ogni quota max 1.50
     • 5 selezioni → ogni quota max 1.38

   📌 BILANCIATA — Campo "tipo": "bilanciata"
   - Fino a 3 bollette bilanciate
   - Quota totale tra 5.00 e 7.50
   - Minimo 2, massimo 7 selezioni per bolletta
   - Quota max per SINGOLA selezione (varia in base al numero di selezioni):
     • 2 selezioni → ogni quota max 2.80
     • 3 selezioni → ogni quota max 2.00
     • 4 selezioni → ogni quota max 1.68
     • 5 selezioni → ogni quota max 1.52
     • 6 selezioni → ogni quota max 1.41
     • 7 selezioni → ogni quota max 1.35

   📌 AMBIZIOSA — Campo "tipo": "ambiziosa"
   - Fino a 3 bollette ambiziose!
   - Quota totale superiore a 8.0
   - Minimo 4, massimo 8 selezioni per bolletta
   - Quota max per SINGOLA selezione (varia in base al numero di selezioni):
     • 4 selezioni → ogni quota max 3.00
     • 5 selezioni → ogni quota max 2.50
     • 6 selezioni → ogni quota max 2.20
     • 7 selezioni → ogni quota max 2.00
     • 8 selezioni → ogni quota max 1.80

   📌 ELITE — Campo "tipo": "elite"
   - Fino a 3 bollette elite
   - TUTTE le selezioni DEVONO essere ★ELITE dal POOL ELITE (100%, nessuna eccezione)
   - NON inserire MAI selezioni non-elite in bollette di tipo elite
   - Le bollette elite NON hanno vincolo sulle date: possono avere partite di oggi, domani o dopodomani liberamente
   - Quota totale MASSIMO 8.00
   - Minimo 2, massimo 5 selezioni per bolletta
   - Quota max per SINGOLA selezione (varia in base al numero di selezioni):
     • 2 selezioni → ogni quota max 2.85
     • 3 selezioni → ogni quota max 2.00
     • 4 selezioni → ogni quota max 1.68
     • 5 selezioni → ogni quota max 1.52
   - Se non ci sono abbastanza selezioni elite nel pool, genera meno bollette elite (anche 0 se necessario)

   Le bollette "oggi" sono SEPARATE e DIVERSE dalle altre — non devono essere le stesse bollette delle altre fasce
   Distribuzione: fino a 3 oggi, fino a 3 selettive, fino a 3 bilanciate, fino a 3 ambiziose, fino a 3 elite
5. Dai preferenza a selezioni con confidence e stelle alte, MA i dati statistici contano di più: una selezione con confidence media ma forma alta, trend in salita e affidabilità forte è MEGLIO di una con confidence alta ma squadra in crisi
5b. ⭐ SELEZIONI ELITE ⭐ — Le selezioni marcate con ★ELITE nel pool sono pronostici che matchano pattern storicamente vincenti (hit rate > 80%). Dai loro PRIORITÀ ASSOLUTA: ogni bolletta dovrebbe contenere almeno 1 selezione elite se disponibile. Non forzare combinazioni innaturali, ma a parità di scelta preferisci SEMPRE una selezione elite
6. ⚠️⚠️⚠️ REGOLA OBBLIGATORIA — ALMENO 1 PARTITA DI OGGI ⚠️⚠️⚠️
   Per le bollette selettiva/bilanciata/ambiziosa: OGNI SINGOLA bolletta DEVE contenere ALMENO 1 partita di OGGI ({today_date}).
   Questa regola NON è opzionale. Una bolletta senza partite di oggi è INVALIDA e verrà scartata.
   L'utente vuole SEMPRE avere qualcosa da seguire subito. Se non ci sono abbastanza partite oggi, metti quelle che ci sono e completa con domani/dopodomani.
   CONTROLLA ogni bolletta prima di inviarla: c'è almeno 1 selezione con data {today_date}? Se no, aggiungila.
8. Non creare bollette con una sola selezione — almeno 2 selezioni per bolletta (selettiva: 2-5, bilanciata: 2-7, ambiziosa: 4-8)
9. Per ogni bolletta, scrivi una motivazione di 2 righe nel campo "reasoning" che spiega PERCHÉ hai scelto quelle selezioni. Cita RH, RA, C e i dati statistici chiave (forma, classifica, trend). Esempio: "Fiorentina RH=65 RA=58 C=72 — 5° in casa, forma 65%, trend in salita. Benevento RH=45 RA=52 C=68 — 4 vittorie consecutive, affidabilità 8.2/10". NO frasi generiche tipo "combinazione sicura" o "favorite nette"
10. Cerca di variare il numero di selezioni tra le bollette della stessa categoria, non mettere sempre lo stesso numero
11. ⚠️ DIVERSIFICAZIONE OBBLIGATORIA DEL NUMERO DI SELEZIONI ⚠️
   NON fare bollette con lo stesso numero di selezioni nella stessa categoria. Segui questi schemi:
   - OGGI (fino a 3 bollette): una da 2, una da 3, una da 4 selezioni
   - SELETTIVA (fino a 3 bollette): una da 2, una da 3, una da 4 selezioni
   - BILANCIATA (fino a 3 bollette): una da 3, una da 5, una da 7 selezioni
   - AMBIZIOSA (fino a 3 bollette): una da 4, una da 6, una da 8 selezioni
   - ELITE (fino a 3 bollette): una da 2, una da 3, una da 4 selezioni
   Questa regola è OBBLIGATORIA. Bollette tutte con lo stesso numero di selezioni verranno scartate.
12. Genera fino a 3 bollette per categoria. Se non ci sono abbastanza selezioni di qualità (punteggio ≥ soglia), generane di meno. È meglio una bolletta in meno che una bolletta perdente in partenza.

═══════════════════════════════════════════════════════════════════════════════
REGOLE DI COMPOSIZIONE (VINCOLI SOFT CON PRIORITÀ ALLA QUALITÀ)
═══════════════════════════════════════════════════════════════════════════════

1. NUMERO BOLLETTE: Obiettivo 3 per categoria, ma riduci se la qualità non è sufficiente.
   Non sacrificare mai la qualità per raggiungere un numero.

2. QUOTA TOTALE: Intervallo desiderabile (es. 1.5-4.5 per selettiva).
   Puoi accettare uno sforamento fino al 15% se la bolletta ha un punteggio medio ≥8.

3. QUOTA SINGOLA: Non superare i limiti indicati, A MENO CHE la selezione non abbia:
   - Punteggio finale ≥9
   - RH e RA in zone OTTIMALI/DEBOLI vincenti (es. RH 10-30, RA 50-70)
   - Mercato GOL o DOPPIA_CHANCE (più affidabili di SEGNO)
   In tal caso, puoi estendere la quota singola massima del 20%.

4. PRIORITÀ ASSOLUTA: Massimizzare il Valore Atteso complessivo del portafoglio.
   Se una bolletta viola un vincolo ma ha EV stimato molto alto, preferiscila a una che rispetta i vincoli ma ha EV basso.

5. SELEZIONI EXTRA: le selezioni marcate "EXTRA" nel pool provengono da partite non elaborate dal sistema AI.
   NON hanno punteggio finale né RH/RA/C. Usale SOLO se strettamente necessario e MAI in bollette ELITE o SELETTIVE.
   Possono essere usate come riempitivo per bollette AMBIZIOSE o BILANCIATE.

═══════════════════════════════════════════════════════════════════════════════
GUIDA OPERATIVA A RH, RA, C — CALIBRATA SU 671 PARTITE REALI
═══════════════════════════════════════════════════════════════════════════════

Ogni selezione ha 3 indicatori già calcolati (range 0-100): RH, RA e C.
Il sistema assegna automaticamente una ZONA a ciascun valore:

| ZONA     | RANGE               | SIGNIFICATO                                          |
|----------|---------------------|------------------------------------------------------|
| OTTIMALE | 30-50               | Zona di riferimento. HR medio-alto.                  |
| DEBOLE   | 10-30 oppure 50-70  | Comportamento DIVERSO per RH e RA (vedi anomalie).   |
| ASSENTE  | <10 oppure >70      | SEGNALE ROSSO — EVITA SEMPRE. HR crolla.             |

ANOMALIE CONFERMATE DAI DATI REALI (671 partite):
- RH: la zona migliore è DEBOLE_BASSO 10-30 (HR 59.5%), seguita da OTTIMALE 30-50 (55.4%).
  Le zone alte (50-70 e >70) sono le peggiori (43.1% e 43.8%).
- RA: la zona migliore è DEBOLE_ALTO 50-70 (HR 57.5%), seguita da OTTIMALE 30-50 (56.2%).
  Le zone basse (<10 e 10-30) sono le peggiori (33.3% e 51.3%).
- C: DEBOLE_ALTO 50-70 (HR 54.9%) è leggermente superiore a OTTIMALE 30-50 (53.9%).
  ASSENTE >70 crolla a 38.5%. C non scende MAI sotto 30.

═══════════════════════════════════════════════════════════════════════════════
PASSO 1 — PUNTEGGIO BASE (SOLO RH, RA, C)
═══════════════════════════════════════════════════════════════════════════════

Per ogni selezione, somma i punti. I valori sono calibrati sugli HR reali:

| CONDIZIONE                                  | PUNTI |
|---------------------------------------------|-------|
| RH in zona DEBOLE_BASSO (10-30)             | +4    |
| RH in zona OTTIMALE (30-50)                 | +3    |
| RH in zona DEBOLE_ALTO (50-70)              | -1    |
| RH in zona ASSENTE (<10 o >70)              | -4    |
| RA in zona DEBOLE_ALTO (50-70)              | +4    |
| RA in zona OTTIMALE (30-50)                 | +3    |
| RA in zona DEBOLE_BASSO (10-30)             | +1    |
| RA in zona ASSENTE (<10 o >70)              | -4    |
| C in zona DEBOLE_ALTO (50-70)               | +2    |
| C in zona OTTIMALE (30-50)                  | +1    |
| C in zona ASSENTE (>70)                     | -3    |

Il punteggio grezzo:
  >= 7 = Fondamenta statistiche ECCELLENTI.
  4-6  = Selezione BUONA/DISCRETA.
  <= 3 = Selezione DEBOLE, da usare con cautela o scartare.

═══════════════════════════════════════════════════════════════════════════════
PASSO 2 — BONUS E MALUS DAGLI ALTRI DATI
═══════════════════════════════════════════════════════════════════════════════

BONUS (aggiungi al punteggio base):
| Fattore                              | Bonus | Note                                        |
|--------------------------------------|-------|---------------------------------------------|
| Selezione ELITE                      | +3    | HR 67.3% vs 49.9% non-elite                |
| Confidence 70-80                     | +2    | Picco HR a 63.2%                            |
| Confidence 60-70                     | +1    | HR 58.4%                                    |
| Stelle 4                             | +2    | HR 61.4% (miglior fascia)                   |
| Stelle 3                             | +1    | HR 52.7%                                    |
| Forma squadra favorita 40-60%        | +2    | HR 59.2% (fascia migliore, NON lineare)     |
| Affidabilita squadra favorita > 7.0  | +1    | HR 58.6-62.5% sopra 7                       |
| Mercato GOL                          | +1    | HR 59.0% vs 45.5% SEGNO                     |

MALUS (sottrai dal punteggio base):
| Fattore                              | Malus | Note                                        |
|--------------------------------------|-------|---------------------------------------------|
| Confidence < 50                      | -2    | HR 41.3%                                    |
| Stelle 2                             | -2    | HR 22.2% (pessimo)                          |
| Forma squadra favorita 20-40%        | -1    | HR 45.8%                                    |
| Forma squadra favorita > 80%         | -1    | HR solo 50.0% (sopravvalutata)              |
| Mercato SEGNO                        | -1    | HR 45.5% (il peggiore)                      |

ELITE applica COMUNQUE bonus/malus: il tag ELITE e un vantaggio di partenza, ma non rende immune da difetti.

═══════════════════════════════════════════════════════════════════════════════
PASSO 3 — SOGLIE DECISIONALI PER LE BOLLETTE
═══════════════════════════════════════════════════════════════════════════════

Somma punteggio base (Passo 1) + bonus/malus (Passo 2) = PUNTEGGIO FINALE (tipico: -5 a +15).

- Bollette SELETTIVE / ELITE: accetta solo punteggio finale >= 7
- Bollette BILANCIATE: accetta punteggio finale >= 5
- Bollette AMBIZIOSE: fino a 2 selezioni con punteggio 3-4, purche le altre siano >= 6
- Bollette OGGI: qualsiasi punteggio >= 4, priorita a quelle >= 7

REGOLE DI ESCLUSIONE ASSOLUTA (NON USARE MAI):
- Qualsiasi selezione con RH o RA in zona ASSENTE
- Selezione con C in zona ASSENTE (>70)
- Selezione con Stelle 2 e Confidence < 60
- Selezione con pronostico SEGNO X (pareggio) — vietato

═══════════════════════════════════════════════════════════════════════════════
COMBINAZIONI DI ZONE VINCENTI (da cercare prioritariamente)
═══════════════════════════════════════════════════════════════════════════════

Cerca selezioni con queste "firme" ad alto HR reale:
- RH_DEBOLE (10-30) + RA_OTTIMALE (30-50) + C_OTTIMALE (30-50) = HR 73.3% (la migliore)
- RH_DEBOLE (10-30) + RA_DEBOLE (50-70) + C_DEBOLE (50-70) = HR 61.5%
- RH_OTTIMALE (30-50) + RA_OTTIMALE (30-50) + C_DEBOLE (50-70) = HR 56.0%

Evita SEMPRE combinazioni che includono ASSENTE (es. RH_ASSENTE + RA_OTTIMALE = HR 40.0%).

═══════════════════════════════════════════════════════════════════════════════
ESEMPI DI RAGIONAMENTO (dati reali)
═══════════════════════════════════════════════════════════════════════════════

Esempio A — Selezione TOP (punteggio 15):
  Luton vs Northampton - Over 2.5
  RH=34 (OTTIMALE) +3 | RA=49 (OTTIMALE) +3 | C=56 (DEBOLE_ALTO) +2 = base 8
  ELITE +3 | Confidence 79 (70-80) +2 | Stelle 4 +2 | Forma 84% -1 | Mercato GOL +1
  PUNTEGGIO FINALE = 15. ECCELLENTE per qualsiasi bolletta.

Esempio B — Selezione da EVITARE (punteggio -1):
  Bolton vs Stevenage - SEGNO 1
  RH=42 (OTTIMALE) +3 | RA=71 (ASSENTE) -4 | C=61 (DEBOLE_ALTO) +2 = base 1
  Forma Bolton 32% -1 | Mercato SEGNO -1
  PUNTEGGIO FINALE = -1. SCARTARE (RA ASSENTE).

Esempio C — Selezione buona per bilanciata (punteggio 12):
  Lanus vs Banfield - SEGNO 1
  RH=37 (OTTIMALE) +3 | RA=36 (OTTIMALE) +3 | C=58 (DEBOLE_ALTO) +2 = base 8
  ELITE +3 | Forma 52% (40-60%) +2 | Mercato SEGNO -1
  PUNTEGGIO FINALE = 12. OTTIMA per selettiva/elite.

Nel campo "reasoning" di ogni bolletta, cita sempre RH, RA, C, il punteggio e i dati chiave.
Esempio: "Luton RH=34(OTT) RA=49(OTT) C=56(DEB) punt.15 — ELITE, conf 79, forma 84%, Over supportato da gol casa"

═══════════════════════════════════════════════════════════════════════════════
💰 MENTALITÀ DELLO SCOMMETTITORE — OGNI BOLLETTA VALE 1€
═══════════════════════════════════════════════════════════════════════════════

Immagina di dover investire **1 euro su ogni bolletta che crei** con i tuoi soldi veri.
Il tuo obiettivo NON è indovinare il risultato, ma **far crescere il capitale nel lungo periodo**.

Per farlo, devi rispettare tre principi fondamentali:

1. **PROBABILITÀ > QUOTA**
   Una bolletta con quota 2.00 e probabilità reale del 60% è un AFFARE.
   Una bolletta con quota 10.00 e probabilità reale del 5% è una TRAPPOLA.
   Il sistema ti fornisce il PUNTEGGIO FINALE: usalo come stima della probabilità di successo.
   Più alto è il punteggio, più la selezione ha basi solide. Non lasciarti abbagliare dalle quote alte.

2. **DIVERSIFICAZIONE DEL RISCHIO**
   Non puntare tutto su un unico evento o su una sola tipologia di bolletta.
   Le diverse categorie (oggi, selettiva, bilanciata, ambiziosa, elite) servono proprio a distribuire il rischio.
   Anche la bolletta più sicura può perdere: se perdi 1€ su una selettiva, puoi rifarti con una ambiziosa che paga 8€.

3. **VALORE ATTESO POSITIVO**
   Il valore atteso (EV) di una bolletta si calcola approssimativamente così:
   `(Probabilità di vincita stimata × Quota) - 1`
   Se il risultato è positivo, la bolletta ha senso **economicamente**.
   Se è negativo, stai regalando soldi al bookmaker.

   Esempio pratico:
   - Bolletta A: punteggio finale 10 (prob. stimata ~65%), quota totale 2.50
     EV = (0.65 × 2.50) - 1 = 1.625 - 1 = **+0.625€** per ogni euro giocato. ✅
   - Bolletta B: punteggio finale 3 (prob. stimata ~30%), quota totale 9.00
     EV = (0.30 × 9.00) - 1 = 2.70 - 1 = **+1.70€** → sembra migliore, ma la probabilità è bassissima e la varianza altissima. ⚠️
     Nel lungo periodo, bollette con bassa probabilità e alta quota sono **perdenti** perché la stima di probabilità reale è spesso sovrastimata.

   **Regola pratica:**
   - Per bollette con punteggio ≥ 7, puoi accettare quote anche medio-basse (1.50 - 3.00) perché la probabilità di successo è alta.
   - Per bollette con punteggio tra 4 e 6, cerca quote che giustifichino il rischio (almeno 3.00 - 6.00).
   - Evita bollette con punteggio < 4, a meno che la quota non sia **enorme** (>15.00) e tu abbia una forte convinzione basata su dati anomali (es. squadra B in crisi nera). Ma in generale, **non ne vale la pena**.

═══════════════════════════════════════════════════════════════════════════════
📊 STRATEGIA DI COSTRUZIONE DEL PORTAFOGLIO (3-5 BOLLETTE PER CATEGORIA)
═══════════════════════════════════════════════════════════════════════════════

Immagina di avere a disposizione 15-20€ totali da distribuire su tutte le bollette della giornata.
Ogni categoria ha un ruolo specifico nel tuo portafoglio:

| Categoria   | Obiettivo                          | Quota ideale | Quante bollette | Punteggio minimo |
|-------------|------------------------------------|--------------|-----------------|------------------|
| **OGGI**    | Coprire le spese quotidiane        | 2.00 - 4.00  | 3               | ≥ 5              |
| **SELETTIVA** | Guadagno sicuro e costante        | 1.80 - 3.50  | 3-5             | ≥ 7              |
| **BILANCIATA**| Bilanciare rischio/rendimento      | 5.00 - 7.50  | 3-5             | ≥ 5              |
| **AMBIZIOSA** | Colpo grosso occasionale           | 8.00 - 15.00 | 3-5             | ≥ 4 (max 2 sotto 5)|
| **ELITE**   | Massima affidabilità su pattern storici | 2.50 - 6.00 | 3-5             | ≥ 7 (e tutte ELITE)|

**Regola d'oro del bankroll:**
Se in una giornata hai generato 15 bollette, significa che stai investendo 15€.
L'obiettivo minimo è che **almeno 3-4 bollette vadano a segno**, coprendo l'investimento totale e generando un profitto.

Per massimizzare le probabilità di successo del portafoglio:
- **NON concentrare tutte le bollette sullo stesso campionato o sulle stesse partite.**
  Un imprevisto (es. rinvio, campo pesante, arbitro casalingo) può affondare tutte le bollette insieme.
- **Includi almeno 1-2 bollette con quota totale < 3.00** (tipicamente selettive o oggi).
  Queste fungono da "ancora" per il portafoglio: hanno alta probabilità di vincita e garantiscono un flusso di cassa minimo.
- **Le bollette AMBIZIOSE devono essere la minoranza.**
  Anche se una paga 12€, la probabilità di centrarla è bassa. Non affidare il tuo profitto giornaliero a una sola bolletta rischiosa.

═══════════════════════════════════════════════════════════════════════════════
🧠 COME SCEGLIERE LE SELEZIONI IN OTTICA DI VALORE ATTESO
═══════════════════════════════════════════════════════════════════════════════

Quando selezioni un pronostico da inserire in una bolletta, poniti queste tre domande:

1. **Il punteggio finale è sufficiente per la categoria?** (vedi soglie al Passo 3)
2. **La quota della singola selezione è proporzionata al suo punteggio?**
   - Punteggio ≥ 8: quota anche bassa (1.30 - 1.70) va bene, perché è molto probabile.
   - Punteggio 5-7: cerca quote almeno 1.70 - 2.50.
   - Punteggio < 5: la quota deve essere > 2.50 per giustificare il rischio.
3. **La selezione aggiunge diversificazione al portafoglio?**
   - Evita di usare la stessa partita in più di 2 bollette.
   - Evita di usare lo stesso mercato (es. Over 2.5) per partite dello stesso campionato, perché i risultati potrebbero essere correlati.

**Esempio di scelta basata sul valore:**

   Hai due selezioni candidate per una bolletta BILANCIATA (target quota 5.00-7.50):

   - Selezione X: punteggio 9, quota 1.55
   - Selezione Y: punteggio 6, quota 2.10

   Quale scegli?
   - X ha probabilità molto alta, ma quota bassa. Da sola non ti aiuta a raggiungere la quota target.
   - Y ha probabilità discreta e quota più alta. È più adatta a una bilanciata.

   Se invece stai costruendo una SELETTIVA (target quota < 4.50), X è perfetta perché aumenta la probabilità di successo della bolletta.

═══════════════════════════════════════════════════════════════════════════════
⚠️ ERRORI COMUNI DA EVITARE (CHE TI FANNO PERDERE SOLDI)
═══════════════════════════════════════════════════════════════════════════════

1. **Innamorarsi della quota alta.**
   Una bolletta con quota 15.00 composta da 5 selezioni con punteggio < 4 ha probabilità di successo inferiore al 5%.
   Significa che in media vinci 1 volta su 20. Se giochi 1€ a bolletta, dopo 20 tentativi avrai speso 20€ per vincerne 15. **Sei in perdita.**

2. **Trascurare le correlazioni.**
   Esempio: mettere "Over 2.5" su tre partite che si giocano sotto la pioggia battente.
   Anche se ogni singola selezione ha un buon punteggio, il contesto esterno (meteo, infortuni dell'ultimo minuto) può affondare tutte e tre insieme.
   **Diversifica sempre campionati e contesti.**

3. **Usare troppe selezioni con punteggio borderline nelle bollette conservative.**
   Una bolletta SELETTIVA con 3 selezioni di cui due con punteggio 5 e una con punteggio 8 ha una probabilità reale di successo molto più bassa di quanto sembri.
   **Per le selettive, esigi almeno 2 selezioni su 3 con punteggio ≥ 7.**

4. **Ignorare la motivazione e il contesto partita.**
   Una squadra che lotta per la salvezza contro una che non ha nulla da chiedere può ribaltare ogni pronostico basato sui dati.
   Se vedi "Motivazione: LOTTA SALVEZZA" vs "Motivazione: NEUTRALE", **rivedi il punteggio al ribasso** per la squadra favorita.
   Il sistema potrebbe non aver ancora incorporato questo fattore nel punteggio.

═══════════════════════════════════════════════════════════════════════════════
💡 SINTESI OPERATIVA PER LA COMPOSIZIONE
═══════════════════════════════════════════════════════════════════════════════

Quando componi le bollette per la giornata, segui questa checklist mentale:

✅ Ho generato almeno 3 bollette per ogni categoria richiesta?
✅ Le bollette SELETTIVE hanno almeno il 70% di selezioni con punteggio ≥ 7?
✅ Le bollette AMBIZIOSE hanno quote che giustificano il rischio (≥ 8.00)?
✅ Ho evitato di usare la stessa partita in più di 2 bollette?
✅ Ho diversificato i campionati e i mercati (GOL, SEGNO, DOPPIA_CHANCE)?
✅ Almeno una bolletta ha quota totale < 3.00 per fare da "ancora"?
✅ Ho controllato che nessuna bolletta abbia RH o RA in zona ASSENTE?
✅ Le motivazioni delle squadre coinvolte sono coerenti con il pronostico?

Se la risposta a tutte queste domande è SÌ, hai costruito un portafoglio solido che **nel lungo periodo ha un valore atteso positivo**.

═══════════════════════════════════════
ALTRI DATI STATISTICI — COME LEGGERLI
═══════════════════════════════════════

Classifica: posizione, punti, V-N-P, GF-GS, posizione casa/trasferta separata.
Forma (Lucifero): 0-100%, ultime 6 partite con pesi decrescenti.
Trend: 5 valori cronologici. Freccia su = miglioramento, giu = peggioramento.
Motivazione: LOTTA TITOLO/EUROPA/SALVEZZA = forte. BASSA/NEUTRALE = rischio calo.
Strisce: serie consecutive attive. Strisce molto lunghe NON significano continuazione.
Affidabilita: 0-10, quanto la squadra rispetta i pronostici. >7 = prevedibile.
Attacco/Difesa/Valore rosa: 0-100, utili per confermare pronostici GOL/Under.

═══════════════════════════════════════
FORMATO OUTPUT — JSON ARRAY
═══════════════════════════════════════

Restituisci SOLO un array JSON valido. Nessun testo prima o dopo. Nessun markdown.

[
  {
    "tipo": "oggi",
    "selezioni": [
      { "match_key": "Inter vs Milan|2026-03-16", "mercato": "SEGNO", "pronostico": "1" },
      { "match_key": "Juventus vs Roma|2026-03-16", "mercato": "GOL", "pronostico": "Over 2.5" }
    ],
    "reasoning": "Due big match di oggi con favorite nette"
  },
  {
    "tipo": "selettiva",
    "selezioni": [
      { "match_key": "Arsenal vs Chelsea|2026-03-17", "mercato": "DOPPIA_CHANCE", "pronostico": "1X" },
      { "match_key": "Inter vs Milan|2026-03-16", "mercato": "GOL", "pronostico": "Under 3.5" }
    ],
    "reasoning": "Combinazione sicura con quote basse"
  }
]

IMPORTANTE:
- match_key deve essere ESATTAMENTE come nel pool (formato "Home vs Away|YYYY-MM-DD")
- mercato e pronostico devono corrispondere ESATTAMENTE a quelli nel pool
- Non inventare partite o pronostici che non sono nel pool
- NON usare MAI il SEGNO X (pareggio) nelle bollette — è troppo imprevedibile
"""


def _sanitize_and_parse_json(content):
    """Sanitizza la risposta Mistral e parsa il JSON.
    5 livelli di fallback per gestire risposte corrotte/troncate."""
    content = content.strip()

    # Step 1: Rimuovi markdown wrapping
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

    # Rimuovi caratteri di controllo
    content = re.sub(r'[\x00-\x1f\x7f](?!["\\/bfnrtu])', ' ', content)

    # Step 2: Tentativo diretto
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass

    # Step 3: Estrai array tra primo [ e ultimo ]
    first_bracket = content.find('[')
    last_bracket = content.rfind(']')
    if first_bracket != -1 and last_bracket > first_bracket:
        extracted = content[first_bracket:last_bracket + 1]
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass

    # Step 4: JSON troncato — trova l'ultimo } completo e chiudi l'array
    if first_bracket != -1:
        extracted = content[first_bracket:]
        # Rimuovi trailing comma prima di chiusure
        extracted = re.sub(r',\s*([}\]])', r'\1', extracted)
        # Trova l'ultimo oggetto completo (ultimo })
        last_brace = extracted.rfind('}')
        if last_brace != -1:
            truncated = extracted[:last_brace + 1] + ']'
            try:
                return json.loads(truncated)
            except json.JSONDecodeError:
                pass

    # Step 5: Regex — estrai singoli oggetti JSON
    objects = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content)
    if objects:
        results = []
        for obj_str in objects:
            try:
                obj = json.loads(obj_str)
                if 'selezioni' in obj or 'tipo' in obj:
                    results.append(obj)
            except json.JSONDecodeError:
                continue
        if results:
            logger.warning(f" JSON riparato via regex: {len(results)} bollette estratte")
            return results

    logger.error(f"❌ JSON non parsabile dopo 5 tentativi. Risposta grezza ({len(content)} chars):\n{content[:2000]}")
    raise json.JSONDecodeError("Impossibile parsare JSON dopo 5 tentativi", content, 0)


def build_pool(today_str, skip_time_filter=False):
    """Costruisce il pool di selezioni dai pronostici unified per 3 giorni."""
    today = datetime.strptime(today_str, "%Y-%m-%d")
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]

    pool = []
    docs = list(db.daily_predictions_unified.find(
        {"date": {"$in": dates}},
        {"home": 1, "away": 1, "date": 1, "league": 1, "match_time": 1,
         "home_mongo_id": 1, "away_mongo_id": 1, "pronostici": 1, "odds": 1}
    ).max_time_ms(30000))

    now = datetime.now()

    for doc in docs:
        home = doc.get("home", "")
        away = doc.get("away", "")
        match_date = doc.get("date", "")
        match_time = doc.get("match_time", "00:00")

        # Escludi partite già iniziate (skip per date retroattive)
        if not skip_time_filter:
            try:
                kick_off = datetime.strptime(f"{match_date} {match_time}", "%Y-%m-%d %H:%M")
                if kick_off <= now:
                    continue
            except ValueError:
                pass

        match_key = f"{home} vs {away}|{match_date}"

        for p in doc.get("pronostici", []):
            quota = p.get("quota")
            if not quota or quota <= 1.0:
                continue  # Escludi senza quota valida
            if p.get("tipo") == "RISULTATO_ESATTO":
                continue  # RE escluso dalle bollette

            pool.append({
                "match_key": match_key,
                "home": home,
                "away": away,
                "league": doc.get("league", ""),
                "match_time": doc.get("match_time", ""),
                "match_date": match_date,
                "home_mongo_id": str(doc.get("home_mongo_id", "")),
                "away_mongo_id": str(doc.get("away_mongo_id", "")),
                "mercato": p.get("tipo", ""),
                "pronostico": p.get("pronostico", ""),
                "quota": round(quota, 2),
                "confidence": p.get("confidence", 0),
                "stars": p.get("stars", 0),
                "elite": p.get("elite", False),
                "source": p.get("source", ""),
                "routing_rule": p.get("routing_rule", ""),
                "edge": p.get("edge", 0) or 0,
                "stake": p.get("stake", 0) or 0,
            })

    logger.info(f"📦 Pool base: {len(pool)} selezioni da {len(docs)} partite ({', '.join(dates)})")
    return pool


def recover_from_yesterday(today_str):
    """Recupera selezioni valide da bollette saltate ieri (perse per 1 sola selezione)."""
    today = datetime.strptime(today_str, "%Y-%m-%d")
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    yesterday_bollette = list(db.bollette.find({"date": yesterday_str}).max_time_ms(30000))
    recovered = []

    for b in yesterday_bollette:
        selezioni = b.get("selezioni", [])
        if not selezioni:
            continue

        # Conta selezioni perse (esito == False)
        lost = [s for s in selezioni if s.get("esito") is False]
        if len(lost) != 1:
            continue  # Solo bollette perse per 1 sola selezione

        # Recupera selezioni future non ancora giocate
        for s in selezioni:
            s_date = s.get("match_date", "")
            if s_date >= today_str and s.get("esito") is None:
                recovered.append({
                    "match_key": f"{s['home']} vs {s['away']}|{s_date}",
                    "home": s.get("home", ""),
                    "away": s.get("away", ""),
                    "league": s.get("league", ""),
                    "match_time": s.get("match_time", ""),
                    "match_date": s_date,
                    "home_mongo_id": s.get("home_mongo_id", ""),
                    "away_mongo_id": s.get("away_mongo_id", ""),
                    "mercato": s.get("mercato", ""),
                    "pronostico": s.get("pronostico", ""),
                    "quota": s.get("quota", 0),
                    "confidence": s.get("confidence", 0),
                    "stars": s.get("stars", 0),
                    "_recovered": True,
                })

    if recovered:
        logger.info(f"♻️ Recuperate {len(recovered)} selezioni da bollette saltate ieri")
    return recovered


def deduplicate_pool(pool):
    """Rimuove duplicati: stessa partita + stesso mercato + stesso pronostico."""
    seen = set()
    unique = []
    for s in pool:
        key = (s["match_key"], s["mercato"], s["pronostico"])
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def _norm_name(s):
    """Normalizza nome squadra: rimuove accenti, punteggiatura, lowercase.
    Identica alla funzione norm() del frontend (VistaPrePartita.tsx)."""
    import unicodedata
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')  # rimuove diacritici
    s = s.lower()
    s = re.sub(r'[^a-z0-9]', '', s)
    return s


def _match_team_name(search_name, candidates_dict, tm_id=None):
    """Matching a 4 livelli identico al frontend (VistaPrePartita.tsx matchTeam).
    Cerca search_name tra le chiavi di candidates_dict.
    Livelli: 0) transfermarkt_id, 1) exact, 2) normalized, 3) substring (>3 chars).
    Ritorna il valore del dict se trovato, altrimenti None."""
    # Livello 0: transfermarkt_id (se disponibile)
    if tm_id is not None:
        for key, val in candidates_dict.items():
            if isinstance(val, dict) and str(val.get("transfermarkt_id", "")) == str(tm_id):
                return val
    # Livello 1: match esatto
    if search_name in candidates_dict:
        return candidates_dict[search_name]
    # Livello 2: match normalizzato
    nn = _norm_name(search_name)
    for key, val in candidates_dict.items():
        if _norm_name(key) == nn:
            return val
    # Livello 3: substring (entrambi >3 chars)
    if len(nn) > 3:
        for key, val in candidates_dict.items():
            rn = _norm_name(key)
            if len(rn) > 3 and (rn in nn or nn in rn):
                return val
    return None


def enrich_pool_with_stats(pool):
    """Arricchisce ogni selezione del pool con i 7 dati statistici per Mistral.
    Fonti: h2h_by_round (lucifero, trend, affidabilità, DNA), teams (motivazioni),
    classifiche (classifica), daily_predictions_unified (strisce).
    I dati vengono raggruppati per partita (match_key) per evitare query duplicate."""

    # Raggruppa per partita
    matches = {}
    for s in pool:
        mk = s["match_key"]
        if mk not in matches:
            matches[mk] = {
                "home": s["home"], "away": s["away"],
                "league": s["league"], "match_date": s["match_date"]
            }

    if not matches:
        return

    # --- 1. Classifiche (per campionato) ---
    leagues = set(m["league"] for m in matches.values())
    classifiche_cache = {}  # league -> {team_name: row}
    for league in leagues:
        doc = db.classifiche.find_one({"league": league}, {"table": 1, "table_home": 1, "table_away": 1}, max_time_ms=30000)
        if not doc:
            continue
        league_map = {}
        for row in doc.get("table", []):
            league_map[row["team"]] = {
                "pos": row.get("rank", "?"), "pt": row.get("points", 0),
                "g": row.get("played", 0), "v": row.get("wins", 0),
                "n": row.get("draws", 0), "p": row.get("losses", 0),
                "gf": row.get("goals_for", 0), "gs": row.get("goals_against", 0),
                "transfermarkt_id": row.get("transfermarkt_id"),
            }
        # Aggiungi dati casa/trasferta completi (matching normalizzato)
        norm_to_key = {_norm_name(k): k for k in league_map}
        for row in doc.get("table_home", []):
            rn = _norm_name(row["team"])
            real_key = norm_to_key.get(rn)
            if real_key:
                league_map[real_key]["pos_casa"] = row.get("rank", "?")
                league_map[real_key]["v_casa"] = row.get("wins", 0)
                league_map[real_key]["n_casa"] = row.get("draws", 0)
                league_map[real_key]["p_casa"] = row.get("losses", 0)
                league_map[real_key]["gf_casa"] = row.get("goals_for", 0)
                league_map[real_key]["gs_casa"] = row.get("goals_against", 0)
                league_map[real_key]["g_casa"] = row.get("played", 0)
        for row in doc.get("table_away", []):
            rn = _norm_name(row["team"])
            real_key = norm_to_key.get(rn)
            if real_key:
                league_map[real_key]["pos_trasf"] = row.get("rank", "?")
                league_map[real_key]["v_trasf"] = row.get("wins", 0)
                league_map[real_key]["n_trasf"] = row.get("draws", 0)
                league_map[real_key]["p_trasf"] = row.get("losses", 0)
                league_map[real_key]["gf_trasf"] = row.get("goals_for", 0)
                league_map[real_key]["gs_trasf"] = row.get("goals_against", 0)
                league_map[real_key]["g_trasf"] = row.get("played", 0)
        classifiche_cache[league] = league_map

    # --- 2. Motivazioni (per squadra, da teams) ---
    # Cerco per nome O aliases (come il frontend che usa transfermarkt_id + aliases)
    all_teams = set()
    for m in matches.values():
        all_teams.add(m["home"])
        all_teams.add(m["away"])
    teams_list = list(all_teams)
    teams_docs = list(db.teams.find(
        {"$or": [{"name": {"$in": teams_list}}, {"aliases": {"$in": teams_list}}]},
        {"name": 1, "aliases": 1, "stats.motivation": 1, "stats.motivation_pressure_euro": 1,
         "stats.motivation_pressure_releg": 1, "stats.motivation_pressure_title": 1}
    ).max_time_ms(30000))
    motivazioni_cache = {}  # team_name -> dict (chiave = nome DB + tutti gli aliases)
    for t in teams_docs:
        stats = t.get("stats", {})
        mot = stats.get("motivation")
        if mot is None:
            continue
        label = "NEUTRALE"
        p_title = stats.get("motivation_pressure_title", 0) or 0
        p_euro = stats.get("motivation_pressure_euro", 0) or 0
        p_releg = stats.get("motivation_pressure_releg", 0) or 0
        if p_title > 0.5:
            label = "LOTTA TITOLO"
        elif p_euro > 0.5:
            label = "LOTTA EUROPA"
        elif p_releg > 0.5:
            label = "LOTTA SALVEZZA"
        elif mot < 7:
            label = "BASSA"
        elif mot > 13:
            label = "MOLTO ALTA"
        mot_data = {"score": round(mot, 1), "label": label}
        motivazioni_cache[t["name"]] = mot_data
        # Aggiungi anche gli aliases come chiavi per matching diretto
        for alias in t.get("aliases", []):
            motivazioni_cache[alias] = mot_data

    # --- 3. h2h_by_round (lucifero, trend, affidabilità, DNA) ---
    # Cerco ogni partita nel h2h_by_round
    h2h_cache = {}  # match_key -> dict
    for mk, m in matches.items():
        doc = db.h2h_by_round.find_one(
            {"league": m["league"], "matches": {"$elemMatch": {"home": m["home"], "away": m["away"]}}},
            {"matches.$": 1},
            sort=[("_id", -1)],
            max_time_ms=30000
        )
        if not doc or not doc.get("matches"):
            continue
        match_doc = doc["matches"][0]
        hd = match_doc.get("h2h_data", {})
        data = {}
        # Salva transfermarkt_id per matching classifica (livello 0 frontend)
        data["home_tm_id"] = match_doc.get("home_tm_id")
        data["away_tm_id"] = match_doc.get("away_tm_id")
        # Lucifero
        lh = hd.get("lucifero_home")
        la = hd.get("lucifero_away")
        if lh is not None:
            data["lucifero_home"] = round(lh, 1)
            data["lucifero_home_pct"] = round((lh / 25.0) * 100, 1)
        if la is not None:
            data["lucifero_away"] = round(la, 1)
            data["lucifero_away_pct"] = round((la / 25.0) * 100, 1)
        # Trend
        data["trend_home"] = hd.get("lucifero_trend_home", [])
        data["trend_away"] = hd.get("lucifero_trend_away", [])
        # Affidabilità
        aff = hd.get("affidabilità", {})
        if isinstance(aff, dict):
            ac = aff.get("affidabilità_casa")
            at = aff.get("affidabilità_trasferta")
            if ac is not None:
                data["affidabilita_casa"] = round(ac, 1)
            if at is not None:
                data["affidabilita_trasf"] = round(at, 1)
        # DNA
        dna = hd.get("h2h_dna", {})
        if dna.get("home_dna"):
            data["dna_home"] = {k: round(v, 1) for k, v in dna["home_dna"].items()}
        if dna.get("away_dna"):
            data["dna_away"] = {k: round(v, 1) for k, v in dna["away_dna"].items()}
        h2h_cache[mk] = data

    # --- 4. Strisce (da daily_predictions_unified) ---
    streak_cache = {}  # match_key -> dict
    dates = list(set(m["match_date"] for m in matches.values()))
    unified_docs = list(db.daily_predictions_unified.find(
        {"date": {"$in": dates}},
        {"home": 1, "away": 1, "date": 1, "streak_home": 1, "streak_away": 1}
    ).max_time_ms(30000))
    for doc in unified_docs:
        mk = f"{doc['home']} vs {doc['away']}|{doc['date']}"
        sh = doc.get("streak_home", {})
        sa = doc.get("streak_away", {})
        if sh or sa:
            streak_cache[mk] = {"streak_home": sh, "streak_away": sa}

    # --- Arricchisci ogni selezione del pool ---
    enriched_count = 0
    for s in pool:
        mk = s["match_key"]
        m = matches[mk]

        # Classifica (matching 4 livelli come frontend, con transfermarkt_id)
        cl = classifiche_cache.get(m["league"], {})
        h2h = h2h_cache.get(mk, {})
        s["classifica_home"] = _match_team_name(m["home"], cl, tm_id=h2h.get("home_tm_id"))
        s["classifica_away"] = _match_team_name(m["away"], cl, tm_id=h2h.get("away_tm_id"))

        # Motivazioni (matching fuzzy come frontend)
        s["motivazione_home"] = _match_team_name(m["home"], motivazioni_cache)
        s["motivazione_away"] = _match_team_name(m["away"], motivazioni_cache)

        # h2h_data (lucifero, trend, affidabilità, DNA) — h2h già caricato sopra
        s["lucifero_home_pct"] = h2h.get("lucifero_home_pct")
        s["lucifero_away_pct"] = h2h.get("lucifero_away_pct")
        s["trend_home"] = h2h.get("trend_home", [])
        s["trend_away"] = h2h.get("trend_away", [])
        s["affidabilita_casa"] = h2h.get("affidabilita_casa")
        s["affidabilita_trasf"] = h2h.get("affidabilita_trasf")
        s["dna_home"] = h2h.get("dna_home")
        s["dna_away"] = h2h.get("dna_away")

        # Strisce
        sk = streak_cache.get(mk, {})
        s["streak_home"] = sk.get("streak_home", {})
        s["streak_away"] = sk.get("streak_away", {})

        if h2h or s.get("classifica_home") or sk:
            enriched_count += 1

    logger.info(f"📊 Arricchite {enriched_count}/{len(matches)} partite con dati statistici")
    return classifiche_cache


# ==================== COEFFICIENTE DI SOLIDITÀ ====================

# Curva a campana strisce (stessi valori di run_daily_predictions.py)
STREAK_CURVES = {
    "vittorie":       {1: 0, 2: 1, 3: 2, 4: 3, 5: 0, 6: -1, 7: -2, 8: -3, "9+": -5},
    "sconfitte":      {1: 0, 2: -1, 3: -2, 4: -3, 5: 0, 6: 1, 7: 2, 8: 3, "9+": 5},
    "imbattibilita":  {"1-2": 0, "3-4": 1, "5-6": 2, "7-8": 0, 9: -1, 10: -2, 11: -3, "12+": -5},
    "pareggi":        {1: 0, 2: -1, 3: -1, 4: -2, 5: -3, 6: -2, 7: -1, "8+": -2},
    "senza_vittorie": {"1-2": 0, "3-4": -1, "5-6": -2, "7-8": 0, 9: 1, 10: 2, 11: 3, "12+": 4},
    "over25":         {1: 0, 2: 1, 3: 2, 4: 3, 5: 0, 6: -1, 7: -2, "8+": -4},
    "under25":        {1: 0, 2: 1, 3: 2, 4: 3, 5: 0, 6: -1, 7: -2, "8+": -4},
    "gg":             {1: 0, 2: 1, 3: 2, 4: 3, 5: 0, 6: -1, 7: -2, "8+": -4},
    "clean_sheet":    {1: 0, 2: 1, 3: 2, 4: 3, 5: 0, 6: -1, 7: -2, "8+": -4},
    "senza_segnare":  {1: 0, 2: 1, 3: 2, 4: 3, 5: 0, 6: -1, 7: -2, "8+": -4},
    "gol_subiti":     {1: 0, 2: 1, 3: 2, 4: 3, 5: 0, 6: -1, 7: -2, "8+": -4},
}
STREAK_MARKET_MAP = {
    "SEGNO": ["vittorie", "sconfitte", "imbattibilita", "pareggi", "senza_vittorie"],
    "GOL":   ["over25", "under25", "gg", "clean_sheet", "senza_segnare", "gol_subiti"],
}
STREAK_THEORETICAL = {
    "SEGNO": {"max": 12, "min": -16},
    "GOL":   {"max": 12, "min": -16},
}

# Pesi per mercato (0-10) — 11 componenti
PESI_SEGNO = {
    "linearita": 10, "gf_gs": 5, "forma": 6, "trend": 7,
    "coerenza": 7, "motivazione": 5,
    "affidabilita": 3, "attacco": 4, "difesa": 7, "valore_rosa": 5,
}
PESI_GOL = {
    "linearita": 6.5, "gf_gs": 10, "forma": 6, "trend": 6,
    "coerenza": 7, "motivazione": 5,
    "affidabilita": 6.5, "attacco": 8, "difesa": 5, "valore_rosa": 3,
}


def _linearita_vnp(v, n, p):
    """Calcola il punteggio di linearità V-N-P (0-100) — CONTINUO, non secco.

    Due componenti:
    1. FORMA (0-60): quanto V-N-P sono vicini all'ordine monotono
       - Perfetto decrescente/crescente = 60
       - N minimo (montagna russa) = 0
       - Scala continua in mezzo
    2. GAP (0-40): quanto sono distanti tra loro i tre valori
       - Gap grande = tendenza chiara = prevedibile
       - Gap piccolo (tipo 10-9-8) = tecnicamente monotono ma poco utile

    Risultato: forma + gap = 0-100 continuo.
    """
    if v is None or n is None or p is None:
        return None

    totale = v + n + p
    if totale == 0:
        return 25.0  # nessun dato

    # --- COMPONENTE 1: FORMA (0-60) ---
    val_min = min(v, p)
    val_max = max(v, p)
    range_vp = val_max - val_min

    if range_vp == 0:
        if n == v:
            forma = 15.0
        elif n < v:
            forma = max(0, 15.0 - (v - n) * 2.0)
        else:
            forma = max(0, 20.0 - (n - v) * 1.5)
    else:
        if val_min <= n <= val_max:
            centro = (val_min + val_max) / 2
            dist_dal_centro = abs(n - centro) / range_vp
            forma = 60.0 - dist_dal_centro * 15.0
        elif n < val_min:
            quanto_sotto = (val_min - n) / max(range_vp, 1)
            forma = max(0, 25.0 - quanto_sotto * 30.0)
        else:
            quanto_sopra = (n - val_max) / max(range_vp, 1)
            forma = max(0, 30.0 - quanto_sopra * 25.0)

    # --- COMPONENTE 2: GAP (0-40) ---
    gap_max = max(v, n, p) - min(v, n, p)
    gap_ratio = gap_max / max(totale / 3, 1)
    gap_score = min(40.0, gap_ratio * 20.0)

    return round(forma + gap_score, 1)


def _analisi_gf_gs(squadra_data, tutte_squadre, contesto="totale"):
    """Analisi GF-GS su 3 livelli: vs fascia (±7pt), vs campionato, posizione virtuale.

    Args:
        squadra_data: dict con pt, gf, gs, g (e varianti _casa/_trasf)
        tutte_squadre: dict {team_name: row} — tutta la classifica del campionato
        contesto: "totale", "casa", "trasferta"

    Returns:
        dict con valori per partita e confronti % vs fascia e vs campionato.
    """
    _empty = {"gf_pm": 0, "gs_pm": 0,
              "att_vs_fascia": 0, "def_vs_fascia": 0,
              "att_vs_camp": 0, "def_vs_camp": 0,
              "n_fascia": 0, "outlier": False}

    if contesto == "casa":
        gf_key, gs_key, g_key = "gf_casa", "gs_casa", "g_casa"
    elif contesto == "trasferta":
        gf_key, gs_key, g_key = "gf_trasf", "gs_trasf", "g_trasf"
    else:
        gf_key, gs_key, g_key = "gf", "gs", "g"

    pt = squadra_data.get("pt", 0)
    gf = squadra_data.get(gf_key, 0)
    gs = squadra_data.get(gs_key, 0)
    g = squadra_data.get(g_key, 0)
    if not g or g == 0:
        return _empty

    squadra_gf_pm = gf / g
    squadra_gs_pm = gs / g

    # Raccogli dati fascia (±7pt) e campionato intero
    fascia_gf, fascia_gs = [], []
    camp_gf, camp_gs = [], []
    for _, row in tutte_squadre.items():
        row_gf = row.get(gf_key, 0)
        row_gs = row.get(gs_key, 0)
        row_g = row.get(g_key, 0)
        if not row_g or row_g == 0:
            continue
        rgf = row_gf / row_g
        rgs = row_gs / row_g
        camp_gf.append(rgf)
        camp_gs.append(rgs)
        if abs(row.get("pt", 0) - pt) <= 7:
            fascia_gf.append(rgf)
            fascia_gs.append(rgs)

    if not camp_gf:
        return _empty

    # Media campionato
    media_camp_gf = sum(camp_gf) / len(camp_gf)
    media_camp_gs = sum(camp_gs) / len(camp_gs)

    # Confronto vs campionato (%)
    att_vs_camp = round(((squadra_gf_pm - media_camp_gf) / max(media_camp_gf, 0.3)) * 100, 1)
    def_vs_camp = round(((squadra_gs_pm - media_camp_gs) / max(media_camp_gs, 0.3)) * 100, 1)

    # Posizione virtuale
    n_squadre = len(camp_gf)
    pos_reale = squadra_data.get("pos", n_squadre // 2)
    camp_gf_sorted = sorted(camp_gf, reverse=True)
    camp_gs_sorted = sorted(camp_gs)
    pos_att = 1
    for val in camp_gf_sorted:
        if squadra_gf_pm >= val:
            break
        pos_att += 1
    pos_dif = 1
    for val in camp_gs_sorted:
        if squadra_gs_pm <= val:
            break
        pos_dif += 1
    gap_att = pos_att - pos_reale
    gap_dif = pos_dif - pos_reale

    # Outlier: meno di 3 squadre nella fascia
    if len(fascia_gf) < 3:
        return {
            "gf_pm": round(squadra_gf_pm, 2), "gs_pm": round(squadra_gs_pm, 2),
            "att_vs_fascia": 0, "def_vs_fascia": 0,
            "att_vs_camp": att_vs_camp, "def_vs_camp": def_vs_camp,
            "pos_att": pos_att, "pos_dif": pos_dif,
            "gap_att": gap_att, "gap_dif": gap_dif,
            "n_fascia": len(fascia_gf), "outlier": True,
        }

    # Media fascia
    media_fascia_gf = sum(fascia_gf) / len(fascia_gf)
    media_fascia_gs = sum(fascia_gs) / len(fascia_gs)

    att_vs_fascia = round(((squadra_gf_pm - media_fascia_gf) / max(media_fascia_gf, 0.3)) * 100, 1)
    def_vs_fascia = round(((squadra_gs_pm - media_fascia_gs) / max(media_fascia_gs, 0.3)) * 100, 1)

    return {
        "gf_pm": round(squadra_gf_pm, 2), "gs_pm": round(squadra_gs_pm, 2),
        "att_vs_fascia": att_vs_fascia, "def_vs_fascia": def_vs_fascia,
        "att_vs_camp": att_vs_camp, "def_vs_camp": def_vs_camp,
        "pos_att": pos_att, "pos_dif": pos_dif,
        "gap_att": gap_att, "gap_dif": gap_dif,
        "n_fascia": len(fascia_gf), "outlier": False,
    }


def _trend_score(trend_values):
    """Calcola il gap tra media trend e forma attuale.
    Negativo = sottoperforma (potenziale riscatto), positivo = sovraperforma.
    NOTA: trend_values[0] = più recente (forma attuale), media = trend medio."""
    if not trend_values or len(trend_values) < 2:
        return 0
    media = sum(trend_values) / len(trend_values)
    forma_attuale = trend_values[0]
    return round(media - forma_attuale, 1)


def _curve_lookup(streak_type, n):
    """Lookup nella curva a campana: striscia tipo + lunghezza → bonus/malus."""
    if n <= 0:
        return 0
    curve = STREAK_CURVES.get(streak_type, {})
    if n in curve:
        return curve[n]
    for key, value in curve.items():
        if isinstance(key, str):
            if '+' in key:
                min_val = int(key.replace('+', ''))
                if n >= min_val:
                    return value
            elif '-' in key:
                lo, hi = key.split('-')
                if int(lo) <= n <= int(hi):
                    return value
    return 0


def _streak_normalized(streaks, market):
    """Calcola il valore normalizzato delle strisce per un mercato.
    Returns: -1.0 a +1.0 (positivo = segnale forte nella direzione, negativo = inversione probabile)."""
    applicable = STREAK_MARKET_MAP.get(market, [])
    theoretical = STREAK_THEORETICAL.get(market, {"max": 12, "min": -16})
    raw = sum(_curve_lookup(st, streaks.get(st, 0)) for st in applicable)
    if raw > 0:
        return min(raw / max(theoretical['max'], 1), 1.0)
    elif raw < 0:
        return max(raw / max(abs(theoretical['min']), 1), -1.0)
    return 0


def _get_mercato_type(mercato, pronostico):
    """Determina se il pronostico è di tipo SEGNO o GOL per scegliere i pesi."""
    m = (mercato or "").upper()
    p = (pronostico or "").upper()
    if m in ("SEGNO", "DOPPIA_CHANCE", "DC"):
        return "SEGNO"
    if m == "GOL" or "OVER" in p or "UNDER" in p or p in ("GOAL", "GG", "NO GOAL", "NOGOL", "NG"):
        return "GOL"
    # Multigol e altri mercati gol
    if "MULTIGOL" in m or "MG" in m:
        return "GOL"
    return "SEGNO"  # default


def _dir_verso_pronostico(valore, soglia_pro, soglia_contro, invertito=False):
    """Calcola direzione 0-100: quanto un valore punta verso il pronostico.
    - valore: il dato grezzo della squadra
    - soglia_pro: valore sopra cui supporta il pronostico (100)
    - soglia_contro: valore sotto cui va contro il pronostico (0)
    - invertito: se True, la logica si inverte (basso = pro)
    Ritorna 0-100 dove 50 = neutro, 100 = totalmente a favore, 0 = totalmente contro."""
    if soglia_pro == soglia_contro:
        return 50
    if invertito:
        valore = soglia_pro + soglia_contro - valore
    ratio = (valore - soglia_contro) / (soglia_pro - soglia_contro)
    return max(0, min(100, round(ratio * 100, 1)))


def calculate_solidity_coefficient(pool, classifiche_cache=None):
    """Calcola il Coefficiente di Solidità (0-100) per ogni selezione del pool.

    11 componenti, ognuno produce per OGNI SQUADRA:
      - score (0-100): qualità/forza del dato
      - dir (0-100): quanto quel dato punta verso il pronostico specifico

    I pesi cambiano in base al mercato (SEGNO vs GOL).
    Il contesto (media pesata delle direzioni) è il moltiplicatore finale (0.7-1.3).
    """
    if classifiche_cache is None:
        classifiche_cache = {}
    calculated = 0
    for s in pool:
        ch = s.get("classifica_home")
        ca = s.get("classifica_away")
        mercato = s.get("mercato", "")
        pronostico = s.get("pronostico", "")

        if not ch or not ca:
            s["coeff_qualita_home"] = None
            s["coeff_qualita_away"] = None
            s["coeff_direzione"] = None
            s["rapporto_home"] = None
            s["rapporto_away"] = None
            s["coerenza_rapporti"] = None
            continue

        # Struttura per squadra: {componente: {home: {score, dir}, away: {score, dir}}}
        componenti = {}

        mercato_type = _get_mercato_type(mercato, pronostico)
        PESI = PESI_SEGNO if mercato_type == "SEGNO" else PESI_GOL

        # Determina il "verso" del pronostico per calcolare le direzioni
        pron_up = (pronostico or "").upper()
        mercato_up = (mercato or "").upper()
        # pron_favor: "1" = casa favorita, "2" = ospite favorita, "X" = pareggio,
        #             "OVER"/"GOAL" = tanti gol, "UNDER"/"NOGOL" = pochi gol
        if mercato_up == "SEGNO":
            pron_favor = pron_up  # "1", "2", "X"
        elif mercato_up in ("DOPPIA_CHANCE", "DC"):
            if "1" in pron_up:
                pron_favor = "1X"
            elif "2" in pron_up:
                pron_favor = "X2"
            else:
                pron_favor = "X"
        elif mercato_up == "GOL":
            if pron_up in ("GOAL", "GG"):
                pron_favor = "GOAL"
            elif pron_up in ("NO GOAL", "NOGOL", "NG"):
                pron_favor = "NOGOL"
            elif "OVER" in pron_up:
                pron_favor = "OVER"
            elif "UNDER" in pron_up:
                pron_favor = "UNDER"
            else:
                pron_favor = "GOAL"
        else:
            pron_favor = pron_up

        is_segno = mercato_type == "SEGNO"
        favor_home = pron_favor in ("1", "1X")
        favor_away = pron_favor in ("2", "X2")
        favor_draw = pron_favor in ("X", "1X", "X2")
        favor_over = pron_favor in ("OVER", "GOAL")
        favor_under = pron_favor in ("UNDER", "NOGOL")

        # === 1. LINEARITÀ V-N-P ===
        lin_home_tot = _linearita_vnp(ch.get("v"), ch.get("n"), ch.get("p"))
        lin_away_tot = _linearita_vnp(ca.get("v"), ca.get("n"), ca.get("p"))
        lin_home_ctx = _linearita_vnp(ch.get("v_casa"), ch.get("n_casa"), ch.get("p_casa"))
        lin_away_ctx = _linearita_vnp(ca.get("v_trasf"), ca.get("n_trasf"), ca.get("p_trasf"))

        if lin_home_tot is not None and lin_home_ctx is not None:
            score_h = lin_home_tot * 0.4 + lin_home_ctx * 0.6
        else:
            score_h = lin_home_tot or lin_home_ctx or 50
        if lin_away_tot is not None and lin_away_ctx is not None:
            score_a = lin_away_tot * 0.4 + lin_away_ctx * 0.6
        else:
            score_a = lin_away_tot or lin_away_ctx or 50

        pt_home = ch.get("pt", 0)
        pt_away = ca.get("pt", 0)
        # Direzione: casa alta in classifica → supporta 1, away alta → supporta 2
        if is_segno:
            if favor_home:
                dir_h = min(100, score_h + min(15, max(0, pt_home - pt_away) * 0.8))
                dir_a = min(100, max(0, 100 - score_a - min(15, max(0, pt_away - pt_home) * 0.8)))
            elif favor_away:
                dir_h = max(0, 100 - score_h - min(15, max(0, pt_home - pt_away) * 0.8))
                dir_a = min(100, score_a + min(15, max(0, pt_away - pt_home) * 0.8))
            else:  # pareggio
                # Squadre vicine in classifica → supporta X
                dir_h = max(0, min(100, 100 - abs(pt_home - pt_away) * 3))
                dir_a = dir_h
        else:
            # Per GOL la linearità è meno rilevante per la direzione
            dir_h = 50
            dir_a = 50

        componenti["linearita"] = {
            "home": {"score": round(score_h, 1), "dir": round(dir_h, 1)},
            "away": {"score": round(score_a, 1), "dir": round(dir_a, 1)},
        }

        # === 2. GF-GS ===
        league = s.get("league", "")
        tutte_squadre = classifiche_cache.get(league, {})
        if not tutte_squadre:
            logger.warning(f"⚠️ Classifica mancante per {league}, coefficiente solidità con fallback")

        gfgs_home_ctx = _analisi_gf_gs(ch, tutte_squadre, "casa")
        gfgs_away_ctx = _analisi_gf_gs(ca, tutte_squadre, "trasferta")

        att_h_pm = gfgs_home_ctx["gf_pm"]
        def_h_pm = gfgs_home_ctx["gs_pm"]
        att_a_pm = gfgs_away_ctx["gf_pm"]
        def_a_pm = gfgs_away_ctx["gs_pm"]

        media_camp_gf = sum(r.get("gf", 0) / max(r.get("g", 1), 1) for r in tutte_squadre.values()) / max(len(tutte_squadre), 1) if tutte_squadre else 1.3
        media_camp_gs = sum(r.get("gs", 0) / max(r.get("g", 1), 1) for r in tutte_squadre.values()) / max(len(tutte_squadre), 1) if tutte_squadre else 1.3

        # Score GF-GS: chiarezza dei dati (quanto i numeri sono estremi vs media)
        clarity_h = min(100, (abs(gfgs_home_ctx.get("att_vs_camp", 0)) + abs(gfgs_home_ctx.get("def_vs_camp", 0))) * 0.8)
        clarity_a = min(100, (abs(gfgs_away_ctx.get("att_vs_camp", 0)) + abs(gfgs_away_ctx.get("def_vs_camp", 0))) * 0.8)

        # Direzione GF-GS
        # Rapporto vs media: 1.0 = nella media, >1 = sopra, <1 = sotto
        ratio_att_h = att_h_pm / max(media_camp_gf, 0.3)  # quanto casa segna vs media
        ratio_def_h = def_h_pm / max(media_camp_gs, 0.3)  # quanto casa subisce vs media
        ratio_att_a = att_a_pm / max(media_camp_gf, 0.3)
        ratio_def_a = def_a_pm / max(media_camp_gs, 0.3)
        if is_segno:
            if favor_home:
                # Dir H per "1": casa segna tanto (ratio_att_h alto) → pro
                dir_h_gfgs = min(100, max(0, ratio_att_h * 50))
                # Dir A per "1": ospite debole = segna poco (ratio basso) + subisce tanto (ratio alto) → pro
                dir_a_gfgs = min(100, max(0, (2 - ratio_att_a + ratio_def_a) / 3 * 100))
            elif favor_away:
                dir_h_gfgs = min(100, max(0, (2 - ratio_att_h + ratio_def_h) / 3 * 100))
                dir_a_gfgs = min(100, max(0, ratio_att_a * 50))
            else:
                dir_h_gfgs = 50
                dir_a_gfgs = 50
        else:
            # GOL: tanti gol attesi → OVER/GOAL, pochi → UNDER/NOGOL
            if favor_over:
                # Segna tanto + subisce tanto → Over
                dir_h_gfgs = min(100, max(0, (ratio_att_h + ratio_def_h) / 2 * 50))
                dir_a_gfgs = min(100, max(0, (ratio_att_a + ratio_def_a) / 2 * 50))
            elif favor_under:
                # Segna poco + subisce poco → Under
                dir_h_gfgs = min(100, max(0, (2 - ratio_att_h + (2 - ratio_def_h)) / 4 * 100))
                dir_a_gfgs = min(100, max(0, (2 - ratio_att_a + (2 - ratio_def_a)) / 4 * 100))
            else:
                # Goal/NoGoal generico
                gol_attesi = att_h_pm + att_a_pm
                dir_h_gfgs = min(100, max(0, gol_attesi / (media_camp_gf * 2) * 50))
                dir_a_gfgs = dir_h_gfgs

        componenti["gf_gs"] = {
            "home": {"score": round(clarity_h, 1), "dir": round(dir_h_gfgs, 1)},
            "away": {"score": round(clarity_a, 1), "dir": round(dir_a_gfgs, 1)},
        }

        # Salva analisi GF-GS per _format_match_stats
        s["gfgs_home"] = gfgs_home_ctx
        s["gfgs_away"] = gfgs_away_ctx
        # Tipo partita (per Mistral)
        att_h_forte = att_h_pm > media_camp_gf * 1.1
        att_h_debole = att_h_pm < media_camp_gf * 0.85
        def_a_debole = def_a_pm > media_camp_gs * 1.1
        def_a_forte = def_a_pm < media_camp_gs * 0.85
        att_a_forte = att_a_pm > media_camp_gf * 1.1
        att_a_debole = att_a_pm < media_camp_gf * 0.85
        def_h_debole = def_h_pm > media_camp_gs * 1.1
        def_h_forte = def_h_pm < media_camp_gs * 0.85
        tipo_parts = []
        if att_h_forte and def_a_debole:
            tipo_parts.append("casa segna bene + ospite subisce tanto → gol casa prevedibili")
        elif att_h_forte and def_a_forte:
            tipo_parts.append("casa segna bene MA ospite difende bene → scontro aperto lato casa")
        elif att_h_debole and def_a_debole:
            tipo_parts.append("casa segna poco MA ospite subisce tanto → imprevedibile lato casa")
        if att_a_forte and def_h_debole:
            tipo_parts.append("ospite segna bene + casa subisce tanto → gol ospite prevedibili")
        elif att_a_forte and def_h_forte:
            tipo_parts.append("ospite segna bene MA casa difende bene → scontro aperto lato ospite")
        elif att_a_debole and def_h_debole:
            tipo_parts.append("ospite segna poco MA casa subisce tanto → imprevedibile lato ospite")
        if gfgs_home_ctx.get("outlier") or gfgs_away_ctx.get("outlier"):
            tipo_parts.append("almeno una squadra outlier (campionato a parte)")
        s["tipo_partita"] = " | ".join(tipo_parts) if tipo_parts else "nessun incrocio chiaro"

        # === 3. FORMA ===
        lh = s.get("lucifero_home_pct")
        la = s.get("lucifero_away_pct")
        score_forma_h = lh if lh is not None else 50
        score_forma_a = la if la is not None else 50
        if is_segno:
            if favor_home:
                dir_forma_h = score_forma_h  # casa in forma → supporta 1
                dir_forma_a = max(0, 100 - score_forma_a)  # away in forma → CONTRO 1
            elif favor_away:
                dir_forma_h = max(0, 100 - score_forma_h)
                dir_forma_a = score_forma_a
            else:
                dir_forma_h = max(0, min(100, 100 - abs(score_forma_h - 50) * 2))
                dir_forma_a = max(0, min(100, 100 - abs(score_forma_a - 50) * 2))
        else:
            dir_forma_h = 50
            dir_forma_a = 50

        componenti["forma"] = {
            "home": {"score": round(score_forma_h, 1), "dir": round(dir_forma_h, 1)},
            "away": {"score": round(score_forma_a, 1), "dir": round(dir_forma_a, 1)},
        }

        # === 4. TREND ===
        th = s.get("trend_home", [])
        ta = s.get("trend_away", [])
        trend_h = _trend_score(th)  # gap media-attuale: negativo=sottoperforma, positivo=sovraperforma
        trend_a = _trend_score(ta)
        # Score: 0-100 dove 50=in linea col suo trend, >50=sovraperforma, <50=sottoperforma
        # Gap max realistico ~30 punti → mappa su scala 0-100
        score_trend_h = min(100, max(0, 50 + trend_h * (50 / 30)))
        score_trend_a = min(100, max(0, 50 + trend_a * (50 / 30)))
        # Direzione: gap positivo = sottoperforma = potenziale riscatto
        # Casa sottoperforma (gap+) → riscatto → pro 1
        # Away sottoperforma (gap+) → riscatto → contro 1
        if is_segno:
            if favor_home:
                dir_trend_h = min(100, max(0, 50 + trend_h * (50 / 30)))  # casa sottoperforma → pro 1
                dir_trend_a = min(100, max(0, 50 - trend_a * (50 / 30)))  # away sottoperforma → contro 1
            elif favor_away:
                dir_trend_h = min(100, max(0, 50 - trend_h * (50 / 30)))
                dir_trend_a = min(100, max(0, 50 + trend_a * (50 / 30)))
            else:
                dir_trend_h = max(0, min(100, 100 - abs(trend_h) * (50 / 30)))
                dir_trend_a = max(0, min(100, 100 - abs(trend_a) * (50 / 30)))
        else:
            dir_trend_h = 50
            dir_trend_a = 50

        componenti["trend"] = {
            "home": {"score": round(score_trend_h, 1), "dir": round(dir_trend_h, 1)},
            "away": {"score": round(score_trend_a, 1), "dir": round(dir_trend_a, 1)},
        }

        # === 5. COERENZA FORMA-TREND ===
        # Coerenza = forma attuale - gap. Più è basso, più è coerente.
        if lh is not None and th and len(th) >= 2:
            gap_h = abs(trend_h)  # trend_h = media - forma, già calcolato sopra
            score_coer_h = max(0, round(lh - gap_h, 1))
        else:
            score_coer_h = 50
        if la is not None and ta and len(ta) >= 2:
            gap_a = abs(trend_a)
            score_coer_a = max(0, round(la - gap_a, 1))
        else:
            score_coer_a = 50

        # Direzione: valore basso = più coerente = più prevedibile
        # Squadra favorita coerente (basso) → pro pronostico
        # Squadra avversaria coerente (basso) → contro pronostico
        if is_segno:
            if favor_home:
                dir_coer_h = max(0, 100 - score_coer_h)  # casa coerente (basso) → dir alta → pro 1
                dir_coer_a = score_coer_a                 # away coerente (basso) → dir bassa → contro 1
            elif favor_away:
                dir_coer_h = score_coer_h
                dir_coer_a = max(0, 100 - score_coer_a)
            else:
                dir_coer_h = score_coer_h
                dir_coer_a = score_coer_a
        else:
            dir_coer_h = 50
            dir_coer_a = 50

        componenti["coerenza"] = {
            "home": {"score": round(score_coer_h, 1), "dir": round(dir_coer_h, 1)},
            "away": {"score": round(score_coer_a, 1), "dir": round(dir_coer_a, 1)},
        }

        # === 6. MOTIVAZIONE ===
        mh = s.get("motivazione_home")
        ma = s.get("motivazione_away")
        mot_h = mh.get("score", 5) if mh else 5
        mot_a = ma.get("score", 5) if ma else 5
        # Score: motivazione alta = dato forte (0-10 → 0-100)
        score_mot_h = min(100, mot_h * 10)
        score_mot_a = min(100, mot_a * 10)
        if is_segno:
            if favor_home:
                dir_mot_h = score_mot_h  # casa motivata → pro
                dir_mot_a = max(0, 100 - score_mot_a)  # away motivata → contro
            elif favor_away:
                dir_mot_h = max(0, 100 - score_mot_h)
                dir_mot_a = score_mot_a
            else:
                # Pareggio: motivazioni simili → pro
                dir_mot_h = max(0, min(100, 100 - abs(mot_h - mot_a) * 10))
                dir_mot_a = dir_mot_h
        else:
            dir_mot_h = 50
            dir_mot_a = 50

        componenti["motivazione"] = {
            "home": {"score": round(score_mot_h, 1), "dir": round(dir_mot_h, 1)},
            "away": {"score": round(score_mot_a, 1), "dir": round(dir_mot_a, 1)},
        }

        # === 7. STRISCE (curva a campana) ===
        sh = s.get("streak_home", {})
        sa = s.get("streak_away", {})

        streak_segno_h = _streak_normalized(sh, "SEGNO")
        streak_segno_a = _streak_normalized(sa, "SEGNO")
        streak_gol_h = _streak_normalized(sh, "GOL")
        streak_gol_a = _streak_normalized(sa, "GOL")

        # Score: forza del segnale (0-100)
        if mercato_type == "SEGNO":
            score_str_h = round(abs(streak_segno_h) * 100, 1)
            score_str_a = round(abs(streak_segno_a) * 100, 1)
        else:
            score_str_h = round(abs(streak_gol_h) * 100, 1)
            score_str_a = round(abs(streak_gol_a) * 100, 1)

        # Direzione strisce
        if is_segno:
            if favor_home:
                # Striscia positiva casa → pro, striscia positiva away → contro
                dir_str_h = min(100, max(0, 50 + streak_segno_h * 50))
                dir_str_a = min(100, max(0, 50 - streak_segno_a * 50))
            elif favor_away:
                dir_str_h = min(100, max(0, 50 - streak_segno_h * 50))
                dir_str_a = min(100, max(0, 50 + streak_segno_a * 50))
            else:
                dir_str_h = max(0, min(100, 50 - abs(streak_segno_h) * 30))
                dir_str_a = max(0, min(100, 50 - abs(streak_segno_a) * 30))
        else:
            if favor_over:
                over_h = sh.get("over25", 0)
                gg_h = sh.get("gg", 0)
                over_a = sa.get("over25", 0)
                gg_a = sa.get("gg", 0)
                dir_str_h = min(100, max(0, (over_h + gg_h) * 15))
                dir_str_a = min(100, max(0, (over_a + gg_a) * 15))
            elif favor_under:
                under_h = sh.get("under25", 0)
                cs_h = sh.get("clean_sheet", 0)
                under_a = sa.get("under25", 0)
                cs_a = sa.get("clean_sheet", 0)
                dir_str_h = min(100, max(0, (under_h + cs_h) * 15))
                dir_str_a = min(100, max(0, (under_a + cs_a) * 15))
            else:
                dir_str_h = min(100, max(0, streak_gol_h * 50 + 50))
                dir_str_a = min(100, max(0, streak_gol_a * 50 + 50))

        componenti["strisce"] = {
            "home": {"score": round(score_str_h, 1), "dir": round(dir_str_h, 1)},
            "away": {"score": round(score_str_a, 1), "dir": round(dir_str_a, 1)},
        }

        # === 8. AFFIDABILITÀ ===
        ac = s.get("affidabilita_casa")
        at = s.get("affidabilita_trasf")
        score_aff_h = min(100, ac * 10) if ac is not None else 50
        score_aff_a = min(100, at * 10) if at is not None else 50
        # Affidabilità non ha una direzione forte, ma squadra affidabile → risultato prevedibile
        dir_aff_h = score_aff_h  # alta affidabilità = fidarsi del dato
        dir_aff_a = score_aff_a

        componenti["affidabilita"] = {
            "home": {"score": round(score_aff_h, 1), "dir": round(dir_aff_h, 1)},
            "away": {"score": round(score_aff_a, 1), "dir": round(dir_aff_a, 1)},
        }

        # === 9. ATTACCO ===
        dh = s.get("dna_home")
        da = s.get("dna_away")
        att_dna_h = dh.get("att", 50) if dh else 50
        att_dna_a = da.get("att", 50) if da else 50

        if is_segno:
            if favor_home:
                dir_att_h = att_dna_h  # attacco casa forte → pro
                dir_att_a = max(0, 100 - att_dna_a)  # attacco away forte → contro
            elif favor_away:
                dir_att_h = max(0, 100 - att_dna_h)
                dir_att_a = att_dna_a
            else:
                dir_att_h = max(0, min(100, 100 - abs(att_dna_h - att_dna_a) * 2))
                dir_att_a = dir_att_h
        else:
            if favor_over:
                dir_att_h = att_dna_h  # attacco forte → gol → pro over
                dir_att_a = att_dna_a
            elif favor_under:
                dir_att_h = max(0, 100 - att_dna_h)
                dir_att_a = max(0, 100 - att_dna_a)
            else:
                dir_att_h = att_dna_h
                dir_att_a = att_dna_a

        componenti["attacco"] = {
            "home": {"score": round(att_dna_h, 1), "dir": round(dir_att_h, 1)},
            "away": {"score": round(att_dna_a, 1), "dir": round(dir_att_a, 1)},
        }

        # === 10. DIFESA ===
        def_dna_h = dh.get("def", 50) if dh else 50
        def_dna_a = da.get("def", 50) if da else 50

        if is_segno:
            if favor_home:
                dir_def_h = def_dna_h  # difesa casa forte → pro (non subisce)
                dir_def_a = max(0, 100 - def_dna_a)  # difesa away forte → contro
            elif favor_away:
                dir_def_h = max(0, 100 - def_dna_h)
                dir_def_a = def_dna_a
            else:
                dir_def_h = max(0, min(100, 100 - abs(def_dna_h - def_dna_a) * 2))
                dir_def_a = dir_def_h
        else:
            if favor_over:
                dir_def_h = max(0, 100 - def_dna_h)  # difesa debole → gol → pro over
                dir_def_a = max(0, 100 - def_dna_a)
            elif favor_under:
                dir_def_h = def_dna_h  # difesa forte → pochi gol → pro under
                dir_def_a = def_dna_a
            else:
                dir_def_h = 50
                dir_def_a = 50

        componenti["difesa"] = {
            "home": {"score": round(def_dna_h, 1), "dir": round(dir_def_h, 1)},
            "away": {"score": round(def_dna_a, 1), "dir": round(dir_def_a, 1)},
        }

        # === 11. VALORE ROSA ===
        val_dna_h = dh.get("val", 50) if dh else 50
        val_dna_a = da.get("val", 50) if da else 50

        if is_segno:
            if favor_home:
                dir_val_h = val_dna_h
                dir_val_a = max(0, 100 - val_dna_a)
            elif favor_away:
                dir_val_h = max(0, 100 - val_dna_h)
                dir_val_a = val_dna_a
            else:
                dir_val_h = max(0, min(100, 100 - abs(val_dna_h - val_dna_a) * 2))
                dir_val_a = dir_val_h
        else:
            dir_val_h = 50
            dir_val_a = 50

        componenti["valore_rosa"] = {
            "home": {"score": round(val_dna_h, 1), "dir": round(dir_val_h, 1)},
            "away": {"score": round(val_dna_a, 1), "dir": round(dir_val_a, 1)},
        }

        # === CALCOLO FINALE: Q separato per squadra + D unico + rapporti ===
        peso_strisce_val = 5

        # 1. QUALITÀ HOME: media pesata degli score home
        somma_qh = 0
        somma_qa = 0
        somma_pesi_max = 0
        for comp_name in PESI:
            peso = PESI[comp_name]
            c = componenti.get(comp_name, {"home": {"score": 50}, "away": {"score": 50}})
            somma_qh += c["home"]["score"] * peso
            somma_qa += c["away"]["score"] * peso
            somma_pesi_max += 100 * peso
        c_str = componenti.get("strisce", {"home": {"score": 50}, "away": {"score": 50}})
        somma_qh += c_str["home"]["score"] * peso_strisce_val
        somma_qa += c_str["away"]["score"] * peso_strisce_val
        somma_pesi_max += 100 * peso_strisce_val
        q_home = (somma_qh / somma_pesi_max) * 100 if somma_pesi_max > 0 else 50
        q_away = (somma_qa / somma_pesi_max) * 100 if somma_pesi_max > 0 else 50

        # 2. DIREZIONE: media pesata delle direzioni (unico)
        somma_dir = 0
        dir_pesi_tot = 0
        for comp_name in PESI:
            peso = PESI[comp_name]
            c = componenti.get(comp_name, {"home": {"dir": 50}, "away": {"dir": 50}})
            avg_dir = (c["home"]["dir"] + c["away"]["dir"]) / 2
            somma_dir += avg_dir * peso
            dir_pesi_tot += peso
        c_str = componenti.get("strisce", {"home": {"dir": 50}, "away": {"dir": 50}})
        somma_dir += ((c_str["home"]["dir"] + c_str["away"]["dir"]) / 2) * peso_strisce_val
        dir_pesi_tot += peso_strisce_val
        coeff_direzione = (somma_dir / dir_pesi_tot) if dir_pesi_tot > 0 else 50

        # 3. RAPPORTI: quanto la direzione supporta la forza di ogni squadra
        # Normalizzati 0-100 (range reale ~60-200)
        rh_raw = coeff_direzione / max(q_home, 1) * 100
        ra_raw = coeff_direzione / max(q_away, 1) * 100
        rapporto_home = round(min(100, max(0, (rh_raw - 60) / 140 * 100)), 1)
        rapporto_away = round(min(100, max(0, (ra_raw - 60) / 140 * 100)), 1)

        # 4. COERENZA: combinazione scostamento dal centro + distanza tra i due
        # Scostamento dal centro (50): sotto 50 = negativo, sopra 50 = positivo
        scost_h = rapporto_home - 50
        scost_a = rapporto_away - 50
        scost_totale = scost_h + scost_a  # positivo se entrambi sopra, negativo se entrambi sotto
        distanza = abs(rapporto_home - rapporto_away)
        # Sopra 50: scostamento si sottrae (migliora). Sotto 50: si somma (peggiora)
        penalita = distanza - scost_totale
        # Range: -100 (migliore) a +200 (peggiore). Normalizzo 0-100
        coerenza = round(100 - (penalita + 100) / 300 * 100, 1)

        s["coeff_qualita_home"] = round(q_home, 1)
        s["coeff_qualita_away"] = round(q_away, 1)
        s["coeff_direzione"] = round(coeff_direzione, 1)
        s["rapporto_home"] = rapporto_home
        s["rapporto_away"] = rapporto_away
        s["coerenza_rapporti"] = coerenza
        s["coeff_componenti"] = componenti
        s["coeff_contesto"] = {
            "mercato_type": mercato_type,
            "pronostico": pron_favor,
        }
        calculated += 1

    logger.info(f"🔢 Coefficiente Solidità calcolato per {calculated}/{len(pool)} selezioni")


def calculate_final_score(pool):
    """Calcola il punteggio finale (Passo 1 + Passo 2) per ogni selezione.
    Calibrato su 671 partite reali. Il punteggio viene salvato in sel['punteggio_finale']."""

    def _zona_rh(v):
        if v < 10 or v > 70: return "ASSENTE"
        if v <= 30: return "DEBOLE_BASSO"
        if v <= 50: return "OTTIMALE"
        return "DEBOLE_ALTO"

    def _zona_ra(v):
        if v < 10 or v > 70: return "ASSENTE"
        if v <= 30: return "DEBOLE_BASSO"
        if v <= 50: return "OTTIMALE"
        return "DEBOLE_ALTO"

    def _zona_c(v):
        if v > 70: return "ASSENTE"
        if v <= 50: return "OTTIMALE"
        return "DEBOLE_ALTO"

    calculated = 0
    for sel in pool:
        rh = sel.get("rapporto_home")
        ra = sel.get("rapporto_away")
        c = sel.get("coerenza_rapporti")

        if rh is None or ra is None or c is None:
            sel["punteggio_finale"] = None
            continue

        # --- PASSO 1: punteggio base da zone RH, RA, C ---
        score = 0
        zrh = _zona_rh(rh)
        if zrh == "DEBOLE_BASSO": score += 4
        elif zrh == "OTTIMALE": score += 3
        elif zrh == "DEBOLE_ALTO": score -= 1
        elif zrh == "ASSENTE": score -= 4

        zra = _zona_ra(ra)
        if zra == "DEBOLE_ALTO": score += 4
        elif zra == "OTTIMALE": score += 3
        elif zra == "DEBOLE_BASSO": score += 1
        elif zra == "ASSENTE": score -= 4

        zc = _zona_c(c)
        if zc == "DEBOLE_ALTO": score += 2
        elif zc == "OTTIMALE": score += 1
        elif zc == "ASSENTE": score -= 3

        # --- PASSO 2: bonus/malus da altri dati ---
        # Elite
        if sel.get("elite"):
            score += 3

        # Confidence
        conf = sel.get("confidence", 0) or 0
        if 70 <= conf <= 80: score += 2
        elif 60 <= conf < 70: score += 1
        elif conf < 50: score -= 2

        # Stelle
        stars = sel.get("stars", 0) or 0
        if stars == 4: score += 2
        elif stars == 3: score += 1
        elif stars == 2: score -= 2

        # Forma e affidabilità squadra chiave (dipende da mercato/pronostico)
        mercato = sel.get("mercato", "")
        pronostico = sel.get("pronostico", "")
        forma_home = sel.get("lucifero_home_pct") or 50
        forma_away = sel.get("lucifero_away_pct") or 50
        aff_home = sel.get("affidabilita_casa") or 5
        aff_away = sel.get("affidabilita_trasf") or 5

        if mercato == "GOL":
            # Per mercati GOL: media delle due forme (entrambe contano)
            forma = (forma_home + forma_away) / 2
            aff = (aff_home + aff_away) / 2
        elif mercato == "SEGNO":
            if pronostico in ("1", "1X"):
                forma, aff = forma_home, aff_home
            elif pronostico in ("2", "X2"):
                forma, aff = forma_away, aff_away
            else:  # X
                forma = (forma_home + forma_away) / 2
                aff = (aff_home + aff_away) / 2
        elif mercato == "DOPPIA_CHANCE":
            if pronostico in ("1X", "1"):
                forma, aff = forma_home, aff_home
            elif pronostico in ("X2", "2"):
                forma, aff = forma_away, aff_away
            else:  # 12
                forma = max(forma_home, forma_away)
                aff = max(aff_home, aff_away)
        else:
            forma = (forma_home + forma_away) / 2
            aff = (aff_home + aff_away) / 2

        if 40 <= forma <= 60: score += 2
        elif 20 <= forma < 40: score -= 1
        elif forma > 80: score -= 1

        # Affidabilità
        if aff > 7: score += 1

        # Mercato
        if mercato == "GOL": score += 1
        elif mercato == "SEGNO": score -= 1

        # Esclusione assoluta: zona ASSENTE su RH, RA o C
        if zrh == "ASSENTE" or zra == "ASSENTE" or zc == "ASSENTE":
            score = -999

        sel["punteggio_finale"] = score
        calculated += 1

    # Filtra selezioni tossiche dal pool (zona ASSENTE)
    before = len(pool)
    pool[:] = [s for s in pool if s.get("punteggio_finale") != -999]
    if before - len(pool) > 0:
        logger.info(f"🚫 Escluse {before - len(pool)} selezioni con zona ASSENTE")

    logger.info(f"📊 Punteggio finale calcolato per {calculated}/{len(pool)} selezioni")


def _format_match_stats(s):
    """Formatta i dati statistici di una selezione per il prompt Mistral."""
    parts = []

    # Rapporti + Coerenza + Punteggio finale
    rh = s.get("rapporto_home")
    ra = s.get("rapporto_away")
    coer = s.get("coerenza_rapporti")
    if rh is not None:
        def _zona(v):
            if v >= 70: return "ASSENTE"
            if v >= 50: return "DEBOLE"
            if v >= 30: return "OTTIMALE"
            if v >= 10: return "DEBOLE"
            return "ASSENTE"
        punt = s.get("punteggio_finale")
        punt_tag = f" | PUNTEGGIO={punt}" if punt is not None else ""
        parts.append(
            f"    RH={rh:.0f}({_zona(rh)}) RA={ra:.0f}({_zona(ra)}) C={coer:.0f}({_zona(coer)}) | QH={s.get('coeff_qualita_home',0):.0f} QA={s.get('coeff_qualita_away',0):.0f} D={s.get('coeff_direzione',0):.0f}{punt_tag}"
        )

    # Classifica totale
    ch = s.get("classifica_home")
    ca = s.get("classifica_away")
    if ch and ca:
        parts.append(
            f"    Classifica: {s['home']} {ch['pos']}o ({ch['pt']}pt, {ch['v']}V-{ch['n']}N-{ch['p']}P, "
            f"GF:{ch['gf']} GS:{ch['gs']}) "
            f"vs {s['away']} {ca['pos']}o ({ca['pt']}pt, {ca['v']}V-{ca['n']}N-{ca['p']}P, "
            f"GF:{ca['gf']} GS:{ca['gs']})"
        )
        casa_parts = []
        if ch.get("v_casa") is not None:
            casa_parts.append(
                f"{s['home']}(casa {ch.get('pos_casa','?')}o): "
                f"{ch['v_casa']}V-{ch['n_casa']}N-{ch['p_casa']}P GF:{ch['gf_casa']} GS:{ch['gs_casa']}"
            )
        if ca.get("v_trasf") is not None:
            casa_parts.append(
                f"{s['away']}(trasf {ca.get('pos_trasf','?')}o): "
                f"{ca['v_trasf']}V-{ca['n_trasf']}N-{ca['p_trasf']}P GF:{ca['gf_trasf']} GS:{ca['gs_trasf']}"
            )
        if casa_parts:
            parts.append(f"    Casa/Trasf: {' vs '.join(casa_parts)}")

    # Analisi GF-GS
    gh = s.get("gfgs_home")
    ga = s.get("gfgs_away")
    if gh and ga:
        gh_gap_att = f"{gh['gap_att']:+d}" if 'gap_att' in gh else "?"
        gh_gap_dif = f"{gh['gap_dif']:+d}" if 'gap_dif' in gh else "?"
        ga_gap_att = f"{ga['gap_att']:+d}" if 'gap_att' in ga else "?"
        ga_gap_dif = f"{ga['gap_dif']:+d}" if 'gap_dif' in ga else "?"
        parts.append(
            f"    GF-GS casa: {s['home']} {gh['gf_pm']}gf/g {gh['gs_pm']}gs/g "
            f"(vs fascia: att {gh['att_vs_fascia']:+.0f}% dif {gh['def_vs_fascia']:+.0f}%, "
            f"vs camp: att {gh['att_vs_camp']:+.0f}% dif {gh['def_vs_camp']:+.0f}%, "
            f"pos att:{gh.get('pos_att','?')}o dif:{gh.get('pos_dif','?')}o gap att:{gh_gap_att} dif:{gh_gap_dif})"
            f"{' [OUTLIER]' if gh.get('outlier') else ''}"
        )
        parts.append(
            f"    GF-GS trasf: {s['away']} {ga['gf_pm']}gf/g {ga['gs_pm']}gs/g "
            f"(vs fascia: att {ga['att_vs_fascia']:+.0f}% dif {ga['def_vs_fascia']:+.0f}%, "
            f"vs camp: att {ga['att_vs_camp']:+.0f}% dif {ga['def_vs_camp']:+.0f}%, "
            f"pos att:{ga.get('pos_att','?')}o dif:{ga.get('pos_dif','?')}o gap att:{ga_gap_att} dif:{ga_gap_dif})"
            f"{' [OUTLIER]' if ga.get('outlier') else ''}"
        )
    tp = s.get("tipo_partita")
    if tp:
        parts.append(f"    Tipo partita: {tp}")

    # Forma
    lh = s.get("lucifero_home_pct")
    la = s.get("lucifero_away_pct")
    if lh is not None and la is not None:
        parts.append(f"    Forma: {s['home']} {lh}% | {s['away']} {la}%")

    # Trend
    th = s.get("trend_home", [])
    ta = s.get("trend_away", [])
    if th and ta:
        th_str = "->".join(f"{v:.0f}" for v in th)
        ta_str = "->".join(f"{v:.0f}" for v in ta)
        th_dir = "+" if len(th) >= 2 and th[-1] > th[0] else "-" if len(th) >= 2 and th[-1] < th[0] else "="
        ta_dir = "+" if len(ta) >= 2 and ta[-1] > ta[0] else "-" if len(ta) >= 2 and ta[-1] < ta[0] else "="
        parts.append(f"    Trend: {s['home']} [{th_str}]{th_dir} | {s['away']} [{ta_str}]{ta_dir}")

    # Motivazione
    mh = s.get("motivazione_home")
    ma = s.get("motivazione_away")
    if mh and ma:
        parts.append(f"    Motivazione: {s['home']} {mh['label']} ({mh['score']}) | {s['away']} {ma['label']} ({ma['score']})")

    # Strisce
    sh = s.get("streak_home", {})
    sa = s.get("streak_away", {})
    if sh or sa:
        streak_parts = []
        for team, sk in [(s["home"], sh), (s["away"], sa)]:
            notable = []
            if sk.get("vittorie", 0) >= 2:
                notable.append(f"{sk['vittorie']}V consecutive")
            if sk.get("sconfitte", 0) >= 2:
                notable.append(f"{sk['sconfitte']}S consecutive")
            if sk.get("imbattibilita", 0) >= 3:
                notable.append(f"{sk['imbattibilita']} imbattute")
            if sk.get("over25", 0) >= 3:
                notable.append(f"{sk['over25']}xOver2.5")
            if sk.get("under25", 0) >= 3:
                notable.append(f"{sk['under25']}xUnder2.5")
            if sk.get("gg", 0) >= 3:
                notable.append(f"{sk['gg']}xGG")
            if sk.get("clean_sheet", 0) >= 2:
                notable.append(f"{sk['clean_sheet']}xCS")
            if sk.get("senza_segnare", 0) >= 2:
                notable.append(f"{sk['senza_segnare']}x senza gol")
            if notable:
                streak_parts.append(f"{team}: {', '.join(notable)}")
        if streak_parts:
            parts.append(f"    Strisce: {' | '.join(streak_parts)}")

    # Affidabilita
    ac = s.get("affidabilita_casa")
    at = s.get("affidabilita_trasf")
    if ac is not None and at is not None:
        parts.append(f"    Affidabilita: {s['home']}(casa) {ac}/10 | {s['away']}(trasf) {at}/10")

    # Attacco, Difesa, Valore rosa (separati, senza Tecnica)
    dh = s.get("dna_home")
    da = s.get("dna_away")
    if dh and da:
        parts.append(f"    Attacco: {s['home']} {dh.get('att',0)}/100 | {s['away']} {da.get('att',0)}/100")
        parts.append(f"    Difesa: {s['home']} {dh.get('def',0)}/100 | {s['away']} {da.get('def',0)}/100")
        parts.append(f"    Valore rosa: {s['home']} {dh.get('val',0)}/100 | {s['away']} {da.get('val',0)}/100")

    return "\n".join(parts)


def serialize_pool_for_prompt(pool):
    """Serializza il pool in formato compatto per il prompt Mistral.
    Pool elite separato dal pool completo per chiarezza.
    Include dati statistici per ogni partita (classifica, forma, trend, ecc.)."""

    elite_pool = [s for s in pool if s.get("elite")]
    lines = []

    # Raggruppa per partita per mostrare stats una sola volta
    def _render_pool(pool_subset, show_elite_tag=False):
        by_date = {}
        for s in pool_subset:
            by_date.setdefault(s["match_date"], []).append(s)

        # Raggruppa selezioni per partita per evitare stats ripetute
        for date in sorted(by_date.keys()):
            lines.append(f"\n=== {date} ===")
            by_match = {}
            for s in by_date[date]:
                by_match.setdefault(s["match_key"], []).append(s)

            for mk, sels in by_match.items():
                # Selezioni della partita
                for s in sels:
                    elite_tag = " ★ELITE" if show_elite_tag and s.get("elite") else ""
                    rh = s.get("rapporto_home")
                    ra = s.get("rapporto_away")
                    coer = s.get("coerenza_rapporti")
                    coeff_tag = f" | RH={rh} RA={ra} C={coer}" if rh is not None else ""
                    punt = s.get("punteggio_finale")
                    if s.get("_extra_pool"):
                        punt_tag = " | EXTRA (no score — fuori dal sistema AI)"
                    else:
                        punt_tag = f" | SCORE={punt}" if punt is not None else ""
                    lines.append(
                        f"  {s['match_key']} | {s['mercato']}: {s['pronostico']} "
                        f"@ {s['quota']} | conf={s['confidence']} ★{s['stars']}{elite_tag}{coeff_tag}{punt_tag}"
                    )
                # Stats della partita (una volta sola)
                stats_text = _format_match_stats(sels[0])
                if stats_text:
                    lines.append(stats_text)

    # Pool elite separato
    if elite_pool:
        lines.append("\n╔══════════════════════════════════════╗")
        lines.append("║  POOL ELITE — usa SOLO queste per    ║")
        lines.append("║  bollette di tipo \"elite\"             ║")
        lines.append("╚══════════════════════════════════════╝")
        _render_pool(elite_pool, show_elite_tag=True)
        lines.append(f"\n  Totale selezioni elite: {len(elite_pool)}")
    else:
        lines.append("\n⚠️ Nessuna selezione elite disponibile — NON generare bollette elite")

    # Pool completo
    lines.append("\n╔══════════════════════════════════════╗")
    lines.append("║  POOL COMPLETO — per bollette oggi,  ║")
    lines.append("║  selettiva, bilanciata, ambiziosa     ║")
    lines.append("╚══════════════════════════════════════╝")
    _render_pool(pool, show_elite_tag=True)

    return "\n".join(lines)


def _call_llm(messages, provider_url=None, provider_model=None, provider_key=None):
    """Chiamata LLM generica con fallback automatico DeepSeek → Mistral."""
    url = provider_url or LLM_URL
    model = provider_model or LLM_MODEL
    api_key = provider_key or LLM_API_KEY

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 16000,
        "response_format": {"type": "json_object"},
    }

    max_retries = 2
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=180)
            if resp.status_code == 429 and attempt < max_retries:
                wait = 15 * attempt
                logger.info(f"⏳ Rate limit 429, retry {attempt}/{max_retries} tra {wait}s...")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            # DeepSeek R1 restituisce ragionamento in <think>...</think> — rimuovilo
            if "<think>" in content:
                import re
                content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            return content
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f" Errore LLM (attempt {attempt}): {e}")
                time.sleep(10)
                continue
            raise

    raise Exception("LLM: tutti i tentativi falliti")


def _save_debug_prompt(messages, label="llm_call"):
    """Salva prompt e messaggi su file per debug."""
    if not DEBUG_MODE:
        return
    debug_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "log")
    os.makedirs(debug_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_file = os.path.join(debug_dir, f"debug_bollette_{label}_{ts}.json")
    try:
        with open(debug_file, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
        logger.debug(f"🐛 Prompt salvato: {debug_file}")
    except Exception as e:
        logger.warning(f"⚠️ Errore salvataggio debug: {e}")


def _call_llm_with_fallback(messages):
    """Chiama LLM primario, se fallisce usa fallback Mistral."""
    _save_debug_prompt(messages, "primary")
    try:
        return _call_llm(messages)
    except Exception as e:
        # Fallback su Mistral solo se il primario è OpenRouter
        if LLM_URL == OPENROUTER_URL and MISTRAL_API_KEY:
            logger.warning(f" DeepSeek fallito ({e}), fallback su Mistral...")
            return _call_llm(messages, MISTRAL_URL, MISTRAL_MODEL, MISTRAL_API_KEY)
        raise


def call_mistral(pool_text, today_str):
    """Chiama LLM per generare le bollette."""
    prompt = SYSTEM_PROMPT.replace("{max_bollette}", str(MAX_BOLLETTE)).replace("{today_date}", today_str)

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Ecco il pool di selezioni disponibili:\n{pool_text}\n\nComponi le bollette."},
    ]

    content = _call_llm_with_fallback(messages)
    return _sanitize_and_parse_json(content)


def _classify_tipo(raw_tipo, selezioni, quota_totale, pool_index, today_str):
    """Determina il tipo della bolletta con validazione vincoli."""
    solo_oggi = all(s["match_date"] == today_str for s in selezioni)
    n_sel = len(selezioni)

    if raw_tipo == "elite":
        elite_count = sum(1 for s in selezioni if pool_index.get(
            (f"{s['home']} vs {s['away']}|{s['match_date']}", s['mercato'], s['pronostico']),
            {}
        ).get("elite", False))
        if elite_count == n_sel:
            return "elite"
        logger.warning(f" Bolletta elite con solo {elite_count}/{n_sel} elite (servono 100%) — riclassificata")

    if raw_tipo == "oggi" and solo_oggi:
        return "oggi"

    # Rispetta il tipo raw se è una fascia valida
    if raw_tipo in ("selettiva", "bilanciata", "ambiziosa"):
        return raw_tipo

    # Fallback: classifica per quota totale (per bollette senza tipo o tipo non riconosciuto)
    for t in ["selettiva", "bilanciata", "ambiziosa"]:
        c = CATEGORY_CONSTRAINTS[t]
        lo = c["min_quota"] or 0
        hi = c["max_quota"] or 9999
        if lo <= quota_totale <= hi:
            return t

    return "ambiziosa"



def validate_with_errors(raw_bollette, pool, today_str, existing_counters=None, existing_docs=None):
    """Valida le bollette e raccoglie errori strutturati per feedback a Mistral.
    existing_docs: bollette già accettate (per check duplicati cross-retry).
    Returns: (valid_docs, errors, counters)
    """
    pool_index = {}
    for s in pool:
        key = (s["match_key"], s["mercato"], s["pronostico"])
        pool_index[key] = s

    # existing_docs serve solo per il check duplicati cross-retry
    _all_accepted = list(existing_docs) if existing_docs else []
    valid_docs = []
    errors = []
    counters = dict(existing_counters) if existing_counters else {
        "oggi": 0, "elite": 0, "selettiva": 0, "bilanciata": 0, "ambiziosa": 0
    }

    for i, raw in enumerate(raw_bollette):
        selezioni_raw = raw.get("selezioni", [])
        raw_tipo = raw.get("tipo", "").lower().strip()

        # --- #15: struttura minima ---
        if not isinstance(selezioni_raw, list) or len(selezioni_raw) < 2:
            errors.append({
                "code": "JSON_MALFORMATO",
                "bolletta_idx": i, "tipo": raw_tipo,
                "feedback": f"Bolletta #{i+1} ({raw_tipo}): meno di 2 selezioni o formato invalido"
            })
            continue

        # --- #13: SEGNO X vietato ---
        segno_x_found = False
        for sel in selezioni_raw:
            if sel.get("mercato") == "SEGNO" and sel.get("pronostico") == "X":
                errors.append({
                    "code": "SEGNO_X_VIETATO",
                    "bolletta_idx": i, "tipo": raw_tipo,
                    "feedback": f"Bolletta #{i+1} ({raw_tipo}): hai usato SEGNO X per "
                               f"{sel.get('match_key', '?')}. Il pareggio e' vietato. "
                               f"Sostituisci con DOPPIA_CHANCE o GOL"
                })
                segno_x_found = True
                break
        if segno_x_found:
            continue

        # --- Risolvi selezioni dal pool ---
        selezioni = []
        resolve_ok = True
        quota_totale = 1.0

        for sel in selezioni_raw:
            key = (sel.get("match_key", ""), sel.get("mercato", ""), sel.get("pronostico", ""))
            pool_entry = pool_index.get(key)
            if not pool_entry:
                # --- #1: selezione non trovata ---
                errors.append({
                    "code": "SELEZIONE_NON_TROVATA",
                    "bolletta_idx": i, "tipo": raw_tipo,
                    "feedback": f"Bolletta #{i+1} ({raw_tipo}): selezione {key[0]} "
                               f"({key[1]}: {key[2]}) non esiste nel pool"
                })
                resolve_ok = False
                break

            quota_totale *= pool_entry["quota"]
            selezioni.append({
                "home": pool_entry["home"],
                "away": pool_entry["away"],
                "league": pool_entry["league"],
                "match_time": pool_entry["match_time"],
                "match_date": pool_entry["match_date"],
                "home_mongo_id": pool_entry["home_mongo_id"],
                "away_mongo_id": pool_entry["away_mongo_id"],
                "mercato": pool_entry["mercato"],
                "pronostico": pool_entry["pronostico"],
                "quota": pool_entry["quota"],
                "confidence": pool_entry["confidence"],
                "stars": pool_entry["stars"],
                "source": pool_entry.get("source", ""),
                "routing_rule": pool_entry.get("routing_rule", ""),
                "edge": pool_entry.get("edge", 0),
                "stake": pool_entry.get("stake", 0),
                "elite": pool_entry.get("elite", False),
                "esito": None,
            })

        if not resolve_ok or not selezioni:
            continue

        # --- #2: partita duplicata ---
        match_keys_in_bolletta = [s["home"] + s["away"] + s["match_date"] for s in selezioni]
        if len(match_keys_in_bolletta) != len(set(match_keys_in_bolletta)):
            errors.append({
                "code": "PARTITA_DUPLICATA",
                "bolletta_idx": i, "tipo": raw_tipo,
                "feedback": f"Bolletta #{i+1} ({raw_tipo}): stessa partita ripetuta nella bolletta"
            })
            continue

        # --- #2b: punteggio minimo selezioni ---
        min_score = MIN_SCORE_PER_CATEGORY.get(raw_tipo, 4)
        low_score_sels = []
        for sel in selezioni_raw:
            key = (sel.get("match_key", ""), sel.get("mercato", ""), sel.get("pronostico", ""))
            pe = pool_index.get(key, {})
            if pe.get("_extra_pool"):
                continue  # extra pool non ha punteggio
            punt = pe.get("punteggio_finale") or 0
            if punt < min_score:
                low_score_sels.append(f"{key[0]} (score={punt})")
        if low_score_sels:
            errors.append({
                "code": "PUNTEGGIO_BASSO",
                "bolletta_idx": i, "tipo": raw_tipo,
                "feedback": f"Bolletta #{i+1} ({raw_tipo}): {len(low_score_sels)} selezioni con punteggio "
                           f"< {min_score}: {', '.join(low_score_sels[:3])}. Sostituisci con selezioni migliori"
            })
            continue

        quota_totale = round(quota_totale, 2)
        n_sel = len(selezioni)
        quote_str = " x ".join(f"{s['quota']}" for s in selezioni)

        # --- Determina tipo ---
        tipo = _classify_tipo(raw_tipo, selezioni, quota_totale, pool_index, today_str)

        # --- #7: elite insufficiente ---
        if raw_tipo == "elite" and tipo != "elite":
            elite_count = sum(1 for s in selezioni if pool_index.get(
                (f"{s['home']} vs {s['away']}|{s['match_date']}", s['mercato'], s['pronostico']),
                {}
            ).get("elite", False))
            errors.append({
                "code": "ELITE_INSUFFICIENTE",
                "bolletta_idx": i, "tipo": "elite",
                "feedback": f"Bolletta #{i+1} (elite): solo {elite_count}/{n_sel} selezioni elite, "
                           f"servono {n_sel}/{n_sel} (100%). Usa SOLO selezioni dal POOL ELITE"
            })

        # --- #9: manca partita di oggi (escluse elite) ---
        has_today = any(s["match_date"] == today_str for s in selezioni)
        if not has_today and tipo not in ("oggi", "elite"):
            errors.append({
                "code": "MANCA_PARTITA_OGGI",
                "bolletta_idx": i, "tipo": tipo,
                "feedback": f"Bolletta #{i+1} ({tipo}): nessuna partita di oggi ({today_str}). "
                           f"Serve almeno 1 partita di oggi"
            })
            continue

        # --- #8: oggi con partite non di oggi ---
        if tipo == "oggi" and not all(s["match_date"] == today_str for s in selezioni):
            errors.append({
                "code": "OGGI_CON_PARTITE_NON_OGGI",
                "bolletta_idx": i, "tipo": "oggi",
                "feedback": f"Bolletta #{i+1} (oggi): contiene partite non di oggi. "
                           f"Bollette 'oggi' = SOLO partite del {today_str}"
            })
            continue

        # --- #3: numero selezioni fuori range ---
        c = CATEGORY_CONSTRAINTS.get(tipo, {})
        min_sel = c.get("min_sel", 2)
        max_sel = c.get("max_sel", 10)
        if n_sel < min_sel or n_sel > max_sel:
            errors.append({
                "code": "NUM_SELEZIONI_FUORI_RANGE",
                "bolletta_idx": i, "tipo": tipo,
                "feedback": f"Bolletta #{i+1} ({tipo}): {n_sel} selezioni, range consentito {min_sel}-{max_sel}"
            })
            continue

        # --- #4: quota totale troppo alta (tolleranza 15%) ---
        max_q = c.get("max_quota")
        if max_q is not None and quota_totale > max_q * (1 + QUOTA_TOTALE_TOLERANCE_UP):
            errors.append({
                "code": "QUOTA_TOTALE_ALTA",
                "bolletta_idx": i, "tipo": tipo,
                "feedback": f"Bolletta #{i+1} ({tipo}): quota {quota_totale} > max {max_q}. "
                           f"Calcolo: {quote_str} = {quota_totale}. "
                           f"Sostituisci la selezione con quota piu' alta"
            })
            continue

        # --- #5: quota totale troppo bassa (tolleranza 0%) ---
        min_q = c.get("min_quota")
        if min_q is not None and quota_totale < min_q * (1 - QUOTA_TOTALE_TOLERANCE_DOWN):
            errors.append({
                "code": "QUOTA_TOTALE_BASSA",
                "bolletta_idx": i, "tipo": tipo,
                "feedback": f"Bolletta #{i+1} ({tipo}): quota {quota_totale} < min {min_q}. "
                           f"Calcolo: {quote_str} = {quota_totale}. "
                           f"Sostituisci la selezione con quota piu' bassa"
            })
            continue

        # --- #6: quota singola troppo alta (tolleranza 10%) ---
        limits = c.get("quota_singola", {})
        if limits:
            max_qs = limits.get(n_sel)
            if max_qs is not None:
                max_qs_tol = max_qs * (1 + QUOTA_SINGOLA_TOLERANCE)
                violazioni = [(s, s["quota"]) for s in selezioni if s["quota"] > max_qs_tol]
                if violazioni:
                    s_viol, q_viol = violazioni[0]
                    errors.append({
                        "code": "QUOTA_SINGOLA_ALTA",
                        "bolletta_idx": i, "tipo": tipo,
                        "feedback": f"Bolletta #{i+1} ({tipo}): con {n_sel} selezioni quota max "
                                   f"singola = {max_qs}, ma {s_viol['home']} vs {s_viol['away']} "
                                   f"({s_viol['mercato']}: {s_viol['pronostico']}) ha {q_viol}"
                    })
                    continue

        # --- #10: troppe bollette per categoria ---
        max_boll = c.get("max_bollette", 99)
        if counters[tipo] >= max_boll:
            errors.append({
                "code": "TROPPE_BOLLETTE",
                "bolletta_idx": i, "tipo": tipo,
                "feedback": f"Bolletta #{i+1} ({tipo}): limite {max_boll} raggiunto. "
                           f"Converti in un'altra fascia"
            })
            continue

        # --- #16: bolletta duplicata (stesse selezioni di una già accettata) ---
        bolletta_fingerprint = frozenset(
            f"{s['home']}|{s['away']}|{s['match_date']}|{s['mercato']}|{s['pronostico']}"
            for s in selezioni
        )
        is_duplicate = False
        for existing_doc in _all_accepted + valid_docs:
            existing_fp = frozenset(
                f"{s['home']}|{s['away']}|{s['match_date']}|{s['mercato']}|{s['pronostico']}"
                for s in existing_doc["selezioni"]
            )
            if bolletta_fingerprint == existing_fp:
                is_duplicate = True
                break
            # Anche bollette con 80%+ selezioni in comune sono troppo simili
            overlap = len(bolletta_fingerprint & existing_fp)
            if overlap >= max(2, len(bolletta_fingerprint) * 0.8):
                is_duplicate = True
                break
        if is_duplicate:
            errors.append({
                "code": "BOLLETTA_DUPLICATA",
                "bolletta_idx": i, "tipo": tipo,
                "feedback": f"Bolletta #{i+1} ({tipo}): identica o troppo simile a una gia' accettata. "
                           f"Cambia almeno 2 selezioni per renderla diversa"
            })
            continue

        # --- Bolletta valida ---
        counters[tipo] += 1
        label = f"{tipo.capitalize()} #{counters[tipo]}"
        solo_oggi = all(s["match_date"] == today_str for s in selezioni)

        valid_docs.append({
            "date": today_str,
            "tipo": tipo,
            "solo_oggi": solo_oggi,
            "quota_totale": quota_totale,
            "label": label,
            "selezioni": selezioni,
            "esito_globale": None,
            "saved_by": [],
            "reasoning": raw.get("reasoning", ""),
            "generated_at": datetime.now(timezone.utc),
            "pool_size": len(pool),
            "version": 1,
        })

    # --- Post-loop: #14 selezione max 1 volta per sezione ---
    # Scarta bollette che ripetono una selezione già presente in un'altra bolletta della stessa sezione
    filtered_docs = []
    used_sels = {}  # tipo -> set di selezioni già usate
    for doc in valid_docs:
        tipo = doc.get("tipo", "")
        if tipo not in used_sels:
            used_sels[tipo] = set()
        doc_sels = set()
        duplicate = False
        for s in doc["selezioni"]:
            key = f"{s['home']} vs {s['away']}|{s['match_date']}|{s['mercato']}:{s['pronostico']}"
            doc_sels.add(key)
            if key in used_sels[tipo]:
                duplicate = True
                errors.append({
                    "code": "SELEZIONE_TROPPO_RIPETUTA",
                    "bolletta_idx": -1, "tipo": tipo,
                    "feedback": f"Selezione {key} già usata in un'altra bolletta {tipo}. "
                               f"Max 1 volta per sezione. Bolletta scartata"
                })
                break
        if not duplicate:
            filtered_docs.append(doc)
            used_sels[tipo].update(doc_sels)
    if len(filtered_docs) < len(valid_docs):
        logger.info(f"🔄 Deduplica: {len(valid_docs)} → {len(filtered_docs)} bollette (selezioni ripetute nella stessa sezione)")
    valid_docs = filtered_docs

    # --- Post-loop: #12 diversificazione assente ---
    by_tipo_nsel = {}
    for doc in valid_docs:
        by_tipo_nsel.setdefault(doc["tipo"], []).append(len(doc["selezioni"]))
    for t, ns in by_tipo_nsel.items():
        if len(ns) >= 3 and len(set(ns)) == 1:
            cc = CATEGORY_CONSTRAINTS.get(t, {})
            errors.append({
                "code": "DIVERSIFICAZIONE_ASSENTE",
                "bolletta_idx": -1, "tipo": t,
                "feedback": f"Tutte le {len(ns)} bollette {t} hanno {ns[0]} selezioni. "
                           f"Diversifica: range {cc.get('min_sel', 2)}-{cc.get('max_sel', 8)}"
            })

    return valid_docs, errors, counters


def validate_and_build(raw_bollette, pool, today_str, existing_counters=None):
    """Wrapper retrocompatibile: restituisce solo i documenti validi."""
    valid_docs, _, _ = validate_with_errors(raw_bollette, pool, today_str, existing_counters)
    return valid_docs


def build_extra_pool(today_str, existing_match_keys, skip_time_filter=False):
    """Costruisce pool esteso da h2h_by_round per partite NON già nel pool AI."""
    today = datetime.strptime(today_str, "%Y-%m-%d")
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]
    now = datetime.now()

    extra_pool = []
    # Cerca partite per date_obj dentro matches[] (non campo date a livello documento)
    date_start = datetime.strptime(dates[0], "%Y-%m-%d")
    date_end = datetime.strptime(dates[-1], "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    rounds = list(db.h2h_by_round.find(
        {"matches.date_obj": {"$gte": date_start, "$lte": date_end}},
        {"league": 1, "matches": 1}
    ).max_time_ms(30000))

    for rnd in rounds:
        league = rnd.get("league", "")
        for m in rnd.get("matches", []):
            home = m.get("home", "")
            away = m.get("away", "")
            match_date = m.get("date_obj")
            if not match_date:
                continue
            if isinstance(match_date, datetime):
                # Filtra solo partite nei 3 giorni
                if match_date < date_start or match_date > date_end:
                    continue
                match_date = match_date.strftime("%Y-%m-%d")
            match_time = m.get("match_time", "00:00")
            match_key = f"{home} vs {away}|{match_date}"

            # Salta se già nel pool AI
            if match_key in existing_match_keys:
                continue

            # Salta partite già iniziate (skip per date retroattive)
            if not skip_time_filter:
                try:
                    kick_off = datetime.strptime(f"{match_date} {match_time}", "%Y-%m-%d %H:%M")
                    if kick_off <= now:
                        continue
                except ValueError:
                    pass

            # Prendi quote se disponibili
            odds = m.get("odds", {})
            if not odds:
                continue

            # Dati per Mistral: stato forma, lucifero, BvS etc.
            home_form = m.get("home_form", "")
            away_form = m.get("away_form", "")
            home_lucifero = m.get("home_lucifero", "")
            away_lucifero = m.get("away_lucifero", "")

            # Genera selezioni dai mercati disponibili con quote
            mercati = []
            o = odds
            if o.get("1"):
                mercati.append(("SEGNO", "1", o["1"]))
            if o.get("X"):
                mercati.append(("SEGNO", "X", o["X"]))
            if o.get("2"):
                mercati.append(("SEGNO", "2", o["2"]))
            if o.get("over_25") or o.get("over_2_5"):
                mercati.append(("GOL", "Over 2.5", o.get("over_25") or o.get("over_2_5")))
            if o.get("under_25") or o.get("under_2_5"):
                mercati.append(("GOL", "Under 2.5", o.get("under_25") or o.get("under_2_5")))
            if o.get("over_15") or o.get("over_1_5"):
                mercati.append(("GOL", "Over 1.5", o.get("over_15") or o.get("over_1_5")))
            if o.get("under_15") or o.get("under_1_5"):
                mercati.append(("GOL", "Under 1.5", o.get("under_15") or o.get("under_1_5")))
            if o.get("over_35") or o.get("over_3_5"):
                mercati.append(("GOL", "Over 3.5", o.get("over_35") or o.get("over_3_5")))
            if o.get("under_35") or o.get("under_3_5"):
                mercati.append(("GOL", "Under 3.5", o.get("under_35") or o.get("under_3_5")))
            if o.get("gg") or o.get("goal"):
                mercati.append(("GOL", "Goal", o.get("gg") or o.get("goal")))
            if o.get("ng") or o.get("nogoal"):
                mercati.append(("GOL", "NoGoal", o.get("ng") or o.get("nogoal")))

            # DC calcolate
            if o.get("1") and o.get("X"):
                dc_1x = round(1 / (1/o["1"] + 1/o["X"]), 2)
                mercati.append(("DOPPIA_CHANCE", "1X", dc_1x))
            if o.get("X") and o.get("2"):
                dc_x2 = round(1 / (1/o["X"] + 1/o["2"]), 2)
                mercati.append(("DOPPIA_CHANCE", "X2", dc_x2))
            if o.get("1") and o.get("2"):
                dc_12 = round(1 / (1/o["1"] + 1/o["2"]), 2)
                mercati.append(("DOPPIA_CHANCE", "12", dc_12))

            for mercato, pronostico, quota in mercati:
                if not quota or quota <= 1.0:
                    continue
                extra_pool.append({
                    "match_key": match_key,
                    "home": home,
                    "away": away,
                    "league": league,
                    "match_time": match_time,
                    "match_date": match_date,
                    "home_mongo_id": str(m.get("home_mongo_id", "")),
                    "away_mongo_id": str(m.get("away_mongo_id", "")),
                    "mercato": mercato,
                    "pronostico": pronostico,
                    "quota": round(float(quota), 2),
                    "confidence": 0,
                    "stars": 0,
                    "_extra_pool": True,
                    "_home_form": home_form,
                    "_away_form": away_form,
                })

    return extra_pool


def call_mistral_integration(pool, fascia, count_needed, today_str, extra_context=""):
    """Chiama Mistral per generare solo le bollette mancanti di una fascia."""
    c = CATEGORY_CONSTRAINTS[fascia]

    # Pre-filtra pool: rimuovi selezioni con quota troppo alta per questa fascia
    quota_singola = c.get("quota_singola", {})
    if quota_singola:
        max_quota_singola = max(quota_singola.values())
        filtered_pool = [s for s in pool if s["quota"] <= max_quota_singola]
        logger.info(f"📋 Pool filtrato per {fascia}: {len(filtered_pool)}/{len(pool)} selezioni (quota max singola: {max_quota_singola})")
    else:
        filtered_pool = pool

    # Pre-filtra pool: rimuovi selezioni con punteggio sotto soglia per questa fascia
    min_score = MIN_SCORE_PER_CATEGORY.get(fascia, 4)
    before_score = len(filtered_pool)
    filtered_pool = [s for s in filtered_pool
                     if s.get("_extra_pool") or (s.get("punteggio_finale") or 0) >= min_score]
    if before_score - len(filtered_pool) > 0:
        logger.info(f"📋 Pool {fascia}: escluse {before_score - len(filtered_pool)} selezioni con punteggio < {min_score}")

    pool_text = serialize_pool_for_prompt(filtered_pool)

    # Costruisci regole specifiche per fascia
    if fascia == "oggi":
        quota_rule = f"Quote libere. TUTTE le selezioni DEVONO essere partite di OGGI ({today_str})"
        sel_rule = f"Minimo {c['min_sel']}, massimo {c['max_sel']} selezioni per bolletta"
        quota_singola_rule = "Nessun vincolo su quota singola"
    else:
        min_q = c['min_quota'] or "—"
        max_q = c['max_quota'] or "libera"
        quota_rule = f"Quota totale: min {min_q}, max {max_q}. ⚠️ OGNI bolletta DEVE contenere ALMENO 1 partita di OGGI ({today_str})"
        sel_rule = f"Minimo {c['min_sel']}, massimo {c['max_sel']} selezioni per bolletta"
        if c['quota_singola']:
            lines = [f"  • {n} selezioni → ogni quota max {q}" for n, q in sorted(c['quota_singola'].items())]
            quota_singola_rule = "Quota max per SINGOLA selezione:\n" + "\n".join(lines)
        else:
            quota_singola_rule = "Nessun vincolo su quota singola"

    # Genera schema diversificazione per questa fascia
    min_s, max_s = c['min_sel'], c['max_sel']
    div_seq = []
    val = min_s
    for i in range(count_needed):
        div_seq.append(val)
        val += 1
        if val > max_s:
            val = min_s
    div_text = ", ".join(f"Bolletta {i+1}: {n} selezioni" for i, n in enumerate(div_seq))

    prompt = f"""Sei un analista dati sportivo. I pronostici sono già decisi dall'AI. Analizza i dati statistici e componi esattamente {count_needed} bollette di tipo "{fascia}".
{quota_rule}

REGOLE:
1. Ogni partita UNA SOLA VOLTA per bolletta, con UN SOLO mercato
2. {sel_rule}
3. {quota_singola_rule}
4. Le selezioni con _extra_pool=true sono partite fuori dal sistema AI — usale se servono
5. ⚠️ OBBLIGATORIO: almeno 1 selezione con data {today_str} in ogni bolletta (escluso elite)
6. Diversifica il numero di selezioni tra bollette: {div_text}
7. ⚠️ CRITICO: NON ripetere la stessa selezione in più bollette! Ogni selezione può apparire in UNA SOLA bolletta. Se la ripeti e perde, perdi tutte le bollette
8. Restituisci SOLO un array JSON valido. Nessun testo prima o dopo

[
  {{
    "tipo": "{fascia}",
    "selezioni": [
      {{ "match_key": "Home vs Away|YYYY-MM-DD", "mercato": "SEGNO", "pronostico": "1" }}
    ],
    "reasoning": "Cita i dati statistici che ti hanno convinto (forma, trend, affidabilità, classifica)"
  }}
]

match_key, mercato e pronostico devono corrispondere ESATTAMENTE al pool."""

    if extra_context:
        prompt += f"\n\n⚠️ ATTENZIONE — ERRORI PRECEDENTI:\n{extra_context}"

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Pool disponibile:\n{pool_text}\n\nComponi {count_needed} bollette {fascia}."},
    ]

    content = _call_llm_with_fallback(messages)

    try:
        return _sanitize_and_parse_json(content)
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f" Parse JSON fallito ({e}), retry con istruzione esplicita...")
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": "ERRORE: la risposta non è un JSON valido. Rispondi con SOLO un array JSON valido, senza testo prima o dopo. Formato: [{...}, {...}]"})
        content2 = _call_llm_with_fallback(messages)
        return _sanitize_and_parse_json(content2)


def _check_feasibility(fascia, pool, today_str):
    """Verifica se e' matematicamente possibile generare bollette per questa fascia.
    Returns: (feasible: bool, reason: str, section_pool: list)
    """
    c = CATEGORY_CONSTRAINTS.get(fascia, {})
    min_sel = c.get("min_sel", 2)
    min_quota = c.get("min_quota")
    max_quota = c.get("max_quota")

    # Soglie punteggio minimo per categoria (calibrate su dati reali)
    MIN_SCORE = {
        "elite": 7,
        "selettiva": 7,
        "bilanciata": 5,
        "ambiziosa": 4,
        "oggi": 4,
    }
    min_score = MIN_SCORE.get(fascia, 4)

    # Filtra pool per la sezione
    if fascia == "oggi":
        section_pool = [s for s in pool if s.get("match_date") == today_str]
    elif fascia == "elite":
        section_pool = [s for s in pool if s.get("elite")]
    else:
        section_pool = pool

    # Check 0: abbastanza selezioni con punteggio sufficiente?
    qualified = [s for s in section_pool if (s.get("punteggio_finale") or 0) >= min_score]
    unique_qualified = set(s.get("match_key", "") for s in qualified)
    if len(unique_qualified) < min_sel:
        return False, f"solo {len(unique_qualified)} partite con punteggio ≥{min_score}, servono almeno {min_sel}", section_pool
    logger.info(f"📊 {fascia}: {len(unique_qualified)} partite qualificate (punteggio ≥{min_score})")

    # Check 1: abbastanza selezioni?
    # Conta partite uniche (ogni partita puo' apparire 1 volta per bolletta)
    unique_matches = set(s.get("match_key", "") for s in section_pool)
    if len(unique_matches) < min_sel:
        return False, f"solo {len(unique_matches)} partite uniche, servono almeno {min_sel}", section_pool

    # Check 2: elite — servono almeno 2 selezioni elite (100% richiesto)
    if fascia == "elite":
        elite_count = sum(1 for s in section_pool if s.get("elite"))
        if elite_count < 2:
            return False, f"solo {elite_count} selezioni elite, servono almeno 2", section_pool

    # Check 3: quota minima raggiungibile?
    if min_quota:
        # Prendi le quote piu' alte per partita unica
        best_by_match = {}
        for s in section_pool:
            mk = s.get("match_key", "")
            q = s.get("quota", 0) or 0
            if mk not in best_by_match or q > best_by_match[mk]:
                best_by_match[mk] = q
        # Quota max = prodotto delle N quote piu' alte
        top_quotes = sorted(best_by_match.values(), reverse=True)[:c.get("max_sel", 8)]
        if len(top_quotes) >= min_sel:
            max_achievable = 1.0
            for q in top_quotes[:min_sel]:
                max_achievable *= q
            if max_achievable < min_quota * (1 - QUOTA_TOTALE_TOLERANCE_DOWN):  # 0% tolleranza sotto
                return False, f"quota max raggiungibile ~{max_achievable:.1f}, minimo {min_quota}", section_pool

    # Check 4: quota massima rispettabile?
    if max_quota:
        # Prendi le quote piu' basse per partita unica
        lowest_by_match = {}
        for s in section_pool:
            mk = s.get("match_key", "")
            q = s.get("quota", 0) or 0
            if q > 1.0 and (mk not in lowest_by_match or q < lowest_by_match[mk]):
                lowest_by_match[mk] = q
        low_quotes = sorted(lowest_by_match.values())[:min_sel]
        if len(low_quotes) >= min_sel:
            min_achievable = 1.0
            for q in low_quotes:
                min_achievable *= q
            if min_achievable > max_quota * (1 + QUOTA_TOTALE_TOLERANCE_UP):  # 15% tolleranza sopra
                return False, f"quota min raggiungibile ~{min_achievable:.1f}, massimo {max_quota}", section_pool

    return True, "OK", section_pool


def _generate_for_section(fascia, needed, pool, today_str, bollette_docs, counters):
    """Genera bollette per una singola sezione con retry.
    Returns: (lista bollette valide, lista selezioni scartate per ricomposizione).
    """
    # Check fattibilita'
    feasible, reason, section_pool = _check_feasibility(fascia, pool, today_str)
    if not feasible:
        logger.error(f" Impossibile: {reason}")
        return [], []

    logger.info(f"📋 Pool per {fascia}: {len(section_pool)} selezioni")

    # Per elite: limita richiesta in base al pool disponibile
    if fascia == "elite":
        unique_elite_matches = len(set(s.get("match_key", "") for s in section_pool))
        max_elite = max(2, unique_elite_matches // 2)  # ~metà delle partite uniche
        needed = min(needed, max_elite)
        logger.info(f"📋 Elite: {unique_elite_matches} partite uniche → max {needed} bollette")

    # Raccolta selezioni scartate per ricomposizione
    all_raw = []
    discarded_sels = []

    # Chiamata Mistral (retry 429 gestito dentro call_mistral_integration)
    raw = None
    try:
        raw = call_mistral_integration(section_pool, fascia, needed, today_str)
    except Exception as e:
        logger.error(f" Errore Mistral per {fascia}: {e}")
        return [], []

    if not isinstance(raw, list):
        logger.error(f" Risposta non valida per {fascia}")
        return [], []

    all_raw.extend(raw)

    # Valida
    valid, errors, new_counters = validate_with_errors(
        raw, section_pool, today_str,
        existing_counters=counters,
        existing_docs=bollette_docs
    )

    # Fix: bollette "oggi" devono avere SOLO partite di oggi
    if fascia == "oggi":
        valid = [
            doc for doc in valid
            if all(s.get("match_date") == today_str for s in doc.get("selezioni", []))
        ]

    # Limita al numero richiesto
    valid = valid[:needed]

    if errors:
        logger.warning(f" {len(errors)} errori per {fascia}")
        for err in errors[:3]:
            logger.warning(f"[{err['code']}] {err['feedback'][:100]}")

    # Se non abbastanza, retry fino a 2 volte con feedback specifico
    for retry_attempt in range(2):
        still_needed = needed - len(valid)
        if still_needed <= 0 or not errors:
            break
        logger.info(f"🔄 Retry {fascia} #{retry_attempt+1}: mancano {still_needed} bollette...")

        # Costruisci feedback specifico con errori e suggerimenti
        error_lines = [f"- {err['feedback']}" for err in errors[:5]]
        c = CATEGORY_CONSTRAINTS.get(fascia, {})
        feedback_text = (
            f"ERRORI nelle bollette {fascia} precedenti:\n"
            + "\n".join(error_lines)
            + f"\n\nRICORDA le regole per {fascia}:"
            + f"\n- Quota totale: min {c.get('min_quota', 'libera')}, max {c.get('max_quota', 'libera')}"
            + f"\n- Selezioni: min {c.get('min_sel', 2)}, max {c.get('max_sel', 8)}"
            + f"\n- Genera esattamente {still_needed} bollette {fascia} VALIDE"
            + f"\n- Ogni bolletta DEVE avere almeno 1 partita di oggi ({today_str})"
            + f"\n- NON ripetere bollette gia' accettate"
        )
        if c.get('quota_singola'):
            for n, q in sorted(c['quota_singola'].items()):
                feedback_text += f"\n- Con {n} selezioni: ogni quota max {q}"

        try:
            retry_raw = call_mistral_integration(section_pool, fascia, still_needed, today_str, extra_context=feedback_text)
            if isinstance(retry_raw, list):
                all_raw.extend(retry_raw)
                retry_valid, errors, new_counters = validate_with_errors(
                    retry_raw, section_pool, today_str,
                    existing_counters=new_counters,
                    existing_docs=bollette_docs + valid
                )
                if fascia == "oggi":
                    retry_valid = [
                        doc for doc in retry_valid
                        if all(s.get("match_date") == today_str for s in doc.get("selezioni", []))
                    ]
                retry_valid = retry_valid[:still_needed]
                valid.extend(retry_valid)
                if retry_valid:
                    logger.info(f"✅ Retry: +{len(retry_valid)} bollette {fascia}")
                if errors:
                    logger.warning(f" Retry: ancora {len(errors)} errori")
        except Exception as e:
            logger.error(f" Errore retry {fascia}: {e}")
            break

    # Assegna tipo e label
    existing_count = sum(1 for b in bollette_docs if b.get("tipo") == fascia)
    for doc in valid:
        existing_count += 1
        doc["tipo"] = fascia
        doc["label"] = f"{fascia.capitalize()} #{existing_count}"

    # Aggiorna counters
    counters.update(new_counters)

    # Raccogli selezioni dalle bollette scartate (raw che non sono in valid)
    valid_fingerprints = set()
    for doc in valid:
        fp = frozenset(
            f"{s['home']}|{s['away']}|{s['match_date']}|{s['mercato']}|{s['pronostico']}"
            for s in doc["selezioni"]
        )
        valid_fingerprints.add(fp)

    pool_index = {}
    for s in section_pool:
        key = (s["match_key"], s["mercato"], s["pronostico"])
        pool_index[key] = s

    for raw_b in all_raw:
        # Controlla se questa raw bolletta e' stata accettata
        selezioni_raw = raw_b.get("selezioni", [])
        if not isinstance(selezioni_raw, list):
            continue
        raw_fp = frozenset(
            f"{s.get('match_key', '')}|{s.get('mercato', '')}|{s.get('pronostico', '')}"
            for s in selezioni_raw
        )
        # Se non e' in valid, le sue selezioni sono scartate
        is_accepted = False
        for vfp in valid_fingerprints:
            # Confronto approssimativo (i formati possono differire)
            if len(raw_fp & vfp) >= len(selezioni_raw) * 0.8:
                is_accepted = True
                break
        if not is_accepted:
            for sel in selezioni_raw:
                key = (sel.get("match_key", ""), sel.get("mercato", ""), sel.get("pronostico", ""))
                pool_entry = pool_index.get(key)
                if pool_entry:
                    discarded_sels.append(pool_entry)

    logger.info(f"📊 {fascia}: {len(valid)}/{needed} bollette generate")
    return valid, discarded_sels


def _recompose_from_discards(discarded_selezioni, pool, today_str, bollette_docs, counters):
    """Ricompone bollette dalle selezioni delle bollette scartate (logica urna).
    Pesca selezioni random, verifica vincoli, classifica per quota totale.
    Returns: lista di nuove bollette valide.
    """
    import random

    if not discarded_selezioni:
        return []

    # Deduplica selezioni nell'urna (stessa partita + mercato + pronostico = 1 volta)
    seen = set()
    urna = []
    for sel in discarded_selezioni:
        key = (sel.get("match_key", f"{sel['home']} vs {sel['away']}|{sel['match_date']}"),
               sel["mercato"], sel["pronostico"])
        if key not in seen:
            seen.add(key)
            urna.append(sel)

    # Filtra per punteggio minimo: solo selezioni con punteggio >= 4
    pre_filter = len(urna)
    urna = [s for s in urna if (s.get("punteggio_finale") or 0) >= 4]
    if pre_filter != len(urna):
        logger.info(f"📊 Urna filtrata per punteggio ≥4: {len(urna)}/{pre_filter} selezioni")

    if len(urna) < 2:
        return []

    # Fasce con range di quota per classificazione
    FASCE_RECOMPOSE = [
        ("selettiva", 1.5, 4.50),
        ("bilanciata", 5.0, 7.50),
        ("ambiziosa", 8.0, 999.0),
    ]

    # Check se ci sono partite di oggi nell'urna
    has_today_in_urna = any(s.get("match_date") == today_str for s in urna)

    new_bollette = []
    consecutive_fails = 0
    max_fails = 50

    # Traccia selezioni già usate per sezione (dalle bollette esistenti)
    used_sels_by_tipo = {}
    for doc in bollette_docs:
        t = doc.get("tipo", "")
        if t not in used_sels_by_tipo:
            used_sels_by_tipo[t] = set()
        for s in doc.get("selezioni", []):
            used_sels_by_tipo[t].add(
                f"{s['home']}|{s['away']}|{s.get('match_date','')}|{s.get('mercato','')}|{s.get('pronostico','')}"
            )

    # Calcola quante bollette servono ancora per fascia
    targets = {"selettiva": 3, "bilanciata": 3, "ambiziosa": 3}
    for fascia in targets:
        targets[fascia] -= counters.get(fascia, 0)

    all_done = all(t <= 0 for t in targets.values())

    while not all_done and consecutive_fails < max_fails:
        # Estrai selezioni random dall'urna
        n_sel = random.randint(2, 8)  # max ambiziosa
        if len(urna) < 2:
            break
        candidate_sels = random.sample(urna, min(n_sel, len(urna)))

        # Check: no stessa partita due volte
        match_keys = [f"{s['home']}|{s['away']}|{s['match_date']}" for s in candidate_sels]
        if len(match_keys) != len(set(match_keys)):
            consecutive_fails += 1
            continue

        # Check: no SEGNO X
        if any(s.get("mercato") == "SEGNO" and s.get("pronostico") == "X" for s in candidate_sels):
            consecutive_fails += 1
            continue

        # Check: almeno 1 partita di oggi (skip se urna non ne ha)
        has_today = any(s.get("match_date") == today_str for s in candidate_sels)
        if has_today_in_urna and not has_today:
            consecutive_fails += 1
            continue

        # Calcola quota totale
        quota_totale = 1.0
        for s in candidate_sels:
            quota_totale *= s["quota"]
        quota_totale = round(quota_totale, 2)

        # Classifica per range di quota — prima fascia con posto
        assigned_fascia = None
        for fascia, lo, hi in FASCE_RECOMPOSE:
            if targets.get(fascia, 0) <= 0:
                continue
            # Tolleranza: 15% sopra, 0% sotto
            if lo <= quota_totale <= hi * (1 + QUOTA_TOTALE_TOLERANCE_UP):
                # Check numero selezioni nel range della fascia
                c = CATEGORY_CONSTRAINTS[fascia]
                if c["min_sel"] <= len(candidate_sels) <= c["max_sel"]:
                    # Check quota singola
                    limits = c.get("quota_singola", {})
                    if limits:
                        max_qs = limits.get(len(candidate_sels))
                        if max_qs is not None:
                            max_qs_tol = max_qs * (1 + QUOTA_SINGOLA_TOLERANCE)
                            if any(s["quota"] > max_qs_tol for s in candidate_sels):
                                continue
                    assigned_fascia = fascia
                    break

        if not assigned_fascia:
            consecutive_fails += 1
            continue

        # Check duplicati con bollette esistenti + nuove
        bolletta_fingerprint = frozenset(
            f"{s['home']}|{s['away']}|{s['match_date']}|{s['mercato']}|{s['pronostico']}"
            for s in candidate_sels
        )
        is_duplicate = False
        for existing_doc in bollette_docs + new_bollette:
            existing_fp = frozenset(
                f"{s['home']}|{s['away']}|{s['match_date']}|{s['mercato']}|{s['pronostico']}"
                for s in existing_doc["selezioni"]
            )
            if bolletta_fingerprint == existing_fp:
                is_duplicate = True
                break
            overlap = len(bolletta_fingerprint & existing_fp)
            # Se urna ha solo 1 partita di oggi, due bollette possono condividerla
            # purché abbiano almeno 1 altra selezione diversa
            threshold = max(2, len(bolletta_fingerprint) * 0.8)
            if overlap >= threshold:
                is_duplicate = True
                break
        if is_duplicate:
            consecutive_fails += 1
            continue

        # Check: selezione già usata nella stessa sezione
        if assigned_fascia not in used_sels_by_tipo:
            used_sels_by_tipo[assigned_fascia] = set()
        sel_keys = [
            f"{s['home']}|{s['away']}|{s['match_date']}|{s['mercato']}|{s['pronostico']}"
            for s in candidate_sels
        ]
        if any(k in used_sels_by_tipo[assigned_fascia] for k in sel_keys):
            consecutive_fails += 1
            continue

        # Bolletta valida — aggiorna tracking selezioni per sezione
        used_sels_by_tipo[assigned_fascia].update(sel_keys)

        solo_oggi = all(s.get("match_date") == today_str for s in candidate_sels)
        counters[assigned_fascia] = counters.get(assigned_fascia, 0) + 1
        existing_count = counters[assigned_fascia]

        selezioni_doc = []
        for s in candidate_sels:
            selezioni_doc.append({
                "home": s["home"],
                "away": s["away"],
                "league": s["league"],
                "match_time": s["match_time"],
                "match_date": s["match_date"],
                "home_mongo_id": s["home_mongo_id"],
                "away_mongo_id": s["away_mongo_id"],
                "mercato": s["mercato"],
                "pronostico": s["pronostico"],
                "quota": s["quota"],
                "confidence": s["confidence"],
                "stars": s["stars"],
                "esito": None,
            })

        doc = {
            "date": today_str,
            "tipo": assigned_fascia,
            "solo_oggi": solo_oggi,
            "quota_totale": quota_totale,
            "label": f"{assigned_fascia.capitalize()} #{existing_count}",
            "selezioni": selezioni_doc,
            "esito_globale": None,
            "saved_by": [],
            "reasoning": "Ricomposta automaticamente dal mini-pool",
            "generated_at": datetime.now(timezone.utc),
            "pool_size": len(pool),
            "version": 1,
        }

        new_bollette.append(doc)
        targets[assigned_fascia] -= 1
        consecutive_fails = 0  # Reset dopo successo

        all_done = all(t <= 0 for t in targets.values())

    return new_bollette


def _timeout_handler():
    """Termina il processo se supera il timeout globale."""
    logger.error(f"⏰ TIMEOUT: script superato {SCRIPT_TIMEOUT_MINUTES} minuti, terminazione forzata")
    os._exit(1)


def main():
    # Timeout globale (Windows-compatible, signal.alarm non disponibile)
    timer = threading.Timer(SCRIPT_TIMEOUT_MINUTES * 60, _timeout_handler)
    timer.daemon = True
    timer.start()

    logger.info("=" * 60)
    logger.info("🎫 GENERAZIONE BOLLETTE — Step 35 (Sequenziale)")
    logger.info(f"⏰ Timeout globale: {SCRIPT_TIMEOUT_MINUTES} minuti")
    logger.info("=" * 60)

    # Supporta --date YYYY-MM-DD e --dry-run
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, default=None, help='Data YYYY-MM-DD')
    parser.add_argument('--dry-run', action='store_true', help='Non salvare su MongoDB')
    parser.add_argument('--debug', action='store_true', help='Salva prompt LLM su file debug')
    args, _ = parser.parse_known_args()
    today_str = args.date if args.date else datetime.now().strftime("%Y-%m-%d")
    is_retroactive = args.date is not None
    dry_run = args.dry_run
    global DEBUG_MODE
    DEBUG_MODE = args.debug
    if dry_run:
        logger.info("🔍 MODALITÀ DRY-RUN — nessun salvataggio su MongoDB")
    if DEBUG_MODE:
        logger.info("🐛 MODALITÀ DEBUG — prompt LLM salvati in log/")

    # 1. Costruisci pool base (pronostici AI)
    pool = build_pool(today_str, skip_time_filter=is_retroactive)
    recovered = recover_from_yesterday(today_str)
    if recovered:
        pool.extend(recovered)
    pool = deduplicate_pool(pool)
    logger.info(f"📊 Pool AI: {len(pool)} selezioni uniche")

    # 1b. Filtra pool con pattern bollette (85 pattern Mixer + elite)
    pool_before = len(pool)
    pool = [s for s in pool if s.get("elite") or matches_bollette_pattern(s)]
    logger.info(f"🎯 Filtro pattern: {pool_before} → {len(pool)} selezioni "
          f"({pool_before - len(pool)} escluse, {len(PATTERNS)} pattern caricati)")

    # 1c. Arricchisci pool con dati statistici (classifica, forma, trend, motivazioni, strisce, affidabilità, DNA)
    classifiche_cache = enrich_pool_with_stats(pool)

    # 1d. Calcola Coefficiente di Solidità (deterministico, Python)
    calculate_solidity_coefficient(pool, classifiche_cache)

    # 1e. Calcola punteggio finale per ogni selezione (Passo 1 + Passo 2)
    calculate_final_score(pool)

    if len(pool) < 2:
        logger.warning(" Pool troppo piccolo (< 2 selezioni). Nessuna bolletta generata.")
        return

    # 2. Generazione sequenziale per sezione
    bollette_docs = []
    counters = {"oggi": 0, "elite": 0, "selettiva": 0, "bilanciata": 0, "ambiziosa": 0}
    all_discarded_sels = []

    for fascia in SECTION_ORDER:
        target = SECTION_TARGETS[fascia]
        logger.info(f"{'─'*50}")
        logger.info(f"📌 SEZIONE {fascia.upper()} — target: {target} bollette")
        logger.info(f"{'─'*50}")

        new_bollette, discarded = _generate_for_section(
            fascia, target, pool, today_str, bollette_docs, counters
        )

        if new_bollette:
            bollette_docs.extend(new_bollette)
            if len(new_bollette) < target:
                logger.info(f"✅ {fascia.upper()}: {len(new_bollette)}/{target} bollette (qualità insufficiente per generarne di più)")
            else:
                logger.info(f"✅ {fascia.upper()}: {len(new_bollette)} bollette generate")
        else:
            logger.warning(f" {fascia.upper()}: nessuna bolletta valida")

        if discarded:
            all_discarded_sels.extend(discarded)

        # Pausa tra sezioni per evitare rate limit Mistral
        time.sleep(5)

    # 3. Ricomposizione automatica dalle bollette scartate
    missing = {f: 3 - counters.get(f, 0) for f in ["selettiva", "bilanciata", "ambiziosa"]}
    any_missing = any(v > 0 for v in missing.values())

    if any_missing and all_discarded_sels:
        logger.info(f"{'─'*50}")
        logger.info(f"🔄 RICOMPOSIZIONE — urna: {len(all_discarded_sels)} selezioni scartate")
        logger.info(f"Mancano: " + ", ".join(f"{f}={v}" for f, v in missing.items() if v > 0))
        logger.info(f"{'─'*50}")

        recomposed = _recompose_from_discards(
            all_discarded_sels, pool, today_str, bollette_docs, counters
        )

        if recomposed:
            bollette_docs.extend(recomposed)
            by_tipo_r = {}
            for b in recomposed:
                by_tipo_r.setdefault(b["tipo"], []).append(b)
            for tipo, bs in by_tipo_r.items():
                quotes = [b["quota_totale"] for b in bs]
                logger.info(f"✅ Ricomposte {len(bs)} {tipo}: quote {quotes}")
        else:
            logger.warning(f" Nessuna bolletta ricomposta")

    if not bollette_docs:
        logger.warning("Nessuna bolletta generata.")
        return

    # 4. Salva su MongoDB
    if dry_run:
        logger.info("🔍 DRY-RUN: skip salvataggio MongoDB")
    else:
        coll = db.bollette
        deleted = coll.delete_many({"date": today_str, "custom": {"$ne": True}})
        if deleted.deleted_count > 0:
            logger.info(f"🗑️ Rimosse {deleted.deleted_count} bollette precedenti per {today_str}")
        coll.insert_many(bollette_docs)

    # 5. Riepilogo finale
    by_tipo = {}
    for b in bollette_docs:
        by_tipo.setdefault(b["tipo"], []).append(b)

    # Conta bollette Mistral vs urna
    n_recomposed = sum(1 for b in bollette_docs if b.get("reasoning", "").startswith("Ricomposta"))
    n_mistral = len(bollette_docs) - n_recomposed

    logger.info(f"{'='*50}")
    logger.info(f"🏆 RIEPILOGO FINALE:")
    logger.info(f"LLM: {n_mistral}/15 bollette")
    if n_recomposed > 0:
        logger.info(f"Urna:    +{n_recomposed} ricomposte")
    logger.info(f"TOTALE:  {len(bollette_docs)} bollette {'✅' if len(bollette_docs) >= 10 else '⚠️ poche bollette di qualità'}")
    logger.info(f"{'='*50}")

    label = "🔍 DRY-RUN" if dry_run else "✅ Salvate"
    logger.info(f"{label} {len(bollette_docs)} bollette:")
    for tipo in SECTION_ORDER:
        if tipo in by_tipo:
            quotes = [b["quota_totale"] for b in by_tipo[tipo]]
            n_sel_list = [len(b["selezioni"]) for b in by_tipo[tipo]]
            r_count = sum(1 for b in by_tipo[tipo] if b.get("reasoning", "").startswith("Ricomposta"))
            urna_tag = f" (🔄 {r_count} da urna)" if r_count > 0 else ""
            logger.info(f"  {tipo.upper()}: {len(by_tipo[tipo])} "
                        f"— quote: {quotes} — selezioni: {n_sel_list}{urna_tag}")

    timer.cancel()


if __name__ == "__main__":
    main()
