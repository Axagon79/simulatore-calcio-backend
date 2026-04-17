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
import re
import math
import json
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


def _apply_fattore_quota(stake, quota):
    """Fattore quota a fasce — bilancia stake con probabilità implicita del mercato.
    <1.50: 2.00/q | 1.50-1.99: nessuno | 2.00-2.49: 2.20/q
    2.50-3.49: 2.00/q | 3.50-4.99: 3.50/q | 5.00+: nessuno
    """
    if not quota or quota <= 0:
        return stake
    if quota < 1.50:
        fattore = 2.00 / quota
    elif quota < 2.00:
        return stake
    elif quota < 2.50:
        fattore = 2.20 / quota
    elif quota < 3.50:
        fattore = 2.00 / quota
    elif quota < 5.00:
        fattore = 3.50 / quota
    else:
        return stake
    return max(1, min(10, round(stake * fattore)))


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


def _apply_goal_quota_conversion(unified, odds):
    """
    Conversione Goal (BTTS) per fasce di quota tossiche:
    - @1.90-1.99: HR BTTS 31%, Under 2.5 92% → converti in Under 2.5
    - @1.70-1.79: HR BTTS 56%, Over 1.5 80% → converti in Over 1.5
    - @1.80-1.89: HR BTTS 55% → resta Goal
    """
    if not odds:
        return unified

    result = []
    for p in unified:
        if p.get('pronostico') != 'Goal' or p.get('tipo') != 'GOL':
            result.append(p)
            continue

        q = p.get('quota') or 0

        # Fascia 1.90-1.99 → Under 2.5
        if 1.90 <= q < 2.00:
            u25_q = float(odds.get('under_25') or 0)
            if u25_q > 1.0:
                p['original_pronostico'] = 'Goal'
                p['original_quota'] = q
                p['pronostico'] = 'Under 2.5'
                p['quota'] = u25_q
                p['source'] = p.get('source', 'C') + '_goal_conv'
                p['routing_rule'] = 'goal_to_u25'
                p['has_odds'] = True
                # Ricalcola stake con Kelly 3/4
                prob_mod = 0.70  # storico U2.5 92% in questa fascia, conservativo
                prob_mkt = 1.0 / u25_q
                edge = prob_mod - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * u25_q - (1 - edge)) / (u25_q - 1)
                    p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), u25_q)
                    p['edge'] = round(edge * 100, 1)
                else:
                    p['stake'] = 1
                    p['edge'] = 0
                p['prob_mercato'] = round(prob_mkt * 100, 1)
                p['prob_modello'] = round(prob_mod * 100, 1)
                p['probabilita_stimata'] = round(prob_mod * 100, 1)
                print(f"    🔄 GOAL→U2.5: Goal @{q:.2f} → Under 2.5 @{u25_q:.2f}")
            result.append(p)

        # Fascia 1.70-1.79 → Over 1.5
        elif 1.70 <= q < 1.80:
            o15_q = float(odds.get('over_15') or 0)
            if o15_q >= 1.35:
                p['original_pronostico'] = 'Goal'
                p['original_quota'] = q
                p['pronostico'] = 'Over 1.5'
                p['quota'] = o15_q
                p['source'] = p.get('source', 'C') + '_goal_conv'
                p['routing_rule'] = 'goal_to_o15'
                p['has_odds'] = True
                prob_mod = 0.78  # storico O1.5 80% in questa fascia, conservativo
                prob_mkt = 1.0 / o15_q
                edge = prob_mod - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * o15_q - (1 - edge)) / (o15_q - 1)
                    p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), o15_q)
                    p['edge'] = round(edge * 100, 1)
                else:
                    p['stake'] = 1
                    p['edge'] = 0
                p['prob_mercato'] = round(prob_mkt * 100, 1)
                p['prob_modello'] = round(prob_mod * 100, 1)
                p['probabilita_stimata'] = round(prob_mod * 100, 1)
                print(f"    🔄 GOAL→O1.5: Goal @{q:.2f} → Over 1.5 @{o15_q:.2f}")
            result.append(p)

        else:
            # 1.80-1.89 e altre fasce: resta Goal
            result.append(p)

    return result


def _apply_gol_low_stake_to_nogoal(unified, odds):
    """
    Conversione Goal (BTTS) a bassa confidence → NoGoal.
    - Stake 1: QUALSIASI GOL → NoGoal (storico 92.3% NoGoal, 12/13)
    - Stake 2: solo Goal (BTTS) → NoGoal (storico 75.0% NoGoal, 21/28)
    """
    if not odds:
        return unified

    result = []
    for p in unified:
        if p.get('pronostico') == 'NO BET' or p.get('tipo') != 'GOL':
            result.append(p)
            continue

        stake = p.get('stake', 0)
        pr = p.get('pronostico', '')

        # Stake 1: qualsiasi GOL → NoGoal (soglia NG <= 1.67)
        # Stake 2: solo Goal (BTTS) → NoGoal (gerarchia 3 livelli, altrimenti NO BET)
        if stake == 1 or (stake == 2 and pr == 'Goal'):
            ng_q = float(odds.get('ng') or 0)
            old_q = p.get('quota', 0) or 0

            if stake == 1:
                # Stake 1: soglia semplice NG <= 1.67
                should_convert = ng_q > 1.0 and ng_q <= 1.67
            else:
                # Stake 2: gerarchia 3 livelli basata su analisi 27 casi (72% HR)
                # DQ = differenza quote (NG - Goal)
                dq = ng_q - old_q if ng_q > 0 and old_q > 0 else -999
                l1 = ng_q >= 1.75 and dq > -0.15       # 70% HR, zona sicura
                l2 = old_q <= 2.30 and ng_q <= 1.60     # 75% HR, NG bassa
                l3 = old_q <= 2.05 and 1.65 <= ng_q <= 1.69  # 75% HR, NG media
                should_convert = ng_q > 1.0 and (l1 or l2 or l3)
                # Se non passa nessun livello → NO BET (non emettere nemmeno l'originale)
                if ng_q > 1.0 and not should_convert:
                    p['original_pronostico'] = pr
                    p['original_quota'] = old_q
                    p['pronostico'] = 'NO BET'
                    p['quota'] = 0
                    p['stake'] = 0
                    p['routing_rule'] = 'gol_s2_to_ng'
                    print(f"    🚫 GOL(s2) gerarchia: {pr} @{old_q:.2f} NG @{ng_q:.2f} → NO BET (nessun livello)")
                    result.append(p)
                    continue

            if should_convert:
                old_pr = pr
                p['original_pronostico'] = old_pr
                p['original_quota'] = old_q
                p['pronostico'] = 'NoGoal'
                p['quota'] = ng_q
                p['tipo'] = 'GOL'
                p['source'] = p.get('source', '?') + f'_gol_s{stake}_conv'
                p['routing_rule'] = f'gol_s{stake}_to_ng'
                p['has_odds'] = True
                prob_mod = 0.80 if stake == 1 else 0.72  # conservativo vs storico 92%/75%
                prob_mkt = 1.0 / ng_q
                edge = prob_mod - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * ng_q - (1 - edge)) / (ng_q - 1)
                    p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), ng_q)
                    p['edge'] = round(edge * 100, 1)
                else:
                    p['stake'] = 1
                    p['edge'] = 0
                p['prob_mercato'] = round(prob_mkt * 100, 1)
                p['prob_modello'] = round(prob_mod * 100, 1)
                p['probabilita_stimata'] = round(prob_mod * 100, 1)
                print(f"    🔄 GOL(s{stake})→NG: {old_pr} @{old_q:.2f} → NoGoal @{ng_q:.2f}")
            result.append(p)
            continue

        result.append(p)

    return result


def _apply_gol_stake3_filter(unified, odds=None):
    """
    Filtro GOL: pronostici tossici → NO BET o conversione MG.
    Stake 3: Over 2.5, MG 2-3 → NO BET.
    Stake 4: Over 2.5 → MG dinamico (O2.5 ≤1.55 → MG 3-5, >1.55 → MG 2-4).
    Stake 7 quota <1.40 → NO BET.
    """
    result = []
    for p in unified:
        stake = p.get('stake', 0)
        pr = p.get('pronostico', '')

        # Stake 4 Over 2.5 → conversione MG dinamico
        if (p.get('tipo') == 'GOL' and stake == 4 and pr == 'Over 2.5' and odds):
            old_pr = pr
            old_q = p.get('quota', 0) or 0

            # Calcola lambda da Under 2.5
            u25_q = odds.get('under_25')
            l_tot = _calc_lambda(float(u25_q)) if u25_q else None

            if l_tot and old_q > 0:
                # MG dinamico: O2.5 bassa (≤1.55) → 3-5, alta (>1.55) → 2-4
                if old_q <= 1.55:
                    mg_range = '3-5'
                    mg_goals = [3, 4, 5]
                else:
                    mg_range = '2-4'
                    mg_goals = [2, 3, 4]

                probs = {g: _poisson(g, l_tot) for g in range(11)}
                mg_prob = sum(probs[g] for g in mg_goals)
                mg_quota = round((1 / mg_prob) * MULTIGOL_MARGINE, 2) if mg_prob > 0 else 99

                if mg_quota >= MULTIGOL_QUOTA_MIN:
                    p['original_pronostico'] = old_pr
                    p['original_quota'] = old_q
                    p['pronostico'] = f'MG {mg_range}'
                    p['quota'] = mg_quota
                    p['routing_rule'] = 'gol_s4_to_mg'
                    print(f"    🔄 GOL(s4) O2.5 @{old_q:.2f} → MG {mg_range} @{mg_quota:.2f}")
                    result.append(p)
                    continue

            # Fallback: se non riesce a calcolare MG → NO BET
            p['original_pronostico'] = old_pr
            p['original_quota'] = old_q
            p['pronostico'] = 'NO BET'
            p['quota'] = 0
            p['stake'] = 0
            p['routing_rule'] = 'gol_s4_filter'
            print(f"    🚫 GOL(s4) filtro: {old_pr} → NO BET (no MG disponibile)")
            result.append(p)
            continue

        # Stake 3 e Stake 7 → NO BET come prima
        if p.get('tipo') == 'GOL' and (
            (stake == 3 and pr in ('Over 2.5', 'MG 2-3'))
            or (stake == 7 and (p.get('quota') or 0) < 1.40)
        ):
            old_pr = pr
            p['original_pronostico'] = old_pr
            p['original_quota'] = p.get('quota', 0)
            p['pronostico'] = 'NO BET'
            p['quota'] = 0
            p['stake'] = 0
            p['routing_rule'] = f'gol_s{stake}_filter'
            print(f"    🚫 GOL(s{stake}) filtro: {old_pr} → NO BET")
        result.append(p)
    return result


def _apply_segno_low_stake_filter(unified):
    """
    Filtri SEGNO/DC a basso stake:
    - SEGNO puro stake 1 quota < 1.60 → NO BET (HR 33.3%, P/L -2.93u)
    - X2 stake 2 → NO BET (HR 56.2%, P/L -4.26u)
    - SEGNO puro stake 2 quota 1.90-1.99 → NO BET (HR 25%, P/L -4.18u)
    - SEGNO puro stake 2 quota >= 2.10 → NO BET (HR 25%, P/L -3.70u)
    """
    result = []
    for p in unified:
        pr = p.get('pronostico', '')
        tipo = p.get('tipo', '')
        stake = p.get('stake', 0)
        quota = p.get('quota') or 0

        # SEGNO puro stake 1 quota < 1.60
        if tipo == 'SEGNO' and stake == 1 and pr != 'NO BET' and quota < 1.60:
            p['original_pronostico'] = pr
            p['original_quota'] = quota
            p['pronostico'] = 'NO BET'
            p['quota'] = 0
            p['stake'] = 0
            p['routing_rule'] = 'segno_s1_low_q_filter'
            print(f"    🚫 SEGNO(s1) filtro: {pr} @{quota:.2f} → NO BET (quota < 1.60)")

        # X2 stake 2
        elif tipo == 'DOPPIA_CHANCE' and stake == 2 and pr == 'X2':
            p['original_pronostico'] = pr
            p['original_quota'] = quota
            p['pronostico'] = 'NO BET'
            p['quota'] = 0
            p['stake'] = 0
            p['routing_rule'] = 'x2_s2_filter'
            print(f"    🚫 X2(s2) filtro: X2 @{quota:.2f} → NO BET")

        # SEGNO puro stake 2 quota 1.90-1.99 o >= 2.10
        elif tipo == 'SEGNO' and stake == 2 and pr != 'NO BET' and ((1.90 <= quota < 2.00) or quota >= 2.10):
            p['original_pronostico'] = pr
            p['original_quota'] = quota
            p['pronostico'] = 'NO BET'
            p['quota'] = 0
            p['stake'] = 0
            p['routing_rule'] = 'segno_s2_toxic_q_filter'
            print(f"    🚫 SEGNO(s2) filtro: {pr} @{quota:.2f} → NO BET (fascia tossica)")

        result.append(p)
    return result


def _apply_dc_stake1_to_under25(unified, odds):
    """
    Conversione DC stake 1 → Under 2.5.
    Storico feb-mar: DC stake 1 HR 52.4% (P/L -3.86u),
    ma Under 2.5 nelle stesse partite 66.7%.
    """
    if not odds:
        return unified

    result = []
    for p in unified:
        if p.get('tipo') != 'DOPPIA_CHANCE' or p.get('stake', 0) != 1 or p.get('pronostico') == 'NO BET':
            result.append(p)
            continue

        u25_q = float(odds.get('under_25') or 0)
        if u25_q > 1.0:
            old_pr = p['pronostico']
            old_q = p.get('quota', 0)
            p['original_pronostico'] = old_pr
            p['original_quota'] = old_q
            p['pronostico'] = 'Under 2.5'
            p['quota'] = u25_q
            p['tipo'] = 'GOL'
            p['source'] = p.get('source', '?') + '_dc_s1_conv'
            p['routing_rule'] = 'dc_s1_to_u25'
            p['has_odds'] = True
            prob_mod = 0.63  # conservativo vs storico 66.7%
            prob_mkt = 1.0 / u25_q
            edge = prob_mod - prob_mkt
            if edge > 0:
                kelly = 0.75 * (edge * u25_q - (1 - edge)) / (u25_q - 1)
                p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), u25_q)
                p['edge'] = round(edge * 100, 1)
            else:
                p['stake'] = 1
                p['edge'] = 0
            p['prob_mercato'] = round(prob_mkt * 100, 1)
            p['prob_modello'] = round(prob_mod * 100, 1)
            p['probabilita_stimata'] = round(prob_mod * 100, 1)
            print(f"    🔄 DC(s1)→U2.5: {old_pr} @{old_q:.2f} → Under 2.5 @{u25_q:.2f}")
        result.append(p)

    return result


def _apply_mg23_stake4_to_under25(unified, odds):
    """
    Conversione MG 2-3 stake 4 → Under 2.5.
    Storico feb-mar: MG 2-3 stake 4 HR 38.5% (P/L -14.52u),
    ma Under 2.5 nelle stesse partite 69.2%.
    DEVE girare PRIMA del filtro fascia 1.80-1.89.
    """
    if not odds:
        return unified

    result = []
    for p in unified:
        if (p.get('tipo') == 'GOL'
            and p.get('stake', 0) == 4
            and p.get('pronostico') == 'MG 2-3'):
            u25_q = float(odds.get('under_25') or 0)
            if u25_q > 1.0:
                old_q = p.get('quota', 0)
                p['original_pronostico'] = 'MG 2-3'
                p['original_quota'] = old_q
                p['pronostico'] = 'Under 2.5'
                p['quota'] = u25_q
                p['tipo'] = 'GOL'
                p['source'] = p.get('source', '?') + '_mg23_s4_conv'
                p['routing_rule'] = 'mg23_s4_to_u25'
                p['has_odds'] = True
                prob_mod = 0.66  # conservativo vs storico 69.2%
                prob_mkt = 1.0 / u25_q
                edge = prob_mod - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * u25_q - (1 - edge)) / (u25_q - 1)
                    p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), u25_q)
                    p['edge'] = round(edge * 100, 1)
                else:
                    p['stake'] = 1
                    p['edge'] = 0
                p['prob_mercato'] = round(prob_mkt * 100, 1)
                p['prob_modello'] = round(prob_mod * 100, 1)
                p['probabilita_stimata'] = round(prob_mod * 100, 1)
                print(f"    🔄 MG23(s4)→U2.5: MG 2-3 @{old_q:.2f} → Under 2.5 @{u25_q:.2f}")
        result.append(p)

    return result


def _apply_gol_stake4_quota_filter(unified):
    """
    Filtro GOL stake 4 fascia quota 1.80-1.89 → NO BET.
    Storico feb-mar: 7/21 HR 33.3%, P/L -32.12u.
    DEVE girare DOPO la conversione MG 2-3 → U2.5 (che cambia quota).
    """
    result = []
    for p in unified:
        if (p.get('tipo') == 'GOL'
            and p.get('stake', 0) == 4
            and p.get('pronostico') != 'NO BET'
            and 1.80 <= (p.get('quota') or 0) < 1.90):
            old_pr = p['pronostico']
            old_q = p.get('quota', 0)
            p['original_pronostico'] = old_pr
            p['original_quota'] = old_q
            p['pronostico'] = 'NO BET'
            p['quota'] = 0
            p['stake'] = 0
            p['routing_rule'] = 'gol_s4_q180_filter'
            print(f"    🚫 GOL(s4) filtro quota: {old_pr} @{old_q:.2f} → NO BET (fascia 1.80-1.89)")
        result.append(p)
    return result


def _apply_over15_stake5_low_to_under25(unified, odds):
    """
    Conversione Over 1.5 stake 5 quota < 1.40 → Under 2.5.
    Storico feb-mar: 7/11 HR 63.6% (P/L -7.65u), BE=74% irraggiungibile.
    Under 2.5 nelle stesse partite 72.7%. Nelle 4 perse, U2.5 4/4 (100%).
    """
    if not odds:
        return unified

    result = []
    for p in unified:
        if (p.get('tipo') == 'GOL'
            and p.get('stake', 0) == 5
            and p.get('pronostico') == 'Over 1.5'
            and (p.get('quota') or 0) < 1.40):
            u25_q = float(odds.get('under_25') or 0)
            if u25_q > 1.0:
                old_q = p.get('quota', 0)
                p['original_pronostico'] = 'Over 1.5'
                p['original_quota'] = old_q
                p['pronostico'] = 'Under 2.5'
                p['quota'] = u25_q
                p['tipo'] = 'GOL'
                p['source'] = p.get('source', '?') + '_o15_s5_conv'
                p['routing_rule'] = 'o15_s5_low_to_u25'
                p['has_odds'] = True
                prob_mod = 0.69  # conservativo vs storico 72.7%
                prob_mkt = 1.0 / u25_q
                edge = prob_mod - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * u25_q - (1 - edge)) / (u25_q - 1)
                    p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), u25_q)
                    p['edge'] = round(edge * 100, 1)
                else:
                    p['stake'] = 1
                    p['edge'] = 0
                p['prob_mercato'] = round(prob_mkt * 100, 1)
                p['prob_modello'] = round(prob_mod * 100, 1)
                p['probabilita_stimata'] = round(prob_mod * 100, 1)
                print(f"    🔄 O1.5(s5,<1.40)→U2.5: Over 1.5 @{old_q:.2f} → Under 2.5 @{u25_q:.2f}")
        result.append(p)

    return result


def _apply_gol_stake7_filter(unified, odds):
    """
    Filtro GOL stake 7 — sub-mercati irrecuperabili → NO BET:
    - Under 2.5: 5/11 HR 45.5% (BE 67.9%, P/L -24.64u) — impossibile recuperare
    - MG 2-3: 1/2 HR 50% (P/L -0.84u) — campione piccolo, marginale
    - Quota 1.90-1.99: 0/2 (P/L -14.00u) — zero vittorie
    NG rate globale 45% → conversione a NoGoal NON funziona.
    """
    result = []
    for p in unified:
        if p.get('tipo') != 'GOL' or p.get('stake', 0) != 7 or p.get('pronostico') == 'NO BET':
            result.append(p)
            continue

        pr = p.get('pronostico', '')
        quota = p.get('quota') or 0
        nobet = False

        if pr == 'Under 2.5':
            nobet = True
            tag = 'u25_s7'
        elif pr == 'MG 2-3':
            nobet = True
            tag = 'mg23_s7'
        elif 1.90 <= quota < 2.00:
            nobet = True
            tag = 'gol_s7_q190'

        if nobet:
            old_pr = pr
            p['original_pronostico'] = old_pr
            p['original_quota'] = quota
            p['pronostico'] = 'NO BET'
            p['routing_rule'] = f'{tag}_nobet'
            print(f"    🚫 GOL(s7) NO BET: {old_pr} @{quota:.2f} [{tag}]")
        result.append(p)

    return result


def _apply_gol_stake5_q160_to_nogoal(unified, odds):
    """
    Conversione GOL stake 5 fascia quota 1.60-1.69 → NoGoal.
    Storico feb-mar: 9/19 HR 47.4% (P/L -21.50u),
    ma NoGoal nelle stesse partite 63.2%. Nelle 10 perse, NG 9/10 (90%).
    """
    if not odds:
        return unified

    result = []
    for p in unified:
        if (p.get('tipo') == 'GOL'
            and p.get('stake', 0) == 5
            and p.get('pronostico') != 'NO BET'
            and 1.60 <= (p.get('quota') or 0) < 1.70):
            ng_q = float(odds.get('ng') or 0)
            if ng_q > 1.0:
                old_pr = p['pronostico']
                old_q = p.get('quota', 0)
                p['original_pronostico'] = old_pr
                p['original_quota'] = old_q
                p['pronostico'] = 'NoGoal'
                p['quota'] = ng_q
                p['tipo'] = 'GOL'
                p['source'] = p.get('source', '?') + '_gol_s5_q160_conv'
                p['routing_rule'] = 'gol_s5_q160_to_ng'
                p['has_odds'] = True
                prob_mod = 0.60  # conservativo vs storico 63.2%
                prob_mkt = 1.0 / ng_q
                edge = prob_mod - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * ng_q - (1 - edge)) / (ng_q - 1)
                    p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), ng_q)
                    p['edge'] = round(edge * 100, 1)
                else:
                    p['stake'] = 1
                    p['edge'] = 0
                p['prob_mercato'] = round(prob_mkt * 100, 1)
                p['prob_modello'] = round(prob_mod * 100, 1)
                p['probabilita_stimata'] = round(prob_mod * 100, 1)
                print(f"    🔄 GOL(s5,q160)→NG: {old_pr} @{old_q:.2f} → NoGoal @{ng_q:.2f}")
        result.append(p)

    return result


def _apply_dc_stake4_to_nogoal(unified, odds):
    """
    Conversione DC stake 4 → NoGoal.
    Storico feb-mar: DC stake 4 HR 60.0% (P/L -8.24u),
    ma NoGoal nelle stesse partite 73.7% (P/L +29.20u).
    NoGoal assente nel sistema → diversifica il portafoglio.
    """
    if not odds:
        return unified

    result = []
    for p in unified:
        if p.get('tipo') != 'DOPPIA_CHANCE' or p.get('stake', 0) != 4 or p.get('pronostico') == 'NO BET':
            result.append(p)
            continue

        ng_q = float(odds.get('ng') or 0)
        if ng_q > 1.0:
            old_pr = p['pronostico']
            old_q = p.get('quota', 0)
            p['original_pronostico'] = old_pr
            p['original_quota'] = old_q
            p['pronostico'] = 'NoGoal'
            p['quota'] = ng_q
            p['tipo'] = 'GOL'
            p['source'] = p.get('source', '?') + '_dc_s4_conv'
            p['routing_rule'] = 'dc_s4_to_ng'
            p['has_odds'] = True
            prob_mod = 0.70  # conservativo vs storico 73.7%
            prob_mkt = 1.0 / ng_q
            edge = prob_mod - prob_mkt
            if edge > 0:
                kelly = 0.75 * (edge * ng_q - (1 - edge)) / (ng_q - 1)
                p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), ng_q)
                p['edge'] = round(edge * 100, 1)
            else:
                p['stake'] = 1
                p['edge'] = 0
            p['prob_mercato'] = round(prob_mkt * 100, 1)
            p['prob_modello'] = round(prob_mod * 100, 1)
            p['probabilita_stimata'] = round(prob_mod * 100, 1)
            print(f"    🔄 DC(s4)→NG: {old_pr} @{old_q:.2f} → NoGoal @{ng_q:.2f}")
        result.append(p)

    return result


def _apply_o25_stake6_to_goal(unified, odds):
    """
    Conversione Over 2.5 stake 6 → Goal (BTTS).
    Storico feb-mar: O2.5 stake 6 HR 61.3% (P/L -13.80u),
    ma BTTS nelle stesse 31 partite 74.2% (P/L +28.20u).
    prob_mod = 0.70 (conservativo vs 74.2%) → Kelly abbassa stake di 1-2 punti.
    """
    if not odds:
        return unified

    result = []
    for p in unified:
        if (p.get('tipo') == 'GOL'
            and p.get('stake', 0) == 6
            and p.get('pronostico') == 'Over 2.5'):
            gg_q = float(odds.get('gg') or 0)
            if gg_q > 1.0:
                old_q = p.get('quota', 0)
                p['original_pronostico'] = 'Over 2.5'
                p['original_quota'] = old_q
                p['pronostico'] = 'Goal'
                p['quota'] = gg_q
                p['tipo'] = 'GOL'
                p['source'] = p.get('source', '?') + '_o25_s6_conv'
                p['routing_rule'] = 'o25_s6_to_goal'
                p['has_odds'] = True
                prob_mod = 0.70  # conservativo vs storico 74.2%
                prob_mkt = 1.0 / gg_q
                edge = prob_mod - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * gg_q - (1 - edge)) / (gg_q - 1)
                    p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), gg_q)
                    p['edge'] = round(edge * 100, 1)
                else:
                    p['stake'] = 1
                    p['edge'] = 0
                p['prob_mercato'] = round(prob_mkt * 100, 1)
                p['prob_modello'] = round(prob_mod * 100, 1)
                p['probabilita_stimata'] = round(prob_mod * 100, 1)
                print(f"    🔄 O2.5(s6)→Goal: Over 2.5 @{old_q:.2f} → Goal @{gg_q:.2f}")
        result.append(p)

    return result


def _apply_segno_stake9_conversions(unified, odds):
    """
    Conversioni SEGNO stake 9 per fasce problematiche:
    - Fascia 1.50-1.59: DC X2 o SEGNO 2 → Goal (BTTS 5/6=83.3%, prob_mod=0.70)
    - Fascia 1.80-1.99: DC X2 → NoGoal (NG 4/5=80%, prob_mod=0.65)
    - Fascia 1.80-1.99: SEGNO 2 → mantieni ma cap stake a 6 (da 9, -3 punti)
    """
    if not odds:
        return unified

    result = []
    for p in unified:
        tipo = p.get('tipo', '')
        stake = p.get('stake', 0)
        pr = p.get('pronostico', '')
        quota = p.get('quota') or 0

        if stake != 9 or pr == 'NO BET':
            result.append(p)
            continue

        # Fascia 1.50-1.59: DC X2 o SEGNO 2 → Goal (BTTS)
        if 1.50 <= quota < 1.60 and (
            (tipo == 'DOPPIA_CHANCE' and pr == 'X2') or
            (tipo == 'SEGNO' and pr == '2')
        ):
            gg_q = float(odds.get('gg') or 0)
            if gg_q > 1.0:
                old_pr = pr
                old_q = quota
                p['original_pronostico'] = old_pr
                p['original_quota'] = old_q
                p['pronostico'] = 'Goal'
                p['quota'] = gg_q
                p['tipo'] = 'GOL'
                p['source'] = p.get('source', '?') + '_segno_s9_f150_conv'
                p['routing_rule'] = 'segno_s9_f150_to_goal'
                p['has_odds'] = True
                prob_mod = 0.70  # conservativo vs storico 83.3%
                prob_mkt = 1.0 / gg_q
                edge = prob_mod - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * gg_q - (1 - edge)) / (gg_q - 1)
                    p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), gg_q)
                    p['edge'] = round(edge * 100, 1)
                else:
                    p['stake'] = 1
                    p['edge'] = 0
                p['prob_mercato'] = round(prob_mkt * 100, 1)
                p['prob_modello'] = round(prob_mod * 100, 1)
                p['probabilita_stimata'] = round(prob_mod * 100, 1)
                print(f"    🔄 SEGNO(s9,q1.50)→Goal: {old_pr} @{old_q:.2f} → Goal @{gg_q:.2f}")
            result.append(p)
            continue

        # Fascia 1.80-1.99: DC X2 → NoGoal
        if 1.80 <= quota < 2.00 and tipo == 'DOPPIA_CHANCE' and pr == 'X2':
            ng_q = float(odds.get('ng') or 0)
            if ng_q > 1.0:
                old_q = quota
                p['original_pronostico'] = 'X2'
                p['original_quota'] = old_q
                p['pronostico'] = 'NoGoal'
                p['quota'] = ng_q
                p['tipo'] = 'GOL'
                p['source'] = p.get('source', '?') + '_dcx2_s9_f180_conv'
                p['routing_rule'] = 'dcx2_s9_f180_to_ng'
                p['has_odds'] = True
                prob_mod = 0.65  # conservativo vs storico 80%
                prob_mkt = 1.0 / ng_q
                edge = prob_mod - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * ng_q - (1 - edge)) / (ng_q - 1)
                    p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), ng_q)
                    p['edge'] = round(edge * 100, 1)
                else:
                    p['stake'] = 1
                    p['edge'] = 0
                p['prob_mercato'] = round(prob_mkt * 100, 1)
                p['prob_modello'] = round(prob_mod * 100, 1)
                p['probabilita_stimata'] = round(prob_mod * 100, 1)
                print(f"    🔄 DCX2(s9,q1.80)→NG: X2 @{old_q:.2f} → NoGoal @{ng_q:.2f}")
            result.append(p)
            continue

        # Fascia 1.80-1.99: SEGNO 2 → mantieni ma cap stake a 6
        if 1.80 <= quota < 2.00 and tipo == 'SEGNO' and pr == '2':
            p['stake'] = 6
            p['routing_rule'] = 'se2_s9_f180_cap6'
            print(f"    📉 SE:2(s9,q1.80) cap stake: 9 → 6 ({pr} @{quota:.2f})")
            result.append(p)
            continue

        result.append(p)

    return result


def _apply_se2_stake8_filter(unified):
    """
    Filtro SEGNO 2 stake 8 fascia quota 1.90-1.99 → NO BET.
    Storico feb-mar: 2/7 HR 28.6% (P/L -23.60u).
    ⚠️ Range 1.90-1.99 (NON >=1.90): la fascia 2.00-2.50 ha 5/9 HR 55.6% (+8.40u), va preservata.
    """
    result = []
    for p in unified:
        if (p.get('tipo') == 'SEGNO'
            and p.get('stake', 0) == 8
            and p.get('pronostico') == '2'
            and 1.90 <= (p.get('quota') or 0) < 2.00):
            old_q = p.get('quota', 0)
            p['original_pronostico'] = '2'
            p['original_quota'] = old_q
            p['pronostico'] = 'NO BET'
            p['quota'] = 0
            p['stake'] = 0
            p['routing_rule'] = 'se2_s8_q190_filter'
            print(f"    🚫 SE:2(s8) filtro: 2 @{old_q:.2f} → NO BET (fascia 1.90-1.99)")
        result.append(p)
    return result


def _apply_gol_stake8_cap(unified):
    """
    Cap stake GOL stake 8 fascia quota 1.50-1.59: 8 → 6.
    Storico feb-mar: 7/13 HR 53.8% (P/L -18.00u), sotto BE 64.9%.
    Le altre fasce funzionano bene (1.40-1.49: 84.6%, 1.60+: 100%).
    """
    result = []
    for p in unified:
        if (p.get('tipo') == 'GOL'
            and p.get('stake', 0) == 8
            and p.get('pronostico') != 'NO BET'
            and 1.50 <= (p.get('quota') or 0) < 1.60):
            p['stake'] = 6
            p['routing_rule'] = 'gol_s8_q150_cap6'
            print(f"    📉 GOL(s8) cap stake: 8 → 6 ({p.get('pronostico','')} @{p.get('quota',0):.2f})")
        result.append(p)
    return result


def _apply_segno_stake7_cap(unified):
    """
    Cap stake SEGNO+DC stake 7 nelle fasce deboli: 7 → 5.
    - Fascia <1.40: 0/1 (BE 71.9%, irraggiungibile)
    - Fascia 1.40-1.49: 3/5 HR 60% (BE 69.4%, P/L -4.48u)
    - Fascia 1.60-1.69: 5/9 HR 55.6% (BE 61%, P/L -6.51u)
    Le fasce 1.50-1.59 (88.9%) e 1.80+ (69.2%+) restano a stake 7.
    """
    result = []
    for p in unified:
        tipo = p.get('tipo', '')
        stake = p.get('stake', 0)
        quota = p.get('quota') or 0
        if (stake == 7
            and tipo in ('SEGNO', 'DOPPIA_CHANCE')
            and p.get('pronostico') != 'NO BET'
            and (quota < 1.50 or (1.60 <= quota < 1.70))):
            p['stake'] = 5
            p['routing_rule'] = 'segno_s7_weak_q_cap5'
            print(f"    📉 SEGNO(s7) cap stake: 7 → 5 ({p.get('pronostico','')} @{quota:.2f})")
        result.append(p)
    return result


def _apply_segno_stake6_conversion(unified, odds):
    """
    Conversione SEGNO stake 6 → mercati più profittevoli.
    Pattern storico feb-mar:
    - SEGNO puro stake 6: HR 50%, Over 2.5 57% → converti in Over 2.5
    - DC stake 6: HR 60%, BTTS 65% → converti in Goal
    """
    if not odds:
        return unified

    result = []
    for p in unified:
        tipo = p.get('tipo', '')
        stake = p.get('stake', 0)
        pr = p.get('pronostico', '')

        # SEGNO puro stake 6 → Over 2.5
        if tipo == 'SEGNO' and stake == 6 and pr != 'NO BET':
            o25_q = float(odds.get('over_25') or 0)
            if o25_q > 1.0:
                old_pr = pr
                old_q = p.get('quota', 0)
                p['original_pronostico'] = old_pr
                p['original_quota'] = old_q
                p['pronostico'] = 'Over 2.5'
                p['quota'] = o25_q
                p['tipo'] = 'GOL'
                p['source'] = p.get('source', '?') + '_segno_s6_conv'
                p['routing_rule'] = 'segno_s6_to_o25'
                p['has_odds'] = True
                prob_mod = 0.57
                prob_mkt = 1.0 / o25_q
                edge = prob_mod - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * o25_q - (1 - edge)) / (o25_q - 1)
                    p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), o25_q)
                    p['edge'] = round(edge * 100, 1)
                else:
                    p['stake'] = 1
                    p['edge'] = 0
                p['prob_mercato'] = round(prob_mkt * 100, 1)
                p['prob_modello'] = round(prob_mod * 100, 1)
                p['probabilita_stimata'] = round(prob_mod * 100, 1)
                print(f"    🔄 SEGNO(s6)→O2.5: {old_pr} @{old_q:.2f} → Over 2.5 @{o25_q:.2f}")
            result.append(p)
            continue

        # DC stake 6 → Goal (BTTS)
        if tipo == 'DOPPIA_CHANCE' and stake == 6 and pr != 'NO BET':
            gg_q = float(odds.get('gg') or 0)
            if gg_q > 1.0:
                old_pr = pr
                old_q = p.get('quota', 0)
                p['original_pronostico'] = old_pr
                p['original_quota'] = old_q
                p['pronostico'] = 'Goal'
                p['quota'] = gg_q
                p['tipo'] = 'GOL'
                p['source'] = p.get('source', '?') + '_dc_s6_conv'
                p['routing_rule'] = 'dc_s6_to_goal'
                p['has_odds'] = True
                prob_mod = 0.65
                prob_mkt = 1.0 / gg_q
                edge = prob_mod - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * gg_q - (1 - edge)) / (gg_q - 1)
                    p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), gg_q)
                    p['edge'] = round(edge * 100, 1)
                else:
                    p['stake'] = 1
                    p['edge'] = 0
                p['prob_mercato'] = round(prob_mkt * 100, 1)
                p['prob_modello'] = round(prob_mod * 100, 1)
                p['probabilita_stimata'] = round(prob_mod * 100, 1)
                print(f"    🔄 DC(s6)→Goal: {old_pr} @{old_q:.2f} → Goal @{gg_q:.2f}")
            result.append(p)
            continue

        result.append(p)

    return result


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

        # GG da Sistema C (conf 60-65) ha ROI +24% — non convertire in MG
        # Over 1.5 da A+S quota 1.35-1.50 ha HR 87% — non convertire in MG
        # Under 3.5 da A quota >= 1.35 ha HR 83% — non convertire in MG
        source = p.get('source', '')
        quota = p.get('quota') or 0
        is_candidate = (
            (pron == 'Over 1.5' and not (source == 'A+S' and 1.35 <= quota <= 1.50)) or
            (pron == 'Under 3.5' and not (source == 'A' and quota >= 1.35)) or
            (pron in ('Goal', 'NoGoal') and 60 <= conf <= 65 and source != 'C')
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
                    mg['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), mg_quota)
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
                dc_pred['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), dc_quota)
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
                x_pred['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), q_x)
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
            x_pred['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), q_x)
            x_pred['edge'] = round(edge * 100, 1)
            x_pred['prob_mercato'] = round(prob_mkt * 100, 1)
            x_pred['prob_modello'] = 70.0
            x_pred['probabilita_stimata'] = 70.0
        result.append(x_pred)

    print(f"    ⚡ COMBO X-DRAW #{combo}: → SEGNO X @{q_x}")
    return result


# Combo che storicamente producono 1 (100% su 11 partite, campione piccolo)
HOME_WIN_COMBOS = {14, 25, 26, 38, 61, 71, 80, 88, 93, 94}


def _apply_home_win_combos(unified, odds, simulation_data):
    """
    Combo Home-Win: 10 combo rare dove il SEGNO 1 ha hit rate 100%.
    Sostituisce SEGNO diverso da 1 con SEGNO 1, o aggiunge SEGNO 1 se assente.
    Solo se quota 1 ≥ 1.35.
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

    if combo not in HOME_WIN_COMBOS:
        return unified

    # Quota 1
    q_1 = float(odds.get('1', 0) or 0)
    if q_1 < 1.35:
        return unified

    # Cerca se c'è già un SEGNO e sostituiscilo, altrimenti aggiungi
    result = []
    replaced = False
    for p in unified:
        if p.get('tipo') == 'SEGNO' and not replaced:
            h_pred = {
                'tipo': 'SEGNO',
                'pronostico': '1',
                'quota': q_1,
                'confidence': p.get('confidence', 55),
                'stars': p.get('stars', 3.0),
                'source': p.get('source', '?') + '_hw',
                'routing_rule': f'home_win_combo_{combo}',
                'has_odds': True,
            }
            prob_mod = 0.75  # stima conservativa (storico 100% ma campione 11 partite)
            prob_mkt = 1.0 / q_1
            edge = prob_mod - prob_mkt
            if edge > 0:
                kelly = 0.75 * (edge * q_1) / (q_1 - 1)
                h_pred['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), q_1)
                h_pred['edge'] = round(edge * 100, 1)
                h_pred['prob_mercato'] = round(prob_mkt * 100, 1)
                h_pred['prob_modello'] = round(prob_mod * 100, 1)
                h_pred['probabilita_stimata'] = round(prob_mod * 100, 1)
            else:
                h_pred['stake'] = 1
                h_pred['edge'] = 0
            result.append(h_pred)
            replaced = True
        else:
            result.append(p)

    # Se non c'era un SEGNO, aggiungilo
    if not replaced:
        h_pred = {
            'tipo': 'SEGNO',
            'pronostico': '1',
            'quota': q_1,
            'confidence': 55,
            'stars': 3.0,
            'source': 'MC_hw',
            'routing_rule': f'home_win_combo_{combo}',
            'has_odds': True,
            'stake': 1,
            'edge': 0,
        }
        prob_mkt = 1.0 / q_1
        edge = 0.75 - prob_mkt
        if edge > 0:
            kelly = 0.75 * (edge * q_1) / (q_1 - 1)
            h_pred['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), q_1)
            h_pred['edge'] = round(edge * 100, 1)
            h_pred['prob_mercato'] = round(prob_mkt * 100, 1)
            h_pred['prob_modello'] = 75.0
            h_pred['probabilita_stimata'] = 75.0
        result.append(h_pred)

    print(f"    ⚡ COMBO HOME-WIN #{combo}: → SEGNO 1 @{q_1}")
    return result


# =====================================================
# DC DOWNGRADE — SEGNO AR + GG conf 60-65 → DC
# =====================================================
def _apply_gg_conf_dc_downgrade(unified, c_doc, match_odds=None):
    """
    Quando Sistema C emette un SEGNO con quota >= 2.51 (Alto Rendimento)
    e la stessa partita ha GG con gg_pct 60-65%:
    1. Tieni il segno originale ma ricalcola stake (media Kelly@50% + originale)
    2. Aggiungi pronostico NoGoal se non esiste già un GOL nella partita
    Storico: 10/12 NoGoal, segno HR ~50% su quote alte.
    """
    if not c_doc:
        return unified

    # Verifica gg_pct dalla simulation_data
    sim_data = c_doc.get('simulation_data', {})
    gg_pct = sim_data.get('gg_pct', 0) or 0
    if not (60 <= gg_pct <= 65):
        return unified

    # Controlla se esiste già un pronostico GOL nella partita
    has_gol = any(p.get('tipo') == 'GOL' for p in unified)

    result = []
    for p in unified:
        if (p.get('tipo') == 'SEGNO'
                and p.get('source', '').startswith('C')
                and (p.get('quota') or 0) >= 2.51):

            pron = p.get('pronostico')
            if pron not in ('1', '2'):
                result.append(p)
                continue

            quota = p.get('quota', 0)
            orig_stake = p.get('stake', 1)

            # 1) Ricalcola stake segno: media(Kelly@50%, stake_originale)
            prob_mod_segno = 0.50
            if quota > 1.0:
                prob_mkt = 1.0 / quota
                edge = prob_mod_segno - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * quota - (1 - edge)) / (quota - 1)
                    kelly_stake = max(1, min(10, round(kelly * 10)))
                else:
                    kelly_stake = 1
                new_stake = _apply_fattore_quota(max(1, round((kelly_stake + orig_stake) / 2)), quota)
                p['stake'] = new_stake
                p['routing_rule'] = 'gg_conf_dc_downgrade'
                print(f"    🎯 GG-DC: SEGNO {pron} @{quota:.2f} stake {orig_stake}→{new_stake} (gg_pct={gg_pct}%)")

            result.append(p)

            # 2) Aggiungi NoGoal se non c'è già un pronostico GOL
            if not has_gol and match_odds:
                ng_q = float(match_odds.get('ng') or 0)
                if ng_q > 1.0:
                    prob_mod_ng = 0.83  # storico 10/12 NoGoal
                    prob_mkt_ng = 1.0 / ng_q
                    edge_ng = prob_mod_ng - prob_mkt_ng
                    ng_pred = {
                        'tipo': 'GOL',
                        'pronostico': 'NoGoal',
                        'quota': ng_q,
                        'confidence': p.get('confidence', 55),
                        'stars': p.get('stars', 3.0),
                        'source': p.get('source', '') + '_gg_ng_add',
                        'routing_rule': 'gg_conf_dc_downgrade',
                        'has_odds': True,
                    }
                    if edge_ng > 0:
                        kelly_ng = 0.75 * (edge_ng * ng_q - (1 - edge_ng)) / (ng_q - 1)
                        ng_pred['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly_ng * 10))), ng_q)
                        ng_pred['edge'] = round(edge_ng * 100, 1)
                    else:
                        ng_pred['stake'] = 1
                        ng_pred['edge'] = 0
                    ng_pred['prob_mercato'] = round(prob_mkt_ng * 100, 1)
                    ng_pred['prob_modello'] = round(prob_mod_ng * 100, 1)
                    ng_pred['probabilita_stimata'] = round(prob_mod_ng * 100, 1)
                    result.append(ng_pred)
                    has_gol = True  # evita duplicati se più segni
                    print(f"    ➕ GG-DC: +NoGoal @{ng_q:.2f} (stake {ng_pred['stake']})")
        else:
            result.append(p)

    return result


# =====================================================
# SCREMATURA SEGNO PER FASCE DI QUOTA
# =====================================================
def _apply_segno_scrematura(unified, odds, base_doc, c_doc=None):
    """
    Scrematura SEGNO: nelle fasce di quota deboli, converte il SEGNO
    in Over 1.5, GOL o GG — oppure lo elimina.
    Fasce BUONE (skip): 1.55-1.65, 1.85-2.10.
    """
    # Trova il pronostico SEGNO
    segno_pred = None
    segno_idx = None
    for i, p in enumerate(unified):
        if p.get('tipo') == 'SEGNO':
            segno_pred = p
            segno_idx = i
            break

    if segno_pred is None:
        return unified

    # Proteggi SEGNO prodotti da combo (qualsiasi combo ha HR altissimi)
    routing = segno_pred.get('routing_rule', '')
    if routing != 'single' and routing != '':
        return unified

    quota = segno_pred.get('quota', 0) or 0
    segno = segno_pred.get('pronostico', '')

    # Fasce BUONE — non toccare
    if 1.55 <= quota < 1.65 or 1.85 <= quota < 2.10:
        return unified

    result = list(unified)

    def _make_sostituto(tipo_pron, nuova_quota):
        """Crea pronostico sostitutivo con stake/edge ricalcolati."""
        p = {
            'tipo': 'GOL',
            'pronostico': tipo_pron,
            'quota': nuova_quota,
            'confidence': segno_pred.get('confidence', 60),
            'stars': segno_pred.get('stars', 3),
            'source': segno_pred.get('source', '') + '_screm',
            'routing_rule': 'scrematura_segno',
            'original_pronostico': segno,
            'original_quota': quota,
            'has_odds': nuova_quota is not None and nuova_quota > 0,
        }
        prob = segno_pred.get('probabilita_stimata', 60)
        if nuova_quota and nuova_quota > 1.0:
            prob_mkt = 1.0 / nuova_quota
            edge = (prob / 100.0) - prob_mkt
            if edge > 0:
                kelly = 0.75 * (edge * nuova_quota - (1 - edge)) / (nuova_quota - 1)
                p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), nuova_quota)
            else:
                p['stake'] = 1
            p['edge'] = round(edge * 100, 1)
            p['prob_mercato'] = round(prob_mkt * 100, 1)
            p['probabilita_stimata'] = prob
        return p

    def _make_segno_x(q_x):
        """Crea pronostico SEGNO X sostitutivo."""
        p = deepcopy(segno_pred)
        p['original_pronostico'] = segno
        p['original_quota'] = quota
        p['pronostico'] = 'X'
        p['quota'] = q_x
        p['source'] = segno_pred.get('source', '') + '_screm_x'
        p['routing_rule'] = 'scrematura_segno_x'
        if q_x and q_x > 1.0:
            prob_mkt = 1.0 / q_x
            prob = segno_pred.get('probabilita_stimata', 60)
            edge = (prob / 100.0) - prob_mkt
            if edge > 0:
                kelly = 0.75 * (edge * q_x - (1 - edge)) / (q_x - 1)
                p['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), q_x)
            else:
                p['stake'] = 1
            p['edge'] = round(edge * 100, 1)
            p['prob_mercato'] = round(prob_mkt * 100, 1)
            p['probabilita_stimata'] = prob
        return p

    over15_q = odds.get('over_15', 0) or 0
    gg_q = odds.get('gg', 0) or 0
    ng_q = odds.get('ng', 0) or 0
    q_x = float(odds.get('x', 0) or odds.get('X', 0) or 0)
    q_1 = float(odds.get('1', 0) or 0)
    q_2 = float(odds.get('2', 0) or 0)
    # Calcola quote DC dalle 1X2 (come combo #96)
    dc_1x_q = round(1/(1/q_1 + 1/q_x), 2) if q_1 > 1 and q_x > 1 else 0
    dc_x2_q = round(1/(1/q_x + 1/q_2), 2) if q_x > 1 and q_2 > 1 else 0

    # Cerca GOL già presente in unified con quota >= 1.35
    gol_in_unified = any(
        p.get('tipo') == 'GOL' and (p.get('quota', 0) or 0) >= 1.35
        for p in unified if p is not segno_pred
    )

    def _mercato_gia_presente(pronostico, tipo='GOL'):
        """Controlla se un pronostico identico esiste già nell'unified."""
        return any(
            p.get('tipo') == tipo and p.get('pronostico') == pronostico
            for p in unified if p is not segno_pred
        )

    fascia = ''
    azione = ''

    def _try_dc_from_segno():
        """DC coerente col SEGNO originale. 1X solo >= 1.65, X2 >= 1.40. Ritorna (pred, azione) o (None, None)."""
        if segno == '1' and dc_1x_q >= 1.65:
            sost = _make_sostituto('1X', dc_1x_q)
            sost['tipo'] = 'DOPPIA_CHANCE'
            sost['source'] = 'C_screm_dc'
            sost['routing_rule'] = 'screm_o15_to_dc'
            return sost, f'DC 1X @{dc_1x_q:.2f}'
        elif segno == '2' and dc_x2_q >= 1.40:
            sost = _make_sostituto('X2', dc_x2_q)
            sost['tipo'] = 'DOPPIA_CHANCE'
            sost['source'] = 'C_screm_dc'
            sost['routing_rule'] = 'screm_o15_to_dc'
            return sost, f'DC X2 @{dc_x2_q:.2f}'
        return None, None

    over25_q = odds.get('over_25', 0) or 0

    # --- FASCIA 1 (1.00-1.44): Escalation O1.5 → DC coerente → O2.5 → GG → SEGNO puro ---
    if quota < 1.45:
        fascia = '1.00-1.44'
        if over15_q >= 1.40:
            result[segno_idx] = _make_sostituto('Over 1.5', over15_q)
            azione = f'Over 1.5 @{over15_q:.2f}'
        elif _try_dc_from_segno()[0] is not None:
            dc_pred, dc_azione = _try_dc_from_segno()
            result[segno_idx] = dc_pred
            azione = dc_azione
        elif over25_q >= 1.35:
            result[segno_idx] = _make_sostituto('Over 2.5', over25_q)
            azione = f'Over 2.5 @{over25_q:.2f}'
        elif gg_q >= 1.35:
            result[segno_idx] = _make_sostituto('Goal', gg_q)
            azione = f'GG @{gg_q:.2f}'
        elif not gol_in_unified:
            # SEGNO puro (nessun GOL in unified) — tieni
            azione = 'TIENI SEGNO (puro, no GOL)'
            return unified
        else:
            result.pop(segno_idx)
            azione = 'ELIMINATO'

    # --- FASCE 2, 3, 5: TIENI SEGNO (buone) — skip automatico sopra ---

    # --- FASCIA 4 (1.65-1.84): Escalation O1.5 → DC coerente → SEGNO puro → ELIMINA ---
    elif 1.65 <= quota < 1.85:
        fascia = '1.65-1.84'
        if over15_q >= 1.40:
            result[segno_idx] = _make_sostituto('Over 1.5', over15_q)
            azione = f'Over 1.5 @{over15_q:.2f}'
        elif _try_dc_from_segno()[0] is not None:
            dc_pred, dc_azione = _try_dc_from_segno()
            result[segno_idx] = dc_pred
            azione = dc_azione
        elif not gol_in_unified:
            # SEGNO puro (nessun GOL in unified) — tieni
            azione = 'TIENI SEGNO (puro, no GOL)'
            return unified
        else:
            result.pop(segno_idx)
            azione = 'ELIMINATO'

    # --- FASCIA 6 (2.10-2.49): Escalation O1.5 → DC coerente → O2.5 → DC fallback → ELIMINA ---
    elif 2.10 <= quota < 2.50:
        fascia = '2.10-2.49'
        if over15_q >= 1.40:
            result[segno_idx] = _make_sostituto('Over 1.5', over15_q)
            azione = f'Over 1.5 @{over15_q:.2f}'
        elif _try_dc_from_segno()[0] is not None:
            dc_pred, dc_azione = _try_dc_from_segno()
            result[segno_idx] = dc_pred
            azione = dc_azione
        elif over25_q >= 1.35:
            result[segno_idx] = _make_sostituto('Over 2.5', over25_q)
            azione = f'Over 2.5 @{over25_q:.2f}'
        else:
            # DC coerente col segno: SEGNO 1 → DC 1X (solo >= 1.65), SEGNO 2 → DC X2 (>= 1.35)
            dc_q = dc_1x_q if segno == '1' else dc_x2_q if segno == '2' else 0
            dc_label = '1X' if segno == '1' else 'X2' if segno == '2' else None
            dc_min = 1.65 if dc_label == '1X' else 1.35
            if dc_q >= dc_min and dc_label:
                sost = _make_sostituto(dc_label, dc_q)
                sost['tipo'] = 'DOPPIA_CHANCE'
                result[segno_idx] = sost
                azione = f'DC {dc_label} @{dc_q:.2f}'
            else:
                result.pop(segno_idx)
                azione = 'ELIMINATO'

    # --- FASCIA 7 (2.50-3.69): O1.5 → DC coerente (solo X2 o 1X >= 1.65) ---
    elif 2.50 <= quota < 3.70:
        fascia = '2.50-3.69'
        if over15_q >= 1.40:
            result[segno_idx] = _make_sostituto('Over 1.5', over15_q)
            azione = f'Over 1.5 @{over15_q:.2f}'
        else:
            dc_q = dc_1x_q if segno == '1' else dc_x2_q if segno == '2' else 0
            dc_label = '1X' if segno == '1' else 'X2' if segno == '2' else None
            # 1X solo se quota >= 1.65 (sotto non rende), X2 ok da 1.35
            dc_min = 1.65 if dc_label == '1X' else 1.35
            if dc_label and dc_q >= dc_min:
                sost = _make_sostituto(dc_label, dc_q)
                sost['tipo'] = 'DOPPIA_CHANCE'
                result[segno_idx] = sost
                azione = f'DC {dc_label} @{dc_q:.2f}'
            elif dc_label and dc_q >= 1.35:
                # 1X con quota < 1.65: tieni SEGNO originale (più profittevole)
                azione = 'TIENI SEGNO (1X quota troppo bassa)'
                return unified
            else:
                result.pop(segno_idx)
                azione = 'ELIMINATO'

    # --- FASCIA 8 (3.70+): SEGNO resta (AR) + AGGIUNGI DC coerente ---
    elif quota >= 3.70:
        fascia = '3.70+'
        dc_q = dc_1x_q if segno == '1' else dc_x2_q if segno == '2' else 0
        dc_label = '1X' if segno == '1' else 'X2' if segno == '2' else None
        # Controlla coerenza: no DC se esiste già qualsiasi DC o SEGNO incoerente
        dc_gia_presente = any(p.get('tipo') == 'DOPPIA_CHANCE' for p in unified if p is not segno_pred)
        segno_incoerente = any(
            p.get('tipo') == 'SEGNO' and p.get('pronostico') != segno
            for p in unified if p is not segno_pred
        )
        if dc_label and not dc_gia_presente and not segno_incoerente:
            sost = _make_sostituto(dc_label, dc_q if dc_q >= 1.35 else None)
            sost['tipo'] = 'DOPPIA_CHANCE'
            result.append(sost)  # AGGIUNGI (non sostituisci) — SEGNO resta
            azione = f'TIENI SEGNO + DC {dc_label} @{dc_q:.2f}' if dc_q >= 1.35 else f'TIENI SEGNO + DC {dc_label}'
        else:
            azione = 'TIENI SEGNO (DC non aggiunta: conflitto)'
            return unified

    else:
        return unified

    # --- SOGLIA DIFFERENZA QUOTA: se la conversione abbassa la quota oltre il 43%, tieni il SEGNO ---
    # Analisi storica 2 mesi (132 casi): soglia -43% = punto ottimale HR/PL (+245u vs +116u)
    SCR_MAX_QUOTA_DROP_PCT = -43
    if segno_idx < len(result) and azione != 'ELIMINATO':
        sost = result[segno_idx]
        nuova_q = sost.get('quota', 0) or 0
        if quota > 0 and nuova_q > 0:
            pct_diff = (nuova_q - quota) / quota * 100
            if pct_diff < SCR_MAX_QUOTA_DROP_PCT:
                print(f"    SOGLIA SCREM: {segno} @{quota:.2f} -> @{nuova_q:.2f} ({pct_diff:.0f}%) supera {SCR_MAX_QUOTA_DROP_PCT}% — tieni originale")
                return unified

    # --- DEDUP: se il sostituto è un mercato già presente nell'unified, rimuovi il SEGNO ---
    if segno_idx < len(result):
        sost = result[segno_idx]
        sost_tipo = sost.get('tipo', '')
        sost_pron = sost.get('pronostico', '')
        if sost.get('routing_rule') == 'scrematura_segno' and _mercato_gia_presente(sost_pron, sost_tipo):
            result.pop(segno_idx)
            azione = f'rimosso ({sost_pron} già presente)'

    print(f"    🔄 SCREMATURA: SEGNO {segno} @{quota:.2f} → {azione} (fascia {fascia})")

    # --- DC deboli: converti o scarta in base alla fascia di quota ---
    if segno_idx < len(result):
        sost = result[segno_idx]
        if (sost.get('tipo') == 'DOPPIA_CHANCE'
                and sost.get('routing_rule') == 'scrematura_segno'):
            dc_q = sost.get('quota') or 0

            # DC quota 1.30-1.40: converti in Over 1.5 se disponibile, altrimenti scarta
            if 1.30 <= dc_q < 1.40:
                o15_q = None
                if c_doc:
                    for p in c_doc.get('pronostici', []):
                        if p.get('pronostico') == 'Over 1.5':
                            o15_q = p.get('quota')
                            break
                if o15_q and o15_q >= 1.35:
                    o15_pred = {
                        'tipo': 'GOL',
                        'pronostico': 'Over 1.5',
                        'quota': o15_q,
                        'confidence': sost.get('confidence', 55),
                        'stars': sost.get('stars', 3.0),
                        'source': 'C_screm_o15',
                        'routing_rule': 'screm_dc_to_over15',
                        'original_pronostico': segno,
                        'original_quota': quota,
                        'has_odds': True,
                    }
                    if o15_q > 1.0:
                        prob_mod = 0.85
                        prob_mkt = 1.0 / o15_q
                        edge = prob_mod - prob_mkt
                        if edge > 0:
                            kelly = 0.75 * (edge * o15_q) / (o15_q - 1)
                            o15_pred['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), o15_q)
                            o15_pred['edge'] = round(edge * 100, 1)
                        else:
                            o15_pred['stake'] = 1
                            o15_pred['edge'] = 0
                        o15_pred['prob_mercato'] = round(prob_mkt * 100, 1)
                        o15_pred['prob_modello'] = round(prob_mod * 100, 1)
                        o15_pred['probabilita_stimata'] = round(prob_mod * 100, 1)
                    result[segno_idx] = o15_pred
                    print(f"    🔄 DC→O15: DC {sost.get('pronostico')} @{dc_q:.2f} → Over 1.5 @{o15_q}")
                else:
                    result.pop(segno_idx)
                    print(f"    🗑️ DC SCARTATA: {sost.get('pronostico')} @{dc_q:.2f} (1.30-1.40), no O1.5")

            # DC quota > 1.60: converti in Under 2.5 se disponibile, altrimenti scarta
            elif dc_q > 1.60:
                u25_q = None
                if c_doc:
                    for p in c_doc.get('pronostici', []):
                        if p.get('pronostico') == 'Under 2.5':
                            u25_q = p.get('quota')
                            break
                if u25_q and u25_q >= 1.35:
                    u25_pred = {
                        'tipo': 'GOL',
                        'pronostico': 'Under 2.5',
                        'quota': u25_q,
                        'confidence': sost.get('confidence', 55),
                        'stars': sost.get('stars', 3.0),
                        'source': 'C_screm_u25',
                        'routing_rule': 'screm_dc_to_under25',
                        'original_pronostico': segno,
                        'original_quota': quota,
                        'has_odds': True,
                    }
                    if u25_q > 1.0:
                        prob_mod = 0.70
                        prob_mkt = 1.0 / u25_q
                        edge = prob_mod - prob_mkt
                        if edge > 0:
                            kelly = 0.75 * (edge * u25_q) / (u25_q - 1)
                            u25_pred['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), u25_q)
                            u25_pred['edge'] = round(edge * 100, 1)
                        else:
                            u25_pred['stake'] = 1
                            u25_pred['edge'] = 0
                        u25_pred['prob_mercato'] = round(prob_mkt * 100, 1)
                        u25_pred['prob_modello'] = round(prob_mod * 100, 1)
                        u25_pred['probabilita_stimata'] = round(prob_mod * 100, 1)
                    result[segno_idx] = u25_pred
                    print(f"    🔄 DC→U25: DC {sost.get('pronostico')} @{dc_q:.2f} → Under 2.5 @{u25_q}")
                else:
                    result.pop(segno_idx)
                    print(f"    🗑️ DC SCARTATA: {sost.get('pronostico')} @{dc_q:.2f} > 1.60, no U2.5")

    return result


# =====================================================
# RECOVERY A+S Over 2.5 debole → alternativa da engine_c
# =====================================================
def _apply_weak_o25_recovery(unified, c_doc):
    """
    Quando A+S emette Over 2.5 con score < 70, sostituisce con alternativa
    da engine_c in ordine di priorità:
    1. SEGNO 1 quota 1.50-2.51 (HR 61%, ROI +25.2% su 23 campioni)
    2. DC X2 (HR 71.4% su 7 campioni)
    3. Under 2.5 quota >= 1.35 (HR 66.7% su 12 campioni)
    4. Nessuna alternativa → scarta
    """
    if not c_doc:
        return unified

    # Trova A+S Over 2.5 con score < 70
    o25_idx = None
    o25_pred = None
    for i, p in enumerate(unified):
        if (p.get('source') == 'A+S'
                and p.get('pronostico') == 'Over 2.5'
                and (p.get('confidence') or 0) < 70):
            o25_idx = i
            o25_pred = p
            break

    if o25_pred is None:
        return unified

    # Cerca alternative in engine_c
    ec_preds = {p.get('pronostico'): p for p in c_doc.get('pronostici', [])}
    odds = c_doc.get('odds', {})
    q1 = float(odds.get('1') or 0)
    qx = float(odds.get('X') or odds.get('x') or 0)
    q2 = float(odds.get('2') or 0)

    result = list(unified)

    def _make_recovery(tipo, pronostico, quota, source, routing_rule, prob_mod):
        pred = {
            'tipo': tipo,
            'pronostico': pronostico,
            'quota': quota,
            'confidence': o25_pred.get('confidence', 60),
            'stars': o25_pred.get('stars', 3.0),
            'source': source,
            'routing_rule': routing_rule,
            'original_pronostico': 'Over 2.5',
            'original_quota': o25_pred.get('quota', 0),
            'has_odds': True,
        }
        if quota and quota > 1.0:
            prob_mkt = 1.0 / quota
            edge = prob_mod - prob_mkt
            if edge > 0:
                kelly = 0.75 * (edge * quota) / (quota - 1)
                pred['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), quota)
                pred['edge'] = round(edge * 100, 1)
            else:
                pred['stake'] = 1
                pred['edge'] = 0
            pred['prob_mercato'] = round(prob_mkt * 100, 1)
            pred['prob_modello'] = round(prob_mod * 100, 1)
            pred['probabilita_stimata'] = round(prob_mod * 100, 1)
        return pred

    # Verifica che non esista già un SEGNO in unified (evita duplicati)
    has_segno = any(p.get('tipo') == 'SEGNO' for p in unified)

    # PRIORITÀ 1: SEGNO 1 quota 1.50-2.51
    segno1 = ec_preds.get('1') or next(
        (p for p in c_doc.get('pronostici', [])
         if p.get('tipo') == 'SEGNO' and p.get('pronostico') == '1'), None)
    if segno1 and not has_segno:
        sq = segno1.get('quota') or 0
        if 1.50 <= sq < 2.51:
            result[o25_idx] = _make_recovery(
                'SEGNO', '1', sq, 'C_as_segno1_rec', 'as_o25_to_segno1', 0.65)
            print(f"    🔄 O25 RECOVERY: Over 2.5 A+S (score {o25_pred.get('confidence')}) → SEGNO 1 @{sq:.2f}")
            return result

    # PRIORITÀ 2: DC X2 (calcolata da quote)
    # Se c'è già un SEGNO, la DC potrebbe contraddirlo (es. SEGNO 1 + DC X2)
    # In quel caso elimina l'Over 2.5 debole senza sostituire
    if has_segno:
        result.pop(o25_idx)
        print(f"    🗑️ O25 SCARTATO: Over 2.5 A+S (score {o25_pred.get('confidence')}) — SEGNO già presente, DC sarebbe incoerente")
        return result
    if qx > 1 and q2 > 1:
        dc_q = round(1 / (1/qx + 1/q2), 2)
        if 2.00 <= dc_q <= 2.50:
            # Converti a X2 solo se quota tra 2.00-2.50 (storico: 2 SALV, 1 DANN, P/L +27.9u)
            has_dc = any(p.get('tipo') == 'DOPPIA_CHANCE' for p in unified)
            if not has_dc:
                result[o25_idx] = _make_recovery(
                    'DOPPIA_CHANCE', 'X2', dc_q, 'C_as_dc_rec', 'as_o25_to_dc', 0.70)
                print(f"    🔄 O25 RECOVERY: Over 2.5 A+S (score {o25_pred.get('confidence')}) → DC X2 @{dc_q:.2f}")
                return result

    # PRIORITÀ 3: Under 2.5 — gerarchia 2 livelli (78% HR vs 64% attuale)
    # L1: DQ ≤ 0 (U2.5 costa meno di O2.5, mercato favorisce Under) → 100% HR
    # L2: DQ > 0 + U2.5 ≥ 2.10 → 60% HR
    # Altrimenti: NO BET
    u25 = ec_preds.get('Under 2.5') or next(
        (p for p in c_doc.get('pronostici', [])
         if p.get('pronostico') == 'Under 2.5'), None)
    if u25:
        uq = u25.get('quota') or 0
        o25_q = o25_pred.get('quota') or 0
        dq = uq - o25_q if uq > 0 and o25_q > 0 else 999
        l1 = dq <= 0                    # U2.5 ≤ O2.5: mercato favorisce Under
        l2 = dq > 0 and uq >= 2.10     # U2.5 alta ma ≥ 2.10

        if uq >= 1.35 and (l1 or l2):
            lvl = 'L1' if l1 else 'L2'
            result[o25_idx] = _make_recovery(
                'GOL', 'Under 2.5', uq, 'C_as_u25_rec', 'as_o25_to_under25', 0.67)
            print(f"    🔄 O25 RECOVERY({lvl}): Over 2.5 @{o25_q:.2f} → Under 2.5 @{uq:.2f} (DQ={dq:+.2f})")
            return result

        if uq > 0 and not (l1 or l2):
            # Nessun livello soddisfatto → NO BET
            result[o25_idx] = {
                'tipo': 'GOL', 'pronostico': 'NO BET', 'quota': 0, 'stake': 0,
                'original_pronostico': 'Over 2.5', 'original_quota': o25_q,
                'routing_rule': 'as_o25_to_under25',
                'source': o25_pred.get('source', ''),
            }
            print(f"    🚫 O25 RECOVERY: Over 2.5 @{o25_q:.2f}, U2.5 @{uq:.2f} (DQ={dq:+.2f}) → NO BET (fuori gerarchia)")
            return result

    # PRIORITÀ 4: nessuna alternativa → scarta
    result.pop(o25_idx)
    print(f"    🗑️ O25 SCARTATO: Over 2.5 A+S (score {o25_pred.get('confidence')}) — no alternative")
    return result


# =====================================================
# FILTRO SEGNO basato su Top4 Monte Carlo
# =====================================================
# Regole validate su 134 partite (13/02-03/03):
#   Algo: 68% HR, +26.56u | Con filtro: 76% HR, +31.35u, 0.352u/bet
# Pattern: classifica i top4 MC scores per segno e applica regole
# Decisioni: TIENI (mantieni segno), CONVERTI (→ O1.5), BLOCCA (rimuovi)

def _apply_diamond_recovery(unified_pronostici, docs_by_sys, match_key, match_odds):
    """
    Recovery pattern diamante: recupera pronostici scartati che matchano pattern ad alta HR.
    Va eseguito DOPO tutti i filtri e dedup.
    Analisi 29/03/2026: 8 pattern con HR 68-90% tra pronostici scartati.
    REGOLA: si attiva SOLO su partite senza pronostici reali (NO BET o vuote).
    """
    # Mercati già coperti — il recovery aggiunge solo mercati mancanti
    existing = set()
    existing_markets = set()  # 'GOL', 'SEGNO', 'DOPPIA_CHANCE'
    for p in unified_pronostici:
        pron = p.get('pronostico', '')
        tipo = p.get('tipo', '')
        if pron and pron != 'NO BET' and tipo != 'RISULTATO_ESATTO':
            existing.add((tipo, pron))
            existing_markets.add(tipo)

    # Carica pronostici dai 3 sistemi
    sys_preds = {}  # sys_id -> list of {tipo, pronostico, confidence, quota}
    for sys_id in ['A', 'S', 'C']:
        doc = docs_by_sys[sys_id].get(match_key)
        if doc:
            sys_preds[sys_id] = [
                {
                    'tipo': p.get('tipo', ''),
                    'pronostico': p.get('pronostico', ''),
                    'confidence': p.get('confidence', 0),
                    'quota': p.get('quota', 0) or 0,
                    'stars': p.get('stars', 0),
                    'probabilita_stimata': p.get('probabilita_stimata'),
                }
                for p in doc.get('pronostici', [])
                if p.get('pronostico') and p['pronostico'] != 'NO BET' and p.get('tipo') != 'RISULTATO_ESATTO'
            ]
        else:
            sys_preds[sys_id] = []

    # Helper: cerca pronostico in un sistema
    def find_pred(sys_id, tipo, pronostico):
        for p in sys_preds.get(sys_id, []):
            if p['tipo'] == tipo and p['pronostico'].lower().strip() == pronostico.lower().strip():
                return p
        return None

    # Spread quote 1X2
    q1 = float(match_odds.get('1') or 0)
    q2 = float(match_odds.get('2') or 0)
    min_q = min(q1, q2) if q1 > 0 and q2 > 0 else 0
    max_q = max(q1, q2) if q1 > 0 and q2 > 0 else 0
    spread = round(max_q - min_q, 2) if min_q > 0 else 0

    recovered = []

    # === PATTERN 1 & 2: Under 3.5, Sistema A/S, conf 60+ ===
    if 'GOL' not in existing_markets:
        for sys_id in ['A', 'S']:
            pred = find_pred(sys_id, 'GOL', 'Under 3.5')
            if pred and pred['confidence'] >= 60 and pred['quota'] >= 1.35:
                recovered.append({**pred, 'source': f'{sys_id}_diamond_u35', 'routing_rule': 'diamond_pattern_1_2'})
                existing.add(('GOL', 'Under 3.5'))

                print(f"    💎 DIAMOND P1/2: Under 3.5 recuperato da {sys_id} conf={pred['confidence']:.0f} @{pred['quota']:.2f}")
                break

    # === PATTERN 4: Over 1.5, Sistema A, conf 65+ ===
    if 'GOL' not in existing_markets:
        pred = find_pred('A', 'GOL', 'Over 1.5')
        if pred and pred['confidence'] >= 65 and pred['quota'] >= 1.35:
            recovered.append({**pred, 'source': 'A_diamond_o15', 'routing_rule': 'diamond_pattern_4'})
            existing.add(('GOL', 'Over 1.5'))
            existing_markets.add('GOL')
            print(f"    💎 DIAMOND P4: Over 1.5 recuperato da A conf={pred['confidence']:.0f} @{pred['quota']:.2f}")

    # === PATTERN 24: Under 3.5, A+S concordano, conf 65+ ===
    if 'GOL' not in existing_markets:
        pred_a = find_pred('A', 'GOL', 'Under 3.5')
        pred_s = find_pred('S', 'GOL', 'Under 3.5')
        if pred_a and pred_s and pred_a['confidence'] >= 65 and pred_s['confidence'] >= 65:
            best = pred_a if pred_a['confidence'] >= pred_s['confidence'] else pred_s
            if best['quota'] >= 1.35:
                recovered.append({**best, 'source': 'AS_diamond_u35', 'routing_rule': 'diamond_pattern_24'})
                existing.add(('GOL', 'Under 3.5'))

                print(f"    💎 DIAMOND P24: Under 3.5 A+S concordano conf_a={pred_a['confidence']:.0f} conf_s={pred_s['confidence']:.0f}")

    # === PATTERN 23: Under 3.5, A+C concordano, conf 65+ ===
    if 'GOL' not in existing_markets:
        pred_a = find_pred('A', 'GOL', 'Under 3.5')
        pred_c = find_pred('C', 'GOL', 'Under 3.5')
        if pred_a and pred_c and pred_a['confidence'] >= 65 and pred_c['confidence'] >= 65:
            best = pred_a if pred_a['confidence'] >= pred_c['confidence'] else pred_c
            if best['quota'] >= 1.35:
                recovered.append({**best, 'source': 'AC_diamond_u35', 'routing_rule': 'diamond_pattern_23'})
                existing.add(('GOL', 'Under 3.5'))

                print(f"    💎 DIAMOND P23: Under 3.5 A+C concordano conf_a={pred_a['confidence']:.0f} conf_c={pred_c['confidence']:.0f}")

    # === PATTERN 14: Goal/GG, Sistema C, conf 65+ ===
    if 'GOL' not in existing_markets:
        pred = find_pred('C', 'GOL', 'Goal')
        if not pred:
            pred = find_pred('C', 'GOL', 'GG')
        if pred and pred['confidence'] >= 65 and pred['quota'] >= 1.35:
            recovered.append({**pred, 'pronostico': 'Goal', 'source': 'C_diamond_goal', 'routing_rule': 'diamond_pattern_14'})
            existing.add(('GOL', 'Goal'))
            existing_markets.add('GOL')
            print(f"    💎 DIAMOND P14: Goal recuperato da C conf={pred['confidence']:.0f} @{pred['quota']:.2f}")

    # === PATTERN 5: Over 1.5, Sistema C, conf 75+ (due vie) ===
    if 'GOL' not in existing_markets:
        pred = find_pred('C', 'GOL', 'Over 1.5')
        if pred and pred['confidence'] >= 75 and pred['quota'] >= 1.35:
            via_a = spread <= 1.0 and pred['quota'] >= 1.45
            via_b = pred['confidence'] >= 80 and pred['quota'] >= 1.50
            if via_a or via_b:
                via = 'A' if via_a else 'B'
                recovered.append({**pred, 'source': f'C_diamond_o15_via{via}', 'routing_rule': 'diamond_pattern_5'})
                existing.add(('GOL', 'Over 1.5'))

                print(f"    💎 DIAMOND P5: Over 1.5 recuperato da C via {via} conf={pred['confidence']:.0f} @{pred['quota']:.2f} spread={spread}")

    # === PATTERN 18: Over 2.5, 3/3 concordano, gerarchia ===
    if 'GOL' not in existing_markets:
        pred_a = find_pred('A', 'GOL', 'Over 2.5')
        pred_s = find_pred('S', 'GOL', 'Over 2.5')
        pred_c = find_pred('C', 'GOL', 'Over 2.5')
        if pred_a and pred_s and pred_c:
            confs = [pred_a['confidence'], pred_s['confidence'], pred_c['confidence']]
            avg_conf = sum(confs) / 3
            min_conf = min(confs)
            best = max([pred_a, pred_s, pred_c], key=lambda p: p['confidence'])

            if avg_conf >= 65 and best['quota'] >= 1.35:
                if min_conf >= 70:
                    level = 1
                elif min_conf >= 65 and best['quota'] >= 1.50:
                    level = 2
                else:
                    level = 3

                recovered.append({**best, 'source': f'ASC_diamond_o25_L{level}', 'routing_rule': f'diamond_pattern_18_L{level}'})
                existing.add(('GOL', 'Over 2.5'))

                print(f"    💎 DIAMOND P18 L{level}: Over 2.5 3/3 concordano min_conf={min_conf:.0f} avg={avg_conf:.0f} @{best['quota']:.2f}")

    # === PATTERN 10: SEGNO 1, Sistema C, conf 70-79, quota >= 1.50 ===
    if 'SEGNO' not in existing_markets:
        pred = find_pred('C', 'SEGNO', '1')
        if pred and 70 <= pred['confidence'] < 80 and pred['quota'] >= 1.50:
            recovered.append({**pred, 'source': 'C_diamond_segno1', 'routing_rule': 'diamond_pattern_10'})
            existing.add(('SEGNO', '1'))
            pass  # no market lock
            print(f"    💎 DIAMOND P10: SEGNO 1 recuperato da C conf={pred['confidence']:.0f} @{pred['quota']:.2f}")

    # (Pattern 18 già gestito sopra)

    # Aggiungi has_odds ai recuperati
    for r in recovered:
        r['has_odds'] = True
        r['diamond'] = True  # Flag per identificare i recuperati

    return unified_pronostici + recovered


def _apply_segno_mc_filter(unified, simulation_data, odds):
    """
    Filtro SEGNO basato su pattern Monte Carlo top4.
    Classifica la concordanza tra pronostico SEGNO e top4 MC scores,
    poi decide: TIENI / CONVERTI a O1.5 / BLOCCA.
    """
    # Trova il pronostico SEGNO
    segno_pred = None
    segno_idx = None
    for i, p in enumerate(unified):
        if p.get('tipo') == 'SEGNO' and p.get('pronostico') in ('1', '2', 'X'):
            segno_pred = p
            segno_idx = i
            break

    if segno_pred is None or simulation_data is None:
        return unified

    top_scores = simulation_data.get('top_scores', [])[:4]
    if len(top_scores) < 4:
        return unified

    segno = segno_pred.get('pronostico', '')
    quota = segno_pred.get('quota', 0) or 0

    # --- Calcola metriche dai top4 ---
    signs = []
    total_goals = 0
    max_margin = 0
    gg_count = 0
    counts = []

    for sp in top_scores:
        score = sp[0] if isinstance(sp, list) else sp
        count = sp[1] if isinstance(sp, list) and len(sp) > 1 else 0
        counts.append(count)
        sign = _score_to_sign(score)
        if sign:
            signs.append(sign)
        parts = str(score).replace(':', '-').split('-')
        if len(parts) == 2:
            try:
                h, a = int(parts[0]), int(parts[1])
                total_goals += h + a
                margin = abs(h - a)
                if margin > max_margin:
                    max_margin = margin
                if h > 0 and a > 0:
                    gg_count += 1
            except ValueError:
                pass

    if len(signs) < 4:
        return unified

    # Conta segni
    sign_counts = {}
    for s in signs:
        sign_counts[s] = sign_counts.get(s, 0) + 1
    pron_count = sign_counts.get(segno, 0)
    unique_signs = len(sign_counts)
    opposite = '2' if segno == '1' else ('1' if segno == '2' else None)
    has_opposite = sign_counts.get(opposite, 0) > 0 if opposite else False
    spread = max(counts) - min(counts) if counts else 0

    # --- Albero decisionale ---
    decision = 'TIENI'
    reason = ''

    # TRIPLA: tutti e 3 i segni presenti
    if unique_signs == 3:
        if total_goals >= 9:
            decision = 'BLOCCA'
            reason = 'TRIPLA + gol>=9 (0% HR storico)'
        elif 1.65 <= quota < 1.80:
            decision = 'BLOCCA'
            reason = 'TRIPLA fascia 1.65-1.80 (30% HR storico)'
        else:
            decision = 'TIENI'
            reason = f'TRIPLA fascia ok (quota {quota:.2f})'

    # ASSENTE: segno pronosticato 0/4
    elif pron_count == 0:
        if gg_count >= 2:
            decision = 'BLOCCA'
            reason = 'ASSENTE + GG>=2 (ex-converti, disattivato)'
        else:
            decision = 'BLOCCA'
            reason = 'ASSENTE senza gol'

    # 4/4: unanime
    elif pron_count == 4:
        decision = 'TIENI'
        reason = '4/4 unanime (81% HR)'

    # 3su4 + X (pareggio)
    elif pron_count == 3 and not has_opposite:
        if max_margin >= 3:
            decision = 'TIENI'
            reason = f'3su4+X margine {max_margin}>=3 (93% HR)'
        elif max_margin == 2:
            if total_goals >= 8:
                decision = 'BLOCCA'
                reason = f'3su4+X margine=2 gol={total_goals}>=8 (ex-converti, disattivato)'
            else:
                decision = 'BLOCCA'
                reason = f'3su4+X margine=2 gol={total_goals}<8 (56% HR)'
        else:
            decision = 'BLOCCA'
            reason = f'3su4+X margine {max_margin}<=1 (ex-converti, disattivato)'

    # 3su4 + OPPOSTO
    elif pron_count == 3 and has_opposite:
        if spread < 5:
            decision = 'BLOCCA'
            reason = f'3su4+OPP spread={spread}<5 (50% HR)'
        else:
            decision = 'BLOCCA'
            reason = f'3su4+OPP spread={spread}>=5 (ex-converti, disattivato)'

    # 2su4
    elif pron_count == 2:
        if total_goals <= 5:
            decision = 'TIENI'
            reason = f'2su4 gol={total_goals}<=5 (81% HR)'
        else:
            decision = 'BLOCCA'
            reason = f'2su4 gol={total_goals}>5 (50% HR)'

    # 1su4 o altro
    else:
        decision = 'BLOCCA'
        reason = f'pron_count={pron_count} non classificato'

    # --- Applica decisione ---
    result = list(unified)

    if decision == 'TIENI':
        print(f"    🎯 FILTRO MC: SEGNO {segno} @{quota:.2f} → TIENI ({reason})")
        return result

    elif decision == 'CONVERTI':
        over15_q = odds.get('over_15', 0) or 0
        if over15_q >= 1.35:
            # Crea sostituto O1.5
            prob = segno_pred.get('probabilita_stimata', 70)
            sost = {
                'tipo': 'GOL',
                'pronostico': 'Over 1.5',
                'quota': over15_q,
                'confidence': segno_pred.get('confidence', 60),
                'stars': segno_pred.get('stars', 3),
                'source': segno_pred.get('source', '') + '_mc_conv',
                'routing_rule': 'mc_filter_convert',
                'original_pronostico': segno,
                'original_quota': quota,
                'has_odds': True,
            }
            if over15_q > 1.0:
                prob_mkt = 1.0 / over15_q
                edge = (prob / 100.0) - prob_mkt
                if edge > 0:
                    kelly = 0.75 * (edge * over15_q - (1 - edge)) / (over15_q - 1)
                    sost['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), over15_q)
                else:
                    sost['stake'] = 1
                sost['edge'] = round(edge * 100, 1)
                sost['prob_mercato'] = round(prob_mkt * 100, 1)
                sost['probabilita_stimata'] = prob
            result[segno_idx] = sost
            print(f"    🔄 FILTRO MC: SEGNO {segno} @{quota:.2f} → CONVERTI O1.5 @{over15_q:.2f} ({reason})")
        else:
            # No quote O1.5 disponibili → blocca
            result.pop(segno_idx)
            print(f"    🚫 FILTRO MC: SEGNO {segno} @{quota:.2f} → BLOCCA (converti ma no O1.5 disponibile)")
        return result

    else:  # BLOCCA
        result.pop(segno_idx)
        print(f"    🚫 FILTRO MC: SEGNO {segno} @{quota:.2f} → BLOCCA ({reason})")
        return result


# =====================================================
# DEDUP GOL CORRELATI
# =====================================================
# Tabella: (pronostico_A, pronostico_B) → chi rimuovere (A o B)
# Se entrambi presenti sulla stessa partita, rimuovi il perdente
_GOL_DEDUP_RULES = {
    # Over + Over → tieni il più sicuro (soglia bassa)
    ('Over 2.5', 'Over 1.5'): 'Over 2.5',
    ('Over 1.5', 'Over 3.5'): 'Over 3.5',
    ('Over 2.5', 'Over 3.5'): 'Over 3.5',
    # Under + Under → tieni il più sicuro (soglia alta)
    ('Under 2.5', 'Under 3.5'): 'Under 2.5',
    # Over + Goal → varie
    ('Over 2.5', 'Goal'): 'Over 2.5',       # GG 83% HR > O2.5 50%
    ('Over 1.5', 'Goal'): 'Goal',            # O1.5 ~100% HR
    ('Over 3.5', 'Goal'): 'Goal',            # O3.5 forte → tieni O3.5
    # Over + No Goal → tieni Over (Over è la previsione forte)
    ('Over 1.5', 'No Goal'): 'No Goal',
    ('Over 2.5', 'No Goal'): 'No Goal',
    ('Over 3.5', 'No Goal'): 'No Goal',
    # Under + Goal → conflitto, tieni Under
    ('Under 2.5', 'Goal'): 'Goal',
    ('Under 3.5', 'Goal'): 'Goal',
    # Under + No Goal → ridondante, tieni Under
    ('Under 3.5', 'No Goal'): 'No Goal',
    # Under + Over → conflitto, tieni Under
    ('Under 2.5', 'Over 1.5'): 'Over 1.5',
    ('Under 3.5', 'Over 1.5'): 'Over 1.5',
}


def _add_exact_score_predictions(unified, c_doc, match_odds=None):
    """Aggiunge pronostici RISULTATO_ESATTO basati su strategia MC + filtro discordanza book/MC.
    Filtro 1 (attuale): somma top4 counts 35-39 o 65-69, Pos1 count 10-11, Pos2 count 20-21.
    Filtro 2 (nuovo): regole discordanza book/MC per conferma.
    Backtest combinato: 25.0% su 12 partite."""
    if not c_doc:
        return unified
    sim_data = c_doc.get('simulation_data', {})
    top_scores = sim_data.get('top_scores', [])
    if len(top_scores) < 4:
        return unified

    # --- FILTRO 1: metodo attuale (mc_sum + mc_count) ---
    sum_counts = sum(ts[1] for ts in top_scores[:4])
    if not ((35 <= sum_counts <= 39) or (65 <= sum_counts <= 69)):
        return unified

    c1 = top_scores[0][1]
    c2 = top_scores[1][1]

    # Nessuna posizione idonea → esci
    if not (10 <= c1 <= 11) and not (20 <= c2 <= 21):
        return unified

    # --- FILTRO 2: regole discordanza book/MC ---
    odds = match_odds or {}
    if not odds:
        return unified

    # Calcola probabilità MC dalla distribuzione top_scores
    total_sims = sum(ts[1] for ts in top_scores)
    if total_sims == 0:
        return unified

    p_home_win = 0
    p_under25 = 0
    p_nogoal = 0
    for score_str, count in top_scores:
        s = str(score_str)
        parts = s.replace(':', '-').split('-')
        if len(parts) == 2:
            try:
                h, a = int(parts[0]), int(parts[1])
                if h > a:
                    p_home_win += count
                if h + a < 3:
                    p_under25 += count
                if h == 0 or a == 0:
                    p_nogoal += count
            except ValueError:
                pass

    p_home_win = p_home_win / total_sims * 100
    p_away_win = 100 - p_home_win - (sum(c for s, c in top_scores if '-' in str(s) and str(s).split('-')[0] == str(s).split('-')[1]) / total_sims * 100 if total_sims > 0 else 0)
    p_under25 = p_under25 / total_sims * 100
    p_nogoal = p_nogoal / total_sims * 100

    # MC favorita = max(home, away)
    mc_fav_pct = max(p_home_win, p_away_win)

    # Quote book
    q1 = odds.get('1', 0) or 0
    q2 = odds.get('2', 0) or 0
    book_fav_quota = min(q1, q2) if q1 > 0 and q2 > 0 else 0
    q_over25 = odds.get('over_2_5', 0) or 0
    q_goal = odds.get('goal', 0) or 0

    # Verifica se passa almeno una regola
    passes_rule = False

    # R1: Discordanza favorito + partita chiusa → Pos.2
    if (book_fav_quota > 0 and book_fav_quota < 2.0
        and mc_fav_pct < 50
        and p_under25 > 50
        and p_nogoal > 50):
        passes_rule = True

    # R2: Concordano favorito, discordano gol → Pos.1
    if (book_fav_quota > 0 and book_fav_quota < 2.0
        and q_over25 > 0 and q_over25 < 1.80
        and q_goal > 0 and q_goal < 1.80
        and mc_fav_pct >= 50
        and p_under25 > 50
        and p_nogoal > 50):
        passes_rule = True

    # R3: MC incerto + base → Pos.3
    if (book_fav_quota > 0 and book_fav_quota < 2.0
        and q_over25 > 0 and q_over25 < 1.80
        and q_goal > 0 and q_goal < 1.80
        and 40 <= mc_fav_pct <= 50
        and p_under25 > 50
        and p_nogoal > 50):
        passes_rule = True

    if not passes_rule:
        return unified

    # --- Aggiungi RE (solo posizioni che passano filtro 1) ---
    added = []

    if 10 <= c1 <= 11:
        score = str(top_scores[0][0]).replace('-', ':')
        unified.append({
            'pronostico': score,
            'tipo': 'RISULTATO_ESATTO',
            'source': 'MC_RE',
            'quota': None,
            'stake': None,
            'confidence': c1,
            'mc_position': 1,
            'mc_count': c1,
            'mc_sum': sum_counts,
        })
        added.append(f"Pos1 {score} (count {c1})")

    if 20 <= c2 <= 21:
        score = str(top_scores[1][0]).replace('-', ':')
        unified.append({
            'pronostico': score,
            'tipo': 'RISULTATO_ESATTO',
            'source': 'MC_RE',
            'quota': None,
            'stake': None,
            'confidence': c2,
            'mc_position': 2,
            'mc_count': c2,
            'mc_sum': sum_counts,
        })
        added.append(f"Pos2 {score} (count {c2})")

    if added:
        print(f"    RE: somma={sum_counts}, regola discordanza OK, {', '.join(added)}")

    return unified


def _dedup_gol_correlati(unified):
    """
    Rimuove pronostici GOL ridondanti o in conflitto sulla stessa partita.
    Usa la tabella _GOL_DEDUP_RULES per decidere chi rimuovere.
    """
    gol_preds = [(i, p.get('pronostico', '')) for i, p in enumerate(unified) if p.get('tipo') == 'GOL']
    if len(gol_preds) < 2:
        return unified

    to_remove = set()

    # Rimuovi duplicati identici (stesso pronostico, source diversa) — tieni il primo
    seen_pron = {}
    for i, name in gol_preds:
        if name in seen_pron:
            to_remove.add(i)
            print(f"    🔀 DEDUP GOL: duplicato {name} ({unified[i].get('source','')}) — tenuto {unified[seen_pron[name]].get('source','')}")
        else:
            seen_pron[name] = i

    # Controlla ogni coppia
    for a_idx in range(len(gol_preds)):
        for b_idx in range(a_idx + 1, len(gol_preds)):
            i_a, name_a = gol_preds[a_idx]
            i_b, name_b = gol_preds[b_idx]

            # Cerca nella tabella (ordine A,B o B,A)
            loser = _GOL_DEDUP_RULES.get((name_a, name_b))
            if loser is None:
                loser = _GOL_DEDUP_RULES.get((name_b, name_a))

            if loser is not None:
                p_a = unified[i_a]
                p_b = unified[i_b]
                # Priorità 1: preferire chi viene dal mercato GOL originale (non convertito da SEGNO)
                orig_a = p_a.get('original_pronostico', '')
                orig_b = p_b.get('original_pronostico', '')
                a_from_gol = orig_a in ('Goal', 'Over 1.5', 'Over 2.5', 'Over 3.5', 'Under 2.5', 'Under 3.5', 'No Goal', 'NoGoal', '') or not orig_a
                b_from_gol = orig_b in ('Goal', 'Over 1.5', 'Over 2.5', 'Over 3.5', 'Under 2.5', 'Under 3.5', 'No Goal', 'NoGoal', '') or not orig_b

                if a_from_gol and not b_from_gol:
                    # A viene da GOL, B è convertito da altro mercato → rimuovi B
                    to_remove.add(i_b)
                    print(f"    🔀 DEDUP GOL ORIGINE: tenuto {name_a} (mercato GOL), rimosso {name_b} (convertito da {orig_b})")
                elif b_from_gol and not a_from_gol:
                    to_remove.add(i_a)
                    print(f"    🔀 DEDUP GOL ORIGINE: tenuto {name_b} (mercato GOL), rimosso {name_a} (convertito da {orig_a})")
                else:
                    # Priorità 2: entrambi stesso mercato → probabilità stimata più alta vince
                    prob_a = p_a.get('probabilita_stimata', 0) or 0
                    prob_b = p_b.get('probabilita_stimata', 0) or 0
                    if prob_a >= prob_b:
                        to_remove.add(i_b)
                    else:
                        to_remove.add(i_a)

    if to_remove:
        removed = [f"{unified[i].get('pronostico', '')}@{unified[i].get('quota', 0):.2f}({unified[i].get('source', '')})"
                   for i in sorted(to_remove)]
        kept = [f"{p.get('pronostico', '')}@{p.get('quota', 0):.2f}"
                for i, p in enumerate(unified) if p.get('tipo') == 'GOL' and i not in to_remove]
        print(f"    🔀 DEDUP GOL: rimosso {', '.join(removed)}, tenuto {', '.join(kept)}")
        unified = [p for i, p in enumerate(unified) if i not in to_remove]

    return unified


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
                        stake = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), ng_quota)
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
                stake = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), ng_quota)
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
def orchestrate_date(date_str, dry_run=False, match_time_filter=None, preserve_analysis=False):
    """
    Orchestrazione per una singola data.
    Ritorna il numero di documenti scritti.

    Args:
        date_str: data in formato YYYY-MM-DD
        dry_run: se True, non scrive in DB
        match_time_filter: lista di orari per filtrare solo i match di quel gruppo orario.
        preserve_analysis: se True, usa update_one/$set per non cancellare i campi
                          analysis_free/analysis_alerts/analysis_score (usato dal pre-match update).
    """
    # 1. Carica pronostici dai 3 sistemi
    docs_by_sys = {}
    for sys_id, coll_name in COLLECTIONS.items():
        find_filter = {'date': date_str}
        if match_time_filter:
            find_filter['match_time'] = {'$in': match_time_filter}
        docs = list(db[coll_name].find(find_filter))
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

    # 2b. Costruisci mappa giornata e data reale da h2h_by_round per questa data
    # Cerca tutti i round che contengono partite in questa data
    _round_map = {}  # (league, home, away) → round_number (int)
    _real_date_map = {}  # (home, away) → data reale YYYY-MM-DD da h2h_by_round
    try:
        from datetime import timezone as _tz
        _date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        _date_start = _date_obj.replace(hour=0, minute=0, second=0)
        _date_end = _date_obj.replace(hour=23, minute=59, second=59)
        _rounds = db['h2h_by_round'].find(
            {'matches.date_obj': {'$gte': _date_start, '$lte': _date_end}},
            {'league': 1, 'round_name': 1, 'matches.home': 1, 'matches.away': 1, 'matches.date_obj': 1}
        )
        for _r in _rounds:
            _rname = _r.get('round_name', '')
            _rnum_match = re.search(r'(\d+)', _rname)
            _rnum = int(_rnum_match.group(1)) if _rnum_match else None
            if _rnum is None:
                continue
            _league = _r.get('league', '')
            for _m in _r.get('matches', []):
                _md = _m.get('date_obj')
                if _md and _date_start <= _md <= _date_end:
                    _round_map[(_league, _m.get('home', ''), _m.get('away', ''))] = _rnum
                    _real_date_map[(_m.get('home', ''), _m.get('away', ''))] = _md.strftime('%Y-%m-%d')
    except Exception as e:
        print(f"    ⚠️ Errore lookup giornata: {e}")

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

        match_odds = base_doc.get('odds', {})

        # --- POST-PROCESSING: Multi-goal su pronostici deboli ---
        unified_pronostici = _apply_multigol(unified_pronostici, match_odds)

        # --- POST-PROCESSING: Combo #96 — SEGNO 2 → DC X2 ---
        c_doc_for_combo = docs_by_sys['C'].get(match_key)
        if c_doc_for_combo:
            sim_data = c_doc_for_combo.get('simulation_data')
            unified_pronostici = _apply_combo96_dc_flip(unified_pronostici, match_odds, sim_data)
            unified_pronostici = _apply_x_draw_combos(unified_pronostici, match_odds, sim_data)
            unified_pronostici = _apply_home_win_combos(unified_pronostici, match_odds, sim_data)

        # --- POST-PROCESSING: DC Downgrade — SEGNO AR + GG conf 60-65 → DC ---
        if c_doc_for_combo:
            unified_pronostici = _apply_gg_conf_dc_downgrade(unified_pronostici, c_doc_for_combo, match_odds=match_odds)

        # --- POST-PROCESSING: Scrematura SEGNO per fasce di quota ---
        unified_pronostici = _apply_segno_scrematura(unified_pronostici, match_odds, base_doc, c_doc=c_doc_for_combo)

        # --- POST-PROCESSING: Recovery A+S Over 2.5 debole (score < 70) ---
        if c_doc_for_combo:
            unified_pronostici = _apply_weak_o25_recovery(unified_pronostici, c_doc_for_combo)

        # --- FILTRO Under 2.5: quota >= 1.55 solo se engine_c ha SEGNO ---
        # Fascia 1.35-1.55: HR 78%, emetti sempre
        # Fascia >= 1.55 senza SEGNO in engine_c: HR 48%, scarta
        u25_to_remove = set()
        for i, p in enumerate(unified_pronostici):
            if (p.get('pronostico') == 'Under 2.5'
                    and p.get('source') == 'A'
                    and (p.get('quota') or 0) >= 1.55):
                # Verifica se engine_c ha SEGNO 1 o 2
                has_ec_segno = False
                if c_doc_for_combo:
                    for ep in c_doc_for_combo.get('pronostici', []):
                        if ep.get('tipo') == 'SEGNO' and ep.get('pronostico') in ('1', '2'):
                            has_ec_segno = True
                            break
                if not has_ec_segno:
                    u25_to_remove.add(i)
                    print(f"    🗑️ U2.5 FILTRO: Under 2.5 @{p.get('quota', '?')} scartato (q>=1.55, no SEGNO in engine_c)")
        if u25_to_remove:
            unified_pronostici = [p for i, p in enumerate(unified_pronostici) if i not in u25_to_remove]

        # --- SEGNO EXTRA: Under 2.5 quota >= 1.75 + SEGNO engine_c → aggiungi SEGNO ---
        # HR storico 83% su entrambi, SEGNO paga il doppio (ROI +247% vs +98%)
        if c_doc_for_combo:
            has_segno_unified = any(p.get('tipo') == 'SEGNO' for p in unified_pronostici)
            if not has_segno_unified:
                for p in unified_pronostici:
                    if (p.get('pronostico') == 'Under 2.5'
                            and p.get('source') == 'A'
                            and (p.get('quota') or 0) >= 1.75):
                        # Cerca SEGNO 1 o 2 in engine_c
                        for ep in c_doc_for_combo.get('pronostici', []):
                            if ep.get('tipo') == 'SEGNO' and ep.get('pronostico') in ('1', '2'):
                                sq = ep.get('quota') or 0
                                if sq >= 1.35:
                                    segno_extra = {
                                        'tipo': 'SEGNO',
                                        'pronostico': ep.get('pronostico'),
                                        'quota': sq,
                                        'confidence': ep.get('confidence', 55),
                                        'stars': ep.get('stars', 3.0),
                                        'source': 'A_u25_segno_extra',
                                        'routing_rule': 'u25_high_segno_add',
                                        'has_odds': True,
                                    }
                                    prob_mod = 0.70
                                    if sq > 1.0:
                                        prob_mkt = 1.0 / sq
                                        edge = prob_mod - prob_mkt
                                        if edge > 0:
                                            kelly = 0.75 * (edge * sq) / (sq - 1)
                                            segno_extra['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), sq)
                                            segno_extra['edge'] = round(edge * 100, 1)
                                        else:
                                            segno_extra['stake'] = 1
                                            segno_extra['edge'] = 0
                                        segno_extra['prob_mercato'] = round(prob_mkt * 100, 1)
                                        segno_extra['prob_modello'] = round(prob_mod * 100, 1)
                                        segno_extra['probabilita_stimata'] = round(prob_mod * 100, 1)
                                    unified_pronostici.append(segno_extra)
                                    print(f"    ➕ SEGNO EXTRA: U2.5 @{p.get('quota','?')} + SEGNO {ep.get('pronostico')} @{sq:.2f}")
                                break
                        break

        # --- DEDUP: Over/Under conflitto S8F vs A → S8F vince ---
        # S8F (scrematura) ROI 4.2% vs A ROI 1.2% → solo contro fonte A
        s8f_preds = [p for p in unified_pronostici if '_screm' in (p.get('source') or '')]
        a_preds = [p for p in unified_pronostici if (p.get('source') or '') == 'A']
        s8f_has_over = any(p.get('pronostico', '').startswith('Over') for p in s8f_preds)
        s8f_has_under = any(p.get('pronostico', '').startswith('Under') for p in s8f_preds)
        to_remove = []
        if s8f_has_over:
            to_remove += [p for p in a_preds if p.get('pronostico', '').startswith('Under')]
        if s8f_has_under:
            to_remove += [p for p in a_preds if p.get('pronostico', '').startswith('Over')]
        if to_remove:
            removed = [f"{p['pronostico']} @{p.get('quota','?')} ({p.get('source','?')})"
                       for p in to_remove]
            kept = [f"{p['pronostico']} @{p.get('quota','?')} (S8F)"
                    for p in s8f_preds if p.get('pronostico', '').startswith(('Over', 'Under'))]
            print(f"    ⚔️ DEDUP Over/Under: S8F vince su A → rimosso {', '.join(removed)}, tenuto {', '.join(kept)}")
            remove_ids = {id(p) for p in to_remove}
            unified_pronostici = [p for p in unified_pronostici if id(p) not in remove_ids]

        # --- POST-PROCESSING: Over 3.5 @>2.00 → Over 2.5 solo se Q_O25 in [1.75, 2.00) ---
        over25_q = match_odds.get('over_25', 0) or 0
        dg35_remove = set()
        for i, p in enumerate(unified_pronostici):
            if p.get('pronostico') == 'Over 3.5' and (p.get('quota') or 0) > 2.00:
                if 1.75 <= over25_q < 2.00:
                    print(f"    🔄 DOWNGRADE: Over 3.5 @{p.get('quota', '?')} → Over 2.5 @{over25_q:.2f}")
                    unified_pronostici[i]['pronostico'] = 'Over 2.5'
                    unified_pronostici[i]['quota'] = over25_q
                    unified_pronostici[i]['source'] = (p.get('source', '') or '') + '_dg35'
                    # Ricalcola edge/stake
                    prob = p.get('probabilita_stimata', 60)
                    if over25_q > 1.0:
                        prob_mkt = 1.0 / over25_q
                        edge = (prob / 100.0) - prob_mkt
                        if edge > 0:
                            kelly = 0.75 * (edge * over25_q - (1 - edge)) / (over25_q - 1)
                            unified_pronostici[i]['stake'] = _apply_fattore_quota(max(1, min(10, round(kelly * 10))), over25_q)
                            unified_pronostici[i]['edge'] = round(edge * 100, 1)
                        unified_pronostici[i]['prob_mercato'] = round(prob_mkt * 100, 1)
                else:
                    # Q_O25 fuori range [1.75, 2.00) — scarta
                    print(f"    🗑️ SCARTO: Over 3.5 @{p.get('quota', '?')} — Q_O25 {over25_q:.2f} fuori [1.75, 2.00)")
                    dg35_remove.add(i)
        if dg35_remove:
            unified_pronostici = [p for i, p in enumerate(unified_pronostici) if i not in dg35_remove]

        # --- FILTRO OVER 2.5: solo quota <= 1.65 (fasce sicure) ---
        # HR 2 settimane: quota <=1.65 = 73%, quota >1.65 = 42%
        unified_pronostici = [
            p for p in unified_pronostici
            if not (p.get('pronostico') == 'Over 2.5' and (p.get('quota') or 0) > 1.65)
        ]

        # --- FILTRO SEGNO: quota minima 1.50 (fascia 1.35-1.50 sotto break-even) ---
        # Feb 2026: fascia 1.35-1.50 = 58.8% HR vs 68.7% BE necessario, P/L -2.45u
        unified_pronostici = [
            p for p in unified_pronostici
            if not (p.get('pronostico') in ('1', 'X', '2') and (p.get('quota') or 0) < 1.50)
        ]

        # --- FILTRO GLOBALE: quota minima 1.35 su tutti i mercati ---
        unified_pronostici = [
            p for p in unified_pronostici
            if (p.get('quota') or 0) >= 1.35
        ]

        # --- COERENZA MG + Over 2.5: upgrade a MG 3-5 ---
        has_over25 = any(p.get('pronostico') == 'Over 2.5' for p in unified_pronostici)
        has_mg = next((p for p in unified_pronostici if (p.get('pronostico') or '').startswith('MG ')), None)
        if has_over25 and has_mg and has_mg['pronostico'] != 'MG 3-5':
            old_mg = has_mg['pronostico']
            # Ricalcola quota per zona 3-5
            u25 = match_odds.get('under_25')
            if u25:
                try:
                    l_tot = _calc_lambda(float(u25))
                    if l_tot:
                        zone_35 = next((z for z in MULTIGOL_ZONES if z['range'] == '3-5'), None)
                        if zone_35:
                            probs_mg = {g: _poisson(g, l_tot) for g in range(11)}
                            mg_prob = sum(probs_mg[g] for g in zone_35['goals'])
                            mg_quota = round((1 / mg_prob) * MULTIGOL_MARGINE, 2) if mg_prob > 0 else 99
                            has_mg['pronostico'] = 'MG 3-5'
                            has_mg['quota'] = mg_quota
                            has_mg['multigol_detail'] = {
                                'lambda': round(l_tot, 3),
                                'zone': '3-5',
                                'goals': zone_35['goals'],
                                'prob': round(mg_prob * 100, 1),
                            }
                            print(f"    🔄 COERENZA MG: {old_mg} → MG 3-5 @{mg_quota} (Over 2.5 presente)")
                except (TypeError, ValueError):
                    pass

        # --- DEDUP CROSS-SISTEMA: stesso pronostico, fonti diverse → tieni fonte migliore ---
        SOURCE_PRIORITY = {
            'A+S': 1, 'A+S_mg': 1, 'AS': 1,
            'C_screm': 2, 'S8F': 2,
            'A': 3, 'S': 3,
            'C': 4, 'C_dg35': 4,
            'A_flip': 5, 'A_flip_mg': 5,
            'MC_xdraw': 6,
        }

        def _get_source_priority(src):
            """Priorità source con fallback a prefisso (es. A+S_dc_s6_conv → A+S = 1)."""
            if not src:
                return 99
            if src in SOURCE_PRIORITY:
                return SOURCE_PRIORITY[src]
            # Match per prefisso: ordina per lunghezza decrescente per matchare il più specifico
            for key in sorted(SOURCE_PRIORITY, key=len, reverse=True):
                if src.startswith(key):
                    return SOURCE_PRIORITY[key]
            return 99
        seen_pron = {}
        dedup_remove = set()
        for i, p in enumerate(unified_pronostici):
            pron = p.get('pronostico', '')
            if pron:
                if pron in seen_pron:
                    j = seen_pron[pron]
                    old = unified_pronostici[j]
                    old_elite = old.get('elite', False)
                    new_elite = p.get('elite', False)
                    # Elite vince sempre su non-elite
                    if new_elite and not old_elite:
                        new_wins = True
                    elif old_elite and not new_elite:
                        new_wins = False
                    else:
                        # Stessa categoria elite → usa source priority
                        old_prio = _get_source_priority(old.get('source', ''))
                        new_prio = _get_source_priority(p.get('source', ''))
                        new_wins = new_prio < old_prio
                    if new_wins:
                        dedup_remove.add(j)
                        seen_pron[pron] = i
                    else:
                        dedup_remove.add(i)
                    winner = unified_pronostici[seen_pron[pron]]
                    loser_src = p.get('source') if not new_wins else old.get('source')
                    print(f"    🔀 DEDUP: {pron} — tenuto {winner.get('source')}{'👑' if winner.get('elite') else ''}, rimosso {loser_src}")
                else:
                    seen_pron[pron] = i
        if dedup_remove:
            unified_pronostici = [p for i, p in enumerate(unified_pronostici) if i not in dedup_remove]

        # --- ULTIMO FILTRO: SEGNO basato su Top4 Monte Carlo ---
        if c_doc_for_combo:
            sim_data_mc = c_doc_for_combo.get('simulation_data')
            if sim_data_mc:
                unified_pronostici = _apply_segno_mc_filter(unified_pronostici, sim_data_mc, match_odds)

        # --- DEDUP GOL CORRELATI: rimuove ridondanze/conflitti tra pronostici GOL ---
        unified_pronostici = _dedup_gol_correlati(unified_pronostici)

        # --- DEDUP DC CONTRASTANTI: se c'è sia 1X che X2, tieni la migliore ---
        dc_preds = [p for p in unified_pronostici if p.get('tipo') == 'DOPPIA_CHANCE']
        dc_prons = [p.get('pronostico') for p in dc_preds]
        if '1X' in dc_prons and 'X2' in dc_prons:
            dc_1x = next(p for p in dc_preds if p.get('pronostico') == '1X')
            dc_x2 = next(p for p in dc_preds if p.get('pronostico') == 'X2')
            elite_1x = dc_1x.get('elite', False)
            elite_x2 = dc_x2.get('elite', False)

            if elite_1x and not elite_x2:
                # Step 1: elite batte non-elite
                winner, loser = dc_1x, dc_x2
                reason = "elite vs non-elite"
            elif elite_x2 and not elite_1x:
                winner, loser = dc_x2, dc_1x
                reason = "elite vs non-elite"
            else:
                # Step 2: entrambe elite (o entrambe non-elite)
                # Media tra probabilità implicita quota favorita e confidence
                q1 = float(match_odds.get('1') or 0)
                q2 = float(match_odds.get('2') or 0)
                # Per DC 1X: prob implicita = 1/quota_1, per DC X2: prob implicita = 1/quota_2
                prob_1x = (1.0 / q1 * 100) if q1 > 1 else 50
                prob_x2 = (1.0 / q2 * 100) if q2 > 1 else 50
                score_1x = (prob_1x + (dc_1x.get('confidence') or 50)) / 2
                score_x2 = (prob_x2 + (dc_x2.get('confidence') or 50)) / 2

                if score_1x >= score_x2:
                    winner, loser = dc_1x, dc_x2
                else:
                    winner, loser = dc_x2, dc_1x
                reason = f"score 1X={score_1x:.1f} vs X2={score_x2:.1f}"

            unified_pronostici = [p for p in unified_pronostici if p is not loser]
            print(f"    ⚔️ DC CONTRASTANTI: tenuto {winner['pronostico']} @{winner.get('quota','?')}, "
                  f"rimosso {loser['pronostico']} @{loser.get('quota','?')} ({reason})")

        # --- RISULTATO ESATTO MC — DISABILITATO (17/04/2026) ---
        # unified_pronostici = _add_exact_score_predictions(unified_pronostici, c_doc_for_combo, match_odds)

        # --- DIAMOND RECOVERY: recupera pronostici scartati con pattern ad alta HR ---
        unified_pronostici = _apply_diamond_recovery(unified_pronostici, docs_by_sys, match_key, match_odds)

        if not unified_pronostici:
            continue

        # --- STAKE EMPIRICO: basato su HR reale per fascia di confidence e mercato ---
        # ⚠️ PER DISATTIVARE: commentare tutto il blocco fino a "# Costruisci documento unified"
        # e lo stake tornera' a quello calcolato dal Kelly Criterion (codice sopra)
        # Ogni entry: (conf_min, conf_max, stake) — ordinate per HR decrescente (stake 10 = migliore)
        STAKE_SEGNI = [
            # Lv1 HR 76.8%: 57-59% + 81-86% + 90-92%
            (57, 59, 10), (81, 86, 10), (90, 92, 10),
            # Lv2 HR 67.7%: 66-71% + 75-77%
            (66, 71, 9), (75, 77, 9),
            # Lv3 HR 64.1%: 60-62% + 72-74% + 87-89%
            (60, 62, 8), (72, 74, 8), (87, 89, 8),
            # Lv4 HR 63.0%: 51-53%
            (51, 53, 7),
            # Lv5 HR 62.5%: 63-65%
            (63, 65, 6),
            # Lv6 HR 62.5%: 45-47%
            (45, 47, 5),
            # Lv7 HR 62.3%: 48-50%
            (48, 50, 4),
            # Lv8 HR 62.1%: 39-41%
            (39, 41, 3),
            # Lv9 HR 58.5%: 54-56%
            (54, 56, 2),
            # Lv10 HR 56.6%: 42-44% + 78-80%
            (42, 44, 1), (78, 80, 1),
        ]
        STAKE_GOL = [
            # Lv1 HR 89.5%: 42-44% + 48-50% + 84-86%
            (42, 44, 10), (48, 50, 10), (84, 86, 10),
            # Lv2 HR 80.0%: 51-53%
            (51, 53, 9),
            # Lv3 HR 80.0%: 78-80%
            (78, 80, 8),
            # Lv4 HR 69.8%: 69-71%
            (69, 71, 7),
            # Lv5 HR 66.2%: 72-74%
            (72, 74, 6),
            # Lv6 HR 62.7%: 39-41% + 45-47% + 75-77%
            (39, 41, 5), (45, 47, 5), (75, 77, 5),
            # Lv7 HR 60.7%: 63-65% + 81-83%
            (63, 65, 4), (81, 83, 4),
            # Lv8 HR 59.4%: 66-68%
            (66, 68, 3),
            # Lv9 HR 55.7%: 57-62%
            (57, 62, 2),
            # Lv10 HR 38.5%: 54-56%
            (54, 56, 1),
        ]

        def _get_empirical_stake(conf, tipo):
            table = STAKE_SEGNI if tipo in ('SEGNO', 'DOPPIA_CHANCE') else STAKE_GOL
            conf_int = int(round(conf))
            for c_min, c_max, stake in table:
                if c_min <= conf_int <= c_max:
                    return stake
            return 3  # fallback se fuori da tutte le fasce

        for p in unified_pronostici:
            if p.get('pronostico') == 'NO BET' or p.get('tipo') == 'RISULTATO_ESATTO':
                continue
            old_stake = p.get('stake', 1)
            new_stake = _get_empirical_stake(p.get('confidence', 50), p.get('tipo', ''))
            p['stake'] = new_stake
            if old_stake != new_stake:
                pass  # silenzioso — troppi log altrimenti

        # --- CONVERSIONI POST-STAKE (ricalcolano stake sul nuovo pronostico) ---
        # ⚠️ ORDINE IMPORTANTE: le conversioni devono girare PRIMA dei filtri quota,
        # perché cambiano il pronostico e la quota (es. MG 2-3 @1.88 → U2.5 @1.55).
        # Se il filtro fascia 1.80-1.89 girasse prima, cancellerebbe tips convertibili.
        unified_pronostici = _apply_goal_quota_conversion(unified_pronostici, match_odds)
        unified_pronostici = _apply_gol_low_stake_to_nogoal(unified_pronostici, match_odds)
        unified_pronostici = _apply_gol_stake3_filter(unified_pronostici, match_odds)
        unified_pronostici = _apply_mg23_stake4_to_under25(unified_pronostici, match_odds)  # PRIMA del filtro quota
        unified_pronostici = _apply_gol_stake4_quota_filter(unified_pronostici)             # DOPO la conversione MG 2-3
        unified_pronostici = _apply_over15_stake5_low_to_under25(unified_pronostici, match_odds)
        unified_pronostici = _apply_gol_stake5_q160_to_nogoal(unified_pronostici, match_odds)
        unified_pronostici = _apply_gol_stake7_filter(unified_pronostici, match_odds)
        unified_pronostici = _apply_o25_stake6_to_goal(unified_pronostici, match_odds)
        unified_pronostici = _apply_segno_low_stake_filter(unified_pronostici)
        unified_pronostici = _apply_dc_stake1_to_under25(unified_pronostici, match_odds)
        unified_pronostici = _apply_dc_stake4_to_nogoal(unified_pronostici, match_odds)
        unified_pronostici = _apply_segno_stake6_conversion(unified_pronostici, match_odds)
        unified_pronostici = _apply_segno_stake9_conversions(unified_pronostici, match_odds)
        unified_pronostici = _apply_se2_stake8_filter(unified_pronostici)
        unified_pronostici = _apply_segno_stake7_cap(unified_pronostici)
        unified_pronostici = _apply_gol_stake8_cap(unified_pronostici)

        # --- DEDUP GOL CORRELATI post-conversioni: le conversioni possono creare Over 1.5 + Over 2.5 ---
        unified_pronostici = _dedup_gol_correlati(unified_pronostici)

        # --- CONFLITTO Over 2.5 (C) vs Under 2.5 (A): Over 2.5 C vince (73.3% HR vs 65.9%) ---
        o25_c_idx = None
        u25_a_idx = None
        for i, p in enumerate(unified_pronostici):
            if p.get('pronostico') == 'Over 2.5' and 'C' in (p.get('source') or ''):
                o25_c_idx = i
            elif p.get('pronostico') == 'Under 2.5' and (p.get('source') or '') == 'A':
                u25_a_idx = i
        if o25_c_idx is not None and u25_a_idx is not None:
            print(f"    ⚔️ CONFLITTO O25(C) vs U25(A): Over 2.5 vince (73.3% vs 65.9%) → rimosso Under 2.5")
            unified_pronostici = [p for i, p in enumerate(unified_pronostici) if i != u25_a_idx]

        # --- DEDUP post-conversioni: le conversioni possono creare duplicati su qualsiasi mercato ---
        seen_pron2 = {}
        dedup_remove2 = set()
        for i, p in enumerate(unified_pronostici):
            pron = p.get('pronostico', '')
            if pron and pron != 'NO BET':
                if pron in seen_pron2:
                    j = seen_pron2[pron]
                    old = unified_pronostici[j]
                    old_elite = old.get('elite', False)
                    new_elite = p.get('elite', False)
                    if new_elite and not old_elite:
                        new_wins = True
                    elif old_elite and not new_elite:
                        new_wins = False
                    else:
                        old_prio = _get_source_priority(old.get('source', ''))
                        new_prio = _get_source_priority(p.get('source', ''))
                        new_wins = new_prio < old_prio
                    if new_wins:
                        dedup_remove2.add(j)
                        seen_pron2[pron] = i
                    else:
                        dedup_remove2.add(i)
                    winner = unified_pronostici[seen_pron2[pron]]
                    loser_src = p.get('source') if not new_wins else old.get('source')
                    print(f"    🔀 DEDUP POST-CONV: {pron} — tenuto {winner.get('source')}{'👑' if winner.get('elite') else ''}, rimosso {loser_src}")
                else:
                    seen_pron2[pron] = i
        if dedup_remove2:
            unified_pronostici = [p for i, p in enumerate(unified_pronostici) if i not in dedup_remove2]

        # --- FATTORE QUOTA FINALE: aggiusta lo stake in base alla fascia di quota ---
        for p in unified_pronostici:
            if p.get('pronostico') == 'NO BET' or p.get('tipo') == 'RISULTATO_ESATTO':
                continue
            quota = p.get('quota') or 0
            old_stake = p.get('stake', 1)
            new_stake = _apply_fattore_quota(old_stake, quota)
            if new_stake != old_stake:
                p['stake'] = new_stake

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

        # Giornata (round number) da h2h_by_round
        _rkey = (unified_doc.get('league', ''), unified_doc.get('home', ''), unified_doc.get('away', ''))
        _giornata = _round_map.get(_rkey)
        if _giornata:
            unified_doc['giornata'] = _giornata

        # Imposta decision in base ai pronostici generati
        has_real_tip = any(p.get('pronostico') and p['pronostico'] != 'NO BET' for p in unified_doc.get('pronostici', []))
        unified_doc['decision'] = 'BET' if has_real_tip else 'NO_BET'

        unified_docs.append(unified_doc)

    if not unified_docs:
        return 0

    # 4. Scrivi in daily_predictions_unified
    coll = db['daily_predictions_unified']

    if not dry_run:
        # Chiavi delle partite generate in questa run (per rilevare quelle non rigenerate)
        generated_keys = set()
        for doc in unified_docs:
            generated_keys.add(f"{doc['home']}||{doc['away']}")

        today_str = datetime.now().strftime('%Y-%m-%d')
        is_anticipata = (today_str < date_str)

        if preserve_analysis:
            # Pre-match update: aggiorna solo i campi pronostici, preserva analysis_*
            for doc in unified_docs:
                find_filter = {'date': date_str, 'home': doc['home'], 'away': doc['away']}
                update_fields = {k: v for k, v in doc.items() if k not in ('_id', 'created_at')}
                update_fields['updated_at'] = datetime.now(timezone.utc)
                coll.update_one(find_filter, {
                    '$set': update_fields,
                    '$setOnInsert': {'created_at': datetime.now(timezone.utc), 'origin_date': today_str, 'anticipata': is_anticipata}
                }, upsert=True)
        else:
            # Pipeline notturna: update_one + upsert (le partite non spariscono mai)
            for doc in unified_docs:
                find_filter = {'date': date_str, 'home': doc['home'], 'away': doc['away']}
                update_fields = {k: v for k, v in doc.items() if k not in ('_id', 'created_at')}
                update_fields['updated_at'] = datetime.now(timezone.utc)
                coll.update_one(find_filter, {
                    '$set': update_fields,
                    '$setOnInsert': {'created_at': datetime.now(timezone.utc), 'origin_date': today_str, 'anticipata': is_anticipata}
                }, upsert=True)

            # Partite già in DB per questa data ma non rigenerate → diventano NO BET
            if not match_time_filter:
                existing_docs = list(coll.find({'date': date_str}, {'home': 1, 'away': 1, 'decision': 1}))
                nobet_count = 0
                for edoc in existing_docs:
                    key = f"{edoc['home']}||{edoc['away']}"
                    if key not in generated_keys and edoc.get('decision') != 'NO_BET':
                        coll.update_one(
                            {'_id': edoc['_id']},
                            {'$set': {
                                'decision': 'NO_BET',
                                'pronostici': [{'tipo': 'SEGNO', 'pronostico': 'NO BET', 'confidence': 0}],
                            }}
                        )
                        nobet_count += 1
                if nobet_count:
                    print(f"    ⚠️ {nobet_count} partite non rigenerate → NO BET")

                # Controlla se qualche partita ha cambiato data in h2h_by_round
                # Se la data reale è diversa, sposta il documento alla data giusta
                moved_count = 0
                for edoc in existing_docs:
                    _home = edoc.get('home', '')
                    _away = edoc.get('away', '')

                    # 1. Controlla nella mappa già costruita
                    _real = _real_date_map.get((_home, _away))

                    # 2. Se non trovata, cerca direttamente in h2h_by_round
                    if not _real:
                        try:
                            _h2h_match = db['h2h_by_round'].find_one(
                                {'matches': {'$elemMatch': {'home': _home, 'away': _away}}},
                                {'matches.$': 1}
                            )
                            if _h2h_match and _h2h_match.get('matches'):
                                _h2h_date = _h2h_match['matches'][0].get('date_obj')
                                if _h2h_date:
                                    _real = _h2h_date.strftime('%Y-%m-%d')
                        except Exception:
                            pass

                    # 3. Se la data reale è diversa, aggiorna il campo date
                    if _real and _real != date_str:
                        # Verifica che non esista già un doc per la stessa partita nella data nuova
                        _existing_new = coll.find_one({'date': _real, 'home': _home, 'away': _away})
                        if not _existing_new:
                            coll.update_one(
                                {'_id': edoc['_id']},
                                {'$set': {'date': _real}}
                            )
                            moved_count += 1
                            print(f"    📅 {_home} - {_away}: data corretta {date_str} → {_real}")
                        else:
                            # Esiste già nella data nuova, elimina il duplicato vecchio
                            coll.delete_one({'_id': edoc['_id']})
                            moved_count += 1
                            print(f"    📅 {_home} - {_away}: rimosso duplicato da {date_str} (esiste già in {_real})")

                        # Aggiorna anche prediction_versions per la stessa partita
                        _old_mk = f"{date_str}_{_home.strip().lower().replace(' ', '_')}_{_away.strip().lower().replace(' ', '_')}"
                        _new_mk = f"{_real}_{_home.strip().lower().replace(' ', '_')}_{_away.strip().lower().replace(' ', '_')}"
                        _pv_result = db['prediction_versions'].update_many(
                            {'date': date_str, 'home': _home, 'away': _away},
                            {'$set': {'date': _real, 'match_key': _new_mk}}
                        )
                        if _pv_result.modified_count > 0:
                            print(f"    📅 {_home} - {_away}: aggiornate {_pv_result.modified_count} versioni in prediction_versions")

                if moved_count:
                    print(f"    📅 {moved_count} partite con data corretta")

        # Salva richieste quote RE per lo scraper SNAI
        re_requests = []
        for doc in unified_docs:
            for p in doc.get('pronostici', []):
                if p.get('tipo') == 'RISULTATO_ESATTO':
                    re_requests.append({
                        'home': doc['home'],
                        'away': doc['away'],
                        'league': doc.get('league', ''),
                        'score': p['pronostico'],
                        'date': date_str,
                        'status': 'pending',
                        'created_at': datetime.now(timezone.utc),
                    })
        if re_requests:
            db['re_quota_requests'].delete_many({'date': date_str})
            db['re_quota_requests'].insert_many(re_requests)
            print(f"    RE quota requests: {len(re_requests)} salvate")

    if dry_run:
        return unified_docs
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
        all_dry_docs = []  # Per salvare i docs in dry-run
        for dt in dates:
            result = orchestrate_date(dt, dry_run=args.dry_run)
            count = len(result) if isinstance(result, list) else result
            total += count
            status = '[DRY]' if args.dry_run else '[OK]'
            print(f"  {dt}: {count} partite {status}")
            if args.dry_run and isinstance(result, list):
                all_dry_docs.extend(result)

        print(f"\n  Totale: {total} partite su {len(dates)} giorni")

        # Salva i pronostici dry-run su file JSON per confronto P/L
        if args.dry_run and all_dry_docs:
            out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'log')
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, 'backfill_dry_run.json')
            # Serializza — converte datetime/ObjectId in stringa
            def _serialize(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                if hasattr(obj, '__str__') and type(obj).__name__ == 'ObjectId':
                    return str(obj)
                raise TypeError(f"Non serializzabile: {type(obj)}")
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(all_dry_docs, f, default=_serialize, ensure_ascii=False, indent=1)
            print(f"\n  💾 Pronostici dry-run salvati in: {out_path}")
            print(f"     ({len(all_dry_docs)} documenti)")
            print(f"     Per confronto P/L: python backfill_pl_compare.py")

    else:
        if args.date:
            # Data specifica passata da CLI
            date_str = args.date
            print(f"\n  MoE Orchestratore — Data: {date_str}")
            if args.dry_run:
                print("  [DRY RUN — nessuna scrittura]")
            result = orchestrate_date(date_str, dry_run=args.dry_run)
            count = len(result) if isinstance(result, list) else result
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
                result = orchestrate_date(date_str, dry_run=args.dry_run)
                count = len(result) if isinstance(result, list) else result
                total += count
                status = '[DRY]' if args.dry_run else '[OK]'
                print(f"  {date_str}: {count} partite {status}")
            print(f"\n  Totale: {total} partite su 7 giorni")

    print()


if __name__ == '__main__':
    main()
