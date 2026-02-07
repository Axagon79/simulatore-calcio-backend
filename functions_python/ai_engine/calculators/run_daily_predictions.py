"""
DAILY PREDICTIONS - Algoritmo di Scrematura e Pronostici
=========================================================
Script schedulato che ogni giorno:
1. Raccoglie tutte le partite "Scheduled" del giorno
2. Analizza ogni partita con tutti i calcolatori
3. Decide: SEGNO, GOL, SEGNO+GOL, o SCARTA
4. Salva i risultati in 'daily_predictions'
"""

import os
import sys
import math
from datetime import datetime, timedelta, timezone

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
predictions_collection = db['daily_predictions']
bombs_collection = db['daily_bombs']

# ==================== COSTANTI ====================

# Soglie decisione
THRESHOLD_INCLUDE = 60      # Sotto 60 = SCARTA
THRESHOLD_HIGH = 70         # Sopra 70 = confidence alta

# Pesi FASE SEGNO (totale 100%)
PESI_SEGNO = {
    'bvs':           0.25,
    'quote':         0.18,
    'lucifero':      0.18,
    'affidabilita':  0.14,
    'dna':           0.08,
    'motivazioni':   0.08,
    'h2h':           0.05,
    'campo':         0.04,
}

# Pesi FASE GOL (totale 100%)
PESI_GOL = {
    'media_gol':     0.25,
    'att_vs_def':    0.22,
    'xg':            0.20,
    'h2h_gol':       0.15,
    'media_lega':    0.10,
    'dna_off_def':   0.08,
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


# ==================== FASE 1: RACCOLTA DATI ====================

def get_today_matches(target_date=None):
    """Recupera tutte le partite del giorno da h2h_by_round (qualsiasi status)."""
    if target_date:
        today = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
    else:
        today, tomorrow = get_today_range()
    
    matches = []
    
    # Cerca in tutti i documenti h2h_by_round
    all_rounds = h2h_collection.find({})
    
    for round_doc in all_rounds:
        league = round_doc.get('league', 'Unknown')
        
        for match in round_doc.get('matches', []):
            date_obj = match.get('date_obj')
            if not date_obj:
                continue
            
            # Controlla se la partita è nel giorno target (qualsiasi status)
            if isinstance(date_obj, datetime):
                if today <= date_obj < tomorrow:
                    match['_league'] = league
                    match['_round_id'] = round_doc.get('_id')
                    matches.append(match)
    
    print(f"\n📅 Trovate {len(matches)} partite per {today.strftime('%Y-%m-%d')}")
    return matches


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
    scores = {
        'bvs': score_bvs(match_data),
        'quote': score_quote(match_data),
        'lucifero': score_lucifero(match_data),
        'affidabilita': score_affidabilita(match_data),
        'dna': score_dna(match_data),
        'motivazioni': score_motivazioni(match_data, home_team_doc, away_team_doc),
        'h2h': score_h2h(match_data),
        'campo': score_campo(match_data),
    }
    
    # Media pesata
    total = sum(scores[k] * PESI_SEGNO[k] for k in PESI_SEGNO)
    
    # Determina QUALE segno
    odds = match_data.get('odds', {})
    q1 = float(odds.get('1', 99))
    qx = float(odds.get('X', 99))
    q2 = float(odds.get('2', 99))
    
    # Blocco segno se quota favorita sotto 1.35
    q_fav = min(q1, q2)
    if q_fav < 1.35:
        total = 0
    
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
    # Si consiglia quando le quote 1 e 2 sono vicine e il pareggio è alto
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
        'dettaglio_raw': dettaglio_raw
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
        return 50, 'neutro'
    
    h_scores = home_team_doc.get('scores', {})
    a_scores = away_team_doc.get('scores', {})
    
    # Attacco casa vs difesa trasferta
    att_home = h_scores.get('attack_home', 7.5)   # 0-15
    def_away = a_scores.get('defense_away', 5.0)   # 0-10
    
    # Attacco trasferta vs difesa casa
    att_away = a_scores.get('attack_away', 7.5)    # 0-15
    def_home = h_scores.get('defense_home', 5.0)   # 0-10
    
    # Mismatch 1: Attacco casa vs Difesa trasferta
    # att_home su scala 0-15, def_away su scala 0-10
    # Normalizzo entrambi su 0-100
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
        return 50, 'neutro'
    
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
    
    return round(max(0, min(100, score)), 1), direction


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
    mg_score, mg_dir, expected_total, both_score = score_media_gol(home_team_doc, away_team_doc, match_data)
    avd_score, avd_dir, both_att_strong = score_att_vs_def(home_team_doc, away_team_doc)
    xg_score, xg_dir = score_xg(home_team_doc, away_team_doc, league_name)
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
    }
    
    # Media pesata
    total = sum(scores[k] * PESI_GOL[k] for k in PESI_GOL)
    
    # Determina direzione prevalente
    directions = [mg_dir, avd_dir, xg_dir, h2h_dir, ml_dir, dna_dir]
    over_count = directions.count('over')
    under_count = directions.count('under')
    
    # Determina tipo pronostico GOL
    if over_count > under_count:
        # Over — ma quale? 1.5 o 2.5?
        if expected_total >= 2.8:
            tipo_gol = 'Over 2.5'
        else:
            tipo_gol = 'Over 1.5'
        
        # Goal/NoGoal
        btts_confidence = h2h_patterns.get('btts_pct', 50) if isinstance(h2h_patterns, dict) else 50
        if (both_score or both_att_strong) and btts_confidence >= 55:
            tipo_gol_extra = 'Goal'
        elif btts_confidence < 35:
            tipo_gol_extra = 'NoGoal'
        else:
            tipo_gol_extra = None
            
    elif under_count > over_count:
        if expected_total <= 2.0:
            tipo_gol = 'Under 2.5'
        else:
            tipo_gol = 'Under 3.5'
        
        btts_confidence = h2h_patterns.get('btts_pct', 50) if isinstance(h2h_patterns, dict) else 50
        if btts_confidence < 40:
            tipo_gol_extra = 'NoGoal'
        else:
            tipo_gol_extra = None
    else:
        tipo_gol = None
        tipo_gol_extra = None
    
    return {
        'score': round(total, 1),
        'tipo_gol': tipo_gol,
        'tipo_gol_extra': tipo_gol_extra,
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
    }
    


# ==================== FASE 4: DECISIONE FINALE ====================

def make_decision(segno_result, gol_result):
    """
    Decide: SEGNO, GOL, SEGNO+GOL, o SCARTA.
    Include doppia chance (1X, X2, 12).
    Sotto 60 su entrambi = SCARTA.
    """
    s_score = segno_result['score']
    g_score = gol_result['score']
    
    # Sotto 60 su entrambi = SCARTA
    if s_score < THRESHOLD_INCLUDE and g_score < THRESHOLD_INCLUDE:
        return {
            'decision': 'SCARTA',
            'pronostici': [],
            'confidence_segno': s_score,
            'confidence_gol': g_score,
            'stars_segno': 0,
            'stars_gol': 0,
        }
    
    pronostici = []
    
    # Segno
    if s_score >= THRESHOLD_INCLUDE:
        pronostici.append({
            'tipo': 'SEGNO',
            'pronostico': segno_result['segno'],
            'quota': segno_result.get('odds', {}).get(segno_result['segno']),
            'confidence': s_score,
            'stars': calculate_stars(s_score),
        })
        
        # Doppia chance (se disponibile e quota >= 1.30)
        dc = segno_result.get('doppia_chance')
        dc_quota = segno_result.get('doppia_chance_quota')
        if dc and dc_quota and dc_quota >= 1.30:
            pronostici.append({
                'tipo': 'DOPPIA_CHANCE',
                'pronostico': dc,
                'quota': dc_quota,
                'confidence': s_score,
                'stars': calculate_stars(s_score),
            })
    
    # Gol
    if g_score >= THRESHOLD_INCLUDE:
        if gol_result['tipo_gol']:
            pronostici.append({
                'tipo': 'GOL',
                'pronostico': gol_result['tipo_gol'],
                'confidence': g_score,
                'stars': calculate_stars(g_score),
            })
        if gol_result['tipo_gol_extra']:
            pronostici.append({
                'tipo': 'GOL',
                'pronostico': gol_result['tipo_gol_extra'],
                'confidence': g_score,
                'stars': calculate_stars(g_score),
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
    """Esegue l'intero processo di previsione giornaliera."""
    
    # Definisci la data target subito
    target_str = (target_date or datetime.now()).strftime('%Y-%m-%d')
    
    print("\n" + "=" * 70)
    print(f"🔮 DAILY PREDICTIONS - {target_str}")
    print("=" * 70)
    
    # 1. Recupera partite del giorno
    matches = get_today_matches(target_date)
    
    if not matches:
        print("⚠️  Nessuna partita oggi.")
        return
    
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
        
        # Recupera dati squadre
        home_team_doc = get_team_data(home)
        away_team_doc = get_team_data(away)
        
        # FASE 2: Analisi Segno
        segno_result = analyze_segno(match, home_team_doc, away_team_doc)
        
        # FASE 3: Analisi Gol
        gol_result = analyze_gol(match, home_team_doc, away_team_doc, league)
        
        # FASE 4: Decisione
        decision = make_decision(segno_result, gol_result)
        match['_home_team_doc'] = home_team_doc
        match['_away_team_doc'] = away_team_doc
        # FASE 5: Commento
        comment = generate_comment(match, segno_result, gol_result, decision)
        
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
        
        # Prepara documento per DB
        prediction_doc = {
            'date': target_str,
            'home': home,
            'away': away,
            'league': league,
            'match_time': match.get('match_time', ''),
            'home_mongo_id': match.get('home_mongo_id', ''),
            'away_mongo_id': match.get('away_mongo_id', ''),
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
            'created_at': datetime.now(),
        }
        
        results.append(prediction_doc)
    
    # 3. Salva nel DB
    if results:
        # Cancella previsioni vecchie per oggi
        
        predictions_collection.delete_many({'date': target_str})
        
        # Inserisci nuove
        predictions_collection.insert_many(results)
        
        print(f"\n{'=' * 70}")
        print(f"✅ COMPLETATO!")
        print(f"   📊 Partite analizzate: {len(matches)}")
        print(f"   ✅ Pronostici salvati: {len(results)}")
        print(f"   ❌ Scartate: {scartate}")
        print(f"   📅 Data: {target_str}")
        print(f"{'=' * 70}\n")
    else:
        print(f"\n⚠️  Nessuna partita ha superato i filtri oggi.")

    # Salva bombe
    if bombs:
        
        bombs_collection.delete_many({'date': target_str})
        bombs_collection.insert_many(bombs)
        print(f"   💣 Bombe salvate: {len(bombs)}")
    else:
        print(f"   💣 Nessuna bomba oggi")
    


# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    for i in range(7):  # 0=oggi, 1=domani, 2=dopodomani, ... 6=tra 6 giorni
        target = datetime.now() + timedelta(days=i)
        print("\n" + "=" * 70)
        print(f"📅 ELABORAZIONE: {target.strftime('%Y-%m-%d')}")
        print("=" * 70)
        run_daily_predictions(target_date=target)