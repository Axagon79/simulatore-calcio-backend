"""
Esplorazione pattern bizzarri/creativi per trovare nuovi pattern Elite.
Cerca combinazioni insolite con HR alto.

Uso:
  python explore_bizarre_patterns.py                  # storico completo
  python explore_bizarre_patterns.py --from 2026-04-01  # solo dal 1 aprile
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
parser = argparse.ArgumentParser(description='Esplorazione pattern bizzarri')
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

print("=== ESPLORAZIONE PATTERN BIZZARRI ===")
print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
print(f"Periodo: {'dal ' + from_date if from_date else 'storico completo'}\n")

# Carica tutti i pronostici con esito
query_filter = {"pronostici.esito": {"$in": [True, False]}}
if from_date:
    query_filter["date"] = {"$gte": from_date}

print("Caricamento dati...", end=" ", flush=True)
docs = list(coll.find(
    query_filter,
    {"pronostici": 1, "home": 1, "away": 1, "date": 1, "league": 1}
))
print(f"OK ({len(docs)} partite)")

print("Estrazione pronostici...", end=" ", flush=True)
all_preds = []
for doc in docs:
    for p in doc.get('pronostici', []):
        if p.get('esito') in [True, False]:
            p['_league'] = doc.get('league', '')
            p['_date'] = doc.get('date', '')
            p['_home'] = doc.get('home', '')
            p['_away'] = doc.get('away', '')
            all_preds.append(p)

print(f"OK ({len(all_preds)} pronostici)\n")

# ========== PATTERN GIA IN PRODUZIONE (per marcatura *) ==========
def is_active_bizarre(name):
    """Verifica se un pattern bizarre corrisponde a uno dei 24 pattern attivi."""
    n = name.upper()

    # --- ELITE ---
    # P1: SEGNO + q1.50-1.79 + STARS>=3 (parziale)
    if 'SEGNO' in n and 'Q1.50-1.' in n and 'STARS>=3' in n:
        return 'E1'
    # P2: SEGNO + q1.50-1.79 + CONF (50-59 nel range)
    # P3/P5: DC + C_screm + q2.00-2.49
    if 'DOPPIA_CHANCE' in n and 'C_SCREM' in n and 'Q2.00-2.49' in n:
        return 'E3'
    if 'DOPPIA_CHANCE' in n and 'Q2.00-2.49' in n:
        return 'E5'
    # P4/P11: GOL + q1.30-1.49 + CONF>=70
    if 'GOL' in n and ('Q1.30-1.3' in n or 'Q1.30-1.4' in n) and 'CONF>=70' in n:
        return 'E4'
    # P6: SEGNO + CONF>=80
    if 'SEGNO' in n and 'CONF>=80' in n:
        return 'E6'
    if 'SEGNO' in n and 'CONF>=85' in n:
        return 'E6'
    if 'SEGNO' in n and 'CONF>=90' in n:
        return 'E6'
    # P7: DC + q1.30-1.49 + CONF>=60
    if 'DOPPIA_CHANCE' in n and ('Q1.30-1.3' in n or 'Q1.30-1.4' in n) and 'CONF>=60' in n:
        return 'E7'
    # P8/P13: GOL + A+S + q1.30-1.49
    if 'GOL' in n and 'SRC=A+S' in n and ('Q1.30-1.3' in n or 'Q1.30-1.4' in n):
        return 'E8'
    # P10: MG 2-4
    if 'MG 2-4' in name or 'MULTIGOL 2-4' in n:
        return 'E10'
    # P14: GOL + C_screm + q1.50-1.59
    if 'GOL' in n and 'C_SCREM' in n and 'Q1.50-1.' in n:
        return 'E14'
    # P15: SEGNO + q1.80-1.99 + CONF>=80
    if 'SEGNO' in n and 'Q1.80-1.99' in n and 'CONF>=80' in n:
        return 'E15'
    # P16: DC + q1.30-1.49 + CONF>=70
    if 'DOPPIA_CHANCE' in n and ('Q1.30-1.3' in n or 'Q1.30-1.4' in n) and 'CONF>=70' in n:
        return 'E16'

    # --- DIAMANTI (routing rules) ---
    if 'DIAMOND' in n:
        return 'D'
    # Diamond P1/2: Under 3.5 + A/S + conf>=60
    if 'UNDER 3.5' in n and ('SRC=A' in n or 'SRC=S' in n) and 'CONF>=60' in n:
        return 'D1'
    # Diamond P4: Over 1.5 + A + conf>=65
    if 'OVER 1.5' in n and 'SRC=A' in n and 'CONF>=65' in n:
        return 'D4'
    # Diamond P14: GOAL + C + conf>=65
    if ('GOAL' in n or 'GG' in n) and 'SRC=C' in n and 'CONF>=65' in n:
        return 'D14'

    return None

def calc_hr(preds_list):
    if not preds_list:
        return 0, 0
    hits = sum(1 for p in preds_list if p.get('esito') is True)
    return round(hits / len(preds_list) * 100, 1), len(preds_list)

def calc_profit(preds_list):
    """Calcola profit unitario di una lista di pronostici."""
    profit = 0
    for p in preds_list:
        q = p.get('quota', 0) or 0
        if p.get('esito') is True:
            profit += (q - 1) if q > 0 else 0
        else:
            profit -= 1
    return round(profit, 1)

def print_results(title, results, results_profit, min_n=8, min_hr=75):
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"  * = gia in produzione")
    print(f"{'='*90}")
    filtered = [(name, hr, n) for name, hr, n in results if n >= min_n and hr >= min_hr]
    filtered.sort(key=lambda x: (-x[1], -x[2]))
    if not filtered:
        print("  Nessun pattern trovato con i criteri minimi")
        return
    print(f"  {'Pattern':<55} {'HR':>7} {'N':>5} {'Profit':>8} {'':>6}")
    print(f"  {'-'*85}")
    for name, hr, n in filtered[:20]:
        active = is_active_bizarre(name)
        tag = f"* {active}" if active else ""
        profit = results_profit.get(name, 0)
        print(f"  {name:<55} {hr:>5.1f}%  {n:>4}  {profit:>+7.1f}  {tag}")

# ============================================================
# GENERAZIONE COMBINAZIONI (15 categorie)
# ============================================================
print("Generazione combinazioni...", end=" ", flush=True)
groups = defaultdict(list)
for p in all_preds:
    # Usiamo la data come proxy
    tipo = p.get('tipo', '')
    quota = p.get('quota', 0) or 0
    conf = p.get('confidence', 0) or 0
    stars = p.get('stars', 0) or 0
    source = p.get('source', '')

    # 2. FAVORITI PESANTI (quota molto bassa)
    if quota > 0 and quota < 1.30:
        groups[f"ULTRA_FAVORITO q<1.30 + {tipo}"].append(p)
    if quota > 0 and quota < 1.20:
        groups[f"MEGA_FAVORITO q<1.20 + {tipo}"].append(p)

    # 3. PARTITE EQUILIBRATE (quota alta per segno)
    if tipo == 'SEGNO' and 2.50 <= quota < 3.50:
        groups[f"SEGNO_EQUILIBRATO q2.50-3.49"].append(p)
    if tipo == 'SEGNO' and quota >= 3.50:
        groups[f"SEGNO_UNDERDOG q>=3.50"].append(p)

    # 4. CONFIDENCE ESTREMA
    if conf >= 90:
        groups[f"CONF>=90 + {tipo}"].append(p)
    if conf >= 85:
        groups[f"CONF>=85 + {tipo}"].append(p)

    # 5. STELLE ALTE
    if stars >= 4.0:
        groups[f"STARS>=4.0 + {tipo}"].append(p)
    if stars >= 3.5:
        groups[f"STARS>=3.5 + {tipo}"].append(p)

    # 6. SOURCE + STARS combos
    if source and stars >= 3.0:
        groups[f"SRC={source} + STARS>=3.0"].append(p)
    if source and conf >= 70:
        groups[f"SRC={source} + CONF>=70"].append(p)

    # 7. QUOTA ESATTA combos
    for qlo, qhi, qlabel in [(1.01, 1.20, "q1.01-1.19"), (1.20, 1.30, "q1.20-1.29"),
                              (1.30, 1.40, "q1.30-1.39"), (1.40, 1.50, "q1.40-1.49"),
                              (1.50, 1.60, "q1.50-1.59"), (1.60, 1.80, "q1.60-1.79"),
                              (1.80, 2.00, "q1.80-1.99"), (2.00, 2.50, "q2.00-2.49"),
                              (2.50, 3.00, "q2.50-2.99"), (3.00, 5.00, "q3.00-4.99")]:
        if qlo <= quota < qhi:
            groups[f"{tipo} + {qlabel}"].append(p)
            if stars >= 3.0:
                groups[f"{tipo} + {qlabel} + STARS>=3"].append(p)
            if conf >= 70:
                groups[f"{tipo} + {qlabel} + CONF>=70"].append(p)
            if conf >= 60:
                groups[f"{tipo} + {qlabel} + CONF>=60"].append(p)
            if source:
                groups[f"{tipo} + {qlabel} + SRC={source}"].append(p)

    # 8. EDGE (probabilita - 1/quota)
    prob = p.get('probabilita_stimata', 0) or 0
    if quota > 0 and prob > 0:
        implied = 1.0 / quota * 100
        edge = prob - implied
        if edge >= 30:
            groups[f"EDGE>=30 + {tipo}"].append(p)
        if edge >= 20:
            groups[f"EDGE>=20 + {tipo}"].append(p)
        if edge >= 20 and conf >= 70:
            groups[f"EDGE>=20 + CONF>=70 + {tipo}"].append(p)
        if edge >= 15 and stars >= 3.0:
            groups[f"EDGE>=15 + STARS>=3 + {tipo}"].append(p)

    # 9. STAKE alto
    stake = p.get('stake', 0) or 0
    if stake >= 3:
        groups[f"STAKE>=3 + {tipo}"].append(p)
    if stake >= 4:
        groups[f"STAKE>=4 + {tipo}"].append(p)

    # 10. ROUTING RULE combos
    rr = p.get('routing_rule', '')
    if rr:
        groups[f"ROUTING={rr} + {tipo}"].append(p)
        if conf >= 70:
            groups[f"ROUTING={rr} + {tipo} + CONF>=70"].append(p)
        if stars >= 3.0:
            groups[f"ROUTING={rr} + {tipo} + STARS>=3"].append(p)

    # 11. PRONOSTICO SPECIFICO (1, X, 2, 1X, X2, 12, Over, Under, GG, NG)
    pron = p.get('pronostico', '')
    if pron and pron != 'NO BET':
        groups[f"PRON={pron}"].append(p)
        if conf >= 70:
            groups[f"PRON={pron} + CONF>=70"].append(p)
        if stars >= 3.0:
            groups[f"PRON={pron} + STARS>=3"].append(p)
        if 1.30 <= quota < 1.50:
            groups[f"PRON={pron} + q1.30-1.49"].append(p)
        if 1.50 <= quota < 1.80:
            groups[f"PRON={pron} + q1.50-1.79"].append(p)

    # 12. COMBO ESTREMI: conf alta + stelle alte + quota bassa
    if conf >= 70 and stars >= 3.5 and quota < 1.60:
        groups[f"EXTREME: CONF>=70 + STARS>=3.5 + q<1.60 + {tipo}"].append(p)
    if conf >= 80 and stars >= 3.0:
        groups[f"EXTREME: CONF>=80 + STARS>=3 + {tipo}"].append(p)
    if conf >= 60 and stars >= 3.0 and 1.30 <= quota < 1.50:
        groups[f"EXTREME: CONF>=60 + STARS>=3 + q1.30-1.49 + {tipo}"].append(p)

    # 13. LEGA + TIPO
    league = p.get('_league', '')
    if league:
        groups[f"LEAGUE={league} + {tipo}"].append(p)

    # 14. DECISION field
    decision = p.get('decision', '')
    if decision:
        groups[f"DECISION={decision} + {tipo}"].append(p)
        if conf >= 70:
            groups[f"DECISION={decision} + {tipo} + CONF>=70"].append(p)

    # 15. MULTIGOL specifici
    if 'Multigol' in pron or 'MG' in pron:
        groups[f"MULTIGOL + {qlabel if qlo <= quota < qhi else 'other'}"].append(p)
        if source:
            groups[f"MULTIGOL + SRC={source}"].append(p)

print(f"OK ({len(groups)} gruppi)")

# Calcola HR e profit per ogni gruppo
print("Calcolo hit rate e profit per gruppo...", end=" ", flush=True)
results = []
results_profit = {}
for name, preds_list in groups.items():
    hr, n = calc_hr(preds_list)
    results.append((name, hr, n))
    results_profit[name] = calc_profit(preds_list)

print("OK")

# Stampa tutti i risultati
print("\nFiltro e stampa risultati...", flush=True)
print_results("PATTERN BIZZARRI — HR >= 75%, N >= 8", results, results_profit, min_n=8, min_hr=75)
print()
print_results("PATTERN BIZZARRI — HR >= 80%, N >= 5 (sample piccolo)", results, results_profit, min_n=5, min_hr=80)
print()
print_results("PATTERN BIZZARRI — HR >= 70%, N >= 15 (campione ampio)", results, results_profit, min_n=15, min_hr=70)

# TOP 30 assoluti per HR * sqrt(N) score
print(f"\n{'='*90}")
print(f"  TOP 30 — Score = HR * sqrt(N) — bilancia hit rate e volume")
print(f"  * = gia in produzione")
print(f"{'='*90}")
scored = []
for name, hr, n in results:
    if n >= 5 and hr >= 70:
        score = hr * (n ** 0.5)
        scored.append((name, hr, n, score))
scored.sort(key=lambda x: -x[3])
print(f"  {'#':>3} {'Pattern':<55} {'HR':>7} {'N':>5} {'Profit':>8} {'Score':>6} {'':>6}")
print(f"  {'-'*95}")
for i, (name, hr, n, score) in enumerate(scored[:30], 1):
    active = is_active_bizarre(name)
    tag = f"* {active}" if active else ""
    profit = results_profit.get(name, 0)
    print(f"  {i:>3}. {name:<55} {hr:>5.1f}%  {n:>4}  {profit:>+7.1f}  {score:>5.0f}  {tag}")

client.close()

print("\nSalvataggio report...", end=" ", flush=True)
# ========== SALVATAGGIO REPORT ==========
log_dir = os.path.join(base, '..', '_analisi_pattern')
os.makedirs(log_dir, exist_ok=True)

today_str = datetime.now().strftime('%Y-%m-%d')
suffix = f"_from_{from_date}" if from_date else ""
base_name = f"bizarre_pattern_report_{today_str}{suffix}"

# Raccogli tutti i risultati per il report
all_results = []
for name, hr, n in results:
    if n >= 5 and hr >= 65:
        all_results.append({'pattern': name, 'hr': hr, 'n': n})
all_results.sort(key=lambda x: (-x['hr'], -x['n']))

# --- TXT ---
lines = []
lines.append(f"{'='*70}")
lines.append(f"  REPORT ESPLORAZIONE PATTERN BIZZARRI")
lines.append(f"  Data report: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
lines.append(f"  Periodo: {'dal ' + from_date if from_date else 'storico completo'}")
lines.append(f"  Pronostici analizzati: {len(all_preds)}")
lines.append(f"{'='*70}\n")

def fmt_section(title, results_list, min_n, min_hr):
    sec = []
    sec.append(f"\n{'='*90}")
    sec.append(f"  {title}")
    sec.append(f"  * = gia in produzione")
    sec.append(f"{'='*90}")
    filtered = [(r['pattern'], r['hr'], r['n']) for r in results_list if r['n'] >= min_n and r['hr'] >= min_hr]
    filtered.sort(key=lambda x: (-x[1], -x[2]))
    if not filtered:
        sec.append("  Nessun pattern trovato con i criteri minimi")
    else:
        sec.append(f"  {'Pattern':<55} {'HR':>7} {'N':>5} {'Profit':>8} {'':>6}")
        sec.append(f"  {'-'*85}")
        for name, hr, n in filtered[:20]:
            active = is_active_bizarre(name)
            tag = f"* {active}" if active else ""
            profit = results_profit.get(name, 0)
            sec.append(f"  {name:<55} {hr:>5.1f}%  {n:>4}  {profit:>+7.1f}  {tag}")
    return sec

lines.extend(fmt_section("PATTERN BIZZARRI — HR >= 75%, N >= 8", all_results, 8, 75))
lines.extend(fmt_section("PATTERN BIZZARRI — HR >= 80%, N >= 5 (sample piccolo)", all_results, 5, 80))
lines.extend(fmt_section("PATTERN BIZZARRI — HR >= 70%, N >= 15 (campione ampio)", all_results, 15, 70))

# TOP 30 per score
lines.append(f"\n{'='*90}")
lines.append(f"  TOP 30 — Score = HR * sqrt(N) — bilancia hit rate e volume")
lines.append(f"  * = gia in produzione")
lines.append(f"{'='*90}")
scored_list = []
for r in all_results:
    if r['n'] >= 5 and r['hr'] >= 70:
        score = r['hr'] * (r['n'] ** 0.5)
        scored_list.append((r['pattern'], r['hr'], r['n'], score))
scored_list.sort(key=lambda x: -x[3])
lines.append(f"  {'#':>3} {'Pattern':<55} {'HR':>7} {'N':>5} {'Profit':>8} {'Score':>6} {'':>6}")
lines.append(f"  {'-'*95}")
for i, (name, hr, n, score) in enumerate(scored_list[:30], 1):
    active = is_active_bizarre(name)
    tag = f"* {active}" if active else ""
    profit = results_profit.get(name, 0)
    lines.append(f"  {i:>3}. {name:<55} {hr:>5.1f}%  {n:>4}  {profit:>+7.1f}  {score:>5.0f}  {tag}")

# CLASSIFICA COMPLETA HR >= 65%, N >= 10
lines.append(f"\n\n{'*'*90}")
lines.append(f" TUTTI I PATTERN HR >= 65%, N >= 10")
lines.append(f" * = pattern gia in produzione")
lines.append(f"{'*'*90}\n")
all_65 = [(r['pattern'], r['hr'], r['n']) for r in all_results if r['n'] >= 10 and r['hr'] >= 65]
all_65.sort(key=lambda x: (-x[1], -x[2]))
lines.append(f"{'Pattern':<60} {'HR':>7} {'N':>5} {'Profit':>8}")
lines.append(f"{'-'*85}")
for name, hr, n in all_65:
    active = is_active_bizarre(name)
    tag = f"  * {active}" if active else ""
    profit = results_profit.get(name, 0)
    lines.append(f"{name:<60} {hr:>5.1f}%  {n:>4}  {profit:>+7.1f}{tag}")

active_count = sum(1 for r in all_results if is_active_bizarre(r['pattern']))
new_count = len(all_results) - active_count
lines.append(f"\nTotale pattern HR>=65%: {len(all_65)} con N>=10 ({active_count} gia attivi *, {new_count} nuovi su totale {len(all_results)})")

txt_path = os.path.join(log_dir, f"{base_name}.txt")
with open(txt_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print(f"\nReport TXT salvato: {txt_path}")

# --- JSON ---
json_data = {
    'report_date': today_str,
    'from_date': from_date,
    'total_predictions': len(all_preds),
    'patterns_hr75_n8': [
        {'pattern': r['pattern'], 'hr': r['hr'], 'n': r['n'], 'active': is_active_bizarre(r['pattern'])}
        for r in all_results if r['n'] >= 8 and r['hr'] >= 75
    ],
    'patterns_hr80_n5': [
        {'pattern': r['pattern'], 'hr': r['hr'], 'n': r['n'], 'active': is_active_bizarre(r['pattern'])}
        for r in all_results if r['n'] >= 5 and r['hr'] >= 80
    ],
    'patterns_hr70_n15': [
        {'pattern': r['pattern'], 'hr': r['hr'], 'n': r['n'], 'active': is_active_bizarre(r['pattern'])}
        for r in all_results if r['n'] >= 15 and r['hr'] >= 70
    ],
    'top30_scored': [
        {'pattern': name, 'hr': hr, 'n': n, 'score': round(score, 1), 'active': is_active_bizarre(name)}
        for name, hr, n, score in scored_list[:30]
    ]
}

json_path = os.path.join(log_dir, f"{base_name}.json")
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(json_data, f, indent=2, ensure_ascii=False)
print("OK")
print(f"Report TXT: {txt_path}")
print(f"Report JSON: {json_path}")

print("\n=== FINE ESPLORAZIONE ===")
