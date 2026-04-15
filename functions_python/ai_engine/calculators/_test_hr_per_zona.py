"""
Test HR (Hit Rate) per zona di RH, RA e Coerenza.
Confronta le zone del coefficiente con i risultati reali.
"""
import os, sys, re
from datetime import datetime, timedelta

sys.path.insert(0, 'C:/Progetti/simulatore-calcio-backend/functions_python/ai_engine')
sys.path.insert(0, 'C:/Progetti/simulatore-calcio-backend/functions_python/ai_engine/calculators')

from config import db
from generate_bollette_2 import enrich_pool_with_stats, calculate_solidity_coefficient

# --- PERIODO ---
start = datetime(2026, 3, 15)
end = datetime(2026, 4, 13)
DATES = []
d = start
while d <= end:
    DATES.append(d.strftime('%Y-%m-%d'))
    d += timedelta(days=1)

print(f"Periodo: {DATES[0]} -> {DATES[-1]} ({len(DATES)} giorni)")

# --- POOL PRONOSTICI ---
pool = []
seen = set()
for day in DATES:
    docs = list(db.daily_predictions_unified.find(
        {"date": day},
        {"home": 1, "away": 1, "date": 1, "league": 1, "match_time": 1,
         "pronostici": 1, "streak_home": 1, "streak_away": 1}
    ))
    for doc in docs:
        home = doc.get("home", "")
        away = doc.get("away", "")
        mk = f"{home} vs {away}|{day}"
        if mk in seen:
            continue
        for p in doc.get("pronostici", []):
            if p.get("tipo") == "RISULTATO_ESATTO":
                continue
            quota = p.get("quota")
            if not quota or quota <= 1.0:
                continue
            pool.append({
                "match_key": mk,
                "home": home, "away": away, "league": doc.get("league", ""),
                "match_date": day, "match_time": doc.get("match_time", ""),
                "mercato": p.get("tipo", ""), "pronostico": p.get("pronostico", ""),
                "quota": round(quota, 2), "confidence": p.get("confidence", 0),
                "stars": p.get("stars", 0),
                "elite": p.get("elite", False),
                "streak_home": doc.get("streak_home", {}),
                "streak_away": doc.get("streak_away", {}),
            })
            seen.add(mk)
            break

print(f"Pool: {len(pool)} partite")

# --- ARRICCHISCI E CALCOLA COEFFICIENTI ---
classifiche_cache = enrich_pool_with_stats(pool)
calculate_solidity_coefficient(pool, classifiche_cache)

calcolati = [s for s in pool if s.get("rapporto_home") is not None]
print(f"Calcolati: {len(calcolati)}/{len(pool)}")

# --- CERCA RISULTATI REALI ---
def parse_score(score_str):
    """Parsa 'H:A' -> (int, int) o None"""
    if not score_str or not isinstance(score_str, str):
        return None
    parts = score_str.split(":")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0].strip()), int(parts[1].strip())
    except:
        return None

def check_pronostico(pronostico, mercato, home_goals, away_goals):
    """Verifica se un pronostico è stato azzeccato."""
    p = pronostico.strip().upper()
    m = mercato.strip().upper()
    total = home_goals + away_goals

    if m == "SEGNO" or "SEGNO" in m:
        if p == "1":
            return home_goals > away_goals
        elif p == "X":
            return home_goals == away_goals
        elif p == "2":
            return home_goals < away_goals
        elif p == "1X":
            return home_goals >= away_goals
        elif p == "X2":
            return home_goals <= away_goals
        elif p == "12":
            return home_goals != away_goals

    if m == "DOPPIA_CHANCE":
        if p == "1X":
            return home_goals >= away_goals
        elif p == "X2":
            return home_goals <= away_goals
        elif p == "12":
            return home_goals != away_goals

    if m == "GOL" or "GOL" in m:
        if p in ("OVER 2.5", "O2.5", "OVER"):
            return total > 2.5
        elif p in ("UNDER 2.5", "U2.5", "UNDER"):
            return total < 2.5
        elif p in ("OVER 1.5", "O1.5"):
            return total > 1.5
        elif p in ("UNDER 1.5", "U1.5"):
            return total < 1.5
        elif p in ("OVER 3.5", "O3.5"):
            return total > 3.5
        elif p in ("UNDER 3.5", "U3.5"):
            return total < 3.5
        elif p in ("GG", "GOAL"):
            return home_goals > 0 and away_goals > 0
        elif p in ("NG", "NO GOAL", "NOGOAL"):
            return home_goals == 0 or away_goals == 0
        # Multigol
        mg = re.match(r'(?:MG\s*|MULTIGOL\s*)(\d+)[- ](\d+)', p)
        if mg:
            lo, hi = int(mg.group(1)), int(mg.group(2))
            return lo <= total <= hi

    return None  # non verificabile

# Cerca risultati in h2h_by_round
results_cache = {}
for s in calcolati:
    home = s["home"]
    away = s["away"]
    date = s["match_date"]

    key = f"{home}|{away}|{date}"
    if key in results_cache:
        score = results_cache[key]
    else:
        # Cerca in h2h_by_round — date_obj è datetime, non stringa
        score = None
        for delta in [0, -1, 1]:
            d_base = datetime.strptime(date, '%Y-%m-%d') + timedelta(days=delta)
            d_start = d_base
            d_end = d_base + timedelta(days=1)
            docs = list(db.h2h_by_round.find(
                {"matches": {"$elemMatch": {
                    "home": home, "away": away,
                    "date_obj": {"$gte": d_start, "$lt": d_end}
                }}},
                {"matches.$": 1}
            ))
            if docs:
                m = docs[0].get("matches", [{}])[0]
                rs = m.get("real_score")
                parsed = parse_score(rs)
                if parsed:
                    score = parsed
                    break
        results_cache[key] = score

    if score:
        s["home_goals"] = score[0]
        s["away_goals"] = score[1]
        esito = check_pronostico(s["pronostico"], s["mercato"], score[0], score[1])
        s["esito_reale"] = esito
    else:
        s["esito_reale"] = None

# --- FILTRA VERIFICABILI ---
verificabili = [s for s in calcolati if s.get("esito_reale") is not None]
print(f"Con risultato verificabile: {len(verificabili)}/{len(calcolati)}")

# --- CALCOLO HR PER ZONA ---
def test_tagli(tagli, nome_set):
    """Testa un set di tagli su tutti e 3 i campi."""
    zone_names = ["NERA", "ROSSA", "GIALLA", "VERDE", "V.SCURO"]

    def get_zona(v):
        if v < tagli[0]: return 0  # NERA
        if v < tagli[1]: return 1  # ROSSA
        if v < tagli[2]: return 2  # GIALLA
        if v < tagli[3]: return 3  # VERDE
        return 4  # V.SCURO

    fields = [
        ("rapporto_home", "RH"),
        ("rapporto_away", "RA"),
        ("coerenza_rapporti", "C"),
    ]

    print(f"\n{'#'*80}")
    print(f"  SET: {nome_set}  —  Tagli: {tagli}")
    print(f"{'#'*80}")

    total_score = 0

    for field, label in fields:
        zone_data = [{"win": 0, "tot": 0} for _ in range(5)]

        for s in verificabili:
            v = s.get(field, 0)
            z = get_zona(v)
            zone_data[z]["tot"] += 1
            if s["esito_reale"]:
                zone_data[z]["win"] += 1

        hrs = []
        print(f"\n  {label}:")
        print(f"  {'Zona':<12s} {'Range':<15s} {'Partite':>8s} {'Vinte':>8s} {'HR':>8s}")
        print(f"  {'-'*55}")

        ranges = [f"<{tagli[0]}", f"{tagli[0]}-{tagli[1]}", f"{tagli[1]}-{tagli[2]}", f"{tagli[2]}-{tagli[3]}", f">{tagli[3]}"]

        for i in range(5):
            d = zone_data[i]
            hr = (d["win"] / d["tot"] * 100) if d["tot"] > 0 else 0
            hrs.append(hr)
            marker = " ★" if i == 2 else ""  # GIALLA = ottimale atteso
            print(f"  {zone_names[i]:<12s} {ranges[i]:<15s} {d['tot']:>8d} {d['win']:>8d} {hr:>7.1f}%{marker}")

        # Score: GIALLA deve avere HR più alta, NERA e V.SCURO le più basse
        # Punteggio = HR_GIALLA - max(HR_NERA, HR_V.SCURO) + (HR_GIALLA - HR media altre)
        gialla_hr = hrs[2]
        estremi_hr = max(hrs[0] if zone_data[0]["tot"] >= 5 else 0,
                         hrs[4] if zone_data[4]["tot"] >= 5 else 0)
        altre_hr = [hrs[i] for i in [0,1,3,4] if zone_data[i]["tot"] >= 5]
        media_altre = sum(altre_hr) / len(altre_hr) if altre_hr else 50

        score = gialla_hr - media_altre
        total_score += score
        print(f"  Score campana: {score:+.1f} (GIALLA {gialla_hr:.1f}% vs media altre {media_altre:.1f}%)")

    print(f"\n  >>> SCORE TOTALE: {total_score:+.1f}")
    return total_score

# Prova diversi set di tagli
candidati = [
    ([15, 30, 50, 65], "A: 15/30/50/65"),
    ([15, 30, 50, 70], "B: 15/30/50/70"),
    ([10, 25, 45, 60], "C: 10/25/45/60"),
    ([10, 25, 50, 65], "D: 10/25/50/65"),
    ([15, 30, 55, 70], "E: 15/30/55/70"),
    ([10, 30, 50, 65], "F: 10/30/50/65"),
    ([15, 35, 55, 70], "G: 15/35/55/70"),
    ([10, 25, 45, 65], "H: 10/25/45/65"),
    ([15, 30, 45, 60], "I: 15/30/45/60"),
    ([10, 30, 55, 70], "J: 10/30/55/70"),
    ([15, 35, 50, 65], "K: 15/35/50/65"),
    ([10, 30, 50, 70], "L: 10/30/50/70"),
]

scores = []
for tagli, nome in candidati:
    s = test_tagli(tagli, nome)
    scores.append((s, nome, tagli))

scores.sort(reverse=True)
print(f"\n\n{'='*60}")
print(f"  CLASSIFICA MIGLIORI SET DI TAGLI")
print(f"{'='*60}")
for i, (s, nome, tagli) in enumerate(scores):
    print(f"  {i+1}. {nome:<25s} Score: {s:+.1f}")

