"""
Step 1.3 — Build vettore feature 23-dim per ogni partita + insert MongoDB.

Per ogni CSV Football-Data:
1. Carica partite ordinate per Date.
2. Calcola classifica progressiva incrementale (1 passata O(n)).
3. Per ogni partita: build vettore feature 23-dim usando lo stato PRIMA della partita.
4. Lookup Elo storico al giorno della partita.
5. Insert in MongoDB collection `historical__matches_pattern`.

Schema doc Mongo (vedi History_System_Engine.md sezione 7.2.1):
{
  match_uid: "I1_2018-19_2018-09-15_INTER_MILAN",
  lega, stagione, data_partita,
  home_team, away_team,
  feature_vector: { 23 features... },
  outcome: { result_1x2, goals_home, goals_away, ft_score },
  raw_data_sources: { footballdata_row, clubelo_home, clubelo_away },
  ingested_at, schema_version
}
"""
from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from io import StringIO
from pathlib import Path

import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.config import (
    LEAGUES, CACHE_FOOTBALLDATA, CACHE_CLUBELO,
    MONGO_COLLECTION_MATCHES,
)
from ai_engine.pattern_match.clubelo_overrides import CLUBELO_OVERRIDES, NO_ELO_TEAMS
from config import db


SCHEMA_VERSION = 1


def parse_date_fd(date_str: str):
    """Football-Data usa dd/mm/yyyy o dd/mm/yy. Restituisce datetime."""
    s = str(date_str).strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def load_clubelo_csv(team_fd_name: str) -> pd.DataFrame | None:
    """Carica il CSV Elo per una squadra. Restituisce None se non disponibile."""
    if team_fd_name in NO_ELO_TEAMS:
        return None
    cache_filename = team_fd_name.replace(" ", "_").replace("/", "_") + ".csv"
    cache_path = CACHE_CLUBELO / cache_filename
    if not cache_path.exists():
        return None
    try:
        df = pd.read_csv(cache_path)
        df["From"] = pd.to_datetime(df["From"], errors="coerce")
        df["To"] = pd.to_datetime(df["To"], errors="coerce")
        return df
    except Exception:
        return None


def get_elo_at_date(elo_df: pd.DataFrame | None, target_date: datetime) -> float | None:
    """Lookup Elo nel range From <= target_date <= To."""
    if elo_df is None or elo_df.empty:
        return None
    target = pd.Timestamp(target_date)
    mask = (elo_df["From"] <= target) & (elo_df["To"] >= target)
    matches = elo_df.loc[mask, "Elo"]
    if matches.empty:
        # Prendi il record piu vicino con From <= target (storico)
        before = elo_df.loc[elo_df["From"] <= target]
        if before.empty:
            return None
        return float(before.iloc[-1]["Elo"])
    return float(matches.iloc[0])


def compute_position(stats_dict: dict[str, dict], team: str, all_teams: set[str]) -> int:
    """Restituisce posizione classifica (1-N) della squadra ordinando per punti/dr/gf."""
    if team not in stats_dict:
        return len(all_teams)
    rankings = []
    for t in all_teams:
        s = stats_dict.get(t, {"points": 0, "gf": 0, "ga": 0})
        rankings.append((t, s["points"], s["gf"] - s["ga"], s["gf"]))
    rankings.sort(key=lambda x: (-x[1], -x[2], -x[3], x[0]))
    for i, (t, *_) in enumerate(rankings, 1):
        if t == team:
            return i
    return len(all_teams)


def init_team_stats() -> dict:
    return {
        "played": 0, "wins": 0, "draws": 0, "losses": 0,
        "gf": 0, "ga": 0, "points": 0,
    }


def update_stats(stats: dict, gf: int, ga: int):
    stats["played"] += 1
    stats["gf"] += gf
    stats["ga"] += ga
    if gf > ga:
        stats["wins"] += 1
        stats["points"] += 3
    elif gf < ga:
        stats["losses"] += 1
    else:
        stats["draws"] += 1
        stats["points"] += 1


def estimate_giornata(stats_home: dict, stats_away: dict) -> int:
    """Approssima la giornata come max(played) + 1."""
    return max(stats_home["played"], stats_away["played"]) + 1


def process_csv(csv_path: Path) -> tuple[list[dict], list[str]]:
    """
    Processa un singolo CSV Football-Data e restituisce lista di documenti Mongo.
    """
    fname = csv_path.stem  # es. "I1_2425"
    fd_code, season_code = fname.split("_")
    league_info = next((l for l in LEAGUES if l["fd_code"] == fd_code), None)
    if not league_info:
        return [], [f"lega sconosciuta: {fd_code}"]

    # Stagione: "2425" -> "2024-25"
    yr1 = int(season_code[:2])
    yr2 = int(season_code[2:])
    stagione = f"20{yr1:02d}-{yr2:02d}"

    try:
        df = pd.read_csv(csv_path, low_memory=False)
    except Exception as e:
        return [], [f"{fname}: parse error: {e}"]

    required = ["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR", "B365H", "B365D", "B365A"]
    if not all(c in df.columns for c in required):
        missing = [c for c in required if c not in df.columns]
        return [], [f"{fname}: colonne mancanti {missing}"]

    df["parsed_date"] = df["Date"].apply(parse_date_fd)
    df = df.dropna(subset=["parsed_date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"])
    df = df.sort_values("parsed_date").reset_index(drop=True)

    # Stats progressive
    overall: dict[str, dict] = defaultdict(init_team_stats)
    home_only: dict[str, dict] = defaultdict(init_team_stats)
    away_only: dict[str, dict] = defaultdict(init_team_stats)
    all_teams = set(df["HomeTeam"].unique()) | set(df["AwayTeam"].unique())

    # Carica CSV Elo per ogni squadra (1 volta per CSV)
    elo_dfs: dict[str, pd.DataFrame | None] = {t: load_clubelo_csv(t) for t in all_teams}

    docs = []
    errors = []

    for _, row in df.iterrows():
        home = row["HomeTeam"]
        away = row["AwayTeam"]
        date = row["parsed_date"]
        try:
            fthg = int(row["FTHG"])
            ftag = int(row["FTAG"])
        except (ValueError, TypeError):
            continue
        ftr = str(row["FTR"]).strip()
        if ftr not in ("H", "D", "A"):
            continue

        # Stato PRIMA della partita
        sh = overall[home]
        sa = overall[away]
        sh_home = home_only[home]
        sa_away = away_only[away]

        pos_h = compute_position(overall, home, all_teams)
        pos_a = compute_position(overall, away, all_teams)
        pos_h_home = compute_position(home_only, home, all_teams)
        pos_a_away = compute_position(away_only, away, all_teams)

        giornata = estimate_giornata(sh, sa)

        # Quote e prob implicite
        try:
            b365h = float(row["B365H"])
            b365d = float(row["B365D"])
            b365a = float(row["B365A"])
            prob_1 = 1.0 / b365h if b365h > 0 else None
            prob_x = 1.0 / b365d if b365d > 0 else None
            prob_2 = 1.0 / b365a if b365a > 0 else None
        except (ValueError, TypeError):
            prob_1 = prob_x = prob_2 = None

        # Elo storici
        elo_home = get_elo_at_date(elo_dfs.get(home), date)
        elo_away = get_elo_at_date(elo_dfs.get(away), date)
        elo_diff = (elo_home - elo_away) if (elo_home is not None and elo_away is not None) else None

        feature_vector = {
            "lega": fd_code,
            "giornata": giornata,
            "posizione_classifica_casa": pos_h,
            "posizione_classifica_ospite": pos_a,
            "punti_casa": sh["points"],
            "punti_ospite": sa["points"],
            "differenza_punti": sh["points"] - sa["points"],
            "partite_giocate_casa": sh["played"],
            "partite_giocate_ospite": sa["played"],
            "gol_fatti_casa": sh["gf"],
            "gol_subiti_casa": sh["ga"],
            "gol_fatti_ospite": sa["gf"],
            "gol_subiti_ospite": sa["ga"],
            "posizione_classifica_casa_solo_casalinga": pos_h_home,
            "punti_casa_solo_casalinga": sh_home["points"],
            "posizione_classifica_ospite_solo_trasferta": pos_a_away,
            "punti_ospite_solo_trasferta": sa_away["points"],
            "prob_implicita_1": prob_1,
            "prob_implicita_X": prob_x,
            "prob_implicita_2": prob_2,
            "elo_casa": elo_home,
            "elo_ospite": elo_away,
            "elo_diff": elo_diff,
        }

        match_uid = f"{fd_code}_{stagione}_{date.strftime('%Y-%m-%d')}_{home.replace(' ', '')}_{away.replace(' ', '')}"

        doc = {
            "match_uid": match_uid,
            "lega": fd_code,
            "stagione": stagione,
            "data_partita": date,
            "home_team": home,
            "away_team": away,
            "feature_vector": feature_vector,
            "outcome": {
                "result_1x2": ftr,
                "goals_home": fthg,
                "goals_away": ftag,
                "ft_score": f"{fthg}-{ftag}",
            },
            "raw_data_sources": {
                "b365h": float(row.get("B365H", 0)) if pd.notna(row.get("B365H")) else None,
                "b365d": float(row.get("B365D", 0)) if pd.notna(row.get("B365D")) else None,
                "b365a": float(row.get("B365A", 0)) if pd.notna(row.get("B365A")) else None,
                "clubelo_home_at_date": elo_home,
                "clubelo_away_at_date": elo_away,
            },
            "ingested_at": datetime.utcnow(),
            "schema_version": SCHEMA_VERSION,
        }
        docs.append(doc)

        # Aggiorna stats DOPO aver salvato il vettore
        update_stats(overall[home], fthg, ftag)
        update_stats(overall[away], ftag, fthg)
        update_stats(home_only[home], fthg, ftag)
        update_stats(away_only[away], ftag, fthg)

    return docs, errors


def build_dataset_to_mongo() -> dict:
    """Processa tutti i CSV in cache e inserisce in MongoDB."""
    coll = db[MONGO_COLLECTION_MATCHES]

    # Indice unique su match_uid per dedup
    coll.create_index("match_uid", unique=True)
    coll.create_index([("lega", 1), ("stagione", 1), ("data_partita", 1)])

    csv_files = sorted(Path(CACHE_FOOTBALLDATA).glob("*.csv"))

    inserted = 0
    skipped_dup = 0
    skipped_no_data = 0
    errors = []

    pbar = tqdm(csv_files, desc="Build dataset", unit="csv")
    for csv_path in pbar:
        pbar.set_postfix_str(csv_path.stem)
        docs, file_errors = process_csv(csv_path)
        errors.extend(file_errors)

        if not docs:
            skipped_no_data += 1
            tqdm.write(f"  SKIP (no data): {csv_path.stem}")
            continue

        ins_count = 0
        dup_count = 0
        for doc in docs:
            try:
                coll.insert_one(doc)
                ins_count += 1
            except Exception as e:
                if "duplicate key" in str(e).lower():
                    dup_count += 1
                else:
                    errors.append(f"{csv_path.stem}: {e}")

        inserted += ins_count
        skipped_dup += dup_count

    pbar.close()

    return {
        "inserted": inserted,
        "skipped_dup": skipped_dup,
        "skipped_no_data": skipped_no_data,
        "errors": errors,
    }
