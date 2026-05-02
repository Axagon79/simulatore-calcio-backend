"""
Fase 3 BIS — Validazione Pattern Match Engine — METODO GERARCHICO.

Per ogni partita test, per ogni mercato, calcola il verdetto in modo gerarchico:
- Visita le 25 celle in ordine T1 23/23 -> T5 8-11 (dalla piu stretta alla piu larga)
- Si ferma alla prima cella con >= N_MIN partite (default 10)
- Quella cella e' la sorgente del verdetto

Output: validation_50_hierarchical.md
- Per ogni partita: 2 verdetti (globale e intra-lega) per ogni mercato
- Riepilogo finale: hit rate per mercato (con info "from_cell" media/distribuzione)

Uso:
    python -m ai_engine.pattern_match.validation_50_hierarchical
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


OUTPUT_MD = Path(__file__).parent / "validation_50_hierarchical.md"
RANDOM_SEED = 42
N_MIN = 10  # soglia minima partite per fermarsi nella cella

# Stesso ordine di visita gerarchico usato per RE
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


def find_first_qualifying_cell(matrix: dict, n_min: int = N_MIN) -> dict | None:
    """
    Visita le 25 celle in ordine gerarchico e ritorna la prima con >= n_min partite.
    Ritorna None se nessuna cella qualifica.
    """
    cells_by_key = {(c["tolerance_level"], c["compatibility_band"]): c
                    for c in matrix["cells"]}
    for lvl, band in CELL_VISIT_ORDER:
        c = cells_by_key.get((lvl, band))
        if c and c["n_matches"] >= n_min:
            return c
    return None


def predict_1x2(cell: dict) -> tuple[str, dict] | tuple[None, None]:
    if not cell:
        return None, None
    d = cell["outcome_distribution"]
    sign = max(d, key=d.get)
    return {"1": "H", "X": "D", "2": "A"}[sign], d


def predict_dc(cell: dict) -> tuple[str, dict] | tuple[None, None]:
    if not cell or not cell.get("doppia_chance"):
        return None, None
    d = cell["doppia_chance"]
    return max(d, key=d.get), d


def predict_ou(cell: dict, soglia: str) -> tuple[str, dict] | tuple[None, None]:
    if not cell or not cell.get(f"over_under_{soglia}"):
        return None, None
    d = cell[f"over_under_{soglia}"]
    return max(d, key=d.get), d


def predict_gg(cell: dict) -> tuple[str, dict] | tuple[None, None]:
    if not cell or not cell.get("goal_nogoal"):
        return None, None
    d = cell["goal_nogoal"]
    return max(d, key=d.get), d


def predict_mg(cell: dict) -> tuple[str, dict] | tuple[None, None]:
    if not cell or not cell.get("multigol"):
        return None, None
    d = cell["multigol"]
    return max(d, key=d.get), d


def real_dc(real_1x2: str) -> str:
    """Per DC, l'esito reale puo' coincidere con piu opzioni: prendiamo la 'piu specifica'."""
    # Per coerenza con metodo cella per cella: confronto la predizione con cosa contiene
    # l'esito reale. Restituiamo le DC compatibili.
    if real_1x2 == "H": return ["1X", "12"]
    if real_1x2 == "D": return ["1X", "X2"]
    if real_1x2 == "A": return ["X2", "12"]
    return []


def real_mg(total_goals: int) -> list[str]:
    """Quali range MG contengono il totale gol reale."""
    out = []
    if 1 <= total_goals <= 2: out.append("1_2")
    if 2 <= total_goals <= 3: out.append("2_3")
    if 1 <= total_goals <= 3: out.append("1_3")
    if 2 <= total_goals <= 4: out.append("2_4")
    if 3 <= total_goals <= 5: out.append("3_5")
    if 4 <= total_goals <= 6: out.append("4_6")
    return out


def main():
    print("[load] caricamento dataset 32k partite...")
    features_db, outcomes_db, metadata_db = load_dataset()
    print(f"[load] {len(metadata_db)} partite\n")

    print(f"[pick] selezione 50 partite test (seed={RANDOM_SEED})...")
    test_matches = pick_test_matches(n_serie_a=25, n_other=25, season="2024-25")
    print(f"[pick] {len(test_matches)} partite\n")

    md = ["# Validazione Pattern Match Engine — METODO GERARCHICO\n"]
    md.append(f"**Soglia minima partite per cella sorgente**: {N_MIN}\n")
    md.append(f"**Test set**: 25 Serie A + 25 altre leghe, stagione 2024-25, seed={RANDOM_SEED}\n")
    md.append(f"**Algoritmo**: per ogni mercato, scendo dalle celle piu strette (T1 23/23) alle piu larghe (T5 8-11). Mi fermo alla prima con >= {N_MIN} partite.\n")
    md.append("---\n")

    # Stats aggregate
    stats = {
        "1x2_global":     {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "1x2_intra":      {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "dc_global":      {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "dc_intra":       {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "ou15_global":    {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "ou15_intra":     {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "ou25_global":    {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "ou25_intra":     {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "ou35_global":    {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "ou35_intra":     {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "gg_global":      {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "gg_intra":       {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "mg_global":      {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "mg_intra":       {"hit": 0, "total": 0, "from_cell_dist": Counter()},
        "re_global":      {"hit": 0, "total": 0},
        "re_intra":       {"hit": 0, "total": 0},
    }

    for idx, target_doc in enumerate(tqdm(test_matches, desc="hier-validation"), 1):
        match_uid = target_doc["match_uid"]
        target_features = target_doc["feature_vector"]
        target_lega = target_doc["lega"]
        real_outcome = target_doc["outcome"]
        real_1x2 = real_outcome["result_1x2"]
        real_total = real_outcome["goals_home"] + real_outcome["goals_away"]
        real_ou15 = "over" if real_total >= 2 else "under"
        real_ou25 = "over" if real_total >= 3 else "under"
        real_ou35 = "over" if real_total >= 4 else "under"
        real_gg = "goal" if (real_outcome["goals_home"] >= 1 and real_outcome["goals_away"] >= 1) else "nogoal"
        real_score = real_outcome["ft_score"]
        real_mg_set = set(real_mg(real_total))
        real_dc_set = set(real_dc(real_1x2))

        # Esclusione self
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

        # Trova celle sorgente per global e intra
        cell_global = find_first_qualifying_cell(matrix_global, N_MIN)
        cell_intra = find_first_qualifying_cell(matrix_intra, N_MIN)

        # Header partita
        md.append(f"\n## Match {idx}/{len(test_matches)}: {target_doc['home_team']} vs {target_doc['away_team']}\n")
        md.append(f"- **uid**: `{match_uid}` | **{target_lega} {target_doc['stagione']}** | **{target_doc['data_partita'].strftime('%Y-%m-%d')}**")
        md.append(f"- **Esito reale**: {real_score} (1X2={real_1x2}, gol_tot={real_total}, GG/NG={real_gg})")
        md.append(f"- **Quote**: 1={1/target_features['prob_implicita_1']:.2f} X={1/target_features['prob_implicita_X']:.2f} 2={1/target_features['prob_implicita_2']:.2f}")

        # Tabella verdetti per la partita
        md.append("\n| Mercato | Verdetto GLOBALE (cella) | Verdetto INTRA-LEGA (cella) | Reale | Hit G | Hit I |")
        md.append("|---|---|---|---|---|---|")

        # 1X2
        p_g, dist_g = predict_1x2(cell_global)
        p_i, dist_i = predict_1x2(cell_intra)
        cg = f"{p_g} ({dist_g[max(dist_g, key=dist_g.get)]*100:.0f}%) [{cell_global['tolerance_level']} {cell_global['compatibility_band']}, n={cell_global['n_matches']}]" if cell_global else "—"
        ci = f"{p_i} ({dist_i[max(dist_i, key=dist_i.get)]*100:.0f}%) [{cell_intra['tolerance_level']} {cell_intra['compatibility_band']}, n={cell_intra['n_matches']}]" if cell_intra else "—"
        hit_g = "✅" if p_g == real_1x2 else "❌"
        hit_i = "✅" if p_i == real_1x2 else "❌"
        md.append(f"| 1X2 | {cg} | {ci} | {real_1x2} | {hit_g} | {hit_i} |")

        if p_g is not None:
            stats["1x2_global"]["total"] += 1
            stats["1x2_global"]["from_cell_dist"][f"{cell_global['tolerance_level']} {cell_global['compatibility_band']}"] += 1
            if p_g == real_1x2: stats["1x2_global"]["hit"] += 1
        if p_i is not None:
            stats["1x2_intra"]["total"] += 1
            stats["1x2_intra"]["from_cell_dist"][f"{cell_intra['tolerance_level']} {cell_intra['compatibility_band']}"] += 1
            if p_i == real_1x2: stats["1x2_intra"]["hit"] += 1

        # DC
        p_g, _ = predict_dc(cell_global)
        p_i, _ = predict_dc(cell_intra)
        hit_g = "✅" if p_g in real_dc_set else "❌"
        hit_i = "✅" if p_i in real_dc_set else "❌"
        md.append(f"| DC | {p_g or '—'} | {p_i or '—'} | {','.join(real_dc_set)} | {hit_g} | {hit_i} |")
        if p_g is not None:
            stats["dc_global"]["total"] += 1
            stats["dc_global"]["from_cell_dist"][f"{cell_global['tolerance_level']} {cell_global['compatibility_band']}"] += 1
            if p_g in real_dc_set: stats["dc_global"]["hit"] += 1
        if p_i is not None:
            stats["dc_intra"]["total"] += 1
            stats["dc_intra"]["from_cell_dist"][f"{cell_intra['tolerance_level']} {cell_intra['compatibility_band']}"] += 1
            if p_i in real_dc_set: stats["dc_intra"]["hit"] += 1

        # O/U 1.5, 2.5, 3.5
        for soglia, real_ou, key_g, key_i in [
            ("1_5", real_ou15, "ou15_global", "ou15_intra"),
            ("2_5", real_ou25, "ou25_global", "ou25_intra"),
            ("3_5", real_ou35, "ou35_global", "ou35_intra"),
        ]:
            p_g, _ = predict_ou(cell_global, soglia)
            p_i, _ = predict_ou(cell_intra, soglia)
            hit_g = "✅" if p_g == real_ou else "❌"
            hit_i = "✅" if p_i == real_ou else "❌"
            md.append(f"| O/U {soglia.replace('_', '.')} | {p_g or '—'} | {p_i or '—'} | {real_ou} | {hit_g} | {hit_i} |")
            if p_g is not None:
                stats[key_g]["total"] += 1
                if p_g == real_ou: stats[key_g]["hit"] += 1
            if p_i is not None:
                stats[key_i]["total"] += 1
                if p_i == real_ou: stats[key_i]["hit"] += 1

        # GG/NG
        p_g, _ = predict_gg(cell_global)
        p_i, _ = predict_gg(cell_intra)
        hit_g = "✅" if p_g == real_gg else "❌"
        hit_i = "✅" if p_i == real_gg else "❌"
        md.append(f"| GG/NG | {p_g or '—'} | {p_i or '—'} | {real_gg} | {hit_g} | {hit_i} |")
        if p_g is not None:
            stats["gg_global"]["total"] += 1
            if p_g == real_gg: stats["gg_global"]["hit"] += 1
        if p_i is not None:
            stats["gg_intra"]["total"] += 1
            if p_i == real_gg: stats["gg_intra"]["hit"] += 1

        # MG
        p_g, _ = predict_mg(cell_global)
        p_i, _ = predict_mg(cell_intra)
        hit_g = "✅" if p_g in real_mg_set else "❌"
        hit_i = "✅" if p_i in real_mg_set else "❌"
        md.append(f"| MG | {p_g or '—'} | {p_i or '—'} | {','.join(sorted(real_mg_set))} | {hit_g} | {hit_i} |")
        if p_g is not None:
            stats["mg_global"]["total"] += 1
            if p_g in real_mg_set: stats["mg_global"]["hit"] += 1
        if p_i is not None:
            stats["mg_intra"]["total"] += 1
            if p_i in real_mg_set: stats["mg_intra"]["hit"] += 1

        # RE (gia gerarchico nel matrix output)
        re_global_scores = [r["score"] for r in matrix_global.get("risultato_esatto_top5", [])]
        re_intra_scores = [r["score"] for r in matrix_intra.get("risultato_esatto_top5", [])]
        hit_g = "✅" if real_score in re_global_scores else "❌"
        hit_i = "✅" if real_score in re_intra_scores else "❌"
        md.append(f"| RE (top5) | {','.join(re_global_scores)} | {','.join(re_intra_scores)} | {real_score} | {hit_g} | {hit_i} |")
        stats["re_global"]["total"] += 1
        stats["re_intra"]["total"] += 1
        if real_score in re_global_scores: stats["re_global"]["hit"] += 1
        if real_score in re_intra_scores: stats["re_intra"]["hit"] += 1

        md.append("\n---\n")

    # Riepilogo finale
    md.append("\n# Riepilogo aggregato — METODO GERARCHICO\n")
    md.append("Hit rate per ogni mercato, calcolato sul verdetto della prima cella con >= 10 partite (in ordine T1 23/23 -> T5 8-11).\n")
    md.append("\n| Mercato | GLOBALE | INTRA-LEGA |")
    md.append("|---|---|---|")
    for label, key_g, key_i in [
        ("1X2", "1x2_global", "1x2_intra"),
        ("DC", "dc_global", "dc_intra"),
        ("O/U 1.5", "ou15_global", "ou15_intra"),
        ("O/U 2.5", "ou25_global", "ou25_intra"),
        ("O/U 3.5", "ou35_global", "ou35_intra"),
        ("GG/NG", "gg_global", "gg_intra"),
        ("MG", "mg_global", "mg_intra"),
        ("RE top5", "re_global", "re_intra"),
    ]:
        sg = stats[key_g]
        si = stats[key_i]
        rate_g = sg["hit"] / sg["total"] * 100 if sg["total"] else 0
        rate_i = si["hit"] / si["total"] * 100 if si["total"] else 0
        md.append(f"| {label} | {sg['hit']}/{sg['total']} = **{rate_g:.1f}%** | {si['hit']}/{si['total']} = **{rate_i:.1f}%** |")

    # Distribuzione celle sorgente per 1X2
    md.append("\n## Distribuzione celle sorgente (per 1X2)\n")
    md.append("Da quale cella e' venuto il verdetto piu spesso? Indica quanto i cerchi stretti sono utilizzabili.\n")
    md.append("\n### GLOBALE\n")
    md.append("| Cella | N partite |")
    md.append("|---|---|")
    for cell, n in stats["1x2_global"]["from_cell_dist"].most_common():
        md.append(f"| {cell} | {n} |")
    md.append("\n### INTRA-LEGA\n")
    md.append("| Cella | N partite |")
    md.append("|---|---|")
    for cell, n in stats["1x2_intra"]["from_cell_dist"].most_common():
        md.append(f"| {cell} | {n} |")

    # Baseline
    md.append("\n## Baseline (su 32k partite)\n")
    md.append("| Esito | Baseline |")
    md.append("|---|---|")
    counter = Counter(outcomes_db)
    over15 = over25 = over35 = 0
    goal = 0
    n = len(outcomes_db)
    for m in metadata_db:
        tg = m["goals_home"] + m["goals_away"]
        if tg >= 2: over15 += 1
        if tg >= 3: over25 += 1
        if tg >= 4: over35 += 1
        if m["goals_home"] >= 1 and m["goals_away"] >= 1: goal += 1
    md.append(f"| 1 | {counter['H']/n*100:.1f}% |")
    md.append(f"| X | {counter['D']/n*100:.1f}% |")
    md.append(f"| 2 | {counter['A']/n*100:.1f}% |")
    md.append(f"| Over 1.5 | {over15/n*100:.1f}% |")
    md.append(f"| Over 2.5 | {over25/n*100:.1f}% |")
    md.append(f"| Over 3.5 | {over35/n*100:.1f}% |")
    md.append(f"| Goal | {goal/n*100:.1f}% |")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[done] output: {OUTPUT_MD}")
    print(f"[done] 1X2 intra: {stats['1x2_intra']['hit']}/{stats['1x2_intra']['total']} = {stats['1x2_intra']['hit']/max(stats['1x2_intra']['total'],1)*100:.1f}%")
    print(f"[done] O/U 2.5 intra: {stats['ou25_intra']['hit']}/{stats['ou25_intra']['total']} = {stats['ou25_intra']['hit']/max(stats['ou25_intra']['total'],1)*100:.1f}%")
    print(f"[done] RE intra: {stats['re_intra']['hit']}/{stats['re_intra']['total']} = {stats['re_intra']['hit']/max(stats['re_intra']['total'],1)*100:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
