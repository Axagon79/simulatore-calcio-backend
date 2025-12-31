import statistics
from collections import Counter
import math

def get_sign(h, a):
    """Restituisce il segno 1X2."""
    if h > a: return "1"
    elif a > h: return "2"
    return "X"

def analyze_betting_data(all_results, bookmaker_odds=None):
    """
    Trasforma le simulazioni grezze in un report professionale.
    all_results: lista di stringhe tipo ['2-1', '1-1', '0-2', ...]
    """
    if not all_results:
        return None

    total_sims = len(all_results)
    
    # --- 1. CALCOLO PROBABILITÀ 1X2 ---
    signs_count = {'1': 0, 'X': 0, '2': 0}
    for score in all_results:
        h, a = map(int, score.split("-"))
        signs_count[get_sign(h, a)] += 1
    
    prob_1x2 = {s: (count / total_sims) * 100 for s, count in signs_count.items()}
    
    # --- 2. ANALISI DISPERSIONE (IMPREVEDIBILITÀ) ---
    pct_values = list(prob_1x2.values())
    global_std_dev = statistics.stdev(pct_values) if len(pct_values) > 1 else 0
    
    # Score imprevedibilità normalizzato (0-100)
    dispersion_score = max(0, min(100, 100 - (global_std_dev / 0.7)))
    
    is_dispersed = False
    recommendation_1x2 = "CONSIGLIATA"
    warning_message = None

    # Logica soglie imprevedibilità dal terminale
    if global_std_dev < 20:
        is_dispersed = True
        recommendation_1x2 = "FORTEMENTE SCONSIGLIATA"
        warning_message = "ALTA IMPREVEDIBILITÀ - Risultati equiprobabili tra più segni."
    elif global_std_dev < 35:
        is_dispersed = True
        recommendation_1x2 = "RISCHIOSA"
        warning_message = "RISULTATI DISPERSI - Due o più segni molto vicini."

    # --- 3. CONFRONTO VALUE BET ⭐ ---
    value_bets = {}
    if bookmaker_odds:
        for sign in ['1', 'X', '2']:
            odd = bookmaker_odds.get(sign)
            if odd and odd > 0:
                prob_bookmaker = (1 / odd) * 100
                differenza = prob_1x2[sign] - prob_bookmaker
                # Se l'IA stima +10% rispetto al bookmaker, è una Value Bet
                value_bets[sign] = {
                    "ia_prob": round(prob_1x2[sign], 1),
                    "book_prob": round(prob_bookmaker, 1),
                    "diff": round(differenza, 1),
                    "is_value": differenza > 10
                }

    # --- 4. UNDER/OVER & GOL/NOGOL ---
    under_count = sum(1 for s in all_results if sum(map(int, s.split("-"))) <= 2.5)
    gg_count = sum(1 for s in all_results if all(int(x) > 0 for x in s.split("-")))
    
    prob_uo = {"U2.5": (under_count / total_sims) * 100, "O2.5": ((total_sims - under_count) / total_sims) * 100}
    prob_gg = {"GG": (gg_count / total_sims) * 100, "NG": ((total_sims - gg_count) / total_sims) * 100}

    # --- 5. TOP 5 RISULTATI ESATTI ---
    top5_raw = Counter(all_results).most_common(5)
    top5_formatted = [
        {"score": s, "prob": round((count / total_sims) * 100, 1)} 
        for s, count in top5_raw
    ]

    return {
        "analisi_dispersione": {
            "std_dev": round(global_std_dev, 1),
            "score_imprevedibilita": round(dispersion_score, 0),
            "is_dispersed": is_dispersed,
            "warning": warning_message
        },
        "probabilita_1x2": {s: round(p, 1) for s, p in prob_1x2.items()},
        "value_bets": value_bets,
        "scommessa_consigliata": recommendation_1x2,
        "under_over": {k: round(v, 1) for k, v in prob_uo.items()},
        "gol_nogol": {k: round(v, 1) for k, v in prob_gg.items()},
        "top_risultati": top5_formatted,
        "totale_simulazioni": total_sims
    }