"""
BACKTEST SISTEMA C — Test pesi motore su partite storiche
==========================================================
Prende le ultime N partite da daily_predictions_engine_c (con risultato),
rilancia la simulazione MC con pesi custom, confronta con risultato reale.

Uso:
    python backtest_engine_c.py                    # 100 partite, pesi attuali
    python backtest_engine_c.py --n 500            # 500 partite
    python backtest_engine_c.py --config pesi.json  # pesi custom da file
"""
import os, sys, json, time, argparse, contextlib
from datetime import datetime
from collections import defaultdict
from tqdm import tqdm

current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

# Engine imports — IMPORTANTE: functions_python ha priorità su ai_engine locale
# perché i calculator in functions_python sono aggiornati (bulk_cache support)
FP_DIR = os.path.join(current_path, 'functions_python', 'ai_engine')
CALC_DIR = os.path.join(FP_DIR, 'calculators')
ENGINE_DIR = os.path.join(FP_DIR, 'engine')
# Inserisci functions_python PRIMA di tutto
sys.path.insert(0, CALC_DIR)
sys.path.insert(0, FP_DIR)
sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, current_path)

# HACK: forza Python a usare i calculator da functions_python/ (aggiornati con bulk_cache)
# altrimenti engine_core importa quelli vecchi da ai_engine/calculators/
import importlib, types
_fp_calc = os.path.join(current_path, 'functions_python', 'ai_engine', 'calculators')
_ai_calc_pkg = types.ModuleType('ai_engine.calculators')
_ai_calc_pkg.__path__ = [_fp_calc]
_ai_calc_pkg.__package__ = 'ai_engine.calculators'
sys.modules['ai_engine.calculators'] = _ai_calc_pkg

# Stessa cosa per ai_engine
_fp_ai = os.path.join(current_path, 'functions_python', 'ai_engine')
if 'ai_engine' not in sys.modules:
    _ai_pkg = types.ModuleType('ai_engine')
    _ai_pkg.__path__ = [_fp_ai]
    _ai_pkg.__package__ = 'ai_engine'
    sys.modules['ai_engine'] = _ai_pkg

from engine.engine_core import predict_match, preload_match_data, WEIGHTS_CACHE, build_weights_compartment
from engine.goals_converter import calculate_goals_from_engine, load_tuning
import bulk_manager_c

# Importa le funzioni di conversione dal Sistema C
# Salva stdout/stderr originali (il modulo li sovrascrive con TeeOutput)
_orig_stdout = sys.__stdout__
_orig_stderr = sys.__stderr__
from run_daily_predictions_engine_c import (
    convert_to_predictions, apply_kelly, run_monte_carlo,
    build_preloaded, suppress_stdout, SIMULATION_CYCLES, ALGO_MODE
)
# Ripristina stdout/stderr per avere la barra tqdm pulita
sys.stdout = _orig_stdout
sys.stderr = _orig_stderr

# ─── ARGOMENTI ───
parser = argparse.ArgumentParser()
parser.add_argument('--n', type=int, default=100, help='Numero partite')
parser.add_argument('--config', type=str, help='File JSON con pesi custom')
parser.add_argument('--cycles', type=int, default=SIMULATION_CYCLES, help='Cicli MC')
args = parser.parse_args()

N_PARTITE = args.n
MC_CYCLES = args.cycles

# ─── CARICA PESI CUSTOM (se forniti) ───
pesi_custom = None
if args.config:
    with open(args.config, 'r') as f:
        pesi_custom = json.load(f)
    print(f"✅ Pesi custom caricati da {args.config}")

# ─── APPLICA PESI CUSTOM AL MOTORE ───
def apply_custom_weights(pesi_dict):
    """Sovrascrive WEIGHTS_CACHE[6] (ALGO_C) con pesi custom."""
    W = WEIGHTS_CACHE[6]  # mode 6 = ALGO_C
    mapping = {
        "PESO_STORIA_H2H": "H2H",
        "PESO_MOTIVAZIONE": "MOTIVATION",
        "PESO_RATING_ROSA": "RATING",
        "PESO_VALORE_ROSA": "ROSA_VAL",
        "PESO_AFFIDABILITA": "RELIABILITY",
        "PESO_BVS_QUOTE": "BVS",
        "PESO_FATTORE_CAMPO": "FIELD",
        "PESO_FORMA_RECENTE": "LUCIFERO",
        "PESO_STREAK": "STREAK",
        "DIVISORE_MEDIA_GOL": "DIVISORE_GOL",
        "POTENZA_FAVORITA_WINSHIFT": "WINSHIFT",
        "IMPATTO_DIFESA_TATTICA": "IMPATTO_DIF",
        "TETTO_MAX_GOL_ATTESI": "MAX_GOL",
    }
    for db_key, engine_key in mapping.items():
        if db_key in pesi_dict:
            W[engine_key] = pesi_dict[db_key]
    print(f"  Pesi motore ALGO_C aggiornati in RAM")

if pesi_custom:
    apply_custom_weights(pesi_custom)

# ─── RECUPERA ULTIME N PARTITE CON RISULTATO ───
print(f"\n{'='*60}")
print(f"BACKTEST SISTEMA C — {N_PARTITE} partite, {MC_CYCLES} cicli MC")
print(f"{'='*60}\n")

print("Recupero partite con risultato...")

# Prendiamo le ultime N partite che hanno almeno un pronostico con esito
pipeline = [
    {"$match": {"pronostici.esito": {"$in": [True, False]}}},
    {"$sort": {"date": -1, "home": 1}},
    {"$limit": N_PARTITE},
]
partite_db = list(db['daily_predictions_engine_c'].aggregate(pipeline))
partite_db.reverse()  # ordine cronologico

print(f"Trovate {len(partite_db)} partite con risultato")

if not partite_db:
    print("❌ Nessuna partita trovata!")
    sys.exit(0)

# ─── RECUPERA RISULTATI REALI DA h2h_by_round ───
print("Recupero risultati reali da h2h_by_round...")

def get_real_result(home, away, date_str):
    """Cerca il risultato reale in h2h_by_round."""
    from datetime import timedelta
    target = datetime.strptime(date_str, '%Y-%m-%d')

    for delta in [0, 1, -1]:  # fallback ±1 giorno
        day = target + timedelta(days=delta)
        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        pipeline = [
            {"$unwind": "$matches"},
            {"$match": {
                "matches.home": home,
                "matches.away": away,
                "matches.date_obj": {"$gte": day_start, "$lt": day_end}
            }},
            {"$project": {"match": "$matches"}}
        ]

        results = list(db['h2h_by_round'].aggregate(pipeline))
        if results:
            m = results[0]['match']
            rs = m.get('real_score', '')
            if rs and ':' in rs:
                return rs
            # Prova anche result.home_score / away_score
            r = m.get('result', {})
            if isinstance(r, dict) and 'home_score' in r:
                return f"{r['home_score']}:{r['away_score']}"
    return None

# ─── VERIFICA ESITO PRONOSTICO ───
def check_pronostico(pronostico, tipo, real_score):
    """Verifica se un pronostico è corretto dato il risultato reale."""
    if not real_score or ':' not in real_score:
        return None

    parts = real_score.split(':')
    try:
        gh, ga = int(parts[0].strip()), int(parts[1].strip())
    except (ValueError, IndexError):
        return None

    total_goals = gh + ga

    if tipo == 'SEGNO':
        if pronostico == '1':
            return gh > ga
        elif pronostico == 'X':
            return gh == ga
        elif pronostico == '2':
            return gh < ga

    elif tipo == 'DOPPIA_CHANCE':
        if pronostico == '1X':
            return gh >= ga
        elif pronostico == 'X2':
            return gh <= ga
        elif pronostico == '12':
            return gh != ga

    elif tipo == 'GOL':
        if pronostico == 'Over 1.5':
            return total_goals > 1
        elif pronostico == 'Over 2.5':
            return total_goals > 2
        elif pronostico == 'Over 3.5':
            return total_goals > 3
        elif pronostico == 'Under 1.5':
            return total_goals <= 1
        elif pronostico == 'Under 2.5':
            return total_goals <= 2
        elif pronostico == 'Under 3.5':
            return total_goals <= 3
        elif pronostico == 'Goal':
            return gh > 0 and ga > 0
        elif pronostico == 'NoGoal':
            return gh == 0 or ga == 0

    elif tipo == 'RISULTATO_ESATTO':
        re_parts = pronostico.split(':')
        if len(re_parts) == 2:
            return int(re_parts[0]) == gh and int(re_parts[1]) == ga

    return None

# ─── BACKTEST PRINCIPALE ───
print(f"\nAvvio backtest su {len(partite_db)} partite...\n")

t_start = time.time()
results = {
    'totale': {'ok': 0, 'ko': 0, 'skip': 0, 'pl': 0.0},
    'SEGNO': {'ok': 0, 'ko': 0, 'pl': 0.0},
    'DOPPIA_CHANCE': {'ok': 0, 'ko': 0, 'pl': 0.0},
    'GOL': {'ok': 0, 'ko': 0, 'pl': 0.0},
    'RISULTATO_ESATTO': {'ok': 0, 'ko': 0, 'pl': 0.0},
}

# Raggruppa per lega per ottimizzare bulk_cache
from collections import OrderedDict
partite_per_lega = OrderedDict()
for p in partite_db:
    lg = p.get('league', 'Unknown')
    if lg not in partite_per_lega:
        partite_per_lega[lg] = []
    partite_per_lega[lg].append(p)

partite_processate = 0
partite_skip = 0

# Conta totale partite per la barra
total_partite = sum(len(lp) for lp in partite_per_lega.values())
pbar = tqdm(total=total_partite, desc="Backtest MC", unit="match",
            bar_format="{l_bar}{bar:30}{r_bar} | HR {postfix[0]} P/L {postfix[1]}",
            postfix=["0/0", "+0.0u"])

for league, league_partite in partite_per_lega.items():
    # Raccogli tutte le squadre della lega
    all_teams = set()
    for p in league_partite:
        all_teams.add(p.get('home', ''))
        all_teams.add(p.get('away', ''))
    all_teams = list(all_teams)

    # Carica cache lega UNA volta (silenzioso)
    try:
        with suppress_stdout():
            league_cache = bulk_manager_c.load_league_cache(all_teams, league)
    except Exception as e:
        print(f"\n  ⚠️ ERRORE league cache {league}: {e}")
        pbar.update(len(league_partite))
        partite_skip += len(league_partite)
        continue

    for p in league_partite:
        home = p.get('home', '')
        away = p.get('away', '')
        date_str = p.get('date', '')
        odds = p.get('odds', {})

        # Risultato reale
        real_score = get_real_result(home, away, date_str)
        if not real_score:
            partite_skip += 1
            pbar.update(1)
            continue

        # Build cache per match + MC + conversione (tutto silenzioso)
        try:
            with suppress_stdout():
                bulk_cache = bulk_manager_c.build_match_cache(league_cache, home, away)
                preloaded = build_preloaded(home, away, league, bulk_cache=bulk_cache)
        except Exception as e:
            if partite_processate == 0 and partite_skip < 3:
                print(f"\n  ⚠️ ERRORE build {home} vs {away}: {e}")
            partite_skip += 1
            pbar.update(1)
            continue

        if not preloaded:
            if partite_processate == 0 and partite_skip < 3:
                print(f"\n  ⚠️ Preloaded None per {home} vs {away} ({league})")
            partite_skip += 1
            pbar.update(1)
            continue

        try:
            with suppress_stdout():
                dist = run_monte_carlo(preloaded, home, away, cycles=MC_CYCLES)
        except Exception:
            partite_skip += 1
            pbar.update(1)
            continue
        if not dist:
            partite_skip += 1
            pbar.update(1)
            continue

        with suppress_stdout():
            pronostici = convert_to_predictions(dist, odds)
            apply_kelly(pronostici, dist, odds)

        # Verifica ogni pronostico (skip RE)
        for pron in pronostici:
            tipo = pron['tipo']
            if tipo == 'RISULTATO_ESATTO':
                continue
            valore = pron['pronostico']
            quota = pron.get('quota') or 0
            stake = pron.get('stake', 1)

            esito = check_pronostico(valore, tipo, real_score)
            if esito is None:
                continue

            if esito:
                pl = (quota - 1) * stake if quota > 0 else 0
                results[tipo]['ok'] += 1
                results[tipo]['pl'] += pl
                results['totale']['ok'] += 1
                results['totale']['pl'] += pl
            else:
                pl = -stake
                results[tipo]['ko'] += 1
                results[tipo]['pl'] += pl
                results['totale']['ko'] += 1
                results['totale']['pl'] += pl

        partite_processate += 1

        # Aggiorna barra
        tot_ok = results['totale']['ok']
        tot_ko = results['totale']['ko']
        tot_pl = results['totale']['pl']
        pbar.postfix[0] = f"{tot_ok}/{tot_ok+tot_ko}"
        pbar.postfix[1] = f"{tot_pl:+.1f}u"
        pbar.update(1)

pbar.close()

elapsed_total = time.time() - t_start

# ─── REPORT ───
print(f"\n{'='*60}")
print(f"RISULTATO BACKTEST — {partite_processate} partite in {elapsed_total:.1f}s")
print(f"Skip: {partite_skip} | Cicli MC: {MC_CYCLES}")
print(f"{'='*60}\n")

print(f"  {'Mercato':<18s} {'OK':>5s} {'KO':>5s} {'Tot':>5s} {'HR':>7s} {'P/L':>10s}")
print(f"  {'─'*55}")

for tipo in ['SEGNO', 'DOPPIA_CHANCE', 'GOL', 'RISULTATO_ESATTO']:
    d = results[tipo]
    tot = d['ok'] + d['ko']
    if tot == 0:
        continue
    hr = round(d['ok'] / tot * 100, 1)
    print(f"  {tipo:<18s} {d['ok']:>5d} {d['ko']:>5d} {tot:>5d} {hr:>6.1f}% {d['pl']:>+10.1f}")

d = results['totale']
tot = d['ok'] + d['ko']
hr = round(d['ok'] / tot * 100, 1) if tot > 0 else 0
print(f"  {'─'*55}")
print(f"  {'TOTALE':<18s} {d['ok']:>5d} {d['ko']:>5d} {tot:>5d} {hr:>6.1f}% {d['pl']:>+10.1f}")

# Salva risultati
out = {
    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "partite": partite_processate,
    "skip": partite_skip,
    "cicli_mc": MC_CYCLES,
    "pesi_custom": pesi_custom,
    "tempo_secondi": round(elapsed_total, 1),
    "risultati": results,
}

log_dir = os.path.join(current_path, 'log')
out_path = os.path.join(log_dir, 'backtest_engine_c_results.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(out, f, indent=2, ensure_ascii=False)
print(f"\n✅ Risultati salvati in {out_path}")
