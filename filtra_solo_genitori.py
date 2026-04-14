"""Filtra solo i 14 genitori esatti, tiene tutto il resto."""

genitori = [
    frozenset({'conf50-59', 'src_C_screm'}),
    frozenset({'conf50-59', 'q1.50-1.79'}),
    frozenset({'pron_Goal', 'q1.30-1.49'}),
    frozenset({'conf60-69', 'q1.30-1.49'}),
    frozenset({'route_union'}),
    frozenset({'pron_1', 'st3.6-3.9'}),
    frozenset({'conf70-79', 'q1.50-1.79'}),
    frozenset({'src_C_screm', 'route_scrematura'}),
    frozenset({'src_C', 'st3.6-3.9'}),
    frozenset({'edge20-50', 'q1.50-1.79'}),
    frozenset({'conf60-69', 'edge50+'}),
    frozenset({'conf60-69', 'src_C'}),
    frozenset({'q3.00-3.99', 'route_single'}),
    frozenset({'edge50+', 'tipo_SEGNO'}),
]

# Leggo dalla classifica completa del mixer
import sys
sys.path.insert(0, 'functions_python/ai_engine')
from config import db
from itertools import combinations

coll = db['daily_predictions_unified']
docs = list(coll.find(
    {'date': {'$gte': '2026-03-15'}, 'real_score': {'$exists': True, '$ne': None}},
    {'pronostici': 1, 'quote_snai': 1}
))

all_entries = []
for doc in docs:
    if not doc.get('pronostici'):
        continue
    quote_snai = doc.get('quote_snai', {})
    for p in doc['pronostici']:
        if p.get('pronostico') == 'NO BET' or p.get('hit') is None:
            continue
        quota = p.get('quota', 0) or 0
        if not quota:
            pron = p.get('pronostico', '')
            quota = quote_snai.get(pron, 0) if quote_snai else 0
        all_entries.append({
            'tipo': p.get('tipo', '?'),
            'pronostico': p.get('pronostico', '?'),
            'quota': quota,
            'confidence': p.get('confidence', 0) or 0,
            'stars': p.get('stars', 0) or 0,
            'stake': p.get('stake') or 1,
            'source': p.get('source', '?'),
            'routing_rule': p.get('routing_rule', '?'),
            'elite': p.get('elite', False),
            'edge': p.get('edge', 0) or 0,
            'hit': p['hit'],
        })

CONDITIONS = {
    'conf50-59': lambda e: 50 <= e['confidence'] <= 59,
    'conf60-69': lambda e: 60 <= e['confidence'] <= 69,
    'conf70-79': lambda e: 70 <= e['confidence'] <= 79,
    'q1.30-1.49': lambda e: 1.30 <= e['quota'] <= 1.49,
    'q1.50-1.79': lambda e: 1.50 <= e['quota'] <= 1.79,
    'q3.00-3.99': lambda e: 3.00 <= e['quota'] <= 3.99,
    'src_C_screm': lambda e: e['source'] == 'C_screm',
    'src_C': lambda e: e['source'] == 'C',
    'route_scrematura': lambda e: e['routing_rule'] == 'scrematura_segno',
    'route_union': lambda e: e['routing_rule'] == 'union',
    'route_single': lambda e: e['routing_rule'] == 'single',
    'tipo_GOL': lambda e: e['tipo'] == 'GOL',
    'tipo_SEGNO': lambda e: e['tipo'] == 'SEGNO',
    'pron_Goal': lambda e: e['pronostico'] == 'Goal',
    'pron_1': lambda e: e['pronostico'] == '1',
    'st3.6-3.9': lambda e: 3.6 <= e['stars'] <= 3.9,
    'edge20-50': lambda e: 20 < e['edge'] <= 50,
    'edge50+': lambda e: e['edge'] > 50,
}

cond_names = list(CONDITIONS.keys())
cond_funcs = list(CONDITIONS.values())

entry_masks = []
for e in all_entries:
    entry_masks.append(tuple(f(e) for f in cond_funcs))

MIN_N = 8
all_results = []

for n_conds in [2, 3, 4]:
    for combo_idx in combinations(range(len(cond_names)), n_conds):
        names = frozenset(cond_names[i] for i in combo_idx)

        # Salta se è un genitore esatto
        if names in genitori:
            continue

        v, p, pl = 0, 0, 0.0
        for idx, mask in enumerate(entry_masks):
            if all(mask[i] for i in combo_idx):
                e = all_entries[idx]
                if e['hit']:
                    v += 1
                    pl += (e['quota'] - 1) * e['stake']
                else:
                    p += 1
                    pl -= e['stake']

        tot = v + p
        if tot < MIN_N:
            continue
        hr = v / tot * 100
        if hr < 65:
            continue

        name = ' + '.join(cond_names[i] for i in combo_idx)
        all_results.append((name, v, p, tot, hr, pl, n_conds))

all_results.sort(key=lambda x: x[5], reverse=True)

print(f'Pattern ibridi (esclusi 14 genitori): {len(all_results)}')
print()
print(f'{"#":>3s} | {"C":>1s} | {"Pattern":60s} | {"V":>3s}/{"P":>3s} | {"HR":>6s} | {"N":>3s} | {"P/L":>9s}')
print(f'{"-"*95}')
for i, (name, v, p, n, hr, pl, nc) in enumerate(all_results, 1):
    print(f'{i:3d} | {nc} | {name:60s} | {v:3d}/{p:3d} | {hr:5.1f}% | {n:3d} | {pl:+8.2f}u')
