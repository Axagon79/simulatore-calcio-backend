"""
Test pattern: Over 2.5 tra 50% e 80% AND X < 30%.

Logica: cerco partite dove il sistema dice "tante reti probabili"
MA "pareggio improbabile" → vincitore chiaro con tante reti.

Test in 2 step:
1. Pattern fisso: Over 50-80%, X < 30%
2. Griglia: Over min/max, X soglia massima → trovo soglie ottimali

Output: validation_over_no_x_pattern.md
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.weighted_engine import (
    extract_extended_features, compute_pool, compute_markets_for_pool,
    compute_re_top5, load_dataset_extended, MIN_PARTITE_PER_PRONOSTICO,
)
from ai_engine.pattern_match.config import MONGO_COLLECTION_MATCHES
from config import db


OUTPUT_MD = Path(__file__).parent / "validation_over_no_x_pattern.md"
RANDOM_SEED = 42


def pick_test_matches(n_serie_a: int = 25, n_other: int = 25,
                      season: str = "2024-25") -> list[dict]:
    coll = db[MONGO_COLLECTION_MATCHES]
    rng = random.Random(RANDOM_SEED)
    serie_a = list(coll.find({"lega": "I1", "stagione": season}))
    others = list(coll.find({"lega": {"$ne": "I1"}, "stagione": season}))
    return rng.sample(serie_a, n_serie_a) + rng.sample(others, n_other)


def main():
    print("[load] caricamento dataset...")
    dataset = load_dataset_extended()
    print(f"[load] {len(dataset)} partite\n")

    test_matches = pick_test_matches()
    print(f"[pick] {len(test_matches)} partite test\n")

    # Pre-calcolo
    print("[compute] mercati per ogni partita...")
    records = []
    for target_doc in tqdm(test_matches, desc="markets"):
        target_lega = target_doc["lega"]
        target_ext = extract_extended_features(target_doc["feature_vector"], target_lega)
        real_outcome = target_doc["outcome"]
        real_total = real_outcome["goals_home"] + real_outcome["goals_away"]
        real_1x2 = real_outcome["result_1x2"]
        real_ou25 = "over" if real_total >= 3 else "under"
        real_gg = "goal" if (real_outcome["goals_home"] >= 1 and real_outcome["goals_away"] >= 1) else "nogoal"
        real_score = real_outcome["ft_score"]

        pool_info = compute_pool(target_ext, dataset, exclude_uid=target_doc["match_uid"])
        if pool_info["n"] < MIN_PARTITE_PER_PRONOSTICO:
            continue

        mkt = compute_markets_for_pool(pool_info["partite"])
        re_top = compute_re_top5(pool_info["partite"], max_results=5)
        re_scores = [r["score"] for r in re_top]

        records.append({
            "home": target_doc["home_team"],
            "away": target_doc["away_team"],
            "x_pct": mkt["1x2"]["X"],
            "over25_pct": mkt["over_under_2_5"]["over"],
            "goal_pct": mkt["goal_nogoal"]["goal"],
            "real_1x2": real_1x2,
            "real_ou25": real_ou25,
            "real_gg": real_gg,
            "real_score": real_score,
            "re_scores": re_scores,
            "re_hit": real_score in re_scores,
        })

    n_test = len(records)
    print(f"\n[compute] {n_test} pronostici\n")

    md = ["# Pattern: Over 2.5 ∈ [X%, Y%] AND X < Z%\n"]
    md.append(f"**Test set**: {n_test} partite (seed={RANDOM_SEED})\n")

    # ============================================================
    # STEP 1: pattern fisso (Over 50-80%, X < 30%)
    # ============================================================
    OVER_MIN = 0.50
    OVER_MAX = 0.80
    X_MAX = 0.30

    active = [r for r in records
              if OVER_MIN <= r["over25_pct"] <= OVER_MAX and r["x_pct"] < X_MAX]
    inactive = [r for r in records if r not in active]

    md.append("\n## STEP 1 — Pattern fisso\n")
    md.append(f"**Condizione**: Over 2.5 ∈ [{OVER_MIN*100:.0f}%, {OVER_MAX*100:.0f}%] AND X < {X_MAX*100:.0f}%\n")
    md.append(f"**Partite attive**: {len(active)}/{n_test} ({len(active)/n_test*100:.1f}%)\n")

    if len(active) >= 5:
        x_hit = sum(1 for r in active if r["real_1x2"] == "D")
        over_hit = sum(1 for r in active if r["real_ou25"] == "over")
        goal_hit = sum(1 for r in active if r["real_gg"] == "goal")
        nogoal_hit = sum(1 for r in active if r["real_gg"] == "nogoal")
        sign1_hit = sum(1 for r in active if r["real_1x2"] == "H")
        sign2_hit = sum(1 for r in active if r["real_1x2"] == "A")
        sign1or2_hit = sign1_hit + sign2_hit
        re_hit = sum(1 for r in active if r["re_hit"])
        n_a = len(active)

        x_hit_in = sum(1 for r in inactive if r["real_1x2"] == "D")
        over_hit_in = sum(1 for r in inactive if r["real_ou25"] == "over")
        goal_hit_in = sum(1 for r in inactive if r["real_gg"] == "goal")
        nogoal_hit_in = sum(1 for r in inactive if r["real_gg"] == "nogoal")
        sign1or2_hit_in = sum(1 for r in inactive if r["real_1x2"] != "D")
        n_in = len(inactive)

        md.append("\n### Confronto hit rate\n")
        md.append("| Mercato | Pattern ATTIVO | Pattern NON attivo |")
        md.append("|---|---|---|")
        md.append(f"| X (pareggio) | {x_hit}/{n_a} = {x_hit/n_a*100:.1f}% | {x_hit_in}/{n_in} = {x_hit_in/n_in*100:.1f}% |")
        md.append(f"| Over 2.5 | {over_hit}/{n_a} = **{over_hit/n_a*100:.1f}%** | {over_hit_in}/{n_in} = {over_hit_in/n_in*100:.1f}% |")
        md.append(f"| Goal | {goal_hit}/{n_a} = **{goal_hit/n_a*100:.1f}%** | {goal_hit_in}/{n_in} = {goal_hit_in/n_in*100:.1f}% |")
        md.append(f"| NoGoal | {nogoal_hit}/{n_a} = **{nogoal_hit/n_a*100:.1f}%** | {nogoal_hit_in}/{n_in} = {nogoal_hit_in/n_in*100:.1f}% |")
        md.append(f"| 1 OR 2 (vincitore chiaro) | {sign1or2_hit}/{n_a} = **{sign1or2_hit/n_a*100:.1f}%** | {sign1or2_hit_in}/{n_in} = {sign1or2_hit_in/n_in*100:.1f}% |")
        md.append(f"| RE reale top 5 | {re_hit}/{n_a} = **{re_hit/n_a*100:.1f}%** | — | — |")

        md.append("\n### Dettaglio partite attive\n")
        md.append("| Partita | Reale | X% | Over% | Goal% | RE Top 5 |")
        md.append("|---|---|---|---|---|---|")
        for r in active:
            md.append(f"| {r['home']} vs {r['away']} ({r['real_score']}) | {r['real_1x2']}/{r['real_ou25']}/{r['real_gg']} | {r['x_pct']*100:.1f}% | {r['over25_pct']*100:.1f}% | {r['goal_pct']*100:.1f}% | {','.join(r['re_scores'])} |")

    # ============================================================
    # STEP 2: griglia
    # ============================================================
    md.append("\n## STEP 2 — Griglia esplorativa\n")
    md.append("Provo varie combinazioni di soglie per trovare il setup ottimale.\n")

    # Range
    over_max_options = [0.70, 0.75, 0.80, 0.85, 0.90, 1.00]
    x_max_options = [0.20, 0.22, 0.24, 0.26, 0.28, 0.30, 0.32, 0.35]
    over_min_options = [0.45, 0.50, 0.55, 0.60, 0.65, 0.70]

    grid_results = []
    for over_min in over_min_options:
        for over_max in over_max_options:
            if over_max < over_min:
                continue
            for x_max in x_max_options:
                act = [r for r in records
                       if over_min <= r["over25_pct"] <= over_max and r["x_pct"] < x_max]
                if len(act) < 5:
                    continue
                n_a = len(act)
                over_hit = sum(1 for r in act if r["real_ou25"] == "over")
                sign1or2_hit = sum(1 for r in act if r["real_1x2"] != "D")
                goal_hit = sum(1 for r in act if r["real_gg"] == "goal")
                nogoal_hit = sum(1 for r in act if r["real_gg"] == "nogoal")
                re_hit = sum(1 for r in act if r["re_hit"])
                grid_results.append({
                    "over_min": over_min,
                    "over_max": over_max,
                    "x_max": x_max,
                    "n": n_a,
                    "over_rate": over_hit / n_a * 100,
                    "sign_rate": sign1or2_hit / n_a * 100,
                    "goal_rate": goal_hit / n_a * 100,
                    "nogoal_rate": nogoal_hit / n_a * 100,
                    "re_rate": re_hit / n_a * 100,
                })

    # Top 20 per Over rate
    md.append("\n### Top 20 combinazioni per Over hit rate (≥5 attive)\n")
    md.append("| Over min | Over max | X max | N attive | Over hit | 1 OR 2 | Goal | NoGoal | RE hit |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    sorted_over = sorted(grid_results, key=lambda x: -x["over_rate"])[:20]
    for r in sorted_over:
        md.append(f"| {r['over_min']*100:.0f}% | {r['over_max']*100:.0f}% | {r['x_max']*100:.0f}% | {r['n']} | **{r['over_rate']:.1f}%** | {r['sign_rate']:.1f}% | {r['goal_rate']:.1f}% | {r['nogoal_rate']:.1f}% | {r['re_rate']:.1f}% |")

    # Top 20 per "1 OR 2"
    md.append("\n### Top 20 combinazioni per '1 OR 2' hit rate (≥5 attive)\n")
    md.append("| Over min | Over max | X max | N attive | Over hit | 1 OR 2 | Goal | NoGoal | RE hit |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    sorted_sign = sorted(grid_results, key=lambda x: -x["sign_rate"])[:20]
    for r in sorted_sign:
        md.append(f"| {r['over_min']*100:.0f}% | {r['over_max']*100:.0f}% | {r['x_max']*100:.0f}% | {r['n']} | {r['over_rate']:.1f}% | **{r['sign_rate']:.1f}%** | {r['goal_rate']:.1f}% | {r['nogoal_rate']:.1f}% | {r['re_rate']:.1f}% |")

    # Top 20 per Goal hit rate
    md.append("\n### Top 20 combinazioni per Goal hit rate (≥5 attive)\n")
    md.append("| Over min | Over max | X max | N attive | Over hit | 1 OR 2 | Goal | NoGoal | RE hit |")
    md.append("|---|---|---|---|---|---|---|---|---|")
    sorted_goal = sorted(grid_results, key=lambda x: -x["goal_rate"])[:20]
    for r in sorted_goal:
        md.append(f"| {r['over_min']*100:.0f}% | {r['over_max']*100:.0f}% | {r['x_max']*100:.0f}% | {r['n']} | {r['over_rate']:.1f}% | {r['sign_rate']:.1f}% | **{r['goal_rate']:.1f}%** | {r['nogoal_rate']:.1f}% | {r['re_rate']:.1f}% |")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[done] output: {OUTPUT_MD}")

    # Sintesi a video
    print(f"\n=== STEP 1 — Pattern fisso (Over 50-80%, X<30%) ===")
    print(f"Pattern attivo: {len(active)}/{n_test}")
    if len(active) >= 5:
        n_a = len(active)
        over_hit = sum(1 for r in active if r["real_ou25"] == "over")
        sign1or2_hit = sum(1 for r in active if r["real_1x2"] != "D")
        goal_hit = sum(1 for r in active if r["real_gg"] == "goal")
        nogoal_hit = sum(1 for r in active if r["real_gg"] == "nogoal")
        re_hit = sum(1 for r in active if r["re_hit"])
        print(f"  Over hit:     {over_hit}/{n_a} = {over_hit/n_a*100:.1f}%")
        print(f"  1 OR 2 hit:   {sign1or2_hit}/{n_a} = {sign1or2_hit/n_a*100:.1f}%")
        print(f"  Goal hit:     {goal_hit}/{n_a} = {goal_hit/n_a*100:.1f}%")
        print(f"  NoGoal hit:   {nogoal_hit}/{n_a} = {nogoal_hit/n_a*100:.1f}%")
        print(f"  RE hit top 5: {re_hit}/{n_a} = {re_hit/n_a*100:.1f}%")

    print(f"\n=== STEP 2 — TOP 5 combinazioni per Over rate (n>=5) ===")
    sorted_over = sorted(grid_results, key=lambda x: -x["over_rate"])[:5]
    for r in sorted_over:
        print(f"  Over {r['over_min']*100:.0f}-{r['over_max']*100:.0f}%, X<{r['x_max']*100:.0f}%  n={r['n']}  Over={r['over_rate']:.1f}%  1or2={r['sign_rate']:.1f}%  RE={r['re_rate']:.1f}%")

    print(f"\n=== STEP 2 — TOP 5 per '1 OR 2' rate ===")
    sorted_sign = sorted(grid_results, key=lambda x: -x["sign_rate"])[:5]
    for r in sorted_sign:
        print(f"  Over {r['over_min']*100:.0f}-{r['over_max']*100:.0f}%, X<{r['x_max']*100:.0f}%  n={r['n']}  Over={r['over_rate']:.1f}%  1or2={r['sign_rate']:.1f}%  RE={r['re_rate']:.1f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
