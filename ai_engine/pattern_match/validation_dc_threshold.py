"""
Test soglia DC per emettere il segno 1X2 secco.

Logica: emetto il segno secco solo se le 2 DC che lo contengono sono
entrambe sopra una soglia X (segno_secco_filter).
- Segno 1: richiede DC 1X >= X e DC 12 >= X
- Segno X: richiede DC 1X >= X e DC X2 >= X
- Segno 2: richiede DC X2 >= X e DC 12 >= X

Provo 81 soglie da 50.0% a 90.0% step 0.5%.
Per ogni soglia: quanti pronostici emessi e hit rate sui 1X2 emessi.

Output: validation_dc_threshold.md (tabella completa)
"""
from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.weighted_engine import (
    extract_extended_features, compute_pool, compute_markets_for_pool,
    load_dataset_extended, MIN_PARTITE_PER_PRONOSTICO,
)
from ai_engine.pattern_match.config import MONGO_COLLECTION_MATCHES
from config import db


OUTPUT_MD = Path(__file__).parent / "validation_dc_threshold.md"
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

    # Calcolo una sola volta i mercati di ogni partita test
    print("[compute] calcolo mercati per ogni partita test (una volta sola)...")
    test_predictions = []
    for target_doc in tqdm(test_matches, desc="markets"):
        target_lega = target_doc["lega"]
        target_ext = extract_extended_features(target_doc["feature_vector"], target_lega)
        real_1x2 = target_doc["outcome"]["result_1x2"]

        pool_info = compute_pool(target_ext, dataset, exclude_uid=target_doc["match_uid"])
        if pool_info["n"] < MIN_PARTITE_PER_PRONOSTICO:
            continue
        mkt = compute_markets_for_pool(pool_info["partite"])

        # 1X2 dominante (per baseline)
        d_1x2 = mkt["1x2"]
        sign = max(d_1x2, key=d_1x2.get)
        pred_letter = {"1": "H", "X": "D", "2": "A"}[sign]

        test_predictions.append({
            "real_1x2": real_1x2,
            "pred_1x2_baseline": pred_letter,
            "1x2_dist": d_1x2,
            "dc_1x": mkt["doppia_chance"]["1X"],
            "dc_x2": mkt["doppia_chance"]["X2"],
            "dc_12": mkt["doppia_chance"]["12"],
        })

    n_test = len(test_predictions)
    print(f"\n[compute] {n_test} pronostici emessi (su {len(test_matches)})")

    # Baseline (senza filtro DC)
    baseline_hit = sum(1 for p in test_predictions if p["pred_1x2_baseline"] == p["real_1x2"])
    baseline_rate = baseline_hit / n_test * 100

    print(f"[baseline] 1X2 hit rate senza filtro DC: {baseline_hit}/{n_test} = {baseline_rate:.1f}%\n")

    # Provo soglie da 50.0% a 90.0% step 0.5%
    thresholds = [round(50.0 + 0.5 * i, 1) for i in range(81)]

    # Per ogni soglia: applico filtro e calcolo hit rate
    print("[grid] esecuzione 81 soglie...")
    results = []
    for thr_pct in thresholds:
        thr = thr_pct / 100.0

        emessi = 0
        hit = 0
        for p in test_predictions:
            sign = max(p["1x2_dist"], key=p["1x2_dist"].get)  # "1", "X", "2"
            # Mappo i requisiti DC per ogni segno
            if sign == "1":
                cond = (p["dc_1x"] >= thr and p["dc_12"] >= thr)
            elif sign == "X":
                cond = (p["dc_1x"] >= thr and p["dc_x2"] >= thr)
            else:  # "2"
                cond = (p["dc_x2"] >= thr and p["dc_12"] >= thr)

            if cond:
                emessi += 1
                pred_letter = {"1": "H", "X": "D", "2": "A"}[sign]
                if pred_letter == p["real_1x2"]:
                    hit += 1

        rate = hit / emessi * 100 if emessi > 0 else 0
        results.append({
            "soglia_pct": thr_pct,
            "emessi": emessi,
            "hit": hit,
            "rate": rate,
        })

    # Output MD
    md = ["# Test soglia DC per filtro 1X2 secco\n"]
    md.append(f"**Test set**: {len(test_matches)} partite (seed={RANDOM_SEED})\n")
    md.append(f"**Pronostici emessi senza filtro DC (baseline)**: {baseline_hit}/{n_test} = **{baseline_rate:.1f}%**\n")
    md.append("\n## Logica del filtro\n")
    md.append("Per emettere il segno secco, le 2 DC che contengono quel segno devono essere entrambe sopra la soglia.\n")
    md.append("- Segno 1 → richiede DC 1X ≥ soglia E DC 12 ≥ soglia")
    md.append("- Segno X → richiede DC 1X ≥ soglia E DC X2 ≥ soglia")
    md.append("- Segno 2 → richiede DC X2 ≥ soglia E DC 12 ≥ soglia\n")
    md.append("\n## Tabella risultati (81 soglie da 50.0% a 90.0%)\n")
    md.append("| Soglia DC | Emessi | Hit | Hit rate |")
    md.append("|---|---|---|---|")
    for r in results:
        md.append(f"| {r['soglia_pct']:.1f}% | {r['emessi']}/{n_test} | {r['hit']} | **{r['rate']:.1f}%** |")

    # Sintesi: top 5 soglie per hit rate
    sorted_by_rate = sorted(results, key=lambda x: (-x["rate"], -x["emessi"]))
    md.append("\n## Top 10 soglie per hit rate (con almeno 10 emessi)\n")
    md.append("| Rank | Soglia DC | Emessi | Hit | Hit rate |")
    md.append("|---|---|---|---|---|")
    rank = 1
    for r in sorted_by_rate:
        if r["emessi"] < 10:
            continue
        md.append(f"| {rank} | {r['soglia_pct']:.1f}% | {r['emessi']}/{n_test} | {r['hit']} | **{r['rate']:.1f}%** |")
        rank += 1
        if rank > 10:
            break

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[done] output: {OUTPUT_MD}")
    print(f"[done] Top 5 soglie con >=10 emessi:")
    rank = 1
    for r in sorted_by_rate:
        if r["emessi"] < 10:
            continue
        print(f"  {rank}. soglia {r['soglia_pct']:.1f}%: {r['hit']}/{r['emessi']} = {r['rate']:.1f}%")
        rank += 1
        if rank > 5:
            break

    return 0


if __name__ == "__main__":
    sys.exit(main())
