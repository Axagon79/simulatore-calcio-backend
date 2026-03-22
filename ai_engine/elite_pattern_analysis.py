"""
Analisi esplorativa dei pattern vincenti per la sezione Elite.
Interroga daily_predictions_unified e trova le combinazioni con hit rate piu alto.
"""

import os
import sys
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from pymongo import MongoClient

# Carica .env
env_path = os.path.join(os.path.dirname(__file__), '..', 'functions_python', '.env')
load_dotenv(env_path)

MONGO_URI = os.getenv('MONGO_URI')
if not MONGO_URI:
    print("ERRORE: MONGO_URI non trovata nel .env")
    sys.exit(1)

client = MongoClient(MONGO_URI)
db = client['football_simulator_db']
coll = db['daily_predictions_unified']

# ========== QUERY: tutte le partite con almeno un pronostico con esito ==========
print("Caricamento dati da daily_predictions_unified...")
docs = list(coll.find(
    {"pronostici.esito": {"$exists": True}},
    {"date": 1, "league": 1, "home": 1, "away": 1, "odds": 1, "decision": 1,
     "pronostici": 1, "confidence_segno": 1, "confidence_gol": 1,
     "simulation_data": 1, "stats": 1}
))
print(f"Partite trovate con esiti: {len(docs)}")
if not docs:
    print("Nessun dato con esiti. Impossibile analizzare.")
    sys.exit(0)

# ========== ESTRAI TUTTI I PRONOSTICI SINGOLI ==========
records = []
for doc in docs:
    league = doc.get('league', 'Unknown')
    date = doc.get('date', '')
    decision = doc.get('decision', '')
    odds = doc.get('odds', {})
    sim = doc.get('simulation_data', {})
    conf_segno = doc.get('confidence_segno', 0)
    conf_gol = doc.get('confidence_gol', 0)
    sources_list = doc.get('stats', {}).get('sources', [])
    n_sources = len(sources_list)

    for p in doc.get('pronostici', []):
        esito = p.get('esito')
        if esito is None or esito == 'void':
            continue
        hit = esito is True

        tipo = p.get('tipo', '')
        pronostico = p.get('pronostico', '')
        quota = p.get('quota', 0) or 0
        confidence = p.get('confidence', 0) or 0
        stars = p.get('stars', 0) or 0
        source = p.get('source', '')
        routing = p.get('routing_rule', '')
        stake = p.get('stake', 0) or 0
        edge = p.get('edge', 0) or 0
        prob_modello = p.get('prob_modello', 0) or 0
        prob_mercato = p.get('prob_mercato', 0) or 0

        # Range quota
        if quota <= 0:
            quota_range = 'no_quota'
        elif quota < 1.30:
            quota_range = '1.00-1.29'
        elif quota < 1.50:
            quota_range = '1.30-1.49'
        elif quota < 1.80:
            quota_range = '1.50-1.79'
        elif quota < 2.00:
            quota_range = '1.80-1.99'
        elif quota < 2.50:
            quota_range = '2.00-2.49'
        elif quota < 3.00:
            quota_range = '2.50-2.99'
        else:
            quota_range = '3.00+'

        # Range confidence
        if confidence >= 80:
            conf_range = '80-100'
        elif confidence >= 70:
            conf_range = '70-79'
        elif confidence >= 60:
            conf_range = '60-69'
        elif confidence >= 50:
            conf_range = '50-59'
        else:
            conf_range = '<50'

        # Range stelle
        if stars >= 4.5:
            stars_range = '4.5-5'
        elif stars >= 4.0:
            stars_range = '4-4.5'
        elif stars >= 3.5:
            stars_range = '3.5-4'
        elif stars >= 3.0:
            stars_range = '3-3.5'
        else:
            stars_range = '<3'

        # Range edge
        if edge >= 20:
            edge_range = '20+'
        elif edge >= 15:
            edge_range = '15-19'
        elif edge >= 10:
            edge_range = '10-14'
        elif edge >= 5:
            edge_range = '5-9'
        else:
            edge_range = '<5'

        records.append({
            'hit': hit, 'tipo': tipo, 'pronostico': pronostico,
            'quota': quota, 'quota_range': quota_range,
            'confidence': confidence, 'conf_range': conf_range,
            'stars': stars, 'stars_range': stars_range,
            'source': source, 'routing': routing,
            'stake': stake, 'edge': edge, 'edge_range': edge_range,
            'league': league, 'decision': decision,
            'prob_modello': prob_modello, 'prob_mercato': prob_mercato,
            'n_sources': n_sources, 'date': date,
        })

print(f"Pronostici totali con esito: {len(records)}")
tot_hit = sum(1 for r in records if r['hit'])
print(f"Hit rate globale: {tot_hit}/{len(records)} = {tot_hit/len(records)*100:.1f}%\n")

# ========== FUNZIONE HELPER: analisi per dimensione ==========
def analyze_dimension(records, dim_name, key_fn, min_sample=10):
    """Raggruppa per una dimensione e calcola hit rate."""
    groups = defaultdict(lambda: {'hit': 0, 'total': 0, 'profit': 0})
    for r in records:
        k = key_fn(r)
        groups[k]['total'] += 1
        if r['hit']:
            groups[k]['hit'] += 1
            groups[k]['profit'] += (r['quota'] - 1) if r['quota'] > 0 else 0
        else:
            groups[k]['profit'] -= 1

    print(f"{'='*60}")
    print(f" {dim_name}")
    print(f"{'='*60}")
    print(f"{'Valore':<25} {'Hit Rate':>10} {'N':>6} {'Profit(1u)':>10}")
    print(f"{'-'*55}")

    sorted_groups = sorted(groups.items(), key=lambda x: x[1]['hit']/max(x[1]['total'],1), reverse=True)
    for k, v in sorted_groups:
        if v['total'] < min_sample:
            continue
        hr = v['hit'] / v['total'] * 100
        print(f"{str(k):<25} {hr:>8.1f}%  {v['total']:>5}  {v['profit']:>+9.1f}")
    print()
    return groups


# ========== ANALISI PER SINGOLA DIMENSIONE ==========

# 1. Per TIPO di mercato
analyze_dimension(records, "PER TIPO DI MERCATO", lambda r: r['tipo'])

# 2. Per PRONOSTICO specifico
analyze_dimension(records, "PER PRONOSTICO SPECIFICO", lambda r: f"{r['tipo']}:{r['pronostico']}")

# 3. Per RANGE QUOTA
analyze_dimension(records, "PER RANGE QUOTA", lambda r: r['quota_range'])

# 4. Per RANGE CONFIDENCE
analyze_dimension(records, "PER RANGE CONFIDENCE", lambda r: r['conf_range'])

# 5. Per STELLE
analyze_dimension(records, "PER RANGE STELLE", lambda r: r['stars_range'])

# 6. Per SOURCE (algoritmo)
analyze_dimension(records, "PER SOURCE (ALGORITMO)", lambda r: r['source'])

# 7. Per ROUTING RULE
analyze_dimension(records, "PER ROUTING RULE", lambda r: r['routing'])

# 8. Per EDGE RANGE
analyze_dimension(records, "PER EDGE RANGE", lambda r: r['edge_range'])

# 9. Per CAMPIONATO (top 15)
analyze_dimension(records, "PER CAMPIONATO", lambda r: r['league'], min_sample=15)

# 10. Per DECISION (BET vs NO_BET)
analyze_dimension(records, "PER DECISION (BET/NO_BET)", lambda r: r['decision'])

# 11. Per STAKE
analyze_dimension(records, "PER STAKE", lambda r: r['stake'])


# ========== ANALISI COMBINAZIONI MULTI-DIMENSIONALI ==========
print(f"\n{'#'*60}")
print(f" COMBINAZIONI MULTI-DIMENSIONALI (min 8 sample)")
print(f"{'#'*60}\n")

combos = defaultdict(lambda: {'hit': 0, 'total': 0, 'profit': 0})
for r in records:
    # Combo: tipo + quota_range + conf_range
    k = (r['tipo'], r['quota_range'], r['conf_range'])
    combos[k]['total'] += 1
    if r['hit']:
        combos[k]['hit'] += 1
        combos[k]['profit'] += (r['quota'] - 1) if r['quota'] > 0 else 0
    else:
        combos[k]['profit'] -= 1

print(f"{'Tipo+Quota+Confidence':<45} {'Hit Rate':>10} {'N':>6} {'Profit':>10}")
print(f"{'-'*75}")
sorted_combos = sorted(combos.items(), key=lambda x: x[1]['hit']/max(x[1]['total'],1), reverse=True)
for k, v in sorted_combos:
    if v['total'] < 8:
        continue
    hr = v['hit'] / v['total'] * 100
    label = f"{k[0]} | Q:{k[1]} | C:{k[2]}"
    print(f"{label:<45} {hr:>8.1f}%  {v['total']:>5}  {v['profit']:>+9.1f}")

# ========== COMBO: source + tipo + quota_range ==========
print(f"\n{'Src+Tipo+Quota':<45} {'Hit Rate':>10} {'N':>6} {'Profit':>10}")
print(f"{'-'*75}")
combos2 = defaultdict(lambda: {'hit': 0, 'total': 0, 'profit': 0})
for r in records:
    k = (r['source'], r['tipo'], r['quota_range'])
    combos2[k]['total'] += 1
    if r['hit']:
        combos2[k]['hit'] += 1
        combos2[k]['profit'] += (r['quota'] - 1) if r['quota'] > 0 else 0
    else:
        combos2[k]['profit'] -= 1

sorted_combos2 = sorted(combos2.items(), key=lambda x: x[1]['hit']/max(x[1]['total'],1), reverse=True)
for k, v in sorted_combos2:
    if v['total'] < 8:
        continue
    hr = v['hit'] / v['total'] * 100
    label = f"{k[0]} | {k[1]} | Q:{k[2]}"
    print(f"{label:<45} {hr:>8.1f}%  {v['total']:>5}  {v['profit']:>+9.1f}")

# ========== COMBO: routing + tipo ==========
print(f"\n{'Routing+Tipo':<45} {'Hit Rate':>10} {'N':>6} {'Profit':>10}")
print(f"{'-'*75}")
combos3 = defaultdict(lambda: {'hit': 0, 'total': 0, 'profit': 0})
for r in records:
    k = (r['routing'], r['tipo'])
    combos3[k]['total'] += 1
    if r['hit']:
        combos3[k]['hit'] += 1
        combos3[k]['profit'] += (r['quota'] - 1) if r['quota'] > 0 else 0
    else:
        combos3[k]['profit'] -= 1

sorted_combos3 = sorted(combos3.items(), key=lambda x: x[1]['hit']/max(x[1]['total'],1), reverse=True)
for k, v in sorted_combos3:
    if v['total'] < 8:
        continue
    hr = v['hit'] / v['total'] * 100
    label = f"{k[0]} | {k[1]}"
    print(f"{label:<45} {hr:>8.1f}%  {v['total']:>5}  {v['profit']:>+9.1f}")


# ========== TOP PATTERN ELITE (hit rate >= 65% con almeno 10 sample) ==========
print(f"\n{'*'*60}")
print(f" TOP PATTERN CANDIDATI ELITE (HR >= 65%, N >= 10)")
print(f"{'*'*60}\n")

all_combos = {}
# Raccogli tutte le combo multi-dim
for r in records:
    keys = [
        ('tipo+quota', (r['tipo'], r['quota_range'])),
        ('tipo+conf', (r['tipo'], r['conf_range'])),
        ('tipo+stars', (r['tipo'], r['stars_range'])),
        ('tipo+source', (r['tipo'], r['source'])),
        ('tipo+routing', (r['tipo'], r['routing'])),
        ('tipo+edge', (r['tipo'], r['edge_range'])),
        ('src+quota', (r['source'], r['quota_range'])),
        ('tipo+quota+conf', (r['tipo'], r['quota_range'], r['conf_range'])),
        ('tipo+quota+stars', (r['tipo'], r['quota_range'], r['stars_range'])),
        ('src+tipo+quota', (r['source'], r['tipo'], r['quota_range'])),
        ('routing+tipo', (r['routing'], r['tipo'])),
    ]
    for dim, k in keys:
        full_key = (dim, k)
        if full_key not in all_combos:
            all_combos[full_key] = {'hit': 0, 'total': 0, 'profit': 0}
        all_combos[full_key]['total'] += 1
        if r['hit']:
            all_combos[full_key]['hit'] += 1
            all_combos[full_key]['profit'] += (r['quota'] - 1) if r['quota'] > 0 else 0
        else:
            all_combos[full_key]['profit'] -= 1

elite_candidates = []
for (dim, k), v in all_combos.items():
    if v['total'] >= 10:
        hr = v['hit'] / v['total'] * 100
        if hr >= 65:
            elite_candidates.append({
                'dim': dim, 'key': k, 'hr': hr,
                'n': v['total'], 'profit': v['profit']
            })

elite_candidates.sort(key=lambda x: (-x['hr'], -x['n']))

print(f"{'Dimensione':<15} {'Pattern':<40} {'HR':>7} {'N':>5} {'Profit':>8}")
print(f"{'-'*80}")
for c in elite_candidates[:40]:
    key_str = ' | '.join(str(x) for x in c['key']) if isinstance(c['key'], tuple) else str(c['key'])
    print(f"{c['dim']:<15} {key_str:<40} {c['hr']:>5.1f}%  {c['n']:>4}  {c['profit']:>+7.1f}")

print(f"\nTotale pattern elite candidati: {len(elite_candidates)}")
print(f"\n{'='*60}")
print("ANALISI COMPLETATA")
print(f"{'='*60}")

client.close()
