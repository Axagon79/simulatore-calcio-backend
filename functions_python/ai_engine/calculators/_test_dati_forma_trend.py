"""
Verifica quali dati forma/trend arrivano per le partite del 13 aprile.
"""
import os, sys

sys.path.insert(0, 'C:/Progetti/simulatore-calcio-backend/functions_python/ai_engine')
sys.path.insert(0, 'C:/Progetti/simulatore-calcio-backend/functions_python/ai_engine/calculators')

from config import db
from generate_bollette_2 import enrich_pool_with_stats

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
            "elite": p.get("elite", False),
            "streak_home": doc.get("streak_home", {}),
            "streak_away": doc.get("streak_away", {}),
        })
        seen.add(mk)
        break
    if len(pool) >= 15:
        break

print(f"Pool: {len(pool)} partite\n")
enrich_pool_with_stats(pool)

for s in pool:
    lh = s.get("lucifero_home_pct")
    la = s.get("lucifero_away_pct")
    th = s.get("trend_home", [])
    ta = s.get("trend_away", [])
    mh = s.get("motivazione_home")
    ma = s.get("motivazione_away")
    ac = s.get("affidabilita_casa")
    at = s.get("affidabilita_trasf")
    dh = s.get("dna_home")
    da = s.get("dna_away")
    sh = s.get("streak_home", {})
    sa = s.get("streak_away", {})
    ch = s.get("classifica_home")
    ca = s.get("classifica_away")

    print(f"{'='*70}")
    print(f"{s['home']} vs {s['away']} ({s['league']})")
    print(f"  classifica_home: {'OK' if ch else 'MANCA'}")
    print(f"  classifica_away: {'OK' if ca else 'MANCA'}")
    if ch:
        print(f"    home casa: v_casa={ch.get('v_casa')} n_casa={ch.get('n_casa')} p_casa={ch.get('p_casa')} gf_casa={ch.get('gf_casa')} gs_casa={ch.get('gs_casa')}")
    if ca:
        print(f"    away trasf: v_trasf={ca.get('v_trasf')} n_trasf={ca.get('n_trasf')} p_trasf={ca.get('p_trasf')} gf_trasf={ca.get('gf_trasf')} gs_trasf={ca.get('gs_trasf')}")
    print(f"  forma_home: {lh}")
    print(f"  forma_away: {la}")
    print(f"  trend_home: {th}")
    print(f"  trend_away: {ta}")
    print(f"  motivazione_home: {mh}")
    print(f"  motivazione_away: {ma}")
    print(f"  affidabilita_casa: {ac}")
    print(f"  affidabilita_trasf: {at}")
    print(f"  dna_home: {dh}")
    print(f"  dna_away: {da}")
    print(f"  streak_home: {sh}")
    print(f"  streak_away: {sa}")
