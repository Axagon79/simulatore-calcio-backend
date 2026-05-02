"""
Test soglia per ogni mercato binario/categorico.

Per O/U 1.5, O/U 2.5, O/U 3.5, GG/NG, MG:
- Provo soglie da 50.0% a 90.0% step 0.5% (81 valori)
- Logica: emetto la predizione solo se la % dominante e' >= soglia
- Per ogni soglia: quanti pronostici emessi e hit rate

Output: validation_all_thresholds.md (tabella per ogni mercato)
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


OUTPUT_MD = Path(__file__).parent / "validation_all_thresholds.md"
RANDOM_SEED = 42


def pick_test_matches(n_serie_a: int = 25, n_other: int = 25,
                      season: str = "2024-25") -> list[dict]:
    coll = db[MONGO_COLLECTION_MATCHES]
    rng = random.Random(RANDOM_SEED)
    serie_a = list(coll.find({"lega": "I1", "stagione": season}))
    others = list(coll.find({"lega": {"$ne": "I1"}, "stagione": season}))
    return rng.sample(serie_a, n_serie_a) + rng.sample(others, n_other)


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

    test_matches = pick_test_matches()
    print(f"[pick] {len(test_matches)} partite test\n")

    # Calcolo i mercati per ogni partita test (una sola volta)
    print("[compute] calcolo mercati...")
    test_predictions = []
    for target_doc in tqdm(test_matches, desc="markets"):
        target_lega = target_doc["lega"]
        target_ext = extract_extended_features(target_doc["feature_vector"], target_lega)
        real_outcome = target_doc["outcome"]
        real_total = real_outcome["goals_home"] + real_outcome["goals_away"]
        real_ou15 = "over" if real_total >= 2 else "under"
        real_ou25 = "over" if real_total >= 3 else "under"
        real_ou35 = "over" if real_total >= 4 else "under"
        real_gg = "goal" if (real_outcome["goals_home"] >= 1 and real_outcome["goals_away"] >= 1) else "nogoal"
        real_mg_set = real_mg(real_total)

        pool_info = compute_pool(target_ext, dataset, exclude_uid=target_doc["match_uid"])
        if pool_info["n"] < MIN_PARTITE_PER_PRONOSTICO:
            continue
        mkt = compute_markets_for_pool(pool_info["partite"])

        test_predictions.append({
            "real_ou15": real_ou15,
            "real_ou25": real_ou25,
            "real_ou35": real_ou35,
            "real_gg": real_gg,
            "real_mg_set": real_mg_set,
            "ou15": mkt["over_under_1_5"],
            "ou25": mkt["over_under_2_5"],
            "ou35": mkt["over_under_3_5"],
            "gg_ng": mkt["goal_nogoal"],
            "multigol": mkt["multigol"],
        })

    n_test = len(test_predictions)
    print(f"\n[compute] {n_test} pronostici emessi\n")

    # Soglie da testare
    thresholds = [round(50.0 + 0.5 * i, 1) for i in range(81)]

    # Definisco i mercati da testare
    markets_to_test = [
        {
            "label": "O/U 1.5",
            "field": "ou15",
            "real_field": "real_ou15",
            "type": "binary",  # 2 opzioni: over/under
        },
        {
            "label": "O/U 2.5",
            "field": "ou25",
            "real_field": "real_ou25",
            "type": "binary",
        },
        {
            "label": "O/U 3.5",
            "field": "ou35",
            "real_field": "real_ou35",
            "type": "binary",
        },
        {
            "label": "GG/NG",
            "field": "gg_ng",
            "real_field": "real_gg",
            "type": "binary",  # goal/nogoal
        },
        {
            "label": "MG",
            "field": "multigol",
            "real_field": "real_mg_set",
            "type": "multi",  # 6 range, hit se predetto in real_mg_set
        },
    ]

    # Calcola hit rate per ogni mercato e ogni soglia
    print("[grid] esecuzione 81 soglie x 5 mercati...")
    market_results = {}

    for mkt_def in markets_to_test:
        results = []
        for thr_pct in thresholds:
            thr = thr_pct / 100.0
            emessi = 0
            hit = 0
            for p in test_predictions:
                d = p[mkt_def["field"]]
                # Trovo dominante e % corrispondente
                pred = max(d, key=d.get)
                pred_pct = d[pred]

                if pred_pct < thr:
                    continue

                emessi += 1
                if mkt_def["type"] == "binary":
                    if pred == p[mkt_def["real_field"]]:
                        hit += 1
                else:  # multi (MG)
                    if pred in p[mkt_def["real_field"]]:
                        hit += 1

            rate = hit / emessi * 100 if emessi > 0 else 0
            results.append({
                "soglia_pct": thr_pct,
                "emessi": emessi,
                "hit": hit,
                "rate": rate,
            })
        market_results[mkt_def["label"]] = results

    # Output MD
    md = ["# Test soglie iper-granulari (0.5%) per tutti i mercati\n"]
    md.append(f"**Test set**: {len(test_matches)} partite (seed={RANDOM_SEED}, {n_test} pronostici emessi)\n")
    md.append("\n## Logica\n")
    md.append("Per ogni mercato: emetto la predizione solo se la % dominante è >= soglia.\n")
    md.append("Se sotto soglia: non emetto quella predizione (gli altri mercati restano emessi).\n")

    for mkt_def in markets_to_test:
        label = mkt_def["label"]
        results = market_results[label]
        # Baseline (soglia 0% → tutto emesso)
        baseline_emessi = n_test
        baseline_hit = sum(1 for p in test_predictions
                           if (max(p[mkt_def["field"]], key=p[mkt_def["field"]].get)
                               in (p[mkt_def["real_field"]] if mkt_def["type"] == "multi"
                                   else {p[mkt_def["real_field"]]})))
        baseline_rate = baseline_hit / baseline_emessi * 100

        md.append(f"\n---\n# Mercato: {label}\n")
        md.append(f"**Baseline (senza filtro)**: {baseline_hit}/{baseline_emessi} = **{baseline_rate:.1f}%**\n")

        # Top 10 soglie con almeno 10 emessi
        sorted_by_rate = sorted(results, key=lambda x: (-x["rate"], -x["emessi"]))
        md.append(f"\n## Top 10 soglie per {label} (con almeno 10 emessi)\n")
        md.append("| Rank | Soglia | Emessi | Hit | Hit rate |")
        md.append("|---|---|---|---|---|")
        rank = 1
        for r in sorted_by_rate:
            if r["emessi"] < 10:
                continue
            md.append(f"| {rank} | {r['soglia_pct']:.1f}% | {r['emessi']}/{n_test} | {r['hit']} | **{r['rate']:.1f}%** |")
            rank += 1
            if rank > 10:
                break

        # Tabella completa
        md.append(f"\n## Tabella completa {label} (81 soglie)\n")
        md.append("| Soglia | Emessi | Hit | Hit rate |")
        md.append("|---|---|---|---|")
        for r in results:
            md.append(f"| {r['soglia_pct']:.1f}% | {r['emessi']}/{n_test} | {r['hit']} | **{r['rate']:.1f}%** |")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[done] output: {OUTPUT_MD}")

    # Sintesi a video
    print(f"\n=== SINTESI per ogni mercato (top 1 con almeno 10 emessi) ===")
    for mkt_def in markets_to_test:
        label = mkt_def["label"]
        results = market_results[label]
        sorted_by_rate = sorted(results, key=lambda x: (-x["rate"], -x["emessi"]))
        for r in sorted_by_rate:
            if r["emessi"] >= 10:
                print(f"  {label:10s}: soglia {r['soglia_pct']:.1f}% → {r['hit']}/{r['emessi']} = {r['rate']:.1f}%")
                break

    return 0


if __name__ == "__main__":
    sys.exit(main())
