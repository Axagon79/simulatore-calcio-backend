"""
GENERATE BOLLETTE — Step 35 Pipeline Notturna
==============================================
Genera bollette (biglietti scommessa pre-composti) tramite Mistral AI.
Legge pronostici unified per 3 giorni, recupera selezioni valide da
bollette saltate, e produce max 10 bollette al giorno.
"""

import os, sys, re, json, time, glob
from datetime import datetime, timedelta, timezone

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
    print("❌ Modulo 'requests' non trovato. Installa con: pip install requests")
    sys.exit(1)

# --- CONFIGURAZIONE ---
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-medium-2508"
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
if not MISTRAL_API_KEY:
    try:
        from dotenv import load_dotenv
        # Prova .env nella cartella config
        load_dotenv(os.path.join(current_path, '.env'))
        MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
        # Fallback: .env nella root del progetto
        if not MISTRAL_API_KEY:
            root_env = os.path.join(current_path, '..', '..', '.env')
            load_dotenv(os.path.abspath(root_env))
            MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
    except ImportError:
        pass
if not MISTRAL_API_KEY:
    print("❌ MISTRAL_API_KEY non trovata!")
    sys.exit(1)

MAX_BOLLETTE = 18

# Fasce quota totale
FASCE = {
    "oggi":       (1.0, 999.0),   # Nessun vincolo quota — solo partite di oggi
    "selettiva":  (1.5, 4.5),
    "bilanciata": (5.0, 7.5),
    "ambiziosa":  (8.0, 999.0),
    "elite":      (1.5, 8.0),     # Almeno 70% selezioni elite
}

# Vincoli per categoria (validazione post-Mistral)
CATEGORY_CONSTRAINTS = {
    "oggi": {
        "min_sel": 2, "max_sel": 4,
        "min_quota": None, "max_quota": None,
        "max_bollette": 3,
        "quota_singola": {},  # nessun vincolo
    },
    "selettiva": {
        "min_sel": 2, "max_sel": 5,
        "min_quota": None, "max_quota": 4.50,
        "max_bollette": 3,
        "quota_singola": {2: 2.20, 3: 1.70, 4: 1.50, 5: 1.38},
    },
    "bilanciata": {
        "min_sel": 3, "max_sel": 7,
        "min_quota": 5.00, "max_quota": 7.50,
        "max_bollette": 3,
        "quota_singola": {2: 2.80, 3: 2.00, 4: 1.68, 5: 1.52, 6: 1.41, 7: 1.35},
    },
    "ambiziosa": {
        "min_sel": 4, "max_sel": 8,
        "min_quota": 8.00, "max_quota": None,
        "max_bollette": 3,
        "quota_singola": {4: 3.00, 5: 2.50, 6: 2.20, 7: 2.00, 8: 1.80},
    },
    "elite": {
        "min_sel": 2, "max_sel": 5,
        "min_quota": None, "max_quota": 8.00,
        "max_bollette": 3,
        "quota_singola": {2: 2.85, 3: 2.00, 4: 1.68, 5: 1.52},
    },
}

# Tolleranze per validazione
QUOTA_TOTALE_TOLERANCE_UP = 0.15    # 15% sopra il max
QUOTA_TOTALE_TOLERANCE_DOWN = 0.0   # 0% sotto il min (nessuna tolleranza)
QUOTA_SINGOLA_TOLERANCE = 0.10  # 10% — quota max 1.50 accetta fino a 1.65
MAX_RETRY_FEEDBACK = 1          # Numero di retry con feedback

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
4. Genera esattamente {max_bollette} bollette totali, divise in 4 categorie. OGNI CATEGORIA DEVE AVERE ALMENO 3 BOLLETTE:

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
9. Rispetta SEMPRE i limiti di quota per singola selezione indicati sopra. Se una selezione ha quota troppo alta per quella categoria, NON usarla in quella bolletta
10. Per ogni bolletta, scrivi una motivazione di 2 righe nel campo "reasoning" che spiega PERCHÉ hai scelto quelle selezioni. Cita i dati statistici: forma, classifica, trend, strisce, affidabilità, motivazione. Esempio: "Fiorentina in casa è 5° in classifica casa con forma al 65% e trend in salita, Benevento ha 4 vittorie consecutive e affidabilità 8.2/10". NO frasi generiche tipo "combinazione sicura" o "favorite nette"
11. Cerca di variare il numero di selezioni tra le bollette della stessa categoria, non mettere sempre lo stesso numero
12. ⚠️ DIVERSIFICAZIONE OBBLIGATORIA DEL NUMERO DI SELEZIONI ⚠️
   NON fare bollette con lo stesso numero di selezioni nella stessa categoria. Segui questi schemi:
   - OGGI (3 bollette): una da 2, una da 3, una da 4 selezioni
   - SELETTIVA (5 bollette): una da 2, una da 3, una da 4, una da 5, una da 3 selezioni
   - BILANCIATA (5 bollette): una da 3, una da 4, una da 5, una da 6, una da 4 selezioni
   - AMBIZIOSA (5 bollette): una da 4, una da 6, una da 8, una da 5, una da 7 selezioni
   - ELITE: una da 3, una da 4, una da 5 selezioni
   Questa regola è OBBLIGATORIA. Bollette tutte con lo stesso numero di selezioni verranno scartate.

═══════════════════════════════════════
DATI STATISTICI — COME LEGGERLI E USARLI
═══════════════════════════════════════

Ogni partita nel pool ha dati statistici sotto le selezioni. Usali per fare scelte INFORMATE, non alla cieca:

📊 **Classifica**: posizione in campionato, punti, vittorie-pareggi-sconfitte, gol fatti/subiti, posizione casa e trasferta separata. Una squadra 3° in casa ma 12° fuori casa è molto diversa. Controlla SEMPRE la classifica casa per la squadra di casa e la classifica trasferta per la squadra in trasferta.

🔥 **Forma (Lucifero)**: percentuale 0-100% che misura le performance nelle ultime 6 partite con pesi decrescenti (le più recenti contano di più). Sopra 60% = buona forma. Sotto 30% = crisi.

📈 **Trend**: 5 valori cronologici della forma (dal più vecchio al più recente). Se i numeri crescono (es. 30→45→60→72→80) la squadra sta migliorando. Se calano sta peggiorando. La freccia ↑ indica miglioramento, ↓ peggioramento. ATTENZIONE: una squadra in forte trend positivo potrebbe essere sottovalutata dalle quote.

🎯 **Motivazione**: cosa si gioca la squadra. LOTTA TITOLO/EUROPA/SALVEZZA = massima motivazione. BASSA/NEUTRALE = niente da chiedere, rischio calo mentale. Due squadre con motivazioni opposte (una lotta salvezza, l'altra non ha nulla da perdere) sono imprevedibili.

🔄 **Strisce**: serie consecutive attive (vittorie, sconfitte, Over 2.5, Under 2.5, GG, clean sheet, ecc.). IMPORTANTE: strisce molto lunghe (es. 7 vittorie consecutive) NON significano che continueranno — statisticamente la probabilità di interrompere la striscia AUMENTA. Usa le strisce per confermare un trend, non per scommettere ciecamente sulla continuazione.

🎯 **Affidabilità**: quanto la squadra rispetta il pronostico dei bookmaker (0-10). Un'affidabilità alta (>7) significa che la squadra tende a vincere quando è favorita e perdere quando è sfavorita — i risultati sono prevedibili. Un'affidabilità bassa (<4) significa risultati imprevedibili, sorprese frequenti. Per bollette selettive (sicure) preferisci squadre affidabili. Per bollette ambiziose puoi rischiare con le meno affidabili.

**Attacco** (0-100): potenza offensiva della squadra. Più è alto, più la squadra segna. Utile per pronostici Goal/Over.

**Difesa** (0-100): solidità difensiva della squadra. Più è alto, meno la squadra subisce gol. Utile per pronostici Under/NoGoal.

**Tecnica** (0-100): qualità tecnica complessiva della rosa.

**Valore rosa** (0-100): valore economico e qualità complessiva della rosa. Indica il gap di qualità tra le due squadre.

REGOLA D'ORO: non scegliere solo per quota e confidence. Una selezione a quota 1.40 con squadra in crisi di forma, motivazione bassa e trend in calo è MENO sicura di una a quota 1.55 con squadra in forma, motivata e affidabile.

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
            print(f"   ⚠️ JSON riparato via regex: {len(results)} bollette estratte")
            return results

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
    ))

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

    print(f"📦 Pool base: {len(pool)} selezioni da {len(docs)} partite ({', '.join(dates)})")
    return pool


def recover_from_yesterday(today_str):
    """Recupera selezioni valide da bollette saltate ieri (perse per 1 sola selezione)."""
    today = datetime.strptime(today_str, "%Y-%m-%d")
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    yesterday_bollette = list(db.bollette.find({"date": yesterday_str}))
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
        print(f"♻️ Recuperate {len(recovered)} selezioni da bollette saltate ieri")
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
        doc = db.classifiche.find_one({"league": league}, {"table": 1, "table_home": 1, "table_away": 1})
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
    ))
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
            sort=[("_id", -1)]
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
    ))
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

    print(f"📊 Arricchite {enriched_count}/{len(matches)} partite con dati statistici")
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
    """Calcola un punteggio di trend (-100 a +100).
    Positivo = miglioramento, negativo = peggioramento."""
    if not trend_values or len(trend_values) < 2:
        return 0
    diff = trend_values[-1] - trend_values[0]
    return max(-100, min(100, round(diff * (100 / 15))))


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


def calculate_solidity_coefficient(pool, classifiche_cache=None):
    """Calcola il Coefficiente di Solidità (0-100) per ogni selezione del pool.

    11 componenti indipendenti, ognuno emette score (0-100) + direzione.
    I pesi cambiano in base al mercato (SEGNO vs GOL).
    Le strisce usano la curva a campana (stessi valori di run_daily_predictions.py).
    Il contesto (confronto direzioni vs pronostico) è il moltiplicatore finale.

    Il coefficiente viene salvato in s['coeff_solidita'] per ogni selezione.
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
            s["coeff_solidita"] = None
            continue

        scores = {}      # {componente: punteggio 0-100}
        direzioni = {}   # {componente: [lista direzioni]}

        # Determina pesi in base al mercato
        mercato_type = _get_mercato_type(mercato, pronostico)
        PESI = PESI_SEGNO if mercato_type == "SEGNO" else PESI_GOL

        # === 1. LINEARITÀ V-N-P ===
        lin_home_tot = _linearita_vnp(ch.get("v"), ch.get("n"), ch.get("p"))
        lin_away_tot = _linearita_vnp(ca.get("v"), ca.get("n"), ca.get("p"))
        lin_home_ctx = _linearita_vnp(ch.get("v_casa"), ch.get("n_casa"), ch.get("p_casa"))
        lin_away_ctx = _linearita_vnp(ca.get("v_trasf"), ca.get("n_trasf"), ca.get("p_trasf"))

        if lin_home_tot is not None and lin_home_ctx is not None:
            lin_home = lin_home_tot * 0.4 + lin_home_ctx * 0.6
        else:
            lin_home = lin_home_tot or lin_home_ctx or 50
        if lin_away_tot is not None and lin_away_ctx is not None:
            lin_away = lin_away_tot * 0.4 + lin_away_ctx * 0.6
        else:
            lin_away = lin_away_tot or lin_away_ctx or 50

        pt_home = ch.get("pt", 0)
        pt_away = ca.get("pt", 0)
        distacco_pt = abs(pt_home - pt_away)
        bonus_distacco = min(15, distacco_pt * 0.8)

        scores["linearita"] = min(100, (lin_home + lin_away) / 2 + bonus_distacco)

        dir_lin = []
        if pt_home > pt_away + 5:
            dir_lin.append("SEGNO_1")
        elif pt_away > pt_home + 5:
            dir_lin.append("SEGNO_2")
        elif distacco_pt <= 5:
            dir_lin.append("SEGNO_X")
        direzioni["linearita"] = dir_lin

        # === 2. GF-GS ===
        league = s.get("league", "")
        tutte_squadre = classifiche_cache.get(league, {})

        gfgs_home_ctx = _analisi_gf_gs(ch, tutte_squadre, "casa")
        gfgs_away_ctx = _analisi_gf_gs(ca, tutte_squadre, "trasferta")

        att_h_pm = gfgs_home_ctx["gf_pm"]
        def_h_pm = gfgs_home_ctx["gs_pm"]
        att_a_pm = gfgs_away_ctx["gf_pm"]
        def_a_pm = gfgs_away_ctx["gs_pm"]

        # Soglie campionato
        media_camp_gf = sum(r.get("gf", 0) / max(r.get("g", 1), 1) for r in tutte_squadre.values()) / max(len(tutte_squadre), 1) if tutte_squadre else 1.3
        media_camp_gs = sum(r.get("gs", 0) / max(r.get("g", 1), 1) for r in tutte_squadre.values()) / max(len(tutte_squadre), 1) if tutte_squadre else 1.3

        att_h_forte = att_h_pm > media_camp_gf * 1.1
        att_h_debole = att_h_pm < media_camp_gf * 0.85
        def_a_debole = def_a_pm > media_camp_gs * 1.1
        def_a_forte = def_a_pm < media_camp_gs * 0.85
        att_a_forte = att_a_pm > media_camp_gf * 1.1
        att_a_debole = att_a_pm < media_camp_gf * 0.85
        def_h_debole = def_h_pm > media_camp_gs * 1.1
        def_h_forte = def_h_pm < media_camp_gs * 0.85

        # Incrocio + tipo partita
        tipo_parts = []
        incrocio_score = 50
        dir_gfgs = []

        if att_h_forte and def_a_debole:
            tipo_parts.append("casa segna bene + ospite subisce tanto → gol casa prevedibili")
            incrocio_score += 25
            dir_gfgs.extend(["SEGNO_1", "OVER", "GOAL"])
        elif att_h_debole and def_a_forte:
            tipo_parts.append("casa segna poco + ospite subisce poco → pochi gol casa prevedibili")
            incrocio_score += 20
            dir_gfgs.extend(["UNDER", "NOGOL"])
        elif att_h_forte and def_a_forte:
            tipo_parts.append("casa segna bene MA ospite difende bene → scontro aperto lato casa")
            incrocio_score -= 10
        elif att_h_debole and def_a_debole:
            tipo_parts.append("casa segna poco MA ospite subisce tanto → imprevedibile lato casa")
            incrocio_score -= 10

        if att_a_forte and def_h_debole:
            tipo_parts.append("ospite segna bene + casa subisce tanto → gol ospite prevedibili")
            incrocio_score += 25
            dir_gfgs.extend(["SEGNO_2", "OVER", "GOAL"])
        elif att_a_debole and def_h_forte:
            tipo_parts.append("ospite segna poco + casa subisce poco → pochi gol ospite prevedibili")
            incrocio_score += 20
            dir_gfgs.extend(["UNDER", "NOGOL"])
        elif att_a_forte and def_h_forte:
            tipo_parts.append("ospite segna bene MA casa difende bene → scontro aperto lato ospite")
            incrocio_score -= 10
        elif att_a_debole and def_h_debole:
            tipo_parts.append("ospite segna poco MA casa subisce tanto → imprevedibile lato ospite")
            incrocio_score -= 10

        if gfgs_home_ctx.get("outlier") or gfgs_away_ctx.get("outlier"):
            tipo_parts.append("almeno una squadra outlier (campionato a parte)")
            incrocio_score += 20

        incrocio_score = max(0, min(100, incrocio_score))
        tipo_partita = " | ".join(tipo_parts) if tipo_parts else "nessun incrocio chiaro"

        gol_attesi = att_h_pm + att_a_pm
        if gol_attesi > 2.8:
            dir_gfgs.append("OVER")
        elif gol_attesi < 2.2:
            dir_gfgs.append("UNDER")

        fascia_clarity_h = abs(gfgs_home_ctx.get("att_vs_fascia", 0)) + abs(gfgs_home_ctx.get("def_vs_fascia", 0))
        fascia_clarity_a = abs(gfgs_away_ctx.get("att_vs_fascia", 0)) + abs(gfgs_away_ctx.get("def_vs_fascia", 0))
        camp_clarity_h = abs(gfgs_home_ctx.get("att_vs_camp", 0)) + abs(gfgs_home_ctx.get("def_vs_camp", 0))
        camp_clarity_a = abs(gfgs_away_ctx.get("att_vs_camp", 0)) + abs(gfgs_away_ctx.get("def_vs_camp", 0))
        fascia_score = min(100, (fascia_clarity_h + fascia_clarity_a) * 0.8)
        camp_score = min(100, (camp_clarity_h + camp_clarity_a) * 0.5)
        scores["gf_gs"] = round(fascia_score * 0.4 + camp_score * 0.3 + incrocio_score * 0.3, 1)
        direzioni["gf_gs"] = dir_gfgs

        s["gfgs_home"] = gfgs_home_ctx
        s["gfgs_away"] = gfgs_away_ctx
        s["tipo_partita"] = tipo_partita

        # === 3. FORMA ===
        lh = s.get("lucifero_home_pct")
        la = s.get("lucifero_away_pct")
        if lh is not None and la is not None:
            diff_forma = abs(lh - la)
            avg_forma = (lh + la) / 2
            scores["forma"] = min(100, diff_forma * 1.5 + max(0, abs(avg_forma - 50) * 0.5))
            dir_forma = []
            if lh > la + 15:
                dir_forma.append("SEGNO_1")
            elif la > lh + 15:
                dir_forma.append("SEGNO_2")
            elif abs(lh - la) < 10:
                dir_forma.append("SEGNO_X")
            direzioni["forma"] = dir_forma
        else:
            scores["forma"] = 50
            direzioni["forma"] = []

        # === 4. TREND ===
        th = s.get("trend_home", [])
        ta = s.get("trend_away", [])
        trend_h = _trend_score(th)
        trend_a = _trend_score(ta)
        if trend_h != 0 or trend_a != 0:
            if (trend_h > 0 and trend_a < 0) or (trend_h < 0 and trend_a > 0):
                scores["trend"] = min(100, abs(trend_h - trend_a) * 0.7)
            else:
                scores["trend"] = min(100, max(abs(trend_h), abs(trend_a)) * 0.5)
        else:
            scores["trend"] = 40
        dir_trend = []
        if trend_h > 20 and trend_a < -10:
            dir_trend.append("SEGNO_1")
        elif trend_a > 20 and trend_h < -10:
            dir_trend.append("SEGNO_2")
        direzioni["trend"] = dir_trend

        # === 5. COERENZA FORMA-TREND ===
        # Forma attuale vs trend: se sono allineati → attendibile, se divergono → sotto/iper-performance
        if lh is not None and la is not None and th and ta:
            # Ultimo valore del trend normalizzato su scala 0-100 (come lucifero_pct)
            trend_h_pct = (th[-1] / 25.0) * 100 if th else lh
            trend_a_pct = (ta[-1] / 25.0) * 100 if ta else la
            # Gap tra forma attuale e trend
            gap_h = abs(lh - trend_h_pct)
            gap_a = abs(la - trend_a_pct)
            gap_medio = (gap_h + gap_a) / 2
            # Score: gap piccolo = coerente = attendibile (score alto)
            # gap grande = incoerente = meno prevedibile (score basso)
            scores["coerenza"] = max(0, min(100, round(100 - gap_medio * 2, 1)))
            # Direzione: sottoperformance = probabile risalita, iperperformance = probabile calo
            dir_coerenza = []
            # Home sottoperforma (forma bassa, trend alto) → probabile risalita → SEGNO_1
            if lh < trend_h_pct - 15:
                dir_coerenza.append("SEGNO_1")
            # Home iperperforma (forma alta, trend basso) → probabile calo → SEGNO_2
            elif lh > trend_h_pct + 15:
                dir_coerenza.append("SEGNO_2")
            # Away sottoperforma → probabile risalita → SEGNO_2
            if la < trend_a_pct - 15:
                dir_coerenza.append("SEGNO_2")
            # Away iperperforma → probabile calo → SEGNO_1
            elif la > trend_a_pct + 15:
                dir_coerenza.append("SEGNO_1")
            direzioni["coerenza"] = dir_coerenza
        else:
            scores["coerenza"] = 50
            direzioni["coerenza"] = []

        # === 6. MOTIVAZIONE ===
        mh = s.get("motivazione_home")
        ma = s.get("motivazione_away")
        if mh and ma:
            mot_h = mh.get("score", 10)
            mot_a = ma.get("score", 10)
            diff_mot = abs(mot_h - mot_a)
            avg_mot = (mot_h + mot_a) / 2
            scores["motivazione"] = min(100, diff_mot * 8 + max(0, abs(avg_mot - 10) * 3))
            dir_mot = []
            if mot_h > mot_a + 3:
                dir_mot.append("SEGNO_1")
            elif mot_a > mot_h + 3:
                dir_mot.append("SEGNO_2")
            direzioni["motivazione"] = dir_mot
        else:
            scores["motivazione"] = 50
            direzioni["motivazione"] = []

        # === 7. STRISCE (curva a campana) ===
        sh = s.get("streak_home", {})
        sa = s.get("streak_away", {})

        # Calcola score e direzioni separati per SEGNO e GOL
        streak_segno_h = _streak_normalized(sh, "SEGNO")
        streak_segno_a = _streak_normalized(sa, "SEGNO")
        streak_gol_h = _streak_normalized(sh, "GOL")
        streak_gol_a = _streak_normalized(sa, "GOL")

        # Score strisce: quanto è forte il segnale complessivo (indipendente dalla direzione)
        # Usiamo il mercato corretto per dare lo score
        if mercato_type == "SEGNO":
            raw_streak = (abs(streak_segno_h) + abs(streak_segno_a)) / 2
        else:
            raw_streak = (abs(streak_gol_h) + abs(streak_gol_a)) / 2
        # 0-1 → 0-100 (0 = nessun segnale, 1 = segnale massimo)
        scores["strisce"] = round(raw_streak * 100, 1)

        # Direzione strisce
        dir_strisce = []
        if streak_segno_h > 0.3:
            dir_strisce.append("SEGNO_1")
        if streak_segno_a > 0.3:
            dir_strisce.append("SEGNO_2")
        if streak_segno_h < -0.3:
            dir_strisce.append("SEGNO_2")  # home in crisi → vantaggio ospite
        if streak_segno_a < -0.3:
            dir_strisce.append("SEGNO_1")  # away in crisi → vantaggio casa
        if streak_gol_h > 0.3 or streak_gol_a > 0.3:
            # Strisce gol positive = over/goal attivi
            if sh.get("over25", 0) >= 3 or sa.get("over25", 0) >= 3:
                dir_strisce.append("OVER")
            if sh.get("gg", 0) >= 3 or sa.get("gg", 0) >= 3:
                dir_strisce.append("GOAL")
            if sh.get("under25", 0) >= 3 or sa.get("under25", 0) >= 3:
                dir_strisce.append("UNDER")
            if sh.get("clean_sheet", 0) >= 2 or sa.get("clean_sheet", 0) >= 2:
                dir_strisce.append("NOGOL")
            if sh.get("senza_segnare", 0) >= 2 or sa.get("senza_segnare", 0) >= 2:
                dir_strisce.append("NOGOL")
        direzioni["strisce"] = dir_strisce

        # === 8. AFFIDABILITÀ ===
        ac = s.get("affidabilita_casa")
        at = s.get("affidabilita_trasf")
        if ac is not None and at is not None:
            scores["affidabilita"] = min(100, ((ac + at) / 2) * 10)
        else:
            scores["affidabilita"] = 50
        direzioni["affidabilita"] = []  # l'affidabilità rafforza, non dà direzione

        # === 9. ATTACCO (separato) ===
        dh = s.get("dna_home")
        da = s.get("dna_away")
        if dh and da:
            att_h = dh.get("att", 50)
            att_a = da.get("att", 50)
            diff_att = abs(att_h - att_a)
            scores["attacco"] = min(100, diff_att * 2.5)
            dir_att = []
            if att_h > att_a + 15:
                dir_att.extend(["SEGNO_1", "OVER"])
            elif att_a > att_h + 15:
                dir_att.extend(["SEGNO_2", "OVER"])
            if att_h > 70 and att_a > 70:
                dir_att.append("OVER")
            elif att_h < 35 and att_a < 35:
                dir_att.append("UNDER")
            direzioni["attacco"] = dir_att
        else:
            scores["attacco"] = 50
            direzioni["attacco"] = []

        # === 10. DIFESA (separato) ===
        if dh and da:
            def_h = dh.get("def", 50)
            def_a = da.get("def", 50)
            diff_def = abs(def_h - def_a)
            scores["difesa"] = min(100, diff_def * 2.5)
            dir_def = []
            # Difesa forte = meno gol subiti = vantaggio nel segno
            if def_h > def_a + 15:
                dir_def.append("SEGNO_1")
            elif def_a > def_h + 15:
                dir_def.append("SEGNO_2")
            if def_h > 70 and def_a > 70:
                dir_def.extend(["UNDER", "NOGOL"])
            elif def_h < 35 and def_a < 35:
                dir_def.extend(["OVER", "GOAL"])
            direzioni["difesa"] = dir_def
        else:
            scores["difesa"] = 50
            direzioni["difesa"] = []

        # === 11. VALORE ROSA (separato, senza tecnica) ===
        if dh and da:
            val_h = dh.get("val", 50)
            val_a = da.get("val", 50)
            diff_val = abs(val_h - val_a)
            scores["valore_rosa"] = min(100, diff_val * 2)
            dir_val = []
            if val_h > val_a + 20:
                dir_val.append("SEGNO_1")
            elif val_a > val_h + 20:
                dir_val.append("SEGNO_2")
            direzioni["valore_rosa"] = dir_val
        else:
            scores["valore_rosa"] = 50
            direzioni["valore_rosa"] = []

        # === CONTESTO — Moltiplicatore finale ===
        # Conta quanti componenti supportano il pronostico vs quanti vanno contro
        mercato_up = mercato.upper() if mercato else ""
        pron_up = pronostico.upper() if pronostico else ""

        dir_supporto = set()
        if mercato_up == "SEGNO":
            if pron_up in ("1", "SEGNO_1"):
                dir_supporto = {"SEGNO_1"}
            elif pron_up in ("2", "SEGNO_2"):
                dir_supporto = {"SEGNO_2"}
            elif pron_up in ("X", "SEGNO_X"):
                dir_supporto = {"SEGNO_X"}
        elif mercato_up in ("DOPPIA_CHANCE", "DC"):
            if "1" in pron_up and "X" in pron_up:
                dir_supporto = {"SEGNO_1", "SEGNO_X"}
            elif "X" in pron_up and "2" in pron_up:
                dir_supporto = {"SEGNO_2", "SEGNO_X"}
            elif "1" in pron_up:
                dir_supporto = {"SEGNO_1", "SEGNO_X"}
            elif "2" in pron_up:
                dir_supporto = {"SEGNO_2", "SEGNO_X"}
        elif mercato_up == "GOL":
            if pron_up in ("GOAL", "GG"):
                dir_supporto = {"GOAL", "OVER"}
            elif pron_up in ("NO GOAL", "NOGOL", "NG"):
                dir_supporto = {"NOGOL", "UNDER"}
            elif "OVER" in pron_up:
                dir_supporto = {"OVER", "GOAL"}
            elif "UNDER" in pron_up:
                dir_supporto = {"UNDER", "NOGOL"}

        dir_contrarie = {
            "SEGNO_1": {"SEGNO_2"},
            "SEGNO_2": {"SEGNO_1"},
            "SEGNO_X": {"SEGNO_1", "SEGNO_2"},
            "OVER": {"UNDER"},
            "UNDER": {"OVER"},
            "GOAL": {"NOGOL"},
            "NOGOL": {"GOAL"},
        }
        dir_contro = set()
        for d in dir_supporto:
            dir_contro.update(dir_contrarie.get(d, set()))

        # Conta pesata: ogni componente vota con il suo peso
        peso_pro = 0
        peso_contro = 0
        peso_totale_dir = sum(PESI.get(k, 0) for k in direzioni if k != "strisce")
        # Le strisce hanno peso implicito dalla curva, aggiungiamo un peso fisso per il voto
        peso_strisce_dir = 5  # peso fisso per il voto direzione delle strisce
        peso_totale_dir += peso_strisce_dir

        for comp, dir_list in direzioni.items():
            if comp == "strisce":
                peso = peso_strisce_dir
            elif comp in PESI:
                peso = PESI[comp]
            else:
                continue
            for d in dir_list:
                if d in dir_supporto:
                    peso_pro += peso
                elif d in dir_contro:
                    peso_contro += peso

        # Bilancio: da -1 (tutto contro) a +1 (tutto a favore)
        if peso_totale_dir > 0:
            bilancio = (peso_pro - peso_contro) / peso_totale_dir
        else:
            bilancio = 0

        # === CALCOLO FINALE ===
        # 1. Somma pesata dei componenti (senza strisce — quelle hanno la curva)
        somma_pesata = sum(scores.get(k, 50) * PESI[k] for k in PESI)
        somma_pesi_max = sum(100 * PESI[k] for k in PESI)

        # 2. Contributo strisce (aggiunto alla somma)
        # Le strisce non hanno peso nella tabella, contribuiscono direttamente col loro score
        streak_contributo = scores.get("strisce", 50)
        somma_pesata += streak_contributo * peso_strisce_dir
        somma_pesi_max += 100 * peso_strisce_dir

        # 3. Normalizza su 0-100
        coeff_base = (somma_pesata / somma_pesi_max) * 100 if somma_pesi_max > 0 else 50

        # 4. Moltiplicatore contesto: bilancio -1/+1 → moltiplicatore 0.7-1.3
        moltiplicatore = 1.0 + bilancio * 0.3
        coeff_finale = coeff_base * moltiplicatore

        # Clamp 0-100
        coeff_finale = max(0, min(100, coeff_finale))

        s["coeff_solidita"] = round(coeff_finale, 1)
        s["coeff_base"] = round(coeff_base, 1)
        s["coeff_moltiplicatore"] = round(moltiplicatore, 2)
        s["coeff_dettaglio"] = {k: round(scores.get(k, 50), 1) for k in list(PESI.keys()) + ["strisce"]}
        s["coeff_direzioni"] = {k: v for k, v in direzioni.items() if v}
        s["coeff_contesto"] = {
            "bilancio": round(bilancio, 2),
            "pro": round(peso_pro, 1),
            "contro": round(peso_contro, 1),
            "mercato_type": mercato_type,
        }
        calculated += 1

    print(f"🔢 Coefficiente Solidità calcolato per {calculated}/{len(pool)} selezioni")


def _format_match_stats(s):
    """Formatta i dati statistici di una selezione per il prompt Mistral."""
    parts = []

    # Coefficiente di Solidità (con dettaglio e contesto)
    coeff = s.get("coeff_solidita")
    if coeff is not None:
        det = s.get("coeff_dettaglio", {})
        det_str = " | ".join(f"{k}:{v}" for k, v in det.items())
        ctx = s.get("coeff_contesto", {})
        molt = s.get("coeff_moltiplicatore", 1.0)
        base = s.get("coeff_base", coeff)
        parts.append(
            f"    SOLIDITA: {coeff}/100 (base:{base} x{molt}) "
            f"[{det_str}] "
            f"contesto: {ctx.get('pro',0)} pro / {ctx.get('contro',0)} contro ({ctx.get('mercato_type','?')})"
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
                    lines.append(
                        f"  {s['match_key']} | {s['mercato']}: {s['pronostico']} "
                        f"@ {s['quota']} | conf={s['confidence']} ★{s['stars']}{elite_tag}"
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


def call_mistral(pool_text, today_str):
    """Chiama Mistral per generare le bollette."""
    prompt = SYSTEM_PROMPT.replace("{max_bollette}", str(MAX_BOLLETTE)).replace("{today_date}", today_str)

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Ecco il pool di selezioni disponibili:\n{pool_text}\n\nComponi le bollette."},
        ],
        "temperature": 0.4,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
    }

    max_retries = 2
    for attempt in range(1, max_retries + 1):
        resp = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code == 429 and attempt < max_retries:
            wait = 10 * attempt
            print(f"⏳ Rate limit 429, retry {attempt}/{max_retries} tra {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break

    content = resp.json()["choices"][0]["message"]["content"]
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
        print(f"  ⚠️ Bolletta elite con solo {elite_count}/{n_sel} elite (servono 100%) — riclassificata")

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
        print(f"   🔄 Deduplica: {len(valid_docs)} → {len(filtered_docs)} bollette (selezioni ripetute nella stessa sezione)")
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
    ))

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
        print(f"   📋 Pool filtrato per {fascia}: {len(filtered_pool)}/{len(pool)} selezioni (quota max singola: {max_quota_singola})")
    else:
        filtered_pool = pool

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

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"Pool disponibile:\n{pool_text}\n\nComponi {count_needed} bollette {fascia}."},
        ],
        "temperature": 0.4,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
    }

    for attempt in range(3):
        resp = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code == 429 and attempt < 2:
            wait = 30 * (attempt + 1)
            print(f"   ⏳ Rate limit 429, attendo {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break

    content = resp.json()["choices"][0]["message"]["content"]

    try:
        return _sanitize_and_parse_json(content)
    except (json.JSONDecodeError, Exception) as e:
        print(f"   ⚠️ Parse JSON fallito ({e}), retry con istruzione esplicita...")
        # Retry: aggiungi istruzione esplicita sul formato
        payload["messages"].append({"role": "assistant", "content": content})
        payload["messages"].append({"role": "user", "content": "ERRORE: la risposta non è un JSON valido. Rispondi con SOLO un array JSON valido, senza testo prima o dopo. Formato: [{...}, {...}]"})
        resp2 = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=120)
        resp2.raise_for_status()
        content2 = resp2.json()["choices"][0]["message"]["content"]
        return _sanitize_and_parse_json(content2)


def build_feedback_prompt(errors, valid_docs, counters, today_str):
    """Costruisce il prompt di feedback per il retry con errori specifici."""
    lines = []

    # Bollette accettate
    if valid_docs:
        lines.append(f"✅ {len(valid_docs)} bollette ACCETTATE (non rigenerarle):")
        for doc in valid_docs:
            lines.append(f"  - {doc['tipo'].capitalize()}: {len(doc['selezioni'])} selezioni, "
                        f"quota {doc['quota_totale']}")
        lines.append("")

    # Errori specifici
    lines.append(f"❌ {len(errors)} problemi trovati. Correggi generando SOLO bollette sostitutive:\n")
    for err in errors:
        lines.append(f"- {err['feedback']}")

    # Stato distribuzione
    lines.append("\n📊 Distribuzione attuale:")
    for tipo in ["oggi", "selettiva", "bilanciata", "ambiziosa", "elite"]:
        actual = counters.get(tipo, 0)
        target = CATEGORY_CONSTRAINTS.get(tipo, {}).get("max_bollette", 5)
        target_min = 3 if tipo != "elite" else 1
        status = "✅" if actual >= target_min else "❌"
        lines.append(f"  {status} {tipo}: {actual}/{target_min}+ (max {target})")

    # Categorie mancanti
    missing = []
    for tipo in ["oggi", "selettiva", "bilanciata", "ambiziosa"]:
        actual = counters.get(tipo, 0)
        if actual < 3:
            missing.append(f"{3 - actual} bollette {tipo}")
    if missing:
        lines.append(f"\n⚠️ SERVONO ANCORA: {', '.join(missing)}")

    lines.append("\nGenera SOLO le bollette sostitutive/mancanti. Array JSON valido, niente testo.")

    return "\n".join(lines)


def call_mistral_retry(pool_text, today_str, original_response, feedback):
    """Richiama Mistral con la conversazione precedente + feedback sugli errori."""
    prompt = SYSTEM_PROMPT.replace("{max_bollette}", str(MAX_BOLLETTE)).replace("{today_date}", today_str)

    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }

    # Conversazione multi-turn: system → user → assistant (risposta originale) → user (feedback)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Ecco il pool di selezioni disponibili:\n{pool_text}\n\nComponi le bollette."},
        {"role": "assistant", "content": json.dumps(original_response, ensure_ascii=False)},
        {"role": "user", "content": feedback},
    ]

    payload = {
        "model": MISTRAL_MODEL,
        "messages": messages,
        "temperature": 0.3,  # Piu' bassa per correzione precisa
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
    }

    resp = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"]
    return _sanitize_and_parse_json(content)


def _check_feasibility(fascia, pool, today_str):
    """Verifica se e' matematicamente possibile generare bollette per questa fascia.
    Returns: (feasible: bool, reason: str, section_pool: list)
    """
    c = CATEGORY_CONSTRAINTS.get(fascia, {})
    min_sel = c.get("min_sel", 2)
    min_quota = c.get("min_quota")
    max_quota = c.get("max_quota")

    # Filtra pool per la sezione
    if fascia == "oggi":
        section_pool = [s for s in pool if s.get("match_date") == today_str]
    elif fascia == "elite":
        section_pool = [s for s in pool if s.get("elite")]
    else:
        section_pool = pool

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
        print(f"   ⛔ Impossibile: {reason}")
        return [], []

    print(f"   📋 Pool per {fascia}: {len(section_pool)} selezioni")

    # Per elite: limita richiesta in base al pool disponibile
    if fascia == "elite":
        unique_elite_matches = len(set(s.get("match_key", "") for s in section_pool))
        max_elite = max(2, unique_elite_matches // 2)  # ~metà delle partite uniche
        needed = min(needed, max_elite)
        print(f"   📋 Elite: {unique_elite_matches} partite uniche → max {needed} bollette")

    # Raccolta selezioni scartate per ricomposizione
    all_raw = []
    discarded_sels = []

    # Chiamata Mistral (retry 429 gestito dentro call_mistral_integration)
    raw = None
    try:
        raw = call_mistral_integration(section_pool, fascia, needed, today_str)
    except Exception as e:
        print(f"   ❌ Errore Mistral per {fascia}: {e}")
        return [], []

    if not isinstance(raw, list):
        print(f"   ❌ Risposta non valida per {fascia}")
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
        print(f"   ⚠️ {len(errors)} errori per {fascia}")
        for err in errors[:3]:
            print(f"      [{err['code']}] {err['feedback'][:100]}")

    # Se non abbastanza, retry fino a 2 volte con feedback specifico
    for retry_attempt in range(2):
        still_needed = needed - len(valid)
        if still_needed <= 0 or not errors:
            break
        print(f"   🔄 Retry {fascia} #{retry_attempt+1}: mancano {still_needed} bollette...")

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
                    print(f"   ✅ Retry: +{len(retry_valid)} bollette {fascia}")
                if errors:
                    print(f"   ⚠️ Retry: ancora {len(errors)} errori")
        except Exception as e:
            print(f"   ❌ Errore retry {fascia}: {e}")
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


def main():
    print("\n" + "=" * 60)
    print("🎫 GENERAZIONE BOLLETTE — Step 35 (Sequenziale)")
    print("=" * 60)

    # Supporta --date YYYY-MM-DD per generare bollette retroattive
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', type=str, default=None, help='Data YYYY-MM-DD')
    args, _ = parser.parse_known_args()
    today_str = args.date if args.date else datetime.now().strftime("%Y-%m-%d")
    is_retroactive = args.date is not None

    # 1. Costruisci pool base (pronostici AI)
    pool = build_pool(today_str, skip_time_filter=is_retroactive)
    recovered = recover_from_yesterday(today_str)
    if recovered:
        pool.extend(recovered)
    pool = deduplicate_pool(pool)
    print(f"📊 Pool AI: {len(pool)} selezioni uniche")

    # 1b. Filtra pool con pattern bollette (85 pattern Mixer + elite)
    pool_before = len(pool)
    pool = [s for s in pool if s.get("elite") or matches_bollette_pattern(s)]
    print(f"🎯 Filtro pattern: {pool_before} → {len(pool)} selezioni "
          f"({pool_before - len(pool)} escluse, {len(PATTERNS)} pattern caricati)")

    # 1c. Arricchisci pool con dati statistici (classifica, forma, trend, motivazioni, strisce, affidabilità, DNA)
    classifiche_cache = enrich_pool_with_stats(pool)

    # 1d. Calcola Coefficiente di Solidità (deterministico, Python)
    calculate_solidity_coefficient(pool, classifiche_cache)

    if len(pool) < 2:
        print("⚠️ Pool troppo piccolo (< 2 selezioni). Nessuna bolletta generata.")
        return

    # 2. Generazione sequenziale per sezione
    bollette_docs = []
    counters = {"oggi": 0, "elite": 0, "selettiva": 0, "bilanciata": 0, "ambiziosa": 0}

    # Target bollette per sezione
    SECTION_TARGETS = {
        "oggi":       3,
        "elite":      3,
        "selettiva":  3,
        "bilanciata": 3,
        "ambiziosa":  3,
    }

    SECTION_ORDER = ["oggi", "elite", "selettiva", "bilanciata", "ambiziosa"]
    all_discarded_sels = []

    for fascia in SECTION_ORDER:
        target = SECTION_TARGETS[fascia]
        print(f"\n{'─'*50}")
        print(f"📌 SEZIONE {fascia.upper()} — target: {target} bollette")
        print(f"{'─'*50}")

        new_bollette, discarded = _generate_for_section(
            fascia, target, pool, today_str, bollette_docs, counters
        )

        if new_bollette:
            bollette_docs.extend(new_bollette)
            print(f"   ✅ {fascia.upper()}: {len(new_bollette)} bollette generate")
        else:
            print(f"   ⚠️ {fascia.upper()}: nessuna bolletta valida")

        if discarded:
            all_discarded_sels.extend(discarded)

        # Pausa tra sezioni per evitare rate limit Mistral
        time.sleep(5)

    # 3. Ricomposizione automatica dalle bollette scartate
    missing = {f: 3 - counters.get(f, 0) for f in ["selettiva", "bilanciata", "ambiziosa"]}
    any_missing = any(v > 0 for v in missing.values())

    if any_missing and all_discarded_sels:
        print(f"\n{'─'*50}")
        print(f"🔄 RICOMPOSIZIONE — urna: {len(all_discarded_sels)} selezioni scartate")
        print(f"   Mancano: " + ", ".join(f"{f}={v}" for f, v in missing.items() if v > 0))
        print(f"{'─'*50}")

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
                print(f"   ✅ Ricomposte {len(bs)} {tipo}: quote {quotes}")
        else:
            print(f"   ⚠️ Nessuna bolletta ricomposta")

    if not bollette_docs:
        print("\n⚠️ Nessuna bolletta generata.")
        return

    # 4. Salva su MongoDB
    coll = db.bollette
    deleted = coll.delete_many({"date": today_str, "custom": {"$ne": True}})
    if deleted.deleted_count > 0:
        print(f"\n🗑️ Rimosse {deleted.deleted_count} bollette precedenti per {today_str}")

    coll.insert_many(bollette_docs)

    # 5. Riepilogo finale
    by_tipo = {}
    for b in bollette_docs:
        by_tipo.setdefault(b["tipo"], []).append(b)

    # Conta bollette Mistral vs urna
    n_recomposed = sum(1 for b in bollette_docs if b.get("reasoning", "").startswith("Ricomposta"))
    n_mistral = len(bollette_docs) - n_recomposed

    print(f"\n{'='*50}")
    print(f"🏆 RIEPILOGO FINALE:")
    print(f"   Mistral: {n_mistral}/15 bollette")
    if n_recomposed > 0:
        print(f"   Urna:    +{n_recomposed} ricomposte")
    print(f"   TOTALE:  {len(bollette_docs)}/15 {'✅' if len(bollette_docs) >= 15 else '⚠️'}")
    print(f"{'='*50}")

    print(f"\n✅ Salvate {len(bollette_docs)} bollette:")
    for tipo in SECTION_ORDER:
        if tipo in by_tipo:
            quotes = [b["quota_totale"] for b in by_tipo[tipo]]
            n_sel_list = [len(b["selezioni"]) for b in by_tipo[tipo]]
            r_count = sum(1 for b in by_tipo[tipo] if b.get("reasoning", "").startswith("Ricomposta"))
            urna_tag = f" (🔄 {r_count} da urna)" if r_count > 0 else ""
            print(f"   {tipo.upper()}: {len(by_tipo[tipo])} "
                  f"— quote: {quotes} — selezioni: {n_sel_list}{urna_tag}")


if __name__ == "__main__":
    main()
