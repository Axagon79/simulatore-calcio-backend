"""Confronto pronostici Produzione vs Sandbox per oggi."""
import os, sys

current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db
from datetime import datetime

today = datetime.now().strftime('%Y-%m-%d')
fields = {'_id': 0, 'home': 1, 'away': 1, 'league': 1, 'pronostici': 1, 'decision': 1,
          'confidence_segno': 1, 'confidence_gol': 1, 'stars_segno': 1, 'stars_gol': 1}

prod = list(db.daily_predictions.find({'date': today}, fields))
sand = list(db.daily_predictions_sandbox.find({'date': today}, fields))

prod_map = {f"{d['home']} vs {d['away']}": d for d in prod}
sand_map = {f"{d['home']} vs {d['away']}": d for d in sand}
all_keys = sorted(set(list(prod_map.keys()) + list(sand_map.keys())))

print(f"Data: {today}")
print(f"Produzione: {len(prod)} pronostici | Sandbox: {len(sand)} pronostici\n")

diffs = 0
same = 0

for key in all_keys:
    p = prod_map.get(key)
    s = sand_map.get(key)

    if not p and s:
        print(f"  [SOLO SANDBOX] {key} (decision={s['decision']})")
        diffs += 1
        continue
    if p and not s:
        print(f"  [SOLO PROD]    {key} (decision={p['decision']})")
        diffs += 1
        continue

    changes = []

    # Decision diversa
    if p['decision'] != s['decision']:
        changes.append(f"decision: {p['decision']} → {s['decision']}")

    # Pronostici diversi
    p_pron = [(x['tipo'], x['pronostico']) for x in p.get('pronostici', [])]
    s_pron = [(x['tipo'], x['pronostico']) for x in s.get('pronostici', [])]
    if p_pron != s_pron:
        p_str = ', '.join(f"{t}:{v}" for t, v in p_pron)
        s_str = ', '.join(f"{t}:{v}" for t, v in s_pron)
        changes.append(f"pronostici: [{p_str}] → [{s_str}]")

    # Confidence diversa
    cs_p = p.get('confidence_segno', 0) or 0
    cs_s = s.get('confidence_segno', 0) or 0
    cg_p = p.get('confidence_gol', 0) or 0
    cg_s = s.get('confidence_gol', 0) or 0
    if abs(cs_p - cs_s) > 0.5:
        changes.append(f"conf_segno: {cs_p:.1f} → {cs_s:.1f}")
    if abs(cg_p - cg_s) > 0.5:
        changes.append(f"conf_gol: {cg_p:.1f} → {cg_s:.1f}")

    # Stelle diverse
    ss_p = p.get('stars_segno', 0) or 0
    ss_s = s.get('stars_segno', 0) or 0
    sg_p = p.get('stars_gol', 0) or 0
    sg_s = s.get('stars_gol', 0) or 0
    if ss_p != ss_s:
        changes.append(f"stelle_segno: {ss_p} → {ss_s}")
    if sg_p != sg_s:
        changes.append(f"stelle_gol: {sg_p} → {sg_s}")

    if changes:
        diffs += 1
        print(f"  [DIFF] {key}")
        for c in changes:
            print(f"         → {c}")
    else:
        same += 1

print(f"\n{'='*50}")
print(f"Identici: {same} | Differenze: {diffs}")
