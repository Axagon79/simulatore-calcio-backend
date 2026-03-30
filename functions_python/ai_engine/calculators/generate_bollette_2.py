"""
GENERATE BOLLETTE — Step 35 Pipeline Notturna
==============================================
Genera bollette (biglietti scommessa pre-composti) tramite Mistral AI.
Legge pronostici unified per 3 giorni, recupera selezioni valide da
bollette saltate, e produce max 10 bollette al giorno.
"""

import os, sys, re, json, time
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

try:
    import requests
except ImportError:
    print("❌ Modulo 'requests' non trovato. Installa con: pip install requests")
    sys.exit(1)

# --- CONFIGURAZIONE ---
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MISTRAL_MODEL = "mistral-small-latest"
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
    "selettiva":  (1.5, 5.0),
    "bilanciata": (5.0, 8.0),
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
        "min_quota": None, "max_quota": 5.00,
        "max_bollette": 5,
        "quota_singola": {2: 2.20, 3: 1.70, 4: 1.50, 5: 1.38},
    },
    "bilanciata": {
        "min_sel": 2, "max_sel": 7,
        "min_quota": 5.00, "max_quota": 8.00,
        "max_bollette": 5,
        "quota_singola": {2: 2.80, 3: 2.00, 4: 1.68, 5: 1.52, 6: 1.41, 7: 1.35},
    },
    "ambiziosa": {
        "min_sel": 4, "max_sel": 8,
        "min_quota": 8.00, "max_quota": None,
        "max_bollette": 5,
        "quota_singola": {4: 3.00, 5: 2.50, 6: 2.20, 7: 2.00, 8: 1.80},
    },
    "elite": {
        "min_sel": 3, "max_sel": 5,
        "min_quota": None, "max_quota": 8.00,
        "max_bollette": 99,  # libero
        "quota_singola": {3: 2.00, 4: 1.68, 5: 1.52},
    },
}

# Tolleranze per validazione
QUOTA_TOTALE_TOLERANCE = 0.05   # 5% — quota max 5.00 accetta fino a 5.25
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
   - ESATTAMENTE 3 bollette oggi

   📌 SELETTIVA — Campo "tipo": "selettiva"
   - Quota totale MASSIMO 5.00
   - Minimo 2, massimo 5 selezioni per bolletta
   - Quota max per SINGOLA selezione (varia in base al numero di selezioni):
     • 2 selezioni → ogni quota max 2.20
     • 3 selezioni → ogni quota max 1.70
     • 4 selezioni → ogni quota max 1.50
     • 5 selezioni → ogni quota max 1.38

   📌 BILANCIATA — Campo "tipo": "bilanciata"
   - Fino a 5 bollette bilanciate
   - Quota totale tra 5.00 e 8.00
   - Minimo 2, massimo 7 selezioni per bolletta
   - Quota max per SINGOLA selezione (varia in base al numero di selezioni):
     • 2 selezioni → ogni quota max 2.80
     • 3 selezioni → ogni quota max 2.00
     • 4 selezioni → ogni quota max 1.68
     • 5 selezioni → ogni quota max 1.52
     • 6 selezioni → ogni quota max 1.41
     • 7 selezioni → ogni quota max 1.35

   📌 AMBIZIOSA — Campo "tipo": "ambiziosa"
   - Fino a 5 bollette ambiziose!
   - Quota totale superiore a 8.0
   - Minimo 4, massimo 8 selezioni per bolletta
   - Quota max per SINGOLA selezione (varia in base al numero di selezioni):
     • 4 selezioni → ogni quota max 3.00
     • 5 selezioni → ogni quota max 2.50
     • 6 selezioni → ogni quota max 2.20
     • 7 selezioni → ogni quota max 2.00
     • 8 selezioni → ogni quota max 1.80

   📌 ELITE — Campo "tipo": "elite"
   - ALMENO il 70% delle selezioni DEVE essere ★ELITE dal POOL ELITE
   - Il restante 30% DEVE provenire dal POOL COMPLETO (selezioni NON elite)
   - ⚠️ REGOLA CRITICA: SFRUTTA SEMPRE il 30% non-elite per completare le bollette!
     Anche se ci sono poche selezioni elite (es. solo 2-3), componi comunque bollette da 3-5 selezioni aggiungendo 1-2 selezioni dal pool completo
   - Minimo elite richieste: 2 su 3 selezioni, 3 su 4, 4 su 5
   - Esempio con 3 selezioni: 2 elite + 1 non-elite con quota più alta (es. @2.0)
   - Esempio con 4 selezioni: 3 elite + 1 non-elite
   - NON fare bollette elite da sole 2 selezioni — il minimo è 3
   - Le bollette elite NON hanno vincolo sulle date: possono avere partite di oggi, domani o dopodomani liberamente
   - Quota totale MASSIMO 8.00
   - Minimo 3, massimo 5 selezioni per bolletta
   - Quota max per SINGOLA selezione (varia in base al numero di selezioni):
     • 3 selezioni → ogni quota max 2.00
     • 4 selezioni → ogni quota max 1.68
     • 5 selezioni → ogni quota max 1.52
   - Se non ci sono abbastanza selezioni elite nel pool, genera meno bollette elite (anche 0 se necessario)

   Le bollette "oggi" sono SEPARATE e DIVERSE dalle altre — non devono essere le stesse bollette delle altre fasce
   Distribuzione: ESATTAMENTE 3 oggi, fino a 5 selettive, fino a 5 bilanciate, fino a 5 ambiziose, elite libero (quante riesci)
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


def build_pool(today_str):
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

        # Escludi partite già iniziate
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

    content = resp.json()["choices"][0]["message"]["content"].strip()

    # Rimuovi markdown wrapping
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

    return json.loads(content)


def _classify_tipo(raw_tipo, selezioni, quota_totale, pool_index, today_str):
    """Determina il tipo della bolletta con validazione vincoli."""
    solo_oggi = all(s["match_date"] == today_str for s in selezioni)
    n_sel = len(selezioni)

    if raw_tipo == "elite":
        elite_count = sum(1 for s in selezioni if pool_index.get(
            (f"{s['home']} vs {s['away']}|{s['match_date']}", s['mercato'], s['pronostico']),
            {}
        ).get("elite", False))
        min_elite = {3: 2, 4: 3, 5: 4}.get(n_sel, max(2, int(n_sel * 0.7)))
        if elite_count >= min_elite:
            return "elite"
        print(f"  ⚠️ Bolletta elite con solo {elite_count}/{n_sel} elite — riclassificata")

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
            min_elite = {3: 2, 4: 3, 5: 4}.get(n_sel, max(2, int(n_sel * 0.7)))
            errors.append({
                "code": "ELITE_INSUFFICIENTE",
                "bolletta_idx": i, "tipo": "elite",
                "feedback": f"Bolletta #{i+1} (elite): solo {elite_count}/{n_sel} selezioni elite, "
                           f"servono almeno {min_elite}. Usa piu' selezioni dal POOL ELITE"
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

        # --- #4: quota totale troppo alta (tolleranza 5%) ---
        max_q = c.get("max_quota")
        if max_q is not None and quota_totale > max_q * (1 + QUOTA_TOTALE_TOLERANCE):
            errors.append({
                "code": "QUOTA_TOTALE_ALTA",
                "bolletta_idx": i, "tipo": tipo,
                "feedback": f"Bolletta #{i+1} ({tipo}): quota {quota_totale} > max {max_q}. "
                           f"Calcolo: {quote_str} = {quota_totale}. "
                           f"Sostituisci la selezione con quota piu' alta"
            })
            continue

        # --- #5: quota totale troppo bassa (tolleranza 5%) ---
        min_q = c.get("min_quota")
        if min_q is not None and quota_totale < min_q * (1 - QUOTA_TOTALE_TOLERANCE):
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


def build_extra_pool(today_str, existing_match_keys):
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

            # Salta partite già iniziate
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


def call_mistral_integration(pool, fascia, count_needed, today_str):
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
        "max_tokens": 4000,
    }

    resp = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

    return json.loads(content)


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
    }

    resp = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()

    content = resp.json()["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

    return json.loads(content)


def main():
    print("\n" + "=" * 60)
    print("🎫 GENERAZIONE BOLLETTE — Step 35")
    print("=" * 60)

    today_str = datetime.now().strftime("%Y-%m-%d")

    # 1. Costruisci pool
    pool = build_pool(today_str)

    # 2. Recupera selezioni da bollette saltate ieri
    recovered = recover_from_yesterday(today_str)
    if recovered:
        pool.extend(recovered)

    # 3. Deduplica
    pool = deduplicate_pool(pool)
    print(f"📊 Pool finale: {len(pool)} selezioni uniche")

    if len(pool) < 3:
        print("⚠️ Pool troppo piccolo (< 3 selezioni). Nessuna bolletta generata.")
        return

    # 4. Serializza e chiama Mistral
    pool_text = serialize_pool_for_prompt(pool)
    print(f"🤖 Chiamata Mistral ({MISTRAL_MODEL})...")

    try:
        raw_bollette = call_mistral(pool_text, today_str)
    except json.JSONDecodeError:
        # #15: JSON malformato — retry con temperatura piu' bassa
        print("  ⚠️ JSON malformato, retry...")
        try:
            raw_bollette = call_mistral(pool_text, today_str)
        except Exception as e:
            print(f"❌ Errore Mistral (retry JSON): {e}")
            return
    except Exception as e:
        print(f"❌ Errore Mistral: {e}")
        return

    if not isinstance(raw_bollette, list):
        print(f"❌ Risposta Mistral non e' un array: {type(raw_bollette)}")
        return

    print(f"📝 Mistral ha proposto {len(raw_bollette)} bollette")

    # 5. Valida con raccolta errori
    bollette_docs, validation_errors, counters = validate_with_errors(
        raw_bollette, pool, today_str
    )

    print(f"   ✅ {len(bollette_docs)} valide, ❌ {len(validation_errors)} errori")
    for err in validation_errors:
        print(f"   ⚠️ [{err['code']}] {err['feedback'][:120]}")

    # 6. Retry con feedback se ci sono errori significativi
    if validation_errors and MAX_RETRY_FEEDBACK > 0:
        # Calcola quante bollette mancano
        missing_count = 0
        for tipo in ["oggi", "selettiva", "bilanciata", "ambiziosa"]:
            actual = counters.get(tipo, 0)
            if actual < 3:
                missing_count += 3 - actual

        if missing_count > 0 or len(validation_errors) >= 3:
            print(f"\n🔄 Retry con feedback ({len(validation_errors)} errori, "
                  f"{missing_count} bollette mancanti)...")

            feedback = build_feedback_prompt(
                validation_errors, bollette_docs, counters, today_str
            )

            try:
                retry_raw = call_mistral_retry(
                    pool_text, today_str, raw_bollette, feedback
                )
                if isinstance(retry_raw, list):
                    retry_valid, retry_errors, counters = validate_with_errors(
                        retry_raw, pool, today_str, existing_counters=counters,
                        existing_docs=bollette_docs
                    )
                    if retry_valid:
                        bollette_docs.extend(retry_valid)
                        print(f"   ✅ Retry: +{len(retry_valid)} bollette valide")
                    if retry_errors:
                        print(f"   ⚠️ Retry: ancora {len(retry_errors)} errori")
                        for err in retry_errors[:5]:
                            print(f"      [{err['code']}] {err['feedback'][:100]}")
            except Exception as e:
                print(f"   ❌ Errore retry: {e}")

    if not bollette_docs:
        print("⚠️ Nessuna bolletta valida dopo validazione e retry.")
        return

    # 7. Integrazione per fasce ancora carenti (dopo retry)
    by_tipo = {}
    for b in bollette_docs:
        by_tipo.setdefault(b["tipo"], []).append(b)

    fasce_carenti = {}
    for fascia in ["oggi", "selettiva", "bilanciata", "ambiziosa"]:
        count = len(by_tipo.get(fascia, []))
        if count < 3:
            fasce_carenti[fascia] = 3 - count

    if fasce_carenti:
        print(f"\n⚠️ Fasce ancora carenti: "
              f"{', '.join(f'{f} (mancano {n})' for f, n in fasce_carenti.items())}")
        print("🔄 Caricamento pool esteso da h2h_by_round...")

        existing_match_keys = set(s["match_key"] for s in pool)
        extra = build_extra_pool(today_str, existing_match_keys)
        extended_pool = pool + extra
        extended_pool = deduplicate_pool(extended_pool)
        print(f"📊 Pool esteso: {len(extended_pool)} selezioni ({len(extra)} extra)")

        for fascia, needed in fasce_carenti.items():
            print(f"🤖 Integrazione {fascia}: generazione {needed} bollette...")
            try:
                # Per bollette "oggi": usa SOLO partite di oggi
                integration_pool = [s for s in extended_pool if s.get("match_date") == today_str] if fascia == "oggi" else extended_pool
                raw_extra = call_mistral_integration(
                    integration_pool, fascia, needed, today_str
                )
                if isinstance(raw_extra, list):
                    extra_valid, _, counters = validate_with_errors(
                        raw_extra, extended_pool, today_str,
                        existing_counters=counters,
                        existing_docs=bollette_docs
                    )
                    # Fix #16: limita al numero richiesto
                    extra_valid = extra_valid[:needed]
                    # Fix: bollette "oggi" devono avere SOLO partite di oggi
                    if fascia == "oggi":
                        extra_valid = [
                            doc for doc in extra_valid
                            if all(s.get("match_date") == today_str for s in doc.get("selezioni", []))
                        ]
                    existing_count = len(by_tipo.get(fascia, []))
                    for doc in extra_valid:
                        existing_count += 1
                        doc["tipo"] = fascia
                        doc["label"] = f"{fascia.capitalize()} #{existing_count}"
                        doc["_integrated"] = True
                    bollette_docs.extend(extra_valid)
                    by_tipo.setdefault(fascia, []).extend(extra_valid)
                    print(f"   ✅ Aggiunte {len(extra_valid)} bollette {fascia}")
                else:
                    print(f"   ❌ Risposta non valida per {fascia}")
            except Exception as e:
                print(f"   ❌ Errore integrazione {fascia}: {e}")

    # 8. Salva su MongoDB
    coll = db.bollette
    deleted = coll.delete_many({"date": today_str, "custom": {"$ne": True}})
    if deleted.deleted_count > 0:
        print(f"🗑️ Rimosse {deleted.deleted_count} bollette precedenti per {today_str}")

    coll.insert_many(bollette_docs)

    # Riepilogo finale
    by_tipo = {}
    for b in bollette_docs:
        by_tipo.setdefault(b["tipo"], []).append(b)

    print(f"\n✅ Salvate {len(bollette_docs)} bollette:")
    for tipo in ["oggi", "elite", "selettiva", "bilanciata", "ambiziosa"]:
        if tipo in by_tipo:
            quotes = [b["quota_totale"] for b in by_tipo[tipo]]
            n_sel_list = [len(b["selezioni"]) for b in by_tipo[tipo]]
            integrated = sum(1 for b in by_tipo[tipo] if b.get("_integrated"))
            extra_label = f" ({integrated} integrate)" if integrated else ""
            print(f"   {tipo.upper()}: {len(by_tipo[tipo])}{extra_label} "
                  f"— quote: {quotes} — selezioni: {n_sel_list}")


if __name__ == "__main__":
    main()
