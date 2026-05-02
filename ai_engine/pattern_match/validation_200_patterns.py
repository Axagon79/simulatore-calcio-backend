"""
Validazione pattern Goal e NoGoal su 200 partite (4x il campione precedente).

Verifica se i pattern trovati sulle 50 partite sono confermati su un campione
piu grande:
- Pattern Goal: X<30% AND Over 2.5>65%   -> atteso ~80% Goal
- Pattern NoGoal: media_tot<2.5 AND min_squadra<0.9   -> atteso ~80% NoGoal

Output: validation_200_patterns.md
"""
from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.weighted_engine import (
    extract_extended_features, compute_pool, compute_markets_for_pool,
    compute_re_top5, detect_pattern_goal, detect_pattern_nogoal,
    load_dataset_extended, MIN_PARTITE_PER_PRONOSTICO,
)
from ai_engine.pattern_match.config import MONGO_COLLECTION_MATCHES
from config import db


OUTPUT_MD = Path(__file__).parent / "validation_200_patterns.md"
RANDOM_SEED = 42


def pick_test_matches(n_serie_a: int = 100, n_other: int = 100,
                      seasons: list = None) -> list[dict]:
    if seasons is None:
        seasons = ["2023-24", "2024-25"]
    coll = db[MONGO_COLLECTION_MATCHES]
    rng = random.Random(RANDOM_SEED)
    serie_a = list(coll.find({"lega": "I1", "stagione": {"$in": seasons}}))
    others = list(coll.find({"lega": {"$ne": "I1"}, "stagione": {"$in": seasons}}))
    return rng.sample(serie_a, min(n_serie_a, len(serie_a))) + rng.sample(others, min(n_other, len(others)))


def main():
    print("[load] caricamento dataset...")
    dataset = load_dataset_extended()
    print(f"[load] {len(dataset)} partite\n")

    test_matches = pick_test_matches(n_serie_a=100, n_other=100,
                                      seasons=["2023-24", "2024-25"])
    print(f"[pick] {len(test_matches)} partite test\n")

    # Calcolo per ogni partita
    print("[compute] elaborazione...")
    pattern_goal_active = []
    pattern_nogoal_active = []
    all_pronostici = []  # per baseline

    for target_doc in tqdm(test_matches, desc="processing"):
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

        record = {
            "home": target_doc["home_team"],
            "away": target_doc["away_team"],
            "lega": target_lega,
            "stagione": target_doc.get("stagione"),
            "data": target_doc["data_partita"].strftime("%Y-%m-%d"),
            "real_score": real_score,
            "real_1x2": real_1x2,
            "real_ou25": real_ou25,
            "real_gg": real_gg,
            "x_pct": mkt["1x2"]["X"],
            "over25_pct": mkt["over_under_2_5"]["over"],
            "media_tot": mkt["medie"]["totali"],
            "media_casa": mkt["medie"]["casa"],
            "media_osp": mkt["medie"]["ospite"],
            "re_scores": re_scores,
            "re_hit": real_score in re_scores,
        }
        all_pronostici.append(record)

        # Check pattern
        goal_active, _ = detect_pattern_goal(mkt)
        nogoal_active, _ = detect_pattern_nogoal(mkt)
        if goal_active:
            pattern_goal_active.append(record)
        if nogoal_active:
            pattern_nogoal_active.append(record)

    n_total = len(all_pronostici)
    print(f"\n[done] {n_total} pronostici emessi\n")

    # Stats baseline
    n_goal_real = sum(1 for r in all_pronostici if r["real_gg"] == "goal")
    n_nogoal_real = sum(1 for r in all_pronostici if r["real_gg"] == "nogoal")
    n_over_real = sum(1 for r in all_pronostici if r["real_ou25"] == "over")

    # Stats Pattern Goal
    n_g = len(pattern_goal_active)
    if n_g > 0:
        goal_hit = sum(1 for r in pattern_goal_active if r["real_gg"] == "goal")
        over_hit = sum(1 for r in pattern_goal_active if r["real_ou25"] == "over")
        sign1or2_hit = sum(1 for r in pattern_goal_active if r["real_1x2"] != "D")
        re_hit_g = sum(1 for r in pattern_goal_active if r["re_hit"])
    else:
        goal_hit = over_hit = sign1or2_hit = re_hit_g = 0

    # Stats Pattern NoGoal
    n_ng = len(pattern_nogoal_active)
    if n_ng > 0:
        nogoal_hit = sum(1 for r in pattern_nogoal_active if r["real_gg"] == "nogoal")
        under_hit = sum(1 for r in pattern_nogoal_active if r["real_ou25"] == "under")
        re_hit_ng = sum(1 for r in pattern_nogoal_active if r["re_hit"])
    else:
        nogoal_hit = under_hit = re_hit_ng = 0

    # Output MD
    md = ["# Validazione pattern Goal/NoGoal — 200 partite\n"]
    md.append(f"**Test set**: {n_total} pronostici (100 Serie A + 100 altre leghe, stagioni 2023-24 + 2024-25, seed={RANDOM_SEED})\n")
    md.append("\n## Baseline (su tutto il test set)\n")
    md.append(f"- Goal: {n_goal_real}/{n_total} = **{n_goal_real/n_total*100:.1f}%**")
    md.append(f"- NoGoal: {n_nogoal_real}/{n_total} = **{n_nogoal_real/n_total*100:.1f}%**")
    md.append(f"- Over 2.5: {n_over_real}/{n_total} = **{n_over_real/n_total*100:.1f}%**\n")

    # Pattern Goal
    md.append("\n## Pattern Goal: X<30% AND Over 2.5>65%\n")
    md.append(f"**Partite attive**: {n_g}/{n_total} ({n_g/n_total*100:.1f}%)\n")
    if n_g >= 5:
        md.append("\n### Hit rate sul pattern attivo\n")
        md.append("| Mercato | Hit | Hit rate | vs Baseline |")
        md.append("|---|---|---|---|")
        md.append(f"| **Goal** | {goal_hit}/{n_g} | **{goal_hit/n_g*100:.1f}%** | vs {n_goal_real/n_total*100:.1f}% (+{goal_hit/n_g*100 - n_goal_real/n_total*100:.1f}) |")
        md.append(f"| Over 2.5 | {over_hit}/{n_g} | **{over_hit/n_g*100:.1f}%** | vs {n_over_real/n_total*100:.1f}% (+{over_hit/n_g*100 - n_over_real/n_total*100:.1f}) |")
        md.append(f"| 1 OR 2 (no X) | {sign1or2_hit}/{n_g} | **{sign1or2_hit/n_g*100:.1f}%** | — |")
        md.append(f"| RE top 5 | {re_hit_g}/{n_g} | **{re_hit_g/n_g*100:.1f}%** | — |")

    # Pattern NoGoal
    md.append("\n## Pattern NoGoal: media_tot<2.5 AND min_squadra<0.9\n")
    md.append(f"**Partite attive**: {n_ng}/{n_total} ({n_ng/n_total*100:.1f}%)\n")
    if n_ng >= 5:
        md.append("\n### Hit rate sul pattern attivo\n")
        md.append("| Mercato | Hit | Hit rate | vs Baseline |")
        md.append("|---|---|---|---|")
        md.append(f"| **NoGoal** | {nogoal_hit}/{n_ng} | **{nogoal_hit/n_ng*100:.1f}%** | vs {n_nogoal_real/n_total*100:.1f}% (+{nogoal_hit/n_ng*100 - n_nogoal_real/n_total*100:.1f}) |")
        md.append(f"| Under 2.5 | {under_hit}/{n_ng} | **{under_hit/n_ng*100:.1f}%** | — |")
        md.append(f"| RE top 5 | {re_hit_ng}/{n_ng} | **{re_hit_ng/n_ng*100:.1f}%** | — |")

    # Dettaglio partite Pattern Goal
    md.append("\n## Dettaglio partite Pattern Goal attivo\n")
    md.append("| Lega | Data | Partita | Score | Reale (1X2/OU/GG) | X% | Over% |")
    md.append("|---|---|---|---|---|---|---|")
    for r in pattern_goal_active:
        md.append(f"| {r['lega']} | {r['data']} | {r['home']} vs {r['away']} | {r['real_score']} | {r['real_1x2']}/{r['real_ou25']}/{r['real_gg']} | {r['x_pct']*100:.1f}% | {r['over25_pct']*100:.1f}% |")

    # Dettaglio partite Pattern NoGoal
    md.append("\n## Dettaglio partite Pattern NoGoal attivo\n")
    md.append("| Lega | Data | Partita | Score | Reale (1X2/OU/GG) | media_tot | min_squadra |")
    md.append("|---|---|---|---|---|---|---|")
    for r in pattern_nogoal_active:
        min_sq = min(r["media_casa"], r["media_osp"])
        md.append(f"| {r['lega']} | {r['data']} | {r['home']} vs {r['away']} | {r['real_score']} | {r['real_1x2']}/{r['real_ou25']}/{r['real_gg']} | {r['media_tot']:.2f} | {min_sq:.2f} |")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[done] output: {OUTPUT_MD}")

    # Sintesi a video
    print(f"\n=== SINTESI VALIDATION 200 PARTITE ===")
    print(f"Test set: {n_total} pronostici")
    print(f"Baseline Goal: {n_goal_real/n_total*100:.1f}% | NoGoal: {n_nogoal_real/n_total*100:.1f}%")
    print()
    print(f"Pattern Goal (X<30 AND Over>65): {n_g} attive")
    if n_g >= 5:
        print(f"  Goal hit:    {goal_hit}/{n_g} = {goal_hit/n_g*100:.1f}%")
        print(f"  Over hit:    {over_hit}/{n_g} = {over_hit/n_g*100:.1f}%")
        print(f"  1 OR 2:      {sign1or2_hit}/{n_g} = {sign1or2_hit/n_g*100:.1f}%")
    print()
    print(f"Pattern NoGoal (media_tot<2.5 AND min<0.9): {n_ng} attive")
    if n_ng >= 5:
        print(f"  NoGoal hit:  {nogoal_hit}/{n_ng} = {nogoal_hit/n_ng*100:.1f}%")
        print(f"  Under hit:   {under_hit}/{n_ng} = {under_hit/n_ng*100:.1f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
