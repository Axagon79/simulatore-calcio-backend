"""
Validazione del nuovo engine pesato (weighted_engine) sulle 50 partite test.

Stesso seed (42) e stessa procedura di validation_50.py per confronto diretto
con engine 5x5 cella-per-cella.

Output: validation_50_weighted.md
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
    MAX_SCORE, MIN_SCORE_THRESHOLD, POOL_SIZE,
    MIN_PARTITE_PER_PRONOSTICO, DC_THRESHOLD_FOR_SECCO, MARKET_THRESHOLDS,
    load_dataset_extended,
)
from ai_engine.pattern_match.config import MONGO_COLLECTION_MATCHES
from config import db


OUTPUT_MD = Path(__file__).parent / "validation_50_weighted.md"
RANDOM_SEED = 42


def pick_test_matches(n_serie_a: int = 25, n_other: int = 25,
                      season: str = "2024-25") -> list[dict]:
    coll = db[MONGO_COLLECTION_MATCHES]
    rng = random.Random(RANDOM_SEED)
    serie_a = list(coll.find({"lega": "I1", "stagione": season}))
    others = list(coll.find({"lega": {"$ne": "I1"}, "stagione": season}))
    return rng.sample(serie_a, n_serie_a) + rng.sample(others, n_other)


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


def predict_dominant(d: dict) -> str:
    return max(d, key=d.get)


def main():
    print("[load] caricamento dataset...")
    dataset = load_dataset_extended()
    print(f"[load] {len(dataset)} partite\n")

    test_matches = pick_test_matches()
    print(f"[pick] {len(test_matches)} partite test (seed={RANDOM_SEED})\n")

    md = ["# Validazione Weighted Engine — 50 partite (seed 42)\n"]
    md.append(f"**Pool size**: {POOL_SIZE} | **Soglia minima**: {MIN_SCORE_THRESHOLD}/{MAX_SCORE} (60%) | **Min partite per emettere**: {MIN_PARTITE_PER_PRONOSTICO}\n")
    md.append(f"**Test set**: 25 Serie A + 25 altre leghe, stagione 2024-25\n")
    md.append("---\n")

    # Stats aggregate
    stats = Counter()
    re_hit = 0
    pronostici_emessi = 0

    for target_doc in tqdm(test_matches, desc="weighted-validation"):
        match_uid = target_doc["match_uid"]
        target_lega = target_doc["lega"]
        target_ext = extract_extended_features(target_doc["feature_vector"], target_lega)
        real_outcome = target_doc["outcome"]
        real_1x2 = real_outcome["result_1x2"]
        real_total = real_outcome["goals_home"] + real_outcome["goals_away"]
        real_ou15 = "over" if real_total >= 2 else "under"
        real_ou25 = "over" if real_total >= 3 else "under"
        real_ou35 = "over" if real_total >= 4 else "under"
        real_gg = "goal" if (real_outcome["goals_home"] >= 1 and real_outcome["goals_away"] >= 1) else "nogoal"
        real_score = real_outcome["ft_score"]
        real_dc_set = real_dc(real_1x2)
        real_mg_set = real_mg(real_total)

        pool_info = compute_pool(target_ext, dataset, exclude_uid=match_uid)
        if pool_info["n"] < MIN_PARTITE_PER_PRONOSTICO:
            md.append(f"\n## {target_doc['home_team']} vs {target_doc['away_team']} ({target_doc['data_partita'].strftime('%Y-%m-%d')}) — `{match_uid}`")
            md.append(f"- Esito reale: {real_score}")
            md.append(f"- **NON EMESSO**: pool n={pool_info['n']} (sotto soglia {MIN_PARTITE_PER_PRONOSTICO})\n")
            continue

        pronostici_emessi += 1
        mkt = compute_markets_for_pool(pool_info["partite"])
        re_top = compute_re_top5(pool_info["partite"], max_results=5)

        # Predizioni
        p_1x2 = predict_dominant(mkt["1x2"])
        # Mappo "1"/"X"/"2" -> "H"/"D"/"A"
        pred_1x2_letter = {"1": "H", "X": "D", "2": "A"}[p_1x2]
        p_dc = predict_dominant(mkt["doppia_chance"])
        p_ou15 = predict_dominant(mkt["over_under_1_5"])
        p_ou25 = predict_dominant(mkt["over_under_2_5"])
        p_ou35 = predict_dominant(mkt["over_under_3_5"])
        p_gg = predict_dominant(mkt["goal_nogoal"])
        p_mg = predict_dominant(mkt["multigol"])

        # 1X2 con filtro DC: emetto il segno secco solo se entrambe le DC sono >= soglia
        secco_1x2_sign, secco_motivo = emit_1x2_secco(mkt)
        emit_secco = secco_1x2_sign is not None

        # Filtri sui mercati (emetto solo se sopra soglia)
        ou15_filt, _, ou15_motivo = emit_market_filtered(mkt, "over_under_1_5")
        ou25_filt, _, ou25_motivo = emit_market_filtered(mkt, "over_under_2_5")
        ou35_filt, _, ou35_motivo = emit_market_filtered(mkt, "over_under_3_5")
        gg_filt, _, gg_motivo = emit_market_filtered(mkt, "goal_nogoal")
        mg_filt, _, mg_motivo = emit_market_filtered(mkt, "multigol")

        # Hit
        hit_1x2 = (pred_1x2_letter == real_1x2)  # baseline (sempre il dominante)
        hit_dc = (p_dc in real_dc_set)
        hit_ou15 = (p_ou15 == real_ou15)
        hit_ou25 = (p_ou25 == real_ou25)
        hit_ou35 = (p_ou35 == real_ou35)
        hit_gg = (p_gg == real_gg)
        hit_mg = (p_mg in real_mg_set)
        hit_re = real_score in [r["score"] for r in re_top]

        if hit_1x2: stats["1x2_hit"] += 1
        stats["1x2_total"] += 1
        # 1X2 filtrato (con soglia DC)
        if emit_secco:
            stats["1x2_filtered_total"] += 1
            if hit_1x2:
                stats["1x2_filtered_hit"] += 1
        if hit_dc: stats["dc_hit"] += 1
        stats["dc_total"] += 1
        if hit_ou15: stats["ou15_hit"] += 1
        stats["ou15_total"] += 1
        if hit_ou25: stats["ou25_hit"] += 1
        stats["ou25_total"] += 1
        if hit_ou35: stats["ou35_hit"] += 1
        stats["ou35_total"] += 1
        if hit_gg: stats["gg_hit"] += 1
        stats["gg_total"] += 1
        if hit_mg: stats["mg_hit"] += 1
        stats["mg_total"] += 1
        if hit_re: re_hit += 1

        # Stats filtrate per ogni mercato
        if ou15_filt is not None:
            stats["ou15_filtered_total"] += 1
            if ou15_filt == real_ou15:
                stats["ou15_filtered_hit"] += 1
        if ou25_filt is not None:
            stats["ou25_filtered_total"] += 1
            if ou25_filt == real_ou25:
                stats["ou25_filtered_hit"] += 1
        if ou35_filt is not None:
            stats["ou35_filtered_total"] += 1
            if ou35_filt == real_ou35:
                stats["ou35_filtered_hit"] += 1
        if gg_filt is not None:
            stats["gg_filtered_total"] += 1
            if gg_filt == real_gg:
                stats["gg_filtered_hit"] += 1
        if mg_filt is not None:
            stats["mg_filtered_total"] += 1
            if mg_filt in real_mg_set:
                stats["mg_filtered_hit"] += 1

        # Output partita nel MD
        md.append(f"\n## {target_doc['home_team']} vs {target_doc['away_team']} ({target_doc['data_partita'].strftime('%Y-%m-%d')})")
        md.append(f"- **uid**: `{match_uid}` | **{target_lega} {target_doc['stagione']}**")
        md.append(f"- **Esito reale**: {real_score} (1X2={real_1x2}, total={real_total})")
        md.append(f"- **Pool**: n={pool_info['n']}, score medio {pool_info['score_medio']:.1f}/{MAX_SCORE} ({pool_info['score_medio']/MAX_SCORE*100:.0f}%)")

        md.append(f"\n| Mercato | Predetto | Reale | Hit |")
        md.append("|---|---|---|---|")
        if emit_secco:
            md.append(f"| 1X2 secco (filtrato) | **{p_1x2}** ({mkt['1x2'][p_1x2]*100:.0f}%) — {secco_motivo} | {real_1x2} | {'✅' if hit_1x2 else '❌'} |")
        else:
            md.append(f"| 1X2 secco (filtrato) | NON EMESSO — {secco_motivo} | {real_1x2} | — |")
        md.append(f"| 1X2 (baseline, sempre dominante) | {p_1x2} ({mkt['1x2'][p_1x2]*100:.0f}%) | {real_1x2} | {'✅' if hit_1x2 else '❌'} |")
        md.append(f"| DC | {p_dc} ({mkt['doppia_chance'][p_dc]*100:.0f}%) | {','.join(real_dc_set)} | {'✅' if hit_dc else '❌'} |")
        md.append(f"| O/U 1.5 | {p_ou15} ({mkt['over_under_1_5'][p_ou15]*100:.0f}%) | {real_ou15} | {'✅' if hit_ou15 else '❌'} |")
        md.append(f"| O/U 2.5 | {p_ou25} ({mkt['over_under_2_5'][p_ou25]*100:.0f}%) | {real_ou25} | {'✅' if hit_ou25 else '❌'} |")
        md.append(f"| O/U 3.5 | {p_ou35} ({mkt['over_under_3_5'][p_ou35]*100:.0f}%) | {real_ou35} | {'✅' if hit_ou35 else '❌'} |")
        md.append(f"| GG/NG | {p_gg} ({mkt['goal_nogoal'][p_gg]*100:.0f}%) | {real_gg} | {'✅' if hit_gg else '❌'} |")
        md.append(f"| MG | {p_mg.replace('_','-')} ({mkt['multigol'][p_mg]*100:.0f}%) | {','.join(sorted(real_mg_set))} | {'✅' if hit_mg else '❌'} |")
        md.append(f"| RE Top 5 | {','.join([r['score'] for r in re_top])} | {real_score} | {'✅' if hit_re else '❌'} |")

    # =================================================================
    # Riepilogo finale
    # =================================================================
    md.append("\n---\n")
    md.append("# Riepilogo aggregato — Weighted Engine\n")
    md.append(f"**Pronostici emessi**: {pronostici_emessi}/50\n")
    md.append("\n## Hit rate per mercato — baseline (sempre dominante) vs filtrato (sopra soglia)\n")
    md.append("| Mercato | Baseline Hit | Baseline % | Filtrato Hit | Filtrato % |")
    md.append("|---|---|---|---|---|")
    markets = [
        ("1X2", "1x2", DC_THRESHOLD_FOR_SECCO * 100, "1x2_filtered"),
        ("O/U 1.5", "ou15", MARKET_THRESHOLDS["over_under_1_5"] * 100, "ou15_filtered"),
        ("O/U 2.5", "ou25", MARKET_THRESHOLDS["over_under_2_5"] * 100, "ou25_filtered"),
        ("O/U 3.5", "ou35", MARKET_THRESHOLDS["over_under_3_5"] * 100, "ou35_filtered"),
        ("GG/NG", "gg", MARKET_THRESHOLDS["goal_nogoal"] * 100, "gg_filtered"),
        ("MG", "mg", MARKET_THRESHOLDS["multigol"] * 100, "mg_filtered"),
    ]
    for label, key, soglia, key_filt in markets:
        h = stats[f"{key}_hit"]
        t = stats[f"{key}_total"]
        rate = h / t * 100 if t else 0
        h_f = stats[f"{key_filt}_hit"]
        t_f = stats[f"{key_filt}_total"]
        rate_f = h_f / t_f * 100 if t_f else 0
        md.append(f"| {label} (soglia {soglia:.1f}%) | {h}/{t} | {rate:.1f}% | {h_f}/{t_f} | **{rate_f:.1f}%** |")
    # DC senza filtro
    h = stats["dc_hit"]
    t = stats["dc_total"]
    md.append(f"| DC (no filtro) | {h}/{t} | **{h/t*100:.1f}%** | — | — |")
    md.append(f"| RE top5 (no filtro) | {re_hit}/{pronostici_emessi} | **{re_hit/pronostici_emessi*100:.1f}%** | — | — |")
    md.append(f"| RE top5 | {re_hit} | {pronostici_emessi} | **{re_hit/pronostici_emessi*100:.1f}%** |" if pronostici_emessi else "| RE top5 | 0 | 0 | — |")

    # Confronto con baseline
    md.append("\n## Baseline (su tutto il dataset)\n")
    md.append("| Esito | Baseline |")
    md.append("|---|---|")
    md.append("| 1 (casa) | 44.4% |")
    md.append("| X (pareggio) | 24.6% |")
    md.append("| 2 (trasferta) | 31.0% |")
    md.append("| Over 2.5 | 53.2% |")
    md.append("| Goal | 53.4% |")

    OUTPUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"\n[done] output: {OUTPUT_MD}")
    print(f"[done] Pronostici emessi: {pronostici_emessi}/50")
    print(f"[done] 1X2 hit: {stats['1x2_hit']}/{stats['1x2_total']} = {stats['1x2_hit']/max(stats['1x2_total'],1)*100:.1f}%")
    print(f"[done] DC hit: {stats['dc_hit']}/{stats['dc_total']} = {stats['dc_hit']/max(stats['dc_total'],1)*100:.1f}%")
    print(f"[done] O/U 2.5 hit: {stats['ou25_hit']}/{stats['ou25_total']} = {stats['ou25_hit']/max(stats['ou25_total'],1)*100:.1f}%")
    print(f"[done] GG/NG hit: {stats['gg_hit']}/{stats['gg_total']} = {stats['gg_hit']/max(stats['gg_total'],1)*100:.1f}%")
    print(f"[done] RE hit: {re_hit}/{pronostici_emessi} = {re_hit/max(pronostici_emessi,1)*100:.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
