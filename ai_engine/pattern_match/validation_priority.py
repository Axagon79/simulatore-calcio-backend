"""
Validation comparativa: 3 ordini di selezione cella (PROFONDITA' vs AMPIEZZA vs MISTA).

Stesse 50 partite, stesse tolleranze BASE, cambia solo l'ordine di scorrimento
delle 25 celle per scegliere "la prima non vuota con >= N_MIN partite".

Strategie:
- PROFONDITA' (attuale): T1 23/23 -> T1 20-22 -> ... -> T5 8-11 (T-first)
- AMPIEZZA: 23/23 T1 -> 23/23 T2 -> ... -> 8-11 T5 (banda-first)
- MISTA: ordinata per score = peso_T x peso_banda

Output: validation_priority_comparison.md

Uso:
    python -m ai_engine.pattern_match.validation_priority
"""
from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.match_engine import (
    compute_matrix, load_dataset, COMPATIBILITY_BANDS,
)
from ai_engine.pattern_match.config import MONGO_COLLECTION_MATCHES
from config import db


OUTPUT_MD = Path(__file__).parent / "validation_priority_comparison.md"
RANDOM_SEED = 42
N_MIN = 5  # soglia minima partite per accettare una cella

LEVELS = ["T1", "T2", "T3", "T4", "T5"]
BANDS = [b[0] for b in COMPATIBILITY_BANDS]  # 23/23, 20-22, 16-19, 12-15, 8-11

# Pesi per strategia MISTA
T_WEIGHTS = {"T1": 1.0, "T2": 0.8, "T3": 0.6, "T4": 0.4, "T5": 0.2}
BAND_WEIGHTS = {"23/23": 1.0, "20-22": 0.85, "16-19": 0.7, "12-15": 0.55, "8-11": 0.4}


def order_profondita() -> list[tuple[str, str]]:
    """T1 23/23 -> T1 20-22 -> ... -> T5 8-11"""
    return [(lvl, band) for lvl in LEVELS for band in BANDS]


def order_ampiezza() -> list[tuple[str, str]]:
    """23/23 T1 -> 23/23 T2 -> ... -> 8-11 T5"""
    return [(lvl, band) for band in BANDS for lvl in LEVELS]


def order_mista() -> list[tuple[str, str]]:
    """Score decrescente = T_WEIGHTS x BAND_WEIGHTS"""
    pairs = [(lvl, band, T_WEIGHTS[lvl] * BAND_WEIGHTS[band])
             for lvl in LEVELS for band in BANDS]
    pairs.sort(key=lambda x: -x[2])
    return [(lvl, band) for lvl, band, _ in pairs]


ORDERS = {
    "PROFONDITA": order_profondita(),
    "AMPIEZZA":   order_ampiezza(),
    "MISTA":      order_mista(),
}


def pick_test_matches(n_serie_a: int = 25, n_other: int = 25,
                      season: str = "2024-25") -> list[dict]:
    coll = db[MONGO_COLLECTION_MATCHES]
    rng = random.Random(RANDOM_SEED)
    serie_a = list(coll.find({"lega": "I1", "stagione": season}))
    others = list(coll.find({"lega": {"$ne": "I1"}, "stagione": season}))
    return rng.sample(serie_a, n_serie_a) + rng.sample(others, n_other)


def real_dc(real_1x2: str) -> set[str]:
    if real_1x2 == "H": return {"1X", "12"}
    if real_1x2 == "D": return {"1X", "X2"}
    if real_1x2 == "A": return {"X2", "12"}
    return set()


def real_mg(total: int) -> set[str]:
    out = set()
    if 1 <= total <= 2: out.add("1_2")
    if 2 <= total <= 3: out.add("2_3")
    if 1 <= total <= 3: out.add("1_3")
    if 2 <= total <= 4: out.add("2_4")
    if 3 <= total <= 5: out.add("3_5")
    if 4 <= total <= 6: out.add("4_6")
    return out


def find_first_cell(matrix: dict, order: list[tuple[str, str]], n_min: int) -> dict | None:
    """Prima cella nell'ordine specificato con >= n_min partite."""
    cells_by_key = {(c["tolerance_level"], c["compatibility_band"]): c
                    for c in matrix["cells"]}
    for lvl, band in order:
        c = cells_by_key.get((lvl, band))
        if c and c["n_matches"] >= n_min:
            return c
    return None


def extract_1x2(c):
    d = c["outcome_distribution"]
    sign = max(d, key=d.get)
    return {"1": "H", "X": "D", "2": "A"}[sign]


def extract_dc(c):
    return max(c["doppia_chance"], key=c["doppia_chance"].get) if c.get("doppia_chance") else None


def extract_ou25(c):
    d = c.get("over_under_2_5")
    return max(d, key=d.get) if d else None


def extract_gg(c):
    return max(c["goal_nogoal"], key=c["goal_nogoal"].get) if c.get("goal_nogoal") else None


def extract_mg(c):
    return max(c["multigol"], key=c["multigol"].get) if c.get("multigol") else None


def main():
    print("[load] caricamento dataset...")
    features_db, outcomes_db, metadata_db = load_dataset()
    print(f"[load] {len(metadata_db)} partite\n")

    test_matches = pick_test_matches()
    print(f"[pick] {len(test_matches)} partite test\n")

    md = ["# Confronto ordine selezione cella — PROFONDITA' vs AMPIEZZA vs MISTA\n"]
    md.append(f"**Soglia minima partite per accettare cella**: {N_MIN}\n")
    md.append(f"**Test set**: 25 Serie A + 25 altre leghe, stagione 2024-25, seed={RANDOM_SEED}\n")
    md.append("\n## Strategie testate\n")
    md.append("- **PROFONDITA**: T-first (T1 23/23 -> T1 20-22 -> ... -> T5 8-11) — dà priorità alla strettezza tolleranza")
    md.append("- **AMPIEZZA**: banda-first (23/23 T1 -> 23/23 T2 -> ... -> 8-11 T5) — dà priorità al numero di feature compatibili")
    md.append("- **MISTA**: score combinato (peso T x peso banda) — bilanciamento\n")
    md.append("\n### Pesi MISTA\n")
    md.append("- T1=1.0, T2=0.8, T3=0.6, T4=0.4, T5=0.2")
    md.append("- 23/23=1.0, 20-22=0.85, 16-19=0.7, 12-15=0.55, 8-11=0.4")
    md.append("- Top score: T1 23/23 (1.0) > T1 20-22 (0.85) > T2 23/23 (0.8) > ...\n")
    md.append("---\n")

    # Stats per ogni strategia
    all_stats = {}
    for strategy_name in ORDERS:
        all_stats[strategy_name] = {
            "stats": Counter(),
            "cell_dist_global": Counter(),
            "cell_dist_intra": Counter(),
        }

    print("[compute] running 50 partite x 3 strategie...")
    for target_doc in tqdm(test_matches, desc="validation"):
        match_uid = target_doc["match_uid"]
        target_features = target_doc["feature_vector"]
        target_lega = target_doc["lega"]
        real_outcome = target_doc["outcome"]
        real_1x2 = real_outcome["result_1x2"]
        real_total = real_outcome["goals_home"] + real_outcome["goals_away"]
        real_ou25 = "over" if real_total >= 3 else "under"
        real_gg = "goal" if (real_outcome["goals_home"] >= 1 and real_outcome["goals_away"] >= 1) else "nogoal"
        real_score = real_outcome["ft_score"]
        real_mg_set = real_mg(real_total)
        real_dc_set = real_dc(real_1x2)

        self_mask = np.array([m["match_uid"] != match_uid for m in metadata_db])
        feat_local = features_db[self_mask]
        out_local = outcomes_db[self_mask]
        meta_local = [m for m, k in zip(metadata_db, self_mask) if k]

        matrix_global = compute_matrix(target_features, target_lega,
                                       feat_local, out_local, meta_local,
                                       intra_lega_only=False, top_k=3)
        intra_mask = np.array([m["lega"] == target_lega for m in meta_local])
        matrix_intra = compute_matrix(target_features, target_lega,
                                      feat_local[intra_mask], out_local[intra_mask],
                                      [m for m, k in zip(meta_local, intra_mask) if k],
                                      intra_lega_only=True, top_k=3)

        for strategy_name, order in ORDERS.items():
            for vista, matrix in [("global", matrix_global), ("intra", matrix_intra)]:
                cell = find_first_cell(matrix, order, N_MIN)
                if cell:
                    cell_label = f"{cell['tolerance_level']} {cell['compatibility_band']}"
                    all_stats[strategy_name][f"cell_dist_{vista}"][cell_label] += 1

                    # 1X2
                    p = extract_1x2(cell)
                    all_stats[strategy_name]["stats"][f"1x2_{vista}_total"] += 1
                    if p == real_1x2:
                        all_stats[strategy_name]["stats"][f"1x2_{vista}_correct"] += 1

                    # DC
                    p = extract_dc(cell)
                    if p is not None:
                        all_stats[strategy_name]["stats"][f"dc_{vista}_total"] += 1
                        if p in real_dc_set:
                            all_stats[strategy_name]["stats"][f"dc_{vista}_correct"] += 1

                    # O/U 2.5
                    p = extract_ou25(cell)
                    if p is not None:
                        all_stats[strategy_name]["stats"][f"ou25_{vista}_total"] += 1
                        if p == real_ou25:
                            all_stats[strategy_name]["stats"][f"ou25_{vista}_correct"] += 1

                    # GG/NG
                    p = extract_gg(cell)
                    if p is not None:
                        all_stats[strategy_name]["stats"][f"gg_{vista}_total"] += 1
                        if p == real_gg:
                            all_stats[strategy_name]["stats"][f"gg_{vista}_correct"] += 1

                    # MG
                    p = extract_mg(cell)
                    if p is not None:
                        all_stats[strategy_name]["stats"][f"mg_{vista}_total"] += 1
                        if p in real_mg_set:
                            all_stats[strategy_name]["stats"][f"mg_{vista}_correct"] += 1

    # =================================================================
    # Tabella confronto
    # =================================================================
    md.append("\n## Hit rate per mercato — confronto strategie\n")
    markets = [("1X2", "1x2"), ("DC", "dc"), ("O/U 2.5", "ou25"),
               ("GG/NG", "gg"), ("MG", "mg")]

    md.append("\n### GLOBALE\n")
    md.append("| Mercato | PROFONDITA | AMPIEZZA | MISTA |")
    md.append("|---|---|---|---|")
    for label, key in markets:
        row = [label]
        for strat in ["PROFONDITA", "AMPIEZZA", "MISTA"]:
            s = all_stats[strat]["stats"]
            tot = s.get(f"{key}_global_total", 0)
            ok = s.get(f"{key}_global_correct", 0)
            rate = ok / tot * 100 if tot else 0
            row.append(f"{ok}/{tot} = **{rate:.1f}%**")
        md.append("| " + " | ".join(row) + " |")

    md.append("\n### INTRA-LEGA\n")
    md.append("| Mercato | PROFONDITA | AMPIEZZA | MISTA |")
    md.append("|---|---|---|---|")
    for label, key in markets:
        row = [label]
        for strat in ["PROFONDITA", "AMPIEZZA", "MISTA"]:
            s = all_stats[strat]["stats"]
            tot = s.get(f"{key}_intra_total", 0)
            ok = s.get(f"{key}_intra_correct", 0)
            rate = ok / tot * 100 if tot else 0
            row.append(f"{ok}/{tot} = **{rate:.1f}%**")
        md.append("| " + " | ".join(row) + " |")

    # Distribuzione celle sorgente
    md.append("\n## Distribuzione celle sorgente\n")
    md.append("Quale cella ha 'vinto' come prima qualificata (>= 5 partite) per ogni strategia.\n")

    for vista_label in ["global", "intra"]:
        md.append(f"\n### Vista {vista_label.upper()}\n")
        md.append("| Cella | PROFONDITA | AMPIEZZA | MISTA |")
        md.append("|---|---|---|---|")
        all_cells = set()
        for strat in ORDERS:
            all_cells.update(all_stats[strat][f"cell_dist_{vista_label}"].keys())
        # Ordina come la matrice 5x5
        ordered = [f"{l} {b}" for l in LEVELS for b in BANDS if f"{l} {b}" in all_cells]
        for cell in ordered:
            row = [cell]
            for strat in ["PROFONDITA", "AMPIEZZA", "MISTA"]:
                row.append(str(all_stats[strat][f"cell_dist_{vista_label}"].get(cell, 0)))
            md.append("| " + " | ".join(row) + " |")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[done] output: {OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
