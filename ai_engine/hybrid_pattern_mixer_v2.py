"""
Hybrid Pattern Mixer v2 — Prende i pattern reali dalle top 30 di elite e bizarre,
estrae le condizioni, le mescola tra loro per creare nuovi pattern ibridi.

A differenza del v1 (brute force su filtri generici), questo parte dai pattern
GIA TROVATI come vincenti e li incrocia.

Uso:
  python hybrid_pattern_mixer_v2.py                     # storico completo
  python hybrid_pattern_mixer_v2.py --from 2026-04-01   # solo dal 1 aprile
  python hybrid_pattern_mixer_v2.py --tipo GOL          # solo pattern GOL
  python hybrid_pattern_mixer_v2.py --tipo SEGNO --from 2026-03-21
  python hybrid_pattern_mixer_v2.py --tipo GOL --quota-min 1.50   # solo GOL con quote >= 1.50
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime
from collections import defaultdict
from itertools import combinations
from math import comb as n_comb
from dotenv import load_dotenv
from pymongo import MongoClient

# ========== ARGOMENTI CLI ==========
parser = argparse.ArgumentParser(description='Hybrid Pattern Mixer v2')
parser.add_argument('--from', dest='from_date', type=str, default=None,
                    help='Data inizio analisi (YYYY-MM-DD). Se omesso: storico completo.')
parser.add_argument('--tipo', dest='tipo_filter', type=str, default=None,
                    help='Filtra solo pattern di un tipo specifico (GOL, SEGNO, DOPPIA_CHANCE).')
parser.add_argument('--quota-min', dest='quota_min', type=float, default=None,
                    help='Tiene solo pattern sorgente con quota >= questo valore (es. 1.50).')
args = parser.parse_args()

from_date = args.from_date
tipo_filter = args.tipo_filter
quota_min = args.quota_min
if from_date:
    try:
        datetime.strptime(from_date, '%Y-%m-%d')
    except ValueError:
        print(f"ERRORE: formato data non valido '{from_date}', usare YYYY-MM-DD")
        sys.exit(1)
if tipo_filter:
    tipo_filter = tipo_filter.upper()
    valid_tipi = ['GOL', 'SEGNO', 'DOPPIA_CHANCE', 'RISULTATO_ESATTO']
    if tipo_filter not in valid_tipi:
        print(f"ERRORE: tipo non valido '{tipo_filter}', usare: {', '.join(valid_tipi)}")
        sys.exit(1)

# Carica .env
base = os.path.dirname(os.path.abspath(__file__))
for env_path in [
    os.path.join(base, '..', 'functions_python', '.env'),
    os.path.join(base, '..', 'functions_python', 'ai_engine', '.env'),
    os.path.join(base, '..', '.env'),
]:
    if os.path.exists(env_path):
        load_dotenv(env_path)
        break
MONGO_URI = os.getenv('MONGO_URI')
if not MONGO_URI:
    print("ERRORE: MONGO_URI non trovata")
    sys.exit(1)

client = MongoClient(MONGO_URI)
db = client['football_simulator_db']
coll = db['daily_predictions_unified']

print("=== HYBRID PATTERN MIXER v2 ===")
print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"Periodo: {'dal ' + from_date if from_date else 'storico completo'}")
print(f"Filtro tipo: {tipo_filter if tipo_filter else 'tutti'}")
print(f"Quota minima sorgente: {quota_min if quota_min else 'nessuna'}\n")

# ========== CARICA REPORT ESISTENTI ==========
report_dir = os.path.join(base, '..', '_analisi_pattern')

# Trova i report piu recenti (senza _from_ per avere lo storico completo)
elite_files = sorted([f for f in os.listdir(report_dir)
                       if f.startswith('elite_pattern_report_') and f.endswith('.json') and '_from_' not in f],
                      reverse=True)
bizarre_files = sorted([f for f in os.listdir(report_dir)
                         if f.startswith('bizarre_pattern_report_') and f.endswith('.json') and '_from_' not in f],
                        reverse=True)

if not elite_files or not bizarre_files:
    print("ERRORE: serve prima lanciare elite_pattern_analysis.py e explore_bizarre_patterns.py")
    sys.exit(1)

elite_path = os.path.join(report_dir, elite_files[0])
bizarre_path = os.path.join(report_dir, bizarre_files[0])
print(f"Report elite:   {elite_files[0]}")
print(f"Report bizarre: {bizarre_files[0]}")

with open(elite_path, 'r', encoding='utf-8') as f:
    elite_data = json.load(f)
with open(bizarre_path, 'r', encoding='utf-8') as f:
    bizarre_data = json.load(f)

# ========== PARSING CONDIZIONI ==========
# Ogni condizione e una tupla (categoria, nome, funzione_test)

def parse_condition(text):
    """Parsa una singola condizione testuale e restituisce (categoria, nome, funzione)."""
    t = text.strip()

    # TIPO
    if t in ('GOL', 'SEGNO', 'DOPPIA_CHANCE', 'RISULTATO_ESATTO'):
        return ('tipo', f"tipo={t}", lambda r, v=t: r['tipo'] == v)

    # PRONOSTICO specifico
    m = re.match(r'^PRON=(.+)$', t)
    if m:
        val = m.group(1)
        return ('pronostico', f"pron={val}", lambda r, v=val: r['pronostico'] == v)

    # SOURCE
    m = re.match(r'^SRC=(.+)$', t)
    if m:
        val = m.group(1)
        return ('source', f"src={val}", lambda r, v=val: r['source'] == v)
    # Elite format: source come primo token (A, A+S, C, C_screm, etc)
    if t in ('A', 'A+S', 'C', 'C_screm', 'C_combo96', 'A+S_mg', 'A+S_o25_s6_conv', 'C_hw', 'C_mg', 'MC_xdraw', 'C_as_dc_rec'):
        return ('source', f"src={t}", lambda r, v=t: r['source'] == v)

    # ROUTING
    m = re.match(r'^ROUTING=(.+)$', t)
    if m:
        val = m.group(1)
        return ('routing', f"routing={val}", lambda r, v=val: r['routing'] == v)
    if t in ('single', 'consensus_both', 'scrematura_segno', 'combo_96_dc_flip',
             'o25_s6_to_goal', 'priority_chain', 'multigol_v6', 'mc_filter_convert', 'union'):
        return ('routing', f"routing={t}", lambda r, v=t: r['routing'] == v)

    # LEAGUE
    m = re.match(r'^LEAGUE=(.+)$', t)
    if m:
        val = m.group(1)
        return ('league', f"league={val}", lambda r, v=val: r['league'] == v)

    # CONFIDENCE soglia
    m = re.match(r'^CONF>=(\d+)$', t)
    if m:
        val = int(m.group(1))
        return ('confidence', f"conf>={val}", lambda r, v=val: r['confidence'] >= v)

    # CONFIDENCE range (elite format: "80-100", "70-79", etc)
    m = re.match(r'^(\d+)-(\d+)$', t)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if 40 <= lo <= 100:  # sembra confidence
            return ('confidence', f"conf{lo}-{hi}", lambda r, l=lo, h=hi: l <= r['confidence'] <= h)

    # STELLE soglia
    m = re.match(r'^STARS>=(.+)$', t)
    if m:
        val = float(m.group(1))
        return ('stars', f"stelle>={val}", lambda r, v=val: r['stars'] >= v)

    # STELLE range (elite format: "3.5-4", "3-3.5", etc)
    m = re.match(r'^(\d+\.?\d*)-(\d+\.?\d*)$', t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo < 6:  # sembra stelle
            return ('stars', f"stelle{lo}-{hi}", lambda r, l=lo, h=hi: l <= r['stars'] < h)

    # QUOTA range (bizarre format: "q1.30-1.39")
    m = re.match(r'^q(\d+\.\d+)-(\d+\.\d+)$', t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return ('quota', f"q{lo}-{hi}", lambda r, l=lo, h=hi+0.001: l <= r['quota'] < h)

    # QUOTA range (elite format: "1.30-1.49", "2.00-2.49")
    m = re.match(r'^(\d+\.\d+)-(\d+\.\d+)$', t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo >= 1.0 and lo < 10.0:  # sembra quota
            return ('quota', f"q{lo}-{hi}", lambda r, l=lo, h=hi+0.001: l <= r['quota'] < h)

    # STAKE
    m = re.match(r'^STAKE>=(\d+)$', t)
    if m:
        val = int(m.group(1))
        return ('stake', f"stake>={val}", lambda r, v=val: r['stake'] >= v)

    # EDGE
    m = re.match(r'^EDGE>=(\d+)$', t)
    if m:
        return None  # edge non e nei record, skip

    # EXTREME: skip il prefisso, le condizioni dentro sono gia parsate
    if t.startswith('EXTREME:'):
        return None

    # Non riconosciuto
    return None


def extract_conditions_elite(pattern_str, dimension):
    """Estrae condizioni da un pattern elite (formato: 'A | B | C' con dimensione che indica l'ordine)."""
    parts = [p.strip() for p in pattern_str.split('|')]
    dim_parts = dimension.split('+')

    conditions = []
    for i, part in enumerate(parts):
        # Usa la dimensione per capire cosa rappresenta il valore
        dim = dim_parts[i] if i < len(dim_parts) else ''

        if dim == 'tipo':
            cond = parse_condition(part)
        elif dim == 'src':
            cond = ('source', f"src={part}", lambda r, v=part: r['source'] == v)
        elif dim == 'quota':
            cond = parse_condition(part)
        elif dim == 'conf':
            cond = parse_condition(part)
        elif dim == 'stars':
            cond = parse_condition(part)
        elif dim == 'routing':
            cond = ('routing', f"routing={part}", lambda r, v=part: r['routing'] == v)
        elif dim == 'edge':
            cond = parse_condition(part)
        else:
            cond = parse_condition(part)

        if cond:
            conditions.append(cond)

    return conditions


def extract_conditions_bizarre(pattern_str):
    """Estrae condizioni da un pattern bizarre (formato: 'A + B + C')."""
    # Rimuovi prefisso EXTREME:
    clean = pattern_str.strip()
    if clean.startswith('EXTREME:'):
        clean = clean[len('EXTREME:'):].strip()

    parts = [p.strip() for p in clean.split('+')]
    conditions = []
    for part in parts:
        cond = parse_condition(part.strip())
        if cond:
            conditions.append(cond)
    return conditions


# ========== FILTRO TIPO PATTERN ==========
# Mappa pronostici -> tipo mercato
PRONOSTICI_GOL = {'Over 1.5', 'Over 2.5', 'Over 3.5', 'Under 1.5', 'Under 2.5', 'Under 3.5',
                  'Goal', 'No Goal', 'MG 2-4', 'MG 3-5', 'MG 2-3', 'MG 1-3'}
PRONOSTICI_SEGNO = {'1', '2', 'X', '1X', 'X2', '12'}
PRONOSTICI_DC = {'X2', '1X', '12'}  # doppia chance


def pattern_has_tipo(pattern_text, tipo_cercato):
    """Controlla se un pattern (testo) produce pronostici del tipo cercato."""
    t = pattern_text.upper()
    if tipo_cercato == 'GOL':
        if 'GOL' in t and 'MULTIGOL' not in t:
            return True
        for p in PRONOSTICI_GOL:
            if f'PRON={p}'.upper() in t:
                return True
        if 'MG ' in t or 'MULTIGOL' in t:
            return True
        return False
    elif tipo_cercato == 'SEGNO':
        if 'SEGNO' in t:
            return True
        for p in ('PRON=1', 'PRON=2', 'PRON=X'):
            if p.upper() in t and 'PRON=X2' not in t and 'PRON=1X' not in t:
                return True
        return False
    elif tipo_cercato == 'DOPPIA_CHANCE':
        if 'DOPPIA_CHANCE' in t:
            return True
        for p in PRONOSTICI_DC:
            if f'PRON={p}'.upper() in t:
                return True
        return False
    return True  # nessun filtro


def pattern_has_quota_min(pattern_text, min_q):
    """Controlla se un pattern ha una condizione di quota >= min_q."""
    # Cerca formati: q1.50-1.59, q1.60-1.79, 1.50-1.79, q<1.60, etc.
    for m in re.finditer(r'q?(\d+\.\d+)', pattern_text):
        val = float(m.group(1))
        if 1.0 <= val < 10.0 and val >= min_q:
            return True
    return False


# ========== RACCOGLI TUTTE LE CONDIZIONI DAI TOP 30 ==========
print("\nEstrazione condizioni dai report...", end=" ", flush=True)

CATEGORIE_ESCLUSE = {'league'}  # troppo specifiche, i pattern devono essere trasversali

all_conditions = {}  # nome -> (categoria, funzione)
pattern_conditions = []  # lista di (source, pattern_name, [condizioni])

skipped_tipo = 0
skipped_quota = 0

# Da elite top 30
for p in elite_data.get('elite_candidates', [])[:30]:
    if tipo_filter and not pattern_has_tipo(p['pattern'], tipo_filter):
        skipped_tipo += 1
        continue
    if quota_min and not pattern_has_quota_min(p['pattern'], quota_min):
        skipped_quota += 1
        continue
    conds = [(cat, name, fn) for cat, name, fn in extract_conditions_elite(p['pattern'], p['dimension']) if cat not in CATEGORIE_ESCLUSE]
    names = [c[1] for c in conds]
    for cat, name, fn in conds:
        if name not in all_conditions:
            all_conditions[name] = (cat, fn)
    if conds:
        pattern_conditions.append(('elite', p['pattern'], names))

# Da bizarre top 30 (scored)
for p in bizarre_data.get('top30_scored', []):
    if tipo_filter and not pattern_has_tipo(p['pattern'], tipo_filter):
        skipped_tipo += 1
        continue
    if quota_min and not pattern_has_quota_min(p['pattern'], quota_min):
        skipped_quota += 1
        continue
    conds = [(cat, name, fn) for cat, name, fn in extract_conditions_bizarre(p['pattern']) if cat not in CATEGORIE_ESCLUSE]
    names = [c[1] for c in conds]
    for cat, name, fn in conds:
        if name not in all_conditions:
            all_conditions[name] = (cat, fn)
    if conds:
        pattern_conditions.append(('bizarre', p['pattern'], names))

# Anche da bizarre hr75_n8
for p in bizarre_data.get('patterns_hr75_n8', []):
    if tipo_filter and not pattern_has_tipo(p['pattern'], tipo_filter):
        skipped_tipo += 1
        continue
    if quota_min and not pattern_has_quota_min(p['pattern'], quota_min):
        skipped_quota += 1
        continue
    conds = [(cat, name, fn) for cat, name, fn in extract_conditions_bizarre(p['pattern']) if cat not in CATEGORIE_ESCLUSE]
    names = [c[1] for c in conds]
    for cat, name, fn in conds:
        if name not in all_conditions:
            all_conditions[name] = (cat, fn)
    if conds:
        pattern_conditions.append(('bizarre', p['pattern'], names))

# Dedup pattern_conditions
seen = set()
unique_patterns = []
for src, pname, conds in pattern_conditions:
    key = tuple(sorted(conds))
    if key not in seen:
        seen.add(key)
        unique_patterns.append((src, pname, conds))

print(f"OK")
if tipo_filter:
    print(f"  Pattern scartati (tipo diverso da {tipo_filter}): {skipped_tipo}")
if quota_min:
    print(f"  Pattern scartati (quota < {quota_min}): {skipped_quota}")
print(f"  Condizioni uniche estratte: {len(all_conditions)}")
print(f"  Pattern sorgente (dedup): {len(unique_patterns)}")

# Mostra le condizioni trovate
print(f"\n  Condizioni per categoria:")
by_cat = defaultdict(list)
for name, (cat, _) in all_conditions.items():
    by_cat[cat].append(name)
for cat in sorted(by_cat):
    print(f"    {cat}: {', '.join(sorted(by_cat[cat]))}")

# ========== CARICA DATI DB ==========
query_filter = {"pronostici.esito": {"$in": [True, False]}}
if from_date:
    query_filter["date"] = {"$gte": from_date}

print(f"\nCaricamento dati...", end=" ", flush=True)
docs = list(coll.find(
    query_filter,
    {"date": 1, "league": 1, "pronostici": 1}
))
print(f"OK ({len(docs)} partite)")

print("Estrazione pronostici...", end=" ", flush=True)
records = []
for doc in docs:
    league = doc.get('league', '')
    for p in doc.get('pronostici', []):
        esito = p.get('esito')
        if esito not in [True, False]:
            continue
        records.append({
            'hit': esito is True,
            'tipo': p.get('tipo', ''),
            'pronostico': p.get('pronostico', ''),
            'quota': p.get('quota', 0) or 0,
            'confidence': p.get('confidence', 0) or 0,
            'stars': p.get('stars', 0) or 0,
            'source': p.get('source', ''),
            'routing': p.get('routing_rule', ''),
            'stake': p.get('stake', 0) or 0,
            'league': league,
        })
print(f"OK ({len(records)} pronostici)")

if not records:
    print("Nessun dato. Uscita.")
    sys.exit(0)

tot_hit = sum(1 for r in records if r['hit'])
print(f"Hit rate globale: {tot_hit}/{len(records)} = {tot_hit/len(records)*100:.1f}%")

# ========== PRE-CALCOLO FILTRI ==========
print("\nPre-calcolo filtri per record...", end=" ", flush=True)
cond_names = sorted(all_conditions.keys())
cond_fns = {name: fn for name, (_, fn) in all_conditions.items()}
cond_cats = {name: cat for name, (cat, _) in all_conditions.items()}

record_matches = []
for r in records:
    rm = set()
    for name, fn in cond_fns.items():
        try:
            if fn(r):
                rm.add(name)
        except:
            pass
    record_matches.append(rm)
print("OK")

# ========== PATTERN GIA IN PRODUZIONE ==========
def is_active_hybrid(combo_set):
    s = combo_set
    if 'tipo=SEGNO' in s and 'q1.50-1.79' in s and any('stelle3' in x for x in s): return 'E1'
    if 'tipo=SEGNO' in s and any('q1.5' in x for x in s) and 'conf50-59' in s: return 'E2'
    if 'tipo=DOPPIA_CHANCE' in s and 'src=C_screm' in s and 'q2.00-2.49' in s: return 'E3'
    if 'tipo=GOL' in s and any('q1.30' in x for x in s) and any('conf7' in x for x in s): return 'E4'
    if 'tipo=DOPPIA_CHANCE' in s and 'q2.00-2.49' in s and len(s) == 2: return 'E5'
    if 'tipo=SEGNO' in s and 'conf>=80' in s and len(s) == 2: return 'E6'
    if 'tipo=DOPPIA_CHANCE' in s and any('q1.30' in x for x in s) and 'conf60-69' in s: return 'E7'
    if 'tipo=GOL' in s and 'src=A+S' in s and any('q1.30' in x for x in s): return 'E8'
    if 'pron=MG 2-4' in s: return 'E10'
    if 'tipo=GOL' in s and 'src=C_screm' in s and any('q1.50' in x for x in s): return 'E14'
    if 'tipo=SEGNO' in s and any('q1.80' in x for x in s) and 'conf>=80' in s: return 'E15'
    if 'tipo=DOPPIA_CHANCE' in s and any('q1.30' in x for x in s) and any('conf70' in x for x in s): return 'E16'
    return None

# ========== MESCOLA: INCROCIA PEZZI DA PATTERN DIVERSI ==========
print("\nMescola pattern...", flush=True)

# Raccogliamo tutte le condizioni uniche come pool
all_cond_names = sorted(all_conditions.keys())
hybrid_results = []
tested = set()
combo_count = 0

# Strategia: per ogni coppia di pattern sorgente, prendi condizioni
# dall'uno e dall'altro e crea combinazioni ibride
for depth in [2, 3, 4, 5]:
    depth_count = 0
    total_combos = n_comb(len(all_cond_names), depth)
    progress_step = max(1, total_combos // 20)  # aggiorna ogni 5%
    idx = 0

    for combo in combinations(all_cond_names, depth):
        idx += 1
        if idx % progress_step == 0:
            pct = idx / total_combos * 100
            print(f"\r  Depth {depth}: {pct:.0f}% ({idx}/{total_combos})", end="", flush=True)

        # Skip se gia testato
        combo_key = tuple(sorted(combo))
        if combo_key in tested:
            continue
        tested.add(combo_key)

        # Skip se due condizioni della stessa categoria
        cats = [cond_cats[c] for c in combo]
        if len(cats) != len(set(cats)):
            continue

        # Conta match
        combo_set = set(combo)
        matching_idx = [i for i, rm in enumerate(record_matches) if combo_set.issubset(rm)]

        if len(matching_idx) < 5:
            continue

        combo_count += 1
        depth_count += 1

        matching = [records[i] for i in matching_idx]
        hits = sum(1 for r in matching if r['hit'])
        hr = round(hits / len(matching) * 100, 1)
        profit = 0
        for r in matching:
            if r['hit']:
                profit += (r['quota'] - 1) if r['quota'] > 0 else 0
            else:
                profit -= 1

        combo_name = ' + '.join(sorted(combo))
        active = is_active_hybrid(set(combo))

        hybrid_results.append({
            'pattern': combo_name,
            'hr': hr,
            'n': len(matching),
            'profit': round(profit, 1),
            'active': active,
            'depth': depth,
            '_idx': frozenset(matching_idx),  # per dedup subset
        })

    print(f"\r  Depth {depth}: 100% — {depth_count} combinazioni valide" + " " * 20)

print(f"Totale combinazioni testate: {combo_count}")

# ========== DEDUPLICAZIONE SUBSET ==========
# Se un pattern lungo matcha gli stessi identici record di uno piu corto,
# il lungo e ridondante (la condizione extra non filtra nulla)
print(f"Deduplicazione subset...", end=" ", flush=True)
hybrid_results.sort(key=lambda x: (x['depth'], -x['hr']))  # prima i piu corti
seen_idx_sets = {}  # frozenset(idx) -> pattern piu corto
deduped = []
removed = 0
for r in hybrid_results:
    idx_set = r['_idx']
    if idx_set in seen_idx_sets:
        # Stesso set di record di un pattern piu corto -> skip
        removed += 1
        continue
    seen_idx_sets[idx_set] = r['pattern']
    deduped.append(r)

hybrid_results = deduped
# Rimuovi campo interno
for r in hybrid_results:
    del r['_idx']
print(f"OK (rimossi {removed} duplicati, restano {len(hybrid_results)})")

# Ordina per HR
hybrid_results.sort(key=lambda x: (-x['hr'], -x['n']))

# ========== STAMPA RISULTATI ==========

tipo_label = f" [{tipo_filter}]" if tipo_filter else ""

# HR >= 75%, N >= 8
print(f"\n{'='*100}")
print(f"  PATTERN IBRIDI v2{tipo_label} — HR >= 75%, N >= 8")
print(f"  * = gia in produzione")
print(f"{'='*100}")
filtered_75 = [r for r in hybrid_results if r['hr'] >= 75 and r['n'] >= 8]
print(f"  {'Pattern':<65} {'HR':>7} {'N':>5} {'Profit':>8} {'':>6}")
print(f"  {'-'*95}")
for r in filtered_75[:30]:
    tag = f"* {r['active']}" if r['active'] else ""
    print(f"  {r['pattern']:<65} {r['hr']:>5.1f}%  {r['n']:>4}  {r['profit']:>+7.1f}  {tag}")

# HR >= 70%, N >= 15
print(f"\n{'='*100}")
print(f"  PATTERN IBRIDI v2 — HR >= 70%, N >= 15 (campione ampio)")
print(f"  * = gia in produzione")
print(f"{'='*100}")
filtered_70 = [r for r in hybrid_results if r['hr'] >= 70 and r['n'] >= 15]
print(f"  {'Pattern':<65} {'HR':>7} {'N':>5} {'Profit':>8} {'':>6}")
print(f"  {'-'*95}")
for r in filtered_70[:30]:
    tag = f"* {r['active']}" if r['active'] else ""
    print(f"  {r['pattern']:<65} {r['hr']:>5.1f}%  {r['n']:>4}  {r['profit']:>+7.1f}  {tag}")

# TOP 30 score
print(f"\n{'='*100}")
print(f"  TOP 30 — Score = HR * sqrt(N)")
print(f"  * = gia in produzione")
print(f"{'='*100}")
scored = [(r, r['hr'] * (r['n'] ** 0.5)) for r in hybrid_results if r['n'] >= 8 and r['hr'] >= 68]
scored.sort(key=lambda x: -x[1])
print(f"  {'#':>3} {'Pattern':<65} {'HR':>7} {'N':>5} {'Profit':>8} {'Score':>6} {'':>6}")
print(f"  {'-'*105}")
for i, (r, score) in enumerate(scored[:30], 1):
    tag = f"* {r['active']}" if r['active'] else ""
    print(f"  {i:>3}. {r['pattern']:<65} {r['hr']:>5.1f}%  {r['n']:>4}  {r['profit']:>+7.1f}  {score:>5.0f}  {tag}")

# Solo NUOVI
print(f"\n{'='*100}")
print(f"  TOP 20 NUOVI — Pattern non ancora in produzione, HR >= 70%, N >= 8")
print(f"{'='*100}")
new_only = [r for r in hybrid_results if not r['active'] and r['hr'] >= 70 and r['n'] >= 8]
print(f"  {'Pattern':<65} {'HR':>7} {'N':>5} {'Profit':>8}")
print(f"  {'-'*90}")
for r in new_only[:20]:
    print(f"  {r['pattern']:<65} {r['hr']:>5.1f}%  {r['n']:>4}  {r['profit']:>+7.1f}")

active_count = sum(1 for r in hybrid_results if r['active'] and r['hr'] >= 65 and r['n'] >= 5)
new_count = sum(1 for r in hybrid_results if not r['active'] and r['hr'] >= 65 and r['n'] >= 5)
print(f"\nTotale pattern HR>=65%: {active_count + new_count} ({active_count} gia attivi, {new_count} nuovi)")

client.close()

# ========== SALVATAGGIO REPORT ==========
print("\nSalvataggio report...", end=" ", flush=True)
log_dir = report_dir
today_str = datetime.now().strftime('%Y-%m-%d')
suffix = f"_from_{from_date}" if from_date else ""
tipo_suffix = f"_{tipo_filter.lower()}" if tipo_filter else ""
quota_suffix = f"_q{quota_min}" if quota_min else ""
base_name = f"hybrid_v2_pattern_report_{today_str}{suffix}{tipo_suffix}{quota_suffix}"

# --- TXT ---
lines = []
lines.append(f"{'='*100}")
lines.append(f"  REPORT HYBRID PATTERN MIXER v2")
lines.append(f"  Data report: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
lines.append(f"  Periodo: {'dal ' + from_date if from_date else 'storico completo'}")
lines.append(f"  Pronostici analizzati: {len(records)}")
lines.append(f"  Hit rate globale: {tot_hit}/{len(records)} = {tot_hit/len(records)*100:.1f}%")
lines.append(f"  Condizioni estratte dai report: {len(all_conditions)}")
lines.append(f"  Combinazioni testate: {combo_count}")
lines.append(f"  Sorgente: top 30 elite + top 30 bizarre + hr75_n8 bizarre")
lines.append(f"{'='*100}\n")

# HR >= 75%
lines.append(f"\n{'='*100}")
lines.append(f"  PATTERN IBRIDI v2 — HR >= 75%, N >= 8")
lines.append(f"  * = gia in produzione")
lines.append(f"{'='*100}")
lines.append(f"  {'Pattern':<65} {'HR':>7} {'N':>5} {'Profit':>8} {'':>6}")
lines.append(f"  {'-'*95}")
for r in filtered_75[:30]:
    tag = f"* {r['active']}" if r['active'] else ""
    lines.append(f"  {r['pattern']:<65} {r['hr']:>5.1f}%  {r['n']:>4}  {r['profit']:>+7.1f}  {tag}")

# HR >= 70% N >= 15
lines.append(f"\n{'='*100}")
lines.append(f"  PATTERN IBRIDI v2 — HR >= 70%, N >= 15 (campione ampio)")
lines.append(f"  * = gia in produzione")
lines.append(f"{'='*100}")
lines.append(f"  {'Pattern':<65} {'HR':>7} {'N':>5} {'Profit':>8} {'':>6}")
lines.append(f"  {'-'*95}")
for r in filtered_70[:30]:
    tag = f"* {r['active']}" if r['active'] else ""
    lines.append(f"  {r['pattern']:<65} {r['hr']:>5.1f}%  {r['n']:>4}  {r['profit']:>+7.1f}  {tag}")

# TOP 30
lines.append(f"\n{'='*100}")
lines.append(f"  TOP 30 — Score = HR * sqrt(N)")
lines.append(f"  * = gia in produzione")
lines.append(f"{'='*100}")
lines.append(f"  {'#':>3} {'Pattern':<65} {'HR':>7} {'N':>5} {'Profit':>8} {'Score':>6} {'':>6}")
lines.append(f"  {'-'*105}")
for i, (r, score) in enumerate(scored[:30], 1):
    tag = f"* {r['active']}" if r['active'] else ""
    lines.append(f"  {i:>3}. {r['pattern']:<65} {r['hr']:>5.1f}%  {r['n']:>4}  {r['profit']:>+7.1f}  {score:>5.0f}  {tag}")

# Nuovi
lines.append(f"\n{'='*100}")
lines.append(f"  TOP 20 NUOVI — Pattern non ancora in produzione, HR >= 70%, N >= 8")
lines.append(f"{'='*100}")
lines.append(f"  {'Pattern':<65} {'HR':>7} {'N':>5} {'Profit':>8}")
lines.append(f"  {'-'*90}")
for r in new_only[:20]:
    lines.append(f"  {r['pattern']:<65} {r['hr']:>5.1f}%  {r['n']:>4}  {r['profit']:>+7.1f}")

lines.append(f"\nTotale pattern HR>=65%: {active_count + new_count} ({active_count} gia attivi, {new_count} nuovi)")

txt_path = os.path.join(log_dir, f"{base_name}.txt")
with open(txt_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))

# --- JSON ---
json_data = {
    'report_date': today_str,
    'from_date': from_date,
    'total_predictions': len(records),
    'total_hits': tot_hit,
    'hit_rate_global': round(tot_hit / len(records) * 100, 1) if records else 0,
    'conditions_extracted': len(all_conditions),
    'combos_tested': combo_count,
    'source_patterns': len(unique_patterns),
    'top_patterns': [
        {
            'pattern': r['pattern'],
            'hit_rate': r['hr'],
            'sample_size': r['n'],
            'profit': r['profit'],
            'active': r['active'],
            'depth': r['depth'],
        }
        for r in hybrid_results if r['hr'] >= 65 and r['n'] >= 5
    ]
}

json_path = os.path.join(log_dir, f"{base_name}.json")
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(json_data, f, indent=2, ensure_ascii=False)

print("OK")
print(f"Report TXT: {txt_path}")
print(f"Report JSON: {json_path}")
print("\n=== FINE HYBRID MIXER v2 ===")
