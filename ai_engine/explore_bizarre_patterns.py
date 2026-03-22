"""
Esplorazione pattern bizzarri/creativi per trovare nuovi pattern Elite.
Cerca combinazioni insolite con HR alto.
"""

import os
import sys
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from pymongo import MongoClient

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
print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

# Carica tutti i pronostici con esito
docs = list(coll.find(
    {"pronostici.esito": {"$in": [True, False]}},
    {"pronostici": 1, "home": 1, "away": 1, "date": 1, "league": 1}
))

all_preds = []
for doc in docs:
    for p in doc.get('pronostici', []):
        if p.get('esito') in [True, False]:
            p['_league'] = doc.get('league', '')
            p['_date'] = doc.get('date', '')
            p['_home'] = doc.get('home', '')
            p['_away'] = doc.get('away', '')
            all_preds.append(p)

print(f"Totale pronostici con esito: {len(all_preds)}\n")

def calc_hr(preds_list):
    if not preds_list:
        return 0, 0
    hits = sum(1 for p in preds_list if p.get('esito') is True)
    return round(hits / len(preds_list) * 100, 1), len(preds_list)

def print_results(title, results, min_n=8, min_hr=75):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")
    filtered = [(name, hr, n) for name, hr, n in results if n >= min_n and hr >= min_hr]
    filtered.sort(key=lambda x: (-x[1], -x[2]))
    if not filtered:
        print("  Nessun pattern trovato con i criteri minimi")
        return
    for name, hr, n in filtered[:20]:
        bar = '#' * int(hr / 5)
        print(f"  {hr:5.1f}% (N={n:3d}) {bar} {name}")

# ============================================================
# 1. PATTERN ORARIO (ora del giorno della partita)
# ============================================================
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

# Calcola HR per ogni gruppo
results = []
for name, preds_list in groups.items():
    hr, n = calc_hr(preds_list)
    results.append((name, hr, n))

# Stampa tutti i risultati
print_results("PATTERN BIZZARRI — HR >= 75%, N >= 8", results, min_n=8, min_hr=75)
print()
print_results("PATTERN BIZZARRI — HR >= 80%, N >= 5 (sample piccolo)", results, min_n=5, min_hr=80)
print()
print_results("PATTERN BIZZARRI — HR >= 70%, N >= 15 (campione ampio)", results, min_n=15, min_hr=70)

# TOP 30 assoluti per HR * sqrt(N) score
print(f"\n{'='*70}")
print(f"  TOP 30 — Score = HR * sqrt(N) — bilancia hit rate e volume")
print(f"{'='*70}")
scored = []
for name, hr, n in results:
    if n >= 5 and hr >= 70:
        score = hr * (n ** 0.5)
        scored.append((name, hr, n, score))
scored.sort(key=lambda x: -x[3])
for i, (name, hr, n, score) in enumerate(scored[:30], 1):
    print(f"  {i:2d}. {hr:5.1f}% (N={n:3d}, score={score:.0f}) {name}")

client.close()
print("\n=== FINE ESPLORAZIONE ===")
