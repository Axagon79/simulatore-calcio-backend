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
ALGO_MODE = 6                    # Master/Ensemble

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

    # Over/Under per tutte le linee (1.5, 2.5, 3.5)
    over_15 = sum(1 for g in results if g[0] + g[1] > 1)
    under_15 = sum(1 for g in results if g[0] + g[1] <= 1)
    over_25 = sum(1 for g in results if g[0] + g[1] > 2)
    under_25 = sum(1 for g in results if g[0] + g[1] <= 2)
    over_35 = sum(1 for g in results if g[0] + g[1] > 3)
    under_35 = sum(1 for g in results if g[0] + g[1] <= 3)

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
        'over_15_pct': round(over_15 / n * 100, 1),
        'under_15_pct': round(under_15 / n * 100, 1),
        'over_25_pct': round(over_25 / n * 100, 1),
        'under_25_pct': round(under_25 / n * 100, 1),
        'over_35_pct': round(over_35 / n * 100, 1),
        'under_35_pct': round(under_35 / n * 100, 1),
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
# Riscrittura completa: 18 regole derivate da analisi caso-per-caso (2026-02-18)

SOGLIA_QUOTA_MIN = 1.30  # Sotto questa quota, NON emettere il pronostico


def _get_quota(odds, key, fallback_key=None):
    """Getter sicuro per le quote."""
    val = odds.get(key) or (odds.get(fallback_key) if fallback_key else None)
    try:
        return float(val) if val else 0.0
    except (ValueError, TypeError):
        return 0.0


def calcola_re_direzione(top_scores, valid_cycles):
    """
    Regola 3: somma % dei top RE raggruppati per casa/pari/ospite e GG/NG.
    """
    casa_count = pari_count = ospite_count = 0
    gg_count = ng_count = 0
    n = valid_cycles if valid_cycles > 0 else 1

    for score_str, count in top_scores:
        gh, ga = int(score_str.split('-')[0]), int(score_str.split('-')[1])
        if gh > ga:
            casa_count += count
        elif gh == ga:
            pari_count += count
        else:
            ospite_count += count
        if gh > 0 and ga > 0:
            gg_count += count
        else:
            ng_count += count

    return {
        'casa': round(casa_count / n * 100, 1),
        'pari': round(pari_count / n * 100, 1),
        'ospite': round(ospite_count / n * 100, 1),
        'gg': round(gg_count / n * 100, 1),
        'ng': round(ng_count / n * 100, 1),
    }


def identifica_favorita(dist):
    """Ritorna (lato, percentuale). Lato: 'casa', 'ospite' o 'pari'."""
    home, draw, away = dist['home_win_pct'], dist['draw_pct'], dist['away_win_pct']
    if home >= away and home >= draw:
        return 'casa', home
    elif away >= home and away >= draw:
        return 'ospite', away
    return 'pari', draw


def _is_piatta(dist):
    """Distribuzione piatta: tutti < 40% e differenza max < 8%."""
    vals = [dist['home_win_pct'], dist['draw_pct'], dist['away_win_pct']]
    return max(vals) < 40 and (max(vals) - min(vals)) < 8


def _get_book_second_fav(odds):
    """Ritorna il 2° segno piu' probabile per il bookmaker (quota piu' bassa dopo il favorito)."""
    pairs = [('1', _get_quota(odds, '1')), ('X', _get_quota(odds, 'X')), ('2', _get_quota(odds, '2'))]
    valid = [(s, q) for s, q in pairs if q > 0]
    valid.sort(key=lambda x: x[1])
    return valid[1][0] if len(valid) >= 2 else None


def _segno_in_dc(segno, dc_label):
    """Controlla se un segno e' contenuto nella DC."""
    dc_map = {'1X': ['1', 'X'], 'X2': ['X', '2'], '12': ['1', '2']}
    return segno in dc_map.get(dc_label, [])


def _calcola_re_gol_medi(top_scores, valid_cycles):
    """Calcola gol medi attesi dai RE top."""
    total_gol = total_count = 0
    for score_str, count in top_scores:
        gh, ga = int(score_str.split('-')[0]), int(score_str.split('-')[1])
        total_gol += (gh + ga) * count
        total_count += count
    return total_gol / total_count if total_count > 0 else 2.0


# ---------- SEGNO / DC (Regole 1-7) ----------

def decidi_segno_dc(dist, odds, re_dir):
    """Albero decisionale SEGNO/DC. Ritorna dict pronostico oppure None."""
    home_pct = dist['home_win_pct']
    draw_pct = dist['draw_pct']
    away_pct = dist['away_win_pct']

    # Identifica favorita tra casa e ospite
    if home_pct >= away_pct:
        fav_pct, fav_segno, fav_side = home_pct, '1', 'casa'
        dc_label = '1X'
        dc_pct = home_pct + draw_pct
    else:
        fav_pct, fav_segno, fav_side = away_pct, '2', 'ospite'
        dc_label = 'X2'
        dc_pct = away_pct + draw_pct

    # Regola 5: Pareggio e' favorito (X > 1 e X > 2)
    if draw_pct > home_pct and draw_pct > away_pct:
        if home_pct >= away_pct:
            dc_l, dc_p = '1X', draw_pct + home_pct
        else:
            dc_l, dc_p = 'X2', draw_pct + away_pct
        q_dc = _get_quota(odds, dc_l)
        if q_dc < SOGLIA_QUOTA_MIN:
            return None
        return {
            'tipo': 'DOPPIA_CHANCE', 'pronostico': dc_l,
            'confidence': round(dc_p, 1), 'stars': calculate_stars(dc_p),
            '_stake_hint': 'medio',
        }

    # Regola 7 (piatta): distribuzione piatta → SKIP salvo RE forte
    if _is_piatta(dist):
        re_max = max(re_dir['casa'], re_dir['ospite'], re_dir['pari'])
        if re_max >= 25:
            if re_dir['casa'] == re_max:
                dc_l, dc_p = '1X', home_pct + draw_pct
            elif re_dir['ospite'] == re_max:
                dc_l, dc_p = 'X2', away_pct + draw_pct
            else:
                dc_l, dc_p = ('1X', draw_pct + home_pct) if home_pct >= away_pct else ('X2', draw_pct + away_pct)
            if _get_quota(odds, dc_l) >= SOGLIA_QUOTA_MIN:
                return {
                    'tipo': 'DOPPIA_CHANCE', 'pronostico': dc_l,
                    'confidence': round(dc_p, 1), 'stars': calculate_stars(dc_p),
                    '_stake_hint': 'basso',
                }
        return None

    q_fav = _get_quota(odds, fav_segno)
    q_dc = _get_quota(odds, dc_label)

    # Regola 1: Quota minima — se entrambe sotto soglia → SKIP
    if q_fav < SOGLIA_QUOTA_MIN and q_dc < SOGLIA_QUOTA_MIN:
        return None

    # RE confermano la favorita?
    re_fav = re_dir[fav_side]
    re_pari = re_dir['pari']
    re_opp = re_dir['ospite'] if fav_side == 'casa' else re_dir['casa']
    re_confermano = re_fav >= re_pari and re_fav >= re_opp

    # Regola 7: Favorita schiacciante (>= 70%)
    if fav_pct >= 70:
        if q_fav >= SOGLIA_QUOTA_MIN:
            return {
                'tipo': 'SEGNO', 'pronostico': fav_segno,
                'confidence': round(fav_pct, 1), 'stars': calculate_stars(fav_pct),
                '_stake_hint': 'alto',
            }
        return None

    # Ramo 2: favorita >= 62%
    if fav_pct >= 62:
        if q_fav >= SOGLIA_QUOTA_MIN:
            return {
                'tipo': 'SEGNO', 'pronostico': fav_segno,
                'confidence': round(fav_pct, 1), 'stars': calculate_stars(fav_pct),
                '_stake_hint': 'alto' if re_confermano else 'medio',
            }
        return None

    # Ramo 3: favorita 55-62%
    if fav_pct >= 55:
        if re_confermano and q_fav >= SOGLIA_QUOTA_MIN:
            return {
                'tipo': 'SEGNO', 'pronostico': fav_segno,
                'confidence': round(fav_pct, 1), 'stars': calculate_stars(fav_pct),
                '_stake_hint': 'medio',
            }
        if q_dc >= SOGLIA_QUOTA_MIN:
            return {
                'tipo': 'DOPPIA_CHANCE', 'pronostico': dc_label,
                'confidence': round(dc_pct, 1), 'stars': calculate_stars(dc_pct),
                '_stake_hint': 'medio-basso',
            }
        if q_fav >= SOGLIA_QUOTA_MIN:
            return {
                'tipo': 'SEGNO', 'pronostico': fav_segno,
                'confidence': round(fav_pct, 1), 'stars': calculate_stars(fav_pct),
                '_stake_hint': 'medio-basso',
            }
        return None

    # Ramo 4: favorita 50-55%
    if fav_pct >= 50:
        if q_fav >= SOGLIA_QUOTA_MIN:
            return {
                'tipo': 'SEGNO', 'pronostico': fav_segno,
                'confidence': round(fav_pct, 1), 'stars': calculate_stars(fav_pct),
                '_stake_hint': 'medio-basso' if re_confermano else 'basso',
            }
        if q_dc >= SOGLIA_QUOTA_MIN:
            return {
                'tipo': 'DOPPIA_CHANCE', 'pronostico': dc_label,
                'confidence': round(dc_pct, 1), 'stars': calculate_stars(dc_pct),
                '_stake_hint': 'basso',
            }
        return None

    # Ramo 5: favorita 40-50%
    if fav_pct >= 40:
        if re_confermano:
            if q_dc >= SOGLIA_QUOTA_MIN:
                hint = 'medio-basso'
                book_second = _get_book_second_fav(odds)
                if book_second and not _segno_in_dc(book_second, dc_label):
                    hint = 'basso'
                return {
                    'tipo': 'DOPPIA_CHANCE', 'pronostico': dc_label,
                    'confidence': round(dc_pct, 1), 'stars': calculate_stars(dc_pct),
                    '_stake_hint': hint,
                }
            if q_fav >= SOGLIA_QUOTA_MIN:
                return {
                    'tipo': 'SEGNO', 'pronostico': fav_segno,
                    'confidence': round(fav_pct, 1), 'stars': calculate_stars(fav_pct),
                    '_stake_hint': 'basso',
                }
        elif re_pari > re_fav:
            if q_dc >= SOGLIA_QUOTA_MIN:
                return {
                    'tipo': 'DOPPIA_CHANCE', 'pronostico': dc_label,
                    'confidence': round(dc_pct, 1), 'stars': calculate_stars(dc_pct),
                    '_stake_hint': 'basso',
                }
        elif re_opp > re_fav:
            q_12 = _get_quota(odds, '12')
            if q_12 >= SOGLIA_QUOTA_MIN:
                return {
                    'tipo': 'DOPPIA_CHANCE', 'pronostico': '12',
                    'confidence': round(home_pct + away_pct, 1),
                    'stars': calculate_stars(home_pct + away_pct),
                    '_stake_hint': 'basso',
                }
        return None

    # Ramo 6: favorita < 40%
    re_max = max(re_dir['casa'], re_dir['ospite'], re_dir['pari'])
    re_min = min(re_dir['casa'], re_dir['ospite'], re_dir['pari'])
    if (re_max - re_min) >= 10:
        if re_dir['casa'] == re_max or re_dir['pari'] == re_max:
            dc_l, dc_p = '1X', home_pct + draw_pct
        else:
            dc_l, dc_p = 'X2', away_pct + draw_pct
        if _get_quota(odds, dc_l) >= SOGLIA_QUOTA_MIN:
            return {
                'tipo': 'DOPPIA_CHANCE', 'pronostico': dc_l,
                'confidence': round(dc_p, 1), 'stars': calculate_stars(dc_p),
                '_stake_hint': 'basso',
            }
    return None


# ---------- OVER / UNDER (Regole 8-12 + Regola 19: Fascia a Campana Under) ----------

# Over: logica classica con soglia
SOGLIA_SEVERA_OVER = 60    # Over: emissione diretta se MC% >= 60%
SOGLIA_MINIMA_OVER = 55    # Over: sotto 55% → eliminato

# Under: fascia a campana (sweet spot 55-75%, paradosso confidence invertita)
# MC sottostima gol → confidence alta Under = sbaglia di piu
UNDER_ELIMINA = 45         # < 45% → eliminato
UNDER_DECLASSA_BASSO = 55  # 45-55% → declassamento
UNDER_SWEET_MAX = 75       # 55-75% → emissione diretta (72.2% HR)
                           # > 75% → declassamento (50% HR)

# Mappa declassamento: linea originale → linea piu sicura
_DOWNGRADE_MAP = {
    ('Over', '3.5'): '2.5',   # Over 3.5 → Over 2.5
    ('Over', '2.5'): '1.5',   # Over 2.5 → Over 1.5
    ('Under', '2.5'): '3.5',  # Under 2.5 → Under 3.5
    # Under 1.5: ELIMINATO (33% HR, non declassabile)
    # Over 1.5 / Under 3.5: non hanno linea adiacente → eliminati
}


def decidi_over_under(dist, odds, re_dir, fav_pct):
    """Regole 8-12 + Regola 19 (Fascia a Campana Under): O/U."""
    if _is_piatta(dist):
        return []  # Regola 9: 1X2 piatta → O/U inaffidabile

    re_avg_gol = _calcola_re_gol_medi(dist['top_scores'], dist['valid_cycles'])
    _, fav_pct_actual = identifica_favorita(dist)

    # Mappa MC% e quote per tutte le linee (per declassamento)
    mc_map = {
        ('Over', '1.5'): dist['over_15_pct'],
        ('Over', '2.5'): dist['over_25_pct'],
        ('Over', '3.5'): dist['over_35_pct'],
        ('Under', '2.5'): dist['under_25_pct'],
        ('Under', '3.5'): dist['under_35_pct'],
    }
    quota_map = {
        ('Over', '1.5'): _get_quota(odds, 'over_15', 'Over 1.5'),
        ('Over', '2.5'): _get_quota(odds, 'over_25', 'Over 2.5'),
        ('Over', '3.5'): _get_quota(odds, 'over_35', 'Over 3.5'),
        ('Under', '2.5'): _get_quota(odds, 'under_25', 'Under 2.5'),
        ('Under', '3.5'): _get_quota(odds, 'under_35', 'Under 3.5'),
    }

    pronostici = []
    emitted_keys = set()
    to_downgrade = []

    lines = [
        ('1.5', dist['over_15_pct'], dist['under_15_pct'],
         _get_quota(odds, 'over_15', 'Over 1.5'), _get_quota(odds, 'under_15', 'Under 1.5')),
        ('2.5', dist['over_25_pct'], dist['under_25_pct'],
         quota_map[('Over', '2.5')], quota_map[('Under', '2.5')]),
        ('3.5', dist['over_35_pct'], dist['under_35_pct'],
         quota_map[('Over', '3.5')], quota_map[('Under', '3.5')]),
    ]

    # --- PASS 1: Emissione diretta ---
    for line, over_pct, under_pct, q_over, q_under in lines:
        line_val = float(line)

        # ===== OVER (logica classica: soglia 60%) =====
        mc_pct, quota = over_pct, q_over
        if mc_pct >= SOGLIA_MINIMA_OVER and quota >= SOGLIA_QUOTA_MIN:
            downgraded = False

            # Regola 10: RE vincono sulla distribuzione quando margine basso
            if mc_pct < 62 and re_avg_gol <= line_val:
                to_downgrade.append(('Over', line, mc_pct))
                downgraded = True

            # Regola 11: Value
            if not downgraded:
                p_implied = 1.0 / quota if quota > 0 else 1.0
                if mc_pct / 100 - p_implied < 0.05 and mc_pct < 70:
                    to_downgrade.append(('Over', line, mc_pct))
                    downgraded = True

            # Regola 9: favorita debole
            if not downgraded and fav_pct_actual < 50 and mc_pct < 65:
                to_downgrade.append(('Over', line, mc_pct))
                downgraded = True

            if not downgraded:
                if mc_pct >= SOGLIA_SEVERA_OVER:
                    pronostici.append({
                        'tipo': 'GOL',
                        'pronostico': f'Over {line}',
                        'confidence': round(mc_pct, 1),
                        'stars': calculate_stars(mc_pct),
                    })
                    emitted_keys.add(('Over', line))
                else:
                    to_downgrade.append(('Over', line, mc_pct))

        # ===== UNDER (fascia a campana: 55-75% sweet spot) =====
        mc_pct, quota = under_pct, q_under

        # Under 1.5: ELIMINATO SEMPRE (33% HR)
        if line == '1.5':
            continue

        if mc_pct < UNDER_ELIMINA:
            continue  # < 45% → eliminato

        if quota < SOGLIA_QUOTA_MIN:
            continue

        # Regola 10: RE vincono → ELIMINA Under (no declassamento)
        if mc_pct < 62 and re_avg_gol > line_val + 0.5:
            continue

        # Regola 11: Value → ELIMINA Under (no declassamento)
        p_implied = 1.0 / quota if quota > 0 else 1.0
        if mc_pct / 100 - p_implied < 0.05 and mc_pct < 70:
            continue

        # Regola 9: favorita debole → ELIMINA Under (no declassamento)
        if fav_pct_actual < 50 and mc_pct < 65:
            continue

        # Fascia a campana: 55-75% = sweet spot
        if UNDER_DECLASSA_BASSO <= mc_pct <= UNDER_SWEET_MAX:
            # Sweet spot → emissione diretta
            pronostici.append({
                'tipo': 'GOL',
                'pronostico': f'Under {line}',
                'confidence': round(mc_pct, 1),
                'stars': calculate_stars(mc_pct),
            })
            emitted_keys.add(('Under', line))
        elif mc_pct > UNDER_SWEET_MAX:
            # > 75% → declassamento (confidence invertita, ma declassati da alta hanno 75% HR)
            to_downgrade.append(('Under', line, mc_pct))
        # 45-55%: eliminato (no declassamento, non aggiunge valore)

    # --- PASS 2: Declassamento (linea piu sicura) ---
    for direction, orig_line, orig_mc_pct in to_downgrade:
        downgrade_line = _DOWNGRADE_MAP.get((direction, orig_line))
        if not downgrade_line:
            continue  # Nessuna linea adiacente

        dest_key = (direction, downgrade_line)
        if dest_key in emitted_keys:
            continue  # Linea gia emessa nel pass 1

        dest_quota = quota_map.get(dest_key, 0)
        if dest_quota < SOGLIA_QUOTA_MIN:
            continue

        dest_mc = mc_map.get(dest_key, 0)
        if dest_mc < UNDER_ELIMINA if direction == 'Under' else dest_mc < SOGLIA_MINIMA_OVER:
            continue

        pronostici.append({
            'tipo': 'GOL',
            'pronostico': f'{direction} {downgrade_line}',
            'confidence': round(dest_mc, 1),
            'stars': calculate_stars(dest_mc),
            '_downgraded_from': f'{direction} {orig_line}',
        })
        emitted_keys.add(dest_key)

    return pronostici


# ---------- GG / NG (Regole 13-16) ----------

def decidi_gg_ng(dist, odds, re_dir, fav_pct, ou_preds):
    """Regole 13-16: GG/NG. Ritorna dict pronostico oppure None."""
    if _is_piatta(dist):
        return None  # Regola 9: 1X2 piatta → inaffidabile

    gg_pct, ng_pct = dist['gg_pct'], dist['ng_pct']
    q_gg = _get_quota(odds, 'gg', 'GG')
    q_ng = _get_quota(odds, 'ng', 'NG')

    # Regola 16: bookmaker come validazione
    book_says_gg = q_gg > 0 and q_ng > 0 and q_gg < q_ng
    book_says_ng = q_gg > 0 and q_ng > 0 and q_ng < q_gg

    # Decidi direzione
    if gg_pct > ng_pct:
        best_pct, best_pron, best_q = gg_pct, 'Goal', q_gg
        re_support, book_confirms = re_dir['gg'], book_says_gg
    else:
        best_pct, best_pron, best_q = ng_pct, 'NoGoal', q_ng
        re_support, book_confirms = re_dir['ng'], book_says_ng

    if best_q < SOGLIA_QUOTA_MIN:
        return None  # Regola 1

    # Regola 13: Soglia flessibile — base 50%, abbassata se RE+book concordano
    soglia = 50
    if re_support >= 20 and book_confirms:
        soglia = 45

    if best_pct < soglia:
        return None

    # Regola 16: book contradice + MC non forte → cautela
    if not book_confirms and best_pct < 58:
        return None

    # Regola 11: Value
    p_implied = 1.0 / best_q if best_q > 0 else 1.0
    if (best_pct / 100) - p_implied < 0.03 and best_pct < 65:
        return None

    # Regola 15: Conflitto Over+NG / Under+GG
    has_over = any('Over' in p['pronostico'] for p in ou_preds)
    has_under = any('Under' in p['pronostico'] for p in ou_preds)
    conflitto = (has_over and best_pron == 'NoGoal') or (has_under and best_pron == 'Goal')

    return {
        'tipo': 'GOL', 'pronostico': best_pron,
        'confidence': round(best_pct, 1), 'stars': calculate_stars(best_pct),
        '_stake_hint': 'basso' if conflitto else 'medio',
        '_conflitto': conflitto,
    }


# ---------- RISULTATO ESATTO (Regole 17-18) ----------

def riordina_re(top_scores, valid_cycles, fav_pct, fav_side, segno_pred, ggng_pred):
    """Regole 17-18: Top 3 RE riordinati per contesto partita."""
    if not top_scores:
        return []

    n = valid_cycles if valid_cycles > 0 else 1
    scored = []

    for score_str, count in top_scores:
        gh, ga = int(score_str.split('-')[0]), int(score_str.split('-')[1])
        re_pct = round(count / n * 100, 1)
        if re_pct < 5:
            continue
        bonus = 0

        # Regola 18A: Favorita forte (55%+) → promuovi RE con 2+ gol favorita
        if fav_pct >= 55:
            fav_goals = gh if fav_side == 'casa' else ga
            if fav_goals >= 2:
                bonus += 3
            elif fav_goals <= 1:
                bonus -= 2  # Demoti 1-0 / 0-1

        # Regola 18B: Partita equilibrata
        if fav_pct < 55:
            if ggng_pred and ggng_pred.get('pronostico') == 'Goal':
                if gh == 0 or ga == 0:
                    bonus -= 1  # Demoti NG scores se GG emesso
                if gh > 0 and ga > 0:
                    bonus += 1
            if ggng_pred and ggng_pred.get('pronostico') == 'NoGoal':
                if gh == 0 and ga == 0:
                    bonus -= 2  # Demoti 0-0 (poco informativo)

        scored.append((score_str, count, re_pct, bonus))

    scored.sort(key=lambda x: (x[3], x[1]), reverse=True)

    return [
        {
            'tipo': 'RISULTATO_ESATTO',
            'pronostico': f"{s.split('-')[0]}:{s.split('-')[1]}",
            'confidence': pct,
            'stars': calculate_stars(pct),
        }
        for s, _, pct, _ in scored[:3]
    ]


# ---------- ASSEGNA QUOTE ----------

def assegna_quote(pronostici, odds):
    """Assegna le quote SNAI a ciascun pronostico."""
    quota_map = {
        '1': odds.get('1'), 'X': odds.get('X'), '2': odds.get('2'),
        '1X': odds.get('1X'), 'X2': odds.get('X2'), '12': odds.get('12'),
        'Over 1.5': odds.get('over_15', odds.get('Over 1.5')),
        'Under 1.5': odds.get('under_15', odds.get('Under 1.5')),
        'Over 2.5': odds.get('over_25', odds.get('Over 2.5')),
        'Under 2.5': odds.get('under_25', odds.get('Under 2.5')),
        'Over 3.5': odds.get('over_35', odds.get('Over 3.5')),
        'Under 3.5': odds.get('under_35', odds.get('Under 3.5')),
        'Goal': odds.get('gg', odds.get('GG')),
        'NoGoal': odds.get('ng', odds.get('NG')),
    }
    for p in pronostici:
        q = quota_map.get(p['pronostico'])
        p['quota'] = float(q) if q else None


# ---------- ORCHESTRATORE ----------

def convert_to_predictions(dist, odds):
    """
    Converte distribuzione MC in pronostici COERENTI tra loro.
    18 regole derivate da analisi caso-per-caso con l'utente.
    """
    pronostici = []
    re_dir = calcola_re_direzione(dist['top_scores'], dist['valid_cycles'])
    fav_side, fav_pct = identifica_favorita(dist)

    # 1. SEGNO / DC (Regole 1-7)
    segno_pred = decidi_segno_dc(dist, odds, re_dir)
    if segno_pred:
        pronostici.append(segno_pred)

    # 2. OVER / UNDER (Regole 8-12)
    ou_preds = decidi_over_under(dist, odds, re_dir, fav_pct)
    pronostici.extend(ou_preds)

    # 3. GG / NG (Regole 13-16)
    ggng_pred = decidi_gg_ng(dist, odds, re_dir, fav_pct, ou_preds)
    if ggng_pred:
        pronostici.append(ggng_pred)

    # 4. RE top 3 riordinati (Regole 17-18)
    re_top3 = riordina_re(dist['top_scores'], dist['valid_cycles'],
                          fav_pct, fav_side, segno_pred, ggng_pred)
    pronostici.extend(re_top3)

    # 5. Assegna quote
    assegna_quote(pronostici, odds)

    return pronostici


# ==================== FASE 5: KELLY/STAKE + 5 MODIFICATORI ====================

def apply_kelly(pronostici, dist, odds=None):
    """
    Kelly Frazionario 1/4 + 5 Modificatori calibrabili.
    La probabilita' MC e' direttamente la probabilita' reale.
    """
    if odds is None:
        odds = {}
    re_dir = calcola_re_direzione(dist['top_scores'], dist['valid_cycles'])

    # Pre-calcola conflitti tra mercati (Fattore 5)
    has_over = any(p['tipo'] == 'GOL' and 'Over' in p.get('pronostico', '') for p in pronostici)
    has_under = any(p['tipo'] == 'GOL' and 'Under' in p.get('pronostico', '') for p in pronostici)
    has_gg = any(p['tipo'] == 'GOL' and p.get('pronostico') == 'Goal' for p in pronostici)
    has_ng = any(p['tipo'] == 'GOL' and p.get('pronostico') == 'NoGoal' for p in pronostici)
    conflitto_mercati = (has_over and has_ng) or (has_under and has_gg)

    for p in pronostici:
        prob = p['confidence'] / 100
        quota = p.get('quota')
        tipo = p['tipo']

        # Rimuovi campi interni temporanei
        p.pop('_stake_hint', None)
        p.pop('_conflitto', None)
        p.pop('_downgraded_from', None)

        if not quota or quota <= 1:
            p['probabilita_stimata'] = round(p['confidence'], 1)
            p['prob_mercato'] = 0
            p['prob_modello'] = round(p['confidence'], 1)
            p['has_odds'] = False
            p['stake'] = 1
            p['stake_min'] = 1
            p['stake_max'] = 1
            p['edge'] = 0
            continue

        p_market = (1.0 / quota) * 0.96
        edge_pct = (prob * quota - 1) * 100

        # --- Kelly 3/4 base ---
        if (prob * quota) <= 1:
            stake_base = 1.0
        else:
            full_kelly = (prob * quota - 1) / (quota - 1)
            tq_kelly = full_kelly * 3 / 4
            stake_base = tq_kelly * 10  # scala 1-10

        # --- 5 Modificatori (proporzionali al Kelly base, cap ±50%) ---
        mod_pct = 0.0

        # Fattore 1: % MC
        if p['confidence'] >= 65:
            mod_pct += 0.20
        elif p['confidence'] < 50:
            mod_pct -= 0.20

        # Fattore 2: RE confermano/contraddicono
        pron = p['pronostico']
        if tipo in ('SEGNO', 'DOPPIA_CHANCE'):
            if pron == '1' and re_dir['casa'] >= 25:
                mod_pct += 0.20
            elif pron == '2' and re_dir['ospite'] >= 25:
                mod_pct += 0.20
            elif pron in ('1X', 'X2'):
                dc_sides = {'1X': ['casa', 'pari'], 'X2': ['ospite', 'pari']}
                if sum(re_dir[s] for s in dc_sides.get(pron, [])) >= 35:
                    mod_pct += 0.20
        elif tipo == 'GOL':
            if pron == 'Goal' and re_dir['gg'] >= 25:
                mod_pct += 0.20
            elif pron == 'Goal' and re_dir['ng'] >= 30:
                mod_pct -= 0.20
            elif pron == 'NoGoal' and re_dir['ng'] >= 25:
                mod_pct += 0.20
            elif pron == 'NoGoal' and re_dir['gg'] >= 30:
                mod_pct -= 0.20

        # Fattore 3: Valore quota (edge)
        edge_val = prob - (1.0 / quota)
        if edge_val > 0.10:
            mod_pct += 0.20
        elif edge_val < 0.03:
            mod_pct -= 0.20

        # Fattore 4: Book conferma/contradice
        if tipo in ('SEGNO', 'DOPPIA_CHANCE'):
            if pron in ('1', '2'):
                q_fav = _get_quota(odds, pron)
                q_other = _get_quota(odds, '2' if pron == '1' else '1')
                if q_fav > 0 and q_other > 0 and q_fav > q_other:
                    mod_pct -= 0.20  # Book non concorda sulla favorita
            elif pron in ('1X', 'X2'):
                book_second = _get_book_second_fav(odds)
                if book_second and not _segno_in_dc(book_second, pron):
                    mod_pct -= 0.20
        elif tipo == 'GOL' and pron in ('Goal', 'NoGoal'):
            q_gg = _get_quota(odds, 'gg', 'GG')
            q_ng = _get_quota(odds, 'ng', 'NG')
            if q_gg > 0 and q_ng > 0:
                if pron == 'Goal' and q_ng < q_gg:
                    mod_pct -= 0.20
                elif pron == 'NoGoal' and q_gg < q_ng:
                    mod_pct -= 0.20

        # Fattore 5: Conflitti mercati
        if conflitto_mercati and tipo == 'GOL':
            mod_pct -= 0.20
        elif not conflitto_mercati and len(pronostici) >= 3:
            mod_pct += 0.20  # Tutto coerente

        # Cap modificatori a ±50% del Kelly base
        mod_pct = max(-0.50, min(0.50, mod_pct))
        mod_value = stake_base * mod_pct

        # Stake finale con range
        raw_stake = max(1.0, min(10.0, stake_base + mod_value))
        floor_val = int(raw_stake)
        decimal_part = raw_stake - floor_val

        if decimal_part > 0.25:
            stake_min = floor_val
            stake_max = floor_val + 1
        else:
            stake_min = floor_val - 1
            stake_max = floor_val

        # Clamp a 1-10
        stake_min = max(1, min(10, stake_min))
        stake_max = max(1, min(10, stake_max))
        stake = max(1, min(10, round(raw_stake)))

        p['probabilita_stimata'] = round(prob * 100, 1)
        p['prob_mercato'] = round(p_market * 100, 1)
        p['prob_modello'] = round(prob * 100, 1)
        p['has_odds'] = True
        p['stake'] = stake
        p['stake_min'] = stake_min
        p['stake_max'] = stake_max
        p['edge'] = round(edge_pct, 2)


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
            'over_15_pct': dist['over_15_pct'],
            'under_15_pct': dist['under_15_pct'],
            'over_25_pct': dist['over_25_pct'],
            'under_25_pct': dist['under_25_pct'],
            'over_35_pct': dist['over_35_pct'],
            'under_35_pct': dist['under_35_pct'],
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

            # Kelly/Stake + 5 Modificatori
            apply_kelly(pronostici, dist, odds)

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
