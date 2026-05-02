"""
Test Pattern Match Engine su Como-Napoli del 2 maggio 2026.

Vettore feature 23-dim costruito manualmente con dati certificati dall'utente.
NON inserisce nulla in DB. Solo stampa output.

Uso:
    python -m ai_engine.pattern_match.test_como_napoli
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.match_engine import (
    compute_matrix, load_dataset, print_matrix, print_top_matches,
    compute_risultato_esatto_single_cell,
    NUMERIC_FEATURES, TOLERANCES, COMPATIBILITY_BANDS, league_compatible,
)


# ====================================================================
# Vettore feature Como-Napoli — 2 maggio 2026
# ====================================================================
# Dati confermati dall'utente:
# - Lega: Serie A (I1)
# - Giornata: 35
# - Como: 5° classifica gen, 61pt, 34g, 59gf-28gs
# - Napoli: 2° classifica gen, 69pt, 34g, 52gf-33gs
# - Como casa: 35pt (61-26 trasferta), pos casa STIMATA 5°
# - Napoli trasferta: 29pt (69-40 casa), 3° in trasferta
# - Quote Bet365.it: 1=2.20, X=3.20, 2=3.50
# - Elo (cache ClubElo, range 2026-04-27 -> 2026-05-02): Como 1746.08, Napoli 1783.48

TARGET_FEATURES = {
    "lega": "I1",
    "giornata": 35,
    "posizione_classifica_casa": 5,
    "posizione_classifica_ospite": 2,
    "punti_casa": 61,
    "punti_ospite": 69,
    "differenza_punti": -8,
    "partite_giocate_casa": 34,
    "partite_giocate_ospite": 34,
    "gol_fatti_casa": 59,
    "gol_subiti_casa": 28,
    "gol_fatti_ospite": 52,
    "gol_subiti_ospite": 33,
    "posizione_classifica_casa_solo_casalinga": 5,    # [STIMA] — Como 35pt casa
    "punti_casa_solo_casalinga": 35,
    "posizione_classifica_ospite_solo_trasferta": 3,
    "punti_ospite_solo_trasferta": 29,
    "prob_implicita_1": 1.0 / 2.20,
    "prob_implicita_X": 1.0 / 3.20,
    "prob_implicita_2": 1.0 / 3.50,
    "elo_casa": 1746.08,
    "elo_ospite": 1783.48,
    "elo_diff": 1746.08 - 1783.48,  # -37.40
}

TARGET_LEGA = "I1"


def main():
    print("=" * 80)
    print("TEST: Como vs Napoli — 2 maggio 2026 (Serie A, giornata 35)")
    print("=" * 80)
    print(f"\n{'Vettore feature target:':<50}")
    f = TARGET_FEATURES
    print(f"  Como (casa):  pos generale={f['posizione_classifica_casa']}, punti={f['punti_casa']}, "
          f"gol {f['gol_fatti_casa']}-{f['gol_subiti_casa']}, "
          f"casa-only pos={f['posizione_classifica_casa_solo_casalinga']} [STIMA] pt={f['punti_casa_solo_casalinga']}")
    print(f"  Napoli (osp): pos generale={f['posizione_classifica_ospite']}, punti={f['punti_ospite']}, "
          f"gol {f['gol_fatti_ospite']}-{f['gol_subiti_ospite']}, "
          f"trasf-only pos={f['posizione_classifica_ospite_solo_trasferta']} pt={f['punti_ospite_solo_trasferta']}")
    print(f"  Quote Bet365: 1=2.20  X=3.20  2=3.50")
    print(f"  Prob implicite: 1={f['prob_implicita_1']:.4f}  X={f['prob_implicita_X']:.4f}  2={f['prob_implicita_2']:.4f}")
    print(f"  Elo: Como={f['elo_casa']:.2f}  Napoli={f['elo_ospite']:.2f}  diff={f['elo_diff']:.2f}")

    print(f"\n[load] caricamento dataset 32k partite...")
    features_db, outcomes_db, metadata_db = load_dataset()
    print(f"[load] {len(metadata_db)} partite caricate")

    # Matrice globale
    matrix_global = compute_matrix(TARGET_FEATURES, TARGET_LEGA,
                                   features_db, outcomes_db, metadata_db,
                                   intra_lega_only=False, top_k=5)
    print_matrix(matrix_global, "MATRICE GLOBALE (10 leghe)")

    # Matrice intra-lega
    intra_mask = np.array([m["lega"] == TARGET_LEGA for m in metadata_db])
    matrix_intra = compute_matrix(TARGET_FEATURES, TARGET_LEGA,
                                  features_db[intra_mask], outcomes_db[intra_mask],
                                  [m for m, k in zip(metadata_db, intra_mask) if k],
                                  intra_lega_only=True, top_k=5)
    print_matrix(matrix_intra, f"MATRICE INTRA-LEGA (Serie A)")

    # Output esteso cella T3 16-19 intra-lega (richiesta utente per verifica)
    print("\n" + "=" * 80)
    print("CELLA T3 16-19 INTRA-LEGA — OUTPUT ESTESO COMPLETO")
    print("=" * 80)
    cell = next((c for c in matrix_intra["cells"]
                 if c["tolerance_level"] == "T3" and c["compatibility_band"] == "16-19"), None)
    if cell and cell["n_matches"] > 0:
        print(f"  N partite nel cluster: {cell['n_matches']}")
        print(f"\n  SEGNO 1X2:")
        for k, v in cell["outcome_distribution"].items():
            print(f"    {k}: {v*100:.2f}%")
        print(f"\n  DOPPIA CHANCE:")
        for k, v in cell["doppia_chance"].items():
            print(f"    {k}: {v*100:.2f}%")
        print(f"\n  OVER/UNDER:")
        for soglia in ["1_5", "2_5", "3_5"]:
            d = cell[f"over_under_{soglia}"]
            print(f"    {soglia.replace('_', '.')}: Over={d['over']*100:.2f}%  Under={d['under']*100:.2f}%")
        print(f"\n  GOAL/NOGOAL:")
        for k, v in cell["goal_nogoal"].items():
            print(f"    {k}: {v*100:.2f}%")
        print(f"\n  MULTIGOL:")
        for k, v in cell["multigol"].items():
            print(f"    {k.replace('_', '-')}: {v*100:.2f}%")
        print(f"\n  MEDIE:")
        for k, v in cell["medie"].items():
            print(f"    {k}: {v:.3f}")
    else:
        print("  Cella vuota o non trovata.")

    # Risultato Esatto gerarchico (intra-lega)
    print("\n" + "=" * 80)
    print("RISULTATO ESATTO TOP 5 — algoritmo gerarchico (intra-lega Serie A)")
    print("=" * 80)
    if matrix_intra.get("risultato_esatto_top5"):
        for i, r in enumerate(matrix_intra["risultato_esatto_top5"], 1):
            print(f"  {i}. {r['score']:6s}  da {r['from_cell']:10s}  "
                  f"({r['frequency_in_cell']}/{r['n_in_cell']} partite cella)  "
                  f"esempio: {r['match_uid']}")
    else:
        print("  Nessun risultato esatto trovato.")

    # Risultato Esatto gerarchico (globale)
    print("\n" + "=" * 80)
    print("RISULTATO ESATTO TOP 5 — algoritmo gerarchico (globale 10 leghe)")
    print("=" * 80)
    if matrix_global.get("risultato_esatto_top5"):
        for i, r in enumerate(matrix_global["risultato_esatto_top5"], 1):
            print(f"  {i}. {r['score']:6s}  da {r['from_cell']:10s}  "
                  f"({r['frequency_in_cell']}/{r['n_in_cell']} partite cella)  "
                  f"esempio: {r['match_uid']}")
    else:
        print("  Nessun risultato esatto trovato.")

    # =================================================================
    # CONFRONTO: metodo cella singola (mio originale) sulla T3 16-19 intra-lega
    # =================================================================
    print("\n" + "=" * 80)
    print("CONFRONTO — METODO CELLA SINGOLA (similitudine in T3 16-19 intra-lega)")
    print("=" * 80)

    # Ricalcolo gli indici delle partite in T3 16-19 intra-lega
    intra_features = features_db[intra_mask]
    intra_metadata = [m for m, k in zip(metadata_db, intra_mask) if k]

    target_vec = np.array([float(TARGET_FEATURES[ff]) for ff in NUMERIC_FEATURES], dtype=np.float64)
    diffs = np.abs(intra_features - target_vec[np.newaxis, :])
    # T3 = livello indice 2
    tol_vec = np.array([TOLERANCES[ff][2] for ff in NUMERIC_FEATURES])
    compat = diffs <= tol_vec[np.newaxis, :]
    n_compat = compat.sum(axis=1)
    # Lega: T3 vuole stessa lega -> tutti True (intra-lega gia filtrato)
    n_total_compat = n_compat + 1
    band_mask = (n_total_compat >= 16) & (n_total_compat <= 19)
    cell_indices = np.where(band_mask)[0].tolist()

    if cell_indices:
        results_single = compute_risultato_esatto_single_cell(
            target_vec, cell_indices, intra_metadata, intra_features, max_results=5
        )
        print(f"  Cella T3 16-19 intra-lega: {len(cell_indices)} partite")
        print(f"  RE unici trovati per similitudine al target:")
        for i, r in enumerate(results_single, 1):
            print(f"    {i}. {r['score']:6s}  dist={r['distance']:.3f}  "
                  f"{r['data']}  {r['home']:25s} vs {r['away']:25s}")
    else:
        print("  Cella T3 16-19 intra-lega vuota.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
