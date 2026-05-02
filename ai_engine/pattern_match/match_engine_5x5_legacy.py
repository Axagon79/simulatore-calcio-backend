"""
[ARCHIVIATO 2026-05-03] Engine v1 con matrice 5x5 — NON USARE.

Sostituito dal nuovo engine pesato in match_engine.py (validazione su 200 partite
ha confermato il pesato come piu affidabile). Mantenuto qui solo per riferimento
storico.

--- Documentazione originale ---

Pattern Match Engine — algoritmo matching 5x5.

Per una partita target (vettore feature 23-dim), calcola:
- Matrice 5x5 globale (su tutte le 10 leghe storiche)
- Matrice 5x5 intra-lega (solo stessa lega del target)

5 livelli tolleranza (T1 strettissima, T5 larghissima) x 5 fasce compatibilita
(23/23, 20-22, 16-19, 12-15, 8-11). Ogni cella: numerosita + distribuzione esiti.

Vedi History_System_Engine.md sezione 5 per design.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.config import MONGO_COLLECTION_MATCHES, LEAGUES
from config import db


# ====================================================================
# Tolleranze per livello T1..T5 (sez. 5.2 design)
# ====================================================================

# Per ogni feature, 5 valori di tolleranza assoluta (T1 stretta -> T5 larga).
# T1=0 = match esatto.
TOLERANCES = {
    "giornata":                                 [0, 1, 2, 4, 6],
    "posizione_classifica_casa":                [0, 1, 2, 4, 6],
    "posizione_classifica_ospite":              [0, 1, 2, 4, 6],
    "punti_casa":                               [0, 2, 4, 7, 12],
    "punti_ospite":                             [0, 2, 4, 7, 12],
    "differenza_punti":                         [0, 2, 5, 10, 15],
    "partite_giocate_casa":                     [0, 1, 2, 4, 6],
    "partite_giocate_ospite":                   [0, 1, 2, 4, 6],
    "gol_fatti_casa":                           [0, 3, 6, 10, 15],
    "gol_subiti_casa":                          [0, 3, 6, 10, 15],
    "gol_fatti_ospite":                         [0, 3, 6, 10, 15],
    "gol_subiti_ospite":                        [0, 3, 6, 10, 15],
    "posizione_classifica_casa_solo_casalinga": [0, 1, 2, 4, 6],
    "punti_casa_solo_casalinga":                [0, 1, 3, 6, 10],
    "posizione_classifica_ospite_solo_trasferta": [0, 1, 2, 4, 6],
    "punti_ospite_solo_trasferta":              [0, 1, 3, 6, 10],
    # Per prob_implicite la tolleranza e' in punti percentuali (0.015 = 1.5pp)
    "prob_implicita_1":                         [0.0, 0.015, 0.04, 0.08, 0.15],
    "prob_implicita_X":                         [0.0, 0.015, 0.04, 0.08, 0.15],
    "prob_implicita_2":                         [0.0, 0.015, 0.04, 0.08, 0.15],
    "elo_casa":                                 [0, 15, 35, 75, 150],
    "elo_ospite":                               [0, 15, 35, 75, 150],
    "elo_diff":                                 [0, 20, 50, 100, 200],
}

NUMERIC_FEATURES = list(TOLERANCES.keys())  # 22 feature numeriche
TOTAL_FEATURES = 23  # +lega categorica = 23

# Fasce compatibilita (sez. 5.5 design)
COMPATIBILITY_BANDS = [
    ("23/23",   23, 23),
    ("20-22",   20, 22),
    ("16-19",   16, 19),
    ("12-15",   12, 15),
    ("8-11",    8,  11),
]
# Sotto 8/23: non rilevante, scartiamo

# Tier leghe per gestione T4/T5 sulla feature lega categorica (sez. 5.3)
LEAGUE_TIERS = {
    "high":   {"E0", "SP1", "D1", "I1"},
    "medium": {"F1", "N1", "P1"},
    "base":   {"B1", "T1", "SC0"},
}

def get_league_tier(fd_code: str) -> str:
    for tier, codes in LEAGUE_TIERS.items():
        if fd_code in codes:
            return tier
    return "base"


def league_compatible(target_lega: str, hist_lega: str, tolerance_level: int) -> bool:
    """
    Sez. 5.3:
    T1, T2, T3 -> stessa lega esatta
    T4 -> stessa famiglia/tier
    T5 -> qualsiasi delle 10
    """
    if tolerance_level <= 2:  # T1, T2, T3 (indice 0,1,2)
        return target_lega == hist_lega
    if tolerance_level == 3:  # T4
        return get_league_tier(target_lega) == get_league_tier(hist_lega)
    return True  # T5


# ====================================================================
# Caricamento dataset
# ====================================================================

def load_dataset(intra_lega: Optional[str] = None) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """
    Carica tutte le partite da Mongo in array numpy per matching veloce.

    Returns:
        features: ndarray shape (N, 22) — feature numeriche
        outcomes: ndarray shape (N,) — esiti H/D/A
        metadata: list[dict] — info per top-K (lega, data, home, away, ft_score, goals_home, goals_away)
    """
    coll = db[MONGO_COLLECTION_MATCHES]
    query = {}
    if intra_lega:
        query["lega"] = intra_lega

    rows = []
    outcomes = []
    metadata = []
    cursor = coll.find(query, {
        "match_uid": 1, "lega": 1, "data_partita": 1,
        "home_team": 1, "away_team": 1,
        "feature_vector": 1, "outcome": 1,
    })
    for doc in cursor:
        fv = doc["feature_vector"]
        # Skip se manca Elo (3 squadre senza Elo, ~160 partite)
        if fv.get("elo_casa") is None or fv.get("elo_ospite") is None:
            continue
        row = []
        skip = False
        for feat in NUMERIC_FEATURES:
            v = fv.get(feat)
            if v is None:
                skip = True
                break
            row.append(float(v))
        if skip:
            continue
        rows.append(row)
        outcomes.append(doc["outcome"]["result_1x2"])
        metadata.append({
            "match_uid": doc["match_uid"],
            "lega": doc["lega"],
            "data": doc["data_partita"],
            "home": doc["home_team"],
            "away": doc["away_team"],
            "ft_score": doc["outcome"]["ft_score"],
            "result": doc["outcome"]["result_1x2"],
            "goals_home": doc["outcome"]["goals_home"],
            "goals_away": doc["outcome"]["goals_away"],
        })
    return np.array(rows, dtype=np.float64), np.array(outcomes), metadata


# ====================================================================
# Mercati estesi: DC, Over/Under, GG/NG, MG, Medie
# ====================================================================

def compute_extended_outcomes(indices: np.ndarray, metadata_db: list[dict]) -> dict:
    """
    Calcola tutti i mercati estesi su un cluster di partite (cella matrice).
    Tutti i campi a precisione float piena, niente arrotondamenti interni.
    """
    n = len(indices)
    if n == 0:
        return {
            "doppia_chance": None,
            "over_under_1_5": None,
            "over_under_2_5": None,
            "over_under_3_5": None,
            "goal_nogoal": None,
            "multigol": None,
            "medie": None,
        }

    cluster = [metadata_db[i] for i in indices]
    n_float = float(n)

    # SEGNO 1X2 contati per DC
    n_h = sum(1 for m in cluster if m["result"] == "H")
    n_d = sum(1 for m in cluster if m["result"] == "D")
    n_a = sum(1 for m in cluster if m["result"] == "A")

    # Totale gol per partita
    totals = [m["goals_home"] + m["goals_away"] for m in cluster]
    homes = [m["goals_home"] for m in cluster]
    aways = [m["goals_away"] for m in cluster]

    # Goal/NoGoal
    n_goal = sum(1 for m in cluster if m["goals_home"] >= 1 and m["goals_away"] >= 1)
    n_nogoal = n - n_goal

    return {
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
            "nogoal": n_nogoal / n_float,
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
            "avg_goals_home":  sum(homes) / n_float,
            "avg_goals_away":  sum(aways) / n_float,
            "avg_total_goals": sum(totals) / n_float,
        },
    }


# ====================================================================
# Risultato Esatto gerarchico
# ====================================================================

# Ordine di visita celle dalla piu stretta alla piu larga.
# Letto come: prima esauriamo T1 in tutte le bande, poi T2, ...
CELL_VISIT_ORDER = [
    (t_label, band_label)
    for t_label in ["T1", "T2", "T3", "T4", "T5"]
    for band_label, _, _ in COMPATIBILITY_BANDS
]


def _euclidean_norm_distance(target_vec: np.ndarray,
                             candidate_vec: np.ndarray) -> float:
    """
    Distanza euclidea normalizzata per scaler T5 (range tipico per feature).
    Piu piccola = piu somigliante.
    """
    scalers = np.array([TOLERANCES[f][4] for f in NUMERIC_FEATURES], dtype=np.float64)
    # Evita divisione per zero (elo_diff t5=200, sicuro non zero, ma per sicurezza)
    scalers = np.where(scalers == 0, 1.0, scalers)
    diff = (target_vec - candidate_vec) / scalers
    return float(np.sqrt(np.sum(diff ** 2)))


def compute_risultato_esatto_single_cell(target_vec: np.ndarray,
                                          cell_indices: list[int],
                                          metadata_db: list[dict],
                                          features_db: np.ndarray,
                                          max_results: int = 5) -> list[dict]:
    """
    Metodo alternativo (NON gerarchico): top-N RE da una singola cella,
    ordinati per similitudine al target.

    Per debugging/confronto con il metodo gerarchico.
    """
    if not cell_indices:
        return []

    # Calcola distanza target per ogni partita della cella
    distances = [(idx, _euclidean_norm_distance(target_vec, features_db[idx]))
                 for idx in cell_indices]
    # Ordina per distanza crescente (piu simile prima)
    distances.sort(key=lambda x: x[1])

    seen_scores: set[str] = set()
    results: list[dict] = []
    for idx, dist in distances:
        md = metadata_db[idx]
        score = md["ft_score"]
        if score in seen_scores:
            continue
        results.append({
            "score": score,
            "match_uid": md["match_uid"],
            "distance": dist,
            "home": md["home"],
            "away": md["away"],
            "data": md["data"].strftime("%Y-%m-%d"),
        })
        seen_scores.add(score)
        if len(results) >= max_results:
            break
    return results


def compute_risultato_esatto_hierarchical(target_vec: np.ndarray,
                                           cells_data: list[dict],
                                           metadata_db: list[dict],
                                           features_db: np.ndarray,
                                           max_results: int = 5) -> list[dict]:
    """
    Calcola top-N risultati esatti unici scendendo gerarchicamente le 25 celle.

    Per ogni cella visitata in ordine T1 23/23 -> ... -> T5 8-11:
    1. Conto frequenza di ogni risultato esatto (ft_score) nelle partite della cella
    2. Tie-break per frequenza uguale: vince la partita piu simile al target
    3. Aggiungo i ft_score non gia visti nella lista finale
    4. match_uid rappresentativo: la partita piu simile tra quelle con quel ft_score
    5. Stop quando ho `max_results` risultati unici

    Returns:
        list[dict] con campi {score, match_uid, from_cell}
    """
    seen_scores: set[str] = set()
    results: list[dict] = []

    # Mappa rapida (level, band) -> cell
    cell_by_key = {(c["tolerance_level"], c["compatibility_band"]): c
                   for c in cells_data}

    for level, band in CELL_VISIT_ORDER:
        if len(results) >= max_results:
            break
        cell = cell_by_key.get((level, band))
        if not cell or cell["n_matches"] == 0:
            continue
        # Indici delle partite della cella (li ho passati come metadata interno)
        cell_indices = cell.get("_indices")
        if cell_indices is None or len(cell_indices) == 0:
            continue

        # Raggruppa per ft_score, tieni indici di tutte le partite per ogni score
        score_to_indices: dict[str, list[int]] = {}
        for idx in cell_indices:
            score = metadata_db[int(idx)]["ft_score"]
            score_to_indices.setdefault(score, []).append(int(idx))

        # Per ogni score, calcola distanza minima al target tra le sue partite
        # e tieni anche la frequenza (numero partite con quel score).
        # Ordine in cella:
        #   1. Frequenza decrescente
        #   2. Tie-break: distanza minima crescente
        score_stats = []
        for score, idxs in score_to_indices.items():
            distances = [_euclidean_norm_distance(target_vec, features_db[i])
                         for i in idxs]
            min_dist = min(distances)
            best_idx = idxs[distances.index(min_dist)]
            score_stats.append({
                "score": score,
                "frequency": len(idxs),
                "min_distance": min_dist,
                "best_match_idx": best_idx,
            })
        score_stats.sort(key=lambda s: (-s["frequency"], s["min_distance"]))

        # Aggiungi alla lista finale i score non gia visti
        for s in score_stats:
            if s["score"] in seen_scores:
                continue
            best_idx = s["best_match_idx"]
            md = metadata_db[best_idx]
            results.append({
                "score": s["score"],
                "match_uid": md["match_uid"],
                "from_cell": f"{level} {band}",
                "frequency_in_cell": s["frequency"],
                "n_in_cell": cell["n_matches"],
            })
            seen_scores.add(s["score"])
            if len(results) >= max_results:
                break

    return results


# ====================================================================
# Algoritmo matching 5x5
# ====================================================================

def compute_matrix(target_features: dict, target_lega: str,
                   features_db: np.ndarray, outcomes_db: np.ndarray,
                   metadata_db: list[dict],
                   intra_lega_only: bool = False, top_k: int = 5,
                   tolerances_override: dict | None = None) -> dict:
    """
    Calcola la matrice 5x5 per la partita target.

    Returns dict:
    {
      "cells": [
        {
          "tolerance_level": "T1"..."T5",
          "compatibility_band": "23/23"...,
          "n_matches": int,
          "outcome_distribution": {"H": float, "D": float, "A": float} | None,
          "top_matches": [ ... ]
        }, ...
      ]
    }
    """
    n_db = len(features_db)
    if n_db == 0:
        return {"cells": [], "error": "dataset vuoto"}

    # Vettore feature target come array
    target_vec = np.array([float(target_features[f]) for f in NUMERIC_FEATURES], dtype=np.float64)

    # Compatibilita lega per ogni partita storica (vettore boolean per livello T)
    leghe_db = np.array([m["lega"] for m in metadata_db])

    # Diff assolute per ogni feature: shape (N, 22)
    diffs = np.abs(features_db - target_vec[np.newaxis, :])

    tolerances = tolerances_override if tolerances_override is not None else TOLERANCES

    cells = []
    for t_idx, t_label in enumerate(["T1", "T2", "T3", "T4", "T5"]):
        # Per ogni feature, soglia tolleranza al livello t_idx
        tol_vec = np.array([tolerances[f][t_idx] for f in NUMERIC_FEATURES])
        # compatible[i, j] = True se partita i ha feature j compatibile a livello t
        compat = diffs <= tol_vec[np.newaxis, :]
        # Numero feature numeriche compatibili per partita: shape (N,)
        n_compat = compat.sum(axis=1)
        # Lega: aggiungi +1 se compatibile a questo livello
        lega_compat_mask = np.array([
            league_compatible(target_lega, hl, t_idx) for hl in leghe_db
        ])
        n_total_compat = n_compat + lega_compat_mask.astype(int)

        # Distribuisci nelle 5 fasce
        for band_label, band_min, band_max in COMPATIBILITY_BANDS:
            band_mask = (n_total_compat >= band_min) & (n_total_compat <= band_max)
            indices = np.where(band_mask)[0]

            cell = {
                "tolerance_level": t_label,
                "compatibility_band": band_label,
                "n_matches": int(len(indices)),
                "outcome_distribution": None,
                "top_matches": [],
                # Indici interni per RE gerarchico (rimossi prima del return)
                "_indices": indices.tolist() if len(indices) > 0 else [],
            }

            if len(indices) > 0:
                outs = outcomes_db[indices]
                counter = Counter(outs)
                total = len(indices)
                cell["outcome_distribution"] = {
                    "1": counter.get("H", 0) / total,
                    "X": counter.get("D", 0) / total,
                    "2": counter.get("A", 0) / total,
                }
                # Top-K: partite con piu feature compatibili nella fascia
                indices_sorted = indices[np.argsort(-n_total_compat[indices])][:top_k]
                cell["top_matches"] = [
                    {
                        "match_uid": metadata_db[i]["match_uid"],
                        "lega": metadata_db[i]["lega"],
                        "data": metadata_db[i]["data"].strftime("%Y-%m-%d"),
                        "home": metadata_db[i]["home"],
                        "away": metadata_db[i]["away"],
                        "ft_score": metadata_db[i]["ft_score"],
                        "n_compat": int(n_total_compat[i]),
                    }
                    for i in indices_sorted
                ]

                # Mercati estesi per la cella
                ext = compute_extended_outcomes(indices, metadata_db)
                cell.update(ext)
            else:
                # Cella vuota: tutti i mercati estesi a None
                cell.update({
                    "doppia_chance": None,
                    "over_under_1_5": None,
                    "over_under_2_5": None,
                    "over_under_3_5": None,
                    "goal_nogoal": None,
                    "multigol": None,
                    "medie": None,
                })

            cells.append(cell)

    # Calcolo RE gerarchico a livello matrice (1 lista per matrice)
    risultato_esatto_top5 = compute_risultato_esatto_hierarchical(
        target_vec, cells, metadata_db, features_db, max_results=5
    )

    # Pulizia: rimuovi indici interni prima del return
    for c in cells:
        c.pop("_indices", None)

    return {
        "cells": cells,
        "risultato_esatto_top5": risultato_esatto_top5,
    }


# ====================================================================
# Render output
# ====================================================================

def print_matrix(matrix: dict, title: str):
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")
    if not matrix.get("cells"):
        print("Nessun dato.")
        return

    # Tabella: righe = tolerance T1..T5, colonne = bande
    bands = [b[0] for b in COMPATIBILITY_BANDS]
    levels = ["T1", "T2", "T3", "T4", "T5"]

    # Header
    header = f"{'':5s}" + " | ".join(f"{b:^15s}" for b in bands)
    print(header)
    print("-" * len(header))
    for lvl in levels:
        row_cells = [c for c in matrix["cells"] if c["tolerance_level"] == lvl]
        cells_by_band = {c["compatibility_band"]: c for c in row_cells}
        line = f"{lvl:5s}"
        for band in bands:
            c = cells_by_band.get(band)
            n = c["n_matches"] if c else 0
            if n == 0 or not c.get("outcome_distribution"):
                cell_str = f"{n:>3d}            "
            else:
                d = c["outcome_distribution"]
                # Mostra n + esito dominante
                dom = max(d, key=d.get)
                pct = d[dom] * 100
                cell_str = f"{n:>3d} {dom}{pct:5.1f}%   "
            line += " | " + cell_str[:15].ljust(15)
        print(line)


def print_top_matches(matrix: dict, level: str, band: str, k: int = 5):
    cell = next((c for c in matrix["cells"]
                 if c["tolerance_level"] == level and c["compatibility_band"] == band), None)
    if not cell or not cell["top_matches"]:
        print(f"\n[Top match {level} {band}]: nessuno")
        return
    print(f"\n[Top {k} match {level} {band}] — {cell['n_matches']} totali, dist {cell['outcome_distribution']}")
    for m in cell["top_matches"][:k]:
        print(f"  {m['data']}  [{m['lega']}]  {m['home']:25s} {m['ft_score']:6s}  {m['away']:25s}  (compat={m['n_compat']}/23)")


# ====================================================================
# Main CLI
# ====================================================================

def get_target_match(match_uid: str) -> Optional[dict]:
    """Carica una partita storica dal DB per usarla come target."""
    coll = db[MONGO_COLLECTION_MATCHES]
    return coll.find_one({"match_uid": match_uid})


def main():
    parser = argparse.ArgumentParser(description="Pattern Match Engine — matrix 5x5")
    parser.add_argument("--match_uid", help="match_uid di una partita storica da usare come target")
    parser.add_argument("--leicester-test", action="store_true",
                        help="Test: usa Leicester-Man City 2015-12-29")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    if args.leicester_test:
        match_uid = "E0_2015-16_2015-12-29_Leicester_ManCity"
    else:
        match_uid = args.match_uid

    if not match_uid:
        print("Specificare --match_uid o --leicester-test")
        return 1

    target_doc = get_target_match(match_uid)
    if not target_doc:
        print(f"Match non trovato: {match_uid}")
        return 1

    target_features = target_doc["feature_vector"]
    target_lega = target_doc["lega"]

    print(f"TARGET: {match_uid}")
    print(f"  {target_doc['home_team']} vs {target_doc['away_team']}  ({target_doc['data_partita'].strftime('%Y-%m-%d')})")
    print(f"  Esito reale: {target_doc['outcome']['ft_score']} (FTR={target_doc['outcome']['result_1x2']})")
    print(f"  Lega: {target_lega} | Giornata: {target_features['giornata']}")
    print(f"  Pos casa: {target_features['posizione_classifica_casa']}, ospite: {target_features['posizione_classifica_ospite']}")
    print(f"  Quote: 1={1/target_features['prob_implicita_1']:.2f}  X={1/target_features['prob_implicita_X']:.2f}  2={1/target_features['prob_implicita_2']:.2f}")
    print(f"  Elo: casa={target_features['elo_casa']:.0f}, ospite={target_features['elo_ospite']:.0f}, diff={target_features['elo_diff']:.0f}")

    # Carica dataset (escludendo la partita target stessa)
    print("\n[load] caricamento dataset 32k partite...")
    features_db, outcomes_db, metadata_db = load_dataset()
    # Esclusione self
    self_mask = np.array([m["match_uid"] != match_uid for m in metadata_db])
    features_db = features_db[self_mask]
    outcomes_db = outcomes_db[self_mask]
    metadata_db = [m for m, k in zip(metadata_db, self_mask) if k]
    print(f"[load] {len(metadata_db)} partite caricate (escludendo target self)")

    # Matrice globale
    matrix_global = compute_matrix(target_features, target_lega,
                                   features_db, outcomes_db, metadata_db,
                                   intra_lega_only=False, top_k=args.top_k)
    print_matrix(matrix_global, "MATRICE GLOBALE (10 leghe)")

    # Matrice intra-lega
    intra_mask = np.array([m["lega"] == target_lega for m in metadata_db])
    matrix_intra = compute_matrix(target_features, target_lega,
                                  features_db[intra_mask], outcomes_db[intra_mask],
                                  [m for m, k in zip(metadata_db, intra_mask) if k],
                                  intra_lega_only=True, top_k=args.top_k)
    print_matrix(matrix_intra, f"MATRICE INTRA-LEGA ({target_lega})")

    # Top match per le celle piu interessanti
    print("\n" + "=" * 80)
    print("TOP MATCHES (celle stringate)")
    print("=" * 80)
    for level in ["T1", "T2", "T3"]:
        for band in ["23/23", "20-22", "16-19"]:
            print_top_matches(matrix_global, level, band, k=args.top_k)

    return 0


if __name__ == "__main__":
    sys.exit(main())
