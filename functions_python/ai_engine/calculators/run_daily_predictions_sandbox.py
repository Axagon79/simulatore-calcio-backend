"""
DAILY PREDICTIONS SANDBOX - Copia sandbox dell'algoritmo di Scrematura
=========================================================
Identico a run_daily_predictions.py ma:
1. Legge i pesi da MongoDB (collection prediction_tuning_settings)
2. Salva su daily_predictions_sandbox / daily_bombs_sandbox
3. NON tocca la produzione (daily_predictions / daily_bombs)
"""

import os
import sys
import math
from datetime import datetime, timedelta, timezone

# --- LOGGING: output su terminale + file log ---
class _TeeOutput:
    def __init__(self, log_path):
        self.terminal = sys.stdout
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
sys.stdout = _TeeOutput(os.path.join(_log_root, 'log', 'pronostici-del-giorno-test.txt'))
sys.stderr = sys.stdout
print(f"{'='*50}")
print(f"AVVIO PRONOSTICI SANDBOX: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
print(f"{'='*50}\n")

# --- FIX PERCORSI UNIVERSALE ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db
import json
import random

# Carica pool commenti
COMMENTS_POOL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'comments_pool.json')
with open(COMMENTS_POOL_PATH, 'r', encoding='utf-8') as f:
    COMMENTS_POOL = json.load(f)
# ==================== COLLECTIONS ====================
h2h_collection = db['h2h_by_round']
teams_collection = db['teams']
seasonal_stats_collection = db['team_seasonal_stats']
league_stats_collection = db['league_stats']
raw_h2h_collection = db['raw_h2h_data_v2']
classifiche_collection = db['classifiche']

# --- SANDBOX: output su collection separate ---
predictions_collection = db['daily_predictions_sandbox']
bombs_collection = db['daily_bombs_sandbox']
ucl_matches_collection = db['matches_champions_league']
uel_matches_collection = db['matches_europa_league']
ucl_teams_collection = db['teams_champions_league']
uel_teams_collection = db['teams_europa_league']

# ==================== COSTANTI (DEFAULT — sovrascritte da MongoDB se disponibili) ====================

# Soglie decisione
THRESHOLD_INCLUDE = 60
THRESHOLD_HIGH = 70

# Pesi FASE SEGNO (totale 100%)
PESI_SEGNO = {
    'bvs':           0.23,
    'quote':         0.16,
    'lucifero':      0.16,
    'affidabilita':  0.13,
    'dna':           0.07,
    'motivazioni':   0.07,
    'h2h':           0.04,
    'campo':         0.04,
    'strisce':       0.10,
}

# Pesi FASE GOL (totale 100%)
PESI_GOL = {
    'media_gol':     0.23,
    'att_vs_def':    0.20,
    'xg':            0.18,
    'h2h_gol':       0.13,
    'media_lega':    0.09,
    'dna_off_def':   0.07,
    'strisce':       0.10,
}

# Pesi FASE BOMBA (totale 100%)
PESI_BOMBA = {
    'bvs_anomalo':      0.25,
    'lucifero_sfi':     0.30,
    'motivazione_sfi':  0.20,
    'affidabilita':     0.15,
    'h2h_sfi':          0.10,
}

THRESHOLD_BOMBA = 65
THRESHOLD_GGNG = 65  # Soglia specifica per Goal/NoGoal (separata da THRESHOLD_INCLUDE)

# ==================== COSTANTI COPPE (UCL/UEL) ====================

# Pesi SEGNO: Potenza (più importante), Forma e Rendimento pari, Solidità ultima
PESI_CUP_SEGNO = {
    'forma': 0.25, 'potenza': 0.35, 'rendimento': 0.25, 'solidita': 0.15,
}

# Pesi GOL — Over/Under
PESI_CUP_OU = {
    'media_gol': 0.30, 'quote_ou': 0.25, 'over_pct': 0.20, 'h2h_gol': 0.15, 'fragilita': 0.10,
}

# Pesi GOL — GG/NG
PESI_CUP_GGNG = {
    'prob_segna_home': 0.30, 'prob_segna_away': 0.30, 'quote_ggng': 0.25, 'h2h_media': 0.15,
}

CUP_AVG_GOALS = {'Champions League': 3.03, 'Europa League': 2.82}
CUP_THRESHOLD_SEGNO = 55
CUP_THRESHOLD_GOL = 55
CUP_THRESHOLD_GGNG = 55
CUP_CONF_CAP = 75

# ==================== COSTANTI STRISCE (Curva a Campana) ====================
STREAK_CURVES = {
    "vittorie":       {1: 0, 2: 0, 3: 2, 4: 3, 5: 0, 6: -1, 7: -3, 8: -6, "9+": -10},
    "sconfitte":      {1: 0, 2: 0, 3: 0, 4: -1, 5: -2, "6+": -5},
    "imbattibilita":  {"1-4": 0, "5-7": 2, "8-10": 0, "11+": -3},
    "pareggi":        {1: 0, 2: 0, 3: -1, 4: 0, 5: 1, "6+": -3},
    "senza_vittorie": {1: 0, 2: 0, 3: -1, 4: -2, 5: 0, 6: 1, "7+": 2},
    "over25":         {1: 0, 2: 0, 3: 3, 4: 3, 5: 0, 6: -1, "7+": -4},
    "under25":        {1: 0, 2: 0, 3: 3, 4: 3, 5: 0, 6: -1, "7+": -4},
    "gg":             {1: 0, 2: 0, 3: 2, 4: 2, 5: 0, "6+": -3},
    "clean_sheet":    {1: 0, 2: 0, 3: 2, 4: 3, 5: 0, 6: -1, "7+": -4},
    "senza_segnare":  {1: 0, 2: 1, 3: 2, 4: 0, 5: -1, "6+": -3},
    "gol_subiti":     {1: 0, 2: 0, 3: 2, 4: 3, 5: 2, 6: 1, "7+": -2},
}
STREAK_MAX_PCT = 0.05          # ±5% moltiplicatore finale (ridotto, strisce sono anche segnale pesato)
STREAK_MIN_MATCHDAYS = 5       # attivazione dopo 5 giornate
STREAK_THEORETICAL = {
    "SEGNO": {"max": 8, "min": -23},
    "GOL":   {"max": 3, "min": -4},
    "GGNG":  {"max": 10, "min": -12},
}
STREAK_MARKET_MAP = {
    "SEGNO": ["vittorie", "sconfitte", "imbattibilita", "pareggi", "senza_vittorie"],
    "GOL":   ["over25", "under25"],
    "GGNG":  ["gg", "clean_sheet", "senza_segnare", "gol_subiti"],
}
ALL_STREAK_TYPES = [
    "vittorie", "sconfitte", "imbattibilita", "pareggi", "senza_vittorie",
    "over25", "under25", "gg", "clean_sheet", "senza_segnare", "gol_subiti",
]


# ==================== X FACTOR — Algoritmo Predizione Pareggi ====================

LEGHE_ALTA_X = {
    "Serie B", "Serie C - Girone B", "Süper Lig", "Serie C - Girone A",
    "Brasileirão Serie A", "Primera División",
}
THRESHOLD_X_FACTOR = 55

def calculate_x_factor(match):
    """Calcola la probabilità di pareggio (X) per una partita."""
    h2h = match.get('h2h_data', {}) or {}
    odds = match.get('odds', {}) or {}
    league = match.get('_league', '')

    raw_score = 0
    signals = []

    classification = h2h.get('classification')
    if classification == 'NON_BVS':
        raw_score += 12; signals.append('NON_BVS')
    elif classification == 'SEMI':
        raw_score -= 10; signals.append('SEMI_penalty')

    q1, q2 = odds.get('1'), odds.get('2')
    if q1 is not None and q2 is not None:
        try:
            diff_q = abs(float(q1) - float(q2))
            if diff_q < 0.50:
                raw_score += 9; signals.append(f'quote_eq({diff_q:.2f})')
        except (ValueError, TypeError): pass

    bvs = h2h.get('bvs_match_index')
    if bvs is not None:
        try:
            bvs_val = float(bvs)
            if bvs_val < -3:
                raw_score += 7; signals.append(f'BVS_neg({bvs_val:.1f})')
            elif bvs_val < -1:
                raw_score += 4; signals.append(f'BVS_mod({bvs_val:.1f})')
            elif -1 <= bvs_val < 1:
                raw_score -= 11; signals.append('BVS_neutro_penalty')
        except (ValueError, TypeError): pass

    trust_away = h2h.get('trust_away_letter')
    trust_home = h2h.get('trust_home_letter')
    if trust_away == 'D':
        raw_score += 6; signals.append('trust_away_D')
    elif trust_away == 'A':
        raw_score -= 11; signals.append('trust_away_A_penalty')
    if trust_home == 'D':
        raw_score += 4; signals.append('trust_home_D')
    elif trust_home == 'A':
        raw_score -= 5; signals.append('trust_home_A_penalty')

    if league in LEGHE_ALTA_X:
        raw_score += 4; signals.append('lega_alta_X')

    qx = odds.get('X')
    if qx is not None:
        try:
            qx_val = float(qx)
            if qx_val < 3.30:
                raw_score += 4; signals.append(f'quota_X({qx_val:.2f})')
            elif qx_val > 5.00:
                raw_score -= 15; signals.append('quota_X_alta_penalty')
        except (ValueError, TypeError): pass

    h2h_dna = h2h.get('h2h_dna', {}) or {}
    home_dna = h2h_dna.get('home_dna', {}) or {}
    away_dna = h2h_dna.get('away_dna', {}) or {}
    h_def, a_def = home_dna.get('def'), away_dna.get('def')
    if h_def is not None and a_def is not None:
        if abs(float(h_def) - float(a_def)) < 15:
            raw_score += 4; signals.append(f'DNA_DEF_sim({abs(float(h_def)-float(a_def)):.0f})')
    h_att, a_att = home_dna.get('att'), away_dna.get('att')
    if h_att is not None and a_att is not None:
        if abs(float(h_att) - float(a_att)) < 15:
            raw_score += 3; signals.append(f'DNA_ATT_sim({abs(float(h_att)-float(a_att)):.0f})')

    h_rank, a_rank = h2h.get('home_rank'), h2h.get('away_rank')
    if h_rank is not None and a_rank is not None:
        if abs(int(h_rank) - int(a_rank)) <= 5:
            raw_score += 3; signals.append(f'rank_vicini({abs(int(h_rank)-int(a_rank))})')

    fc = h2h.get('fattore_campo', {}) or {}
    fc_home = fc.get('field_home')
    if fc_home is not None:
        try:
            if float(fc_home) < 45:
                raw_score += 3; signals.append(f'FC_basso({float(fc_home):.0f})')
        except (ValueError, TypeError): pass

    # --- SEGNALI DA ENGINE INTERNO (se disponibili) ---

    # 11. Engine predice Under 2.5 con alta confidence → +6
    gol_r = match.get('_gol_result', {})
    if gol_r:
        tipo_gol = gol_r.get('tipo_gol', '')
        gol_score = gol_r.get('score', 0)
        if tipo_gol == 'Under 2.5' and gol_score >= 60:
            raw_score += 6
            signals.append(f'eng_Under({gol_score:.0f})')

        # 12. Engine predice GG con alta confidence → +4
        tipo_gg = gol_r.get('tipo_gol_extra', '')
        conf_gg = gol_r.get('confidence_gol_extra', 0)
        if tipo_gg == 'Goal' and conf_gg >= 60:
            raw_score += 4
            signals.append(f'eng_GG({conf_gg:.0f})')

    # 13. Segno incerto (confidence < 55) → +5
    segno_r = match.get('_segno_result', {})
    if segno_r:
        segno_score = segno_r.get('score', 100)
        if segno_score < 55:
            raw_score += 5
            signals.append(f'segno_incerto({segno_score:.0f})')

    confidence = max(10, min(70, 27.3 + raw_score))
    if confidence < THRESHOLD_X_FACTOR:
        return None
    return {
        'confidence': round(confidence, 1),
        'raw_score': raw_score,
        'signals': signals,
        'n_signals': len([s for s in signals if 'penalty' not in s]),
        'quota_x': float(qx) if qx else None,
    }


def load_tuning_config():
    """
    Carica pesi e soglie da MongoDB (prediction_tuning_settings).
    Se non trova nulla, usa i default hardcoded sopra.
    """
    global PESI_SEGNO, PESI_GOL, PESI_BOMBA, THRESHOLD_INCLUDE, THRESHOLD_HIGH, THRESHOLD_BOMBA, THRESHOLD_GGNG

    try:
        tuning_collection = db['prediction_tuning_settings']
        doc = tuning_collection.find_one({'_id': 'main_config'})

        if doc and 'config' in doc:
            config = doc['config']

            if 'PESI_SEGNO' in config:
                PESI_SEGNO = config['PESI_SEGNO']
                if 'strisce' not in PESI_SEGNO:
                    PESI_SEGNO['strisce'] = 0.10
            if 'PESI_GOL' in config:
                PESI_GOL = config['PESI_GOL']
                if 'strisce' not in PESI_GOL:
                    PESI_GOL['strisce'] = 0.10
            if 'PESI_BOMBA' in config:
                PESI_BOMBA = config['PESI_BOMBA']
            if 'SOGLIE' in config:
                soglie = config['SOGLIE']
                THRESHOLD_INCLUDE = soglie.get('THRESHOLD_INCLUDE', THRESHOLD_INCLUDE)
                THRESHOLD_HIGH = soglie.get('THRESHOLD_HIGH', THRESHOLD_HIGH)
                THRESHOLD_BOMBA = soglie.get('THRESHOLD_BOMBA', THRESHOLD_BOMBA)
                THRESHOLD_GGNG = soglie.get('THRESHOLD_GGNG', THRESHOLD_GGNG)

            print(f"   ✅ Pesi caricati da: MongoDB (prediction_tuning_settings)")
            return True
        else:
            print(f"   ⚠️  Nessuna config trovata in MongoDB — uso default hardcoded")
            return False
    except Exception as e:
        print(f"   ❌ Errore caricamento config da MongoDB: {e}")
        print(f"   ⚠️  Uso default hardcoded")
        return False


# ==================== RISULTATO ESATTO — Algoritmo basato su Profili Storici ====================

# Profili medi per risultato (da 4294 partite analizzate)
EXACT_SCORE_PROFILES = {
    '1:0': {'base_rate': 10.9, 'fc_home': 59.62, 'fc_away': 42.67, 'dna_att_diff': 6.62, 'dna_def_diff': 4.65, 'rank_diff': -3.16, 'avg_total_goals': 2.22, 'bvs': -0.15, 'h2h_score_diff': 0.64, 'lucifero_home': 9.45, 'lucifero_away': 9.10, 'dna_home_def': 55.12, 'dna_away_def': 50.47},
    '0:1': {'base_rate': 7.6, 'fc_home': 44.81, 'fc_away': 58.73, 'dna_att_diff': -7.38, 'dna_def_diff': -8.47, 'rank_diff': 4.06, 'avg_total_goals': 2.26, 'bvs': -1.81, 'h2h_score_diff': -1.01, 'lucifero_home': 7.41, 'lucifero_away': 9.63, 'dna_home_def': 48.11, 'dna_away_def': 56.58},
    '1:1': {'base_rate': 12.8, 'fc_home': 50.06, 'fc_away': 50.05, 'dna_att_diff': -2.41, 'dna_def_diff': -1.78, 'rank_diff': 1.31, 'avg_total_goals': 2.35, 'bvs': -2.18, 'h2h_score_diff': -0.17, 'lucifero_home': 8.84, 'lucifero_away': 9.24, 'dna_home_def': 48.92, 'dna_away_def': 50.70},
    '0:0': {'base_rate': 7.5, 'fc_home': 49.42, 'fc_away': 49.70, 'dna_att_diff': -2.83, 'dna_def_diff': -0.79, 'rank_diff': 0.88, 'avg_total_goals': 2.12, 'bvs': -1.15, 'h2h_score_diff': -0.07, 'lucifero_home': 8.35, 'lucifero_away': 10.36, 'dna_home_def': 52.96, 'dna_away_def': 53.75},
    '2:0': {'base_rate': 6.5, 'fc_home': 61.51, 'fc_away': 42.88, 'dna_att_diff': 11.35, 'dna_def_diff': 10.64, 'rank_diff': -3.95, 'avg_total_goals': 2.36, 'bvs': -0.19, 'h2h_score_diff': 0.85, 'lucifero_home': 11.06, 'lucifero_away': 9.79, 'dna_home_def': 58.28, 'dna_away_def': 47.64},
    '2:1': {'base_rate': 9.1, 'fc_home': 59.64, 'fc_away': 42.72, 'dna_att_diff': 4.69, 'dna_def_diff': 6.10, 'rank_diff': -2.69, 'avg_total_goals': 2.46, 'bvs': -0.02, 'h2h_score_diff': 0.41, 'lucifero_home': 9.61, 'lucifero_away': 9.25, 'dna_home_def': 52.85, 'dna_away_def': 46.74},
    '1:2': {'base_rate': 7.6, 'fc_home': 46.16, 'fc_away': 58.72, 'dna_att_diff': -7.81, 'dna_def_diff': -7.02, 'rank_diff': 3.33, 'avg_total_goals': 2.47, 'bvs': -0.98, 'h2h_score_diff': -0.77, 'lucifero_home': 9.09, 'lucifero_away': 10.66, 'dna_home_def': 45.73, 'dna_away_def': 52.75},
    '0:2': {'base_rate': 4.9, 'fc_home': 43.31, 'fc_away': 59.54, 'dna_att_diff': -13.57, 'dna_def_diff': -12.78, 'rank_diff': 4.86, 'avg_total_goals': 2.45, 'bvs': -1.97, 'h2h_score_diff': -1.06, 'lucifero_home': 9.70, 'lucifero_away': 11.93, 'dna_home_def': 43.58, 'dna_away_def': 56.36},
    '2:2': {'base_rate': 5.8, 'fc_home': 49.64, 'fc_away': 48.02, 'dna_att_diff': -3.56, 'dna_def_diff': -0.92, 'rank_diff': 0.79, 'avg_total_goals': 2.52, 'bvs': -1.46, 'h2h_score_diff': -0.22, 'lucifero_home': 9.56, 'lucifero_away': 9.98, 'dna_home_def': 45.53, 'dna_away_def': 46.45},
    '3:1': {'base_rate': 4.5, 'fc_home': 60.69, 'fc_away': 43.01, 'dna_att_diff': 11.75, 'dna_def_diff': 8.54, 'rank_diff': -3.63, 'avg_total_goals': 2.54, 'bvs': -0.64, 'h2h_score_diff': 0.46, 'lucifero_home': 10.27, 'lucifero_away': 9.04, 'dna_home_def': 52.57, 'dna_away_def': 44.03},
    '3:0': {'base_rate': 3.3, 'fc_home': 64.99, 'fc_away': 39.30, 'dna_att_diff': 19.76, 'dna_def_diff': 16.33, 'rank_diff': -6.03, 'avg_total_goals': 2.58, 'bvs': -0.01, 'h2h_score_diff': 0.49, 'lucifero_home': 12.26, 'lucifero_away': 7.64, 'dna_home_def': 59.64, 'dna_away_def': 43.31},
    '0:3': {'base_rate': 2.7, 'fc_home': 42.22, 'fc_away': 65.48, 'dna_att_diff': -22.98, 'dna_def_diff': -21.36, 'rank_diff': 5.93, 'avg_total_goals': 2.58, 'bvs': -0.62, 'h2h_score_diff': -0.99, 'lucifero_home': 8.71, 'lucifero_away': 12.79, 'dna_home_def': 38.35, 'dna_away_def': 59.71},
    '1:3': {'base_rate': 2.5, 'fc_home': 44.34, 'fc_away': 57.79, 'dna_att_diff': -11.89, 'dna_def_diff': -11.13, 'rank_diff': 4.40, 'avg_total_goals': 2.53, 'bvs': -1.02, 'h2h_score_diff': -0.85, 'lucifero_home': 6.99, 'lucifero_away': 11.99, 'dna_home_def': 41.16, 'dna_away_def': 52.29},
    '3:2': {'base_rate': 2.3, 'fc_home': 58.59, 'fc_away': 40.83, 'dna_att_diff': 4.21, 'dna_def_diff': 5.78, 'rank_diff': -3.81, 'avg_total_goals': 2.68, 'bvs': -0.47, 'h2h_score_diff': 0.44, 'lucifero_home': 9.79, 'lucifero_away': 7.81, 'dna_home_def': 47.85, 'dna_away_def': 42.06},
    '2:3': {'base_rate': 1.9, 'fc_home': 47.29, 'fc_away': 60.62, 'dna_att_diff': -10.49, 'dna_def_diff': -8.78, 'rank_diff': 4.23, 'avg_total_goals': 2.73, 'bvs': -3.33, 'h2h_score_diff': -0.88, 'lucifero_home': 8.60, 'lucifero_away': 9.84, 'dna_home_def': 41.72, 'dna_away_def': 50.50},
}

# Pesi segnali (dalla varianza tra risultati)
EXACT_SIGNAL_WEIGHTS = {
    'dna_att_diff': 10, 'dna_def_diff': 9,
    'fc_home': 8, 'fc_away': 8,
    'avg_total_goals': 7, 'rank_diff': 6,
    'dna_home_def': 5, 'dna_away_def': 5,
    'h2h_score_diff': 4, 'bvs': 3,
    'lucifero_home': 3, 'lucifero_away': 3,
}

# Range per normalizzazione
EXACT_SIGNAL_RANGES = {
    'dna_att_diff': 43.0, 'dna_def_diff': 38.0,
    'fc_home': 23.0, 'fc_away': 26.0,
    'avg_total_goals': 0.65, 'rank_diff': 12.0,
    'dna_home_def': 21.5, 'dna_away_def': 18.0,
    'h2h_score_diff': 2.0, 'bvs': 3.5,
    'lucifero_home': 5.5, 'lucifero_away': 5.5,
}

# Bonus categorici — Classification
EXACT_CLASS_BONUS = {
    '1:1': {'NON_BVS': 4, 'PURO': -2, 'SEMI': -2},
    '0:0': {'NON_BVS': 2, 'PURO': 0, 'SEMI': -2},
    '1:0': {'PURO': 1, 'SEMI': 0, 'NON_BVS': -1},
    '0:1': {'NON_BVS': 2, 'SEMI': 1, 'PURO': -3},
    '2:0': {'PURO': 1, 'SEMI': 2, 'NON_BVS': -2},
    '2:1': {'PURO': 2, 'SEMI': 1, 'NON_BVS': -3},
    '1:2': {'NON_BVS': 1, 'PURO': -2, 'SEMI': 0},
    '0:2': {'SEMI': 2, 'NON_BVS': 1, 'PURO': -2},
    '2:2': {'PURO': 2, 'SEMI': -2, 'NON_BVS': 0},
    '3:0': {'PURO': 1, 'SEMI': 2, 'NON_BVS': -2},
    '3:1': {'SEMI': 1, 'PURO': -1, 'NON_BVS': 0},
    '0:3': {'SEMI': 2, 'NON_BVS': 1, 'PURO': -2},
}

# Bonus Trust Home
EXACT_TRUST_HOME_BONUS = {
    '1:0': {'A': 3, 'B': 1, 'C': -1, 'D': -2},
    '0:1': {'A': -3, 'B': -3, 'C': 4, 'D': 2},
    '1:1': {'A': -1, 'B': 0, 'C': 1, 'D': 0},
    '0:0': {'A': 0, 'B': 0, 'C': 0, 'D': 1},
    '2:0': {'A': 2, 'B': 3, 'C': -3, 'D': -2},
    '2:1': {'A': 3, 'B': 2, 'C': -3, 'D': -1},
    '1:2': {'A': -2, 'B': -2, 'C': 3, 'D': 3},
    '0:2': {'A': -2, 'B': -2, 'C': 3, 'D': 2},
}

# Bonus Trust Away
EXACT_TRUST_AWAY_BONUS = {
    '1:0': {'A': -1, 'B': -1, 'C': 0, 'D': 3},
    '0:1': {'A': 1, 'B': 2, 'C': 0, 'D': -5},
    '1:1': {'A': -1, 'B': -1, 'C': 0, 'D': 2},
    '0:0': {'A': 0, 'B': 0, 'C': 0, 'D': 1},
    '2:0': {'A': -1, 'B': -1, 'C': 1, 'D': 2},
    '2:1': {'A': -1, 'B': -1, 'C': 2, 'D': 1},
    '1:2': {'A': 1, 'B': 2, 'C': 0, 'D': -3},
    '0:2': {'A': 2, 'B': 3, 'C': 0, 'D': -3},
}

# Lookup per score properties
_SCORE_TOTAL = {s: sum(int(x) for x in s.split(':')) for s in EXACT_SCORE_PROFILES}
_SCORE_BOTH = {s: int(s.split(':')[0]) > 0 and int(s.split(':')[1]) > 0 for s in EXACT_SCORE_PROFILES}
_SCORE_HOME_W = {s: int(s.split(':')[0]) > int(s.split(':')[1]) for s in EXACT_SCORE_PROFILES}
_SCORE_AWAY_W = {s: int(s.split(':')[1]) > int(s.split(':')[0]) for s in EXACT_SCORE_PROFILES}

THRESHOLD_EXACT_SCORE = 52


def _safe_float_es(val, default=None):
    if val is None:
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def calculate_exact_score(match):
    """
    Algoritmo Risultato Esatto — profili storici (4294 partite) + segnali engine.
    Per ogni risultato candidato, calcola quanto la partita assomiglia
    al profilo tipico di quel risultato.
    """
    h2h = match.get('h2h_data', {}) or {}
    fc = h2h.get('fattore_campo', {}) or {}
    h2h_dna = h2h.get('h2h_dna', {}) or {}
    home_dna = h2h_dna.get('home_dna', {}) or {}
    away_dna = h2h_dna.get('away_dna', {}) or {}

    # --- Estrai segnali numerici ---
    signals = {}
    signals['fc_home'] = _safe_float_es(fc.get('field_home'))
    signals['fc_away'] = _safe_float_es(fc.get('field_away'))

    dna_h_att = _safe_float_es(home_dna.get('att'))
    dna_h_def = _safe_float_es(home_dna.get('def'))
    dna_a_att = _safe_float_es(away_dna.get('att'))
    dna_a_def = _safe_float_es(away_dna.get('def'))

    signals['dna_att_diff'] = (dna_h_att - dna_a_att) if (dna_h_att is not None and dna_a_att is not None) else None
    signals['dna_def_diff'] = (dna_h_def - dna_a_def) if (dna_h_def is not None and dna_a_def is not None) else None
    signals['dna_home_def'] = dna_h_def
    signals['dna_away_def'] = dna_a_def

    hr = _safe_float_es(h2h.get('home_rank'))
    ar = _safe_float_es(h2h.get('away_rank'))
    signals['rank_diff'] = (hr - ar) if (hr is not None and ar is not None) else None

    signals['avg_total_goals'] = _safe_float_es(h2h.get('avg_total_goals'))
    signals['bvs'] = _safe_float_es(h2h.get('bvs_match_index'))

    hs = _safe_float_es(h2h.get('home_score'))
    aws = _safe_float_es(h2h.get('away_score'))
    signals['h2h_score_diff'] = (hs - aws) if (hs is not None and aws is not None) else None

    signals['lucifero_home'] = _safe_float_es(h2h.get('lucifero_home'))
    signals['lucifero_away'] = _safe_float_es(h2h.get('lucifero_away'))

    # Categorici
    classification = h2h.get('classification')
    trust_home = h2h.get('trust_home_letter')
    trust_away = h2h.get('trust_away_letter')

    # Engine (se disponibili dal loop principale)
    gol_r = match.get('_gol_result', {})
    segno_r = match.get('_segno_result', {})

    # Minimo 4 segnali disponibili
    available = sum(1 for v in signals.values() if v is not None)
    if available < 4:
        return None

    # --- Calcola fit score per ogni risultato candidato ---
    candidate_scores = {}

    for score_key, profile in EXACT_SCORE_PROFILES.items():
        # 1. Base rate come starting point
        fit = profile['base_rate'] * 0.3

        # 2. Prossimità segnali numerici
        for sig_name, weight in EXACT_SIGNAL_WEIGHTS.items():
            match_val = signals.get(sig_name)
            profile_val = profile.get(sig_name)
            if match_val is None or profile_val is None:
                continue
            range_val = EXACT_SIGNAL_RANGES[sig_name]
            diff = abs(match_val - profile_val) / range_val
            proximity = max(0.0, 1.0 - diff)
            fit += weight * proximity

        # 3. Classification
        if classification and score_key in EXACT_CLASS_BONUS:
            fit += EXACT_CLASS_BONUS[score_key].get(classification, 0)

        # 4. Trust Home
        if trust_home and score_key in EXACT_TRUST_HOME_BONUS:
            fit += EXACT_TRUST_HOME_BONUS[score_key].get(trust_home, 0)

        # 5. Trust Away
        if trust_away and score_key in EXACT_TRUST_AWAY_BONUS:
            fit += EXACT_TRUST_AWAY_BONUS[score_key].get(trust_away, 0)

        # 6. Engine: Under/Over
        if gol_r:
            tipo_gol = gol_r.get('tipo_gol') or ''
            gol_conf = gol_r.get('score') or 0
            total_goals = _SCORE_TOTAL[score_key]

            if gol_conf >= 55:
                scale = min(1.3, gol_conf / 60)
                if 'Under' in tipo_gol:
                    if total_goals <= 1:
                        fit += 4 * scale
                    elif total_goals == 2:
                        fit += 2 * scale
                    elif total_goals >= 4:
                        fit -= 3 * scale
                elif 'Over' in tipo_gol:
                    if total_goals >= 4:
                        fit += 3 * scale
                    elif total_goals == 3:
                        fit += 2 * scale
                    elif total_goals <= 1:
                        fit -= 3 * scale

            # GG/NG
            tipo_gg = gol_r.get('tipo_gol_extra') or ''
            gg_conf = gol_r.get('confidence_gol_extra') or 0
            both_score = _SCORE_BOTH[score_key]

            if gg_conf >= 55:
                scale = min(1.3, gg_conf / 60)
                if tipo_gg == 'Goal':
                    fit += (3 if both_score else -3) * scale
                elif tipo_gg == 'No Goal':
                    fit += (3 if not both_score else -2) * scale

        # 7. Engine: Segno
        if segno_r:
            segno_tipo = segno_r.get('tipo') or ''
            segno_conf = segno_r.get('score') or 0

            if segno_conf >= 55:
                scale = min(1.3, segno_conf / 60)
                if segno_tipo == '1':
                    if _SCORE_HOME_W[score_key]:
                        fit += 2 * scale
                    elif _SCORE_AWAY_W[score_key]:
                        fit -= 2 * scale
                elif segno_tipo == '2':
                    if _SCORE_AWAY_W[score_key]:
                        fit += 2 * scale
                    elif _SCORE_HOME_W[score_key]:
                        fit -= 2 * scale

            # Confidence segno bassa → favorisce pareggi
            if segno_conf < 52:
                h_g, a_g = (int(x) for x in score_key.split(':'))
                if h_g == a_g:
                    fit += 2

        candidate_scores[score_key] = max(0, fit)

    # Ordina e normalizza
    sorted_scores = sorted(candidate_scores.items(), key=lambda x: -x[1])
    total = sum(s for _, s in sorted_scores)
    if total <= 0:
        return None

    top_scores = [{'score': k, 'prob': round(v / total * 100, 1)} for k, v in sorted_scores[:5]]

    # Gap tra top-1 e probabilità uniforme (100/15 = 6.67%)
    avg_uniform = 100.0 / len(EXACT_SCORE_PROFILES)
    gap = top_scores[0]['prob'] - avg_uniform

    # Confidence basata su quanto top-1 emerge sopra la distribuzione uniforme
    confidence = min(70, max(25, 30 + gap * 7))

    if confidence < THRESHOLD_EXACT_SCORE:
        return None

    return {
        'top_3': top_scores[:3],
        'confidence': round(confidence, 1),
        'gap': round(gap, 2),
    }


# ==================== UTILITY ====================

def get_today_range():
    """Restituisce (inizio_oggi, inizio_domani) in ora locale italiana"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    return today, tomorrow


def normalize(value, min_val, max_val):
    """Normalizza un valore su scala 0-100."""
    if max_val <= min_val:
        return 50.0
    result = ((value - min_val) / (max_val - min_val)) * 100
    return max(0.0, min(100.0, result))


def calculate_stars(score):
    """Calcola stelle continue (2.5 - 5.0) da punteggio 60-100."""
    if score < 60:
        return 0.0
    stars = 2.5 + (score - 60) * (2.5 / 40)
    return round(min(5.0, stars), 1)


# ==================== STRISCE: Cache + Calcolo + Curva a Campana ====================

_streak_cache = {}            # {team_name: {total: {...}, home: {...}, away: {...}}}
_streak_cache_leagues = set()  # leghe già processate


def build_streak_cache(league_name):
    """Costruisce la cache strisce per tutte le squadre di una lega.
    Esegue 1 query MongoDB per lega, poi calcola tutte le strisce."""
    global _streak_cache, _streak_cache_leagues

    if league_name in _streak_cache_leagues:
        return

    # Tutte le partite giocate della lega, ordinate per data (più recente prima)
    pipeline = [
        {"$match": {"league": league_name}},
        {"$unwind": "$matches"},
        {"$match": {"matches.real_score": {"$exists": True, "$ne": "-:-", "$ne": ""}}},
        {"$sort": {"matches.date_obj": -1}},
        {"$project": {
            "home": "$matches.home",
            "away": "$matches.away",
            "real_score": "$matches.real_score",
            "date_obj": "$matches.date_obj",
        }}
    ]

    # Raggruppa per squadra
    team_matches = {}
    for doc in h2h_collection.aggregate(pipeline):
        home = doc.get('home', '')
        away = doc.get('away', '')
        score = doc.get('real_score', '')
        if not score or not home or not away:
            continue

        match_info = {'home': home, 'away': away, 'score': score, 'date': doc.get('date_obj')}

        team_matches.setdefault(home, []).append({**match_info, 'is_home': True})
        team_matches.setdefault(away, []).append({**match_info, 'is_home': False})

    # Verifica minimo giornate
    if not team_matches:
        _streak_cache_leagues.add(league_name)
        return

    max_played = max(len(m) for m in team_matches.values())
    if max_played < STREAK_MIN_MATCHDAYS:
        print(f"   [STREAK] {league_name}: solo {max_played} giornate, skip (min={STREAK_MIN_MATCHDAYS})")
        _streak_cache_leagues.add(league_name)
        return

    # Calcola strisce per ogni squadra
    for team, matches in team_matches.items():
        if team in _streak_cache:
            continue

        total_streaks = calculate_team_streaks(team, matches)
        home_matches = [m for m in matches if m['is_home']]
        away_matches = [m for m in matches if not m['is_home']]
        home_streaks = calculate_team_streaks(team, home_matches)
        away_streaks = calculate_team_streaks(team, away_matches)

        _streak_cache[team] = {
            'total': total_streaks,
            'home': home_streaks,
            'away': away_streaks,
        }

    _streak_cache_leagues.add(league_name)
    print(f"   [STREAK] {league_name}: cache costruita per {len(team_matches)} squadre")


def calculate_team_streaks(team_name, matches):
    """Calcola la lunghezza di tutte le strisce per una squadra.
    matches: lista ordinata dal più recente al più vecchio."""
    result = {}
    for streak_type in ALL_STREAK_TYPES:
        count = 0
        for match in matches:
            if _check_streak_condition(team_name, match, streak_type):
                count += 1
            else:
                break
        result[streak_type] = count
    return result


def _check_streak_condition(team, match, streak_type):
    """Verifica se una partita soddisfa la condizione di una striscia."""
    score = match.get('score', '')
    if not score or ':' not in score:
        return False

    parts = score.split(':')
    try:
        home_goals = int(parts[0].strip())
        away_goals = int(parts[1].strip())
    except (ValueError, IndexError):
        return False

    is_home = match.get('is_home', True)
    team_goals = home_goals if is_home else away_goals
    opp_goals = away_goals if is_home else home_goals
    total_goals = home_goals + away_goals

    if streak_type == 'vittorie':
        return team_goals > opp_goals
    elif streak_type == 'sconfitte':
        return team_goals < opp_goals
    elif streak_type == 'imbattibilita':
        return team_goals >= opp_goals
    elif streak_type == 'pareggi':
        return team_goals == opp_goals
    elif streak_type == 'senza_vittorie':
        return team_goals <= opp_goals
    elif streak_type == 'over25':
        return total_goals >= 3
    elif streak_type == 'under25':
        return total_goals <= 2
    elif streak_type == 'gg':
        return home_goals > 0 and away_goals > 0
    elif streak_type == 'clean_sheet':
        return opp_goals == 0
    elif streak_type == 'senza_segnare':
        return team_goals == 0
    elif streak_type == 'gol_subiti':
        return opp_goals > 0
    return False


def _curve_lookup(streak_type, n):
    """Lookup nella curva a campana: striscia tipo + lunghezza → bonus/malus."""
    if n <= 0:
        return 0

    curve = STREAK_CURVES.get(streak_type, {})

    # Lookup diretto per chiave numerica
    if n in curve:
        return curve[n]

    # Range keys: "1-4", "5-7", "9+", "6+", "7+", "11+"
    for key, value in curve.items():
        if isinstance(key, str):
            if '+' in key:
                min_val = int(key.replace('+', ''))
                if n >= min_val:
                    return value
            elif '-' in key:
                lo, hi = key.split('-')
                if int(lo) <= n <= int(hi):
                    return value

    return 0


def _get_streak_normalized(streaks_total, streaks_context, market):
    """Calcola il valore normalizzato delle strisce per un mercato.

    Returns:
        float: valore normalizzato da -1.0 a +1.0
    """
    applicable = STREAK_MARKET_MAP.get(market, [])
    theoretical = STREAK_THEORETICAL.get(market, {"max": 1, "min": -1})

    raw_total = sum(_curve_lookup(st, streaks_total.get(st, 0)) for st in applicable)
    raw_context = sum(_curve_lookup(st, streaks_context.get(st, 0)) for st in applicable)

    # Peso 50/50 tra totale e contesto
    raw_combined = (raw_total * 0.5) + (raw_context * 0.5)

    # Normalizzazione
    if raw_combined > 0:
        return min(raw_combined / theoretical['max'], 1.0) if theoretical['max'] > 0 else 0
    elif raw_combined < 0:
        return max(raw_combined / abs(theoretical['min']), -1.0) if theoretical['min'] != 0 else 0
    return 0


def get_streak_adjustment(streaks_total, streaks_context, market):
    """Moltiplicatore finale strisce (±5%). Usato DOPO la media pesata."""
    return _get_streak_normalized(streaks_total, streaks_context, market) * STREAK_MAX_PCT


def score_strisce(home_name, away_name, market):
    """Score strisce 0-100 per la media pesata.
    50 = neutro, >50 = bonus, <50 = penalità."""
    if home_name not in _streak_cache or away_name not in _streak_cache:
        return 50  # neutro se dati non disponibili

    h_data = _streak_cache[home_name]
    a_data = _streak_cache[away_name]

    norm_home = _get_streak_normalized(h_data['total'], h_data['home'], market)
    norm_away = _get_streak_normalized(a_data['total'], a_data['away'], market)

    # Media delle due squadre → scala 0-100
    avg_normalized = (norm_home + norm_away) / 2
    score = 50 + avg_normalized * 50

    return max(0, min(100, round(score, 1)))


def get_match_streak_data(home_name, away_name):
    """Recupera i dati strisce per entrambe le squadre di una partita.
    Returns: dict con streak_home, streak_away, oppure None se non disponibili."""
    if home_name not in _streak_cache or away_name not in _streak_cache:
        return None

    home_data = _streak_cache[home_name]
    away_data = _streak_cache[away_name]

    return {
        'home': {
            'total': home_data['total'],
            'home': home_data['home'],
        },
        'away': {
            'total': away_data['total'],
            'away': away_data['away'],
        },
    }


# ==================== FASE 1: RACCOLTA DATI ====================

def get_today_matches(target_date=None):
    """Recupera tutte le partite del giorno da h2h_by_round (aggregation pipeline)."""
    if target_date:
        today = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
    else:
        today, tomorrow = get_today_range()

    # Aggregation pipeline: filtra direttamente sul server MongoDB
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

    print(f"\n📅 Trovate {len(matches)} partite per {today.strftime('%Y-%m-%d')}")
    return matches


def get_today_cup_matches(target_date=None):
    """Recupera partite UCL/UEL del giorno dalle collections coppe."""
    if target_date:
        day_str = target_date.strftime('%d-%m-%Y')
    else:
        day_str = datetime.now().strftime('%d-%m-%Y')

    cup_matches = []
    for collection, league_name, teams_coll in [
        (ucl_matches_collection, 'Champions League', ucl_teams_collection),
        (uel_matches_collection, 'Europa League', uel_teams_collection),
    ]:
        docs = list(collection.find({
            'match_date': {'$regex': f'^{day_str}'},
            'status': {'$in': ['scheduled', 'Scheduled', 'not_started']}
        }))

        for doc in docs:
            match_date_str = doc.get('match_date', '')
            match_time = ''
            if ' ' in match_date_str:
                match_time = match_date_str.split(' ')[1]

            raw_odds = doc.get('odds', {})
            mapped_odds = {}
            if raw_odds:
                mapped_odds['1'] = raw_odds.get('home') or raw_odds.get('1')
                mapped_odds['X'] = raw_odds.get('draw') or raw_odds.get('X')
                mapped_odds['2'] = raw_odds.get('away') or raw_odds.get('2')
                for k in ['over_25', 'under_25', 'gg', 'ng', 'over_15', 'under_15', 'over_35', 'under_35']:
                    if k in raw_odds:
                        mapped_odds[k] = raw_odds[k]

            home_name = doc.get('home_team', '')
            away_name = doc.get('away_team', '')

            home_cup_team = teams_coll.find_one({
                '$or': [{'name': home_name}, {'aliases': home_name}]
            })
            away_cup_team = teams_coll.find_one({
                '$or': [{'name': away_name}, {'aliases': away_name}]
            })

            home_mongo_id = str(home_cup_team['_id']) if home_cup_team else ''
            away_mongo_id = str(away_cup_team['_id']) if away_cup_team else ''

            h2h_data = build_cup_h2h_data(home_cup_team, away_cup_team)

            cup_match = {
                'home': home_name,
                'away': away_name,
                'match_time': match_time,
                'odds': mapped_odds,
                'h2h_data': h2h_data,
                'home_mongo_id': home_mongo_id,
                'away_mongo_id': away_mongo_id,
                '_league': league_name,
                '_source': 'cup',
                '_round_id': None,
                'sportradar_h2h': doc.get('sportradar_h2h', {}),
                'home_elo': (home_cup_team or {}).get('elo_rating', 1500),
                'away_elo': (away_cup_team or {}).get('elo_rating', 1500),
                'home_valore_rosa': (home_cup_team or {}).get('valore_rosa_transfermarkt', 200_000_000),
                'away_valore_rosa': (away_cup_team or {}).get('valore_rosa_transfermarkt', 200_000_000),
            }
            cup_matches.append(cup_match)

    if cup_matches:
        print(f"🏆 Trovate {len(cup_matches)} partite coppe europee")
    return cup_matches


def build_cup_h2h_data(home_team_data, away_team_data):
    """Costruisce h2h_data sintetico per partite coppa da ELO + valore rosa."""
    home_elo = (home_team_data or {}).get('elo_rating', 1500)
    away_elo = (away_team_data or {}).get('elo_rating', 1500)
    home_value = (home_team_data or {}).get('valore_rosa_transfermarkt', 200_000_000)
    away_value = (away_team_data or {}).get('valore_rosa_transfermarkt', 200_000_000)

    elo_diff = home_elo - away_elo

    abs_diff = abs(elo_diff)
    if abs_diff > 150:
        classification = 'PURO'
    elif abs_diff > 50:
        classification = 'SEMI'
    else:
        classification = 'NON_BVS'

    bvs_index = max(-6, min(7, elo_diff / 300 * 7))

    def value_to_trust(value):
        if value >= 600_000_000: return 'A', 8.5
        elif value >= 400_000_000: return 'B', 7.0
        elif value >= 200_000_000: return 'C', 5.0
        else: return 'D', 3.0

    trust_home, aff_home = value_to_trust(home_value)
    trust_away, aff_away = value_to_trust(away_value)

    return {
        'classification': classification,
        'bvs_match_index': round(bvs_index, 2),
        'is_linear': abs_diff > 100,
        'trust_home_letter': trust_home,
        'trust_away_letter': trust_away,
        'affidabilità_casa': aff_home,
        'affidabilità_trasferta': aff_away,
        'affidabilità': {
            'affidabilità_casa': aff_home,
            'affidabilità_trasferta': aff_away,
        },
        'lucifero_home': 12.5,
        'lucifero_away': 12.5,
        'lucifero_trend_home': 0,
        'lucifero_trend_away': 0,
        'home_dna': {'att': 50, 'def': 50, 'tec': 50, 'val': 50},
        'away_dna': {'att': 50, 'def': 50, 'tec': 50, 'val': 50},
        'h2h_dna': {
            'home_dna': {'att': 50, 'def': 50, 'tec': 50, 'val': 50},
            'away_dna': {'att': 50, 'def': 50, 'tec': 50, 'val': 50},
        },
        'fattore_campo': {'field_home': 45, 'field_away': 40},
        'home_score': 5.0,
        'away_score': 5.0,
        'total_matches': 0,
        'avg_total_goals': 2.7,
    }


# ==================== SEGNALI CUP — SEGNO (Per-Team Scoring) ====================

def cup_forma(match):
    """Segnale Forma: metodo Lucifero con 5 partite, pesi [5,4,3,2,1].
    Ritorna (home_score, away_score) su scala 0-25."""
    sr = match.get('sportradar_h2h', {})

    def lucifero_5(letters):
        if not letters:
            return 12.5  # neutro
        weights = [5, 4, 3, 2, 1]
        total = 0
        max_score = 0
        for i, letter in enumerate(letters[:5]):
            w = weights[i] if i < len(weights) else 1
            max_score += 3 * w
            if letter == 'V':
                total += 3 * w
            elif letter == 'P':
                total += 1 * w
            # S = 0
        if max_score == 0:
            return 12.5
        return (total / max_score) * 25.0

    h_form = sr.get('home_form', [])
    a_form = sr.get('away_form', [])

    return (round(lucifero_5(h_form), 2), round(lucifero_5(a_form), 2))


def cup_potenza(match):
    """Segnale Potenza: ELO (40%) + Quote (35%) + Valore Rosa (25%).
    Ritorna (home_score, away_score) su scala 0-100."""
    odds = match.get('odds', {})
    q1 = float(odds.get('1', 99))
    qx = float(odds.get('X', 99))
    q2 = float(odds.get('2', 99))

    # Quote: probabilità implicita senza aggio
    total_ip = 0
    if q1 > 0: total_ip += 1/q1
    if qx > 0: total_ip += 1/qx
    if q2 > 0: total_ip += 1/q2

    if total_ip > 0:
        quote_home = (1/q1) / total_ip * 100 if q1 > 0 else 33.3
        quote_away = (1/q2) / total_ip * 100 if q2 > 0 else 33.3
    else:
        quote_home = 33.3
        quote_away = 33.3

    # ELO: normalizzato con divisore 2100
    home_elo = match.get('home_elo', 1500)
    away_elo = match.get('away_elo', 1500)
    elo_home = (home_elo / 2100) * 100
    elo_away = (away_elo / 2100) * 100

    # Valore Rosa: scala 50-100, gap max 50
    home_rosa = match.get('home_valore_rosa', 200_000_000)
    away_rosa = match.get('away_valore_rosa', 200_000_000)
    rosa_home = 50 + (home_rosa / 1_350_000_000) * 50
    rosa_away = 50 + (away_rosa / 1_350_000_000) * 50

    # Media pesata
    h_score = elo_home * 0.40 + quote_home * 0.35 + rosa_home * 0.25
    a_score = elo_away * 0.40 + quote_away * 0.35 + rosa_away * 0.25

    return (round(h_score, 2), round(a_score, 2))


def cup_rendimento(match):
    """Segnale Rendimento Coppa: Posizione + Punti + Form_pct + H2H record.
    Ritorna (home_score, away_score) su scala 50-100."""
    sr = match.get('sportradar_h2h', {})

    def calc_rendimento(prefix, team_side):
        components = []

        # Posizione: (37 - pos) / 36 * 100
        pos = sr.get(f'{prefix}_position')
        if pos is not None:
            components.append((37 - pos) / 36 * 100)

        # Punti: punti / 24 * 100
        pts = sr.get(f'{prefix}_points')
        if pts is not None:
            components.append((pts / 24) * 100)

        # Form_pct: diretto (0-100)
        form_pct = sr.get(f'{prefix}_form_pct')
        if form_pct is not None:
            components.append(form_pct)

        # H2H record: vittorie squadra / totale * 100
        h_wins = sr.get('h2h_home_wins')
        draws = sr.get('h2h_draws')
        a_wins = sr.get('h2h_away_wins')
        if h_wins is not None and a_wins is not None:
            total = h_wins + (draws or 0) + a_wins
            if total > 0:
                if team_side == 'home':
                    components.append(h_wins / total * 100)
                else:
                    components.append(a_wins / total * 100)

        if not components:
            return 75.0  # neutro nel range 50-100

        media = sum(components) / len(components)
        # Comprimi su 50-100
        return 50 + (media / 100) * 50

    h_score = calc_rendimento('home', 'home')
    a_score = calc_rendimento('away', 'away')

    return (round(h_score, 2), round(a_score, 2))


def cup_solidita(match):
    """Segnale Solidità: Win rate + Goal diff.
    Ritorna (home_score, away_score) su scala 50-100."""
    sr = match.get('sportradar_h2h', {})

    def calc_solidita(prefix):
        stand = sr.get(f'{prefix}_standing', {})
        if not stand:
            return 75.0  # neutro

        played = stand.get('played', 0)
        if played == 0:
            return 75.0

        # Win rate: wins / played * 100
        win_rate = (stand.get('wins', 0) / played) * 100

        # Goal diff normalizzato: 50 + (gd/played) * 25 → clamp 0-100
        gd = stand.get('goal_diff', 0)
        gd_norm = max(0, min(100, 50 + (gd / played) * 25))

        # Media dei due
        media = (win_rate + gd_norm) / 2

        # Comprimi su 50-100
        return 50 + (media / 100) * 50

    h_score = calc_solidita('home')
    a_score = calc_solidita('away')

    return (round(h_score, 2), round(a_score, 2))


# ==================== SEGNALI CUP — GOL (Over/Under) ====================

def cup_ou_media_gol(match):
    """Media gol combinata delle due squadre. >50=Over, <50=Under."""
    sr = match.get('sportradar_h2h', {})
    h_avg = sr.get('home_avg_goals_cl')
    a_avg = sr.get('away_avg_goals_cl')
    if h_avg is None or a_avg is None:
        return 50

    combined = (h_avg + a_avg) / 2
    # 2.5 = neutro (50). Ogni 0.5 sopra/sotto = ±20 punti
    score = 50 + (combined - 2.5) * 40
    return max(0, min(100, round(score, 1)))


def cup_ou_quote(match):
    """Probabilità implicita Over/Under 2.5 dalle quote."""
    odds = match.get('odds', {})
    q_over = odds.get('over_25')
    q_under = odds.get('under_25')
    if q_over is None or q_under is None:
        return 50

    q_over_f = float(q_over)
    q_under_f = float(q_under)
    if q_over_f <= 0 or q_under_f <= 0:
        return 50

    # Implied probability senza aggio
    total_ip = 1/q_over_f + 1/q_under_f
    ip_over = (1/q_over_f) / total_ip * 100
    return max(0, min(100, round(ip_over, 1)))


def cup_ou_over_pct(match):
    """Media Over% storico delle due squadre."""
    sr = match.get('sportradar_h2h', {})
    h_over = sr.get('home_over_pct')
    a_over = sr.get('away_over_pct')
    if h_over is None or a_over is None:
        return 50

    return max(0, min(100, round((h_over + a_over) / 2, 1)))


def cup_ou_h2h_gol(match):
    """Media gol nei precedenti diretti. >50=Over, <50=Under."""
    sr = match.get('sportradar_h2h', {})
    avg = sr.get('h2h_avg_goals')
    if avg is None:
        return 50

    # 2.5 = neutro. Ogni 0.5 = ±20 punti
    score = 50 + (avg - 2.5) * 40
    return max(0, min(100, round(score, 1)))


def cup_ou_fragilita(match):
    """Fragilità difensiva: 100 - media clean_sheet%. Alto=difese deboli=Over."""
    sr = match.get('sportradar_h2h', {})
    h_cs = sr.get('home_clean_sheet_pct')
    a_cs = sr.get('away_clean_sheet_pct')
    if h_cs is None or a_cs is None:
        return 50

    avg_cs = (h_cs + a_cs) / 2
    return max(0, min(100, round(100 - avg_cs, 1)))


# ==================== SEGNALI CUP — GOL (GG/NG) ====================

def cup_gg_prob_segna_home(match):
    """Probabilità che la casa segni: score_pct × (100 - cs_pct avversaria)."""
    sr = match.get('sportradar_h2h', {})
    h_score = sr.get('home_score_pct')
    a_cs = sr.get('away_clean_sheet_pct')
    if h_score is None or a_cs is None:
        return 50

    prob = h_score * (100 - a_cs) / 100
    return max(0, min(100, round(prob, 1)))


def cup_gg_prob_segna_away(match):
    """Probabilità che l'ospite segni: score_pct × (100 - cs_pct avversaria)."""
    sr = match.get('sportradar_h2h', {})
    a_score = sr.get('away_score_pct')
    h_cs = sr.get('home_clean_sheet_pct')
    if a_score is None or h_cs is None:
        return 50

    prob = a_score * (100 - h_cs) / 100
    return max(0, min(100, round(prob, 1)))


def cup_gg_quote(match):
    """Probabilità implicita GG dalle quote GG/NG."""
    odds = match.get('odds', {})
    q_gg = odds.get('gg')
    q_ng = odds.get('ng')
    if q_gg is None or q_ng is None:
        return 50

    q_gg_f = float(q_gg)
    q_ng_f = float(q_ng)
    if q_gg_f <= 0 or q_ng_f <= 0:
        return 50

    total_ip = 1/q_gg_f + 1/q_ng_f
    ip_gg = (1/q_gg_f) / total_ip * 100
    return max(0, min(100, round(ip_gg, 1)))


def cup_gg_h2h_media(match):
    """H2H avg goals + media gol squadre → indicatore GG."""
    sr = match.get('sportradar_h2h', {})
    h2h_avg = sr.get('h2h_avg_goals')
    h_avg = sr.get('home_avg_goals_cl')
    a_avg = sr.get('away_avg_goals_cl')

    components = []
    if h2h_avg is not None:
        # >2.5 favorisce GG, <1.5 favorisce NG
        h2h_score = 50 + (h2h_avg - 2.0) * 30
        components.append(max(0, min(100, h2h_score)))

    if h_avg is not None and a_avg is not None:
        # Il minore dei due determina: se entrambe segnano almeno 1.0 → GG
        both_score = min(h_avg, a_avg)
        avg_score = 50 + (both_score - 1.0) * 40
        components.append(max(0, min(100, avg_score)))

    if not components:
        return 50

    return round(sum(components) / len(components), 1)


# ==================== ANALYZE CUP — SEGNO + GOL ====================

def analyze_cup_segno(match):
    """Analisi SEGNO dedicata per partite coppa UCL/UEL.
    4 segnali per-team: Forma, Potenza, Rendimento, Solidità.
    Home total vs Away total → favorita + confidence."""
    odds = match.get('odds', {})
    q1 = float(odds.get('1', 99))
    qx = float(odds.get('X', 99))
    q2 = float(odds.get('2', 99))

    # Calcola i 4 segnali (ognuno ritorna (home, away))
    forma_h, forma_a = cup_forma(match)
    potenza_h, potenza_a = cup_potenza(match)
    rendimento_h, rendimento_a = cup_rendimento(match)
    solidita_h, solidita_a = cup_solidita(match)

    # Normalizza Forma da 0-25 a 0-100
    forma_h_norm = (forma_h / 25) * 100
    forma_a_norm = (forma_a / 25) * 100

    # Totale pesato per ogni squadra
    home_total = (
        forma_h_norm * PESI_CUP_SEGNO['forma'] +
        potenza_h * PESI_CUP_SEGNO['potenza'] +
        rendimento_h * PESI_CUP_SEGNO['rendimento'] +
        solidita_h * PESI_CUP_SEGNO['solidita']
    )
    away_total = (
        forma_a_norm * PESI_CUP_SEGNO['forma'] +
        potenza_a * PESI_CUP_SEGNO['potenza'] +
        rendimento_a * PESI_CUP_SEGNO['rendimento'] +
        solidita_a * PESI_CUP_SEGNO['solidita']
    )

    # Gap → confidence
    gap = abs(home_total - away_total)
    confidence = min(CUP_CONF_CAP, round(50 + gap, 1))

    # Favorita: chi ha il totale più alto
    if home_total >= away_total:
        segno = '1'
        q_fav = q1
    else:
        segno = '2'
        q_fav = q2

    # Segno bloccato se quota troppo bassa
    segno_blocked = q_fav < 1.35

    # Doppia chance
    doppia_chance = None
    doppia_chance_quota = None
    if q1 < q2:
        if qx < 4.0:
            doppia_chance = '1X'
            doppia_chance_quota = 1 / (1/q1 + 1/qx) if q1 < 99 and qx < 99 else None
        else:
            doppia_chance = '12'
            doppia_chance_quota = 1 / (1/q1 + 1/q2) if q1 < 99 and q2 < 99 else None
    elif q2 < q1:
        if qx < 4.0:
            doppia_chance = 'X2'
            doppia_chance_quota = 1 / (1/qx + 1/q2) if qx < 99 and q2 < 99 else None
        else:
            doppia_chance = '12'
            doppia_chance_quota = 1 / (1/q1 + 1/q2) if q1 < 99 and q2 < 99 else None

    # Dettaglio per frontend — formato compatibile con renderDetailBarWithTeams
    # dettaglio[key] = affidabilità (50 + gap = quanto il segnale differenzia)
    # dettaglio_raw[key] = {home, away, scala} per barre confronto squadre
    dettaglio = {
        'forma': min(100, round(50 + abs(forma_h_norm - forma_a_norm), 1)),
        'potenza': min(100, round(50 + abs(potenza_h - potenza_a), 1)),
        'rendimento': min(100, round(50 + abs(rendimento_h - rendimento_a), 1)),
        'solidita': min(100, round(50 + abs(solidita_h - solidita_a), 1)),
    }
    dettaglio_raw = {
        'forma': {'home': forma_h, 'away': forma_a, 'scala': '/25'},
        'potenza': {'home': round(potenza_h, 1), 'away': round(potenza_a, 1), 'scala': '%'},
        'rendimento': {'home': round(rendimento_h, 1), 'away': round(rendimento_a, 1), 'scala': '%'},
        'solidita': {'home': round(solidita_h, 1), 'away': round(solidita_a, 1), 'scala': '%'},
    }

    print(f"  🏆 CUP SEGNO: home_total={round(home_total,1)} away_total={round(away_total,1)} gap={round(gap,1)} → {segno} conf={confidence}")

    return {
        'score': confidence,
        'segno': segno,
        'doppia_chance': doppia_chance,
        'doppia_chance_quota': doppia_chance_quota,
        'odds': {'1': q1, 'X': qx, '2': q2},
        'dettaglio': dettaglio,
        'dettaglio_raw': dettaglio_raw,
        'segno_blocked': segno_blocked,
        'streak_adjustment_segno': 0,
    }


def analyze_cup_gol(match, league_name):
    """Analisi GOL dedicata per partite coppa UCL/UEL.
    Over/Under: 5 segnali. GG/NG: 4 segnali incrociati."""
    sr = match.get('sportradar_h2h', {})

    # ===== OVER/UNDER =====
    ou_scores = {
        'media_gol': cup_ou_media_gol(match),
        'quote_ou': cup_ou_quote(match),
        'over_pct': cup_ou_over_pct(match),
        'h2h_gol': cup_ou_h2h_gol(match),
        'fragilita': cup_ou_fragilita(match),
    }

    ou_total = sum(ou_scores[k] * PESI_CUP_OU[k] for k in PESI_CUP_OU)

    # Direction: >50 = Over, <50 = Under. Distanza da 50 = confidence
    ou_confidence = round(abs(ou_total - 50) + 50, 1)
    tipo_gol = None
    if ou_confidence >= CUP_THRESHOLD_GOL:
        tipo_gol = 'Over 2.5' if ou_total > 50 else 'Under 2.5'

    # ===== GG/NG =====
    gg_scores = {
        'prob_segna_home': cup_gg_prob_segna_home(match),
        'prob_segna_away': cup_gg_prob_segna_away(match),
        'quote_ggng': cup_gg_quote(match),
        'h2h_media': cup_gg_h2h_media(match),
    }

    gg_total = sum(gg_scores[k] * PESI_CUP_GGNG[k] for k in PESI_CUP_GGNG)

    gg_confidence = round(abs(gg_total - 50) + 50, 1)
    tipo_gol_extra = None
    confidence_gol_extra = 0
    if gg_confidence >= CUP_THRESHOLD_GGNG:
        if gg_total > 50:
            tipo_gol_extra = 'Goal'
            confidence_gol_extra = gg_confidence
        else:
            tipo_gol_extra = 'NoGoal'
            confidence_gol_extra = gg_confidence

    # Anti-conflitto: Over+NG o Under+GG
    if tipo_gol and tipo_gol_extra:
        is_conflict = (
            ('Over' in tipo_gol and tipo_gol_extra == 'NoGoal') or
            ('Under' in tipo_gol and tipo_gol_extra == 'Goal')
        )
        if is_conflict:
            if ou_confidence >= confidence_gol_extra:
                tipo_gol_extra = None
                confidence_gol_extra = 0
            else:
                tipo_gol = None

    # Expected total goals
    h_avg = sr.get('home_avg_goals_cl')
    a_avg = sr.get('away_avg_goals_cl')
    expected_total = ((h_avg or 2.7) + (a_avg or 2.7)) / 2
    league_avg = CUP_AVG_GOALS.get(league_name, 2.7)

    # Directions O/U + GG/NG (per frontend)
    directions = {}
    for k, v in ou_scores.items():
        if v > 55: directions[k] = 'over'
        elif v < 45: directions[k] = 'under'
        else: directions[k] = 'neutro'
    for k, v in gg_scores.items():
        if v > 55: directions[f'gg_{k}'] = 'goal'
        elif v < 45: directions[f'gg_{k}'] = 'nogoal'
        else: directions[f'gg_{k}'] = 'neutro'

    print(f"  🏆 CUP GOL: ou_total={round(ou_total,1)} ou_conf={ou_confidence} → {tipo_gol or 'SKIP'} | gg_total={round(gg_total,1)} gg_conf={gg_confidence} → {tipo_gol_extra or 'SKIP'}")

    return {
        'score': ou_confidence,
        'tipo_gol': tipo_gol,
        'tipo_gol_extra': tipo_gol_extra,
        'confidence_gol_extra': round(confidence_gol_extra, 1),
        'expected_total': round(expected_total, 2),
        'league_avg': league_avg,
        'dettaglio': {**ou_scores, **{f'gg_{k}': v for k, v in gg_scores.items()}},
        'directions': directions,
        'h2h_patterns': {
            'btts_pct': gg_scores.get('prob_segna_home', 50),
            'over25_pct': ou_scores.get('over_pct', 50),
        },
        'streak_adjustment_gol': 0,
        'streak_adjustment_ggng': 0,
    }


def get_team_data(team_name):
    """Recupera tutti i dati di una squadra dalla collection teams."""
    team = teams_collection.find_one({
        "$or": [
            {"name": team_name},
            {"aliases": team_name},
            {"aliases_transfermarkt": team_name}
        ]
    })
    return team


def get_seasonal_stats(team_name, league_name):
    """Recupera xG e volume gol medio da team_seasonal_stats."""
    doc = seasonal_stats_collection.find_one({
        "team": team_name,
        "league": league_name
    })
    if not doc:
        # Prova senza league
        doc = seasonal_stats_collection.find_one({"team": team_name})
    return doc


def get_league_avg_goals(league_name):
    """Recupera media gol del campionato da league_stats."""
    doc = league_stats_collection.find_one({"_id": league_name})
    if doc:
        return doc.get('avg_goals', 2.5)
    return 2.5  # Default


def get_h2h_goal_patterns(home_name, away_name, home_tm_id, away_tm_id):
    """
    Analizza i pattern gol dagli scontri diretti (raw_h2h_data_v2).
    Restituisce: % over 2.5, % entrambe segnano, media gol totali
    """
    doc = raw_h2h_collection.find_one({
        "$or": [
            {"tm_id_a": int(home_tm_id), "tm_id_b": int(away_tm_id)},
            {"tm_id_a": int(away_tm_id), "tm_id_b": int(home_tm_id)}
        ]
    })

    if not doc or not doc.get('matches'):
        return {'over25_pct': 50.0, 'btts_pct': 50.0, 'avg_goals': 2.5, 'total_matches': 0}

    matches = doc['matches']
    total = 0
    over25 = 0
    btts = 0
    total_goals = 0

    # Analizza solo gli ultimi 20 scontri (più recenti = più rilevanti)
    recent_matches = [m for m in matches if m.get('score', '-:-') != '-:-'][:20]

    for m in recent_matches:
        score = m.get('score', '0:0')
        try:
            if ':' in score:
                parts = score.split(':')
            elif '-' in score:
                parts = score.split('-')
            else:
                continue

            g_home = int(parts[0].strip())
            g_away = int(parts[1].strip())

            total += 1
            total_goals += g_home + g_away

            if g_home + g_away > 2:
                over25 += 1
            if g_home > 0 and g_away > 0:
                btts += 1
        except (ValueError, IndexError):
            continue

    if total == 0:
        return {'over25_pct': 50.0, 'btts_pct': 50.0, 'avg_goals': 2.5, 'total_matches': 0}

    return {
        'over25_pct': (over25 / total) * 100,
        'btts_pct': (btts / total) * 100,
        'avg_goals': total_goals / total,
        'total_matches': total
    }


# ==================== FASE 2: ANALISI SEGNO ====================

def score_bvs(match_data):
    """
    Punteggio BVS (0-100).
    PURO + alto valore = massimo, NON_BVS = minimo.
    """
    h2h = match_data.get('h2h_data', {})
    classification = h2h.get('classification', 'NON_BVS')
    bvs_index = h2h.get('bvs_match_index', 0)
    is_linear = h2h.get('is_linear', False)

    # Base per classificazione
    if classification == 'PURO':
        base = 65
    elif classification == 'SEMI':
        base = 40
    else:  # NON_BVS
        base = 10

    # Bonus/malus per bvs_match_index (-6 a +7)
    # Normalizzo su scala -35 a +35
    index_bonus = normalize(bvs_index, -6, 7) * 0.35

    # Bonus linearità
    linear_bonus = 10 if is_linear else 0

    score = base + index_bonus + linear_bonus
    return max(0, min(100, score))


def score_quote(match_data):
    """
    Punteggio Quote (0-100).
    Range ideale 1.55-2.20, picco a 1.75.
    Sotto 1.35 = scarta, sopra 2.20 = penalizzata.
    """
    odds = match_data.get('odds', {})
    q1 = float(odds.get('1', 99))
    qx = float(odds.get('X', 99))
    q2 = float(odds.get('2', 99))

    if q1 == 99 or q2 == 99:
        return 30  # Dati mancanti

    # La quota del favorito
    q_fav = min(q1, q2)

    # Sotto 1.35 = quasi scartata
    if q_fav < 1.35:
        score = 15
    # 1.35-1.55 = valore basso, rischio/rendimento scarso
    elif 1.35 <= q_fav < 1.55:
        score = 30 + (q_fav - 1.35) * 100  # 30-50
    # 1.55-2.20 = range ideale, picco a 1.75
    elif 1.55 <= q_fav <= 2.20:
        distance_from_ideal = abs(q_fav - 1.75)
        score = 100 - (distance_from_ideal * 45)  # 100 a 1.75, scende ai bordi
    # Sopra 2.20 = penalizzata, troppo rischiosa
    elif 2.20 < q_fav <= 2.80:
        score = 45 - (q_fav - 2.20) * 40  # 45-21
    else:
        # Sopra 2.80 = molto rischiosa
        score = max(10, 20 - (q_fav - 2.80) * 15)

    return max(0, min(100, score))


def score_lucifero(match_data):
    """
    Punteggio Lucifero (0-100).
    Grande divario di forma = buon pronostico.
    """
    h2h = match_data.get('h2h_data', {})
    luc_home = h2h.get('lucifero_home', 12.5)
    luc_away = h2h.get('lucifero_away', 12.5)

    # Divario di forma (0-25 possibile)
    divario = abs(luc_home - luc_away)

    # La squadra in forma migliore
    max_luc = max(luc_home, luc_away)
    min_luc = min(luc_home, luc_away)

    # Punteggio basato sul divario
    # Divario 0 = 20 (nessuna differenza)
    # Divario 10 = 60
    # Divario 15+ = 80+
    score = 20 + (divario / 25) * 70

    # Bonus se la squadra migliore è molto in forma
    if max_luc >= 20:
        score += 10
    elif max_luc >= 15:
        score += 5

    # Malus se entrambe in cattiva forma
    if max_luc < 8:
        score -= 15

    # Bonus dal trend (ultime 5)
    trend_home = h2h.get('lucifero_trend_home', [])
    trend_away = h2h.get('lucifero_trend_away', [])

    if trend_home and trend_away:
        # La favorita sta migliorando?
        if luc_home > luc_away and len(trend_home) >= 2:
            if trend_home[0] > trend_home[-1]:  # trend[0] = più recente
                score += 5  # In miglioramento
        elif luc_away > luc_home and len(trend_away) >= 2:
            if trend_away[0] > trend_away[-1]:
                score += 5

    return max(0, min(100, score))


def score_affidabilita(match_data):
    """
    Punteggio Affidabilità (0-100).
    Trust letter A = massimo, D = minimo.
    Più importante l'affidabilità della favorita.
    """
    h2h = match_data.get('h2h_data', {})
    aff_home = h2h.get('affidabilità_casa', 5.0)
    aff_away = h2h.get('affidabilità_trasferta', 5.0)
    trust_home = h2h.get('trust_home_letter', 'C')
    trust_away = h2h.get('trust_away_letter', 'C')

    # Determina chi è la favorita dalle quote
    odds = match_data.get('odds', {})
    q1 = float(odds.get('1', 99))
    q2 = float(odds.get('2', 99))

    if q1 < q2:
        # Casa favorita
        aff_favorita = aff_home
        trust_favorita = trust_home
        aff_sfidante = aff_away
        trust_sfidante = trust_away
    else:
        # Ospite favorita
        aff_favorita = aff_away
        trust_favorita = trust_away
        aff_sfidante = aff_home
        trust_sfidante = trust_home

    # Punteggio base dall'affidabilità numerica della favorita (0-10 → 0-70)
    score = (aff_favorita / 10) * 70

    # Bonus/Malus dalla trust letter della favorita
    trust_bonus = {'A': 20, 'B': 10, 'C': 0, 'D': -15}
    score += trust_bonus.get(trust_favorita, 0)

    # Bonus se anche la sfidante è affidabile (partita prevedibile)
    if aff_sfidante >= 7:
        score += 10
    elif aff_sfidante <= 3:
        score -= 5  # Sfidante imprevedibile

    return max(0, min(100, score))


def score_dna(match_data):
    """
    Punteggio DNA (0-100).
    Divario tecnico netto tra le squadre.
    """
    h2h = match_data.get('h2h_data', {})
    dna_home = h2h.get('home_dna', {})
    dna_away = h2h.get('away_dna', {})

    if not dna_home or not dna_away:
        return 50  # Neutro

    # Calcola "potenza" complessiva DNA per squadra
    home_power = (
        dna_home.get('att', 50) * 0.35 +
        dna_home.get('def', 50) * 0.25 +
        dna_home.get('tec', 50) * 0.25 +
        dna_home.get('val', 50) * 0.15
    )

    away_power = (
        dna_away.get('att', 50) * 0.35 +
        dna_away.get('def', 50) * 0.25 +
        dna_away.get('tec', 50) * 0.25 +
        dna_away.get('val', 50) * 0.15
    )

    # Divario (0-100 possibile)
    divario = abs(home_power - away_power)

    # Più divario = più facile pronosticare
    score = 30 + (divario / 100) * 70

    return max(0, min(100, score))


def score_motivazioni(match_data, home_team_doc, away_team_doc):
    """
    Punteggio Motivazioni (0-100).
    Squadra favorita molto motivata = bene.
    """
    mot_home = 10
    mot_away = 10

    if home_team_doc:
        mot_home = home_team_doc.get('stats', {}).get('motivation', None)
        if mot_home is None:
            mot_home = 10
    if away_team_doc:
        mot_away = away_team_doc.get('stats', {}).get('motivation', None)
        if mot_away is None:
            mot_away = 10

    # Determina favorita dalle quote
    odds = match_data.get('odds', {})
    q1 = float(odds.get('1', 99))
    q2 = float(odds.get('2', 99))

    if q1 < q2:
        mot_favorita = mot_home
        mot_sfidante = mot_away
    else:
        mot_favorita = mot_away
        mot_sfidante = mot_home

    # Favorita motivata (5-15 → 0-100)
    score = normalize(mot_favorita, 5, 15) * 0.7

    # Bonus se divario motivazionale
    divario_mot = abs(mot_home - mot_away)
    score += (divario_mot / 10) * 30

    return max(0, min(100, score))


def score_h2h(match_data):
    """
    Punteggio H2H (0-100).
    Precedenti diretti confermano il favorito.
    """
    h2h = match_data.get('h2h_data', {})
    home_score = h2h.get('home_score', 5.0)
    away_score = h2h.get('away_score', 5.0)
    total_matches = h2h.get('total_matches', 0)
    h2h_weight = h2h.get('h2h_weight', 0)

    if total_matches == 0 or h2h_weight == 0:
        return 50  # Neutro

    # Divario H2H (0-10 possibile)
    divario = abs(home_score - away_score)

    # Normalizza
    score = 30 + (divario / 10) * 50

    # Bonus per tanti scontri diretti (più dati = più affidabile)
    if total_matches >= 15:
        score += 15
    elif total_matches >= 8:
        score += 10
    elif total_matches >= 3:
        score += 5

    return max(0, min(100, score))


def score_campo(match_data):
    """
    Punteggio Fattore Campo (0-100).
    """
    h2h = match_data.get('h2h_data', {})
    fc = h2h.get('fattore_campo', {})

    field_home = fc.get('field_home', 3.5) if isinstance(fc, dict) else 3.5
    field_away = fc.get('field_away', 3.5) if isinstance(fc, dict) else 3.5

    # Se i dati sono direttamente nel h2h_data
    if not isinstance(fc, dict):
        field_home = h2h.get('field_home', 3.5)
        field_away = h2h.get('field_away', 3.5)

    # Divario campo (0-100)
    divario = abs(field_home - field_away)

    # Casa forte = conferma pronostico
    score = 30 + (divario / 100) * 50

    # Bonus se casa molto forte
    if field_home >= 70:
        score += 15
    elif field_home >= 55:
        score += 8

    return max(0, min(100, score))


def calculate_doppia_chance(q_a, q_b):
    """Calcola la quota della doppia chance: 1/((1/A)+(1/B))"""
    try:
        return 1 / ((1 / q_a) + (1 / q_b))
    except ZeroDivisionError:
        return 0


def analyze_segno(match_data, home_team_doc, away_team_doc):
    """
    FASE 2: Calcola punteggio complessivo SEGNO (0-100) e determina quale segno.
    Include logica doppia chance (1X, X2, 12).
    """
    home_name = match_data.get('home', '')
    away_name = match_data.get('away', '')

    scores = {
        'bvs': score_bvs(match_data),
        'quote': score_quote(match_data),
        'lucifero': score_lucifero(match_data),
        'affidabilita': score_affidabilita(match_data),
        'dna': score_dna(match_data),
        'motivazioni': score_motivazioni(match_data, home_team_doc, away_team_doc),
        'h2h': score_h2h(match_data),
        'campo': score_campo(match_data),
        'strisce': score_strisce(home_name, away_name, 'SEGNO'),
    }

    # Media pesata (include strisce come segnale)
    total = sum(scores[k] * PESI_SEGNO[k] for k in PESI_SEGNO)

    # --- MOLTIPLICATORE STRISCE (±5%, spinta finale) ---
    streak_adj_segno = 0.0
    if home_name in _streak_cache and away_name in _streak_cache:
        h_data = _streak_cache[home_name]
        a_data = _streak_cache[away_name]
        adj_home = get_streak_adjustment(h_data['total'], h_data['home'], 'SEGNO')
        adj_away = get_streak_adjustment(a_data['total'], a_data['away'], 'SEGNO')
        streak_adj_segno = adj_home + adj_away  # contributo indipendente
        if streak_adj_segno != 0:
            total = total * (1 + streak_adj_segno)
            total = max(0.0, min(100.0, total))
            print(f"   [STREAK SEGNO] Score: {scores['strisce']:.0f}/100 | Molt: {streak_adj_segno:+.2%}")

    # Determina QUALE segno
    odds = match_data.get('odds', {})
    q1 = float(odds.get('1', 99))
    qx = float(odds.get('X', 99))
    q2 = float(odds.get('2', 99))

    # Blocco pronostico segno se quota favorita sotto 1.35 (ma analisi resta visibile)
    q_fav = min(q1, q2)
    segno_blocked = q_fav < 1.35

    h2h = match_data.get('h2h_data', {})
    tip_sign = h2h.get('tip_sign', '')

    # Il segno viene dal BVS tip_sign, confermato dalle quote
    if tip_sign in ['1', '2']:
        segno = tip_sign
    elif q1 < q2:
        segno = '1'
    else:
        segno = '2'

    # --- LOGICA DOPPIA CHANCE ---
    doppia_chance = None
    doppia_chance_quota = None

    # Calcola tutte le doppie chance
    dc_1x = calculate_doppia_chance(q1, qx) if q1 < 99 and qx < 99 else 0
    dc_x2 = calculate_doppia_chance(qx, q2) if qx < 99 and q2 < 99 else 0
    dc_12 = calculate_doppia_chance(q1, q2) if q1 < 99 and q2 < 99 else 0

    # Determina quale doppia chance consigliare
    if segno == '1' and dc_1x >= 1.30:
        doppia_chance = '1X'
        doppia_chance_quota = round(dc_1x, 2)
    elif segno == '2' and dc_x2 >= 1.30:
        doppia_chance = 'X2'
        doppia_chance_quota = round(dc_x2, 2)

    # Caso speciale: 12 (entrambe segnano, raramente pareggiano)
    if dc_12 >= 1.30 and qx > 3.50 and abs(q1 - q2) < 1.0:
        doppia_chance = '12'
        doppia_chance_quota = round(dc_12, 2)

    # --- RACCOLTA DATI GREZZI PER FRONTEND ---
    # BVS
    bvs_home = h2h.get('bvs_index', 0)
    bvs_away = h2h.get('bvs_away', 0)

    # Quote -> Probabilità senza aggio, con metà pareggio distribuita
    prob_1_raw = 1/q1 if q1 < 99 else 0
    prob_x_raw = 1/qx if qx < 99 else 0
    prob_2_raw = 1/q2 if q2 < 99 else 0
    total_prob = prob_1_raw + prob_x_raw + prob_2_raw
    if total_prob > 0:
        prob_1_norm = (prob_1_raw / total_prob) * 100
        prob_x_norm = (prob_x_raw / total_prob) * 100
        prob_2_norm = (prob_2_raw / total_prob) * 100
        # Distribuisci metà del pareggio a ciascuna squadra
        quote_home = round(prob_1_norm + prob_x_norm / 2, 1)
        quote_away = round(prob_2_norm + prob_x_norm / 2, 1)
    else:
        quote_home = 50.0
        quote_away = 50.0

    # Lucifero
    lucifero_home = h2h.get('lucifero_home', 12.5)
    lucifero_away = h2h.get('lucifero_away', 12.5)

    # Affidabilità
    trust_home = h2h.get('trust_home_letter', 'C')
    trust_away = h2h.get('trust_away_letter', 'C')
    aff_home_num = h2h.get('affidabilità_casa', 5.0)
    aff_away_num = h2h.get('affidabilità_trasferta', 5.0)

    # DNA
    dna_home = h2h.get('home_dna', {})
    dna_away = h2h.get('away_dna', {})
    dna_home_power = (
        dna_home.get('att', 50) * 0.35 +
        dna_home.get('def', 50) * 0.25 +
        dna_home.get('tec', 50) * 0.25 +
        dna_home.get('val', 50) * 0.15
    ) if dna_home else 50
    dna_away_power = (
        dna_away.get('att', 50) * 0.35 +
        dna_away.get('def', 50) * 0.25 +
        dna_away.get('tec', 50) * 0.25 +
        dna_away.get('val', 50) * 0.15
    ) if dna_away else 50

    # Motivazioni
    mot_home = 10
    mot_away = 10
    if home_team_doc:
        mot_home = home_team_doc.get('stats', {}).get('motivation', 10) or 10
    if away_team_doc:
        mot_away = away_team_doc.get('stats', {}).get('motivation', 10) or 10

    # H2H
    h2h_home_score = h2h.get('home_score', 5.0)
    h2h_away_score = h2h.get('away_score', 5.0)
    h2h_total_matches = h2h.get('total_matches', 0)

    # Fattore Campo
    fc = h2h.get('fattore_campo', {})
    if isinstance(fc, dict):
        field_home = fc.get('field_home', 3.5)
        field_away = fc.get('field_away', 3.5)
    else:
        field_home = h2h.get('field_home', 3.5)
        field_away = h2h.get('field_away', 3.5)

    # Costruisci dettaglio_raw
    dettaglio_raw = {
        'bvs': {'home': bvs_home, 'away': bvs_away, 'scala': '±7'},
        'quote': {'home': quote_home, 'away': quote_away, 'scala': '%'},
        'lucifero': {'home': lucifero_home, 'away': lucifero_away, 'scala': '/25'},
        'affidabilita': {'home': trust_home, 'away': trust_away, 'home_num': aff_home_num, 'away_num': aff_away_num, 'scala': 'A-D'},
        'dna': {'home': round(dna_home_power, 1), 'away': round(dna_away_power, 1), 'scala': '/100'},
        'motivazioni': {'home': mot_home, 'away': mot_away, 'scala': '/15'},
        'h2h': {'home': h2h_home_score, 'away': h2h_away_score, 'matches': h2h_total_matches, 'scala': '/10'},
        'campo': {'home': field_home, 'away': field_away, 'scala': '/7'},
    }

    return {
        'score': round(total, 1),
        'segno': segno,
        'doppia_chance': doppia_chance,
        'doppia_chance_quota': doppia_chance_quota,
        'odds': {'1': q1, 'X': qx, '2': q2},
        'dettaglio': scores,
        'dettaglio_raw': dettaglio_raw,
        'segno_blocked': segno_blocked,
        'streak_adjustment_segno': round(streak_adj_segno * 100, 2),
    }


# ==================== FASE 3: ANALISI GOL ====================

def score_media_gol(home_team_doc, away_team_doc, match_data):
    """
    Punteggio Media Gol squadre (0-100).
    Gol fatti/subiti casa e trasferta.
    """
    score_over = 50  # Neutro


    if not home_team_doc or not away_team_doc:
        return 50, 'neutro', 2.5, False

    h_ranking = home_team_doc.get('ranking', {})
    a_ranking = away_team_doc.get('ranking', {})

    h_home = h_ranking.get('homeStats', {})
    a_away = a_ranking.get('awayStats', {})

    h_played = h_home.get('played', 0)
    a_played = a_away.get('played', 0)

    if h_played == 0 or a_played == 0:
        return 50, 'neutro', 2.5, False

    # Media gol fatti e subiti
    h_gf_avg = h_home.get('goalsFor', 0) / h_played  # Gol fatti casa
    h_ga_avg = h_home.get('goalsAgainst', 0) / h_played  # Gol subiti casa
    a_gf_avg = a_away.get('goalsFor', 0) / a_played  # Gol fatti trasferta
    a_ga_avg = a_away.get('goalsAgainst', 0) / a_played  # Gol subiti trasferta

    # Stima gol attesi nella partita
    expected_home_goals = (h_gf_avg + a_ga_avg) / 2
    expected_away_goals = (a_gf_avg + h_ga_avg) / 2
    expected_total = expected_home_goals + expected_away_goals

    # Punteggio Over/Under
    if expected_total >= 3.0:
        score_over = 80 + min(20, (expected_total - 3.0) * 15)
        direction = 'over'
    elif expected_total >= 2.5:
        score_over = 60 + (expected_total - 2.5) * 40
        direction = 'over'
    elif expected_total <= 1.8:
        score_over = 80 + min(20, (1.8 - expected_total) * 25)
        direction = 'under'
    elif expected_total <= 2.2:
        score_over = 55 + (2.2 - expected_total) * 60
        direction = 'under'
    else:
        score_over = 45
        direction = 'neutro'

    # Goal/NoGoal
    both_score_likely = (expected_home_goals >= 1.0 and expected_away_goals >= 0.8)

    return round(score_over, 1), direction, expected_total, both_score_likely


def score_att_vs_def(home_team_doc, away_team_doc):
    """
    Punteggio Attacco vs Difesa (0-100).
    Attacco forte vs difesa debole = Over/Goal.
    """
    if not home_team_doc or not away_team_doc:
        return 50, 'neutro', False

    h_scores = home_team_doc.get('scores', {})
    a_scores = away_team_doc.get('scores', {})

    # Attacco casa vs difesa trasferta
    att_home = h_scores.get('attack_home', 7.5)   # 0-15
    def_away = a_scores.get('defense_away', 5.0)   # 0-10

    # Attacco trasferta vs difesa casa
    att_away = a_scores.get('attack_away', 7.5)    # 0-15
    def_home = h_scores.get('defense_home', 5.0)   # 0-10

    # Mismatch 1: Attacco casa vs Difesa trasferta
    att_h_norm = (att_home / 15) * 100
    def_a_norm = (def_away / 10) * 100
    mismatch_1 = max(0, att_h_norm - def_a_norm)

    # Mismatch 2: Attacco trasferta vs Difesa casa
    att_a_norm = (att_away / 15) * 100
    def_h_norm = (def_home / 10) * 100
    mismatch_2 = max(0, att_a_norm - def_h_norm)

    # Entrambi gli attacchi dominano le difese = Over/Goal
    total_mismatch = mismatch_1 + mismatch_2

    if total_mismatch > 60:
        score = 75 + min(25, (total_mismatch - 60) * 0.5)
        direction = 'over'
    elif total_mismatch > 30:
        score = 55 + (total_mismatch - 30) * 0.65
        direction = 'over'
    elif total_mismatch < 10:
        # Difese dominano
        score = 65 + (10 - total_mismatch) * 2
        direction = 'under'
    else:
        score = 45
        direction = 'neutro'

    # Determina BTTS
    both_attack_strong = att_h_norm > 55 and att_a_norm > 45

    return round(score, 1), direction, both_attack_strong


def score_xg(home_team_doc, away_team_doc, league_name):
    """
    Punteggio xG e volume gol (0-100).
    """
    home_name = home_team_doc.get('name', '') if home_team_doc else ''
    away_name = away_team_doc.get('name', '') if away_team_doc else ''

    h_stats = get_seasonal_stats(home_name, league_name)
    a_stats = get_seasonal_stats(away_name, league_name)

    if not h_stats or not a_stats:
        return 50, 'neutro', 1.25, 1.25

    h_xg = h_stats.get('xg_avg', 1.25)
    a_xg = a_stats.get('xg_avg', 1.25)
    h_vol = h_stats.get('total_volume_avg', 2.5)
    a_vol = a_stats.get('total_volume_avg', 2.5)

    # Media xG combinata
    combined_xg = h_xg + a_xg
    combined_vol = (h_vol + a_vol) / 2

    # Punteggio basato su xG
    if combined_xg >= 2.8:
        score = 80 + min(20, (combined_xg - 2.8) * 20)
        direction = 'over'
    elif combined_xg >= 2.3:
        score = 55 + (combined_xg - 2.3) * 50
        direction = 'over'
    elif combined_xg <= 1.5:
        score = 75 + min(25, (1.5 - combined_xg) * 30)
        direction = 'under'
    elif combined_xg <= 1.9:
        score = 55 + (1.9 - combined_xg) * 50
        direction = 'under'
    else:
        score = 45
        direction = 'neutro'

    # Bonus/malus dal volume
    if combined_vol >= 3.0:
        score += 8
    elif combined_vol <= 2.0:
        score -= 5

    return round(max(0, min(100, score)), 1), direction, h_xg, a_xg


def score_h2h_gol(match_data):
    """
    Punteggio H2H Gol storici (0-100).
    Pattern Over/Under/BTTS negli scontri diretti.
    """
    home_tm_id = match_data.get('home_tm_id', 0)
    away_tm_id = match_data.get('away_tm_id', 0)
    home_name = match_data.get('home', '')
    away_name = match_data.get('away', '')

    if not home_tm_id or not away_tm_id:
        return 50, 'neutro', {}

    patterns = get_h2h_goal_patterns(home_name, away_name, home_tm_id, away_tm_id)

    if patterns['total_matches'] < 3:
        return 50, 'neutro', patterns

    over_pct = patterns['over25_pct']
    btts_pct = patterns['btts_pct']
    avg_goals = patterns['avg_goals']

    # Punteggio basato su pattern
    if over_pct >= 70:
        score = 75 + min(25, (over_pct - 70) * 0.8)
        direction = 'over'
    elif over_pct >= 55:
        score = 55 + (over_pct - 55) * 1.3
        direction = 'over'
    elif over_pct <= 30:
        score = 70 + min(30, (30 - over_pct) * 1.0)
        direction = 'under'
    elif over_pct <= 40:
        score = 55 + (40 - over_pct) * 1.5
        direction = 'under'
    else:
        score = 45
        direction = 'neutro'

    # Bonus affidabilità del dato (più match = più affidabile)
    if patterns['total_matches'] >= 15:
        score += 8
    elif patterns['total_matches'] >= 8:
        score += 4

    return round(max(0, min(100, score)), 1), direction, patterns


def score_media_lega(league_name):
    """
    Punteggio Media Gol Campionato (0-100).
    """
    avg = get_league_avg_goals(league_name)

    if avg >= 3.0:
        score = 75 + min(25, (avg - 3.0) * 30)
        direction = 'over'
    elif avg >= 2.7:
        score = 55 + (avg - 2.7) * 65
        direction = 'over'
    elif avg <= 2.0:
        score = 70 + min(30, (2.0 - avg) * 40)
        direction = 'under'
    elif avg <= 2.3:
        score = 55 + (2.3 - avg) * 50
        direction = 'under'
    else:
        score = 50
        direction = 'neutro'

    return round(score, 1), direction, avg


def score_dna_off_def(match_data):
    """
    Punteggio DNA offensivo/difensivo (0-100).
    """
    h2h = match_data.get('h2h_data', {})
    dna_home = h2h.get('home_dna', {})
    dna_away = h2h.get('away_dna', {})

    if not dna_home or not dna_away:
        return 50, 'neutro'

    # Potenza offensiva combinata
    att_combined = (dna_home.get('att', 50) + dna_away.get('att', 50)) / 2
    def_combined = (dna_home.get('def', 50) + dna_away.get('def', 50)) / 2

    # Attacchi dominano difese = Over
    if att_combined > def_combined + 15:
        score = 65 + min(35, (att_combined - def_combined - 15) * 1.5)
        direction = 'over'
    elif def_combined > att_combined + 15:
        score = 65 + min(35, (def_combined - att_combined - 15) * 1.5)
        direction = 'under'
    else:
        score = 45
        direction = 'neutro'

    return round(max(0, min(100, score)), 1), direction


def analyze_gol(match_data, home_team_doc, away_team_doc, league_name):
    """
    FASE 3: Calcola punteggio complessivo GOL (0-100) e determina tipo pronostico.
    """
    # Calcola ogni sotto-punteggio
    home_name = match_data.get('home', '')
    away_name = match_data.get('away', '')

    mg_score, mg_dir, expected_total, both_score = score_media_gol(home_team_doc, away_team_doc, match_data)
    avd_score, avd_dir, both_att_strong = score_att_vs_def(home_team_doc, away_team_doc)
    xg_score, xg_dir, h_xg, a_xg = score_xg(home_team_doc, away_team_doc, league_name)
    h2h_score, h2h_dir, h2h_patterns = score_h2h_gol(match_data)
    ml_score, ml_dir, league_avg = score_media_lega(league_name)
    dna_score, dna_dir = score_dna_off_def(match_data)

    scores = {
        'media_gol': mg_score,
        'att_vs_def': avd_score,
        'xg': xg_score,
        'h2h_gol': h2h_score,
        'media_lega': ml_score,
        'dna_off_def': dna_score,
        'strisce': score_strisce(home_name, away_name, 'GOL'),
    }

    # Media pesata (include strisce come segnale)
    total = sum(scores[k] * PESI_GOL[k] for k in PESI_GOL)

    # --- MOLTIPLICATORE STRISCE GOL (±5%, spinta finale) ---
    streak_adj_gol = 0.0
    if home_name in _streak_cache and away_name in _streak_cache:
        h_data = _streak_cache[home_name]
        a_data = _streak_cache[away_name]
        adj_h_gol = get_streak_adjustment(h_data['total'], h_data['home'], 'GOL')
        adj_a_gol = get_streak_adjustment(a_data['total'], a_data['away'], 'GOL')
        streak_adj_gol = (adj_h_gol + adj_a_gol) / 2  # media
        if streak_adj_gol != 0:
            total = total * (1 + streak_adj_gol)
            total = max(0.0, min(100.0, total))
            print(f"   [STREAK GOL] Score: {scores['strisce']:.0f}/100 | Molt: {streak_adj_gol:+.2%}")

    # Determina direzione prevalente
    directions = [mg_dir, avd_dir, xg_dir, h2h_dir, ml_dir, dna_dir]
    over_count = directions.count('over')
    under_count = directions.count('under')

    # Determina tipo pronostico GOL (Over/Under)
    if over_count > under_count:
        if expected_total >= 2.8:
            tipo_gol = 'Over 2.5'
        else:
            tipo_gol = 'Over 1.5'
    elif under_count > over_count:
        if expected_total <= 2.0:
            tipo_gol = 'Under 2.5'
        else:
            tipo_gol = 'Under 3.5'
    else:
        tipo_gol = None

    # Goal/NoGoal: decisione INDIPENDENTE da Over/Under
    # La direzione viene determinata DOPO il calcolo btts_total (vedi sotto)
    tipo_gol_extra = None  # verrà impostato dopo btts_total

    # ====== CONFIDENCE SEPARATA per Goal/NoGoal (8 segnali) ======
    # Ogni segnale: 0-100 (alto = probabile che entrambe segnino → Goal)
    # Decisione Goal/NoGoal INDIPENDENTE da Over/Under

    odds = match_data.get('odds', {})

    # 1. BTTS% dagli H2H (peso 0.18)
    btts_h2h = h2h_patterns.get('btts_pct', 50) if isinstance(h2h_patterns, dict) else 50

    # 2. Gol attesi + xG combinato — squadra più debole (peso 0.15)
    #    Fonde i vecchi segnali exp e xG (ridondanti se separati)
    if home_team_doc and away_team_doc:
        h_hs = home_team_doc.get('ranking', {}).get('homeStats', {})
        a_as = away_team_doc.get('ranking', {}).get('awayStats', {})
        hp, ap = h_hs.get('played', 0), a_as.get('played', 0)
        if hp > 0 and ap > 0:
            exp_h = (h_hs.get('goalsFor', 0) / hp + a_as.get('goalsAgainst', 0) / ap) / 2
            exp_a = (a_as.get('goalsFor', 0) / ap + h_hs.get('goalsAgainst', 0) / hp) / 2
            btts_exp_raw = min(100, (min(exp_h, exp_a) / 1.4) * 100)
        else:
            btts_exp_raw = 50
    else:
        btts_exp_raw = 50
    btts_xg_raw = min(100, (min(h_xg, a_xg) / 1.4) * 100)
    btts_exp_xg = (btts_exp_raw + btts_xg_raw) / 2  # media dei due

    # 3. Forza attacco più debole (peso 0.10)
    if home_team_doc and away_team_doc:
        h_sc = home_team_doc.get('scores', {})
        a_sc = away_team_doc.get('scores', {})
        att_h_n = (h_sc.get('attack_home', 7.5) / 15) * 100
        att_a_n = (a_sc.get('attack_away', 7.5) / 15) * 100
        btts_att = min(att_h_n, att_a_n)
    else:
        btts_att = 50

    # 4. DNA offensivo più debole (peso 0.07)
    h2h_d = match_data.get('h2h_data', {})
    dna_h_att = h2h_d.get('home_dna', {}).get('att', 50) if h2h_d.get('home_dna') else 50
    dna_a_att = h2h_d.get('away_dna', {}).get('att', 50) if h2h_d.get('away_dna') else 50
    btts_dna = min(dna_h_att, dna_a_att)

    # 5. Both score likely bonus (peso 0.07)
    btts_both = 80 if both_score else 30

    # 6. Strisce GG/NG (peso 0.08)
    btts_strisce = score_strisce(home_name, away_name, 'GGNG')

    # 7. NUOVO — Conceding rate: % gol subiti per partita (peso 0.15)
    #    Alto = entrambe subiscono spesso → probabile GG
    if home_team_doc and away_team_doc:
        h_hs_c = home_team_doc.get('ranking', {}).get('homeStats', {})
        a_as_c = away_team_doc.get('ranking', {}).get('awayStats', {})
        hp_c, ap_c = h_hs_c.get('played', 0), a_as_c.get('played', 0)
        if hp_c > 0 and ap_c > 0:
            # Gol subiti per partita: alto = difesa bucata = più probabile GG
            h_concede = h_hs_c.get('goalsAgainst', 0) / hp_c
            a_concede = a_as_c.get('goalsAgainst', 0) / ap_c
            # Media gol subiti: se entrambe subiscono ~1.5/partita → GG probabile
            avg_concede = (h_concede + a_concede) / 2
            # Scala 0-100: 0 gol/partita→0, 1.5 gol/partita→75, 2+→100
            btts_concede = min(100, (avg_concede / 2.0) * 100)
        else:
            btts_concede = 50
    else:
        btts_concede = 50

    # 8. NUOVO — Quota SNAI GG/NG come segnale (peso 0.20)
    #    Quota bassa = bookmaker convinto → segnale forte
    q_gg_raw = odds.get('gg')
    q_ng_raw = odds.get('ng')
    if q_gg_raw is not None and q_ng_raw is not None:
        q_gg_f = float(q_gg_raw)
        q_ng_f = float(q_ng_raw)
        # Probabilità implicita: 1/quota (normalizzata per overround)
        prob_gg = 1.0 / q_gg_f
        prob_ng = 1.0 / q_ng_f
        overround = prob_gg + prob_ng
        if overround > 0:
            btts_odds = (prob_gg / overround) * 100  # 0-100 (alto = GG probabile)
        else:
            btts_odds = 50
    else:
        btts_odds = 50  # Nessuna quota → neutro

    # Media pesata → 0-100 (alto = probabile BTTS/Goal)
    btts_total = (
        btts_h2h    * 0.18 +
        btts_exp_xg * 0.15 +
        btts_att    * 0.10 +
        btts_dna    * 0.07 +
        btts_both   * 0.07 +
        btts_strisce * 0.08 +
        btts_concede * 0.15 +
        btts_odds   * 0.20
    )

    # --- MOLTIPLICATORE STRISCE GG/NG (±5%, spinta finale) ---
    streak_adj_ggng = 0.0
    if home_name in _streak_cache and away_name in _streak_cache:
        h_data = _streak_cache[home_name]
        a_data = _streak_cache[away_name]
        adj_h_gg = get_streak_adjustment(h_data['total'], h_data['home'], 'GGNG')
        adj_a_gg = get_streak_adjustment(a_data['total'], a_data['away'], 'GGNG')
        streak_adj_ggng = (adj_h_gg + adj_a_gg) / 2
        if streak_adj_ggng != 0:
            btts_total = btts_total * (1 + streak_adj_ggng)
            btts_total = max(0.0, min(100.0, btts_total))
            print(f"   [STREAK GG/NG] Score: {btts_strisce:.0f}/100 | Molt: {streak_adj_ggng:+.2%}")

    # ====== CALCOLO SEPARATO NoGoal (segnali invertiti, pesi dedicati) ======
    nogoal_h2h     = 100 - btts_h2h        # storico NoGoal
    nogoal_exp_xg  = 100 - btts_exp_xg     # bassa pericolosità
    nogoal_att     = 100 - btts_att         # attacchi deboli
    nogoal_dna     = 100 - btts_dna         # DNA poco offensivo
    nogoal_both    = 20 if both_score else 70  # invertito
    nogoal_strisce = 100 - btts_strisce     # strisce NoGoal
    nogoal_concede = 100 - btts_concede     # squadre che NON subiscono
    nogoal_odds    = 100 - btts_odds        # probabilità implicita NG

    nogoal_total = (
        nogoal_h2h     * 0.18 +
        nogoal_exp_xg  * 0.05 +
        nogoal_att     * 0.12 +
        nogoal_dna     * 0.02 +
        nogoal_both    * 0.08 +
        nogoal_strisce * 0.08 +
        nogoal_concede * 0.22 +
        nogoal_odds    * 0.25
    )

    # Moltiplicatore strisce invertito per NoGoal (GG streaks → penalizza NoGoal)
    if streak_adj_ggng != 0:
        nogoal_total = nogoal_total * (1 - streak_adj_ggng)
        nogoal_total = max(0.0, min(100.0, nogoal_total))

    # ====== DECISIONE Goal/NoGoal (calcoli SEPARATI e INDIPENDENTI) ======
    BTTS_SOGLIA_GOAL_MIN = 60     # btts_total 60-64 → Goal
    BTTS_SOGLIA_GOAL_MAX = 64     # sopra → SKIP (segnali estremi)
    NOGOAL_SOGLIA = 56            # nogoal_total >= 56 → NoGoal (senza cap: più alto = meglio)

    if BTTS_SOGLIA_GOAL_MIN <= btts_total <= BTTS_SOGLIA_GOAL_MAX:
        tipo_gol_extra = 'Goal'
        confidence_gol_extra = round(btts_total, 1)
    elif nogoal_total >= NOGOAL_SOGLIA:
        tipo_gol_extra = 'NoGoal'
        confidence_gol_extra = round(nogoal_total, 1)
    else:
        tipo_gol_extra = None
        confidence_gol_extra = 0

    print(f"   [GG/NG v2] btts_total={btts_total:.1f} nogoal={nogoal_total:.1f} | "
          f"H2H={btts_h2h:.0f} ExpXG={btts_exp_xg:.0f} Att={btts_att:.0f} DNA={btts_dna:.0f} "
          f"Both={btts_both:.0f} Strisce={btts_strisce:.0f} Concede={btts_concede:.0f} "
          f"Odds={btts_odds:.0f} → {tipo_gol_extra or 'SKIP'}")

    # ====== RISOLUZIONE CONFLITTI: Over+NoGoal / Under+Goal ======
    # odds già caricato sopra per il segnale quote SNAI
    quota_map = {
        'Over 2.5': 'over_25', 'Over 1.5': 'over_15',
        'Under 2.5': 'under_25', 'Under 3.5': 'under_35',
        'Goal': 'gg', 'NoGoal': 'ng',
    }

    if tipo_gol and tipo_gol_extra:
        is_conflict = ('Over' in tipo_gol and tipo_gol_extra == 'NoGoal') or \
                      ('Under' in tipo_gol and tipo_gol_extra == 'Goal')
        if is_conflict:
            conf_ou = total  # Confidence Over/Under
            conf_gg = confidence_gol_extra  # Confidence Goal/NoGoal
            if abs(conf_ou - conf_gg) > 3:
                # Confidence diversa → vince la più alta
                if conf_ou >= conf_gg:
                    tipo_gol_extra = None
                    confidence_gol_extra = 0
                else:
                    tipo_gol = None
            else:
                # Parità confidence → confronta quote SNAI (la più bassa vince)
                q_ou = odds.get(quota_map.get(tipo_gol)) if tipo_gol in quota_map else None
                q_gg = odds.get(quota_map.get(tipo_gol_extra)) if tipo_gol_extra in quota_map else None
                if q_ou is not None and q_gg is not None:
                    if float(q_ou) <= float(q_gg):
                        tipo_gol_extra = None
                        confidence_gol_extra = 0
                    else:
                        tipo_gol = None
                elif q_ou is not None:
                    tipo_gol_extra = None
                    confidence_gol_extra = 0
                elif q_gg is not None:
                    tipo_gol = None
                else:
                    # Nessuna quota → O/U (6 segnali) batte GG/NG
                    tipo_gol_extra = None
                    confidence_gol_extra = 0

    # Blocco pronostico GOL se quota SNAI sotto 1.35 (ma analisi resta visibile)
    if tipo_gol and tipo_gol in quota_map:
        q = odds.get(quota_map[tipo_gol])
        if q is not None and float(q) < 1.35:
            tipo_gol = None
    if tipo_gol_extra and tipo_gol_extra in quota_map:
        q = odds.get(quota_map[tipo_gol_extra])
        if q is not None and float(q) < 1.35:
            tipo_gol_extra = None
            confidence_gol_extra = 0

    return {
        'score': round(total, 1),
        'tipo_gol': tipo_gol,
        'tipo_gol_extra': tipo_gol_extra,
        'confidence_gol_extra': confidence_gol_extra,
        'expected_total': round(expected_total, 2) if expected_total else None,
        'league_avg': league_avg,
        'dettaglio': scores,
        'directions': {
            'media_gol': mg_dir,
            'att_vs_def': avd_dir,
            'xg': xg_dir,
            'h2h_gol': h2h_dir,
            'media_lega': ml_dir,
            'dna_off_def': dna_dir
        },
        'h2h_patterns': h2h_patterns,
        'streak_adjustment_gol': round(streak_adj_gol * 100, 2),
        'streak_adjustment_ggng': round(streak_adj_ggng * 100, 2),
    }



# ==================== KELLY CRITERION — Probabilità Stimata e Stake ====================

def get_quota_segno(pronostico, match):
    """Recupera quota per SEGNO/DOPPIA_CHANCE. DC = quota sintetica."""
    odds = match.get('odds', {})
    if pronostico in ['1', '2', 'X']:
        v = float(odds.get(pronostico, 0))
        return v if v > 1.01 else None
    dc_map = {'1X': ('1', 'X'), 'X2': ('X', '2'), '12': ('1', '2')}
    pair = dc_map.get(pronostico)
    if pair:
        q1, q2 = float(odds.get(pair[0], 0)), float(odds.get(pair[1], 0))
        if q1 > 1 and q2 > 1:
            return round(1 / (1/q1 + 1/q2), 2)
    return None

def get_quota_gol(pronostico, match):
    """Recupera quota per GOL (Over/Under, Goal/NoGoal)."""
    odds = match.get('odds', {})
    mapping = {
        'over 2.5': 'over_25', 'under 2.5': 'under_25',
        'over 1.5': 'over_15', 'under 3.5': 'under_35',
        'goal': 'gg', 'nogoal': 'ng',
    }
    key = mapping.get(pronostico.lower())
    if key:
        v = float(odds.get(key, 0))
        return v if v > 1.01 else None
    return None

def calcola_probabilita_stimata(quota, dettaglio, tipo, directions=None):
    """
    Probabilità stimata per-match, per-pronostico.
    Modello PURO — nessun blend con mercato.
    Slope differenziata per tipo (SEGNO/DC/GOL), bonus a gradini.
    """
    # A) Probabilità mercato (solo per display, non per blend)
    if quota and quota > 1.01:
        p_market = (1.0 / quota) * 0.96
        p_market = min(p_market, 0.92)
        has_odds = True
    else:
        p_market = 0.50
        has_odds = False

    # B) Probabilità modello (segnali algoritmo)
    scores = [v for v in dettaglio.values() if isinstance(v, (int, float))]
    n = len(scores)
    if n == 0:
        p = round(p_market * 100, 1)
        return {'probabilita_stimata': p, 'prob_mercato': p, 'prob_modello': 50.0, 'has_odds': has_odds}

    avg = sum(scores) / n
    consensus = sum(1 for s in scores if s > 55) / n
    strong = sum(1 for s in scores if s > 70) / n
    variance = sum((s - avg) ** 2 for s in scores) / n
    std = variance ** 0.5

    # Consenso direzionale GOL
    dir_bonus = 0
    if directions:
        vals = [v for v in directions.values() if v != 'neutro']
        if vals:
            most = max(set(vals), key=vals.count)
            dir_ratio = vals.count(most) / len(vals)
            if dir_ratio > 0.70:
                dir_bonus = (dir_ratio - 0.70) * 0.12

    # Calcolo differenziato per tipo di mercato
    if tipo == 'SEGNO':
        p_model = 0.44 + (avg - 50) * 0.015
    elif tipo == 'DOPPIA_CHANCE':
        p_model = 0.52 + (avg - 50) * 0.018
    else:  # GOL (Over/Under, GG/NG)
        p_model = 0.42 + (avg - 50) * 0.013

    # Bonus consensus (a gradini)
    if consensus >= 0.80:
        p_model += 0.03
    elif consensus >= 0.70:
        p_model += 0.02
    elif consensus >= 0.60:
        p_model += 0.01

    # Bonus strong signals (a gradini)
    if strong >= 0.50:
        p_model += 0.03
    elif strong >= 0.35:
        p_model += 0.02

    # Direction bonus GOL + penalità varianza
    p_model += dir_bonus
    if std > 12:
        p_model -= (std - 12) * 0.003
    p_model = max(0.25, min(0.88, p_model))

    # Modello puro — nessun blend con il mercato
    p_final = p_model

    # Cap per tipo mercato
    caps = {
        'SEGNO': (0.30, 0.78), 'DOPPIA_CHANCE': (0.45, 0.88), 'GOL': (0.35, 0.80),
    }
    lo, hi = caps.get(tipo, (0.30, 0.85))
    p_final = max(lo, min(hi, p_final))

    return {
        'probabilita_stimata': round(p_final * 100, 1),
        'prob_mercato': round(p_market * 100, 1),
        'prob_modello': round(p_model * 100, 1),
        'has_odds': has_odds,
    }

def calcola_stake_kelly(quota, probabilita_stimata, tipo='GOL'):
    """Quarter Kelly Criterion — tutti i pronostici ricevono stake 1-10."""
    p = probabilita_stimata / 100
    if not quota or quota <= 1:
        return 1, 0.0  # Stake minimo anche senza quota
    edge = (p * quota - 1) * 100
    if (p * quota) <= 1:
        # Edge negativo → stake minimo (il modello ha già filtrato)
        return 1, round(edge, 2)
    full_kelly = (p * quota - 1) / (quota - 1)
    quarter_kelly = full_kelly / 4
    stake = min(max(round(quarter_kelly * 100), 1), 10)

    # Protezioni tipo-specifiche
    if tipo == 'SEGNO':
        if quota < 1.30:
            stake = min(stake, 2)   # Favorita fortissima
        elif quota < 1.50:
            stake = min(stake, 4)   # Favorita media
    if quota < 1.20:
        stake = min(stake, 2)       # Generale: quote bassissime
    if probabilita_stimata > 85:
        stake = min(stake, 3)       # Overconfidence protection
    if quota > 5.0:
        stake = min(stake, 2)       # Value trap protection
    return stake, round(edge, 2)


# ==================== FASE 4: DECISIONE FINALE ====================

def make_decision(segno_result, gol_result, is_cup=False):
    """
    Decide: SEGNO, GOL, SEGNO+GOL, o SCARTA.
    Include doppia chance (1X, X2, 12).
    Sotto soglia su entrambi = SCARTA.
    Coppe: soglia SEGNO abbassata a 55 (meno segnali disponibili).
    """
    s_score = segno_result['score']
    g_score = gol_result['score']

    # Soglia SEGNO ridotta per coppe (6 segnali su 9 a default neutro)
    CUP_THRESHOLD_SEGNO = 55
    threshold_segno = CUP_THRESHOLD_SEGNO if is_cup else THRESHOLD_INCLUDE

    # Sotto soglia su entrambi = SCARTA
    if s_score < threshold_segno and g_score < THRESHOLD_INCLUDE:
        return {
            'decision': 'SCARTA',
            'pronostici': [],
            'confidence_segno': s_score,
            'confidence_gol': g_score,
            'stars_segno': 0,
            'stars_gol': 0,
        }

    pronostici = []

    # Segno (bloccato se quota < 1.35, ma analisi resta visibile)
    if s_score >= threshold_segno and not segno_result.get('segno_blocked'):

        # === DIROTTAMENTO X FACTOR (2026-02-16) ===
        # Pattern storico: lucifero > affidabilita + quota > 1.60 → ~50% finisce in X
        # NON emettere SEGNO, lasciare che X Factor gestisca la partita
        lucif_score = segno_result.get('dettaglio', {}).get('lucifero', 0)
        affid_score = segno_result.get('dettaglio', {}).get('affidabilita', 0)
        odds_data = segno_result.get('odds', {})
        q1_raw = float(odds_data.get('1', 0) or 0)
        q2_raw = float(odds_data.get('2', 0) or 0)
        q_fav = min(q1_raw, q2_raw) if q1_raw > 0 and q2_raw > 0 else 0

        x_factor_divert = (lucif_score > affid_score and q_fav >= 1.60 and q_fav < 1.80)

        if not x_factor_divert:
            # Partita NON dirottata → check DC intelligente o SEGNO secco
            q_pred = odds_data.get(segno_result['segno'])
            dc = segno_result.get('doppia_chance')
            dc_quota = segno_result.get('doppia_chance_quota')
            q_pred_float = float(q_pred) if q_pred else 0

            # === DC INTELLIGENTE (2026-02-16) ===
            # Conf bassa + quota alta (ma non dirottata a XF) → solo DC se quota decente
            SOGLIA_CONF_DC = 65
            SOGLIA_QUOTA_DC = 1.60
            SOGLIA_QUOTA_MIN_DC = 1.35

            if s_score < SOGLIA_CONF_DC and q_pred_float > SOGLIA_QUOTA_DC:
                # Zona critica residua: conf bassa + quota alta
                if dc and dc_quota and dc_quota >= SOGLIA_QUOTA_MIN_DC:
                    pronostici.append({
                        'tipo': 'DOPPIA_CHANCE',
                        'pronostico': dc,
                        'quota': dc_quota,
                        'confidence': s_score,
                        'stars': calculate_stars(s_score),
                    })
                else:
                    # Fallback: DC non disponibile o quota troppo bassa → emetti SEGNO comunque
                    pronostici.append({
                        'tipo': 'SEGNO',
                        'pronostico': segno_result['segno'],
                        'quota': q_pred,
                        'confidence': s_score,
                        'stars': calculate_stars(s_score),
                    })
            else:
                # Conf alta OPPURE quota bassa → SEGNO secco
                pronostici.append({
                    'tipo': 'SEGNO',
                    'pronostico': segno_result['segno'],
                    'quota': q_pred,
                    'confidence': s_score,
                    'stars': calculate_stars(s_score),
                })

                # Doppia chance aggiuntiva (se disponibile e quota >= 1.30)
                if dc and dc_quota and dc_quota >= 1.30:
                    pronostici.append({
                        'tipo': 'DOPPIA_CHANCE',
                        'pronostico': dc,
                        'quota': dc_quota,
                        'confidence': s_score,
                        'stars': calculate_stars(s_score),
                    })
        # else: SEGNO skippato — X Factor processerà questa partita

    # Gol — Over/Under (usa g_score)
    if g_score >= THRESHOLD_INCLUDE and gol_result['tipo_gol']:
        pronostici.append({
            'tipo': 'GOL',
            'pronostico': gol_result['tipo_gol'],
            'confidence': g_score,
            'stars': calculate_stars(g_score),
        })

    # Gol — Goal/NoGoal (usa confidence separata)
    conf_gg = gol_result.get('confidence_gol_extra', 0)
    if conf_gg >= THRESHOLD_GGNG and gol_result['tipo_gol_extra']:
        pronostici.append({
            'tipo': 'GOL',
            'pronostico': gol_result['tipo_gol_extra'],
            'confidence': conf_gg,
            'stars': calculate_stars(conf_gg),
        })

    if not pronostici:
        return {
            'decision': 'SCARTA',
            'pronostici': [],
            'confidence_segno': s_score,
            'confidence_gol': g_score,
            'stars_segno': 0,
            'stars_gol': 0,
        }

    # Determina tipo decisione
    has_segno = any(p['tipo'] in ['SEGNO', 'DOPPIA_CHANCE'] for p in pronostici)
    has_gol = any(p['tipo'] == 'GOL' for p in pronostici)

    if has_segno and has_gol:
        decision = 'SEGNO+GOL'
    elif has_segno:
        decision = 'SEGNO'
    else:
        decision = 'GOL'

    return {
        'decision': decision,
        'pronostici': pronostici,
        'confidence_segno': s_score,
        'confidence_gol': g_score,
        'stars_segno': calculate_stars(s_score) if has_segno else 0,
        'stars_gol': calculate_stars(g_score) if has_gol else 0,
    }


def analyze_bomba(match_data, home_team_doc, away_team_doc):
    """
    Analizza le partite scartate per trovare possibili sorprese.
    Cerca segnali anomali a favore della sfavorita.
    """
    odds = match_data.get('odds', {})
    q1 = float(odds.get('1', 99))
    q2 = float(odds.get('2', 99))
    h2h = match_data.get('h2h_data', {})

    # Determina chi è la sfavorita
    if q1 > q2:
        # Casa è sfavorita
        sfavorita = match_data.get('home', '???')
        segno_bomba = '1'
        lucifero_sfi = h2h.get('lucifero_home', 12.5)
        lucifero_fav = h2h.get('lucifero_away', 12.5)
        trust_sfi = h2h.get('trust_home_letter', 'C')
        trust_fav = h2h.get('trust_away_letter', 'C')
        h2h_score_sfi = h2h.get('home_score', 5)
        h2h_score_fav = h2h.get('away_score', 5)
        mot_sfi_doc = home_team_doc
        mot_fav_doc = away_team_doc
    else:
        # Trasferta è sfavorita
        sfavorita = match_data.get('away', '???')
        segno_bomba = '2'
        lucifero_sfi = h2h.get('lucifero_away', 12.5)
        lucifero_fav = h2h.get('lucifero_home', 12.5)
        trust_sfi = h2h.get('trust_away_letter', 'C')
        trust_fav = h2h.get('trust_home_letter', 'C')
        h2h_score_sfi = h2h.get('away_score', 5)
        h2h_score_fav = h2h.get('home_score', 5)
        mot_sfi_doc = away_team_doc
        mot_fav_doc = home_team_doc

    # --- 1. BVS ANOMALO (25%) ---
    classification = h2h.get('classification', 'PURO')
    bvs_index = h2h.get('bvs_match_index', 0)

    if classification == 'NON_BVS':
        score_bvs = 80
        if bvs_index < -2:
            score_bvs = 95
    elif classification == 'SEMI':
        score_bvs = 50
        if bvs_index < 0:
            score_bvs = 65
    else:  # PURO
        score_bvs = 15  # BVS PURO = nessuna anomalia

    # --- 2. LUCIFERO SFAVORITA (30%) ---
    if lucifero_sfi >= 20:
        score_luc = 95
    elif lucifero_sfi >= 17:
        score_luc = 80
    elif lucifero_sfi >= 14:
        score_luc = 60
    elif lucifero_sfi >= 10:
        score_luc = 40
    else:
        score_luc = 15

    # Bonus se sfavorita ha Lucifero superiore alla favorita
    if lucifero_sfi > lucifero_fav:
        score_luc += 10

    score_luc = min(100, score_luc)

    # --- 3. MOTIVAZIONE SFAVORITA (20%) ---
    mot_sfi = 10
    if mot_sfi_doc:
        mot_sfi = mot_sfi_doc.get('stats', {}).get('motivation', None)
        if mot_sfi is None:
            mot_sfi = 10

    if mot_sfi >= 14:
        score_mot = 95
    elif mot_sfi >= 12:
        score_mot = 75
    elif mot_sfi >= 10:
        score_mot = 50
    else:
        score_mot = 20

    # --- 4. AFFIDABILITA BASSA ENTRAMBE (15%) ---
    trust_values = {'A': 1, 'B': 2, 'C': 3, 'D': 4}
    trust_fav_num = trust_values.get(trust_fav, 2)
    trust_sfi_num = trust_values.get(trust_sfi, 2)

    # Entrambe inaffidabili = partita imprevedibile = bomba
    if trust_fav_num >= 3 and trust_sfi_num >= 3:
        score_aff = 90  # Entrambe C o D
    elif trust_fav_num >= 3:
        score_aff = 70  # Favorita inaffidabile
    elif trust_fav_num == 2 and trust_sfi_num >= 3:
        score_aff = 40  # Solo sfavorita inaffidabile
    else:
        score_aff = 15  # Entrambe affidabili, nessuna sorpresa

    # --- 5. H2H SFAVORITA (10%) ---
    if h2h_score_sfi > h2h_score_fav + 2:
        score_h2h = 90
    elif h2h_score_sfi > h2h_score_fav:
        score_h2h = 70
    elif abs(h2h_score_sfi - h2h_score_fav) < 1:
        score_h2h = 50
    else:
        score_h2h = 20

    # --- PUNTEGGIO FINALE ---
    scores = {
        'bvs_anomalo': score_bvs,
        'lucifero_sfi': score_luc,
        'motivazione_sfi': score_mot,
        'affidabilita': score_aff,
        'h2h_sfi': score_h2h,
    }

    total = sum(scores[k] * PESI_BOMBA[k] for k in PESI_BOMBA)

    return {
        'score': round(total, 1),
        'sfavorita': sfavorita,
        'segno_bomba': segno_bomba,
        'dettaglio': scores,
    }

# ==================== FASE 5: GENERAZIONE COMMENTO ====================

def generate_comment(match_data, segno_result, gol_result, decision_result):
    """
    Genera commenti professionali per ogni pronostico usando il pool JSON.
    Restituisce un dict con un commento per ogni tipo di pronostico.
    """
    h2h = match_data.get('h2h_data', {})
    odds = match_data.get('odds', {})
    q1 = float(odds.get('1', 99))
    q2 = float(odds.get('2', 99))

    # Determina favorita/sfidante
    if q1 < q2:
        lucifero_fav = h2h.get('lucifero_home', 0)
        lucifero_sfi = h2h.get('lucifero_away', 0)
        trust_fav = h2h.get('trust_home_letter', 'C')
        trust_sfi = h2h.get('trust_away_letter', 'C')
        quota_fav = q1
    else:
        lucifero_fav = h2h.get('lucifero_away', 0)
        lucifero_sfi = h2h.get('lucifero_home', 0)
        trust_fav = h2h.get('trust_away_letter', 'C')
        trust_sfi = h2h.get('trust_home_letter', 'C')
        quota_fav = q2

    # Dati comuni per i placeholder
    home_team_doc = match_data.get('_home_team_doc', {}) or {}
    away_team_doc = match_data.get('_away_team_doc', {}) or {}
    h_scores = home_team_doc.get('scores', {})
    a_scores = away_team_doc.get('scores', {})
    dna_home = h2h.get('home_dna', {}) or {}
    dna_away = h2h.get('away_dna', {}) or {}

    placeholders = {
        'bvs_index': h2h.get('bvs_match_index', 0),
        'classification': h2h.get('classification', 'N/A'),
        'lucifero_fav': lucifero_fav,
        'lucifero_sfi': lucifero_sfi,
        'trust_fav': trust_fav,
        'trust_sfi': trust_sfi,
        'field_home': h2h.get('fattore_campo', {}).get('field_home', 0) if isinstance(h2h.get('fattore_campo'), dict) else h2h.get('field_home', 0),
        'h2h_score_fav': max(h2h.get('home_score', 5), h2h.get('away_score', 5)),
        'h2h_score_sfi': min(h2h.get('home_score', 5), h2h.get('away_score', 5)),
        'h2h_total': h2h.get('total_matches', 0),
        'mot_fav': (home_team_doc.get('stats', {}).get('motivation') or 10) if q1 < q2 else (away_team_doc.get('stats', {}).get('motivation') or 10),
        'mot_sfi': (away_team_doc.get('stats', {}).get('motivation') or 10) if q1 < q2 else (home_team_doc.get('stats', {}).get('motivation') or 10),
        'dna_fav': dna_home.get('val', 50) if q1 < q2 else dna_away.get('val', 50),
        'dna_sfi': dna_away.get('val', 50) if q1 < q2 else dna_home.get('val', 50),
        'quota_fav': quota_fav,
        'dc_tipo': segno_result.get('doppia_chance', ''),
        'dc_quota': segno_result.get('doppia_chance_quota', 0),
        'att_home': h_scores.get('attack_home', 0),
        'att_away': a_scores.get('attack_away', 0),
        'def_home': h_scores.get('defense_home', 0),
        'def_away': a_scores.get('defense_away', 0),
        'xg_combined': gol_result.get('expected_total', 0) or 0,
        'league_avg': gol_result.get('league_avg', 2.5),
        'h2h_avg_goals': h2h.get('avg_total_goals', 0),
        'h2h_over_pct': 0,
        'h2h_under_pct': 0,
        'h2h_btts_pct': 0,
        'h2h_nogoal_pct': 0,
        'dna_att_home': dna_home.get('att', 50),
        'dna_att_away': dna_away.get('att', 50),
        'dna_def_home': dna_home.get('def', 50),
        'dna_def_away': dna_away.get('def', 50),
    }

    # Calcola percentuali H2H gol se disponibili
    h2h_patterns = gol_result.get('h2h_patterns', {})
    if h2h_patterns:
        placeholders['h2h_over_pct'] = round(h2h_patterns.get('over25_pct', 0))
        placeholders['h2h_under_pct'] = round(100 - h2h_patterns.get('over25_pct', 50))
        placeholders['h2h_btts_pct'] = round(h2h_patterns.get('btts_pct', 0))
        placeholders['h2h_nogoal_pct'] = round(100 - h2h_patterns.get('btts_pct', 50))

    # Gestisci None nei placeholder
    for k, v in placeholders.items():
        if v is None:
            placeholders[k] = 0

    comments = {}

    # Commento per SEGNO
    if decision_result['confidence_segno'] >= THRESHOLD_INCLUDE:
        template = random.choice(COMMENTS_POOL.get('SEGNO', ['Analisi algoritmica']))
        try:
            comments['segno'] = template.format(**placeholders)
        except (KeyError, ValueError):
            comments['segno'] = 'Analisi algoritmica'

    # Commento per DOPPIA CHANCE
    dc = segno_result.get('doppia_chance')
    if dc and segno_result.get('doppia_chance_quota', 0) >= 1.30:
        template = random.choice(COMMENTS_POOL.get('DOPPIA_CHANCE', ['Copertura consigliata']))
        try:
            comments['doppia_chance'] = template.format(**placeholders)
        except (KeyError, ValueError):
            comments['doppia_chance'] = 'Copertura consigliata'

    # Commento per GOL
    if decision_result['confidence_gol'] >= THRESHOLD_INCLUDE:
        tipo_gol = gol_result.get('tipo_gol', '')
        if 'Over' in str(tipo_gol):
            pool_key = 'OVER'
        elif 'Under' in str(tipo_gol):
            pool_key = 'UNDER'
        else:
            pool_key = 'OVER'
        template = random.choice(COMMENTS_POOL.get(pool_key, ['Analisi algoritmica']))
        try:
            comments['gol'] = template.format(**placeholders)
        except (KeyError, ValueError):
            comments['gol'] = 'Analisi algoritmica'

        # Commento per Goal/NoGoal
        tipo_extra = gol_result.get('tipo_gol_extra', '')
        if tipo_extra == 'Goal':
            pool_key_extra = 'GOAL'
        elif tipo_extra == 'NoGoal':
            pool_key_extra = 'NOGOAL'
        else:
            pool_key_extra = None

        if pool_key_extra:
            template = random.choice(COMMENTS_POOL.get(pool_key_extra, ['Analisi algoritmica']))
            try:
                comments['gol_extra'] = template.format(**placeholders)
            except (KeyError, ValueError):
                comments['gol_extra'] = 'Analisi algoritmica'

    return comments

def generate_bomba_comment(match_data, bomba_result, home_team_doc, away_team_doc):
    """Genera commento per le bombe usando il pool JSON."""
    h2h = match_data.get('h2h_data', {})
    odds = match_data.get('odds', {})
    q1 = float(odds.get('1', 99))
    q2 = float(odds.get('2', 99))

    if q1 > q2:
        lucifero_sfi = h2h.get('lucifero_home', 0)
        lucifero_fav = h2h.get('lucifero_away', 0)
        trust_fav = h2h.get('trust_away_letter', 'C')
        trust_sfi = h2h.get('trust_home_letter', 'C')
        mot_sfi = (home_team_doc or {}).get('stats', {}).get('motivation') or 10
    else:
        lucifero_sfi = h2h.get('lucifero_away', 0)
        lucifero_fav = h2h.get('lucifero_home', 0)
        trust_fav = h2h.get('trust_home_letter', 'C')
        trust_sfi = h2h.get('trust_away_letter', 'C')
        mot_sfi = (away_team_doc or {}).get('stats', {}).get('motivation') or 10

    placeholders = {
        'bvs_index': h2h.get('bvs_match_index', 0),
        'classification': h2h.get('classification', 'N/A'),
        'lucifero_fav': lucifero_fav,
        'lucifero_sfi': lucifero_sfi,
        'trust_fav': trust_fav,
        'trust_sfi': trust_sfi,
        'mot_sfi': mot_sfi,
        'h2h_score_sfi': min(h2h.get('home_score', 5), h2h.get('away_score', 5)),
    }

    for k, v in placeholders.items():
        if v is None:
            placeholders[k] = 0

    template = random.choice(COMMENTS_POOL.get('BOMBA', ['Anomalia statistica rilevata']))
    try:
        return template.format(**placeholders)
    except (KeyError, ValueError):
        return 'Anomalia statistica rilevata'


# ==================== MAIN ====================

def run_daily_predictions(target_date=None):
    """Esegue l'intero processo di previsione giornaliera (SANDBOX)."""

    # Definisci la data target subito
    target_str = (target_date or datetime.now()).strftime('%Y-%m-%d')

    print("\n" + "=" * 70)
    print(f"🧪 DAILY PREDICTIONS SANDBOX - {target_str}")
    print("=" * 70)

    # Carica pesi da MongoDB (o usa default)
    load_tuning_config()

    print(f"   PESI_SEGNO: {PESI_SEGNO}")
    print(f"   PESI_GOL: {PESI_GOL}")
    print(f"   PESI_BOMBA: {PESI_BOMBA}")
    print(f"   SOGLIE: INCLUDE={THRESHOLD_INCLUDE}, HIGH={THRESHOLD_HIGH}, BOMBA={THRESHOLD_BOMBA}, GG/NG={THRESHOLD_GGNG}")

    # 1. Recupera partite del giorno
    matches = get_today_matches(target_date)

    # 1a. Recupera partite coppe europee (UCL/UEL)
    cup_matches = get_today_cup_matches(target_date)
    matches = matches + cup_matches

    if not matches:
        print("⚠️  Nessuna partita oggi.")
        return

    # 1b. Costruisci cache strisce per tutte le leghe delle partite di oggi
    leagues_today = set(m.get('_league', '') for m in matches if m.get('_league'))
    for league in leagues_today:
        build_streak_cache(league)
    print(f"   📊 Streak cache: {len(_streak_cache)} squadre da {len(leagues_today)} campionati")

    # 2. Analizza ogni partita
    results = []
    scartate = 0
    bombs = []

    for match in matches:
        home = match.get('home', '???')
        away = match.get('away', '???')
        league = match.get('_league', 'Unknown')

        print(f"\n{'─' * 50}")
        print(f"⚽ {home} vs {away} ({league})")

        # Recupera dati squadre + analisi (coppe: algoritmo dedicato)
        if match.get('_source') == 'cup':
            home_team_doc = None
            away_team_doc = None
            segno_result = analyze_cup_segno(match)
            gol_result = analyze_cup_gol(match, league)
        else:
            home_team_doc = get_team_data(home)
            away_team_doc = get_team_data(away)
            segno_result = analyze_segno(match, home_team_doc, away_team_doc)
            gol_result = analyze_gol(match, home_team_doc, away_team_doc, league)

        # FASE 4: Decisione
        is_cup = match.get('_source') == 'cup'
        decision = make_decision(segno_result, gol_result, is_cup=is_cup)
        match['_home_team_doc'] = home_team_doc
        match['_away_team_doc'] = away_team_doc
        # Salva risultati interni per X Factor (accessibili nel loop successivo)
        match['_segno_result'] = segno_result
        match['_gol_result'] = gol_result
        # FASE 5: Commento
        comment = generate_comment(match, segno_result, gol_result, decision)
        # Per coppe: usa commenti Sportradar al posto di quelli generati
        if match.get('_source') == 'cup':
            sr_comments = match.get('sportradar_h2h', {}).get('comments', [])
            if sr_comments:
                keys = ['segno', 'gol', 'doppia_chance', 'gol_extra']
                comment = {keys[i]: c for i, c in enumerate(sr_comments[:4])}
            else:
                comment = {}

        if decision['decision'] == 'SCARTA':
            print(f"   ❌ SCARTATA (Segno: {segno_result['score']}, Gol: {gol_result['score']})")
            scartate += 1

            # Analisi BOMBA sulle scartate
            bomba_result = analyze_bomba(match, home_team_doc, away_team_doc)
            if bomba_result['score'] >= THRESHOLD_BOMBA:
                print(f"   💣 BOMBA! {bomba_result['sfavorita']} ({bomba_result['score']}/100)")

                bomba_doc = {
                    'date': target_str,
                    'home': match.get('home', '???'),
                    'away': match.get('away', '???'),
                    'league': league,
                    'match_time': match.get('match_time', ''),
                    'sfavorita': bomba_result['sfavorita'],
                    'segno_bomba': bomba_result['segno_bomba'],
                    'confidence': bomba_result['score'],
                    'stars': calculate_stars(bomba_result['score']),
                    'dettaglio': bomba_result['dettaglio'],
                    'odds': match.get('odds', {}),
                    'comment': generate_bomba_comment(match, bomba_result, home_team_doc, away_team_doc),
                    'created_at': datetime.now(),
                }
                bombs.append(bomba_doc)

            continue

        # Stampa risultato
        print(f"   ✅ {decision['decision']}")
        for p in decision['pronostici']:
            print(f"      → {p['pronostico']} ({p['confidence']:.0f}/100, {p['stars']:.1f}⭐)")
        print(f"      💬 {comment}")

        # Cap confidence per coppe (dati Sportradar reali → cap 75)
        if is_cup:
            for p in decision['pronostici']:
                if p['confidence'] > CUP_CONF_CAP:
                    p['confidence'] = CUP_CONF_CAP
                    p['stars'] = calculate_stars(CUP_CONF_CAP)
            if decision['confidence_segno'] > CUP_CONF_CAP:
                decision['confidence_segno'] = CUP_CONF_CAP
                decision['stars_segno'] = calculate_stars(CUP_CONF_CAP)
            if decision['confidence_gol'] > CUP_CONF_CAP:
                decision['confidence_gol'] = CUP_CONF_CAP
                decision['stars_gol'] = calculate_stars(CUP_CONF_CAP)

        # KELLY: Arricchisci ogni pronostico con probabilità stimata, stake, edge
        for p in decision['pronostici']:
            tipo = p.get('tipo', '')
            pronostico = p.get('pronostico', '')
            if tipo in ('SEGNO', 'DOPPIA_CHANCE'):
                quota_prono = get_quota_segno(pronostico, match)
                det = segno_result.get('dettaglio', {})
                dirs = None
            else:  # GOL
                quota_prono = get_quota_gol(pronostico, match)
                det = gol_result.get('dettaglio', {})
                dirs = gol_result.get('directions', {})

            prob_result = calcola_probabilita_stimata(quota_prono, det, tipo, dirs)
            stake, edge = calcola_stake_kelly(quota_prono, prob_result['probabilita_stimata'], tipo)

            p['quota'] = p.get('quota') or quota_prono
            p['probabilita_stimata'] = prob_result['probabilita_stimata']
            p['prob_mercato'] = prob_result['prob_mercato']
            p['prob_modello'] = prob_result['prob_modello']
            p['has_odds'] = prob_result['has_odds']
            p['stake'] = stake
            p['edge'] = edge

            if stake > 0:
                print(f"      💰 {pronostico}: stake {stake}/10 (edge {edge:+.1f}%, prob {prob_result['probabilita_stimata']:.1f}%)")

        # Prepara documento per DB
        prediction_doc = {
            'date': target_str,
            'home': home,
            'away': away,
            'league': league,
            'match_time': match.get('match_time', ''),
            'home_mongo_id': match.get('home_mongo_id', ''),
            'away_mongo_id': match.get('away_mongo_id', ''),
            'is_cup': is_cup,
            'decision': decision['decision'],
            'pronostici': decision['pronostici'],
            'confidence_segno': decision['confidence_segno'],
            'confidence_gol': decision['confidence_gol'],
            'stars_segno': decision['stars_segno'],
            'stars_gol': decision['stars_gol'],
            'comment': comment,
            'odds': match.get('odds', {}),
            'segno_dettaglio': segno_result['dettaglio'],
            'gol_dettaglio': gol_result['dettaglio'],
            'gol_directions': gol_result.get('directions', {}),
            'expected_total_goals': gol_result.get('expected_total'),
            'league_avg_goals': gol_result.get('league_avg'),
            'segno_dettaglio_raw': segno_result.get('dettaglio_raw', {}),
            'streak_adjustment_segno': segno_result.get('streak_adjustment_segno', 0),
            'streak_adjustment_gol': gol_result.get('streak_adjustment_gol', 0),
            'streak_adjustment_ggng': gol_result.get('streak_adjustment_ggng', 0),
            'streak_home': _streak_cache.get(home, {}).get('total', {}),
            'streak_away': _streak_cache.get(away, {}).get('total', {}),
            'streak_home_context': _streak_cache.get(home, {}).get('home', {}),
            'streak_away_context': _streak_cache.get(away, {}).get('away', {}),
            'created_at': datetime.now(),
        }

        # Aggiungi cup_dettaglio per partite coppa
        if is_cup:
            sr = match.get('sportradar_h2h', {})
            prediction_doc['cup_dettaglio'] = {
                'sportradar_available': bool(sr),
                'segno_dettaglio': segno_result.get('dettaglio', {}),
                'segno_dettaglio_raw': segno_result.get('dettaglio_raw', {}),
                'gol_dettaglio': gol_result.get('dettaglio', {}),
                'forma_home_letters': sr.get('home_form', []),
                'forma_away_letters': sr.get('away_form', []),
                'position_home': sr.get('home_position'),
                'position_away': sr.get('away_position'),
                'h2h_record': f"{sr.get('h2h_home_wins', 0)}-{sr.get('h2h_draws', 0)}-{sr.get('h2h_away_wins', 0)}",
                'comments': sr.get('comments', []),
            }

        results.append(prediction_doc)

    # ==================== FASE X FACTOR (SANDBOX) ====================
    x_factor_results = []
    print(f"\n{'─' * 50}")
    print(f"🎯 FASE X FACTOR — Analisi pareggi su {len(matches)} partite")

    for match in matches:
        xf = calculate_x_factor(match)
        if xf is None:
            continue

        home = match.get('home', '???')
        away = match.get('away', '???')
        league = match.get('_league', 'Unknown')

        print(f"   ✖️  {home} vs {away} — conf {xf['confidence']}% ({xf['n_signals']} segnali)")

        xf_doc = {
            'date': target_str,
            'home': home,
            'away': away,
            'league': league,
            'match_time': match.get('match_time', ''),
            'home_mongo_id': match.get('home_mongo_id', ''),
            'away_mongo_id': match.get('away_mongo_id', ''),
            'is_x_factor': True,
            'decision': 'X_FACTOR',
            'pronostici': [{
                'tipo': 'X_FACTOR',
                'pronostico': 'X',
                'quota': xf['quota_x'],
                'confidence': xf['confidence'],
                'stars': calculate_stars(xf['confidence']),
            }],
            'confidence_segno': xf['confidence'],
            'confidence_gol': 0,
            'stars_segno': calculate_stars(xf['confidence']),
            'stars_gol': 0,
            'x_factor_signals': xf['signals'],
            'x_factor_n_signals': xf['n_signals'],
            'x_factor_raw_score': xf['raw_score'],
            'odds': match.get('odds', {}),
            'comment': f"X Factor: {xf['n_signals']} segnali attivi",
            'created_at': datetime.now(),
        }
        x_factor_results.append(xf_doc)

    if x_factor_results:
        print(f"   🎯 X Factor trovate: {len(x_factor_results)}")
    else:
        print(f"   🎯 Nessuna partita X Factor oggi")

    # ==================== FASE RISULTATO ESATTO (SANDBOX) ====================
    exact_score_results = []
    print(f"\n{'─' * 50}")
    print(f"🎯 FASE RISULTATO ESATTO — Analisi su {len(matches)} partite")

    for match in matches:
        es = calculate_exact_score(match)
        if es is None:
            continue

        home = match.get('home', '???')
        away = match.get('away', '???')
        league = match.get('_league', 'Unknown')

        top3_str = ', '.join([f"{s['score']} ({s['prob']:.1f}%)" for s in es['top_3']])
        print(f"   🎯 {home} vs {away} — conf {es['confidence']}% | {top3_str}")

        es_doc = {
            'date': target_str,
            'home': home,
            'away': away,
            'league': league,
            'match_time': match.get('match_time', ''),
            'home_mongo_id': match.get('home_mongo_id', ''),
            'away_mongo_id': match.get('away_mongo_id', ''),
            'is_exact_score': True,
            'decision': 'RISULTATO_ESATTO',
            'pronostici': [{
                'tipo': 'RISULTATO_ESATTO',
                'pronostico': es['top_3'][0]['score'],
                'confidence': es['confidence'],
                'stars': calculate_stars(es['confidence']),
                'top_3': es['top_3'],
            }],
            'confidence_segno': es['confidence'],
            'confidence_gol': 0,
            'stars_segno': calculate_stars(es['confidence']),
            'stars_gol': 0,
            'exact_score_top3': es['top_3'],
            'exact_score_gap': es['gap'],
            'odds': match.get('odds', {}),
            'comment': f"RE: {es['top_3'][0]['score']} ({es['top_3'][0]['prob']:.1f}%)",
            'created_at': datetime.now(),
        }
        exact_score_results.append(es_doc)

    if exact_score_results:
        print(f"   🎯 Risultato Esatto trovati: {len(exact_score_results)}")
    else:
        print(f"   🎯 Nessun Risultato Esatto oggi")

    # 3. Salva nel DB (SANDBOX)
    all_results = results + x_factor_results + exact_score_results

    if all_results:
        # Cancella previsioni vecchie per oggi
        predictions_collection.delete_many({'date': target_str})

        # Inserisci tutte (normali + X Factor + Risultato Esatto)
        predictions_collection.insert_many(all_results)

        print(f"\n{'=' * 70}")
        print(f"🧪 SANDBOX COMPLETATO!")
        print(f"   📊 Partite analizzate: {len(matches)}")
        print(f"   ✅ Pronostici salvati: {len(results)} (su daily_predictions_sandbox)")
        print(f"   🎯 X Factor salvati: {len(x_factor_results)}")
        print(f"   🎯 Risultato Esatto salvati: {len(exact_score_results)}")
        print(f"   ❌ Scartate: {scartate}")
        print(f"   📅 Data: {target_str}")
        print(f"{'=' * 70}\n")
    else:
        print(f"\n⚠️  Nessuna partita ha superato i filtri oggi.")

    # Salva bombe (SANDBOX)
    if bombs:

        bombs_collection.delete_many({'date': target_str})
        bombs_collection.insert_many(bombs)
        print(f"   💣 Bombe salvate: {len(bombs)} (su daily_bombs_sandbox)")
    else:
        print(f"   💣 Nessuna bomba oggi")



# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    for i in range(7):  # 0=oggi, 1=domani, 2=dopodomani, ... 6=tra 6 giorni
        target = datetime.now() + timedelta(days=i)
        print("\n" + "=" * 70)
        print(f"🧪 ELABORAZIONE SANDBOX: {target.strftime('%Y-%m-%d')}")
        print("=" * 70)
        run_daily_predictions(target_date=target)
