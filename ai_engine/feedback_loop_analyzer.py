"""
FEEDBACK LOOP ANALYZER — Step 29.5 Pipeline Notturna
=====================================================
Analizza automaticamente i pronostici errati con Mistral AI.
Salva l'analisi strutturata in 'prediction_errors' su MongoDB.
"""

import os, sys, re, json, argparse, time
from datetime import datetime, timedelta, timezone
from collections import Counter

# --- FIX PERCORSI (stessa logica di calculate_profit_loss.py) ---
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
    # Prova a caricare da .env
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(current_path, '.env'))
        MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY")
    except ImportError:
        pass
if not MISTRAL_API_KEY:
    print("❌ MISTRAL_API_KEY non trovata! Impostala in .env o come variabile d'ambiente.")
    sys.exit(1)

# --- PROMPT (identico a quello in llmService.js) ---
FEEDBACK_LOOP_PROMPT = """Sei un analista di errori predittivi per un sistema di pronostici calcistici. Il tuo compito è diagnosticare perché un pronostico è stato sbagliato. Sii diretto, preciso e spietato nell'analisi — non fare diplomazia.

Ricevi: partita, pronostico emesso, risultato reale, quote, segnali statistici, strisce, simulazione Monte Carlo.

Restituisci SOLO un oggetto JSON valido. Nessun testo prima o dopo. Nessun markdown. Nessun commento.

═══════════════════════════════════════
VARIABILI DA VALUTARE (0.0 - 1.0 ciascuna)
═══════════════════════════════════════

- form: la forma recente era fuorviante (es. squadra in striscia positiva che crolla, o squadra in crisi che reagisce)
- motivation: fattori motivazionali non catturati (lotta retrocessione, corsa titolo, derby, ultima giornata, nulla in gioco)
- home_advantage: il fattore campo è stato sopravvalutato o sottovalutato
- market_odds: le quote di mercato suggerivano un esito diverso dal modello — il mercato aveva ragione
- h2h: gli scontri diretti indicavano un pattern diverso da quello predetto
- fatigue: calendario fitto, turno infrasettimanale, impegni coppa, viaggi internazionali
- streaks: le strisce (vittorie/sconfitte/imbattibilità/senza vittorie) hanno ingannato il modello
- tactical_dna: lo stile di gioco (offensivo/difensivo/equilibrato) non è stato pesato correttamente

REGOLE PESI:
- Devono sommare a 1.0 (tolleranza ±0.05)
- Assegna 0.0 alle variabili irrilevanti
- Concentra il peso sulle 2-3 variabili dominanti (almeno una deve essere ≥ 0.3)

═══════════════════════════════════════
SEVERITY — CRITERI OBBLIGATORI
═══════════════════════════════════════

Usa QUESTI criteri numerici, non il tuo giudizio generico:

HIGH (errore grave):
- Il pronostico era SEGNO e la confidence ≥ 65% ma il risultato è l'OPPOSTO (es. pronostico "1", risultato "2")
- OPPURE il modello dava probabilità ≥ 70% per un esito e si è verificato l'opposto
- OPPURE Monte Carlo dava home_win_pct ≥ 65% (o away_win_pct ≥ 65%) e ha vinto l'altra squadra
- OPPURE upset completo: squadra con 5+ partite senza vittoria batte la favorita

LOW (errore marginale):
- La confidence era < 55%
- OPPURE il risultato è "vicino" al pronostico (es. pronostico "1", risultato "X" — mancava poco)
- OPPURE pronostico GOL sbagliato per 1 solo gol di differenza (es. Over 2.5, risultato 2 gol totali)
- OPPURE il modello stesso aveva segnali contraddittori (edge < 2%)

MEDIUM: tutto ciò che non rientra in HIGH né in LOW.

NON mettere medium per default. Valuta PRIMA se è high o low, e solo se non rientra in nessuno dei due metti medium.

═══════════════════════════════════════
PATTERN TAGS
═══════════════════════════════════════

Scegli SOLO tra questi (minimo 1, massimo 4):
["forma_fuorviante", "derby", "motivazione_nascosta", "calendario_fitto", "upset", "quota_troppo_alta", "quota_troppo_bassa", "striscia_interrotta", "fattore_campo_ignorato", "difesa_atipica", "attacco_atipico", "portiere_decisivo", "espulsione", "rigore_decisivo", "meteo", "arbitraggio", "modello_overconfident", "modello_underconfident", "dati_insufficienti"]

═══════════════════════════════════════
CAMPI TESTUALI — REGOLE DI STILE
═══════════════════════════════════════

root_cause (max 20 parole):
- DEVE citare almeno UN numero specifico dal contesto
- Esempio BUONO: "Bologna 3 vittorie consecutive ma Verona 12 trasferte senza vittoria nascondeva reazione"
- Esempio CATTIVO: "La forma recente era fuorviante"

ai_analysis (2-3 frasi, italiano):
- Sii DIRETTO: di' cosa ha sbagliato il modello, non cosa "potrebbe" essere andato storto
- Cita numeri specifici: percentuali Monte Carlo, confidence, quote, strisce
- NON usare frasi vaghe tipo "suggerendo una valutazione più equilibrata" o "non completamente catturati"
- Esempio BUONO: "Il modello ha dato 68% casa basandosi su 3 vittorie consecutive del Bologna, ignorando che il Verona nelle ultime 3 trasferte ha sempre segnato almeno un gol. La quota 6.00 per il 2 segnalava un'anomalia che il modello non ha intercettato."
- Esempio CATTIVO: "Il modello ha sovrastimato la forma recente e non ha considerato adeguatamente i segnali contrari."

suggested_adjustment (1 frase):
- DEVE nominare il segnale specifico del modello da modificare (usa i nomi dei campi: bvs, lucifero, affidabilita, dna, motivazioni, h2h, campo, strisce, media_gol, att_vs_def, xg, ecc.)
- Esempio BUONO: "Ridurre il peso di 'strisce' quando la squadra sfavorita ha quote > 5.00 — il mercato prezza un upset possibile."
- Esempio CATTIVO: "Aggiungere un peso maggiore ai segnali di miglioramento."

═══════════════════════════════════════
FORMATO RISPOSTA (JSON puro)
═══════════════════════════════════════

{
  "variables_impact": {
    "form": 0.0,
    "motivation": 0.0,
    "home_advantage": 0.0,
    "market_odds": 0.0,
    "h2h": 0.0,
    "fatigue": 0.0,
    "streaks": 0.0,
    "tactical_dna": 0.0
  },
  "pattern_tags": [],
  "severity": "low|medium|high",
  "root_cause": "",
  "ai_analysis": "",
  "suggested_adjustment": ""
}"""

VALID_TAGS = {
    "forma_fuorviante", "derby", "motivazione_nascosta", "calendario_fitto",
    "upset", "quota_troppo_alta", "quota_troppo_bassa", "striscia_interrotta",
    "fattore_campo_ignorato", "difesa_atipica", "attacco_atipico",
    "portiere_decisivo", "espulsione", "rigore_decisivo", "meteo",
    "arbitraggio", "modello_overconfident", "modello_underconfident",
    "dati_insufficienti"
}


# --- FUNZIONI ---

def compute_actual_outcome(tipo, live_score):
    """Calcola cosa è successo davvero dal risultato reale."""
    parts = re.split(r'[:\-]', str(live_score).strip())
    if len(parts) != 2:
        return None
    try:
        h, a = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    total = h + a
    sign = '1' if h > a else ('X' if h == a else '2')
    btts = h > 0 and a > 0

    if tipo == 'SEGNO':
        return sign
    elif tipo == 'DOPPIA_CHANCE':
        if sign == '1': return '1X o 12'
        elif sign == 'X': return '1X o X2'
        else: return 'X2 o 12'
    elif tipo in ('GOL', 'MG'):
        parts_out = []
        parts_out.append(f"Over 2.5" if total >= 3 else "Under 2.5")
        parts_out.append("GG" if btts else "NG")
        parts_out.append(f"totale gol: {total}")
        return ", ".join(parts_out)
    elif tipo == 'RISULTATO_ESATTO':
        return f"{h}-{a}"
    return None


def map_error_type(tipo):
    """Mappa il tipo di pronostico al tipo di errore."""
    mapping = {
        'SEGNO': 'segno_errato',
        'DOPPIA_CHANCE': 'doppia_chance_errata',
        'GOL': 'gol_errato',
        'MG': 'mg_errato',
        'RISULTATO_ESATTO': 're_errato',
    }
    return mapping.get(tipo, 'altro_errato')


def build_context_for_mistral(doc, prono, live_score):
    """Costruisce il contesto testuale da inviare a Mistral."""
    lines = [
        f"PARTITA: {doc.get('home', '?')} vs {doc.get('away', '?')}",
        f"CAMPIONATO: {doc.get('league', '?')}",
        f"DATA: {doc.get('date', '?')} ore {doc.get('match_time', '?')}",
        f"RISULTATO REALE: {live_score}",
        f"",
        f"PRONOSTICO ERRATO:",
        f"  Tipo: {prono.get('tipo', '?')}",
        f"  Pronostico: {prono.get('pronostico', '?')}",
        f"  Quota: {prono.get('quota', '?')}",
        f"  Confidence: {prono.get('confidence', '?')}%",
        f"  Stelle: {prono.get('stars', '?')}",
        f"  Probabilità stimata: {prono.get('probabilita_stimata', '?')}",
        f"  Prob mercato: {prono.get('prob_mercato', '?')}",
        f"  Edge: {prono.get('edge', '?')}",
        f"  Source: {prono.get('source', 'unknown')}",
    ]

    # Quote partita
    odds = doc.get('odds')
    if odds:
        lines.append(f"\nQUOTE PARTITA: {json.dumps(odds, default=str)}")

    # Segnali segno
    sd = doc.get('segno_dettaglio')
    if sd:
        lines.append(f"\nSEGNALI SEGNO (0-100, contribuzione al pronostico):")
        for k, v in sd.items():
            lines.append(f"  {k}: {v}")

    # Segnali gol
    gd = doc.get('gol_dettaglio')
    if gd:
        lines.append(f"\nSEGNALI GOL (0-100):")
        for k, v in gd.items():
            direction = ""
            if doc.get('gol_directions', {}).get(k):
                direction = f" (direzione: {doc['gol_directions'][k]})"
            lines.append(f"  {k}: {v}{direction}")

    # Strisce
    for label, key in [("STRISCE CASA", "streak_home"), ("STRISCE OSPITE", "streak_away")]:
        streak = doc.get(key)
        if streak:
            lines.append(f"\n{label}: {json.dumps(streak, default=str)}")

    # Simulation data (MC)
    sim = doc.get('simulation_data')
    if sim:
        lines.append(f"\nSIMULAZIONE MONTE CARLO:")
        for k in ['home_win_pct', 'draw_pct', 'away_win_pct',
                   'over_25_pct', 'under_25_pct', 'gg_pct', 'ng_pct',
                   'avg_goals_home', 'avg_goals_away', 'predicted_score']:
            if k in sim:
                lines.append(f"  {k}: {sim[k]}")

    return "\n".join(lines)


def call_mistral(context_text):
    """Chiama Mistral API e ritorna il JSON parsato."""
    headers = {
        "Authorization": f"Bearer {MISTRAL_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MISTRAL_MODEL,
        "messages": [
            {"role": "system", "content": FEEDBACK_LOOP_PROMPT},
            {"role": "user", "content": context_text},
        ],
        "temperature": 0.3,
        "max_tokens": 1500,
    }

    max_retries = 2
    for attempt in range(1, max_retries + 1):
        resp = requests.post(MISTRAL_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 429 and attempt < max_retries:
            wait = 10 * attempt
            print(f"      ⏳ Rate limit 429, retry {attempt}/{max_retries} tra {wait}s...")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break

    content = resp.json()["choices"][0]["message"]["content"].strip()

    # Rimuovi eventuale markdown wrapping
    if content.startswith("```"):
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)

    return json.loads(content)


def validate_ai_response(data):
    """Valida e normalizza la risposta di Mistral."""
    vi = data.get("variables_impact", {})
    expected_keys = {"form", "motivation", "home_advantage", "market_odds",
                     "h2h", "fatigue", "streaks", "tactical_dna"}
    for k in expected_keys:
        if k not in vi:
            vi[k] = 0.0
        vi[k] = max(0.0, min(1.0, float(vi[k])))

    # Normalizza somma a 1.0
    total = sum(vi.values())
    if total > 0 and abs(total - 1.0) > 0.05:
        for k in vi:
            vi[k] = round(vi[k] / total, 3)

    # Filtra tag invalidi
    tags = [t for t in data.get("pattern_tags", []) if t in VALID_TAGS]

    severity = data.get("severity", "medium")
    if severity not in ("low", "medium", "high"):
        severity = "medium"

    return {
        "variables_impact": vi,
        "pattern_tags": tags,
        "severity": severity,
        "root_cause": str(data.get("root_cause", ""))[:200],
        "ai_analysis": str(data.get("ai_analysis", ""))[:1000],
        "suggested_adjustment": str(data.get("suggested_adjustment", ""))[:500],
    }


def main():
    parser = argparse.ArgumentParser(description="Feedback Loop — Analisi Errori Pronostici")
    parser.add_argument("--date", type=str, help="Data specifica YYYY-MM-DD")
    parser.add_argument("--days", type=int, default=1, help="Ultimi N giorni (default: 1 = ieri)")
    parser.add_argument("--from", type=str, dest="from_date", help="Data inizio range YYYY-MM-DD (usare con --to)")
    parser.add_argument("--to", type=str, dest="to_date", help="Data fine range YYYY-MM-DD (usare con --from)")
    parser.add_argument("--report-only", action="store_true", help="Genera solo i report senza analizzare nuovi errori")
    parser.add_argument("--report-days", type=int, default=30, help="Giorni coperti dal report (default: 30)")
    args = parser.parse_args()

    if args.report_only:
        generate_reports(days=args.report_days)
        return

    # Determina le date da analizzare
    if args.from_date and args.to_date:
        start = datetime.strptime(args.from_date, '%Y-%m-%d')
        end = datetime.strptime(args.to_date, '%Y-%m-%d')
        if start > end:
            start, end = end, start
        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
    elif args.date:
        dates = [args.date]
    else:
        dates = []
        for i in range(1, args.days + 1):
            d = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
            dates.append(d)

    print(f"\n{'='*60}")
    print(f"🔁 FEEDBACK LOOP — Analisi Errori Pronostici")
    print(f"{'='*60}")
    print(f"Date da analizzare: {', '.join(dates)}")

    coll_unified = db.daily_predictions_unified
    coll_errors = db.prediction_errors

    # Indice unique per deduplicazione
    try:
        coll_errors.create_index(
            [("match_id", 1), ("prediction_type", 1), ("prediction_value", 1)],
            unique=True, background=True
        )
    except Exception:
        pass

    # Indici aggiuntivi per query pattern recognition
    try:
        coll_errors.create_index([("match_date", -1)], background=True)
        coll_errors.create_index([("league", 1), ("match_date", -1)], background=True)
        coll_errors.create_index([("source", 1)], background=True)
        coll_errors.create_index([("pattern_tags", 1)], background=True)
        coll_errors.create_index([("severity", 1)], background=True)
        coll_errors.create_index([("variables_impact.form", -1)], background=True)
        coll_errors.create_index([("variables_impact.motivation", -1)], background=True)
    except Exception:
        pass

    total_analyzed = 0
    total_skipped = 0
    all_severities = Counter()
    all_tags = Counter()

    for target_date in dates:
        # Trova pronostici persi
        docs = list(coll_unified.find({
            "date": target_date,
            "pronostici": {"$elemMatch": {
                "esito": False,
                "profit_loss": {"$lt": 0}
            }}
        }))

        # Estrai singoli pronostici persi
        errors = []
        for doc in docs:
            live_score = doc.get("live_score")
            if not live_score:
                # Fallback: cerca real_score in h2h_by_round
                home = doc.get("home", "")
                away = doc.get("away", "")
                league = doc.get("league", "")
                h2h_match = db.h2h_by_round.aggregate([
                    {"$match": {"league": league}},
                    {"$unwind": "$matches"},
                    {"$match": {"matches.home": home, "matches.away": away, "matches.real_score": {"$exists": True, "$nin": ["", None, "-:-"]}}},
                    {"$sort": {"matches.date_obj": -1}},
                    {"$limit": 1},
                    {"$project": {"_id": 0, "real_score": "$matches.real_score"}}
                ])
                h2h_result = list(h2h_match)
                if h2h_result:
                    live_score = h2h_result[0]["real_score"]
                    doc["live_score"] = live_score  # inietta per uso successivo
                else:
                    continue
            for prono in doc.get("pronostici", []):
                if prono.get("esito") is False and prono.get("profit_loss", 0) < 0:
                    errors.append((doc, prono))

        if not errors:
            print(f"\n📊 {target_date}: nessun pronostico errato trovato")
            continue

        print(f"\n📊 Trovati {len(errors)} pronostici errati per {target_date}")

        for idx, (doc, prono) in enumerate(errors, 1):
            home = doc.get("home", "?")
            away = doc.get("away", "?")
            tipo = prono.get("tipo", "?")
            pronostico = prono.get("pronostico", "?")
            live_score = doc.get("live_score", "?")
            match_id = f"{doc.get('date', '')}_{home}_{away}"

            # Deduplicazione
            existing = coll_errors.find_one({
                "match_id": match_id,
                "prediction_type": tipo,
                "prediction_value": pronostico,
            })
            if existing:
                print(f"   {idx}/{len(errors)} ⏭️ {home} vs {away} — {tipo} ({pronostico}) — già analizzato, skip")
                total_skipped += 1
                continue

            # Costruisci contesto e chiama Mistral
            try:
                context = build_context_for_mistral(doc, prono, live_score)
                ai_result = call_mistral(context)
                ai_result = validate_ai_response(ai_result)
                time.sleep(2)  # Rate limiting: pausa tra chiamate Mistral
            except Exception as e:
                print(f"   {idx}/{len(errors)} ❌ {home} vs {away} — Errore Mistral: {e}")
                continue

            # Costruisci documento da salvare
            error_doc = {
                # Identificazione partita
                "match_id": match_id,
                "league": doc.get("league", ""),
                "home_team": home,
                "away_team": away,
                "match_date": datetime.strptime(doc.get("date", "2000-01-01"), "%Y-%m-%d"),
                "match_time": doc.get("match_time", ""),
                "is_cup": doc.get("is_cup", False),
                # Pronostico errato
                "prediction_type": tipo,
                "prediction_value": pronostico,
                "actual_result": live_score,
                "actual_outcome": compute_actual_outcome(tipo, live_score),
                "error_type": map_error_type(tipo),
                # Dati pronostico originale
                "confidence": prono.get("confidence"),
                "stars": prono.get("stars"),
                "quota": prono.get("quota"),
                "probabilita_stimata": prono.get("probabilita_stimata"),
                "prob_mercato": prono.get("prob_mercato"),
                "stake": prono.get("stake"),
                "edge": prono.get("edge"),
                "source": prono.get("source", "unknown"),
                "profit_loss": prono.get("profit_loss"),
                # Contesto statistico
                "odds": doc.get("odds"),
                "segno_dettaglio": doc.get("segno_dettaglio"),
                "gol_dettaglio": doc.get("gol_dettaglio"),
                "streak_home": doc.get("streak_home"),
                "streak_away": doc.get("streak_away"),
                "simulation_data": doc.get("simulation_data"),
                # Analisi AI
                **ai_result,
                # Metadata
                "analyzed_at": datetime.now(tz=timezone.utc),
                "created_at": datetime.now(tz=timezone.utc),
                "feedback_version": "1.0",
            }

            try:
                coll_errors.insert_one(error_doc)
                severity = ai_result.get("severity", "medium")
                all_severities[severity] += 1
                for tag in ai_result.get("pattern_tags", []):
                    all_tags[tag] += 1
                total_analyzed += 1
                print(f"   {idx}/{len(errors)} ✅ {home} vs {away} — {tipo} ({pronostico}) → reale: {live_score} — severity: {severity}")
            except Exception as e:
                if "duplicate key" in str(e).lower() or "E11000" in str(e):
                    print(f"   {idx}/{len(errors)} ⏭️ {home} vs {away} — già analizzato, skip")
                    total_skipped += 1
                else:
                    print(f"   {idx}/{len(errors)} ❌ {home} vs {away} — Errore salvataggio: {e}")

    # --- REPORT FINALE ---
    print(f"\n{'='*60}")
    print(f"✅ Feedback Loop completato: {total_analyzed} errori analizzati, {total_skipped} skippati")
    if all_severities:
        print(f"   Severity: {', '.join(f'{v} {k}' for k, v in all_severities.most_common())}")
    if all_tags:
        top_tags = all_tags.most_common(5)
        print(f"   Top pattern: {', '.join(f'{t} ({c}x)' for t, c in top_tags)}")
    print(f"{'='*60}\n")

    # Genera report automaticamente dopo l'analisi
    generate_reports(days=args.report_days)

    # Report settimanale — solo il martedì
    if datetime.now().weekday() == 1:  # 0=lunedì, 1=martedì
        print("\n📊 Martedì — Generazione report settimanale...")
        generate_weekly_report(report_days=7)


def _cleanup_old_reports(reports_dir, keep=2):
    """Mantiene solo le ultime `keep` coppie di report (JSON+TXT), cancella le più vecchie."""
    import glob
    json_files = sorted(glob.glob(os.path.join(reports_dir, "feedback_report_*.json")))
    while len(json_files) > keep:
        oldest = json_files.pop(0)
        txt_pair = oldest.replace(".json", ".txt")
        for f in [oldest, txt_pair]:
            if os.path.exists(f):
                os.remove(f)
                print(f"🗑️ Rimosso report vecchio: {os.path.basename(f)}")


def _get_quota_range(quota):
    """Restituisce la fascia quota per un valore (fasce da 0.20)."""
    if quota is None:
        return None
    if quota <= STD_QUOTA_LIMIT:
        # Standard
        if quota < 1.55:
            return "1.35-1.55"
        elif quota < 1.75:
            return "1.55-1.75"
        elif quota < 1.95:
            return "1.75-1.95"
        elif quota < 2.15:
            return "1.95-2.15"
        elif quota < 2.35:
            return "2.15-2.35"
        else:
            return "2.35-2.50"
    else:
        # Alto Rendimento
        if quota < 2.70:
            return "2.50-2.70"
        elif quota < 2.90:
            return "2.70-2.90"
        elif quota < 3.10:
            return "2.90-3.10"
        elif quota < 3.50:
            return "3.10-3.50"
        else:
            return ">3.50"


STD_QUOTA_RANGES = ["1.35-1.55", "1.55-1.75", "1.75-1.95", "1.95-2.15", "2.15-2.35", "2.35-2.50"]
AR_QUOTA_RANGES = ["2.50-2.70", "2.70-2.90", "2.90-3.10", "3.10-3.50", ">3.50"]
QUOTA_RANGES_ORDER = STD_QUOTA_RANGES + AR_QUOTA_RANGES
MINOR_LEAGUES = {"Serie C - Girone A", "Serie C - Girone B", "Serie C - Girone C",
                 "Ligue 2", "2. Bundesliga", "LaLiga 2", "Championship", "League One",
                 "League of Ireland Premier Division",
                 "League Two", "Veikkausliiga", "3. Liga", "Liga MX", "Eerste Divisie",
                 "Liga Portugal 2", "1. Lig", "Saudi Pro League", "Scottish Championship"}
STD_QUOTA_LIMIT = 2.50  # Standard vs Alto Rendimento



def generate_reports(days=30):
    """Genera report v2.1 JSON + TXT da prediction_errors + daily_predictions_unified."""
    reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    os.makedirs(reports_dir, exist_ok=True)

    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    today_file = now.strftime('%Y-%m-%d_%H%M')
    from_date = now - timedelta(days=days)
    to_date = now
    from_str = from_date.strftime('%Y-%m-%d')
    to_str = to_date.strftime('%Y-%m-%d')

    coll_errors = db.prediction_errors
    coll_unified = db.daily_predictions_unified

    # Conta errori analizzati dal feedback loop
    analyzed_count = coll_errors.count_documents({"match_date": {"$gte": from_date, "$lte": to_date}})

    unified_docs = list(coll_unified.find(
        {"date": {"$gte": from_str, "$lte": to_str}},
        {"pronostici": 1, "league": 1, "date": 1, "streak_home": 1, "streak_away": 1}
    ))

    # ══════════════════════════════════════════════════════════
    # RACCOLTA DATI — contatori globali e Standard/Alto Rendimento
    # ══════════════════════════════════════════════════════════
    # Globali
    totals_by_type = Counter(); errors_by_type = Counter()
    # Standard (quota <= 2.50)
    std_totals_by_type = Counter(); std_errors_by_type = Counter()
    std_totals_by_source = Counter(); std_errors_by_source = Counter()
    std_totals_by_league = Counter(); std_errors_by_league = Counter()
    std_totals_by_quota_range = Counter(); std_errors_by_quota_range = Counter()
    std_totals_src_league = Counter(); std_errors_src_league = Counter()
    std_totals_quota_source = Counter(); std_errors_quota_source = Counter()
    std_totals_league_tipo = Counter(); std_errors_league_tipo = Counter()
    # Alto Rendimento (quota > 2.50)
    ar_totals_by_type = Counter(); ar_errors_by_type = Counter()
    ar_totals_by_quota_range = Counter(); ar_errors_by_quota_range = Counter()
    ar_pl_by_quota_range = Counter()  # P/L per fascia AR (tutti i pronostici)
    ar_total = 0; ar_errors = 0; ar_pl = 0.0
    # Weekly (tutti)
    weekly_totals = Counter(); weekly_errors = Counter()
    # P/L per tutti i pronostici (corretti + errati) — per pattern
    std_pl_src_league = Counter(); std_pl_quota_source = Counter()
    std_pl_league_tipo = Counter(); std_pl_by_quota_range = Counter()
    # Pattern detection
    streak_total = 0; streak_errors = 0; streak_pl = 0.0
    lowquota_hconf_total = 0; lowquota_hconf_errors = 0; lowquota_hconf_pl = 0.0
    highconf_total = 0; highconf_errors = 0; highconf_pl = 0.0
    c_minor_pl_all = 0.0  # P/L tutti i pronostici C su leghe minori

    total_predictions = 0; total_errors_count = 0
    std_total = 0; std_errors_total = 0

    for doc in unified_docs:
        league = doc.get("league", "unknown")
        date_str = doc.get("date", "")
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            week_str = dt.strftime('%G-W%V')
        except (ValueError, TypeError):
            week_str = "unknown"

        streak_h = doc.get("streak_home") or {}
        streak_a = doc.get("streak_away") or {}
        has_long_streak = (
            streak_h.get("vittorie", 0) >= 4 or
            streak_a.get("senza_vittorie", 0) >= 6 or
            streak_h.get("sconfitte", 0) >= 4 or
            streak_a.get("vittorie", 0) >= 4
        )

        for p in doc.get("pronostici", []):
            esito = p.get("esito")
            if esito is None:
                continue

            tipo = p.get("tipo", "ALTRO")
            source = p.get("source", "unknown")
            quota = p.get("quota")
            qr = _get_quota_range(quota)
            confidence = p.get("confidence", 0) or 0
            pl = p.get("profit_loss", 0) or 0
            is_error = esito is False
            is_std = quota is not None and quota <= STD_QUOTA_LIMIT

            total_predictions += 1
            totals_by_type[tipo] += 1
            weekly_totals[week_str] += 1

            if is_error:
                total_errors_count += 1
                errors_by_type[tipo] += 1
                weekly_errors[week_str] += 1

            if is_std:
                std_total += 1
                std_totals_by_type[tipo] += 1
                std_totals_by_source[source] += 1
                std_totals_by_league[league] += 1
                if qr:
                    std_totals_by_quota_range[qr] += 1
                    std_pl_by_quota_range[qr] += pl
                std_totals_src_league[(source, league)] += 1
                std_pl_src_league[(source, league)] += pl
                if qr:
                    std_totals_quota_source[(qr, source)] += 1
                    std_pl_quota_source[(qr, source)] += pl
                std_totals_league_tipo[(league, tipo)] += 1
                std_pl_league_tipo[(league, tipo)] += pl

                # C su leghe minori (tutti)
                if source.startswith("C") and league in MINOR_LEAGUES:
                    c_minor_pl_all += pl

                if has_long_streak:
                    streak_total += 1
                    streak_pl += pl
                if quota and quota < 1.50 and confidence > 70:
                    lowquota_hconf_total += 1
                    lowquota_hconf_pl += pl
                if confidence > 70:
                    highconf_total += 1
                    highconf_pl += pl

                if is_error:
                    std_errors_total += 1
                    std_errors_by_type[tipo] += 1
                    std_errors_by_source[source] += 1
                    std_errors_by_league[league] += 1
                    if qr:
                        std_errors_by_quota_range[qr] += 1
                    std_errors_src_league[(source, league)] += 1
                    if qr:
                        std_errors_quota_source[(qr, source)] += 1
                    std_errors_league_tipo[(league, tipo)] += 1

                    if has_long_streak:
                        streak_errors += 1
                    if quota and quota < 1.50 and confidence > 70:
                        lowquota_hconf_errors += 1
                    if confidence > 70:
                        highconf_errors += 1
            else:
                ar_total += 1
                ar_totals_by_type[tipo] += 1
                if qr:
                    ar_totals_by_quota_range[qr] += 1
                    ar_pl_by_quota_range[qr] += pl
                if is_error:
                    ar_errors += 1
                    ar_errors_by_type[tipo] += 1
                    if qr:
                        ar_errors_by_quota_range[qr] += 1
                ar_pl += pl

    if total_predictions == 0:
        print(f"📊 Nessun pronostico nel periodo — report non generato")
        return

    avg_error_rate = round(total_errors_count / total_predictions * 100, 1)
    total_correct = total_predictions - total_errors_count
    std_correct = std_total - std_errors_total
    std_error_rate = round(std_errors_total / std_total * 100, 1) if std_total else 0
    ar_correct = ar_total - ar_errors
    ar_error_rate = round(ar_errors / ar_total * 100, 1) if ar_total else 0
    not_analyzed = total_errors_count - analyzed_count

    # ══════════════════════════════════════════════════════════
    # SEZ 1 — PANORAMICA
    # ══════════════════════════════════════════════════════════
    by_type = []
    for tipo in sorted(totals_by_type.keys()):
        t = totals_by_type[tipo]; e = errors_by_type.get(tipo, 0)
        by_type.append({"type": tipo, "total": t, "errors": e, "error_rate": round(e / t * 100, 1) if t else 0})
    by_type.sort(key=lambda x: x["error_rate"], reverse=True)

    std_by_type = []
    for tipo in sorted(std_totals_by_type.keys()):
        t = std_totals_by_type[tipo]; e = std_errors_by_type.get(tipo, 0)
        std_by_type.append({"type": tipo, "total": t, "errors": e, "error_rate": round(e / t * 100, 1) if t else 0})
    std_by_type.sort(key=lambda x: x["error_rate"], reverse=True)

    ar_by_type = []
    for tipo in sorted(ar_totals_by_type.keys()):
        t = ar_totals_by_type[tipo]; e = ar_errors_by_type.get(tipo, 0)
        ar_by_type.append({"type": tipo, "total": t, "errors": e, "error_rate": round(e / t * 100, 1) if t else 0})
    ar_by_type.sort(key=lambda x: x["error_rate"], reverse=True)

    overview = {
        "total_predictions": total_predictions, "correct": total_correct,
        "errors": total_errors_count, "error_rate": avg_error_rate,
        "analyzed": analyzed_count, "not_analyzed": not_analyzed,
        "by_type": by_type,
        "standard": {"total": std_total, "correct": std_correct, "errors": std_errors_total,
                     "error_rate": std_error_rate, "by_type": std_by_type},
        "alto_rendimento": {"total": ar_total, "correct": ar_correct, "errors": ar_errors,
                           "error_rate": ar_error_rate, "profit_loss": ar_pl, "by_type": ar_by_type},
    }

    # ══════════════════════════════════════════════════════════
    # SEZ 2 — PER SOURCE (solo Standard)
    # ══════════════════════════════════════════════════════════
    by_source = []
    for src in sorted(std_totals_by_source.keys()):
        t = std_totals_by_source[src]; e = std_errors_by_source.get(src, 0); c = t - e
        rate = round(e / t * 100, 1) if t else 0
        delta = round(rate - std_error_rate, 1)
        flag = "⚠️" if delta > 5 else ("✓" if delta < -3 else "")
        by_source.append({"source": src, "total": t, "correct": c, "errors": e,
                          "error_rate": rate, "delta": delta, "flag": flag})
    by_source.sort(key=lambda x: x["error_rate"], reverse=True)

    # ══════════════════════════════════════════════════════════
    # SEZ 3 — PER LEAGUE (solo Standard)
    # ══════════════════════════════════════════════════════════
    by_league = []
    for lg in sorted(std_totals_by_league.keys()):
        t = std_totals_by_league[lg]; e = std_errors_by_league.get(lg, 0)
        rate = round(e / t * 100, 1) if t else 0
        delta = round(rate - std_error_rate, 1)
        flag = "⚠️" if delta > 5 else ("✓" if delta < -3 else "")
        by_league.append({"league": lg, "total": t, "errors": e,
                          "error_rate": rate, "delta": delta, "flag": flag})
    by_league.sort(key=lambda x: x["error_rate"], reverse=True)

    # ══════════════════════════════════════════════════════════
    # SEZ 4 — ANALISI INCROCIATA (solo Standard)
    # ══════════════════════════════════════════════════════════
    source_x_league = []
    for (src, lg), t in std_totals_src_league.items():
        if t < 5:
            continue
        e = std_errors_src_league.get((src, lg), 0)
        rate = round(e / t * 100, 1)
        delta = round(rate - std_error_rate, 1)
        if abs(delta) > 8:
            flag = "🔴" if delta > 15 else ("🟡" if delta > 8 else "🟢")
            source_x_league.append({"source": src, "league": lg, "total": t, "errors": e,
                                    "error_rate": rate, "delta": delta, "flag": flag})
    source_x_league.sort(key=lambda x: x["error_rate"], reverse=True)

    by_quota_range = []
    for qr in STD_QUOTA_RANGES:
        t = std_totals_by_quota_range.get(qr, 0)
        if t == 0:
            continue
        e = std_errors_by_quota_range.get(qr, 0)
        rate = round(e / t * 100, 1)
        by_quota_range.append({"range": qr, "total": t, "errors": e, "error_rate": rate})

    ar_by_quota_range = []
    for qr in AR_QUOTA_RANGES:
        t = ar_totals_by_quota_range.get(qr, 0)
        if t == 0:
            continue
        e = ar_errors_by_quota_range.get(qr, 0)
        rate = round(e / t * 100, 1)
        pl_qr = round(ar_pl_by_quota_range.get(qr, 0), 2)
        ar_by_quota_range.append({"range": qr, "total": t, "errors": e, "error_rate": rate, "profit_loss": pl_qr})

    quota_x_source = []
    for (qr, src), t in std_totals_quota_source.items():
        if t < 5:
            continue
        e = std_errors_quota_source.get((qr, src), 0)
        rate = round(e / t * 100, 1)
        delta = round(rate - std_error_rate, 1)
        if abs(delta) > 8:
            flag = "🔴" if delta > 15 else ("✓" if delta < -8 else "🟡")
            quota_x_source.append({"range": qr, "source": src, "total": t, "errors": e,
                                   "error_rate": rate, "delta": delta, "flag": flag})
    quota_x_source.sort(key=lambda x: x["error_rate"], reverse=True)

    cross_analysis = {
        "source_x_league": source_x_league[:15],
        "by_quota_range": by_quota_range,
        "quota_x_source": quota_x_source[:10],
    }

    # ══════════════════════════════════════════════════════════
    # SEZ 5 — TREND SETTIMANALE
    # ══════════════════════════════════════════════════════════
    all_weeks = sorted(set(list(weekly_totals.keys()) + list(weekly_errors.keys())))
    all_weeks = [w for w in all_weeks if w != "unknown"]
    weekly_trend = []
    prev_rate = None
    consecutive_worse = 0
    last_two_weeks = []
    for w in all_weeks:
        t = weekly_totals.get(w, 0); e = weekly_errors.get(w, 0)
        rate = round(e / t * 100, 1) if t else 0
        small_sample = t < 20
        delta_prev = round(rate - prev_rate, 1) if prev_rate is not None else None
        if delta_prev is not None and not small_sample:
            if delta_prev > 2:
                trend = "📈"; consecutive_worse += 1
            elif delta_prev < -2:
                trend = "📉"; consecutive_worse = 0
            else:
                trend = "➡️"; consecutive_worse = 0
        else:
            trend = "—"
            if not small_sample and prev_rate is None:
                pass  # primo dato
        weekly_trend.append({"week": w, "total": t, "errors": e, "error_rate": rate,
                             "delta_prev": delta_prev, "trend": trend, "small_sample": small_sample})
        if not small_sample:
            prev_rate = rate
        last_two_weeks.append({"week": w, "rate": rate, "total": t})

    weekly_warning = None
    sig_weeks = [wt for wt in weekly_trend if not wt["small_sample"]]
    if consecutive_worse >= 2:
        if len(sig_weeks) >= 2:
            w1, w2 = sig_weeks[-2], sig_weeks[-1]
            weekly_warning = (f"⚠️ ALERT: Tasso errore in peggioramento per {consecutive_worse} settimane consecutive "
                              f"({w1['week']}: {w1['error_rate']}% → {w2['week']}: {w2['error_rate']}%). "
                              f"Verificare se è dovuto a cambio leghe coperte o degradazione modello.")
    elif not weekly_warning and len(sig_weeks) >= 2:
        # Regola alternativa: tra le ultime 3 settimane significative, se almeno 2 sono sopra media std → warning
        recent = sig_weeks[-3:] if len(sig_weeks) >= 3 else sig_weeks[-2:]
        above_avg = [w for w in recent if w["error_rate"] > std_error_rate]
        if len(above_avg) >= 2:
            w1, w2 = above_avg[-2], above_avg[-1]
            weekly_warning = (f"⚠️ ALERT: Tasso errore in peggioramento "
                              f"({w1['week']}: {w1['error_rate']}% → {w2['week']}: {w2['error_rate']}%). "
                              f"Verificare se dovuto a cambio leghe coperte o degradazione modello.")

    # ══════════════════════════════════════════════════════════
    # SEZ 6 — PATTERN DETECTION (dai dati, non da Mistral)
    # ══════════════════════════════════════════════════════════
    patterns_detected = []
    MIN_PAT_NEG = 8   # soglia minima pronostici per pattern negativo
    MIN_PAT_POS = 10  # soglia minima pronostici per pattern positivo
    DELTA_NEG = 8     # delta minimo per pattern negativo
    DELTA_POS = 6     # delta minimo per pattern positivo

    # Pattern: Sistema C su leghe minori
    c_minor_total = 0; c_minor_errors = 0
    for (src, lg), t in std_totals_src_league.items():
        if src.startswith("C") and lg in MINOR_LEAGUES:
            c_minor_total += t
            c_minor_errors += std_errors_src_league.get((src, lg), 0)
    if c_minor_total >= MIN_PAT_NEG:
        c_minor_rate = round(c_minor_errors / c_minor_total * 100, 1)
        c_minor_delta = round(c_minor_rate - std_error_rate, 1)
        if c_minor_delta > DELTA_NEG:
            color = "🔴" if c_minor_delta > 15 else "🟡"
            patterns_detected.append({
                "name": "Sistema C su leghe minori", "positive": False, "color": color,
                "where": "Source C/C_screm × Serie C + Ligue 2 + 2. Bundesliga + ...",
                "total": c_minor_total, "errors": c_minor_errors,
                "error_rate": c_minor_rate, "delta": c_minor_delta, "impact_pl": round(c_minor_pl_all, 2),
            })

    # Pattern: Quote basse + confidence alta
    if lowquota_hconf_total >= MIN_PAT_NEG:
        lq_rate = round(lowquota_hconf_errors / lowquota_hconf_total * 100, 1)
        lq_delta = round(lq_rate - std_error_rate, 1)
        if lq_delta > DELTA_NEG:
            color = "🔴" if lq_delta > 15 else "🟡"
            patterns_detected.append({
                "name": "Quote basse + confidence alta", "positive": False, "color": color,
                "where": "Quota < 1.50, confidence > 70%",
                "total": lowquota_hconf_total, "errors": lowquota_hconf_errors,
                "error_rate": lq_rate, "delta": lq_delta, "impact_pl": round(lowquota_hconf_pl, 2),
            })

    # Pattern: Confidence alta in generale
    if highconf_total >= MIN_PAT_NEG:
        hc_rate = round(highconf_errors / highconf_total * 100, 1)
        hc_delta = round(hc_rate - std_error_rate, 1)
        if hc_delta > DELTA_NEG:
            color = "🔴" if hc_delta > 15 else "🟡"
            patterns_detected.append({
                "name": "Pronostici con confidence > 70%", "positive": False, "color": color,
                "where": "Qualsiasi source/league, confidence > 70%",
                "total": highconf_total, "errors": highconf_errors,
                "error_rate": hc_rate, "delta": hc_delta, "impact_pl": round(highconf_pl, 2),
            })

    # Pattern: Striscia lunga interrotta
    if streak_total >= MIN_PAT_NEG:
        s_rate = round(streak_errors / streak_total * 100, 1)
        s_delta = round(s_rate - std_error_rate, 1)
        if s_delta > DELTA_NEG:
            color = "🔴" if s_delta > 15 else "🟡"
            patterns_detected.append({
                "name": "Striscia lunga interrotta", "positive": False, "color": color,
                "where": "streak vittorie ≥ 4 OPPURE senza_vittorie ≥ 6",
                "total": streak_total, "errors": streak_errors,
                "error_rate": s_rate, "delta": s_delta, "impact_pl": round(streak_pl, 2),
            })

    # Pattern: Source × fascia quota (negativi)
    for (qr, src), t in std_totals_quota_source.items():
        if t < MIN_PAT_NEG:
            continue
        e = std_errors_quota_source.get((qr, src), 0)
        rate = round(e / t * 100, 1)
        delta = round(rate - std_error_rate, 1)
        if delta > DELTA_NEG:
            color = "🔴" if delta > 15 else "🟡"
            pl = round(std_pl_quota_source.get((qr, src), 0), 2)
            patterns_detected.append({
                "name": f"Source {src} con quota {qr}", "positive": False, "color": color,
                "where": f"Source {src} × fascia quota {qr}",
                "total": t, "errors": e,
                "error_rate": rate, "delta": delta, "impact_pl": pl,
            })

    # Pattern: League × tipo pronostico (negativi)
    for (lg, tipo), t in std_totals_league_tipo.items():
        if t < MIN_PAT_NEG:
            continue
        e = std_errors_league_tipo.get((lg, tipo), 0)
        rate = round(e / t * 100, 1)
        delta = round(rate - std_error_rate, 1)
        if delta > DELTA_NEG:
            color = "🔴" if delta > 15 else "🟡"
            pl = round(std_pl_league_tipo.get((lg, tipo), 0), 2)
            patterns_detected.append({
                "name": f"{tipo} su {lg}", "positive": False, "color": color,
                "where": f"Tipo {tipo} × {lg}",
                "total": t, "errors": e,
                "error_rate": rate, "delta": delta, "impact_pl": pl,
            })

    # Pattern: Source × League negativi
    for (src, lg), t in std_totals_src_league.items():
        if t < MIN_PAT_NEG:
            continue
        e = std_errors_src_league.get((src, lg), 0)
        rate = round(e / t * 100, 1)
        delta = round(rate - std_error_rate, 1)
        if delta > DELTA_NEG:
            color = "🔴" if delta > 15 else "🟡"
            pl = round(std_pl_src_league.get((src, lg), 0), 2)
            patterns_detected.append({
                "name": f"Source {src} su {lg}", "positive": False, "color": color,
                "where": f"Source {src} × {lg}",
                "total": t, "errors": e,
                "error_rate": rate, "delta": delta, "impact_pl": pl,
            })

    # Pattern positivi: Source × League
    for (src, lg), t in std_totals_src_league.items():
        if t < MIN_PAT_POS:
            continue
        e = std_errors_src_league.get((src, lg), 0)
        rate = round(e / t * 100, 1)
        delta = round(rate - std_error_rate, 1)
        if delta < -DELTA_POS:
            pl = round(std_pl_src_league.get((src, lg), 0), 2)
            patterns_detected.append({
                "name": f"Source {src} su {lg}", "positive": True, "color": "🟢",
                "where": f"Source {src} × {lg}",
                "total": t, "errors": e,
                "error_rate": rate, "delta": delta, "impact_pl": pl,
            })

    # Deduplica per nome (tieni quello con impact_pl più estremo)
    seen = {}
    for p in patterns_detected:
        key = p["name"]
        if key not in seen or abs(p.get("impact_pl", 0)) > abs(seen[key].get("impact_pl", 0)):
            seen[key] = p
    patterns_detected = list(seen.values())

    neg_patterns = sorted([p for p in patterns_detected if not p["positive"]],
                          key=lambda x: x.get("impact_pl", 0))[:7]
    pos_patterns = sorted([p for p in patterns_detected if p["positive"]],
                          key=lambda x: x.get("impact_pl", 0), reverse=True)[:3]
    patterns_detected = neg_patterns + pos_patterns

    # ══════════════════════════════════════════════════════════
    # SEZ 7 — RACCOMANDAZIONI (consolidate per causa comune)
    # ══════════════════════════════════════════════════════════
    recommendations = []
    if total_predictions < 1000 and not patterns_detected:
        recommendations.append(
            "Dataset insufficiente per raccomandazioni affidabili. "
            f"Servono almeno 1000+ pronostici (attualmente {total_predictions}).")

    # Consolida pattern negativi per causa comune
    neg_pats = [p for p in patterns_detected if not p["positive"]]
    pos_pats = [p for p in patterns_detected if p["positive"]]

    # Raggruppa per fascia quota (se 3+ pattern nella stessa fascia)
    quota_groups = {}
    league_groups = {}
    standalone = []
    for pat in neg_pats:
        # Estrai fascia quota dal nome/where
        matched_qr = None
        for qr in STD_QUOTA_RANGES + AR_QUOTA_RANGES:
            if qr in pat.get("where", "") or qr in pat.get("name", ""):
                matched_qr = qr
                break
        # Estrai league
        matched_lg = None
        for lg_key in std_totals_by_league.keys():
            if lg_key in pat.get("where", "") or lg_key in pat.get("name", ""):
                matched_lg = lg_key
                break

        if matched_qr:
            quota_groups.setdefault(matched_qr, []).append(pat)
        elif matched_lg:
            league_groups.setdefault(matched_lg, []).append(pat)
        else:
            standalone.append(pat)

    # Genera raccomandazioni consolidate
    used_pats = set()

    # Consolida per fascia quota (3+ pattern → 1 raccomandazione)
    for qr, pats in sorted(quota_groups.items(), key=lambda x: -len(x[1])):
        if len(pats) >= 3:
            total_pron = sum(p["total"] for p in pats)
            avg_rate = round(sum(p["error_rate"] * p["total"] for p in pats) / total_pron, 1) if total_pron else 0
            details = ", ".join(f"{p['name'].replace(f' con quota {qr}', '')}: {p['error_rate']}%" for p in pats[:4])
            rec = (f"FASCIA QUOTA {qr}: Tasso errore {avg_rate}% su {total_pron} pronostici — "
                   f"problema trasversale a più source ({details}). "
                   f"Ridurre stake del 30% per TUTTI i pronostici in questa fascia, "
                   f"oppure alzare la soglia minima di edge richiesto.")
            recommendations.append(rec)
            for p in pats:
                used_pats.add(id(p))
        else:
            for p in pats:
                standalone.append(p)

    # Consolida per league (2+ pattern → 1 raccomandazione)
    for lg, pats in sorted(league_groups.items(), key=lambda x: -len(x[1])):
        if len(pats) >= 2:
            total_pron = sum(p["total"] for p in pats)
            avg_rate = round(sum(p["error_rate"] * p["total"] for p in pats) / total_pron, 1) if total_pron else 0
            details = ", ".join(f"{p['name'].replace(f' su {lg}', '')}: {p['error_rate']}%" for p in pats[:3])
            specifics = " e ".join(p['name'].replace(f' su {lg}', '') for p in pats[:3])
            rec = (f"RIDURRE STAKE: {lg} — tasso errore medio {avg_rate}% su {total_pron} pronostici "
                   f"({details}). Ridurre stake del 40% per {specifics} su {lg} e richiedere edge minimo 5%.")
            recommendations.append(rec)
            for p in pats:
                used_pats.add(id(p))
        else:
            for p in pats:
                standalone.append(p)

    # Pattern standalone (non consolidati)
    for pat in standalone:
        if id(pat) in used_pats:
            continue
        n = pat["total"]
        if n < 15:
            action = "MONITORARE"
            detail = (f"Campione piccolo ({n}) ma anomalia forte. "
                      f"Se persiste a 20+ pronostici, ridurre stake del 50%.")
        elif "leghe minori" in pat["name"].lower():
            action = "RIDURRE STAKE"
            detail = f"Ridurre stake del 40% e richiedere edge minimo 5%. P/L: {pat['impact_pl']}"
        elif "striscia" in pat["name"].lower():
            action = "ATTENUARE STRISCE"
            detail = "Ridurre il peso di 'strisce' del 25% quando la striscia supera 4 partite."
        elif "confidence" in pat["name"].lower():
            action = "CAP CONFIDENCE"
            detail = "Il modello è troppo sicuro. Ridurre confidence massima a 65%."
        else:
            action = "RIDURRE STAKE"
            detail = f"Ridurre stake del 30% e cap confidence a 55%. P/L: {pat['impact_pl']}"
        rec = (f"{action}: {pat['name']} — tasso errore {pat['error_rate']}% "
               f"({pat['delta']:+.1f}% vs media {std_error_rate}%). {detail}")
        recommendations.append(rec)

    # Limita a max 5 negative
    recommendations = recommendations[:5]

    # Pattern positivi (max 2)
    for pat in pos_pats[:2]:
        rec = (f"MANTENERE: {pat['name']} funziona bene ({pat['error_rate']}% errore, "
               f"{pat['delta']:+.1f}% vs media). P/L: {pat['impact_pl']}. Non modificare.")
        recommendations.append(rec)

    # ══════════════════════════════════════════════════════════
    # JSON REPORT
    # ══════════════════════════════════════════════════════════
    report_data = {
        "report_version": "2.2",
        "generated_at": f"{today}T{datetime.now().strftime('%H:%M:%S')}Z",
        "period": {"from": from_str, "to": to_str, "days": days},
        "overview": overview,
        "by_source": by_source,
        "by_league": by_league,
        "alto_rendimento_detail": {"by_quota_range": ar_by_quota_range, "total_pl": round(ar_pl, 2)},
        "cross_analysis": cross_analysis,
        "weekly_trend": weekly_trend,
        "weekly_warning": weekly_warning,
        "patterns_detected": patterns_detected,
        "recommendations": recommendations,
    }

    json_path = os.path.join(reports_dir, f"feedback_report_{today_file}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    # ══════════════════════════════════════════════════════════
    # TXT REPORT (7 sezioni)
    # ══════════════════════════════════════════════════════════
    W = 66
    L = []
    a = L.append

    a("═" * W)
    a(f"  FEEDBACK LOOP REPORT v2.2 — {today}")
    a(f"  Periodo: {from_str} → {to_str} ({days} giorni)")
    a("═" * W)
    a("")

    # SEZ 1 — Panoramica
    a("PANORAMICA")
    a("─" * W)
    a(f"  Pronostici totali emessi:     {total_predictions}")
    a(f"  Corretti:                     {total_correct}  ({round(total_correct/total_predictions*100,1)}%)")
    a(f"  Errati:                       {total_errors_count}  ({avg_error_rate}%)")
    a(f"  Analizzati dal feedback loop: {analyzed_count}  ({not_analyzed} senza risultato)")
    a("")
    a("  STANDARD (quota ≤ 2.50)")
    a("  ─────────────────────────")
    a(f"  Emessi: {std_total} | Corretti: {std_correct} ({round(std_correct/std_total*100,1) if std_total else 0}%)"
      f" | Errati: {std_errors_total} ({std_error_rate}%)")
    best_std = min(std_by_type, key=lambda x: x["error_rate"]) if std_by_type else None
    worst_std = max(std_by_type, key=lambda x: x["error_rate"]) if std_by_type else None
    for t in std_by_type:
        note = ""
        if t == worst_std:
            note = "  ← peggiore"
        elif t == best_std:
            note = "  ← migliore"
        a(f"    {t['type']:<18} {t['total']:>4} emessi → {t['errors']:>3} errati  ({t['error_rate']:>5.1f}%){note}")
    a("")
    a("  ALTO RENDIMENTO (quota > 2.50)")
    a("  ─────────────────────────────")
    a(f"  Emessi: {ar_total} | Corretti: {ar_correct} ({round(ar_correct/ar_total*100,1) if ar_total else 0}%)"
      f" | Errati: {ar_errors} ({ar_error_rate}%)")
    for t in ar_by_type:
        a(f"    {t['type']:<18} {t['total']:>4} emessi → {t['errors']:>3} errati  ({t['error_rate']:>5.1f}%)")
    a("")

    # SEZ 2 — Per Source (Standard)
    a("ANALISI PER SOURCE (Standard)")
    a("─" * W)
    a(f"  {'Source':<13} {'Emessi':>7} {'Corretti':>9} {'Errati':>7} {'Tasso':>7} {'Δ media':>8}")
    a(f"  {'─'*13} {'─'*7} {'─'*9} {'─'*7} {'─'*7} {'─'*8}")
    for s in by_source:
        delta_str = f"{'+' if s['delta']>=0 else ''}{s['delta']}%"
        a(f"  {s['source']:<13} {s['total']:>7} {s['correct']:>9} {s['errors']:>7} {s['error_rate']:>6.1f}% {delta_str:>7}  {s['flag']}")
    a(f"  {'─'*W}")
    a(f"  MEDIA STANDARD{' '*36}{std_error_rate:>6.1f}%")
    a("")

    # SEZ 3 — Per League (Standard)
    a("ANALISI PER LEAGUE (Standard)")
    a("─" * W)
    a(f"  {'League':<28} {'Emessi':>7} {'Errati':>7} {'Tasso':>7} {'Δ media':>8}")
    a(f"  {'─'*28} {'─'*7} {'─'*7} {'─'*7} {'─'*8}")
    for lg in by_league[:20]:
        delta_str = f"{'+' if lg['delta']>=0 else ''}{lg['delta']}%"
        a(f"  {lg['league']:<28} {lg['total']:>7} {lg['errors']:>7} {lg['error_rate']:>6.1f}% {delta_str:>7}  {lg['flag']}")
    a("")

    # SEZ 4 — Analisi incrociata (Standard)
    a("ANALISI INCROCIATA — Combinazioni anomale (Standard)")
    a("─" * W)
    if source_x_league:
        a(f"  {'Source × League':<40} {'Emessi':>7} {'Errati':>7} {'Tasso':>6} {'Δ':>7}")
        a(f"  {'─'*40} {'─'*7} {'─'*7} {'─'*6} {'─'*7}")
        for sx in source_x_league[:10]:
            label = f"{sx['source']} × {sx['league']}"
            if len(label) > 40:
                label = label[:37] + "..."
            a(f"  {label:<40} {sx['total']:>7} {sx['errors']:>7} {sx['error_rate']:>5.1f}% {sx['delta']:>+6.1f}%  {sx['flag']}")
    a("")

    a("ANALISI PER FASCIA QUOTA (Standard)")
    a("─" * W)
    a(f"  {'Fascia quota':<18} {'Emessi':>7} {'Errati':>7} {'Tasso':>7}")
    a(f"  {'─'*18} {'─'*7} {'─'*7} {'─'*7}")
    has_small_qr = False
    for qr in by_quota_range:
        small = "*" if qr["total"] < 5 else " "
        if qr["total"] < 5:
            has_small_qr = True
        a(f" {small}{qr['range']:<18} {qr['total']:>7} {qr['errors']:>7} {qr['error_rate']:>6.1f}%")
    if has_small_qr:
        a("  * campione < 5")
    # Insight: confronta fascia più bassa vs più alta
    std_qr_data = [q for q in by_quota_range if q["range"] in STD_QUOTA_RANGES and q["total"] >= 5]
    if len(std_qr_data) >= 2:
        worst_qr = max(std_qr_data, key=lambda x: x["error_rate"])
        best_qr = min(std_qr_data, key=lambda x: x["error_rate"])
        a(f"  INSIGHT: {worst_qr['range']}: {worst_qr['error_rate']}% errore vs {best_qr['range']}: {best_qr['error_rate']}% errore")
    a("")

    if quota_x_source:
        a("INCROCIO QUOTA × SOURCE (solo anomalie)")
        a("─" * W)
        for qs in quota_x_source[:8]:
            a(f"  Source {qs['source']} con quota {qs['range']}: {qs['total']} emessi → {qs['errors']} errati ({qs['error_rate']}%)  {qs['flag']}")
        a("")

    # SEZ 5 — Trend settimanale
    a("TREND SETTIMANALE")
    a("─" * W)
    a(f"  {'Settimana':<11} {'Emessi':>7} {'Errati':>7} {'Tasso':>6} {'Δ sett.':>8} {'Trend':>6}")
    a(f"  {'─'*11} {'─'*7} {'─'*7} {'─'*6} {'─'*8} {'─'*6}")
    for w in weekly_trend:
        d_str = f"{w['delta_prev']:+.1f}%" if w['delta_prev'] is not None else "—"
        prefix = "* " if w.get("small_sample") else "  "
        a(f"{prefix}{w['week']:<11} {w['total']:>7} {w['errors']:>7} {w['error_rate']:>5.1f}% {d_str:>7}  {w['trend']}")
    has_small = any(w.get("small_sample") for w in weekly_trend)
    if has_small:
        a("  * campione < 20, non significativo")
    if weekly_warning:
        a(f"  {weekly_warning}")
    a("")

    # SEZ 5b — Alto Rendimento dedicata
    a("ALTO RENDIMENTO (quota > 2.50) — Analisi dedicata")
    a("─" * W)
    a(f"  Emessi: {ar_total} | Corretti: {ar_correct} ({round(ar_correct/ar_total*100,1) if ar_total else 0}%)"
      f" | Errati: {ar_errors} ({ar_error_rate}%)")
    a(f"  Bilancio P/L totale: {ar_pl:+.1f} unità")
    a("")
    a("  Per fascia:")
    has_ar_small = False
    for qr in AR_QUOTA_RANGES:
        t_ar = ar_totals_by_quota_range.get(qr, 0)
        if t_ar == 0:
            continue
        e_ar = ar_errors_by_quota_range.get(qr, 0)
        rate_ar = round(e_ar / t_ar * 100, 1)
        pl_ar = ar_pl_by_quota_range.get(qr, 0)
        small = "*" if t_ar < 5 else " "
        if t_ar < 5:
            has_ar_small = True
        a(f"   {small}{qr:<12} {t_ar:>3} emessi → {e_ar:>2} errati ({rate_ar:>5.1f}%)  P/L: {pl_ar:+.1f}")
    if has_ar_small:
        a("  * campione < 5")
    a("")
    if ar_pl >= 0:
        a("  Verdict: Il profitto compensa le perdite (P/L positivo).")
    else:
        a("  Verdict: Le perdite superano i profitti — valutare se mantenere.")
    a("")

    # SEZ 6 — Pattern detection
    a("PATTERN RILEVATI (basati sui dati, non sui tag Mistral)")
    a("─" * W)
    if not patterns_detected:
        a("  Nessun pattern significativo rilevato nel periodo.")
    for pat in patterns_detected:
        a("")
        a(f"  {pat['color']} PATTERN: {pat['name']}")
        a(f"     Dove: {pat['where']}")
        a(f"     Tasso errore: {pat['error_rate']}% (vs {std_error_rate}% media std)")
        a(f"     Pronostici coinvolti: {pat['total']}")
        a(f"     Impact P/L: {pat['impact_pl']}")
    a("")

    # SEZ 7 — Raccomandazioni
    a("RACCOMANDAZIONI (basate sui pattern rilevati)")
    a("═" * W)
    for i, rec in enumerate(recommendations, 1):
        a("")
        a(f"  {i}. {rec}")
    if not recommendations:
        a("")
        a("  Nessuna raccomandazione — nessun pattern anomalo rilevato.")
    a("")
    a("═" * W)

    txt_path = os.path.join(reports_dir, f"feedback_report_{today_file}.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L))

    print(f"📄 Report JSON: {json_path}")
    print(f"📄 Report TXT:  {txt_path}")

    # Cleanup DOPO il salvataggio: mantieni max 2 coppie (json+txt)
    _cleanup_old_reports(reports_dir, keep=2)


def generate_weekly_report(report_days=7):
    """Genera report settimanale in ai_engine/reports/weekly/."""
    weekly_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports", "weekly")
    os.makedirs(weekly_dir, exist_ok=True)

    # Usa la stessa logica di generate_reports ma salva con nome settimanale
    today = datetime.now()
    week_str = today.strftime('%G-W%V')

    # Genera il report giornaliero nella cartella weekly con nome settimanale
    reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")

    # Genera report standard (salva in reports/)
    generate_reports(days=report_days)

    # Copia il file più recente nella cartella weekly con nome settimanale
    import glob, shutil
    today_str = today.strftime('%Y-%m-%d')
    json_files = sorted(glob.glob(os.path.join(reports_dir, f"feedback_report_{today_str}_*.json")))
    if json_files:
        src_json = json_files[-1]  # il più recente
        src_txt = src_json.replace(".json", ".txt")
        dst_json = os.path.join(weekly_dir, f"feedback_weekly_{week_str}.json")
        dst_txt = os.path.join(weekly_dir, f"feedback_weekly_{week_str}.txt")
        shutil.copy2(src_json, dst_json)
        if os.path.exists(src_txt):
            shutil.copy2(src_txt, dst_txt)

        print(f"📊 Report settimanale: {dst_json}")
        print(f"📊 Report settimanale: {dst_txt}")
    else:
        print("⚠️ Nessun report giornaliero trovato da copiare per il weekly")


if __name__ == "__main__":
    main()
