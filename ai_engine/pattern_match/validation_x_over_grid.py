"""
Griglia di soglie per pattern X (pareggio) + Over 2.5.

Provo tutte le combinazioni:
- X da 20% a 50% step 1%
- Over 2.5 da 45% a 80% step 1%

Per ogni combinazione:
- Quante partite attivano il pattern
- Hit rate per X reale, Over 2.5 reale, Goal reale, 1-1 e 2-2 nei top 5

Output: validation_x_over_grid.md
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


OUTPUT_MD = Path(__file__).parent / "validation_x_over_grid.md"
RANDOM_SEED = 42

# Range soglie da testare
X_THRESHOLDS = [round(0.20 + 0.01 * i, 2) for i in range(31)]      # 20% .. 50%
OVER25_THRESHOLDS = [round(0.45 + 0.01 * i, 2) for i in range(36)] # 45% .. 80%


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

    # Pre-calcolo i mercati per ogni partita test (una volta sola)
    print("[compute] calcolo mercati per ogni partita...")
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
            "x_pct": mkt["1x2"]["X"],
            "over25_pct": mkt["over_under_2_5"]["over"],
            "real_1x2": real_1x2,
            "real_ou25": real_ou25,
            "real_gg": real_gg,
            "real_score": real_score,
            "has_1_1": "1-1" in re_scores,
            "has_2_2": "2-2" in re_scores,
            "re_hit": real_score in re_scores,
        })

    n_test = len(records)
    print(f"\n[compute] {n_test} pronostici\n")

    # Per ogni combinazione di soglie, calcolo statistiche
    print(f"[grid] esecuzione {len(X_THRESHOLDS)}x{len(OVER25_THRESHOLDS)} = {len(X_THRESHOLDS)*len(OVER25_THRESHOLDS)} combinazioni...")

    results = []
    for thr_x in X_THRESHOLDS:
        for thr_ou in OVER25_THRESHOLDS:
            active = [r for r in records if r["x_pct"] >= thr_x and r["over25_pct"] >= thr_ou]
            n_a = len(active)
            if n_a == 0:
                continue
            x_hit = sum(1 for r in active if r["real_1x2"] == "D")
            over_hit = sum(1 for r in active if r["real_ou25"] == "over")
            goal_hit = sum(1 for r in active if r["real_gg"] == "goal")
            re_hit = sum(1 for r in active if r["re_hit"])
            results.append({
                "thr_x": thr_x,
                "thr_ou": thr_ou,
                "n": n_a,
                "x_rate": x_hit / n_a * 100,
                "over_rate": over_hit / n_a * 100,
                "goal_rate": goal_hit / n_a * 100,
                "re_rate": re_hit / n_a * 100,
            })

    # Output MD
    md = ["# Griglia pattern: X (pareggio) + Over 2.5\n"]
    md.append(f"**Test set**: {n_test} partite (seed={RANDOM_SEED})\n")
    md.append(f"**Combinazioni testate**: X 20-50% step 1%, Over 2.5 45-80% step 1%\n")

    # Top 20 per Over hit rate (soglia minima 5 partite attive)
    md.append("\n## Top 20 combinazioni per Over 2.5 hit rate (≥5 attive)\n")
    md.append("| Soglia X | Soglia Over | N attive | X hit | Over hit | Goal hit | RE hit |")
    md.append("|---|---|---|---|---|---|---|")
    sorted_over = sorted([r for r in results if r["n"] >= 5], key=lambda x: -x["over_rate"])[:20]
    for r in sorted_over:
        md.append(f"| {r['thr_x']*100:.0f}% | {r['thr_ou']*100:.0f}% | {r['n']} | {r['x_rate']:.1f}% | **{r['over_rate']:.1f}%** | {r['goal_rate']:.1f}% | {r['re_rate']:.1f}% |")

    # Top 20 per X hit rate (≥5 attive)
    md.append("\n## Top 20 combinazioni per X hit rate (≥5 attive)\n")
    md.append("| Soglia X | Soglia Over | N attive | X hit | Over hit | Goal hit | RE hit |")
    md.append("|---|---|---|---|---|---|---|")
    sorted_x = sorted([r for r in results if r["n"] >= 5], key=lambda x: -x["x_rate"])[:20]
    for r in sorted_x:
        md.append(f"| {r['thr_x']*100:.0f}% | {r['thr_ou']*100:.0f}% | {r['n']} | **{r['x_rate']:.1f}%** | {r['over_rate']:.1f}% | {r['goal_rate']:.1f}% | {r['re_rate']:.1f}% |")

    # Top 20 per Goal hit rate
    md.append("\n## Top 20 combinazioni per Goal hit rate (≥5 attive)\n")
    md.append("| Soglia X | Soglia Over | N attive | X hit | Over hit | Goal hit | RE hit |")
    md.append("|---|---|---|---|---|---|---|")
    sorted_goal = sorted([r for r in results if r["n"] >= 5], key=lambda x: -x["goal_rate"])[:20]
    for r in sorted_goal:
        md.append(f"| {r['thr_x']*100:.0f}% | {r['thr_ou']*100:.0f}% | {r['n']} | {r['x_rate']:.1f}% | {r['over_rate']:.1f}% | **{r['goal_rate']:.1f}%** | {r['re_rate']:.1f}% |")

    # Top 20 per RE hit rate
    md.append("\n## Top 20 combinazioni per RE hit rate (≥5 attive)\n")
    md.append("| Soglia X | Soglia Over | N attive | X hit | Over hit | Goal hit | RE hit |")
    md.append("|---|---|---|---|---|---|---|")
    sorted_re = sorted([r for r in results if r["n"] >= 5], key=lambda x: -x["re_rate"])[:20]
    for r in sorted_re:
        md.append(f"| {r['thr_x']*100:.0f}% | {r['thr_ou']*100:.0f}% | {r['n']} | {r['x_rate']:.1f}% | {r['over_rate']:.1f}% | {r['goal_rate']:.1f}% | **{r['re_rate']:.1f}%** |")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[done] output: {OUTPUT_MD}")

    # Sintesi a video
    print("\n=== TOP 5 per ogni metrica (≥5 attive) ===")
    for label, key in [("Over hit", "over_rate"), ("X hit", "x_rate"), ("Goal hit", "goal_rate"), ("RE hit", "re_rate")]:
        print(f"\n{label}:")
        sorted_r = sorted([r for r in results if r["n"] >= 5], key=lambda x: -x[key])[:5]
        for r in sorted_r:
            print(f"  X≥{r['thr_x']*100:.0f}% Over≥{r['thr_ou']*100:.0f}%  n={r['n']}  X={r['x_rate']:.0f}%  Over={r['over_rate']:.0f}%  Goal={r['goal_rate']:.0f}%  RE={r['re_rate']:.0f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
