"""
Test pattern: convergenza X (pareggio) >= 35% E Over 2.5 >= 65.5%.

Logica: quando il sistema dice "alta probabilita di pareggio" + "alta probabilita
di tante reti", cerco partite tipo 1-1, 2-2, 3-2 ecc. — pareggi prolifici.

Misuro:
- Quante partite attivano il pattern
- Hit rate per X reale, Over 2.5 reale, Goal reale
- Frequenza di 1-1 e 2-2 nei top 5 RE
- Confronto vs hit rate baseline (no pattern)

Output: validation_x_over_pattern.md
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
    compute_re_top5, load_dataset_extended, MIN_PARTITE_PER_PRONOSTICO,
)
from ai_engine.pattern_match.config import MONGO_COLLECTION_MATCHES
from config import db


OUTPUT_MD = Path(__file__).parent / "validation_x_over_pattern.md"
RANDOM_SEED = 42

# Soglie del pattern
THRESHOLD_X = 0.35
THRESHOLD_OVER25 = 0.655


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

    print("[compute] elaborazione...")
    pattern_active = []  # partite con pattern attivo
    pattern_inactive = []  # tutte le altre

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
        x_pct = mkt["1x2"]["X"]
        over25_pct = mkt["over_under_2_5"]["over"]

        re_top = compute_re_top5(pool_info["partite"], max_results=5)
        re_scores = [r["score"] for r in re_top]

        is_active = (x_pct >= THRESHOLD_X) and (over25_pct >= THRESHOLD_OVER25)

        record = {
            "match_uid": target_doc["match_uid"],
            "home": target_doc["home_team"],
            "away": target_doc["away_team"],
            "real_score": real_score,
            "real_1x2": real_1x2,
            "real_ou25": real_ou25,
            "real_gg": real_gg,
            "x_pct": x_pct,
            "over25_pct": over25_pct,
            "re_scores": re_scores,
            "has_1_1": "1-1" in re_scores,
            "has_2_2": "2-2" in re_scores,
        }

        if is_active:
            pattern_active.append(record)
        else:
            pattern_inactive.append(record)

    n_active = len(pattern_active)
    n_inactive = len(pattern_inactive)
    n_total = n_active + n_inactive
    print(f"\n[compute] {n_total} pronostici ({n_active} pattern attivi, {n_inactive} non attivi)\n")

    # Calcolo hit rate per ogni gruppo
    def hit_stats(rows: list[dict]):
        if not rows:
            return {}
        x_hit = sum(1 for r in rows if r["real_1x2"] == "D")
        over_hit = sum(1 for r in rows if r["real_ou25"] == "over")
        goal_hit = sum(1 for r in rows if r["real_gg"] == "goal")
        re_1_1_in_top = sum(1 for r in rows if r["has_1_1"])
        re_2_2_in_top = sum(1 for r in rows if r["has_2_2"])
        re_hit_real = sum(1 for r in rows if r["real_score"] in r["re_scores"])
        n = len(rows)
        return {
            "n": n,
            "x_hit": x_hit, "x_rate": x_hit / n * 100,
            "over_hit": over_hit, "over_rate": over_hit / n * 100,
            "goal_hit": goal_hit, "goal_rate": goal_hit / n * 100,
            "re_1_1_top": re_1_1_in_top, "re_1_1_rate": re_1_1_in_top / n * 100,
            "re_2_2_top": re_2_2_in_top, "re_2_2_rate": re_2_2_in_top / n * 100,
            "re_hit": re_hit_real, "re_hit_rate": re_hit_real / n * 100,
        }

    stats_active = hit_stats(pattern_active)
    stats_inactive = hit_stats(pattern_inactive)
    stats_all = hit_stats(pattern_active + pattern_inactive)

    # Output MD
    md = ["# Pattern: X >= 35% AND Over 2.5 >= 65.5%\n"]
    md.append(f"**Test set**: {n_total} partite (seed={RANDOM_SEED})\n")
    md.append(f"**Pattern attivo**: {n_active} partite ({n_active/n_total*100:.1f}%)\n")
    md.append(f"**Pattern non attivo**: {n_inactive} partite ({n_inactive/n_total*100:.1f}%)\n")

    md.append("\n## Confronto hit rate\n")
    md.append("| Mercato | Pattern ATTIVO | Pattern NON attivo | Tutto (no filtro) |")
    md.append("|---|---|---|---|")
    if n_active > 0:
        md.append(f"| X (pareggio) | {stats_active['x_hit']}/{stats_active['n']} = **{stats_active['x_rate']:.1f}%** | {stats_inactive['x_hit']}/{stats_inactive['n']} = {stats_inactive['x_rate']:.1f}% | {stats_all['x_hit']}/{stats_all['n']} = {stats_all['x_rate']:.1f}% |")
        md.append(f"| Over 2.5 | {stats_active['over_hit']}/{stats_active['n']} = **{stats_active['over_rate']:.1f}%** | {stats_inactive['over_hit']}/{stats_inactive['n']} = {stats_inactive['over_rate']:.1f}% | {stats_all['over_hit']}/{stats_all['n']} = {stats_all['over_rate']:.1f}% |")
        md.append(f"| Goal | {stats_active['goal_hit']}/{stats_active['n']} = **{stats_active['goal_rate']:.1f}%** | {stats_inactive['goal_hit']}/{stats_inactive['n']} = {stats_inactive['goal_rate']:.1f}% | {stats_all['goal_hit']}/{stats_all['n']} = {stats_all['goal_rate']:.1f}% |")
        md.append(f"| 1-1 in top 5 RE | {stats_active['re_1_1_top']}/{stats_active['n']} = **{stats_active['re_1_1_rate']:.1f}%** | {stats_inactive['re_1_1_top']}/{stats_inactive['n']} = {stats_inactive['re_1_1_rate']:.1f}% | — |")
        md.append(f"| 2-2 in top 5 RE | {stats_active['re_2_2_top']}/{stats_active['n']} = **{stats_active['re_2_2_rate']:.1f}%** | {stats_inactive['re_2_2_top']}/{stats_inactive['n']} = {stats_inactive['re_2_2_rate']:.1f}% | — |")
        md.append(f"| RE reale in top 5 | {stats_active['re_hit']}/{stats_active['n']} = **{stats_active['re_hit_rate']:.1f}%** | {stats_inactive['re_hit']}/{stats_inactive['n']} = {stats_inactive['re_hit_rate']:.1f}% | — |")

    # Dettaglio partite con pattern attivo
    md.append("\n## Dettaglio partite con pattern ATTIVO\n")
    md.append("| Partita | Reale | X% | Over% | RE Top 5 |")
    md.append("|---|---|---|---|---|")
    for r in pattern_active:
        md.append(f"| {r['home']} vs {r['away']} ({r['real_score']}) | {r['real_1x2']} / {r['real_ou25']} / {r['real_gg']} | {r['x_pct']*100:.1f}% | {r['over25_pct']*100:.1f}% | {','.join(r['re_scores'])} |")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[done] output: {OUTPUT_MD}")

    # Sintesi a video
    print(f"\n=== SINTESI pattern X≥{THRESHOLD_X*100:.0f}% E Over2.5≥{THRESHOLD_OVER25*100:.1f}% ===")
    print(f"Pattern attivo:     {n_active}/{n_total} partite ({n_active/n_total*100:.1f}%)")
    if n_active > 0:
        print(f"\nNel pattern attivo ({n_active} partite):")
        print(f"  X reale:        {stats_active['x_hit']}/{n_active} = {stats_active['x_rate']:.1f}%")
        print(f"  Over reale:     {stats_active['over_hit']}/{n_active} = {stats_active['over_rate']:.1f}%")
        print(f"  Goal reale:     {stats_active['goal_hit']}/{n_active} = {stats_active['goal_rate']:.1f}%")
        print(f"  1-1 in top 5:   {stats_active['re_1_1_top']}/{n_active} = {stats_active['re_1_1_rate']:.1f}%")
        print(f"  2-2 in top 5:   {stats_active['re_2_2_top']}/{n_active} = {stats_active['re_2_2_rate']:.1f}%")
        print(f"  RE reale top 5: {stats_active['re_hit']}/{n_active} = {stats_active['re_hit_rate']:.1f}%")
        print(f"\nVS pattern non attivo ({n_inactive} partite):")
        print(f"  X reale:        {stats_inactive['x_hit']}/{n_inactive} = {stats_inactive['x_rate']:.1f}%")
        print(f"  Over reale:     {stats_inactive['over_hit']}/{n_inactive} = {stats_inactive['over_rate']:.1f}%")
        print(f"  Goal reale:     {stats_inactive['goal_hit']}/{n_inactive} = {stats_inactive['goal_rate']:.1f}%")
    else:
        print("Nessuna partita ha attivato il pattern. Soglie troppo strette.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
