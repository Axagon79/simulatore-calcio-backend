"""
Validation comparativa: BASE vs WIDE_A vs WIDE_B (allargamento maglie T1-T3).

Esegue le stesse 50 partite test su 3 set di tolleranze diversi e confronta:
- Hit rate per mercato (1X2, DC, O/U, GG/NG, MG, RE)
- Distribuzione celle sorgente (cella per cella vs gerarchico)

Output: validation_comparison_widening.md

Uso:
    python -m ai_engine.pattern_match.validation_comparison
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
from ai_engine.pattern_match.tolerances_variants import VARIANTS
from config import db


OUTPUT_MD = Path(__file__).parent / "validation_comparison_widening.md"
RANDOM_SEED = 42
N_MIN_HIER = 10  # soglia gerarchico

LEVELS = ["T1", "T2", "T3", "T4", "T5"]
BANDS = [b[0] for b in COMPATIBILITY_BANDS]
CELL_VISIT_ORDER = [(lvl, band) for lvl in LEVELS for band in BANDS]


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


def real_mg(total_goals: int) -> set[str]:
    out = set()
    if 1 <= total_goals <= 2: out.add("1_2")
    if 2 <= total_goals <= 3: out.add("2_3")
    if 1 <= total_goals <= 3: out.add("1_3")
    if 2 <= total_goals <= 4: out.add("2_4")
    if 3 <= total_goals <= 5: out.add("3_5")
    if 4 <= total_goals <= 6: out.add("4_6")
    return out


def find_first_qualifying_cell(matrix: dict, n_min: int) -> dict | None:
    cells_by_key = {(c["tolerance_level"], c["compatibility_band"]): c
                    for c in matrix["cells"]}
    for lvl, band in CELL_VISIT_ORDER:
        c = cells_by_key.get((lvl, band))
        if c and c["n_matches"] >= n_min:
            return c
    return None


def best_cell_for_market(matrix: dict, market_extractor) -> tuple[str | None, dict | None]:
    """
    Per il metodo 'cella per cella': scorre tutte le celle non vuote,
    e ritorna la predizione della cella piu stretta non vuota.
    """
    cells_by_key = {(c["tolerance_level"], c["compatibility_band"]): c
                    for c in matrix["cells"]}
    for lvl, band in CELL_VISIT_ORDER:
        c = cells_by_key.get((lvl, band))
        if c and c["n_matches"] > 0:
            pred = market_extractor(c)
            if pred is not None:
                return pred, c
    return None, None


def extract_1x2(c):
    d = c["outcome_distribution"]
    sign = max(d, key=d.get)
    return {"1": "H", "X": "D", "2": "A"}[sign]


def extract_dc(c):
    return max(c["doppia_chance"], key=c["doppia_chance"].get) if c.get("doppia_chance") else None


def extract_ou(soglia):
    def _ext(c):
        d = c.get(f"over_under_{soglia}")
        return max(d, key=d.get) if d else None
    return _ext


def extract_gg(c):
    return max(c["goal_nogoal"], key=c["goal_nogoal"].get) if c.get("goal_nogoal") else None


def extract_mg(c):
    return max(c["multigol"], key=c["multigol"].get) if c.get("multigol") else None


def evaluate_partita(target_doc, features_db, outcomes_db, metadata_db,
                     tolerances: dict) -> dict:
    """
    Per una partita target + variante tolleranze, calcola hit per ogni mercato
    sia con metodo cella-per-cella sia con gerarchico.
    Ritorna dict di stats e dati su celle scelte.
    """
    match_uid = target_doc["match_uid"]
    target_features = target_doc["feature_vector"]
    target_lega = target_doc["lega"]
    real_outcome = target_doc["outcome"]
    real_1x2 = real_outcome["result_1x2"]
    real_total = real_outcome["goals_home"] + real_outcome["goals_away"]
    real_ou25 = "over" if real_total >= 3 else "under"
    real_ou15 = "over" if real_total >= 2 else "under"
    real_ou35 = "over" if real_total >= 4 else "under"
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
                                   intra_lega_only=False, top_k=3,
                                   tolerances_override=tolerances)
    intra_mask = np.array([m["lega"] == target_lega for m in meta_local])
    matrix_intra = compute_matrix(target_features, target_lega,
                                  feat_local[intra_mask], out_local[intra_mask],
                                  [m for m, k in zip(meta_local, intra_mask) if k],
                                  intra_lega_only=True, top_k=3,
                                  tolerances_override=tolerances)

    res = {}

    # --- METODO CELLA PER CELLA: prima cella non vuota in ordine T1->T5 ---
    for vista, matrix in [("global", matrix_global), ("intra", matrix_intra)]:
        # 1X2
        pred, cell = best_cell_for_market(matrix, extract_1x2)
        res[f"1x2_{vista}_cbc_hit"] = (pred == real_1x2) if pred else None
        res[f"1x2_{vista}_cbc_cell"] = f"{cell['tolerance_level']} {cell['compatibility_band']}" if cell else None

        # O/U 2.5
        pred, cell = best_cell_for_market(matrix, extract_ou("2_5"))
        res[f"ou25_{vista}_cbc_hit"] = (pred == real_ou25) if pred else None
        res[f"ou25_{vista}_cbc_cell"] = f"{cell['tolerance_level']} {cell['compatibility_band']}" if cell else None

        # GG/NG
        pred, cell = best_cell_for_market(matrix, extract_gg)
        res[f"gg_{vista}_cbc_hit"] = (pred == real_gg) if pred else None

        # MG
        pred, cell = best_cell_for_market(matrix, extract_mg)
        res[f"mg_{vista}_cbc_hit"] = (pred in real_mg_set) if pred else None

        # DC
        pred, cell = best_cell_for_market(matrix, extract_dc)
        res[f"dc_{vista}_cbc_hit"] = (pred in real_dc_set) if pred else None

    # --- METODO GERARCHICO: prima cella >= N_MIN_HIER ---
    for vista, matrix in [("global", matrix_global), ("intra", matrix_intra)]:
        cell = find_first_qualifying_cell(matrix, N_MIN_HIER)
        if cell:
            res[f"hier_{vista}_cell"] = f"{cell['tolerance_level']} {cell['compatibility_band']}"
            pred = extract_1x2(cell)
            res[f"1x2_{vista}_hier_hit"] = (pred == real_1x2)
            pred = extract_ou("2_5")(cell)
            res[f"ou25_{vista}_hier_hit"] = (pred == real_ou25)
            pred = extract_gg(cell)
            res[f"gg_{vista}_hier_hit"] = (pred == real_gg)
            pred = extract_mg(cell)
            res[f"mg_{vista}_hier_hit"] = (pred in real_mg_set) if pred else None
            pred = extract_dc(cell)
            res[f"dc_{vista}_hier_hit"] = (pred in real_dc_set) if pred else None
        else:
            res[f"hier_{vista}_cell"] = None
            for k in ["1x2", "ou25", "gg", "mg", "dc"]:
                res[f"{k}_{vista}_hier_hit"] = None

    # --- RE top5 (solo metodo gerarchico, gia integrato in matrix) ---
    for vista, matrix in [("global", matrix_global), ("intra", matrix_intra)]:
        re_scores = [r["score"] for r in matrix.get("risultato_esatto_top5", [])]
        res[f"re_{vista}_hit"] = real_score in re_scores

    return res


def main():
    print("[load] caricamento dataset 32k partite...")
    features_db, outcomes_db, metadata_db = load_dataset()
    print(f"[load] {len(metadata_db)} partite\n")

    print(f"[pick] selezione 50 partite test (seed={RANDOM_SEED})...")
    test_matches = pick_test_matches(n_serie_a=25, n_other=25, season="2024-25")

    md = ["# Confronto allargamento maglie — BASE vs WIDE_A vs WIDE_B\n"]
    md.append(f"**Test set**: 25 Serie A + 25 altre leghe, stagione 2024-25, seed={RANDOM_SEED}\n")
    md.append(f"**Soglia minima per gerarchico**: {N_MIN_HIER} partite\n")
    md.append("\n## Definizione varianti\n")
    md.append("- **BASE**: tolleranze attuali (T1=0 esatto, T2/T3 standard).")
    md.append("- **WIDE_A**: T1 invariato (T1=0), T2 e T3 allargate ~+15-20%.")
    md.append("- **WIDE_B**: T1 leggermente allargato (T1>0), T2 e T3 allargate ~+30-40%.\n")
    md.append("---\n")

    # Stats per ogni variante
    all_stats = {}

    for variant_name, tolerances in VARIANTS.items():
        print(f"\n[variant {variant_name}] inizio validation...")
        stats = Counter()
        cell_distribution_global_cbc = Counter()
        cell_distribution_intra_cbc = Counter()
        cell_distribution_global_hier = Counter()
        cell_distribution_intra_hier = Counter()

        for target_doc in tqdm(test_matches, desc=variant_name):
            r = evaluate_partita(target_doc, features_db, outcomes_db, metadata_db, tolerances)

            # Hit conteggio per ogni metrica
            for k, v in r.items():
                if k.endswith("_hit") and v is not None:
                    stats[f"{k}_total"] += 1
                    if v: stats[f"{k}_correct"] += 1
                elif k.endswith("_cell") and v:
                    if "1x2_global_cbc_cell" in k:
                        cell_distribution_global_cbc[v] += 1
                    elif "1x2_intra_cbc_cell" in k:
                        cell_distribution_intra_cbc[v] += 1
                    elif "hier_global_cell" in k:
                        cell_distribution_global_hier[v] += 1
                    elif "hier_intra_cell" in k:
                        cell_distribution_intra_hier[v] += 1

        all_stats[variant_name] = {
            "stats": stats,
            "cell_dist_global_cbc": cell_distribution_global_cbc,
            "cell_dist_intra_cbc": cell_distribution_intra_cbc,
            "cell_dist_global_hier": cell_distribution_global_hier,
            "cell_dist_intra_hier": cell_distribution_intra_hier,
        }

    # =================================================================
    # Tabella confronto
    # =================================================================
    md.append("\n## Hit rate — confronto 3 varianti\n")

    markets = [
        ("1X2", "1x2"),
        ("DC", "dc"),
        ("O/U 2.5", "ou25"),
        ("GG/NG", "gg"),
        ("MG", "mg"),
    ]

    md.append("\n### Metodo CELLA-PER-CELLA (prima cella non vuota)\n")
    md.append("| Mercato | Vista | BASE | WIDE_A | WIDE_B |")
    md.append("|---|---|---|---|---|")
    for label, key in markets:
        for vista in ["global", "intra"]:
            row = [label, vista]
            for v in ["BASE", "WIDE_A", "WIDE_B"]:
                s = all_stats[v]["stats"]
                tot = s.get(f"{key}_{vista}_cbc_hit_total", 0)
                ok = s.get(f"{key}_{vista}_cbc_hit_correct", 0)
                rate = ok / tot * 100 if tot else 0
                row.append(f"{ok}/{tot} = **{rate:.1f}%**")
            md.append("| " + " | ".join(row) + " |")

    md.append(f"\n### Metodo GERARCHICO (prima cella >= {N_MIN_HIER} partite)\n")
    md.append("| Mercato | Vista | BASE | WIDE_A | WIDE_B |")
    md.append("|---|---|---|---|---|")
    for label, key in markets:
        for vista in ["global", "intra"]:
            row = [label, vista]
            for v in ["BASE", "WIDE_A", "WIDE_B"]:
                s = all_stats[v]["stats"]
                tot = s.get(f"{key}_{vista}_hier_hit_total", 0)
                ok = s.get(f"{key}_{vista}_hier_hit_correct", 0)
                rate = ok / tot * 100 if tot else 0
                row.append(f"{ok}/{tot} = **{rate:.1f}%**")
            md.append("| " + " | ".join(row) + " |")

    md.append("\n### Risultato Esatto (top 5 gerarchico)\n")
    md.append("| Vista | BASE | WIDE_A | WIDE_B |")
    md.append("|---|---|---|---|")
    for vista in ["global", "intra"]:
        row = [vista]
        for v in ["BASE", "WIDE_A", "WIDE_B"]:
            s = all_stats[v]["stats"]
            tot = s.get(f"re_{vista}_hit_total", 0)
            ok = s.get(f"re_{vista}_hit_correct", 0)
            rate = ok / tot * 100 if tot else 0
            row.append(f"{ok}/{tot} = **{rate:.1f}%**")
        md.append("| " + " | ".join(row) + " |")

    # Distribuzione celle sorgente
    md.append("\n## Distribuzione celle sorgente — metodo cella-per-cella (1X2)\n")
    md.append("Quale cella e' stata 'la prima non vuota' (cioe' la cella usata per il verdetto)?\n")
    for vista_label in ["global", "intra"]:
        md.append(f"\n### Vista {vista_label.upper()}\n")
        md.append("| Cella | BASE | WIDE_A | WIDE_B |")
        md.append("|---|---|---|---|")
        all_cells = set()
        for v in ["BASE", "WIDE_A", "WIDE_B"]:
            key = f"cell_dist_{vista_label}_cbc"
            all_cells.update(all_stats[v][key].keys())
        # Ordina per CELL_VISIT_ORDER
        ordered_cells = [f"{l} {b}" for l in LEVELS for b in BANDS if f"{l} {b}" in all_cells]
        for cell in ordered_cells:
            row = [cell]
            for v in ["BASE", "WIDE_A", "WIDE_B"]:
                key = f"cell_dist_{vista_label}_cbc"
                row.append(str(all_stats[v][key].get(cell, 0)))
            md.append("| " + " | ".join(row) + " |")

    md.append("\n## Distribuzione celle sorgente — metodo gerarchico (>=10 partite)\n")
    for vista_label in ["global", "intra"]:
        md.append(f"\n### Vista {vista_label.upper()}\n")
        md.append("| Cella | BASE | WIDE_A | WIDE_B |")
        md.append("|---|---|---|---|")
        all_cells = set()
        for v in ["BASE", "WIDE_A", "WIDE_B"]:
            key = f"cell_dist_{vista_label}_hier"
            all_cells.update(all_stats[v][key].keys())
        ordered_cells = [f"{l} {b}" for l in LEVELS for b in BANDS if f"{l} {b}" in all_cells]
        for cell in ordered_cells:
            row = [cell]
            for v in ["BASE", "WIDE_A", "WIDE_B"]:
                key = f"cell_dist_{vista_label}_hier"
                row.append(str(all_stats[v][key].get(cell, 0)))
            md.append("| " + " | ".join(row) + " |")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[done] output: {OUTPUT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
