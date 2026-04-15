"""
Test distribuzione Q e D dal 15 marzo al 13 aprile 2026.
Tutte le partite, per definire le fasce reali dei coefficienti.
"""
import os, sys, json
from datetime import datetime, timedelta

sys.path.insert(0, 'C:/Progetti/simulatore-calcio-backend/functions_python/ai_engine')
sys.path.insert(0, 'C:/Progetti/simulatore-calcio-backend/functions_python/ai_engine/calculators')

from config import db
from generate_bollette_2 import (
    enrich_pool_with_stats, calculate_solidity_coefficient,
)

# Genera tutte le date dal 15 marzo al 13 aprile
start = datetime(2026, 3, 15)
end = datetime(2026, 4, 13)
DATES = []
d = start
while d <= end:
    DATES.append(d.strftime('%Y-%m-%d'))
    d += timedelta(days=1)

print(f"Periodo: {DATES[0]} -> {DATES[-1]} ({len(DATES)} giorni)")

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

print(f"Pool totale: {len(pool)} partite ({', '.join(DATES)})\n")

# Arricchisci e calcola
classifiche_cache = enrich_pool_with_stats(pool)
calculate_solidity_coefficient(pool, classifiche_cache)

# Filtra solo quelli calcolati
calcolati = [s for s in pool if s.get("rapporto_home") is not None]
print(f"Calcolati: {len(calcolati)}/{len(pool)}\n")

qhs = sorted([s["coeff_qualita_home"] for s in calcolati])
qas = sorted([s["coeff_qualita_away"] for s in calcolati])
ds = sorted([s["coeff_direzione"] for s in calcolati])
rhs = sorted([s["rapporto_home"] for s in calcolati])
ras = sorted([s["rapporto_away"] for s in calcolati])
coer = sorted([s["coerenza_rapporti"] for s in calcolati])

def stats(vals, label):
    n = len(vals)
    avg = sum(vals) / n
    mn, mx = min(vals), max(vals)
    med = vals[n // 2]
    p10 = vals[int(n * 0.1)]
    p25 = vals[int(n * 0.25)]
    p75 = vals[int(n * 0.75)]
    p90 = vals[int(n * 0.9)]
    print(f"\n{'='*60}")
    print(f"  {label} — {n} partite")
    print(f"{'='*60}")
    print(f"  Min: {mn:.1f}  |  Max: {mx:.1f}  |  Media: {avg:.1f}  |  Mediana: {med:.1f}")
    print(f"  P10: {p10:.1f}  |  P25: {p25:.1f}  |  P75: {p75:.1f}  |  P90: {p90:.1f}")

    # Distribuzione a fasce di 10
    print(f"\n  Distribuzione:")
    for lo in range(0, 200, 10):
        hi = lo + 10
        cnt = sum(1 for v in vals if lo <= v < hi)
        if cnt > 0:
            bar = '#' * min(cnt, 80)
            print(f"  {lo:3d}-{hi:3d}: {cnt:3d} {bar}")

stats(qhs, "QUALITA HOME (Q_H)")
stats(qas, "QUALITA AWAY (Q_A)")
stats(ds, "DIREZIONE (D)")
stats(rhs, "RAPPORTO HOME (D/Q_H)")
stats(ras, "RAPPORTO AWAY (D/Q_A)")
stats(coer, "COERENZA (100=vicini, 0=opposti)")

# Lista top 40 ordinata per rapporto_home
print(f"\n{'='*80}")
print(f"  TOP 40 per RAPPORTO HOME")
print(f"{'='*80}")
for i, s in enumerate(sorted(calcolati, key=lambda x: x["rapporto_home"], reverse=True)[:40]):
    print(f"  {i+1:3d}. RH:{s['rapporto_home']:5.1f} RA:{s['rapporto_away']:5.1f} C:{s['coerenza_rapporti']:5.1f} | QH:{s['coeff_qualita_home']:5.1f} QA:{s['coeff_qualita_away']:5.1f} D:{s['coeff_direzione']:5.1f} | {s['home']:18s} vs {s['away']:18s} | {s['mercato']}: {s['pronostico']} @ {s['quota']}")
