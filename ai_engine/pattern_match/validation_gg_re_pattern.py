"""
Test pattern coerenza GG/NG vs top 15 Risultati Esatti.

Per ogni partita test:
1. Calcolo predizione GG/NG dal pool
2. Estraggo top 15 RE (per frequenza)
3. Conto quanti dei 15 RE sono "coerenti" con la predizione GG/NG
   - Se predico Goal: RE coerente = entrambe le squadre hanno almeno 1 gol
   - Se predico NoGoal: RE coerente = almeno una squadra a 0
4. Raggruppo per livello di coerenza (15/15, 14/15, ..., 0/15)
5. Per ogni gruppo: hit rate GG/NG sul reale

Output: validation_gg_re_pattern.md
"""
from __future__ import annotations

import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.weighted_engine import (
    extract_extended_features, compute_pool, compute_markets_for_pool,
    compute_re_top5, load_dataset_extended, MIN_PARTITE_PER_PRONOSTICO,
)
from ai_engine.pattern_match.config import MONGO_COLLECTION_MATCHES
from config import db


OUTPUT_MD = Path(__file__).parent / "validation_gg_re_pattern.md"
RANDOM_SEED = 42
N_RE_TO_CHECK = 15


def pick_test_matches(n_serie_a: int = 25, n_other: int = 25,
                      season: str = "2024-25") -> list[dict]:
    coll = db[MONGO_COLLECTION_MATCHES]
    rng = random.Random(RANDOM_SEED)
    serie_a = list(coll.find({"lega": "I1", "stagione": season}))
    others = list(coll.find({"lega": {"$ne": "I1"}, "stagione": season}))
    return rng.sample(serie_a, n_serie_a) + rng.sample(others, n_other)


def is_re_coherent_with_gg(ft_score: str, gg_pred: str) -> bool:
    """
    Verifica se un risultato esatto e' coerente con la predizione GG/NG.
    - gg_pred = "goal" -> coerente se entrambe hanno >= 1 gol (es. 1-1, 2-1, 3-2)
    - gg_pred = "nogoal" -> coerente se almeno una a 0 (es. 0-0, 1-0, 2-0, 0-1)
    """
    try:
        h, a = ft_score.split("-")
        h, a = int(h), int(a)
    except (ValueError, AttributeError):
        return False
    is_goal = (h >= 1 and a >= 1)
    if gg_pred == "goal":
        return is_goal
    elif gg_pred == "nogoal":
        return not is_goal
    return False


def main():
    print("[load] caricamento dataset...")
    dataset = load_dataset_extended()
    print(f"[load] {len(dataset)} partite\n")

    test_matches = pick_test_matches()
    print(f"[pick] {len(test_matches)} partite test\n")

    # Per ogni partita test: predizione GG, top 15 RE, esito reale
    print("[compute] calcolo per ogni partita...")
    rows = []
    for target_doc in tqdm(test_matches, desc="processing"):
        target_lega = target_doc["lega"]
        target_ext = extract_extended_features(target_doc["feature_vector"], target_lega)
        real_outcome = target_doc["outcome"]
        real_gg = "goal" if (real_outcome["goals_home"] >= 1 and real_outcome["goals_away"] >= 1) else "nogoal"
        real_score = real_outcome["ft_score"]

        pool_info = compute_pool(target_ext, dataset, exclude_uid=target_doc["match_uid"])
        if pool_info["n"] < MIN_PARTITE_PER_PRONOSTICO:
            continue

        mkt = compute_markets_for_pool(pool_info["partite"])
        gg_dist = mkt["goal_nogoal"]
        gg_pred = max(gg_dist, key=gg_dist.get)
        gg_pct = gg_dist[gg_pred]

        # Top 15 RE dal pool
        re_top = compute_re_top5(pool_info["partite"], max_results=N_RE_TO_CHECK)
        n_re = len(re_top)

        # Conta quanti RE sono coerenti con la predizione GG
        coherent = sum(1 for r in re_top if is_re_coherent_with_gg(r["score"], gg_pred))

        rows.append({
            "match_uid": target_doc["match_uid"],
            "home": target_doc["home_team"],
            "away": target_doc["away_team"],
            "real_score": real_score,
            "real_gg": real_gg,
            "gg_pred": gg_pred,
            "gg_pct": gg_pct,
            "coherent": coherent,
            "n_re": n_re,
            "hit": gg_pred == real_gg,
        })

    n_test = len(rows)
    print(f"\n[compute] {n_test} pronostici\n")

    # Raggruppa per livello di coerenza (numero RE coerenti)
    by_coherence = defaultdict(list)
    for r in rows:
        by_coherence[r["coherent"]].append(r)

    # Output MD
    md = ["# Test pattern: coerenza GG/NG vs Top 15 RE\n"]
    md.append(f"**Test set**: {n_test} partite (seed={RANDOM_SEED})\n")
    md.append(f"**N RE controllati per partita**: {N_RE_TO_CHECK}\n")
    md.append("\n## Logica\n")
    md.append("Per ogni partita: confronto la predizione GG/NG con i top 15 RE.")
    md.append("Conto quanti RE sono *coerenti*:")
    md.append("- Se predizione = **Goal** → RE coerente se entrambe le squadre hanno ≥1 gol (es. 1-1, 2-1)")
    md.append("- Se predizione = **NoGoal** → RE coerente se almeno una squadra a 0 (es. 0-0, 1-0, 0-1)\n")
    md.append("Più coerenza = più segnale forte. Verifico se hit rate aumenta con coerenza.\n")

    # Tabella per livello di coerenza
    md.append("\n## Hit rate GG/NG per livello di coerenza\n")
    md.append("| Coerenza (RE coerenti / 15) | N partite | Hit | Hit rate |")
    md.append("|---|---|---|---|")
    sorted_coh = sorted(by_coherence.keys(), reverse=True)
    cumulative_partite = 0
    cumulative_hit = 0
    for coh in sorted_coh:
        partite = by_coherence[coh]
        hit = sum(1 for p in partite if p["hit"])
        n = len(partite)
        rate = hit / n * 100 if n else 0
        md.append(f"| {coh}/15 | {n} | {hit} | **{rate:.1f}%** |")

    # Cumulativo: hit rate per soglie minime di coerenza
    md.append("\n## Cumulativo: Hit rate quando coerenza >= soglia\n")
    md.append("| Soglia minima coerenza | N partite (>=) | Hit | Hit rate |")
    md.append("|---|---|---|---|")
    for coh in sorted_coh:
        n_above = sum(len(by_coherence[c]) for c in sorted_coh if c >= coh)
        hit_above = sum(sum(1 for p in by_coherence[c] if p["hit"]) for c in sorted_coh if c >= coh)
        rate = hit_above / n_above * 100 if n_above else 0
        md.append(f"| ≥ {coh}/15 | {n_above}/{n_test} | {hit_above} | **{rate:.1f}%** |")

    # Dettaglio partite ordinate per coerenza
    md.append("\n## Dettaglio per partita (ordinate per coerenza decrescente)\n")
    md.append("| Coerenza | Partita | Reale | Predetto | GG % | Hit |")
    md.append("|---|---|---|---|---|---|")
    sorted_rows = sorted(rows, key=lambda x: -x["coherent"])
    for r in sorted_rows:
        hit_emoji = "✅" if r["hit"] else "❌"
        md.append(f"| {r['coherent']}/{r['n_re']} | {r['home']} vs {r['away']} ({r['real_score']}) | {r['real_gg']} | {r['gg_pred']} ({r['gg_pct']*100:.0f}%) | {hit_emoji} |")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[done] output: {OUTPUT_MD}")

    # Sintesi a video
    print("\n=== SINTESI per livello di coerenza ===")
    print(f"{'Coerenza':<15} {'N partite':<12} {'Hit':<6} {'Hit rate':<10}")
    for coh in sorted_coh:
        partite = by_coherence[coh]
        hit = sum(1 for p in partite if p["hit"])
        n = len(partite)
        rate = hit / n * 100 if n else 0
        print(f"{coh}/15{'':<10} {n:<12} {hit:<6} {rate:.1f}%")

    print("\n=== CUMULATIVO (coerenza >= X) ===")
    for coh in sorted_coh:
        n_above = sum(len(by_coherence[c]) for c in sorted_coh if c >= coh)
        hit_above = sum(sum(1 for p in by_coherence[c] if p["hit"]) for c in sorted_coh if c >= coh)
        rate = hit_above / n_above * 100 if n_above else 0
        print(f">= {coh}/15:  {n_above}/{n_test} partite, hit rate {rate:.1f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
