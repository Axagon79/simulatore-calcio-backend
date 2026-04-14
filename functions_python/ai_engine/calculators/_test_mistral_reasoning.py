"""
Test isolato: 10 partite del 13 aprile (già finite) → Mistral sceglie 3 e motiva con numeri.
"""
import os, sys, json, requests
from datetime import datetime, timedelta

sys.path.insert(0, 'C:/Progetti/simulatore-calcio-backend/functions_python/ai_engine')
sys.path.insert(0, 'C:/Progetti/simulatore-calcio-backend/functions_python/ai_engine/calculators')

from config import db
import re, unicodedata
from dotenv import load_dotenv
# Carica .env dalla stessa logica di generate_bollette_2.py
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
if not os.getenv('MISTRAL_API_KEY'):
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env'))
MISTRAL_API_KEY = os.getenv('MISTRAL_API_KEY')
if not MISTRAL_API_KEY:
    print("MISTRAL_API_KEY non trovata!")
    sys.exit(1)
print(f"API Key: {MISTRAL_API_KEY[:8]}...")

# 1. Pool: solo partite del 13 aprile (già finite)
today_str = '2026-04-13'
docs = list(db.daily_predictions_unified.find(
    {"date": today_str},
    {"home": 1, "away": 1, "date": 1, "league": 1, "match_time": 1,
     "pronostici": 1, "streak_home": 1, "streak_away": 1}
))

pool = []
seen = set()
for doc in docs:
    home = doc.get("home", "")
    away = doc.get("away", "")
    mk = f"{home} vs {away}"
    if mk in seen:
        continue
    for p in doc.get("pronostici", []):
        if p.get("tipo") == "RISULTATO_ESATTO":
            continue
        quota = p.get("quota")
        if not quota or quota <= 1.0:
            continue
        pool.append({
            "match_key": f"{home} vs {away}|{today_str}",
            "home": home, "away": away, "league": doc.get("league", ""),
            "match_date": today_str, "match_time": doc.get("match_time", ""),
            "mercato": p.get("tipo", ""), "pronostico": p.get("pronostico", ""),
            "quota": round(quota, 2), "confidence": p.get("confidence", 0),
            "stars": p.get("stars", 0),
            "streak_home": doc.get("streak_home", {}),
            "streak_away": doc.get("streak_away", {}),
        })
        seen.add(mk)
        break
    if len(pool) >= 10:
        break

print(f"Trovate {len(pool)} partite del {today_str}")

def _norm_name(s):
    """Normalizza nome squadra: identica al frontend (VistaPrePartita.tsx norm())."""
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if unicodedata.category(c) != 'Mn')
    s = s.lower()
    s = re.sub(r'[^a-z0-9]', '', s)
    return s

def _match_team_in_table(search_name, table_rows, tm_id=None):
    """Matching a 4 livelli identico al frontend (VistaPrePartita.tsx matchTeam)."""
    # Livello 0: transfermarkt_id
    if tm_id is not None:
        for row in table_rows:
            if str(row.get("transfermarkt_id", "")) == str(tm_id):
                return row
    nn = _norm_name(search_name)
    # Livello 1: match esatto
    for row in table_rows:
        if row["team"] == search_name:
            return row
    # Livello 2: match normalizzato
    for row in table_rows:
        if _norm_name(row["team"]) == nn:
            return row
    # Livello 3: substring (entrambi >3 chars)
    if len(nn) > 3:
        for row in table_rows:
            rn = _norm_name(row["team"])
            if len(rn) > 3 and (rn in nn or nn in rn):
                return row
    return None

# 2. Arricchisci con dati statistici
for s in pool:
    # h2h_by_round
    h2h_doc = db.h2h_by_round.find_one(
        {"league": s["league"], "matches": {"$elemMatch": {"home": s["home"], "away": s["away"]}}},
        {"matches.$": 1}, sort=[("_id", -1)]
    )
    if h2h_doc and h2h_doc.get("matches"):
        match_doc = h2h_doc["matches"][0]
        s["home_tm_id"] = match_doc.get("home_tm_id")
        s["away_tm_id"] = match_doc.get("away_tm_id")
        hd = match_doc.get("h2h_data", {})
        lh = hd.get("lucifero_home")
        la = hd.get("lucifero_away")
        s["forma_home"] = round((lh / 25) * 100, 1) if lh else None
        s["forma_away"] = round((la / 25) * 100, 1) if la else None
        s["trend_home"] = hd.get("lucifero_trend_home", [])
        s["trend_away"] = hd.get("lucifero_trend_away", [])
        aff = hd.get("affidabilità", {})
        if isinstance(aff, dict):
            s["affid_casa"] = round(aff.get("affidabilità_casa", 0) or 0, 1)
            s["affid_trasf"] = round(aff.get("affidabilità_trasferta", 0) or 0, 1)
        dna = hd.get("h2h_dna", {})
        s["dna_home"] = dna.get("home_dna")
        s["dna_away"] = dna.get("away_dna")

    # Motivazioni da teams (cerca per nome O aliases)
    for side, name in [("home", s["home"]), ("away", s["away"])]:
        t = db.teams.find_one(
            {"$or": [{"name": name}, {"aliases": name}]},
            {"name": 1, "stats.motivation": 1, "stats.motivation_pressure_euro": 1,
             "stats.motivation_pressure_releg": 1, "stats.motivation_pressure_title": 1}
        )
        if t:
            stats = t.get("stats", {})
            mot = stats.get("motivation")
            p_t = stats.get("motivation_pressure_title", 0) or 0
            p_e = stats.get("motivation_pressure_euro", 0) or 0
            p_r = stats.get("motivation_pressure_releg", 0) or 0
            label = "NEUTRALE"
            if p_t > 0.5: label = "LOTTA TITOLO"
            elif p_e > 0.5: label = "LOTTA EUROPA"
            elif p_r > 0.5: label = "LOTTA SALVEZZA"
            elif mot and mot < 7: label = "BASSA"
            elif mot and mot > 13: label = "MOLTO ALTA"
            s[f"motiv_{side}"] = f"{label} ({round(mot, 1)})" if mot else None

    # Classifica (matching fuzzy come frontend)
    cl = db.classifiche.find_one({"league": s["league"]}, {"table": 1})
    if cl:
        table = cl.get("table", [])
        row_h = _match_team_in_table(s["home"], table, tm_id=s.get("home_tm_id"))
        row_a = _match_team_in_table(s["away"], table, tm_id=s.get("away_tm_id"))
        if row_h:
            s["class_home"] = (f"{row_h.get('rank')}o {row_h.get('points')}pt "
                f"({row_h.get('wins')}V-{row_h.get('draws')}N-{row_h.get('losses')}P "
                f"GF:{row_h.get('goals_for')} GS:{row_h.get('goals_against')})")
        if row_a:
            s["class_away"] = (f"{row_a.get('rank')}o {row_a.get('points')}pt "
                f"({row_a.get('wins')}V-{row_a.get('draws')}N-{row_a.get('losses')}P "
                f"GF:{row_a.get('goals_for')} GS:{row_a.get('goals_against')})")

# 3. Serializza
lines = []
for i, s in enumerate(pool):
    lines.append(f"\n--- PARTITA {i+1}: {s['home']} vs {s['away']} ({s['league']}) ---")
    lines.append(f"  Data: {s['match_date']} ore {s['match_time']}")
    lines.append(f"  Pronostico AI: {s['mercato']}: {s['pronostico']} @ {s['quota']} | confidence={s['confidence']} stelle={s['stars']}")
    if s.get("class_home"):
        lines.append(f"  Classifica: {s['home']} {s['class_home']} | {s['away']} {s.get('class_away', '?')}")
    if s.get("forma_home") is not None:
        lines.append(f"  Forma (ultimi 6 match): {s['home']} {s['forma_home']}% | {s['away']} {s.get('forma_away', '?')}%")
    if s.get("trend_home"):
        th = "->".join(f"{v:.0f}" for v in s["trend_home"])
        ta = "->".join(f"{v:.0f}" for v in s.get("trend_away", []))
        lines.append(f"  Trend forma (5 giornate): {s['home']} [{th}] | {s['away']} [{ta}]")
    if s.get("motiv_home"):
        lines.append(f"  Motivazione: {s['home']} {s['motiv_home']} | {s['away']} {s.get('motiv_away', '?')}")
    sh = s.get("streak_home", {})
    sa = s.get("streak_away", {})
    notable_h = [f"{k}:{v}" for k, v in sh.items() if v and v >= 2]
    notable_a = [f"{k}:{v}" for k, v in sa.items() if v and v >= 2]
    if notable_h or notable_a:
        lines.append(f"  Strisce: {s['home']} [{' '.join(notable_h)}] | {s['away']} [{' '.join(notable_a)}]")
    if s.get("affid_casa") is not None:
        lines.append(f"  Affidabilita: {s['home']}(casa) {s['affid_casa']}/10 | {s['away']}(trasf) {s.get('affid_trasf', '?')}/10")
    if s.get("dna_home"):
        dh = s["dna_home"]
        da = s.get("dna_away", {})
        lines.append(f"  Attacco: {s['home']} {dh.get('att',0)}/100 | {s['away']} {da.get('att',0)}/100")
        lines.append(f"  Difesa: {s['home']} {dh.get('def',0)}/100 | {s['away']} {da.get('def',0)}/100")
        lines.append(f"  Tecnica: {s['home']} {dh.get('tec',0)}/100 | {s['away']} {da.get('tec',0)}/100")
        lines.append(f"  Valore rosa: {s['home']} {dh.get('val',0)}/100 | {s['away']} {da.get('val',0)}/100")

pool_text = "\n".join(lines)
print("\n=== POOL INVIATO A MISTRAL ===")
print(pool_text)

# 4. Chiama Mistral
prompt = """Sei un analista dati sportivo. NON sei tu a fare i pronostici — quelli li ha già fatti un sistema AI. Il tuo compito è ANALIZZARE i dati statistici di ogni selezione.

Per ogni partita hai 10 dati statistici:
1. Classifica (posizione, punti, V-N-P, gol fatti/subiti, posizione casa/trasferta)
2. Forma (percentuale ultimi 6 match, 0-100%)
3. Trend forma (5 valori cronologici, sta migliorando o peggiorando?)
4. Motivazione (cosa si gioca la squadra: titolo, Europa, salvezza, nulla)
5. Strisce (vittorie consecutive, sconfitte, Over, Under, GG, clean sheet, ecc.)
6. Affidabilità (quanto la squadra rispetta il pronostico dei bookmaker, 0-10)
7. Attacco (potenza offensiva della squadra, 0-100)
8. Difesa (solidità difensiva della squadra, 0-100)
9. Tecnica (qualità tecnica della squadra, 0-100)
10. Valore rosa (valore complessivo della rosa, 0-100)

COMPITO: Per ognuna delle 10 partite, calcola un COEFFICIENTE DI SOLIDITÀ da 0 a 100.

Il coefficiente deve essere il risultato di un'analisi di TUTTI e 10 i dati statistici. Nessun dato può essere ignorato.

Per ogni partita scrivi:
- Il COEFFICIENTE (0-100)
- Per OGNUNO dei 10 dati: il valore letto dal pool + un punteggio parziale (positivo o negativo) che hai assegnato + perché
- Come hai calcolato il coefficiente finale dai 10 punteggi parziali

Alla fine:
1. Ordina le 10 partite dal coefficiente PIÙ ALTO al PIÙ BASSO.
2. Spiega nel dettaglio la FORMULA che hai usato per calcolare il coefficiente: come assegni i punteggi parziali, che scala usi, come li combini, come converti il risultato in un numero 0-100. Deve essere una formula replicabile identica per ogni partita.

Rispondi in italiano. Cita i numeri esatti dal pool."""

headers = {
    "Authorization": f"Bearer {MISTRAL_API_KEY}",
    "Content-Type": "application/json",
}
payload = {
    "model": "mistral-small-latest",
    "messages": [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"Ecco le 10 partite con tutti i dati:\n{pool_text}"}
    ],
    "temperature": 0.3,
    "max_tokens": 12000,
}

print("\n=== RISPOSTA MISTRAL ===\n")
resp = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=payload)
data = resp.json()
if "choices" not in data:
    print("ERRORE API:", json.dumps(data, indent=2))
else:
    answer = data["choices"][0]["message"]["content"]
    print(answer)

    # Salva tutto su file per review
    output_path = os.path.join(os.path.dirname(__file__), "_test_mistral_output.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=== POOL INVIATO A MISTRAL ===\n")
        f.write(pool_text)
        f.write("\n\n=== RISPOSTA MISTRAL ===\n\n")
        f.write(answer if "choices" in data else json.dumps(data, indent=2))
    print(f"\n📄 Output salvato in: {output_path}")
