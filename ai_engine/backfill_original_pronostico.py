"""
BACKFILL original_pronostico + original_quota
=============================================
Ricostruisce i campi original_pronostico e original_quota
per tutti i pronostici storici in daily_predictions_unified
che hanno un routing_rule ma non hanno ancora original_pronostico.

Strategie di recovery:
1. Base (single, consensus, combo, diamond, cap) → original = current
2. Deterministico dalla regola (gol_s2_to_ng=Goal, o25_s6_to_goal=Over2.5, etc.)
3. Lookup in daily_predictions_engine_c per scrematura, mc_filter, dc conversions
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from config import db
from collections import Counter

# =====================================================
# REGOLE BASE — original = current (nessuna conversione)
# =====================================================
BASE_RULES = {
    'single', 'consensus_both', 'priority_chain', 'union',
    'multigol_v6', 'combo_96_dc_flip', 'u25_high_segno_add',
}
BASE_PREFIXES = ('home_win_combo_', 'x_draw_combo_', 'diamond_pattern_')

# =====================================================
# REGOLE CAP — original = current (solo stake cambiato)
# =====================================================
CAP_RULES = {'se2_s9_f180_cap6', 'segno_s7_weak_q_cap5', 'gol_s8_q150_cap6'}

# =====================================================
# REGOLE DETERMINISTICHE — original noto dalla regola
# =====================================================
DETERMINISTIC = {
    'gol_s2_to_ng': 'Goal',           # stake 2 converte solo Goal
    'o25_s6_to_goal': 'Over 2.5',     # Over 2.5 → Goal
    'as_o25_to_dc': 'Over 2.5',       # Recovery O2.5 → DC
    'as_o25_to_segno1': 'Over 2.5',   # Recovery O2.5 → SEGNO 1
    'as_o25_to_under25': 'Over 2.5',  # Recovery O2.5 → Under 2.5
    'x2_s2_filter': 'X2',             # X2 stake 2 → NO BET
    'se2_s8_q190_filter': '2',        # SEGNO 2 stake 8 → NO BET
    'gol_s4_filter': 'Over 2.5',      # GOL stake 4 solo Over 2.5
    'goal_to_u25': 'Goal',            # Goal → Under 2.5
    'goal_to_o15': 'Goal',            # Goal → Over 1.5
    'mg23_s4_to_u25': 'MG 2-3',      # MG 2-3 → Under 2.5
    'o15_s5_low_to_u25': 'Over 1.5',  # Over 1.5 → Under 2.5
    'dcx2_s9_f180_to_ng': 'X2',      # DC X2 stake 9 → NoGoal
}


def _get_engine_c_segno(date, home, away):
    """Cerca il SEGNO originale nel sistema C per questa partita."""
    doc = db.daily_predictions_engine_c.find_one(
        {'date': date, 'home': home, 'away': away},
        {'pronostici': 1}
    )
    if not doc:
        return None, None
    for p in doc.get('pronostici', []):
        if p.get('tipo') == 'SEGNO':
            return p.get('pronostico'), p.get('quota', 0)
    return None, None


def _get_engine_c_dc(date, home, away):
    """Cerca la DC originale nel sistema C."""
    doc = db.daily_predictions_engine_c.find_one(
        {'date': date, 'home': home, 'away': away},
        {'pronostici': 1}
    )
    if not doc:
        return None, None
    for p in doc.get('pronostici', []):
        if p.get('tipo') == 'DOPPIA_CHANCE':
            return p.get('pronostico'), p.get('quota', 0)
    return None, None


def _get_engine_c_gol(date, home, away):
    """Cerca il GOL originale nel sistema C."""
    doc = db.daily_predictions_engine_c.find_one(
        {'date': date, 'home': home, 'away': away},
        {'pronostici': 1}
    )
    if not doc:
        return None, None
    for p in doc.get('pronostici', []):
        if p.get('tipo') == 'GOL':
            return p.get('pronostico'), p.get('quota', 0)
    return None, None


def _get_sistema_a_prediction(date, home, away, tipo):
    """Cerca il pronostico originale nel sistema A."""
    doc = db.daily_predictions.find_one(
        {'date': date, 'home': home, 'away': away},
        {'pronostici': 1}
    )
    if not doc:
        return None, None
    for p in doc.get('pronostici', []):
        if p.get('tipo') == tipo:
            return p.get('pronostico'), p.get('quota', 0)
    return None, None


def recover_original(p, date, home, away):
    """
    Tenta di ricostruire original_pronostico e original_quota.
    Ritorna (pronostico, quota) o (None, None) se non recuperabile.
    """
    rule = p.get('routing_rule', '')
    source = p.get('source', '')
    current_pr = p.get('pronostico', '')
    current_q = p.get('quota', 0)

    # 1. Base/Cap: original = current
    if rule in BASE_RULES or rule in CAP_RULES:
        return current_pr, current_q
    if any(rule.startswith(prefix) for prefix in BASE_PREFIXES):
        return current_pr, current_q

    # 2. Deterministico
    if rule in DETERMINISTIC:
        orig_pr = DETERMINISTIC[rule]
        # Per quota: lookup engine_c
        if rule.startswith('as_o25_'):
            # Recovery: la quota originale era dell'Over 2.5 in A+S
            _, oq = _get_engine_c_gol(date, home, away)
            return orig_pr, oq or 0
        elif rule in ('gol_s2_to_ng', 'goal_to_u25', 'goal_to_o15'):
            _, oq = _get_engine_c_gol(date, home, away)
            return orig_pr, oq or 0
        elif rule == 'o25_s6_to_goal':
            return orig_pr, 0  # quota O2.5 persa, non critica
        elif rule == 'mg23_s4_to_u25':
            return orig_pr, 0
        elif rule == 'o15_s5_low_to_u25':
            return orig_pr, 0
        else:
            return orig_pr, 0

    # 3. Scrematura SEGNO
    if rule in ('scrematura_segno', 'scrematura_segno_x'):
        # Se il risultato è una DC (1X/X2), l'originale è il SEGNO corrispondente
        if current_pr == '1X':
            return '1', 0
        elif current_pr == 'X2':
            return '2', 0
        elif current_pr == 'X':
            # Scrematura → X: lookup engine_c per il SEGNO originale
            orig_pr, orig_q = _get_engine_c_segno(date, home, away)
            return orig_pr or '?', orig_q or 0
        else:
            # Convertito in GOL (Over 1.5, Over 2.5, Goal) → lookup engine_c SEGNO
            orig_pr, orig_q = _get_engine_c_segno(date, home, away)
            return orig_pr or '?', orig_q or 0

    # Scrematura DC → Over/Under
    if rule in ('screm_dc_to_over15', 'screm_dc_to_under25', 'screm_o15_to_dc'):
        # Multi-step: SEGNO → DC → Over/Under. L'originale è il SEGNO
        orig_pr, orig_q = _get_engine_c_segno(date, home, away)
        return orig_pr or '?', orig_q or 0

    # 4. Filtro MC
    if rule == 'mc_filter_convert':
        # Era un SEGNO, convertito in Over 1.5
        if '_hw_' in source or 'home_win' in source:
            return '1', 0
        elif '_xdraw_' in source or 'x_draw' in source:
            return 'X', 0
        else:
            orig_pr, orig_q = _get_engine_c_segno(date, home, away)
            return orig_pr or '?', orig_q or 0

    # 5. Conversioni DC
    if rule == 'dc_s1_to_u25':
        # Era una DC. Lookup engine_c per capire quale
        orig_pr, orig_q = _get_engine_c_dc(date, home, away)
        if not orig_pr:
            orig_pr, _ = _get_engine_c_segno(date, home, away)
            if orig_pr == '1':
                return '1X', 0
            elif orig_pr == '2':
                return 'X2', 0
        return orig_pr or '?', orig_q or 0

    if rule == 'dc_s4_to_ng':
        if 'combo96' in source or 'dc_flip' in source:
            return 'X2', 0
        orig_pr, orig_q = _get_engine_c_segno(date, home, away)
        if orig_pr == '1':
            return '1X', 0
        elif orig_pr == '2':
            return 'X2', 0
        return '?', 0

    if rule == 'dc_s6_to_goal':
        if 'combo96' in source or 'dc_flip' in source:
            return 'X2', 0
        if 'as_dc_rec' in source:
            return 'X2', 0
        # Lookup
        orig_pr, orig_q = _get_engine_c_dc(date, home, away)
        if not orig_pr:
            s_pr, _ = _get_engine_c_segno(date, home, away)
            if s_pr == '1':
                return '1X', 0
            elif s_pr == '2':
                return 'X2', 0
        return orig_pr or '?', orig_q or 0

    # 6. GOL conversioni (stake 1 è complesso, stake 5 idem)
    if rule == 'gol_s1_to_ng':
        # Stake 1: qualsiasi GOL → NG. Cerco in engine_c
        orig_pr, orig_q = _get_engine_c_gol(date, home, away)
        if orig_pr:
            return orig_pr, orig_q
        # Fallback: potrebbe venire da scrematura
        if '_screm' in source:
            return 'Over 2.5', 0  # scrematura spesso produce O2.5
        return 'Goal', 0  # best guess

    if rule == 'gol_s5_q160_to_ng':
        orig_pr, orig_q = _get_engine_c_gol(date, home, away)
        return orig_pr or 'Goal', orig_q or 0

    if rule == 'gol_s4_q180_filter':
        orig_pr, orig_q = _get_engine_c_gol(date, home, away)
        return orig_pr or 'Goal', orig_q or 0

    if rule == 'gol_s7_filter':
        # Potrebbe essere Under 2.5, MG 2-3, o quota 1.90-1.99
        orig_pr, orig_q = _get_engine_c_gol(date, home, away)
        return orig_pr or 'Goal', orig_q or 0

    # 7. Filtri SEGNO
    if rule == 'segno_s1_low_q_filter':
        orig_pr, orig_q = _get_engine_c_segno(date, home, away)
        return orig_pr or '?', orig_q or 0

    if rule == 'segno_s2_toxic_q_filter':
        if '_hw' in source or 'home_win' in source:
            return '1', 0
        orig_pr, orig_q = _get_engine_c_segno(date, home, away)
        return orig_pr or '?', orig_q or 0

    # 8. Conversioni SEGNO
    if rule == 'segno_s6_to_o25':
        orig_pr, orig_q = _get_engine_c_segno(date, home, away)
        return orig_pr or '?', orig_q or 0

    if rule == 'segno_s9_f150_to_goal':
        orig_pr, orig_q = _get_engine_c_segno(date, home, away)
        return orig_pr or '?', orig_q or 0

    # 9. GG conf DC downgrade
    if rule == 'gg_conf_dc_downgrade':
        orig_pr, orig_q = _get_engine_c_segno(date, home, away)
        return orig_pr or '?', orig_q or 0

    # Non riconosciuto
    return None, None


def main():
    print("=" * 60)
    print("BACKFILL original_pronostico + original_quota")
    print("=" * 60)

    # Trova tutti i pronostici con routing_rule ma senza original_pronostico
    docs = list(db.daily_predictions_unified.find(
        {'pronostici.routing_rule': {'$exists': True}},
        {'_id': 1, 'date': 1, 'home': 1, 'away': 1, 'pronostici': 1}
    ))

    print(f"Documenti con routing_rule: {len(docs)}")

    stats = Counter()
    updated = 0
    errors = []

    for doc in docs:
        date = doc['date']
        home = doc['home']
        away = doc['away']
        pronostici = doc.get('pronostici', [])
        changed = False

        for p in pronostici:
            rule = p.get('routing_rule')
            if not rule:
                continue
            if p.get('original_pronostico'):
                stats['gia_presente'] += 1
                continue

            orig_pr, orig_q = recover_original(p, date, home, away)
            if orig_pr is not None:
                p['original_pronostico'] = orig_pr
                p['original_quota'] = orig_q or 0
                changed = True
                stats[f'ok_{rule}'] += 1
            else:
                stats[f'skip_{rule}'] += 1
                errors.append(f"  {date} {home} vs {away}: {rule} — non recuperabile")

        if changed:
            db.daily_predictions_unified.update_one(
                {'_id': doc['_id']},
                {'$set': {'pronostici': pronostici}}
            )
            updated += 1

    print(f"\nDocumenti aggiornati: {updated}")
    print(f"\nStatistiche per regola:")
    for key, count in sorted(stats.items()):
        print(f"  {key}: {count}")

    if errors:
        print(f"\nNon recuperabili ({len(errors)}):")
        for e in errors[:20]:
            print(e)

    total_ok = sum(v for k, v in stats.items() if k.startswith('ok_'))
    total_skip = sum(v for k, v in stats.items() if k.startswith('skip_'))
    total_present = stats.get('gia_presente', 0)
    print(f"\nTotale: {total_ok} recuperati, {total_skip} non recuperabili, {total_present} già presenti")


if __name__ == '__main__':
    main()
