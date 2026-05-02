"""
Pattern Match Engine — engine principale v2 con punteggio pesato.

Sistema a punteggio (sostituisce la matrice 5x5 dell'engine v1 archiviato in
match_engine_5x5_legacy.py):
- 19 feature, ognuna con tolleranza unica e peso (totale max = 122 punti)
- Punteggio per ogni partita storica = somma pesi feature compatibili
- Pool unico = top 20 partite con score >= 73/122 (60%)
- Numero minimo per emettere pronostico: 9 partite
- Filtro DC>=71% sul segno 1X2 secco (unico mercato che lo merita per
  validazione 200 partite)

Mercati emessi:
- DC, O/U 1.5/2.5/3.5, GG/NG, MG, RE top 5 (sempre come dominante del pool)
- 1X2 secco: solo se DC>=71% sul segno proposto

Uso CLI:
    python -m ai_engine.pattern_match.match_engine --match_uid I1_2024-25_...
    python -m ai_engine.pattern_match.match_engine --como-napoli
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

import numpy as np
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.config import MONGO_COLLECTION_MATCHES, LEAGUES
from config import db


# ====================================================================
# Pesi delle 19 feature (somma = 122)
# ====================================================================

FEATURE_WEIGHTS = {
    "lega":                                 2,
    "blocco_stagione":                      4,
    "fascia_classifica_casa":               7,
    "fascia_classifica_ospite":             7,
    "punti_casa":                           5,
    "punti_ospite":                         5,
    "differenza_punti":                     6,  # con segno
    "differenza_reti_casa":                 7,
    "differenza_reti_ospite":               7,
    "fascia_classifica_solo_casa":          5,
    "punti_solo_casa":                      5,
    "fascia_classifica_solo_trasferta":     5,
    "punti_solo_trasferta":                 5,
    "prob_implicita_1":                     10,
    "prob_implicita_X":                     10,
    "prob_implicita_2":                     10,
    "elo_casa":                             8,
    "elo_ospite":                           8,
    "differenza_elo":                       6,  # con segno
}

MAX_SCORE = sum(FEATURE_WEIGHTS.values())  # 122

# Soglia minima score per accettare una partita nel pool
MIN_SCORE_THRESHOLD = int(MAX_SCORE * 0.60)  # 73

# Pool size obiettivo
POOL_SIZE = 20

# Minimo partite per emettere pronostico
MIN_PARTITE_PER_PRONOSTICO = 9

# Soglia DC per emettere il segno 1X2 secco.
# Unico filtro mantenuto: 1X2 ha un "fratello logico" nelle DC, quindi e' l'unico
# mercato dove un filtro multi-mercato ha senso teorico. Validato su 200 partite:
# 1X2 filtrato 61.7% vs baseline 48.2% (+13.5 punti).
#
# Tutti gli altri filtri (O/U, GG/NG, MG, pattern Goal, pattern NoGoal) sono stati
# RIMOSSI dopo la validazione 200 partite: i numeri belli sui 50 erano overfit,
# su 200 crollano o restano uguali alla baseline.
DC_THRESHOLD_FOR_SECCO = 0.71


# ====================================================================
# Tolleranze fisse (concordate con utente, una per feature)
# ====================================================================

# Tolleranze numeriche assolute
NUMERIC_TOLERANCES = {
    "punti_casa":                  6,
    "punti_ospite":                6,
    "differenza_punti":            5,    # con segno
    "differenza_reti_casa":        6,
    "differenza_reti_ospite":      6,
    "punti_solo_casa":             3,
    "punti_solo_trasferta":        3,
    "prob_implicita_1":            0.015,  # 1.5 punti percentuali
    "prob_implicita_X":            0.015,
    "prob_implicita_2":            0.015,
    "elo_casa":                    50,
    "elo_ospite":                  50,
    "differenza_elo":              100,   # con segno
}

# Feature categoriche/fasce (matching = stessa fascia)
FASCIA_FEATURES = {
    "blocco_stagione",
    "fascia_classifica_casa",
    "fascia_classifica_ospite",
    "fascia_classifica_solo_casa",
    "fascia_classifica_solo_trasferta",
}


# ====================================================================
# Configurazione lega-specifica per fasce
# ====================================================================

# Numero squadre per lega (per calcolare fasce classifica in 5 quintili)
LEAGUE_TEAMS_COUNT = {
    "E0": 20, "SP1": 20, "I1": 20, "T1": 20, "SC0": 12,
    "D1": 18, "F1": 18, "N1": 18, "P1": 18, "B1": 16,
}

# Numero giornate per lega (per calcolare blocchi stagione 1-5)
LEAGUE_MATCHDAYS = {
    "E0": 38, "SP1": 38, "I1": 38, "T1": 38, "SC0": 38,
    "D1": 34, "F1": 34, "N1": 34, "P1": 34, "B1": 30,
}


def compute_fascia(posizione: int | None, n_squadre: int) -> int:
    """Restituisce 1 (Alta) ... 5 (Bassa) in base alla posizione."""
    if posizione is None or n_squadre is None or n_squadre == 0 or posizione < 1:
        return 0  # 0 = sconosciuto, non matcha mai
    block_size = n_squadre / 5
    fascia = int((posizione - 1) // block_size) + 1
    return min(5, max(1, fascia))


def compute_blocco_stagione(giornata: int | None, lega: str) -> int:
    """Restituisce 1 (inizio) ... 5 (finale)."""
    n_match = LEAGUE_MATCHDAYS.get(lega, 38)
    if giornata is None or giornata < 1:
        return 0
    block_size = n_match / 5
    blocco = int((giornata - 1) // block_size) + 1
    return min(5, max(1, blocco))


# ====================================================================
# Estrazione feature derivate da un feature_vector originale
# ====================================================================

def extract_extended_features(fv: dict, lega: str) -> dict:
    """
    Aggiunge campi calcolati al feature_vector originale:
    - blocco_stagione (1-5)
    - fascia_classifica_casa, ospite, solo_casa, solo_trasferta (1-5)
    - differenza_reti_casa, ospite (gol fatti - subiti)
    - differenza_elo (con segno)
    - differenza_punti (con segno)
    - punti_solo_casa, punti_solo_trasferta (alias)
    """
    n_squadre = LEAGUE_TEAMS_COUNT.get(lega, 20)
    out = dict(fv)
    out["lega"] = lega

    out["blocco_stagione"] = compute_blocco_stagione(fv.get("giornata"), lega)
    out["fascia_classifica_casa"] = compute_fascia(fv.get("posizione_classifica_casa"), n_squadre)
    out["fascia_classifica_ospite"] = compute_fascia(fv.get("posizione_classifica_ospite"), n_squadre)
    out["fascia_classifica_solo_casa"] = compute_fascia(
        fv.get("posizione_classifica_casa_solo_casalinga"), n_squadre)
    out["fascia_classifica_solo_trasferta"] = compute_fascia(
        fv.get("posizione_classifica_ospite_solo_trasferta"), n_squadre)

    gf_casa = fv.get("gol_fatti_casa", 0) or 0
    gs_casa = fv.get("gol_subiti_casa", 0) or 0
    gf_osp = fv.get("gol_fatti_ospite", 0) or 0
    gs_osp = fv.get("gol_subiti_ospite", 0) or 0
    out["differenza_reti_casa"] = gf_casa - gs_casa
    out["differenza_reti_ospite"] = gf_osp - gs_osp

    out["punti_solo_casa"] = fv.get("punti_casa_solo_casalinga", 0)
    out["punti_solo_trasferta"] = fv.get("punti_ospite_solo_trasferta", 0)

    # differenza_punti e differenza_elo con segno (potrebbero essere gia presenti)
    if out.get("differenza_punti") is None:
        out["differenza_punti"] = (fv.get("punti_casa", 0) or 0) - (fv.get("punti_ospite", 0) or 0)
    if out.get("differenza_elo") is None:
        elo_c = fv.get("elo_casa")
        elo_o = fv.get("elo_ospite")
        if elo_c is not None and elo_o is not None:
            out["differenza_elo"] = elo_c - elo_o

    return out


# ====================================================================
# Calcolo punteggio compatibilita (target vs candidate)
# ====================================================================

def compute_match_score(target_ext: dict, candidate_ext: dict) -> tuple[int, dict]:
    """
    Restituisce (punteggio totale 0..122, dict per-feature compatibili).
    target_ext e candidate_ext sono feature_vector estesi.
    """
    score = 0
    detail = {}

    # 1. Lega: peso 2 SEMPRE (qualsiasi lega va bene secondo decisione utente)
    if candidate_ext.get("lega") in {l["fd_code"] for l in LEAGUES}:
        score += FEATURE_WEIGHTS["lega"]
        detail["lega"] = True

    # 2-5, 10, 12. Feature di fascia: stesso valore della fascia
    for f in FASCIA_FEATURES:
        t_val = target_ext.get(f, 0)
        c_val = candidate_ext.get(f, 0)
        if t_val != 0 and t_val == c_val:
            score += FEATURE_WEIGHTS[f]
            detail[f] = True

    # 5-9, 11, 13-19. Feature numeriche con tolleranza
    for f, tol in NUMERIC_TOLERANCES.items():
        t_val = target_ext.get(f)
        c_val = candidate_ext.get(f)
        if t_val is None or c_val is None:
            continue
        if abs(t_val - c_val) <= tol:
            score += FEATURE_WEIGHTS[f]
            detail[f] = True

    return score, detail


# ====================================================================
# Caricamento dataset
# ====================================================================

def load_dataset_extended() -> list[dict]:
    """
    Carica tutte le partite con feature_vector esteso (campi derivati).
    """
    coll = db[MONGO_COLLECTION_MATCHES]
    out = []
    cursor = coll.find({}, {
        "match_uid": 1, "lega": 1, "stagione": 1, "data_partita": 1,
        "home_team": 1, "away_team": 1,
        "feature_vector": 1, "outcome": 1,
    })
    for doc in cursor:
        fv = doc["feature_vector"]
        # Skip se manca Elo (squadre senza Elo, ~160 partite)
        if fv.get("elo_casa") is None or fv.get("elo_ospite") is None:
            continue
        ext = extract_extended_features(fv, doc["lega"])
        out.append({
            "match_uid": doc["match_uid"],
            "lega": doc["lega"],
            "stagione": doc.get("stagione"),
            "data": doc["data_partita"],
            "home": doc["home_team"],
            "away": doc["away_team"],
            "ft_score": doc["outcome"]["ft_score"],
            "result": doc["outcome"]["result_1x2"],
            "goals_home": doc["outcome"]["goals_home"],
            "goals_away": doc["outcome"]["goals_away"],
            "fv_extended": ext,
        })
    return out


# ====================================================================
# Pool unico (top 50, soglia 60%)
# ====================================================================

def compute_feature_frequency(target_ext: dict, pool: list[dict]) -> dict:
    """Per ogni feature, quante partite del pool sono compatibili."""
    if not pool:
        return {}
    freq = {f: 0 for f in FEATURE_WEIGHTS}
    for entry in pool:
        _, detail = compute_match_score(target_ext, entry["fv_extended"])
        for f in FEATURE_WEIGHTS:
            if detail.get(f):
                freq[f] += 1
    return freq


def compute_pool(target_ext: dict, dataset: list[dict],
                 exclude_uid: str | None = None,
                 pool_size: int = POOL_SIZE,
                 min_score: int = MIN_SCORE_THRESHOLD) -> dict:
    """
    Calcola il pool unico:
    1. Score per ogni partita storica
    2. Filtro: score >= min_score
    3. Top pool_size partite per score decrescente

    Returns:
        {
          "partite": list[dict],         # le partite nel pool, ordinate score desc
          "n": int,                       # quante partite nel pool
          "score_medio": float,           # media score
          "score_max": int,               # score della partita migliore
          "score_min": int,               # score della partita peggiore (nel pool)
          "scartate_sotto_soglia": int,   # quante avevano score < min_score
        }
    """
    scored = []
    scartate = 0
    for entry in dataset:
        if exclude_uid and entry["match_uid"] == exclude_uid:
            continue
        score, _detail = compute_match_score(target_ext, entry["fv_extended"])
        if score < min_score:
            scartate += 1
            continue
        scored.append({**entry, "score": score})

    scored.sort(key=lambda x: -x["score"])
    pool = scored[:pool_size]

    if pool:
        score_medio = sum(p["score"] for p in pool) / len(pool)
        score_max = pool[0]["score"]
        score_min = pool[-1]["score"]
    else:
        score_medio = 0.0
        score_max = 0
        score_min = 0

    return {
        "partite": pool,
        "n": len(pool),
        "score_medio": score_medio,
        "score_max": score_max,
        "score_min": score_min,
        "scartate_sotto_soglia": scartate,
    }


# ====================================================================
# Calcolo mercati su un pool
# ====================================================================

def compute_markets_for_pool(pool: list[dict]) -> dict:
    """Calcola tutti i mercati per il pool. Restituisce dict di mercati o None se vuoto."""
    n = len(pool)
    if n == 0:
        return {"n": 0}

    n_h = sum(1 for p in pool if p["result"] == "H")
    n_d = sum(1 for p in pool if p["result"] == "D")
    n_a = sum(1 for p in pool if p["result"] == "A")
    totals = [p["goals_home"] + p["goals_away"] for p in pool]
    homes = [p["goals_home"] for p in pool]
    aways = [p["goals_away"] for p in pool]
    n_goal = sum(1 for p in pool if p["goals_home"] >= 1 and p["goals_away"] >= 1)
    n_float = float(n)

    return {
        "n": n,
        "1x2": {
            "1": n_h / n_float,
            "X": n_d / n_float,
            "2": n_a / n_float,
        },
        "doppia_chance": {
            "1X": (n_h + n_d) / n_float,
            "X2": (n_d + n_a) / n_float,
            "12": (n_h + n_a) / n_float,
        },
        "over_under_1_5": {
            "over":  sum(1 for t in totals if t >= 2) / n_float,
            "under": sum(1 for t in totals if t <= 1) / n_float,
        },
        "over_under_2_5": {
            "over":  sum(1 for t in totals if t >= 3) / n_float,
            "under": sum(1 for t in totals if t <= 2) / n_float,
        },
        "over_under_3_5": {
            "over":  sum(1 for t in totals if t >= 4) / n_float,
            "under": sum(1 for t in totals if t <= 3) / n_float,
        },
        "goal_nogoal": {
            "goal":   n_goal / n_float,
            "nogoal": (n - n_goal) / n_float,
        },
        "multigol": {
            "1_2": sum(1 for t in totals if 1 <= t <= 2) / n_float,
            "2_3": sum(1 for t in totals if 2 <= t <= 3) / n_float,
            "1_3": sum(1 for t in totals if 1 <= t <= 3) / n_float,
            "2_4": sum(1 for t in totals if 2 <= t <= 4) / n_float,
            "3_5": sum(1 for t in totals if 3 <= t <= 5) / n_float,
            "4_6": sum(1 for t in totals if 4 <= t <= 6) / n_float,
        },
        "medie": {
            "casa":   sum(homes) / n_float,
            "ospite": sum(aways) / n_float,
            "totali": sum(totals) / n_float,
        },
    }


def emit_1x2_secco(mkt: dict, dc_threshold: float = DC_THRESHOLD_FOR_SECCO) -> tuple[str | None, str]:
    """
    Decide se emettere il segno 1X2 secco in base alle 2 DC che lo contengono.

    Returns:
        (segno_secco | None, motivo)
        - segno_secco = "1" / "X" / "2" se entrambe le DC sono >= soglia
        - None se almeno una DC e' sotto soglia (in quel caso emette solo la DC)
    """
    if not mkt.get("1x2") or not mkt.get("doppia_chance"):
        return None, "mercati assenti"

    d_1x2 = mkt["1x2"]
    dc = mkt["doppia_chance"]
    sign = max(d_1x2, key=d_1x2.get)  # "1" / "X" / "2"

    # DC richieste per ogni segno
    if sign == "1":
        dc1, dc2 = dc["1X"], dc["12"]
        dc1_label, dc2_label = "1X", "12"
    elif sign == "X":
        dc1, dc2 = dc["1X"], dc["X2"]
        dc1_label, dc2_label = "1X", "X2"
    else:  # "2"
        dc1, dc2 = dc["X2"], dc["12"]
        dc1_label, dc2_label = "X2", "12"

    if dc1 >= dc_threshold and dc2 >= dc_threshold:
        return sign, f"DC {dc1_label}={dc1*100:.1f}% e DC {dc2_label}={dc2*100:.1f}% (entrambe sopra soglia {dc_threshold*100:.1f}%)"
    else:
        return None, f"DC {dc1_label}={dc1*100:.1f}% / DC {dc2_label}={dc2*100:.1f}% (almeno una sotto soglia {dc_threshold*100:.1f}%)"


def compute_re_top5(pool: list[dict], max_results: int = 5) -> list[dict]:
    """
    Risultato Esatto: top 5 RE unici dal pool, ordinati per frequenza decrescente.
    Per il match_uid rappresentativo: la partita con score piu alto tra quelle con quel RE.
    """
    if not pool:
        return []

    # Conta frequenza di ogni RE nel pool
    score_counts = Counter([p["ft_score"] for p in pool])
    # Per ogni RE, trova la partita con score di compatibilita piu alto
    score_to_best = {}
    for p in pool:
        s = p["ft_score"]
        if s not in score_to_best or p["score"] > score_to_best[s]["score"]:
            score_to_best[s] = p

    # Ordina i RE per frequenza decrescente, poi prendi top max_results
    out = []
    for ft_score, freq in score_counts.most_common():
        if len(out) >= max_results:
            break
        best = score_to_best[ft_score]
        out.append({
            "score": ft_score,
            "freq": freq,
            "n_pool": len(pool),
            "match_uid": best["match_uid"],
            "compat_score": best["score"],
            "home": best["home"],
            "away": best["away"],
            "data": best["data"].strftime("%Y-%m-%d") if hasattr(best["data"], "strftime") else str(best["data"]),
        })
    return out


# ====================================================================
# Output rendering
# ====================================================================

def print_pool_summary(pool_info: dict, target_label: str):
    print(f"\n{'='*80}")
    print(f"POOL — TARGET: {target_label}")
    print(f"{'='*80}")
    print(f"N partite nel pool:      {pool_info['n']} (su max {POOL_SIZE})")
    print(f"Score migliore:          {pool_info['score_max']}/{MAX_SCORE} ({pool_info['score_max']/MAX_SCORE*100:.0f}%)")
    print(f"Score minore (nel pool): {pool_info['score_min']}/{MAX_SCORE} ({pool_info['score_min']/MAX_SCORE*100:.0f}%)")
    print(f"Score medio:             {pool_info['score_medio']:.1f}/{MAX_SCORE} ({pool_info['score_medio']/MAX_SCORE*100:.0f}%)")
    print(f"Soglia minima score:     {MIN_SCORE_THRESHOLD}/{MAX_SCORE} (60%)")
    print(f"Scartate sotto soglia:   {pool_info['scartate_sotto_soglia']}")
    if pool_info['n'] < MIN_PARTITE_PER_PRONOSTICO:
        print(f"\n⚠️  ATTENZIONE: pool < {MIN_PARTITE_PER_PRONOSTICO} partite — pronostico NON emesso (campione troppo piccolo)")


def print_mercati(mkt: dict):
    if mkt.get("n", 0) == 0:
        print("\n[mercati] Pool vuoto, nessun calcolo.")
        return
    print(f"\n## 1X2")
    for k in ["1", "X", "2"]:
        print(f"  {k}: {mkt['1x2'][k]*100:.1f}%")

    print(f"\n## Doppia Chance")
    for k in ["1X", "X2", "12"]:
        print(f"  {k}: {mkt['doppia_chance'][k]*100:.1f}%")

    print(f"\n## Over/Under")
    for soglia in ["1_5", "2_5", "3_5"]:
        d = mkt[f"over_under_{soglia}"]
        print(f"  {soglia.replace('_','.')} → Over {d['over']*100:.1f}% | Under {d['under']*100:.1f}%")

    print(f"\n## Goal/NoGoal")
    print(f"  Goal:   {mkt['goal_nogoal']['goal']*100:.1f}%")
    print(f"  NoGoal: {mkt['goal_nogoal']['nogoal']*100:.1f}%")

    print(f"\n## Multigol")
    for k, v in mkt["multigol"].items():
        print(f"  {k.replace('_','-')}: {v*100:.1f}%")

    print(f"\n## Medie gol")
    print(f"  casa:   {mkt['medie']['casa']:.2f}")
    print(f"  ospite: {mkt['medie']['ospite']:.2f}")
    print(f"  totali: {mkt['medie']['totali']:.2f}")


def print_re_top5(re_list: list[dict]):
    print(f"\n## Risultato Esatto Top 5")
    if not re_list:
        print("  (nessun RE nel pool)")
        return
    for i, r in enumerate(re_list, 1):
        print(f"  {i}. {r['score']:6s} (freq {r['freq']}/{r['n_pool']}, score compat {r['compat_score']}/{MAX_SCORE}) — esempio: {r['data']} {r['home']} vs {r['away']}")


def print_top_partite(pool_info: dict, n: int = 10):
    print(f"\n## Top {n} partite del pool (per somiglianza)")
    for p in pool_info["partite"][:n]:
        print(f"  score={p['score']}/{MAX_SCORE} ({p['score']/MAX_SCORE*100:.0f}%)  "
              f"{p['data'].strftime('%Y-%m-%d') if hasattr(p['data'], 'strftime') else p['data']}  "
              f"{p['home']:25s} {p['ft_score']:6s} {p['away']:25s} [{p['lega']}]")


# ====================================================================
# Vettore feature Como-Napoli (per --como-napoli)
# ====================================================================

COMO_NAPOLI_FV = {
    "giornata": 35,
    "posizione_classifica_casa": 5,
    "posizione_classifica_ospite": 2,
    "punti_casa": 61,
    "punti_ospite": 69,
    "differenza_punti": -8,
    "partite_giocate_casa": 34,
    "partite_giocate_ospite": 34,
    "gol_fatti_casa": 59,
    "gol_subiti_casa": 28,
    "gol_fatti_ospite": 52,
    "gol_subiti_ospite": 33,
    "posizione_classifica_casa_solo_casalinga": 5,
    "punti_casa_solo_casalinga": 35,
    "posizione_classifica_ospite_solo_trasferta": 3,
    "punti_ospite_solo_trasferta": 29,
    "prob_implicita_1": 1.0 / 2.20,
    "prob_implicita_X": 1.0 / 3.20,
    "prob_implicita_2": 1.0 / 3.50,
    "elo_casa": 1746.08,
    "elo_ospite": 1783.48,
}


# ====================================================================
# Main CLI
# ====================================================================

def main():
    parser = argparse.ArgumentParser(description="Weighted Pattern Match Engine v2")
    parser.add_argument("--match_uid", help="match_uid di una partita storica come target")
    parser.add_argument("--como-napoli", action="store_true", help="Test su Como-Napoli 2026-05-02")
    parser.add_argument("--top-n", type=int, default=10, help="Quante partite top mostrare")
    args = parser.parse_args()

    print("[load] caricamento dataset...")
    dataset = load_dataset_extended()
    print(f"[load] {len(dataset)} partite caricate (escludendo quelle senza Elo)\n")

    if args.como_napoli:
        target_lega = "I1"
        target_ext = extract_extended_features(COMO_NAPOLI_FV, target_lega)
        target_label = "Como vs Napoli — 2 maggio 2026 (Serie A, giornata 35)"
        target_real = "0-0 (X)"
        exclude_uid = None
    elif args.match_uid:
        coll = db[MONGO_COLLECTION_MATCHES]
        doc = coll.find_one({"match_uid": args.match_uid})
        if not doc:
            print(f"Match non trovato: {args.match_uid}")
            return 1
        target_lega = doc["lega"]
        target_ext = extract_extended_features(doc["feature_vector"], target_lega)
        target_label = f"{doc['home_team']} vs {doc['away_team']} ({doc['data_partita'].strftime('%Y-%m-%d')})"
        target_real = f"{doc['outcome']['ft_score']} (FTR={doc['outcome']['result_1x2']})"
        exclude_uid = args.match_uid
    else:
        print("Specificare --match_uid o --como-napoli")
        return 1

    # Stampa info target
    print(f"TARGET: {target_label}")
    print(f"Esito reale: {target_real}")
    print(f"Lega: {target_lega} | Blocco stagione: {target_ext['blocco_stagione']}")
    print(f"Fascia classifica casa: {target_ext['fascia_classifica_casa']} | ospite: {target_ext['fascia_classifica_ospite']}")
    print(f"Diff reti: casa={target_ext['differenza_reti_casa']} ospite={target_ext['differenza_reti_ospite']}")
    if target_ext.get("prob_implicita_1"):
        print(f"Quote: 1={1/target_ext['prob_implicita_1']:.2f} X={1/target_ext['prob_implicita_X']:.2f} 2={1/target_ext['prob_implicita_2']:.2f}")
    print(f"Elo: casa={target_ext['elo_casa']:.0f} ospite={target_ext['elo_ospite']:.0f} diff={target_ext.get('differenza_elo', 0):.0f}")

    # Calcola pool
    print(f"\n[pool] calcolo punteggi pesati su {len(dataset)} partite...")
    pool_info = compute_pool(target_ext, dataset, exclude_uid=exclude_uid)

    print_pool_summary(pool_info, target_label)

    if pool_info["n"] < MIN_PARTITE_PER_PRONOSTICO:
        print("\nPronostico NON emesso. Termino.")
        return 0

    # Calcola e stampa mercati
    mkt = compute_markets_for_pool(pool_info["partite"])
    print_mercati(mkt)

    # RE top 5
    re_top = compute_re_top5(pool_info["partite"], max_results=5)
    print_re_top5(re_top)

    # Top partite del pool
    print_top_partite(pool_info, n=args.top_n)

    # Frequenza compatibilita per feature (quali parametri "tirano" il match)
    print(f"\n## Frequenza compatibilita per feature (su {pool_info['n']} partite del pool)")
    print(f"{'Feature':<40} {'Peso':>5} {'N compat':>10} {'%':>6}")
    print("-" * 65)
    freq = compute_feature_frequency(target_ext, pool_info["partite"])
    for f in sorted(FEATURE_WEIGHTS.keys(), key=lambda x: -freq.get(x, 0)):
        w = FEATURE_WEIGHTS[f]
        n = freq.get(f, 0)
        pct = n / pool_info["n"] * 100 if pool_info["n"] > 0 else 0
        print(f"{f:<40} {w:>5} {n:>10} {pct:>5.0f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
