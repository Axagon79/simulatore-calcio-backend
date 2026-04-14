"""
Test coefficiente di solidita su partite del 13 aprile 2026.
Usa le funzioni di generate_bollette_2.py per arricchire e calcolare.
"""
import os, sys, json

sys.path.insert(0, 'C:/Progetti/simulatore-calcio-backend/functions_python/ai_engine')
sys.path.insert(0, 'C:/Progetti/simulatore-calcio-backend/functions_python/ai_engine/calculators')

from config import db
from generate_bollette_2 import (
    enrich_pool_with_stats, calculate_solidity_coefficient, _format_match_stats
)

# 1. Costruisci pool dal 13 aprile
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

print(f"Pool: {len(pool)} partite del {today_str}\n")

# 2. Arricchisci
classifiche_cache = enrich_pool_with_stats(pool)

# 3. Calcola coefficiente
calculate_solidity_coefficient(pool, classifiche_cache)

# 4. Mostra risultati ordinati per coefficiente
pool_sorted = sorted(pool, key=lambda x: x.get("coeff_solidita") or 0, reverse=True)

for i, s in enumerate(pool_sorted):
    coeff = s.get("coeff_solidita")
    base = s.get("coeff_base", "?")
    molt = s.get("coeff_moltiplicatore", "?")
    ctx = s.get("coeff_contesto", {})
    det = s.get("coeff_dettaglio", {})
    dirs = s.get("coeff_direzioni", {})

    print(f"\n{'='*80}")
    print(f"#{i+1} | {s['home']} vs {s['away']} ({s['league']})")
    print(f"   Pronostico: {s['mercato']}: {s['pronostico']} @ {s['quota']}")
    print(f"   COEFFICIENTE: {coeff}/100 (base: {base} x {molt})")
    print(f"   Contesto: {ctx.get('pro',0)} pro / {ctx.get('contro',0)} contro ({ctx.get('mercato_type','?')})")
    print(f"   Dettaglio:")
    for k, v in det.items():
        dir_list = dirs.get(k, [])
        dir_str = f" -> {', '.join(dir_list)}" if dir_list else ""
        print(f"      {k:20s}: {v:5.1f}{dir_str}")
    print(f"\n   Stats Mistral:")
    print(_format_match_stats(s))

print(f"\n\n{'='*80}")
print("RIEPILOGO ORDINATO:")
print(f"{'='*80}")
for i, s in enumerate(pool_sorted):
    coeff = s.get("coeff_solidita", 0)
    base = s.get("coeff_base", 0)
    molt = s.get("coeff_moltiplicatore", 1.0)
    print(f"  {i+1:2d}. {coeff:5.1f}/100 (base:{base} x{molt}) | {s['home']:20s} vs {s['away']:20s} | {s['mercato']}: {s['pronostico']} @ {s['quota']}")
