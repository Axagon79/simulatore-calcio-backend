"""
POST-MATCH COHERENCE ANALYZER — Fase 1: Vincoli Numerici
=========================================================
Confronta le stats post-partita reali (SofaScore, 39 campi) con i pronostici emessi.
Assegna uno score di coerenza 0-100 e un verdetto per ogni pronostico.

NON usa AI — solo calcoli numerici basati su vincoli validati.
Fasi successive: 2 = Mistral, 3 = Self-check loop.

Uso:
    python post_match_coherence_analyzer.py                          # ieri
    python post_match_coherence_analyzer.py --date 2026-03-27        # data specifica
    python post_match_coherence_analyzer.py --days 3                 # ultimi 3 giorni
    python post_match_coherence_analyzer.py --from 2026-03-01 --to 2026-03-27
    python post_match_coherence_analyzer.py --force                  # ricalcola anche gia analizzati
"""

import os, sys, re, argparse
from datetime import datetime, timedelta, timezone
from collections import Counter

# --- FIX PERCORSI ---
current_path = os.path.dirname(os.path.abspath(__file__))
while not os.path.exists(os.path.join(current_path, 'config.py')):
    parent = os.path.dirname(current_path)
    if parent == current_path:
        raise FileNotFoundError("Impossibile trovare config.py!")
    current_path = parent
sys.path.append(current_path)

from config import db

# ═══════════════════════════════════════════════════════════
# CONFIGURAZIONE — 39 campi, 4 tier, pesi sommano a 1.000
# ═══════════════════════════════════════════════════════════

WEIGHTS = {
    # --- TIER A — Peso alto (6 campi, ~55%) ---
    "shots_on_target": 0.13,
    "big_chances": 0.09,
    "touches_in_opp_box": 0.09,
    "hit_woodwork": 0.07,
    "big_saves": 0.07,
    "shots_inside_box": 0.07,
    # --- TIER B — Peso medio (8 campi, ~22%) ---
    "total_shots": 0.04,
    "blocked_shots": 0.035,
    "xg": 0.03,               # modello, non realta — contesto secondario
    "big_chances_missed": 0.03,
    "crosses": 0.03,           # formato X/Y (Z%)
    "final_third_entries": 0.03,
    "corners": 0.03,
    "fouls_in_final_third": 0.025,
    # --- TIER C — Peso basso (23 campi, ~22%) ---
    "through_balls": 0.018,    # passaggi filtranti riusciti
    "shots_outside_box": 0.012,
    "possession": 0.012,
    "shots_off_target": 0.01,
    "saves": 0.01,
    "clearances": 0.01,
    "interceptions": 0.01,
    "tackles": 0.01,
    "tackles_won": 0.01,       # percentuale (es. 71.0 = 71%)
    "accurate_passes": 0.01,
    "long_balls": 0.01,        # formato X/Y (Z%)
    "ground_duels": 0.01,      # formato X/Y (Z%)
    "dribbles": 0.01,          # formato X/Y (Z%)
    "recoveries": 0.01,
    "fouls": 0.01,
    "yellow_cards": 0.01,
    "passes": 0.008,
    "aerial_duels": 0.008,     # formato X/Y (Z%)
    "duels_total": 0.008,      # percentuale (es. 49.0 = 49%)
    "offsides": 0.008,
    "goal_kicks": 0.008,
    "throw_ins": 0.008,
    # --- TIER D — Peso minimo (2 campi, ~1%) ---
    "punches": 0.006,
    "high_claims": 0.004,
}

# Campi in formato "X/Y (Z%)" — vanno parsati
RATIO_FIELDS = {"crosses", "long_balls", "ground_duels", "aerial_duels", "dribbles"}

# Campi che sono gia percentuali (es. 71.0 = 71%)
PCT_FIELDS = {"tackles_won", "duels_total", "possession"}

# Soglie di riferimento per Over 2.5 (somma delle due squadre)
OVER_REFS = {
    # TIER A
    "shots_on_target": 10, "xg": 3.0, "big_chances": 6, "touches_in_opp_box": 40,
    "hit_woodwork": 2, "big_saves": 4, "shots_inside_box": 16,
    # TIER B
    "total_shots": 24, "blocked_shots": 8, "big_chances_missed": 4,
    "crosses": 50, "final_third_entries": 80, "corners": 10, "fouls_in_final_third": 6,
    # TIER C
    "through_balls": 4, "shots_outside_box": 10, "possession": 100,
    "shots_off_target": 14, "saves": 8, "clearances": 30, "interceptions": 20,
    "tackles": 30, "tackles_won": 100, "accurate_passes": 600, "long_balls": 50,
    "ground_duels": 50, "dribbles": 30, "recoveries": 80, "fouls": 24,
    "yellow_cards": 4, "passes": 800, "aerial_duels": 30, "duels_total": 100,
    "offsides": 4, "goal_kicks": 12, "throw_ins": 40,
    # TIER D
    "punches": 2, "high_claims": 4,
}

THRESHOLD_MULT = {1.5: 0.6, 2.5: 1.0, 3.5: 1.4}

# ═══════════════════════════════════════════════════════════
# PESI PER MERCATO — set diversi per tipo di pronostico
# ═══════════════════════════════════════════════════════════

# OVER/UNDER e MULTIGOL — solo occasioni da gol concrete (14 campi)
# Gerarchia: shots_on_target > big_chances > touches_in_opp_box > resto
WEIGHTS_VOLUME = {
    "shots_on_target": 0.18,
    "big_chances": 0.14,
    "touches_in_opp_box": 0.12,
    "shots_inside_box": 0.10,
    "hit_woodwork": 0.08,
    "big_saves": 0.07,
    "total_shots": 0.06,
    "blocked_shots": 0.05,
    "big_chances_missed": 0.04,
    "xg": 0.04,
    "through_balls": 0.04,
    "shots_outside_box": 0.03,
    "shots_off_target": 0.03,
    "saves": 0.02,            # ridondante con SoT, peso minimo
}
# Somma: 1.000

# GG/NG — pericolosita per squadra (stessi campi di VOLUME)
# Usato nel threat_score per-squadra
WEIGHTS_THREAT = WEIGHTS_VOLUME

# SEGNO e DC — tutti i 38 campi (WEIGHTS principale, invariato)

# Campi Tier A per boost dominanza
TIER_A_KEYS = ["shots_on_target", "big_chances", "touches_in_opp_box",
               "hit_woodwork", "big_saves", "shots_inside_box"]

VERDICTS = [
    (85, "COERENTE"),
    (65, "RAGIONEVOLE"),
    (40, "INCERTO"),
    (20, "FORZATO"),
    (0, "ERRATO"),
]


def get_verdict(score):
    for threshold, label in VERDICTS:
        if score >= threshold:
            return label
    return "ERRATO"


# ═══════════════════════════════════════════════════════════
# HELPERS — Estrazione e parsing stats
# ═══════════════════════════════════════════════════════════

def safe_float(val, default=0.0):
    """Converte un valore a float in modo sicuro."""
    if val is None:
        return default
    try:
        if isinstance(val, str):
            val = val.replace('%', '').replace(',', '.').strip()
        return float(val)
    except (ValueError, TypeError):
        return default


def parse_ratio_field(val):
    """
    Parsa campi formato "X/Y (Z%)" -> ritorna percentuale come 0.0-1.0.
    Es. "38/85 (45%)" -> 0.45
    Se e' un numero secco, lo tratta come valore assoluto.
    Ritorna None se il campo e' None (dato non disponibile).
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    # Cerca pattern "X/Y (Z%)"
    m = re.match(r'(\d+)\s*/\s*(\d+)\s*\((\d+(?:\.\d+)?)%?\)', s)
    if m:
        return float(m.group(3)) / 100.0
    # Cerca pattern "X/Y" senza percentuale
    m2 = re.match(r'(\d+)\s*/\s*(\d+)', s)
    if m2:
        total = int(m2.group(2))
        if total > 0:
            return int(m2.group(1)) / total
        return 0.0
    # Numero secco
    try:
        return float(s.replace('%', '').replace(',', '.'))
    except (ValueError, TypeError):
        return None


def get_stat(stats_dict, key):
    """
    Estrae una statistica dal dict home_stats o away_stats.
    Per campi ratio (X/Y%), ritorna la percentuale 0-1.
    Per campi percentuali (possession, tackles_won, duels_total), normalizza /100.
    Ritorna None se il dato non e' disponibile (campo assente o None).
    """
    raw = stats_dict.get(key)
    if raw is None:
        return None

    if key in RATIO_FIELDS:
        return parse_ratio_field(raw)

    val = safe_float(raw, default=None)
    if val is None:
        return None

    # Campi percentuali: normalizza a 0-1 per coerenza
    if key in PCT_FIELDS:
        return val / 100.0

    return val


def get_stat_or_zero(stats_dict, key):
    """Come get_stat ma ritorna 0.0 invece di None."""
    val = get_stat(stats_dict, key)
    return val if val is not None else 0.0


def parse_score(risultato_str):
    """Parsa il risultato 'H-A' o 'H:A' e ritorna (home_goals, away_goals) o None."""
    if not risultato_str:
        return None
    parts = re.split(r'[:\-]', str(risultato_str).strip())
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def get_available_weights(home_stats, away_stats):
    """
    Calcola i pesi effettivi escludendo campi con None in ENTRAMBE le squadre.
    Ridistribuisce il peso dei campi mancanti proporzionalmente sugli altri.
    Ritorna dict {key: peso_effettivo}.
    """
    available = {}
    missing_weight = 0.0

    for key, weight in WEIGHTS.items():
        h_val = get_stat(home_stats, key)
        a_val = get_stat(away_stats, key)
        # Se almeno una squadra ha il dato, il campo e' utilizzabile
        if h_val is not None or a_val is not None:
            available[key] = weight
        else:
            missing_weight += weight

    if not available:
        return {}

    # Ridistribuisci peso mancante proporzionalmente
    if missing_weight > 0:
        total_available = sum(available.values())
        if total_available > 0:
            factor = 1.0 / total_available  # normalizza a 1.0
            available = {k: v * factor for k, v in available.items()}

    return available


# ═══════════════════════════════════════════════════════════
# MODIFICATORI TRASVERSALI
# ═══════════════════════════════════════════════════════════

def check_efficiency_anomaly(home_stats, away_stats, risultato):
    """
    Efficienza anomala: se gol/tiri_in_porta > 0.40 per una squadra,
    il risultato e' gonfiato da episodi.
    Ritorna lista di (squadra, penalty_points).
    """
    score_parsed = parse_score(risultato)
    if not score_parsed:
        return []

    h_goals, a_goals = score_parsed
    anomalies = []

    for label, goals, stats in [("home", h_goals, home_stats), ("away", a_goals, away_stats)]:
        if goals <= 0:
            continue
        sot = get_stat_or_zero(stats, 'shots_on_target')
        if sot <= 0:
            continue
        efficiency = goals / sot
        if efficiency > 0.40:
            penalty = min((efficiency - 0.40) * 30, 18)
            anomalies.append((label, round(penalty, 1)))

    return anomalies


def check_sterile_possession(home_stats, away_stats):
    """
    Possesso sterile: possesso > 60% ma tiri in porta <= 3.
    Ritorna lista di squadre con possesso sterile.
    """
    sterile = []
    for label, stats in [("home", home_stats), ("away", away_stats)]:
        poss = get_stat_or_zero(stats, 'possession') * 100  # get_stat normalizza a 0-1
        sot = get_stat_or_zero(stats, 'shots_on_target')
        if poss > 60 and sot <= 3:
            sterile.append(label)
    return sterile


def check_red_card(home_stats, away_stats):
    """
    Espulsione: se red_cards >= 1, la partita e' stata condizionata.
    Ritorna lista di squadre con espulsione.
    """
    reds = []
    for label, stats in [("home", home_stats), ("away", away_stats)]:
        rc = get_stat_or_zero(stats, 'red_cards')
        if rc >= 1:
            reds.append(label)
    return reds


def amplify_from_center(score):
    """
    Amplificazione non-lineare: allontana lo score dal centro (50).
    Score vicini a 50 vengono spinti verso gli estremi.
    Usa una curva sigmoide centrata su 50.
    """
    # Normalizza a [-1, 1] dove 0 = centro
    x = (score - 50) / 50  # -1 a +1
    # Curva di potenza che amplifica: sign(x) * |x|^0.7
    # Esponente < 1 = amplifica i valori piccoli (vicini al centro)
    if x >= 0:
        amplified = x ** 0.75
    else:
        amplified = -((-x) ** 0.75)
    return 50 + amplified * 50


def apply_tier_a_dominance(score, indicators, invert=False):
    """
    Se i campi Tier A puntano chiaramente in una direzione,
    il loro segnale forte non deve essere annacquato dal Tier C/D.
    Boost progressivo: piu forte e' il segnale, piu pesa.

    invert=True per Under/NG: indicatori bassi = pronostico coerente,
    quindi il boost va nella direzione opposta.
    """
    tier_a_vals = []
    for key in TIER_A_KEYS:
        val = indicators.get(key)
        if isinstance(val, (int, float)):
            tier_a_vals.append(val)

    if len(tier_a_vals) < 3:
        return score  # troppo pochi dati Tier A

    tier_a_avg = sum(tier_a_vals) / len(tier_a_vals)
    distanza = abs(tier_a_avg - 0.5)

    if distanza > 0.08:
        boost = (distanza ** 1.3) * 120

        if invert:
            # Under/NG: Tier A basso = volume basso = pronostico coerente = alza score
            if tier_a_avg < 0.5:
                score += boost
            else:
                score -= boost
        else:
            # Over/SEGNO/DC: Tier A alto = dominio = pronostico coerente = alza score
            if tier_a_avg > 0.5:
                score += boost
            else:
                score -= boost

    return score


def pronostico_to_side(pronostico):
    """Mappa pronostico a 'home' o 'away'."""
    if pronostico in ('1', '1X'):
        return 'home'
    if pronostico in ('2', 'X2'):
        return 'away'
    return None


# ═══════════════════════════════════════════════════════════
# SCORING PER MERCATO — usa tutti i 39 campi
# ═══════════════════════════════════════════════════════════

def _apply_modifiers_segno(raw_score, pronostico, home_stats, away_stats, risultato, modifiers_log):
    """Applica i 3 modificatori trasversali per SEGNO e DC."""
    winner_side = pronostico_to_side(pronostico)

    # 1. Efficienza anomala
    anomalies = check_efficiency_anomaly(home_stats, away_stats, risultato)
    for side, penalty in anomalies:
        if side == winner_side:
            raw_score -= penalty
            modifiers_log.append(f"efficiency_anomaly_{side}")
        else:
            raw_score += penalty * 0.5
            modifiers_log.append(f"efficiency_anomaly_{side}_opponent")

    # 2. Possesso sterile
    sterile = check_sterile_possession(home_stats, away_stats)
    for side in sterile:
        if side == winner_side:
            raw_score -= 5
        modifiers_log.append(f"sterile_possession_{side}")

    # 3. Espulsione
    reds = check_red_card(home_stats, away_stats)
    for side in reds:
        if side == winner_side:
            # La squadra pronosticata ha subito un rosso: sfortuna
            raw_score += 10
        else:
            # L'avversario ha subito un rosso: vantaggio numerico
            raw_score -= 10
        modifiers_log.append(f"red_card_{side}")

    return raw_score


def check_volume_balance(home_stats, away_stats):
    """
    Calcola quanto il volume offensivo e' bilanciato tra le due squadre.
    Ritorna balance medio 0-1 (0 = tutto da una parte, 1 = perfettamente bilanciato).
    """
    balance_keys = ["shots_on_target", "big_chances", "touches_in_opp_box", "xg"]
    balances = []
    for key in balance_keys:
        h = get_stat_or_zero(home_stats, key)
        a = get_stat_or_zero(away_stats, key)
        mx = max(h, a)
        if mx > 0:
            balances.append(min(h, a) / (mx + 0.001))
    if not balances:
        return 0.5
    return sum(balances) / len(balances)


# Intensita bilanciamento per threshold O/U
# Over 3.5 richiede entrambe le squadre, Over 1.5 basta una sola
BALANCE_INTENSITY = {1.5: 3, 2.5: 5, 3.5: 8}


def _apply_modifiers_volume(raw_score, direction, home_stats, away_stats, risultato, modifiers_log, threshold=2.5):
    """Applica modificatori trasversali per O/U e Multigol."""
    # 1. Efficienza anomala
    anomalies = check_efficiency_anomaly(home_stats, away_stats, risultato)
    for side, penalty in anomalies:
        if direction == "over":
            raw_score -= penalty
        else:
            raw_score += penalty * 0.5
        modifiers_log.append(f"efficiency_anomaly_{side}")

    # 2. Possesso sterile
    sterile = check_sterile_possession(home_stats, away_stats)
    for side in sterile:
        if direction == "over":
            raw_score -= 3
        else:
            raw_score += 2
        modifiers_log.append(f"sterile_possession_{side}")

    # 3. Espulsione (un rosso riduce il volume atteso)
    reds = check_red_card(home_stats, away_stats)
    for side in reds:
        if direction == "over":
            raw_score -= 5
        else:
            raw_score += 5
        modifiers_log.append(f"red_card_{side}")

    # 4. Bilanciamento volume — se tutto viene da una parte, Over e' meno probabile
    balance = check_volume_balance(home_stats, away_stats)
    intensity = BALANCE_INTENSITY.get(threshold, 5)
    if balance < 0.15:
        if direction == "over":
            raw_score -= intensity
        else:
            raw_score += intensity
        modifiers_log.append(f"unbalanced_volume_{intensity}pt")

    return raw_score


def score_segno(pronostico, home_stats, away_stats, risultato, modifiers_log):
    """SEGNO (1/X/2) — chi ha dominato il campo? Usa tutti i 39 campi."""
    eff_weights = get_available_weights(home_stats, away_stats)
    if not eff_weights:
        return 50, {}

    if pronostico in ('1', '2'):
        squadra = home_stats if pronostico == '1' else away_stats
        avversario = away_stats if pronostico == '1' else home_stats

        score = 0.0
        indicators = {}
        for key, weight in eff_weights.items():
            sq_val = get_stat(squadra, key)
            av_val = get_stat(avversario, key)
            # Se None, usa 0
            sq_val = sq_val if sq_val is not None else 0.0
            av_val = av_val if av_val is not None else 0.0
            total = sq_val + av_val + 0.001
            ratio = sq_val / total
            indicators[key] = round(ratio, 3)
            score += ratio * weight

        raw_score = score * 100

        # Bonus sfortuna
        bc_missed = get_stat_or_zero(squadra, 'big_chances_missed')
        woodwork = get_stat_or_zero(squadra, 'hit_woodwork')
        if bc_missed >= 2:
            raw_score += 5
        if woodwork >= 2:
            raw_score += 3

        raw_score = _apply_modifiers_segno(raw_score, pronostico, home_stats, away_stats, risultato, modifiers_log)
        return max(0, min(100, round(raw_score))), indicators

    elif pronostico == 'X':
        score = 0.0
        indicators = {}
        for key, weight in eff_weights.items():
            h_val = get_stat(home_stats, key)
            a_val = get_stat(away_stats, key)
            h_val = h_val if h_val is not None else 0.0
            a_val = a_val if a_val is not None else 0.0
            total = h_val + a_val + 0.001
            balance = 1 - abs(h_val - a_val) / total
            indicators[key] = round(balance, 3)
            score += balance * weight

        raw_score = score * 100

        # Modificatori per X
        anomalies = check_efficiency_anomaly(home_stats, away_stats, risultato)
        for side, penalty in anomalies:
            raw_score -= penalty * 0.5
            modifiers_log.append(f"efficiency_anomaly_{side}")

        sterile = check_sterile_possession(home_stats, away_stats)
        for side in sterile:
            raw_score -= 3
            modifiers_log.append(f"sterile_possession_{side}")

        reds = check_red_card(home_stats, away_stats)
        for side in reds:
            raw_score -= 8  # un rosso rende la X meno probabile
            modifiers_log.append(f"red_card_{side}")

        return max(0, min(100, round(raw_score))), indicators

    return 50, {}


def _get_volume_weights(home_stats, away_stats):
    """Calcola pesi effettivi per O/U e MG, escludendo campi None."""
    available = {}
    missing_weight = 0.0
    for key, weight in WEIGHTS_VOLUME.items():
        h_val = get_stat(home_stats, key)
        a_val = get_stat(away_stats, key)
        if h_val is not None or a_val is not None:
            available[key] = weight
        else:
            missing_weight += weight
    if not available:
        return {}
    if missing_weight > 0:
        total_available = sum(available.values())
        if total_available > 0:
            factor = 1.0 / total_available
            available = {k: v * factor for k, v in available.items()}
    return available


def score_over_under(pronostico, home_stats, away_stats, risultato, modifiers_log):
    """OVER/UNDER — volume offensivo combinato vs soglie. Solo campi offensivi (14)."""
    match = re.match(r'(Over|Under)\s+(\d+\.?\d*)', pronostico)
    if not match:
        return 50, {}

    direction = match.group(1)
    threshold = float(match.group(2))
    mult = THRESHOLD_MULT.get(threshold, 1.0)

    vol_weights = _get_volume_weights(home_stats, away_stats)
    if not vol_weights:
        return 50, {}

    score = 0.0
    indicators = {}
    for key, weight in vol_weights.items():
        h_val = get_stat(home_stats, key)
        a_val = get_stat(away_stats, key)
        h_val = h_val if h_val is not None else 0.0
        a_val = a_val if a_val is not None else 0.0
        combined = h_val + a_val
        ref = OVER_REFS.get(key, 1) * mult
        ratio = min(combined / (ref + 0.001), 1.5) / 1.5
        indicators[key] = round(ratio, 3)
        score += ratio * weight

    if direction == "Over":
        raw_score = score * 100
    else:
        raw_score = (1 - score) * 100

    raw_score = _apply_modifiers_volume(
        raw_score, "over" if direction == "Over" else "under",
        home_stats, away_stats, risultato, modifiers_log, threshold=threshold)

    return max(0, min(100, round(raw_score))), indicators


def score_gg_ng(pronostico, home_stats, away_stats, risultato, modifiers_log):
    """GG/NG — threat_score per ciascuna squadra. Usa tutti i 39 campi."""
    eff_weights = get_available_weights(home_stats, away_stats)
    if not eff_weights:
        return 50, {}

    threats = {}
    for label, stats, opp_stats in [("home", home_stats, away_stats),
                                     ("away", away_stats, home_stats)]:
        # Calcola threat con i campi piu rilevanti per "questa squadra ha creato?"
        xg = get_stat_or_zero(stats, 'xg')
        sot = get_stat_or_zero(stats, 'shots_on_target')
        bc = get_stat_or_zero(stats, 'big_chances')
        tbox = get_stat_or_zero(stats, 'touches_in_opp_box')
        sib = get_stat_or_zero(stats, 'shots_inside_box')
        hw = get_stat_or_zero(stats, 'hit_woodwork')
        opp_saves = get_stat_or_zero(opp_stats, 'saves')
        opp_big_saves = get_stat_or_zero(opp_stats, 'big_saves')
        fte = get_stat_or_zero(stats, 'final_third_entries')
        tb = get_stat_or_zero(stats, 'through_balls')

        threat = (
            min(xg / 2.0, 1.0) * 0.22 +
            min(sot / 4.0, 1.0) * 0.18 +
            min(bc / 2.0, 1.0) * 0.14 +
            min(tbox / 15.0, 1.0) * 0.10 +
            min(sib / 8.0, 1.0) * 0.08 +
            min(hw / 1.5, 1.0) * 0.06 +
            min(opp_saves / 4.0, 1.0) * 0.06 +
            min(opp_big_saves / 2.0, 1.0) * 0.06 +
            min(fte / 40.0, 1.0) * 0.05 +
            min(tb / 2.0, 1.0) * 0.05
        )
        threats[label] = min(threat, 1.0)

    min_threat = min(threats['home'], threats['away'])

    if pronostico == 'GG':
        raw_score = min_threat * 100
    else:
        raw_score = (1 - min_threat) * 100

    # Indicators: ratio minima tra squadre per campi offensivi
    vol_weights = _get_volume_weights(home_stats, away_stats)
    indicators = {}
    for key in vol_weights:
        h_val = get_stat(home_stats, key)
        a_val = get_stat(away_stats, key)
        h_val = h_val if h_val is not None else 0.0
        a_val = a_val if a_val is not None else 0.0
        mx = max(h_val, a_val)
        indicators[key] = round(min(h_val, a_val) / (mx + 0.001), 3) if mx > 0 else 0.0

    # Modificatori
    anomalies = check_efficiency_anomaly(home_stats, away_stats, risultato)
    for side, penalty in anomalies:
        if pronostico == 'GG':
            raw_score -= penalty * 0.7
        else:
            raw_score += penalty * 0.5
        modifiers_log.append(f"efficiency_anomaly_{side}")

    sterile = check_sterile_possession(home_stats, away_stats)
    for side in sterile:
        if pronostico == 'GG':
            raw_score -= 3
        else:
            raw_score += 2
        modifiers_log.append(f"sterile_possession_{side}")

    reds = check_red_card(home_stats, away_stats)
    for side in reds:
        if pronostico == 'GG':
            raw_score -= 5
        else:
            raw_score += 5
        modifiers_log.append(f"red_card_{side}")

    return max(0, min(100, round(raw_score))), indicators


def score_doppia_chance(pronostico, home_stats, away_stats, risultato, modifiers_log):
    """DOPPIA CHANCE (1X/X2/12) — quanto ha dominato la squadra ESCLUSA? Usa tutti i 39 campi."""
    eff_weights = get_available_weights(home_stats, away_stats)
    if not eff_weights:
        return 50, {}

    indicators = {}

    if pronostico in ('1X', 'X2'):
        esclusa = away_stats if pronostico == '1X' else home_stats

        score = 0.0
        for key, weight in eff_weights.items():
            h_val = get_stat(home_stats, key)
            a_val = get_stat(away_stats, key)
            e_val = get_stat(esclusa, key)
            h_val = h_val if h_val is not None else 0.0
            a_val = a_val if a_val is not None else 0.0
            e_val = e_val if e_val is not None else 0.0
            total = h_val + a_val + 0.001
            ratio_esclusa = e_val / total
            indicators[key] = round(1 - ratio_esclusa, 3)
            score += ratio_esclusa * weight

        dominio_esclusa = score * 100
        raw_score = (1 - dominio_esclusa / 100) * 100

    elif pronostico == '12':
        score = 0.0
        for key, weight in eff_weights.items():
            h_val = get_stat(home_stats, key)
            a_val = get_stat(away_stats, key)
            h_val = h_val if h_val is not None else 0.0
            a_val = a_val if a_val is not None else 0.0
            total = h_val + a_val + 0.001
            diff = abs(h_val - a_val) / total
            indicators[key] = round(diff, 3)
            score += diff * weight

        raw_score = score * 100
    else:
        return 50, {}

    raw_score = _apply_modifiers_segno(raw_score, pronostico, home_stats, away_stats, risultato, modifiers_log)
    return max(0, min(100, round(raw_score))), indicators


def score_multigol(pronostico, home_stats, away_stats, risultato, modifiers_log):
    """MULTIGOL — come Over/Under calibrato sul range specifico. Solo campi offensivi (14)."""
    mg_match = re.match(r'MG\s+(\d+)-(\d+)', pronostico)
    if not mg_match:
        return 50, {}

    low = int(mg_match.group(1))
    high = int(mg_match.group(2))

    vol_weights = _get_volume_weights(home_stats, away_stats)
    if not vol_weights:
        return 50, {}

    volume_score = 0.0
    indicators = {}
    for key, weight in vol_weights.items():
        h_val = get_stat(home_stats, key)
        a_val = get_stat(away_stats, key)
        h_val = h_val if h_val is not None else 0.0
        a_val = a_val if a_val is not None else 0.0
        combined = h_val + a_val
        ref = OVER_REFS.get(key, 1)
        ratio = min(combined / (ref + 0.001), 1.5) / 1.5
        indicators[key] = round(ratio, 3)
        volume_score += ratio * weight

    # Calibra in base al range
    if low == 0 and high <= 1:
        raw_score = (1 - volume_score) * 100
    elif low == 0 and high <= 2:
        raw_score = (1 - volume_score * 0.7) * 100
    elif low <= 1 and high <= 3:
        raw_score = (1 - abs(volume_score - 0.5) * 2) * 100
    elif low <= 2 and high <= 4:
        raw_score = volume_score * 0.85 * 100
    else:
        raw_score = volume_score * 100

    direction = "under" if (low == 0 and high <= 2) else "over"
    # Threshold equivalente per il bilanciamento: media del range
    mg_threshold = (low + high) / 2.0
    # Mappa a 1.5/2.5/3.5 per l'intensita
    if mg_threshold <= 1.5:
        bal_threshold = 1.5
    elif mg_threshold <= 2.5:
        bal_threshold = 2.5
    else:
        bal_threshold = 3.5
    raw_score = _apply_modifiers_volume(
        raw_score, direction, home_stats, away_stats, risultato, modifiers_log,
        threshold=bal_threshold)

    return max(0, min(100, round(raw_score))), indicators


# ═══════════════════════════════════════════════════════════
# DISPATCH — Analizza un singolo pronostico
# ═══════════════════════════════════════════════════════════

FORCE = False


def analyze_pronostico(prono, home_stats, away_stats, risultato):
    """
    Analizza un singolo pronostico e ritorna il dict post_match_analysis.
    Ritorna None se il pronostico va saltato.
    """
    tipo = prono.get('tipo', '')
    pronostico = prono.get('pronostico', '')
    hit = prono.get('hit')

    # Skip conditions
    if tipo == 'RISULTATO_ESATTO':
        return None
    if pronostico == 'NO BET':
        return None
    if hit is None:
        return None
    if prono.get('post_match_analysis') and not FORCE:
        return None

    modifiers_log = []

    # Normalizza alias tipo
    tipo_normalized = tipo
    if tipo.upper().replace('.', '').replace('-', '').replace(' ', '').replace('_', '') in ('DC', 'DOPPIACHANCE', 'DOPPIAC'):
        tipo_normalized = 'DOPPIA_CHANCE'
    elif tipo.upper().replace('.', '').replace('-', '').replace(' ', '').replace('_', '') in ('MG', 'MULTIGOL', 'MULTIGOAL'):
        tipo_normalized = 'MG'

    # Normalizza alias pronostici
    pron_normalized = pronostico
    if pronostico.lower() in ('goal', 'gol'):
        pron_normalized = 'GG'
    elif pronostico.lower() in ('no goal', 'no gol', 'nogoal'):
        pron_normalized = 'NG'

    if tipo_normalized == 'SEGNO':
        score, indicators = score_segno(pronostico, home_stats, away_stats, risultato, modifiers_log)
    elif tipo_normalized == 'GOL':
        if pron_normalized in ('GG', 'NG'):
            score, indicators = score_gg_ng(pron_normalized, home_stats, away_stats, risultato, modifiers_log)
        elif pronostico.startswith('MG'):
            score, indicators = score_multigol(pronostico, home_stats, away_stats, risultato, modifiers_log)
        elif pronostico.startswith('Over') or pronostico.startswith('Under'):
            score, indicators = score_over_under(pronostico, home_stats, away_stats, risultato, modifiers_log)
        else:
            return None
    elif tipo_normalized == 'DOPPIA_CHANCE':
        score, indicators = score_doppia_chance(pronostico, home_stats, away_stats, risultato, modifiers_log)
    elif tipo_normalized == 'MG':
        score, indicators = score_multigol(pronostico, home_stats, away_stats, risultato, modifiers_log)
    else:
        return None

    # Boost dominanza Tier A: se i campi principali puntano chiaramente
    # in una direzione, non lasciare che i Tier C/D annacquino il segnale
    # invert=True per Under e NG: indicatori bassi = pronostico coerente
    invert_tier_a = pronostico.startswith('Under') or pron_normalized == 'NG'
    # Per Multigol range basso (0-1, 0-2) si inverte anche
    if pronostico.startswith('MG'):
        mg_m = re.match(r'MG\s+(\d+)-(\d+)', pronostico)
        if mg_m and int(mg_m.group(1)) == 0 and int(mg_m.group(2)) <= 2:
            invert_tier_a = True
    score = apply_tier_a_dominance(score, indicators, invert=invert_tier_a)

    # Amplificazione non-lineare: allontana gli score dal centro (50)
    # per evitare che la massa dei Tier C/D appiattisca tutto su INCERTO
    score = amplify_from_center(score)
    score = max(0, min(100, round(score)))

    verdict = get_verdict(score)

    return {
        "coherence_score": score,
        "verdict": verdict,
        "market_type": tipo_normalized,
        "phase": 1,
        "indicators": indicators,
        "modifiers_applied": modifiers_log,
        "analyzed_at": datetime.now(timezone.utc),
    }


# ═══════════════════════════════════════════════════════════
# PROCESSAMENTO PER DATA
# ═══════════════════════════════════════════════════════════

def _find_result_h2h(home, away, league, date_str):
    """Cerca il risultato reale in h2h_by_round come fallback."""
    h2h_coll = db['h2h_by_round']
    rounds = h2h_coll.find(
        {'league': league},
        {'matches.home': 1, 'matches.away': 1, 'matches.real_score': 1}
    )
    for r in rounds:
        for m in r.get('matches', []):
            if m.get('home') == home and m.get('away') == away:
                rs = m.get('real_score')
                if rs:
                    return rs
    return ''


def process_date(date_str):
    """Processa tutti i pronostici di una data. Ritorna stats dict."""
    stats = {
        'analyzed': 0,
        'skip_already': 0,
        'skip_no_stats': 0,
        'skip_not_concluded': 0,
        'skip_re': 0,
        'verdicts': Counter(),
        'hit_verdicts': Counter(),
        'miss_verdicts': Counter(),
        'modifiers': Counter(),
    }

    coll = db['daily_predictions_unified']
    post_match = db['post_match_stats']

    preds = list(coll.find(
        {'date': date_str},
        {'home': 1, 'away': 1, 'league': 1, 'pronostici': 1}
    ))

    if not preds:
        return stats

    pms_docs = list(post_match.find(
        {'date': date_str},
        {'home': 1, 'away': 1, 'home_stats': 1, 'away_stats': 1, 'risultato': 1}
    ))
    pms_map = {}
    for doc in pms_docs:
        key = (doc.get('home', ''), doc.get('away', ''))
        pms_map[key] = doc

    for pred in preds:
        home = pred.get('home', '')
        away = pred.get('away', '')
        key = (home, away)

        pms = pms_map.get(key)
        if not pms:
            stats['skip_no_stats'] += len([p for p in pred.get('pronostici', [])
                                           if p.get('tipo') != 'RISULTATO_ESATTO'
                                           and p.get('pronostico') != 'NO BET'])
            continue

        home_stats = pms.get('home_stats', {})
        away_stats = pms.get('away_stats', {})
        risultato = pms.get('risultato', '')

        if not risultato or risultato == 'None-None' or risultato == '?-?':
            risultato = _find_result_h2h(home, away, pred.get('league', ''), date_str)

        updates = {}
        pronostici = pred.get('pronostici', [])

        for i, prono in enumerate(pronostici):
            tipo = prono.get('tipo', '')
            hit = prono.get('hit')

            if tipo == 'RISULTATO_ESATTO':
                stats['skip_re'] += 1
                continue
            if prono.get('pronostico') == 'NO BET':
                stats['skip_re'] += 1
                continue
            if hit is None:
                stats['skip_not_concluded'] += 1
                continue
            if prono.get('post_match_analysis') and not FORCE:
                stats['skip_already'] += 1
                continue

            # Controlla xG per SEGNO (primo indicatore, senza non ha senso)
            if tipo == 'SEGNO':
                h_xg = get_stat(home_stats, 'xg')
                a_xg = get_stat(away_stats, 'xg')
                if (h_xg is None or h_xg == 0) and (a_xg is None or a_xg == 0):
                    stats['skip_no_stats'] += 1
                    continue

            analysis = analyze_pronostico(prono, home_stats, away_stats, risultato)
            if analysis is None:
                continue

            updates[f'pronostici.{i}.post_match_analysis'] = analysis
            stats['analyzed'] += 1
            stats['verdicts'][analysis['verdict']] += 1

            if hit is True:
                stats['hit_verdicts'][analysis['verdict']] += 1
            elif hit is False:
                stats['miss_verdicts'][analysis['verdict']] += 1

            for mod in analysis.get('modifiers_applied', []):
                stats['modifiers'][mod] += 1

        if updates:
            try:
                coll.update_one({'_id': pred['_id']}, {'$set': updates})
            except Exception as e:
                print(f"  Errore update {home} vs {away}: {e}")

    return stats


# ═══════════════════════════════════════════════════════════
# REPORT FINALE
# ═══════════════════════════════════════════════════════════

def print_report(all_stats, dates):
    """Stampa il report finale aggregato."""
    totals = {
        'analyzed': 0, 'skip_already': 0, 'skip_no_stats': 0,
        'skip_not_concluded': 0, 'skip_re': 0,
        'verdicts': Counter(), 'hit_verdicts': Counter(),
        'miss_verdicts': Counter(), 'modifiers': Counter(),
    }

    for s in all_stats:
        totals['analyzed'] += s['analyzed']
        totals['skip_already'] += s['skip_already']
        totals['skip_no_stats'] += s['skip_no_stats']
        totals['skip_not_concluded'] += s['skip_not_concluded']
        totals['skip_re'] += s['skip_re']
        totals['verdicts'] += s['verdicts']
        totals['hit_verdicts'] += s['hit_verdicts']
        totals['miss_verdicts'] += s['miss_verdicts']
        totals['modifiers'] += s['modifiers']

    total_analyzed = totals['analyzed']

    print(f"\n{'='*60}")
    print(f"  POST-MATCH COHERENCE ANALYZER — Report (39 campi)")
    print(f"{'='*60}")
    print(f"  Date: {dates[0]} -> {dates[-1]}" if len(dates) > 1 else f"  Data: {dates[0]}")
    print(f"  Analizzati: {total_analyzed} | Skip gia fatti: {totals['skip_already']} | "
          f"Skip no stats: {totals['skip_no_stats']} | Skip non conclusi: {totals['skip_not_concluded']} | "
          f"Skip RE/NB: {totals['skip_re']}")

    if total_analyzed == 0:
        print("\n  Nessun pronostico analizzato.")
        print(f"{'='*60}")
        return

    print(f"\n  Verdetti:")
    for label in ["COERENTE", "RAGIONEVOLE", "INCERTO", "FORZATO", "ERRATO"]:
        count = totals['verdicts'].get(label, 0)
        pct = count / total_analyzed * 100 if total_analyzed else 0
        bar = '#' * int(pct / 2)
        print(f"    {label:12s}  {count:3d} ({pct:5.1f}%)  {bar}")

    print(f"\n  Per esito:")
    hit_solid = totals['hit_verdicts'].get('COERENTE', 0) + totals['hit_verdicts'].get('RAGIONEVOLE', 0)
    hit_lucky = totals['hit_verdicts'].get('FORZATO', 0) + totals['hit_verdicts'].get('ERRATO', 0)
    hit_mid = totals['hit_verdicts'].get('INCERTO', 0)
    miss_unlucky = totals['miss_verdicts'].get('COERENTE', 0) + totals['miss_verdicts'].get('RAGIONEVOLE', 0)
    miss_error = totals['miss_verdicts'].get('FORZATO', 0) + totals['miss_verdicts'].get('ERRATO', 0)
    miss_mid = totals['miss_verdicts'].get('INCERTO', 0)

    print(f"    HIT + COERENTE/RAGIONEVOLE:   {hit_solid:3d}  -> modello solido")
    print(f"    HIT + INCERTO:                {hit_mid:3d}  -> al limite")
    print(f"    HIT + FORZATO/ERRATO:         {hit_lucky:3d}  -> fortunati")
    print(f"    MISS + COERENTE/RAGIONEVOLE:  {miss_unlucky:3d}  -> sfortuna")
    print(f"    MISS + INCERTO:               {miss_mid:3d}  -> era 50/50")
    print(f"    MISS + FORZATO/ERRATO:        {miss_error:3d}  -> errori reali")

    if totals['modifiers']:
        print(f"\n  Modificatori applicati:")
        for mod, count in totals['modifiers'].most_common():
            print(f"    {count}x {mod}")

    print(f"{'='*60}")


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    global FORCE

    parser = argparse.ArgumentParser(description='Post-Match Coherence Analyzer — Fase 1 (39 campi)')
    parser.add_argument('--date', type=str, help='Data specifica (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, default=1, help='Ultimi N giorni (default: 1 = ieri)')
    parser.add_argument('--from', dest='from_date', type=str, help='Data inizio range')
    parser.add_argument('--to', dest='to_date', type=str, help='Data fine range')
    parser.add_argument('--force', action='store_true', help='Ricalcola anche pronostici gia analizzati')
    args = parser.parse_args()

    FORCE = args.force

    if args.date:
        dates = [args.date]
    elif args.from_date and args.to_date:
        start = datetime.strptime(args.from_date, "%Y-%m-%d")
        end = datetime.strptime(args.to_date, "%Y-%m-%d")
        dates = []
        d = start
        while d <= end:
            dates.append(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)
    else:
        today = datetime.now()
        dates = []
        for i in range(args.days, 0, -1):
            d = today - timedelta(days=i)
            dates.append(d.strftime("%Y-%m-%d"))

    print(f"{'='*60}")
    print(f"  POST-MATCH COHERENCE ANALYZER — Fase 1 (39 campi)")
    print(f"  {len(dates)} date da processare")
    if FORCE:
        print(f"  FORCE MODE: ricalcolo anche gia analizzati")
    print(f"{'='*60}")

    all_stats = []
    for date_str in dates:
        print(f"\n  [{date_str}]")
        s = process_date(date_str)
        all_stats.append(s)
        if s['analyzed'] > 0:
            print(f"    Analizzati: {s['analyzed']} pronostici")
        else:
            print(f"    Nessun pronostico analizzato"
                  f" (no stats: {s['skip_no_stats']}, non conclusi: {s['skip_not_concluded']},"
                  f" gia fatti: {s['skip_already']})")

    print_report(all_stats, dates)


if __name__ == '__main__':
    main()
