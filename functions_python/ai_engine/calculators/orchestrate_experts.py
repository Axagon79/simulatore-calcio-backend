"""
MIXTURE OF EXPERTS — Orchestratore
===================================
Legge pronostici dai 3 sistemi (A, C, S), applica routing per mercato,
scrive in daily_predictions_unified.

Ogni sistema è "esperto" solo nei mercati dove ha il miglior HR.
L'orchestratore NON calcola nulla — seleziona e combina.

Uso:
  python orchestrate_experts.py                    # oggi
  python orchestrate_experts.py 2026-02-18         # data specifica
  python orchestrate_experts.py --backfill 2026-02-11 2026-02-19  # range
"""

import sys
import os
import math
import argparse
from datetime import datetime, timedelta, timezone
from copy import deepcopy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from config import db

# =====================================================
# CONFIGURAZIONE ROUTING
# =====================================================
COLLECTIONS = {
    'A': 'daily_predictions',
    'C': 'daily_predictions_engine_c',
    'S': 'daily_predictions_sandbox',
}

# Tabella routing definitiva (validata con analisi overlap 11-18 feb)
ROUTING = {
    '1X2':       {'systems': ['C'], 'rule': 'single'},
    'DC':        {'systems': ['A', 'S'], 'rule': 'consensus_both'},
    'OVER_1.5':  {'systems': ['A', 'S'], 'rule': 'consensus_both'},
    'OVER_2.5':  {'systems': ['A', 'S'], 'rule': 'consensus_both'},
    'OVER_3.5':  {'systems': ['C'], 'rule': 'single'},
    'UNDER_2.5': {'systems': ['A'], 'rule': 'single'},
    'UNDER_3.5': {'systems': ['A', 'S'], 'rule': 'union'},
    'GG':        {'systems': ['S', 'C'], 'rule': 'priority_chain'},
    'NG':        {'systems': ['A', 'C', 'S'], 'rule': 'combo_under_segno'},
}

# Campi da copiare dal documento sorgente (livello match)
MATCH_FIELDS = [
    'home', 'away', 'date', 'league', 'match_time',
    'home_mongo_id', 'away_mongo_id', 'is_cup', 'odds',
    'confidence_segno', 'confidence_gol', 'stars_segno', 'stars_gol',
]

ROUTING_VERSION = '1.0'


# =====================================================
# MULTI-GOAL — Poisson + Lambda zones
# =====================================================
MULTIGOL_ZONES = [
    {'lambda_min': 0,    'lambda_max': 2.00, 'range': '1-2', 'goals': [1, 2]},
    {'lambda_min': 2.00, 'lambda_max': 2.45, 'range': '1-3', 'goals': [1, 2, 3]},
    {'lambda_min': 2.45, 'lambda_max': 2.70, 'range': '2-3', 'goals': [2, 3]},
    {'lambda_min': 2.70, 'lambda_max': 3.00, 'range': '2-4', 'goals': [2, 3, 4]},
    {'lambda_min': 3.00, 'lambda_max': 99,   'range': '3-5', 'goals': [3, 4, 5]},
]
MULTIGOL_MARGINE = 0.88
MULTIGOL_QUOTA_MIN = 1.35


def _poisson(k, lamb):
    """Probabilità Poisson P(X=k) dato lambda."""
    return (math.exp(-lamb) * (lamb ** k)) / math.factorial(k)


def _calc_lambda(under_25_odds):
    """Calcola lambda totale dalla quota Under 2.5 (bisection Poisson)."""
    if not under_25_odds or under_25_odds <= 1.0:
        return None
    p_u25 = (1 / under_25_odds) * 1.06
    l_tot = 0.1
    while sum(_poisson(i, l_tot) for i in range(3)) > p_u25:
        l_tot += 0.005
        if l_tot > 10:
            return None
    return l_tot


def _score_to_sign(score_str):
    """Segno da score MC: '2-1' → '1', '1-1' → 'X', '0-2' → '2'"""
    if not score_str:
        return None
    parts = str(score_str).replace(':', '-').split('-')
    if len(parts) != 2:
        return None
    try:
        h, a = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if h > a: return '1'
    if h == a: return 'X'
    return '2'


def _apply_multigol(unified, odds):
    """
    Post-processing: sostituisce pronostici deboli con Multi-goal.
    Candidati: Over 1.5, Under 3.5, GG/NG con confidence 60-65.
    Logica: Poisson → lambda → zona MG → quota calcolata ≥ 1.35.
    """
    u25 = odds.get('under_25')
    if not u25:
        return unified
    try:
        u25_f = float(u25)
    except (TypeError, ValueError):
        return unified

    l_tot = _calc_lambda(u25_f)
    if l_tot is None:
        return unified

    # Probabilità per ogni numero di gol (0-10)
    probs = {g: _poisson(g, l_tot) for g in range(11)}

    # Trova zona MG in base a lambda
    zone = None
    for z in MULTIGOL_ZONES:
        if z['lambda_min'] <= l_tot < z['lambda_max']:
            zone = z
            break
    if not zone:
        return unified

    # Calcola prob e quota MG per questa zona
    mg_prob = sum(probs[g] for g in zone['goals'])
    mg_quota = round((1 / mg_prob) * MULTIGOL_MARGINE, 2) if mg_prob > 0 else 99

    # Filtro quota minima — se troppo bassa, non conviene
    if mg_quota < MULTIGOL_QUOTA_MIN:
        return unified

    # Scansiona pronostici e sostituisci i candidati
    result = []
    for p in unified:
        pron = p.get('pronostico', '')
        conf = p.get('confidence', 0)

        is_candidate = (
            pron == 'Over 1.5' or
            pron == 'Under 3.5' or
            (pron in ('Goal', 'NoGoal') and 60 <= conf <= 65)
        )

        if is_candidate:
            mg = {
                'tipo': 'GOL',
                'pronostico': f'MG {zone["range"]}',
                'confidence': conf,
                'stars': p.get('stars', 3.0),
                'quota': mg_quota,
                'probabilita_stimata': round(mg_prob * 100, 1),
                'has_odds': True,
                'source': p.get('source', '?') + '_mg',
                'routing_rule': 'multigol_v6',
                'multigol_detail': {
                    'lambda': round(l_tot, 3),
                    'zone': zone['range'],
                    'original': pron,
                    'mg_prob': round(mg_prob, 4),
                },
            }
            # Calcola stake con Kelly 3/4
            if mg_quota > 1.0:
                edge = mg_prob - (1.0 / mg_quota)
                if edge > 0:
                    kelly_fraction = 0.75
                    kelly = kelly_fraction * (edge * mg_quota - (1 - edge)) / (mg_quota - 1)
                    mg['stake'] = max(1, min(10, round(kelly * 10)))
                    mg['edge'] = round(edge * 100, 1)
                    mg['prob_mercato'] = round(100.0 / mg_quota, 1)
                    mg['prob_modello'] = round(mg_prob * 100, 1)
                else:
                    mg['stake'] = 1
                    mg['edge'] = 0
            else:
                mg['stake'] = 1
                mg['edge'] = 0
            result.append(mg)
        else:
            result.append(p)

    return result


def _apply_combo96_dc_flip(unified, odds, simulation_data):
    """
    Combo #96: se Pos1=2, Pos4=X, MC=2, Under 2.5, NG
    e quota DC X2 ≥ 1.35 → sostituisce SEGNO 2 con DC X2.
    Backtest: 12 partite con DC X2 ≥1.35 → 100% HR, +55.6% yield.
    """
    if not simulation_data or not odds:
        return unified

    top_scores = simulation_data.get('top_scores', [])
    if len(top_scores) < 4:
        return unified

    # Check 5 condizioni combo #96
    pos1 = _score_to_sign(top_scores[0][0])
    pos4 = _score_to_sign(top_scores[3][0])
    if pos1 != '2' or pos4 != 'X':
        return unified

    h_pct = simulation_data.get('home_win_pct', 0) or 0
    d_pct = simulation_data.get('draw_pct', 0) or 0
    a_pct = simulation_data.get('away_win_pct', 0) or 0
    if not (a_pct >= h_pct and a_pct >= d_pct):  # MC max = 2
        return unified

    o25 = simulation_data.get('over_25_pct', 0) or 0
    u25 = simulation_data.get('under_25_pct', 0) or 0
    if not (u25 > o25):  # Under
        return unified

    gg = simulation_data.get('gg_pct', 0) or 0
    ng = simulation_data.get('ng_pct', 0) or 0
    if not (ng > gg):  # NG
        return unified

    # Calcola quota DC X2
    q_x = float(odds.get('X', 0) or 0)
    q_2 = float(odds.get('2', 0) or 0)
    if q_x <= 1 or q_2 <= 1:
        return unified

    dc_quota = round(1 / (1/q_x + 1/q_2), 2)
    if dc_quota < 1.35:
        return unified  # Quota troppo bassa, tieni SEGNO 2

    # Trova SEGNO 2 e sostituisci con DC X2
    result = []
    flipped = False
    for p in unified:
        if p.get('tipo') == 'SEGNO' and p.get('pronostico') == '2' and not flipped:
            dc_pred = {
                'tipo': 'DOPPIA_CHANCE',
                'pronostico': 'X2',
                'quota': dc_quota,
                'confidence': p.get('confidence', 60),
                'stars': p.get('stars', 3.0),
                'source': p.get('source', '?') + '_combo96',
                'routing_rule': 'combo_96_dc_flip',
                'has_odds': True,
            }
            # Ricalcola stake/edge
            prob_est = p.get('probabilita_stimata', p.get('confidence', 60))
            prob_mod = prob_est / 100.0 if prob_est > 1 else prob_est
            prob_mkt = 1.0 / dc_quota
            edge = prob_mod - prob_mkt
            if edge > 0:
                kelly = 0.75 * (edge * dc_quota) / (dc_quota - 1)
                dc_pred['stake'] = max(1, min(10, round(kelly * 10)))
                dc_pred['edge'] = round(edge * 100, 1)
                dc_pred['prob_mercato'] = round(prob_mkt * 100, 1)
                dc_pred['prob_modello'] = round(prob_mod * 100, 1)
                dc_pred['probabilita_stimata'] = round(prob_mod * 100, 1)
            else:
                dc_pred['stake'] = 1
                dc_pred['edge'] = 0
            result.append(dc_pred)
            flipped = True
        else:
            result.append(p)

    if flipped:
        print(f"    ⚡ COMBO #96: SEGNO 2 → DC X2 @{dc_quota}")

    return result


# Combo che storicamente producono X (91.7% su 12 partite)
# Pattern: segnali 1X2 contraddittori + GG prevalente
X_DRAW_COMBOS = {3, 21, 32, 39, 45, 57, 59, 85}


def _apply_x_draw_combos(unified, odds, simulation_data):
    """
    Combo X-draw: quando i segnali MC sono contraddittori e GG prevale,
    il pareggio è molto probabile (91.7% storico su 12 partite).
    Sostituisce SEGNO 1/2 con SEGNO X, o aggiunge SEGNO X se assente.
    """
    if not simulation_data or not odds:
        return unified

    top_scores = simulation_data.get('top_scores', [])
    if len(top_scores) < 4:
        return unified

    # Calcola combo number
    pos1 = _score_to_sign(top_scores[0][0])
    pos4 = _score_to_sign(top_scores[3][0])
    if not pos1 or not pos4:
        return unified

    h_pct = simulation_data.get('home_win_pct', 0) or 0
    d_pct = simulation_data.get('draw_pct', 0) or 0
    a_pct = simulation_data.get('away_win_pct', 0) or 0
    if h_pct >= d_pct and h_pct >= a_pct:
        mc = '1'
    elif d_pct >= h_pct and d_pct >= a_pct:
        mc = 'X'
    else:
        mc = '2'

    o25 = simulation_data.get('over_25_pct', 0) or 0
    u25 = simulation_data.get('under_25_pct', 0) or 0
    ou = 'Over' if o25 >= u25 else 'Under'

    gg_pct = simulation_data.get('gg_pct', 0) or 0
    ng_pct = simulation_data.get('ng_pct', 0) or 0
    ggng = 'GG' if gg_pct >= ng_pct else 'NG'

    # Calcola numero combo
    s = {'1': 0, 'X': 1, '2': 2}
    ou_idx = 0 if ou == 'Over' else 1
    gg_idx = 0 if ggng == 'GG' else 1
    combo = s[pos1] * 36 + s[pos4] * 12 + s[mc] * 4 + ou_idx * 2 + gg_idx + 1

    if combo not in X_DRAW_COMBOS:
        return unified

    # Quota X
    q_x = float(odds.get('X', 0) or 0)
    if q_x <= 1:
        return unified

    # Cerca se c'è già un SEGNO e sostituiscilo, altrimenti aggiungi
    result = []
    replaced = False
    for p in unified:
        if p.get('tipo') == 'SEGNO' and not replaced:
            # Sostituisci SEGNO 1/2 con SEGNO X
            x_pred = {
                'tipo': 'SEGNO',
                'pronostico': 'X',
                'quota': q_x,
                'confidence': p.get('confidence', 55),
                'stars': p.get('stars', 3.0),
                'source': p.get('source', '?') + '_xdraw',
                'routing_rule': f'x_draw_combo_{combo}',
                'has_odds': True,
            }
            # Stake/edge
            prob_mod = 0.70  # stima conservativa (storico 91.7% ma campione piccolo)
            prob_mkt = 1.0 / q_x
            edge = prob_mod - prob_mkt
            if edge > 0:
                kelly = 0.75 * (edge * q_x) / (q_x - 1)
                x_pred['stake'] = max(1, min(10, round(kelly * 10)))
                x_pred['edge'] = round(edge * 100, 1)
                x_pred['prob_mercato'] = round(prob_mkt * 100, 1)
                x_pred['prob_modello'] = round(prob_mod * 100, 1)
                x_pred['probabilita_stimata'] = round(prob_mod * 100, 1)
            else:
                x_pred['stake'] = 1
                x_pred['edge'] = 0
            result.append(x_pred)
            replaced = True
        else:
            result.append(p)

    # Se non c'era un SEGNO, aggiungilo
    if not replaced:
        x_pred = {
            'tipo': 'SEGNO',
            'pronostico': 'X',
            'quota': q_x,
            'confidence': 55,
            'stars': 3.0,
            'source': 'MC_xdraw',
            'routing_rule': f'x_draw_combo_{combo}',
            'has_odds': True,
            'stake': 1,
            'edge': 0,
        }
        prob_mkt = 1.0 / q_x
        edge = 0.70 - prob_mkt
        if edge > 0:
            kelly = 0.75 * (edge * q_x) / (q_x - 1)
            x_pred['stake'] = max(1, min(10, round(kelly * 10)))
            x_pred['edge'] = round(edge * 100, 1)
            x_pred['prob_mercato'] = round(prob_mkt * 100, 1)
            x_pred['prob_modello'] = 70.0
            x_pred['probabilita_stimata'] = 70.0
        result.append(x_pred)

    print(f"    ⚡ COMBO X-DRAW #{combo}: → SEGNO X @{q_x}")
    return result


# =====================================================
# MAPPING PREDIZIONE → CHIAVE MERCATO
# =====================================================
def market_key(pred):
    """Mappa un pronostico alla chiave mercato del routing."""
    tipo = pred.get('tipo', '')
    pron = pred.get('pronostico', '')

    if tipo == 'SEGNO':
        return '1X2'
    if tipo == 'DOPPIA_CHANCE':
        return 'DC'
    if tipo == 'GOL':
        if 'Over' in pron:
            try:
                val = pron.split()[-1]
                return f'OVER_{val}'
            except:
                return None
        if 'Under' in pron:
            try:
                val = pron.split()[-1]
                return f'UNDER_{val}'
            except:
                return None
        if pron == 'Goal':
            return 'GG'
        if pron == 'NoGoal':
            return 'NG'
    # X_FACTOR e RISULTATO_ESATTO non sono nel routing
    return None


# =====================================================
# HELPERS PER NG COMBO
# =====================================================
def _has_under(preds_set):
    """True se il set contiene almeno un Under."""
    return any(mk.startswith('UNDER_') for mk in preds_set)


def _has_segno(preds_set):
    """True se il set contiene 1X2."""
    return '1X2' in preds_set


def _check_ng_combo(markets_by_sys):
    """
    Verifica le 6 condizioni Under+Segno cross-sistema.
    markets_by_sys: {'A': set di market_key, 'C': set, 'S': set}
    Restituisce True se almeno una condizione è soddisfatta.
    """
    a = markets_by_sys.get('A', set())
    c = markets_by_sys.get('C', set())
    s = markets_by_sys.get('S', set())

    # 1. A=Under + C=Segno
    if _has_under(a) and _has_segno(c):
        return True
    # 2. A=Under + S=Segno
    if _has_under(a) and _has_segno(s):
        return True
    # 3. A+S entrambi Under
    if _has_under(a) and _has_under(s):
        return True
    # 4. C=Under + A=Segno
    if _has_under(c) and _has_segno(a):
        return True
    # 5. S=Under + C=Segno
    if _has_under(s) and _has_segno(c):
        return True
    # 6. Almeno 2 sistemi Under
    under_count = sum(1 for sys_mks in [a, c, s] if _has_under(sys_mks))
    if under_count >= 2:
        return True

    return False


# =====================================================
# LOGICA ROUTING PER MERCATO
# =====================================================
def route_predictions(preds_by_sys, markets_by_sys):
    """
    Applica il routing e restituisce la lista di pronostici unified.

    preds_by_sys: {'A': {market_key: pred_dict}, 'C': {...}, 'S': {...}}
    markets_by_sys: {'A': set(market_keys), 'C': set, 'S': set}

    Restituisce: lista di pronostici con campo 'source' e 'routing_rule' aggiunti.
    """
    unified = []

    for mk, config in ROUTING.items():
        rule = config['rule']
        systems = config['systems']

        if rule == 'single':
            # Prendi dal sistema specificato
            sys_id = systems[0]
            pred = preds_by_sys.get(sys_id, {}).get(mk)
            if pred:
                p = deepcopy(pred)
                p['source'] = sys_id
                p['routing_rule'] = rule
                unified.append(p)

        elif rule == 'consensus_both':
            # Entrambi i sistemi devono emettere E concordare
            s1, s2 = systems[0], systems[1]
            p1 = preds_by_sys.get(s1, {}).get(mk)
            p2 = preds_by_sys.get(s2, {}).get(mk)
            if p1 and p2 and p1.get('pronostico') == p2.get('pronostico'):
                # Usa quello con confidence più alta
                winner = p1 if p1.get('confidence', 0) >= p2.get('confidence', 0) else p2
                source = s1 if winner is p1 else s2
                p = deepcopy(winner)
                p['source'] = f'{s1}+{s2}'
                p['routing_rule'] = rule
                unified.append(p)

        elif rule == 'union':
            # Pool: prendi da qualsiasi sistema nella lista (no duplicati per match)
            added = False
            for sys_id in systems:
                pred = preds_by_sys.get(sys_id, {}).get(mk)
                if pred and not added:
                    p = deepcopy(pred)
                    p['source'] = sys_id
                    p['routing_rule'] = rule
                    unified.append(p)
                    added = True

        elif rule == 'priority_chain':
            # Prova sistemi in ordine di priorità
            for sys_id in systems:
                pred = preds_by_sys.get(sys_id, {}).get(mk)
                if pred:
                    p = deepcopy(pred)
                    p['source'] = sys_id
                    p['routing_rule'] = rule
                    unified.append(p)
                    break

        elif rule == 'combo_under_segno':
            # Regola speciale NG: cross-sistema Under+Segno
            if _check_ng_combo(markets_by_sys):
                # NG combo attivata — crea pronostico derivato
                # Cerca quota NG dagli odds di qualsiasi sistema
                ng_quota = None
                for sys_id in ['A', 'C', 'S']:
                    pred = preds_by_sys.get(sys_id, {}).get('NG')
                    if pred and pred.get('quota'):
                        ng_quota = pred['quota']
                        break

                # NG combo DISABILITATO — HR troppo basso (37-42%)
                # TODO: creare algoritmo NG dedicato
                if True:  # sempre skip
                    continue

                p = {
                    'tipo': 'GOL',
                    'pronostico': 'NoGoal',
                    'confidence': 67,
                    'stars': 3.0,
                    'quota': ng_quota,
                    'probabilita_stimata': 67.0,
                    'has_odds': ng_quota is not None,
                    'source': 'MoE',
                    'routing_rule': rule,
                    'combo_detail': _get_combo_detail(markets_by_sys),
                }
                # Calcola stake se c'è quota
                if ng_quota and ng_quota > 1.0:
                    edge = (67.0 - (100.0 / ng_quota)) / 100.0
                    if edge > 0:
                        kelly_fraction = 0.75  # 3/4 Kelly
                        kelly = kelly_fraction * (edge * ng_quota - (1 - edge)) / (ng_quota - 1)
                        stake = max(1, min(10, round(kelly * 10)))
                        p['stake'] = stake
                        p['edge'] = round(edge * 100, 1)
                        p['prob_mercato'] = round(100.0 / ng_quota, 1)
                        p['prob_modello'] = 67.0
                    else:
                        p['stake'] = 1
                        p['edge'] = 0
                else:
                    p['stake'] = 1
                    p['edge'] = 0

                unified.append(p)

    # --- FLIP: Goal debole Sistema A → NoGoal ---
    # Se Sistema A ha Goal con confidence < 65, è segnale invertito (61.1% NoGoal reale)
    goal_a = preds_by_sys.get('A', {}).get('GG')
    if goal_a and goal_a.get('confidence', 0) < 65:
        # Rimuovi qualsiasi Goal dalla lista unified
        unified = [p for p in unified if p.get('pronostico') != 'Goal']
        # Cerca quota NoGoal dagli odds di qualsiasi sistema
        ng_quota = None
        for sys_id in ['A', 'C', 'S']:
            ng_pred = preds_by_sys.get(sys_id, {}).get('NG')
            if ng_pred and ng_pred.get('quota'):
                ng_quota = ng_pred['quota']
                break
        # Crea pronostico NoGoal derivato dal flip
        p = {
            'tipo': 'GOL',
            'pronostico': 'NoGoal',
            'confidence': 65,
            'stars': 3.0,
            'quota': ng_quota,
            'probabilita_stimata': 61.0,
            'has_odds': ng_quota is not None,
            'source': 'A_flip',
            'routing_rule': 'goal_flip',
        }
        # Calcola stake se c'è quota
        if ng_quota and ng_quota > 1.0:
            edge = (61.0 - (100.0 / ng_quota)) / 100.0
            if edge > 0:
                kelly_fraction = 0.75
                kelly = kelly_fraction * (edge * ng_quota - (1 - edge)) / (ng_quota - 1)
                stake = max(1, min(10, round(kelly * 10)))
                p['stake'] = stake
                p['edge'] = round(edge * 100, 1)
                p['prob_mercato'] = round(100.0 / ng_quota, 1)
                p['prob_modello'] = 61.0
            else:
                p['stake'] = 1
                p['edge'] = 0
        else:
            p['stake'] = 1
            p['edge'] = 0
        unified.append(p)

    # --- DEDUP: Goal vs NoGoal mutualmente esclusivi ---
    # Se entrambi presenti = conflitto → rimuovi ENTRAMBI (match incerto)
    gg_list = [p for p in unified if p.get('pronostico') == 'Goal']
    ng_list = [p for p in unified if p.get('pronostico') == 'NoGoal']
    if gg_list and ng_list:
        unified = [p for p in unified if p.get('pronostico') not in ('Goal', 'NoGoal')]

    return unified


def _get_combo_detail(markets_by_sys):
    """Restituisce quali condizioni NG combo sono attive."""
    a = markets_by_sys.get('A', set())
    c = markets_by_sys.get('C', set())
    s = markets_by_sys.get('S', set())
    details = []
    if _has_under(a) and _has_segno(c): details.append('A=Under+C=Segno')
    if _has_under(a) and _has_segno(s): details.append('A=Under+S=Segno')
    if _has_under(a) and _has_under(s): details.append('A+S=Under')
    if _has_under(c) and _has_segno(a): details.append('C=Under+A=Segno')
    if _has_under(s) and _has_segno(c): details.append('S=Under+C=Segno')
    under_count = sum(1 for sys_mks in [a, c, s] if _has_under(sys_mks))
    if under_count >= 2: details.append('2+Under')
    return details


# =====================================================
# ORCHESTRAZIONE PRINCIPALE
# =====================================================
def orchestrate_date(date_str, dry_run=False):
    """
    Orchestrazione per una singola data.
    Ritorna il numero di documenti scritti.
    """
    # 1. Carica pronostici dai 3 sistemi
    docs_by_sys = {}
    for sys_id, coll_name in COLLECTIONS.items():
        docs = list(db[coll_name].find({'date': date_str}))
        idx = {}
        for doc in docs:
            # Salta documenti RISULTATO_ESATTO (duplicati con comment stringa)
            if doc.get('decision') == 'RISULTATO_ESATTO':
                continue
            key = doc.get('home', '') + '__' + doc.get('away', '')
            if key in idx:
                # Mergia pronostici da documenti multipli della stessa partita
                idx[key]['pronostici'].extend(doc.get('pronostici', []))
            else:
                idx[key] = doc
        docs_by_sys[sys_id] = idx

    # 2. Trova tutte le partite uniche
    all_match_keys = set()
    for idx in docs_by_sys.values():
        all_match_keys.update(idx.keys())

    if not all_match_keys:
        return 0

    # 3. Per ogni partita, applica routing
    unified_docs = []
    for match_key in sorted(all_match_keys):
        # Trova documento base (preferenza: A > S > C)
        base_doc = None
        for sys_id in ['A', 'S', 'C']:
            if match_key in docs_by_sys[sys_id]:
                base_doc = docs_by_sys[sys_id][match_key]
                break

        if not base_doc:
            continue

        # Costruisci indice pronostici per sistema
        preds_by_sys = {}  # sys_id -> {market_key: pred_dict}
        markets_by_sys = {}  # sys_id -> set(market_keys)

        for sys_id in ['A', 'C', 'S']:
            doc = docs_by_sys[sys_id].get(match_key)
            if not doc:
                preds_by_sys[sys_id] = {}
                markets_by_sys[sys_id] = set()
                continue

            pred_idx = {}
            mk_set = set()
            for p in doc.get('pronostici', []):
                mk = market_key(p)
                if mk:
                    pred_idx[mk] = p
                    mk_set.add(mk)

            preds_by_sys[sys_id] = pred_idx
            markets_by_sys[sys_id] = mk_set

        # Applica routing
        unified_pronostici = route_predictions(preds_by_sys, markets_by_sys)

        # --- POST-PROCESSING: Multi-goal su pronostici deboli ---
        match_odds = base_doc.get('odds', {})
        unified_pronostici = _apply_multigol(unified_pronostici, match_odds)

        # --- POST-PROCESSING: Combo #96 — SEGNO 2 → DC X2 ---
        c_doc_for_combo = docs_by_sys['C'].get(match_key)
        if c_doc_for_combo:
            sim_data = c_doc_for_combo.get('simulation_data')
            unified_pronostici = _apply_combo96_dc_flip(unified_pronostici, match_odds, sim_data)
            unified_pronostici = _apply_x_draw_combos(unified_pronostici, match_odds, sim_data)

        if not unified_pronostici:
            continue

        # Costruisci documento unified
        unified_doc = {}
        for field in MATCH_FIELDS:
            if field in base_doc:
                unified_doc[field] = base_doc[field]

        unified_doc['pronostici'] = unified_pronostici
        unified_doc['routing_version'] = ROUTING_VERSION
        unified_doc['created_at'] = datetime.now(timezone.utc)

        # Aggiungi statistiche
        unified_doc['stats'] = {
            'total_predictions': len(unified_pronostici),
            'sources': list(set(p.get('source', '?') for p in unified_pronostici)),
            'markets': list(set(market_key(p) or '?' for p in unified_pronostici)),
        }

        # --- Campi extra da sistemi specifici ---

        # simulation_data: SOLO da Sistema C (Monte Carlo)
        c_doc = docs_by_sys['C'].get(match_key)
        if c_doc and 'simulation_data' in c_doc:
            unified_doc['simulation_data'] = c_doc['simulation_data']

        # comment, dettagli, strisce: preferenza A > S > C
        EXTRA_FIELDS = [
            'comment', 'segno_dettaglio', 'gol_dettaglio',
            'streak_home', 'streak_away',
            'streak_home_context', 'streak_away_context',
            'gol_directions', 'expected_total_goals',
        ]
        for field in EXTRA_FIELDS:
            for sys_id in ['A', 'S', 'C']:
                doc = docs_by_sys[sys_id].get(match_key)
                if doc and field in doc and doc[field]:
                    unified_doc[field] = doc[field]
                    break

        unified_docs.append(unified_doc)

    if not unified_docs:
        return 0

    # 4. Scrivi in daily_predictions_unified
    coll = db['daily_predictions_unified']

    if not dry_run:
        # Rimuovi vecchi documenti per questa data
        coll.delete_many({'date': date_str})
        # Inserisci nuovi
        coll.insert_many(unified_docs)

    return len(unified_docs)


# =====================================================
# MAIN
# =====================================================
def main():
    parser = argparse.ArgumentParser(description='Mixture of Experts — Orchestratore')
    parser.add_argument('date', nargs='?', help='Data YYYY-MM-DD (default: oggi)')
    parser.add_argument('--backfill', nargs=2, metavar=('START', 'END'),
                        help='Range date per backfill')
    parser.add_argument('--dry-run', action='store_true',
                        help='Simula senza scrivere')
    args = parser.parse_args()

    if args.backfill:
        start_str, end_str = args.backfill
        start = datetime.strptime(start_str, '%Y-%m-%d')
        end = datetime.strptime(end_str, '%Y-%m-%d')
        dates = []
        d = start
        while d <= end:
            dates.append(d.strftime('%Y-%m-%d'))
            d += timedelta(days=1)

        print(f"\n  MoE Backfill: {start_str} -> {end_str} ({len(dates)} giorni)")
        if args.dry_run:
            print("  [DRY RUN — nessuna scrittura]")
        print()

        total = 0
        for dt in dates:
            count = orchestrate_date(dt, dry_run=args.dry_run)
            total += count
            status = '[DRY]' if args.dry_run else '[OK]'
            print(f"  {dt}: {count} partite {status}")

        print(f"\n  Totale: {total} partite su {len(dates)} giorni")

    else:
        if args.date:
            # Data specifica passata da CLI
            date_str = args.date
            print(f"\n  MoE Orchestratore — Data: {date_str}")
            if args.dry_run:
                print("  [DRY RUN — nessuna scrittura]")
            count = orchestrate_date(date_str, dry_run=args.dry_run)
            print(f"  Partite scritte: {count}")
        else:
            # Nessun argomento → 7 giorni (oggi + 6 futuri), come Sistema A e C
            print(f"\n  MoE Orchestratore — 7 giorni (oggi + 6 futuri)")
            if args.dry_run:
                print("  [DRY RUN — nessuna scrittura]")
            total = 0
            for i in range(7):
                target = datetime.now() + timedelta(days=i)
                date_str = target.strftime('%Y-%m-%d')
                count = orchestrate_date(date_str, dry_run=args.dry_run)
                total += count
                status = '[DRY]' if args.dry_run else '[OK]'
                print(f"  {date_str}: {count} partite {status}")
            print(f"\n  Totale: {total} partite su 7 giorni")

    print()


if __name__ == '__main__':
    main()
