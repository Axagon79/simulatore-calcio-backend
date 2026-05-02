"""
Helper Fase 1.2 — trova i nomi ClubElo per le squadre Football-Data mancanti.

Scarica la lista globale ClubElo a una data passata (es. 2024-08-01) e cerca
match approssimati per i nomi Football-Data che hanno fallito.

Uso:
    python -m ai_engine.pattern_match.find_elo_names
"""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path

import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.ingest import collect_unique_teams_from_cache
from ai_engine.pattern_match.config import CACHE_CLUBELO, fd_to_elo_team


GLOBAL_DATE = "2024-08-01"
URL = f"http://api.clubelo.com/{GLOBAL_DATE}"


def fetch_global_clubs() -> pd.DataFrame:
    print(f"[fetch] {URL}")
    r = requests.get(URL, timeout=30)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text))
    print(f"[fetch] {len(df)} squadre, colonne: {list(df.columns)}")
    return df


def find_unmapped_teams() -> list[str]:
    """Squadre Football-Data per cui non esiste cache ClubElo."""
    teams = collect_unique_teams_from_cache()
    unmapped = []
    for fd_team in sorted(teams):
        elo_name = fd_to_elo_team(fd_team)
        cache_file = CACHE_CLUBELO / f"{elo_name}.csv"
        if not cache_file.exists():
            unmapped.append(fd_team)
    return unmapped


def fuzzy_search(query: str, club_list: list[str]) -> list[tuple[str, float]]:
    """Match approssimato semplice basato su substring + lunghezza simile."""
    q = query.lower().replace(" ", "").replace(".", "").replace("-", "")
    results = []
    for club in club_list:
        c = club.lower().replace(" ", "").replace(".", "").replace("-", "")
        # Score: 1 se uno e' substring dell'altro, peso per lunghezza simile
        if q in c or c in q:
            score = min(len(q), len(c)) / max(len(q), len(c))
            results.append((club, score))
        else:
            # Match parziale: prefissi 4+ caratteri
            for n in range(min(len(q), len(c)), 3, -1):
                if q[:n] == c[:n]:
                    score = n / max(len(q), len(c)) * 0.6
                    results.append((club, score))
                    break
    return sorted(results, key=lambda x: -x[1])[:5]


def main():
    df = fetch_global_clubs()
    all_clubs = df["Club"].tolist()

    unmapped = find_unmapped_teams()
    print(f"\n[unmapped] {len(unmapped)} squadre Football-Data senza Elo:")

    suggestions = {}
    for fd_team in unmapped:
        candidates = fuzzy_search(fd_team, all_clubs)
        suggestions[fd_team] = candidates
        cand_str = ", ".join(f"{c[0]}({c[1]:.2f})" for c in candidates[:3]) if candidates else "(nessun match)"
        print(f"  {fd_team:30s} -> {cand_str}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
