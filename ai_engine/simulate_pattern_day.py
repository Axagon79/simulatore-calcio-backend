"""
Simulazione giornaliera pattern — Verifica come sarebbero andati oggi i pronostici
che matchano le top 30 elite, top 30 bizarre e top 30 hybrid.

Uso:
  python simulate_pattern_day.py                    # oggi
  python simulate_pattern_day.py --date 2026-04-10  # data specifica
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv
from pymongo import MongoClient

# ========== ARGOMENTI CLI ==========
parser = argparse.ArgumentParser(description='Simulazione giornaliera pattern')
parser.add_argument('--date', type=str, default=None,
                    help='Data da simulare (YYYY-MM-DD). Default: oggi.')
args = parser.parse_args()

sim_date = args.date or datetime.now().strftime('%Y-%m-%d')

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

print(f"=== SIMULAZIONE PATTERN — {sim_date} ===\n")

# ========== PARSING CONDIZIONI (da hybrid_pattern_mixer_v2.py) ==========

def parse_condition(text):
    """Parsa una singola condizione testuale e restituisce (categoria, nome, funzione)."""
    t = text.strip()

    if t in ('GOL', 'SEGNO', 'DOPPIA_CHANCE', 'RISULTATO_ESATTO'):
        return ('tipo', f"tipo={t}", lambda r, v=t: r['tipo'] == v)

    m = re.match(r'^PRON=(.+)$', t)
    if m:
        val = m.group(1)
        return ('pronostico', f"pron={val}", lambda r, v=val: r['pronostico'] == v)

    m = re.match(r'^SRC=(.+)$', t)
    if m:
        val = m.group(1)
        return ('source', f"src={val}", lambda r, v=val: r['source'] == v)
    if t in ('A', 'A+S', 'C', 'C_screm', 'C_combo96', 'A+S_mg', 'A+S_o25_s6_conv', 'C_hw', 'C_mg', 'MC_xdraw', 'C_as_dc_rec'):
        return ('source', f"src={t}", lambda r, v=t: r['source'] == v)

    m = re.match(r'^ROUTING=(.+)$', t)
    if m:
        val = m.group(1)
        return ('routing', f"routing={val}", lambda r, v=val: r['routing'] == v)
    if t in ('single', 'consensus_both', 'scrematura_segno', 'combo_96_dc_flip',
             'o25_s6_to_goal', 'priority_chain', 'multigol_v6', 'mc_filter_convert', 'union'):
        return ('routing', f"routing={t}", lambda r, v=t: r['routing'] == v)

    m = re.match(r'^CONF>=(\d+)$', t)
    if m:
        val = int(m.group(1))
        return ('confidence', f"conf>={val}", lambda r, v=val: r['confidence'] >= v)

    m = re.match(r'^(\d+)-(\d+)$', t)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if 40 <= lo <= 100:
            return ('confidence', f"conf{lo}-{hi}", lambda r, l=lo, h=hi: l <= r['confidence'] <= h)

    m = re.match(r'^STARS>=(.+)$', t)
    if m:
        val = float(m.group(1))
        return ('stars', f"stelle>={val}", lambda r, v=val: r['stars'] >= v)

    m = re.match(r'^(\d+\.?\d*)-(\d+\.?\d*)$', t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo < 6:
            return ('stars', f"stelle{lo}-{hi}", lambda r, l=lo, h=hi: l <= r['stars'] < h)

    m = re.match(r'^q(\d+\.\d+)-(\d+\.\d+)$', t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return ('quota', f"q{lo}-{hi}", lambda r, l=lo, h=hi+0.001: l <= r['quota'] < h)

    m = re.match(r'^(\d+\.\d+)-(\d+\.\d+)$', t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        if lo >= 1.0 and lo < 10.0:
            return ('quota', f"q{lo}-{hi}", lambda r, l=lo, h=hi+0.001: l <= r['quota'] < h)

    m = re.match(r'^STAKE>=(\d+)$', t)
    if m:
        val = int(m.group(1))
        return ('stake', f"stake>={val}", lambda r, v=val: r['stake'] >= v)

    if t.startswith('EXTREME:') or t.startswith('EDGE>='):
        return None

    return None


def extract_conditions_elite(pattern_str, dimension):
    parts = [p.strip() for p in pattern_str.split('|')]
    dim_parts = dimension.split('+')
    conditions = []
    for i, part in enumerate(parts):
        dim = dim_parts[i] if i < len(dim_parts) else ''
        if dim == 'src':
            cond = ('source', f"src={part}", lambda r, v=part: r['source'] == v)
        elif dim == 'routing':
            cond = ('routing', f"routing={part}", lambda r, v=part: r['routing'] == v)
        else:
            cond = parse_condition(part)
        if cond:
            conditions.append(cond)
    return conditions


def extract_conditions_bizarre(pattern_str):
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


def extract_conditions_hybrid(pattern_str):
    """Pattern hybrid hanno formato: 'cond1 + cond2 + cond3' con nomi gia normalizzati."""
    parts = [p.strip() for p in pattern_str.split(' + ')]
    conditions = []
    for part in parts:
        # I pattern hybrid usano gia il formato normalizzato (tipo=SEGNO, q1.3-1.49, etc)
        cond = parse_hybrid_condition(part)
        if cond:
            conditions.append(cond)
    return conditions


def parse_hybrid_condition(text):
    """Parsa una condizione nel formato normalizzato dell'output hybrid."""
    t = text.strip()

    m = re.match(r'^tipo=(.+)$', t)
    if m:
        val = m.group(1)
        return ('tipo', t, lambda r, v=val: r['tipo'] == v)

    m = re.match(r'^pron=(.+)$', t)
    if m:
        val = m.group(1)
        return ('pronostico', t, lambda r, v=val: r['pronostico'] == v)

    m = re.match(r'^src=(.+)$', t)
    if m:
        val = m.group(1)
        return ('source', t, lambda r, v=val: r['source'] == v)

    m = re.match(r'^routing=(.+)$', t)
    if m:
        val = m.group(1)
        return ('routing', t, lambda r, v=val: r['routing'] == v)

    m = re.match(r'^conf>=(\d+)$', t)
    if m:
        val = int(m.group(1))
        return ('confidence', t, lambda r, v=val: r['confidence'] >= v)

    m = re.match(r'^conf(\d+)-(\d+)$', t)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return ('confidence', t, lambda r, l=lo, h=hi: l <= r['confidence'] <= h)

    m = re.match(r'^stelle>=(.+)$', t)
    if m:
        val = float(m.group(1))
        return ('stars', t, lambda r, v=val: r['stars'] >= v)

    m = re.match(r'^stelle(\d+\.?\d*)-(\d+\.?\d*)$', t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return ('stars', t, lambda r, l=lo, h=hi: l <= r['stars'] < h)

    m = re.match(r'^q(\d+\.\d+)-(\d+\.\d+)$', t)
    if m:
        lo, hi = float(m.group(1)), float(m.group(2))
        return ('quota', t, lambda r, l=lo, h=hi+0.001: l <= r['quota'] < h)

    m = re.match(r'^stake>=(\d+)$', t)
    if m:
        val = int(m.group(1))
        return ('stake', t, lambda r, v=val: r['stake'] >= v)

    return None


# ========== VERIFICA ESITO ==========
def check_pronostico(pronostico, tipo, real_score):
    if not real_score or ':' not in real_score:
        return None
    parts = real_score.split(':')
    try:
        gh, ga = int(parts[0].strip()), int(parts[1].strip())
    except (ValueError, IndexError):
        return None

    total_goals = gh + ga

    if tipo == 'SEGNO':
        if pronostico == '1': return gh > ga
        elif pronostico == 'X': return gh == ga
        elif pronostico == '2': return gh < ga

    elif tipo == 'DOPPIA_CHANCE':
        if pronostico == '1X': return gh >= ga
        elif pronostico == 'X2': return gh <= ga
        elif pronostico == '12': return gh != ga

    elif tipo == 'GOL':
        if pronostico == 'Over 1.5': return total_goals > 1
        elif pronostico == 'Over 2.5': return total_goals > 2
        elif pronostico == 'Over 3.5': return total_goals > 3
        elif pronostico == 'Under 1.5': return total_goals <= 1
        elif pronostico == 'Under 2.5': return total_goals <= 2
        elif pronostico == 'Under 3.5': return total_goals <= 3
        elif pronostico == 'Goal': return gh > 0 and ga > 0
        elif pronostico in ('NoGoal', 'No Goal'): return gh == 0 or ga == 0
        # Multigol
        m = re.match(r'^MG (\d+)-(\d+)$', pronostico)
        if m:
            lo, hi = int(m.group(1)), int(m.group(2))
            return lo <= total_goals <= hi

    elif tipo == 'RISULTATO_ESATTO':
        re_parts = pronostico.split(':')
        if len(re_parts) == 2:
            return int(re_parts[0]) == gh and int(re_parts[1]) == ga

    return None


# ========== CARICA REPORT PATTERN ==========
report_dir = os.path.join(base, '..', '_analisi_pattern')

# Trova i report piu recenti
def find_latest(prefix):
    files = sorted([f for f in os.listdir(report_dir)
                    if f.startswith(prefix) and f.endswith('.json') and '_from_' not in f],
                   reverse=True)
    return os.path.join(report_dir, files[0]) if files else None

elite_path = find_latest('elite_pattern_report_')
bizarre_path = find_latest('bizarre_pattern_report_')
hybrid_path = find_latest('hybrid_v2_pattern_report_')

if not elite_path or not bizarre_path:
    print("ERRORE: report elite/bizarre non trovati in _analisi_pattern/")
    sys.exit(1)

with open(elite_path, 'r', encoding='utf-8') as f:
    elite_data = json.load(f)
with open(bizarre_path, 'r', encoding='utf-8') as f:
    bizarre_data = json.load(f)

hybrid_data = None
if hybrid_path:
    with open(hybrid_path, 'r', encoding='utf-8') as f:
        hybrid_data = json.load(f)

# Costruisci lista pattern con condizioni
all_patterns = []  # (nome_classifica, pattern_text, condizioni_parsed, hr_storica, n_storico)

# Elite top 30
for p in elite_data.get('elite_candidates', [])[:30]:
    conds = extract_conditions_elite(p['pattern'], p['dimension'])
    if conds:
        all_patterns.append(('ELITE', p['pattern'], conds, p['hit_rate'], p['sample_size']))

# Bizarre top 30
for p in bizarre_data.get('top30_scored', [])[:30]:
    conds = extract_conditions_bizarre(p['pattern'])
    if conds:
        all_patterns.append(('BIZARRE', p['pattern'], conds, p.get('hr', p.get('hit_rate', 0)), p.get('n', p.get('sample_size', 0))))

# Hybrid top 30 (score)
if hybrid_data:
    top_hybrid = [p for p in hybrid_data.get('top_patterns', []) if p.get('sample_size', 0) >= 8]
    # Ordina per score = HR * sqrt(N)
    top_hybrid.sort(key=lambda x: -x['hit_rate'] * (x['sample_size'] ** 0.5))
    for p in top_hybrid[:30]:
        conds = extract_conditions_hybrid(p['pattern'])
        if conds:
            all_patterns.append(('HYBRID', p['pattern'], conds, p['hit_rate'], p['sample_size']))

print(f"Pattern caricati: {len(all_patterns)} (ELITE: {sum(1 for p in all_patterns if p[0]=='ELITE')}, "
      f"BIZARRE: {sum(1 for p in all_patterns if p[0]=='BIZARRE')}, "
      f"HYBRID: {sum(1 for p in all_patterns if p[0]=='HYBRID')})")

# ========== CARICA PRONOSTICI DI OGGI ==========
print(f"\nCaricamento pronostici {sim_date}...", end=" ", flush=True)
docs = list(db['daily_predictions_unified'].find(
    {"date": sim_date},
    {"date": 1, "league": 1, "home": 1, "away": 1, "pronostici": 1}
))
print(f"{len(docs)} partite")

if not docs:
    print("Nessun pronostico trovato per questa data.")
    sys.exit(0)

# ========== CERCA RISULTATI ==========
print("Ricerca risultati...", end=" ", flush=True)
target = datetime.strptime(sim_date, '%Y-%m-%d')
results_map = {}  # (home, away) -> real_score

for delta in [0, 1, -1]:
    day = target + timedelta(days=delta)
    day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)

    pipeline = [
        {"$unwind": "$matches"},
        {"$match": {"matches.date_obj": {"$gte": day_start, "$lt": day_end}}},
        {"$project": {"match": "$matches"}}
    ]

    for r in db['h2h_by_round'].aggregate(pipeline):
        m = r['match']
        home = m.get('home', '')
        away = m.get('away', '')
        rs = m.get('real_score', '')
        if rs and ':' in rs and (home, away) not in results_map:
            results_map[(home, away)] = rs

print(f"{len(results_map)} risultati trovati")

# ========== MATCH PRONOSTICI vs PATTERN ==========
print("\nAnalisi match pattern...\n")

# Per ogni pronostico, prepara il record
all_prons = []  # (match_info, record, esito)
for doc in docs:
    home = doc.get('home', '')
    away = doc.get('away', '')
    league = doc.get('league', '')
    real_score = results_map.get((home, away))

    for p in doc.get('pronostici', []):
        record = {
            'tipo': p.get('tipo', ''),
            'pronostico': p.get('pronostico', ''),
            'quota': p.get('quota', 0) or 0,
            'confidence': p.get('confidence', 0) or 0,
            'stars': p.get('stars', 0) or 0,
            'source': p.get('source', ''),
            'routing': p.get('routing_rule', ''),
            'stake': p.get('stake', 0) or 0,
            'league': league,
        }

        # Calcola esito al volo da h2h_by_round (non dal campo esito del DB che si aggiorna dopo)
        esito = None
        if real_score:
            esito = check_pronostico(p.get('pronostico', ''), p.get('tipo', ''), real_score)

        all_prons.append({
            'home': home,
            'away': away,
            'league': league,
            'real_score': real_score,
            'record': record,
            'esito': esito,
            'tipo': p.get('tipo', ''),
            'pronostico': p.get('pronostico', ''),
            'quota': p.get('quota', 0) or 0,
            'elite': p.get('elite', False),
        })

print(f"Pronostici totali oggi: {len(all_prons)}")
con_risultato = [p for p in all_prons if p['esito'] is not None]
senza_risultato = [p for p in all_prons if p['real_score'] is None]
print(f"Con risultato: {len(con_risultato)}, Senza risultato (non giocate): {len(senza_risultato)}")

# Per ogni pattern, trova quali pronostici matchano
print(f"\n{'='*110}")
print(f"  RISULTATI SIMULAZIONE — {sim_date}")
print(f"{'='*110}\n")

# Raccogli tutti i match per pattern
pattern_results = []
for classifica, ptext, conds, hr_stor, n_stor in all_patterns:
    matched = []
    for pron in all_prons:
        r = pron['record']
        try:
            if all(fn(r) for _, _, fn in conds):
                matched.append(pron)
        except:
            continue

    if matched:
        pattern_results.append({
            'classifica': classifica,
            'pattern': ptext,
            'hr_storica': hr_stor,
            'n_storico': n_stor,
            'matched': matched,
        })

# Stampa risultati per classifica
for classifica_name in ['ELITE', 'BIZARRE', 'HYBRID']:
    patterns_cls = [p for p in pattern_results if p['classifica'] == classifica_name]
    if not patterns_cls:
        continue

    print(f"\n  --- TOP 30 {classifica_name} ---")
    print(f"  {'Pattern':<60} {'HR stor':>8} {'Match':>5} {'W':>3} {'L':>3} {'?':>3} {'P/L':>7} {'HR oggi':>8}")
    print(f"  {'-'*100}")

    cls_wins = 0
    cls_losses = 0
    cls_pl = 0.0
    cls_pending = 0

    for pr in patterns_cls:
        wins = sum(1 for m in pr['matched'] if m['esito'] is True)
        losses = sum(1 for m in pr['matched'] if m['esito'] is False)
        pending = sum(1 for m in pr['matched'] if m['esito'] is None)
        n = len(pr['matched'])

        pl = 0
        for m in pr['matched']:
            if m['esito'] is True:
                pl += (m['quota'] - 1) if m['quota'] > 0 else 0
            elif m['esito'] is False:
                pl -= 1

        hr_oggi = f"{wins/(wins+losses)*100:.0f}%" if (wins + losses) > 0 else "n/d"

        print(f"  {pr['pattern']:<60} {pr['hr_storica']:>6.1f}%  {n:>4}  {wins:>3} {losses:>3} {pending:>3} {pl:>+7.2f}  {hr_oggi:>7}")

        cls_wins += wins
        cls_losses += losses
        cls_pl += pl
        cls_pending += pending

    cls_hr = f"{cls_wins/(cls_wins+cls_losses)*100:.1f}%" if (cls_wins + cls_losses) > 0 else "n/d"
    print(f"  {'-'*100}")
    print(f"  {'TOTALE ' + classifica_name:<60} {'':>8} {'':>5} {cls_wins:>3} {cls_losses:>3} {cls_pending:>3} {cls_pl:>+7.2f}  {cls_hr:>7}")

# ========== RIEPILOGO PRONOSTICI UNICI ==========
# Un pronostico puo matchare piu pattern — mostriamo i pronostici unici selezionati
print(f"\n\n{'='*110}")
print(f"  PRONOSTICI UNICI SELEZIONATI DAI PATTERN")
print(f"{'='*110}\n")

# Raggruppa per (home, away, pronostico) con lista pattern che lo matchano
selected = defaultdict(lambda: {'pron': None, 'patterns': []})
for pr in pattern_results:
    for m in pr['matched']:
        key = (m['home'], m['away'], m['pronostico'], m['tipo'])
        if selected[key]['pron'] is None:
            selected[key]['pron'] = m
        selected[key]['patterns'].append(f"{pr['classifica'][:3]}")

print(f"  {'Partita':<40} {'Pronostico':<15} {'Tipo':<10} {'Quota':>6} {'Esito':>6} {'P/L':>7} {'N.Pat':>5} {'Elite':>5}")
print(f"  {'-'*100}")

tot_wins = 0
tot_losses = 0
tot_pl = 0.0
tot_pending = 0

# Ordina per partita
for key in sorted(selected.keys()):
    info = selected[key]
    m = info['pron']
    n_patterns = len(info['patterns'])
    match_label = f"{m['home']} - {m['away']}"
    if len(match_label) > 38:
        match_label = match_label[:38]

    if m['esito'] is True:
        esito_str = "WIN"
        pl = (m['quota'] - 1) if m['quota'] > 0 else 0
        tot_wins += 1
    elif m['esito'] is False:
        esito_str = "LOSS"
        pl = -1
        tot_losses += 1
    else:
        esito_str = "---"
        pl = 0
        tot_pending += 1

    tot_pl += pl
    elite_str = "si" if m.get('elite') else ""

    print(f"  {match_label:<40} {m['pronostico']:<15} {m['tipo']:<10} {m['quota']:>5.2f}  {esito_str:>5} {pl:>+7.2f} {n_patterns:>5} {elite_str:>5}")

print(f"  {'-'*100}")
hr_str = f"{tot_wins/(tot_wins+tot_losses)*100:.1f}%" if (tot_wins + tot_losses) > 0 else "n/d"
print(f"  TOTALE: {tot_wins}W {tot_losses}L {tot_pending}? | HR: {hr_str} | P/L: {tot_pl:>+.2f}u")

print(f"\n=== FINE SIMULAZIONE ===")
client.close()
