"""
Analisi Incrociata — Predizioni Engine × Risultato Esatto
JOIN tra daily_predictions (pronostici + confidence + dettagli) e h2h_by_round (real_score).
Struttura daily_predictions: 1 doc per pronostico emesso, ma OGNI doc contiene
confidence_segno, confidence_gol, expected_total_goals, segno_dettaglio, gol_dettaglio.
"""
import sys, os
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db
from collections import defaultdict
import statistics

predictions_col = db['daily_predictions']
h2h_col = db['h2h_by_round']

# ==================== 1. RISULTATI REALI da h2h_by_round ====================

print("Raccogliendo risultati reali da h2h_by_round...")

pipeline_h2h = [
    {"$unwind": "$matches"},
    {"$match": {
        "matches.real_score": {"$exists": True, "$nin": ["-:-", "", None]},
    }},
    {"$project": {
        "home": "$matches.home",
        "away": "$matches.away",
        "real_score": "$matches.real_score",
    }}
]

real_scores = {}
for doc in h2h_col.aggregate(pipeline_h2h):
    key = (doc.get('home', ''), doc.get('away', ''))
    real_scores[key] = doc['real_score']

print(f"Risultati reali trovati: {len(real_scores)}")

# ==================== 2. PREDIZIONI da daily_predictions ====================

print("Raccogliendo predizioni da daily_predictions...")

all_preds = list(predictions_col.find({}))
print(f"Documenti totali: {len(all_preds)}")

# Raggruppa per partita (home, away, date) → merge tutti i dati
match_data = defaultdict(dict)
for p in all_preds:
    key = (p.get('home', ''), p.get('away', ''), p.get('date', ''))
    d = match_data[key]
    d['home'] = p.get('home', '')
    d['away'] = p.get('away', '')
    d['date'] = p.get('date', '')
    d['league'] = p.get('league', '')

    # Confidence sono sempre presenti in ogni doc
    if 'confidence_segno' not in d or p.get('confidence_segno', 0) > 0:
        d['confidence_segno'] = p.get('confidence_segno', 0)
    if 'confidence_gol' not in d or p.get('confidence_gol', 0) > 0:
        d['confidence_gol'] = p.get('confidence_gol', 0)
    if 'expected_total_goals' not in d:
        d['expected_total_goals'] = p.get('expected_total_goals')

    # Dettagli
    if p.get('segno_dettaglio') and 'segno_dettaglio' not in d:
        d['segno_dettaglio'] = p['segno_dettaglio']
    if p.get('gol_dettaglio') and 'gol_dettaglio' not in d:
        d['gol_dettaglio'] = p['gol_dettaglio']
    if p.get('gol_directions') and 'gol_directions' not in d:
        d['gol_directions'] = p['gol_directions']

    # Pronostici emessi
    for pred in p.get('pronostici', []):
        tipo = pred.get('tipo', '')
        if tipo == 'SEGNO':
            d['segno_pronostico'] = pred.get('pronostico', '')
            d['segno_conf_emesso'] = pred.get('confidence', 0)
        elif tipo == 'GOL':
            pronostico = pred.get('pronostico', '')
            if 'Over' in pronostico or 'Under' in pronostico:
                d['ou_pronostico'] = pronostico
                d['ou_conf_emesso'] = pred.get('confidence', 0)
            elif pronostico in ('Goal', 'No Goal'):
                d['ggng_pronostico'] = pronostico
                d['ggng_conf_emesso'] = pred.get('confidence', 0)
        elif tipo == 'X_FACTOR':
            d['x_factor'] = True
            d['x_factor_conf'] = pred.get('confidence', 0)

print(f"Partite uniche: {len(match_data)}")

# ==================== 3. JOIN ====================

print("Incrociando...")

matches = []
for key, data in match_data.items():
    real = real_scores.get((data['home'], data['away']))
    if real is None:
        continue

    if ':' not in real:
        continue
    parts = real.split(':')
    try:
        h, a = int(parts[0].strip()), int(parts[1].strip())
    except (ValueError, IndexError):
        continue

    data['_h'] = h
    data['_a'] = a
    data['_score'] = f"{h}:{a}"
    data['_total'] = h + a
    matches.append(data)

print(f"Partite con predizione + risultato: {len(matches)}")

if not matches:
    print("Nessun dato!")
    sys.exit(0)

# ==================== DISTRIBUZIONE ====================

score_count = defaultdict(int)
for m in matches:
    score_count[m['_score']] += 1

sorted_scores = sorted(score_count.keys(), key=lambda s: -score_count[s])

print(f"\n{'='*70}")
print(f"DISTRIBUZIONE RISULTATI — {len(matches)} partite")
print(f"{'='*70}")
for s in sorted_scores[:15]:
    n = score_count[s]
    pct = 100 * n / len(matches)
    print(f"  {s:>5}: {n:>4} ({pct:>5.1f}%)")

# ==================== CONFIDENCE SEGNO PER RISULTATO ====================

print(f"\n{'='*70}")
print("CONFIDENCE SEGNO MEDIA per risultato esatto")
print(f"Engine assegnava quale confidence al segno per queste partite?")
print(f"{'='*70}")

print(f"\n{'Score':>6} {'n':>4} | {'conf_segno':>12} | {'Segno emesso':>14} | {'% con segno':>12}")
print("-" * 60)

for s in sorted_scores[:15]:
    sm = [m for m in matches if m['_score'] == s]
    n = len(sm)

    confs = [m['confidence_segno'] for m in sm if m.get('confidence_segno')]
    avg_conf = statistics.mean(confs) if confs else 0

    with_segno = [m for m in sm if 'segno_pronostico' in m]
    pct_segno = 100 * len(with_segno) / n if n else 0

    # Segno più frequente emesso
    segno_types = defaultdict(int)
    for m in with_segno:
        segno_types[m['segno_pronostico']] += 1
    top_segno = max(segno_types, key=segno_types.get) if segno_types else "N/A"

    print(f"  {s:>5} {n:>4} | {avg_conf:>10.1f}% | {top_segno:>14} | {pct_segno:>10.1f}%")

# ==================== CONFIDENCE GOL PER RISULTATO ====================

print(f"\n{'='*70}")
print("CONFIDENCE GOL MEDIA per risultato esatto")
print(f"{'='*70}")

print(f"\n{'Score':>6} {'n':>4} | {'conf_gol':>10} | {'O/U emesso':>12} | {'GG/NG':>8} | {'exp_goals':>10}")
print("-" * 70)

for s in sorted_scores[:15]:
    sm = [m for m in matches if m['_score'] == s]
    n = len(sm)

    gol_confs = [m['confidence_gol'] for m in sm if m.get('confidence_gol')]
    avg_gol = statistics.mean(gol_confs) if gol_confs else 0

    # O/U emesso
    ou_types = defaultdict(int)
    for m in sm:
        if 'ou_pronostico' in m:
            ou_types[m['ou_pronostico']] += 1
    top_ou = max(ou_types, key=ou_types.get) if ou_types else "N/A"

    # GG/NG emesso
    gg_types = defaultdict(int)
    for m in sm:
        if 'ggng_pronostico' in m:
            gg_types[m['ggng_pronostico']] += 1
    top_gg = max(gg_types, key=gg_types.get) if gg_types else "N/A"

    # Expected total goals
    exp_goals = [m['expected_total_goals'] for m in sm if m.get('expected_total_goals')]
    avg_exp = statistics.mean(exp_goals) if exp_goals else 0

    h, a = s.split(':')
    actual_total = int(h) + int(a)

    print(f"  {s:>5} {n:>4} | {avg_gol:>8.1f}% | {top_ou:>12} | {top_gg:>8} | {avg_exp:>8.2f} (reale:{actual_total})")

# ==================== EXPECTED_TOTAL_GOALS × RISULTATO ====================

print(f"\n{'='*70}")
print("EXPECTED TOTAL GOALS (engine) × RISULTATO ESATTO")
print(f"Quanto prevede l'engine in termini di gol totali?")
print(f"{'='*70}")

for s in sorted_scores[:12]:
    sm = [m for m in matches if m['_score'] == s]
    exp = [m['expected_total_goals'] for m in sm if m.get('expected_total_goals')]
    if len(exp) < 3:
        continue
    h, a = s.split(':')
    actual = int(h) + int(a)
    avg = statistics.mean(exp)
    med = statistics.median(exp)
    mn, mx = min(exp), max(exp)
    print(f"  {s} (gol reali={actual}): exp_media={avg:.2f}, mediana={med:.2f}, range=[{mn:.1f}-{mx:.1f}], n={len(exp)}")

# ==================== SEGNO EMESSO → RISULTATO ====================

print(f"\n{'='*70}")
print("SEGNO EMESSO → Top risultati esatti")
print(f"{'='*70}")

for segno in ['1', '2']:
    segno_matches = [m for m in matches if m.get('segno_pronostico') == segno]
    if not segno_matches:
        continue

    print(f"\n  --- Segno {segno} (n={len(segno_matches)}) ---")

    # Per fascia confidence
    conf_buckets = [(55, 62), (62, 68), (68, 75), (75, 100)]
    for lo, hi in conf_buckets:
        bucket = [m for m in segno_matches if lo <= m.get('segno_conf_emesso', 0) < hi]
        if len(bucket) < 3:
            continue
        score_dist = defaultdict(int)
        for m in bucket:
            score_dist[m['_score']] += 1
        top = sorted(score_dist.items(), key=lambda x: -x[1])[:5]
        total = len(bucket)
        parts = [f"{sc}={100*n/total:.0f}%" for sc, n in top]
        print(f"    conf {lo}-{hi} (n={total}): {', '.join(parts)}")

# ==================== O/U EMESSO → RISULTATO ====================

print(f"\n{'='*70}")
print("OVER/UNDER EMESSO → Top risultati esatti")
print(f"{'='*70}")

for ou in ['Over 2.5', 'Under 2.5', 'Over 3.5', 'Under 3.5']:
    ou_matches = [m for m in matches if m.get('ou_pronostico') == ou]
    if len(ou_matches) < 3:
        continue

    score_dist = defaultdict(int)
    for m in ou_matches:
        score_dist[m['_score']] += 1
    top = sorted(score_dist.items(), key=lambda x: -x[1])[:6]
    total = len(ou_matches)

    print(f"\n  {ou} (n={total}):")
    for sc, n in top:
        pct = 100 * n / total
        print(f"    {sc}: {n} ({pct:.1f}%)")

# ==================== GG/NG EMESSO → RISULTATO ====================

print(f"\n{'='*70}")
print("GG/NG EMESSO → Top risultati esatti")
print(f"{'='*70}")

for gg in ['Goal', 'No Goal']:
    gg_matches = [m for m in matches if m.get('ggng_pronostico') == gg]
    if len(gg_matches) < 3:
        continue

    score_dist = defaultdict(int)
    for m in gg_matches:
        score_dist[m['_score']] += 1
    top = sorted(score_dist.items(), key=lambda x: -x[1])[:6]
    total = len(gg_matches)

    print(f"\n  {gg} (n={total}):")
    for sc, n in top:
        pct = 100 * n / total
        print(f"    {sc}: {n} ({pct:.1f}%)")

# ==================== COMBINAZIONE COMPLETA → RISULTATO ====================

print(f"\n{'='*70}")
print("COMBINAZIONE SEGNO + O/U + GG/NG → Top risultati esatti")
print(f"{'='*70}")

combo_map = defaultdict(lambda: defaultdict(int))
combo_total = defaultdict(int)

for m in matches:
    segno = m.get('segno_pronostico', '?')
    ou = m.get('ou_pronostico', '?')
    if ou != '?':
        ou = ou.replace(' 2.5', '').replace(' 3.5', '')
    gg = m.get('ggng_pronostico', '?')

    # Almeno uno deve essere non-?
    parts = []
    if segno != '?':
        parts.append(f"S={segno}")
    if ou != '?':
        parts.append(ou)
    if gg != '?':
        parts.append(gg)

    if not parts:
        continue

    combo = " + ".join(parts)
    combo_map[combo][m['_score']] += 1
    combo_total[combo] += 1

for combo in sorted(combo_total.keys(), key=lambda c: -combo_total[c]):
    total = combo_total[combo]
    if total < 3:
        continue
    top = sorted(combo_map[combo].items(), key=lambda x: -x[1])[:5]
    parts = [f"{sc}={100*n/total:.0f}%" for sc, n in top]
    print(f"  {combo} (n={total}): {', '.join(parts)}")

# ==================== GOL DETTAGLIO per risultato ====================

print(f"\n{'='*70}")
print("GOL DETTAGLIO MEDIO per risultato esatto")
print(f"Scores dei sub-calcolatori GOL (media_gol, att_vs_def, xg, h2h_gol)")
print(f"{'='*70}")

gol_signals = ['media_gol', 'att_vs_def', 'xg', 'h2h_gol', 'media_lega', 'dna_off_def']

print(f"\n{'Score':>6} {'n':>4}", end="")
for sig in gol_signals:
    print(f" | {sig[:10]:>10}", end="")
print()
print("-" * (12 + 13 * len(gol_signals)))

for s in sorted_scores[:12]:
    sm = [m for m in matches if m['_score'] == s]
    n = len(sm)

    print(f"  {s:>5} {n:>4}", end="")
    for sig in gol_signals:
        vals = [m.get('gol_dettaglio', {}).get(sig, None) for m in sm]
        vals = [v for v in vals if v is not None]
        if vals:
            avg = statistics.mean(vals)
            print(f" | {avg:>10.1f}", end="")
        else:
            print(f" | {'N/A':>10}", end="")
    print()

# ==================== SEGNO DETTAGLIO per risultato ====================

print(f"\n{'='*70}")
print("SEGNO DETTAGLIO MEDIO per risultato esatto")
print(f"{'='*70}")

segno_signals = ['bvs', 'quote', 'lucifero', 'affidabilita', 'dna', 'motivazioni', 'h2h', 'campo']

print(f"\n{'Score':>6} {'n':>4}", end="")
for sig in segno_signals:
    print(f" | {sig[:10]:>10}", end="")
print()
print("-" * (12 + 13 * len(segno_signals)))

for s in sorted_scores[:12]:
    sm = [m for m in matches if m['_score'] == s]
    n = len(sm)

    print(f"  {s:>5} {n:>4}", end="")
    for sig in segno_signals:
        vals = [m.get('segno_dettaglio', {}).get(sig, None) for m in sm]
        vals = [v for v in vals if v is not None]
        if vals:
            avg = statistics.mean(vals)
            print(f" | {avg:>10.1f}", end="")
        else:
            print(f" | {'N/A':>10}", end="")
    print()

# ==================== RIEPILOGO ====================

print(f"\n{'='*70}")
print("RIEPILOGO")
print(f"{'='*70}")
print(f"Partite analizzate: {len(matches)}")
print(f"  Con segno emesso: {sum(1 for m in matches if 'segno_pronostico' in m)}")
print(f"  Con O/U emesso: {sum(1 for m in matches if 'ou_pronostico' in m)}")
print(f"  Con GG/NG emesso: {sum(1 for m in matches if 'ggng_pronostico' in m)}")
print(f"  Con X Factor: {sum(1 for m in matches if m.get('x_factor'))}")
print(f"  Con expected_total_goals: {sum(1 for m in matches if m.get('expected_total_goals'))}")
print(f"  Con confidence_segno: {sum(1 for m in matches if m.get('confidence_segno'))}")
print(f"  Con confidence_gol: {sum(1 for m in matches if m.get('confidence_gol'))}")
