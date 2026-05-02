"""
Ingest dataset storico Pattern Match Engine.

Step 1.1 — Download CSV Football-Data per 10 leghe x 10 stagioni (100 file)
Step 1.2 — Download Elo storico per ogni squadra unica (CSV per team)
Step 1.3 — Build vettore feature 23-dim per ogni partita -> insert MongoDB

Output: collezione `historical__matches_pattern` (~33k documenti).

Cache locale CSV in `_cache_pattern_match/` per evitare ri-download.
Dataset finale e' SOLO MongoDB (vedi History_System_Engine.md sezione 7).

Uso:
    python -m ai_engine.pattern_match.ingest --step 1.1   # solo download FD
    python -m ai_engine.pattern_match.ingest --step 1.2   # solo download Elo
    python -m ai_engine.pattern_match.ingest --step 1.3   # solo build dataset
    python -m ai_engine.pattern_match.ingest              # tutti gli step
"""
from __future__ import annotations

import argparse
import sys
import time
from io import StringIO
from pathlib import Path

import requests
import pandas as pd
from tqdm import tqdm

# Auto-discovery config.db (walk-up del path) come gli altri script del progetto
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ai_engine.pattern_match.config import (
    LEAGUES, SEASONS,
    FOOTBALLDATA_URL_TEMPLATE, FD_REQUIRED_COLS,
    CLUBELO_TEAM_URL_TEMPLATE,
    CACHE_FOOTBALLDATA, CACHE_CLUBELO,
)
from ai_engine.pattern_match.clubelo_overrides import CLUBELO_OVERRIDES, NO_ELO_TEAMS
from ai_engine.pattern_match.build_dataset import build_dataset_to_mongo
from config import db


# ====================================================================
# Step 1.1 — Download CSV Football-Data
# ====================================================================

def download_footballdata_csvs(force: bool = False) -> dict:
    """
    Scarica i CSV per LEAGUES x SEASONS. Cache locale.

    Returns:
        dict con report: {ok, skipped, missing, errors}
    """
    CACHE_FOOTBALLDATA.mkdir(parents=True, exist_ok=True)
    report = {"ok": 0, "skipped": 0, "missing": [], "errors": []}

    pairs = [(l["fd_code"], s) for l in LEAGUES for s in SEASONS]

    pbar = tqdm(pairs, desc="FootballData CSV", unit="csv")
    for fd_code, season in pbar:
        cache_file = CACHE_FOOTBALLDATA / f"{fd_code}_{season}.csv"
        pbar.set_postfix_str(f"{fd_code} {season}")

        if cache_file.exists() and not force:
            report["skipped"] += 1
            continue

        url = FOOTBALLDATA_URL_TEMPLATE.format(stagione=season, lega=fd_code)
        try:
            r = requests.get(url, timeout=30)
            if r.status_code == 404:
                report["missing"].append((fd_code, season))
                tqdm.write(f"  NOT FOUND (404): {fd_code} {season}")
                continue
            r.raise_for_status()
            try:
                df = pd.read_csv(StringIO(r.text))
            except Exception as e:
                report["errors"].append((fd_code, season, f"parse: {e}"))
                tqdm.write(f"  ERROR parse {fd_code} {season}: {e}")
                continue
            missing_cols = [c for c in FD_REQUIRED_COLS if c not in df.columns]
            if missing_cols:
                report["errors"].append((fd_code, season, f"cols mancanti: {missing_cols}"))
                tqdm.write(f"  WARN cols mancanti {fd_code} {season}: {missing_cols}")
            cache_file.write_text(r.text, encoding="utf-8")
            report["ok"] += 1
            time.sleep(0.3)  # rate limit
        except Exception as e:
            report["errors"].append((fd_code, season, str(e)))
            tqdm.write(f"  ERROR {fd_code} {season}: {e}")

    pbar.close()
    return report


# ====================================================================
# Step 1.2 — Download Elo storico per squadre uniche
# ====================================================================

def collect_unique_teams_from_cache() -> set[str]:
    """Estrae i nomi unici delle squadre da tutti i CSV scaricati."""
    teams = set()
    for csv_file in sorted(CACHE_FOOTBALLDATA.glob("*.csv")):
        try:
            df = pd.read_csv(csv_file)
            if "HomeTeam" in df.columns:
                teams.update(df["HomeTeam"].dropna().unique())
            if "AwayTeam" in df.columns:
                teams.update(df["AwayTeam"].dropna().unique())
        except Exception as e:
            print(f"[teams] errore {csv_file.name}: {e}")
    return teams


def get_team_aliases_from_db(fd_name: str) -> list[str]:
    """
    Cerca la squadra nella collezione `teams` e ritorna lista di candidati ClubElo.

    Strategy: cerca il nome FD in name/aliases/aliases_transfermarkt.
    Se trovato, restituisce [name, *aliases] come candidati.
    Sennò restituisce [fd_name] come fallback.
    """
    doc = db.teams.find_one({
        "$or": [
            {"name": fd_name},
            {"aliases": fd_name},
            {"aliases_transfermarkt": fd_name},
        ]
    })
    if not doc:
        return [fd_name]
    candidates = []
    name = doc.get("name")
    if name:
        candidates.append(name)
    aliases = doc.get("aliases") or []
    if isinstance(aliases, str):
        aliases = [aliases]
    candidates.extend(aliases)
    # Aggiungi anche fd_name per sicurezza
    if fd_name not in candidates:
        candidates.append(fd_name)
    # Dedup preservando ordine
    seen = set()
    unique = []
    for c in candidates:
        key = c.lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def try_clubelo_download(name: str) -> tuple[bool, str | None]:
    """
    Tenta download Elo per un nome (e variante senza spazi).
    Returns: (success, csv_text). csv_text e' None se fallito.
    """
    # ClubElo API vuole nomi senza spazi
    candidates = [name.replace(" ", ""), name]
    for cand in candidates:
        try:
            url = CLUBELO_TEAM_URL_TEMPLATE.format(team=cand)
            r = requests.get(url, timeout=20)
            if r.status_code == 200 and len(r.text.strip()) > 100:
                return True, r.text
        except Exception:
            continue
    return False, None


def download_clubelo_team_history(force: bool = False) -> dict:
    """
    Scarica storico Elo per ogni squadra unica.

    Strategy:
    1. Per ogni team Football-Data, cerca in `teams` collection
    2. Estrai i candidati (name + aliases)
    3. Prova ognuno su ClubElo finche' non trova match
    4. Salva il primo che funziona, traccia il nome usato

    Returns:
        dict con report: {ok, skipped, missing, errors, mapping_log}
    """
    CACHE_CLUBELO.mkdir(parents=True, exist_ok=True)
    teams_set = collect_unique_teams_from_cache()
    report = {"ok": 0, "skipped": 0, "missing": [], "errors": [], "mapping_log": {}}

    pbar = tqdm(sorted(teams_set), desc="ClubElo download", unit="team")
    for fd_team in pbar:
        cache_file = CACHE_CLUBELO / f"{fd_team.replace(' ', '_').replace('/', '_')}.csv"
        pbar.set_postfix_str(fd_team[:30])

        if cache_file.exists() and not force:
            report["skipped"] += 1
            continue

        # Squadre note senza Elo: skip immediato
        if fd_team in NO_ELO_TEAMS:
            report["missing"].append(fd_team)
            tqdm.write(f"  SKIP (no Elo): {fd_team}")
            continue

        # Override locale ha priorita massima
        success_name = None
        csv_text = None
        candidates_tried = []

        if fd_team in CLUBELO_OVERRIDES:
            override = CLUBELO_OVERRIDES[fd_team]
            candidates_tried.append(override)
            success, txt = try_clubelo_download(override)
            if success:
                success_name = override
                csv_text = txt

        # Fallback su DB aliases se override non c'era o ha fallito
        if not success_name:
            db_candidates = get_team_aliases_from_db(fd_team)
            for cand in db_candidates:
                if cand in candidates_tried:
                    continue
                candidates_tried.append(cand)
                success, txt = try_clubelo_download(cand)
                if success:
                    success_name = cand
                    csv_text = txt
                    break

        if not success_name:
            report["missing"].append(fd_team)
            tqdm.write(f"  NOT FOUND: {fd_team}  (provati: {candidates_tried})")
            continue

        cache_file.write_text(csv_text, encoding="utf-8")
        report["ok"] += 1
        report["mapping_log"][fd_team] = success_name
        if success_name != fd_team:
            tqdm.write(f"  OK: {fd_team:30s} via '{success_name}'")
        time.sleep(0.2)

    pbar.close()
    return report


# ====================================================================
# Main
# ====================================================================

def main():
    parser = argparse.ArgumentParser(description="Ingest dataset Pattern Match Engine")
    parser.add_argument("--step", choices=["1.1", "1.2", "1.3"], help="Singolo step")
    parser.add_argument("--force", action="store_true", help="Re-download anche se cache presente")
    args = parser.parse_args()

    if args.step in (None, "1.1"):
        print("=" * 70)
        print("STEP 1.1 — Download Football-Data CSV (100 file)")
        print("=" * 70)
        rep = download_footballdata_csvs(force=args.force)
        print(f"\nRiepilogo Step 1.1: ok={rep['ok']} skipped={rep['skipped']} missing={len(rep['missing'])} errors={len(rep['errors'])}")
        if rep["missing"]:
            print(f"Mancanti (404): {rep['missing']}")
        if rep["errors"]:
            print(f"Errori (primi 5): {rep['errors'][:5]}")

    if args.step in (None, "1.2"):
        print("\n" + "=" * 70)
        print("STEP 1.2 — Download Elo storico ClubElo per squadra")
        print("=" * 70)
        rep = download_clubelo_team_history(force=args.force)
        print(f"\nRiepilogo Step 1.2: ok={rep['ok']} skipped={rep['skipped']} missing={len(rep['missing'])} errors={len(rep['errors'])}")
        if rep["missing"]:
            print(f"Squadre senza Elo (primi 20): {rep['missing'][:20]}")

    if args.step in (None, "1.3"):
        print("\n" + "=" * 70)
        print("STEP 1.3 — Build vettore feature + insert MongoDB")
        print("=" * 70)
        rep = build_dataset_to_mongo()
        print(f"\nRiepilogo Step 1.3: inserted={rep['inserted']} skipped_dup={rep['skipped_dup']} skipped_no_data={rep['skipped_no_data']} errors={len(rep['errors'])}")
        if rep["errors"]:
            print(f"Errori (primi 5): {rep['errors'][:5]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
