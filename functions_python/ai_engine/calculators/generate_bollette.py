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
    "selettiva":  (1.5, 3.0),
    "bilanciata": (3.0, 8.0),
    "ambiziosa":  (8.0, 999.0),
}

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
   - Oggi: SOLO partite di oggi ({today_date}). Campo "tipo": "oggi". Quote libere, qualsiasi fascia. Minimo 3 bollette
   - Selettiva: quota totale MASSIMO 3.0 — la quota moltiplicata di tutte le selezioni NON deve superare 3.0
   - Bilanciata: quota totale tra 3.0 e 8.0
   - Ambiziosa: quota totale superiore a 8.0 — usa più selezioni (5-10) o mercati con quote alte (1X2, Under 1.5)
   Le bollette "oggi" sono SEPARATE e DIVERSE dalle altre — non devono essere le stesse bollette delle altre fasce
   Distribuzione consigliata: 3 oggi, 5 selettive, 5 bilanciate, 5 ambiziose
   Quante selezioni mettere in ogni bolletta lo decidi tu in base alla tua esperienza
5. Si consiglia di dare la preferenza a selezioni con confidence e stelle alte, ma fai affidamento alla tua esperienza: se una selezione con stelle più basse ti convince per il contesto della bolletta, usala
5b. ⭐ SELEZIONI ELITE ⭐ — Le selezioni marcate con ★ELITE nel pool sono pronostici che matchano pattern storicamente vincenti (hit rate > 80%). Dai loro PRIORITÀ ASSOLUTA: ogni bolletta dovrebbe contenere almeno 1 selezione elite se disponibile. Non forzare combinazioni innaturali, ma a parità di scelta preferisci SEMPRE una selezione elite
6. ⚠️⚠️⚠️ REGOLA OBBLIGATORIA — ALMENO 1 PARTITA DI OGGI ⚠️⚠️⚠️
   Per le bollette selettiva/bilanciata/ambiziosa: OGNI SINGOLA bolletta DEVE contenere ALMENO 1 partita di OGGI ({today_date}).
   Questa regola NON è opzionale. Una bolletta senza partite di oggi è INVALIDA e verrà scartata.
   L'utente vuole SEMPRE avere qualcosa da seguire subito. Se non ci sono abbastanza partite oggi, metti quelle che ci sono e completa con domani/dopodomani.
   CONTROLLA ogni bolletta prima di inviarla: c'è almeno 1 selezione con data {today_date}? Se no, aggiungila.
8. Non creare bollette con una sola selezione — almeno 2 selezioni per bolletta
9. Massimo 10 selezioni per bolletta. Se hai in mente più di 10, dividi in 2 bollette separate
10. Per ogni bolletta, scrivi una breve motivazione (1 frase) che spiega la logica

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
    """Serializza il pool in formato compatto per il prompt Mistral."""
    by_date = {}
    for s in pool:
        d = s["match_date"]
        by_date.setdefault(d, []).append(s)

    lines = []
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
        resp = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
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


def validate_and_build(raw_bollette, pool, today_str):
    """Valida le bollette di Mistral e costruisce i documenti MongoDB."""
    # Indice veloce del pool
    pool_index = {}
    for s in pool:
        key = (s["match_key"], s["mercato"], s["pronostico"])
        pool_index[key] = s

    bollette_docs = []
    counters = {"oggi": 0, "selettiva": 0, "bilanciata": 0, "ambiziosa": 0}

    for raw in raw_bollette:
        selezioni_raw = raw.get("selezioni", [])
        if len(selezioni_raw) < 2:
            continue

        selezioni = []
        valid = True
        quota_totale = 1.0

        for sel in selezioni_raw:
            key = (sel.get("match_key", ""), sel.get("mercato", ""), sel.get("pronostico", ""))
            pool_entry = pool_index.get(key)
            if not pool_entry:
                print(f"  ⚠️ Selezione non trovata nel pool: {key}")
                valid = False
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

        if not valid or not selezioni:
            continue

        # Verifica unicità partita per bolletta
        match_keys_in_bolletta = [s["home"] + s["away"] + s["match_date"] for s in selezioni]
        if len(match_keys_in_bolletta) != len(set(match_keys_in_bolletta)):
            print(f"  ⚠️ Bolletta scartata: partita duplicata")
            continue

        quota_totale = round(quota_totale, 2)

        # Check: almeno 1 partita di oggi (per selettiva/bilanciata/ambiziosa)
        has_today = any(s["match_date"] == today_str for s in selezioni)
        raw_tipo_check = raw.get("tipo", "").lower().strip()
        if not has_today and raw_tipo_check not in ("oggi", ""):
            print(f"  ⚠️ Bolletta {raw_tipo_check} senza partite di oggi — scartata")
            continue

        # Determina tipo — se Mistral ha specificato "oggi", usa quello
        raw_tipo = raw.get("tipo", "").lower().strip()
        solo_oggi = all(s["match_date"] == today_str for s in selezioni)

        if raw_tipo == "oggi" and solo_oggi:
            tipo = "oggi"
        elif raw_tipo == "oggi" and not solo_oggi:
            # Mistral ha detto "oggi" ma ci sono partite future — classifica normalmente
            tipo = "ambiziosa"
            for t, (lo, hi) in list(FASCE.items()):
                if t == "oggi":
                    continue
                if lo <= quota_totale < hi:
                    tipo = t
                    break
        else:
            tipo = "ambiziosa"
            for t, (lo, hi) in list(FASCE.items()):
                if t == "oggi":
                    continue
                if lo <= quota_totale < hi:
                    tipo = t
                    break

        counters[tipo] += 1
        label = f"{tipo.capitalize()} #{counters[tipo]}"

        bollette_docs.append({
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

    return bollette_docs


def build_extra_pool(today_str, existing_match_keys):
    """Costruisce pool esteso da h2h_by_round per partite NON già nel pool AI."""
    today = datetime.strptime(today_str, "%Y-%m-%d")
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(3)]
    now = datetime.now()

    extra_pool = []
    rounds = list(db.h2h_by_round.find(
        {"date": {"$in": dates}},
        {"date": 1, "matches": 1, "league": 1}
    ))

    for rnd in rounds:
        league = rnd.get("league", "")
        for m in rnd.get("matches", []):
            home = m.get("home", "")
            away = m.get("away", "")
            match_date = m.get("date_obj", rnd.get("date", ""))
            if isinstance(match_date, datetime):
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
            if o.get("over_2_5"):
                mercati.append(("GOL", "Over 2.5", o["over_2_5"]))
            if o.get("under_2_5"):
                mercati.append(("GOL", "Under 2.5", o["under_2_5"]))
            if o.get("over_1_5"):
                mercati.append(("GOL", "Over 1.5", o["over_1_5"]))
            if o.get("under_1_5"):
                mercati.append(("GOL", "Under 1.5", o["under_1_5"]))
            if o.get("over_3_5"):
                mercati.append(("GOL", "Over 3.5", o["over_3_5"]))
            if o.get("under_3_5"):
                mercati.append(("GOL", "Under 3.5", o["under_3_5"]))
            if o.get("goal"):
                mercati.append(("GOL", "Goal", o["goal"]))
            if o.get("nogoal"):
                mercati.append(("GOL", "NoGoal", o["nogoal"]))

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


def call_mistral_integration(pool_text, fascia, count_needed, today_str):
    """Chiama Mistral per generare solo le bollette mancanti di una fascia."""
    fascia_range = FASCE[fascia]
    if fascia == "oggi":
        quota_rule = "Quote libere, qualsiasi fascia. TUTTE le selezioni DEVONO essere partite di OGGI ({today_str})"
    else:
        quota_rule = f"Quota totale tra {fascia_range[0]} e {fascia_range[1]}. ⚠️ OGNI bolletta DEVE contenere ALMENO 1 partita di OGGI ({today_str}) — bollette senza partite di oggi verranno scartate"

    prompt = f"""Sei un tipster professionista. Devi comporre esattamente {count_needed} bollette di tipo "{fascia}".
{quota_rule}

REGOLE:
1. Ogni partita UNA SOLA VOLTA per bolletta, con UN SOLO mercato
2. Almeno 2 selezioni per bolletta, massimo 10
3. Le selezioni con _extra_pool=true sono partite fuori dal sistema AI — usale se servono
4. ⚠️ OBBLIGATORIO: almeno 1 selezione con data {today_str} in ogni bolletta
5. Restituisci SOLO un array JSON valido. Nessun testo prima o dopo

[
  {{
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

    resp = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=60)
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
    except Exception as e:
        print(f"❌ Errore Mistral: {e}")
        return

    if not isinstance(raw_bollette, list):
        print(f"❌ Risposta Mistral non è un array: {type(raw_bollette)}")
        return

    print(f"📝 Mistral ha proposto {len(raw_bollette)} bollette")

    # 5. Valida e costruisci documenti
    bollette_docs = validate_and_build(raw_bollette, pool, today_str)

    if not bollette_docs:
        print("⚠️ Nessuna bolletta valida dopo la validazione.")
        return

    # 6. Conta per fascia e integra se serve
    by_tipo = {}
    for b in bollette_docs:
        by_tipo.setdefault(b["tipo"], []).append(b)

    fasce_carenti = {}
    for fascia in ["oggi", "selettiva", "bilanciata", "ambiziosa"]:
        count = len(by_tipo.get(fascia, []))
        if count < 3:
            fasce_carenti[fascia] = 3 - count

    if fasce_carenti:
        print(f"\n⚠️ Fasce carenti: {', '.join(f'{f} (mancano {n})' for f, n in fasce_carenti.items())}")
        print("🔄 Caricamento pool esteso da h2h_by_round...")

        existing_match_keys = set(s["match_key"] for s in pool)
        extra = build_extra_pool(today_str, existing_match_keys)
        extended_pool = pool + extra
        extended_pool = deduplicate_pool(extended_pool)
        print(f"📊 Pool esteso: {len(extended_pool)} selezioni ({len(extra)} extra)")

        extended_pool_text = serialize_pool_for_prompt(extended_pool)

        for fascia, needed in fasce_carenti.items():
            print(f"🤖 Integrazione {fascia}: generazione {needed} bollette...")
            try:
                raw_extra = call_mistral_integration(extended_pool_text, fascia, needed, today_str)
                if isinstance(raw_extra, list):
                    extra_docs = validate_and_build(raw_extra, extended_pool, today_str)
                    # Rinumera label
                    existing_count = len(by_tipo.get(fascia, []))
                    for doc in extra_docs:
                        existing_count += 1
                        doc["tipo"] = fascia
                        doc["label"] = f"{fascia.capitalize()} #{existing_count}"
                        doc["_integrated"] = True
                    bollette_docs.extend(extra_docs)
                    print(f"   ✅ Aggiunte {len(extra_docs)} bollette {fascia}")
                else:
                    print(f"   ❌ Risposta non valida per {fascia}")
            except Exception as e:
                print(f"   ❌ Errore integrazione {fascia}: {e}")

    # 7. Salva su MongoDB
    coll = db.bollette
    deleted = coll.delete_many({"date": today_str, "custom": {"$ne": True}})
    if deleted.deleted_count > 0:
        print(f"🗑️ Rimosse {deleted.deleted_count} bollette precedenti per {today_str}")

    coll.insert_many(bollette_docs)

    # Riepilogo
    by_tipo = {}
    for b in bollette_docs:
        by_tipo.setdefault(b["tipo"], []).append(b)

    print(f"\n✅ Salvate {len(bollette_docs)} bollette:")
    for tipo in ["oggi", "selettiva", "bilanciata", "ambiziosa"]:
        if tipo in by_tipo:
            quotes = [b["quota_totale"] for b in by_tipo[tipo]]
            integrated = sum(1 for b in by_tipo[tipo] if b.get("_integrated"))
            extra_label = f" ({integrated} integrate)" if integrated else ""
            print(f"   {tipo.upper()}: {len(by_tipo[tipo])}{extra_label} — quote: {quotes}")


if __name__ == "__main__":
    main()
