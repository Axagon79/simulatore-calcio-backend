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

MAX_BOLLETTE = 10

# Fasce quota totale
FASCE = {
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
4. Se ci sono partite di oggi con buoni pronostici, valuta di creare qualche bolletta composta SOLO da partite di oggi (campo "solo_oggi": true), così chi vuole giocare subito ha opzioni pronte. Quante farne lo decidi tu in base al materiale disponibile
5. Genera esattamente {max_bollette} bollette totali, divise in 3 fasce. Distribuzione OBBLIGATORIA: 4 selettive, 4 bilanciate, 2 ambiziose:
   - Selettiva: quota totale MASSIMO 3.0 — la quota moltiplicata di tutte le selezioni NON deve superare 3.0
   - Bilanciata: quota totale tra 3.0 e 8.0
   - Ambiziosa: quota totale superiore a 8.0
   Quante selezioni mettere in ogni bolletta lo decidi tu in base alla tua esperienza
6. Si consiglia di dare la preferenza a selezioni con confidence e stelle alte, ma fai affidamento alla tua esperienza: se una selezione con stelle più basse ti convince per il contesto della bolletta, usala
7. Non creare bollette con una sola selezione — almeno 2 selezioni per bolletta
8. Massimo 10 selezioni per bolletta. Se hai in mente più di 10, dividi in 2 bollette separate
9. Per ogni bolletta, scrivi una breve motivazione (1 frase) che spiega la logica

═══════════════════════════════════════
FORMATO OUTPUT — JSON ARRAY
═══════════════════════════════════════

Restituisci SOLO un array JSON valido. Nessun testo prima o dopo. Nessun markdown.

[
  {
    "selezioni": [
      { "match_key": "Inter vs Milan|2026-03-15", "mercato": "SEGNO", "pronostico": "1" },
      { "match_key": "Arsenal vs Chelsea|2026-03-16", "mercato": "GOL", "pronostico": "Over 2.5" }
    ],
    "reasoning": "Due big match con favorite nette in casa"
  }
]

IMPORTANTE:
- match_key deve essere ESATTAMENTE come nel pool (formato "Home vs Away|YYYY-MM-DD")
- mercato e pronostico devono corrispondere ESATTAMENTE a quelli nel pool
- Non inventare partite o pronostici che non sono nel pool
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
            lines.append(
                f"  {s['match_key']} | {s['mercato']}: {s['pronostico']} "
                f"@ {s['quota']} | conf={s['confidence']} ★{s['stars']}"
            )
    return "\n".join(lines)


def call_mistral(pool_text):
    """Chiama Mistral per generare le bollette."""
    prompt = SYSTEM_PROMPT.replace("{max_bollette}", str(MAX_BOLLETTE))

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
        "max_tokens": 4000,
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
    counters = {"selettiva": 0, "bilanciata": 0, "ambiziosa": 0}

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

        # Determina tipo
        tipo = "ambiziosa"
        for t, (lo, hi) in FASCE.items():
            if lo <= quota_totale < hi:
                tipo = t
                break

        solo_oggi = all(s["match_date"] == today_str for s in selezioni)

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
        raw_bollette = call_mistral(pool_text)
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

    # 6. Salva su MongoDB
    coll = db.bollette
    deleted = coll.delete_many({"date": today_str})
    if deleted.deleted_count > 0:
        print(f"🗑️ Rimosse {deleted.deleted_count} bollette precedenti per {today_str}")

    coll.insert_many(bollette_docs)

    # Riepilogo
    by_tipo = {}
    for b in bollette_docs:
        by_tipo.setdefault(b["tipo"], []).append(b)

    print(f"\n✅ Salvate {len(bollette_docs)} bollette:")
    for tipo in ["selettiva", "bilanciata", "ambiziosa"]:
        if tipo in by_tipo:
            labels = [b["label"] for b in by_tipo[tipo]]
            quotes = [b["quota_totale"] for b in by_tipo[tipo]]
            print(f"   {tipo.upper()}: {len(by_tipo[tipo])} — quote: {quotes}")


if __name__ == "__main__":
    main()
