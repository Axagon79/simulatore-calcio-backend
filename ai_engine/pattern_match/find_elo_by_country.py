"""
Helper Fase 1.2 — trova nomi ClubElo per squadre mancanti, filtrando per Country.

Riduce drasticamente i falsi positivi del fuzzy match: invece di cercare
"Karabukspor" tra 629 squadre, cerca solo tra le 19 turche.

Output:
- AUTO: 1 candidato univoco -> match sicuro, da aggiungere agli alias.
- AMBIGUI: 2+ candidati -> servono conferma utente.
- NONE: 0 candidati -> probabilmente squadra non in ClubElo.

Uso:
    python -m ai_engine.pattern_match.find_elo_by_country
"""
from __future__ import annotations

import glob
import sys
from io import StringIO
from pathlib import Path

import requests
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.config import CACHE_FOOTBALLDATA, LEAGUES


# Mappa lega Football-Data -> Country ClubElo
LEAGUE_TO_COUNTRY = {league["fd_code"]: league["country"] for league in LEAGUES}

# Le 43 squadre mancanti dall'output Step 1.2
MISSING = [
    "AZ Alkmaar", "Ad. Demirspor", "Ajaccio GFCO", "Akhisar Belediyespor",
    "Almere City", "Ankaragucu", "Ath Bilbao", "Ath Madrid", "Beerschot VA",
    "Bodrumspor", "Buyuksehyr", "Club Brugge", "Ein Frankfurt", "Espanol",
    "FC Emmen", "FC Koln", "For Sittard", "Fortuna Dusseldorf", "Goztep",
    "Graafschap", "Greuther Furth", "Holstein Kiel", "Inverness C",
    "Karabukspor", "Karagumruk", "Kayserispor", "La Coruna", "M'gladbach",
    "Mersin Idman Yurdu", "Mouscron-Peruwelz", "NAC Breda", "Nott'm Forest",
    "Nurnberg", "Osmanlispor", "PSV Eindhoven", "RWD Molenbeek", "Schalke 04",
    "Sp Braga", "Sp Gijon", "Sp Lisbon", "Sparta Rotterdam", "St Etienne",
    "St. Gilloise", "Uniao Madeira", "VVV Venlo", "Vallecano",
    "Waasland-Beveren", "Waregem", "Werder Bremen", "Wolves", "Yeni Malatyaspor",
]


def fetch_clubelo_global() -> pd.DataFrame:
    url = "http://api.clubelo.com/2024-08-01"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text))


def find_team_league() -> dict[str, set[str]]:
    """Mappa team Football-Data -> set di leghe FD in cui appare."""
    team_to_leagues: dict[str, set[str]] = {}
    for csv_path in sorted(Path(CACHE_FOOTBALLDATA).glob("*.csv")):
        lega = csv_path.name.split("_")[0]
        try:
            df = pd.read_csv(csv_path, low_memory=False)
            teams = set(df["HomeTeam"].dropna().unique()) | set(df["AwayTeam"].dropna().unique())
            for t in teams:
                team_to_leagues.setdefault(t, set()).add(lega)
        except Exception:
            continue
    return team_to_leagues


def main() -> int:
    df = fetch_clubelo_global()
    team_to_leagues = find_team_league()

    auto_matches: dict[str, str] = {}
    ambiguous: list[tuple[str, list[str], str]] = []

    print("=" * 80)
    print("Match per squadra mancante (filtrato per Country)")
    print("=" * 80)

    for fd in sorted(MISSING):
        leagues = team_to_leagues.get(fd, set())
        if not leagues:
            print(f"  ?? {fd:30s} -> non trovata in nessun CSV (?)")
            continue
        # Prendi la prima lega (le squadre normalmente sono in 1 sola)
        lega = sorted(leagues)[0]
        country = LEAGUE_TO_COUNTRY.get(lega)
        if not country:
            continue
        sub = df[df["Country"] == country]

        # Cerca per parole chiave (>2 chars, niente apostrofi/punti)
        words = [w for w in fd.replace("'", "").replace(".", "").replace("-", " ").split() if len(w) > 2]
        candidates = []
        for _, row in sub.iterrows():
            club = row["Club"]
            club_l = club.lower()
            for w in words:
                if w.lower() in club_l:
                    if club not in candidates:
                        candidates.append(club)
                    break

        if len(candidates) == 1:
            auto_matches[fd] = candidates[0]
            print(f"  OK    {fd:30s} ({country}) -> {candidates[0]}")
        elif len(candidates) > 1:
            ambiguous.append((fd, candidates, country))
            print(f"  AMBIG {fd:30s} ({country}) -> {candidates}")
        else:
            # Mostra primi 15 club della nazione per riferimento
            ambiguous.append((fd, [], country))
            print(f"  NONE  {fd:30s} ({country}) -> nessun match")
            print(f"        Lista {country} (primi 15): {sub['Club'].tolist()[:15]}")

    print("\n" + "=" * 80)
    print(f"AUTO sicuri:   {len(auto_matches)}")
    print(f"AMBIG / NONE:  {len(ambiguous)}")

    print("\n=== AUTO MATCHES (da aggiungere come alias) ===")
    for fd, elo in auto_matches.items():
        print(f'  "{fd}" -> "{elo}"')

    print("\n=== AMBIGUI / NONE (richiedono decisione manuale) ===")
    for fd, cands, country in ambiguous:
        print(f"  {fd:30s} ({country}): {cands if cands else 'NESSUN match'}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
