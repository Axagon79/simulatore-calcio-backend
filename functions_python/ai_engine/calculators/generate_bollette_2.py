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
# 33 pattern (B1-B33) da report elite+bizarre + 150 pattern hybrid
# Un pronostico entra nel pool non-elite se matcha almeno uno di questi

def _match_pattern_b(sel):
    """Controlla se una selezione matcha uno dei 33 pattern B1-B33 (elite+bizarre)."""
    t = sel.get("mercato", "")
    q = sel.get("quota", 0) or 0
    c = sel.get("confidence", 0) or 0
    s = sel.get("stars", 0) or 0
    src = sel.get("source", "")
    rt = sel.get("routing_rule", "")
    e = sel.get("edge", 0) or 0
    pr = sel.get("pronostico", "")

    # B1: SEGNO | quota 1.50-1.79 | confidence 60-69
    if t == "SEGNO" and 1.50 <= q < 1.80 and 60 <= c <= 69: return True
    # B2: SEGNO | quota 1.50-1.79 | confidence 80-100
    if t == "SEGNO" and 1.50 <= q < 1.80 and 80 <= c <= 100: return True
    # B3: SEGNO | quota 2.00-2.49 | confidence 70-79
    if t == "SEGNO" and 2.00 <= q < 2.50 and 70 <= c <= 79: return True
    # B4: SEGNO | quota 1.80-1.99 | stelle 4-4.5
    if t == "SEGNO" and 1.80 <= q < 2.00 and 4.0 <= s <= 4.5: return True
    # B5: GOL | quota 1.50-1.79 | confidence 80-100
    if t == "GOL" and 1.50 <= q < 1.80 and 80 <= c <= 100: return True
    # B6: SEGNO | edge 5-9
    if t == "SEGNO" and 5 <= e <= 9: return True
    # B7: GOL | source A+S_o25_s6_conv
    if t == "GOL" and src == "A+S_o25_s6_conv": return True
    # B8: DOPPIA_CHANCE | quota 1.40-1.49 | confidence >=60
    if t == "DOPPIA_CHANCE" and 1.40 <= q < 1.50 and c >= 60: return True
    # B9: EXTREME conf>=70 stelle>=3.5 quota<1.60 DOPPIA_CHANCE
    if t == "DOPPIA_CHANCE" and c >= 70 and s >= 3.5 and q < 1.60: return True
    # B10: confidence>=85 GOL
    if t == "GOL" and c >= 85: return True
    # B11: source A+S_mg stelle>=3.0
    if src == "A+S_mg" and s >= 3.0: return True
    # B12: routing consensus_both DOPPIA_CHANCE stelle>=3
    if t == "DOPPIA_CHANCE" and rt == "consensus_both" and s >= 3: return True
    # B13: DOPPIA_CHANCE quota 1.40-1.49 source A+S
    if t == "DOPPIA_CHANCE" and 1.40 <= q < 1.50 and src == "A+S": return True
    # B14: DOPPIA_CHANCE quota 1.40-1.49 source C_combo96
    if t == "DOPPIA_CHANCE" and 1.40 <= q < 1.50 and src == "C_combo96": return True
    # B15: GOL quota 1.60-1.79 source C_mg
    if t == "GOL" and 1.60 <= q < 1.80 and src == "C_mg": return True
    # B16: DOPPIA_CHANCE quota 1.40-1.49 stelle>=3
    if t == "DOPPIA_CHANCE" and 1.40 <= q < 1.50 and s >= 3: return True
    # B17: source C_combo96 stelle>=3.0
    if src == "C_combo96" and s >= 3.0: return True
    # B18: GOL quota 1.30-1.39 confidence>=60
    if t == "GOL" and 1.30 <= q < 1.40 and c >= 60: return True
    # B19: routing combo_96_dc_flip DOPPIA_CHANCE stelle>=3
    if t == "DOPPIA_CHANCE" and rt == "combo_96_dc_flip" and s >= 3: return True
    # B20: DOPPIA_CHANCE quota 1.40-1.49
    if t == "DOPPIA_CHANCE" and 1.40 <= q < 1.50: return True
    # B21: DOPPIA_CHANCE quota 1.40-1.49 source C_screm
    if t == "DOPPIA_CHANCE" and 1.40 <= q < 1.50 and src == "C_screm": return True
    # B22: SEGNO quota 1.60-1.79 stelle>=3
    if t == "SEGNO" and 1.60 <= q < 1.80 and s >= 3: return True
    # B23: source A stelle>=3.0
    if src == "A" and s >= 3.0: return True
    # B24: EXTREME conf>=70 stelle>=3.5 quota<1.60 GOL
    if t == "GOL" and c >= 70 and s >= 3.5 and q < 1.60: return True
    # B25: EXTREME conf>=80 stelle>=3 GOL
    if t == "GOL" and c >= 80 and s >= 3: return True
    # B26: edge>=20 conf>=70 SEGNO
    if t == "SEGNO" and e >= 20 and c >= 70: return True
    # B27: SEGNO quota 1.80-1.99 conf>=70
    if t == "SEGNO" and 1.80 <= q < 2.00 and c >= 70: return True
    # B28: routing single GOL stelle>=3
    if t == "GOL" and rt == "single" and s >= 3: return True
    # B29: stelle>=4.0 SEGNO
    if t == "SEGNO" and s >= 4.0: return True
    # B30: SEGNO quota 1.60-1.79 source C
    if t == "SEGNO" and 1.60 <= q < 1.80 and src == "C": return True
    # B31: pronostico 1 conf>=70
    if pr == "1" and c >= 70: return True
    # B32: SEGNO quota 2.00-2.49 conf>=70
    if t == "SEGNO" and 2.00 <= q < 2.50 and c >= 70: return True
    # B33: SEGNO quota 1.60-1.79 conf>=60
    if t == "SEGNO" and 1.60 <= q < 1.80 and c >= 60: return True
    return False


def _check_hybrid_condition(cond_str, sel):
    """Verifica una singola condizione hybrid su una selezione."""
    t = sel.get("mercato", "")
    q = sel.get("quota", 0) or 0
    c = sel.get("confidence", 0) or 0
    s = sel.get("stars", 0) or 0
    src = sel.get("source", "")
    rt = sel.get("routing_rule", "")
    st = sel.get("stake", 0) or 0
    pr = sel.get("pronostico", "")
    cs = cond_str.strip()

    m = re.match(r"conf(\d+)-(\d+)", cs)
    if m: return int(m.group(1)) <= c <= int(m.group(2))
    m = re.match(r"conf>=(\d+)", cs)
    if m: return c >= int(m.group(1))
    m = re.match(r"stelle([\d.]+)-([\d.]+)", cs)
    if m: return float(m.group(1)) <= s < float(m.group(2))
    m = re.match(r"stelle>=([\d.]+)", cs)
    if m: return s >= float(m.group(1))
    m = re.match(r"q([\d.]+)-([\d.]+)", cs)
    if m: return float(m.group(1)) <= q <= float(m.group(2)) + 0.001
    m = re.match(r"tipo=(.+)", cs)
    if m: return t == m.group(1)
    m = re.match(r"src=(.+)", cs)
    if m: return src == m.group(1)
    m = re.match(r"routing=(.+)", cs)
    if m: return rt == m.group(1)
    m = re.match(r"pron=(.+)", cs)
    if m: return pr == m.group(1)
    m = re.match(r"stake>=(\d+)", cs)
    if m: return st >= int(m.group(1))
    return False


def _load_hybrid_patterns():
    """Carica i 150 pattern hybrid dal file txt più recente."""
    # Cerca nella cartella _analisi_pattern
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pattern_dir = os.path.join(base_dir, "..", "..", "..", "_analisi_pattern")
    pattern_file = os.path.join(pattern_dir, "hybrid_75_by_profit.txt")

    if not os.path.exists(pattern_file):
        print("⚠️ File hybrid_75_by_profit.txt non trovato, skip pattern hybrid")
        return []

    patterns = []
    with open(pattern_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line[0] not in "0123456789":
                continue
            parts = line.split()
            # Estrai pattern: dal secondo token fino al profit (+N.N o -N.N)
            pat_parts = []
            for p in parts[1:]:
                if p.startswith("+") or p.startswith("-"):
                    try:
                        float(p)
                        break
                    except ValueError:
                        pass
                pat_parts.append(p)
            pattern = " ".join(pat_parts)
            conditions = [c.strip() for c in pattern.split("+")]
            patterns.append(conditions)

    return patterns


# Carica pattern hybrid all'avvio
_HYBRID_PATTERNS = _load_hybrid_patterns()


def matches_bollette_pattern(sel):
    """Controlla se una selezione matcha almeno uno dei 183 pattern (B1-B33 + hybrid).
    Usato per filtrare il pool prima di passarlo a Mistral nelle sezioni non-elite."""
    # Check B1-B33
    if _match_pattern_b(sel):
        return True
    # Check 150 hybrid
    for conds in _HYBRID_PATTERNS:
        if all(_check_hybrid_condition(c, sel) for c in conds):
            return True
    return False


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
SYSTEM_PROMPT = """Sei un tipster professionista con 20 anni di esperienza nel mondo delle scommesse sportive. Hai una conoscenza profonda del calcio europeo e mondiale, delle dinamiche delle quote e della gestione del rischio.

Il tuo compito è comporre bollette scommesse intelligenti a partire da un pool di pronostici generati da un sistema AI. Ricevi selezioni divise per giornata, ognuna con: partita, mercato, pronostico, quota, confidence (0-100), stelle (1-5).

Usa la tua esperienza per costruire bollette equilibrate, evitando trappole classiche: non accumulare troppe quote basse che non rendono, non mischiare mercati incompatibili, e distribuisci il rischio con intelligenza. Ragiona come un professionista che deve proteggere il bankroll e massimizzare il valore.

Rispetta TUTTE queste regole:

═══════════════════════════════════════
REGOLE COMPOSIZIONE
═══════════════════════════════════════

1. Ogni partita può apparire UNA SOLA VOLTA per bolletta, con UN SOLO mercato
2. La stessa partita con lo stesso pronostico PUÒ apparire in bollette diverse, ma ATTENZIONE: non ripetere la stessa selezione in tutte le bollette. Se quella partita va male, perdiamo tutte le bollette in cui compare. Varia e diversifica
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
5. Si consiglia di dare la preferenza a selezioni con confidence e stelle alte, ma fai affidamento alla tua esperienza: se una selezione con stelle più basse ti convince per il contesto della bolletta, usala
5b. ⭐ SELEZIONI ELITE ⭐ — Le selezioni marcate con ★ELITE nel pool sono pronostici che matchano pattern storicamente vincenti (hit rate > 80%). Dai loro PRIORITÀ ASSOLUTA: ogni bolletta dovrebbe contenere almeno 1 selezione elite se disponibile. Non forzare combinazioni innaturali, ma a parità di scelta preferisci SEMPRE una selezione elite
6. ⚠️⚠️⚠️ REGOLA OBBLIGATORIA — ALMENO 1 PARTITA DI OGGI ⚠️⚠️⚠️
   Per le bollette selettiva/bilanciata/ambiziosa: OGNI SINGOLA bolletta DEVE contenere ALMENO 1 partita di OGGI ({today_date}).
   Questa regola NON è opzionale. Una bolletta senza partite di oggi è INVALIDA e verrà scartata.
   L'utente vuole SEMPRE avere qualcosa da seguire subito. Se non ci sono abbastanza partite oggi, metti quelle che ci sono e completa con domani/dopodomani.
   CONTROLLA ogni bolletta prima di inviarla: c'è almeno 1 selezione con data {today_date}? Se no, aggiungila.
8. Non creare bollette con una sola selezione — almeno 2 selezioni per bolletta (selettiva: 2-5, bilanciata: 2-7, ambiziosa: 4-8)
9. Rispetta SEMPRE i limiti di quota per singola selezione indicati sopra. Se una selezione ha quota troppo alta per quella categoria, NON usarla in quella bolletta
10. Per ogni bolletta, scrivi una breve motivazione (1 frase) che spiega la logica
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


def serialize_pool_for_prompt(pool):
    """Serializza il pool in formato compatto per il prompt Mistral.
    Pool elite separato dal pool completo per chiarezza."""

    elite_pool = [s for s in pool if s.get("elite")]
    lines = []

    # Pool elite separato — per bollette tipo "elite"
    if elite_pool:
        lines.append("\n╔══════════════════════════════════════╗")
        lines.append("║  POOL ELITE — usa SOLO queste per    ║")
        lines.append("║  bollette di tipo \"elite\"             ║")
        lines.append("╚══════════════════════════════════════╝")
        by_date_elite = {}
        for s in elite_pool:
            by_date_elite.setdefault(s["match_date"], []).append(s)
        for date in sorted(by_date_elite.keys()):
            lines.append(f"\n  --- {date} ---")
            for s in by_date_elite[date]:
                lines.append(
                    f"  {s['match_key']} | {s['mercato']}: {s['pronostico']} "
                    f"@ {s['quota']} | conf={s['confidence']} ★{s['stars']} ★ELITE"
                )
        lines.append(f"\n  Totale selezioni elite: {len(elite_pool)}")
    else:
        lines.append("\n⚠️ Nessuna selezione elite disponibile — NON generare bollette elite")

    # Pool completo — per tutte le altre bollette
    lines.append("\n╔══════════════════════════════════════╗")
    lines.append("║  POOL COMPLETO — per bollette oggi,  ║")
    lines.append("║  selettiva, bilanciata, ambiziosa     ║")
    lines.append("╚══════════════════════════════════════╝")
    by_date = {}
    for s in pool:
        by_date.setdefault(s["match_date"], []).append(s)
    for date in sorted(by_date.keys()):
        lines.append(f"\n=== {date} ===")
        for s in by_date[date]:
            elite_tag = " ★ELITE" if s.get("elite") else ""
            lines.append(
                f"  {s['match_key']} | {s['mercato']}: {s['pronostico']} "
                f"@ {s['quota']} | conf={s['confidence']} ★{s['stars']}{elite_tag}"
            )

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

    # --- Post-loop: #14 selezione troppo ripetuta ---
    if len(valid_docs) >= 4:
        sel_count = {}
        for doc in valid_docs:
            for s in doc["selezioni"]:
                key = f"{s['home']} vs {s['away']}|{s['match_date']}|{s['mercato']}:{s['pronostico']}"
                sel_count[key] = sel_count.get(key, 0) + 1
        max_appearances = max(2, len(valid_docs) // 2)
        for key, count in sel_count.items():
            if count > max_appearances:
                errors.append({
                    "code": "SELEZIONE_TROPPO_RIPETUTA",
                    "bolletta_idx": -1, "tipo": "cross",
                    "feedback": f"Selezione {key} appare in {count}/{len(valid_docs)} bollette. "
                               f"Max consigliato: {max_appearances}. Diversifica"
                })

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

    prompt = f"""Sei un tipster professionista. Devi comporre esattamente {count_needed} bollette di tipo "{fascia}".
{quota_rule}

REGOLE:
1. Ogni partita UNA SOLA VOLTA per bolletta, con UN SOLO mercato
2. {sel_rule}
3. {quota_singola_rule}
4. Le selezioni con _extra_pool=true sono partite fuori dal sistema AI — usale se servono
5. ⚠️ OBBLIGATORIO: almeno 1 selezione con data {today_str} in ogni bolletta (escluso elite)
6. Diversifica il numero di selezioni tra bollette: {div_text}
7. Restituisci SOLO un array JSON valido. Nessun testo prima o dopo

[
  {{
    "tipo": "{fascia}",
    "selezioni": [
      {{ "match_key": "Home vs Away|YYYY-MM-DD", "mercato": "SEGNO", "pronostico": "1" }}
    ],
    "reasoning": "Motivazione breve"
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

        # Bolletta valida — costruisci documento
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

    # 1b. Filtra pool con pattern bollette (183 pattern + elite)
    pool_before = len(pool)
    pool = [s for s in pool if s.get("elite") or matches_bollette_pattern(s)]
    print(f"🎯 Filtro pattern: {pool_before} → {len(pool)} selezioni "
          f"({pool_before - len(pool)} escluse, {len(_HYBRID_PATTERNS)} pattern hybrid caricati)")

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

    print(f"\n✅ Salvate {len(bollette_docs)} bollette:")
    for tipo in SECTION_ORDER:
        if tipo in by_tipo:
            quotes = [b["quota_totale"] for b in by_tipo[tipo]]
            n_sel_list = [len(b["selezioni"]) for b in by_tipo[tipo]]
            print(f"   {tipo.upper()}: {len(by_tipo[tipo])} "
                  f"— quote: {quotes} — selezioni: {n_sel_list}")


if __name__ == "__main__":
    main()
