"""
Validazione COMPLETA su 200 partite.

Testa TUTTO il sistema:
- 1X2 baseline (sempre dominante) e filtrato (DC>=71%)
- DC (no filtro)
- O/U 1.5, 2.5, 3.5 (baseline e filtrati con soglie 65.5/65.5/70.5)
- GG/NG (no filtro, baseline)
- MG (baseline e filtrato 65.5%)
- RE top 5
- Pattern Goal (X<30 AND Over>65)
- Pattern NoGoal (media_tot<2.5 AND min_squadra<0.9)

Output: validation_200_full.md
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
    compute_re_top5, emit_1x2_secco, emit_market_filtered,
    detect_pattern_goal, detect_pattern_nogoal,
    load_dataset_extended, MIN_PARTITE_PER_PRONOSTICO,
    DC_THRESHOLD_FOR_SECCO, MARKET_THRESHOLDS, MAX_SCORE,
)
from ai_engine.pattern_match.config import MONGO_COLLECTION_MATCHES
from config import db


OUTPUT_MD = Path(__file__).parent / "validation_200_full.md"
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


def main():
    print("[load] caricamento dataset...")
    dataset = load_dataset_extended()
    print(f"[load] {len(dataset)} partite\n")

    test_matches = pick_test_matches(n_serie_a=100, n_other=100,
                                      seasons=["2023-24", "2024-25"])
    print(f"[pick] {len(test_matches)} partite test (stagioni 2023-24 + 2024-25)\n")

    stats = Counter()
    pattern_goal_records = []
    pattern_nogoal_records = []
    pronostici_emessi = 0

    for target_doc in tqdm(test_matches, desc="full-validation"):
        target_lega = target_doc["lega"]
        target_ext = extract_extended_features(target_doc["feature_vector"], target_lega)
        real_outcome = target_doc["outcome"]
        real_total = real_outcome["goals_home"] + real_outcome["goals_away"]
        real_1x2 = real_outcome["result_1x2"]
        real_ou15 = "over" if real_total >= 2 else "under"
        real_ou25 = "over" if real_total >= 3 else "under"
        real_ou35 = "over" if real_total >= 4 else "under"
        real_gg = "goal" if (real_outcome["goals_home"] >= 1 and real_outcome["goals_away"] >= 1) else "nogoal"
        real_score = real_outcome["ft_score"]
        real_dc_set = real_dc(real_1x2)
        real_mg_set = real_mg(real_total)

        pool_info = compute_pool(target_ext, dataset, exclude_uid=target_doc["match_uid"])
        if pool_info["n"] < MIN_PARTITE_PER_PRONOSTICO:
            continue
        pronostici_emessi += 1

        mkt = compute_markets_for_pool(pool_info["partite"])
        re_top = compute_re_top5(pool_info["partite"], max_results=5)
        re_scores = [r["score"] for r in re_top]

        # 1X2 baseline (sempre dominante)
        d_1x2 = mkt["1x2"]
        sign = max(d_1x2, key=d_1x2.get)
        pred_1x2 = {"1": "H", "X": "D", "2": "A"}[sign]
        hit_1x2_base = (pred_1x2 == real_1x2)

        # 1X2 filtrato (con DC>=71%)
        secco_sign, _ = emit_1x2_secco(mkt)
        emit_secco = secco_sign is not None

        # DC
        p_dc = max(mkt["doppia_chance"], key=mkt["doppia_chance"].get)
        hit_dc = (p_dc in real_dc_set)

        # O/U 1.5
        d_ou15 = mkt["over_under_1_5"]
        p_ou15 = max(d_ou15, key=d_ou15.get)
        hit_ou15 = (p_ou15 == real_ou15)
        ou15_filt, _, _ = emit_market_filtered(mkt, "over_under_1_5")

        # O/U 2.5
        d_ou25 = mkt["over_under_2_5"]
        p_ou25 = max(d_ou25, key=d_ou25.get)
        hit_ou25 = (p_ou25 == real_ou25)
        ou25_filt, _, _ = emit_market_filtered(mkt, "over_under_2_5")

        # O/U 3.5
        d_ou35 = mkt["over_under_3_5"]
        p_ou35 = max(d_ou35, key=d_ou35.get)
        hit_ou35 = (p_ou35 == real_ou35)
        ou35_filt, _, _ = emit_market_filtered(mkt, "over_under_3_5")

        # GG/NG
        p_gg = max(mkt["goal_nogoal"], key=mkt["goal_nogoal"].get)
        hit_gg = (p_gg == real_gg)

        # MG
        p_mg = max(mkt["multigol"], key=mkt["multigol"].get)
        hit_mg = (p_mg in real_mg_set)
        mg_filt, _, _ = emit_market_filtered(mkt, "multigol")

        # RE top 5
        hit_re = real_score in re_scores

        # Stats baseline
        stats["1x2_total"] += 1
        if hit_1x2_base: stats["1x2_hit"] += 1
        # 1X2 filtrato
        if emit_secco:
            stats["1x2_filt_total"] += 1
            if hit_1x2_base: stats["1x2_filt_hit"] += 1
        stats["dc_total"] += 1
        if hit_dc: stats["dc_hit"] += 1
        stats["ou15_total"] += 1
        if hit_ou15: stats["ou15_hit"] += 1
        if ou15_filt is not None:
            stats["ou15_filt_total"] += 1
            if ou15_filt == real_ou15: stats["ou15_filt_hit"] += 1
        stats["ou25_total"] += 1
        if hit_ou25: stats["ou25_hit"] += 1
        if ou25_filt is not None:
            stats["ou25_filt_total"] += 1
            if ou25_filt == real_ou25: stats["ou25_filt_hit"] += 1
        stats["ou35_total"] += 1
        if hit_ou35: stats["ou35_hit"] += 1
        if ou35_filt is not None:
            stats["ou35_filt_total"] += 1
            if ou35_filt == real_ou35: stats["ou35_filt_hit"] += 1
        stats["gg_total"] += 1
        if hit_gg: stats["gg_hit"] += 1
        stats["mg_total"] += 1
        if hit_mg: stats["mg_hit"] += 1
        if mg_filt is not None:
            stats["mg_filt_total"] += 1
            if mg_filt in real_mg_set: stats["mg_filt_hit"] += 1
        stats["re_total"] += 1
        if hit_re: stats["re_hit"] += 1

        # Pattern Goal
        goal_active, _ = detect_pattern_goal(mkt)
        if goal_active:
            pattern_goal_records.append({
                "real_gg": real_gg, "real_ou25": real_ou25,
                "real_1x2": real_1x2, "re_hit": hit_re,
            })

        # Pattern NoGoal
        nogoal_active, _ = detect_pattern_nogoal(mkt)
        if nogoal_active:
            pattern_nogoal_records.append({
                "real_gg": real_gg, "real_ou25": real_ou25,
                "real_1x2": real_1x2, "re_hit": hit_re,
            })

    # Output
    md = ["# Validazione COMPLETA su 200 partite\n"]
    md.append(f"**Test set**: {pronostici_emessi} pronostici (100 Serie A + 100 altre leghe, stagioni 2023-24 + 2024-25, seed={RANDOM_SEED})\n")

    md.append("\n## Hit rate per mercato — baseline vs filtrato\n")
    md.append("| Mercato | Baseline Hit | Baseline % | Filtrato Hit | Filtrato % |")
    md.append("|---|---|---|---|---|")
    rows = [
        ("1X2 (DC>=71%)", "1x2", "1x2_filt"),
        ("O/U 1.5 (>=65.5%)", "ou15", "ou15_filt"),
        ("O/U 2.5 (>=65.5%)", "ou25", "ou25_filt"),
        ("O/U 3.5 (>=70.5%)", "ou35", "ou35_filt"),
        ("MG (>=65.5%)", "mg", "mg_filt"),
    ]
    for label, base_key, filt_key in rows:
        h = stats[f"{base_key}_hit"]
        t = stats[f"{base_key}_total"]
        rate = h/t*100 if t else 0
        h_f = stats[f"{filt_key}_hit"]
        t_f = stats[f"{filt_key}_total"]
        rate_f = h_f/t_f*100 if t_f else 0
        md.append(f"| {label} | {h}/{t} | {rate:.1f}% | {h_f}/{t_f} | **{rate_f:.1f}%** |")
    md.append(f"| DC (no filtro) | {stats['dc_hit']}/{stats['dc_total']} | **{stats['dc_hit']/stats['dc_total']*100:.1f}%** | — | — |")
    md.append(f"| GG/NG (no filtro) | {stats['gg_hit']}/{stats['gg_total']} | **{stats['gg_hit']/stats['gg_total']*100:.1f}%** | — | — |")
    md.append(f"| RE top 5 | {stats['re_hit']}/{stats['re_total']} | **{stats['re_hit']/stats['re_total']*100:.1f}%** | — | — |")

    # Pattern Goal
    n_g = len(pattern_goal_records)
    md.append(f"\n## Pattern GOAL (X<30% AND Over 2.5>65%)\n")
    md.append(f"**Partite attive**: {n_g}/{pronostici_emessi} ({n_g/pronostici_emessi*100:.1f}%)\n")
    if n_g >= 5:
        goal_hit = sum(1 for r in pattern_goal_records if r["real_gg"] == "goal")
        over_hit = sum(1 for r in pattern_goal_records if r["real_ou25"] == "over")
        sign1or2_hit = sum(1 for r in pattern_goal_records if r["real_1x2"] != "D")
        re_hit_g = sum(1 for r in pattern_goal_records if r["re_hit"])
        md.append("| Mercato | Hit | Hit rate |")
        md.append("|---|---|---|")
        md.append(f"| **Goal** | {goal_hit}/{n_g} | **{goal_hit/n_g*100:.1f}%** |")
        md.append(f"| Over 2.5 | {over_hit}/{n_g} | **{over_hit/n_g*100:.1f}%** |")
        md.append(f"| 1 OR 2 | {sign1or2_hit}/{n_g} | **{sign1or2_hit/n_g*100:.1f}%** |")
        md.append(f"| RE top 5 | {re_hit_g}/{n_g} | **{re_hit_g/n_g*100:.1f}%** |")

    # Pattern NoGoal
    n_ng = len(pattern_nogoal_records)
    md.append(f"\n## Pattern NOGOAL (media_tot<2.5 AND min_squadra<0.9)\n")
    md.append(f"**Partite attive**: {n_ng}/{pronostici_emessi} ({n_ng/pronostici_emessi*100:.1f}%)\n")
    if n_ng >= 5:
        nogoal_hit = sum(1 for r in pattern_nogoal_records if r["real_gg"] == "nogoal")
        under_hit = sum(1 for r in pattern_nogoal_records if r["real_ou25"] == "under")
        re_hit_ng = sum(1 for r in pattern_nogoal_records if r["re_hit"])
        md.append("| Mercato | Hit | Hit rate |")
        md.append("|---|---|---|")
        md.append(f"| **NoGoal** | {nogoal_hit}/{n_ng} | **{nogoal_hit/n_ng*100:.1f}%** |")
        md.append(f"| Under 2.5 | {under_hit}/{n_ng} | **{under_hit/n_ng*100:.1f}%** |")
        md.append(f"| RE top 5 | {re_hit_ng}/{n_ng} | **{re_hit_ng/n_ng*100:.1f}%** |")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[done] output: {OUTPUT_MD}")
    print(f"\n=== SINTESI VALIDATION 200 PARTITE ===")
    print(f"Test set: {pronostici_emessi} pronostici")
    print(f"\nBaseline:")
    print(f"  1X2:    {stats['1x2_hit']}/{stats['1x2_total']} = {stats['1x2_hit']/stats['1x2_total']*100:.1f}%  | filt: {stats['1x2_filt_hit']}/{stats['1x2_filt_total']} = {stats['1x2_filt_hit']/max(stats['1x2_filt_total'],1)*100:.1f}%")
    print(f"  DC:     {stats['dc_hit']}/{stats['dc_total']} = {stats['dc_hit']/stats['dc_total']*100:.1f}%")
    print(f"  OU 2.5: {stats['ou25_hit']}/{stats['ou25_total']} = {stats['ou25_hit']/stats['ou25_total']*100:.1f}%  | filt: {stats['ou25_filt_hit']}/{stats['ou25_filt_total']} = {stats['ou25_filt_hit']/max(stats['ou25_filt_total'],1)*100:.1f}%")
    print(f"  GG/NG:  {stats['gg_hit']}/{stats['gg_total']} = {stats['gg_hit']/stats['gg_total']*100:.1f}%")
    print(f"  RE:     {stats['re_hit']}/{stats['re_total']} = {stats['re_hit']/stats['re_total']*100:.1f}%")
    print()
    print(f"Pattern GOAL (X<30 AND Over>65): {n_g} attive")
    if n_g >= 5:
        goal_hit = sum(1 for r in pattern_goal_records if r["real_gg"] == "goal")
        print(f"  Goal: {goal_hit}/{n_g} = {goal_hit/n_g*100:.1f}%")
    print(f"Pattern NOGOAL (media<2.5 AND min<0.9): {n_ng} attive")
    if n_ng >= 5:
        nogoal_hit = sum(1 for r in pattern_nogoal_records if r["real_gg"] == "nogoal")
        print(f"  NoGoal: {nogoal_hit}/{n_ng} = {nogoal_hit/n_ng*100:.1f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
