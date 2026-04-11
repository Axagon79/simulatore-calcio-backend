"""
Analisi esplorativa dei pattern vincenti per la sezione Elite.
Interroga daily_predictions_unified e trova le combinazioni con hit rate piu alto.

Uso:
  python elite_pattern_analysis.py                  # storico completo
  python elite_pattern_analysis.py --from 2026-04-01  # solo dal 1 aprile
"""

import os
import sys
import json
import argparse
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from pymongo import MongoClient

# ========== ARGOMENTI CLI ==========
parser = argparse.ArgumentParser(description='Analisi pattern Elite')
parser.add_argument('--from', dest='from_date', type=str, default=None,
                    help='Data inizio analisi (YYYY-MM-DD). Se omesso: storico completo.')
args = parser.parse_args()

from_date = args.from_date
if from_date:
    try:
        datetime.strptime(from_date, '%Y-%m-%d')
    except ValueError:
        print(f"ERRORE: formato data non valido '{from_date}', usare YYYY-MM-DD")
        sys.exit(1)

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
query_filter = {"pronostici.esito": {"$exists": True}}
if from_date:
    query_filter["date"] = {"$gte": from_date}
    print(f"Caricamento dati dal {from_date}...")
else:
    print("Caricamento dati da daily_predictions_unified (storico completo)...")

docs = list(coll.find(
    query_filter,
    {"date": 1, "league": 1, "home": 1, "away": 1, "odds": 1, "decision": 1,
     "pronostici": 1, "confidence_segno": 1, "confidence_gol": 1,
     "simulation_data": 1, "stats": 1}
))
print(f"Caricamento dati... OK ({len(docs)} partite)")
if not docs:
    print("Nessun dato con esiti. Impossibile analizzare.")
    sys.exit(0)

# ========== ESTRAI TUTTI I PRONOSTICI SINGOLI ==========
print("Estrazione pronostici...", end=" ", flush=True)
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

print(f"OK ({len(records)} pronostici)")
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
dim_list = [
    ("PER TIPO DI MERCATO", lambda r: r['tipo'], 10),
    ("PER PRONOSTICO SPECIFICO", lambda r: f"{r['tipo']}:{r['pronostico']}", 10),
    ("PER RANGE QUOTA", lambda r: r['quota_range'], 10),
    ("PER RANGE CONFIDENCE", lambda r: r['conf_range'], 10),
    ("PER RANGE STELLE", lambda r: r['stars_range'], 10),
    ("PER SOURCE (ALGORITMO)", lambda r: r['source'], 10),
    ("PER ROUTING RULE", lambda r: r['routing'], 10),
    ("PER EDGE RANGE", lambda r: r['edge_range'], 10),
    ("PER CAMPIONATO", lambda r: r['league'], 15),
    ("PER DECISION (BET/NO_BET)", lambda r: r['decision'], 10),
    ("PER STAKE", lambda r: r['stake'], 10),
]

for i, (title, key_fn, min_s) in enumerate(dim_list, 1):
    print(f"Analisi dimensione {i}/{len(dim_list)}: {title}...", flush=True)
    analyze_dimension(records, title, key_fn, min_s)


# ========== ANALISI COMBINAZIONI MULTI-DIMENSIONALI ==========
print("Analisi combinazioni multi-dimensionali...", flush=True)
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
print("Ricerca pattern Elite candidati...", flush=True)
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

# ========== PATTERN GIA IN PRODUZIONE (per marcatura *) ==========
def is_active_pattern(dim, key):
    """Verifica se un pattern trovato corrisponde a uno dei 24 pattern attivi (16 Elite + 8 Diamante)."""
    # Normalizza chiave in set per matching indipendente dall'ordine
    if isinstance(key, tuple):
        parts = set(str(x) for x in key)
    else:
        parts = {str(key)}

    # --- 16 PATTERN ELITE (tag_elite.py) ---
    # P1: SEGNO + quota 1.50-1.79 + stelle 3-3.5
    if parts == {'SEGNO', '1.50-1.79', '3-3.5'}:
        return 'E1'
    # P2: SEGNO + quota 1.50-1.79 + conf 50-59
    if parts == {'SEGNO', '1.50-1.79', '50-59'}:
        return 'E2'
    # P3: DOPPIA_CHANCE + C_screm + quota 2.00-2.49
    if parts == {'DOPPIA_CHANCE', 'C_screm', '2.00-2.49'} or parts == {'C_screm', 'DOPPIA_CHANCE', '2.00-2.49'}:
        return 'E3'
    # P4: GOL + quota 1.30-1.49 + conf 70-79
    if parts == {'GOL', '1.30-1.49', '70-79'}:
        return 'E4'
    # P5: DOPPIA_CHANCE + quota 2.00-2.49
    if parts == {'DOPPIA_CHANCE', '2.00-2.49'}:
        return 'E5'
    # P6: SEGNO + conf 80-100
    if parts == {'SEGNO', '80-100'}:
        return 'E6'
    # P7: DOPPIA_CHANCE + quota 1.30-1.49 + conf 60-69
    if parts == {'DOPPIA_CHANCE', '1.30-1.49', '60-69'}:
        return 'E7'
    # P8: GOL + A+S + quota 1.30-1.49
    if parts == {'GOL', 'A+S', '1.30-1.49'} or parts == {'A+S', 'GOL', '1.30-1.49'}:
        return 'E8'
    # P9: DOPPIA_CHANCE + quota 1.30-1.49 (parziale — copre anche P7/P16 con conf)
    # P10: MG 2-4 — non rilevabile come combinazione dimensionale
    # P11: GOL + quota 1.30-1.49 + conf 70-79 (uguale a P4 con range piu stretto, ma stesso range)
    # P14: GOL + C_screm + quota 1.50-1.79
    if parts == {'GOL', 'C_screm', '1.50-1.79'} or parts == {'C_screm', 'GOL', '1.50-1.79'}:
        return 'E14'
    # P15: SEGNO + quota 1.80-1.99 + conf 80-100
    if parts == {'SEGNO', '1.80-1.99', '80-100'}:
        return 'E15'
    # P16: DOPPIA_CHANCE + quota 1.30-1.49 + conf 70-79
    if parts == {'DOPPIA_CHANCE', '1.30-1.49', '70-79'}:
        return 'E16'

    # --- Matching parziali (sottoinsieme di un pattern attivo) ---
    # GOL + quota 1.30-1.49 (copre P4, P8, P11, P13)
    if parts == {'GOL', '1.30-1.49'}:
        return 'E4+'
    # DOPPIA_CHANCE + quota 1.30-1.49 (copre P7, P9, P12, P16)
    if parts == {'DOPPIA_CHANCE', '1.30-1.49'}:
        return 'E7+'
    # SEGNO + quota 1.50-1.79 (copre P1, P2)
    if parts == {'SEGNO', '1.50-1.79'}:
        return 'E1+'
    # C_screm + quota 2.00-2.49 (copre P3)
    if parts == {'C_screm', '2.00-2.49'}:
        return 'E3+'
    # GOL + A+S (copre P8, P13)
    if parts == {'GOL', 'A+S'}:
        return 'E8+'
    # DOPPIA_CHANCE + C_combo96 + quota 1.30-1.49
    if parts == {'DOPPIA_CHANCE', 'C_combo96', '1.30-1.49'} or parts == {'C_combo96', 'DOPPIA_CHANCE', '1.30-1.49'}:
        return 'E7~'
    # C + GOL + quota 1.30-1.49
    if parts == {'C', 'GOL', '1.30-1.49'}:
        return 'E4~'
    # SEGNO + quota 1.80-1.99 (copre P15)
    if parts == {'SEGNO', '1.80-1.99'}:
        return 'E15+'

    # --- Routing rules dei Diamanti ---
    for p in parts:
        if 'diamond' in str(p).lower():
            return 'D'
    # Routing rules Elite
    if 'o25_s6_to_goal' in parts:
        return 'E~'
    if 'combo_96_dc_flip' in parts:
        return 'E~'

    return None

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

# Aggiungi info pattern attivo
for c in elite_candidates:
    c['active'] = is_active_pattern(c['dim'], c['key'])

print(f"{'Dimensione':<15} {'Pattern':<40} {'HR':>7} {'N':>5} {'Profit':>8} {'':>6}")
print(f"{'-'*85}")
for c in elite_candidates[:40]:
    key_str = ' | '.join(str(x) for x in c['key']) if isinstance(c['key'], tuple) else str(c['key'])
    tag = f"* {c['active']}" if c['active'] else ""
    print(f"{c['dim']:<15} {key_str:<40} {c['hr']:>5.1f}%  {c['n']:>4}  {c['profit']:>+7.1f}  {tag}")

print(f"\nTotale pattern elite candidati: {len(elite_candidates)}")
print(f"\n{'='*60}")
print("ANALISI COMPLETATA")
print(f"{'='*60}")

client.close()

# ========== SALVATAGGIO REPORT ==========
log_dir = os.path.join(os.path.dirname(__file__), '..', '_analisi_pattern')
os.makedirs(log_dir, exist_ok=True)

today_str = datetime.now().strftime('%Y-%m-%d')
suffix = f"_from_{from_date}" if from_date else ""
base_name = f"elite_pattern_report_{today_str}{suffix}"

# --- Cattura output TXT rieseguendo le stampe ---
lines = []
lines.append(f"{'='*60}")
lines.append(f" REPORT ANALISI PATTERN ELITE")
lines.append(f" Data report: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
lines.append(f" Periodo: {'dal ' + from_date if from_date else 'storico completo'}")
lines.append(f" Pronostici analizzati: {len(records)}")
lines.append(f" Hit rate globale: {tot_hit}/{len(records)} = {tot_hit/len(records)*100:.1f}%")
lines.append(f"{'='*60}\n")

# Funzione helper per formattare una sezione
def fmt_dimension(title, groups_dict, min_sample=10):
    section = []
    section.append(f"{'='*60}")
    section.append(f" {title}")
    section.append(f"{'='*60}")
    section.append(f"{'Valore':<25} {'Hit Rate':>10} {'N':>6} {'Profit(1u)':>10}")
    section.append(f"{'-'*55}")
    sorted_g = sorted(groups_dict.items(), key=lambda x: x[1]['hit']/max(x[1]['total'],1), reverse=True)
    for k, v in sorted_g:
        if v['total'] < min_sample:
            continue
        hr = v['hit'] / v['total'] * 100
        section.append(f"{str(k):<25} {hr:>8.1f}%  {v['total']:>5}  {v['profit']:>+9.1f}")
    section.append("")
    return section

# Ricalcola i gruppi per il report (riuso analyze_dimension senza print)
def build_groups(records_list, key_fn):
    grp = defaultdict(lambda: {'hit': 0, 'total': 0, 'profit': 0})
    for r in records_list:
        k = key_fn(r)
        grp[k]['total'] += 1
        if r['hit']:
            grp[k]['hit'] += 1
            grp[k]['profit'] += (r['quota'] - 1) if r['quota'] > 0 else 0
        else:
            grp[k]['profit'] -= 1
    return grp

dims = [
    ("PER TIPO DI MERCATO", lambda r: r['tipo'], 10),
    ("PER PRONOSTICO SPECIFICO", lambda r: f"{r['tipo']}:{r['pronostico']}", 10),
    ("PER RANGE QUOTA", lambda r: r['quota_range'], 10),
    ("PER RANGE CONFIDENCE", lambda r: r['conf_range'], 10),
    ("PER RANGE STELLE", lambda r: r['stars_range'], 10),
    ("PER SOURCE (ALGORITMO)", lambda r: r['source'], 10),
    ("PER ROUTING RULE", lambda r: r['routing'], 10),
    ("PER EDGE RANGE", lambda r: r['edge_range'], 10),
    ("PER CAMPIONATO", lambda r: r['league'], 15),
    ("PER DECISION (BET/NO_BET)", lambda r: r['decision'], 10),
    ("PER STAKE", lambda r: r['stake'], 10),
]

for title, key_fn, min_s in dims:
    grp = build_groups(records, key_fn)
    lines.extend(fmt_dimension(title, grp, min_s))

# Top pattern Elite
lines.append(f"\n{'*'*60}")
lines.append(f" TOP PATTERN CANDIDATI ELITE (HR >= 65%, N >= 10)")
lines.append(f" * = pattern gia in produzione")
lines.append(f"{'*'*60}\n")
lines.append(f"{'Dimensione':<15} {'Pattern':<40} {'HR':>7} {'N':>5} {'Profit':>8} {'':>6}")
lines.append(f"{'-'*85}")
for c in elite_candidates[:40]:
    key_str = ' | '.join(str(x) for x in c['key']) if isinstance(c['key'], tuple) else str(c['key'])
    tag = f"* {c['active']}" if c.get('active') else ""
    lines.append(f"{c['dim']:<15} {key_str:<40} {c['hr']:>5.1f}%  {c['n']:>4}  {c['profit']:>+7.1f}  {tag}")

active_count = sum(1 for c in elite_candidates if c.get('active'))
new_count = len(elite_candidates) - active_count
lines.append(f"\nTotale pattern: {len(elite_candidates)} ({active_count} gia attivi *, {new_count} nuovi)")

print("Salvataggio report...", end=" ", flush=True)
# Salva TXT
txt_path = os.path.join(log_dir, f"{base_name}.txt")
with open(txt_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f"\nReport TXT salvato: {txt_path}")

# Salva JSON
json_data = {
    'report_date': today_str,
    'from_date': from_date,
    'total_predictions': len(records),
    'total_hits': tot_hit,
    'hit_rate_global': round(tot_hit / len(records) * 100, 1) if records else 0,
    'elite_candidates': [
        {
            'dimension': c['dim'],
            'pattern': ' | '.join(str(x) for x in c['key']) if isinstance(c['key'], tuple) else str(c['key']),
            'hit_rate': round(c['hr'], 1),
            'sample_size': c['n'],
            'profit': round(c['profit'], 2),
            'active': c.get('active')
        }
        for c in elite_candidates
    ]
}

json_path = os.path.join(log_dir, f"{base_name}.json")
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(json_data, f, indent=2, ensure_ascii=False)
print(f"OK")
print(f"Report TXT: {txt_path}")
print(f"Report JSON: {json_path}")
