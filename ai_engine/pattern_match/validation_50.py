"""
Fase 3 — Validazione Pattern Match Engine su 50 partite finite.

Pesca 50 partite della stagione 2024/25 (25 Serie A + 25 altre leghe a caso),
per ognuna:
- Esclude la partita stessa dal dataset di matching
- Calcola la matrice 5x5 (globale + intra-lega) per tutti i mercati
- Calcola RE gerarchico
- Confronta con esito reale

Output: validation_50_matches.md con:
- Per ogni partita: matrice 5x5 SEGNO (globale e intra-lega) + tabella mercati
  per cella T3 16-19 + RE top 5 + esito reale
- Riepilogo finale: hit rate per cerchio per mercato + statistica RE

Uso:
    python -m ai_engine.pattern_match.validation_50
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.match_engine import (
    compute_matrix, load_dataset,
    NUMERIC_FEATURES, COMPATIBILITY_BANDS,
)
from ai_engine.pattern_match.config import MONGO_COLLECTION_MATCHES
from config import db


OUTPUT_MD = Path(__file__).parent / "validation_50_matches.md"
RANDOM_SEED = 42  # riproducibilita


def pick_test_matches(n_serie_a: int = 25, n_other: int = 25,
                      season: str = "2024-25") -> list[dict]:
    """
    Pesca a caso n_serie_a partite di Serie A + n_other partite di altre leghe
    dalla stagione indicata. Solo partite con esito reale.
    """
    coll = db[MONGO_COLLECTION_MATCHES]
    rng = random.Random(RANDOM_SEED)

    serie_a = list(coll.find({"lega": "I1", "stagione": season}))
    others = list(coll.find({"lega": {"$ne": "I1"}, "stagione": season}))

    picked_sa = rng.sample(serie_a, min(n_serie_a, len(serie_a)))
    picked_other = rng.sample(others, min(n_other, len(others)))

    return picked_sa + picked_other


def render_matrix_md(matrix: dict, title: str) -> str:
    """Rende la matrice 5x5 in markdown table."""
    lines = [f"\n#### {title}\n"]
    bands = [b[0] for b in COMPATIBILITY_BANDS]
    levels = ["T1", "T2", "T3", "T4", "T5"]

    # Header
    header = "| | " + " | ".join(bands) + " |"
    sep = "|---|" + "|".join(["---"] * len(bands)) + "|"
    lines.append(header)
    lines.append(sep)

    cells_by_key = {
        (c["tolerance_level"], c["compatibility_band"]): c
        for c in matrix["cells"]
    }
    for lvl in levels:
        row = [f"**{lvl}**"]
        for band in bands:
            c = cells_by_key.get((lvl, band))
            if not c or c["n_matches"] == 0:
                row.append("0")
            else:
                d = c["outcome_distribution"]
                dom = max(d, key=d.get)
                pct = d[dom] * 100
                row.append(f"{c['n_matches']}<br>{dom} {pct:.0f}%")
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def render_extended_cell_md(cell: dict, label: str) -> str:
    """Stampa mercati estesi di una cella in markdown."""
    if not cell or cell["n_matches"] == 0:
        return f"\n#### {label}\n\n_Cella vuota_\n"
    lines = [f"\n#### {label} — {cell['n_matches']} partite\n"]
    lines.append("| Mercato | Valore |")
    lines.append("|---|---|")
    d = cell["outcome_distribution"]
    lines.append(f"| 1X2 | 1 {d['1']*100:.1f}% / X {d['X']*100:.1f}% / 2 {d['2']*100:.1f}% |")
    if cell.get("doppia_chance"):
        dc = cell["doppia_chance"]
        lines.append(f"| DC | 1X {dc['1X']*100:.1f}% / X2 {dc['X2']*100:.1f}% / 12 {dc['12']*100:.1f}% |")
    if cell.get("over_under_2_5"):
        ou = cell["over_under_2_5"]
        lines.append(f"| O/U 2.5 | Over {ou['over']*100:.1f}% / Under {ou['under']*100:.1f}% |")
    if cell.get("goal_nogoal"):
        gn = cell["goal_nogoal"]
        lines.append(f"| GG/NG | Goal {gn['goal']*100:.1f}% / NoGoal {gn['nogoal']*100:.1f}% |")
    if cell.get("medie"):
        m = cell["medie"]
        lines.append(f"| Medie gol | casa {m['avg_goals_home']:.2f} / osp {m['avg_goals_away']:.2f} / tot {m['avg_total_goals']:.2f} |")
    return "\n".join(lines)


def render_re_md(re_list: list, title: str) -> str:
    if not re_list:
        return f"\n#### {title}\n\n_Nessun RE trovato_\n"
    lines = [f"\n#### {title}\n"]
    lines.append("| # | Score | From cell | Freq cella |")
    lines.append("|---|---|---|---|")
    for i, r in enumerate(re_list, 1):
        lines.append(f"| {i} | **{r['score']}** | {r['from_cell']} | {r['frequency_in_cell']}/{r['n_in_cell']} |")
    return "\n".join(lines)


def predict_from_cell(cell: dict) -> str | None:
    """Estrae il segno dominante da una cella, o None se vuota.
    Mappa "1"/"X"/"2" (chiavi distribution) -> "H"/"D"/"A" (formato real_1x2)."""
    if not cell or cell["n_matches"] == 0:
        return None
    d = cell["outcome_distribution"]
    sign = max(d, key=d.get)  # "1", "X" o "2"
    return {"1": "H", "X": "D", "2": "A"}[sign]


def predict_ou25_from_cell(cell: dict) -> str | None:
    if not cell or cell["n_matches"] == 0:
        return None
    ou = cell["over_under_2_5"]
    return "over" if ou["over"] >= 0.5 else "under"


def predict_gg_from_cell(cell: dict) -> str | None:
    if not cell or cell["n_matches"] == 0:
        return None
    gn = cell["goal_nogoal"]
    return "goal" if gn["goal"] >= 0.5 else "nogoal"


def find_best_cell(matrix: dict, min_n: int = 10) -> dict | None:
    """Cella piu stretta non vuota con almeno min_n partite (T1->T5, 23/23->8-11)."""
    levels = ["T1", "T2", "T3", "T4", "T5"]
    bands = [b[0] for b in COMPATIBILITY_BANDS]
    cells_by_key = {(c["tolerance_level"], c["compatibility_band"]): c
                    for c in matrix["cells"]}
    for lvl in levels:
        for band in bands:
            c = cells_by_key.get((lvl, band))
            if c and c["n_matches"] >= min_n:
                return c
    return None


def main():
    print("[load] caricamento dataset 32k partite...")
    features_db, outcomes_db, metadata_db = load_dataset()
    print(f"[load] {len(metadata_db)} partite caricate\n")

    print(f"[pick] selezione 50 partite test (seed={RANDOM_SEED})...")
    test_matches = pick_test_matches(n_serie_a=25, n_other=25, season="2024-25")
    print(f"[pick] selezionate {len(test_matches)} partite\n")

    md_lines = ["# Validazione Pattern Match Engine — 50 partite (stagione 2024/25)\n"]
    md_lines.append(f"**Dataset**: {len(metadata_db)} partite storiche\n")
    md_lines.append(f"**Test set**: 25 Serie A + 25 altre leghe, stagione 2024/25, seed={RANDOM_SEED}\n")
    md_lines.append("**Metodo**: per ogni partita, esclusa dal dataset, calcolo matrice 5x5 globale + intra-lega.\n")
    md_lines.append("---\n")

    # Stats aggregate per riepilogo finale
    stats_by_cell = {}  # {(lvl, band, vista): {"correct_1x2": 0, "total_1x2": 0, ...}}
    re_in_top5_count = 0
    re_total = 0

    for idx, target_doc in enumerate(tqdm(test_matches, desc="validation"), 1):
        match_uid = target_doc["match_uid"]
        target_features = target_doc["feature_vector"]
        target_lega = target_doc["lega"]
        real_outcome = target_doc["outcome"]
        real_1x2 = real_outcome["result_1x2"]
        real_total_goals = real_outcome["goals_home"] + real_outcome["goals_away"]
        real_ou25 = "over" if real_total_goals >= 3 else "under"
        real_gg = "goal" if (real_outcome["goals_home"] >= 1 and real_outcome["goals_away"] >= 1) else "nogoal"
        real_score = real_outcome["ft_score"]

        # Esclusione self
        self_mask = np.array([m["match_uid"] != match_uid for m in metadata_db])
        feat_local = features_db[self_mask]
        out_local = outcomes_db[self_mask]
        meta_local = [m for m, k in zip(metadata_db, self_mask) if k]

        # Matrice globale
        matrix_global = compute_matrix(target_features, target_lega,
                                       feat_local, out_local, meta_local,
                                       intra_lega_only=False, top_k=3)

        # Matrice intra-lega
        intra_mask = np.array([m["lega"] == target_lega for m in meta_local])
        matrix_intra = compute_matrix(target_features, target_lega,
                                      feat_local[intra_mask], out_local[intra_mask],
                                      [m for m, k in zip(meta_local, intra_mask) if k],
                                      intra_lega_only=True, top_k=3)

        # Header partita nel MD
        md_lines.append(f"\n## Match {idx}/{len(test_matches)}: {target_doc['home_team']} vs {target_doc['away_team']}\n")
        md_lines.append(f"- **match_uid**: `{match_uid}`")
        md_lines.append(f"- **Lega/Stagione**: {target_lega} {target_doc['stagione']}")
        md_lines.append(f"- **Data**: {target_doc['data_partita'].strftime('%Y-%m-%d')}")
        md_lines.append(f"- **Esito reale**: {real_score} (1X2={real_1x2}, O/U2.5={real_ou25}, GG/NG={real_gg})")
        md_lines.append(f"- **Quote pre-match**: 1={1/target_features['prob_implicita_1']:.2f}  X={1/target_features['prob_implicita_X']:.2f}  2={1/target_features['prob_implicita_2']:.2f}")
        md_lines.append(f"- **Elo**: casa={target_features['elo_casa']:.0f}  ospite={target_features['elo_ospite']:.0f}")

        md_lines.append(render_matrix_md(matrix_global, "Matrice GLOBALE (10 leghe) — 1X2"))
        md_lines.append(render_matrix_md(matrix_intra, "Matrice INTRA-LEGA — 1X2"))

        # Cella T3 16-19 intra-lega: mercati estesi
        cell_t3_intra = next((c for c in matrix_intra["cells"]
                              if c["tolerance_level"] == "T3" and c["compatibility_band"] == "16-19"), None)
        md_lines.append(render_extended_cell_md(cell_t3_intra, "Cella T3 16-19 INTRA-LEGA — Mercati estesi"))

        # RE gerarchico
        md_lines.append(render_re_md(matrix_intra.get("risultato_esatto_top5", []),
                                      "RE Top 5 (intra-lega)"))
        md_lines.append(render_re_md(matrix_global.get("risultato_esatto_top5", []),
                                      "RE Top 5 (globale)"))

        # RE check: esito reale presente nei top 5?
        re_real = real_score
        re_intra_scores = [r["score"] for r in matrix_intra.get("risultato_esatto_top5", [])]
        re_global_scores = [r["score"] for r in matrix_global.get("risultato_esatto_top5", [])]
        re_hit_intra = re_real in re_intra_scores
        re_hit_global = re_real in re_global_scores
        md_lines.append(f"\n**RE hit**: intra-lega={re_hit_intra}, globale={re_hit_global}")
        if re_hit_intra or re_hit_global:
            re_in_top5_count += 1
        re_total += 1

        # Stats per cella per riepilogo finale
        for matrix, vista_label in [(matrix_global, "global"), (matrix_intra, "intra")]:
            for c in matrix["cells"]:
                key = (c["tolerance_level"], c["compatibility_band"], vista_label)
                if key not in stats_by_cell:
                    stats_by_cell[key] = {
                        "n_partite_con_dati": 0,
                        "correct_1x2": 0,
                        "total_1x2": 0,
                        "correct_ou25": 0, "total_ou25": 0,
                        "correct_gg": 0, "total_gg": 0,
                    }
                if c["n_matches"] == 0:
                    continue
                stats_by_cell[key]["n_partite_con_dati"] += 1

                pred_1x2 = predict_from_cell(c)
                if pred_1x2 is not None:
                    stats_by_cell[key]["total_1x2"] += 1
                    if pred_1x2 == real_1x2:
                        stats_by_cell[key]["correct_1x2"] += 1

                pred_ou = predict_ou25_from_cell(c)
                if pred_ou is not None:
                    stats_by_cell[key]["total_ou25"] += 1
                    if pred_ou == real_ou25:
                        stats_by_cell[key]["correct_ou25"] += 1

                pred_gg = predict_gg_from_cell(c)
                if pred_gg is not None:
                    stats_by_cell[key]["total_gg"] += 1
                    if pred_gg == real_gg:
                        stats_by_cell[key]["correct_gg"] += 1

        md_lines.append("\n---\n")

    # Riepilogo finale
    md_lines.append("\n# Riepilogo aggregato — hit rate per cella\n")
    md_lines.append("Hit rate = % partite in cui la cella ha predetto correttamente l'esito reale (escludendo le celle vuote per quella partita).\n")

    for vista_label, vista_title in [("global", "GLOBALE"), ("intra", "INTRA-LEGA")]:
        md_lines.append(f"\n## Vista {vista_title}\n")
        md_lines.append("| Cerchio | N partite con dati | 1X2 hit | O/U 2.5 hit | GG/NG hit |")
        md_lines.append("|---|---|---|---|---|")
        levels = ["T1", "T2", "T3", "T4", "T5"]
        bands = [b[0] for b in COMPATIBILITY_BANDS]
        for lvl in levels:
            for band in bands:
                key = (lvl, band, vista_label)
                s = stats_by_cell.get(key, {})
                n_dati = s.get("n_partite_con_dati", 0)
                if n_dati == 0:
                    continue
                rate_1x2 = s["correct_1x2"] / s["total_1x2"] * 100 if s.get("total_1x2") else 0
                rate_ou = s["correct_ou25"] / s["total_ou25"] * 100 if s.get("total_ou25") else 0
                rate_gg = s["correct_gg"] / s["total_gg"] * 100 if s.get("total_gg") else 0
                md_lines.append(f"| {lvl} {band} | {n_dati} | "
                                f"{s['correct_1x2']}/{s['total_1x2']} = **{rate_1x2:.1f}%** | "
                                f"{s['correct_ou25']}/{s['total_ou25']} = **{rate_ou:.1f}%** | "
                                f"{s['correct_gg']}/{s['total_gg']} = **{rate_gg:.1f}%** |")

    md_lines.append(f"\n## RE — Esito reale presente nei Top 5\n")
    md_lines.append(f"- **Hit rate**: {re_in_top5_count}/{re_total} = **{re_in_top5_count/re_total*100:.1f}%**\n")

    # Baseline
    md_lines.append("\n## Baseline di riferimento (su tutto il dataset 32k partite)\n")
    md_lines.append("| Esito | %  baseline |")
    md_lines.append("|---|---|")
    counter = {"H": 0, "D": 0, "A": 0}
    over25 = under25 = 0
    goal = nogoal = 0
    for o in outcomes_db:
        counter[o] += 1
    for m in metadata_db:
        tg = m["goals_home"] + m["goals_away"]
        if tg >= 3: over25 += 1
        else: under25 += 1
        if m["goals_home"] >= 1 and m["goals_away"] >= 1: goal += 1
        else: nogoal += 1
    n = len(outcomes_db)
    md_lines.append(f"| 1 (casa) | {counter['H']/n*100:.1f}% |")
    md_lines.append(f"| X (pareggio) | {counter['D']/n*100:.1f}% |")
    md_lines.append(f"| 2 (trasferta) | {counter['A']/n*100:.1f}% |")
    md_lines.append(f"| Over 2.5 | {over25/n*100:.1f}% |")
    md_lines.append(f"| Under 2.5 | {under25/n*100:.1f}% |")
    md_lines.append(f"| Goal | {goal/n*100:.1f}% |")
    md_lines.append(f"| NoGoal | {nogoal/n*100:.1f}% |")

    OUTPUT_MD.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"\n[done] output scritto in: {OUTPUT_MD}")
    print(f"[done] RE hit rate: {re_in_top5_count}/{re_total} = {re_in_top5_count/re_total*100:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
