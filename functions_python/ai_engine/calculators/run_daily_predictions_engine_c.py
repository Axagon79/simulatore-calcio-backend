"""
SISTEMA C — Pronostici dal Simulatore Monte Carlo
====================================================
Usa engine_core.py (algoritmo Master/Ensemble mode=5) per simulare
ogni partita N volte, raccoglie la distribuzione dei risultati,
e da quelli deriva SEGNO / GOL / DC.

Collection output: daily_predictions_engine_c
"""

import os
import sys
import json
import time
import contextlib
from datetime import datetime, timedelta
from collections import Counter

# ==================== TUNING ====================
SIMULATION_CYCLES = 100          # Cicli MC per partita
ALGO_MODE = 5                    # Master/Ensemble

# Soglie (da calibrare dopo i test — per ora emette tutto)
MIN_CONFIDENCE = 0               # 0 = emette tutto, calibrare dopo
COLLECTION_NAME = 'daily_predictions_engine_c'

# ==================== LOGGING ====================
class _TeeOutput:
    def __init__(self, log_path):
        self.terminal = sys.__stdout__
        self.log = open(log_path, 'w', encoding='utf-8')
    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)
    def flush(self):
        self.terminal.flush()
        self.log.flush()

_log_root = os.path.dirname(os.path.abspath(__file__))
while not os.path.isdir(os.path.join(_log_root, 'log')):
    _p = os.path.dirname(_log_root)
    if _p == _log_root:
        break
    _log_root = _p
_log_path = os.path.join(_log_root, 'log', 'pronostici-engine-c.txt')
sys.stdout = _TeeOutput(_log_path)
sys.stderr = sys.stdout
print(f"{'='*50}")
print(f"SISTEMA C — AVVIO: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
print(f"Cicli MC: {SIMULATION_CYCLES} | Algoritmo: Master (mode {ALGO_MODE})")
print(f"{'='*50}\n")

# ==================== PATH SETUP ====================
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

# Engine imports
ENGINE_DIR = os.path.join(current_path, 'engine')
sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, current_path)

from engine.engine_core import predict_match, preload_match_data
from engine.goals_converter import calculate_goals_from_engine, load_tuning
import ai_engine.calculators.bulk_manager as bulk_manager

# ==================== COLLECTIONS ====================
h2h_collection = db['h2h_by_round']
predictions_collection = db[COLLECTION_NAME]

# ==================== SUPPRESS STDOUT ====================
@contextlib.contextmanager
def suppress_stdout():
    with open(os.devnull, "w", encoding="utf-8") as devnull:
        old = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old

# ==================== HELPER ====================
def calculate_stars(score):
    """Stelle continue 2.5-5.0 da punteggio 0-100."""
    if score < 40:
        return 0.0
    stars = 2.5 + (score - 40) * (2.5 / 60)
    return round(min(5.0, stars), 1)


def get_today_range():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    return today, tomorrow


# ==================== FASE 1: RACCOLTA PARTITE ====================

def get_today_matches(target_date=None):
    """Recupera partite del giorno da h2h_by_round (solo campionati, no coppe)."""
    if target_date:
        today = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
    else:
        today, tomorrow = get_today_range()

    pipeline = [
        {"$unwind": "$matches"},
        {"$match": {"matches.date_obj": {"$gte": today, "$lt": tomorrow}}},
        {"$project": {
            "league": 1,
            "round_id": "$_id",
            "match": "$matches"
        }}
    ]

    matches = []
    for doc in h2h_collection.aggregate(pipeline):
        m = doc['match']
        m['_league'] = doc.get('league', 'Unknown')
        m['_round_id'] = doc.get('round_id')
        matches.append(m)

    print(f"📅 Trovate {len(matches)} partite per {today.strftime('%Y-%m-%d')}")
    return matches


# ==================== FASE 2: PONTE DATI ====================

def build_preloaded(home, away, league, bulk_cache=None):
    """
    Costruisce preloaded_data per engine_core usando bulk_cache.
    Wrapper di preload_match_data() — ritorna None se fallisce.
    """
    try:
        data = preload_match_data(home, away, league=league, bulk_cache=bulk_cache)
        return data
    except Exception as e:
        print(f"  ⚠️ Preload fallito per {home} vs {away}: {e}")
        return None


# ==================== FASE 3: MONTE CARLO ====================

def run_monte_carlo(preloaded_data, home, away, cycles=SIMULATION_CYCLES):
    """
    Esegue N cicli di simulazione Monte Carlo.
    Ogni ciclo: predict_match → goals_converter → risultato (gh, ga).
    Ritorna distribuzione completa.
    """
    settings_in_ram = load_tuning(ALGO_MODE)
    results = []
    valid = 0

    for i in range(cycles):
        with suppress_stdout():
            out = predict_match(home, away, mode=ALGO_MODE, preloaded_data=preloaded_data)
            if out is None or out[0] is None:
                continue
            s_h, s_a, r_h, r_a = out

            is_cup = preloaded_data.get('is_cup', False)
            goal_result = calculate_goals_from_engine(
                s_h, s_a, r_h, r_a,
                algo_mode=ALGO_MODE,
                home_name=home,
                away_name=away,
                settings_cache=settings_in_ram,
                debug_mode=False,
                is_cup=is_cup
            )
            gh, ga = int(goal_result[0]), int(goal_result[1])
            results.append((gh, ga))
            valid += 1

    if valid == 0:
        return None

    # Calcola distribuzione
    home_wins = sum(1 for g in results if g[0] > g[1])
    draws = sum(1 for g in results if g[0] == g[1])
    away_wins = sum(1 for g in results if g[0] < g[1])
    over_25 = sum(1 for g in results if g[0] + g[1] > 2)
    under_25 = sum(1 for g in results if g[0] + g[1] <= 2)
    gg = sum(1 for g in results if g[0] > 0 and g[1] > 0)
    ng = sum(1 for g in results if g[0] == 0 or g[1] == 0)

    n = len(results)
    scores = [f"{g[0]}-{g[1]}" for g in results]
    top_scores = Counter(scores).most_common(5)

    avg_gh = sum(g[0] for g in results) / n
    avg_ga = sum(g[1] for g in results) / n

    return {
        'home_win_pct': round(home_wins / n * 100, 1),
        'draw_pct': round(draws / n * 100, 1),
        'away_win_pct': round(away_wins / n * 100, 1),
        'over_25_pct': round(over_25 / n * 100, 1),
        'under_25_pct': round(under_25 / n * 100, 1),
        'gg_pct': round(gg / n * 100, 1),
        'ng_pct': round(ng / n * 100, 1),
        'avg_goals_home': round(avg_gh, 2),
        'avg_goals_away': round(avg_ga, 2),
        'total_avg_goals': round(avg_gh + avg_ga, 2),
        'top_scores': top_scores,
        'valid_cycles': valid,
        'predicted_score': top_scores[0][0] if top_scores else '0-0',
    }


# ==================== FASE 4: CONVERSIONE → PRONOSTICI ====================

def convert_to_predictions(dist, odds):
    """
    Converte distribuzione MC in pronostici SEGNO / GOL / DC.
    Per ora emette tutto (soglie a 0), da calibrare dopo.
    """
    pronostici = []

    # --- SEGNO ---
    home_pct = dist['home_win_pct']
    away_pct = dist['away_win_pct']
    draw_pct = dist['draw_pct']

    if home_pct > away_pct:
        fav_pct, fav_segno = home_pct, '1'
        q_fav = float(odds.get('1', 0) or 0)
    else:
        fav_pct, fav_segno = away_pct, '2'
        q_fav = float(odds.get('2', 0) or 0)

    if fav_pct >= MIN_CONFIDENCE:
        # DC se quota alta (>2.50) oppure confidence bassa
        if q_fav > 2.50 and fav_pct < 50:
            dc_map = {'1': '1X', '2': 'X2'}
            dc = dc_map.get(fav_segno, '1X')
            pronostici.append({
                'tipo': 'DOPPIA_CHANCE',
                'pronostico': dc,
                'confidence': round(fav_pct + draw_pct, 1),
                'stars': calculate_stars(fav_pct + draw_pct),
            })
        else:
            pronostici.append({
                'tipo': 'SEGNO',
                'pronostico': fav_segno,
                'confidence': round(fav_pct, 1),
                'stars': calculate_stars(fav_pct),
            })

    # --- GOL: Over/Under 2.5 ---
    if dist['over_25_pct'] >= dist['under_25_pct']:
        ou_pct = dist['over_25_pct']
        ou_pronostico = 'Over 2.5'
        ou_quota = float(odds.get('over_25', odds.get('Over 2.5', 0)) or 0)
    else:
        ou_pct = dist['under_25_pct']
        ou_pronostico = 'Under 2.5'
        ou_quota = float(odds.get('under_25', odds.get('Under 2.5', 0)) or 0)

    if ou_pct >= MIN_CONFIDENCE:
        pronostici.append({
            'tipo': 'GOL',
            'pronostico': ou_pronostico,
            'confidence': round(ou_pct, 1),
            'stars': calculate_stars(ou_pct),
        })

    # --- GOL: GG/NG ---
    if dist['gg_pct'] >= dist['ng_pct']:
        gg_pct = dist['gg_pct']
        gg_pronostico = 'Goal'
        gg_quota = float(odds.get('gg', odds.get('GG', 0)) or 0)
    else:
        gg_pct = dist['ng_pct']
        gg_pronostico = 'NoGoal'
        gg_quota = float(odds.get('ng', odds.get('NG', 0)) or 0)

    if gg_pct >= MIN_CONFIDENCE:
        pronostici.append({
            'tipo': 'GOL',
            'pronostico': gg_pronostico,
            'confidence': round(gg_pct, 1),
            'stars': calculate_stars(gg_pct),
        })

    # Assegna quote ai pronostici
    quota_map = {
        '1': odds.get('1'), 'X': odds.get('X'), '2': odds.get('2'),
        '1X': odds.get('1X'), 'X2': odds.get('X2'), '12': odds.get('12'),
        'Over 2.5': odds.get('over_25', odds.get('Over 2.5')),
        'Under 2.5': odds.get('under_25', odds.get('Under 2.5')),
        'Goal': odds.get('gg', odds.get('GG')),
        'NoGoal': odds.get('ng', odds.get('NG')),
    }
    for p in pronostici:
        q = quota_map.get(p['pronostico'])
        p['quota'] = float(q) if q else None

    return pronostici


# ==================== FASE 5: KELLY/STAKE ====================

def apply_kelly(pronostici, dist):
    """
    Per Sistema C, la probabilità MC è direttamente la probabilità reale.
    Non serve la formula a slope del Sistema A.
    """
    for p in pronostici:
        # La confidence MC è la probabilità stimata
        prob = p['confidence'] / 100
        quota = p.get('quota')
        tipo = p['tipo']

        if not quota or quota <= 1:
            p['probabilita_stimata'] = round(p['confidence'], 1)
            p['prob_mercato'] = 0
            p['prob_modello'] = round(p['confidence'], 1)
            p['has_odds'] = False
            p['stake'] = 1
            p['edge'] = 0
            continue

        p_market = (1.0 / quota) * 0.96
        edge = (prob * quota - 1) * 100

        if (prob * quota) <= 1:
            stake = 1
        else:
            full_kelly = (prob * quota - 1) / (quota - 1)
            quarter_kelly = full_kelly / 4
            stake = min(max(round(quarter_kelly * 100), 1), 10)

        # Protezioni
        if tipo == 'SEGNO':
            if quota < 1.30:
                stake = min(stake, 2)
            elif quota < 1.50:
                stake = min(stake, 4)
        if quota < 1.20:
            stake = min(stake, 2)
        if p['confidence'] > 85:
            stake = min(stake, 3)
        if quota > 5.0:
            stake = min(stake, 2)

        p['probabilita_stimata'] = round(prob * 100, 1)
        p['prob_mercato'] = round(p_market * 100, 1)
        p['prob_modello'] = round(prob * 100, 1)
        p['has_odds'] = True
        p['stake'] = stake
        p['edge'] = round(edge, 2)


# ==================== FASE 6: BUILD DOCUMENTO ====================

def build_document(match, pronostici, dist, target_str):
    """Costruisce documento nel formato identico a daily_predictions."""
    home = match.get('home', match.get('home_team', ''))
    away = match.get('away', match.get('away_team', ''))
    league = match.get('_league', 'Unknown')
    odds = match.get('odds', {})

    # Decisione
    tipi = [p['tipo'] for p in pronostici]
    has_segno = 'SEGNO' in tipi or 'DOPPIA_CHANCE' in tipi
    has_gol = 'GOL' in tipi
    if has_segno and has_gol:
        decision = 'SEGNO+GOL'
    elif has_segno:
        decision = 'SEGNO'
    elif has_gol:
        decision = 'GOL'
    else:
        decision = 'SCARTA'

    # Confidence per tipo
    segno_p = [p for p in pronostici if p['tipo'] in ('SEGNO', 'DOPPIA_CHANCE')]
    gol_p = [p for p in pronostici if p['tipo'] == 'GOL']
    conf_segno = segno_p[0]['confidence'] if segno_p else 0
    conf_gol = max((p['confidence'] for p in gol_p), default=0)
    stars_segno = segno_p[0]['stars'] if segno_p else 0
    stars_gol = max((p['stars'] for p in gol_p), default=0)

    # Commento auto
    score = dist['predicted_score']
    comment = f"Simulazione MC ({dist['valid_cycles']} cicli): score più frequente {score}"

    doc = {
        'date': target_str,
        'home': home,
        'away': away,
        'league': league,
        'match_time': match.get('match_time', match.get('time', '')),
        'home_mongo_id': str(match.get('home_mongo_id', '')),
        'away_mongo_id': str(match.get('away_mongo_id', '')),
        'is_cup': False,
        'decision': decision,
        'pronostici': pronostici,
        'confidence_segno': conf_segno,
        'confidence_gol': conf_gol,
        'stars_segno': stars_segno,
        'stars_gol': stars_gol,
        'comment': comment,
        'odds': odds,
        'source': 'engine_c',
        'simulation_data': {
            'cycles': dist['valid_cycles'],
            'home_win_pct': dist['home_win_pct'],
            'draw_pct': dist['draw_pct'],
            'away_win_pct': dist['away_win_pct'],
            'over_25_pct': dist['over_25_pct'],
            'under_25_pct': dist['under_25_pct'],
            'gg_pct': dist['gg_pct'],
            'ng_pct': dist['ng_pct'],
            'avg_goals_home': dist['avg_goals_home'],
            'avg_goals_away': dist['avg_goals_away'],
            'predicted_score': dist['predicted_score'],
            'top_scores': dist['top_scores'],
        },
        'created_at': datetime.now(),
    }
    return doc


# ==================== FASE 7: MAIN ====================

def run_engine_c(target_date=None):
    """Entry point principale Sistema C."""
    t_start = time.time()

    if target_date:
        target_str = target_date.strftime('%Y-%m-%d')
    else:
        target_str = datetime.now().strftime('%Y-%m-%d')
        target_date = datetime.now()

    print(f"\n🚀 SISTEMA C — Generazione pronostici per {target_str}")
    print(f"   Cicli: {SIMULATION_CYCLES} | Algo: Master (mode {ALGO_MODE})\n")

    # 1. Raccolta partite
    matches = get_today_matches(target_date)
    if not matches:
        print("❌ Nessuna partita trovata.")
        return

    # 2. Raggruppa per lega → bulk_cache per lega
    leagues = {}
    for m in matches:
        lg = m.get('_league', 'Unknown')
        if lg not in leagues:
            leagues[lg] = []
        leagues[lg].append(m)

    documents = []
    skipped = 0
    total = len(matches)

    for league, league_matches in leagues.items():
        print(f"\n📂 {league} ({len(league_matches)} partite)")

        for m in league_matches:
            home = m.get('home', m.get('home_team', ''))
            away = m.get('away', m.get('away_team', ''))
            t_match = time.time()

            # Carica bulk_cache per ogni partita (ogni coppia di squadre)
            try:
                with suppress_stdout():
                    bulk_cache = bulk_manager.get_all_data_bulk(home, away, league)
            except Exception as e:
                print(f"  ⏭️ Skip (bulk fallito): {home} vs {away} — {e}")
                skipped += 1
                continue

            # Ponte dati — chiamo preload_match_data direttamente per catturare errori
            preload_error = None
            with suppress_stdout():
                try:
                    preloaded = preload_match_data(home, away, league=league, bulk_cache=bulk_cache)
                except Exception as e:
                    preloaded = None
                    preload_error = str(e)
            if not preloaded:
                err_msg = f" — {preload_error}" if preload_error else ""
                print(f"  ⏭️ Skip (preload fallito): {home} vs {away}{err_msg}")
                skipped += 1
                continue

            # Monte Carlo
            dist = run_monte_carlo(preloaded, home, away)
            if not dist:
                print(f"  ⚠️ MC fallito: {home} vs {away}")
                skipped += 1
                continue

            # Conversione → pronostici
            odds = m.get('odds', {})
            pronostici = convert_to_predictions(dist, odds)

            # Kelly/Stake
            apply_kelly(pronostici, dist)

            # Build documento
            doc = build_document(m, pronostici, dist, target_str)
            documents.append(doc)

            # Log
            elapsed = time.time() - t_match
            segno_str = next((p['pronostico'] for p in pronostici if p['tipo'] in ('SEGNO', 'DOPPIA_CHANCE')), '-')
            gol_str = ', '.join(p['pronostico'] for p in pronostici if p['tipo'] == 'GOL') or '-'
            print(f"  ✅ {home} vs {away} | {dist['predicted_score']} | "
                  f"1:{dist['home_win_pct']}% X:{dist['draw_pct']}% 2:{dist['away_win_pct']}% | "
                  f"SEGNO={segno_str} GOL={gol_str} | {elapsed:.1f}s")

    # 3. Salva in DB
    if documents:
        # Rimuovi vecchi pronostici per la stessa data
        deleted = predictions_collection.delete_many({'date': target_str})
        if deleted.deleted_count > 0:
            print(f"\n🗑️ Rimossi {deleted.deleted_count} pronostici precedenti per {target_str}")

        predictions_collection.insert_many(documents)
        print(f"\n💾 Salvati {len(documents)} pronostici in '{COLLECTION_NAME}'")
    else:
        print("\n⚠️ Nessun pronostico generato.")

    # 4. Riepilogo
    elapsed_total = time.time() - t_start
    print(f"\n{'='*50}")
    print(f"RIEPILOGO SISTEMA C — {target_str}")
    print(f"  Partite totali: {total}")
    print(f"  Pronostici generati: {len(documents)}")
    print(f"  Skippate: {skipped}")
    print(f"  Tempo totale: {elapsed_total:.1f}s")
    print(f"{'='*50}")

    return documents


# ==================== MAIN ====================
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Sistema C — Pronostici Monte Carlo')
    parser.add_argument('--date', type=str, help='Data target YYYY-MM-DD (default: oggi)')
    parser.add_argument('--cycles', type=int, default=SIMULATION_CYCLES, help='Cicli MC per partita')
    args = parser.parse_args()

    if args.cycles != SIMULATION_CYCLES:
        SIMULATION_CYCLES = args.cycles
        print(f"⚙️ Cicli MC override: {SIMULATION_CYCLES}")

    if args.date:
        target = datetime.strptime(args.date, '%Y-%m-%d')
        run_engine_c(target)
    else:
        for i in range(7):  # 0=oggi, 1=domani, 2=dopodomani, ... 6=tra 6 giorni
            target = datetime.now() + timedelta(days=i)
            print("\n" + "=" * 70)
            print(f"📅 ELABORAZIONE: {target.strftime('%Y-%m-%d')}")
            print("=" * 70)
            run_engine_c(target)
