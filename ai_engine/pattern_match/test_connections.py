"""
Test connessioni Pattern Match Engine — Fase 0.

Verifica:
1. Football-Data.co.uk: scarica 1 CSV (Serie A 2024/25) e mostra prime righe.
2. ClubElo storico: chiama API per Inter e mostra prime righe.

Uso:
    python ai_engine/pattern_match/test_connections.py

Niente scrittura su disco, niente DB. Solo test in memoria.
"""
from __future__ import annotations

import sys
from io import StringIO

import requests
import pandas as pd


# ====================================================================
# TEST 1 — Football-Data.co.uk
# ====================================================================

FOOTBALLDATA_URL_TEMPLATE = "https://www.football-data.co.uk/mmz4281/{stagione}/{lega}.csv"

# Stagioni: 2425 = 2024/25, 2324 = 2023/24, ecc.
TEST_STAGIONE = "2425"
TEST_LEGA = "I1"  # Serie A


def test_footballdata():
    url = FOOTBALLDATA_URL_TEMPLATE.format(stagione=TEST_STAGIONE, lega=TEST_LEGA)
    print(f"[FD] GET {url}")
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    print(f"[FD] OK: {len(df)} righe, {len(df.columns)} colonne")
    cols_needed = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "B365H", "B365D", "B365A"]
    missing = [c for c in cols_needed if c not in df.columns]
    if missing:
        print(f"[FD] WARN: colonne mancanti: {missing}")
    else:
        print(f"[FD] OK: tutte le colonne attese presenti")
    print(f"\n[FD] Prime 5 righe (colonne core):")
    print(df[cols_needed].head().to_string(index=False))
    return df


# ====================================================================
# TEST 2 — ClubElo storico per 1 squadra
# ====================================================================

CLUBELO_TEAM_URL_TEMPLATE = "http://api.clubelo.com/{team}"

TEST_TEAM = "Inter"


def test_clubelo_team_history():
    url = CLUBELO_TEAM_URL_TEMPLATE.format(team=TEST_TEAM)
    print(f"\n[CE] GET {url}")
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    print(f"[CE] OK: {len(df)} righe, colonne: {list(df.columns)}")
    print(f"\n[CE] Prime 5 righe:")
    print(df.head().to_string(index=False))
    print(f"\n[CE] Ultime 5 righe:")
    print(df.tail().to_string(index=False))
    return df


def main():
    print("=" * 70)
    print("FASE 0 — Test connessioni Pattern Match Engine")
    print("=" * 70)

    try:
        fd_df = test_footballdata()
    except Exception as e:
        print(f"[FD] ERRORE: {e}")
        return 1

    try:
        ce_df = test_clubelo_team_history()
    except Exception as e:
        print(f"[CE] ERRORE: {e}")
        return 1

    print("\n" + "=" * 70)
    print("Entrambi i test passati. Connessioni OK.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
